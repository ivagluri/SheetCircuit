from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts, load_tracks, track_from_dict
from game.models import Driver
from game.race_session import enter_event, simulate_tick
from game.simulation import calculate_lap_time, lap_time_over_interval


def _track(segments, base_lap_time=120.0, laps=3, length_km=3.0):
    return track_from_dict(
        {
            "id": "tmp",
            "name": "Tmp",
            "layout_type": "circuit",
            "base_lap_time": base_lap_time,
            "laps": laps,
            "length_km": length_km,
            "pit_lane_loss_s": 20.0,
            "overtake_difficulty": 0.5,
            "elevation_change_m": 10,
            "surface": "tarmac",
            "default_condition": "dry",
            "weather_variability": 0.1,
            "segments": segments,
        }
    )


def _seg(name, length_pct, tags, surface="tarmac", condition="dry"):
    return {"name": name, "length_pct": length_pct, "tags": tags, "surface": surface, "condition": condition}


def _driver(wet_skill=50, pace=55):
    return Driver(
        id="d", name="D", pace=pace, consistency=60, racecraft=60, feedback=60,
        fitness=60, aggression=40, mechanical_sympathy=60, wet_skill=wet_skill, salary=0,
    )


class SegmentResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}
        self.tracks = {track.id: track for track in load_tracks()}
        self.eff = compute_effective_stats(self.cars["kanto_k660"], self.parts)

    def test_interval_times_integrate_to_full_lap(self) -> None:
        track = self.tracks["maple_short"]
        full = calculate_lap_time(self.eff, track)
        n = 8
        pieces = sum(lap_time_over_interval(self.eff, track, start=i / n, length=1.0 / n) for i in range(n))
        self.assertAlmostEqual(full, pieces, places=6)

    def test_dry_tarmac_matches_legacy_aggregate_formula(self) -> None:
        # Integral-preserving design: a dry tarmac lap equals base_lap_time minus the
        # aggregate-weighted car bonus (the pre-segment formula), so balance is intact.
        from constants import PERF_SCALE
        from game.simulation import _track_composite

        track = self.tracks["maple_short"]
        legacy = track.base_lap_time - PERF_SCALE * _track_composite(self.eff, track)
        self.assertAlmostEqual(calculate_lap_time(self.eff, track), legacy, places=6)

    def test_segment_position_shapes_pace_within_lap(self) -> None:
        # A power straight up front vs slow corners at the back: equal-length slices
        # take different time, proving composition (not just the blend) drives pace.
        track = _track(
            [
                _seg("Straight", 0.50, ["long_straight"]),
                _seg("Corners", 0.50, ["slow_corner", "technical_section"]),
            ]
        )
        front = lap_time_over_interval(self.eff, track, start=0.0, length=0.5)
        back = lap_time_over_interval(self.eff, track, start=0.5, length=0.5)
        self.assertNotAlmostEqual(front, back, places=3)

    def test_wet_is_slower_and_wears_tires_more_than_dry(self) -> None:
        segs = [_seg("A", 0.5, ["high_speed_corner"]), _seg("B", 0.5, ["slow_corner"])]
        dry = _track([dict(s, condition="dry") for s in segs])
        wet = _track([dict(s, condition="wet") for s in segs])

        self.assertGreater(calculate_lap_time(self.eff, wet), calculate_lap_time(self.eff, dry))
        self.assertGreater(wet.tire_wear_rate, dry.tire_wear_rate)

    def test_gravel_reduces_grip_and_increases_wear(self) -> None:
        segs = [_seg("A", 1.0, ["high_speed_corner", "slow_corner"])]
        tarmac = _track([dict(s, surface="tarmac") for s in segs])
        gravel = _track([dict(s, surface="gravel") for s in segs])

        self.assertGreater(calculate_lap_time(self.eff, gravel), calculate_lap_time(self.eff, tarmac))
        self.assertGreater(gravel.tire_wear_rate, tarmac.tire_wear_rate)

    def test_wet_skill_rewarded_in_the_wet_only(self) -> None:
        wet = _track([_seg("A", 1.0, ["slow_corner", "technical_section"], condition="wet")])
        dry = _track([_seg("A", 1.0, ["slow_corner", "technical_section"], condition="dry")])
        ace, poor = _driver(wet_skill=95), _driver(wet_skill=20)

        self.assertLess(calculate_lap_time(self.eff, wet, ace), calculate_lap_time(self.eff, wet, poor))
        self.assertAlmostEqual(
            calculate_lap_time(self.eff, dry, ace), calculate_lap_time(self.eff, dry, poor), places=6
        )

    def test_example_tracks_load_with_profiles_summing_to_aggregate(self) -> None:
        for track_id in ("summit_ridge_gp", "alpine_hillclimb"):
            track = self.tracks[track_id]
            with self.subTest(track=track_id):
                self.assertTrue(track.segment_profiles)
                tags = {tag for seg in track.segments for tag in seg.tags}
                self.assertEqual(len(tags), 12, "reference track should exercise all 12 tags")
                # length-weighted grip weight from profiles == aggregate grip weight
                summed = sum(p.length_pct * p.weights["grip"] for p in track.segment_profiles)
                self.assertAlmostEqual(summed, track.grip_weight, places=6)


class LapVsNonLapParityTests(unittest.TestCase):
    """A single-lap point-to-point stage must race with the same live loop as a circuit."""

    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}

    def _session(self, event_id, car_id="torino_500r", seed=5):
        state = GameState(garage=[deepcopy(self.cars[car_id])], money=5000)
        return enter_event(state, event_id, car_id, "driver_novak", seed=seed)

    def test_single_lap_stage_runs_many_live_ticks(self) -> None:
        session = self._session("alpine_hillclimb_stage")
        self.assertEqual(session.total_laps, 1)
        self.assertGreater(session.ticks_per_lap, 1)

    def test_telemetry_is_live_within_the_single_lap(self) -> None:
        session = self._session("alpine_hillclimb_stage")
        player = next(c for c in session.cars if c.is_player)
        fuel0, tire0 = player.fuel_pct, player.tire_pct

        result = simulate_tick(session)  # one mid-stage tick, not the finish

        self.assertFalse(result.is_lap_end)
        self.assertEqual(session.current_lap, 0)
        self.assertFalse(session.is_finished)
        self.assertLess(player.fuel_pct, fuel0)
        self.assertLess(player.tire_pct, tire0)

    def test_point_to_point_finishes_after_one_traversal(self) -> None:
        session = self._session("alpine_hillclimb_stage")
        for _ in range(session.ticks_per_lap):
            simulate_tick(session)
        self.assertTrue(session.is_finished)
        self.assertEqual(session.current_lap, 1)


if __name__ == "__main__":
    unittest.main()
