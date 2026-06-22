# SheetCircuit — Pending Updates

Forward-looking roadmap. Completed work has moved to `CHANGELOG.md`. This document is
self-contained so it can be ported to an issue tracker or another repo.

Conventions:
- References are by **symbol/function name**, not line number, so they survive edits.
- Each item is its own commit and must leave `python3 -m unittest discover -s tests` green,
  re-pinning `tests/test_balance_baseline.py` in the same commit if the change legitimately
  shifts the reference race.
- **Don't pin to the sample catalog**: references should be intrinsic design choices or
  real-world magnitudes, never `min/max/mean` of whatever cars happen to be loaded.

---

## Next up — Settings menu (time control + sim knobs)

### Context
The race clock is now honest (canonical seconds) and only presentation compresses it, but the
player can't see or change that compression. "1×" actually means **13.3× faster than realtime**
(`PRESENTATION_SPEED_FACTOR = 13.3`), which is confusing, and there's no UI to adjust it. Add a
Settings menu exposing the presentation-speed "time slider" plus a couple of live knobs, built so
future settings drop in cleanly. Settings persist **inside each save** (GameState).

### Scope (v1)
1. **Presentation speed** — the time slider. Named presets *and* a custom factor:
   `Realtime (1×)`, `Fast (13×, default)`, `Faster (30×)`, plus free numeric entry (floor 1.0).
   Directly de-confuses "1×" by offering a true realtime option.
2. **Tick cadence** — `TICK_RATE_HZ` (updates/sec of watched time; the smoothness knob), numeric.
3. **Deterministic seed** — fixed race seed for reproducible races, or random (default).

### Design
- **Model + persistence (in-save).** New `game/settings.py`: `@dataclass Settings` with
  `presentation_speed_factor`, `tick_rate_hz`, `race_seed: int | None`, defaulting from the
  constants. Add `settings: Settings = field(default_factory=Settings)` to `GameState`
  (`game/game_state.py`); `new_game`/`new_career` get defaults for free. In `game/save_load.py`,
  add `settings` to `game_state_to_dict`/`_from_dict` using `data.get("settings")` with a default
  when absent so **old saves still load** (no forced `SCHEMA_VERSION` bump).
- **Engine reads settings (the call sites already hold `state`).**
  - `race_session.ticks_per_lap_for(lap_s, factor=…, rate=…)` — add params, keep constant
    defaults (engine stays pure). `enter_event(game_state, …)` passes `game_state.settings` and
    stores `presentation_factor` + `tick_rate_hz` on the `RaceSession` (new `game/models.py`
    fields).
  - `interfaces/cli.py` `_run_race`: `base_tick_sleep = 1.0 / session.tick_rate_hz`.
  - `actions.estimate_race_times(…, factor=…)`; `event_detail_screen(event_id, state)` passes
    `state.settings.presentation_speed_factor`.
  - `start_race_action(state, …, seed=None)`: default `seed` to `state.settings.race_seed`.
- **UI (reuse the tune pattern).** `interfaces/menu.py` add `MenuAction("O", "Options",
  "options")`. `actions.settings_screen(state)` built from `FieldData` (as `tune_fields_screen`
  does) — `OptionData` presets for speed, numeric ranges for cadence/seed; `update_setting_action`
  mirrors `tune_car_action`/`update_tune_fields`. `interfaces/cli.py` routes `options` to a
  `_settings_picker(state)` modeled on `_tune_picker`.

### Files
New: `game/settings.py`, `tests/test_settings.py`. Edit: `game/game_state.py`,
`game/save_load.py`, `game/models.py`, `game/race_session.py`, `game/actions.py`,
`interfaces/cli.py`, `interfaces/menu.py`, `AGENT_MAP.md`.

### Verification
- `tests/test_settings.py`: defaults equal the constants; save→load round-trips `settings`; an
  **old save without `settings` still loads** with defaults; `update_setting_action` validates
  bounds; `ticks_per_lap_for` honors a passed factor/rate; `estimate_race_times` scales with
  `factor` (Realtime 1.0 → play == canonical).
- Manual: `python3 main.py` → `O` → set Realtime, run a race, confirm the clock advances at ~real
  time; set a fixed seed and confirm two runs match; save, reload, confirm settings persist.

---

## Quick fixes — time-display legibility

Small render-only fixes surfaced while validating the time work:
1. **Duration clock overshoot.** A duration race finishes on the lap boundary *after* the cap, so
   the clock legitimately exceeds the target (e.g. `20:58/20:00`), but the UI shows it as
   `elapsed / target` with no hint the target is a floor. Reframe in `interfaces/cli.py`
   (`_print_lap_bar`) and `game/actions.py` (`race_screen`) to read e.g. `20:58 / 20:00 min` or
   `+0:58 over cap`.
2. **Estimate is a floor, not a prediction.** `estimate_race_times` is a clean nominal (no wear,
   mistakes, or variance), so real interactive races run longer. Label the `event_detail_screen`
   row accordingly (e.g. "clean est." / "≈ floor").

---

## Deferred — async / ragged enduro
Each car holds its own track position ⇒ true lapped cars, "+N laps", lap-aware `gap_to_leader`,
ragged per-car telemetry. A separate phase on top of the lockstep duration engine, once the time
model is stable. The current lockstep duration already gives long races, real strategy, and
realistic time.

## Deferred — gravel-era twin + real surface effect
Surface/condition currently only trims a segment's *composite*, which barely moves lap time on a
long track (~4 s over 20 km gravel/wet) — so a wet race isn't meaningfully slower, which is itself
wrong. Make surface/condition a **lap-time multiplier** (wet ≈ ×1.25, damp ≈ ×1.12, gravel ≈
×1.15); then a gravel-era `granite_peak_classic` twin reproduces the pre-2011 Pikes times (BMW 325
~14:00, Beetle/Metro ~18:00) on the same power-to-weight model. Re-pins `cinder_pass` (gravel) and
the wet/damp tracks.

## Deferred — built-in reference manual
A browsable in-game **reference manual**, separate from the contextual Help screen: tabular pages
explaining what each mechanic does (engine maps, race commands, tune fields, car-class derivation,
segment tags). **Data-driven**: generate the tables *from* the sim's own constants/data
(`ENGINE_MAP_POWER`/`FUEL`/`HEAT`, `COMMAND_MODIFIERS`, `TUNE_FIELD_RANGES`, the reference suite,
`SEGMENT_TAG_SPEED`) so the manual can never drift from behaviour — the same principle as the
engine-map option "Effect" column (which reads `actions._engine_map_desc`). Each page is just a
`ScreenData` of `TableData`; no new dependency — the existing `interfaces/terminal.py` rich adapter
already does tabular (and live) rendering. New menu entry + a `manual_screen(page)` in
`game/actions.py`.
