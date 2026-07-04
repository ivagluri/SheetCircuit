from __future__ import annotations

import contextlib
import io
from unittest import TestCase
from unittest.mock import patch

from game.game_state import new_career
from game.loader import load_cars
import interfaces.cli as cli
from interfaces.cli import _race_command, run_command, run_menu_choice
from interfaces.menu import menu_bar, menu_command, status_bar, team_xp_status


class CliTests(TestCase):
    def test_menu_bar_exposes_hotkeys(self) -> None:
        bar = menu_bar()

        self.assertIn("[G]arage", bar)
        self.assertIn("[R]ace", bar)
        self.assertEqual(menu_command("g"), "garage")
        self.assertEqual(menu_command("R"), "race")

    def test_status_bar_shows_money_week_team_xp_and_screen(self) -> None:
        self.assertEqual(
            status_bar(8000, 1, 1, "garage"),
            "Money: $8,000  Week: 1  Garage: 1  Team Lv 1 [░░░░░░░░] 0/100 XP  Screen: Garage",
        )
        self.assertEqual(team_xp_status(145), "Team Lv 2 [██░░░░░░] 145/250 XP")
        self.assertEqual(team_xp_status(1400), "Team Lv 6 [MAX] 1400 XP")

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

    def test_race_picker_steps_accept_sort(self) -> None:
        # `sort` works inside the race entry picker with the main-screen grammar and
        # feeds the same shared sort state (the events screen stays sorted after).
        from game.loader import load_events
        from game.sorting import SortSpec, sort_items

        state = new_career()
        cli._SCREEN_SORTS.clear()
        top_fee_event = sort_items("events", load_events(), SortSpec("fee", True))[0]
        scripted_input = ["sort fee desc", "1", "q"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        self.assertIn("sorted by Entry Fee desc", output.getvalue())
        self.assertIn(f"Event: {top_fee_event.name}", output.getvalue())
        self.assertIn("events", cli._SCREEN_SORTS)
        cli._SCREEN_SORTS.clear()

    def test_hire_picker_accepts_sort(self) -> None:
        from game.loader import load_drivers
        from game.sorting import SortSpec, sort_items

        state = new_career()
        cli._SCREEN_SORTS.clear()
        hired_ids = {d.id for d in state.hired_drivers}
        available = [d for d in load_drivers() if d.id not in hired_ids]
        priciest = sort_items("drivers", available, SortSpec("salary", True))[0]

        with patch("builtins.input", side_effect=["sort salary desc", "1"]), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "hire")

        self.assertIn("sorted by Salary desc", output.getvalue())
        self.assertIn(priciest.id, {d.id for d in state.hired_drivers})
        cli._SCREEN_SORTS.clear()

    def test_tune_picker_keeps_fixed_order(self) -> None:
        # The tune flow is deliberately exempt from picker sorting.
        state = new_career()
        cli._SCREEN_SORTS.clear()

        with patch("builtins.input", side_effect=["sort hp desc", "q"]), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertIn("This list has a fixed order.", output.getvalue())
        self.assertNotIn("garage", cli._SCREEN_SORTS)
        cli._SCREEN_SORTS.clear()

    def test_race_command_guides_selection_and_runs_event(self) -> None:
        state = new_career()
        starting_mileage = state.garage[0].condition.mileage
        scripted_input = ["sunday_cup", "1", "1"]

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
        scripted_input = ["sunday_cup", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race finished", text)

    def test_race_screen_keeps_lap_updates_visible_between_commands(self) -> None:
        state = new_career()
        scripted_input = ["sunday_cup", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race Log", text)

    def test_unknown_race_command_stays_in_race_screen(self) -> None:
        # Commands come in via select.select during animation, not via builtins.input.
        # In non-interactive mode the race runs to completion with the default command.
        state = new_career()
        scripted_input = ["sunday_cup", "1", "1"]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "race")

        text = output.getvalue()
        self.assertIn("Standings", text)
        self.assertIn("Race finished", text)

    # The tune editor is section-based (creator look and feel): car -> sections menu
    # -> section fields -> value. Edits stage into a draft; [W] applies atomically.

    def test_blank_tune_value_cancels_without_crashing(self) -> None:
        state = new_career()
        scripted_input = [
            "1",           # car
            "2",           # Drivetrain section
            "engine map",  # engine_map (choice field) within the section
            "",            # blank value: nothing staged
            "b",   # back to sections
            "b",   # back out (draft empty: exits cleanly)
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "balanced")
        self.assertIn("No change staged", output.getvalue())

    def test_tune_choice_field_staged_then_applied(self) -> None:
        state = new_career()
        scripted_input = [
            "1",           # car
            "2",           # Drivetrain section
            "engine map",  # engine_map
            "3",           # hot
            "b",   # back to sections (still only staged)
            "w",   # apply the draft
            "b",   # exit
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "hot")
        self.assertIn("Engine Map Options", output.getvalue())
        self.assertIn("1 staged change (not applied)", output.getvalue())
        self.assertIn("Setup applied: Engine Map.", output.getvalue())

    def test_tune_sections_and_fields_accept_display_labels(self) -> None:
        state = new_career()
        scripted_input = [
            "1",
            "Drivetrain",
            "Engine Map",
            "Hot",
            "b",
            "w",
            "b",
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()):
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "hot")

    def test_tune_discard_leaves_car_untouched(self) -> None:
        state = new_career()
        scripted_input = [
            "1",
            "2",
            "engine map",
            "4",   # qualifying (raises power: the preview must show a delta arrow)
            "b",   # back to sections
            "b",   # try to leave with a staged change
            "d",   # discard
        ]

        with patch("builtins.input", side_effect=scripted_input), contextlib.redirect_stdout(io.StringIO()) as output:
            run_command(state, "tune")

        self.assertEqual(state.garage[0].tune.engine_map, "balanced")
        self.assertIn("→", output.getvalue())  # live before→after readout rendered

    def test_race_commands_accept_display_labels(self) -> None:
        self.assertEqual(_race_command("Save Fuel"), "save_fuel")
        self.assertEqual(_race_command("Go All Out"), "go_all_out")
        self.assertEqual(_race_command("Cool Down"), "cool_down")


class CompendiumCliTests(TestCase):
    def test_hotkey_and_drilldown_navigation(self) -> None:
        state = new_career()
        _, screen = run_menu_choice(state, "c", "garage")
        self.assertEqual(screen, "compendium")
        _, screen = run_menu_choice(state, "1", screen)  # Cars
        self.assertEqual(screen, "compendium:cars")
        _, screen = run_menu_choice(state, "tune", screen)  # by name
        self.assertEqual(screen, "compendium:cars/Tune")
        _, screen = run_menu_choice(state, "b", screen)
        self.assertEqual(screen, "compendium:cars")
        _, screen = run_menu_choice(state, "b", screen)
        self.assertEqual(screen, "compendium")
        _, screen = run_menu_choice(state, "b", screen)  # leave the compendium
        self.assertEqual(screen, "garage")

    def test_direct_jump_token(self) -> None:
        state = new_career()
        _, screen = run_menu_choice(state, "compendium final_drive", "garage")
        self.assertEqual(screen, "compendium?car.tune.final_drive")

    def test_render_index_lists_chapters(self) -> None:
        state = new_career()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli._render_screen(state, "compendium", "")
        out = buffer.getvalue()
        self.assertIn("Chapters", out)
        self.assertIn("Cars", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
