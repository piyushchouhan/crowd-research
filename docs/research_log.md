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

## 2026-11-02 — Phase 4, first pass: phone pings on the 1000/min merge jam
Code: `scripts/pings.py` (synthetic pings), `scripts/warn.py` (warnings and scoring); settings in
`config/sim.json` -> `pings`, `warning`, fixed before looking at results. Runs: `oneway_in1000`
(jam, 45 min, first ≥ 4/m² event at 17.1 min at the G3+G4 merge) and `calm_in500` (new, 500/min,
75 min, never ≥ 4/m²; snapshots kept). Grid: phone share 1/2/5% × ping interval 5/15/30 s × GPS
error 5/10/20 m × zone 12/20/32 m, 20 draws each. Results in `out/phase4/`; figures
`docs/figures/fig_phase4_*.png`. Compute: 21 min in all.

- **Truth:** a danger event is a 4 m cell at ≥ 4/m² for 60 s in a row. Lead time = event onset
  minus the first alarm in its zone or a neighbouring zone.
- **Warnings** (alarm once the condition holds 30 s, estimates over the last 120 s):
  count (phone pings scaled by the known share ≥ 2/m², Fruin LoS F), speed (median phone speed
  < 0.5 m/s, Weidmann ≈ 2.3/m²), trend (count estimate projected 10 min ahead reaches 4/m²).
- **Oracle** (everyone reports every 10 s, no GPS error): count warns 3.1 min ahead, trend 5.3 min,
  speed 1.1 min *late*. So the warning rule, not the phones, limits the lead time: only the trend
  rule reaches 5 min even with perfect data. Speed is late because simulated people keep walking
  until it is already crowded (CollisionFreeSpeed slows only near contact); real crowds probably
  slow earlier, so this is a model limit, not evidence against speed.
- **Density estimate (count, share known):** median error where the true density ≥ 1/m²,
  2% phones, 15 s, 10 m: 29% (12 m zones), 23% (20 m), 21% (32 m); 5% phones: 15–22%. GPS error
  (5→20 m) and ping interval matter little; zone size and phone share matter most. Passes ±30% at
  2% for zones ≥ 20 m, **if the phone share is known**, which in practice it is not.
- **Lead time, 2% phones, 15 s, 10 m, 20 m zones:** trend 5.4 min median (10–90%: 4.4–6.0), ≥ 5 min
  in 70% of draws; count 3.6 min; speed 1.3 min late. Phone settings barely change the median.
- **False alarms are the problem.** Calm run, same setting: count alarms in 31 zones, trend in 59
  (of 667 valid 20 m zones, 75 min) where the oracle raises none: pure sampling noise. A 20 m road
  zone at 1.5/m² holds ~165 people, i.e. ~3 phones at 2%, so the estimate swings by ±50%. 5% phones
  cut this to 10 (count) and 21 (trend). In the jam run, the oracle's own "false" alarms (27 zones,
  count) lie on the road below the merge, a packed but moving stream at 2.1–2.6/m² that never
  reaches 4: the count rule cannot tell it from the start of a queue.
- **Caveat on lead:** with few phones the median lead can exceed the oracle's (trend at 1%: 5.4 vs
  5.3 min). That is noise firing early near the event, not skill; lead must be read together with
  false alarms.
- **Go/no-go (set in the roadmap: 2% → density ±30% and ≥ 5 min warning):** met on paper by the
  trend rule (23%, 5.4 min), but the criterion did not include false alarms, and at ~50 false zone
  alarms per hour on a calm day the warning would not be usable. **Verdict: not a go yet.** The
  density side is promising; the warning side needs false-alarm control.
- Known limits: one jam (one run, one place); phones spread at random (in reality one per family,
  clustered); returning bathers get a new phone draw; the phone share is assumed known.

## 2026-11-02 — Phase 4: how many phones are needed?
`warn.py oneway_in1000 --calm-run calm_in500 --shares 0.01 0.02 0.05 0.1 0.2 0.5 --name phase4_shares`
(15 s pings, 10 m GPS error, 20 and 32 m zones, 20 draws; 6 min). Figure
`docs/figures/fig_phase4_share_sweep.png`. Medians over draws:

