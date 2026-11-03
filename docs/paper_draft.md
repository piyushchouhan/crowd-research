# Can sparse smartphone pings give early warning of crowd crushes at mass religious gatherings? A simulation study at the Sangam, Prayagraj

*Working draft. Sections marked **[TODO]** cover phases not yet done. Numbers come from
`out/validation/*/summary.json` and `data/hotspot/sangam_nose.json` at the commit that last
touched this file; regenerate them with the commands in §8.*

---

## 1. Introduction

Crowd crushes recur at Indian mass religious gatherings, including at the Prayagraj Kumbh
(1954, 2013) and on 29 January 2025 (Mauni Amavasya). Crushes form at bottlenecks and
counter-flows when local density rises past roughly 5–6 people/m², and they build over
minutes. If organisers know where and how fast density is rising, they can intervene
(hold inflow, open alternative routes, alert people upstream).

Video monitoring covers fixed points. Smartphones are everywhere, but only a small share
of attendees will share their location, and GPS is noisy in dense crowds.

**Research question.** Can location pings from a small share of attendees (1–5%) estimate
local crowd density well enough, and early enough, to warn of a dangerous situation
5–10 minutes ahead? And do alerts or re-routing reduce peak density?

**Scope.** The aim is a general method for fairs and mass gatherings (melas, temples, festivals).
The Sangam at Prayagraj serves as a realistic test site, not as an incident reconstruction.

**Approach.** We cannot test this on real crushes, so we use a pedestrian simulation of the
Sangam nose as ground truth. We draw synthetic pings with realistic sampling and GPS error
from the simulated crowd, and measure how well and how early density can be recovered.
Before trusting the simulation, we validate its model against controlled lab experiments
(§5).

**Contributions (planned).**
1. A walkable-geometry model of the Sangam bathing area with corridor widths and capacities,
   built from Sentinel-2 imagery and measured road widths (§3).
2. A validation of the JuPedSim collision-free speed model against Jülich bottleneck and
   corridor experiments. The default parameters underpredict bottleneck flow by about half;
   a two-parameter calibration brings all widths within ±15% (§5).
3. **[TODO]** Sangam test scenarios over a range of inflows (Phase 3).
4. Detection performance vs. share of users, ping interval and GPS error (Phase 4, §7). Per-zone
   density from 2% of users does not give a usable warning. Counting users on the roads that
   feed a known bottleneck, against a capacity the users' own traces learn from past days, gives
   an amber "near capacity" alert 14–20 min before every simulated jam at 2–5% of users; an early
   and reliable "over capacity" alert needs ~20%. The share of users need not be known.
5. **[TODO]** Effect of interventions (Phase 5).

## 2. Related work

- **Crowd disasters and early-warning measures.** Helbing, Johansson and Al-Abideen (2007)
  analysed video of the 2006 Hajj crush and proposed *crowd pressure* (local density ×
  velocity variance) as an early-warning measure. Fruin's density levels are used as risk
  thresholds. Johansson et al. described stop-and-go waves before turbulence.
- **Smartphone crowd sensing.** Wirz et al. (2013) collected GPS from 828 app users (<1% of
  ~500,000 attendees) at the Lord Mayor's Show, London 2011. They inferred crowd density
  through a speed–density calibration against CCTV and reached r = 0.83 and RMSE 0.36/m²
  with a 55 m kernel. Densities were 0.2–2.7/m², and the method estimates current density;
  it does not forecast. The authors list sensitivity to the share of app users as future
  work, which is the question we take up.
- **Kumbh crowds.** Gayathri, Gulhare and Verma (2018) observed the Shahi Snan procession
  at the 2016 Ujjain Kumbh. 95% of surveyed pilgrims came in groups. Groups moved as
  "serpentine" chains. Gated entry to the ghat produced stop-and-go waves travelling
  backwards, and people at the rear did not know the front had stopped. That information
  gap is what upstream alerts would address.
- **Lab data for model validation.** Forschungszentrum Jülich published trajectories from
  bottleneck experiments (Seyfried et al., 2010) and corridor experiments (Zhang et al.,
  2011). These are the standard benchmarks for pedestrian models.

**Gap.** Earlier smartphone studies estimate current density at moderate densities in
Western events. None quantifies how much warning a sparse, noisy sample gives before a
crush, at Kumbh-like densities and flow patterns.

## 3. Study area and geometry

