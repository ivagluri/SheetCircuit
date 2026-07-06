# SheetCircuit Agent Map

Concise code map for future coding agents. The game is Python stdlib-first, with optional `rich` terminal rendering. Core rule: engine code lives in `game/`; UI code lives in `interfaces/`.

Project docs: `CHANGELOG.md` = shipped history (what landed, by commit), self-contained/portable. (The old `SIM_AUDIT.md` audit record and `pendingupdates.md` roadmap were retired 2026-07-04; their content lives in git history.)

## Run And Test

- Start game: `python3 main.py`
- Start creator: `python3 creator.py`
- Full tests: `python3 -m unittest discover -s tests`
- Compile check: `python3 -m compileall .`
- Progression probe: `python3 tools/probe_progression.py`
- Pace/thermal probe: `python3 tools/pace_probe.py` (per-lap temps/wear/incident table)
- Optional terminal polish: `python3 -m pip install -r requirements.txt`

## Top-Level Flow

```text
main.py
  -> interfaces.cli.main()
    -> new_career()
    -> command_loop()                # starts on the Home screen
      -> render current screen (chrome: status bar + breadcrumb + footer)
      -> run_menu_choice() or run_command()
      -> game.actions / game.* engine functions
      (GoHome from any nested picker/editor unwinds back to Home)
```

For future web UI, prefer calling `game.actions` instead of `interfaces.cli`.

## Architecture Tree

