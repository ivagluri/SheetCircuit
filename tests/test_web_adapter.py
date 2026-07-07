from __future__ import annotations

import json
import unittest
from unittest import TestCase

import interfaces.cli as cli
from constants import SCHEMA_VERSION
from game.loader import load_drivers
from interfaces.web import (
    MODE_MENU,
    MODE_RACE,
    MODE_RACE_CAR,
    MODE_RACE_EVENT,
    MODE_RACE_RESULT,
    MODE_TUNE_CAR,
    MODE_TUNE_SECTIONS,
    WebGame,
    install_stdin_guard,
)


def make_game(seed: int = 42) -> WebGame:
    cli._SCREEN_SORTS.clear()
    return WebGame(race_seed=seed)


def meta(game: WebGame) -> dict:
    return json.loads(game.ui_meta())


def run_race_to_finish(game: WebGame, max_ticks: int = 20000) -> str:
    out = ""
    for _ in range(max_ticks):
        if meta(game)["mode"] != MODE_RACE:
            break
        out = game.race_tick()
    return out


class WebNavigationTests(TestCase):
    def test_initial_render_shows_garage(self) -> None:
        game = make_game()
        out = game.render()
        self.assertIn("SheetCircuit", out)
        self.assertIn("Garage", out)
        self.assertIn("Torino 500R", out)  # the car's display name (ID column removed)
        self.assertEqual(meta(game)["mode"], MODE_MENU)

    def test_hotkeys_switch_screens(self) -> None:
        game = make_game()
        for key, screen, marker in [
            ("e", "events", "Events"),
            ("d", "drivers", "Drivers"),
            ("m", "market", "Market"),
            ("h", "help", "Menu Hotkeys"),
            ("g", "garage", "Garage"),
        ]:
            out = game.handle_input(key)
            self.assertEqual(meta(game)["screen"], screen)
            self.assertIn(marker, out)

    def test_number_opens_detail_and_enter_returns(self) -> None:
        game = make_game()
        game.handle_input("d")
        out = game.handle_input("1")
        self.assertIn("Driver Stats", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)
        out = game.handle_input("")
        self.assertIn("Your Team", out)

    def test_unknown_command_reports_message(self) -> None:
        game = make_game()
        out = game.handle_input("frobnicate")
        self.assertIn("Unknown command", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)

    def test_sort_persists_in_table_title(self) -> None:
        game = make_game()
        game.handle_input("m")
        out = game.handle_input("sort hp desc")
        self.assertIn("sorted by", out)
        cli._SCREEN_SORTS.clear()

    def test_quit_shows_browser_hint(self) -> None:
        game = make_game()
        out = game.handle_input("q")
        self.assertIn("close the tab", out)


