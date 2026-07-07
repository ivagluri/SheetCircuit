from __future__ import annotations

import unittest
from collections import Counter

from game.effective_stats import compute_effective_stats, derived_class
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import calculate_lap_time


class CarCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = load_cars()
        self.cars_by_id = {car.identity.id: car for car in self.cars}
        self.tracks = load_tracks()

    def test_catalog_has_lower_tier_depth(self) -> None:
        # Class is derived from intrinsic capability, not catalog percentiles. This only
        # guards the starter/midgame breadth; future catalog additions can extend either
        # end without requiring this test to be rewritten.
        counts = Counter(derived_class(car, self.parts) for car in self.cars)

        lower = counts["E"] + counts["D"] + counts["C"]
        upper = counts["B"] + counts["A"] + counts["S"]
        self.assertGreater(lower, upper)
        self.assertGreaterEqual(counts["E"], 2)

    def test_known_endgame_focus_cars_are_s_class(self) -> None:
        s_cars = [
            self.cars_by_id[car_id]
            for car_id in ("aichi_gt_one", "blackpool_twelve", "escarpa_pikes")
        ]
        focus_tags = [
            tag
            for car in s_cars
            for tag in car.identity.tags
            if tag.startswith("s_") and tag.endswith("_focus")
        ]

        self.assertCountEqual(focus_tags, ["s_power_focus", "s_handling_focus", "s_traction_focus"])
        self.assertTrue(all(derived_class(car, self.parts) == "S" for car in s_cars))

    def test_known_s_class_focus_cars_are_competitive(self) -> None:
        s_cars = [
            self.cars_by_id[car_id]
            for car_id in ("aichi_gt_one", "blackpool_twelve", "escarpa_pikes")
        ]

        # Proportional pace (PERF_FRACTION) lets a capability edge open a bigger lap-time gap,
        # so the intra-S spread is ~a few % of the lap. The S cars stay competitive within a
        # class, so the guard is widened to 3.1s. If it creeps
        # past that, PERF_FRACTION or the orphan-stat magnitudes are too hot. Net-climb tracks
        # are excluded: a hillclimb is a power-to-weight time-attack, not wheel-to-wheel
        # racing, so same-class cars rightly spread out by tens of seconds there.
        for track in self.tracks:
            if track.climb_gradient_pct > 0.0:
                continue
            laps = [
                calculate_lap_time(compute_effective_stats(car, self.parts), track)
                for car in s_cars
            ]
            with self.subTest(track=track.id):
                self.assertLess(max(laps) - min(laps), 3.1)

    def test_s_class_focuses_are_reflected_in_raw_stats(self) -> None:
        s_cars = {
            car_id: self.cars_by_id[car_id]
            for car_id in ("aichi_gt_one", "blackpool_twelve", "escarpa_pikes")
        }

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
