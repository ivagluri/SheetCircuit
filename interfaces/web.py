"""Event-driven adapter that drives the game for the browser (Pyodide) build.

The terminal CLI blocks on ``input()``; a browser cannot. ``WebGame`` re-expresses
interfaces/cli.py's blocking picker flows as an input-mode state machine with a
string-in / string-out surface: the JS shell submits one line of input at a time
and displays whatever text comes back in a <pre>. Rendering reuses cli.py's
print-based helpers with stdout captured, so the output matches the no-rich
terminal experience byte for byte. Runs under plain CPython too, which is how
the unit tests exercise it.
"""

from __future__ import annotations

import contextlib
import io
import json
import shlex

from constants import SCHEMA_VERSION, TICK_RATE_HZ
from game.actions import (
    COMPENDIUM_PREFIX,
    advance_race_action,
    advance_to_lap_end_action,
    apply_tune_draft,
    buy_car_action,
    car_extended_screen,
    compendium_nav,
    compendium_token_from_args,
    fire_driver_action,
    finish_race_action,
    hire_driver_action,
    market_car_extended_screen,
    repair_car_action,
    sell_car_action,
    simulate_to_end_action,
    stage_tune_value,
    start_race_action,
    tune_car_action,
    tune_editor_screen,
    tune_section_screen,
)
from game.economy import EconomyError
from game.game_state import GameState, new_career
from game.loader import DataLoadError, load_drivers, load_tracks
from game.save_load import SaveVersionError, game_state_from_dict, game_state_to_dict
from game.simulation import SimulationError
from game.sorting import sort_items
from game.tuning import TuningError
from interfaces import cli
from interfaces.menu import menu_bar, menu_command, status_bar
from interfaces.render_text import driver_rows, event_rows, garage_rows
from interfaces.terminal import terminal

WEB_SUBTITLE = "Web edition — the whole game runs in your browser."

MODE_MENU = "menu"
MODE_BUY = "buy"
MODE_SELL = "sell"
MODE_REPAIR = "repair"
MODE_HIRE = "hire"
MODE_FIRE = "fire"
MODE_EXT = "ext"
MODE_TUNE_CAR = "tune_car"
MODE_TUNE_SECTIONS = "tune_sections"
MODE_TUNE_FIELD = "tune_field"
MODE_TUNE_VALUE = "tune_value"
MODE_TUNE_EXIT = "tune_exit"
MODE_RACE_EVENT = "race_event"
MODE_RACE_CAR = "race_car"
MODE_RACE_DRIVER = "race_driver"
MODE_RACE = "race"
MODE_RACE_RESULT = "race_result"

_GARAGE_HEADERS = ["#", "ID", "Car", "Class", "PR", "Type", "Condition", "Power"]
_DRIVER_HEADERS = ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Pot", "Salary"]
_EVENT_HEADERS = ["#", "ID", "Event", "Track", "Class", "Req", "Status", "Best", "Fee", "Opp"]

_PROMPT_LABELS = {
    MODE_MENU: "Choice",
    MODE_BUY: "Buy (number or ID)",
    MODE_SELL: "Sell",
    MODE_REPAIR: "Repair",
    MODE_HIRE: "Hire",
    MODE_FIRE: "Release",
    MODE_EXT: "Extended view (number or ID)",
    MODE_TUNE_CAR: "Car",
    MODE_TUNE_SECTIONS: "Section",
    MODE_TUNE_FIELD: "Field",
    MODE_TUNE_VALUE: "Value",
    MODE_TUNE_EXIT: "[s] apply & exit  [d] discard  [any] keep editing",
    MODE_RACE_EVENT: "Event",
    MODE_RACE_CAR: "Car",
    MODE_RACE_DRIVER: "Driver",
    MODE_RACE: "Race command",
    MODE_RACE_RESULT: "Enter to continue",
}

_CANCEL_WORDS = {"q", "quit", "cancel"}
# The tune editor navigates UP one level rather than cancelling outright, and its
# hint lines advertise [B] like the creator, so back accepts "b" too.
_TUNE_BACK_WORDS = _CANCEL_WORDS | {"b", ""}

