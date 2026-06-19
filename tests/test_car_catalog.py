from __future__ import annotations

import unittest
from collections import Counter

from game.effective_stats import compute_effective_stats
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import calculate_lap_time


class CarCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = load_cars()
        self.tracks = load_tracks()

    def test_catalog_distribution_is_bottom_heavy(self) -> None:
        counts = Counter(car.identity.car_class for car in self.cars)

        self.assertGreaterEqual(counts["E"], counts["D"])
        self.assertGreaterEqual(counts["D"], counts["C"])
        self.assertGreaterEqual(counts["C"], counts["B"])
        self.assertGreaterEqual(counts["B"], counts["A"])
        self.assertEqual(counts["S"], 3)

    def test_s_class_has_one_car_per_endgame_focus(self) -> None:
        s_cars = [car for car in self.cars if car.identity.car_class == "S"]
        focus_tags = [
            tag
            for car in s_cars
            for tag in car.identity.tags
            if tag.startswith("s_") and tag.endswith("_focus")
        ]

        self.assertCountEqual(focus_tags, ["s_power_focus", "s_handling_focus", "s_traction_focus"])

    def test_s_class_focus_cars_are_competitive(self) -> None:
        s_cars = [car for car in self.cars if car.identity.car_class == "S"]

        for track in self.tracks:
            laps = [
                calculate_lap_time(compute_effective_stats(car, self.parts), track)
                for car in s_cars
            ]
            with self.subTest(track=track.id):
                self.assertLess(max(laps) - min(laps), 2.0)

    def test_s_class_focuses_are_reflected_in_raw_stats(self) -> None:
        s_cars = {car.identity.id: car for car in self.cars if car.identity.car_class == "S"}

        self.assertGreater(
            s_cars["blackpool_twelve"].powertrain.power_hp,
            s_cars["aichi_gt_one"].powertrain.power_hp,
        )
        self.assertGreater(
            s_cars["aichi_gt_one"].suspension.handling,
            s_cars["blackpool_twelve"].suspension.handling,
        )
        self.assertGreater(
            s_cars["escarpa_pikes"].suspension.mechanical_grip,
            s_cars["aichi_gt_one"].suspension.mechanical_grip,
        )


if __name__ == "__main__":
    unittest.main()
