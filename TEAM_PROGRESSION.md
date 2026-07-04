# SheetCircuit Team Progression V1 Plan

This document captures the agreed plan for the manager-focused Team Progression
feature so work can resume after context reset.

## Product Shape

- Keep the game in a team manager paradigm. The player does not become a driver.
- Add non-spendable Team XP that derives numeric Team Level.
- Do not store Team Level separately; derive it from `team_xp`.
- V1 progression affects events only. Defer driver hiring gates, sponsors, parts
  shop, full race history, and new event content.
- Locked events remain visible, like Gran Turismo-style future goals.
- Event entry should be blocked centrally when team level is too low.
- Open invitationals remain available as safety valves and variety, but should be
  less efficient for Team XP and authored with real friction.
- Existing event content should be annotated explicitly even though loader defaults
  can infer compatibility values.

## Committed Milestones

### Milestone 1: Progression Math

Commit: `a92b025 Add team progression math`

Added:

- Team progression constants in `constants.py`
- Pure helper module `game/progression.py`
- Focused tests in `tests/test_progression.py`
- AGENT_MAP entries for progression rules and tests

Core helpers:

- `team_level_for_xp(team_xp)`
- `team_xp_progress(team_xp)`
- `min_team_level_for_class(car_class_limit)`
- `is_team_level_unlocked(team_xp, min_team_level)`
- `empty_event_progress()`
- `normalize_event_progress(progress)`
- `updated_event_progress(progress, position, is_dnf, total_time_s)`
- `team_xp_award(class, event_kind, position, is_dnf, event_progress_before)`

### Milestone 2: Persist Progression State

Commit: `fe3d98a Persist team progression state`

Added:

- `GameState.team_xp`
- `GameState.event_progress`
- save schema bumped to `SCHEMA_VERSION = 2`
- save/load round-trip support for progression fields
- load-time normalization for event progress records
- browser export/import test coverage for progression fields
- AGENT_MAP entries for saved state shape

Current worktree was clean after this commit.

### Milestone 3: Event Model, Loader, And Data

Commit: `b191356 Add event progression metadata`

Added:

- `Event.min_team_level`
- `Event.event_kind`
- loader inference of missing `min_team_level` from `car_class_limit`
- loader default/validation/normalization for `event_kind`
- explicit progression metadata in existing `data/events/*.json`
- `sunday_cup` as the Level 1 ladder starter
- `beater_enduro` as Level 1 `open_invitational`
- creator event schema round-trip support for progression metadata
- focused loader/model and creator-web tests
- AGENT_MAP entries for event progression metadata

Validation run:

- `python3 -m unittest tests.test_models tests.test_race_format tests.test_creator_web tests.test_progression`
- `python3 -m unittest discover -s tests`

### Milestone 4: Event Gates

Commit: `6e2ee8e Enforce event team level gates`

Added:

- Central team-level gate in `race_session.enter_event()`
- Matching gate in the one-shot `simulate_race()` path
- Clear blocked-entry message with required/current Team Level and current Team XP
- No entry-fee deduction when a locked event is blocked
- CLI handling for locked-event errors from the race picker
- Tests for blocked and allowed entry
- Test fixture updates for high-tier event entry
- AGENT_MAP entry for the entry gate

Validation run:

- `python3 -m unittest tests.test_actions tests.test_opponents tests.test_segment_resolution tests.test_supercar_tracks tests.test_wired_systems tests.test_economy`
- `python3 -m unittest discover -s tests`

## Remaining Milestones

### Milestone 5: Event List And Detail UI

Commit: `55d7910 Show event progression status`

Added:

- Shared `game/event_display.py` helpers for event kind, team requirement/status,
  XP-to-unlock, and compact best-progress text
- Event list columns for requirement, status, and best result in action-layer,
  CLI, and web event tables
- Event detail rows for kind, team requirement, locked/open status, current team
  level/XP, and XP needed when locked
