"""Build-verification for the static compendium page (the globs=None target)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import build_web
from compendium import registry
from compendium.render_html import render_compendium


class CompendiumRenderTests(unittest.TestCase):
    def test_render_covers_every_chapter_and_appendix(self) -> None:
        html = render_compendium()
        for chapter in registry.CHAPTERS:
            self.assertIn(f'id="chap-{chapter.id}"', html)
        self.assertIn('id="chap-appendix"', html)
        # every documented field is a filterable row (main tables + appendix)
        self.assertGreaterEqual(html.count('class="doc-row"'), len(registry.ENTRIES_BY_ID))

    def test_render_is_escaped(self) -> None:
        # The '&' in "Identity & Layout" must be HTML-escaped, not raw.
        html = render_compendium()
        self.assertIn("Identity &amp; Layout", html)
        self.assertNotIn("Identity & Layout", html)


class CompendiumBuildTests(unittest.TestCase):
    def test_build_writes_self_contained_static_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = build_web.build("compendium", Path(tmp) / "compendium.html")
            self.assertTrue(output.exists())
            text = output.read_text(encoding="utf-8")
        self.assertNotIn(build_web.PLACEHOLDER, text)
        self.assertGreater(len(text), 10_000)
        self.assertIn("SheetCircuit Compendium", text)
        self.assertIn('id="filter"', text)  # the JS filter box
        self.assertIn("doc-row", text)
        # a static page must not carry the Pyodide runtime.
        self.assertNotIn("pyodide", text.lower())


if __name__ == "__main__":
    unittest.main()