```text
constants.py
  All tuning constants, progression XP thresholds, command modifiers, validation ranges.

data/
  JSON seed data: cars, drivers, tracks, events, parts. Event JSON carries
  explicit progression metadata (`min_team_level`, `event_kind`).

game/
  models.py          Dataclasses for cars, tracks, events (including progression
                     metadata), race state, telemetry.
  loader.py          JSON loading, validation, track weight derivation. Event loading
                     defaults `min_team_level` from class and validates `event_kind`.
  game_state.py      GameState, new_game(), new_career(). Stores money/week,
                     team_xp, garage, hired_drivers, event_progress.
  save_load.py       Versioned JSON save/load (schema v2 includes team progression).
  actions.py         UI-neutral service layer for CLI and future web UI.
  economy.py         buy_car(), sell_car(), repair_car(), buy_part(), install_part(),
                     uninstall_part() (unequip = back to stock, no refund).
  parts.py           GT-style upgrade parts: SLOT_RULES (one part per slot),
                     part_map()/canonical_part_id(), installed_part_for_slot(),
                     installed_unlocks() — parts can gate tune fields (e.g. a
                     sports ECU unlocks engine maps; lock_reason_for_tune_field()).
  part_effects.py    Readable part-effect display layer: stat-path metadata,
                     simulation-aware polarity, catalog-relative intensity,
                     compact summaries, and selected-part detail rows.
  market.py          list_market_cars(), list_free_agents() — a persisted rotating
                     free-agent driver market (GameState.free_agents, churned every
                     N weeks, seeded per career).
  driver_gen.py      Procedural drivers: generate_driver()/archetypes/market pools,
                     name pools, potential + salary formulas. Rivals get real
                     generated drivers (no "Rival N"). Driver.potential caps XP growth.
  progression.py     Pure team career progression helpers: Team XP -> Team Level,
                     event-progress normalization/update, and Team XP award math
                     (finish quality, event kind, repeat wins, first-win bonus).
  tuning.py          set_tune(), update_tune_fields(), tune validation. Covers setup
                     knobs (TuneSetup) and garage-tweakable hard-mod car stats
                     (constants.CAR_MOD_FIELD_SECTIONS); tune_target() maps a field
                     name to the object that owns it.
  effective_stats.py compute_effective_stats(), derived_rating()/class_rating(),
                     performance_type(). Secondary car/tune/durability stats fold
                     into the 7 effective axes via centered factors (see the
                     "orphan-stat reference points" block in constants).
  event_display.py   Shared event UI text for progression requirement/status and
                     best-progress summaries.
  opponents.py       Event entry validation and event-pace-aware AI grid generation.
  simulation.py      Lap-time formula and non-interactive full race simulation.
                     Resolution-invariant: noise (driver variance, rival jitter) scales by
                     sqrt(slice) so any tick count yields the same per-lap spread; the live
                     engine matches the one-shot instant sim (the anchor for all balance).
  race_session.py    Interactive RaceSession lifecycle and tick simulation.
                     ticks_per_lap_for(lap_s) sets tick density from *watched* wall-clock
                     (lap_s / PRESENTATION_SPEED_FACTOR * TICK_RATE_HZ), using the player's
                     nominal lap pace -> a slow car genuinely takes longer to watch.
                     `finish_event()` commits money/week, Team XP, event progress,
                     driver XP, and car wear, returning `FinishEventResult`; sessions
                     snapshot the player's pre-race car condition for post-race deltas.
  telemetry.py       Telemetry history, warnings, mistake/failure probabilities.
  sorting.py         SortSpec parsing and per-screen list sorting (class/PR/type-aware).

interfaces/
  shell.py           THE universal screen contract (see ## UI Shell Contract):
                     pure dispatch(), Screen/LocalKey, nav stack + breadcrumb,
                     auto-generated footer, slash palette, confirm helpers, GoHome.
  cli.py             Terminal state machine on top of the shell: Home + browse
                     screens (run_menu_choice), guided pickers (_picker/_choose),
                     upgrades/tune editors, the live race loop.
  terminal.py        Rich/stdlib terminal adapter. Chrome (footers/breadcrumbs)
                     must go through print_plain() — rich's markup parser eats
                     bracketed text like "[q Quit]" otherwise.
  menu.py            MENU_ACTIONS (Home tab list + hotkeys) and global status bar,
                     including Team Level/XP display via `team_xp_status()`.
  render_text.py     Legacy/simple row render helpers.
  web.py             Browser (Pyodide) adapter; reuses cli render helpers.

editor/
  app.py             CreatorApp (creator.py entry): interactive car/track/event
                     editor. Same universal contract via the pure shell pieces
                     (dispatch/footer_line) read through its scriptable ask() seam,
                     with a local crumb() breadcrumb trail.
  fields.py          Car/track/event field schemas + templates (harvested by the
                     compendium; the tune menu mirrors the car schema).

compendium/
  model.py           Entry/Section/Chapter dataclasses (the doc data model).
  content_*.py       Per-domain content: cars/tracks/events harvest ranges &
                     choices from editor.fields + constants (only prose is
                     hand-written); drivers hand-built from the Driver dataclass;
                     content_intro is the index framing. See ## Compendium.
  registry.py        Assembles CHAPTERS / ENTRIES_BY_ID / TUNE_LOOKUP; imports no
                     game-UI code so game.actions can import it without a cycle.
  render_html.py     Pure-stdlib static-page renderer (used by tools/build_web).

tools/
  probe_progression.py  Dependency-free Team XP payout and pacing probe.
  pace_probe.py         Pace/thermal tuning harness: deterministic per-lap table of
                        temps, tyre/fuel %, lap time, incident probabilities for any
                        car at a fixed command (the tactical-pace rework's instrument).
  build_web.py          Bundles the game/creator (embedded Python + Pyodide) and
                        renders the static compendium page. SOURCE_GLOBS must
                        embed everything the bundle imports (incl. compendium/*.py
                        and editor/fields.py) — guarded by an isolation-import test.
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
race_entry_screen(state, step="events", sort_spec=None)  # guided race picker
                                           # (events/cars/drivers); sort_spec applies
                                           # to the step's own list
tune_editor_screen(state, car_id, draft=None)   # tune editor top level: sections + delta readout
tune_section_screen(state, car_id, section, draft=None)  # one section's knobs (Current/Staged/Allowed)
stage_tune_value(state, car_id, field, value)   # validate one draft value (raises TuningError)
apply_tune_draft(state, car_id, draft)          # atomic validated apply of the whole draft
tune_fields_screen(state, car_id)               # legacy flat list (kept for API/tests)
# The tune menu covers the full TuneSetup PLUS the garage-tweakable hard-mod stats
# (constants.CAR_MOD_FIELD_SECTIONS): the creator's car knobs minus intrinsic
# properties (identity/value, engine hp/torque/aspiration/character, weight_kg,
# durability build quality, fuel hardware, condition). Hard mods write straight
# into the car's stat sections and persist through save/load.
race_screen(session, tick=None, error="",  # pinned constant-size panels incl. "Track" strip
            log_event_chars=None)          # (vertical dot mini-map; magnified gaps, no two rows
                                           # share unless times tie). log_event_chars = Event
                                           # column width budget from the UI's terminal size.
race_command_options()

List screens accept an optional SortSpec (see game/sorting.py).

Car list screens show `Class`, `PR`, and `Type`:

```text
Class  broad event eligibility letter; event restrictions can narrow it further
PR     synthetic derived performance rating from effective race stats
Type   short role hint from stat shape/tags: Balanced, Power, Handling, Challenge, etc.
```

upgrades_slot_screen(state, car_id)        # part slots + what's installed
upgrades_part_screen(state, car_id, slot)  # one slot's parts (owned/installed/price)
buy_part_action(state, car_id, part_id, install=False)
install_part_action(state, car_id, part_id)      # installing an owned part is free
uninstall_part_action(state, car_id, slot_or_part_id)  # back to stock, no refund

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

## Team Progression

Team career progression is pure and derived. Store `GameState.team_xp`, derive Team
Level through `game.progression.team_level_for_xp()` and `TEAM_LEVEL_THRESHOLDS`;
do not store a separate level. Per-event progress lives in
`GameState.event_progress[event_id]` as expandable dicts normalized on load by
`normalize_event_progress()`:

```text
starts, best_position, wins, podiums, best_time_s
```

Team XP awards come from `team_xp_award(class, event_kind, position, is_dnf,
event_progress_before)`: base XP by event class, finish multiplier, event-kind
multiplier, repeat-win smoothing, plus a one-time first-win bonus. Keep this module
UI-free and simulation-free so pacing can be tested without running races.

Each `Event` has `min_team_level` and `event_kind`. The loader infers missing
`min_team_level` from `TEAM_LEVEL_BY_CLASS` and defaults missing `event_kind` to
`ladder`, but seed data is explicitly annotated. Valid event kinds are defined by
`constants.EVENT_KINDS`; `beater_enduro` is the level-1 `open_invitational`.
The global CLI/web status bar includes compact Team Level/XP text from
`interfaces.menu.team_xp_status()` so progression is visible on every screen.

## UI Shell Contract

`interfaces/shell.py` is the one input contract every screen obeys — never
hand-roll a `while True: input()` loop for a new screen.

Universal keys (un-shadowable, on every screen, always in the footer):

```text
b / back        pop one level (cancel picker, leave detail, step up an editor;
                root tab -> Home; Home -> quit-confirm)
