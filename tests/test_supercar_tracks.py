"""Supercar 'home' tracks + the soft-knee / AWD mechanics that make them matter.

Each of the three new tracks is tilted toward one S-class car (not a guaranteed win — the
deterministic spread stays inside the S-class competitiveness guard). The pace soft knee
gives the supercars headroom above 100 without a wall (future-proof for upgrade parts),
while display/rating stay clamped; AWD adds traction, most of it on low-grip surfaces.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from constants import PACE_SOFT_KNEE
from game.effective_stats import compute_effective_stats, class_rating, derived_class
from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks, resolve_race
from game.simulation import calculate_lap_time, lap_time_over_interval
from game.race_session import enter_event


FAVOURED = {
    "cresta_speed_run": "blackpool_twelve",  # power / top-end, no-laps point-to-point
    "glenmoor_esses": "aichi_gt_one",        # handling / braking
    "cinder_pass": "escarpa_pikes",          # acceleration / AWD traction on gravel
}


class SupercarTrackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}
        self.s_cars = [c for c in self.cars.values() if derived_class(c, self.parts) == "S"]

    def _lap(self, car, track):
        return calculate_lap_time(compute_effective_stats(car, self.parts), track)

    def test_each_new_track_keeps_its_supercar_in_the_front_band(self) -> None:
        for track_id, favoured_id in FAVOURED.items():
            track = self.tracks[track_id]
            laps = {c.identity.id: self._lap(c, track) for c in self.s_cars}
            best_lap = min(laps.values())
            with self.subTest(track=track_id):
                # The named home car should be in the lead fight, not necessarily pinned as
                # absolute fastest forever as the catalog expands or condition tuning moves.
                self.assertLessEqual(laps[favoured_id] - best_lap, 0.75, f"{track_id} laps: {laps}")
                # Subtle tilt, not a blowout — the S field stays competitive. Band widened
                # to 3.1s after the Phase 3b gulf widening.
                self.assertLess(max(laps.values()) - min(laps.values()), 3.1)

    def test_straight_track_is_no_laps_point_to_point(self) -> None:
        # Race length now lives on the event: the cresta event runs a single pass.
        event = next(e for e in load_events() if e.track_id == "cresta_speed_run")
        self.assertEqual(resolve_race(event, self.tracks["cresta_speed_run"]).laps, 1)

    def test_favoured_car_laps_at_a_realistic_pace(self) -> None:
        # Phase 4.1 derives base_lap_time from the track's own geometry, so the favoured S
        # car's home lap is now an absolute realism anchor, not a loose placeholder band:
        # the average speed must be plausible for the track's length and character (a fast
        # point-to-point speed run vs a twisty esses vs a gravel mountain pass).
        expected_kmh = {
            "cresta_speed_run": (230, 280),  # ~6.2 km speed run, top-end hypercar flat out
            "glenmoor_esses": (115, 140),    # ~4.4 km handling circuit
            "cinder_pass": (105, 130),       # ~3.9 km gravel pass, traction-limited
        }
        for track_id, favoured_id in FAVOURED.items():
            track = self.tracks[track_id]
            lap = self._lap(self.cars[favoured_id], track)
            avg_kmh = track.length_km / lap * 3600
            low, high = expected_kmh[track_id]
            with self.subTest(track=track_id):
                self.assertGreaterEqual(avg_kmh, low, f"{track_id}: {avg_kmh:.0f} km/h too slow")
                self.assertLessEqual(avg_kmh, high, f"{track_id}: {avg_kmh:.0f} km/h too fast")

    def test_speed_axes_have_headroom_with_no_wall(self) -> None:
        # Supercars exceed 100 internally (no flat clamp) and stay distinct on a speed axis
        # that used to pin every one of them to exactly 100.
        eff = {c.identity.id: compute_effective_stats(c, self.parts) for c in self.s_cars}
        self.assertGreater(eff["blackpool_twelve"].power, 100.0)
        tops = {cid: e.top_speed for cid, e in eff.items()}
        self.assertGreater(len(set(round(v, 3) for v in tops.values())), 1, tops)
        self.assertGreater(eff["blackpool_twelve"].top_speed, eff["escarpa_pikes"].top_speed)

    def test_reference_car_is_below_the_knee(self) -> None:
        # Ordinary cars sit under the knee, where the transform is the identity, so the
        # k660 reference lap and balance are untouched by the soft knee.
        e = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        self.assertLess(e.acceleration, PACE_SOFT_KNEE)
        self.assertLess(e.top_speed, PACE_SOFT_KNEE)

    def test_supercars_land_in_s_with_distinct_ratings(self) -> None:
        # Class is derived from capability, which includes the soft-knee speed headroom, so
        # supercars land in S with distinct ratings rather than being suppressed to a wall.
        ratings = {c.identity.id: class_rating(c, self.parts) for c in self.s_cars}
        for c in self.s_cars:
            self.assertEqual(derived_class(c, self.parts), "S", c.identity.id)
        self.assertGreater(len(set(ratings.values())), 1, ratings)

    def test_awd_raises_grip(self) -> None:
        awd = deepcopy(self.cars["escarpa_pikes"])
        rwd = deepcopy(awd)
        rwd.identity.drivetrain = "RWD"
        self.assertGreater(
            compute_effective_stats(awd, self.parts).grip,
            compute_effective_stats(rwd, self.parts).grip,
        )

    def test_awd_dry_tarmac_keeps_segment_equivalence(self) -> None:
        # The surface-scaled AWD bonus is zero on dry tarmac, so an AWD car's per-interval
        # integral still reproduces the whole-lap aggregate exactly.
        track = self.tracks["glenmoor_esses"]  # all tarmac / dry
        eff = compute_effective_stats(self.cars["escarpa_pikes"], self.parts)
        n = 8
        full = calculate_lap_time(eff, track)
        pieces = sum(lap_time_over_interval(eff, track, start=i / n, length=1.0 / n) for i in range(n))
        self.assertAlmostEqual(full, pieces, places=6)

    def test_new_events_load_and_enter(self) -> None:
        events = {e.id: e for e in load_events()}
        drivers = load_drivers()
        driver_id = drivers[0].id
        for event_id, car_id in (
            ("cresta_top_speed", "blackpool_twelve"),
            ("glenmoor_trophy", "aichi_gt_one"),
            ("cinder_pass_rally", "escarpa_pikes"),
        ):
            self.assertIn(event_id, events)
            state = GameState(team_xp=1300, garage=[deepcopy(self.cars[car_id])], money=20000)
            session = enter_event(state, event_id, car_id, driver_id, seed=4)
            with self.subTest(event=event_id):
                self.assertEqual(session.event_id, event_id)
                self.assertGreater(len(session.cars), 1)


if __name__ == "__main__":
    unittest.main()
