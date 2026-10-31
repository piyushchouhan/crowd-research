# Crowd research: Sangam nose

Research sandbox for a crowd early-warning system. The question it answers first:
**at what inflow does the Sangam nose become dangerous, and where?** Later runs
will test whether sparse phone pings (1–5% of people) can detect it in time.

## Layout

| Path | What |
|---|---|
| `data/sentinel2/` | Sentinel-2 true-colour crops, Oct 2024 + Jan–Feb 2025 (Copernicus, free) |
| `data/hotspot/sangam_nose.json` | Walkable area, bathing ghat, goal and gates in local metres (origin in UTM 44N) |
| `scripts/build_hotspot.py` | Builds the hotspot from the Sangam Command traced layers (a local checkout of [sangam-command](https://github.com/piyushchouhan/sangam-command); path set in `config/sim.json`) |
| `scripts/run_sim.py` | JuPedSim simulation: inbound to the ghat + outbound counter-flow |
| `scripts/analyze.py` | Density / speed / crowd pressure per 4 m cell, plots |
| `out/<run>/` | Snapshots (1 s), `run.json`, `metrics.json`, PNGs |

## Run

```sh
python3 -m venv .venv && .venv/bin/pip install jupedsim shapely pyproj numpy matplotlib
.venv/bin/python scripts/build_hotspot.py
.venv/bin/python scripts/run_sim.py --inflow 3000 --minutes 20
cd scripts && ../.venv/bin/python analyze.py in3000_out60
```

## Config

All assumptions live in `config/sim.json`; scripts read it through `scripts/config.py`.
`CROWD_MAP_DIR` overrides `map_data_dir` (path to sangam-command's `data/`).
Change the config, then re-run `build_hotspot.py` before simulating.

## Assumptions (change before trusting numbers)

- Widths come from the map: each corridor uses its feature's `approx_width_m` and
  `width_source` (mela roads and bank lanes 5.5 m measured on Google satellite, pontoons
  5 m estimated). Missing widths fall back to `default_width_m`; `width_override_m`
  forces one width per kind. Widths per corridor are listed in `sangam_nose.json`.
- Capacity = width × 1.3 people/m/s (`capacity.specific_flow_pms`, free-flow value).
  `build_hotspot.py` prints each gate's capacity; `run_sim.py` prints inbound demand
  against it and saves it as `gate_load` in `run.json`. Over capacity is allowed, so queues form.
  A gate fed by several corridors sums their widths, which can overcount where they overlap.
- Only the plated roads count as walkable; open sand beside them does not. This is
  probably too narrow on the nose itself.
- Model: JuPedSim `CollisionFreeSpeedModel`, radius 0.2 m, desired speed N(1.2, 0.2) m/s.
  Not yet calibrated against Jülich bottleneck data; no groups, no pushing forces.
- Reaching the goal circle = bathed and gone. Outbound walkers start on the ghat at
  `--outflow-frac` × inflow and pick a random gate.
- Gate shares are guesses (`gate_weights`).
- Thresholds: 4 people/m² = free walking stops, 6 people/m² = crush risk.
- Runs in `out/in*_out60` were made with the old 15/25 m widths and are stale.

Sources: geometry traced from Copernicus Sentinel-2 (2025-01-27) in the Sangam Command
project, © OpenStreetMap contributors (ODbL) where used.

## Licence

Code is MIT (see `LICENSE`). Sentinel-2 data: modified Copernicus Sentinel data 2024–2025. Hobby research, not an operational safety system; simulation numbers are uncalibrated.
