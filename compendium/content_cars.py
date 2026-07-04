"""Cars chapter.

Harvests every car field from ``editor.fields.CAR_SECTIONS`` (skipping the
curated "Basics" front-door section, which only re-lists paths owned by the
detailed sections below it). Ranges/choices come straight from the schema;
per-subsystem intros and per-field prose/ideal/effect live in the authored
tables below.

The ``editable_in`` tag is derived, not hand-maintained: a car field is
tune-menu-editable iff it is a TuneSetup knob (a key of the schema's "Tune"
section) or a garage hard-mod (a key of ``CAR_MOD_FIELD_SECTIONS``) — exactly
the union that ``game.actions._TUNE_FIELD_GROUPS`` exposes in-game. Everything
in the creator schema is creator-editable.
"""

from __future__ import annotations

from typing import Any

from constants import CAR_MOD_FIELD_SECTIONS
from editor.fields import CAR_SECTIONS
from compendium.harvest import entry_from_spec
from compendium.model import Chapter, Section

DOMAIN = "car"
_SKIP_SECTIONS = {"Basics"}


def _tune_section_keys() -> tuple[str, ...]:
    """The 22 TuneSetup knobs, read from the creator schema's Tune section."""
    tune = next(s for s in CAR_SECTIONS if s.title == "Tune")
    return tuple(spec.key for spec in tune.fields)


TUNE_SECTION_KEYS: tuple[str, ...] = _tune_section_keys()
_TUNE_MENU_KEYS = set(TUNE_SECTION_KEYS) | set(CAR_MOD_FIELD_SECTIONS)


def _editable_in(spec) -> tuple[str, ...]:
    tags = ["creator"]
    if spec.key in _TUNE_MENU_KEYS:
        tags.append("tune_menu")
    return tuple(tags)


# --- Authored content (Phase 3a fills these in) ------------------------------
# chapter-level intro paragraph
CHAPTER_INTRO: str = ""

# per-subsystem intro paragraphs, keyed by Section.title
SECTION_INTROS: dict[str, str] = {}

# per-field authored content, keyed by full Entry.id:
#   {"effect": "...", "prose": "...", "ideal": <num|str>, "units": "...", "source": "..."}
FIELD_CONTENT: dict[str, dict[str, Any]] = {}


def build_chapter() -> Chapter:
    sections: list[Section] = []
    for section in CAR_SECTIONS:
        if section.title in _SKIP_SECTIONS:
            continue
        entries = tuple(
            entry_from_spec(
                spec,
                domain=DOMAIN,
                section_title=section.title,
                id_prefix=DOMAIN,
                editable_in=_editable_in(spec),
                authored=FIELD_CONTENT,
            )
            for spec in section.fields
        )
        sections.append(
            Section(title=section.title, intro=SECTION_INTROS.get(section.title, ""), entries=entries)
        )
    return Chapter(id="cars", title="Cars", intro=CHAPTER_INTRO, sections=tuple(sections))
