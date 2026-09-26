#!/usr/bin/env python3
"""Parse a Shearwater Cloud CSV export (+ matching sqlite db) into data/dives/<id>.json.

Usage: python3 scripts/parse_dive.py raw/*.csv.csv
"""
import csv
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"


def num_or_none(value):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return None  # placeholder strings like "No comms for 90s +"


def bool_or_none(value):
    if value is None or value.strip() == "":
        return None
    return value.strip().lower() == "true"


def find_dive_id_from_filename(csv_path: Path) -> str:
    m = re.search(r"#(\d+)", csv_path.name)
    return m.group(1) if m else csv_path.stem


def load_sqlite_metadata(dive_number: str):
    db_candidates = list(RAW.glob("*.db"))
    if not db_candidates:
        return {}
    con = sqlite3.connect(str(db_candidates[0]))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "select * from dive_details where DiveNumber = ?", (dive_number,)
    )
    row = cur.fetchone()
    details = dict(row) if row else {}

    site = {}
    if details.get("Site"):
        cur.execute("select * from dive_site where Name = ?", (details["Site"],))
        site_row = cur.fetchone()
        if site_row:
            site = dict(site_row)
    con.close()
    return {"details": details, "site": site}


def parse_csv(csv_path: Path):
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    summary_header, summary_values = rows[0], rows[1]
    summary = dict(zip(summary_header, summary_values))

    record_header = rows[2]
    record_rows = rows[3:]

    samples = []
    for r in record_rows:
        rec = dict(zip(record_header, r))
        samples.append(
            {
                "t": num_or_none(rec.get("Time (sec)")),
                "depth": num_or_none(rec.get("Depth")),
                "firstStopDepth": num_or_none(rec.get("First Stop Depth")),
                "timeToSurfaceMin": num_or_none(rec.get("Time To Surface (min)")),
                "ppo2": num_or_none(rec.get("Average PPO2")),
                "fractionO2": num_or_none(rec.get("Fraction O2")),
                "fractionHe": num_or_none(rec.get("Fraction He")),
                "ndlMin": num_or_none(rec.get("Current NDL")),
                "circuitMode": num_or_none(rec.get("Current Circuit Mode")),
                "waterTempC": num_or_none(rec.get("Water Temp")),
                "gasSwitchNeeded": bool_or_none(rec.get("Gas Switch Needed")),
                "batteryVoltage": num_or_none(rec.get("Battery Voltage")),
                "tankPressurePsi": [
                    num_or_none(rec.get("Tank 1 pressure (PSI)")),
                    num_or_none(rec.get("Tank 2 pressure (PSI)")),
                    num_or_none(rec.get("Tank 3 pressure (PSI)")),
                    num_or_none(rec.get("Tank 4 pressure (PSI)")),
                ],
                "sacRate": num_or_none(rec.get("SAC Rate (2 minute avg)")),
                "ascentRate": num_or_none(rec.get("Ascent Rate")),
                "safeAscentDepth": num_or_none(rec.get("Safe Ascent Depth")),
                "co2mbar": num_or_none(rec.get("CO2mbar")),
            }
        )

    dive_number = summary.get("Dive Number", "").strip()
    meta = load_sqlite_metadata(dive_number)
    details = meta.get("details", {})
    site = meta.get("site", {})

    dive = {
        "id": dive_number or find_dive_id_from_filename(csv_path),
        "diveNumber": num_or_none(dive_number),
        "computer": {
            "model": summary.get("Product"),
            "serial": summary.get("Computer Serial Number"),
            "firmware": num_or_none(summary.get("Computer Firmware Version")),
        },
        "startDate": details.get("DiveDate") or summary.get("Start Date"),
        "endDate": summary.get("End Date"),
        "location": details.get("Location"),
        "site": details.get("Site"),
        "buddy": details.get("Buddy"),
        "notes": details.get("Notes"),
        "coordinates": (
            {"lat": site.get("Latitude"), "lon": site.get("Longitude")}
            if site.get("Latitude") is not None
            else None
        ),
        "gfMin": num_or_none(summary.get("GF Minimum")),
        "gfMax": num_or_none(summary.get("GF Maximum")),
        "surfaceIntervalMin": num_or_none(summary.get("Surface Interval (min)")),
        "maxDepthM": num_or_none(summary.get("Max Depth")),
        "maxTimeSec": num_or_none(summary.get("Max Time")),
        "decoModel": summary.get("Deco Model"),
        "vpmbConservatism": summary.get("VPM-B Conservatism"),
        "startBatteryVoltage": num_or_none(summary.get("Start Battery Voltage")),
        "endBatteryVoltage": num_or_none(summary.get("End Battery Voltage")),
        "startCns": num_or_none(summary.get("Start CNS %")),
        "endCns": num_or_none(summary.get("End CNS")),
        "samples": samples,
    }
    return dive


def main():
    args = sys.argv[1:]
    csv_paths = [Path(p) for p in args] if args else list(RAW.glob("*.csv.csv"))
    if not csv_paths:
        print("No CSV files found in raw/", file=sys.stderr)
        sys.exit(1)

    DATA.mkdir(exist_ok=True)
    (DATA / "dives").mkdir(exist_ok=True)

    index = []
    for csv_path in csv_paths:
        dive = parse_csv(csv_path)
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

    index.sort(key=lambda d: d["startDate"] or "")
    (DATA / "dives.json").write_text(json.dumps(index, indent=2))
    print(f"Wrote {DATA / 'dives.json'} ({len(index)} dives)")


if __name__ == "__main__":
    main()
