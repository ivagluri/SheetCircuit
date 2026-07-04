from __future__ import annotations

from typing import Any

from constants import TEAM_LEVEL_THRESHOLDS
from game.progression import normalize_event_progress, team_level_for_xp


def event_kind_label(event_kind: str) -> str:
    return str(event_kind).replace("_", " ").title()


def event_requirement_text(event: Any) -> str:
    return f"Lv {event.min_team_level}"


def team_status_text(state: Any, event: Any) -> str:
    current_level = team_level_for_xp(state.team_xp)
    if current_level >= event.min_team_level:
        return "Open"
    return f"Locked ({xp_needed_for_team_level(state.team_xp, event.min_team_level)} XP)"


def xp_needed_for_team_level(team_xp: int, min_team_level: int) -> int:
    target = TEAM_LEVEL_THRESHOLDS.get(int(min_team_level), max(TEAM_LEVEL_THRESHOLDS.values()))
    return max(0, target - max(0, int(team_xp)))


def event_best_text(progress: dict | None) -> str:
    normalized = normalize_event_progress(progress)
    if normalized["starts"] == 0:
        return "No starts"
    best_position = normalized["best_position"]
    if best_position is None:
        return "No finish"
    wins = normalized["wins"]
    if wins == 1:
        return "Win"
    if wins > 1:
        return f"{wins} wins"
    if best_position <= 3:
        return f"P{best_position} podium"
    return f"P{best_position}"


def event_progress_rows(progress: dict | None) -> list[list[object]]:
    normalized = normalize_event_progress(progress)
    best_time = normalized["best_time_s"]
    return [
        ["Starts", normalized["starts"]],
        ["Best Result", event_best_text(normalized)],
        ["Wins", normalized["wins"]],
        ["Podiums", normalized["podiums"]],
        ["Best Time", f"{best_time:.1f}s" if best_time is not None else "-"],
    ]
