"""Behavioural guards for the simplified race-command set.

Covers the fixes from the command cleanup: the stress column is now live (was dead),
Pit is one-shot, and race commands no longer change the engine map (that's tuning only).
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts
from game.race_session import apply_player_command, enter_event, simulate_tick


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}
        self.parts = load_parts()

    def _session(self):
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=11)
        session.ticks_per_lap = 1  # one tick == one full lap for unit tests
        return session

    def _player(self, session):
        return next(car for car in session.cars if car.is_player)

    def test_stress_uses_its_own_column_not_engine_heat(self) -> None:
        # save_tyres and save_fuel share the same stress multiplier (0.85) but very
        # different engine-heat multipliers. With the bug, stress tracked engine heat,
        # so they would differ; now stress reads its own column and they match.
        a = self._session()
        b = self._session()
        apply_player_command(a, "save_tyres")
        apply_player_command(b, "save_fuel")
        self.assertAlmostEqual(
            self._player(a).driver_stress, self._player(b).driver_stress, places=9
        )

    def test_go_all_out_builds_more_stress_than_cool_down(self) -> None:
        hot = self._session()
        calm = self._session()
        apply_player_command(hot, "go_all_out")
        apply_player_command(calm, "cool_down")
        self.assertGreater(self._player(hot).driver_stress, self._player(calm).driver_stress)

    def test_pit_is_one_shot(self) -> None:
        session = self._session()
        player = self._player(session)
        player.pace_mode = "pit"
        # Drive the pit lap to completion without re-issuing the command.
        simulate_tick(session)
        self.assertEqual(player.pace_mode, "normal")

    def test_command_does_not_change_engine_map(self) -> None:
        # The race command no longer influences effective stats; the engine map comes
        # solely from the tune. The parameter is gone, so passing it is an error.
        car = self.cars["kanto_k660"]
        with self.assertRaises(TypeError):
            compute_effective_stats(car, self.parts, command="go_all_out")

    def test_engine_map_drives_power_via_tune_only(self) -> None:
        balanced = deepcopy(self.cars["kanto_k660"])
        hot = deepcopy(balanced)
        hot.tune.engine_map = "hot"
        self.assertGreater(
            compute_effective_stats(hot, self.parts).power,
            compute_effective_stats(balanced, self.parts).power,
        )


if __name__ == "__main__":
    unittest.main()