| phones | density error (20 m) | calm-run false zones, count / trend (20 m) | lead, trend (20 m) | lead, count (20 m) |
|---|---|---|---|---|
| 1% | 30% | 61 / 122 | 5.8 min | 4.0 min |
| 2% | 23% | 32 / 61 | 5.4 | 3.4 |
| 5% | 16% | 12 / 23 | 5.4 | 3.2 |
| 10% | 13% | 4 / 9 | 5.3 | 3.3 |
| 20% | 12% | 2 / 3 | 5.3 | 3.3 |
| 50% | 10% | 1 / 2 | 5.3 | 3.4 |
| everyone, no GPS error | 6% | 0 / 0 | 5.3 | 3.1 |

- With the simple rules of the first pass, false alarms on the calm day fall to ~1–3 zones only at
  20–50% phones, far above the 1–5% the project is about. More phones do not add warning time:
  the trend rule stays at ~5.3 min and the count rule at ~3.3 min, as with perfect data.
- In 32 m zones a floor of ~6 false zones (count) remains even at 50%, where perfect data gives 0.
  Likely an artefact of the method (snapping GPS points onto the walkable edge piles them up in
  zones with little walkable area), not sampling noise. To check.
- Reading: adding phones is an expensive way to remove noise. The next step is rules that use the
  few phones better (more averaging, persistence, neighbouring zones, count with speed), aiming at
  the false-alarm level of 20% phones with 2–5%.

## 2026-11-02 — Phase 4: smarter warning rules (hold, neighbours, slowing)
- **Method fix first:** at 50% phones, 32 m zones still had ~6 false alarms on the calm day.
  They were slivers of road at zone corners (13–28 m² walkable); a few GPS points snapped into
  them looked like a crowd. Zones now need ≥ 50 m² walkable (`warning.min_zone_m2`); their cells
  still count for the neighbouring zones. This alone roughly halves the false alarms. Numbers in
  the two entries above were made before this fix.
- **Pass/fail fixed before testing** (`warning.go`): at 2% phones (15 s, 10 m GPS error), median
  density error ≤ 30%, first jam warned ≥ 5 min ahead in ≥ 80% of draws, and ≤ 1 false alarm per
  hour on a calm day (median alarmed zones).
- **Rules** (`scripts/rules.py`, grid in `warning.rules`): base count or trend × window 2/5 min ×
  hold 30 s/2 min/3 min × neighbour zone also over (no/yes) × phones nearby below 0.8 m/s (no/yes)
  × 20/32 m zones = 96 rules, at 1/2/5% phones, 20 draws. Chosen on the training runs
  (`oneway_in1000`, `calm_in500`), then checked unchanged on two new runs: `holdout_jam`
  (1000/min, seed 2, equal gate split; first ≥ 4/m² at 18.4 min at the same merge, max 6.3/m²)
  and `holdout_calm` (500/min, seed 2, 75 min). Results `out/phase4_rules/`, figure
  `docs/figures/fig_phase4_rules.png`. Compute ~70 min.
- **Result: no rule passes at 2% phones.** 83 of 96 rules meet the false-alarm limit, but none of
  them warns 5 min ahead in any draw on the training jam. Best trade-offs on training at 2%:

  | false alarms/hour allowed | best rule | warned ≥ 5 min ahead | median lead |
  |---|---|---|---|
  | ≤ 1 | trend, 20 m, hold 30 s, +neighbour, +slow | 0% | 3.1 min |
  | ≤ 5 | trend, 20 m, 5 min window | 0% | 3.6 min |
  | ≤ 20 | trend, 32 m (no extras) | 50% | 5.0 min |
  | ≤ 50 | trend, 20 m (no extras) | 70% | 5.5 min |

- On the holdout, the chosen rule keeps its false alarms (0/h on the new calm day) and warns
  4.3 min ahead (median; ≥ 5 min in 40% of draws): it carries over, but still fails the lead
  criterion.
- **Why:** each extra check removes noise by waiting for more evidence, and waiting costs lead.
  Even with perfect data the best rule warns only 5.3 min ahead (training jam) and 6.7 min
  (holdout), so there is almost no margin to spend on filtering. Phone speed does not help in this
  model, because simulated people slow only once it is already dense.
- **Closest to passing:** trend, 32 m zones, no extras, at **5%** phones: ≤ 1 false alarm/hour on
  both calm days, lead 4.5 min (training, 25% of draws ≥ 5 min) and 6.2 min (holdout, 85%).
- **Reading:** with density alone, the warning horizon is set by how early the build-up shows in
  density, about 5 min here, not by the number of phones. A longer horizon needs a signal that
  shows earlier. The candidate is flow: this jam forms because 667–700 people/min reach a road
  that carries ~430–610/min, which phones crossing the gates could show from the first minutes.
  Not tested yet.

