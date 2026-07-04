from __future__ import annotations

import select
import shlex
import shutil
import sys

from constants import PRESENTATION_SPEED_FACTOR, TICK_RATE_HZ
# Presentation fast-forward multipliers cycled with F in the race loop. Pure render speed:
# they change only the per-tick wall-clock pause, never the simulated result.
_RACE_SPEEDS = (1.0, 2.0, 4.0, 8.0)

from game.actions import (
    advance_race_action,
    advance_to_lap_end_action,
    buy_car_action,
    car_detail_screen,
    driver_detail_screen,
    drivers_screen,
    event_detail_screen,
    events_screen,
    finish_race_action,
    format_race_clock,
    fire_driver_action,
    garage_screen,
    hire_driver_action,
    load_game_action,
    car_extended_screen,
    market_screen,
    market_car_detail_screen,
    market_car_extended_screen,
    race_clock_elapsed,
    race_command_options,
    race_entry_screen,
    race_screen,
    repair_car_action,
    save_game_action,
    sell_car_action,
    simulate_to_end_action,
    apply_tune_draft,
    stage_tune_value,
    start_race_action,
    tune_car_action,
    tune_editor_screen,
    tune_section_screen,
)
from game.economy import EconomyError
from game.game_state import GameState, new_career
from game.loader import load_drivers, load_events, load_tracks
from game.market import list_market_cars
from game.sorting import SortSpec, is_sortable_screen, parse_sort_spec, sort_fields, sort_items, sort_label
from game.simulation import SimulationError
from game.tuning import TuningError
from interfaces.menu import menu_bar, menu_command, status_bar
from interfaces.render_text import (
    driver_rows,
    event_rows,
    garage_rows,
    render_drivers,
    render_events,
    render_garage,
    render_race_status,
    standings_rows,
)
from interfaces.terminal import RICH_AVAILABLE, terminal

_SCREEN_SORTS: dict[str, SortSpec] = {}
_SORTABLE_SCREENS = ("garage", "drivers", "events", "market")


def main() -> None:
    state = new_career()
    if not sys.stdin.isatty():
        print(render_garage(state))
        print(render_drivers(load_drivers()))
        print(render_events(load_events()))
        return
    command_loop(state)


def command_loop(state: GameState) -> None:
    subtitle = "Rich UI enabled." if RICH_AVAILABLE else "Install rich for color tables: python3 -m pip install -r requirements.txt"
    screen = "garage"
    while True:
        terminal.clear()
        _render_screen(state, screen, subtitle)
        raw = terminal.prompt("Choice").strip()
        if not raw:
            continue
        try:
            state, screen = run_menu_choice(state, raw, screen)
        except (EconomyError, TuningError, ValueError) as exc:
            terminal.print(exc)
            terminal.pause()


def run_menu_choice(state: GameState, raw: str, current_screen: str = "garage") -> tuple[GameState, str]:
    if raw.strip().isdigit() or "_" in raw.strip():
        detail_screen = _screen_selection(state, current_screen, raw.strip())
        if detail_screen is not None:
            _show_detail_screen(state, detail_screen, current_screen)
            return state, current_screen
    command = menu_command(raw) if len(raw.strip()) == 1 else None
    command = command or raw.strip()
    if command in {"garage", "drivers", "events", "market", "help"}:
        return state, command
    tokens = shlex.split(raw.strip())
    if tokens and tokens[0].lower() == "sort":
        sorted_screen = _apply_sort_choice(tokens, current_screen)
        return state, sorted_screen or current_screen
    if command == "buy":
        if current_screen == "market":
            _buy_on_market(state)
        return state, "market"
    if command == "sell":
        _sell_picker(state)
        return state, "garage"
    if command == "repair":
        _repair_picker(state)
        return state, "garage"
    if command == "tune":
        _tune_picker(state)
        return state, "garage"
    if command == "race":
        _race_picker(state)
        return state, "garage"
    if command == "hire":
        _hire_picker(state)
        return state, "drivers"
    if command == "fire":
        _fire_picker(state)
        return state, "drivers"
    if command == "save":
        _save_picker(state)
        return state, current_screen
    if command == "load":
        return _load_picker(state), "garage"
    if command == "quit":
        raise SystemExit
    if tokens and tokens[0].lower() in {"ext", "extended"}:
        car_token = tokens[1] if len(tokens) > 1 else None
        _show_extended_car(state, current_screen, car_token)
        return state, current_screen
    return run_command(state, command), current_screen


