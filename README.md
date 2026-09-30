# Perdix — Dive Log Visualization

A static web viewer for dive computer logs, built around exports from a
Shearwater Perdix AI (Shearwater Cloud).

## Structure

```
raw/         Original exports from Shearwater Cloud (CSV, UDDF, XML, ZXU, sqlite db)
scripts/     parse_dive.py — converts a Shearwater Cloud db export into data/dives/<id>.json
data/        Parsed dive data consumed by the web viewer
  dives.json       Index of all dives (id, site, dates, depth/time summary)
  dives/<id>.json  Full per-dive sample data (depth, gas, tank pressure, etc.)
web/         Static web viewer (index.html) — reads data/ and renders dive profiles
```

## Viewing the log

The viewer is a single static HTML file with no build step.

```bash
python3 -m http.server 8123
```

Then open `http://localhost:8123/web/`.

## Adding a new dive

1. In Shearwater Cloud, sync the dive and fill in its details (site, buddy,
   tanks), then export the database into `raw/`. The database is the only file
   needed — it holds both the logbook details and the full dive log.
2. Run the parser:

   ```bash
   python3 scripts/parse_dive.py
   ```

   This reads the most recently modified `.db` in `raw/` (or pass a path), and
   writes `data/dives/<id>.json` for every dive in it plus `data/dives.json`.
   Reload the viewer to see the new dive.

The per-dive samples are stored in the database's `log_data` table as a
gzip-compressed Shearwater Petrel Native Format (`sw-pnf`) log of 32-byte
records, which `parse_dive.py` decodes. Its decoding was checked field by field
against Shearwater Cloud's CSV export. The CSV, UDDF, XML and ZXU exports are
not needed.

## Deploying

The viewer is hosted on the divelog container (`http://192.168.200.124/`).
To parse the newest export and publish it in one step:

```bash
scripts/deploy.sh
```

Only `web/` and `data/` are sent; `raw/` stays local. Run
`scripts/deploy.sh --help` for options (parse a specific export, skip the
parser, or preview with `--dry-run`).

## Notes

- Tank pressures are stored and displayed in bar (converted from the psi values
  in the raw Shearwater log).
- Only metric logs are supported; the parser stops on a dive logged in imperial
  units.
- `raw/` contains original exports as downloaded from Shearwater Cloud, kept for
  reference/reprocessing. This repo is private — be mindful of what you share
  outside it, since these files can include personal dive log details.
