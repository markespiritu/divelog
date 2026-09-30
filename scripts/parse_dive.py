#!/usr/bin/env python3
"""Parse a Shearwater Cloud database export into data/dives/<id>.json.

Every dive in the database is parsed: the dive log itself comes from the
compressed Petrel Native Format (sw-pnf) blob in log_data, and the logbook
details (site, buddy, tanks, ...) from dive_details.

Usage: python3 scripts/parse_dive.py [raw/<export>.db]
       (defaults to the most recently modified .db in raw/)
"""
import gzip
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"

PSI_PER_BAR = 14.5037738

# Petrel Native Format: the log is a sequence of 32-byte records, the first
# byte of each giving its type.
RECORD_SIZE = 32
REC_SAMPLE = 0x01
REC_SAMPLE_EXT = 0xE1  # follows each sample; holds tank 3/4 pressures
REC_OPENING = 0x10  # 0x10..0x19: settings at the start of the dive
REC_CLOSING = 0x20  # 0x20..0x29: the same, at the end of the dive

# Sample status byte flags.
STATUS_GAS_SWITCH_NEEDED = 0x01
STATUS_OPEN_CIRCUIT = 0x10

# Placeholder values in place of a reading, e.g. 0xFFFD/0xFFFE for a tank
# transmitter out of contact for 30s/90s, or 0xFFF9 while waiting for data.
NO_VALUE_16 = 0xFFF0
NO_VALUE_8 = 0xEF  # gas time remaining: 0xF8.. codes, 0xFC while in deco


def u16(record, offset):
    return record[offset] << 8 | record[offset + 1]


def u24(record, offset):
    return record[offset] << 16 | u16(record, offset + 1)


def u32(record, offset):
    return u16(record, offset) << 16 | u16(record, offset + 2)


def s8(value):
    return value - 256 if value > 127 else value


def timestamp(seconds):
    """Shearwater stores local time as if it were a UTC epoch."""
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def tank_pressure_bar(raw):
    # Tank pressure in 2 psi units; the top nibble is not part of the value.
    if raw >= NO_VALUE_16:
        return None
    return round((raw & 0x0FFF) * 2 / PSI_PER_BAR, 1)


def read_pnf(blob):
    """Decompress a log_data blob: a 4-byte little-endian length, then gzip."""
    size = int.from_bytes(blob[:4], "little")
    data = gzip.decompress(blob[4:])
    if len(data) != size:
        raise ValueError(f"expected {size} bytes of log data, got {len(data)}")
    return [data[i : i + RECORD_SIZE] for i in range(0, len(data), RECORD_SIZE)]


def parse_sample(t, rec, ext):
    status = rec[12]
    first_stop_depth = u16(rec, 3)
    in_deco = first_stop_depth > 0
    sac = u16(rec, 30)
    return {
        "t": t,
        "depth": u16(rec, 1) / 10,
        "firstStopDepth": first_stop_depth,
        # Byte 10 is the first stop time while in deco, and the NDL otherwise.
        "firstStopTimeMin": rec[10] if in_deco else 0,
        "timeToSurfaceMin": u16(rec, 5),
        "ppo2": rec[7] / 100,
        "fractionO2": rec[8] / 100,
        "fractionHe": rec[9] / 100,
        "ndlMin": 0 if in_deco else rec[10],
        "circuitMode": 1 if status & STATUS_OPEN_CIRCUIT else 0,
        "waterTempC": s8(rec[14]),
        "gasSwitchNeeded": bool(status & STATUS_GAS_SWITCH_NEEDED),
        "batteryVoltage": u16(rec, 17) / 100,
        "tankPressureBar": [
            tank_pressure_bar(u16(rec, 28)),
            tank_pressure_bar(u16(rec, 20)),
            tank_pressure_bar(u16(ext, 1)) if ext else None,
            tank_pressure_bar(u16(ext, 3)) if ext else None,
        ],
        "gasTimeRemainingMin": None if rec[22] >= NO_VALUE_8 else rec[22],
        # 0 when there is no reading yet.
        "sacRate": None if sac == 0 or sac >= NO_VALUE_16 else sac / 100,
    }


def parse_log(records):
    by_type = {}
    for rec in records:
        by_type.setdefault(rec[0], rec)
    opening = [by_type.get(REC_OPENING + i) for i in range(10)]
    closing = [by_type.get(REC_CLOSING + i) for i in range(10)]
    if not opening[0] or not closing[0]:
        raise ValueError("log has no opening/closing records")

    interval_sec = u16(opening[5], 23) / 1000
    samples = []
    for i, rec in enumerate(records):
        if rec[0] != REC_SAMPLE:
            continue
        nxt = records[i + 1] if i + 1 < len(records) else None
        ext = nxt if nxt and nxt[0] == REC_SAMPLE_EXT else None
        samples.append(parse_sample(round(len(samples) * interval_sec), rec, ext))

    # A tank slot that reads 0 for the whole dive has no transmitter behind it.
    for i in range(4):
        if all(s["tankPressureBar"][i] in (0, None) for s in samples):
            for s in samples:
                s["tankPressureBar"][i] = None

    return {
        "startTime": u32(opening[0], 12),
        "endTime": u32(closing[0], 12),
        "gfMin": opening[0][4],
        "gfMax": opening[0][5],
        "surfaceIntervalMin": u16(opening[0], 6),
        "maxDepthM": u16(closing[0], 4) / 10,
        "maxTimeSec": u24(closing[0], 6),
        "startCns": opening[0][11],
        "endCns": closing[0][11],
        "startBatteryVoltage": u16(opening[4], 5) / 100,
        "endBatteryVoltage": u16(closing[4], 5) / 100,
        "samples": samples,
    }