class WebPickerTests(TestCase):
    def test_buy_picker_insufficient_funds_surfaces_error(self) -> None:
        game = make_game()
        game.handle_input("m")
        game.handle_input("sort price desc")
        game.handle_input("buy")
        out = game.handle_input("1")
        self.assertIn("Error:", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)
        self.assertEqual(len(game.state.garage), 1)
        cli._SCREEN_SORTS.clear()

    def test_buy_picker_purchase_adds_car(self) -> None:
        game = make_game()
        game.handle_input("m")
        game.handle_input("sort price asc")
        money = game.state.money
        game.handle_input("buy")
        out = game.handle_input("1")
        self.assertIn("Bought", out)
        self.assertEqual(len(game.state.garage), 2)
        self.assertLess(game.state.money, money)
        cli._SCREEN_SORTS.clear()

    def test_race_picker_event_step_accepts_sort(self) -> None:
        from game.loader import load_events
        from game.sorting import SortSpec, sort_items

        game = make_game()
        top_fee_event = sort_items("events", load_events(), SortSpec("fee", True))[0]
        game.handle_input("race")
        out = game.handle_input("sort fee desc")
        self.assertIn("sorted by Entry Fee desc", out)
        self.assertEqual(meta(game)["mode"], MODE_RACE_EVENT)
        game.handle_input("1")
        self.assertEqual(meta(game)["mode"], MODE_RACE_CAR)
        self.assertEqual(game._entry_event_id, top_fee_event.id)
        cli._SCREEN_SORTS.clear()

    def test_tune_car_step_ignores_sort(self) -> None:
        # The tune flow is deliberately exempt from picker sorting.
        game = make_game()
        game.handle_input("tune")
        out = game.handle_input("sort hp desc")
        self.assertIn("Unknown car", out)
        self.assertEqual(meta(game)["mode"], MODE_TUNE_CAR)
        self.assertNotIn("garage", cli._SCREEN_SORTS)

    def test_sell_flow_increases_money(self) -> None:
        game = make_game()
        money = game.state.money
        out = game.handle_input("sell")
        self.assertIn("Sell Car", out)
        self.assertEqual(meta(game)["prompt_label"], "Sell")
        out = game.handle_input("1")
        self.assertIn("Sold torino_500r", out)
        self.assertEqual(len(game.state.garage), 0)
        self.assertGreater(game.state.money, money)

    def test_sell_with_empty_garage_reports(self) -> None:
        game = make_game()
        game.handle_input("sell")
        game.handle_input("1")
        out = game.handle_input("sell")
        self.assertIn("Garage is empty", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)

    def test_repair_flow(self) -> None:
        game = make_game()
        game.handle_input("p")
        out = game.handle_input("torino_500r")
        self.assertIn("Repaired torino_500r", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)

    def test_hire_and_fire_flow(self) -> None:
        game = make_game()
        game.handle_input("hire")
        out = game.handle_input("1")
        self.assertIn("Hired", out)
        self.assertEqual(len(game.state.hired_drivers), 2)
        game.handle_input("fire")
        out = game.handle_input("2")
        self.assertIn("Released", out)
        self.assertEqual(len(game.state.hired_drivers), 1)

    def test_picker_cancel_returns_to_menu(self) -> None:
        game = make_game()
        for command in ["sell", "repair", "tune", "hire", "fire", "race", "buy"]:
            if command == "buy":
                game.handle_input("m")
            game.handle_input(command)
            out = game.handle_input("q")
            self.assertIn("Cancelled", out)
            self.assertEqual(meta(game)["mode"], MODE_MENU, command)

    def test_picker_unknown_choice_reprompts(self) -> None:
        game = make_game()
        game.handle_input("sell")
        out = game.handle_input("zzz")
        self.assertIn("Unknown sell: zzz", out)
        self.assertEqual(meta(game)["mode"], "sell")
        game.handle_input("q")

    def test_ext_picker_shows_extended_specs(self) -> None:
        game = make_game()
        out = game.handle_input("ext")
        self.assertIn("Extended Specs", out)
        out = game.handle_input("1")
        self.assertIn("torino_500r", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)
        out = game.handle_input("ext torino_500r")
        self.assertIn("Aerodynamics", out)


