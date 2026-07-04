from __future__ import annotations

import json
from dataclasses import asdict
import tempfile
import unittest
from pathlib import Path

from constants import SCHEMA_VERSION, STARTING_MONEY, STARTING_WEEK
from game.game_state import GameState, new_game
from game.loader import load_cars, load_drivers
from game.save_load import SaveVersionError, load_game, save_game


class SaveLoadTests(unittest.TestCase):
    def test_new_game_state_starts_empty(self) -> None:
        state = new_game()

        self.assertEqual(state.money, STARTING_MONEY)
        self.assertEqual(state.week, STARTING_WEEK)
        self.assertEqual(state.team_xp, 0)
        self.assertEqual(state.garage, [])
        self.assertEqual(state.hired_drivers, [])
        self.assertEqual(state.event_progress, {})

    def test_save_load_round_trip_preserves_nested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            car = load_cars()[0]
            driver = load_drivers()[0]
            car.condition.engine_condition = 57.5
            car.tune.brake_bias = 0.61
            # In-game hard mods write into the car's stat sections; they must persist.
            car.tires.tire_compound = "semi_slick"
            car.tires.base_grip = 71
            car.chassis.weight_distribution_front = 0.49
            state = GameState(
                money=7150,
                week=3,
                team_xp=145,
                garage=[car],
                hired_drivers=[driver],
                event_progress={
                    "sunday_cup": {
                        "starts": 2,
                        "best_position": 1,
                        "wins": 1,
                        "podiums": 2,
                        "best_time_s": 382.4,
                    }
                },
            )
            save_path = Path(tmpdir) / "save.json"

            save_game(state, save_path)
            loaded = load_game(save_path)

            self.assertEqual(loaded.money, 7150)
            self.assertEqual(loaded.week, 3)
            self.assertEqual(loaded.team_xp, 145)
            self.assertEqual(asdict(loaded.garage[0]), asdict(car))
            self.assertEqual(asdict(loaded.hired_drivers[0]), asdict(driver))
            self.assertEqual(loaded.event_progress["sunday_cup"]["starts"], 2)
            self.assertEqual(loaded.event_progress["sunday_cup"]["best_position"], 1)
            self.assertEqual(loaded.event_progress["sunday_cup"]["wins"], 1)
            self.assertEqual(loaded.event_progress["sunday_cup"]["podiums"], 2)
            self.assertEqual(loaded.event_progress["sunday_cup"]["best_time_s"], 382.4)

    def test_game_state_from_dict_defaults_progression_fields(self) -> None:
        from game.save_load import game_state_from_dict

        loaded = game_state_from_dict({"money": 12, "week": 4, "garage": [], "hired_drivers": []})

        self.assertEqual(loaded.team_xp, 0)
        self.assertEqual(loaded.event_progress, {})

    def test_game_state_from_dict_normalizes_event_progress(self) -> None:
        from game.save_load import game_state_from_dict

        loaded = game_state_from_dict({
            "money": 12,
            "week": 4,
            "team_xp": 100,
            "garage": [],
            "hired_drivers": [],
            "event_progress": {"sunday_cup": {"wins": 2}},
        })

        self.assertEqual(loaded.event_progress["sunday_cup"]["starts"], 0)
        self.assertIsNone(loaded.event_progress["sunday_cup"]["best_position"])
        self.assertEqual(loaded.event_progress["sunday_cup"]["wins"], 2)
        self.assertEqual(loaded.event_progress["sunday_cup"]["podiums"], 0)
        self.assertIsNone(loaded.event_progress["sunday_cup"]["best_time_s"])

    def test_save_file_includes_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "save.json"
            save_game(new_game(), save_path)

            payload = json.loads(save_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)

    def test_mismatched_schema_version_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "save.json"
            save_game(new_game(), save_path)
            payload = json.loads(save_path.read_text(encoding="utf-8"))
            payload["schema_version"] = SCHEMA_VERSION + 1
            save_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SaveVersionError):
                load_game(save_path)


if __name__ == "__main__":
    unittest.main()
