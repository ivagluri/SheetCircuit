"""Drivers chapter.

Unlike cars/tracks/events there is no creator schema to harvest from, so every
field entry is hand-built here, one per field of the ``Driver`` dataclass
(``game/models.py``). Drivers are procedurally generated into a rotating
free-agent market you scout and hire from; their stats then develop through race
XP up to a per-driver potential ceiling. A Presets section documents the intrinsic
archetypes the generator draws from. The ``source`` notes cite the mechanic each
stat actually drives, for maintainers; they are not shown to players.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

from constants import DRIVER_ARCHETYPES, DRIVER_STAT_CAP
from game.models import Driver
from compendium.harvest import slug
from compendium.model import Chapter, Entry, Section

DOMAIN = "driver"
_EDITABLE = ("derived",)  # not player-editable; generated/hired, stats grow via XP
_SKILL_RANGE = (0, DRIVER_STAT_CAP)
_ARCHETYPE_SECTION = "Archetypes (Market)"

CHAPTER_INTRO: str = (
    "Drivers are not built in an editor — you scout and hire them from a rotating "
    "free-agent market. Skills sit on a 0-99 scale. After each race a driver banks "
    "experience, and every so often that XP raises whichever of their progression "
    "skills is currently lowest — up to their personal potential ceiling, and never "
    "past the 99 cap. Two traits — feedback and aggression — are fixed personality and "
    "never change. The market refreshes every few weeks: a cheap rookie with a high "
    "potential can grow into a star, while a finished veteran is already near their "
    "ceiling. Every row here is read-only; the value is in knowing what to look for "
    "when signing a driver and how they will grow."
)

SECTION_INTROS: dict[str, str] = {
    _ARCHETYPE_SECTION: (
        "How the market is stocked. Every generated free agent is rolled from one of "
        "these intrinsic archetypes — a skill band, a personality bias, and how much "
        "room they have to grow into their potential. They are design templates, not "
        "copies of the hand-authored starting drivers."
    ),
    "Identity": "Who the driver is. Labels only — no performance effect.",
    "Skills": (
        "The eight ability ratings. Six of them (pace, consistency, racecraft, fitness, "
        "mechanical sympathy, wet skill) improve through race XP; feedback and aggression "
        "are fixed personality traits that never move."
    ),
    "Career": "Cost and progression bookkeeping: what the driver is paid and how they level up.",
}

# id -> content. required: label, section, effect. optional: prose, units, value_range, source.
_STATS: dict[str, dict[str, Any]] = {
    "id": {"section": "Identity", "label": "id", "effect": "Roster slug identifying the driver in data and saves."},
    "name": {"section": "Identity", "label": "name", "effect": "Display name shown across menus and results."},
    "pace": {
        "section": "Skills", "label": "pace", "value_range": _SKILL_RANGE,
        "effect": "Raw speed — a direct lap-time bonus, the single biggest driver stat.",
        "source": "constants.py:145 DRIVER_PACE_FRACTION; game/simulation.py:113",
    },
    "consistency": {
        "section": "Skills", "label": "consistency", "value_range": _SKILL_RANGE,
        "effect": "Steadiness — fewer mistakes and a lower chance of throwing a race away.",
        "source": "constants.py:276 MISTAKE_CONSISTENCY_SCALE; game/telemetry.py:67",
    },
    "racecraft": {
        "section": "Skills", "label": "racecraft", "value_range": _SKILL_RANGE,
        "effect": "Wheel-to-wheel skill — the edge that wins and defends overtakes.",
        "source": "constants.py:713 OVERTAKE_RACECRAFT_PER_POINT; game/race_session.py:431",
    },
    "feedback": {
        "section": "Skills", "label": "feedback", "value_range": _SKILL_RANGE,
        "effect": "Quality of the setup/telemetry read-outs the driver gives you; a fixed trait.",
        "prose": (
            "Feedback gates how useful the driver's in-race commentary is: below ~50 it is vague, above "
            "~75 it is genuinely informative. It never improves with experience — it is part of who the "
            "driver is."
        ),
        "source": "constants.py:389-390 LOW/HIGH_FEEDBACK_THRESHOLD; game/telemetry.py:99",
    },
    "fitness": {
        "section": "Skills", "label": "fitness", "value_range": _SKILL_RANGE,
        "effect": "Stamina — drains energy and focus more slowly over a long race.",
        "source": "constants.py:556-557 FITNESS_REF / FITNESS_DRAIN_PER_UNIT",
    },
    "aggression": {
        "section": "Skills", "label": "aggression", "value_range": _SKILL_RANGE,
        "effect": "Appetite for risk — raises mistake rate; a fixed personality trait.",
        "prose": (
            "Aggression is double-edged and, like feedback, fixed for life. It lifts mistake risk, so a "
            "hot-headed driver needs matching consistency to stay clean."
        ),
        "source": "constants.py:275 MISTAKE_AGGRESSION_SCALE; game/telemetry.py:66",
    },
    "mechanical_sympathy": {
        "section": "Skills", "label": "mechanical_sympathy", "value_range": _SKILL_RANGE,
        "effect": "Kindness to the car — lowers the risk of mechanical failure.",
        "source": "constants.py:287 FAILURE_SYMPATHY_SCALE; game/telemetry.py:86",
    },
    "wet_skill": {
        "section": "Skills", "label": "wet_skill", "value_range": _SKILL_RANGE,
        "effect": "Wet-weather pace — blended into pace on damp and wet segments.",
        "source": "game/simulation.py:199 _blended_pace; constants.py:727-731 CONDITION_MODIFIERS",
    },
    "salary": {
        "section": "Career", "label": "salary", "units": "$",
        "effect": "Hire fee — the one-off cost to sign them, scaling with ability and potential.",
        "prose": (
            "For generated free agents the fee is computed from current ability (super-linearly) plus a "
            "premium for potential headroom, so a promising rookie is never a free pickup. Optional weekly "
            "upkeep exists but is disabled by default."
        ),
        "source": "game/driver_gen.py compute_salary; constants.py SALARY_* ; upkeep constants.py:328-331 SALARY_WEEKLY_*",
    },
    "experience": {
        "section": "Career", "label": "experience", "units": "XP",
        "effect": "Banked race XP: +10 per race, and every 50 XP raises the lowest progression skill (cap 99).",
        "prose": (
            "Progression is automatic and targets weaknesses: the six progression skills (pace, "
            "consistency, racecraft, fitness, mechanical sympathy, wet skill) improve one point at a time, "
            "always lifting whichever is currently lowest, until each hits the 99 cap. Feedback and "
            "aggression are excluded."
        ),
        "source": "constants.py:146-148 DRIVER_XP_*; game/race_session.py:407-423",
    },
    "potential": {
        "section": "Career", "label": "potential", "value_range": _SKILL_RANGE,
        "effect": "Development ceiling — XP progression cannot raise any skill past this value.",
        "prose": (
            "Potential is a single number showing how high this driver's skills can ultimately climb. A "
            "rookie may sit well below their potential and grow into it over many races; a veteran is often "
            "already at their ceiling. It caps growth only — it never lowers a stat — and a driver whose "
            "current skills already exceed a low potential simply stops improving."
        ),
        "source": "game/models.py Driver.potential; game/race_session.py:407-423 _apply_driver_progression",
    },
}

_SECTION_ORDER = ("Identity", "Skills", "Career")


def _archetype_section() -> Section:
    entries = tuple(
        Entry(
            id=f"{DOMAIN}.archetype.{slug(name)}",
            domain=DOMAIN,
            section=_ARCHETYPE_SECTION,
            label=name,
            effect_summary=description,
            editable_in=_EDITABLE,
            source="constants.py DRIVER_ARCHETYPES; game/driver_gen.py generate_from_archetype",
        )
        for name, description, _spec in DRIVER_ARCHETYPES
    )
    return Section(title=_ARCHETYPE_SECTION, intro=SECTION_INTROS[_ARCHETYPE_SECTION], entries=entries)


def build_chapter() -> Chapter:
    # Guard: every Driver dataclass field must be documented (mirrors the test,
    # but fails fast at import if someone adds a stat without an entry).
    field_names = [f.name for f in dataclass_fields(Driver)]
    missing = [n for n in field_names if n not in _STATS]
    if missing:
        raise AssertionError(f"undocumented Driver fields: {missing}")

    sections: list[Section] = [_archetype_section()]
    for section_title in _SECTION_ORDER:
        entries = tuple(
            Entry(
                id=f"{DOMAIN}.{name}",
                domain=DOMAIN,
                section=section_title,
                label=content["label"],
                units=content.get("units", ""),
                value_range=content.get("value_range"),
                effect_summary=content["effect"],
                prose=content.get("prose", ""),
                editable_in=_EDITABLE,
                source=content.get("source", ""),
            )
            for name in field_names
            for content in [_STATS[name]]
            if content["section"] == section_title
        )
        sections.append(Section(title=section_title, intro=SECTION_INTROS[section_title], entries=entries))
    return Chapter(id="drivers", title="Drivers", intro=CHAPTER_INTRO, sections=tuple(sections))