class WebTuneTests(TestCase):
    # Section-based tune editor (creator look and feel): car -> sections -> fields
    # -> value. Edits stage into a draft; [W] applies atomically.

    def _open_tyres_section(self, game: WebGame) -> str:
        game.handle_input("t")
        out = game.handle_input("1")  # car
        self.assertEqual(meta(game)["mode"], MODE_TUNE_SECTIONS)
        self.assertIn("Setup Sections", out)
        out = game.handle_input("1")  # Tyres
        self.assertEqual(meta(game)["mode"], "tune_field")
        self.assertIn("Tyre Pressure (F)", out)
        return out

    def test_tune_numeric_field_staged_then_applied(self) -> None:
        game = make_game()
        self._open_tyres_section(game)
        out = game.handle_input("tire_pressure_front")
        self.assertEqual(meta(game)["mode"], "tune_value")
        self.assertIn("Value (", meta(game)["prompt_label"])
        out = game.handle_input("2.2")
        self.assertEqual(meta(game)["mode"], "tune_field")
        self.assertIn("2.2", out)  # staged column
        self.assertNotEqual(game.state.garage[0].tune.tire_pressure_front, 2.2)  # not yet applied
        game.handle_input("b")  # back to sections
        out = game.handle_input("w")  # apply
        self.assertIn("Setup applied", out)
        self.assertEqual(game.state.garage[0].tune.tire_pressure_front, 2.2)
        self.assertEqual(meta(game)["mode"], MODE_TUNE_SECTIONS)

    def test_tune_option_field_by_number(self) -> None:
        game = make_game()
        game.handle_input("buy part torino_500r sports_ecu install")
        game.handle_input("t")
        game.handle_input("1")
        game.handle_input("2")  # ECU
        out = game.handle_input("engine map")
        self.assertEqual(meta(game)["prompt_label"], "Option")
        self.assertIn("Engine Map Options", out)
        game.handle_input("3")  # hot: staged
        game.handle_input("b")
        out = game.handle_input("w")
        self.assertIn("Setup applied", out)
        self.assertEqual(game.state.garage[0].tune.engine_map, "hot")

    def test_tune_unknown_option_stays_in_editor(self) -> None:
        game = make_game()
        game.handle_input("t")
        game.handle_input("1")
        game.handle_input("2")
        game.handle_input("engine map")
        out = game.handle_input("warp")
        self.assertIn("Rejected: Unknown option", out)
        self.assertEqual(meta(game)["mode"], "tune_field")

    def test_tune_value_out_of_range_stays_in_editor(self) -> None:
        game = make_game()
        self._open_tyres_section(game)
        game.handle_input("tire_pressure_front")
        out = game.handle_input("99")
        self.assertIn("Rejected:", out)
        self.assertEqual(meta(game)["mode"], "tune_field")
        self.assertEqual(game._tune_draft, {})

    def test_tune_empty_value_stages_nothing(self) -> None:
        game = make_game()
        self._open_tyres_section(game)
        game.handle_input("tire_pressure_front")
        out = game.handle_input("")
        self.assertIn("No change staged", out)
        self.assertEqual(meta(game)["mode"], "tune_field")

    def test_tune_exit_with_staged_changes_asks_and_discards(self) -> None:
        game = make_game()
        self._open_tyres_section(game)
        game.handle_input("tire_pressure_front")
        game.handle_input("2.2")
        game.handle_input("b")  # back to sections with a staged change
        out = game.handle_input("q")
        self.assertEqual(meta(game)["mode"], "tune_exit")
        self.assertIn("staged change", out)
        out = game.handle_input("d")
        self.assertEqual(meta(game)["mode"], MODE_MENU)
        self.assertIn("Discarded", out)
        self.assertNotEqual(game.state.garage[0].tune.tire_pressure_front, 2.2)

    def test_tune_preview_shows_deltas(self) -> None:
        game = make_game()
        game.handle_input("buy part torino_500r sports_ecu install")
        game.handle_input("t")
        game.handle_input("1")
        game.handle_input("2")  # ECU
        game.handle_input("engine map")
        out = game.handle_input("4")  # qualifying: more power
        self.assertIn("→", out)  # before→after readout
        game.handle_input("b")
        game.handle_input("q")
        game.handle_input("d")

    def test_direct_tune_command(self) -> None:
        game = make_game()
        game.handle_input("buy part torino_500r sports_ecu install")
        out = game.handle_input("tune torino_500r engine_map hot")
        self.assertIn("Updated engine_map", out)
        self.assertEqual(game.state.garage[0].tune.engine_map, "hot")

    def test_upgrade_flow_buys_and_installs_part(self) -> None:
        game = make_game()
        out = game.handle_input("u")
        self.assertEqual(meta(game)["mode"], "upgrades_car")
        self.assertIn("Upgrades", out)
        game.handle_input("1")
        self.assertEqual(meta(game)["mode"], "upgrades_slot")
        game.handle_input("brake_controller")
        self.assertEqual(meta(game)["mode"], "upgrades_part")
        out = game.handle_input("brake_controller")
        self.assertEqual(meta(game)["mode"], "upgrades_action")
        self.assertIn("Unlocks", out)
        self.assertIn("unlocks Brake Balance", out)
        out = game.handle_input("i")
        self.assertIn("Bought Brake Balance Controller and installed", out)
        self.assertIn("brake_controller", game.state.garage[0].owned_parts)
        self.assertIn("brake_controller", game.state.garage[0].installed_parts)


