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

## 2026-11-01 — Imposed lanes for two-way flow
- **Diagnosis of the earlier failure.** In the busiest runs the agents are not stuck for good; they
  meet head-on and pack to ~7/m² where the real corridor never exceeded 3.5/m² (flow −66 to −77%).
  Permanent clogs of 76–112 agents happen only at entrances ≤ 0.65 m. In ~6 runs only 2–4 agents
  stick to the thin entrance walls, outside the measurement area.
- **Lanes in the real data** (same-direction share among each person's 4 nearest neighbours in the
  middle 4 m of the corridor; chance level ≈ 0.51): at 1.5–2.3/m² it is 0.61–0.65, so lanes form,
  but each direction is spread ~50/50 across the width (several thin lanes, not two halves). Below
  ~1/m² it is 0.42–0.48 (no lanes) with a loose side preference (one direction ~65% on one half).
  This matches the user's field observation that lanes form when it is crowded. Groups cannot be
  tested: the participants walked as individuals and the data has no group labels.
- **Implementation** (`validate_juelich.py --lanes halves|alternating|divided`): each agent enters
  the corridor through a waypoint inside a lane of its own direction, then heads for the side exit
  nearer its lane. `divided` adds a 5 cm wall along the corridor centre (a barricade). Tried and
  dropped: a second waypoint at the far end (agents pushed off the point turned back to it and
  blocked the mouth), and a random exit side (outgoing people cut across the waiting crowd).
- **Result, 18 runs × 3 seeds:**

  | Lanes | Runs within ±15% | Mean abs. flow error | Deadlocked runs | Peak corridor density, worst run (real 3.5) |
  |---|---|---|---|---|
  | none | 0/18 | 34% | 11 | 7.2/m² |
  | halves | 2/18 | 30% | 9 | 5.4/m² |
  | divided | 2/18 | 29% | 7 | 5.3/m² |

  Lanes cut the head-on overcrowding and the worst errors (−77% → −67%, −73% → −57/−65%, and
  −32% → −15% at bot-300-100-100), but no variant passes.
- **What still limits flow.** (1) The corridor ends: people leaving must cross the crowd waiting to
  enter (the lab told half of each group to use the far exit). The simulated waiting crowd packs to
  ~3/m² against ~1/m² in reality, and collision-free agents cannot weave through it. (2) The narrow
  entrances (0.5–1.0 m) of the low-density runs: their flow is 17–33% low with or without lanes, and
  most remaining deadlocks are at entrances ≤ 0.65 m, the known narrow-opening weakness.
- **Conclusion:** imposed lanes fix the false crush in the corridor but not the throughput. The
  remaining error comes largely from the set-up around the corridor (entrances, holding areas),
  which the real data does not constrain. Proposed next: drive the simulation with the real
  boundary conditions (each person starts where and when they entered the camera view), so that
  only the corridor is tested.

## 2026-11-01 — Replay test: is it the model or the set-up?
- **Question (user):** is the two-way failure in the model or in the data? The data covers only
  the camera view (y −7.2..7.2 m), so the holding areas, start density (3/m², assumed) and release
  in our set-up are guesses.
- **Replay design** (`--replay`): each simulated person appears at the real person's first tracked
  position and time (just inside an entrance) and walks to an exit circle (r = 0.6 m) at their last
  tracked position. Nothing outside the camera view is assumed. An occupied entry spot delays the
  entry; the mean delay is reported (≤ 0.5 s in all runs, so the inflow was always absorbed).
- **Result, 18 runs × 3 seeds, no lanes:** 10/18 within ±15% (was 0/18), mean error 19% (was
  34%), 3 deadlocked runs (was 11). The split is by density:

  | Real peak density | Runs | Result |
  |---|---|---|
  | < ~1.8/m² | 11 | 10 pass, errors −3% to +2%; one −17% |
  | ≥ ~2/m² | 7 | all fail, −11% (deadlock) to −73% |

  Caveat: at low density the flow through the middle line is set mostly by the arrivals, so passing
  there is a weak test. It does show that the earlier low-density failures came from the set-up
  (holding areas, narrow entrances), not from the model.
- **The model fails exactly where real lanes form** (same-direction neighbour share above chance
  from ~1.5/m², see above). Snapshot (`figures/fig_bidir_replay_dense.png`): with real arrivals the
  simulated corridor locks at ~5/m² (one direction along both walls, the other in the middle) while
  the real crowd is interleaved at 2–3/m².
- **Replay + imposed lanes is worse** (8 crowded runs, 3 seeds; mean abs. error): none 41%, halves
  63%, alternating 59%, divided 58%. Real people enter across the whole width and half of each group
  leaves on the far side (lab instruction), so forcing lanes makes agents cross the incoming stream.
  A diagnostic with a divider and every exit moved to the agent's own side still gave −32% to −69%:
  crossing at the exits is not the main cause either.
