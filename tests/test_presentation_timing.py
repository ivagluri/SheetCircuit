"""Presentation/time-scale layer: tick density tied to watched wall-clock, the pre-race
time estimate, and resolution-invariance of the lap-time noise (the sqrt(slice) scaling).

The sim must be resolution-invariant: slicing a lap into more ticks may not change the race
result (mean *or* spread). The deterministic integral is covered by test_segment_resolution;
here we pin the *random* spread, which previously shrank as ticks rose (noise was scaled
linearly instead of by sqrt(slice)). See game.race_session.ticks_per_lap_for.
"""
from __future__ import annotations

import random
import statistics
import unittest

from constants import MAX_TICKS_PER_LAP, MIN_TICKS_PER_LAP, PRESENTATION_SPEED_FACTOR, TICK_RATE_HZ
from game.effective_stats import compute_effective_stats
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks
from game.models import Driver
from game.race_session import ticks_per_lap_for
from game.actions import estimate_race_times
from game.simulation import calculate_lap_time, lap_time_over_interval


def _inconsistent_driver() -> Driver:
    # Low consistency -> nonzero lap variance, so the spread is measurable.
    return Driver(
        id="d", name="D", pace=55, consistency=40, racecraft=60, feedback=60,
        fitness=60, aggression=40, mechanical_sympathy=60, wet_skill=50, salary=0,
    )


class ResolutionInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.tracks = {t.id: t for t in load_tracks()}
        self.eff = compute_effective_stats(load_cars()[0], self.parts)
        self.driver = _inconsistent_driver()

    def _lap_total(self, track, n_slices: int, seed: int) -> float:
        rng = random.Random(seed)
        return sum(
            lap_time_over_interval(self.eff, track, self.driver, None, rng, start=i / n_slices, length=1.0 / n_slices)
            for i in range(n_slices)
        )

    def test_lap_variance_spread_is_resolution_invariant(self) -> None:
        track = self.tracks["maple_short"]
        seeds = range(4000)
        std_1 = statistics.pstdev(self._lap_total(track, 1, s) for s in seeds)
        std_64 = statistics.pstdev(self._lap_total(track, 64, s) for s in seeds)
        self.assertGreater(std_1, 0.0)
        # sqrt(slice) scaling keeps the accumulated per-lap spread constant; allow sampling slack.
        self.assertAlmostEqual(std_1, std_64, delta=0.1 * std_1)

    def test_mean_unchanged_by_resolution(self) -> None:
        track = self.tracks["maple_short"]
        seeds = range(4000)
        mean_1 = statistics.mean(self._lap_total(track, 1, s) for s in seeds)
        mean_64 = statistics.mean(self._lap_total(track, 64, s) for s in seeds)
        # Deterministic core integrates exactly; zero-mean noise leaves the mean alone.
        self.assertAlmostEqual(mean_1, mean_64, delta=0.02)


class TickDensityTests(unittest.TestCase):
    def test_density_tracks_watched_time(self) -> None:
        # ticks / watched_seconds ~= TICK_RATE_HZ, so the per-update pause is ~constant.
        for lap_s in (200.0, 700.0):
            watched = lap_s / PRESENTATION_SPEED_FACTOR
            ticks = ticks_per_lap_for(lap_s)
            self.assertAlmostEqual(ticks / watched, TICK_RATE_HZ, delta=TICK_RATE_HZ * 0.05)

    def test_density_is_clamped(self) -> None:
        self.assertEqual(ticks_per_lap_for(0.001), MIN_TICKS_PER_LAP)
        self.assertEqual(ticks_per_lap_for(10 ** 9), MAX_TICKS_PER_LAP)

    def test_realtime_gets_far_more_ticks_than_compressed(self) -> None:
        # A factor-1.0 (realtime) lap yields proportionally more ticks at the same cadence.
        compressed = ticks_per_lap_for(700.0)
        realtime = ticks_per_lap_for(700.0 * PRESENTATION_SPEED_FACTOR)
        self.assertGreater(realtime, compressed * 5)


class EstimateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.tracks = {t.id: t for t in load_tracks()}
        self.events = {e.id: e for e in load_events()}
        self.cars = {c.identity.id: c for c in load_cars()}
        self.driver = load_drivers()[0]

    def test_play_is_canonical_compressed(self) -> None:
        event = self.events["granite_peak_climb"]
        track = self.tracks[event.track_id]
        car = self.cars["torino_500r"]
        canonical, play = estimate_race_times(car, self.driver, event, track, self.parts)
        self.assertAlmostEqual(play, canonical / PRESENTATION_SPEED_FACTOR, places=6)
        # Canonical equals the deterministic lap time x lap count for a lap race.
        nominal = calculate_lap_time(compute_effective_stats(car, self.parts), track, self.driver, None, None)
        self.assertAlmostEqual(canonical, nominal, places=6)  # 1-lap event

    def test_faster_car_has_shorter_race(self) -> None:
        event = self.events["granite_peak_climb"]
        track = self.tracks[event.track_id]
        slow, _ = estimate_race_times(self.cars["torino_500r"], self.driver, event, track, self.parts)
        fast, _ = estimate_race_times(self.cars["escarpa_pikes"], self.driver, event, track, self.parts)
        self.assertLess(fast, slow)


if __name__ == "__main__":
    unittest.main()
