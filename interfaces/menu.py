from __future__ import annotations

from dataclasses import dataclass

from game.progression import team_xp_progress


@dataclass(frozen=True)
class MenuAction:
    key: str
    label: str
    command: str


MENU_ACTIONS = [
    MenuAction("G", "Garage", "garage"),
    MenuAction("E", "Events", "events"),
    MenuAction("D", "Drivers", "drivers"),
    MenuAction("M", "Market", "market"),
    MenuAction("R", "Race", "race"),
    MenuAction("X", "Sell", "sell"),
    MenuAction("U", "Upgrades", "upgrades"),
    MenuAction("T", "Tune", "tune"),
    MenuAction("P", "Repair", "repair"),
    MenuAction("S", "Save", "save"),
    MenuAction("L", "Load", "load"),
    MenuAction("C", "Compendium", "compendium"),
    MenuAction("H", "Help", "help"),
    MenuAction("Q", "Quit", "quit"),
]


def menu_bar() -> str:
    labels: list[str] = []
    for action in MENU_ACTIONS:
        if action.label.lower().startswith(action.key.lower()):
            labels.append(f"[{action.key}]{action.label[1:]}")
        else:
            labels.append(f"[{action.key}]{action.label}")
    return "  ".join(labels)


def menu_command(choice: str) -> str | None:
    normalized = choice.strip().lower()
    if not normalized:
        return None
    for action in MENU_ACTIONS:
        if normalized == action.key.lower():
            return action.command
    return None


def team_xp_status(team_xp: int, width: int = 8) -> str:
    progress = team_xp_progress(team_xp)
    if progress.next_level is None:
        return f"Team Lv {progress.level} [MAX] {progress.xp} XP"
    filled = round(progress.level_fraction * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"Team Lv {progress.level} [{bar}] {progress.xp}/{progress.next_level_xp} XP"


def status_bar(money: int, week: int, garage_count: int, screen: str, team_xp: int = 0) -> str:
    return (
        f"Money: ${money:,}  Week: {week}  Garage: {garage_count}  "
        f"{team_xp_status(team_xp)}  Screen: {screen.title()}"
    )
