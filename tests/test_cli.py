from __future__ import annotations

import contextlib
import io
from unittest import TestCase
from unittest.mock import patch

from game.game_state import new_career
from game.loader import load_cars
import interfaces.cli as cli
from interfaces.cli import _race_command, run_command, run_menu_choice
from interfaces.menu import menu_bar, menu_command, status_bar


class CliTests(TestCase):
    def test_menu_bar_exposes_hotkeys(self) -> None:
        bar = menu_bar()

        self.assertIn("[G]arage", bar)
        self.assertIn("[R]ace", bar)
        self.assertEqual(menu_command("g"), "garage")
        self.assertEqual(menu_command("R"), "race")

    def test_status_bar_shows_money_week_and_screen(self) -> None:
        self.assertEqual(status_bar(8000, 1, 1, "garage"), "Money: $8,000  Week: 1  Garage: 1  Screen: Garage")

    def test_hotkey_choice_changes_screen_without_typed_command(self) -> None:
        state = new_career()

        next_state, screen = run_menu_choice(state, "e", "garage")

        self.assertIs(next_state, state)
        self.assertEqual(screen, "events")

    def test_number_on_drivers_screen_opens_driver_detail(self) -> None:
        state = new_career()

        with contextlib.redirect_stdout(io.StringIO()) as output:
            next_state, screen = run_menu_choice(state, "1", "drivers")

        self.assertIs(next_state, state)
        self.assertEqual(screen, "drivers")
        self.assertIn("Pete Novak", output.getvalue())
        self.assertIn("Driver Stats", output.getvalue())

    def test_sort_command_changes_market_selection_order(self) -> None:
        state = new_career()
        cli._SCREEN_SORTS.clear()
        strongest = max(load_cars(), key=lambda car: car.powertrain.power_hp)

        next_state, screen = run_menu_choice(state, "sort hp", "market")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            run_menu_choice(state, "1", "market")

        self.assertIs(next_state, state)
        self.assertEqual(screen, "market")
        self.assertIn(strongest.identity.name, output.getvalue())
        cli._SCREEN_SORTS.clear()

    def test_race_command_guides_selection_and_runs_event(self) -> None:
        state = new_career()
        starting_mileage = state.garage[0].condition.mileage
        scripted_input = ["1", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        self.assertIn("Race finished", output.getvalue())
        # Racing adds the event's distance to the car's mileage.
        self.assertGreater(state.garage[0].condition.mileage, starting_mileage)

    def test_help_lists_menu_typed_and_race_commands(self) -> None:
        state = new_career()

        with contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "help")

        text = output.getvalue()
        self.assertIn("Menu Hotkeys", text)
        self.assertIn("Typed Commands", text)
        self.assertIn("Car Columns", text)
        self.assertIn("Sortable Fields", text)
        self.assertIn("Race Commands", text)
        self.assertIn("PR", text)
        self.assertIn("Type", text)
        self.assertIn("derived event pace", text)
        self.assertIn("<number> / <id>", text)
        self.assertIn("enter <event_id> <car_id> <driver_id>", text)
        self.assertIn("sort <field> (asc|desc)", text)
        self.assertIn("type", text)
        self.assertIn("hp", text)
        self.assertIn("salary", text)
        self.assertIn("Save Fuel", text)

    def test_help_in_race_screen_does_not_error(self) -> None:
        # "help" typed during animation is handled asynchronously via select.select,
        # not via builtins.input — in non-interactive mode the race just completes.
        state = new_career()
        scripted_input = ["1", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race finished", text)

    def test_race_screen_keeps_lap_updates_visible_between_commands(self) -> None:
        state = new_career()
        scripted_input = ["1", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race Log", text)

    def test_unknown_race_command_stays_in_race_screen(self) -> None:
        # Commands come in via select.select during animation, not via builtins.input.
        # In non-interactive mode the race runs to completion with the default command.
        state = new_career()
        scripted_input = ["1", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race finished", text)

    def test_blank_tune_value_cancels_without_crashing(self) -> None:
        state = new_career()
        scripted_input = [
            "1",
            "12",  # engine_map (choice field) in the grouped Drivetrain section
            "",
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "balanced")
        self.assertIn("No tune change made", output.getvalue())

    def test_tune_choice_field_can_be_selected_by_number(self) -> None:
        state = new_career()
        scripted_input = [
            "1",
            "12",  # engine_map is the 12th field in the grouped tune list
            "3",
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "hot")
        self.assertIn("Engine Map Options", output.getvalue())

    def test_tune_choice_field_accepts_display_labels(self) -> None:
        state = new_career()
        scripted_input = [
            "1",
            "Engine Map",
            "Hot",
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()):
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "hot")

    def test_race_commands_accept_display_labels(self) -> None:
        self.assertEqual(_race_command("Save Fuel"), "save_fuel")
        self.assertEqual(_race_command("Go All Out"), "go_all_out")
        self.assertEqual(_race_command("Cool Down"), "cool_down")


if __name__ == "__main__":
    import unittest

    unittest.main()
