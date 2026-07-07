"""Shared helper: turn an ``editor.fields.FieldSpec`` into a compendium
``Entry``, pulling range/choices from the spec and prose/ideal/units from a
hand-authored table.

The authored table is keyed by the full (domain-prefixed) ``Entry.id`` so a
single flat dict per content module is unambiguous. Fields absent from the
table simply get empty prose — that is expected during scaffolding (Phase 2)
and for the many fields whose table row is self-explanatory.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from compendium.model import Entry


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def entry_from_spec(
    spec,
    *,
    domain: str,
    section_title: str,
    id_prefix: str,
    editable_in: tuple[str, ...],
    authored: Mapping[str, Mapping[str, Any]],
) -> Entry:
    dotted = ".".join(spec.path)
    entry_id = f"{id_prefix}.{dotted}"
    value_range: tuple[float | None, float | None] | None = None
    if spec.minimum is not None or spec.maximum is not None:
        value_range = (spec.minimum, spec.maximum)
    fields = authored.get(entry_id, {})
    return Entry(
        id=entry_id,
        domain=domain,
        section=section_title,
        label=spec.label,
        units=fields.get("units", ""),
        value_range=value_range,
        choices=tuple(spec.choices),
        ideal=fields.get("ideal"),
        effect_summary=fields.get("effect", ""),
        prose=fields.get("prose", ""),
        editable_in=editable_in,
        source=fields.get("source", ""),
    )
