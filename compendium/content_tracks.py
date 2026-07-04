"""Tracks chapter.

Harvests the top-level track fields from ``editor.fields.TRACK_SECTIONS`` and
the per-segment fields from ``SEGMENT_FIELDS`` (which the creator edits in a
dedicated list screen, not as flat fields) into a synthesised "Segments"
section. Segment entry ids are prefixed ``track.segment.`` so they never
collide with same-named top-level fields (e.g. ``surface``).

A hand-built "Derived Values" section documents what the loader computes for
you (base lap time, aggregate weights, wear/fuel/heat rates, climb gradient) so
authors understand the consequences of their choices without treating those
outputs as edit points.
"""

from __future__ import annotations

from typing import Any

from constants import (
    OVERTAKE_DIFFICULTY_TAG_DELTA,
    SEGMENT_TAG_RATES,
    SEGMENT_TAG_SPEED,
    SEGMENT_TAG_WEIGHTS,
)
from editor.fields import SEGMENT_FIELDS, TRACK_SECTIONS
from compendium.harvest import entry_from_spec
from compendium.model import Chapter, Entry, Section

DOMAIN = "track"
_EDITABLE = ("creator",)
_SEGMENT_SECTION = "Segments"
_TAGS_SECTION = "Segment Tags"
_DERIVED_SECTION = "Derived Values"

CHAPTER_INTRO: str = (
    "A track is a lap built from segments. You set its overall shape — length, layout, "
    "surface, weather — then divide the lap into segments whose tags describe what each "
    "part demands of the car. Race length is NOT set here: one track can host a 5-lap "
    "sprint or a long enduro, and that lives on the event. From your segments the loader "
    "derives a reference lap time, the performance emphasis, and per-lap wear/fuel/heat; "
    "those derived values are explained below but are not directly editable. For a worked "
    "example that exercises every field, tag, surface and condition, see the shipped "
    "reference track data/tracks/summit_ridge_gp.json (its 'description' field is "
    "documentation only)."
)

SECTION_INTROS: dict[str, str] = {
    "Identity & Layout": (
        "The track's overall character. Length sets one lap; layout decides whether the "
        "track loops or runs once; surface, condition and weather set the default grip "
        "environment that individual segments can override."
    ),
    _SEGMENT_SECTION: (
        "The lap is divided into segments whose length fractions must sum to exactly 1.0. "
        "Each segment's tags are the real design tool: they decide what that stretch "
        "demands (power, grip, braking, handling, aero...) and how hard it is on tyres, "
        "fuel and engine heat. Surface and condition can be set per segment to make part "
        "of the lap gravel or wet. See the Segment Tags section for each tag's effect."
    ),
    _TAGS_SECTION: (
        "The heart of the lap-time model. Each tag sets a baseline speed for the stretch "
        "(a straight is fast, a chicane is slow) and layers demands onto specific car "
        "axes — so a track built from long straights rewards a different car than one full "
        "of slow corners. Tags also drive tyre wear, fuel burn and engine heat. Stack "
        "several on one segment to describe a complex piece of road. The figures below are "
        "read straight from the simulation's own tables."
    ),
    _DERIVED_SECTION: (
        "What the loader computes from your design when the track is loaded — never stored "
        "and never edited directly. They are listed so you can see how your segment choices "
        "translate into lap time, car emphasis, and consumables."
    ),
}