q / quit        quit with a confirm prompt, from anywhere
? / h / help    unified context-aware help (universal tables + the active
                screen's key table + screen-specific notes)
```

Slash palette (works at any prompt): `/save` (instant save), `/home`/`/menu`
(jump to Home, confirming if edits are staged), `/ref` (compendium overlay,
returns in place), `/quit` `/help` aliases; `/load` is Home-only.

Building blocks:

```text
dispatch(raw, keys)        pure dispatcher -> Action(kind, value); order is
                           palette/universal -> local keys -> free text
Screen(name, keys, render, dirty, help)   pushed via shell.screen() (a context
                           manager) -> nav stack drives the breadcrumb
LocalKey(key, label, words, description)  one entry of a screen's key table;
                           the footer and help are GENERATED from it, so an
                           advertised key can never be dead
shell.prompt(label)        footer + read + intercept universal/palette; returns
                           only back/local/text to the calling loop
GoHome                     exception; /home raises it, command_loop catches it
confirm(prompt)            y/N helper
```

Gotchas: chrome must print via `terminal.print_plain()` (rich markup eats
`[q Quit]`); the creator uses the pure pieces (`dispatch`/`footer_line`)
through `CreatorApp.prompt_action()`/`ask()` so tests can script it; the race
loop reads stdin via select but builds its footer/help from
`cli._race_local_keys()` — keep that table collision-free (pace n/f vs
presentation l/> was a real shadowing bug). Local keys must avoid b/q/h.
Upgrades action prompt is y=buy, i=install/buy&install, u=unequip.

`tests/test_shell.py` pins the contract at the framework level.

## Main Game Loop

`interfaces.cli.command_loop()` is currently the text UI loop.

```text
command_loop(state)
  screen = "home"                    # Home is the root; tabs are its children
  clear + render screen (header, status bar, breadcrumb, tab bar*, body, footer)
  prompt Choice:
  run_menu_choice(state, raw, screen)   # pure seam: returns (state, screen)
```

\*The tab bar (`menu_bar()`) renders only where its hotkeys are live: Home and
the four root browse tabs. Modal sub-screens (pickers/editors/details/race)
show breadcrumb + auto-footer instead.

Menu hotkeys live in [interfaces/menu.py](interfaces/menu.py) (`MENU_ACTIONS`
is the Home tab list's source of truth):

```text
G Garage, E Events, D Drivers, M Market, R Race, X Sell, U Upgrades,
T Tune, P Repair, S Save, L Load, C Compendium, H Help, Q Quit (confirms)
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
sort <field> [asc|desc]   re-sort the current list screen (see game/sorting.py); the same
                          grammar works at every picker prompt (buy/sell/repair/hire/fire/
                          ext and all three race-entry steps) against the picker's backing
                          screen, sharing the same sort state (cli._choose(sort_screen=,
                          refresh=); web._picker_sort). The tune flow is deliberately
                          exempt (its car step is a plain picker; the tune fields list
                          keeps its authored subsystem grouping)
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
    -> team-level gate (`event.min_team_level` vs derived level from `state.team_xp`)
    -> validate_event_entry()
    -> build_opponent_grid()
    -> RaceSession

advance_race_action()
  -> race_session.apply_player_command()
    -> race_session.simulate_tick()
      -> session.effective_stats[car_id]  # cached once per entry in enter_event
      -> lap_time_over_interval()   # segment-resolved slice of the lap
      -> _apply_lap_wear(profile=)  # per-segment local rates
      -> mistake_chance()/failure_chance()  # rolled PER TICK (scaled by slice)
      -> record_telemetry()         # at lap end (one sample per lap)

finish_race_action()
  -> finish_event()
    -> prize money, Team XP, event progress, driver XP, mileage, wear
  -> ScreenData(name="post_race") with Final Standings, Rewards, Team Progress,
     Event Progress, Driver Progress, and Car Condition tables
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
life, engine heat and driver fatigue accrue over time (see `_apply_lap_wear`). An empty
tank is a real failure state: the car limps at +`FUEL_EMPTY_PACE_FRACTION` of the base
lap per lap until it pits. Temperatures are a heat *balance*: gain fights an always-on
passive cooling (linear in seconds, so the segment<->aggregate integration invariant
stays exact). Normal running holds a mid car near its operating floor (`TIRE_OPTIMAL_C`
/ `INITIAL_ENGINE_TEMP_C`); thermally demanding cars creep up and must lift; the cooling
commands multiply the passive rate (`TIRE_COOLING_BOOST`/`ENGINE_COOLING_BOOST`). A
mechanical failure can be terminal (`telemetry.failure_dnf_chance`, steeper past engine
overheat), for player and rivals alike.

Incidents damage the car mid-race (`RaceCarState.condition_pct`, feeding failure risk and
post-race wear), and driver energy is live (fatigue mistake risk + a pace leak when
exhausted). Post-race wear scales with real race distance and hits sub-systems
(`simulation.apply_post_race_wear`); resale depreciates with condition/mileage
(`economy._resale_factor`); each race consumes a week. Race-day **weather** is one
forecast roll per race (`loader.roll_race_condition`, seeded off the race seed on an
isolated stream; `track.weather_variability` is the chance of change) applied by
escalating the session track's segment profiles (`loader.apply_race_condition` -- never
dries an authored-wet segment). **Overtaking** is live-only (like jitter): the car
behind must make a pass stick (`race_session._contest_overtakes` walks the road ahead
nearest-first; `_pass_chance` = per-lap base x (1 - track.overtake_difficulty) x
racecraft edge). A won contest *completes* the pass -- a follower still nominally
behind exchanges race clocks with the defender (time-conserving), so the move always
reorders the road; a failed one holds the car in dirty air in a breathing band
`[OVERTAKE_FOLLOW_GAP_S, +OVERTAKE_GAP_JITTER_S]` (re-drawn per tick, so trains
flutter instead of freezing). Only a car strictly ahead at tick start defends (a
standing start / dead heat spreads on pace alone); sweeping past a crippled car
(pitted/crawling) is free.

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

