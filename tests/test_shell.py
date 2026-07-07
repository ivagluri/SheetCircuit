"""The universal screen contract, tested at the framework level.

Every screen gets its behaviour from interfaces.shell, so these tests pin the
contract once: b/q/? are un-shadowable, the palette works from any depth, the
footer advertises exactly the live keys, and dirty screens confirm before a
jump discards their staged edits.
"""

from __future__ import annotations

import contextlib
import io
from unittest import TestCase
from unittest.mock import patch

from interfaces.shell import (
    Action,
    GoHome,
    LocalKey,
    Screen,
    Shell,
    confirm,
    dispatch,
    footer_line,
)


class DispatchTests(TestCase):
    def test_universal_keys_and_words_case_insensitive(self) -> None:
        for raw in ("b", "B", "back", "BACK"):
            self.assertEqual(dispatch(raw).kind, "back")
        for raw in ("q", "Q", "quit"):
            self.assertEqual(dispatch(raw).kind, "quit")
        for raw in ("?", "h", "help", "HELP"):
            self.assertEqual(dispatch(raw).kind, "help")

    def test_universal_keys_cannot_be_shadowed_by_local_keys(self) -> None:
        keys = (LocalKey("b", "Buy"), LocalKey("q", "Qualify"))
        self.assertEqual(dispatch("b", keys).kind, "back")
        self.assertEqual(dispatch("q", keys).kind, "quit")

    def test_local_key_matches_letter_and_words(self) -> None:
        keys = (LocalKey("y", "Buy", words=("buy",)), LocalKey("u", "Unequip", words=("unequip", "uninstall")))
        self.assertEqual(dispatch("y", keys), Action("local", "y"))
        self.assertEqual(dispatch("BUY", keys), Action("local", "y"))
        self.assertEqual(dispatch("uninstall", keys), Action("local", "u"))

    def test_palette_commands(self) -> None:
        self.assertEqual(dispatch("/save"), Action("palette", "save"))
        self.assertEqual(dispatch("/home"), Action("palette", "home"))
        self.assertEqual(dispatch("/menu"), Action("palette", "home"))
        self.assertEqual(dispatch("/ref"), Action("palette", "ref"))
        self.assertEqual(dispatch("/load"), Action("palette", "load"))
        self.assertEqual(dispatch("/quit").kind, "quit")
        self.assertEqual(dispatch("/help").kind, "help")
        self.assertEqual(dispatch("/nope").kind, "unknown_palette")

    def test_free_text_and_empty_fall_through(self) -> None:
        self.assertEqual(dispatch("kanto_k660"), Action("text", "kanto_k660"))
        self.assertEqual(dispatch("  3 "), Action("text", "3"))
        self.assertEqual(dispatch("   ").kind, "empty")


class FooterTests(TestCase):
    def test_footer_lists_local_keys_then_universal_trio(self) -> None:
        line = footer_line((LocalKey("w", "Apply"), LocalKey("u", "Unequip")))
        self.assertEqual(line, "[w Apply]  [u Unequip]  [b Back]  [? Help]  [q Quit]")

    def test_footer_without_local_keys_is_just_the_trio(self) -> None:
        self.assertEqual(footer_line(), "[b Back]  [? Help]  [q Quit]")


