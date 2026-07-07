# Scripted pty playtests

Expect-style drivers that play the real terminal game (`python3 main.py`) through a pty —
no mocks, the same screens a player sees. Written during the 2026-07-07 audit playtest
that reached Team Level 3 in ~60 races and surfaced the class-oscillation and economy
findings (see PLAYTEST_FIXES.md at the repo root).

Not unittest cases: file names deliberately don't match `test*.py`, so
`python3 -m unittest discover -s tests` ignores this folder. Run one directly:

```bash
python3 tests/playtest/play2.py   # from anywhere; scripts cd via absolute ROOT
```

Each script prints checkpoint lines as it plays, a `CHECKPOINTS`/`ANOMALIES` summary at
the end, and writes a full ANSI transcript log next to itself.

Current status: use these as smoke/regression drivers for real terminal flows. The full
multi-session career pacing replay is intentionally deferred until the planned event/track
catalog expansion lands, because Lv3 timing depends on available E/D/C content.

These scripts should not preserve real playtime. They drive the real pty and screens, but
race progress should use instant/sim-to-end commands; timeout values are deadlock guards
only, not pacing targets.

| Script   | Scenario |
|----------|----------|
| play.py  | Session 1 — feature sweep on a fresh career: market browse/detail, buy+sell round trip, hire+fire, buy&install a part, tune stage+apply, 14 races, repair, save, quit. |
| play2.py | Session 2 — smart career: buy the Nagoya, tune it, race/repair loop. (Found the repair→class-flip lockout.) |
| play3.py | Session 3 — Eurovan grind to Lv2, then D-class events with the Nagoya. (Found the repair-cost > car-value economy corner.) |
| play4.py | Session 4 — loads a save through the UI, continues the career. (Found lightweight max_weight enforcement, repeat-XP decay to +3.) |
| play5.py | Session 5 — broke-state recovery: free open_track_day farming, then repair + D-event pushes. |
| play6.py | Session 6 — first-win hunting on never-entered E events with the Torino. |
| play7.py | Session 7 — final push: track-day farm then a lightweight_challenge first win → **Team Lv3**. |

Sessions 4–7 load `saves/save1.json` (or a named save) — they continue a career rather
than starting fresh, so run them against a save you're willing to play forward.

Mechanics cheat-sheet (details in each script):

- Prompts are `input()`-based with stable labels (`Choice:`, `Back:`, `Sell:`, `Hire:`,
  `Release:`, `Repair:`, `Car:`, `Slot:`, `Part:`, `Action:`, `Section:`, `Field:`,
  `Path:`, `Value (lo-hi):`). Strip ANSI before matching — rich is installed.
- Actions confirm with `Press Enter...` pauses; the `settle()` helper dismisses them.
- In the race loop send `x` to simulate-to-end instantly; `b` asks for confirmation.
- Pickers accept ids (`torino_500r`, `sunday_cup`, `driver_novak`) — more robust than row
  numbers.
- If a driver script dies mid-session it can orphan the game process:
  `pkill -f "python3 main.py"`.
