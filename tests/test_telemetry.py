from __future__ import annotations

from copy import deepcopy
import unittest

from constants import ENGINE_OVERHEAT_C, TIRE_OVERHEAT_C
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts, load_tracks
from game.race_session import apply_player_command, enter_event, simulate_tick
from game.simulation import _initial_state, calculate_lap_time
from game.telemetry import failure_chance, mistake_chance


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}
        self.parts = load_parts()
        self.tracks = {track.id: track for track in load_tracks()}

    def _session(self, seed: int = 21):
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=seed)
        session.ticks_per_lap = 1  # one tick == one full lap for unit tests
        return session

    def test_telemetry_lists_have_one_entry_per_lap(self) -> None:
        session = self._session()
        laps = 3
        for _ in range(laps):
            apply_player_command(session, "push")

        history = session.telemetry["YOU"]
        self.assertEqual(len(history.lap_times), laps)
        self.assertEqual(len(history.positions), laps)
        self.assertEqual(len(history.engine_temps), laps)
        self.assertEqual(len(history.fuel_pct), laps)
        self.assertEqual(len(history.tire_wear), laps)
        self.assertEqual(len(history.tire_temps), laps)
        self.assertEqual(len(history.driver_energy), laps)
        self.assertEqual(len(history.driver_focus), laps)
        self.assertEqual(len(history.driver_stress), laps)

    def test_push_tire_wear_monotonically_decreases(self) -> None:
        session = self._session()
        for _ in range(3):
            apply_player_command(session, "push")

        wear = session.telemetry["YOU"].tire_wear
        self.assertEqual(wear, sorted(wear, reverse=True))

    def test_tire_temp_rises_under_push_and_falls_under_cool_down(self) -> None:
        push = self._session()
        cool = self._session()
        apply_player_command(push, "push")
        apply_player_command(cool, "cool_down")

        self.assertGreater(push.telemetry["YOU"].tire_temps[-1], 85.0)
        self.assertLessEqual(cool.telemetry["YOU"].tire_temps[-1], 85.0)

    def test_fuel_decreases_and_engine_heats_faster_under_push(self) -> None:
        normal = self._session()
        hot = self._session()
        # Start above the operating floor so the push-vs-normal heat delta is visible
        # (heat is a balance; the kei's engine sits on the floor at any pace).
        for session in (normal, hot):
            next(car for car in session.cars if car.is_player).engine_temp = 100.0
        for _ in range(2):
            simulate_tick(normal)
            apply_player_command(hot, "push")

        self.assertLess(normal.telemetry["YOU"].fuel_pct[-1], normal.telemetry["YOU"].fuel_pct[0])
        self.assertGreater(hot.telemetry["YOU"].engine_temps[-1], normal.telemetry["YOU"].engine_temps[-1])

    def test_driver_energy_drops_faster_going_all_out(self) -> None:
        normal = self._session()
        attack = self._session()
        simulate_tick(normal)
        apply_player_command(attack, "go_all_out")

        self.assertLess(attack.telemetry["YOU"].driver_energy[-1], normal.telemetry["YOU"].driver_energy[-1])

    def test_penalty_and_failure_chance_increase_with_bad_state(self) -> None:
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        track = self.tracks["maple_short"]
        good = _initial_state("kanto_k660", "driver_novak", "YOU", True)
        bad = _initial_state("kanto_k660", "driver_novak", "YOU", True)
        bad.tire_pct = 20.0
        bad.engine_temp = ENGINE_OVERHEAT_C + 10
        driver = self._session().driver_roster["driver_novak"]

        self.assertGreater(calculate_lap_time(effective, track, state=bad), calculate_lap_time(effective, track, state=good))
        self.assertGreater(failure_chance(bad, effective, driver), failure_chance(good, effective, driver))

    def test_warnings_and_stress_affect_mistake_chance(self) -> None:
        session = self._session()
        player = next(car for car in session.cars if car.is_player)
        player.tire_temp = TIRE_OVERHEAT_C + 1
        player.fuel_pct = 19.0
        result = simulate_tick(session)

        joined = " ".join(result.event_log)
        self.assertIn("Tire temperature", joined)
        self.assertIn("Fuel is below 20%", joined)

        driver = session.driver_roster[player.driver_id]
        player.driver_stress = 35.0
        low = mistake_chance(player, driver)
        player.driver_stress = 80.0
        high = mistake_chance(player, driver)
        self.assertGreater(high, low)


if __name__ == "__main__":
    unittest.main()