def run_command(state: GameState, raw: str) -> GameState:
    tokens = shlex.split(raw)
    if not tokens:
        return state
    menu_match = menu_command(tokens[0]) if len(tokens) == 1 else None
    if menu_match is not None:
        tokens = [menu_match]
    command = tokens[0]
    if command == "help":
        _show_help()
    elif command == "garage":
        _show_garage(state)
    elif command == "drivers":
        _show_drivers(state)
    elif command == "events":
        _show_events()
    elif command == "market":
        _show_market()
    elif command == "sort":
        screen = _apply_sort_choice(tokens, "garage")
        if screen is None:
            return state
        if screen == "drivers":
            _show_drivers(state)
        elif screen == "events":
            _show_events()
        elif screen == "market":
            _show_market()
        else:
            _show_garage(state)
    elif command == "buy" and len(tokens) == 3 and tokens[1] == "car":
        result = buy_car_action(state, tokens[2])
        terminal.print(result.message)
    elif command == "buy" and len(tokens) == 2:
        market = _sorted_market()
        car = _select_from_collection(market, tokens[1], lambda item: item.identity.id)
        if car is None:
            raise ValueError(f"Unknown market car: {tokens[1]}")
        result = buy_car_action(state, car.identity.id)
        terminal.print(result.message)
    elif command == "sell" and len(tokens) == 3 and tokens[1] == "car":
        sell_car_action(state, tokens[2])
        _show_garage(state)
    elif command == "repair" and len(tokens) >= 2:
        repair_car_action(state, tokens[1])
        _show_garage(state)
    elif command == "tune" and len(tokens) == 4:
        tune_car_action(state, tokens[1], tokens[2], _parse_value(tokens[3]))
        _show_garage(state)
    elif command == "buy":
        _show_market()
    elif command == "sell":
        _sell_picker(state)
    elif command == "repair":
        _repair_picker(state)
    elif command == "tune":
        _tune_picker(state)
    elif command == "race":
        _race_picker(state)
    elif command == "hire" and len(tokens) == 2:
        result = hire_driver_action(state, tokens[1])
        terminal.print(result.message)
        _show_drivers(state)
    elif command == "fire" and len(tokens) == 2:
        result = fire_driver_action(state, tokens[1])
        terminal.print(result.message)
        _show_drivers(state)
    elif command == "hire":
        _hire_picker(state)
    elif command == "fire":
        _fire_picker(state)
    elif command == "enter" and len(tokens) == 4:
        _run_race(state, tokens[1], tokens[2], tokens[3])
    elif command == "save":
        result = save_game_action(state, tokens[1] if len(tokens) > 1 else "saves/save1.json")
        terminal.print(result.message)
    elif command == "load":
        result = load_game_action(tokens[1] if len(tokens) > 1 else "saves/save1.json")
        state = result.state
        terminal.print(result.message)
    elif command == "quit":
        raise SystemExit
    else:
        terminal.print("Unknown command. Type help.")
    return state


def _render_screen(state: GameState, screen: str, subtitle: str = "") -> None:
    terminal.header("SheetCircuit", subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), screen, state.team_xp))
    terminal.menu(menu_bar())
    if screen == "garage":
        _show_garage(state)
    elif screen == "drivers":
        _show_drivers(state)
    elif screen == "events":
        _show_events(state)
    elif screen == "market":
        _show_market()
    elif screen == "help":
        _show_help()
    else:
        _show_garage(state)


def _show_garage(state: GameState) -> None:
    _render_action_screen(garage_screen(state, _screen_sort("garage")))


def _show_drivers(state: GameState) -> None:
    _render_action_screen(drivers_screen(state, _screen_sort("drivers")))


def _show_events(state: GameState) -> None:
    _render_action_screen(events_screen(state, _screen_sort("events")))


def _show_market() -> None:
    _render_action_screen(market_screen(_screen_sort("market")))
    terminal.print("Enter a number or ID to view details  |  'buy' or 'buy <id>' to purchase  |  'ext <id>' for full specs")


def _show_extended_car(state: GameState, screen: str, car_token: str | None) -> None:
    if screen == "market":
        cars = _sorted_market()
        get_id = lambda c: c.identity.id
        get_screen = lambda c: market_car_extended_screen(c.identity.id)
    elif screen == "garage":
        cars = _sorted_garage(state)
        get_id = lambda c: c.identity.id
        get_screen = lambda c: car_extended_screen(state, c.identity.id)
    else:
        terminal.print("Extended view is available on the market and garage screens.")
        terminal.pause()
        return
    if car_token is not None:
        car = _select_from_collection(cars, car_token, get_id)
        if car is None:
            terminal.print(f"Unknown car: {car_token}")
            terminal.pause()
            return
    else:
        def show():
            terminal.clear()
            _render_screen(state, screen)
            return _sorted_market() if screen == "market" else _sorted_garage(state)

        car = _choose(cars, get_id, "Extended view (number or ID)", sort_screen=screen, refresh=show)
        if car is None:
            return
    _show_detail_screen(state, get_screen(car), screen)