- Event detail progress table with starts, best result, wins, podiums, and best
  time
- Locked events remain visible and selectable for detail
- Focused action-layer tests for list/detail progression UI
- AGENT_MAP entry for shared event display helpers

Validation run:

- `python3 -m unittest tests.test_actions tests.test_cli tests.test_web_adapter`
- `python3 -m unittest discover -s tests`

### Milestone 6: Post-Race Summary And Progress Commit

Scope:

- Update `finish_event()`/`finish_race_action()` to commit:
  - Team XP
  - event progress
  - first-win bonus
  - repeat multiplier effects
- Return a dedicated `ScreenData(name="post_race", ...)` instead of a final live
  race screen.
- Post-race summary should include final competitor standings as the first table.
- Suggested table order:
  1. Final Standings
  2. Rewards
  3. Team Progress
  4. Event Progress
  5. Driver Progress
  6. Car Condition
- Capture player car condition before race on `RaceSession` so before/after wear
  can be shown.
- Add focused tests for progress commit and summary contents.
- Update AGENT_MAP.
- Commit milestone.

### Milestone 7: Status Bar Team XP Display

Scope:

- Add compact Team Level/XP display to global status bar.
- Suggested text:
  - `Team Lv 2 [████░░░░] 145/250 XP`
  - max level: `Team Lv 6 [MAX] 1320 XP`
- Keep numeric XP for playtesting.
- Update CLI/web tests affected by status bar output.
- Update AGENT_MAP.
- Commit milestone.

### Milestone 8: Progression Probe Tool

Scope:

- Add `tools/probe_progression.py`.
- Print XP payouts by class, event kind, finish, and repeat win count.
- Optionally simulate simple career paths through event tiers.
- Keep it quick and dependency-free.
- Update AGENT_MAP.
- Commit milestone.

### Milestone 9: Full Test And Tuning Pass

Scope:

- Run full unit suite.
- Run probe output and inspect progression pacing.
- Adjust constants only if obvious rough edges appear.
- Rebuild web bundle only if code/data changes require it at delivery point.
- Commit final tuning/doc updates if any.

## Agreed XP Rules

Current constants:

```python
TEAM_LEVEL_THRESHOLDS = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 850,
    6: 1300,
}

TEAM_XP_BY_CLASS = {
    "E": 25,
    "D": 45,
    "C": 70,
    "B": 105,
    "A": 150,
    "S": 210,
}

TEAM_XP_FINISH_MULTIPLIERS = {
    1: 1.00,
    2: 0.65,
    3: 0.45,
    "finish": 0.15,
    "dnf": 0.00,
}

TEAM_XP_EVENT_KIND_MULTIPLIER = {
    "ladder": 1.00,
    "open_invitational": 0.70,
}

TEAM_XP_REPEAT_MULTIPLIERS = [1.00, 0.85, 0.70, 0.60]
TEAM_XP_FIRST_WIN_BONUS_MULTIPLIER = 1.00
```

Award order:

```text
Team XP = event_base_xp * finish_multiplier * event_kind_multiplier * repeat_multiplier
          + first_win_bonus
```

Repeat multiplier is based on wins already recorded for the event and applies to
non-win finishes after the event has already been won.

## Event Progress Shape

V1 stores structured per-event progress, not full history:

```python
event_progress[event_id] = {
    "starts": 3,
    "best_position": 2,
    "wins": 0,
    "podiums": 1,
    "best_time_s": 384.2,
}
```

This intentionally leaves room for a later `race_history` feature with detailed
spreadsheet-style records: week, event, car, driver, position, lap times, weather,
incidents, prize, Team XP, driver XP, and condition deltas.

## Verification Baseline

After Milestone 2:

```bash
python3 -m unittest tests.test_save_load tests.test_web_adapter.WebSaveLoadTests
python3 -m unittest tests.test_progression
python3 -m unittest discover -s tests
```

Full suite result: 329 tests passing.