- **Conclusion:** both. The set-up caused the low-density failures; the model (CollisionFreeSpeed)
  causes the high-density ones. It reproduces two-way flow up to ~1.8/m² and fails above ~2/m²,
  where real pedestrians self-organise into lanes. Imposed lanes do not repair it. Until a model
  passes this test, two-way areas above ~2/m² are unvalidated.
- **Next options:** (1) calibrate the AnticipationVelocity model (designed for counter-flow; so far
  tried only with default parameters) on the replay test; (2) for site scenarios, use one-way routing
  where counter-flow would exceed ~2/m² (one-way pontoons are also standard practice at the Kumbh);
  (3) later, a movement model learned from trajectories.

## 2026-11-01 — AnticipationVelocity calibration: failed
- JuPedSim describes the AnticipationVelocity model (Xu et al. 2021) as reproducing bidirectional
  flow, so it was calibrated like CollisionFreeSpeed (`scripts/avm_grid.sh`), on the training runs of
  all three tests, two-way by replay, 2 seeds per run.
- Defaults (T = 1.06 s, r = 0.2 m): bottleneck −55%, corridor speed −51%, two-way −50% with all 9
  runs deadlocked, even the lightest. The stuck agents stand in one file along a corridor wall, 0.4 m
  apart, facing each other: the model's wall-gliding sends both directions along the same wall line.
- Stage 1, time gap × radius on the bottleneck (8 settings): best T = 0.6 s / r = 0.15 m (11%, 3/5
  widths) and T = 0.5 s / r = 0.175 m (14%, 3/5). Every setting clogs permanently at 0.9 and 1.2 m.
- Stage 2, anticipation time {0.5, 1, 2 s} × reaction time {0.1, 0.3, 0.6 s} on both stage-1
  winners (16 of 18 settings run; stopped by the user once the result was clear):
  - While people move, flow is close to real: best setting (T 0.6, r 0.15, anticipation 0.5 s,
    reaction 0.1 s) has bottleneck error 7% and two-way flow error 3%, including crowded runs.
  - But every setting leaves agents stuck for good in every one-way corridor run, and in most
    two-way runs (best: 4/9 two-way runs pass; 1112 stuck agent-runs in total, worst 5015). In the
    crowded two-way runs 120–290 of ~300 agents freeze.
  - Longer anticipation and reaction times make it worse, monotonically.
- **Conclusion:** AnticipationVelocity, as implemented in JuPedSim 1.4.2, is not usable: it reproduces
  flow rates but freezes, which real crowds do not. Note that the flow metric (steady 10–90% window of
  the people who crossed) looks good on runs that later freeze; the deadlock rule is what catches it.
- **Decision (with the user): no new model.** Building or training our own model is out of scope for
  a two-person project. CollisionFreeSpeed stays the model, with its validated range: one-way flow
  and bottlenecks, and two-way flow up to ~1.8/m². Site scenarios use one-way routing where
  counter-flow would exceed that, which is also standard practice at the Kumbh (one-way pontoons),
  and report remaining counter-flow areas as unvalidated.

## 2026-11-01 — Sangam: one-way routing, return trips after bathing
- `run_sim.py`: gates have roles (`routing` in config; `--routing two_way` keeps the old set-up).
  Inbound agents that reach the goal have bathed; after `bathing_min` (10, a guess) a share
  `outflow_frac` (0.6) reappear on the ghat and walk to an outbound gate. This replaces outbound
  spawning from t = 0. Runs are 45 min. Each agent's direction is saved in the snapshots.
- `analyze.py`: a cell is counter-flow when the smaller direction is ≥ 20% of its people; at
  ≥ 1.8/m² that is outside the validated two-way range and is hatched on the danger map
  (`area_counterflow_m2`).
- **Test 1** (in: G2–G5, out: G0, G1; 1000/min, 45 min; `out/oneway_test1/`): no queue at the
  gates, 44,742 entered, still filling at the end (~650 more people per minute). The only dense area
  (1654 m², up to 8.7/m²) is the foot of the G2 lane at the ghat, from minute 25, when return trips
  start. It is counter-flow: the G2 lane is the only link between the nose and the pontoons, so
  people heading for G0/G1 walked up it against the inbound stream. An artefact of the routing, not
  a result.
- **Change:** G2 becomes outbound (in: G3, G4, G5; out: G0, G1, G2), so the G2 lane and the
  pontoons carry one direction only.
- **Test 2** (in: G3, G4, G5; out: G0, G1, G2; 1000/min, 45 min; `out/oneway_in1000/`): counter-flow
  is gone (16 m² for 2 s, no dense cell in counter-flow). 45,356 entered, 22,143 bathed, 8,387
  walked out; no queue at the gates; still filling at the end (30,840 people inside).
  The one danger area is now a **merge**: the G3 and G4 roads join at about (400, 700) and continue
  as one 5.5 m road. Demand there is 700/min (G3 400 + G4 300) against 429/min at the configured
  1.3 people/m/s (614/min at the measured 1.86). A queue grows back up both roads: ≥ 4/m² from
  minute 17 (1261 m² in total), up to 6.4/m² over 51 m² (above the validated range). Downstream of
  the merge people walk at ~0.6 m/s. This is one-way flow through a bottleneck, the regime the model
  is validated for, but it follows from the assumed gate shares.