`COMMAND_MODIFIERS[name]` = (pace, tire_wear, fuel_burn, engine_heat, mistake, stress,
overtake); pace > 1 is faster, the other columns are >1 = more of that effect (all seven
columns are live — see the `COMMAND_*_INDEX` constants). Every command gets the passive
cooling baseline; `TYRE_COOLING_COMMANDS` / `ENGINE_COOLING_COMMANDS` multiply it by the
matching `*_COOLING_BOOST`. `go_all_out` can crash a car out
(`race_session._dnf_chance`, eased by driver consistency/mechanical sympathy — hook for
future driver levels). `pit` is one-shot: `simulate_tick` resets `pace_mode` to `normal`
after the stop and the CLI loop resumes the prior command.

**Tactical pace model** (tuned via `tools/pace_probe.py`): push/all-out are
*heat-limited bursts*, not free pace. The thermal brake makes engine heat climb hard at
all-out (a mid car redlines in ~2 laps; even the coolest engine within ~3 —
`ENGINE_HEAT_FACTOR_MIN`) and recover in ~1 cool-down lap; heat rates are normalised +
compressed (`ENGINE_HEAT_REF`/`EXPONENT`) so cooling/engine-map stay real build levers.
Overheat has two teeth: a warning band that clearly bleeds lap time, then a danger band
where a mechanical issue is roughly a coin flip to end the race. The overtake column
(graded N<P<O) multiplies an attacker's pass chance and divides a defender's, and a
failed hot attempt can be *botched* (pass fails AND ~2.5s lost). Tyre wear is the slow
permanent layer under it: a linear lap-time tax plus a convex end-of-life cliff (the
"pit now" pressure in enduros; a lightly-worn sprint set stays cheap).
`tests/test_commands.py` + the exploit-closed guard pin that managed rhythm beats
held all-out.

