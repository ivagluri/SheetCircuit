"""Attrition endgame guards: fuel has a failure state, heat is a balance, the AI
manages both, and a mechanical issue can end a race.

These pin the simulation-audit rework (see CHANGELOG): an empty tank makes the car limp
(not free), normal running no longer cooks the tyres inexorably, cooling commands
actually recover temperature, rivals pit/lift instead of degrading forever, and
failures can be terminal -- especially on an overheated engine.
"""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest import mock

from constants import (
    FUEL_EMPTY_PACE_FRACTION,
    TIRE_CRITICAL_C,
    TIRE_OPTIMAL_C,
    TIRE_OVERHEAT_C,
)
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_parts, load_tracks
from game.race_session import _ai_command, apply_player_command, enter_event, simulate_tick
from game.simulation import _apply_lap_wear, _initial_state, calculate_lap_time
from game.telemetry import failure_dnf_chance


class AttritionEndgameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}
        self.eff = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        self.track = self.tracks["maple_short"]

    def _session(self, ticks_per_lap: int = 1):
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=11)
        session.ticks_per_lap = ticks_per_lap
        return session

    # --- Fuel endgame -------------------------------------------------------

    def test_empty_tank_makes_the_car_limp(self) -> None:
        from constants import FUEL_WEIGHT_PENALTY_PER_L

        fresh = _initial_state("c", "d", "Y", True)
        dry = _initial_state("c", "d", "Y", True)
        dry.fuel_pct = 0.0

        fresh_lap = calculate_lap_time(self.eff, self.track, state=fresh)
        dry_lap = calculate_lap_time(self.eff, self.track, state=dry)

        # The limp penalty dominates, minus the (physically honest) lightness of the
        # burned-off fuel load.
        expected = (
            self.track.base_lap_time * FUEL_EMPTY_PACE_FRACTION
            - self.eff.fuel_capacity_l * FUEL_WEIGHT_PENALTY_PER_L
        )
        self.assertAlmostEqual(dry_lap - fresh_lap, expected, places=6)

    # --- Heat balance -------------------------------------------------------

    def test_normal_running_does_not_cook_the_tyres(self) -> None:
        # Old model: temps only ever rose, so any long stint ended beyond critical.
        # Now passive airflow holds a mid car near its operating floor at normal pace.
        st = _initial_state("c", "d", "Y", True)
        for _ in range(50):
            lap_s = calculate_lap_time(self.eff, self.track, state=st)
            _apply_lap_wear(st, self.eff, self.track, "normal", seconds=lap_s)
        self.assertLess(st.tire_temp, TIRE_OVERHEAT_C)

    def test_attacking_heats_and_cooling_command_recovers(self) -> None:
        hot = _initial_state("c", "d", "Y", True)
        lap_s = calculate_lap_time(self.eff, self.track, state=hot)
        for _ in range(3):
            _apply_lap_wear(hot, self.eff, self.track, "go_all_out", seconds=lap_s)
        self.assertGreater(hot.tire_temp, TIRE_OPTIMAL_C)

        peak = hot.tire_temp
        _apply_lap_wear(hot, self.eff, self.track, "cool_down", seconds=lap_s)
        self.assertLess(hot.tire_temp, peak)

    def test_passive_cooling_never_drops_below_operating_floor(self) -> None:
        st = _initial_state("c", "d", "Y", True)
        lap_s = calculate_lap_time(self.eff, self.track, state=st)
        for _ in range(20):
            _apply_lap_wear(st, self.eff, self.track, "cool_down", seconds=lap_s)
        self.assertGreaterEqual(st.tire_temp, TIRE_OPTIMAL_C - 1e-9)

    # --- AI pit boss --------------------------------------------------------

    def test_ai_pits_on_worn_tyres_or_low_fuel(self) -> None:
        state = _initial_state("c", "d", "R", False)
        state.tire_pct = 20.0
        self.assertEqual(_ai_command(state, player_time=1000.0), "pit")
        state.tire_pct = 100.0
        state.fuel_pct = 5.0
        self.assertEqual(_ai_command(state, player_time=1000.0), "pit")

    def test_ai_lifts_when_overheating(self) -> None:
        state = _initial_state("c", "d", "R", False)
        state.tire_temp = TIRE_OVERHEAT_C + 5
        self.assertEqual(_ai_command(state, player_time=1000.0), "save_tyres")
        state.engine_temp = 110.0
        self.assertEqual(_ai_command(state, player_time=1000.0), "cool_down")
        state.tire_temp = TIRE_OPTIMAL_C
        self.assertEqual(_ai_command(state, player_time=1000.0), "save_fuel")

    def test_ai_pushes_in_a_close_battle_when_healthy(self) -> None:
        state = _initial_state("c", "d", "R", False)
        state.total_time = 100.0
        self.assertEqual(_ai_command(state, player_time=100.5), "push")
        self.assertEqual(_ai_command(state, player_time=200.0), "normal")

    def test_ai_pit_restores_the_car_and_is_logged(self) -> None:
        session = self._session(ticks_per_lap=1)
        rival = next(car for car in session.cars if not car.is_player)
        rival.tire_pct = 20.0
        rival.fuel_pct = 40.0

        simulate_tick(session)

        self.assertEqual(rival.tire_pct, 100.0)
        self.assertEqual(rival.fuel_pct, 100.0)
        self.assertTrue(any("pitted" in message for _lap, message in session.race_log))

    # --- Terminal failures --------------------------------------------------

    def test_overheated_engine_raises_terminal_failure_odds(self) -> None:
        cool = _initial_state("c", "d", "Y", True)
        hot = _initial_state("c", "d", "Y", True)
        hot.engine_temp = 118.0
        self.assertGreater(failure_dnf_chance(hot), failure_dnf_chance(cool))

    def test_mechanical_failure_can_retire_the_car(self) -> None:
        session = self._session(ticks_per_lap=4)  # first tick is mid-lap
        with mock.patch("game.race_session.failure_chance", return_value=1000.0), \
                mock.patch("game.race_session.failure_dnf_chance", return_value=2.0), \
                mock.patch("game.race_session.mistake_chance", return_value=0.0):
            apply_player_command(session, "normal")

        player = next(car for car in session.cars if car.is_player)
        self.assertTrue(player.is_dnf)
        self.assertTrue(
            any("retired with a mechanical failure" in message for _lap, message in session.race_log)
        )

    # --- End to end ---------------------------------------------------------

    def test_enduro_field_survives_with_managed_temperatures(self) -> None:
        # Old model end state: the whole field at 122-144C (beyond critical) because
        # nothing could ever cool. Now the all-normal player holds near the floor and
        # rivals lift when hot, so nobody active finishes beyond critical.
        from game.actions import advance_race_action, start_race_action
        from game.game_state import new_career

        state = new_career()  # the starter car is worn enough for the beater event
        state.money += 50000
        result = start_race_action(
            state, "beater_enduro", state.garage[0].identity.id, state.hired_drivers[0].id, seed=3
        )
        session = result.session
        while not session.is_finished:
            advance_race_action(session, "normal")

        player = next(car for car in session.cars if car.is_player)
        self.assertLess(player.tire_temp, TIRE_OVERHEAT_C)
        for car in session.cars:
            if not car.is_dnf:
                self.assertLess(car.tire_temp, TIRE_CRITICAL_C, car.label)


if __name__ == "__main__":
    unittest.main()
