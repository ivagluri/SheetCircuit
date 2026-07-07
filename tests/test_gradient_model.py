"""Hillclimb climb model: a net climb's pace is driven by real power-to-weight.

Pace is proportional (a fraction of the lap per composite point), so capability already
spreads cars over a long lap; on top of that the climb model adds the real GRAVITATIONAL time
penalty, monotonic in the car's own hp/kg, anchored to REAL paved Pikes Peak stock times
(econobox ~14:00, 911 Turbo S 9:53) -- never to our catalog, so a custom car gets a real climb
time from its own specs. The two contributions were re-split when pace went proportional (see
GRADIENT_PW_GAIN). Gated to net-climb layouts; loops return to start and get no adjustment.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
import unittest

from game.effective_stats import compute_effective_stats, derived_class
from game.loader import load_cars, load_parts, load_tracks, track_from_dict
from game.simulation import _climb_adjustment, calculate_lap_time, lap_time_over_interval


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


def _showroom(car):
    """A condition-100 copy, so effective hp/kg equals the car's factory spec."""
    car = deepcopy(car)
    for field in fields(car.condition):
        setattr(car.condition, field.name, 100.0 if field.name != "mileage" else 0)
    return car


class ClimbModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}

    def _eff(self, car_id):
        return compute_effective_stats(self.cars[car_id], self.parts)

    def test_climb_adjustment_is_monotonic_in_power_to_weight(self) -> None:
        # The whole point: a lower hp/kg car eats more climb time than a higher one, all the
        # way down -- no plateau, no clamp bunching weak cars together.
        climb = _track("hillclimb")
        by_pw = sorted(
            ("torino_500r", "kanto_k660", "bavaria_325s", "maranello_forty", "blackpool_twelve"),
            key=lambda cid: self._eff(cid).power_to_weight,
        )
        adjustments = [_climb_adjustment(climb, self._eff(cid)) for cid in by_pw]
        self.assertEqual(adjustments, sorted(adjustments, reverse=True))

    def test_below_reference_car_is_slower_on_a_climb_than_the_same_loop(self) -> None:
        # A modest car (below the time-neutral hp/kg) loses time to the grade.
        climb = _track("hillclimb")
        loop = _track("circuit")  # identical segments, returns to start -> no net climb
        self.assertGreater(climb.climb_gradient_pct, 0.0)
        self.assertEqual(loop.climb_gradient_pct, 0.0)
        eff = self._eff("bavaria_325s")
        self.assertGreater(calculate_lap_time(eff, climb), calculate_lap_time(eff, loop))

    def test_loop_layouts_never_get_a_climb_adjustment(self) -> None:
        loops = {"circuit", "oval", "road_course", "rallycross"}
        eff = self._eff("bavaria_325s")
        for track in self.tracks.values():
            if track.layout_type in loops:
                with self.subTest(track=track.id):
                    self.assertEqual(track.climb_gradient_pct, 0.0)
                    self.assertEqual(_climb_adjustment(track, eff), 0.0)

    def test_climb_preserves_the_segment_aggregate_integral(self) -> None:
        # The adjustment distributes by interval length, so a whole-lap time still equals the
        # sum of its pieces on a climb (the documented integration invariant).
        climb = _track("hillclimb")
        eff = self._eff("bavaria_325s")
        whole = calculate_lap_time(eff, climb)
        pieces = (
            lap_time_over_interval(eff, climb, start=0.0, length=0.4)
            + lap_time_over_interval(eff, climb, start=0.4, length=0.6)
        )
        self.assertAlmostEqual(whole, pieces, places=6)

    def test_climb_does_not_change_derived_class(self) -> None:
        # Class reads the flat reference suite's composite, not lap time, so climb
        # calculations must not mutate or reclass the car.
        car = self.cars["bavaria_325s"]
        before = derived_class(car, self.parts)
        calculate_lap_time(compute_effective_stats(car, self.parts), self.tracks["granite_peak_hillclimb"])
        self.assertEqual(derived_class(car, self.parts), before)


class GranitePeakRealismTests(unittest.TestCase):
    """Validation against real paved Pikes Peak factory-stock times."""

    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.track = {t.id: t for t in load_tracks()}["granite_peak_hillclimb"]

    def _lap(self, car) -> float:
        return calculate_lap_time(compute_effective_stats(car, self.parts), self.track)

    def test_showroom_supercar_matches_the_real_911_time(self) -> None:
        # maranello_forty (0.377 hp/kg) is a 911-Turbo-S analog; David Donner's 100% stock
        # 911 Turbo S ran 9:53. A showroom maranello must land in that envelope -- and the
        # model was anchored to the curve, not to this car, so this is a real validation.
        lap = self._lap(_showroom(self.cars["maranello_forty"]))
        self.assertGreater(lap, 9 * 60 + 30, f"{lap:.0f}s too fast")
        self.assertLess(lap, 10 * 60 + 20, f"{lap:.0f}s too slow")

    def test_the_climb_spreads_the_field_by_minutes_not_seconds(self) -> None:
        # No plateau: a shitbox and a supercar are minutes apart, the way the real curve runs.
        shitbox = self._lap(_showroom(self.cars["torino_500r"]))   # ~0.06 hp/kg
        supercar = self._lap(_showroom(self.cars["maranello_forty"]))  # ~0.38 hp/kg
        self.assertGreater(shitbox - supercar, 240.0)  # > 4 minutes apart

    def test_a_worn_car_climbs_slower_than_a_showroom_one(self) -> None:
        # Condition feeds effective power, so an aged engine makes less power and climbs slower.
        car = self.cars["maranello_forty"]
        self.assertGreater(self._lap(car), self._lap(_showroom(car)))

    def test_more_power_to_weight_helps_on_the_climb(self) -> None:
        # Upgrades that raise hp/kg (power, weight reduction) cut climb time -- no plateau.
        stock = self._lap(self.cars["bavaria_325s"])
        built = deepcopy(self.cars["bavaria_325s"])
        built.installed_parts = ["basic_turbo_kit", "weight_reduction_1", "basic_intake_1"]
        self.assertLess(self._lap(built), stock)


if __name__ == "__main__":
    unittest.main()