def _buy_on_market(state: GameState) -> None:
    def show():
        terminal.clear()
        _render_screen(state, "market")
        return _sorted_market()

    car = _choose(_sorted_market(), lambda item: item.identity.id, "Buy (number or ID)", sort_screen="market", refresh=show)
    if car is None:
        return
    result = buy_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _show_detail_screen(state: GameState, screen, parent_screen: str) -> None:
    terminal.clear()
    terminal.header(screen.title, screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), parent_screen, state.team_xp))
    terminal.menu(menu_bar())
    _render_action_screen(screen)
    terminal.pause()


def _screen_selection(state: GameState, screen: str, raw: str):
    if screen == "drivers":
        combined = _sorted_hired_drivers(state) + _sorted_available_drivers(state)
        driver = _select_from_collection(combined, raw, lambda item: item.id)
        return driver_detail_screen(driver.id) if driver is not None else None
    if screen == "events":
        events = _sorted_events()
        event = _select_from_collection(events, raw, lambda item: item.id)
        return event_detail_screen(event.id, state) if event is not None else None
    if screen == "garage":
        car = _select_from_collection(_sorted_garage(state), raw, lambda item: item.identity.id)
        return car_detail_screen(state, car.identity.id) if car is not None else None
    if screen == "market":
        cars = _sorted_market()
        car = _select_from_collection(cars, raw, lambda item: item.identity.id)
        return market_car_detail_screen(car.identity.id) if car is not None else None
    return None


def _select_from_collection(items: list[object], raw: str, get_id):
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(items):
            return items[index]
        return None
    normalized = raw.lower()
    return next((item for item in items if get_id(item).lower() == normalized), None)


def _apply_sort_choice(tokens: list[str], current_screen: str) -> str | None:
    if len(tokens) == 1:
        _show_sort_help(current_screen)
        return None

    requested_screen = current_screen
    field_index = 1
    if tokens[1].lower() in _SORTABLE_SCREENS:
        requested_screen = tokens[1].lower()
        field_index = 2

    if not is_sortable_screen(requested_screen):
        valid = ", ".join(_SORTABLE_SCREENS)
        raise ValueError(f"Specify a sortable screen: {valid}")
    if field_index >= len(tokens):
        _show_sort_help(requested_screen)
        return requested_screen
    if len(tokens) - field_index > 2:
        raise ValueError("Use: sort [screen] <field> [asc|desc]")

    field = tokens[field_index].lower()
    if field in {"clear", "default", "reset", "none"}:
        _SCREEN_SORTS.pop(requested_screen, None)
        return requested_screen

    direction = tokens[field_index + 1] if field_index + 1 < len(tokens) else None
    _SCREEN_SORTS[requested_screen] = parse_sort_spec(requested_screen, field, direction)
    return requested_screen


def _show_sort_help(current_screen: str) -> None:
    rows = []
    screens = [current_screen] if is_sortable_screen(current_screen) else list(_SORTABLE_SCREENS)
    for screen in screens:
        rows.append([screen.title(), ", ".join(sort_fields(screen))])
    terminal.table("Sort Fields", ["Screen", "Fields"], rows)
    terminal.print("Use sort <field> [asc|desc], sort <screen> <field> [asc|desc], or sort clear.")


def _screen_sort(screen: str) -> SortSpec | None:
    return _SCREEN_SORTS.get(screen)


def _sort_table_title(title: str, screen: str) -> str:
    spec = _screen_sort(screen)
    if spec is None:
        return title
    return f"{title} (sorted by {sort_label(screen, spec)})"


def _sorted_garage(state: GameState):
    return sort_items("garage", state.garage, _screen_sort("garage"))


def _sorted_market():
    return sort_items("market", list_market_cars(), _screen_sort("market"))


def _sorted_events():
    return sort_items("events", load_events(), _screen_sort("events"))


def _sorted_hired_drivers(state: GameState):
    return sort_items("drivers", state.hired_drivers, _screen_sort("drivers"))


