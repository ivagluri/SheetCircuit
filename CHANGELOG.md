# SheetCircuit — Changelog

Work on the `refactor/track-agnostic-sim` branch: making the simulation track-agnostic,
de-pinned from the sample catalog, and honest about time. Newest first.

## Simulation audit (SIM_AUDIT.md)

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
