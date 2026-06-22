# SheetCircuit Agent Map

Concise code map for future coding agents. The game is Python stdlib-first, with optional `rich` terminal rendering. Core rule: engine code lives in `game/`; UI code lives in `interfaces/`.

Project docs: `CHANGELOG.md` = shipped history (what landed, by commit); `pendingupdates.md` = forward-looking roadmap (next work + deferred backlog). Both are self-contained/portable.

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
  effective_stats.py compute_effective_stats(), derived_rating()/class_rating(),
                     performance_type(). Secondary car/tune/durability stats fold
                     into the 7 effective axes via centered factors (see the
                     "orphan-stat reference points" block in constants).
  opponents.py       Event entry validation and event-pace-aware AI grid generation.
  simulation.py      Lap-time formula and non-interactive full race simulation.
                     Resolution-invariant: noise (driver variance, rival jitter) scales by
                     sqrt(slice) so any tick count yields the same per-lap spread; the live
                     engine matches the one-shot instant sim (the anchor for all balance).
  race_session.py    Interactive RaceSession lifecycle and tick simulation.
                     ticks_per_lap_for(lap_s) sets tick density from *watched* wall-clock
                     (lap_s / PRESENTATION_SPEED_FACTOR * TICK_RATE_HZ), using the player's
                     nominal lap pace -> a slow car genuinely takes longer to watch.
  telemetry.py       Telemetry history, warnings, mistake/failure probabilities.
  sorting.py         SortSpec parsing and per-screen list sorting (class/PR/type-aware).

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
garage_screen(state, sort_spec=None)
drivers_screen(state, sort_spec=None)
events_screen(sort_spec=None)
market_screen(sort_spec=None)
car_detail_screen(state, car_id)
market_car_detail_screen(car_id)
car_extended_screen(state, car_id)         # full spec sheet (garage)
market_car_extended_screen(car_id)         # full spec sheet (market)
driver_detail_screen(driver_id)
event_detail_screen(event_id, state=None)  # adds an "Est. Time" row (play/real) when state given
estimate_race_times(car, driver, event, track, parts=None) -> (canonical_s, play_s)
race_entry_screen(state, step="events")    # guided race picker (events/cars/drivers)
tune_fields_screen(state, car_id)
race_screen(session, tick=None, error="")
race_command_options()

List screens accept an optional SortSpec (see game/sorting.py).

Car list screens show `Class`, `PR`, and `Type`:

```text
Class  broad event eligibility letter; event restrictions can narrow it further
PR     synthetic derived performance rating from effective race stats
Type   short role hint from stat shape/tags: Balanced, Power, Handling, Challenge, etc.
```

buy_car_action(state, car_id)
sell_car_action(state, car_id)
repair_car_action(state, car_id)
hire_driver_action(state, driver_id)
fire_driver_action(state, driver_id)
tune_car_action(state, car_id, field_name, value)
save_game_action(state, path="saves/save1.json")
load_game_action(path="saves/save1.json")
start_race_action(state, event_id, car_id, driver_id, seed=None)
advance_race_action(session, command)
simulate_to_end_action(session, command="normal")   # fast-forward to flag
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

List-screen commands (parsed in `interfaces/cli.run_*` before menu hotkeys):

```text
sort <field> [asc|desc]   re-sort the current list screen (see game/sorting.py)
ext [id|number]           full car spec sheet on garage/market (car_extended_screen)
hire / hire <id|number>   drivers screen: picker or direct hire (hire_driver_action)
fire / fire <id|number>   drivers screen: picker or direct fire (fire_driver_action)
```

Garage/market car sorts include `pr` and `type`; `rating` remains an alias for
`pr` for older commands/tests.

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
roll per tick, a single-lap point-to-point stage (an event with `laps: 1`, start !=
finish) races with the same pseudo-live telemetry and commands as a multi-lap circuit.
Race length lives on the **event** (one of `laps` / `distance_km` / `duration_s`,
resolved by `loader.resolve_race`), not the track; the track defines one lap of
geometry. Attrition is physical: fuel is litres vs the tank, tyres are a distance-based
life, engine heat and driver fatigue accrue over time (see `_apply_lap_wear`).

