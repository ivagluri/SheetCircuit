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
        self.assertEqual(state.garage, [])
        self.assertEqual(state.hired_drivers, [])

    def test_save_load_round_trip_preserves_nested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            car = load_cars()[0]
            driver = load_drivers()[0]
            car.condition.engine_condition = 57.5
            car.tune.brake_bias = 0.61
            state = GameState(money=7150, week=3, garage=[car], hired_drivers=[driver])
            save_path = Path(tmpdir) / "save.json"

            save_game(state, save_path)
            loaded = load_game(save_path)

            self.assertEqual(loaded.money, 7150)
            self.assertEqual(loaded.week, 3)
            self.assertEqual(asdict(loaded.garage[0]), asdict(car))
            self.assertEqual(asdict(loaded.hired_drivers[0]), asdict(driver))

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
