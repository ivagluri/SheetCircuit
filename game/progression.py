from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from constants import (
    EVENT_KIND_LADDER,
    TEAM_LEVEL_BY_CLASS,
    TEAM_LEVEL_THRESHOLDS,
    TEAM_XP_BY_CLASS,
    TEAM_XP_EVENT_KIND_MULTIPLIER,
    TEAM_XP_FINISH_MULTIPLIERS,
    TEAM_XP_FIRST_WIN_BONUS_MULTIPLIER,
    TEAM_XP_REPEAT_MULTIPLIERS,
)


@dataclass(frozen=True)
class TeamXpProgress:
    level: int
    xp: int
    level_start_xp: int
    next_level: int | None
    next_level_xp: int | None
    xp_into_level: int
    xp_needed_for_next: int | None
    level_fraction: float


@dataclass(frozen=True)
class TeamXpAward:
    car_class_limit: str
    event_kind: str
    base_xp: int
    finish_multiplier: float
    event_kind_multiplier: float
    repeat_multiplier: float
    first_win: bool
    result_xp: int
    first_win_bonus: int
    total_xp: int


def team_level_for_xp(team_xp: int) -> int:
    """Highest team level whose threshold has been reached."""
    xp = max(0, int(team_xp))
    level = min(TEAM_LEVEL_THRESHOLDS)
    for candidate, threshold in sorted(TEAM_LEVEL_THRESHOLDS.items()):
        if xp >= threshold:
            level = candidate
    return level


def team_xp_progress(team_xp: int) -> TeamXpProgress:
    """Progress within the current level, including next-level target when any."""
    xp = max(0, int(team_xp))
    level = team_level_for_xp(xp)
    level_start = TEAM_LEVEL_THRESHOLDS[level]
    later_levels = [
        (candidate, threshold)
        for candidate, threshold in sorted(TEAM_LEVEL_THRESHOLDS.items())
        if candidate > level
    ]
    if not later_levels:
        return TeamXpProgress(
            level=level,
            xp=xp,
            level_start_xp=level_start,
            next_level=None,
            next_level_xp=None,
            xp_into_level=xp - level_start,
            xp_needed_for_next=None,
            level_fraction=1.0,
        )
    next_level, next_threshold = later_levels[0]
    span = max(1, next_threshold - level_start)
    into_level = xp - level_start
    return TeamXpProgress(
        level=level,
        xp=xp,
        level_start_xp=level_start,
        next_level=next_level,
        next_level_xp=next_threshold,
        xp_into_level=into_level,
        xp_needed_for_next=max(0, next_threshold - xp),
        level_fraction=max(0.0, min(1.0, into_level / span)),
    )


def min_team_level_for_class(car_class_limit: str) -> int:
    """Default event gate for a class ladder event."""
    try:
        return TEAM_LEVEL_BY_CLASS[car_class_limit]
    except KeyError as exc:
        raise ValueError(f"Unknown car class limit: {car_class_limit}") from exc


def is_team_level_unlocked(team_xp: int, min_team_level: int) -> bool:
    return team_level_for_xp(team_xp) >= int(min_team_level)


def empty_event_progress() -> dict[str, Any]:
    return {
        "starts": 0,
        "best_position": None,
        "wins": 0,
        "podiums": 0,
        "best_time_s": None,
    }


def normalize_event_progress(progress: Mapping[str, Any] | None) -> dict[str, Any]:
    """Fill missing event-progress fields while preserving future extra keys."""
    normalized = empty_event_progress()
    if progress:
        normalized.update(dict(progress))
    normalized["starts"] = max(0, int(normalized.get("starts") or 0))
    normalized["wins"] = max(0, int(normalized.get("wins") or 0))
    normalized["podiums"] = max(0, int(normalized.get("podiums") or 0))
    best_position = normalized.get("best_position")
    normalized["best_position"] = int(best_position) if best_position is not None else None
    best_time = normalized.get("best_time_s")
    normalized["best_time_s"] = float(best_time) if best_time is not None else None
    return normalized


def updated_event_progress(
    progress: Mapping[str, Any] | None,
    position: int,
    is_dnf: bool,
    total_time_s: float | None = None,
) -> dict[str, Any]:
    """Return a new per-event progress record after one race result."""
    updated = normalize_event_progress(progress)
    updated["starts"] += 1
    if is_dnf:
        return updated

    position = _valid_position(position)
    best = updated["best_position"]
    if best is None or position < best:
        updated["best_position"] = position
    if position == 1:
        updated["wins"] += 1
    if position <= 3:
        updated["podiums"] += 1
    if total_time_s is not None:
        total_time = max(0.0, float(total_time_s))
        best_time = updated["best_time_s"]
        if best_time is None or total_time < best_time:
            updated["best_time_s"] = total_time
    return updated


def team_xp_award(
    car_class_limit: str,
    event_kind: str = EVENT_KIND_LADDER,
    position: int = 1,
    is_dnf: bool = False,
    event_progress_before: Mapping[str, Any] | None = None,
) -> TeamXpAward:
    """Calculate team XP from result quality, event type, and prior event wins."""
    progress = normalize_event_progress(event_progress_before)
    base_xp = _value_for_key(TEAM_XP_BY_CLASS, car_class_limit, "car class limit")
    kind_multiplier = _value_for_key(TEAM_XP_EVENT_KIND_MULTIPLIER, event_kind, "event kind")
    finish_multiplier = _finish_multiplier(position, is_dnf)
    repeat_multiplier = _repeat_multiplier(progress["wins"])
    first_win = not is_dnf and position == 1 and progress["wins"] == 0
    result_xp = round(base_xp * kind_multiplier * finish_multiplier * repeat_multiplier)
    first_win_bonus = (
        round(base_xp * kind_multiplier * TEAM_XP_FIRST_WIN_BONUS_MULTIPLIER)
        if first_win
        else 0
    )
    return TeamXpAward(
        car_class_limit=car_class_limit,
        event_kind=event_kind,
        base_xp=base_xp,
        finish_multiplier=finish_multiplier,
        event_kind_multiplier=kind_multiplier,
        repeat_multiplier=repeat_multiplier,
        first_win=first_win,
        result_xp=result_xp,
        first_win_bonus=first_win_bonus,
        total_xp=result_xp + first_win_bonus,
    )


def _finish_multiplier(position: int, is_dnf: bool) -> float:
    if is_dnf:
        return TEAM_XP_FINISH_MULTIPLIERS["dnf"]
    position = _valid_position(position)
    return TEAM_XP_FINISH_MULTIPLIERS.get(position, TEAM_XP_FINISH_MULTIPLIERS["finish"])


def _repeat_multiplier(wins_before: int) -> float:
    index = max(0, int(wins_before))
    if index >= len(TEAM_XP_REPEAT_MULTIPLIERS):
        return TEAM_XP_REPEAT_MULTIPLIERS[-1]
    return TEAM_XP_REPEAT_MULTIPLIERS[index]


def _valid_position(position: int) -> int:
    position = int(position)
    if position < 1:
        raise ValueError(f"Race position must be 1 or greater: {position}")
    return position


def _value_for_key(mapping: Mapping[Any, Any], key: Any, label: str) -> Any:
    try:
        return mapping[key]
    except KeyError as exc:
        raise ValueError(f"Unknown {label}: {key}") from exc
