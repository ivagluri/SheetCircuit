# SheetCircuit

A text-based racing management sim. Build a garage, hire drivers, tune your
cars, and race them in live, tick-by-tick events — all rendered as tables and
text, in the terminal or right in your browser. Inspired by classic basketball
sim games and gran-turismo-style careers.

## Play

**In the browser** — open `web/sheetcircuit.html`. It's a single self-contained
file: no install, no server, no account. The first load fetches the Python
runtime (~7 MB, cached afterwards); after that everything runs locally in the
tab. Progress saves to your browser, and you can download/upload your save as
a JSON file to move it between devices.

**In the terminal** — `python3 main.py` (Python 3.10+, no dependencies
required). For color tables, optionally `python3 -m pip install -r
requirements.txt`.

## The game

- Start with a beater and **$8,000**; buy, sell, repair, and race your way up
  through a market of 27 cars — from a 32 hp microcar to Le Mans prototypes.
- Every car's **class and PR (performance rating)** are computed, not stored:
  each car is run on fixed drag, slalom, and hybrid reference tracks, so
  home-built cars are rated exactly like stock ones.
- **Hire drivers** with different pace, consistency, and feedback skills; they
  earn XP as they race for you.
- **Tune** 22 setup fields per car — tire pressures, gearing, diff, brake bias,
  ride height, camber, engine maps, and more — and it all feeds the simulation.
- **Race live**: pick an event, car, and driver, then manage the race tick by
  tick with pace commands (push, save tyres, save fuel, cool down, pit…) while
  tires wear, fuel burns, engines heat, and race-day weather rolls in. Rivals
  run their own pit strategy, passes must be earned through dirty air, and
  mistakes, damage, or an empty tank can wreck a run. Fast-forward laps, change
  presentation speed, or sim to the end at any point.
- 11 events across 9 tracks — sprints, ovals, hillclimbs, rallies, top-speed
  runs, and duration enduros. Tracks are pure geometry; race length lives on
  the event, so one track can host both a sprint and an enduro.

## Create your own content

`python3 creator.py` opens a standalone text-mode editor that surfaces every
car, track, and event knob in grouped sections, shows a live PR / lap-profile /
race readout as you edit, validates against the game loader, and writes JSON
straight into `data/`. The game and the web build pick new content up
automatically.

The creator also runs in the browser (`web/creator.html`, linked from the game
page). Since a web page can't write into the repo, saving **downloads** the
validated `<id>.json` — drop it into `data/` and open a PR to contribute it.
Everything you save or import is also kept in your browser's storage, so your
work-in-progress collection survives reloads and shows up in the open/clone
pickers; the "Session files" panel manages those copies, and "Import JSON"
brings a downloaded file back in.

## Hosting the web version

`python3 tools/build_web.py` bundles the Python sources and all of `data/`
into a single static `web/sheetcircuit.html` that runs the real, unmodified
game code in the browser via [Pyodide](https://pyodide.org). Host it anywhere
static files go — or just send someone the file. `--target creator` builds the
browser creator (`web/creator.html`) the same way.

For GitHub Pages, `.github/workflows/pages.yml` runs the test suite, rebuilds
the bundle, and deploys it on every push to `main`. One-time setup:
**Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Development

- Run the tests: `python3 -m unittest discover -s tests`
- Game logic lives in `game/` (pure standard library), interfaces in
  `interfaces/` (terminal CLI and the browser adapter), and all content is
  data-driven JSON under `data/`.
- Rebuild the web bundle after changing game code or data:
  `python3 tools/build_web.py`.
