"""Build the single-file web versions of SheetCircuit.

Embeds the Python sources and all data JSON into an HTML template and writes a
fully static page: it can be opened straight from disk (file://) or dropped on
any static host; the only external request it makes is for the Pyodide runtime
on its CDN. Two targets share the machinery:

  python3 tools/build_web.py                    -> web/sheetcircuit.html (the game)
  python3 tools/build_web.py --target creator   -> web/creator.html (the editor)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "__SHEETCIRCUIT_FILES__"

# Explicit allowlist: only what runs in the browser. tools/, tests/, creator.py
# and main.py stay out of the bundles; editor/ ships only with the creator.
SOURCE_GLOBS = [
    "constants.py",
    "game/*.py",
    "interfaces/*.py",
    "data/cars/*.json",
    "data/drivers/*.json",
    "data/events/*.json",
    "data/parts/*.json",
    "data/tracks/*.json",
]

EDITOR_GLOBS = [
    "editor/__init__.py",
    "editor/app.py",
    "editor/fields.py",
    "editor/sample_tracks.py",
    "editor/web.py",
]

TARGETS = {
    "game": (ROOT / "tools" / "web_template.html", ROOT / "web" / "sheetcircuit.html", SOURCE_GLOBS),
    "creator": (ROOT / "tools" / "creator_template.html", ROOT / "web" / "creator.html", SOURCE_GLOBS + EDITOR_GLOBS),
}


def collect_files(globs: list[str]) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for pattern in globs:
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise SystemExit(f"build_web: no files matched {pattern!r} — layout changed?")
        for path in matches:
            manifest[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    return manifest


def build(target: str, output: Path | None = None) -> Path:
    template_path, default_output, globs = TARGETS[target]
    output = output or default_output
    template = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"build_web: placeholder {PLACEHOLDER} missing from {template_path}")
    manifest = collect_files(globs)
    # </ would terminate the inline <script> block early; JSON reads <\/ as </.
    payload = json.dumps(manifest).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGETS), default="game")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = build(args.target, args.output)
    size_kb = output.stat().st_size / 1024
    file_count = len(collect_files(TARGETS[args.target][2]))
    print(f"Wrote {output} ({size_kb:.0f} KB, {file_count} embedded files)")


if __name__ == "__main__":
    sys.exit(main())
