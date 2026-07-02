"""Build the single-file web version of SheetCircuit.

Embeds the game's Python sources and all data JSON into tools/web_template.html
and writes web/sheetcircuit.html. The result is fully static: it can be opened
straight from disk (file://) or dropped on any static host; the only external
request it makes is for the Pyodide runtime on its CDN.

Usage: python3 tools/build_web.py [--output web/sheetcircuit.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "web_template.html"
PLACEHOLDER = "__SHEETCIRCUIT_FILES__"

# Explicit allowlist: only what the game needs at runtime in the browser.
# editor/, tools/, tests/, creator.py and main.py stay out of the bundle.
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


def collect_files() -> dict[str, str]:
    manifest: dict[str, str] = {}
    for pattern in SOURCE_GLOBS:
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise SystemExit(f"build_web: no files matched {pattern!r} — layout changed?")
        for path in matches:
            manifest[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    return manifest


def build(output: Path) -> Path:
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"build_web: placeholder {PLACEHOLDER} missing from {TEMPLATE}")
    manifest = collect_files()
    # </ would terminate the inline <script> block early; JSON reads <\/ as </.
    payload = json.dumps(manifest).replace("</", "<\\/")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "web" / "sheetcircuit.html")
    args = parser.parse_args(argv)
    output = build(args.output)
    size_kb = output.stat().st_size / 1024
    file_count = len(collect_files())
    print(f"Wrote {output} ({size_kb:.0f} KB, {file_count} embedded files)")


if __name__ == "__main__":
    sys.exit(main())
