from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import class_rating, compute_effective_stats
from game.loader import load_cars, load_parts


class EffectiveStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}

    def test_turbo_increases_power_and_engine_heat(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        turbo = deepcopy(base)
        turbo.installed_parts.append("basic_turbo_kit")

        base_stats = compute_effective_stats(base, self.parts)
        turbo_stats = compute_effective_stats(turbo, self.parts)

        self.assertGreater(turbo_stats.power, base_stats.power)
        self.assertGreater(turbo_stats.engine_heat_rate, base_stats.engine_heat_rate)

    def test_brake_kit_increases_braking(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        upgraded = deepcopy(base)
        upgraded.installed_parts.append("sport_brake_kit_1")

        self.assertGreater(
            compute_effective_stats(upgraded, self.parts).braking,
            compute_effective_stats(base, self.parts).braking,
        )

    def test_low_condition_reduces_reliability_and_grip(self) -> None:
        good = deepcopy(self.cars["suzuka_roadster"])
        poor = deepcopy(good)
        poor.condition.overall_condition = 50.0

        good_stats = compute_effective_stats(good, self.parts)
        poor_stats = compute_effective_stats(poor, self.parts)

        self.assertLess(poor_stats.reliability, good_stats.reliability)
        self.assertLess(poor_stats.grip, good_stats.grip)

    def test_engine_maps_change_power_and_fuel(self) -> None:
        balanced = deepcopy(self.cars["kanto_k660"])
        hot = deepcopy(balanced)
        fuel_save = deepcopy(balanced)
        hot.tune.engine_map = "hot"
        fuel_save.tune.engine_map = "fuel_save"

        balanced_stats = compute_effective_stats(balanced, self.parts)
        hot_stats = compute_effective_stats(hot, self.parts)
        fuel_save_stats = compute_effective_stats(fuel_save, self.parts)

        self.assertGreater(hot_stats.power, balanced_stats.power)
        self.assertGreater(hot_stats.fuel_burn_rate, balanced_stats.fuel_burn_rate)
        self.assertLess(fuel_save_stats.fuel_burn_rate, balanced_stats.fuel_burn_rate)

    def test_weight_reduces_acceleration(self) -> None:
        light = deepcopy(self.cars["kanto_k660"])
        heavy = deepcopy(light)
        heavy.chassis.weight_kg += 300

        self.assertLess(
            compute_effective_stats(heavy, self.parts).acceleration,
            compute_effective_stats(light, self.parts).acceleration,
        )

    def test_downforce_tune_increases_aero_and_drag(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        tuned = deepcopy(base)
        tuned.tune.front_downforce = 12
        tuned.tune.rear_downforce = 18

        base_stats = compute_effective_stats(base, self.parts)
        tuned_stats = compute_effective_stats(tuned, self.parts)

        self.assertGreater(tuned_stats.aero_grip, base_stats.aero_grip)
        self.assertGreater(tuned_stats.drag, base_stats.drag)

    def test_camber_changes_grip(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        tuned = deepcopy(base)
        tuned.tune.camber_front = 0.0

        self.assertNotEqual(
            compute_effective_stats(tuned, self.parts).grip,
            compute_effective_stats(base, self.parts).grip,
        )

    def test_brake_bias_changes_braking_and_stability(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        tuned = deepcopy(base)
        tuned.tune.brake_bias = 0.75

        base_stats = compute_effective_stats(base, self.parts)
        tuned_stats = compute_effective_stats(tuned, self.parts)

        self.assertNotEqual(tuned_stats.braking, base_stats.braking)
        self.assertNotEqual(tuned_stats.brake_stability, base_stats.brake_stability)

    def test_final_drive_changes_acceleration_and_top_speed_oppositely(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        short = deepcopy(base)
        short.tune.final_drive = base.tune.final_drive + 0.60

        base_stats = compute_effective_stats(base, self.parts)
        short_stats = compute_effective_stats(short, self.parts)

        self.assertGreater(short_stats.acceleration, base_stats.acceleration)
        self.assertLess(short_stats.top_speed, base_stats.top_speed)

    def test_class_rating_increases_with_performance_part(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        upgraded = deepcopy(base)
        upgraded.installed_parts.append("basic_turbo_kit")

        self.assertGreater(class_rating(upgraded, self.parts), class_rating(base, self.parts))

    def test_different_cars_have_different_ratings(self) -> None:
        self.assertNotEqual(
            class_rating(self.cars["kanto_k660"], self.parts),
            class_rating(self.cars["suzuka_roadster"], self.parts),
        )


if __name__ == "__main__":
    unittest.main()