**Site.** The Sangam nose: the dry-land tip of the confluence bank at Prayagraj and the main
bathing point. Pontoon bridges, bank lanes and mela roads approach it.

**Source geometry** (the companion `sangam-command` project). All layers were traced on
Copernicus Sentinel-2 imagery of 2025-01-27 (10 m RGB, scene S2B_44RNP_20250127_0_L2A):

| Layer | Count | Notes |
|---|---|---|
| River / water mask | 1 | Constrained RGB classification; banks ±10–20 m |
| Pontoon bridges | 27 observed | Observation IDs, not official numbers; position uncertainty ~20 m |
| Pontoon approaches / bank lanes | 46 | Water portions removed |
| Mela roads | 28 | Chequered-plate temporary roads |

OSM (snapshot of 2026-10-25) supplies stations and permanent roads.

**Corridor widths.** 10 m imagery cannot resolve widths, so each feature carries an
`approx_width_m` and a `width_source`:

| Kind | Width | Source |
|---|---|---|
| Mela roads, bank lanes | 5.5 m | Measured on Google Maps satellite (Kila Ghat Rd 5.4 m, Sangam Marg ~5 m, Annapurna Rd ~5.5 m) |
| Pontoon decks | 5.0 m | Estimate |
| OSM roads | width tag > lanes × 3.5 m > class default | OSM |

**Walkable area.** `scripts/build_hotspot.py` takes a window of about 1.3 × 1.2 km around the
nose. Each corridor is buffered by its own width, the bathing zone is land within 120 m
of the nose tip, and the area is clipped to land, except pontoon decks, which cross water.
The largest connected component is kept. Result: **8.57 ha walkable, 36 corridors,
10 pontoons, 6 entry/exit gates** (Fig. S1). Before linking widths to the map, assumed
widths of 15–25 m gave 15.4 ha.

**Capacity.** Gate capacity = width × specific flow. With the original 1.3 people/m/s,
single-road gates carry about 429 people/min and the pontoon-side gate (16 m combined)
about 1,248 people/min. The validation in §5 measured a real specific flow of
1.86 people/m/s, so these capacities are probably conservative (see §6).

## 4. Simulation model

- **Software:** JuPedSim 1.4.2, `CollisionFreeSpeedModel` (Tordeux, Chraibi and Seyfried, 2016).
- **How the model moves agents:** each agent moves towards its target at the largest speed
  that keeps a time gap *T* to the agent in front:
  v = min(v₀, max(0, (s − ℓ)/T)), where *s* is the spacing and ℓ = 2r is the agent size.
  Its direction is adjusted by exponential repulsion from neighbours and walls.
- **Calibrated parameters (§5):** T = 0.6 s, r = 0.175 m. Repulsion strengths and ranges are
  at their defaults (neighbour 8.0 / 0.1 m, geometry 5.0 / 0.02 m).
- **Desired speed:** for Sangam, v₀ ~ N(1.2, 0.2) m/s clipped to [0.6, 1.8]. This is an
  assumption for pilgrims, not a measurement. Validation used the Jülich population's
  N(1.34, 0.26) (Weidmann, 1993).
- **Sangam demand:** inflow at the six gates with fixed shares (0.15/0.15/0.20/0.20/0.15/0.15,
  assumed). Reaching the goal circle (40 m radius at the nose) counts as bathed and
  removed. Outbound walkers start in the bathing zone at a fraction of the inflow
  (default 0.6) and head to a random gate. People who cannot be placed queue outside
  (backlog).
- **Outputs:** positions every 1 s. Metrics per 4 m cell: density, speed, and crowd
  pressure. Thresholds are 4/m² (free walking stops) and 6/m² (crush risk).
- **Not modelled:** groups, pushing and contact forces, overtaking intent, and behaviour
  that varies by person beyond speed.

## 5. Model validation against Jülich experiments

### 5.1 Data

| Experiment | DOI | Runs used | Participants | fps |
|---|---|---|---|---|
| Bottleneck, Caserne (Düsseldorf 2006) | 10.34735/ped.2006.2 | b090–b250: widths 0.9, 1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5 m; length 4 m | 170–179 per run (soldiers) | 25 |
| Unidirectional corridor, open boundary (Hermes, Düsseldorf 2009) | 10.34735/ped.2009.14 | 29 runs; corridors 1.8/2.4/3.0 m with varied entrance and exit widths | 61–351 per run | 16 |