The AI is a rule-based pit boss playing the same game (`_ai_command`): pit when
tyres/fuel cross `AI_PIT_TIRE_PCT`/`AI_PIT_FUEL_PCT`, lift to the matching cooling
command past an overheat threshold, and fight tactically — within the attack gap a
healthy rival goes `go_all_out`, merely near it leans on `push`, and on the last lap of
a battle it sends it even in the red (gated by its own reliability/skill, so it can
cook itself).

**Race loop keys** (`cli._run_race`): the footer + help are generated from
`cli._race_local_keys()` — pace n/p/o/t/f/c/i, presentation `l` next-lap / `>` faster /
`x` end, empty Enter toggles pause (PAUSED banner; sim only advances while running),
`?` opens help with the sim clock frozen, `b` leave-race confirm (simulate to end,
result recorded), `q` quit-game confirm.

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

Liveliness comes from three engine-side touches in `simulate_tick`:

```text
rival jitter   (RIVAL_LAP_JITTER_S, sqrt(slice)-scaled)  -> pack shuffles (tick-count invariant)
reactive push  (RIVAL_REACTIVE_GAP_S)                    -> rivals race you back
overtaking     (OVERTAKE_* constants)                    -> passes must stick; trains form on
                                                            narrow tracks with breathing follow
                                                            gaps (racecraft is live)
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
tune_editor_screen(state, car_id, draft)          # sections menu + delta readout
tune_section_screen(state, car_id, section, draft) # one group of knobs
stage_tune_value(state, car_id, field, value)      # per-field draft validation
apply_tune_draft(state, car_id, draft)             # atomic apply ([W])
```