def _sorted_available_drivers(state: GameState):
    all_drivers = load_drivers()
    hired_ids = {d.id for d in state.hired_drivers}
    return sort_items("drivers", [d for d in all_drivers if d.id not in hired_ids], _screen_sort("drivers"))


def _render_action_screen(screen) -> None:
    for table in screen.tables:
        terminal.table(table.title, table.headers, table.rows)
    for message in screen.messages:
        terminal.print(message)


def _show_help() -> None:
    terminal.table(
        "Menu Hotkeys",
        ["Key", "Action"],
        [
            ["G", "Garage screen"],
            ["E", "Events screen"],
            ["D", "Drivers screen"],
            ["M", "Market screen (view & buy)"],
            ["R", "Guided race entry"],
            ["X", "Guided car sale"],
            ["T", "Guided tuning"],
            ["P", "Guided repair"],
            ["S", "Save game"],
            ["L", "Load game"],
            ["H", "Help"],
            ["Q", "Quit"],
        ],
    )
    terminal.table(
        "Typed Commands",
        ["Command", "Purpose"],
        [
            ["<number> / <id>", "Open details for a visible list item"],
            ["ext <number> / ext <id>", "Full spec view on market or garage screen"],
            ["garage", "Show owned cars"],
            ["drivers", "Show drivers"],
            ["events", "Show race events"],
            ["market", "Show market cars (supports buying)"],
            ["race", "Choose event, car, and driver"],
            ["buy", "Go to market; on market screen: pick a car to buy"],
            ["buy <car_id>", "Buy a specific market car by ID or number"],
            ["buy car <car_id>", "Buy a specific market car by ID"],
            ["sell", "Choose an owned car to sell"],
            ["sell car <car_id>", "Sell a specific garage car"],
            ["repair", "Choose an owned car to repair"],
            ["repair <car_id>", "Repair a specific garage car"],
            ["tune", "Choose an owned car to tune"],
            ["tune <car_id> <field> <value>", "Set one tune field"],
            ["hire", "Choose a driver to hire"],
            ["hire <driver_id>", "Hire a specific driver"],
            ["fire", "Choose a driver to release"],
            ["fire <driver_id>", "Release a specific driver"],
            ["enter <event_id> <car_id> <driver_id>", "Start a race directly"],
            ["sort <field> (asc|desc)", "Sort the visible list (works in pickers too)"],
            ["sort <screen> <field> (asc|desc)", "Sort garage, drivers, events, or market"],
            ["sort clear", "Clear sorting on the current screen"],
            ["save [path]", "Save game, default saves/save1.json"],
            ["load [path]", "Load game, default saves/save1.json"],
            ["help", "Show this help"],
            ["quit", "Exit"],
        ],
    )
    terminal.table(
        "Car Columns",
        ["Column", "Meaning"],
        [
            ["Class", "Event eligibility letter (E..S), derived from PR; restrictions may still apply"],
            ["PR", "Performance rating: mean capability across three reference tracks (drag/slalom/hybrid)"],
            ["Type", "Shape — where pace comes from: Balanced, Power, Handling, or Challenge"],
        ],
    )
    terminal.print(
        "Class is computed, not stored: every car (including ones you build) is run on a fixed"
        " drag, slalom and hybrid reference track; the average is its PR/class and the spread is"
        " its Type. Open a car's details to see the per-track numbers."
    )
    terminal.print(
        "Rivals are matched near your car's derived event pace; higher-class events keep a faster pace floor."
    )
    terminal.table(
        "Sortable Fields",
        ["Screen", "Fields"],
        [[screen.title(), ", ".join(sort_fields(screen))] for screen in _SORTABLE_SCREENS],
    )
    _show_race_help()


def _show_race_help() -> None:
    terminal.table(
        "Race Commands",
        ["Key", "Command", "Effect"],
        [[option.key, option.label, option.description] for option in race_command_options()]
        + [
            ["N / next", "Next lap", "Fast-forward to the end of the current lap"],
            ["F / >", "Faster", "Cycle presentation speed (1x/2x/4x/8x); no effect on the result"],
            ["X / end", "End", "Simulate remaining laps instantly and show result"],
            ["? / help", "Help", "Show race command help"],
        ],
    )


_PICKER_SUBTITLE = "Choose {noun} by number or ID; 'sort <field>' re-orders; q cancels."


