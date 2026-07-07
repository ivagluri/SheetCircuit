# SheetCircuit — Changelog

Shipped history: what landed, by commit, newest first. (Older sections below were
written on the `refactor/track-agnostic-sim` branch.)

## De-bloat audit

- **Dead code deleted** (`479a967`) — a full-codebase audit (every definition
  cross-referenced against every call site, including tests and the web bundles) removed
  ~15 orphaned functions left behind by earlier reworks: the legacy string renderers and
  unused row builders in `render_text.py`, two superseded `set_tune` implementations,
  the pre-picker `upgrades_car_screen`/`race_entry_screen` screens, `load_all_data`,
  `tune_field_value_allowed`, the never-instantiated `Column` dataclass, the orphaned
  `CAR_MOD_FIELD_*` constants from the removed hard-mod feature, and a dozen unused
  imports. 211 lines gone, zero behavior change.
- **Duplicated helpers consolidated** (`947f223`, `04b2813`) — seven copy-paste
  duplications now live in one home each: the slot/part picker-input matchers moved from
  both interfaces into `game.parts` (`match_part_slot`/`match_slot_part`), the compendium
  Range/Ideal/Editable column formatters into a new `compendium/format.py` shared by the
  in-game screens and the static page, `clamp` into `game.effective_stats`, `slug` into
  `compendium.harvest`, the browse/sort screen tuple into `game.sorting.SORTABLE_SCREENS`,
  text truncation into `game.actions.clip_text`, and the class rank map into
  `constants.CLASS_ORDER` (derived from `CLASS_THRESHOLDS` so it can never drift). Only
  visible change: post-race truncation now uses `…` instead of `...`.
- **Agent map refreshed** (`ab561c6`) — `AGENT_MAP.md` no longer references the deleted
  code and now documents the previously unmapped modules (`reference_suite`,
  `compendium/harvest` + `format`, the editor web adapter/sample tracks/verify harness,
  and the `probe_event`/`inspect_car` tools).

## UI polish

- **Readable upgrade effects** (`67e97ba` → `e33b37f`) — the upgrade shop and parts compendium no longer expose
  raw stat paths like `powertrain.power_hp`; part rows now show compact mechanical
  summaries such as `Power +`, `Drag --`, and `unlocks Engine Map`, while selected-part
  prompts show separate rows for improvements, reductions, numeric overrides, and
  tune-control unlocks.
- **Race banner names the event, track, and driver** — the live race screen led with
  only "Lap X/Y"; it now reads e.g. `Sunday Cup @ Maple Short · Pete Novak · Lap 2/5`
  so you can see what you're running and who's driving without waiting for the results
  screen (shared render path, so CLI and web both get it).
- **Internal IDs dropped from the data tables** — with names rendering reliably
  everywhere, the redundant `ID` column is gone from every list screen (garage, market,
  drivers, events, part slots, and the parts catalog) in both the terminal and the
  browser; the part-slot table's duplicated id/name pair collapses to the slot label,
  and the upgrades/tune breadcrumbs show the car's name instead of its id. Selecting by
  number (or still typing an id) is unchanged; only the display column was removed. The
  single `ID` field in the car/event/part *detail* views is intentionally kept.

## One screen contract (UI/UX unification)

- **Universal keys + shell framework** — every screen now obeys one input contract,
  enforced by the new `interfaces/shell.py` rather than per-screen discipline: `b`/`back`
  pops one level everywhere (pickers, details, editors, compendium, race), `q`/`quit`
  always quit-confirms, `?`/`h` opens one context-aware help, and a slash palette works
  from any prompt (`/save` instant save, `/home` jumps to the new **Home** root menu,
  `/ref` opens the compendium overlay and returns in place, `/load` stays Home-only).
  Screens declare a key table; the breadcrumb (`Home › Upgrades car › Tires`) and footer
  are auto-generated from it, so an advertised key can never be dead — which killed the
  tab bar printed (dead) on every sub-screen, the `q`=quit-vs-cancel ambiguity, and the
  upgrades prompt where `b` meant *buy* (now y=buy, i=install, u=unequip). The race gains
  Enter-to-pause with a PAUSED banner, help that freezes the sim clock, `b` leave-race
  confirm, and a footer listing *all* keys — un-shadowing the pace hotkeys N/F from
  next-lap/faster (now `l`/`>`). Same contract in the creator (its `B`/`W` keep working;
  `?` help + footer + breadcrumb added). Chrome prints through a markup-safe
  `terminal.print_plain` (rich ate `[q Quit]` as a style tag). New `tests/test_shell.py`
  pins the contract; 437 tests green.

