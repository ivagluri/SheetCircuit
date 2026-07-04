from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase, mock

from editor import app as editor_app
from editor.web import (
    MODE_EDIT,
    MODE_FIELD,
    MODE_GUARD,
    MODE_MENU,
    MODE_OVERWRITE,
    MODE_SAVE_AS,
    MODE_SECTION,
    MODE_SEGMENT,
    MODE_SEGMENTS,
    MODE_SIM_TRACK,
    WebCreator,
    strip_markup,
)
from game.loader import car_from_dict, event_from_dict, resolve_race, track_from_dict

REAL_DATA = editor_app.DATA_ROOT


class CreatorWebCase(TestCase):
    """All cases run against a temp DATA_ROOT so saves never touch repo data/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        for subdir in ("cars", "tracks", "events"):
            (root / subdir).mkdir()
        shutil.copy(REAL_DATA / "cars" / "torino_500r.json", root / "cars")
        shutil.copy(REAL_DATA / "tracks" / "maple_short.json", root / "tracks")
        for subdir in ("parts", "drivers"):
            shutil.copytree(REAL_DATA / subdir, root / subdir)
        # The adapter reads editor_app.DATA_ROOT dynamically, so one patch covers
        # its pickers, save_draft, and the explicit-root refresh. game.loader's
        # load_* defaults are bound at import and keep reading repo data
        # read-only (previews, event validation) — same split the browser
        # avoids by having a single /app/data root.
        self._patch = mock.patch.object(editor_app, "DATA_ROOT", root)
        self._patch.start()
        self.root = root
        self.creator = WebCreator()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def meta(self) -> dict:
        return json.loads(self.creator.ui_meta())

    def drive(self, *inputs: str) -> str:
        out = ""
        for raw in inputs:
            out = self.creator.handle_input(raw)
        return out

    def new_car(self, archetype: str = "1") -> None:
        self.drive("c", archetype)

    def set_field(self, section: str, field: str, value: str) -> str:
        return self.drive(section, field, value, "b")

    def save_named_car(self, name: str = "web_test_car") -> str:
        self.new_car()
        self.set_field("2", "1", name)  # Identity → id
        return self.drive("w")


class MenuAndFlowTests(CreatorWebCase):
    def test_initial_menu_renders_clean(self) -> None:
        out = self.creator.render()
        self.assertIn("SheetCircuit Creator", out)
        self.assertIn("[C] New car", out)
        self.assertNotIn("[/", out)
        self.assertEqual(self.meta()["mode"], MODE_MENU)

    def test_new_car_archetype_flow(self) -> None:
        out = self.creator.handle_input("c")
        self.assertIn("Clone existing car", out)
        out = self.creator.handle_input("2")
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.assertIn("Editing car", out)
        self.assertFalse(self.meta()["dirty"])

    def test_edit_field_updates_draft_and_previews(self) -> None:
        self.new_car()
        out = self.drive("1", "1", "999")
        self.assertEqual(self.meta()["mode"], MODE_SECTION)
        self.assertEqual(self.creator.draft["powertrain"]["power_hp"], 999)
        self.assertIn("est. lap", out)
        out = self.drive("b")
        self.assertIn("PR ", out)
        self.assertNotIn("[bold]", out)

    def test_coercion_error_stays_in_field_mode(self) -> None:
        self.new_car()
        self.drive("1", "1")
        out = self.creator.handle_input("banana")
        self.assertIn("Rejected:", out)
        self.assertEqual(self.meta()["mode"], MODE_FIELD)
        self.creator.handle_input("500")
        self.assertEqual(self.meta()["mode"], MODE_SECTION)
        self.assertEqual(self.creator.draft["powertrain"]["power_hp"], 500)

    def test_enter_keeps_current_value(self) -> None:
        self.new_car()
        before = self.creator.draft["powertrain"]["power_hp"]
        self.drive("1", "1", "")
        self.assertEqual(self.meta()["mode"], MODE_SECTION)
        self.assertEqual(self.creator.draft["powertrain"]["power_hp"], before)

    def test_open_existing_and_cancels(self) -> None:
        out = self.creator.handle_input("e")
        self.assertIn("torino_500r.json", out)
        self.creator.handle_input("1")
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.assertEqual(self.creator.draft["id"], "torino_500r")
        self.creator.handle_input("b")  # untouched → no guard
        self.assertEqual(self.meta()["mode"], MODE_MENU)
        self.creator.handle_input("e")
        self.creator.handle_input("")
        self.assertEqual(self.meta()["mode"], MODE_MENU)
        self.creator.handle_input("e")
        self.creator.handle_input("99")
        self.assertEqual(self.meta()["mode"], MODE_MENU)

    def test_clone_blanks_id(self) -> None:
        self.drive("c", "c", "1")
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.assertEqual(self.creator.draft["id"], "")
        self.assertEqual(self.creator.draft["name"], "1975 Torino 500R")
        out = self.creator.handle_input("w")
        self.assertIn("Cannot save", out)


class SaveFlowTests(CreatorWebCase):
    def test_blank_id_save_rejected(self) -> None:
        self.new_car()
        out = self.creator.handle_input("w")
        self.assertIn("Cannot save: id is required", out)
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.assertIsNone(self.creator.js_request)

    def test_save_downloads_and_roundtrips_loader(self) -> None:
        self.save_named_car("web_test_car")
        request = self.creator.js_request
        self.assertEqual(request["download"]["filename"], "web_test_car.json")
        self.assertEqual(request["stash"]["path"], "data/cars/web_test_car.json")
        payload = json.loads(request["download"]["content"])
        car = car_from_dict(payload)
        self.assertEqual(car.identity.id, "web_test_car")
        self.assertTrue((self.root / "cars" / "web_test_car.json").exists())
        self.creator.clear_js_request()
        self.assertIsNone(json.loads(self.creator.ui_meta())["js_request"])
        self.creator.handle_input("b")  # snapshot refreshed → clean exit
        self.assertEqual(self.meta()["mode"], MODE_MENU)

    def test_unsaved_guard_paths(self) -> None:
        self.new_car()
        self.set_field("1", "1", "999")
        self.creator.handle_input("b")
        self.assertEqual(self.meta()["mode"], MODE_GUARD)
        self.creator.handle_input("x")  # anything else keeps editing
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.drive("b", "d")  # discard
        self.assertEqual(self.meta()["mode"], MODE_MENU)
        self.assertEqual(list((self.root / "cars").glob("web_*.json")), [])

    def test_guard_save_exits_when_valid_and_stays_when_not(self) -> None:
        self.new_car()
        self.set_field("1", "1", "999")
        out = self.drive("b", "s")  # blank id → save fails, stay in editor
        self.assertIn("Cannot save", out)
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.set_field("2", "1", "web_guard_car")
        self.drive("b", "s")
        self.assertEqual(self.meta()["mode"], MODE_MENU)
        self.assertTrue((self.root / "cars" / "web_guard_car.json").exists())

    def test_overwrite_cancel_and_save_as(self) -> None:
        self.save_named_car("web_dup_car")
        self.creator.clear_js_request()
        out = self.creator.handle_input("w")  # same id again
        self.assertEqual(self.meta()["mode"], MODE_OVERWRITE)
        self.assertIn("web_dup_car.json exists", out)
        out = self.creator.handle_input("")  # cancel
        self.assertIn("Save cancelled", out)
        self.assertEqual(self.meta()["mode"], MODE_EDIT)
        self.assertIsNone(self.creator.js_request)
        self.drive("w", "d")  # → save-as
        self.assertEqual(self.meta()["mode"], MODE_SAVE_AS)
        self.creator.handle_input("web_dup_car_two")
        self.assertTrue((self.root / "cars" / "web_dup_car_two.json").exists())
        self.assertEqual(self.creator.js_request["download"]["filename"], "web_dup_car_two.json")
        self.assertEqual(self.creator.draft["id"], "web_dup_car_two")

    def test_save_as_onto_existing_id_loops_to_overwrite(self) -> None:
        self.save_named_car("web_first")
        self.drive("w", "d")
        self.creator.handle_input("torino_500r")  # collides with seeded car
        self.assertEqual(self.meta()["mode"], MODE_OVERWRITE)
        self.creator.handle_input("n")
        self.assertEqual(self.meta()["mode"], MODE_EDIT)

    def test_save_as_empty_or_same_id_cancels(self) -> None:
        self.save_named_car("web_same")
        self.drive("w", "d")
        out = self.creator.handle_input("web_same")
        self.assertIn("Save cancelled", out)
        self.assertEqual(self.meta()["mode"], MODE_EDIT)


class TrackAndEventTests(CreatorWebCase):
    def test_segments_add_edit_delete_normalize(self) -> None:
        self.drive("t", "s")
        self.assertEqual(self.meta()["mode"], MODE_SEGMENTS)
        self.drive("a", "b", "a", "b")  # add two segments, back out of each
        self.assertEqual(len(self.creator.draft["segments"]), 2)
        self.drive("1")  # open segment 1
        self.assertEqual(self.meta()["mode"], MODE_SEGMENT)
        # find length_pct field index
        from editor.fields import SEGMENT_FIELDS

        idx = next(i for i, s in enumerate(SEGMENT_FIELDS) if s.key == "length_pct") + 1
        self.drive(str(idx), "0.4", "b")
        self.drive("d 2")
        self.assertEqual(len(self.creator.draft["segments"]), 1)
        self.drive("n")
        total = sum(s["length_pct"] for s in self.creator.draft["segments"])
        self.assertEqual(total, 1.0)
        out = self.creator.render()
        self.assertIn("OK", strip_markup(out))

    def test_event_race_length_translation_roundtrip(self) -> None:
        self.drive("v")
        self.assertEqual(self.creator.schema.kind, "event")
        self.set_field("1", "1", "web_test_event")   # Event → id
        self.set_field("1", "2", "Web Test Event")   # name
        self.set_field("1", "3", "maple_short")      # track_id (seeded track)
        self.set_field("2", "2", "8")                # Race Length → race_value
        self.creator.handle_input("w")
        request = self.creator.js_request
        self.assertIsNotNone(request)
        payload = json.loads(request["download"]["content"])
        self.assertEqual(payload["laps"], 8)
        self.assertEqual(payload["min_team_level"], 1)
        self.assertEqual(payload["event_kind"], "ladder")
        self.assertNotIn("race_mode", payload)
        self.assertNotIn("race_value", payload)
        self.assertEqual(payload["restrictions"], {})
        event = event_from_dict(payload)
        track = track_from_dict(json.loads((self.root / "tracks" / "maple_short.json").read_text()))
        fmt = resolve_race(event, track)
        self.assertEqual(fmt.laps, 8)

    def test_open_event_translates_to_draft_and_back(self) -> None:
        (self.root / "events" / "web_evt.json").write_text(json.dumps({
            "id": "web_evt", "name": "Evt", "track_id": "maple_short",
            "car_class_limit": "E", "entry_fee": 100, "prize_money": [500],
            "min_team_level": 2, "event_kind": "open_invitational",
            "opponent_count": 3, "duration_s": 600.0, "restrictions": {"max_power_hp": 90},
        }))
        self.drive("f", "1")
        self.assertEqual(self.creator.draft["race_mode"], "duration_s")
        self.assertEqual(self.creator.draft["race_value"], 600.0)
        self.assertEqual(self.creator.draft["min_team_level"], 2)
        self.assertEqual(self.creator.draft["event_kind"], "open_invitational")
        self.assertEqual(self.creator.draft["restr_max_power_hp"], 90)
        self.creator.handle_input("w")  # unchanged → target exists → overwrite prompt
        self.assertEqual(self.meta()["mode"], MODE_OVERWRITE)
        self.creator.handle_input("y")
        payload = json.loads(self.creator.js_request["download"]["content"])
        self.assertEqual(payload["duration_s"], 600.0)
        self.assertEqual(payload["min_team_level"], 2)
        self.assertEqual(payload["event_kind"], "open_invitational")
        self.assertEqual(payload["restrictions"], {"max_power_hp": 90})

    def test_track_save_refreshes_event_choices_and_sim_tracks(self) -> None:
        source = json.loads((self.root / "tracks" / "maple_short.json").read_text())
        source["id"] = "web_new_track"
        source["name"] = "Web New Track"
        (self.root / "tracks" / "web_new_track.json").write_text(json.dumps(source))
        # Simulate a fresh save-side refresh (import path exercises the same helper).
        self.creator._refresh_tracks()
        self.assertIn("web_new_track", self.creator.app.sim_tracks)
        self.drive("v", "1")  # event editor → Event section
        out = self.creator.handle_input("3")  # track_id field
        self.assertEqual(self.meta()["mode"], MODE_FIELD)
        self.assertIn("web_new_track", out)
        self.creator.handle_input("web_new_track")
        self.assertEqual(self.creator.draft["track_id"], "web_new_track")


class SimReadoutTests(CreatorWebCase):
    def test_sim_view_cycles_and_track_pick(self) -> None:
        self.new_car()
        out = self.creator.render()
        self.assertIn("view: your track", out)
        out = self.creator.handle_input("m")
        self.assertIn("your track + 2", out)
        out = self.creator.handle_input("m")
        self.assertIn("sample extremes", out)
        self.creator.handle_input("m")  # wraps
        self.assertEqual(self.creator.app.sim_mode, 0)
        out = self.creator.handle_input("g")
        self.assertEqual(self.meta()["mode"], MODE_SIM_TRACK)
        self.assertIn("Sim anchor track", out)
        first_id = list(self.creator.app.sim_tracks)[0]
        self.creator.handle_input("1")
        self.assertEqual(self.creator.app.sim_track_id, first_id)
        self.assertEqual(self.meta()["mode"], MODE_EDIT)


class ImportDeleteTests(CreatorWebCase):
    def test_import_valid_car_stashes_without_download(self) -> None:
        data = json.loads((self.root / "cars" / "torino_500r.json").read_text())
        data["id"] = "web_imported"
        out = self.creator.import_record(json.dumps(data))
        self.assertIn("Imported web_imported.json", out)
        self.assertTrue((self.root / "cars" / "web_imported.json").exists())
        self.assertIn("stash", self.creator.js_request)
        self.assertNotIn("download", self.creator.js_request)

    def test_import_rejects_bad_payloads(self) -> None:
        for payload in ("{not json", "[1, 2]", '"just a string"'):
            out = self.creator.import_record(payload)
            self.assertIn("Import failed", out)
            self.assertIsNone(self.creator.js_request)

    def test_import_invalid_record_reports_loader_error(self) -> None:
        # Track whose segments don't sum to 1.0 — rejected by the real loader.
        bad_track = {"id": "web_bad", "segments": [
            {"name": "half", "length_pct": 0.5, "tags": [], "surface": "tarmac", "condition": "dry"},
        ]}
        out = self.creator.import_record(json.dumps(bad_track))
        self.assertIn("Import failed", out)
        self.assertFalse((self.root / "tracks" / "web_bad.json").exists())

    def test_delete_record_and_containment(self) -> None:
        data = json.loads((self.root / "cars" / "torino_500r.json").read_text())
        data["id"] = "web_delete_me"
        self.creator.import_record(json.dumps(data))
        out = self.creator.delete_record("data/cars/web_delete_me.json")
        self.assertIn("Removed web_delete_me.json", out)
        self.assertFalse((self.root / "cars" / "web_delete_me.json").exists())
        out = self.creator.delete_record("data/cars/../../creator.py")
        self.assertIn("Refusing", out)
        out = self.creator.delete_record("data/cars/never_existed.json")
        self.assertIn("not found", out)


class EventRestrictionRoundTripTests(TestCase):
    """The creator now exposes all five restriction keys the engine honours;
    shipped events using the previously JSON-only keys must survive an editor
    load/save round trip unchanged."""

    def _roundtrip_restrictions(self, event_id: str) -> None:
        source = json.loads((REAL_DATA / "events" / f"{event_id}.json").read_text())
        draft = editor_app.event_json_to_draft(source)
        rebuilt = editor_app.event_draft_to_json(draft)
        self.assertEqual(rebuilt["restrictions"], source["restrictions"])

    def test_max_weight_kg_survives_roundtrip(self) -> None:
        self._roundtrip_restrictions("lightweight_challenge")

    def test_max_overall_condition_survives_roundtrip(self) -> None:
        self._roundtrip_restrictions("beater_enduro")


class MarkupStripTests(TestCase):
    def test_allowlist_strips_tags_but_keeps_literal_brackets(self) -> None:
        self.assertEqual(strip_markup("[red]bad[/red] [M] cycle · [G] track"), "bad [M] cycle · [G] track")
        self.assertEqual(strip_markup("[bold]PR 300[/bold] [s] save"), "PR 300 [s] save")


if __name__ == "__main__":
    unittest.main()