Both datasets are CC BY 4.0. Each run's geometry comes from the WKT polygon in the archive
metadata.

### 5.2 Simulation set-up

- **Bottleneck:** a 7 m wide floor, a b × 4 m bottleneck at y = 0, and an 8 m wide exit room.
  Agents start 4 m in front of the bottleneck (`bottleneck_distance` in the metadata) on a
  square lattice at 3/m². The holding-area density is not recorded, so this is assumed.
  N matches the real run.
- **Corridor:** the archive polygon, with a holding area added behind the entrance, and the
  floor beside the corridor closed off (it is open in the polygon, but no participant
  used it).
- **Time step** = half a frame (0.02 s and 0.031 s). Trajectories are written at the real
  frame rate. Each run is simulated with 5 seeds and stops when everyone has left or at
  600 s.

### 5.3 Measurements (identical for real and simulated data, PedPy 1.5.1)

- **Flow through the bottleneck:** N–t at a line across the middle of the bottleneck.
  J = (k₉₀ − k₁₀)/(t₉₀ − t₁₀), the slope between the 10% and 90% passing points. Specific
  flow is the least-squares slope of J = c·b through the origin.
- **Speed–density:** Voronoi density and speed (Steffen and Seyfried, 2010) in a W × 2 m
  area at mid-corridor. Voronoi cells are cut off at 1 m. Individual speed comes from a
  0.5 s displacement window. One sample is taken every 0.25 s. Mean speed is compared per
  0.25/m² density bin, for bins of at least 0.5/m² that have at least 20 samples on each
  side. Below 0.5/m² only 1–2 people are in the area and the estimates are unreliable.
- **Pass rule (set before calibration):** the simulated flow at every width is within ±15%
  of the real one, **and** no run ends with people permanently stuck (deadlock).

### 5.4 Calibration

1. **Grid 1 (v₀ as for Sangam):** T ∈ {0.3, …, 0.7} s × r ∈ {0.15, 0.20} m. Tuned on 5 of the
   10 widths (0.9, 1.2, 1.6, 2.0, 2.5 m) with 2 seeds.
2. **Grid 2 (v₀ = Jülich population):** 11 (T, r) settings around the best of grid 1. Each
   was scored on the same 5 widths plus 7 corridor runs spanning low to high density.
   Score = mean |flow error| + mean |speed error|. Settings that deadlocked were rejected.
3. The best setting, **T = 0.6 s, r = 0.175 m**, was then checked on all 10 widths and all
   29 corridor runs with 5 seeds. The 5 bottleneck widths left out of tuning (1.0, 1.1,
   1.4, 1.8, 2.2 m) act as a hold-out check.

Every setting with r = 0.20 m clogged permanently at b = 0.9 m in at least one seed. That
ruled out several settings whose mean flow error was otherwise low.

### 5.5 Results

**Table 1. Flow through the bottleneck, real vs simulated** (people/s; simulated values are the
mean ± sd of 5 seeds).

| b [m] | Real | Default (T = 1.0, r = 0.20, v₀ 1.2) | Error | Calibrated (T = 0.6, r = 0.175, v₀ 1.34) | Error |
|---|---|---|---|---|---|
| 0.9 | 1.56 | 0.72 ± 0.02 † | −54% | 1.50 ± 0.06 | −4% |
| 1.0* | 1.84 | 0.88 ± 0.02 † | −52% | 1.73 ± 0.03 | −6% |
| 1.1* | 1.98 | 1.05 ± 0.04 | −47% | 1.87 ± 0.02 | −5% |
| 1.2 | 2.25 | 1.20 ± 0.02 | −47% | 1.97 ± 0.04 | −12% |
| 1.4* | 2.68 | 1.36 ± 0.02 | −49% | 2.34 ± 0.04 | −13% |
| 1.6 | 2.76 | 1.59 ± 0.04 | −43% | 2.82 ± 0.03 | +2% |
| 1.8* | 3.46 | 1.84 ± 0.05 | −47% | 2.98 ± 0.08 | −14% |
| 2.0 | 3.44 | 2.02 ± 0.03 | −41% | 3.47 ± 0.03 | +1% |
| 2.2* | 4.03 | 2.24 ± 0.04 | −44% | 3.82 ± 0.07 | −5% |
| 2.5 | 4.96 | 2.50 ± 0.05 | −50% | 4.32 ± 0.13 | −13% |
| **Specific flow [/m/s]** | **1.86** | **0.99** | | **1.71** | |
| **Within ±15%** | | **0/10** | | **10/10** (mean 8%, max 14%) | |