def _garage_picker_show(state: GameState, title: str, subtitle: str, screen_label: str):
    """Render a garage-table picker view and return the sorted cars; reusable as the
    _choose refresh so 'sort' re-orders the list in place."""
    def show():
        terminal.clear()
        terminal.header(title, subtitle)
        terminal.print(status_bar(state.money, state.week, len(state.garage), screen_label, state.team_xp))
        terminal.menu(menu_bar())
        terminal.table(_sort_table_title("Garage", "garage"), ["#", "ID", "Car", "Class", "PR", "Type", "Condition", "Power"], garage_rows(state, _screen_sort("garage")))
        return _sorted_garage(state)
    return show


def _sell_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    show = _garage_picker_show(state, "Sell Car", _PICKER_SUBTITLE.format(noun="a garage car"), "sell")
    car = _choose(show(), lambda item: item.identity.id, "Sell", sort_screen="garage", refresh=show)
    if car is None:
        return
    result = sell_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _repair_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    show = _garage_picker_show(state, "Repair", _PICKER_SUBTITLE.format(noun="a garage car"), "repair")
    car = _choose(show(), lambda item: item.identity.id, "Repair", sort_screen="garage", refresh=show)
    if car is None:
        return
    result = repair_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _tune_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    # Deliberately not sortable: the tune flow keeps its plain picker (and the tune
    # fields list keeps its authored subsystem grouping).
    _garage_picker_show(state, "Tune", "Choose a car to set up. q cancels.", "tune")()
    car = _choose(_sorted_garage(state), lambda item: item.identity.id, "Car")
    if car is None:
        return
    _tune_editor(state, car.identity.id)


def _tune_editor(state: GameState, car_id: str) -> None:
    """Creator-style setup editor: sections -> fields -> value.

    Edits are STAGED into a draft; [W] applies the whole draft atomically and
    backing out with staged changes asks first (mirrors the creator's edit loop)."""
    draft: dict[str, object] = {}
    while True:
        screen = tune_editor_screen(state, car_id, draft)
        terminal.clear()
        terminal.header(screen.title, screen.subtitle)
        terminal.print(status_bar(state.money, state.week, len(state.garage), "tune", state.team_xp))
        terminal.menu(menu_bar())
        _render_action_screen(screen)
        terminal.print("number/name = open section  |  W = apply staged setup  |  B = back")
        raw = terminal.prompt("Section").strip()
        low = raw.lower()
        if low in {"b", "q", "cancel", ""}:
            if not draft:
                return
            confirm = terminal.prompt(
                "Staged changes not applied — [s] apply & exit, [d] discard & exit, anything else keeps editing"
            ).strip().lower()
            if confirm == "s" and _apply_staged_tune(state, car_id, draft):
                return
            if confirm == "d":
                return
            continue
        if low == "w":
            if _apply_staged_tune(state, car_id, draft):
                draft = {}
            continue
        try:
            tune_section_screen(state, car_id, raw, draft)
        except ValueError as exc:
            terminal.print(exc)
            terminal.pause()
            continue
        _tune_section_editor(state, car_id, raw, draft)


def _tune_section_editor(state: GameState, car_id: str, section: str, draft: dict[str, object]) -> None:
    while True:
        screen = tune_section_screen(state, car_id, section, draft)
        terminal.clear()
        terminal.header(screen.title, screen.subtitle)
        terminal.print(status_bar(state.money, state.week, len(state.garage), "tune", state.team_xp))
        terminal.menu(menu_bar())
        _render_action_screen(screen)
        terminal.print("number/name = edit field  |  B = back to sections")
        raw = terminal.prompt("Field").strip()
        if raw.lower() in {"b", "q", "cancel", ""}:
            return
        selected_field = _match_tune_field(screen.fields, raw)
        if selected_field is None:
            terminal.print(f"Unknown tune field: {raw}")
            terminal.pause()
            continue
        try:
            value = _prompt_field_value(selected_field)
            if value is None:
                terminal.print("No change staged.")
                continue
            stage_tune_value(state, car_id, selected_field.name, value)
        except TuningError as exc:
            terminal.print(f"Rejected: {exc}")
            terminal.pause()
            continue
        if value == selected_field.current:
            # Re-entering the applied value un-stages the field.
            draft.pop(selected_field.name, None)
        else:
            draft[selected_field.name] = value


def _match_tune_field(fields: list, raw: str):
    """Resolve a tune field by its number in the shown list, name, or display label."""
    if raw.isdigit() and 1 <= int(raw) <= len(fields):
        return fields[int(raw) - 1]
    normalized = raw.lower()
    return next((f for f in fields if normalized in {f.name.lower(), f.label.lower()}), None)


