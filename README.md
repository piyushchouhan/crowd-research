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
| `scripts/validate_juelich.py` | Model validation against Jülich bottleneck and corridor experiments |
| `docs/paper_draft.md` | Paper draft: methods, validation results, limitations, references |
| `docs/research_log.md` | Dated log of what was done and decided |

## Run

```sh
python3 -m venv .venv && .venv/bin/pip install jupedsim shapely pyproj numpy matplotlib pedpy
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
- Model: JuPedSim `CollisionFreeSpeedModel`, radius 0.175 m, time gap 0.6 s (calibrated on
  Jülich data, see Validation), desired speed N(1.2, 0.2) m/s (pilgrims; a guess, not measured).
  No groups, no pushing forces.
- Reaching the goal circle = bathed and gone. Outbound walkers start on the ghat at
  `--outflow-frac` × inflow and pick a random gate.
- Gate shares are guesses (`gate_weights`).
- Thresholds: 4 people/m² = free walking stops, 6 people/m² = crush risk.
- Runs in `out/in*_out60` were made with the old 15/25 m widths and are stale.

## Validation (Jülich experiments)

`scripts/validate_juelich.py` re-runs two Jülich lab experiments in JuPedSim with the
model from `config/sim.json` and measures real and simulated trajectories with the
same PedPy functions. The data is in `data/juelich/` (see its README to download).

```sh
cd scripts && ../.venv/bin/python validate_juelich.py --dataset all --seeds 5 --name check \
  --set agents.desired_speed_mps.mean=1.34 agents.desired_speed_mps.sd=0.26
```

- **Bottleneck flow** (2006 Caserne, widths 0.9–2.5 m): flow J through a line in the
  bottleneck, steady part of the N–t curve. Pass = within ±15% of the real flow at every
  width, and no run where people stay stuck for good.
- **Speed–density** (2009 Hermes unidirectional corridor, 29 runs): Voronoi density and
  speed in a 2 m area mid-corridor, compared per 0.25/m² bin above 0.5/m².

Validation uses the Jülich participants' free speed, N(1.34, 0.26) m/s (Weidmann);
the Sangam runs keep their own pilgrim speed.

| Model | Bottleneck widths within ±15% | Specific flow (real 1.86 /m/s) | Corridor speed error |
|---|---|---|---|
| Default (T = 1.0 s, r = 0.2 m, v0 1.2) | 0/10, flow about half, clogs at 0.9–1.0 m | 0.99 | 27–74% low |
| **Calibrated (T = 0.6 s, r = 0.175 m)** | **10/10, mean 8%, worst −14%** | **1.71** | **16% mean** |

Calibration: grid over time gap and radius, tuned on widths 0.9/1.2/1.6/2.0/2.5 m and
7 corridor runs (2 seeds), checked on all 10 widths and 29 corridor runs (5 seeds).
Results in `out/validation/<name>/` (`summary.json`, `flow_vs_width.png`,
`nt_curves.png`, `speed_density.png`).

What it does **not** show:
- The model still clogs for good at the narrowest corridor exits (0.7–0.8 m) in some seeds;
  real people never did. Sangam corridors are 5 m and wider.
- Corridor speeds are ~30% low near 0.6/m² and ~35% high near 3.6/m²; the real data stops
  at ~4/m², so nothing above that, including 6/m² crush densities, is validated.
- Participants were German soldiers and adults; Indian pilgrims, groups and pushing are not
  in the data or the model. This checks the mechanism, not a Kumbh calibration.
- Real bottleneck flow is ~1.86 people/m/s, above the 1.3 in `capacity.specific_flow_pms`.
  That config value is unchanged.
- In the corridor setup 2–3 agents sometimes stick at the thin entrance walls; they are
  outside the measurement area.

Sources: geometry traced from Copernicus Sentinel-2 (2025-01-27) in the Sangam Command
project, © OpenStreetMap contributors (ODbL) where used.

## Licence

Code is MIT (see `LICENSE`). Sentinel-2 data: modified Copernicus Sentinel data 2024–2025. Hobby research, not an operational safety system; simulation numbers are uncalibrated.