## 2026-11-02 — Phase 4: flow signals (in/out balance, demand vs capacity)
Density alone gives at most ~5–6.5 min of warning (entry above). Two flow-based warnings, same
runs, same protocol (choose on training, check on holdout) and the same go criteria.

**1. In/out balance, no map** (`scripts/flow.py`, `warning.flow`): phones entering minus leaving a
zone and its 8 neighbours, alarm when the surplus is beyond chance (≥ 2–3 σ) and would fill the
block to 4/m² within 10 min. 24 settings. Chosen (32 m, 3 min window, 2 σ, hold 60 s), 2% phones:
lead 6.3 min training / 4.6 min holdout, ≥ 5 min in 50% / 35% of draws, false alarms 0.4 / 0 per
hour. Fails the lead criterion. The build-up at the merge is the small difference of two large
flows (~700/min in, ~550/min out, i.e. 100–160/min), which 2% of phones measure poorly; with perfect
data it warns 5.6–7 min ahead, little more than density.

**2. Demand vs capacity at a known bottleneck** (`scripts/bottleneck.py`, `warning.bottleneck`).
From the map, the G3 and G4 roads (5.5 m each) join into one 5.5 m road: capacity 429/min at
1.3 people/m/s. Demand = unique phones seen in counting circles (12 m) on the two feeding roads
per window / phone share; alarm when demand − capacity ≥ 1–2 standard errors for 1–2 min.
Counting circles either 60 m before the merge ("near") or 30 m inside the G3 and G4 gates
("gates", ~500 m and ~6 min walk upstream). 24 settings. The "near" version was run first; it
fails (2%: lead 5.0 / 3.8 min, ≥ 5 min in 50% / 20%) because people reach those circles only from
minute 7 and the jam starts at minute 17. Counting at the gates was the version proposed; the
walk from gate to merge is real warning time.

Chosen on training: gates, 2 min window, 1 σ, hold 60 s. **It passes all three go criteria at 2%
on both the training and the holdout runs:**

| phones | jam lead, median (10–90%) train / holdout | ≥ 5 min ahead train / holdout | calm false alarms/hour (median) | calm days with any false alarm |
|---|---|---|---|---|
| 1% | 12.4 (5.9–14.0) / 11.7 (4.0–15.2) min | 95% / 90% | 0 / 0 | 10% / 15% |
| **2%** | **13.8 (12.5–14.1) / 13.8 (8.9–15.4) min** | **100% / 100%** | **0 / 0** | 10% / 30% |
| 5% | 13.9 / 15.2 min | 100% / 100% | 0 / 0 | 0% / 0% |
| everyone | 14.1 / 15.5 min | 100% / 100% | 0 / 0 | 0% / 0% |

Stricter settings (2 σ) have no false alarm on any calm draw but warn in time in only 60–85% of draws.

**What this does and does not show:**
- The warning comes from *where* phones are counted: upstream counting sees the demand one walk
  (~6 min) plus one queue build-up (~7 min) before the jam. Watching density at the jam site
  cannot see that far ahead.
- It needs the bottleneck and its capacity in advance (from the map). It only watches listed
  bottlenecks; a jam elsewhere (e.g. on the ghat at 1500/min) is not covered.
- The calm day is an easy test: merge demand there is ~350/min against 429. Demand close to
  capacity, a gradual rise in arrivals, and the capacity value itself (429 at 1.3 people/m/s vs
  614 at the measured 1.86, see Open decisions) are untested. The capacity is the biggest risk:
  if the real one is higher, the alarm fires without a jam.
- The phone share is assumed known (demand is scaled by it).
- One site, one bottleneck, two jam runs (two gate splits). Simulated people, not real ones.

## 2026-11-02 — Phase 4: stress test of the bottleneck warning
`scripts/stress.py` applies the rule chosen on training (gates, 2 min window, 1 σ, hold 60 s)
unchanged to new runs, with the merge capacity at 429/min (config, 1.3 people/m/s) and at
614/min (Jülich, 1.86). New runs (`run_sim.py --ramp-min` added: inflow rises linearly):
`stress_merge380/430/480/550` (60 min, seed 3, default gate shares, so 380–550 people/min head for
the merge) and `stress_ramp` (inflow 0 → 1000/min over 30 min, 60 min, seed 4). Results
`out/phase4_stress/`, figure `docs/figures/fig_phase4_stress.png`.

