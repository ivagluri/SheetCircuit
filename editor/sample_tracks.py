"""Synthetic 'extreme' tracks for the creator's live lap-time panel.

Purpose-built, intrinsic archetypes -- a flat-out drag strip, a stop-and-go hairpin
sequence, a rapid-transition slalom, and sweeping high-speed esses -- so a user can see
how a design copes with each pure demand, not only the real catalog tracks.

Built the same tag-driven way as the class-derivation reference suite
(``game/reference_suite.py``), but kept a separate, editor-only set so tweaking these can
never move a car's class. Each tag carries the dimension weights in
``constants.SEGMENT_TAG_WEIGHTS``; the tags chosen below make each track lean hard on one
demand (power/top-speed, braking+traction, handling, aero+handling-at-speed).
"""
from __future__ import annotations

from game.loader import track_from_dict
from game.models import Track


def _synthetic(track_id: str, name: str, tags: list[str], length_km: float) -> Track:
    n = len(tags)
    segments = [
        {"name": f"s{i}", "length_pct": 1.0 / n, "tags": [tag], "surface": "tarmac", "condition": "dry"}
        for i, tag in enumerate(tags)
    ]
    return track_from_dict(
        {
            "id": track_id, "name": name, "layout_type": "circuit",
            "length_km": length_km, "pit_lane_loss_s": 20.0, "overtake_difficulty": 0.5,
            "surface": "tarmac", "default_condition": "dry", "weather_variability": 0.0,
            "elevation_change_m": 0, "segments": segments,
        }
    )


# Built once at import; order is the cycle order shown in the panel.
SAMPLE_TRACKS: list[Track] = [
    _synthetic("sample_drag", "Drag Strip", ["long_straight", "long_straight"], 2.0),
    _synthetic(
        "sample_hairpins", "Hairpin Sequence",
        ["hard_braking_zone", "slow_corner", "hard_braking_zone", "slow_corner"], 2.4,
    ),
    _synthetic(
        "sample_slalom", "Slalom",
        ["tight_chicane", "technical_section", "tight_chicane", "technical_section"], 2.4,
    ),
    _synthetic(
        "sample_esses", "Long Esses",
        ["high_speed_corner", "technical_section", "high_speed_corner"], 3.0,
    ),
]
