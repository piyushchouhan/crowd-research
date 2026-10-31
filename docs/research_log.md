# Research log

Dated record of what was done and decided, and why. Newest last. The paper draft
(`paper_draft.md`) uses this as its source.

## 2026-10-25 — Start
- Question: can 1–5% of attendees' phone pings warn of a crush 5–10 min ahead, and do
  alerts or re-routing reduce density? Target events: Kumbh (Nashik 2027, Ujjain 2028),
  temples, melas.
- Proof by simulation before building any product.
- Roadmap: 0 setup · 1 literature · 2 validate model (±15%) · 3 Sangam scenarios incl.
  29 Jan 2025 · 4 synthetic pings (main result) · 5 interventions · 6 GPU scale-up
  (optional) · 7 field pilot · 8 write-up.

## 2026-10-26 — Geometry (sangam-command)
- Traced on Sentinel-2 2025-01-27: 25 sectors, river mask, 27 pontoons, 46 approaches,
  28 mela roads; OSM stations and roads; a connected walking network (~102k nodes).
- Widths: mela roads 5.5 m measured on Google satellite; pontoons 5 m estimated; OSM by
  tag, then lanes, then class. Every edge records `width_source`.

## 2026-10-27 — Repos public
- Both repos published under MIT. sangam-command history squashed to one commit, so that a
  copyrighted newspaper map and a hosting config are not distributed. Commits use the
  GitHub noreply email.

## 2026-10-31 — Phase 1 literature (done by the user)
- Wirz et al. 2013 (ETH, London 2011): <1% of users, r = 0.83, RMSE 0.36/m² at a 55 m
  kernel. Only 0.2–2.7/m²; estimates current density, no forecasting. Lists sensitivity to
  the share of app users as future work, which is our Phase 4.
- Gayathri et al. 2018 (IISc, Ujjain 2016): 95% of pilgrims in groups; serpentine chains;
  gated ghat entry causes stop-and-go waves moving backwards; people at the rear do not
  know the front has stopped. Our model has no groups or pushing.

## 2026-10-31 — Phase 0: width → capacity, config (PR #1)
- Each corridor is now buffered by its own map width instead of the old 15/25 m guesses.
  Walkable area went from 15.4 ha to 8.57 ha.
- Capacity = width × 1.3 people/m/s. `run_sim.py` reports demand against capacity for
  each gate.
- All assumptions moved to `config/sim.json`.

## 2026-10-31 — Phase 2: validation against Jülich data
- Data: 2006 Caserne bottleneck (10 widths) and 2009 Hermes unidirectional corridor
  (29 runs), CC BY 4.0. Geometry taken from the archive's WKT.
- Measured real and simulated trajectories with the same PedPy functions.
- **Default model failed:** bottleneck flow about half the real flow at every width (0/10
  within ±15%). Permanent clogs at 0.9–1.0 m and at corridor exits of 0.7–0.8 m.
- **Decision: count a deadlock as a fail.** Real crowds do not stay stuck for good, and the
  flow from a clogged run is not meaningful.
- **Decision: validate with the Jülich population's speed** N(1.34, 0.26), while Sangam keeps
  its pilgrim speed. Desired speed belongs to the population, not to the model. With
  v₀ = 1.2, the corridor speeds stayed ~30% low because the model has no overtaking.
- **Decision: compare speed–density only at ≥ 0.5/m².** Below that, 1–2 people in the area
  make the Voronoi estimates meaningless, for real and simulated data alike.
- Calibration: two grids over (T, r), tuned on 5 widths and 7 corridor runs; the other
  5 widths were held out.
- **Result: T = 0.6 s, r = 0.175 m.** 10/10 widths within ±15% (mean 8%, max 14%), including
  the held-out widths. Speed–density error 16%. Written to `config/sim.json`.
- Found: the real specific flow is 1.86/m/s, against the configured capacity of 1.3/m/s. Left
  unchanged pending the user's decision.
- Operational: a full validation with kept trajectories wrote ~5 GB and filled the disk.
  The script now deletes trajectories after analysis unless `--keep-sim` is given.

## Open decisions
- Change `capacity.specific_flow_pms` from 1.3 to the measured ~1.86?
- Merge PR #1 and the Phase 2 work.
- Next phase (3: Sangam scenarios) not started.