- **The simulated merge passes ~600 people/min once jammed** (600–606 in all four jam runs),
  i.e. ~1.82 people/m/s, close to the Jülich 1.86, as expected for a model calibrated on Jülich.
- **Where the jam starts:** no jam in 60 min at 380, 430 or 480/min; a jam at 550/min (from minute
  30). So the effective capacity of this merge in the model lies between 480 and 550/min, below
  its jammed throughput (two streams merging lose some capacity).
- Share of draws that alarmed, 2% phones (jam runs: warned ≥ 5 min ahead):

  | run | jam? | capacity 429 | capacity 614 |
  |---|---|---|---|
  | oneway_in1000 (700/min) | yes, 17 min | 100% (lead 13.9 min) | 75% ≥ 5 min (9.2 min) |
  | holdout_jam (667/min) | yes, 18 min | 100% (14.8) | 60% (7.2) |
  | stress_merge550 | yes, 30 min | 100% (23.4) | 10% (mostly missed) |
  | stress_ramp | yes, 40 min | 100% (15.3) | 45% (4.9) |
  | calm_in500 / holdout_calm (350/min) | no | 20% / 0% false | 0% / 0% |
  | stress_merge380 | no | 35% false | 0% |
  | stress_merge430 | no | **85% false** | 5% |
  | stress_merge480 | no | **90% false** | 5% |

- **Neither capacity value passes.** At 429 every jam is warned 14–23 min ahead, also with a slow
  build-up, but demand between 429 and the real capacity raises false alarms on most days. At 614
  false alarms vanish, but jams that form below 614 (550/min) are missed and the lead drops to
  5–9 min.
- **Reading:** the method is only as good as the capacity number of the bottleneck. With the right
  threshold (here somewhere around 500/min) it would likely work, but choosing it from these runs
  would be tuning on the test. The capacity has to come from outside: measured on site, e.g. the
  flow phones see leaving the bottleneck while it is jammed (here ~600/min), corrected for merging.
  This is a calibration step the method needs at every site.
- The slow build-up (ramp) does not hurt: with 429 the lead is 15 min, with perfect data 21 min.

## 2026-11-02 — Phase 4: phones learn the capacity themselves
`scripts/calibrate.py`. Instead of taking the capacity from a book value, the phones learn it from
a history of days, with no simulation truth: each day they measure the demand at the gates (5 min
window) and whether a queue formed at the merge (median speed of ≥ 3 phones within 40 m below
0.5 m/s for 3 min, each speed over 60–120 s because GPS error swamps a 15 s step). The day's demand
is the median over the 10 min before the queue (or the whole day after minute 10 if none). Learned
capacity = midway between the busiest day without a queue and the quietest day with one. Each
draw of 2% phones learns its own value. Then the frozen rule (gates, 2 min, 1 σ, hold 60 s) with
the learned threshold runs on six fresh runs not used anywhere before: `fresh_merge460/500/520/540/580/620`
(60 min, seed 5, nominal demand at the merge 460–620/min). Truth only scores. Results
`out/phase4_calibrate/`, figure `docs/figures/fig_phase4_calibrate.png`.

- **History (9 old runs):** the 2% phones saw a queue on all four jam days in all 20 draws and on
  none of the five calm days. Queue detection works.
- **Learned capacity:** with everyone's phones 535/min; with 2% a median 450 (10–90%: 412–486) in
  phone units, which read ~12% low (GPS moves pings out of the counting circles); the same bias
  applies when the rule runs, so it cancels.
- Fresh runs, share of draws that alarmed:

  | run | truth | 2% phones | everyone |
  |---|---|---|---|
  | fresh_merge460 | no jam | **65% false** | 0% |
  | fresh_merge500 | no jam | **95% false** | 100% false |
  | fresh_merge520 | no jam | **100% false** | 100% false |
  | fresh_merge540 | jam at 50 min | 100% (lead 39 min, ≥ 5 min in 95%) | 100% |
  | fresh_merge580 | jam at 23 min | 100% (lead 17 min, 90%) | 100% |
  | fresh_merge620 | jam at 19 min | 100% (lead 13 min, 100%) | 100% |

