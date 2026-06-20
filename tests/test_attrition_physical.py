"""Physical-units attrition guards.

Fuel is litres over distance drawn against the tank; tyres lose a distance-based share
of life; engine heat and driver fatigue accrue over time. These pin the properties that
make the model physical (and rebuild-proof): distance-proportional fuel/tyre wear,
range that scales with tank size, time-driven fatigue, and the unchanged segment↔
aggregate integration invariant.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import _apply_lap_wear, _initial_state


class PhysicalAttritionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}
        self.eff = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        self.track = self.tracks["maple_short"]

    def _run(self, eff, track, laps, seconds=90.0):
        st = _initial_state("c", "d", "Y", True)
        for _ in range(laps):
            _apply_lap_wear(st, eff, track, "normal", seconds=seconds)
        return st

    def test_fuel_and_tyre_wear_scale_with_distance(self) -> None:
        one = self._run(self.eff, self.track, 1)
        three = self._run(self.eff, self.track, 3)
        self.assertAlmostEqual(100 - three.fuel_pct, 3 * (100 - one.fuel_pct), places=6)
        self.assertAlmostEqual(100 - three.tire_pct, 3 * (100 - one.tire_pct), places=6)

    def test_bigger_tank_extends_range(self) -> None:
        big = deepcopy(self.cars["kanto_k660"])
        big.fuel.fuel_capacity_l *= 2
        small_eff = self.eff
        big_eff = compute_effective_stats(big, self.parts)
        # Double the tank => half the % consumed over the same distance.
        small_used = 100 - self._run(small_eff, self.track, 10).fuel_pct
        big_used = 100 - self._run(big_eff, self.track, 10).fuel_pct
        self.assertAlmostEqual(big_used, small_used / 2, places=6)

    def test_fatigue_and_engine_heat_scale_with_time_not_distance(self) -> None:
        short = self._run(self.eff, self.track, 1, seconds=60.0)
        long = self._run(self.eff, self.track, 1, seconds=180.0)
        # Same distance (1 lap), 3x the time => 3x the stress build.
        self.assertAlmostEqual(long.driver_stress, 3 * short.driver_stress, places=6)
        self.assertGreater(long.engine_temp - 90.0, short.engine_temp - 90.0)
        # Tyre wear is distance-based, so equal across the two.
        self.assertAlmostEqual(short.tire_pct, long.tire_pct, places=9)

    def test_realistic_stint_and_range_order_of_magnitude(self) -> None:
        # A full tank and a tyre set should both be measured in (many) tens of km, not a
        # couple of laps and not thousands of km — guards against a calibration slip.
        st = _initial_state("c", "d", "Y", True)
        km = 0.0
        while st.fuel_pct > 0 and st.tire_pct > 0 and km < 5000:
            _apply_lap_wear(st, self.eff, self.track, "normal", seconds=90.0)
            km += self.track.length_km
        self.assertGreater(km, 40)
        self.assertLess(km, 2000)

    def test_integration_invariant_holds(self) -> None:
        # One whole-lap call wears the car the same as walking the segment profiles.
        whole = _initial_state("c", "d", "Y", True)
        _apply_lap_wear(whole, self.eff, self.track, "normal", seconds=90.0)

        pieces = _initial_state("c", "d", "Y", True)
        for profile in self.track.segment_profiles:
            _apply_lap_wear(
                pieces, self.eff, self.track, "normal",
                fraction=profile.length_pct, profile=profile,
                seconds=90.0 * profile.length_pct,
            )
        self.assertAlmostEqual(whole.fuel_pct, pieces.fuel_pct, places=6)
        self.assertAlmostEqual(whole.tire_pct, pieces.tire_pct, places=6)
        self.assertAlmostEqual(whole.engine_temp, pieces.engine_temp, places=6)


if __name__ == "__main__":
    unittest.main()