\* Not used in calibration (hold-out). † Deadlock in at least one seed.

**Speed–density.** With default parameters, simulated speed is 27–74% below the real speed in
every bin, and the model clogged at the narrowest exits. Calibrated, the mean error per bin
is 16%. The fit is close at 1–3/m². Speeds are about 30% low near 0.6/m² and up to 35%
high near 3.6/m² (Fig. 3). The real data reaches 3.9/m².

**Figures**
- Fig. 1 `figures/fig_flow_vs_width_default.png`: default model, flow about half the real flow.
- Fig. 2 `figures/fig_flow_vs_width_calibrated.png`: calibrated model, all widths inside the ±15% band.
- Fig. 3 `figures/fig_speed_density_default.png` and `figures/fig_speed_density_calibrated.png`.
- Fig. 4 `figures/fig_nt_calibrated.png`: N–t curves, real (solid) vs simulated (dashed).
- Fig. S1 `figures/fig_sangam_walkable.png`: Sangam walkable area, bathing zone, goal and gates.

### 5.6 Interpretation

- With its default parameters, the model gives bottlenecks about half their real capacity.
  Sangam runs made with it overstate queuing at pontoons and gates. Earlier exploratory
  runs (`out/in*_out60`) are therefore not used.
- After calibration, bottleneck flow is reproduced within ±15% across a 2.8× range of
  widths, including widths left out of tuning. This supports using the model for capacity
  questions on corridors 1–2.5 m wide. Extrapolating to the 5 m pontoons and roads at
  Sangam is untested.
- The speed–density relation is reproduced to about 16% between 0.5 and 3.9/m². Nothing
  above 3.9/m² is validated, including the 4–6/m² range that matters for crush risk.

## 6. Limitations (to date)

1. **Population.** The participants were German soldiers and adults. Pilgrims differ in age,
   group structure (95% in groups; Gayathri et al., 2018), speed and pushing behaviour.
   The validation checks the model's mechanism, not a Kumbh calibration.
2. **Density range.** The validation stops at 3.9/m². Crush-level densities remain unvalidated.
3. **Deadlocks.** The collision-free speed model can clog permanently at openings ≤ 0.8 m.
   Real crowds keep moving, through pushing and squeezing.
4. **Geometry.** Widths are approximate: pontoons are estimated, and roads are measured on
   satellite imagery. Only plated roads count as walkable, which probably understates the
   open sand near the nose. A gate fed by several corridors sums their widths.
5. **Capacity constant.** The configured specific flow (1.3/m/s) is below the measured 1.86/m/s.
   It has not been changed. The Phase 4 warning does not use it (the capacity is learned), but
   gate loads in the scenarios do.
6. **Demand.** Gate shares, the outbound fraction and the pilgrims' desired speed are assumed.
7. **Phase 4 scope.** The warning was tested at one bottleneck of one site, with simulated
   crowds and synthetic pings. It needs the bottleneck and its feeding roads from the map, a
   history of days near capacity, GPS error ≲ 10 m (for the queue detection) and a share of
   users that is stable across days.

## 7. Methods for remaining phases [TODO]

- **Phase 3:** Sangam test scenarios (ordinary and peak bathing days) over a range of inflows,
  with outbound flow tied to arrivals and a warm-up period. No incident reconstruction: the
  Sangam is a test site for a general method.
