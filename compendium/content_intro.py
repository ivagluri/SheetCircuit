"""Top-level compendium framing, shown on the index page (in-game and static).

Not a chapter — a short orientation blurb the index renders above the chapter
list. Deliberately reassures casual players that all this detail is optional.
"""

from __future__ import annotations

TITLE = "SheetCircuit Compendium"

INTRO = (
    "A complete reference to every knob you can set when building cars, tracks, "
    "events, and when tuning a car in the garage. You do not need any of this to "
    "play: the creator ships quick-setup archetypes and sensible defaults, and a "
    "stock car is already neutral and race-ready. This is here for when you want to "
    "understand exactly what a setting does and drill down."
)

HOW_TO_READ = (
    "Each chapter is split into subsystems. Every field lists what it controls "
    "(Effect), its range and units, and where you can change it (creator, the in-game "
    "Tune menu, or read-only/derived). Tune knobs also list a neutral \"ideal\" — the "
    "value that neither helps nor hurts — so tuning is about trading away from neutral, "
    "not chasing a single best number. A few genuinely subtle fields carry a longer "
    "note; most are covered by their one-line effect."
)
