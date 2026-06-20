# SheetCircuit — Pending Updates

Roadmap for the remaining "track-agnostic / de-pin from sample data" work, plus the
deferred time/duration race buildout. **Done** on branch `refactor/track-agnostic-sim`:
Phase 1 (events own race length + physical-units attrition + creator event editor +
starter-by-criteria, `f4e745e`); Phase 2 (re-anchor orphan-stat references to intrinsic
design anchors, `e796a2b`); Phase 3 (car class derived at runtime from a drag/slalom/hybrid
reference suite + the on-track gulf widened, `5b23a58`/`6118935`, with the F1/F2 class
explainers `084eba0`). Phase 4 (below) is reassessed and ready to build. This document is
self-contained so it can be ported to an issue tracker or another repo.

Conventions used below:
- References are by **symbol/function name**, not line number, so they survive edits.
- Every phase is its own commit and must leave `python3 -m unittest discover -s tests`
  green, deliberately re-pinning `tests/test_balance_baseline.py` in the same commit if
  the change legitimately shifts the reference race (its docstring already says to).
- "Don't pin to the sample catalog" is the throughline: references should be intrinsic
  design choices or real-world magnitudes, never `min/max/mean` of whatever cars happen
  to be loaded (a car's performance must not depend on what other cars exist).

---

## Phase 2 — Re-anchor the orphan-stat references (de-pin from catalog means)

### Problem
`constants.py` (the "Orphan-stat reference points" block) states outright that its
reference points are *"the catalog means at the time of wiring."* These centre every
secondary-stat fold at the mean of the original 27 cars, so as the catalog grows or a
custom car (e.g. the Bugatti Veyron facsimile) is built, "neutral" drifts away from
reality and composition stops meaning what it should.

Affected constants (all in `constants.py`), consumed by `game/effective_stats.py`
via `_centered_factor(value, REF, per_unit)` and the `*_IDEAL` penalties:
- Rating centre: `RATING_REF` (65).
- Engine character: `TORQUE_RATIO_REF` (1.23), `POWERBAND_REF`, `THROTTLE_RESPONSE_REF`.
- Chassis: `RIGIDITY_REF`, `CENTER_OF_GRAVITY_REF`, `ROTATION_REF`, `WEIGHT_DIST_IDEAL`,
  `WEIGHT_REFERENCE_KG` (1100).
- Tyres: `TIRE_WIDTH_FRONT_REF` (214), `TIRE_WIDTH_REAR_REF` (231), `TIRE_WARMUP_REF`.
- Brakes: `BRAKE_COOLING_REF`, `BRAKE_FADE_REF`.
- Suspension: `BUMP_ABSORPTION_REF`, `STEERING_PRECISION_REF`, `COMPLIANCE_REF`,
  `CURB_HANDLING_REF`.
- Aero/fuel/durability: `AERO_EFFICIENCY_REF`, `FUEL_EFFICIENCY_REF`,
  `FUEL_CAPACITY_REF_L` (now unused after Phase 1 — delete), `DURABILITY_REF`,
  `GEARBOX_CONDITION_REF`, `BODY_CONDITION_REF`.
- Tune "ideals" (catalog-mean default setups): `SUSP_STIFFNESS_IDEAL` (49),
  `ANTIROLL_IDEAL` (4.5), `DIFF_POWER_IDEAL` (34), `DIFF_COAST_IDEAL` (18),
  `DIFF_PRELOAD_IDEAL` (15).

### Approach (decided)
Re-base these to **intrinsic / absolute design anchors**, not the live catalog. Do NOT
compute them from `load_cars()` at runtime — that makes a car's effective stats depend
on what else is loaded, which is wrong for a sim and non-deterministic for tests.

1. For each `*_REF`, pick a principled fixed value: a midpoint of the stat's *design
   range* (e.g. 0-100 ratings → 50, or a documented "typical" value), not the seed mean.
   Document the intent in the comment ("a neutral mid-spec X", not "catalog mean").
2. For tune `*_IDEAL`, anchor to the *neutral setup* meaning (the setup that neither
   helps nor hurts), independent of what the seed cars happen to ship.
3. Delete `FUEL_CAPACITY_REF_L` and its now-dead comment (Phase 1 removed its use).
4. Keep the orphan clamp band (`ORPHAN_FACTOR_FLOOR/CEIL`) so no single axis can swing
   too far — this contains any rebalance.

### Touch points
- `constants.py` (the reference block).
- `game/effective_stats.py` (consumers — values only, logic unchanged).
- `tests/test_balance_baseline.py` — re-pin `PLAYER_TOTAL_BASELINE` + the reference-lap
  band if the new anchors shift the kanto@maple reference.
- `tests/test_orphan_stats.py` — these assert *relative* effects (wider tyre → more
  grip, etc.); they should still hold, but verify each.

### Acceptance criteria
- A custom out-of-distribution car (build the Veyron via the creator) lands in a sane
  place on every axis (no axis pinned to the orphan clamp purely from being non-typical).
- `test_orphan_stats` relative directions all still pass.
- Reference race re-pinned and green; the catalog's intra-class competitiveness guard
  (`tests/test_supercar_tracks.py`) still holds.

### Risk
Medium balance shift across the whole catalog. Do it alone (no other behavioural change
in the same commit) so any regression is attributable.

---

## Phase 3 — PR / class generalisation (one source of truth)

### Problem
Two conflicting notions of "class" exist:
- `car.identity.car_class` — a **stored** string (E…S), used by `opponents._class_allowed`
  for event eligibility and by event `car_class_limit`.
- `derived_rating()` / `class_rating()` in `game/effective_stats.py` — a **computed** PR
  from `CLASS_RATING_WEIGHTS` × clamped effective axes × `CLASS_RATING_SCALE` (4),
  bracketed by `CLASS_THRESHOLDS`.

They can disagree. The formula is grip/handling-weighted and centred on ~1100 kg starter
cars (`WEIGHT_REFERENCE_KG`), so it doesn't generalise: the Veyron facsimile computes
**PR 347** (≈ C/D bracket) while being hand-labelled **S**. A heavy, very fast hypercar
is under-rated by a formula tuned to light nimble cars.

### Approach (decided — Option A, runtime-derived)
**Derive class at runtime from a fixed reference suite, never stored** (the de-pin
principle: a custom/creator car must get a real class with nothing to look up). A car's
PR = its mean capability *composite* across three intrinsic in-code fixtures -- a drag
run, a slalom, and a hybrid (`game/reference_suite.py`) -- scaled by `CLASS_RATING_SCALE`
(now 10), bracketed by re-anchored `CLASS_THRESHOLDS`. Tier basis is the **mean** across
archetypes; the per-archetype split surfaces as the car's **shape** (`performance_type`:
Power/Handling/Balanced/Challenge), so same-tier cars are still distinguished (the torino
reads "E · Challenge", the detroit "E · Power"). The capability composite is
`base_lap_time`-independent, so the 3b race-pace tune does not move the tiers.