def _apply_staged_tune(state: GameState, car_id: str, draft: dict[str, object]) -> bool:
    if not draft:
        terminal.print("No staged changes to apply.")
        terminal.pause()
        return False
    try:
        result = apply_tune_draft(state, car_id, dict(draft))
    except TuningError as exc:
        terminal.print(f"Cannot apply: {exc}")
        terminal.pause()
        return False
    terminal.print(result.message)
    terminal.pause()
    return True


def _prompt_field_value(field) -> object | None:
    if field.options:
        has_desc = any(option.description for option in field.options)
        if has_desc:
            rows = [[index, option.label, option.description] for index, option in enumerate(field.options, start=1)]
            terminal.table(f"{field.label} Options", ["#", "Option", "Effect"], rows)
        else:
            rows = [[index, option.label, option.value] for index, option in enumerate(field.options, start=1)]
            terminal.table(f"{field.label} Options", ["#", "Option", "Value"], rows)
        raw = terminal.prompt("Option").strip()
        if raw == "" or raw.lower() in {"q", "quit", "cancel"}:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(field.options):
            return field.options[int(raw) - 1].value
        normalized = raw.lower()
        for option in field.options:
            if normalized in {option.value.lower(), option.label.lower()}:
                return option.value
        raise TuningError(f"Unknown option for {field.label}: {raw}")
    range_text = f"{field.minimum:g}-{field.maximum:g}" if field.minimum is not None and field.maximum is not None else ""
    value = terminal.prompt(f"Value ({range_text})").strip()
    if value == "" or value.lower() in {"q", "quit", "cancel"}:
        return None
    return _parse_value(value)


def _save_picker(state: GameState) -> None:
    path = terminal.prompt("Save path", "saves/save1.json")
    result = save_game_action(state, path)
    terminal.print(result.message)
    terminal.pause()


def _load_picker(state: GameState) -> GameState:
    path = terminal.prompt("Load path", "saves/save1.json")
    result = load_game_action(path)
    loaded = result.state
    terminal.print(result.message)
    terminal.pause()
    return loaded


def _hire_picker(state: GameState) -> None:
    def available_drivers():
        hired_ids = {d.id for d in state.hired_drivers}
        return sort_items("drivers", [d for d in load_drivers() if d.id not in hired_ids], _screen_sort("drivers"))

    if not available_drivers():
        terminal.print("No drivers available to hire.")
        return

    def show():
        terminal.clear()
        terminal.header("Hire Driver", _PICKER_SUBTITLE.format(noun="a driver"))
        terminal.print(status_bar(state.money, state.week, len(state.garage), "hire", state.team_xp))
        terminal.menu(menu_bar())
        available = available_drivers()
        terminal.table(_sort_table_title("Available Drivers", "drivers"), ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(available))
        return available

    driver = _choose(show(), lambda item: item.id, "Hire", sort_screen="drivers", refresh=show)
    if driver is None:
        return
    result = hire_driver_action(state, driver.id)
    terminal.print(result.message)
    terminal.pause()


def _fire_picker(state: GameState) -> None:
    if not state.hired_drivers:
        terminal.print("No drivers on your team.")
        return

    def show():
        terminal.clear()
        terminal.header("Release Driver", _PICKER_SUBTITLE.format(noun="a driver"))
        terminal.print(status_bar(state.money, state.week, len(state.garage), "fire", state.team_xp))
        terminal.menu(menu_bar())
        drivers = _sorted_hired_drivers(state)
        terminal.table(_sort_table_title("Your Team", "drivers"), ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(drivers))
        return drivers

    driver = _choose(show(), lambda item: item.id, "Release", sort_screen="drivers", refresh=show)
    if driver is None:
        return
    result = fire_driver_action(state, driver.id)
    terminal.print(result.message)
    terminal.pause()