- **Two-way flow (found in Phase 3):** the calibrated CollisionFreeSpeed model fails Jülich
  two-way corridor runs (0/18 within ±15%, flow 17–77% low, 11/18 deadlocked): agents meet
  head-on and pack to ~7/m² where the real corridor stayed ≤ 3.5/m². JuPedSim's other models did
  not do better (SocialForce: no setting of an 18-point grid passed). In the real data,
  same-direction neighbours exceed chance only above ~1.5/m² (0.61–0.65 vs 0.51), i.e. lanes form
  when crowded, as several thin lanes. Imposing lanes on the collision-free model (each direction
  enters its own half; optionally a centre barricade) reduces peak corridor density (7.2 → 5.3/m²)
  and deadlocks (11 → 7 runs) but passes only 2/18 runs (mean flow error 29%). The remaining
  deficit sits at the corridor ends, where outgoing people must cross the waiting crowd, and at
  narrow (≤ 1 m) entrances. Driving the simulation with the measured entry times and positions
  (each person enters where and when they were first tracked and leaves where they were last
  tracked) separates set-up from model: 10/18 runs pass (mean error 19%). All runs with real peak
  density below ~1.8/m² pass but one (−3% to +2%; −17%), and all runs at ≥ ~2/m² fail (−11% to −73%),
  with the simulated corridor locking at ~5/m² where the real crowd is interleaved at 2–3/m². The
  failure threshold coincides with the density at which lanes appear in the real data. Imposed
  lanes on top of the replay make it worse (mean error 58–63% vs 41% on the crowded runs). So the
  collision-free model is validated for two-way flow up to ~1.8/m² only; counter-flow areas above
  ~2/m² in site scenarios are reported as unvalidated. The AnticipationVelocity model (Xu et al.,
  2021), designed for bidirectional flow, was calibrated in two stages (time gap × radius, then
  anticipation × reaction time; 24 settings): its best setting matches flow while people move
  (bottleneck 7%, two-way 3%) but every setting freezes permanently in every one-way corridor run and
  in most two-way runs, so it was rejected. Site scenarios therefore use one-way routing wherever
  counter-flow would exceed ~2/m², as one-way pontoon systems at the Kumbh already do.
- **Phase 3 results so far (ordinary day, one-way routing):** inbound through G3/G4/G5, outbound
  through G0/G1/G2, 60% of bathers walk back out after 10 min; 75 min per run, one seed. Peak
  density stays below 4/m² at 250 and 500 people/min (2.1, 2.9/m²). At 1000/min the merge of the
  G3 and G4 roads (demand 700/min vs capacity 429/min) holds ≥ 4/m² from minute 17 over 2,659 m²;
  at 1500/min all inbound gates are over capacity, ≥ 4/m² from minute 15 over 5,481 m², and
  14,299 people are still outside the gates at the end. No dense cell is in counter-flow. Where the
  jam forms depends on the assumed gate shares: with an equal split the merge still jams, with half
  of arrivals at G5 it does not (max 4.8/m²) and the queue moves outside G5. Gate shares are
  therefore treated as an uncertain input in Phase 4.
- **Phase 4:** synthetic pings drawn from the simulated agents. Variables: share of users
  (1–5%), ping interval (5–30 s), GPS error (σ = 5/10/20 m, plus outliers and dropouts),
  and map-matching to the walking network. Estimators: kernel density (after Wirz et al.)
  and speed-based detection of stop-and-go waves and rising crowd pressure. Go/no-go:
  2% of users gives density within ±30% and at least 5 min of warning.
- **Phase 4 results, first pass (one jam, one calm run; `docs/research_log.md`):** with 2% of
  people reporting every 15 s with 10 m GPS error, density in 20 m zones is estimated within a
  median 23% when the phone share is known (21–29% for 12–32 m zones). A trend rule (count
  projected 10 min ahead) warns 5.4 min (median) before the first ≥ 4/m² event, close to the 5.3 min
  it gets with perfect data from everyone; a plain count threshold (2/m²) gives 3.6 min and phone
  speed comes too late in this model. But sampling noise raises alarms in 31–59 zones (counted before slivers of road under 50 m² were
  excluded, which removed about half of them) on a calm
  75 min run where perfect data raises none, so the warning is not yet usable. The lead time is
  limited by the warning rule, the false alarms by the number of phones per zone.
  (Figs. `fig_phase4_lead_vs_share.png`, `fig_phase4_density_error.png`, `fig_phase4_false_alarms.png`.)
- **Phase 4, smarter rules:** 96 warning rules (hold time, neighbouring zone, phone speed, window,
  zone size), selected on one jam and one calm run and checked on two new runs, with the pass
  criterion fixed beforehand (2% phones: density ±30%, ≥ 5 min warning in ≥ 80% of draws, ≤ 1 false
  alarm per hour). No rule passes at 2%: the rules that meet the false-alarm limit warn at most
  ~3 min ahead (median), and the ones that warn 5 min ahead raise 20–50 false alarms per hour.
  With perfect data the best rule warns 5.3–6.7 min ahead, so density alone leaves little margin.
  At 5% phones a trend rule on 32 m zones comes close (≤ 1 false alarm/hour; ≥ 5 min ahead in 25% of
  draws on the training jam, 85% on the holdout). (Fig. `fig_phase4_rules.png`.)