- **Every jam is warned in time, but this does not pass the false-alarm criterion.**
- **Two different causes of the false alarms:**
  - **500–520/min: a grey zone, not a phone problem.** Even with every phone, the learned 535
    alarms there. These days sit within ~5% of the merge's capacity: 540 jammed only at minute 50,
    550 at minute 30, 520 not within the hour. Whether such a day "jams" depends on the run length
    and chance, so an alarm here is arguably a fair "near capacity" warning, but by the pre-set
    definition (≥ 4/m² for 60 s) it is false.
  - **460/min: a phone problem.** With everyone no alarm; with 2% two out of three draws alarm at
    some point in the hour. At 2% a 2 min window holds only ~16 phones, so the demand estimate has
    ~25% noise, too much to tell 460 from 535 (a 15% gap), and a 1 σ margin is crossed by chance
    over an hour.
- **Reading:** self-calibration finds the right capacity (535 vs the 480–550 tipping point seen
  in the stress test), so the "where does the capacity come from" problem is solved in principle.
  What remains is precision: at 2% the rule cannot separate demand 15% below capacity from
  demand at capacity. Not tuned here (would be tuning on the test); options for a next step are a
  longer window or a larger margin (fewer false alarms, less lead), or a two-level alert
  ("near capacity" vs "over capacity").

## 2026-11-02 — Phase 4: longer window and two-level alert
`scripts/two_level.py`, config `warning.two_level`. Two fixes for the false alarms above:
(1) windows up to 5 min, so more phones per count; (2) amber when demand reaches amber_frac × the
learned capacity, red when it exceeds it, both by k standard errors held for hold_s. Days are
classed by the truth at the merge: jam (≥ 4/m² event), busy (peak 20 m zone ≥ 2/m² for 60 s,
Fruin LoS F, no jam: amber is right, red is false), calm (both false). Go criteria, set before the
test, at 2% phones: jam days first alert ≥ 5 min ahead in ≥ 80% of draws and red before the jam
in ≥ 80%; days without a jam red in ≤ 20%; calm days amber in ≤ 20%. Capacity learned per draw
from the 9 history runs (as in calibrate.py). 36 rules (window 2/3/5 min × 1/2 σ × amber at
80/85/90% × hold 60/120 s) scored on the history; best chosen there; tested unchanged on six
new runs never looked at before: `clean_merge450/490/510/530/560/600` (60 min, seed 6). The
earlier `fresh_merge*` runs are also reported but are not a clean test (the fixes were designed
after seeing them). Results `out/phase4_two_level/`, figure `docs/figures/fig_phase4_two_level.png`.

- **Chosen on history:** 5 min window, 2 σ, amber at 80% of capacity, hold 120 s (8 of 9 history
  days pass; stress_merge550 fails on red before the jam).
- **Clean test, 2% phones:**

  | run | truth (peak at merge) | amber | red | verdict | old rule (2 min, one level) |
  |---|---|---|---|---|---|
  | clean_merge450 | calm (2.0/m²) | 20% | 0% | pass | 65% |
  | clean_merge490 | busy (2.3) | 60% | 5% | pass | 90% |
  | clean_merge510 | busy (2.5) | 90% | 10% | pass | 90% |
  | clean_merge530 | busy (2.7) | 95% | 20% | pass | 100% |
  | clean_merge560 | jam at 27 min | 100%, lead 16.5 min, ≥ 5 min 75% | before jam 15% | fail | 100% |
  | clean_merge600 | jam at 23 min | 100%, lead 14.5 min, ≥ 5 min 100% | before jam 30% | fail | 100% |

- **False alarms fixed:** red on days without a jam fell from 65–100% of draws to 0–20%; those
  days now get amber, which matches what happened (crowded, no jam).
- **Early warning kept:** amber comes 14–17 min before both jams.
- **Red fails:** it comes before the jam in only 15–30% of draws (median red at minute 20 for
  the jam at 27, at minute 40 for the jam at 23, i.e. mostly after). With 2% phones a 5 min window
  holds ~50 phones, so 2 σ is ~27% of demand: red needs demand ~25% above capacity before it
  fires, and these jams form at 5–12% above. With every phone red comes 17–21 min ahead on both
  jams, so this is phone precision, not the method.
- **Overall: does not pass the pre-set go** (2 of 6 clean days fail, both on red; clean_merge560
  also at 75% < 80% on lead). The trade-off at 2% is now explicit: a red that is both early and
  rarely false needs to tell demand 5% over capacity from 5% under, which ~50 phones cannot.
  With every phone even clean_merge530 (no jam) gets red, so part of this is the grey zone too.
