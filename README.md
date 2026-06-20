# SheetCircuit
text based racing management simulation
Inspired by the great "Basketball Simulator" and racing games, trying to vibe code my way to a frankenhybrid of the two.

## Running

- Game: `python3 main.py`
- Track & car creator: `python3 creator.py`

The creator is a standalone, text-mode editor (rich-only) that surfaces every car,
track, and **event** knob in grouped sections, shows a live PR / lap-profile / race
readout, validates against the game loader, and writes JSON straight into `data/`.
Tracks are pure geometry (one lap); race length lives on the event (laps, distance, or
duration), so one track can host both a sprint and an enduro.
