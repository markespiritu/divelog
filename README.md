# Perdix — Dive Log Visualization

A static web viewer for dive computer logs, built around exports from a
Shearwater Perdix AI (Shearwater Cloud).

## Structure

```
raw/         Original exports from Shearwater Cloud (CSV, UDDF, XML, ZXU, sqlite db)
scripts/     parse_dive.py — converts a raw CSV/db export into data/dives/<id>.json
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

1. Export the dive from Shearwater Cloud as CSV, and export the Shearwater Cloud
   sqlite database, into `raw/`.
2. Run the parser:

   ```bash
   python3 scripts/parse_dive.py raw/<your-export>.csv.csv
   ```

3. This writes `data/dives/<id>.json` and updates `data/dives.json`. Reload the
   viewer to see the new dive.

## Notes

- Tank pressures are stored and displayed in bar (converted from the psi values
  in the raw Shearwater export).
- `raw/` contains original exports as downloaded from Shearwater Cloud, kept for
  reference/reprocessing. This repo is private — be mindful of what you share
  outside it, since these files can include personal dive log details.