FIELD_CONTENT: dict[str, dict[str, Any]] = {
    # --- Identity & Layout ---
    "track.id": {"effect": "Filename slug identifying the track; also how events reference it."},
    "track.name": {"effect": "Display name shown across menus and results."},
    "track.layout_type": {"effect": "circuit/oval loop the lap; point_to_point, hillclimb and sprint run once (and use net climb)."},
    "track.length_km": {"effect": "Length of ONE lap; total race distance is set per-event.", "units": "km"},
    "track.pit_lane_loss_s": {"effect": "Time lost each time a car pits.", "units": "s"},
    "track.elevation_change_m": {"effect": "Net elevation change; sustained climb taxes fuel and engine heat.", "units": "m", "source": "constants.py:519 ELEVATION_REF_M"},
    "track.surface": {"effect": "Default surface; gravel cuts grip and raises tyre wear. Segments can override.", "source": "constants.py:722 SURFACE_MODIFIERS"},
    "track.default_condition": {"effect": "Default condition; damp/wet cut grip and lean on wet grip and wet skill.", "source": "constants.py:728 CONDITION_MODIFIERS"},
    "track.weather_variability": {"effect": "0..1 chance the pre-race forecast shifts the track's condition."},
    "track.overtake_difficulty": {"effect": "0..1 base difficulty of passing; narrow/wide segment tags nudge it.", "source": "constants.py:692 OVERTAKE_DIFFICULTY_TAG_DELTA"},
    # --- Segments ---
    "track.segment.name": {"effect": "Label for the segment; flavour only."},
    "track.segment.length_pct": {"effect": "Fraction of the lap this segment covers; all segments must sum to 1.0.", "units": "fraction"},
    "track.segment.tags": {
        "effect": "Multi-select demands (12 tags) that set the segment's speed, performance weights and wear/fuel/heat.",
        "prose": (
            "The single most important design choice for a segment. Each tag is broken down individually "
            "in the Segment Tags section — what it rewards, its baseline speed, and its consumable load. "
            "Stack several tags to describe a complex stretch of road."
        ),
        "source": "constants.py:662 SEGMENT_TAG_WEIGHTS / :677 SEGMENT_TAG_RATES / :105 SEGMENT_TAG_SPEED",
    },
    "track.segment.surface": {"effect": "Per-segment surface override (tarmac/concrete/gravel)."},
    "track.segment.condition": {"effect": "Per-segment condition override (dry/damp/wet)."},
}

# Hand-built derived-value entries (no FieldSpec — these are loader outputs).
_DERIVED_ENTRIES: tuple[dict[str, Any], ...] = (
    {"id": "track.derived.base_lap_time", "label": "base_lap_time", "units": "s",
     "effect": "Reference lap time the loader computes from segment speed factors and lap length; never stored.",
     "source": "game/loader.py:317 derive_base_lap_time"},
    {"id": "track.derived.performance_weights", "label": "performance emphasis",
     "effect": "Aggregate power/accel/top-speed/grip/braking/handling/aero emphasis, summed from segment tags.",
     "source": "game/loader.py:245 derive_weights"},
    {"id": "track.derived.consumable_rates", "label": "wear / fuel / heat rates",
     "effect": "Per-lap tyre-wear, fuel-burn and engine-heat demand from segment tags, scaled by elevation.",
     "source": "game/loader.py:254 derive_rates; constants.py:677 SEGMENT_TAG_RATES"},
    {"id": "track.derived.climb_gradient_pct", "label": "climb_gradient_pct", "units": "%",
     "effect": "Net climb grade adding a time penalty on point_to_point/hillclimb/sprint layouts.",
     "source": "game/loader.py:372; constants.py:135 NET_CLIMB_LAYOUTS"},
)


# --- Segment tags: one entry each, derived from the sim's own tables ---------
_AXIS_LABEL = {
    "power": "power",
    "top_speed": "top speed",
    "acceleration": "acceleration",
    "grip": "grip",
    "braking": "braking",
    "handling": "handling",
    "aero": "aero",
}

# Hand-written "what this stretch of road is" — the human read on each tag.
_TAG_PROSE: dict[str, str] = {
    "long_straight": "A flat-out straight: engine power and top speed decide everything, and it drinks fuel and heat while doing it.",
    "short_straight": "A brief squirt between corners — acceleration off the preceding corner matters more than outright top speed.",
    "high_speed_corner": "A fast sweeper taken near-flat: aerodynamic downforce keeps the car planted, so aero-heavy cars gain the most.",
    "slow_corner": "A tight, low-speed corner where mechanical grip and the ability to get back on the power dominate.",
    "hard_braking_zone": "A heavy stop from speed: braking performance (and brake cooling over a stint) is the limiting factor.",
    "technical_section": "A flowing, connected sequence that rewards handling and balance over raw power.",
    "tight_chicane": "A slow, sharp direction change — quick handling response plus strong braking to scrub speed.",
    "bumpy_surface": "Broken tarmac that upsets the car; compliant handling helps, and the surface chews through tyres.",
    "curb_riding": "Kerbs to attack or ride out; composure over kerbs keeps the lap tidy.",
    "narrow_track": "Little room and few passing spots — handling matters and overtaking is harder here (raises the track's overtake difficulty).",
    "wide_track": "Generous width with room to run side by side, which makes overtaking easier (lowers overtake difficulty).",
    "exposed": "Open to the elements: a touch aero-sensitive and the most affected when the weather turns.",
}