class ShellNavigationTests(TestCase):
    def setUp(self) -> None:
        self.shell = Shell()

    def test_breadcrumb_tracks_the_stack(self) -> None:
        self.assertEqual(self.shell.breadcrumb(), "Home")
        with self.shell.screen(Screen("Garage")):
            with self.shell.screen(Screen("Tune")):
                self.assertEqual(self.shell.breadcrumb(), "Home › Garage › Tune")
            self.assertEqual(self.shell.breadcrumb(), "Home › Garage")

    def test_back_pops_one_level(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["b"]):
                action = self.shell.prompt("Choice")
        self.assertEqual(action.kind, "back")

    def test_quit_asks_to_confirm_and_cancel_stays(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["q", "n", "1"]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Choice")
        self.assertEqual(action, Action("text", "1"))

    def test_quit_confirmed_raises_system_exit(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["q", "y"]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.shell.prompt("Choice")

    def test_home_palette_unwinds_from_any_depth(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with self.shell.screen(Screen("Upgrades")):
                with patch("builtins.input", side_effect=["/home"]), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(GoHome):
                        self.shell.prompt("Part")

    def test_home_palette_confirms_when_a_screen_is_dirty(self) -> None:
        draft = {"gear": 3}
        with self.shell.screen(Screen("Tune", dirty=lambda: bool(draft))):
            # Refusing the confirm keeps the screen; a later plain input returns.
            with patch("builtins.input", side_effect=["/home", "n", "b"]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Section")
            self.assertEqual(action.kind, "back")
            with patch("builtins.input", side_effect=["/home", "y"]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(GoHome):
                    self.shell.prompt("Section")

    def test_save_palette_calls_handler_and_keeps_prompting(self) -> None:
        saved = []
        self.shell.save_handler = lambda: saved.append(True)
        with self.shell.screen(Screen("Market")):
            with patch("builtins.input", side_effect=["/save", "2"]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Buy")
        self.assertEqual(saved, [True])
        self.assertEqual(action, Action("text", "2"))

    def test_ref_palette_opens_overlay_and_returns_in_place(self) -> None:
        opened = []
        self.shell.ref_handler = lambda: opened.append(True)
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["/ref", "3"]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Choice")
        self.assertEqual(opened, [True])
        self.assertEqual(action, Action("text", "3"))

    def test_load_palette_is_home_only(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["/load", "b"]), contextlib.redirect_stdout(io.StringIO()) as output:
                action = self.shell.prompt("Choice")
        self.assertEqual(action.kind, "back")
        self.assertIn("Home screen only", output.getvalue())

    def test_help_shows_universal_and_local_keys_then_reprompts(self) -> None:
        keys = (LocalKey("w", "Apply", description="Apply the staged setup"),)
        with self.shell.screen(Screen("Tune", keys=keys)):
            with patch("builtins.input", side_effect=["?", "b"]), contextlib.redirect_stdout(io.StringIO()) as output:
                action = self.shell.prompt("Section")
        text = output.getvalue()
        self.assertEqual(action.kind, "back")
        self.assertIn("Universal Keys", text)
        self.assertIn("Slash Palette", text)
        self.assertIn("Apply the staged setup", text)

    def test_footer_never_advertises_dead_keys(self) -> None:
        # The footer is generated from the same key table dispatch consults, so
        # every advertised key resolves and no unlisted local key exists.
        keys = (LocalKey("y", "Buy"), LocalKey("i", "Install"))
        with self.shell.screen(Screen("Upgrades", keys=keys)):
            footer = self.shell.footer()
            for key in keys:
                self.assertIn(f"[{key.key} ", footer)
                self.assertEqual(dispatch(key.key, keys).kind, "local")

    def test_empty_input_can_mean_back_for_detail_screens(self) -> None:
        with self.shell.screen(Screen("Car Detail")):
            with patch("builtins.input", side_effect=[""]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Detail", empty="back")
        self.assertEqual(action.kind, "back")

    def test_empty_input_can_be_returned_for_default_prompts(self) -> None:
        with self.shell.screen(Screen("Save")):
            with patch("builtins.input", side_effect=[""]), contextlib.redirect_stdout(io.StringIO()):
                action = self.shell.prompt("Path", empty="return")
        self.assertEqual(action.kind, "empty")

    def test_unknown_palette_command_reports_and_reprompts(self) -> None:
        with self.shell.screen(Screen("Garage")):
            with patch("builtins.input", side_effect=["/frobnicate", "b"]), contextlib.redirect_stdout(io.StringIO()) as output:
                action = self.shell.prompt("Choice")
        self.assertEqual(action.kind, "back")
        self.assertIn("Unknown command /frobnicate", output.getvalue())


class ConfirmTests(TestCase):
    def test_confirm_accepts_only_yes(self) -> None:
        with patch("builtins.input", side_effect=["y"]):
            self.assertTrue(confirm("Sure?"))
        with patch("builtins.input", side_effect=["yes"]):
            self.assertTrue(confirm("Sure?"))
        with patch("builtins.input", side_effect=[""]):
            self.assertFalse(confirm("Sure?"))
        with patch("builtins.input", side_effect=["nope"]):
            self.assertFalse(confirm("Sure?"))


if __name__ == "__main__":
    import unittest

    unittest.main()
