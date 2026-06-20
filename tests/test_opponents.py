from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from game.effective_stats import class_rating
from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks
from game.opponents import EventEntryError, build_opponent_grid, validate_event_entry
from game.race_session import enter_event
from game.simulation import simulate_race


class OpponentGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}
        self.events = {event.id: event for event in load_events()}
        self.drivers = {driver.id: driver for driver in load_drivers()}
        self.tracks = {track.id: track for track in load_tracks()}
        self.parts = load_parts()

    def test_sunday_cup_opponents_respect_event_restrictions(self) -> None:
        event = self.events["sunday_cup"]
        track = self.tracks[event.track_id]
        opponent_cars, _drivers, entries = build_opponent_grid(
            event, "kanto_k660", self.drivers["driver_novak"], self.cars, self.parts, track, seed=1
        )

        self.assertEqual(len(entries), event.opponent_count)
        for car_id, _driver_id in entries:
            car = opponent_cars[car_id]
            self.assertEqual(car.identity.car_class, "E")
            self.assertLessEqual(car.powertrain.power_hp, 140)

    def test_player_entry_restrictions_are_enforced(self) -> None:
        event = self.events["sunday_cup"]

        with self.assertRaises(EventEntryError):
            validate_event_entry(self.cars["detroit_v8"], event, self.parts)

    def test_enter_event_uses_generated_opponent_ids(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=2)
        opponent_ids = [car.car_id for car in session.cars if not car.is_player]

        self.assertEqual(len(opponent_ids), len(set(opponent_ids)))
        self.assertTrue(all(car_id.startswith("opponent_") for car_id in opponent_ids))

    def test_kanto_starter_is_competitive_in_sunday_cup(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=1)

        field_size = len(result.standings)
        # Hybrid difficulty: the starter should be competitive (top half of the
        # field) rather than dominant or hopeless.
        self.assertLessEqual(result.player_position, field_size // 2)

    def test_field_is_tight_not_a_blowout(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=1)

        spread = max(s.total_time for s in result.standings) - min(s.total_time for s in result.standings)
        base = self.tracks["maple_short"].base_lap_time
        # Whole field finishes within a fraction of a single lap of each other.
        self.assertLess(spread, base * 0.25)

    def test_rivals_are_not_all_identical(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "clubman_trial", "kanto_k660", "driver_bellamy", seed=3)
        rival_driver_stats = {
            (
                session.driver_roster[car.driver_id].pace,
                session.driver_roster[car.driver_id].consistency,
                session.driver_roster[car.driver_id].racecraft,
            )
            for car in session.cars
            if not car.is_player
        }

        # The field is a spread of real drivers, not seven scalar-adjusted clones.
        self.assertGreater(len(rival_driver_stats), 1)

    def test_s_event_field_uses_s_tier_cars(self) -> None:
        event = self.events["cresta_top_speed"]
        track = self.tracks[event.track_id]
        opponent_cars, _drivers, entries = build_opponent_grid(
            event, "blackpool_twelve", self.drivers["driver_bellamy"], self.cars, self.parts, track, seed=4
        )

        self.assertEqual(len(entries), event.opponent_count)
        self.assertTrue(all(opponent_cars[car_id].identity.car_class == "S" for car_id, _driver_id in entries))
        self.assertTrue(all(class_rating(opponent_cars[car_id], self.parts) >= 330 for car_id, _driver_id in entries))

    def test_higher_rival_skill_makes_race_harder(self) -> None:
        low_skill_events = deepcopy(list(self.events.values()))
        high_skill_events = deepcopy(list(self.events.values()))
        for event in low_skill_events:
            if event.id == "sunday_cup":
                event.rival_skill = 20
        for event in high_skill_events:
            if event.id == "sunday_cup":
                event.rival_skill = 90

        def average_position(events) -> float:
            positions = []
            with patch("game.simulation.load_events", return_value=events):
                for seed in range(1, 8):
                    state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
                    result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=seed)
                    positions.append(result.player_position)
            return sum(positions) / len(positions)

        self.assertLess(average_position(low_skill_events), average_position(high_skill_events))

    def test_race_states_do_not_have_performance_scalar(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=2)

        self.assertTrue(all(not hasattr(car, "performance_scalar") for car in session.cars))


if __name__ == "__main__":
    unittest.main()
