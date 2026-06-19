from __future__ import annotations

import select
import shlex
import sys
import time

_RACE_SPEED_FACTOR = 13.3   # display each lap this many times faster than real-time

from game.actions import (
    advance_race_action,
    buy_car_action,
    car_detail_screen,
    driver_detail_screen,
    drivers_screen,
    event_detail_screen,
    events_screen,
    finish_race_action,
    fire_driver_action,
    garage_screen,
    hire_driver_action,
    load_game_action,
    market_screen,
    market_car_detail_screen,
    race_command_options,
    race_entry_screen,
    race_screen,
    repair_car_action,
    save_game_action,
    sell_car_action,
    simulate_to_end_action,
    start_race_action,
    tune_car_action,
    tune_fields_screen,
)
from game.economy import EconomyError
from game.game_state import GameState, new_career
from game.loader import load_drivers, load_events, load_tracks
from game.market import list_market_cars
from game.simulation import SimulationError
from game.tuning import TuningError
from interfaces.menu import menu_bar, menu_command, status_bar
from interfaces.render_text import (
    driver_rows,
    event_rows,
    garage_rows,
    market_rows,
    render_drivers,
    render_events,
    render_garage,
    render_race_status,
    standings_rows,
)
from interfaces.terminal import RICH_AVAILABLE, terminal


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
    if command == "buy":
        _buy_picker(state)
        return state, "garage"
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
    elif command == "buy" and len(tokens) == 3 and tokens[1] == "car":
        buy_car_action(state, tokens[2])
        _show_garage(state)
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
        _buy_picker(state)
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
    terminal.print(status_bar(state.money, state.week, len(state.garage), screen))
    terminal.menu(menu_bar())
    if screen == "garage":
        _show_garage(state)
    elif screen == "drivers":
        _show_drivers(state)
    elif screen == "events":
        _show_events()
    elif screen == "market":
        _show_market()
    elif screen == "help":
        _show_help()
    else:
        _show_garage(state)


def _show_garage(state: GameState) -> None:
    _render_action_screen(garage_screen(state))


def _show_drivers(state: GameState) -> None:
    _render_action_screen(drivers_screen(state))


def _show_events() -> None:
    _render_action_screen(events_screen())


def _show_market() -> None:
    _render_action_screen(market_screen())


def _show_detail_screen(state: GameState, screen, parent_screen: str) -> None:
    terminal.clear()
    terminal.header(screen.title, screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), parent_screen))
    terminal.menu(menu_bar())
    _render_action_screen(screen)
    terminal.pause()


def _screen_selection(state: GameState, screen: str, raw: str):
    if screen == "drivers":
        all_drivers = load_drivers()
        hired_ids = {d.id for d in state.hired_drivers}
        available = [d for d in all_drivers if d.id not in hired_ids]
        combined = state.hired_drivers + available
        driver = _select_from_collection(combined, raw, lambda item: item.id)
        return driver_detail_screen(driver.id) if driver is not None else None
    if screen == "events":
        events = load_events()
        event = _select_from_collection(events, raw, lambda item: item.id)
        return event_detail_screen(event.id) if event is not None else None
    if screen == "garage":
        car = _select_from_collection(state.garage, raw, lambda item: item.identity.id)
        return car_detail_screen(state, car.identity.id) if car is not None else None
    if screen == "market":
        cars = list_market_cars()
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
            ["M", "Market screen"],
            ["R", "Guided race entry"],
            ["B", "Guided car purchase"],
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
            ["garage", "Show owned cars"],
            ["drivers", "Show available drivers"],
            ["events", "Show available race events"],
            ["market", "Show market cars"],
            ["race", "Open guided race entry"],
            ["buy", "Open guided buy flow"],
            ["buy car <car_id>", "Buy a specific market car"],
            ["sell", "Open guided sell flow"],
            ["sell car <car_id>", "Sell a specific garage car"],
            ["repair", "Open guided repair flow"],
            ["repair <car_id>", "Repair a specific garage car"],
            ["tune", "Open guided tune flow"],
            ["tune <car_id> <field> <value>", "Set one tune field"],
            ["hire", "Open guided driver hire flow"],
            ["hire <driver_id>", "Hire a specific driver"],
            ["fire", "Open guided driver release flow"],
            ["fire <driver_id>", "Release a specific driver"],
            ["enter <event_id> <car_id> <driver_id>", "Start a race directly"],
            ["save [path]", "Save game, default saves/save1.json"],
            ["load [path]", "Load game, default saves/save1.json"],
            ["help", "Show this help"],
            ["quit", "Exit"],
        ],
    )
    _show_race_help()


