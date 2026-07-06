"""Editor starting templates + the Basics section stay valid and simulable.

The creator lets a new car start from an intrinsic archetype and edit only the big
knobs in a "Basics" section (whose FieldSpecs reuse existing draft paths). These tests
guard that every archetype round-trips through the real loader and produces a finite
lap time, and that no Basics path silently points at a key that isn't in the template.
"""

from __future__ import annotations

import copy
import unittest

from editor.app import CreatorApp, CAR_SCHEMA, _deep_merge, _get
from editor.fields import CAR_ARCHETYPES, CAR_SECTIONS, CAR_TEMPLATE
from editor.sample_tracks import SAMPLE_TRACKS
from game.effective_stats import compute_effective_stats
from game.loader import car_from_dict, load_tracks
from game.simulation import calculate_lap_time


class EditorTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracks = {t.id: t for t in load_tracks()}
        self.track = self.tracks["granite_peak_hillclimb"]

    def test_archetypes_round_trip_and_simulate(self) -> None:
        self.assertTrue(CAR_ARCHETYPES)
        for name, _help, overrides in CAR_ARCHETYPES:
            with self.subTest(archetype=name):
                draft = _deep_merge(CAR_TEMPLATE, overrides)
                draft["id"] = "test_archetype"  # id is required before validation
                car = car_from_dict(draft)
                lap = calculate_lap_time(compute_effective_stats(car), self.track, None, None, None)
                self.assertTrue(lap > 0 and lap == lap and lap != float("inf"), f"{name}: {lap}")

    def test_sample_tracks_simulate_and_discriminate(self) -> None:
        # Every synthetic 'extreme' produces a finite lap time, and they aren't clones:
        # a muscle car (big power) must beat a lightweight one on the drag strip.
        self.assertTrue(SAMPLE_TRACKS)
        by_name = {name: ov for name, _h, ov in CAR_ARCHETYPES}

        def eff(overrides):
            draft = _deep_merge(CAR_TEMPLATE, overrides)
            draft["id"] = "t"
            return compute_effective_stats(car_from_dict(draft))

        muscle = eff(by_name["Muscle / power"])
        light = eff(by_name["Lightweight momentum"])
        for track in SAMPLE_TRACKS:
            with self.subTest(track=track.name):
                lap = calculate_lap_time(muscle, track, None, None, None)
                self.assertTrue(lap > 0 and lap == lap and lap != float("inf"))
        drag = next(t for t in SAMPLE_TRACKS if t.id == "sample_drag")
        self.assertLess(
            calculate_lap_time(muscle, drag, None, None, None),
            calculate_lap_time(light, drag, None, None, None),
        )

    def test_basics_section_paths_resolve_in_template(self) -> None:
        basics = CAR_SECTIONS[0]
        self.assertEqual(basics.title, "Basics")
        for spec in basics.fields:
            with self.subTest(field=spec.label):
                # _get raises KeyError if the path points at a missing key.
                _get(CAR_TEMPLATE, spec.path)


class _Stop(Exception):
    """Raised when the scripted input runs out, to break the editor loop."""


class _DummyTerm:
    """No-op stand-in for the rich terminal so the editor loop can run headless."""

    def __getattr__(self, _name):
        return lambda *a, **k: None


class UnsavedGuardTests(unittest.TestCase):
    def _drive(self, inputs):
        """Run CreatorApp.edit on a fresh car draft with scripted keypresses.

        Returns (prompts, draft): the labels the app asked and the final draft.
        """
        app = CreatorApp()
        app.term = _DummyTerm()
        prompts: list[str] = []
        queue = list(inputs)

        def fake_ask(label):
            prompts.append(label)
            if not queue:
                raise _Stop
            return queue.pop(0)

        app.ask = fake_ask  # type: ignore[method-assign]
        draft = copy.deepcopy(CAR_SCHEMA.template)
        try:
            app.edit(CAR_SCHEMA, draft)
        except _Stop:
            self.fail(f"editor did not exit; asked: {prompts}")
        return prompts, draft

    def test_clean_exit_does_not_prompt(self) -> None:
        prompts, _ = self._drive(["b"])  # back immediately, no edits
        self.assertEqual(len(prompts), 1)
        self.assertFalse(any("Unsaved" in p for p in prompts))

    def test_dirty_exit_warns_then_discards(self) -> None:
        # edit Basics (1) → power_hp (1) → 999 → back (b) → quit (b) → discard (d)
        prompts, draft = self._drive(["1", "1", "999", "b", "b", "d"])
        self.assertEqual(draft["powertrain"]["power_hp"], 999)  # the edit landed
        self.assertTrue(any("Unsaved" in p for p in prompts), prompts)

    def test_failed_save_keeps_editor_open(self) -> None:
        # A blank-id draft can't save, so choosing [s] at the guard must not exit —
        # the second guard prompt proves we stayed in the editor.
        prompts, _ = self._drive(["1", "1", "999", "b", "b", "s", "b", "d"])
        self.assertGreaterEqual(sum("Unsaved" in p for p in prompts), 2, prompts)


class _RecordingTerm(_DummyTerm):
    """DummyTerm that remembers the table titles it was asked to render."""

    def __init__(self) -> None:
        self.tables: list[str] = []

    def table(self, title, headers, rows):  # noqa: D401 - test stub
        self.tables.append(title)


class CreatorCompendiumTests(unittest.TestCase):
    def test_browser_drills_in_and_exits_cleanly(self) -> None:
        app = CreatorApp()
        term = _RecordingTerm()
        app.term = term
        # index → Cars (1) → Tune (by name) → field 3, then b all the way out
        # (q now quit-confirms per the universal contract; b past the index leaves)
        queue = ["1", "tune", "3", "b", "b", "b", "b"]

        def fake_ask(_label):
            if not queue:
                raise _Stop
            return queue.pop(0)

        app.ask = fake_ask  # type: ignore[method-assign]
        try:
            app.compendium()
        except _Stop:
            self.fail("compendium browser did not exit")
        self.assertIn("Chapters", term.tables)  # index rendered
        self.assertIn("Tune", term.tables)  # section page rendered


if __name__ == "__main__":
    unittest.main()
