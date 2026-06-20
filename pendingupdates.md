# SheetCircuit — Pending Updates

Roadmap for the remaining "track-agnostic / de-pin from sample data" work, plus the
deferred time/duration race buildout. Phase 1 (events own race length + physical-units
attrition + creator event editor + starter-by-criteria) is **done** on branch
`refactor/track-agnostic-sim` (commit `f4e745e`). Phase 2 (re-anchor the orphan-stat
references to intrinsic design anchors) is **implemented, pending review/commit**. This
document is self-contained so it can be ported to an issue tracker or another repo.

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

**Anchor `base_lap_time` to realism (decided).** The current per-track lap times (and the
84–90 s reference band) were chosen for watchability, not realism. Derive/validate
`base_lap_time` from `length_km` × a plausible class average speed (a real-world
magnitude), and move watchability entirely to presentation speed. Then the reference-lap
test asserts realism (a class's average speed on the track), not a comfort window. Expect
to adjust some `data/tracks/*` values and re-pin `test_balance_baseline.py` in the same
commit. Continues the de-pin throughline.

Phase 1 made the model **duration-ready**; this phase makes it **raceable**. Already in
place:
- `Event.duration_s` parses and validates; `loader.resolve_race` returns
  `RaceFormat(mode="duration", laps=None, duration_s=…)`.
- `simulation._rank` sorts by `(-lap, total_time)` — correct for cars on different lap
  counts.
- `simulate_race`'s loop is predicate-shaped (`while completed_laps < total_laps`).
- Engine heat and driver fatigue accrue over real `seconds` (threaded through
  `_apply_lap_wear`), so a longer race fatigues correctly with no further change.
- Both `simulate_race` and `race_session.start_race` currently **raise**
  `SimulationError("Duration-based races are not yet supported")` when `laps is None` —
  these are the two guards to lift.

### Work to do
1. **Completion predicate.** Replace the fixed-lap guard with: run laps until the leader's
   `total_time >= duration_s`, then every car finishes its current (lead) lap — standard
   enduro rule. Factor a `_race_finished(states, race_format)` helper used by both the
   batch loop (`simulate_race`) and the interactive loop (`race_session.simulate_tick`).
2. **Ragged lap counts.** With a time cap, faster cars complete more laps. `_rank` already
   handles this; audit everything that assumes a uniform lap count:
   - `gap_to_leader` must become **lap-aware** (a car a lap down is behind even with lower
     elapsed time). Compute gap as (laps_behind × leader_avg_lap) + time_delta, or show
     "+N laps".
   - `RaceResult.total_laps` / `RaceSession.total_laps` become the **leader's** lap count
     (or per-car); the UI ("Lap X/Y") needs a duration-aware variant.
   - Telemetry (`record_telemetry`, `TelemetryHistory`) is per-lap; ensure per-car lap
     arrays of differing length don't break standings/plots.
3. **Interactive path.** `race_session` derives `ticks_per_lap` from `base_lap_time`; that
   still works per lap, but `is_finished` (currently `current_lap >= total_laps`) must use
   the time predicate, and the per-car ragged-lap bookkeeping must hold across ticks.
4. **Pit/strategy.** With real duration + physical fuel/tyres (Phase 1), enduros should
   *need* stops — validate that a thirsty car (e.g. `escarpa_pikes`, ~74 km range) is
   forced to pit over a multi-hour event. Tune `pit_lane_loss_s` and refuel/tyre-change
   semantics in `_apply_lap_wear`'s `pit` branch if a stop should restore a real amount.
5. **UI/creator.** The creator event editor already exposes `duration_s` (race_mode
   `duration_s`) and labels it "not yet raceable" — flip that copy on completion. Add a
   duration-aware race screen (`game/actions.py` `race_screen`, `event_detail_screen`).

### Acceptance criteria
- A `duration_s` event runs to completion; standings rank by laps-completed then time;
  a lapped car shows "+N laps".
- A short sprint and a long enduro on the *same track* both work and feel different
  (enduro forces fuel/tyre strategy).
- New `tests/test_duration_race.py`: time predicate stops correctly; ragged ranking;
  lap-aware gap; thirsty car is forced to pit.

### Risk
High — it changes the race core (loop + ranking + UI). Land it after Phases 2–3 so the
balance baseline is stable underneath it.

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
