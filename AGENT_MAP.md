# SheetCircuit Agent Map

Concise code map for future coding agents. The game is Python stdlib-first, with optional `rich` terminal rendering. Core rule: engine code lives in `game/`; UI code lives in `interfaces/`.

## Run And Test

- Start game: `python3 main.py`
- Full tests: `python3 -m unittest discover -s tests`
- Compile check: `python3 -m compileall .`
- Optional terminal polish: `python3 -m pip install -r requirements.txt`

## Top-Level Flow

```text
main.py
  -> interfaces.cli.main()
    -> new_career()
    -> command_loop()
      -> render current screen
      -> run_menu_choice() or run_command()
      -> game.actions / game.* engine functions
```

For future web UI, prefer calling `game.actions` instead of `interfaces.cli`.

## Architecture Tree

```text
constants.py
  All tuning constants, command modifiers, validation ranges.

data/
  JSON seed data: cars, drivers, tracks, events, parts.

game/
  models.py          Dataclasses for cars, tracks, events, race state, telemetry.
  loader.py          JSON loading, validation, track weight derivation.
  game_state.py      GameState, new_game(), new_career().
  save_load.py       Versioned JSON save/load.
  actions.py         UI-neutral service layer for CLI and future web UI.
  economy.py         buy_car(), sell_car(), repair_car().
  market.py          list_market_cars().
  tuning.py          set_tune(), update_tune_fields(), tune validation.
  effective_stats.py compute_effective_stats(), class_rating().
  opponents.py       Event entry validation and event-aware AI grid generation.
  simulation.py      Lap-time formula and non-interactive full race simulation.
  race_session.py    Interactive RaceSession lifecycle and tick simulation.
  telemetry.py       Telemetry history, warnings, mistake/failure probabilities.

interfaces/
  cli.py             Terminal state machine, menu flow, guided pickers.
  terminal.py        Rich/stdlib terminal adapter.
  menu.py            Main menu hotkeys and status bar.
  render_text.py     Legacy/simple row render helpers.
```

## UI-Neutral Service Layer

Use [game/actions.py](game/actions.py) for new UI work.

Core screen/result dataclasses:

```text
TableData(title, headers, rows)
OptionData(value, label, key="", description="")
FieldData(name, label, current, value_type, min/max, options)
ScreenData(name, title, subtitle, tables, messages, actions, fields)
ActionResult(state, message, screen)
RaceActionResult(session, tick, screen, error, prize_money)
```

Important functions:

```text
garage_screen(state)
drivers_screen()
events_screen()
market_screen()
car_detail_screen(state, car_id)
market_car_detail_screen(car_id)
driver_detail_screen(driver_id)
event_detail_screen(event_id)
tune_fields_screen(state, car_id)
race_screen(session, tick=None, error="")
race_command_options()

buy_car_action(state, car_id)
sell_car_action(state, car_id)
repair_car_action(state, car_id)
tune_car_action(state, car_id, field_name, value)
save_game_action(state, path="saves/save1.json")
load_game_action(path="saves/save1.json")
start_race_action(state, event_id, car_id, driver_id, seed=1)
advance_race_action(session, command)
finish_race_action(state, session)
```

## Main Game Loop

`interfaces.cli.command_loop()` is currently the text UI loop.

```text
command_loop(state)
  screen = "garage"
  clear + render current screen
  prompt Choice:
  run_menu_choice(state, raw, screen)
```

Menu hotkeys live in [interfaces/menu.py](interfaces/menu.py):

```text
G Garage, E Events, D Drivers, M Market, R Race,
X Sell, T Tune, P Repair, S Save, L Load, H Help, Q Quit
```

On passive list screens, entering a row number or ID opens detail:

```text
garage -> car_detail_screen()
drivers -> driver_detail_screen()
events -> event_detail_screen()
market -> market_car_detail_screen()
```

The market screen is the single place to browse and buy cars. From the market screen:
- enter a number or ID → `market_car_detail_screen()` (read-only detail)
- type `buy` → inline picker prompts for car number/ID
- type `buy <id>` or `buy <number>` → direct purchase

## Race Flow

Interactive:

```text
start_race_action()
  -> race_session.enter_event()
    -> validate_event_entry()
    -> build_opponent_grid()
    -> RaceSession

advance_race_action()
  -> race_session.apply_player_command()
    -> race_session.simulate_tick()
      -> compute_effective_stats()
      -> lap_time_over_interval()   # segment-resolved slice of the lap
      -> _apply_lap_wear(profile=)  # per-segment local rates
      -> mistake_chance()/failure_chance()  # rolled PER TICK (scaled by slice)
      -> record_telemetry()         # at lap end (one sample per lap)

finish_race_action()
  -> finish_event()
    -> prize money, mileage, wear
```