def _race_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty. Buy a car first.")
        return
    tracks = {track.id: track for track in load_tracks()}

    def show_events():
        terminal.clear()
        terminal.header("Race Entry", "Choose an event, car, and driver. Enter a number or ID; 'sort <field>' re-orders; q cancels.")
        terminal.print(status_bar(state.money, state.week, len(state.garage), "race entry", state.team_xp))
        terminal.menu(menu_bar())
        events = _sorted_events()
        terminal.table(
            _sort_table_title("Available Events", "events"),
            ["#", "ID", "Event", "Track", "Class", "Req", "Status", "Best", "Fee", "Opp"],
            event_rows(events, tracks, state=state),
        )
        return events

    event = _choose(show_events(), lambda item: item.id, "Event", sort_screen="events", refresh=show_events)
    if event is None:
        return

    show_cars = _garage_picker_show(state, "Race Entry", f"Event: {event.name}", "race entry")
    car = _choose(show_cars(), lambda item: item.identity.id, "Car", sort_screen="garage", refresh=show_cars)
    if car is None:
        return

    def show_drivers():
        terminal.clear()
        terminal.header("Race Entry", f"{event.name} / {car.identity.name}")
        terminal.print(status_bar(state.money, state.week, len(state.garage), "race entry", state.team_xp))
        terminal.menu(menu_bar())
        drivers = sort_items("drivers", state.hired_drivers or load_drivers(), _screen_sort("drivers"))
        terminal.table(_sort_table_title("Drivers", "drivers"), ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(drivers))
        return drivers

    driver = _choose(show_drivers(), lambda item: item.id, "Driver", sort_screen="drivers", refresh=show_drivers)
    if driver is None:
        return
    _run_race(state, event.id, car.identity.id, driver.id)


def _choose(items: list[object], get_id, label: str, sort_screen: str | None = None, refresh=None):
    """Prompt until an item is picked (or cancelled). Every picker list is sortable
    with the same grammar as the main screens: pass the backing sort screen plus a
    ``refresh`` that re-renders the picker's table and returns the re-sorted items."""
    while True:
        raw = terminal.prompt(label).strip()
        if raw.lower() in {"q", "quit", "cancel"}:
            terminal.print("Cancelled.")
            return None
        tokens = shlex.split(raw) if raw else []
        if tokens and tokens[0].lower() == "sort":
            if sort_screen is None or refresh is None:
                terminal.print("This list has a fixed order.")
                continue
            if len(tokens) == 1:
                _show_sort_help(sort_screen)
                continue
            try:
                _apply_sort_choice(tokens, sort_screen)
            except ValueError as exc:
                terminal.print(exc)
                continue
            items = refresh()
            continue
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(items):
                return items[index]
        for item in items:
            if get_id(item) == raw:
                return item
        terminal.print(f"Unknown {label.lower()}: {raw}")


def _run_race(state: GameState, event_id: str, car_id: str, driver_id: str) -> None:
    try:
        race = start_race_action(state, event_id, car_id, driver_id)
    except SimulationError as exc:
        terminal.print(str(exc))
        terminal.pause()
        return
    session = race.session
    last_result = None
    current_command = "normal"
    resume_command = "normal"  # what to fall back to after a one-shot pit
    pending_command: str | None = None
    race_error = ""
    show_help = False
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    # Constant per-update pause: tick count already scales with the car's watched length
    # (see ticks_per_lap_for), so total watched = ticks / TICK_RATE_HZ tracks the real race.
    base_tick_sleep = 1.0 / TICK_RATE_HZ
    speed_mult = 1.0  # presentation speed; F cycles it, never touches the result

    _render_race_screen(state, session, None, "")
    _print_lap_bar(session, current_command, pending_command, speed_mult)

    while not session.is_finished:
        skip_to_lap = False
        if interactive:
            ready = select.select([sys.stdin], [], [], base_tick_sleep / speed_mult)[0]
            if ready:
                raw = sys.stdin.readline().strip()
                low = raw.lower()
                if low in {"help", "?"}:
                    show_help = True
                elif low in {"end", "skip", "x"}:
                    result = simulate_to_end_action(session, current_command)
                    last_result = result.tick
                    _render_race_screen(state, session, last_result, "")
                    terminal.print("Race simulated to completion.")
                    break
                elif low in {"n", "next", "lap", "l"}:
                    skip_to_lap = True  # fast-forward over the rest of this lap
                elif low in {"f", "ff", ">"}:
                    speed_mult = _cycle_speed(speed_mult)
                elif raw:
                    matched = _race_command(raw)
                    if matched is not None:
                        pending_command = matched

        if pending_command:
            if pending_command == "pit" and current_command != "pit":
                resume_command = current_command
            current_command = pending_command
            pending_command = None

        try:
            advance = advance_to_lap_end_action if skip_to_lap else advance_race_action
            race_result = advance(session, current_command)
            last_result = race_result.tick
        except SimulationError as exc:
            race_error = str(exc)
            break

        # Pit is one-shot: once the stop completes at lap end, resume prior pace.
        if current_command == "pit" and last_result is not None and last_result.is_lap_end:
            current_command = resume_command

        _render_race_screen(state, session, last_result, race_error)
        race_error = ""

        if show_help:
            # Hold the race so help is readable; the sim only advances when we tick it,
            # and the next tick's redraw restores the pinned race layout.
            _show_race_help()
            terminal.pause("Press Enter to resume the race")
            show_help = False

        _print_lap_bar(session, current_command, pending_command, speed_mult)

    finished = finish_race_action(state, session)
    terminal.clear()
    terminal.header(finished.screen.title, finished.screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), "post race", state.team_xp))
    terminal.menu(menu_bar())
    _render_action_screen(finished.screen)
    terminal.pause()


