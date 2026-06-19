from __future__ import annotations

from copy import deepcopy
import unittest

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
        for car_id, _driver_id, _scalar in entries:
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
        rival_scalars = {round(car.performance_scalar, 3) for car in session.cars if not car.is_player}

        # The field is a spread of strengths, not seven clones.
        self.assertGreater(len(rival_scalars), 1)


if __name__ == "__main__":
    unittest.main()
