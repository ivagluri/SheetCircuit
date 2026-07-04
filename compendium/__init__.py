"""SheetCircuit compendium: the single source of truth for player-facing
reference documentation of every editable/tunable parameter.

Content is authored once here as structured data (``model.Entry`` /
``Section`` / ``Chapter``) and consumed by two renderers that must never drift
apart: the in-game manpages-style screens (``game.actions.compendium_screen``)
and the standalone static page (``compendium.render_html``). Ranges and choices
are harvested programmatically from ``editor.fields`` and ``constants`` so they
cannot fall out of sync with the schemas the game actually validates against;
only the human prose is hand-written.
"""