- Possible next steps (not tested): judge the system on amber as the warning and red as a
  confirmation (would need a new pre-set criterion, and is a weaker claim); or measure how the
  red's timing improves with phone share (5%, 10%).

## 2026-11-02 — Phase 4: how many phones does the two-level alert need?
`scripts/two_level_shares.py`. Same protocol as two_level.py at 2, 5, 10 and 20% phones (nested:
the 5% phones include the 2% ones), 20 draws, plus everyone. Per share: capacity learned from the
9 history runs, then two rules on the six unseen `clean_merge*` runs: the rule chosen at 2% in
two_level.py (fixed: 5 min, 2 σ, amber 80%, hold 120 s) and the rule chosen on the history at
that share (own). The 2% set is a new draw; it matches two_level.py closely (red before jam
10/35% vs 15/30%). Results `out/phase4_two_level_shares/`, figure
`docs/figures/fig_phase4_two_level_shares.png`.

- Fixed rule, unseen runs:

  | share | red before jam (560 / 600) | first alert ≥ 5 min ahead | false red, worst day without a jam (530) | days passing |
  |---|---|---|---|---|
  | 2% | 10% / 35% | 75% / 100% | 25% | 3/6 |
  | 5% | 25% / 80% | 100% / 100% | 15% | 4/6 |
  | 10% | 70% / 100% | 100% / 100% | 30% | 3/6 |
  | 20% | 90% / 100% | 100% / 100% | 45% | 4/6 |
  | everyone | 100% / 100% | 100% / 100% | 0% | 5/6 |

- **Red needs ~20% phones** to come before both jams in ≥ 80% of draws (10% for the bigger
  overload at 600/min, 5% for it at the margin). Amber warns ≥ 5 min ahead from 5% on, in every draw.
- **No share passes all six days.** The remaining failures are not about the number of phones:
  - **clean_merge450, amber on a "calm" day** (fails from 5% on): its peak was 1.99/m², just under
    the 2.0 busy line, and its demand (~84% of capacity) is above the amber level. Everyone's
    phones give amber there too. A boundary case of the day classes, not a phone error.
  - **clean_merge530, false red rising with share** (25 → 45%, everyone 0%). Checked: the phones'
    undercount is the same on every day (20%/everyone = 0.84–0.85 on 480, 510, 530 and 550), and
    the learned capacity tightens with share (10–90%: 411–490 at 2%, 440–457 at 20%, phone units)
    without moving. But this day's real demand (546/min, everyone's phones) is above the learned
    535: the history has no day between 497 (no jam) and 573 (jam), so the capacity is only known
    to lie in that range, and the midpoint is slightly low. With less random noise the red margin
    shrinks and this shows. Probably also: the error estimate (√ of the phone count) leaves out
    GPS moving pings in and out of the 12 m counting circles, so "2 σ" is less than 2 real σ.
- **Rules chosen at 10–20% overfit:** with less noise the history picks sharper rules (3 or 2 min,
  amber 90%) that pass every history day but give a false red on 85% of draws on the 530 day.
  The history's only busy no-jam day is 480, so nothing in it punishes red near capacity.
- **Reading:** at 2–5% the system gives an early "near capacity" warning; an early "over capacity"
  red needs ~20%. Above that, the limit is how well the capacity is known: a history needs days
  close to capacity on both sides (here nothing between 497 and 573/min) before red can be
  trusted near the line.

## 2026-11-03 — Phase 4: ping interval and GPS error
`two_level_shares.py --interval --sigma`: the same protocol and the fixed 2% rule with pings
every 5 or 30 s (GPS 10 m) and GPS error 5 or 20 m (every 15 s); capacity learned with the same
phones. Results `out/phase4_sens_i{5,30,15}_s{10,5,20}/`. Unseen runs, fixed rule
(red before jam on 560 / 600; first alert ≥ 5 min ahead on 560 / 600; worst false red, 530 day):