### Time Scale / Presentation

Three layers are kept strictly independent (see `constants.py` "Presentation / time-scale"):

```text
canonical clock  base_lap_time / per-car lap time -- real in-world seconds (drives physics)
sim resolution   ticks_per_lap -- integration granularity; outcome-invariant (sqrt(slice) noise)
presentation     PRESENTATION_SPEED_FACTOR (watched = canonical / factor; 1.0 == realtime)
```

`ticks_per_lap_for()` ties density to *watched* time, so the per-update pause is a constant
`1/TICK_RATE_HZ` on every track (no dead air) and realtime gets proportionally more ticks. The
sim is honest; only the presentation factor compresses it. There is deliberately **no per-track
target time** -- the same track yields different times per car, so `estimate_race_times` reports
the car-specific figure (and the editor preview shows the fastest->slowest spread).

Non-interactive full race:

```text
simulation.simulate_race(state, event_id, car_id, driver_id, seed)
```

### Race Commands

Race commands are driver/pit-boss *intents* only — engine/ECU maps are a tuning
setting (`tune.engine_map`), never changed mid-race (`compute_effective_stats` takes no
`command`). The closed set is the single source of truth in `race_command_options()`
(CLI/UI resolve labels via `_race_command`):

```text
normal, push, go_all_out, save_tyres, save_fuel, cool_down, pit
```

`COMMAND_MODIFIERS[name]` = (pace, tire_wear, fuel_burn, engine_heat, mistake, stress);
pace > 1 is faster, the other columns are >1 = more of that effect (all six columns are
live — stress uses `COMMAND_STRESS_INDEX`). Cooling is targeted via
`TYRE_COOLING_COMMANDS` / `ENGINE_COOLING_COMMANDS`. `go_all_out` can crash a car out
(`race_session._dnf_chance`, eased by driver consistency/mechanical sympathy — hook for
future driver levels). `pit` is one-shot: `simulate_tick` resets `pace_mode` to `normal`
after the stop and the CLI loop resumes the prior command. AI uses only `push`/`normal`
(`_ai_command`).

## Opponents And Entry Rules

[game/opponents.py](game/opponents.py):

```text
validate_event_entry(car, event, parts)
build_opponent_grid(event, player_car_id, player_driver, cars, parts, track, seed)
  -> (car_roster, driver_roster, entries)
     entries: list of (car_id, driver_id)
```

Opponents respect event restrictions:

```text
car_class_limit  max_power_hp  max_weight_kg
max_overall_condition  allowed_tires  max_class_rating
```

`max_class_rating` uses the synthetic derived rating/PR, not only the hand-authored
letter class.

Field generation is event-set difficulty plus dynamic pace matching (see
`EVENT_PACE_FLOOR_PERCENTILE` and `RIVAL_MATCH_*` constants):

```text
1. eligible = cars that pass car_class_limit + event restrictions
2. compute each eligible car's natural lap on the event track
3. anchor rival selection near the player's natural event pace
   -> higher-class events use an event-floor percentile so a very slow car
      cannot scale the whole field all the way down
   -> thin/edge pools reuse nearby models with unique opponent ids
4. rival_skill = event.rival_skill or CLASS_RIVAL_SKILL[class]
5. each rival is a real copied car + generated Driver; no performance scalar
```

Liveliness comes from two engine-side touches in `simulate_tick`:

```text
rival jitter   (RIVAL_LAP_JITTER_S, sqrt(slice)-scaled)  -> pack shuffles (tick-count invariant)
reactive push  (RIVAL_REACTIVE_GAP_S)                    -> rivals race you back
```

`start_race_action` uses a random seed by default (pass an explicit seed for
deterministic runs / tests). `simulate_race` is the quick, deterministic,
all-normal summary and does NOT apply jitter/reactive push. Both paths seed the
opponent builder with the player's actual garage car, so tune/condition/upgrades
can affect the peer pool.

If balancing feels wrong, inspect (tune constants first):

