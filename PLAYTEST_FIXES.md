# Fix plan: playtest findings (class oscillation, economy spiral, save prompt, tune minors)

## Context

A scripted pty playtest (7 sessions, ~60 races to Team Lv3) surfaced one contract bug and
two design problems:

1. **Save/load path prompts bypass the shell contract** — typing `q` at "Save path" wrote a
   file named `q` at the repo root (`interfaces/cli.py:1107,1116` use raw `terminal.prompt`).
2. **Class oscillates with condition** — eligibility class derives from condition-scaled
   stats, so the market sells intrinsically-D cars labeled E at 70% condition, repairing
   flips them D (locked out of the E event they just won), and one race of wear flips them
   back. Root causes: `derived_class`/`class_rating` read condition-scaled stats, and
   `_condition_factor = condition/100` (linear) makes wear cost huge pace.
3. **Economy corners a mediocre player** — rivals rubber-band up to the player's pace
   (`opponents.py:106: anchor_lap = min(player_lap, floor_lap)`), so over-carring never wins;
   the intended first-win-driven XP ladder (TEAM_PROGRESSION.md) stalls; only top-3 pay;
   repair is one flat ~$2,250 button (can exceed the car's price; no partial option).
4. **Minor**: tune apply `w` only bound at the Section menu — at the Field list it errors
   "Unknown tune field: w".

Decisions locked with the user (grill session 2026-07-07): intrinsic class AND intrinsic PR;
gentle condition→pace curve (condition's teeth = failure risk + resale); one-sided
matchmaking cap at event-typical pace; prizes paid to ~P5; partial + value-scaled repairs;
XP constants untouched; Team Level system kept — event-catalog expansion is a **separate
follow-on**, after which the pty playtest must be re-run.

## Workstreams

### 1. Intrinsic class & PR (game/effective_stats.py)

`derived_rating` (:284), `class_rating` (:294), `derived_class` (:298), `class_breakdown`
(:304), `performance_type` (:325) all compute on a **nominal-condition copy** of the car
(deepcopy with every `condition` field set to 100; keep parts/tune). Everything downstream
inherits intrinsic behavior automatically: garage/market Class+PR columns, sorting keys,
`max_class_rating` event restriction, opponent eligibility, compendium class derivation.
Sell price (`economy._resale_factor`) keeps using real condition — unchanged.
Add a small private helper (e.g. `_nominal(car)`) rather than threading flags through.

### 2. Gentle condition→pace curve (game/effective_stats.py:350 + constants.py)

Replace linear `_condition_factor(value) = value/100` with a two-slope curve, constants in
constants.py next to `MIN_CONDITION_FACTOR`:

```
factor = 1 - GENTLE*(100-c) - STEEP*max(0, KNEE-c), clamped to MIN_CONDITION_FACTOR (0.40)
GENTLE=0.002, KNEE=40, STEEP=0.01  →  100%:1.00  70%:0.94  40%:0.88  0%:0.40
```

Comment the intent: worn cars mostly *break* (FAILURE_CONDITION_SCALE unchanged) and resell
poorly; they only crawl when truly wrecked. Note: the reference car is at 100% so
`test_balance_baseline` anchors should not move; direction tests in
`test_effective_stats`/`test_orphan_stats` may pin the old linear slope — update those.
Sanity-check the new slope with `tools/pace_probe.py` and `tools/inspect_car.py`.

### 3. Matchmaking: cap rivals at event-typical pace (game/opponents.py + constants.py)

Keep the mercy floor; stop chasing a fast player upward. After the existing anchor calc
(`opponents.py:106`):

```
typical_lap = percentile of eligible-field laps at new EVENT_PACE_ANCHOR_PERCENTILE (per class)
anchor_lap  = max(min(player_lap, floor_lap), typical_lap)   # laps: smaller = faster
```

Reuse `_event_floor_lap`'s shape for the percentile helper. Add
`EVENT_PACE_ANCHOR_PERCENTILE` beside `EVENT_PACE_FLOOR_PERCENTILE` (start ~0.25–0.35 per
class; practice events keep player anchoring as today). Update `tests/test_opponents.py`
(pins current anchoring) and verify with `tools/probe_event.py` that an over-classed car
now heads the matchmaking band.

### 4. Prizes to ~P5 (data/events/*.json only)

Extend each event's `prize_money` to 5 entries: P4 ≈ 15% and P5 ≈ 8% of the win, rounded to
tidy values. `simulation._prize_for_position` already handles arbitrary table length — no
code change. Keep `open_track_day` as-is (already pays deep).

### 5. Repairs: partial + value-scaled (game/economy.py:57, constants.py, interfaces/cli.py + web.py)

- Cost: replace flat `REPAIR_COST_PER_POINT = 18` with value-scaled per-point:
  `max(REPAIR_COST_MIN_PER_POINT, car.value * REPAIR_COST_VALUE_FRACTION)` (start
  ~`0.002`, min ~$4) so a total wreck costs ~25% of car value to fully fix. Keep
  `repair_car(points=...)` signature.
- UI: after the repair car pick, an `Action`-style prompt (shell contract, LocalKeys) with
  tiers — `f` full (25 pts), `h` half (12), `p` patch (5) — each showing its computed cost;
  same flow mirrored in `interfaces/web.py`'s repair input mode.
- Update `tests/test_economy.py` cost expectations; add a partial-repair test.

### 6. Save/load prompts onto the shell contract (interfaces/cli.py:1107,1116)

Route `_save_picker`/`_load_picker` through `shell.prompt` (so b/q/?/palette work), keep the
`saves/save1.json` default on empty, and validate the path (must end `.json`; reject names
that collide with command words). The `/save` palette path is already fine.

### 7. Tune-apply `w` at the Field list (interfaces/cli.py:~1029 + web.py tune modes)

Add `_TUNE_APPLY_KEY` to the section editor's LocalKey table so the Field-list footer
advertises `[w Apply setup]` and `w` applies from there too (identical apply path as the
Section menu). Mirror in `interfaces/web.py`'s `_tune_field_input`. Kill the
"Unknown tune field: w" path.

## Test & docs sweep

- Expect re-baselining: `test_car_catalog` (catalog class distribution rises — cars ship
  <100% condition), `test_opponents`, `test_economy`, `test_effective_stats`,
  `test_orphan_stats`, `test_cli` (repair tiers, save prompt, tune footer).
- `test_balance_baseline` should NOT move (reference car at 100%); treat movement as a bug.
- CHANGELOG.md entry (repo convention), AGENT_MAP.md touch-ups (repair tiers, intrinsic
  class note, `tests/playtest/` mention), rebuild web bundles (`tools/build_web.py` +
  `--target creator`) and commit them with the source, per repo convention.
- Commit the two new untracked artifacts with this work: `tests/playtest/` (the pty
  playtest drivers + README) and `PLAYTEST_FIXES.md` (this plan, copied to the repo root).

## Verification

1. Full suite: `python3 -m unittest discover -s tests`.
2. Probes: `tools/pace_probe.py` (condition curve), `tools/probe_event.py` (matchmaking cap
   with an over-classed car), `tools/inspect_car.py` (intrinsic PR at varied condition).
3. **Scripted pty playtest** (the method that found these bugs): the seven session drivers
   plus a README now live in `tests/playtest/` (deliberately not `test*.py`, so unittest
   discovery ignores them; run e.g. `python3 tests/playtest/play2.py`). Re-run a fresh
   career after the fixes. Success criteria: repairing never changes a car's class; an
   over-carred E event is winnable; a mid-pack career is never cornered into 0-XP farming
   as the *only* legal move; Lv3 reachable in roughly 15–25 races.

   2026-07-07 implementation note: run the pty scripts as smoke/regression drivers for
   shell flows now, but defer the full seven-session career replay until the follow-on
   event-catalog expansion lands. The current pacing result depends materially on how much
   E/D/C event content exists.

## Follow-on (explicitly out of scope here)

Event-catalog expansion (~more E/D/C events on existing tracks with varied restrictions) as
its own design pass — then **re-run the pty playtest** against the fuller board to judge XP
pacing before touching TEAM_XP constants.
