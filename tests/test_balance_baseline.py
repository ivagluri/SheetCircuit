"""Drift tripwire for the effective-stats model.

This is a *regression guard*, not a definition of correctness: it does not tie the
sim to the starter car, it only fails loudly when a change shifts balance more than
intended so any regression stays bisectable. The orphan-stat folds and their
references are meant to be roughly balance-neutral at the reference (composition
matters car-to-car, but the catalog's overall pace is steady). The reference-lap
band is an absolute, track-anchored sanity check; the captured race times are a
characterization of the current model. When a change deliberately moves the
reference (e.g. re-anchoring the orphan references in Phase 2), re-pin the values
below in the same commit. The tolerance is wide enough to allow the intended
few-percent refinement but tight enough to catch a real regression.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import calculate_lap_time, simulate_race

# Player (kanto_k660 / driver_novak / sunday_cup) total time, re-pinned with the race-day
# weather model: seed 7 now rolls a WET race on maple (weather_variability 0.15), so its
# pin characterizes the wet path; 42 and 9 stay dry and pin the dry model (bit-for-bit
# unchanged by the attrition/weather rework). Folds may nudge these but must stay within
# tolerance.
# (Nudged ~-0.05s when fuel load was wired: burned litres lighten the car.)
PLAYER_TOTAL_BASELINE = {7: 408.500, 42: 400.299, 9: 399.152}
TOLERANCE = 0.03  # +/-3%


class BalanceBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}
        self.tracks = {track.id: track for track in load_tracks()}

    def test_reference_lap_stays_in_band(self) -> None:
        # Re-pinned after the proportional-pace rework: dropping the +18s base_lap_time offset
        # and making perf a fraction of the lap moves the kei's maple reference lap to ~82s.
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        lap = calculate_lap_time(effective, self.tracks["maple_short"])
        self.assertGreaterEqual(lap, 79.0)
        self.assertLessEqual(lap, 85.0)

    def test_race_outcomes_stay_near_baseline(self) -> None:
        for seed, baseline in PLAYER_TOTAL_BASELINE.items():
            gs = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
            result = simulate_race(gs, "sunday_cup", "kanto_k660", "driver_novak", seed=seed)
            player = next(s for s in result.standings if s.is_player)
            self.assertAlmostEqual(
                player.total_time, baseline, delta=baseline * TOLERANCE,
                msg=f"seed={seed} drifted from balance baseline",
            )


if __name__ == "__main__":
    unittest.main()
