"""Data model for compendium content.

Frozen dataclasses so the assembled registry is effectively immutable at
runtime. All collections are tuples for the same reason (and so the frozen
dataclasses stay hashable).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One documented parameter.

    ``id`` is a globally-unique, domain-prefixed dotted path mirroring the
    field's location in its schema, e.g. ``"car.tune.final_drive"``,
    ``"car.powertrain.power_hp"``, ``"track.segment.length_pct"``,
    ``"event.restr_max_power_hp"``, or the bare stat name for drivers
    (``"driver.pace"``). ``value_range``/``choices`` are harvested from the
    schema; ``ideal``/``effect_summary``/``prose``/``units`` are hand-authored.
    ``prose`` is intentionally sparse — populated only for genuinely
    non-obvious fields; most fields rely on ``effect_summary`` alone.
    """

    id: str
    domain: str  # "car" | "driver" | "track" | "event"
    section: str  # subsystem / chapter subsection, e.g. "Tune", "Driver Stats"
    label: str
    units: str = ""
    value_range: tuple[float | None, float | None] | None = None
    choices: tuple[str, ...] = ()
    ideal: float | str | None = None
    effect_summary: str = ""  # one-liner: table row + inline Help column
    prose: str = ""  # longer "why", sparse — only where genuinely non-obvious
    editable_in: tuple[str, ...] = ()  # subset of {"creator", "tune_menu", "derived"}
    source: str = ""  # dev-only provenance, e.g. "constants.py:537 DIFF_POWER_IDEAL"


@dataclass(frozen=True)
class Section:
    """A subsystem within a chapter — its intro paragraph plus field entries."""

    title: str
    intro: str = ""
    entries: tuple[Entry, ...] = ()


@dataclass(frozen=True)
class Chapter:
    """A domain: Cars / Drivers / Tracks / Events."""

    id: str  # "cars" | "drivers" | "tracks" | "events"
    title: str
    intro: str = ""
    sections: tuple[Section, ...] = ()
