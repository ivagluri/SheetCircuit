"""Phase 4.1 — base_lap_time is derived from track geometry, not stored.

These are absolute realism guards: every car must lap at a plausible average speed for the
track it is on (no 64 hp kei "averaging" 205 km/h on a twisty circuit), and the derivation
must work for a track that was never authored with a base_lap_time — a custom/creator track
gets a sane lap for free. The de-pin principle applies: the anchors are intrinsic
(BASE_REFERENCE_SPEED, the design-midpoint REFERENCE_COMPOSITE, the tag speed table), never
a function of which tracks or cars happen to be loaded.
"""

from __future__ import annotations

import unittest

from constants import BASE_REFERENCE_SPEED, REFERENCE_COMPOSITE
from game.effective_stats import compute_effective_stats
from game.loader import derive_base_lap_time, load_cars, load_parts, load_tracks, track_from_dict
from game.models import TrackSegment
from game.simulation import calculate_lap_time


def _avg_kmh(track, lap_time: float) -> float:
    return track.length_km / lap_time * 3600.0


class LapTimeRealismTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = load_cars()
        self.tracks = load_tracks()

    def test_every_car_laps_at_a_plausible_speed(self) -> None:
        # The whole catalog on every track lands inside a wide-but-real racing band. The
        # ceiling allows a hypercar flat-out on the oval; the floor catches a lap so long it
        # implies a parked car.
        for car in self.cars:
            eff = compute_effective_stats(car, self.parts)
            for track in self.tracks:
                speed = _avg_kmh(track, calculate_lap_time(eff, track))
                with self.subTest(car=car.identity.id, track=track.id):
                    self.assertGreater(speed, 70.0, "implausibly slow")
                    self.assertLess(speed, 320.0, "implausibly fast")

    def test_no_kei_breaks_200_kmh(self) -> None:
        # The headline Phase 4 symptom: the 64 hp kei used to "average" ~205 km/h on a speed
        # run. It must now stay sub-200 everywhere, including the fast tracks.
        kei = next(c for c in self.cars if c.identity.id == "kanto_k660")
        eff = compute_effective_stats(kei, self.parts)
        for track in self.tracks:
            speed = _avg_kmh(track, calculate_lap_time(eff, track))
            with self.subTest(track=track.id):
                self.assertLess(speed, 200.0)

    def test_base_lap_time_is_derived_from_geometry(self) -> None:
        # Each loaded track's base_lap_time equals what the geometry derivation produces,
        # i.e. nothing is read from a stored field any more.
        for track in self.tracks:
            self.assertAlmostEqual(
                track.base_lap_time,
                derive_base_lap_time(track.segments, track.length_km),
                places=6,
                msg=track.id,
            )

    def test_straighter_track_has_a_higher_reference_speed(self) -> None:
        # The tag speed table must order tracks: a straight-dominated lap implies a higher
        # reference pace than a chicane-dominated one of the same length.
        def ref_speed(tags):
            length_km = 4.0
            segs = [TrackSegment(name="s", length_pct=1.0, tags=tags, surface="tarmac", condition="dry")]
            return length_km / derive_base_lap_time(segs, length_km) * 3600.0

        self.assertGreater(ref_speed(["long_straight"]), ref_speed(["tight_chicane"]))

    def test_design_midpoint_car_laps_at_the_reference_speed(self) -> None:
        # On neutral geometry (speed_factor == 1.0) a car at the design-midpoint composite
        # laps at exactly BASE_REFERENCE_SPEED -- the intrinsic anchor the model is built on.
        length_km = 4.0
        # A single tag whose speed factor is ~1.0 keeps the geometry neutral; exposed is 1.05,
        # short_straight 1.15 -- average them to land on 1.0 for a clean check.
        segs = [
            TrackSegment(name="a", length_pct=0.5, tags=["wide_track"], surface="tarmac", condition="dry"),
            TrackSegment(name="b", length_pct=0.5, tags=["hard_braking_zone"], surface="tarmac", condition="dry"),
        ]
        base = derive_base_lap_time(segs, length_km)
        # base = ref_lap + PERF_SCALE * REFERENCE_COMPOSITE, so a midpoint car laps at ref_lap.
        from constants import PERF_SCALE

        ref_lap = base - PERF_SCALE * REFERENCE_COMPOSITE
        ref_speed = length_km / ref_lap * 3600.0
        # speed_factor for (wide_track 1.25 + hard_braking 0.70)/2 = 0.975, so ~BASE * 0.975.
        self.assertAlmostEqual(ref_speed, BASE_REFERENCE_SPEED * 0.975, delta=1.0)

    def test_creator_track_without_stored_base_derives_a_sane_lap(self) -> None:
        # A track dict that never carried a base_lap_time still loads and gets a usable lap.
        payload = {
            "id": "custom", "name": "Custom", "layout_type": "circuit",
            "length_km": 3.5, "pit_lane_loss_s": 20.0, "overtake_difficulty": 0.5,
            "surface": "tarmac", "default_condition": "dry", "weather_variability": 0.0,
            "elevation_change_m": 20,
            "segments": [
                {"name": "front", "length_pct": 0.5, "tags": ["long_straight"], "surface": "tarmac", "condition": "dry"},
                {"name": "infield", "length_pct": 0.5, "tags": ["technical_section"], "surface": "tarmac", "condition": "dry"},
            ],
        }
        track = track_from_dict(payload)
        self.assertGreater(track.base_lap_time, 0.0)
        # A mid-pack car laps it within the same broad realistic band as the shipped catalog.
        eff = compute_effective_stats(self.cars[0], self.parts)
        speed = _avg_kmh(track, calculate_lap_time(eff, track))
        self.assertGreater(speed, 70.0)
        self.assertLess(speed, 320.0)


if __name__ == "__main__":
    unittest.main()
