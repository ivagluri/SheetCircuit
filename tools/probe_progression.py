#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from constants import EVENT_KINDS, TEAM_LEVEL_BY_CLASS, TEAM_LEVEL_THRESHOLDS, TEAM_XP_BY_CLASS
from game.progression import team_level_for_xp, team_xp_award

FINISHES = [
    ("P1", 1, False),
    ("P2", 2, False),
    ("P3", 3, False),
    ("Finish", 4, False),
    ("DNF", 1, True),
]
REPEAT_WINS = [0, 1, 2, 3]


def main() -> int:
    print("SheetCircuit Team Progression Probe")
    print()
    print_thresholds()
    print()
    print_awards()
    print()
    print_career_path()
    return 0


def print_thresholds() -> None:
    print("Team Level Thresholds")
    for level, xp in sorted(TEAM_LEVEL_THRESHOLDS.items()):
        print(f"  Lv {level}: {xp} XP")


def print_awards() -> None:
    print("Team XP Awards")
    for event_kind in EVENT_KINDS:
        print(f"\nEvent Kind: {event_kind}")
        headers = ["Class", "Wins Before", *[label for label, _position, _dnf in FINISHES]]
        print(_row(headers))
        print(_rule(headers))
        for car_class in TEAM_XP_BY_CLASS:
            for wins_before in REPEAT_WINS:
                values = [car_class, str(wins_before)]
                for _label, position, is_dnf in FINISHES:
                    award = team_xp_award(
                        car_class,
                        event_kind,
                        position=position,
                        is_dnf=is_dnf,
                        event_progress_before={"wins": wins_before},
                    )
                    values.append(str(award.total_xp))
                print(_row(values))


def print_career_path() -> None:
    print("Simple Ladder Path")
    team_xp = 0
    open_wins = 0
    print(_row(["Step", "Class", "Kind", "XP Award", "Team XP", "Team Lv"]))
    print(_rule(["Step", "Class", "Kind", "XP Award", "Team XP", "Team Lv"]))
    step = 1
    for car_class in TEAM_XP_BY_CLASS:
        while team_level_for_xp(team_xp) < TEAM_LEVEL_BY_CLASS[car_class]:
            award = team_xp_award("E", "open_invitational", position=1, event_progress_before={"wins": open_wins})
            team_xp += award.total_xp
            open_wins += 1
            print(_row([str(step), "E", "open_invitational", f"+{award.total_xp}", str(team_xp), str(team_level_for_xp(team_xp))]))
            step += 1
        award = team_xp_award(car_class, "ladder", position=1, event_progress_before={"wins": 0})
        team_xp += award.total_xp
        print(_row([str(step), car_class, "ladder", f"+{award.total_xp}", str(team_xp), str(team_level_for_xp(team_xp))]))
        step += 1

def _row(values: list[str]) -> str:
    widths = [8, 12, 18, 8, 8, 8, 8]
    padded = []
    for index, value in enumerate(values):
        width = widths[index] if index < len(widths) else 8
        padded.append(str(value).ljust(width))
    return "  ".join(padded).rstrip()


def _rule(values: list[str]) -> str:
    return _row(["-" * len(value) for value in values])


if __name__ == "__main__":
    raise SystemExit(main())