Segment-resolved simulation: the whole field shares one track position each tick
(`current_sub_tick / ticks_per_lap`). `lap_time_over_interval()` sums the
`Track.segment_profiles` overlapped by that position interval, so a track's tag mix
and per-segment surface/condition shape pace *within* the lap. Profiles are
*intensive* (length-weighted sum reproduces the aggregate weights/rates), so dry
tarmac integrates to the legacy `calculate_lap_time` exactly and balance is preserved;
`calculate_lap_time(... )` is just the whole-lap (`start=0,length=1`) case and stays
the reference used by opponents and `simulate_race`. Surface/condition come from
`SURFACE_MODIFIERS`/`CONDITION_MODIFIERS` (grip + tyre-wear mult, plus a `wet_weight`
that blends car grip->wet_grip and driver pace->wet_skill). Because mistakes/failures
roll per tick, a single-lap point-to-point stage (`laps: 1`, start != finish) races
with the same pseudo-live telemetry and commands as a multi-lap circuit.

Non-interactive full race:

```text
simulation.simulate_race(state, event_id, car_id, driver_id, seed)
```

Race command closed set comes from `race_command_options()` and is consumed by CLI and future UI.

## Opponents And Entry Rules

[game/opponents.py](game/opponents.py):

```text
validate_event_entry(car, event, parts)
build_opponent_grid(event, player_car_id, player_driver, cars, parts, track, seed)
  -> (car_roster, driver_roster, entries)
     entries: list of (car_id, driver_id, performance_scalar)
```

Opponents respect event restrictions:

```text
car_class_limit  max_power_hp  max_weight_kg
max_overall_condition  allowed_tires  max_class_rating
```

Field generation is hybrid-difficulty (see `RIVAL_*` constants):

```text
1. player_ref = player's honest normal-pace lap on this track
2. center = clamp(player_ref, event class band) + RIVAL_PLAYER_EDGE_S
     -> rivals track the player but you can outgrow easy events
3. rivals spread into a small deterministic tier ladder around center
4. each target lap realised via closest eligible base car + solved
   driver pace, with RaceCarState.performance_scalar covering the
   residual (scales car_performance_bonus in calculate_lap_time)
```

Liveliness comes from two engine-side touches in `simulate_tick`:

```text
per-tick rival jitter   (RIVAL_TICK_VARIANCE_S)  -> pack shuffles
reactive push           (RIVAL_REACTIVE_GAP_S)   -> rivals race you back
```

`start_race_action` uses a random seed by default (pass an explicit
seed for deterministic runs / tests). `simulate_race` is the quick,
deterministic, all-normal summary and does NOT apply jitter/reactive push.

If balancing feels wrong, inspect (tune constants first):

```text
constants.py  (RIVAL_* block)
game/opponents.py
data/events/seed_events.json
game/effective_stats.py
```

## Tuning And User Input Validation

Tune validation is centralized in [game/tuning.py](game/tuning.py).

```text
update_tune_fields(state, car_id, **fields)
  validates all fields first
  then mutates atomically
```

Ranges live in `constants.TUNE_FIELD_RANGES`. Engine map choices are from `constants.ENGINE_MAP_POWER`.

The UI should use:

```text
tune_fields_screen(state, car_id)
```

This returns `FieldData` with labels, current value, ranges, and option lists. Do not make players memorize internal values.

## Data Loading

[game/loader.py](game/loader.py):

```text
load_cars()
load_drivers()
load_tracks()
load_events()
load_parts()
load_all_data()
```

Tracks derive aggregate weights/rates AND per-segment profiles from segment tags
(plus surface/condition) during load:

```text
derive_weights(segments)        # normalized aggregate stat weights (sum to 1)
derive_rates(segments)          # aggregate wear/fuel/heat (surface/condition baked into tyre wear)
build_segment_profiles(segments) -> Track.segment_profiles  # intensive, position-resolved
```

`data/tracks/summit_ridge_gp.json` (circuit) and `data/tracks/alpine_hillclimb.json`
(`laps: 1` point-to-point) are reference tracks exercising all 12 tags and the full
surface/condition range.

Adding data should usually mean adding JSON files under `data/`, not editing registries.

## Common Change Targets

- New car/driver/event/part/track: add JSON under `data/`, update tests if needed.
- New tune field: update `TuneSetup`, seed JSON, `TUNE_FIELD_RANGES`, `tune_fields_for_car()`, tests.
- New race command: update `COMMAND_MODIFIERS`, `race_command_options()`, `_race_command()` behavior if needed, tests.
- Balance lap times: update constants first, then formulas in `effective_stats.py` or `simulation.py`.
- Balance opponents: tune the `RIVAL_*` constants first, then event restrictions/data or `opponents.py`.
- Add web UI: create new interface/API layer that calls `game.actions`; avoid importing `interfaces.cli`.
- Add save fields: update dataclasses, loader/save roundtrip tests, schema if breaking.

## Test Map

```text
test_models.py           Loaders/dataclasses/track validation.
test_save_load.py        Save schema and roundtrip.
test_effective_stats.py  Stats, class rating, tune effects.
test_lap_time.py         Lap formula and full-race basics.
test_race_tick.py        Interactive race commands.
test_telemetry.py        Telemetry history and warnings.
test_economy.py          Buy/sell/repair/prizes.
test_opponents.py        Event restrictions and opponent generation.
test_actions.py          UI-neutral action/screen layer.
test_cli.py              Terminal menu/screen behavior.
```