Split into two commits:
- **3a (done)** — runtime class/shape + drop stored `car_class` everywhere. Single source
  of truth: `effective_stats.derived_class()`; eligibility (`opponents._class_allowed`)
  and all display/sort readers route to it. Stored `car_class` removed from `CarIdentity`,
  `car_from_dict`, all 27 `data/cars/*.json`, and the creator schema. Event
  `max_class_rating` restrictions rescaled to the new PR scale (`new = round(1.4·old+60)`).
- **3b (done)** — widen the on-track race gulf: `PERF_SCALE` 0.25 -> 0.36, so a hypercar
  laps a pure drag ~49% quicker than a 32 hp microcar (was ~33%) while equal-capability
  cars stay even. Added a `MIN_LAP_FRACTION` lap-time floor; re-pinned the balance
  baseline and the (now wider) S-class competitiveness guards.

### Follow-ups
- **F1 — player explainer (done).** Help explains class is computed from a fixed
  drag/slalom/hybrid reference suite; the car detail screen has a "Class Derivation" table
  (per-fixture capability -> mean -> PR -> class/shape) via `effective_stats.class_breakdown`.
- **F2 — creator derivation (done).** The creator preview shows the per-fixture suite
  scores live (`editor/app.py`) alongside the derived class.

### Acceptance criteria (met in 3a)
- A spread of archetypes land in sensible brackets; a fabricated Veyron reads top-tier
  (S, PR ~1030), the kei `kanto_k660` bottom-tier (E) -- both computed, no stored class
  (`tests/test_reference_class.py`).
- Event eligibility still works; existing events still admit the intended fields.

### Risk
Medium-high (touches the progression/economy backbone via class gating). Isolated to 3a.

---

