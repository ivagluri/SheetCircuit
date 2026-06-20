"""Characterization guard for the orphan-stat wiring work.

The orphan-stat folds (engine/chassis/tyre/brake/suspension/tune/durability stats
into the existing effective axes) are meant to be *balance-neutral*: composition now
matters car-to-car, but the catalog's overall pace is unchanged. These tests pin the
reference lap and a few full-race outcomes so that any phase which accidentally shifts
balance fails loudly. The tolerance is wide enough to allow the intended few-percent
refinement but tight enough to catch a real regression. If a change is deliberate,
update the captured baselines here in the same commit.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import calculate_lap_time, simulate_race

# Player (kanto_k660 / driver_novak / sunday_cup) total time captured on the
# pre-wiring code. Folds may nudge these but must stay within tolerance.
PLAYER_TOTAL_BASELINE = {7: 415.463, 42: 417.641, 9: 415.822}
TOLERANCE = 0.03  # +/-3%


class BalanceBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}
        self.tracks = {track.id: track for track in load_tracks()}

    def test_reference_lap_stays_in_band(self) -> None:
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        lap = calculate_lap_time(effective, self.tracks["maple_short"])
        self.assertGreaterEqual(lap, 84.0)
        self.assertLessEqual(lap, 90.0)

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