## GT-style parts & upgrades

- **Parts catalog + tune unlocks** (`b68715a`) — a Gran Turismo-style upgrade economy:
  30 parts across one-per-slot categories (`game/parts.py` SLOT_RULES), bought per car,
  installed/unequipped freely once owned (unequip = back to stock, no refund). Part
  effects fold into `compute_effective_stats`, and parts **gate tune fields** — e.g.
  non-stock engine maps need a sports ECU (`lock_reason_for_tune_field`). Guided
  upgrades flow (car → slot → part) in CLI and web, a parts chapter in the compendium,
  an `open_track_day` no-fee event, and save-schema support for owned/installed parts.

## Tactical pace

- **Heat-limited bursts** (`aa34781`, Phases A–C) — Normal/Push/All-Out finally matter in
  short sprints. Thermal brake: engine heat genuinely climbs at all-out (a mid car
  redlines in ~2 laps) and recovers in ~1 cool-down lap, with catalog heat rates
  normalised so cooling/engine-map stay real build levers. Overheat teeth: a warning
  band that bleeds lap time, then a danger band where a mechanical issue is ~a coin
  flip. Pace now feeds **overtaking** (new modifier column, graded N<P<O, two-sided:
  boosts the attacker, weakens the defender) and a failed hot attempt can be *botched*
  (~2.5s lost).
- **Rivals play the same game** (`4db8085`, Phase D) — within the attack gap a healthy
  rival sends `go_all_out`, merely near it leans on `push`, and on the final lap of a
  battle it throws everything at the flag even in the red — and can cook itself.
- **Progressive tyre tax** (`c60a885`, Phase E) — worn tyres cost a steady linear tax
  plus a convex end-of-life cliff (0% ≈ 12s/lap): real pit pressure in enduros while a
  lightly-worn sprint set stays cheap.
- **Exploit closed** (`8f0b81d`, Phase F) — regression-tested: managed rhythm (cruise +
  final-lap burst) beats held all-out on mean finish and never DNFs, while naive
  all-out throws ~7% of races away. Cool-car floor raised so even the kei starter pays
  within ~3 laps.
- **Tooling & fixes** (`0c64f8f`, `e965d6a`) — `tools/pace_probe.py` (the per-lap
  thermal/wear instrumentation the rework was tuned against); shadowed pace hotkeys
  fixed and an elapsed clock added to all race bars.

## Procedural drivers

- **Generator, market, potential** (`62dba07`, `e2f6b27`) — the fixed 4-driver roster is
  replaced by a procedurally generated, developing population: `game/driver_gen.py`
  (archetypes, name pools, potential + salary formulas), a persisted rotating
  **free-agent market** (churns every few weeks, seeded per career), and
  `Driver.potential` capping XP growth. Race rivals get real generated drivers instead
  of "Rival N". Fixed hired-generated-driver race entry; `tests/test_driver_gen.py`
  pins determinism, market churn, and save round-trips.

## Compendium

- **Single-source reference docs** (`b86a126` → `cad5acd`) — the `compendium/` package
  is the one registry documenting every editable/tunable parameter (cars, parts,
  drivers, tracks, events): ranges/choices harvested programmatically from the editor
  schemas + constants, only prose hand-written. Three consumers that cannot drift:
  in-game manpages-style screens (`C` hotkey, drill-down index → chapter → section →
  field, direct `compendium <field>` jump), per-field help at point of use (tune
  editor, driver detail, creator field notes), and a static filterable
  `web/compendium.html`. Completeness tripwire tests fail loudly if a knob lands
  undocumented.

## Team progression

- **Team XP career ladder** (`a92b025` → `2df617d`) — pure, derived progression:
  `GameState.team_xp` → Team Level via thresholds (never stored), XP awarded from
  finish quality × event class × event kind with repeat-win smoothing and a first-win
  bonus. Events carry `min_team_level` gates + `event_kind`; per-event progress
  (starts/wins/podiums/best) persists in saves (schema v2). Team Level/XP shows in the
  global status bar, post-race commits it all with before→after tables, and
  `tools/probe_progression.py` checks pacing without racing. Post-race results got a
  compact multi-column layout (`4ab367c`).

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