The in-game tune flow is a **creator-style section editor** (mirrors `editor/app.py`'s
edit → edit_section → edit_field loops): pick a car, then a sections menu
(`_TUNE_FIELD_GROUPS`: Tyres/Drivetrain/Brakes/Suspension/Aero) opens one group of
knobs at a time. Edits are **staged into a draft** (dict field → value, owned by the
UI session — CLI locals in `cli._tune_editor`, web `self._tune_draft`); `[W]` applies
the whole draft atomically via `apply_tune_draft`/`update_tune_fields`, and backing
out with staged changes asks apply/discard/keep-editing. Every screen carries a live
readout with before→after deltas (`_tune_preview_lines`: PR/class/type + effective
stats; deliberately **no lap-time sim panel** in-game — that's the creator's job, and
the event screen's Est. Time row covers "how will this race go"). Screens return
`FieldData` with labels, current value, ranges, and option lists — do not make
players memorize internal values; every knob influences `compute_effective_stats`.

Choice fields (`value_type="choice"`) carry an `OptionData.description`; the CLI picker renders it as an **Effect** column so the player sees what each option does. `engine_map` uses this — `actions._engine_map_desc` summarises each map's power/fuel/heat trade-off (`ENGINE_MAP_POWER`/`FUEL`/`HEAT`). Reuse this pattern for any new enum field instead of hardcoding prose.

Some tune fields/values are **gated by installed parts** (GT-style unlocks): a
field can arrive locked with a reason (`FieldData.locked`/`lock_reason` via
`game/parts.py: lock_reason_for_tune_field` / `tune_field_value_allowed`), e.g.
non-stock engine maps need a sports ECU. Buy/install parts through the upgrades
flow (`upgrades_slot_screen` → `upgrades_part_screen` → buy/install/unequip).

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

## Compendium

The `compendium/` package is the **single source of truth** for player-facing
reference documentation of every editable/tunable parameter (cars, drivers,
tracks, events). Two renderers consume the one assembled registry so they cannot
drift: the in-game manpages-style screens and the standalone static page.

- **Data model** (`model.py`): `Chapter` → `Section` → `Entry`. `Entry.id` is a
  globally-unique domain-prefixed dotted path (`car.tune.final_drive`,
  `track.segment.tags`, `track.tag.long_straight`, `driver.pace`).
- **Content** (`content_*.py`): ranges/choices/`editable_in` are **harvested
  programmatically** from `editor.fields` schemas + `constants` (never retyped);
  only labels/units/ideals/effect summaries/prose are hand-authored. Prose is
  intentionally sparse — the `effect_summary` one-liner carries most fields.
  Drivers are hand-built (no schema). Segment tags are one `Entry` each, their
  effects derived from `SEGMENT_TAG_SPEED/_WEIGHTS/_RATES`.
- **Registry** (`registry.py`): builds `CHAPTERS`, `ENTRIES_BY_ID`, and
  `TUNE_LOOKUP` (bare tune-field name → `Entry`, via deterministic dotted-id
  construction). Imports **no** `game.actions` — that module imports the registry,
  so a dependency the other way would be circular.
- **In-game** (`game/actions.py`): `compendium_screen(path, query)` builds the
  index/chapter/section/field-detail `ScreenData`; navigation state rides in the
  screen token (`compendium`, `compendium:cars/Tune`, `compendium?<id>`) so the
  terminal and Pyodide web build share one render path. `compendium_nav()` maps an
  input to the next token (used by `cli.run_menu_choice` and `web._menu_input`).
  Reachable via the `C` hotkey, `compendium <field>` direct-jump, and the `/ref`
  overlay from any prompt (returns in place; leaving the compendium goes back to
  wherever it was opened from). Per-field help
  also surfaces in the tune editor (`FieldData.help` from `TUNE_LOOKUP`, shown when
  a field is opened — NOT as a table column, which breaks the pinned layout), the
  driver detail Help column, and creator field notes (`registry.entry_for`). The
  terminal creator has an `[R]` launcher into the same drill-down.
- **Static page** (`render_html.py` → `tools/compendium_template.html` →
  `web/compendium.html`): a `globs is None` target in `build_web.py` (pre-rendered
  HTML, no Pyodide payload); every row carries `data-text` for the vanilla-JS
  filter box; cross-linked from the game and creator pages.
- **Tripwires** (`tests/test_compendium.py`): every `editor.fields` schema field,
  every `Driver` field, every `_TUNE_FIELD_GROUPS` name, and every `SEGMENT_TAG`
  must resolve to an entry, and harvested ranges must match source of truth. **Add a
  documented knob and you MUST add a compendium entry or these fail.**

## Common Change Targets

- New car/driver/event/part/track: add JSON under `data/`, update tests if needed.
  Parts live in `data/parts/seed_parts.json` (slot, price, effects, optional
  `unlocks`); every part/slot needs a compendium entry (completeness test).
- New screen or picker: go through `interfaces/shell.py` — push a `Screen` with a
  `LocalKey` table and read input via `shell.prompt()` (or `cli._picker` for list
  pickers; `CreatorApp.prompt_action` in the editor). Never hand-roll an input
  loop, never print chrome with markup-parsing `terminal.print` (use
  `print_plain`), and never bind a local key to b/q/h.
- New tune field: update `TuneSetup`, seed JSON, `TUNE_FIELD_RANGES`, `_TUNE_FIELD_GROUPS`/`_TUNE_FIELD_LABELS` in actions.py, fold it into `compute_effective_stats` (centered factor, ideal in constants), and add a `compendium/content_cars.py` entry (the completeness test fails otherwise), tests.
- New schema field (car/track/event) or segment tag: add the field to `editor.fields` (or the tag to `SEGMENT_TAG_*`), then a matching `compendium/content_*.py` entry — `tests/test_compendium.py` fails until documented. See ## Compendium.
- New race command: update `COMMAND_MODIFIERS` (7-column tuple incl. overtake), `race_command_options()`, cooling sets if it cools, tests — and make sure its key doesn't collide in `cli._race_local_keys()`. Engine maps are NOT commands — they live in `tune.engine_map`.
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
- Balance team progression: tune `TEAM_LEVEL_THRESHOLDS`, `TEAM_XP_BY_CLASS`,
  `TEAM_XP_FINISH_MULTIPLIERS`, `TEAM_XP_EVENT_KIND_MULTIPLIER`, and
  `TEAM_XP_REPEAT_MULTIPLIERS`, then progression tests/probe output; keep rules in
  `game/progression.py`.
- Add web UI: create new interface/API layer that calls `game.actions`; avoid importing `interfaces.cli`.
- Add save fields: update dataclasses, loader/save roundtrip tests, schema if breaking.

## Test Map

```text
test_models.py             Loaders/dataclasses/track validation.
test_save_load.py          Save schema and roundtrip.
test_progression.py        Team Level derivation, event progress, and Team XP award math.
test_effective_stats.py    Stats, derived PR/class rating, tune effects.
test_lap_time.py           Lap formula and full-race basics.
test_segment_resolution.py Segment profiles and per-interval lap pace.
test_orphan_stats.py       Secondary car/tune/durability stat folds (direction tests).
test_balance_baseline.py   Reference lap + race-outcome balance guard (catches drift).
test_race_tick.py          Interactive race commands.
test_commands.py           Command set: live stress column, one-shot pit, engine-map decoupling.
test_attrition_endgame.py  Fuel failure state, heat balance, AI pit boss, terminal failures.
test_wired_systems.py      Mid-race damage, driver energy, distance wear, resale, weeks,
                           overtaking, race-day weather.
test_telemetry.py          Telemetry history and warnings.
test_economy.py            Buy/sell/repair/prizes.
test_opponents.py          Event restrictions, pace floors, and opponent generation.
test_car_catalog.py        Catalog class distribution and S-class competitiveness.
test_actions.py            UI-neutral action/screen layer.
test_shell.py              The universal screen contract (dispatch, palette, back
                           semantics, footer generation, dirty-jump confirms).
test_cli.py                Terminal menu/screen behavior (Home, b/q/? semantics,
                           pickers, tune editor, upgrades rebind, race key table).
test_driver_gen.py         Procedural drivers: generator determinism, potential,
                           salary, market churn, save round-trip.
test_editor_templates.py   Creator schemas/templates + unsaved-draft guard +
                           creator compendium browser.
test_compendium.py         Doc registry completeness/consistency tripwires.
test_build_web.py          Static compendium render + bundle isolation-import guard.
test_presentation_timing.py Resolution-invariance of lap noise, watched-time tick density,
                            and the pre-race play/real estimate.
```