- Note: at 1000/min the area had not reached a steady state after 45 min; the sweep will need
  longer runs (~60–90 min), about 1.5–2× the compute (a 45 min run takes ~75 min).

## 2026-11-01 — Gate shares: the danger spot follows the assumed split
How arrivals split over the inbound gates is not known, so test 2 was repeated with two other
splits (1000/min, 45 min, one seed each; `out/gates_equal/`, `out/gates_west/`, snapshots deleted).

| split (G3 / G4 / G5, per min) | G3+G4 at the merge | first ≥ 4/m² | area ≥ 4/m² | area ≥ 6/m² | max | waiting outside at end |
|---|---|---|---|---|---|---|
| test 2: 400 / 300 / 300 | 700 | 17.1 min, merge | 1261 m² | 51 m² | 6.4 | 0 |
| equal: 333 / 333 / 333 | 667 | 17.9 min, merge | 931 m² | 72 m² | 6.4 | 0 |
| west: 250 / 250 / 500 | 500 | 32.8 min, elsewhere | 39 m² | 0 | 4.8 | 430 (G5 over capacity) |

- Equal split: the same merge jams, slightly later and over a smaller area. Demand at the merge
  (667/min) is still above its capacity (429, or 614 at 1.86).
- West-heavy split: the merge stays below 4/m². The only dense cells are short-lived (3 min at most)
  around (620, 266) and (518, 246); G5 is over its capacity (500 vs 429/min), so a queue of 430 people
  forms outside the gate instead of inside the area.
- Counter-flow stays small in all three (≤ 96 m², ≤ 5 s).
- **Reading:** where and whether a jam forms depends on the gate split, which is an assumption. The
  merge jam is a property of the split, not a fixed fact of the site. The split is therefore a key
  input for the sweeps and the ping experiment, and moving arrivals from G3/G4 to G5 is a candidate
  intervention for Phase 5 (it trades a jam inside for a queue at the gate).

## 2026-11-01 — Normal-day sweep (one-way routing, 75 min)
`sweep.py normal_day --jobs 2`: inflows 250/500/1000/1500 per min, 75 min, seed 1, default gate
shares (G3 40%, G4 30%, G5 30%), outflow_frac 0.6. `out/sweeps/normal_day/summary.{json,png}`,
per-run maps in `out/normal_day_in*_s1/` (snapshots deleted).

| inflow/min | max density | first ≥ 4/m² | area ≥ 4/m² | area ≥ 6/m² | two-way ≥ 1.8/m² | inside at end | waiting outside at end | compute |
|---|---|---|---|---|---|---|---|---|
| 250 | 2.1 | never | 0 | 0 | 0 | 7,234 | 0 | 39 min |
| 500 | 2.9 | never | 0 | 0 | 16 m², 1 s | 15,112 | 0 | 80 min |
| 1000 | 6.7 | 17.1 min | 2,659 m² | 143 m² | 144 m², ≤ 12 s | 41,313 | 2 | 3.2 h |
| 1500 | 8.0 | 14.8 min | 5,481 m² | 628 m² | 176 m², ≤ 17 s | 59,455 | 14,299 | 11.8 h |

- **Up to 500/min the site stays below 4/m²** everywhere; nobody queues at the gates.
- **At 1000/min the G3+G4 merge jams** (as in test 2), from minute 17, and stays ≥ 4/m² for ~58 min.
  The area is still filling at 75 min (+4,300 people in the last 15 min), so no steady state yet.
- **At 1500/min all three inbound gates are over capacity** (G3 600 vs 429/min, G4 and G5 450 vs
  429). The merge queue runs back up both the G3 and G4 roads to the gates, and 14,299 people are
  still waiting outside at the end. A second, smaller dense spot appears on the ghat at about
  (620, 265), the same place as in the west-heavy gate split.
- **No dense cell is in counter-flow** in any run; two-way areas above the validated range are small
  and short (≤ 176 m², ≤ 17 s).
- **Reading:** for these gate shares the tipping point lies between 500 and 1000/min (the max-density
  curve crosses 4/m² at roughly 650/min, by linear interpolation between two runs). All dense
  areas are one-way queues behind a bottleneck (merge, gates), the validated regime. Values above
  ~4–5/m² are what the model indicates, not validated. One seed per inflow, and the split is an
  assumption (see the gate-share check), so the tipping point is indicative only.
- Compute: a 1500/min run took 11.8 h on one core; per-step cost grows with the crowd. Python
  bookkeeping in `run_sim.py` (positions read several times per second, spawn checks against all
  agents) is a likely share of that and is the first thing to trim before the peak-day sweep.

## Open decisions
- Change `capacity.specific_flow_pms` from 1.3 to the measured ~1.86?
- Merge PR #1 and the Phase 2 work.
- Next phase (3: Sangam scenarios) not started.
