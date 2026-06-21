"""Intrinsic reference fixtures for runtime car-class derivation.

A car's class is computed on the fly from its capability on a small, FIXED suite of
archetype tracks -- a drag run (power), a slalom (technical), and a hybrid of the two --
never from a stored label or the loaded track catalog. This keeps class a property of the
car alone: a custom/creator car gets a real class with nothing to look up and nothing to
go stale (the same de-pin principle the orphan-stat references follow).

The fixtures' geometry (length, derived base lap time) is irrelevant here -- class reads
the capability *composite* (a base_lap_time-independent weighted sum of the car's effective
axes for that archetype's tag mix), so the race-pace tuning (PERF_SCALE etc.) does not
move the tiers.
"""
from __future__ import annotations

from game.loader import track_from_dict
from game.models import EffectiveCarStats, Track


def _fixture(fixture_id: str, tags: list[str]) -> Track:
    n = len(tags)
    segments = [
        {"name": f"s{i}", "length_pct": 1.0 / n, "tags": [tag], "surface": "tarmac", "condition": "dry"}
        for i, tag in enumerate(tags)
    ]
    return track_from_dict(
        {
            "id": fixture_id, "name": fixture_id, "layout_type": "circuit",
            "laps": 1, "length_km": 3.0, "pit_lane_loss_s": 20.0,
            "overtake_difficulty": 0.5, "surface": "tarmac", "default_condition": "dry",
            "weather_variability": 0.0, "elevation_change_m": 10, "segments": segments,
        }
    )


# Built once at import. Insertion order is stable, so shape reads are deterministic.
REFERENCE_FIXTURES: dict[str, Track] = {
    "power": _fixture("ref_drag", ["long_straight", "long_straight"]),
    "technical": _fixture("ref_slalom", ["tight_chicane", "technical_section"]),
    "hybrid": _fixture("ref_hybrid", ["long_straight", "technical_section", "slow_corner"]),
}


def archetype_capabilities(effective: EffectiveCarStats) -> dict[str, float]:
    """The car's capability composite on each archetype fixture (higher = more capable)."""
    # Lazy import: simulation imports effective_stats, which imports this module lazily.
    from game.simulation import _track_composite

    return {name: _track_composite(effective, track) for name, track in REFERENCE_FIXTURES.items()}


def mean_capability(effective: EffectiveCarStats) -> float:
    """Mean capability across the suite -- the scalar a car's tier is bracketed from."""
    caps = archetype_capabilities(effective)
    return sum(caps.values()) / len(caps)
