"""Hillclimb gradient model: a net climb costs time, eased by power-to-weight.

The pace model is otherwise an additive seconds shave that's fixed regardless of track
length, so on a long climb a stock-vs-prepped capability gap compresses to nothing. The
gradient term makes a climb genuinely slow AND makes power-to-weight matter, so a built car
climbs faster. It is gated to net-climb traversals (point-to-point / hillclimb): a loop
returns to start, so its stored elevation is undulation, not net gain, and gets no penalty.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats, derived_class
from game.loader import load_cars, load_parts, load_tracks, track_from_dict
from game.simulation import _gradient_penalty, calculate_lap_time, lap_time_over_interval


def _track(layout_type: str, elevation_change_m: int = 1000):
    # Identical twisty geometry; only the layout (and thus whether it's a net climb) varies.
    payload = {
        "id": "t", "name": "T", "layout_type": layout_type, "length_km": 10.0,
        "pit_lane_loss_s": 0.0, "overtake_difficulty": 0.5, "elevation_change_m": elevation_change_m,
        "surface": "tarmac", "default_condition": "dry", "weather_variability": 0.0,
        "segments": [
            {"name": "a", "length_pct": 0.5, "tags": ["technical_section", "slow_corner"], "surface": "tarmac", "condition": "dry"},
            {"name": "b", "length_pct": 0.5, "tags": ["tight_chicane", "hard_braking_zone"], "surface": "tarmac", "condition": "dry"},
        ],
    }
    return track_from_dict(payload)


class GradientModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}
        self.eff = compute_effective_stats(self.cars["bavaria_325s"], self.parts)

    def test_net_climb_is_slower_than_the_same_geometry_on_a_loop(self) -> None:
        climb = _track("hillclimb")
        loop = _track("circuit")  # identical segments, but returns to start -> no net climb
        self.assertGreater(climb.climb_gradient_pct, 0.0)
        self.assertEqual(loop.climb_gradient_pct, 0.0)
        self.assertGreater(calculate_lap_time(self.eff, climb), calculate_lap_time(self.eff, loop))

    def test_penalty_shrinks_with_power_to_weight(self) -> None:
        climb = _track("hillclimb")
        weak = compute_effective_stats(self.cars["kanto_k660"], self.parts)     # 64 hp kei
        strong = compute_effective_stats(self.cars["blackpool_twelve"], self.parts)  # hypercar
        self.assertLess(strong.acceleration, 200)  # sanity: accel is the P/W axis
        self.assertGreater(weak.acceleration, 0)
        self.assertLess(_gradient_penalty(climb, strong), _gradient_penalty(climb, weak))

    def test_loop_layouts_never_get_a_gradient_penalty(self) -> None:
        # Every shipped loop track (circuit/oval/road_course/rallycross) has zero grade and
        # zero penalty regardless of its stored elevation_change_m.
        loops = {"circuit", "oval", "road_course", "rallycross"}
        for track in self.tracks.values():
            if track.layout_type in loops:
                with self.subTest(track=track.id):
                    self.assertEqual(track.climb_gradient_pct, 0.0)
                    self.assertEqual(_gradient_penalty(track, self.eff), 0.0)

    def test_gradient_preserves_the_segment_aggregate_integral(self) -> None:
        # The penalty distributes by interval length, so a whole-lap time still equals the
        # sum of its pieces on a climb (the documented integration invariant).
        climb = _track("hillclimb")
        whole = calculate_lap_time(self.eff, climb)
        pieces = (
            lap_time_over_interval(self.eff, climb, start=0.0, length=0.4)
            + lap_time_over_interval(self.eff, climb, start=0.4, length=0.6)
        )
        self.assertAlmostEqual(whole, pieces, places=6)

    def test_gradient_does_not_change_derived_class(self) -> None:
        # Class reads the flat reference suite's composite, not lap time, so it's untouched.
        self.assertEqual(derived_class(self.cars["bavaria_325s"], self.parts), "D")


class GranitePeakRealismTests(unittest.TestCase):
    """Calibration against real Pikes Peak 325 times (11:35 modified .. 14:02 stock-ish)."""

    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.track = {t.id: t for t in load_tracks()}["granite_peak_hillclimb"]

    def _lap(self, car) -> float:
        return calculate_lap_time(compute_effective_stats(car, self.parts), self.track)

    def test_stock_bavaria_matches_the_stock_era_time(self) -> None:
        # The 1992 stock-ish 325i ran 14:02.451; our stock 325S should land in that envelope.
        lap = self._lap(self.cars["bavaria_325s"])
        self.assertGreater(lap, 13 * 60 + 30, f"{lap:.0f}s too fast")
        self.assertLess(lap, 14 * 60 + 30, f"{lap:.0f}s too slow")

    def test_street_upgrades_meaningfully_help_on_the_climb(self) -> None:
        # Power-to-weight matters on a climb, so a street-built 325 is tens of seconds quicker
        # than stock -- the differentiation the flat additive model could not express.
        stock = self._lap(self.cars["bavaria_325s"])
        built = deepcopy(self.cars["bavaria_325s"])
        built.installed_parts = [
            "basic_intake_1", "performance_exhaust_1", "cooling_upgrade_1",
            "sport_suspension_1", "street_tires_1", "sport_brake_kit_1", "weight_reduction_1",
        ]
        self.assertLess(self._lap(built), stock - 20.0)


if __name__ == "__main__":
    unittest.main()
