"""Runtime, sim-grounded car class (Phase 3).

Class is computed from a car's mean capability across the fixed drag/slalom/hybrid
reference suite -- never stored, never pinned to the catalog. These tests lock the
intuitive ladder, the same-tier/different-shape distinction that a single letter used to
hide, and that a fabricated out-of-distribution car (not in the catalog) still classes
sanely.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import class_breakdown, class_rating, derived_class, derived_rating, performance_type
from game.loader import load_cars, load_parts
from game.reference_suite import REFERENCE_FIXTURES, archetype_capabilities
from game.effective_stats import compute_effective_stats


class ReferenceClassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}

    def _pr(self, car):
        return class_rating(car, self.parts)

    def test_capability_ladder_orders_the_catalog_sanely(self) -> None:
        # Torino (32 hp microcar) sits clearly below the detroit/k660 cluster, which sits
        # far below the Aichi GT -- the ladder the all-"E" stored labels could not express.
        torino, detroit, k660, aichi = (
            self._pr(self.cars["torino_500r"]),
            self._pr(self.cars["detroit_v8"]),
            self._pr(self.cars["kanto_k660"]),
            self._pr(self.cars["aichi_gt_one"]),
        )
        self.assertLess(torino, detroit)
        self.assertLess(torino, k660)
        self.assertLess(max(detroit, k660), aichi)
        self.assertEqual(derived_class(self.cars["aichi_gt_one"], self.parts), "S")

    def test_same_tier_cars_are_split_by_shape(self) -> None:
        # The torino and the detroit are both entry tier by mean capability, but the shape
        # tag carries the difference a single class letter threw away.
        torino, detroit = self.cars["torino_500r"], self.cars["detroit_v8"]
        self.assertEqual(derived_class(torino, self.parts), derived_class(detroit, self.parts))
        self.assertNotEqual(performance_type(torino, self.parts), performance_type(detroit, self.parts))
        self.assertEqual(performance_type(detroit, self.parts), "Power")

    def test_out_of_distribution_car_classes_without_being_in_the_catalog(self) -> None:
        # A fabricated hypercar (never loaded) reads top tier; a kei reads bottom tier.
        # Class is a property of the car alone -- nothing is looked up.
        veyron = deepcopy(self.cars["aichi_gt_one"])
        veyron.powertrain.power_hp = 1001
        veyron.powertrain.torque_nm = 1250
        veyron.chassis.weight_kg = 1888
        veyron.tires.tire_width_front = 265
        veyron.tires.tire_width_rear = 365
        veyron.aero.downforce = 10
        self.assertEqual(derived_class(veyron, self.parts), "S")
        self.assertEqual(derived_class(self.cars["kanto_k660"], self.parts), "E")

    def test_class_breakdown_matches_the_real_class(self) -> None:
        # The player-facing explainer must never drift from the actual eligibility class.
        for cid in ("torino_500r", "detroit_v8", "aichi_gt_one"):
            bd = class_breakdown(self.cars[cid], self.parts)
            self.assertEqual(bd["pr"], derived_rating(self.cars[cid], self.parts))
            self.assertEqual(bd["class"], derived_class(self.cars[cid], self.parts))
            self.assertEqual(bd["shape"], performance_type(self.cars[cid], self.parts))
            self.assertEqual(set(bd), {"drag", "slalom", "hybrid", "mean", "pr", "class", "shape"})

    def test_no_axis_pins_the_reference_suite_for_being_atypical(self) -> None:
        # Both extremes produce a full capability profile on every fixture (no zero/NaN),
        # so neither is silently floored just for being out of distribution.
        for cid in ("torino_500r", "aichi_gt_one"):
            caps = archetype_capabilities(compute_effective_stats(self.cars[cid], self.parts))
            self.assertEqual(set(caps), set(REFERENCE_FIXTURES))
            for name, value in caps.items():
                self.assertGreater(value, 0.0, f"{cid}:{name}")


if __name__ == "__main__":
    unittest.main()
