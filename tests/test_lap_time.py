from __future__ import annotations

from copy import deepcopy
import unittest

from constants import ENGINE_OVERHEAT_C
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks, resolve_race
from game.save_load import load_game, save_game
from game.simulation import _initial_state, calculate_lap_time, simulate_race
from game.telemetry import generate_driver_feedback


class LapTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}
        self.drivers = {driver.id: driver for driver in load_drivers()}
        self.tracks = {track.id: track for track in load_tracks()}

    def test_simulation_is_deterministic_by_seed(self) -> None:
        state_a = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        state_b = GameState(garage=[deepcopy(self.cars["kanto_k660"])])

        result_a = simulate_race(state_a, "sunday_cup", "kanto_k660", "driver_novak", seed=42)
        result_b = simulate_race(state_b, "sunday_cup", "kanto_k660", "driver_novak", seed=42)

        self.assertEqual(result_a.lap_times, result_b.lap_times)
        self.assertEqual([car.position for car in result_a.standings], [car.position for car in result_b.standings])

    def test_higher_effective_stats_are_faster_same_track(self) -> None:
        track = self.tracks["maple_short"]
        weak = compute_effective_stats(self.cars["eurovan_cup"], self.parts)
        strong = compute_effective_stats(self.cars["suzuka_roadster"], self.parts)

        self.assertLess(calculate_lap_time(strong, track), calculate_lap_time(weak, track))

    def test_tire_degradation_increases_lap_time(self) -> None:
        track = self.tracks["maple_short"]
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        fresh = _state(tire_pct=100.0)
        worn = _state(tire_pct=20.0)

        self.assertGreater(
            calculate_lap_time(effective, track, state=worn),
            calculate_lap_time(effective, track, state=fresh),
        )

    def test_engine_overheat_increases_lap_time(self) -> None:
        track = self.tracks["maple_short"]
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        normal = _state(engine_temp=ENGINE_OVERHEAT_C - 1)
        hot = _state(engine_temp=ENGINE_OVERHEAT_C + 10)

        self.assertGreater(
            calculate_lap_time(effective, track, state=hot),
            calculate_lap_time(effective, track, state=normal),
        )

    def test_directional_car_track_matchups(self) -> None:
        oval = self.tracks["northbank_oval"]
        maple = self.tracks["maple_short"]
        k660 = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        roadster = compute_effective_stats(self.cars["suzuka_roadster"], self.parts)
        v8 = compute_effective_stats(self.cars["detroit_v8"], self.parts)

        self.assertLess(calculate_lap_time(v8, oval), calculate_lap_time(k660, oval))
        self.assertLess(calculate_lap_time(roadster, maple), calculate_lap_time(v8, maple))

    def test_race_finishes_after_track_laps_and_positions_ranked(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=7)

        event = next(e for e in load_events() if e.id == "sunday_cup")
        expected_laps = resolve_race(event, self.tracks["maple_short"]).laps
        self.assertEqual(result.total_laps, expected_laps)
        self.assertTrue(all(len(times) == expected_laps for times in result.lap_times.values()))
        self.assertEqual(result.standings[0].position, 1)
        self.assertEqual(result.standings, sorted(result.standings, key=lambda car: car.total_time))

    def test_prize_money_mileage_and_wear_apply(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        start_mileage = car.condition.mileage
        start_condition = car.condition.overall_condition
        state = GameState(garage=[car])

        result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=9)

        self.assertEqual(state.money, 8000 + result.prize_money)
        self.assertGreater(car.condition.mileage, start_mileage)
        self.assertLess(car.condition.overall_condition, start_condition)

    def test_k660_maple_reference_lap_time(self) -> None:
        # Re-pinned to ~82s after the proportional-pace rework (no +18s base_lap_time offset).
        track = self.tracks["maple_short"]
        effective = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        lap_time = calculate_lap_time(effective, track)

        self.assertGreaterEqual(lap_time, 79.0)
        self.assertLessEqual(lap_time, 85.0)

    def test_hot_map_improves_lap_but_increases_engine_heat(self) -> None:
        track = self.tracks["maple_short"]
        balanced_car = deepcopy(self.cars["kanto_k660"])
        hot_car = deepcopy(balanced_car)
        hot_car.tune.engine_map = "hot"

        balanced = compute_effective_stats(balanced_car, self.parts)
        hot = compute_effective_stats(hot_car, self.parts)

        self.assertLess(calculate_lap_time(hot, track), calculate_lap_time(balanced, track))
        self.assertGreater(hot.engine_heat_rate, balanced.engine_heat_rate)

    def test_saved_tune_restores_on_load(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            car = deepcopy(self.cars["kanto_k660"])
            car.tune.front_downforce = 11
            car.tune.brake_bias = 0.62
            state = GameState(garage=[car])
            save_path = Path(tmpdir) / "save.json"

            save_game(state, save_path)
            loaded = load_game(save_path)

            self.assertEqual(loaded.garage[0].tune.front_downforce, 11)
            self.assertEqual(loaded.garage[0].tune.brake_bias, 0.62)

    def test_driver_feedback_scales_with_feedback_stat(self) -> None:
        from game.models import TelemetryHistory

        history = TelemetryHistory(tire_temps=[115.0], engine_temps=[98.0], fuel_pct=[55.0])

        high = generate_driver_feedback(self.drivers["driver_costa"], history)
        low = generate_driver_feedback(self.drivers["driver_novak"], history)

        self.assertIn("115C", high)
        self.assertNotIn("115C", low)


def _state(tire_pct: float = 100.0, engine_temp: float = 90.0):
    state = _initial_state("car", "driver", "YOU", True)
    state.tire_pct = tire_pct
    state.engine_temp = engine_temp
    return state


if __name__ == "__main__":
    unittest.main()