- **Phase 4, flow signals:** counting phones entering minus leaving an area does not help at 2%
  (the build-up is a small difference of two large flows). Comparing the demand heading for a
  known bottleneck with its capacity does: with 2% of people reporting every 15 s, counting phones
  just inside the two feeding gates (~500 m upstream) and alarming when demand exceeds the merge's
  capacity (429/min) warns a median 13.8 min before the first ≥ 4/m² cell on both the training and
  the holdout jam (≥ 5 min ahead in 100% of draws), with no false alarm on the median calm day
  (one false alarm in 10–30% of calm draws). This passes the pre-set go criteria. It requires the
  bottleneck and its capacity to be known from the map, covers only listed bottlenecks, assumes
  the phone share is known, and has not yet been tested with demand near capacity, a gradual
  rise in arrivals, or the higher measured capacity (1.86 people/m/s). (Fig. `fig_phase4_bottleneck.png`.)
- **Phase 4, stress test:** with the rule fixed, five new runs with 380–550 people/min heading for the
  merge and one with arrivals rising over 30 min. The jammed merge passes ~600/min (1.82 people/m/s);
  jams form at 550/min but not at 480/min within 60 min. With the threshold at 429/min every jam
  is warned 14–23 min ahead (including the slow rise), but 85–90% of days at 430–480/min raise a
  false alarm; at 614/min false alarms vanish but the 550/min jam is mostly missed and leads fall
  to 5–9 min. The warning therefore stands or falls with the bottleneck's effective capacity,
  which has to be measured per site. (Fig. `fig_phase4_stress.png`.)
- **Phase 4, self-calibration:** the phones learn the capacity from a history of nine days
  without simulation truth (demand at the gates on days with and without a queue at the merge,
  the queue detected from phone speeds). 2% phones saw a queue on every jam day and on no calm
  day; the learned capacity (535/min with every phone) matches the tipping point from the stress
  test. On six fresh runs (460–620/min) the frozen rule warned every jam 13–39 min ahead (≥ 5 min
  in 90–100% of draws), but alarmed on 65–100% of draws on the three days that did not jam. At
  500–520/min even perfect data alarms: these days are within ~5% of capacity and do not jam within
  the hour, a grey zone the jam definition cannot resolve. At 460/min the false alarms come from
  the phones: ~16 phones in a 2 min window give ~25% noise on demand. Self-calibration thus fixes
  the capacity, but 2% phones are not precise enough to separate demand 15% below capacity from
  demand at capacity. (Fig. `fig_phase4_calibrate.png`.)
- **Phase 4, longer window and two-level alert:** counting over 5 min instead of 2, with an
  amber alert at 80% of the learned capacity and a red one above it (2 σ, held 2 min), chosen
  on the history runs and tested unchanged on six unseen runs (450–600/min). Red on days without
  a jam fell from 65–100% of draws to 0–20%, and those days got amber instead; amber came
  14–17 min before both jams. But red came before the jam in only 15–30% of draws: at 2% phones
  2 σ is ~27% of demand, while these jams form at 5–12% over capacity. With every phone red came
  17–21 min ahead. The pre-set criteria are not met (both jam days fail on red). At 2% the
  system can give an early "near capacity" warning but not an early, reliable "over capacity"
  one. (Fig. `fig_phase4_two_level.png`.)
- **Phase 4, phone share for the two-level alert:** with the same rule at 2, 5, 10 and 20% phones
  on the unseen runs, red came before the two jams in 10/35%, 25/80%, 70/100% and 90/100% of draws
  (everyone 100/100%), and the first alert came ≥ 5 min ahead in every draw from 5% on. Red thus
  needs ~20% phones to be early and reliable. No share passed all six days: a day just under the
  busy line got amber at every share, and a no-jam day whose demand (546/min) was above the
  learned capacity (535/min) got a false red more often as noise fell (25% at 2%, 45% at 20%,
  0% with every phone). The history brackets the capacity only between 497 (no jam) and 573/min
  (jam); rules re-chosen at 10–20% overfit this history. Beyond the phone share, red near
  capacity needs a history with days close to capacity on both sides. (Fig.
  `fig_phase4_two_level_shares.png`.)
