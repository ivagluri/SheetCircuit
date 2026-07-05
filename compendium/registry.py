"""Assembled compendium registry — the single object every consumer reads.

Deliberately imports no game-UI code (``game.actions`` imports *this* module in
turn, so a dependency the other way would be circular). The set of tune-menu
fields is reconstructed from ``game.parts`` rather than from
``game.actions._TUNE_FIELD_GROUPS``; a test asserts the two agree.

Exposes:
  CHAPTERS       ordered tuple of every Chapter (index/drill-down source)
  ENTRIES_BY_ID  every Entry keyed by its globally-unique domain-prefixed id
  TUNE_LOOKUP    bare tune-field name -> Entry, for the in-game tune menu
"""

from __future__ import annotations

from compendium import (
    content_cars,
    content_drivers,
    content_events,
    content_intro,
    content_parts,
    content_tracks,
)
from game.parts import TUNE_MENU_FIELD_NAMES
from compendium.model import Chapter, Entry

# Index-page framing (see content_intro).
TITLE: str = content_intro.TITLE
INTRO: str = content_intro.INTRO
HOW_TO_READ: str = content_intro.HOW_TO_READ

CHAPTERS: tuple[Chapter, ...] = (
    content_cars.build_chapter(),
    content_parts.build_chapter(),
    content_drivers.build_chapter(),
    content_tracks.build_chapter(),
    content_events.build_chapter(),
)


def _index_by_id(chapters: tuple[Chapter, ...]) -> dict[str, Entry]:
    index: dict[str, Entry] = {}
    for chapter in chapters:
        for section in chapter.sections:
            for entry in section.entries:
                if entry.id in index:
                    raise AssertionError(f"duplicate compendium entry id: {entry.id!r}")
                index[entry.id] = entry
    return index


ENTRIES_BY_ID: dict[str, Entry] = _index_by_id(CHAPTERS)


def _tune_entry_id(name: str) -> str:
    """Deterministic dotted id for an in-game tune-menu setup field."""
    return f"car.tune.{name}"


def _build_tune_lookup() -> dict[str, Entry]:
    # The tune menu exposes setup-only knobs; hardware/stat changes live in Upgrades.
    names = set(TUNE_MENU_FIELD_NAMES)
    return {name: ENTRIES_BY_ID[_tune_entry_id(name)] for name in sorted(names)}


TUNE_LOOKUP: dict[str, Entry] = _build_tune_lookup()


def entry_for(domain: str, path: tuple[str, ...], *, segment: bool = False) -> Entry | None:
    """Look up an entry by its schema location — used by the creator to surface
    a field's compendium prose at point of use. ``segment=True`` addresses a
    track segment field (id prefix ``track.segment``)."""
    prefix = f"{domain}.segment" if segment else domain
    return ENTRIES_BY_ID.get(f"{prefix}.{'.'.join(path)}")