def parse_coordinates(details, site):
    gnss = details.get("GnssEntryLocation")
    if gnss:
        try:
            loc = json.loads(gnss)
        except (json.JSONDecodeError, TypeError):
            loc = {}
        lat, lon = loc.get("Latitude"), loc.get("Longitude")
        if lat is not None and lon is not None:
            return {"lat": lat, "lon": lon}
    if site.get("Latitude") is not None:
        return {"lat": site.get("Latitude"), "lon": site.get("Longitude")}
    return None


def parse_tanks(details):
    """Tank name and breathing mix per transmitter, from Shearwater Cloud's TankProfileData.

    Returns a list indexed like tankPressureBar (tank 1..4); None for slots
    with no transmitter paired.
    """
    try:
        profile = json.loads(details.get("TankProfileData") or "")
    except json.JSONDecodeError:
        return []
    tanks = [None] * 4
    for entry in profile.get("TankData") or []:
        transmitter = entry.get("DiveTransmitter")
        if not transmitter:
            continue
        index = transmitter.get("TankIndex")
        if index is None or not 0 <= index < len(tanks):
            continue
        gas = entry.get("GasProfile") or {}
        tanks[index] = {
            "name": transmitter.get("Name") or f"T{index + 1}",
            "o2Percent": gas.get("O2Percent"),
            "hePercent": gas.get("HePercent"),
        }
    return tanks


def computer_model(cur, details):
    serial = details.get("SerialNumber")
    cur.execute("select JsonData from StoredDiveComputer")
    for (data,) in cur.fetchall():
        try:
            info = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
        if serial and info.get("SerialNumber") == int(serial, 16):
            return info.get("DeviceName")
    # File names look like "Perdix AI[3343DB3D]#260 2026-9-26 8-33-13.swlogzp".
    return (details.get("FileName") or "").split("[")[0] or None


def parse_dive(cur, details):
    cur.execute(
        "select format, data_bytes_1, data_bytes_3, calculated_values_from_samples"
        " from log_data where log_id = ?",
        (details["DiveId"],),
    )
    row = cur.fetchone()
    if not row or row["format"] != "sw-pnf" or not row["data_bytes_1"]:
        return None

    try:
        log_info = json.loads(row["data_bytes_3"] or "{}")
    except json.JSONDecodeError:
        log_info = {}
    if log_info.get("UnitSystem", 0) != 0:
        raise ValueError(f"dive {details['DiveNumber']}: imperial logs are not supported yet")

    log = parse_log(read_pnf(row["data_bytes_1"]))

    site = {}
    if details.get("Site"):
        cur.execute("select * from dive_site where Name = ?", (details["Site"],))
        site_row = cur.fetchone()
        if site_row:
            site = dict(site_row)

    # Summary values Shearwater Cloud derives from the samples, e.g. EndGF99.
    try:
        calculated = json.loads(row["calculated_values_from_samples"] or "{}")
    except json.JSONDecodeError:
        calculated = {}

    dive_number = int(details["DiveNumber"])
    return {
        "id": str(dive_number),
        "diveNumber": dive_number,
        "computer": {
            "model": computer_model(cur, details),
            "serial": details.get("SerialNumber"),
        },
        "startDate": details.get("DiveDate") or timestamp(log["startTime"]),
        "endDate": timestamp(log["endTime"]),
        "location": details.get("Location"),
        "site": details.get("Site"),
        "buddy": details.get("Buddy"),
        "notes": details.get("Notes"),
        "coordinates": parse_coordinates(details, site),
        "gfMin": log["gfMin"],
        "gfMax": log["gfMax"],
        # Shearwater Cloud's GF99 summary for the dive, shown at the surfacing point.
        "endGf99": calculated.get("EndGF99"),
        "surfaceIntervalMin": log["surfaceIntervalMin"],
        "maxDepthM": log["maxDepthM"],
        "maxTimeSec": log["maxTimeSec"],
        "startBatteryVoltage": log["startBatteryVoltage"],
        "endBatteryVoltage": log["endBatteryVoltage"],
        "startCns": log["startCns"],
        "endCns": log["endCns"],
        "tanks": parse_tanks(details),
        "samples": log["samples"],
    }


def main():
    args = sys.argv[1:]
    if args:
        db_path = Path(args[0])
    else:
        candidates = sorted(RAW.glob("*.db"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            print("No .db files found in raw/", file=sys.stderr)
            sys.exit(1)
        db_path = candidates[-1]

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("select * from dive_details order by DiveDate")
    all_details = [dict(r) for r in cur.fetchall()]

    (DATA / "dives").mkdir(parents=True, exist_ok=True)

    index = []
    for details in all_details:
        dive = parse_dive(cur, details)
        if dive is None:
            print(f"Skipping dive {details.get('DiveNumber')}: no sw-pnf log data", file=sys.stderr)
            continue
        out_path = DATA / "dives" / f"{dive['id']}.json"
        out_path.write_text(json.dumps(dive, indent=2))
        index.append(
            {
                "id": dive["id"],
                "diveNumber": dive["diveNumber"],
                "startDate": dive["startDate"],
                "site": dive["site"],
                "location": dive["location"],
                "maxDepthM": dive["maxDepthM"],
                "maxTimeSec": dive["maxTimeSec"],
                "file": f"dives/{dive['id']}.json",
            }
        )
        print(f"Wrote {out_path} ({len(dive['samples'])} samples)")
    con.close()

    index.sort(key=lambda d: d["startDate"] or "")
    (DATA / "dives.json").write_text(json.dumps(index, indent=2))
    print(f"Wrote {DATA / 'dives.json'} ({len(index)} dives) from {db_path.name}")


if __name__ == "__main__":
    main()
