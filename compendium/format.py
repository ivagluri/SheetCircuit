"""Shared formatting for compendium entry columns.

Used by both the in-game ``compendium_screen`` (``game.actions``) and the
static HTML renderer (``compendium.render_html``) so the Range/Ideal/Editable
columns stay identical across surfaces. Pure stdlib — no game runtime imports,
so it is safe for the decoupled HTML renderer to use.
"""

from __future__ import annotations

from compendium.model import Entry

EDITABLE_LABEL = {"creator": "creator", "tune_menu": "tune menu", "upgrades": "upgrades", "derived": "read-only"}


def entry_range(entry: Entry) -> str:
    if entry.choices:
        return ", ".join(entry.choices)
    if entry.value_range is None:
        return "—"
    low, high = entry.value_range
    low_text = "…" if low is None else f"{low:g}"
    high_text = "…" if high is None else f"{high:g}"
    return f"{low_text}–{high_text}"


def entry_ideal(entry: Entry, empty: str = "—") -> str:
    if entry.ideal is None:
        return empty
    return f"{entry.ideal:g}" if isinstance(entry.ideal, float) else str(entry.ideal)


def entry_editable(entry: Entry) -> str:
    if not entry.editable_in:
        return "—"
    return ", ".join(EDITABLE_LABEL.get(tag, tag) for tag in entry.editable_in)
