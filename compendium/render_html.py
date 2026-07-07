"""Render the compendium registry to a self-contained static HTML fragment.

Pure stdlib (no game runtime, no Pyodide): the output is inserted into
``tools/compendium_template.html`` by ``tools/build_web.py`` to produce
``web/compendium.html``. Every field row and prose block carries a lowercased
``data-text`` attribute so the template's vanilla-JS filter box can show/hide
by substring. Formatting mirrors the in-game ``compendium_screen`` columns but
is reimplemented here to keep this module decoupled from ``game.actions``.
"""

from __future__ import annotations

import re
from html import escape

from compendium import registry
from compendium.format import entry_editable, entry_ideal, entry_range
from compendium.model import Chapter, Entry, Section

_COLUMNS = ["Field", "Range", "Units", "Ideal", "Effect", "Editable"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _entry_text(entry: Entry) -> str:
    parts = [entry.label, entry.effect_summary, entry.prose, entry_editable(entry), entry_range(entry), entry.units]
    return " ".join(part for part in parts if part).lower()


def _field_table(entries: tuple[Entry, ...]) -> str:
    head = "".join(f"<th>{escape(col)}</th>" for col in _COLUMNS)
    rows = []
    for entry in entries:
        cells = [
            f'<td class="field">{escape(entry.label)}</td>',
            f"<td>{escape(entry_range(entry))}</td>",
            f"<td>{escape(entry.units) or '—'}</td>",
            f"<td>{escape(entry_ideal(entry))}</td>",
            f'<td class="effect">{escape(entry.effect_summary)}</td>',
            f"<td>{escape(entry_editable(entry))}</td>",
        ]
        rows.append(f'<tr class="doc-row" data-text="{escape(_entry_text(entry))}">{"".join(cells)}</tr>')
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _prose_block(entries: tuple[Entry, ...]) -> str:
    notes = [
        f'<p class="doc-row prose" data-text="{escape(_entry_text(entry))}">'
        f"<b>{escape(entry.label)}</b> — {escape(entry.prose)}</p>"
        for entry in entries
        if entry.prose
    ]
    return f'<div class="notes">{"".join(notes)}</div>' if notes else ""


def _section_html(chapter: Chapter, section: Section) -> str:
    anchor = f"{chapter.id}-{_slug(section.title)}"
    intro = f'<p class="section-intro">{escape(section.intro)}</p>' if section.intro else ""
    return (
        f'<section class="doc-section" id="{anchor}">'
        f"<h3>{escape(section.title)}</h3>{intro}"
        f"{_field_table(section.entries)}{_prose_block(section.entries)}"
        "</section>"
    )


def _chapter_html(chapter: Chapter) -> str:
    intro = f'<p class="chapter-intro">{escape(chapter.intro)}</p>' if chapter.intro else ""
    sections = "".join(_section_html(chapter, section) for section in chapter.sections)
    return (
        f'<section class="doc-chapter" id="chap-{chapter.id}">'
        f"<h2>{escape(chapter.title)}</h2>{intro}{sections}"
        "</section>"
    )


def _appendix_html() -> str:
    """Compact quick-reference: one Field/Range/Ideal/Effect table per domain."""
    blocks = []
    for chapter in registry.CHAPTERS:
        entries = tuple(entry for section in chapter.sections for entry in section.entries)
        head = "".join(f"<th>{col}</th>" for col in ("Field", "Range", "Ideal", "Effect"))
        rows = []
        for entry in entries:
            rows.append(
                f'<tr class="doc-row" data-text="{escape(_entry_text(entry))}">'
                f'<td class="field">{escape(entry.label)}</td>'
                f"<td>{escape(entry_range(entry))}</td>"
                f"<td>{escape(entry_ideal(entry))}</td>"
                f'<td class="effect">{escape(entry.effect_summary)}</td></tr>'
            )
        blocks.append(
            f'<section class="doc-section" id="appendix-{chapter.id}">'
            f"<h3>{escape(chapter.title)}</h3>"
            f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            "</section>"
        )
    return (
        '<section class="doc-chapter" id="chap-appendix">'
        "<h2>Appendix — quick reference</h2>"
        '<p class="chapter-intro">Every field again, condensed to one row each, grouped by domain.</p>'
        f'{"".join(blocks)}</section>'
    )


def _toc_html() -> str:
    links = [f'<a href="#chap-{chapter.id}">{escape(chapter.title)}</a>' for chapter in registry.CHAPTERS]
    links.append('<a href="#chap-appendix">Appendix</a>')
    return f'<nav class="toc">{"".join(links)}</nav>'


def render_compendium() -> str:
    intro = (
        f'<div class="intro"><p>{escape(registry.INTRO)}</p>'
        f"<p>{escape(registry.HOW_TO_READ)}</p></div>"
    )
    chapters = "".join(_chapter_html(chapter) for chapter in registry.CHAPTERS)
    return intro + _toc_html() + chapters + _appendix_html()