def _tag_emphasis(tag: str) -> str:
    weights = SEGMENT_TAG_WEIGHTS[tag]
    peak = max(weights.values())
    strong = [axis for axis, weight in weights.items() if weight >= 0.5]
    chosen = strong or [axis for axis, weight in weights.items() if weight == peak]
    chosen.sort(key=lambda axis: weights[axis], reverse=True)
    return ", ".join(_AXIS_LABEL[axis] for axis in chosen)


def _tag_effect(tag: str) -> str:
    speed = SEGMENT_TAG_SPEED[tag]
    speed_word = "Fast" if speed >= 1.3 else "Slow" if speed <= 0.7 else "Medium-speed"
    rates = SEGMENT_TAG_RATES[tag]
    heavy = []
    if rates["tire_wear"] >= 0.7:
        heavy.append("hard on tyres")
    if rates["fuel_burn"] >= 0.7:
        heavy.append("thirsty")
    if rates["engine_heat"] >= 0.7:
        heavy.append("runs hot")
    consumables = " and ".join(heavy) if heavy else "easy on consumables"
    return f"{speed_word} (speed ×{speed:g}); rewards {_tag_emphasis(tag)}; {consumables}."


def _tags_section() -> Section:
    entries = tuple(
        Entry(
            id=f"{DOMAIN}.tag.{tag}",
            domain=DOMAIN,
            section=_TAGS_SECTION,
            label=tag,
            effect_summary=_tag_effect(tag),
            prose=_TAG_PROSE.get(tag, ""),
            editable_in=_EDITABLE,
            source="constants.py SEGMENT_TAG_SPEED / _WEIGHTS / _RATES"
            + (" / OVERTAKE_DIFFICULTY_TAG_DELTA" if tag in OVERTAKE_DIFFICULTY_TAG_DELTA else ""),
        )
        for tag in SEGMENT_TAG_WEIGHTS
    )
    return Section(title=_TAGS_SECTION, intro=SECTION_INTROS[_TAGS_SECTION], entries=entries)


def _derived_section() -> Section:
    entries = tuple(
        Entry(
            id=item["id"],
            domain=DOMAIN,
            section=_DERIVED_SECTION,
            label=item["label"],
            units=item.get("units", ""),
            effect_summary=item["effect"],
            editable_in=("derived",),
            source=item.get("source", ""),
        )
        for item in _DERIVED_ENTRIES
    )
    return Section(title=_DERIVED_SECTION, intro=SECTION_INTROS[_DERIVED_SECTION], entries=entries)


def build_chapter() -> Chapter:
    sections: list[Section] = []
    for section in TRACK_SECTIONS:
        entries = tuple(
            entry_from_spec(
                spec,
                domain=DOMAIN,
                section_title=section.title,
                id_prefix=DOMAIN,
                editable_in=_EDITABLE,
                authored=FIELD_CONTENT,
            )
            for spec in section.fields
        )
        sections.append(
            Section(title=section.title, intro=SECTION_INTROS.get(section.title, ""), entries=entries)
        )
    segment_entries = tuple(
        entry_from_spec(
            spec,
            domain=DOMAIN,
            section_title=_SEGMENT_SECTION,
            id_prefix=f"{DOMAIN}.segment",
            editable_in=_EDITABLE,
            authored=FIELD_CONTENT,
        )
        for spec in SEGMENT_FIELDS
    )
    sections.append(
        Section(title=_SEGMENT_SECTION, intro=SECTION_INTROS[_SEGMENT_SECTION], entries=segment_entries)
    )
    sections.append(_tags_section())
    sections.append(_derived_section())
    return Chapter(id="tracks", title="Tracks", intro=CHAPTER_INTRO, sections=tuple(sections))
