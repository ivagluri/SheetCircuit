from __future__ import annotations

import unittest

from game.loader import load_parts
from game.part_effects import (
    assert_catalog_display_metadata,
    compact_part_effect_summary,
    modifier_effect,
    part_effect_display,
    readable_part_effect_rows,
)


class PartEffectDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parts = load_parts()
        cls.by_id = {part.id: part for part in cls.parts}

    def test_catalog_metadata_covers_all_part_effect_inputs(self) -> None:
        assert_catalog_display_metadata(self.parts)

    def test_polarity_follows_simulation_math(self) -> None:
        cases = {
            ("tires.tire_warmup", 3): "reduces",
            ("tires.tire_warmup", -3): "improves",
            ("suspension.suspension_compliance", 3): "improves",
            ("suspension.suspension_compliance", -3): "reduces",
            ("powertrain.engine_stress", 3): "reduces",
            ("aero.drag", 3): "reduces",
            ("chassis.weight_kg", 3): "reduces",
            ("durability.mechanical_sympathy_modifier", 1): "improves",
        }
        for (path, delta), expected in cases.items():
            with self.subTest(path=path, delta=delta):
                self.assertEqual(modifier_effect(path, delta, self.parts).polarity, expected)

    def test_compact_summary_splits_tradeoff_themes(self) -> None:
        summary = compact_part_effect_summary(self.by_id["aero_kit"], self.parts)

        self.assertIn("Aero ++", summary)
        self.assertIn("Drag --", summary)
        self.assertIn("unlocks Downforce", summary)
        self.assertNotIn("aero.", summary)

    def test_intensity_is_catalog_relative_without_absolute_floor(self) -> None:
        summary = compact_part_effect_summary(self.by_id["sports_ecu"], self.parts)

        self.assertIn("Power +", summary)
        self.assertIn("Fuel -", summary)
        self.assertIn("unlocks Engine Map", summary)

    def test_overrides_and_unlocks_use_readable_text(self) -> None:
        summary = compact_part_effect_summary(self.by_id["semi_slick_tires_1"], self.parts)
        self.assertIn("Compound: Semi Slick", summary)
        self.assertNotIn("tires.", summary)

        display = part_effect_display(self.by_id["sports_ecu"], self.parts)
        self.assertEqual(display.unlocks, ("Engine Map",))

    def test_detail_rows_separate_effect_kinds(self) -> None:
        rows = readable_part_effect_rows(self.by_id["sport_suspension_1"], self.parts)
        by_label = {row[0]: row[1] for row in rows}

        self.assertIn("Improves", by_label)
        self.assertIn("Reduces", by_label)
        self.assertIn("Handling +10", by_label["Improves"])
        self.assertIn("Compliance -5", by_label["Reduces"])
        for value in by_label.values():
            self.assertNotIn("suspension.", value)


if __name__ == "__main__":
    unittest.main()
