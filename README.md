# SheetCircuit
text based racing management simulation
Inspired by the great "Basketball Simulator" and racing games, trying to vibe code my way to a frankenhybrid of the two.

## Running

- Game: `python3 main.py`
- Track & car creator: `python3 creator.py`
- Web version: open `web/sheetcircuit.html` in a browser (build it with `python3 tools/build_web.py`)

## Web version

`tools/build_web.py` bundles the whole game — Python sources and every JSON under
`data/` — into a single static `web/sheetcircuit.html`. The page runs the real,
unmodified game code in the browser via [Pyodide](https://pyodide.org) (fetched
from its CDN on first load, ~7 MB, cached afterwards), so there is no server, no
backend, and nothing to install: double-click the file or drop it on any static
host (GitHub Pages etc.). Saves go to browser localStorage, with download/upload
of the save JSON as a portable fallback. Rebuild after changing game code or data.

### GitHub Pages

`.github/workflows/pages.yml` rebuilds the web version and deploys it to GitHub
Pages on every push to `main` (it runs the test suite first). One-time setup:
repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.
After that the game is live at `https://<user>.github.io/SheetCircuit/`; the
workflow can also be run manually from the Actions tab.

The creator is a standalone, text-mode editor (rich-only) that surfaces every car,
track, and **event** knob in grouped sections, shows a live PR / lap-profile / race
readout, validates against the game loader, and writes JSON straight into `data/`.
Tracks are pure geometry (one lap); race length lives on the event (laps, distance, or
duration), so one track can host both a sprint and an enduro.
