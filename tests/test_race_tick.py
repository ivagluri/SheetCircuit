from __future__ import annotations

from copy import deepcopy
import unittest

from game.game_state import GameState
from game.loader import load_cars
from game.race_session import apply_player_command, enter_event, simulate_tick
from game.telemetry import mistake_chance


class RaceTickTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}

    def _session(self):
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=11)
        session.ticks_per_lap = 1  # one tick == one full lap for unit tests
        return session

    def test_apply_player_command_sets_pace_mode(self) -> None:
        session = self._session()
        apply_player_command(session, "push")
        player = next(car for car in session.cars if car.is_player)

        self.assertEqual(player.pace_mode, "push")

    def test_push_wears_tires_more_than_normal(self) -> None:
        normal = self._session()
        push = self._session()

        simulate_tick(normal)
        apply_player_command(push, "push")

        normal_player = next(car for car in normal.cars if car.is_player)
        push_player = next(car for car in push.cars if car.is_player)
        self.assertLess(push_player.tire_pct, normal_player.tire_pct)

    def test_conserve_wears_tires_less_than_normal(self) -> None:
        normal = self._session()
        conserve = self._session()

        simulate_tick(normal)
        apply_player_command(conserve, "conserve")

        normal_player = next(car for car in normal.cars if car.is_player)
        conserve_player = next(car for car in conserve.cars if car.is_player)
        self.assertGreater(conserve_player.tire_pct, normal_player.tire_pct)

    def test_fuel_save_uses_less_fuel_than_normal(self) -> None:
        normal = self._session()
        fuel_save = self._session()

        simulate_tick(normal)
        apply_player_command(fuel_save, "fuel_save")

        normal_player = next(car for car in normal.cars if car.is_player)
        fuel_player = next(car for car in fuel_save.cars if car.is_player)
        self.assertGreater(fuel_player.fuel_pct, normal_player.fuel_pct)

    def test_hot_map_heats_engine_more_than_normal(self) -> None:
        normal = self._session()
        hot = self._session()

        simulate_tick(normal)
        apply_player_command(hot, "hot_map")

        normal_player = next(car for car in normal.cars if car.is_player)
        hot_player = next(car for car in hot.cars if car.is_player)
        self.assertGreater(hot_player.engine_temp, normal_player.engine_temp)

    def test_positions_gaps_and_event_log_update(self) -> None:
        session = self._session()
        result = simulate_tick(session)

        self.assertEqual(result.standings[0].position, 1)
        self.assertEqual(result.standings[0].gap_to_leader, 0.0)
        self.assertTrue(result.event_log)

    def test_mistake_chance_higher_on_attack_with_worn_tires(self) -> None:
        session = self._session()
        player = next(car for car in session.cars if car.is_player)
        driver = session.driver_roster[player.driver_id]

        fresh = mistake_chance(player, driver, "normal")
        player.tire_pct = 20.0
        worn_attack = mistake_chance(player, driver, "maximum_attack")

        self.assertGreater(worn_attack, fresh)

    def test_session_finishes_after_total_laps(self) -> None:
        session = self._session()
        for _ in range(session.total_laps * session.ticks_per_lap):
            simulate_tick(session)

        self.assertTrue(session.is_finished)

    def test_dnf_removed_from_active_standings(self) -> None:
        session = self._session()
        victim = next(car for car in session.cars if not car.is_player)
        victim.is_dnf = True

        result = simulate_tick(session)

        self.assertNotIn(victim, result.standings)


if __name__ == "__main__":
    unittest.main()
