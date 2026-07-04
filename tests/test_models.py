from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
import unittest

from game.loader import DataLoadError, event_from_dict, load_cars, load_drivers, load_events, load_parts, load_tracks
from game.models import Car, Driver, Event, Part, Track


class ModelLoadTests(unittest.TestCase):
    def test_load_all_seed_data_types(self) -> None:
        cars = load_cars()
        drivers = load_drivers()
        events = load_events()
        parts = load_parts()

        self.assertGreaterEqual(len(cars), 11)
        self.assertTrue(all(isinstance(car, Car) for car in cars))
        self.assertGreater(cars[0].powertrain.power_hp, 0)
        self.assertGreater(cars[0].condition.engine_condition, 0)
        self.assertEqual(cars[0].tune.engine_map, "balanced")
        self.assertTrue(all(isinstance(driver, Driver) for driver in drivers))
        self.assertTrue(all(isinstance(event, Event) for event in events))
        self.assertTrue(all(isinstance(part, Part) for part in parts))

    def test_track_loads_segments_and_normalized_weights(self) -> None:
        track = next(track for track in load_tracks() if track.id == "maple_short")

        self.assertIsInstance(track, Track)
        self.assertTrue(track.segments)
        self.assertLess(abs(sum(segment.length_pct for segment in track.segments) - 1.0), 0.001)
        total_weight = (
            track.power_weight
            + track.acceleration_weight
            + track.top_speed_weight
            + track.grip_weight
            + track.braking_weight
            + track.handling_weight
            + track.aero_weight
        )
        self.assertAlmostEqual(total_weight, 1.0)

    def test_malformed_json_names_offending_file(self) -> None:
        with TemporaryDataRoot() as data_root:
            (data_root / "cars").mkdir(parents=True)
            bad_file = data_root / "cars" / "bad.json"
            bad_file.write_text("{not json", encoding="utf-8")

            with self.assertRaisesRegex(DataLoadError, "bad.json"):
                load_cars(data_root)

    def test_extra_valid_json_file_is_discovered(self) -> None:
        with TemporaryDataRoot(copy_seed=True) as source_root:
            original = load_cars(source_root)
            extra = asdict(original[0])
            extra["identity"]["id"] = "extra_k660"
            extra["identity"]["name"] = "Extra K660"

            extra_file = source_root / "cars" / "extra.json"
            extra_file.write_text(json.dumps(extra), encoding="utf-8")

            loaded_ids = {car.identity.id for car in load_cars(source_root)}
            self.assertIn("extra_k660", loaded_ids)
            self.assertEqual(len(loaded_ids), len(original) + 1)

    def test_event_progression_defaults_are_inferred_and_normalized(self) -> None:
        payload = {
            "id": "progression_default",
            "name": "Progression Default",
            "track_id": "maple_short",
            "car_class_limit": "D",
            "entry_fee": 0,
            "prize_money": [0],
            "opponent_count": 3,
            "restrictions": {},
            "laps": 3,
        }

        defaulted = event_from_dict(payload)
        explicit = event_from_dict({
            **payload,
            "min_team_level": "4",
            "event_kind": " Open_Invitational ",
        })

        self.assertEqual(defaulted.min_team_level, 2)
        self.assertEqual(defaulted.event_kind, "ladder")
        self.assertEqual(explicit.min_team_level, 4)
        self.assertEqual(explicit.event_kind, "open_invitational")

    def test_event_progression_fields_are_validated(self) -> None:
        payload = {
            "id": "bad_progression",
            "name": "Bad Progression",
            "track_id": "maple_short",
            "car_class_limit": "E",
            "entry_fee": 0,
            "prize_money": [0],
            "opponent_count": 3,
            "restrictions": {},
            "laps": 3,
        }

        with self.assertRaisesRegex(DataLoadError, "event_kind"):
            event_from_dict({**payload, "event_kind": "bonus"})
        with self.assertRaisesRegex(DataLoadError, "min_team_level"):
            event_from_dict({**payload, "min_team_level": 0})

    def test_bad_track_segment_sum_raises(self) -> None:
        with TemporaryDataRoot(copy_seed=True) as source_root:
            track_file = source_root / "tracks" / "bad_track.json"
            track = json.loads((source_root / "tracks" / "maple_short.json").read_text(encoding="utf-8"))
            track["id"] = "bad_track"
            track["segments"][0]["length_pct"] = 0.50
            track_file.write_text(json.dumps(track), encoding="utf-8")

            with self.assertRaisesRegex(DataLoadError, "sum"):
                load_tracks(source_root)


class TemporaryDataRoot:
    def __init__(self, copy_seed: bool = False) -> None:
        self.copy_seed = copy_seed
        self.path: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        self.path = Path(tempfile.mkdtemp())
        if self.copy_seed:
            shutil.copytree("data", self.path / "data")
            return self.path / "data"
        return self.path / "data"

    def __exit__(self, *_args: object) -> None:
        if self.path is not None:
            shutil.rmtree(self.path)


if __name__ == "__main__":
    unittest.main()