## Phase 4 — Time / duration races (wire in the deferred buildout)

### Time-scale model (decided)
Keep three quantities strictly independent (NBA2K's "quarter length" slider wrongly
fuses them, which is what produces the "season of 2-min quarters" odd-numbers trap):
1. **Canonical clock** — the real in-world seconds a race takes (`laps × base_lap_time`
   or `duration_s`). This is the only one that drives physics, attrition, strategy, and
   points. The engine already integrates real `seconds`, so this exists.
2. **Sim resolution** — `ticks_per_lap` (4–16). Integration granularity only; the
   outcome is a Riemann sum over the same real seconds, so it is already
   resolution-invariant. Never let it affect results.
3. **Presentation speed** — wall-clock the player spends (1× live → fast-forward →
   instant-resolve). A pure render multiplier; must have **zero** effect on the result.
   Does not exist yet — add it as a runtime/UI concept, not race data. For *interactive*
   races this also sets **decision density** (canonical seconds between player commands):
   the real arcade↔sim feel knob, still presentation-layer, never canonical length.

**Regime: A now, B later.** Regime **A** = fixed canonical length per event; watchability
is solved by presentation speed, so results never change with how you watched and the
odd-numbers trap is structurally impossible. Build A first. **B** (player-selectable
sprint/full/enduro with economy outputs — points/prize/XP — normalised to a reference
distance so seasons stay comparable) is a later layer on the same plumbing: A + a
normalisation factor on extrapolatable rewards only. **Never** ship C (selectable length
with raw, un-normalised rewards).

### Reassessment after Phases 2–3 (two findings reshape this phase)
1. **One lockstep engine.** The game races via `race_session` (interactive, the whole field
   shares a track position each tick); "instant resolve" (`actions.simulate_to_end_action`)
   just loops that engine's ticks, so watch-live and instant are already
   presentation-invariant. `simulate_race` (batch) is for tests. Because the engine is
   lockstep, a **Regime-A duration race produces no ragged lap counts** — the field runs the
   same number of laps and the race ends on time. So the original "ragged ranking / lap-aware
   gap / +N laps / ragged telemetry" work is **out of scope for v1** (it needs async — see
   the follow-up below). Decision: **lockstep now, async later.**
2. **`base_lap_time` is unrealistic and 3b made it worse.** It was watchability-set
   (~85–120 s on every track regardless of length), so the 64 hp k660 "averages" 205 km/h
   on cresta and 154 on glenmoor. 3b (`PERF_SCALE` 0.25→0.36) dropped lap times further; we
   loosened the lap-time bands with a "Phase 4 retightens" note. Making lap time real is the
   core of this phase.

Already wired from Phase 1: `Event.duration_s` parses; `loader.resolve_race` returns
`RaceFormat(mode="duration", …)`; `_rank` sorts `(-lap, total_time)`; wear accrues over real
`seconds`; `event_detail_screen` already prints a duration description. Two
`SimulationError("Duration-based races are not yet supported")` guards (`simulation.py`,
`race_session.py`) are the live blockers.

### Work to do (four sub-commits)
**4.1 — Derive `base_lap_time` fully dynamically from track geometry (decided).** Never
stored; computed from the track's own segments at load (mirrors how a real lap estimate
comes from the corner/straight sequence): (a) a track **speed factor** from its segment
tag mix (an intrinsic tag→reference-speed table, consistent with `SEGMENT_TAG_WEIGHTS` —
straights fast, chicanes slow), integrated `Σ length_pct × tag_speed`; (b) realistic
reference lap `ref_lap = length_km / (BASE_REFERENCE_SPEED × speed_factor) × 3600`; (c)
`base_lap_time = ref_lap + PERF_SCALE × REFERENCE_COMPOSITE`, so a notional average car
(fixed intrinsic `REFERENCE_COMPOSITE`, not a live catalog stat) laps at `ref_lap` and a
below-average kei correctly laps slower. Additive constant ⇒ rescales absolute lap times
without changing who wins; auto-updates for custom/creator tracks. Coordinate with
`PERF_SCALE` (a larger base on long tracks compresses the % gulf — re-check the 3b
drag-fixture gulf, nudge if needed) and retighten the 3b-loosened bands. Touch:
`game/loader.py` (`track_from_dict`), `constants.py` (tag-speed table, `BASE_REFERENCE_SPEED`,
`REFERENCE_COMPOSITE`), `data/tracks/*.json` (drop stored `base_lap_time`), `editor/`
(derived base in preview), re-pin `test_balance_baseline.py` / `test_supercar_tracks.py`,
new `tests/test_lap_time_realism.py`.

