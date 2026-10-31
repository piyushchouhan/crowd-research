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

## 2026-10-31 — Phase 3 start: scenario tooling, and a counter-flow problem
- Added scenario presets (`normal_day` 250–1500/min, `mauni_amavasya` 2000–6000/min; the real
  inflow at the nose is unknown, so each is swept), a danger map in `analyze.py` (when each 4 m
  cell first reaches 4 and 6/m²), and `scripts/sweep.py`.
- First `normal_day` runs showed three problems, so the sweep was stopped:
  1. 20 min is too short: walking from the gates to the nose takes ~15 min, so runs end while
     the area is still filling.
  2. Outbound walkers leave the ghat from minute 0 at 60% of inflow, before anyone has bathed.
  3. At 500/min the only "danger" was one spot on the west bank lane, ~200 m north of the
     nose, where inbound and outbound people met head-on on a 5.5 m lane and jammed (504
     people within 8 m, 37% stopped, mean speed 0.1 m/s). The lane is not a geometry pinch.
- **Two-way validation** (Jülich 2009 Hermes, symmetric and asymmetric two-way corridors,
  18 runs × 3 seeds, calibrated model, v₀ 1.34): **0/18 runs within ±15%**. Flow is 17–77% too
  low (mean 34%; worst −66 to −77% in the busiest runs) and 11/18 runs deadlock. Speed–density
  error is 16%, the same as one-way. Real people form lanes; the model's agents meet head-on
  and block each other.
- **Conclusion:** CollisionFreeSpeed, as calibrated, is valid for one-way flow only.
  Counter-flow hotspots in Sangam runs cannot be trusted. Some deadlocks happen at narrow
  entrances (≤ 0.65 m), the same narrow-opening clog seen before.

## 2026-10-31 — Scope change and model comparison for two-way flow
- **Scope (user decision):** the goal is a general crowd model for fairs and gatherings
  (analytics and early warning). The Sangam is a test site; there will be no 29 January 2025
  reconstruction. General mechanisms validated on lab data come before site detail.
- Tried JuPedSim's other models on two two-way runs with default parameters:
  AnticipationVelocity −65/−76% flow, deadlocks in both runs; SocialForce −60/−41%, one deadlock;
  GeneralizedCentrifugalForce crashed (an agent was pushed outside the walkable area).
- Snapshots (`figures/fig_bidir_snapshots_real_cfs_sf.png`): real people mix and form lanes, and
  the corridor never gets very full. CollisionFreeSpeed meets as two blocks with a front between
  them, at twice the real corridor density. SocialForce forms lanes, but people bunch up at the
  ends of the corridor.
- **Decision:** calibrate SocialForce (Option A). It has the lane-forming mechanism the others
  lack. It must pass one-way (bottleneck, corridor) and two-way tests to replace
  CollisionFreeSpeed. Fallback: one-way routing with CollisionFreeSpeed.

## 2026-10-31 — SocialForce calibration: failed
- JuPedSim's default SocialForce contact forces (body 120000, friction 240000) push agents through
  walls when the crowd compresses: crash ~6 s into a 1 m bottleneck run, whatever the time step
  (tested down to 1/625 s) or start spacing. Forces ÷10 are stable; this is now the config default.
- Grid (`scripts/sf_grid.sh`, ranked by `scripts/score_validation.py`): body force 6000/12000/24000
  × agent push 1000/2000/4000 × radius 0.2/0.25, on the training runs of all three tests (2 seeds).
- **No setting passes any test.** Best (body 6000, push 4000, r 0.25): bottleneck 31% (0/5),
  corridor speed 43%, two-way flow 70% (0/9; all 9 stuck or crashed). Radius 0.25 helps the
  bottleneck and hurts two-way; 0.2 does the reverse. Stronger forces are worse.
- **Conclusion:** SocialForce, as implemented in JuPedSim, is not usable for this purpose.
  CollisionFreeSpeed stays the model for one-way flow (bottleneck 8%, corridor 16%).
- Next idea: CollisionFreeSpeed with **imposed lanes** for two-way flow (each direction routed
  along its own half of a path, as real crowds self-organise), validated on the same two-way runs.

## Open decisions
- Change `capacity.specific_flow_pms` from 1.3 to the measured ~1.86?
- Merge PR #1 and the Phase 2 work.
- Next phase (3: Sangam scenarios) not started.