- **Phase 4, ping interval and GPS error:** with pings every 5 or 30 s and GPS error of 5 m the
  results stay close to the baseline (15 s, 10 m); at 30 s and 2% the first alert comes later
  (median 9–10 min). At 20 m GPS error the method fails in its learning step: the phones no
  longer see the slow queue on the mildest jam day (10% of draws vs 100% at 10 m), the learned
  capacity comes out too high, and red never fires before a jam. The learned capacity is in
  "phone units" (it differs per ping setting, 318–560/min) and the alert condition does not
  depend on the assumed share of users, so neither needs to be known, as long as the same
  phones are used for learning and alerting.
- **Phase 4, conclusion:** sparse pings do not resolve crowd density in small zones well enough
  to warn, but they do measure how many people are heading for a known bottleneck. With 2–5% of
  users this gives an early near-capacity warning (14–20 min ahead in the simulation); a reliable
  over-capacity alarm needs ~20%. No method met the pre-set go criteria in full (2%: ≥ 5 min ahead
  in ≥ 80% of draws and ≤ 1 false alarm per hour). The method's precision near the line is set by
  how well the capacity is known: the past days must include days just below and just above it.
- **Phase 5:** upstream alerts, inflow holds and re-routing.

## 8. Reproducibility

| Item | Value |
|---|---|
| Code | github.com/piyushchouhan/crowd-research (MIT); geometry: github.com/piyushchouhan/sangam-command |
| Software | Python 3.12, JuPedSim 1.4.2, PedPy 1.5.1, Shapely 2.2, NumPy 2.5 |
| Configuration | `config/sim.json` (all assumptions in one file) |
| Validation data | `data/juelich/README.md` (download commands, citations) |

```sh
.venv/bin/python scripts/build_hotspot.py
cd scripts
# Validation as reported (Table 1, Figs. 1–4)
../.venv/bin/python validate_juelich.py --dataset all --seeds 5 --name calibrated \
  --set agents.desired_speed_mps.mean=1.34 agents.desired_speed_mps.sd=0.26
# Default-parameter baseline
../.venv/bin/python validate_juelich.py --dataset all --seeds 5 --name baseline \
  --set agents.time_gap_s=1.0 agents.radius_m=0.2
```

## References

- Fruin, J. J. (1993). The causes and prevention of crowd disasters. *First International
  Conference on Engineering for Crowd Safety*, London.
- Gayathri, H., Gulhare, S., & Verma, A. (2018). Understanding crowd dynamics in processions
  during mass religious gatherings: A case study of Shahi Snan in Kumbh Mela. *Proceedings of
  PED 2018*, Lund, 403–412.
- Helbing, D., Johansson, A., & Al-Abideen, H. Z. (2007). Dynamics of crowd disasters: An
  empirical study. *Physical Review E*, 75, 046109.
- Seyfried, A., Boltes, M., Kähler, J., Klingsch, W., Portz, A., Rupprecht, T., Schadschneider,
  A., Steffen, B., & Winkens, A. (2010). Enhanced empirical data for the fundamental diagram
  and the flow through bottlenecks. In *Pedestrian and Evacuation Dynamics 2008*, Springer,
  145–156. Data: doi:10.34735/ped.2006.2.
- Steffen, B., & Seyfried, A. (2010). Methods for measuring pedestrian density, flow, speed
  and direction with minimal scatter. *Physica A*, 389(9), 1902–1910.
- Tordeux, A., Chraibi, M., & Seyfried, A. (2016). Collision-free speed model for pedestrian
  dynamics. In *Traffic and Granular Flow '15*, Springer.
- Weidmann, U. (1993). *Transporttechnik der Fussgänger*. IVT, ETH Zürich.
- Wirz, M., Franke, T., Roggen, D., Mitleton-Kelly, E., Lukowicz, P., & Tröster, G. (2013).
  Probing crowd density through smartphones in city-scale mass gatherings. *EPJ Data
  Science*, 2, 5.
- Zhang, J., Klingsch, W., Schadschneider, A., & Seyfried, A. (2011). Transitions in pedestrian
  fundamental diagrams of straight corridors and T-junctions. *J. Stat. Mech.*, P06004.
  Data: doi:10.34735/ped.2009.14.
- Contains modified Copernicus Sentinel data 2024–2025. © OpenStreetMap contributors (ODbL).
