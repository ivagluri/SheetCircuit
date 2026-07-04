"""Tracks chapter.

Harvests the top-level track fields from ``editor.fields.TRACK_SECTIONS`` and
the per-segment fields from ``SEGMENT_FIELDS`` (which the creator edits in a
dedicated list screen, not as flat fields) into a synthesised "Segments"
section. Segment entry ids are prefixed ``track.segment.`` so they never
collide with same-named top-level fields (e.g. ``surface``).

A "what the loader derives for you" section (base lap time, aggregate weights,
wear/fuel/heat rates, climb gradient) is authored in Phase 3c as ``derived``
entries — those have no FieldSpec to harvest and are added directly.
"""

from __future__ import annotations

from typing import Any

from editor.fields import SEGMENT_FIELDS, TRACK_SECTIONS
from compendium.harvest import entry_from_spec
from compendium.model import Chapter, Section

DOMAIN = "track"
_EDITABLE = ("creator",)
_SEGMENT_SECTION = "Segments"

CHAPTER_INTRO: str = ""
SECTION_INTROS: dict[str, str] = {}
FIELD_CONTENT: dict[str, dict[str, Any]] = {}


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
        Section(
            title=_SEGMENT_SECTION,
            intro=SECTION_INTROS.get(_SEGMENT_SECTION, ""),
            entries=segment_entries,
        )
    )
    return Chapter(id="tracks", title="Tracks", intro=CHAPTER_INTRO, sections=tuple(sections))
