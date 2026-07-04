# SheetCircuit — Changelog

Work on the `refactor/track-agnostic-sim` branch: making the simulation track-agnostic,
de-pinned from the sample catalog, and honest about time. Newest first.

## UI consistency

- **Creator knobs in the tune menu** — almost everything the creator can edit on a car
  is now a tweakable knob in-game. The tune editor gains the creator's hard-mod stats
  (28 new fields): the full Tyres group (compound/widths/grip/wear/heat/warmup), all
  brake and suspension ratings, body aero (downforce/drag/efficiency/high-speed
  stability), a new Chassis section (weight distribution, CoG, rigidity, stability,
  rotation) and fuel efficiency — 50 knobs across 6 sections, same staged-draft flow,
  free to apply. Hard mods write straight into the car's stat sections (they persist
  through save/load and move PR/class live). Intrinsic properties stay creator-only:
  identity/value, the engine itself (hp/torque/aspiration/powerband/throttle/cooling/
  stress), weight_kg, durability build quality, fuel hardware, and condition (that's
  wear). The compound vocabulary moved to `constants.TIRE_COMPOUNDS`, shared by the
  creator and validated in-game (events' `allowed_tires` restrictions read it).
- **Creator-style tune editor** — the in-game Tune flow now has the creator's look and
  feel: a sections menu (Tyres/Drivetrain/Brakes/Suspension/Aero) opens one group of
  knobs at a time instead of one flat 22-row screen, and the editor is a persistent
  session (edit as many fields as you like before leaving). Edits STAGE into a draft —
  nothing touches the car until `[W]` applies the whole draft atomically — and backing
  out with staged changes asks apply/discard/keep-editing. Every screen carries a live
  PR/class/stat readout with before→after deltas (no lap-sim panel in-game; the event
  screen's Est. Time covers that). Same flow in the terminal CLI and the browser
  adapter; `tune <car> <field> <value>` stays for one-shot typed changes.
- **Sort everywhere you choose** — every picker prompt now accepts the same `sort`
  grammar as the main screens (buy, sell, repair, hire, fire, ext, and all three
  race-entry steps), in both the terminal CLI and the browser adapter. Sorting inside
  a picker feeds the same per-screen sort state, so the order sticks when you return
  to the matching main screen. `actions.race_entry_screen` gained a `sort_spec`
  pass-through for API parity. The tune flow is deliberately exempt (the tune fields
  list keeps its authored subsystem grouping).

## Simulation audit

- **Breathing follow gap; audit docs retired** — a failed pass now holds the car in a
  band `[OVERTAKE_FOLLOW_GAP_S, +OVERTAKE_GAP_JITTER_S]` re-drawn every tick, so train
  gaps flutter like a car bobbing in the wake instead of freezing at exactly 0.400s.
  The jitter exposed an interleave in the stacking sweep (two same-tick holds behind
  one defender could land 0.007s apart); the sweep now guards both sides of a settled
  car. `SIM_AUDIT.md` (every item fixed) and `pendingupdates.md` retired — content in
  git history; the roadmap's unbuilt items (settings menu, ragged enduro, gravel twin,
  reference manual) were dropped with it.
- **Overtaking math fix** — the `d936448` overtake gate froze every field into a train
  behind whoever was processed first (the player, on ties), pinned at exactly the follow
  gap, and dragged faster cars down to the leader's pace. Two rules fixed for all tracks:
  a car that was not strictly ahead when the tick began (standing start / dead heat)
  holds no road to defend, and a *won* contest now completes the pass — the pair
  exchange race clocks (time-conserving), so the move genuinely reorders the road
  instead of evaporating at the ranking step. Passes are logged to the race log.
- **Audit record & docs** — SIM_AUDIT.md tracks every finding from the full engine audit
  with per-item status; AGENT_MAP updated for the reworked race flow.
- **Engine rework** (`d936448`) — attrition endgame (dry-tank limp, heat as a passive-cooling
  *balance* with thermal character per car), rule-based AI pit boss + terminal failures,
  mid-race damage and live driver energy, distance-scaled per-system post-race wear, weekly
  calendar, live overtaking (passes must stick; trains form on narrow tracks; racecraft and
  overtake_difficulty finally load-bearing), race-day weather rolled from weather_variability,
  fuel load as lap time, per-entry effective-stats cache (~8x faster ticks), collision-safe
  tick RNG stride, one-shot pit in run-to-flag, batch sim charges the entry fee. Race log
  publishes each event exactly once (was re-emitting stale events every lap) and crashing
  cars' messages are no longer dropped.
- **Guard suites** (`3ed556d`) — test_attrition_endgame + test_wired_systems pin all of the
  above; existing heat/money/baseline pins re-pinned deliberately (dry pace verified
  bit-for-bit unchanged; balance seed 7 now characterizes a wet race).
- **Groundwork** (`ce85c20`) — constants blocks, session weather/cache fields, forecast
  roll/escalation in the loader, terminal-failure + fatigue terms in telemetry, resale
  depreciation in the economy.
- **Crash fix** (`40b9041`) — event detail screen crashed whenever the garage had a car
  (EffectiveCarStats passed where a Car was expected).

## Honest time & pace

- **Proportional pace model** (`1e04f53`) — performance is now a *fraction* of the lap, not a
  fixed-second shave: a capability/driver edge is the same percentage on a sprint or a long
  climb. Dropped the fixed `+18s` offset, so `base_lap_time` is the honest reference-car geometry
  lap. Climb stays real gravitational seconds (re-split via `GRADIENT_PW_GAIN`). Catalog spans a
  realistic 80–240 km/h.
- **Presentation decoupled from the sim** (`20d93dd`) — tick density follows the *watched*
  wall-clock and the car's own pace, so the per-update pause is constant (no dead air) and a slow
  car honestly takes longer to watch. Sim made truly resolution-invariant (√slice noise scaling).
  Single `PRESENTATION_SPEED_FACTOR` knob; pre-race play/real time estimate shown in the event
  screen and editor previews.

## Realistic lap time & duration races (Phase 4)

- **Geometry-derived `base_lap_time`** (`31b2ba3`) — computed from a track's own segment tag mix
  (`SEGMENT_TAG_SPEED`), never stored; custom/creator tracks get a sane lap for free. No more
  200 km/h keis.
- **Duration races on the lockstep engine** (`777a34e`) — time-capped (Regime A) events finish on
  a clean lap boundary; watch-live and instant-resolve give identical results. `beater_enduro` is
  a real 1200s enduro.
- **Presentation speed / fast-forward** (`6cb6985`) — `N` = next lap, `F` = cycle 1×/2×/4×/8×;
  pure render speed, zero effect on the result.
- **Duration-aware race UI** (`3174569`) — race screen reads elapsed/target time instead of
  "Lap X/Y" for timed events.

## Hillclimb realism

- **Power-to-weight climb model + paved Granite Peak** (`e84fd68`, `921d287`) — on a net climb,
  a per-lap time adjustment monotonic in the car's real hp/kg, anchored to **real paved Pikes
  Peak stock times** (econobox ~14:00, 911 Turbo S ~9:53), never to our catalog. A showroom
  supercar laps the de-branded `granite_peak_hillclimb` in ~9:5x without being tuned to it.

## De-pin from the sample catalog

- **Runtime car class** (`5b23a58`, `6118935`, `084eba0`) — class/PR derived at runtime from a
  fixed drag/slalom/hybrid reference suite (never a stored letter), so a custom car gets a real
  class with nothing to look up. Tier = mean capability; `performance_type` (Power/Handling/…)
  splits same-tier cars. On-track gulf widened so a capability edge actually pulls away. In-game
  "Class Derivation" explainer + live creator preview.
- **Intrinsic orphan-stat anchors** (`e796a2b`) — re-based every secondary-stat reference from
  "the catalog mean" to a principled design midpoint, so "neutral" no longer drifts as the
  catalog grows.

## Track-agnostic foundation

- **Events own race length, physical attrition** (`f4e745e`) — race length lives on the event
  (`laps`/`distance_km`/`duration_s`), not the track; the track defines one lap of geometry.
  Attrition is physical (litres of fuel, distance-based tyre life, time-based heat/fatigue).
  Creator gains an event editor; the career starts from a by-criteria starter car/driver.

## Cleanups

- **Affine fuel economy** (`59766cc`) — compressed the catalog into a realistic 15–65 L/100km
  band so pit strategy matters across the whole field.
- **Collapsed duplicated `fuel_efficiency`** (`1b30ebd`) onto `FuelStats` (balance-neutral).
- **Creator** (`201307c`) shows an overflow count for choice domains.