def _show_race_help() -> None:
    terminal.table(
        "Race Commands",
        ["Key", "Command", "Effect"],
        [[option.key, option.label, option.description] for option in race_command_options()]
        + [
            ["X / end", "End", "Simulate remaining laps instantly and show result"],
            ["? / help", "Help", "Show race command help"],
        ],
    )


def _buy_picker(state: GameState) -> None:
    market = list_market_cars()
    terminal.clear()
    terminal.header("Buy Car", "Choose a market car by number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "buy"))
    terminal.menu(menu_bar())
    terminal.table("Market", ["#", "ID", "Car", "Class", "Price", "Power", "Cond"], market_rows(market))
    car = _choose(market, lambda item: item.identity.id, "Buy")
    if car is None:
        return
    result = buy_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _sell_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    terminal.clear()
    terminal.header("Sell Car", "Choose a garage car by number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "sell"))
    terminal.menu(menu_bar())
    terminal.table("Garage", ["#", "ID", "Car", "Class", "Rating", "Condition", "Power"], garage_rows(state))
    car = _choose(state.garage, lambda item: item.identity.id, "Sell")
    if car is None:
        return
    result = sell_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _repair_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    terminal.clear()
    terminal.header("Repair", "Choose a garage car by number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "repair"))
    terminal.menu(menu_bar())
    terminal.table("Garage", ["#", "ID", "Car", "Class", "Rating", "Condition", "Power"], garage_rows(state))
    car = _choose(state.garage, lambda item: item.identity.id, "Repair")
    if car is None:
        return
    result = repair_car_action(state, car.identity.id)
    terminal.print(result.message)
    terminal.pause()


def _tune_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty.")
        return
    terminal.clear()
    terminal.header("Tune", "Choose car, field, and value. q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "tune"))
    terminal.menu(menu_bar())
    terminal.table("Garage", ["#", "ID", "Car", "Class", "Rating", "Condition", "Power"], garage_rows(state))
    car = _choose(state.garage, lambda item: item.identity.id, "Car")
    if car is None:
        return
    terminal.clear()
    screen = tune_fields_screen(state, car.identity.id)
    terminal.header(screen.title, screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), "tune"))
    terminal.menu(menu_bar())
    _render_action_screen(screen)
    field_choice = terminal.prompt("Field").strip()
    if field_choice.lower() in {"q", "quit", "cancel"}:
        terminal.print("Cancelled.")
        return
    selected_field = None
    if field_choice.isdigit() and 1 <= int(field_choice) <= len(screen.fields):
        selected_field = screen.fields[int(field_choice) - 1]
    else:
        normalized_choice = field_choice.lower()
        for field in screen.fields:
            if normalized_choice in {field.name.lower(), field.label.lower()}:
                selected_field = field
                break
    if selected_field is None:
        terminal.print(f"Unknown tune field: {field_choice}")
        return
    value = _prompt_field_value(selected_field)
    if value is None:
        terminal.print("No tune change made.")
        terminal.pause()
        return
    result = tune_car_action(state, car.identity.id, selected_field.name, value)
    terminal.print(result.message)
    terminal.pause()


def _prompt_field_value(field) -> object | None:
    if field.options:
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
    all_drivers = load_drivers()
    hired_ids = {d.id for d in state.hired_drivers}
    available = [d for d in all_drivers if d.id not in hired_ids]
    if not available:
        terminal.print("No drivers available to hire.")
        return
    terminal.clear()
    terminal.header("Hire Driver", "Choose a driver by number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "hire"))
    terminal.menu(menu_bar())
    terminal.table("Available Drivers", ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(available))
    driver = _choose(available, lambda item: item.id, "Hire")
    if driver is None:
        return
    result = hire_driver_action(state, driver.id)
    terminal.print(result.message)
    terminal.pause()


def _fire_picker(state: GameState) -> None:
    if not state.hired_drivers:
        terminal.print("No drivers on your team.")
        return
    terminal.clear()
    terminal.header("Release Driver", "Choose a driver by number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "fire"))
    terminal.menu(menu_bar())
    terminal.table("Your Team", ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(state.hired_drivers))
    driver = _choose(state.hired_drivers, lambda item: item.id, "Release")
    if driver is None:
        return
    result = fire_driver_action(state, driver.id)
    terminal.print(result.message)
    terminal.pause()


def _race_picker(state: GameState) -> None:
    if not state.garage:
        terminal.print("Garage is empty. Buy a car first.")
        return
    events = load_events()
    drivers = state.hired_drivers or load_drivers()
    tracks = {track.id: track for track in load_tracks()}

    terminal.clear()
    terminal.header("Race Entry", "Choose an event, car, and driver. Enter a number or ID; q cancels.")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "race entry"))
    terminal.menu(menu_bar())
    terminal.table("Available Events", ["#", "ID", "Event", "Track", "Class", "Fee", "Opp"], event_rows(events, tracks))
    event = _choose(events, lambda item: item.id, "Event")
    if event is None:
        return
    terminal.clear()
    terminal.header("Race Entry", f"Event: {event.name}")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "race entry"))
    terminal.menu(menu_bar())
    terminal.table("Your Cars", ["#", "ID", "Car", "Class", "Rating", "Condition", "Power"], garage_rows(state))
    car = _choose(state.garage, lambda item: item.identity.id, "Car")
    if car is None:
        return
    terminal.clear()
    terminal.header("Race Entry", f"{event.name} / {car.identity.name}")
    terminal.print(status_bar(state.money, state.week, len(state.garage), "race entry"))
    terminal.menu(menu_bar())
    terminal.table("Drivers", ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"], driver_rows(drivers))
    driver = _choose(drivers, lambda item: item.id, "Driver")
    if driver is None:
        return
    _run_race(state, event.id, car.identity.id, driver.id)


def _choose(items: list[object], get_id, label: str):
    while True:
        raw = terminal.prompt(label).strip()
        if raw.lower() in {"q", "quit", "cancel"}:
            terminal.print("Cancelled.")
            return None
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(items):
                return items[index]
        for item in items:
            if get_id(item) == raw:
                return item
        terminal.print(f"Unknown {label.lower()}: {raw}")


def _run_race(state: GameState, event_id: str, car_id: str, driver_id: str) -> None:
    race = start_race_action(state, event_id, car_id, driver_id)
    session = race.session
    last_result = None
    current_command = "normal"
    pending_command: str | None = None
    race_error = ""
    show_help = False
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    track = session.track
    tick_sleep = (track.base_lap_time / _RACE_SPEED_FACTOR / session.ticks_per_lap) if track else 0.4

    _render_race_screen(state, session, None, "")
    _print_lap_bar(session, current_command, pending_command)

    while not session.is_finished:
        if interactive:
            ready = select.select([sys.stdin], [], [], tick_sleep)[0]
            if ready:
                raw = sys.stdin.readline().strip()
                if raw.lower() in {"help", "?"}:
                    show_help = True
                elif raw.lower() in {"end", "skip", "x"}:
                    result = simulate_to_end_action(session, current_command)
                    last_result = result.tick
                    _render_race_screen(state, session, last_result, "")
                    terminal.print("Race simulated to completion.")
                    break
                elif raw:
                    matched = _race_command(raw)
                    if matched is not None:
                        pending_command = matched

        if pending_command:
            current_command = pending_command
            pending_command = None

        try:
            race_result = advance_race_action(session, current_command)
            last_result = race_result.tick
        except SimulationError as exc:
            race_error = str(exc)
            break

        _render_race_screen(state, session, last_result, race_error)
        race_error = ""

        if show_help:
            _show_race_help()
            show_help = False

        _print_lap_bar(session, current_command, pending_command)

    finished = finish_race_action(state, session)
    terminal.print(f"Race finished. Prize: ${finished.prize_money}")
    for message in finished.screen.messages:
        terminal.print(message)
    terminal.pause()


def _print_lap_bar(session, current_command: str, pending_command: str | None) -> None:
    tpl = session.ticks_per_lap
    st = session.current_sub_tick
    filled = int(st / tpl * 24)
    bar = "█" * filled + "░" * (24 - filled)
    pct = int(st / tpl * 100)
    lap = min(session.current_lap + 1, session.total_laps)
    status = f"next: {pending_command}" if pending_command else current_command
    sys.stdout.write(f"  Lap {lap}/{session.total_laps}  [{bar}] {pct:3d}%  [{status}]  cmd+Enter  X=skip to end\n")
    sys.stdout.flush()


def _render_race_screen(state: GameState, session, result=None, error: str = "") -> None:
    screen = race_screen(session, result, error)
    terminal.clear()
    terminal.header(screen.title, screen.subtitle)
    terminal.print(status_bar(state.money, state.week, len(state.garage), "race"))
    terminal.menu(_option_bar(screen.actions) + "  help")
    for message in screen.messages:
        terminal.print(message)
    race_log = next((table for table in screen.tables if table.title == "Race Log"), None)
    main_tables = [table for table in screen.tables if table.title != "Race Log"]
    if race_log is not None:
        terminal.table_columns(
            [(table.title, table.headers, table.rows) for table in main_tables],
            (race_log.title, race_log.headers, race_log.rows),
        )
        return
    for table in main_tables:
        terminal.table(table.title, table.headers, table.rows)


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
