"""Structural completeness + source-of-truth consistency for the compendium.

These are the tripwires that keep the compendium from silently going stale:
add a car/track/event knob to the schema (or a tune field) without a matching
compendium entry and one of these fails loudly. Prose content is asserted in
Phase 3's per-domain tests; here we only check structure and harvested data.
"""

from __future__ import annotations

import unittest

from dataclasses import fields as dataclass_fields

from constants import TUNE_FIELD_RANGES
from editor.fields import CAR_SECTIONS, EVENT_SECTIONS, SEGMENT_FIELDS, TRACK_SECTIONS
from game.actions import _TUNE_FIELD_GROUPS
from game.loader import load_parts
from game.models import Driver
from game.parts import SLOT_RULES
from compendium import registry


class CompendiumCompletenessTests(unittest.TestCase):
    def test_every_car_fieldspec_has_entry(self) -> None:
        for section in CAR_SECTIONS:
            if section.title == "Basics":
                continue  # curated re-listing of other sections' paths
            for spec in section.fields:
                entry_id = "car." + ".".join(spec.path)
                self.assertIn(entry_id, registry.ENTRIES_BY_ID, entry_id)

    def test_every_track_fieldspec_has_entry(self) -> None:
        for section in TRACK_SECTIONS:
            for spec in section.fields:
                entry_id = "track." + ".".join(spec.path)
                self.assertIn(entry_id, registry.ENTRIES_BY_ID, entry_id)
        for spec in SEGMENT_FIELDS:
            entry_id = "track.segment." + spec.key
            self.assertIn(entry_id, registry.ENTRIES_BY_ID, entry_id)

    def test_every_event_fieldspec_has_entry(self) -> None:
        for section in EVENT_SECTIONS:
            for spec in section.fields:
                entry_id = "event." + ".".join(spec.path)
                self.assertIn(entry_id, registry.ENTRIES_BY_ID, entry_id)

    def test_every_driver_field_has_entry(self) -> None:
        for field in dataclass_fields(Driver):
            entry_id = "driver." + field.name
            self.assertIn(entry_id, registry.ENTRIES_BY_ID, entry_id)

    def test_every_segment_tag_has_entry(self) -> None:
        from constants import SEGMENT_TAG_WEIGHTS

        for tag in SEGMENT_TAG_WEIGHTS:
            self.assertIn(f"track.tag.{tag}", registry.ENTRIES_BY_ID, tag)

    def test_tune_lookup_matches_ingame_tune_fields(self) -> None:
        names = [name for _title, group in _TUNE_FIELD_GROUPS for name in group]
        # no duplicate field names across the tune-menu groups
        self.assertEqual(len(names), len(set(names)))
        # the reconstructed lookup covers exactly the in-game tune field set
        self.assertEqual(set(names), set(registry.TUNE_LOOKUP))
        # and every one resolves to a real, car-domain entry
        for name in names:
            entry = registry.TUNE_LOOKUP[name]
            self.assertEqual(entry.domain, "car", name)
            self.assertIn("tune_menu", entry.editable_in, name)

    def test_harvested_ranges_match_source_of_truth(self) -> None:
        for name in registry.TUNE_LOOKUP:
            if name not in TUNE_FIELD_RANGES:
                continue
            expected = TUNE_FIELD_RANGES[name]
            self.assertEqual(registry.TUNE_LOOKUP[name].value_range, expected, name)

    def test_every_part_and_slot_has_entry(self) -> None:
        for part in load_parts():
            self.assertIn(f"part.{part.id}", registry.ENTRIES_BY_ID, part.id)
        for rule in SLOT_RULES:
            self.assertIn(f"part.slot.{rule.id}", registry.ENTRIES_BY_ID, rule.id)

    def test_part_catalog_summaries_are_readable(self) -> None:
        part_entries = [
            entry
            for entry_id, entry in registry.ENTRIES_BY_ID.items()
            if entry_id.startswith("part.") and not entry_id.startswith("part.slot.")
        ]
        self.assertTrue(part_entries)
        raw_fragments = [
            "powertrain.",
            "chassis.",
            "tires.",
            "brakes.",
            "suspension.",
            "aero.",
            "durability.",
            "fuel.",
        ]
        for entry in part_entries:
            with self.subTest(entry=entry.id):
                self.assertFalse(any(fragment in entry.effect_summary for fragment in raw_fragments))
                self.assertNotIn("\n", entry.effect_summary)
        self.assertIn("unlocks Engine Map", registry.ENTRIES_BY_ID["part.sports_ecu"].effect_summary)
        self.assertIn("Aero ++", registry.ENTRIES_BY_ID["part.aero_kit"].effect_summary)
        self.assertIn("Drag --", registry.ENTRIES_BY_ID["part.aero_kit"].effect_summary)


class DomainContentTests(unittest.TestCase):
    """Every section in a fully-authored chapter has an intro, and every entry
    a one-line effect summary. Called per-domain as each Phase 3 sub-phase lands
    its content; prose is intentionally sparse so it is NOT asserted here."""

    def _assert_chapter_documented(self, chapter_id: str) -> None:
        chapter = next(c for c in registry.CHAPTERS if c.id == chapter_id)
        self.assertTrue(chapter.intro.strip(), f"{chapter_id} chapter missing intro")
        for section in chapter.sections:
            self.assertTrue(section.intro.strip(), f"{chapter_id}/{section.title} missing intro")
            self.assertTrue(section.entries, f"{chapter_id}/{section.title} has no entries")
            for entry in section.entries:
                self.assertTrue(entry.effect_summary.strip(), f"{entry.id} missing effect_summary")

    def test_cars_fully_documented(self) -> None:
        self._assert_chapter_documented("cars")

    def test_parts_fully_documented(self) -> None:
        self._assert_chapter_documented("parts")

    def test_drivers_fully_documented(self) -> None:
        self._assert_chapter_documented("drivers")

    def test_tracks_fully_documented(self) -> None:
        self._assert_chapter_documented("tracks")

    def test_events_fully_documented(self) -> None:
        self._assert_chapter_documented("events")


if __name__ == "__main__":
    unittest.main()