```text
constants.py  (RIVAL_* block)
game/opponents.py
data/events/*.json   (one file per event; race length lives here)
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

This returns `FieldData` with labels, current value, ranges, and option lists. Do not make players memorize internal values. `tune_fields_for_car()` exposes **every** editable `TuneSetup` field, grouped for display by `_TUNE_FIELD_GROUPS` (Tyres/Drivetrain/Brakes/Suspension/Aero) with one continuous numbering; every knob now influences `compute_effective_stats`.

Choice fields (`value_type="choice"`) carry an `OptionData.description`; the CLI picker renders it as an **Effect** column so the player sees what each option does. `engine_map` uses this — `actions._engine_map_desc` summarises each map's power/fuel/heat trade-off (`ENGINE_MAP_POWER`/`FUEL`/`HEAT`). Reuse this pattern for any new enum field instead of hardcoding prose.

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

`data/tracks/` ships eight tracks. `summit_ridge_gp.json` (circuit) and
`alpine_hillclimb.json` (point-to-point; its event runs `laps: 1`) are reference tracks
exercising all 12 tags and the full surface/condition range; `maple_short.json`,
`northbank_oval.json`, `red_valley_club.json`, `cresta_speed_run.json`,
`glenmoor_esses.json`, and `cinder_pass.json` round out the calendar.

Adding data should usually mean adding JSON files under `data/`, not editing registries.

## Common Change Targets

- New car/driver/event/part/track: add JSON under `data/`, update tests if needed.
- New tune field: update `TuneSetup`, seed JSON, `TUNE_FIELD_RANGES`, `_TUNE_FIELD_GROUPS`/`_TUNE_FIELD_LABELS` in actions.py, and fold it into `compute_effective_stats` (centered factor, ideal in constants), tests.
- New race command: update `COMMAND_MODIFIERS` (6-column tuple), `race_command_options()`, cooling sets if it cools, tests. Engine maps are NOT commands — they live in `tune.engine_map`.
- New sortable field/screen: update the per-screen options in `game/sorting.py`, tests.
- Balance lap times: update constants first, then formulas in `effective_stats.py` or `simulation.py`.
  Pace is **proportional**: `lap = base_lap_time × _pace_multiplier(composite, pace_factor, driver_pace)`
  where the multiplier is `1 − PERF_FRACTION·(composite·pace_factor − REFERENCE_COMPOSITE) − DRIVER_PACE_FRACTION·driver_pace`.
  A design-midpoint car laps at exactly `base_lap_time` (which is now the honest reference-car
  geometry lap — no additive offset); a capability/driver edge is a consistent *percentage* on any
  track length. `_climb_adjustment` stays **absolute** real seconds (gravity), re-split from pace via
  `GRADIENT_PW_GAIN` when pace went proportional. Fix unrealistic outliers by tuning that track's
  `SEGMENT_TAG_SPEED` or a car's stats — never by bending `PERF_FRACTION` away from honest.
- Balance opponents: tune `RIVAL_MATCH_*`, `EVENT_PACE_FLOOR_PERCENTILE`, and other `RIVAL_*` constants first, then event restrictions/data or `opponents.py`.
- Add web UI: create new interface/API layer that calls `game.actions`; avoid importing `interfaces.cli`.
- Add save fields: update dataclasses, loader/save roundtrip tests, schema if breaking.

## Test Map

```text
test_models.py             Loaders/dataclasses/track validation.
test_save_load.py          Save schema and roundtrip.
test_effective_stats.py    Stats, derived PR/class rating, tune effects.
test_lap_time.py           Lap formula and full-race basics.
test_segment_resolution.py Segment profiles and per-interval lap pace.
test_orphan_stats.py       Secondary car/tune/durability stat folds (direction tests).
test_balance_baseline.py   Reference lap + race-outcome balance guard (catches drift).
test_race_tick.py          Interactive race commands.
test_commands.py           Command set: live stress column, one-shot pit, engine-map decoupling.
test_telemetry.py          Telemetry history and warnings.
test_economy.py            Buy/sell/repair/prizes.
test_opponents.py          Event restrictions, pace floors, and opponent generation.
test_car_catalog.py        Catalog class distribution and S-class competitiveness.
test_actions.py            UI-neutral action/screen layer.
test_cli.py                Terminal menu/screen behavior.
test_presentation_timing.py Resolution-invariance of lap noise, watched-time tick density,
                            and the pre-race play/real estimate.
```
