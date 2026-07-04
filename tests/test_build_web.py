"""Build-verification for the static compendium page (the globs=None target)."""

from __future__ import annotations

import os
import subprocess
import sys
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


class EmbeddedSourceTests(unittest.TestCase):
    def test_game_and_creator_bundles_embed_compendium(self) -> None:
        # game.actions and the editor import compendium.registry at module load,
        # so the Pyodide bundles must ship the package or they fail to boot.
        for target in ("game", "creator"):
            manifest = build_web.collect_files(build_web.TARGETS[target][2])
            self.assertIn("compendium/registry.py", manifest, target)
            self.assertIn("compendium/__init__.py", manifest, target)

    def _assert_bundle_imports(self, target: str, modules: str) -> None:
        """Write the bundle's embedded files to an isolated dir and import its
        entry modules with nothing else on the path — the real check that the
        globs are self-sufficient (the repo on sys.path hides missing files)."""
        manifest = build_web.collect_files(build_web.TARGETS[target][2])
        with tempfile.TemporaryDirectory() as tmp:
            for relpath, content in manifest.items():
                dest = Path(tmp) / relpath
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = ""  # cwd (tmp) + stdlib only, not the repo
            result = subprocess.run(
                [sys.executable, "-c", f"import {modules}"],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(result.returncode, 0, f"{target} bundle failed to import:\n{result.stderr}")

    def test_game_bundle_imports_in_isolation(self) -> None:
        self._assert_bundle_imports("game", "interfaces.cli, interfaces.web, game.actions")

    def test_creator_bundle_imports_in_isolation(self) -> None:
        self._assert_bundle_imports("creator", "editor.web")


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
