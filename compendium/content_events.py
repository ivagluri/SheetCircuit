"""Events chapter.

Harvests the flattened event draft fields from ``editor.fields.EVENT_SECTIONS``
(Event / Race Length / Restrictions). These are all creator-authored; there is
no in-game event editor. The draft carries ``race_mode``/``race_value`` and
``restr_*`` knobs which ``editor.app`` translates to the stored event JSON —
the compendium documents the draft-level knobs the user actually sets.
"""

from __future__ import annotations

from typing import Any

from editor.fields import EVENT_SECTIONS
from compendium.harvest import entry_from_spec
from compendium.model import Chapter, Section

DOMAIN = "event"
_EDITABLE = ("creator",)

CHAPTER_INTRO: str = ""
SECTION_INTROS: dict[str, str] = {}
FIELD_CONTENT: dict[str, dict[str, Any]] = {}


def build_chapter() -> Chapter:
    sections: list[Section] = []
    for section in EVENT_SECTIONS:
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
    return Chapter(id="events", title="Events", intro=CHAPTER_INTRO, sections=tuple(sections))