| setting | 2% | 5% | 20% |
|---|---|---|---|
| 15 s, 10 m (baseline) | red 10/35%; alert 75/100%; false 25% | 25/80%; 100/100%; 15% | 90/100%; 100/100%; 45% |
| 5 s, 10 m | 10/50%; 95/100%; 20% | 35/90%; 100/100%; 30% | 95/100%; 100/100%; 35% |
| 30 s, 10 m | 10/45%; 65/80% (lead 9–10 min); 5% | 20/70%; 95/100%; 15% | 80/100%; 100/100%; 35% |
| 15 s, 5 m | 20/45%; 90/100%; 30% | 25/75%; 100/100%; 20% | 80/100%; 100/100%; 30% |
| 15 s, 20 m | 0/5%; 20/50% (lead 5–8 min); 0% | 0/5%; 45/85%; 0% | 0/0%; 90/100%; 0% |

- **Ping interval (5–30 s) and GPS error up to 10 m change little.** At 30 s and 2% the first
  alert is later (median 9–10 min, ≥ 5 min ahead in 65–80%); from 5% on it is as before.
- **The learned capacity is in "phone units"** and differs per setting (median 318 at 30 s,
  449 at 15 s, 560 at 5 s, all at 10 m): fewer pings per crossing means fewer phones caught in the
  12 m counting circles. It does not matter as long as learning and alerting use the same phones.
- **At 20 m GPS error the method breaks, in the learning step.** Checked: at 20 m, 2% phones see
  the queue on the mildest jam day (stress_merge550) in only 10% of draws (100% at 10 m); on the
  bigger jams still 100%. Counted as a day without a queue, it pushes the learned capacity above
  the real one (phones read 460 on that day; learned 505–516), so red never fires before the jams
  and amber comes late. The counts themselves read ~20% low at 20 m on every day alike, which
  would cancel. Cause: between two pings 60–120 s apart, 20 m of GPS error adds roughly 0.3–0.4 m/s of
  apparent speed (about half that at 10 m, less after snapping to the walkable area), enough to
  lift a slow queue over the 0.5 m/s line. Not tuned (longer speed spans or a wider circle would be the
  candidates); a stated limit: queue detection, and so the capacity, needs GPS error ≲ 10 m.
- **The phone share does not need to be known.** Demand, its standard error and the learned
  capacity are all divided by the same assumed share, so the alert condition is the same whatever
  share is assumed, as long as the real share is the same on the history days and the day of the
  alert. A share that changes between days (app adoption growing) would bias it.

## 2026-11-03 — Phase 4: conclusion
Question: can 1–5% of people's phones warn of a dangerous jam 5–10 min ahead?
- **Density in small zones: no.** At 2% the density error is fine (23%), but per-zone density,
  speed and trend rules either warn too late or false-alarm many times an hour; ~20% phones would
  be needed (first pass, smarter rules, flow).
- **Demand at a known bottleneck against a learned capacity: partly yes.** Counting phones at the
  gates that feed the bottleneck, with a capacity the phones learn from past days:
  - an amber "near capacity" alert comes 14–20 min before every jam at 2–5% phones (≥ 5 min ahead
    in 75–100% of draws at 2%, all draws from 5%), with pings every 5–15 s and GPS error ≤ 10 m;
    with pings every 30 s it holds from 5% on (at 2%: median 9–10 min, ≥ 5 min ahead in 65–80%);
  - a red "over capacity" alert that is both early and rarely false needs ~20% phones for jams
    5–12% over capacity (10% for bigger overloads);
  - false red on days without a jam: 0–45%, worst on a day 2% above the learned capacity, which
    no number of phones fixes: the history bracketed the capacity only between 497 and 573/min.
- **The pre-set go criteria (2%, ≥ 5 min in ≥ 80%, ≤ 1 false alarm/h) are not met** by any method
  in full. What is met at 2–5% is an early near-capacity warning with few false reds.
- **Limits:** one bottleneck (G3+G4 merge), one site, simulated pings and crowd; the bottleneck
  must be known from the map with its feeding roads; the capacity needs a history with days near
  it; GPS error must stay ≲ 10 m for the queue detection; the phone share must be stable across days.
- Next (agreed 2026-11-03): a general-events phase for fairs, concerts and pandals: find
  bottlenecks and counting points from the map automatically, get the capacity without a history
  (width × specific flow as a start, then the flow phones see leaving a queued bottleneck), and add
  a density check for standing crowds (concert fronts).

## Open decisions
- `capacity.specific_flow_pms` (1.3 vs ~1.86): no longer blocks the warning, because the phones
  learn the capacity. Still used for gate loads in `run_sim.py` and would be the starting value
  for sites without a history. The simulated merge passes ~600 people/min (~1.82 people/m/s).
- Phase 4 is committed on branch `phase4-pings`. PRs #1–#4 are merged.