def _cycle_speed(current: float) -> float:
    """Step to the next presentation speed, wrapping 8x back to 1x."""
    try:
        index = _RACE_SPEEDS.index(current)
    except ValueError:
        index = 0
    return _RACE_SPEEDS[(index + 1) % len(_RACE_SPEEDS)]


def _print_lap_bar(session, current_command: str, pending_command: str | None, speed_mult: float = 1.0) -> None:
    status = f"next: {pending_command}" if pending_command else current_command
    if session.duration_s is not None:
        # Duration race: the bar tracks elapsed against the time cap, not within-lap position.
        elapsed = race_clock_elapsed(session)
        frac = min(elapsed / session.duration_s, 1.0) if session.duration_s else 1.0
        label = f"{format_race_clock(elapsed)}/{format_race_clock(session.duration_s)} · Lap {session.current_lap}"
    else:
        frac = session.current_sub_tick / session.ticks_per_lap
        lap = min(session.current_lap + 1, session.total_laps)
        label = f"Lap {lap}/{session.total_laps}"
    filled = int(frac * 24)
    bar = "█" * filled + "░" * (24 - filled)
    sys.stdout.write(
        f"  {label}  [{bar}] {int(frac * 100):3d}%  [{status}]  {speed_mult:g}x"
        "  cmd+Enter  N=next lap  F=faster  X=end\n"
    )
    sys.stdout.flush()


def _race_log_event_budget(session) -> int:
    """Race-log Event width that keeps the three-column race layout inside the terminal.

    Panel widths are deterministic (rich SIMPLE_HEAVY tables): the strip is the lane grid + 4,
    standings are the longest car label + 43, and the log adds 10 around the Event column, plus
    ~5 for inter-column gaps. Everything but the Event text is fixed, so it takes the remainder.
    Below the floor the log wraps under the other panels — still pinned, just taller.
    """
    width = shutil.get_terminal_size((120, 40)).columns
    strip_w = 2 * len(session.cars) + 3
    label_w = max((len(car.label) for car in session.cars), default=10)
    middle_w = max(label_w + 43, 43)
    return max(16, min(48, width - strip_w - middle_w - 10 - 5))


def _render_race_screen(state: GameState, session, result=None, error: str = "") -> None:
    screen = race_screen(session, result, error, log_event_chars=_race_log_event_budget(session))
    terminal.clear()
    terminal.header(screen.title, screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), "race", state.team_xp))
    terminal.menu(_option_bar(screen.actions) + "  help")
    for message in screen.messages:
        terminal.print(message)
    # Pinned three-column layout: track strip | standings + player status | race log. Every
    # panel is constant-height (see race_screen), so nothing shifts or scrolls between ticks.
    side_titles = {"Track", "Race Log"}
    strip = next((table for table in screen.tables if table.title == "Track"), None)
    race_log = next((table for table in screen.tables if table.title == "Race Log"), None)
    main_tables = [table for table in screen.tables if table.title not in side_titles]
    groups = [[table] for table in (strip,) if table is not None]
    groups.append(main_tables)
    if race_log is not None:
        groups.append([race_log])
    if len(groups) == 1:
        for table in main_tables:
            terminal.table(table.title, table.headers, table.rows)
        return
    terminal.table_columns(
        *[[(table.title, table.headers, table.rows) for table in group] for group in groups]
    )


def _parse_value(value: str) -> object:
    if value in {"safe", "balanced", "hot", "qualifying", "fuel_save"}:
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _race_command(raw: str) -> str | None:
    normalized = raw.lower()
    for option in race_command_options():
        if normalized in {option.key.lower(), option.value.lower(), option.label.lower()}:
            return option.value
    return None


def _option_bar(options) -> str:
    labels = []
    for option in options:
        if option.label.lower().startswith(option.key.lower()):
            labels.append(f"[{option.key}]{option.label[1:]}")
        else:
            labels.append(f"[{option.key}]{option.label}")
    return "  ".join(labels)


if __name__ == "__main__":
    main()