# Picker modes whose table is backed by a sortable screen: typing `sort …` inside the
# picker re-sorts it with the same grammar as the main screens (shared sort state).
# Absent modes (the tune flow — deliberately, and race/value prompts) keep their
# normal input handling. MODE_EXT is dynamic: it sorts whichever of garage/market
# the extended view was opened from.
_PICKER_SORT_SCREENS = {
    MODE_BUY: "market",
    MODE_SELL: "garage",
    MODE_REPAIR: "garage",
    MODE_RACE_CAR: "garage",
    MODE_HIRE: "drivers",
    MODE_FIRE: "drivers",
    MODE_RACE_DRIVER: "drivers",
    MODE_RACE_EVENT: "events",
}


class _RaisingStdin(io.TextIOBase):
    """Stdin replacement that fails loudly if any code path ever blocks on input."""

    def read(self, *args):  # pragma: no cover - defensive
        raise RuntimeError("stdin is not available in the web build")

    readline = read

    def isatty(self) -> bool:
        return False


def install_stdin_guard() -> None:
    """Called once at browser boot so a missed input() raises instead of hanging."""
    import sys

    sys.stdin = _RaisingStdin()


class WebGame:
    def __init__(self, state: GameState | None = None, race_seed: int | None = None) -> None:
        self.state = state if state is not None else new_career()
        self.screen = "garage"
        self.mode = MODE_MENU
        self.race_seed = race_seed
        self.js_request: str | None = None
        self.race_paused = False
        self.session = None
        self._view = ""
        self._last_tick = None
        self._current_command = "normal"
        self._resume_command = "normal"
        self._pending_command: str | None = None
        self._speed_mult = 1.0
        self._skip_to_lap = False
        self._race_error = ""
        self._tune_car_id: str | None = None
        self._tune_section: str = ""
        self._tune_draft: dict[str, object] = {}
        self._tune_field = None
        self._entry_event_id: str | None = None
        self._entry_car_id: str | None = None

    # ------------------------------------------------------------------ API

    def render(self) -> str:
        if not self._view:
            self._view = self._captured(self._print_main_view)
        return self._view

    def handle_input(self, raw: str) -> str:
        raw = (raw or "").strip()
        if self.mode == MODE_RACE:
            self._view = self._captured(self._race_input, raw)
            return self._view
        if self.mode == MODE_RACE_RESULT:
            self.mode = MODE_MENU
            self.screen = "garage"
            self._view = self._captured(self._print_main_view)
            return self._view
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                self._dispatch(raw)
            self._view = buffer.getvalue()
        except (EconomyError, TuningError, ValueError, SimulationError, DataLoadError) as exc:
            self.mode = MODE_MENU
            self._view = self._captured(self._print_main_view) + f"\nError: {exc}\n"
        return self._view

    def race_tick(self) -> str:
        if self.mode != MODE_RACE or self.session is None or self.race_paused:
            return self._view
        self._view = self._captured(self._advance_race)
        return self._view

    def ui_meta(self) -> str:
        label = _PROMPT_LABELS.get(self.mode, "Choice")
        if self.mode == MODE_TUNE_VALUE and self._tune_field is not None:
            if self._tune_field.options:
                label = "Option"
            elif self._tune_field.minimum is not None and self._tune_field.maximum is not None:
                label = f"Value ({self._tune_field.minimum:g}-{self._tune_field.maximum:g})"
        return json.dumps(
            {
                "mode": self.mode,
                "screen": self.screen,
                "in_race": self.mode == MODE_RACE,
                "race_paused": self.race_paused,
                "speed_mult": self._speed_mult,
                "tick_hz": TICK_RATE_HZ,
                "prompt_label": label,
                "js_request": self.js_request,
            }
        )

    def export_save(self) -> str:
        return json.dumps({"schema_version": SCHEMA_VERSION, "game_state": game_state_to_dict(self.state)})

    def confirm_save(self) -> str:
        self.js_request = None
        self._view = self._captured(self._print_main_view) + "\nSaved to browser storage.\n"
        return self._view

    def import_save(self, payload: str) -> str:
        self.js_request = None
        message = "Loaded from browser storage."
        try:
            if not payload:
                raise DataLoadError("No saved game found.")
            data = json.loads(payload)
            version = data.get("schema_version")
            if version != SCHEMA_VERSION:
                raise SaveVersionError(f"Unsupported save schema_version {version}; expected {SCHEMA_VERSION}")
            self.state = game_state_from_dict(data["game_state"])
            self.mode = MODE_MENU
            self.screen = "garage"
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            message = f"Could not read save: {exc}"
        except (DataLoadError, SaveVersionError) as exc:
            message = str(exc)
        self._view = self._captured(self._print_main_view) + f"\n{message}\n"
        return self._view

    # ------------------------------------------------------- shared helpers

    def _captured(self, func, *args) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            func(*args)
        return buffer.getvalue()

    def _print_main_view(self) -> None:
        cli._render_screen(self.state, self.screen, WEB_SUBTITLE)
        if self.screen == "garage":
            terminal.print("Enter a number or ID to view details  |  'ext <id>' for full specs")

    def _print_status_menu(self, screen_label: str) -> None:
        terminal.print(status_bar(self.state.money, self.state.week, len(self.state.garage), screen_label, self.state.team_xp))
        terminal.menu(menu_bar())

    def _print_detail(self, screen) -> None:
        terminal.header(screen.title, screen.subtitle)
        self._print_status_menu(self.screen)
        cli._render_action_screen(screen)
        terminal.print("Enter to return.")

    def _print_garage_table(self) -> None:
        terminal.table(
            cli._sort_table_title("Garage", "garage"),
            _GARAGE_HEADERS,
            garage_rows(self.state, cli._screen_sort("garage")),
        )

    def _cancel(self, message: str = "Cancelled.") -> None:
        self.mode = MODE_MENU
        self._print_main_view()
        terminal.print(message)

    def _resolve(self, items, get_id, label: str, raw: str):
        """Mirror cli._choose for one submitted line: item, or None if not resolved.

        On cancel words the mode is reset and the main view printed; on an unknown
        token the picker view is reprinted with a hint so the user can retry.
        """
        if raw.lower() in _CANCEL_WORDS:
            self._cancel()
            return None
        item = cli._select_from_collection(items, raw, get_id)
        if item is None:
            self._print_mode_view()
            terminal.print(f"Unknown {label.lower()}: {raw}")
        return item

    # ------------------------------------------------------------ dispatch

    def _dispatch(self, raw: str) -> None:
        if self.mode != MODE_MENU and self._picker_sort(raw):
            return
        handler = {
            MODE_MENU: self._menu_input,
            MODE_BUY: self._buy_input,
            MODE_SELL: self._sell_input,
            MODE_REPAIR: self._repair_input,
            MODE_HIRE: self._hire_input,
            MODE_FIRE: self._fire_input,
            MODE_EXT: self._ext_input,
            MODE_TUNE_CAR: self._tune_car_input,
            MODE_TUNE_SECTIONS: self._tune_sections_input,
            MODE_TUNE_FIELD: self._tune_field_input,
            MODE_TUNE_VALUE: self._tune_value_input,
            MODE_TUNE_EXIT: self._tune_exit_input,
            MODE_RACE_EVENT: self._race_event_input,
            MODE_RACE_CAR: self._race_car_input,
            MODE_RACE_DRIVER: self._race_driver_input,
        }[self.mode]
        handler(raw)

    def _picker_sort(self, raw: str) -> bool:
        """Handle `sort …` inside a sortable picker; True when the input was consumed.

        Mirrors cli._choose: same grammar as the main screens, applied to the picker's
        backing screen, then the picker view reprints in the new order. Modes not in
        _PICKER_SORT_SCREENS (the tune flow) fall through untouched."""
        tokens = shlex.split(raw) if raw.strip() else []
        if not tokens or tokens[0].lower() != "sort":
            return False
        sort_screen = _PICKER_SORT_SCREENS.get(self.mode)
        if sort_screen is None and self.mode == MODE_EXT:
            sort_screen = self.screen
        if sort_screen is None:
            return False
        if len(tokens) == 1:
            self._print_mode_view()
            cli._show_sort_help(sort_screen)
            return True
        cli._apply_sort_choice(tokens, sort_screen)
        self._print_mode_view()
        return True

    def _menu_input(self, raw: str) -> None:
        if self.screen.startswith(COMPENDIUM_PREFIX):
            nav = compendium_nav(self.screen, raw)
            if nav is not None:
                self.screen = nav or "garage"
                self._print_main_view()
                return
        if not raw:
            self._print_main_view()
            return
        if raw.isdigit() or "_" in raw:
            detail = cli._screen_selection(self.state, self.screen, raw)
            if detail is not None:
                self._print_detail(detail)
                return
        tokens = shlex.split(raw)
        command = menu_command(raw) if len(raw) == 1 else None
        if command is not None:
            tokens = [command]
        else:
            command = tokens[0] if tokens else ""
        if command in {"garage", "drivers", "events", "market", "help", "compendium"} and len(tokens) == 1:
            self.screen = command
            self._print_main_view()
            return
        lead = tokens[0].lower() if tokens else ""
        if lead == "compendium":
            self.screen = compendium_token_from_args(tokens[1:])
            self._print_main_view()
            return
        if lead == "sort":
            sorted_screen = cli._apply_sort_choice(tokens, self.screen)
            if sorted_screen:
                self.screen = sorted_screen
                self._print_main_view()
            return
        if lead in {"ext", "extended"}:
            self._start_ext(tokens[1] if len(tokens) > 1 else None)
            return
        if command == "quit":
            self._print_main_view()
            terminal.print("This is a browser game — close the tab to quit.")
            return
        if command == "save":
            self.js_request = "save"
            self._print_main_view()
            terminal.print("Saving to browser storage…")
            return
        if command == "load":
            self.js_request = "load"
            self._print_main_view()
            terminal.print("Loading from browser storage…")
            return
        self._command_input(command, tokens)

    def _command_input(self, command: str, tokens: list[str]) -> None:
        """The direct (typed) command forms plus picker entry, mirroring cli.run_command."""
        if command == "buy":
            if len(tokens) == 3 and tokens[1] == "car":
                result = buy_car_action(self.state, tokens[2])
            elif len(tokens) == 2:
                market = cli._sorted_market()
                car = cli._select_from_collection(market, tokens[1], lambda item: item.identity.id)
                if car is None:
                    raise ValueError(f"Unknown market car: {tokens[1]}")
                result = buy_car_action(self.state, car.identity.id)
            elif self.screen == "market":
                self._start_picker(MODE_BUY)
                return
            else:
                self.screen = "market"
                self._print_main_view()
                return
            self.screen = "garage"
            self._print_main_view()
            terminal.print(result.message)
        elif command == "sell":
            if len(tokens) == 3 and tokens[1] == "car":
                result = sell_car_action(self.state, tokens[2])
                self.screen = "garage"
                self._print_main_view()
                terminal.print(result.message)
            else:
                self._start_picker(MODE_SELL)
        elif command == "repair":
            if len(tokens) >= 2:
                result = repair_car_action(self.state, tokens[1])
                self.screen = "garage"
                self._print_main_view()
                terminal.print(result.message)
            else:
                self._start_picker(MODE_REPAIR)
        elif command == "tune":
            if len(tokens) == 4:
                result = tune_car_action(self.state, tokens[1], tokens[2], cli._parse_value(tokens[3]))
                self.screen = "garage"
                self._print_main_view()
                terminal.print(result.message)
            else:
                self._start_picker(MODE_TUNE_CAR)
        elif command == "hire":
            if len(tokens) == 2:
                result = hire_driver_action(self.state, tokens[1])
                self.screen = "drivers"
                self._print_main_view()
                terminal.print(result.message)
            else:
                self._start_picker(MODE_HIRE)
        elif command == "fire":
            if len(tokens) == 2:
                result = fire_driver_action(self.state, tokens[1])
                self.screen = "drivers"
                self._print_main_view()
                terminal.print(result.message)
            else:
                self._start_picker(MODE_FIRE)
        elif command == "race":
            self._start_picker(MODE_RACE_EVENT)
        elif command == "enter" and len(tokens) == 4:
            self._start_race(tokens[1], tokens[2], tokens[3])
        else:
            self._print_main_view()
            terminal.print("Unknown command. Type help.")

    # ------------------------------------------------------------- pickers

    def _start_picker(self, mode: str) -> None:
        if mode in {MODE_SELL, MODE_REPAIR, MODE_TUNE_CAR} and not self.state.garage:
            self._print_main_view()
            terminal.print("Garage is empty.")
            return
        if mode == MODE_RACE_EVENT and not self.state.garage:
            self._print_main_view()
            terminal.print("Garage is empty. Buy a car first.")
            return
        if mode == MODE_HIRE and not self._available_drivers():
            self._print_main_view()
            terminal.print("No drivers available to hire.")
            return
        if mode == MODE_FIRE and not self.state.hired_drivers:
            self._print_main_view()
            terminal.print("No drivers on your team.")
            return
        self.mode = mode
        self._print_mode_view()

    def _start_ext(self, car_token: str | None) -> None:
        """Mirror cli._show_extended_car without the blocking prompt."""
        if self.screen not in {"market", "garage"}:
            self._print_main_view()
            terminal.print("Extended view is available on the market and garage screens.")
            return
        if car_token is None:
            self.mode = MODE_EXT
            self._print_mode_view()
            return
        car = cli._select_from_collection(self._ext_cars(), car_token, lambda item: item.identity.id)
        if car is None:
            self._print_main_view()
            terminal.print(f"Unknown car: {car_token}")
            return
        self._print_detail(self._ext_screen(car))

    def _ext_cars(self):
        return cli._sorted_market() if self.screen == "market" else cli._sorted_garage(self.state)

    def _ext_screen(self, car):
        if self.screen == "market":
            return market_car_extended_screen(car.identity.id)
        return car_extended_screen(self.state, car.identity.id)

    def _available_drivers(self):
        return cli._sorted_available_drivers(self.state)

    def _entry_drivers(self):
        return sort_items("drivers", self.state.hired_drivers or load_drivers(), cli._screen_sort("drivers"))

    def _print_mode_view(self) -> None:
        """Print the current mode's full picker screen (header, status, menu, table)."""
        if self.mode == MODE_BUY:
            terminal.header("Buy Car", "Choose a market car by number or ID; q cancels.")
            self._print_status_menu("market")
            cli._show_market()
        elif self.mode == MODE_SELL:
            terminal.header("Sell Car", "Choose a garage car by number or ID; q cancels.")
            self._print_status_menu("sell")
            self._print_garage_table()
        elif self.mode == MODE_REPAIR:
            terminal.header("Repair", "Choose a garage car by number or ID; q cancels.")
            self._print_status_menu("repair")
            self._print_garage_table()
        elif self.mode == MODE_HIRE:
            terminal.header("Hire Driver", "Choose a driver by number or ID; q cancels.")
            self._print_status_menu("hire")
            terminal.table(
                cli._sort_table_title("Available Drivers", "drivers"), _DRIVER_HEADERS, driver_rows(self._available_drivers())
            )
        elif self.mode == MODE_FIRE:
            terminal.header("Release Driver", "Choose a driver by number or ID; q cancels.")
            self._print_status_menu("fire")
            terminal.table(
                cli._sort_table_title("Your Team", "drivers"), _DRIVER_HEADERS, driver_rows(cli._sorted_hired_drivers(self.state))
            )
        elif self.mode == MODE_EXT:
            terminal.header("Extended Specs", "Choose a car by number or ID; q cancels.")
            self._print_status_menu(self.screen)
            self._print_main_body_table()
        elif self.mode == MODE_TUNE_CAR:
            terminal.header("Tune", "Choose car, field, and value. q cancels.")
            self._print_status_menu("tune")
            self._print_garage_table()
        elif self.mode == MODE_TUNE_SECTIONS:
            screen = tune_editor_screen(self.state, self._tune_car_id, self._tune_draft)
            terminal.header(screen.title, screen.subtitle)
            self._print_status_menu("tune")
            cli._render_action_screen(screen)
            terminal.print("number/name = open section  |  W = apply staged setup  |  B = back")
        elif self.mode == MODE_TUNE_FIELD:
            screen = tune_section_screen(self.state, self._tune_car_id, self._tune_section, self._tune_draft)
            terminal.header(screen.title, screen.subtitle)
            self._print_status_menu("tune")
            cli._render_action_screen(screen)
            terminal.print("number/name = edit field  |  B = back to sections")
        elif self.mode == MODE_TUNE_EXIT:
            terminal.header("Tune", "Staged changes not applied")
            self._print_status_menu("tune")
            terminal.print(
                f"{len(self._tune_draft)} staged change(s) — [s] apply & exit, [d] discard & exit, anything else keeps editing."
            )
        elif self.mode == MODE_TUNE_VALUE:
            field = self._tune_field
            terminal.header("Tune", f"{self._tune_car_id} / {field.label}")
            self._print_status_menu("tune")
            if field.help:
                terminal.print(f"  {field.help}")
            if field.options:
                if any(option.description for option in field.options):
                    rows = [[index, option.label, option.description] for index, option in enumerate(field.options, start=1)]
                    terminal.table(f"{field.label} Options", ["#", "Option", "Effect"], rows)
                else:
                    rows = [[index, option.label, option.value] for index, option in enumerate(field.options, start=1)]
                    terminal.table(f"{field.label} Options", ["#", "Option", "Value"], rows)
            else:
                terminal.print(f"Current: {field.current}  Allowed: {field.minimum:g}-{field.maximum:g}")
        elif self.mode == MODE_RACE_EVENT:
            tracks = {track.id: track for track in load_tracks()}
            terminal.header("Race Entry", "Choose an event, car, and driver. Enter a number or ID; q cancels.")
            self._print_status_menu("race entry")
            terminal.table(
                cli._sort_table_title("Available Events", "events"),
                _EVENT_HEADERS,
                event_rows(cli._sorted_events(), tracks, state=self.state),
            )
        elif self.mode == MODE_RACE_CAR:
            terminal.header("Race Entry", f"Event: {self._entry_event_id}")
            self._print_status_menu("race entry")
            self._print_garage_table()
        elif self.mode == MODE_RACE_DRIVER:
            terminal.header("Race Entry", f"{self._entry_event_id} / {self._entry_car_id}")
            self._print_status_menu("race entry")
            terminal.table(cli._sort_table_title("Drivers", "drivers"), _DRIVER_HEADERS, driver_rows(self._entry_drivers()))

    def _print_main_body_table(self) -> None:
        if self.screen == "market":
            cli._show_market()
        else:
            self._print_garage_table()

    def _buy_input(self, raw: str) -> None:
        car = self._resolve(cli._sorted_market(), lambda item: item.identity.id, "Buy", raw)
        if car is None:
            return
        result = buy_car_action(self.state, car.identity.id)
        self.mode = MODE_MENU
        self.screen = "market"
        self._print_main_view()
        terminal.print(result.message)

    def _sell_input(self, raw: str) -> None:
        car = self._resolve(cli._sorted_garage(self.state), lambda item: item.identity.id, "Sell", raw)
        if car is None:
            return
        result = sell_car_action(self.state, car.identity.id)
        self.mode = MODE_MENU
        self.screen = "garage"
        self._print_main_view()
        terminal.print(result.message)

    def _repair_input(self, raw: str) -> None:
        car = self._resolve(cli._sorted_garage(self.state), lambda item: item.identity.id, "Repair", raw)
        if car is None:
            return
        result = repair_car_action(self.state, car.identity.id)
        self.mode = MODE_MENU
        self.screen = "garage"
        self._print_main_view()
        terminal.print(result.message)

    def _hire_input(self, raw: str) -> None:
        driver = self._resolve(self._available_drivers(), lambda item: item.id, "Hire", raw)
        if driver is None:
            return
        result = hire_driver_action(self.state, driver.id)
        self.mode = MODE_MENU
        self.screen = "drivers"
        self._print_main_view()
        terminal.print(result.message)

    def _fire_input(self, raw: str) -> None:
        driver = self._resolve(cli._sorted_hired_drivers(self.state), lambda item: item.id, "Release", raw)
        if driver is None:
            return
        result = fire_driver_action(self.state, driver.id)
        self.mode = MODE_MENU
        self.screen = "drivers"
        self._print_main_view()
        terminal.print(result.message)

    def _ext_input(self, raw: str) -> None:
        car = self._resolve(self._ext_cars(), lambda item: item.identity.id, "Extended view", raw)
        if car is None:
            return
        self.mode = MODE_MENU
        self._print_detail(self._ext_screen(car))

    def _tune_car_input(self, raw: str) -> None:
        car = self._resolve(cli._sorted_garage(self.state), lambda item: item.identity.id, "Car", raw)
        if car is None:
            return
        self._tune_car_id = car.identity.id
        self._tune_draft = {}
        self.mode = MODE_TUNE_SECTIONS
        self._print_mode_view()

    def _tune_sections_input(self, raw: str) -> None:
        low = raw.lower()
        if low in _TUNE_BACK_WORDS:
            if not self._tune_draft:
                self._cancel()
                return
            self.mode = MODE_TUNE_EXIT
            self._print_mode_view()
            return
        if low == "w":
            self._apply_tune_draft(exit_after=False)
            return
        try:
            tune_section_screen(self.state, self._tune_car_id, raw, self._tune_draft)
        except ValueError as exc:
            self._print_mode_view()
            terminal.print(str(exc))
            return
        self._tune_section = raw
        self.mode = MODE_TUNE_FIELD
        self._print_mode_view()

    def _tune_field_input(self, raw: str) -> None:
        if raw.lower() in _TUNE_BACK_WORDS:
            self.mode = MODE_TUNE_SECTIONS
            self._print_mode_view()
            return
        screen = tune_section_screen(self.state, self._tune_car_id, self._tune_section, self._tune_draft)
        selected_field = cli._match_tune_field(screen.fields, raw)
        if selected_field is None:
            self._print_mode_view()
            terminal.print(f"Unknown tune field: {raw}")
            return
        self._tune_field = selected_field
        self.mode = MODE_TUNE_VALUE
        self._print_mode_view()

    def _tune_value_input(self, raw: str) -> None:
        if raw.lower() in _TUNE_BACK_WORDS:
            self.mode = MODE_TUNE_FIELD
            self._print_mode_view()
            terminal.print("No change staged.")
            return
        field = self._tune_field
        try:
            if field.options:
                value = None
                if raw.isdigit() and 1 <= int(raw) <= len(field.options):
                    value = field.options[int(raw) - 1].value
                else:
                    normalized = raw.lower()
                    for option in field.options:
                        if normalized in {option.value.lower(), option.label.lower()}:
                            value = option.value
                            break
                if value is None:
                    raise TuningError(f"Unknown option for {field.label}: {raw}")
            else:
                value = cli._parse_value(raw)
            stage_tune_value(self.state, self._tune_car_id, field.name, value)
        except (TuningError, ValueError) as exc:
            # Stay in the editor: a rejected value must not eject the whole draft.
            self.mode = MODE_TUNE_FIELD
            self._print_mode_view()
            terminal.print(f"Rejected: {exc}")
            return
        if value == field.current:
            self._tune_draft.pop(field.name, None)
        else:
            self._tune_draft[field.name] = value
        self.mode = MODE_TUNE_FIELD
        self._print_mode_view()

    def _tune_exit_input(self, raw: str) -> None:
        low = raw.lower()
        if low == "s":
            self._apply_tune_draft(exit_after=True)
            return
        if low == "d":
            count = len(self._tune_draft)
            self._tune_draft = {}
            self._cancel(f"Discarded {count} staged change(s).")
            return
        self.mode = MODE_TUNE_SECTIONS
        self._print_mode_view()

    def _apply_tune_draft(self, exit_after: bool) -> None:
        if not self._tune_draft:
            self.mode = MODE_TUNE_SECTIONS
            self._print_mode_view()
            terminal.print("No staged changes to apply.")
            return
        try:
            result = apply_tune_draft(self.state, self._tune_car_id, dict(self._tune_draft))
        except TuningError as exc:
            self.mode = MODE_TUNE_SECTIONS
            self._print_mode_view()
            terminal.print(f"Cannot apply: {exc}")
            return
        self._tune_draft = {}
        if exit_after:
            self.mode = MODE_MENU
            self.screen = "garage"
            self._print_main_view()
        else:
            self.mode = MODE_TUNE_SECTIONS
            self._print_mode_view()
        terminal.print(result.message)

    def _race_event_input(self, raw: str) -> None:
        event = self._resolve(cli._sorted_events(), lambda item: item.id, "Event", raw)
        if event is None:
            return
        self._entry_event_id = event.id
        self.mode = MODE_RACE_CAR
        self._print_mode_view()

    def _race_car_input(self, raw: str) -> None:
        car = self._resolve(cli._sorted_garage(self.state), lambda item: item.identity.id, "Car", raw)
        if car is None:
            return
        self._entry_car_id = car.identity.id
        self.mode = MODE_RACE_DRIVER
        self._print_mode_view()

    def _race_driver_input(self, raw: str) -> None:
        driver = self._resolve(self._entry_drivers(), lambda item: item.id, "Driver", raw)
        if driver is None:
            return
        self._start_race(self._entry_event_id, self._entry_car_id, driver.id)

    # ---------------------------------------------------------------- race

    def _start_race(self, event_id: str, car_id: str, driver_id: str) -> None:
        race = start_race_action(self.state, event_id, car_id, driver_id, seed=self.race_seed)
        self.session = race.session
        self._last_tick = None
        self._current_command = "normal"
        self._resume_command = "normal"
        self._pending_command = None
        self._speed_mult = 1.0
        self._skip_to_lap = False
        self._race_error = ""
        self.race_paused = False
        self.mode = MODE_RACE
        self._print_race_frame()

    def _print_race_frame(self) -> None:
        cli._render_race_screen(self.state, self.session, self._last_tick, self._race_error)
        cli._print_lap_bar(self.session, self._current_command, self._pending_command, self._speed_mult)

    def _advance_race(self) -> None:
        # Mirrors one iteration of cli._run_race's loop body.
        if self._pending_command:
            if self._pending_command == "pit" and self._current_command != "pit":
                self._resume_command = self._current_command
            self._current_command = self._pending_command
            self._pending_command = None
        try:
            advance = advance_to_lap_end_action if self._skip_to_lap else advance_race_action
            self._skip_to_lap = False
            result = advance(self.session, self._current_command)
            self._last_tick = result.tick
        except SimulationError as exc:
            self._race_error = str(exc)
            self._finish_race()
            return
        if self._current_command == "pit" and self._last_tick is not None and self._last_tick.is_lap_end:
            self._current_command = self._resume_command
        if self.session.is_finished:
            self._finish_race()
            return
        self._print_race_frame()

    def _finish_race(self) -> None:
        finished = finish_race_action(self.state, self.session)
        terminal.header(finished.screen.title, finished.screen.subtitle)
        terminal.print(cli._post_race_status_bar(self.state))
        cli._render_post_race_screen(finished.screen)
        if self._race_error:
            terminal.print(self._race_error)
        terminal.print("Enter to continue.")
        self.session = None
        self.race_paused = False
        self.mode = MODE_RACE_RESULT

    def _race_input(self, raw: str) -> None:
        low = raw.lower()
        if self.race_paused:
            # Any input resumes; mirrors the "Press Enter to resume" pause in the CLI.
            self.race_paused = False
            self._print_race_frame()
            return
        if low in {"help", "?"}:
            self.race_paused = True
            cli._render_race_screen(self.state, self.session, self._last_tick, "")
            cli._show_race_help()
            terminal.print("Race paused — enter anything to resume.")
            return
        if low in {"end", "skip", "x"}:
            result = simulate_to_end_action(self.session, self._current_command)
            self._last_tick = result.tick
            terminal.print("Race simulated to completion.")
            self._finish_race()
            return
        if low in {"next", "lap", "l"}:
            self._skip_to_lap = True
        elif low in {"ff", ">"}:
            self._speed_mult = cli._cycle_speed(self._speed_mult)
        elif raw:
            matched = cli._race_command(raw)
            if matched is not None:
                self._pending_command = matched
        self._print_race_frame()