class WebRaceTests(TestCase):
    def enter_first_event(self, game: WebGame) -> None:
        game.handle_input("r")
        game.handle_input("sunday_cup")
        game.handle_input("1")
        game.handle_input("1")

    def test_race_entry_steps(self) -> None:
        game = make_game()
        out = game.handle_input("r")
        self.assertIn("Race Entry", out)
        self.assertIn("Available Events", out)
        out = game.handle_input("sunday_cup")
        self.assertEqual(meta(game)["mode"], "race_car")
        out = game.handle_input("1")
        self.assertEqual(meta(game)["mode"], "race_driver")
        out = game.handle_input("1")
        self.assertTrue(meta(game)["in_race"])
        # The lap bar dropped its inline key hints (the CLI footer owns them now);
        # it still shows progress, the active pace command, and the speed.
        self.assertIn("[normal]", out)
        self.assertIn("1x", out)

    def test_seeded_race_runs_to_result_and_pays_prize(self) -> None:
        game = make_game(seed=7)
        money_before = game.state.money
        self.enter_first_event(game)
        out = run_race_to_finish(game)
        self.assertEqual(meta(game)["mode"], MODE_RACE_RESULT)
        self.assertIn("Race finished. Prize: $", out)
        self.assertNotEqual(game.state.money, money_before)
        out = game.handle_input("")
        self.assertEqual(meta(game)["mode"], MODE_MENU)
        self.assertEqual(meta(game)["screen"], "garage")

    def test_race_result_view_is_compact(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        out = run_race_to_finish(game)
        self.assertNotIn("[G]arage", out)
        self.assertIn("Team Progress", out)
        self.assertIn("Car Condition", out)
        self.assertLessEqual(len(out.splitlines()), 45)

    def test_race_end_command_simulates_to_completion(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        game.race_tick()
        out = game.handle_input("x")
        self.assertIn("Race simulated to completion", out)
        self.assertIn("Race finished. Prize: $", out)
        self.assertEqual(meta(game)["mode"], MODE_RACE_RESULT)

    def test_race_speed_cycle_wraps(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        speeds = []
        for _ in range(4):
            game.handle_input("f")
            speeds.append(meta(game)["speed_mult"])
        self.assertEqual(speeds, [2.0, 4.0, 8.0, 1.0])

    def test_race_pace_command_is_pending_then_applied(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        out = game.handle_input("push")
        self.assertIn("next: push", out)
        game.race_tick()
        self.assertEqual(game._current_command, "push")

    def test_pit_is_one_shot_and_resumes_prior_pace(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        game.handle_input("push")
        game.race_tick()
        game.handle_input("pit")
        saw_pit = False
        for _ in range(20000):
            if meta(game)["mode"] != MODE_RACE:
                break
            game.race_tick()
            if game._current_command == "pit":
                saw_pit = True
            if saw_pit and game._current_command != "pit":
                break
        self.assertTrue(saw_pit)
        if meta(game)["mode"] == MODE_RACE:
            self.assertEqual(game._current_command, "push")

    def test_race_help_pauses_until_next_input(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        game.race_tick()
        out = game.handle_input("?")
        self.assertIn("Race Commands", out)
        self.assertTrue(meta(game)["race_paused"])
        self.assertEqual(game.race_tick(), out)
        game.handle_input("")
        self.assertFalse(meta(game)["race_paused"])

    def test_next_lap_fast_forwards(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        game.race_tick()
        lap_ticks = game.session.current_sub_tick
        game.handle_input("n")
        game.race_tick()
        if meta(game)["mode"] == MODE_RACE:
            self.assertTrue(game._last_tick.is_lap_end or game.session.current_sub_tick < lap_ticks)

    def test_unknown_race_command_is_ignored(self) -> None:
        game = make_game(seed=7)
        self.enter_first_event(game)
        game.handle_input("frobnicate")
        self.assertIsNone(game._pending_command)
        self.assertTrue(meta(game)["in_race"])

    def test_direct_enter_command_starts_race(self) -> None:
        game = make_game(seed=7)
        driver = load_drivers()[0]
        game.handle_input(f"enter sunday_cup torino_500r {driver.id}")
        self.assertTrue(meta(game)["in_race"])


class WebSaveLoadTests(TestCase):
    def test_save_sets_js_request_and_confirm_clears_it(self) -> None:
        game = make_game()
        out = game.handle_input("save")
        self.assertIn("Saving to browser storage", out)
        self.assertEqual(meta(game)["js_request"], "save")
        out = game.confirm_save()
        self.assertIn("Saved to browser storage", out)
        self.assertIsNone(meta(game)["js_request"])

    def test_export_import_round_trip(self) -> None:
        game = make_game()
        game.handle_input("sell")
        game.handle_input("1")
        game.state.team_xp = 145
        game.state.event_progress["sunday_cup"] = {
            "starts": 2,
            "best_position": 1,
            "wins": 1,
            "podiums": 2,
            "best_time_s": 382.4,
        }
        payload = game.export_save()
        data = json.loads(payload)
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        other = make_game()
        out = other.import_save(payload)
        self.assertIn("Loaded from browser storage", out)
        self.assertEqual(other.state.money, game.state.money)
        self.assertEqual(len(other.state.garage), 0)
        self.assertEqual(other.state.team_xp, 145)
        self.assertEqual(other.state.event_progress["sunday_cup"]["wins"], 1)

    def test_import_empty_payload_reports_no_save(self) -> None:
        game = make_game()
        out = game.import_save("")
        self.assertIn("No saved game found", out)
        self.assertEqual(meta(game)["mode"], MODE_MENU)

    def test_import_wrong_version_reports_error(self) -> None:
        game = make_game()
        payload = json.dumps({"schema_version": -1, "game_state": {}})
        out = game.import_save(payload)
        self.assertIn("Unsupported save schema_version", out)

    def test_import_malformed_json_reports_error(self) -> None:
        game = make_game()
        out = game.import_save("{not json")
        self.assertIn("Could not read save", out)

    def test_load_sets_js_request(self) -> None:
        game = make_game()
        game.handle_input("load")
        self.assertEqual(meta(game)["js_request"], "load")
        game.import_save(game.export_save())
        self.assertIsNone(meta(game)["js_request"])


class WebCompendiumTests(TestCase):
    def test_hotkey_opens_index(self) -> None:
        game = make_game()
        out = game.handle_input("c")
        self.assertEqual(meta(game)["screen"], "compendium")
        self.assertIn("Chapters", out)

    def test_drill_into_chapter_then_section_then_back(self) -> None:
        game = make_game()
        game.handle_input("c")
        out = game.handle_input("1")  # Cars chapter
        self.assertTrue(meta(game)["screen"].startswith("compendium:cars"))
        self.assertIn("Sections", out)
        game.handle_input("compendium cars tune")
        self.assertEqual(meta(game)["screen"], "compendium:cars/Tune")
        out = game.handle_input("b")  # back to the Cars chapter
        self.assertEqual(meta(game)["screen"], "compendium:cars")
        game.handle_input("b")  # back to the index
        out = game.handle_input("b")  # out of the compendium entirely
        self.assertEqual(meta(game)["screen"], "garage")

    def test_direct_jump_by_field_name(self) -> None:
        game = make_game()
        out = game.handle_input("compendium final_drive")
        self.assertIn("final_drive", out)
        self.assertTrue(meta(game)["screen"].startswith("compendium?"))


class WebStdinGuardTests(TestCase):
    def test_stdin_guard_raises_instead_of_blocking(self) -> None:
        import sys

        original = sys.stdin
        try:
            install_stdin_guard()
            self.assertFalse(sys.stdin.isatty())
            with self.assertRaises(RuntimeError):
                sys.stdin.readline()
        finally:
            sys.stdin = original


if __name__ == "__main__":
    unittest.main()