**4.2 — Run duration races (lockstep time-cap, Regime A).** Lift both guards; add one
`_race_finished(states, race_format)` predicate (laps → lap count; duration → leader
`total_time >= duration_s`, then finish the lead lap) used by the batch loop and the
interactive `is_finished`. Field stays synchronized ⇒ `_rank` and the time-delta
`gap_to_leader` are unchanged. `RaceResult.total_laps` / `RaceSession.total_laps` become the
completed lap count. Validate a thirsty car (`escarpa_pikes`) is forced to pit over a long
event (Phase 1 attrition already drives this). Touch: `game/simulation.py`,
`game/race_session.py`, new `tests/test_duration_race.py`.

**4.3 — Presentation speed (watchability).** Decoupled from the sim (zero outcome effect).
Instant-resolve and "end" exist; add a "skip to next lap" / fast-forward control to the race
loop so a multi-hour event isn't ticked by hand. Touch: `interfaces/cli.py` (race loop +
`_show_race_help`), `game/actions.py` (advance-to-lap-end helper).

**4.4 — Duration-aware UI + creator copy.** Race screen shows elapsed/target time instead of
"Lap X/Y" for a duration race; drop "duration not yet raceable" in `editor/fields.py`. Touch:
`game/actions.py` `race_screen`.

### Acceptance criteria
- Every car laps at a plausible speed for the track's length (no 200 km/h keis); k660@maple
  stays sane; baseline re-pinned.
- A `duration_s` event runs to completion in both watch-live and instant-resolve with the
  same result; a short sprint and a long enduro on one track feel different (enduro forces a
  fuel/tyre stop).
- A long event is watchable via fast-forward; the race screen reads in time, not "Lap X/Y".

### Risk
High — 4.1 touches every lap time (race-pace backbone), 4.2 the finish condition. Isolate
4.1 (balance) from 4.2 (mechanic); each its own commit, baseline re-pinned.

### Deferred follow-up — async / ragged enduro
Each car holds its own track position ⇒ true lapped cars, "+N laps", lap-aware
`gap_to_leader`, ragged per-car telemetry. A separate phase on top of 4.x once the time
model + realistic `base_lap_time` are stable; the lockstep duration above already gives long
races, real strategy, and realistic time.

---

## Small deferred cleanups (fold into a convenient commit)

1. **`fuel_efficiency` duplication.** It lives on **both** `PowertrainStats.fuel_efficiency`
   and `FuelStats.fuel_efficiency` and is averaged in `effective_stats.compute_effective_stats`
   (`fuel_efficiency = (pt.fuel_efficiency + fu.fuel_efficiency) / 2`). Pick one home
   (recommend `fuel.fuel_efficiency`), drop the other from `models.py`, `loader.py`,
   the effective-stats average, the creator schema (`editor/fields.py`), and all 27
   `data/cars/*.json`. Cosmetic; no balance change if the single value equals the old
   average input.

2. **Attrition calibration by feel.** Phase 1 calibrated the physical constants to land at
   realistic stint/range, but the **fuel-economy spread is too wide** (the kei
   `kanto_k660` reads ~4.6 L/100km — hypermiling territory). The *shape* is right (thirsty
   cars need enduro stops); the absolute numbers are tunable:
   - `FUEL_L_PER_KM_UNIT` (0.13) — global economy scale.
   - `TYRE_WEAR_PCT_PER_KM` (1.25) — global tyre-life scale.
   - `ENGINE_HEAT_PER_S`, `ENGINE_COOL_PER_S`, `TIRE_HEAT_PER_KM`, `TIRE_COOL_PER_S`,
     `DRIVER_*_PER_S` — time/work rates.
   Consider making economy **affine** (`economy = floor + eff.fuel_burn_rate × unit`) to
   compress the kei↔hypercar range into a realistic ~15–65 L/100km band instead of the
   current ~5–95. Verify against `tests/test_attrition_physical.py`
   (`test_realistic_stint_and_range_order_of_magnitude`).

---

## Suggested order
Phase 2 → Phase 3 → small cleanups → Phase 4. Each its own commit, baseline re-pinned in
the same commit, full suite green before moving on (so any fault stays bisectable).
