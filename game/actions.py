from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from constants import ENGINE_CRITICAL_C, ENGINE_MAP_POWER, TIRE_CRITICAL_C, TUNE_FIELD_RANGES
from game.economy import buy_car, fire_driver, hire_driver, repair_car, sell_car
from game.effective_stats import class_rating, compute_effective_stats
from game.game_state import GameState
from game.loader import load_drivers, load_events, load_tracks
from game.market import list_market_cars
from game.models import RaceSession, RaceTickResult
from game.race_session import apply_player_command, enter_event, finish_event
from game.save_load import load_game, save_game
from game.sorting import SortSpec, sort_items, sort_label
from game.tuning import update_tune_fields


@dataclass
class TableData:
    title: str
    headers: list[str]
    rows: list[list[Any]]


@dataclass
class OptionData:
    value: str
    label: str
    key: str = ""
    description: str = ""


@dataclass
class FieldData:
    name: str
    label: str
    current: Any
    value_type: str
    minimum: float | None = None
    maximum: float | None = None
    options: list[OptionData] = field(default_factory=list)


@dataclass
class ScreenData:
    name: str
    title: str
    subtitle: str = ""
    tables: list[TableData] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    actions: list[OptionData] = field(default_factory=list)
    fields: list[FieldData] = field(default_factory=list)


@dataclass
class ActionResult:
    state: GameState
    message: str = ""
    screen: ScreenData | None = None


@dataclass
class RaceActionResult:
    session: RaceSession
    tick: RaceTickResult | None = None
    screen: ScreenData | None = None
    error: str = ""
    prize_money: int | None = None


def garage_screen(state: GameState, sort_spec: SortSpec | None = None) -> ScreenData:
    cars = sort_items("garage", state.garage, sort_spec)
    return ScreenData(
        name="garage",
        title="Garage",
        tables=[
            TableData(
                _table_title("Garage", "garage", sort_spec),
                ["#", "ID", "Car", "Class", "Rating", "Condition", "Power"],
                [
                    [
                        index,
                        car.identity.id,
                        car.identity.name,
                        car.identity.car_class,
                        class_rating(car),
                        f"{car.condition.overall_condition:.0f}%",
                        f"{car.powertrain.power_hp} hp",
                    ]
                    for index, car in enumerate(cars, start=1)
                ],
            )
        ],
    )


def drivers_screen(state: GameState, sort_spec: SortSpec | None = None) -> ScreenData:
    all_drivers = load_drivers()
    hired_ids = {d.id for d in state.hired_drivers}
    hired = sort_items("drivers", state.hired_drivers, sort_spec)
    available = sort_items("drivers", [d for d in all_drivers if d.id not in hired_ids], sort_spec)
    tables = []
    if hired:
        tables.append(
            TableData(
                _table_title("Your Team", "drivers", sort_spec),
                ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"],
                [
                    [index, d.id, d.name, d.pace, d.consistency, d.feedback, f"${d.salary}"]
                    for index, d in enumerate(hired, start=1)
                ],
            )
        )
    tables.append(
        TableData(
            _table_title("Available Drivers", "drivers", sort_spec),
            ["#", "ID", "Name", "Pace", "Cons", "Feedback", "Salary"],
            [
                [index, d.id, d.name, d.pace, d.consistency, d.feedback, f"${d.salary}"]
                for index, d in enumerate(available, start=1)
            ],
        )
    )
    return ScreenData(name="drivers", title="Drivers", tables=tables)


def events_screen(sort_spec: SortSpec | None = None) -> ScreenData:
    tracks = {track.id: track for track in load_tracks()}
    events = sort_items("events", load_events(), sort_spec)
    return ScreenData(
        name="events",
        title="Events",
        tables=[
            TableData(
                _table_title("Events", "events", sort_spec),
                ["#", "ID", "Event", "Track", "Class", "Fee", "Opp"],
                [
                    [
                        index,
                        event.id,
                        event.name,
                        tracks[event.track_id].name if event.track_id in tracks else event.track_id,
                        event.car_class_limit,
                        f"${event.entry_fee}",
                        event.opponent_count,
                    ]
                    for index, event in enumerate(events, start=1)
                ],
            )
        ],
    )


def market_screen(sort_spec: SortSpec | None = None) -> ScreenData:
    cars = sort_items("market", list_market_cars(), sort_spec)
    return ScreenData(
        name="market",
        title="Market",
        tables=[
            TableData(
                _table_title("Market", "market", sort_spec),
                ["#", "ID", "Car", "Class", "Price", "Power", "Cond"],
                [
                    [
                        index,
                        car.identity.id,
                        car.identity.name,
                        car.identity.car_class,
                        f"${car.value}",
                        f"{car.powertrain.power_hp} hp",
                        f"{car.condition.overall_condition:.0f}%",
                    ]
                    for index, car in enumerate(cars, start=1)
                ],
            )
        ],
    )


def car_detail_screen(state: GameState, car_id: str) -> ScreenData:
    car = next((garage_car for garage_car in state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown garage car: {car_id}")
    return _car_detail_screen(car, "garage_car")


def market_car_detail_screen(car_id: str) -> ScreenData:
    car = next((market_car for market_car in list_market_cars() if market_car.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown market car: {car_id}")
    return _car_detail_screen(car, "market_car")


def _car_detail_screen(car, name: str) -> ScreenData:
    return ScreenData(
        name=name,
        title=car.identity.name,
        subtitle=f"{car.identity.manufacturer} {car.identity.model} / {car.identity.car_class}",
        tables=[
            TableData(
                "Overview",
                ["Field", "Value"],
                [
                    ["ID", car.identity.id],
                    ["Value", f"${car.value}"],
                    ["Rating", class_rating(car)],
                    ["Power", f"{car.powertrain.power_hp} hp"],
                    ["Torque", f"{car.powertrain.torque_nm} Nm"],
                    ["Weight", f"{car.chassis.weight_kg} kg"],
                    ["Drivetrain", car.identity.drivetrain],
                    ["Tags", ", ".join(car.identity.tags)],
                ],
            ),
            TableData(
                "Condition",
                ["Area", "Value"],
                [
                    ["Overall", f"{car.condition.overall_condition:.0f}%"],
                    ["Engine", f"{car.condition.engine_condition:.0f}%"],
                    ["Gearbox", f"{car.condition.gearbox_condition:.0f}%"],
                    ["Suspension", f"{car.condition.suspension_condition:.0f}%"],
                    ["Brakes", f"{car.condition.brake_condition:.0f}%"],
                    ["Tires", f"{car.condition.tire_condition:.0f}%"],
                    ["Mileage", f"{car.condition.mileage:,} km"],
                ],
            ),
        ],
    )


def car_extended_screen(state: GameState, car_id: str) -> ScreenData:
    car = next((c for c in state.garage if c.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown garage car: {car_id}")
    return _car_extended_screen(car, "garage_car_extended")


def market_car_extended_screen(car_id: str) -> ScreenData:
    car = next((c for c in list_market_cars() if c.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown market car: {car_id}")
    return _car_extended_screen(car, "market_car_extended")


def _car_extended_screen(car, name: str) -> ScreenData:
    i = car.identity
    pt = car.powertrain
    ch = car.chassis
    ti = car.tires
    br = car.brakes
    su = car.suspension
    ae = car.aero
    du = car.durability
    fu = car.fuel
    co = car.condition
    tu = car.tune

    front_dist = round(ch.weight_distribution_front * 100, 0)
    rear_dist = round(100 - front_dist, 0)
    eff = compute_effective_stats(car)

    return ScreenData(
        name=name,
        title=f"{i.name} — Extended Specs",
        subtitle=f"{i.manufacturer} {i.model} ({i.year}) / {i.car_class}",
        tables=[
            TableData(
                "Identity",
                ["Field", "Value"],
                [
                    ["ID", i.id],
                    ["Year", i.year],
                    ["Drivetrain", i.drivetrain],
                    ["Layout", i.layout],
                    ["Value", f"${car.value:,}"],
                    ["Rating", class_rating(car)],
                    ["Tags", ", ".join(i.tags)],
                    ["Installed Parts", ", ".join(car.installed_parts) if car.installed_parts else "none"],
                ],
            ),
            # Net result of every spec below (parts, tune and condition folded in) — the
            # numbers that actually drive a race. The raw stat tables that follow feed these.
            TableData(
                "Effective (Race) Stats",
                ["Axis", "Value"],
                [
                    ["Acceleration", f"{eff.acceleration:.0f}"],
                    ["Top Speed", f"{eff.top_speed:.0f}"],
                    ["Grip", f"{eff.grip:.0f}"],
                    ["Braking", f"{eff.braking:.0f}"],
                    ["Handling", f"{eff.handling:.0f}"],
                    ["Aero Grip", f"{eff.aero_grip:.0f}"],
                    ["Stability", f"{eff.stability:.0f}"],
                    ["Reliability", f"{eff.reliability:.0f}"],
                    ["Tyre Wear Rate", f"{eff.tire_wear_rate:.2f}"],
                    ["Fuel Burn Rate", f"{eff.fuel_burn_rate:.2f}"],
                    ["Engine Heat Rate", f"{eff.engine_heat_rate:.1f}"],
                ],
            ),
            TableData(
                "Engine",
                ["Stat", "Value"],
                [
                    ["Aspiration", pt.aspiration],
                    ["Power", f"{pt.power_hp} hp"],
                    ["Torque", f"{pt.torque_nm} Nm"],
                    ["Powerband", pt.powerband],
                    ["Throttle Response", pt.throttle_response],
                    ["Reliability", pt.engine_reliability],
                    ["Cooling", pt.cooling],
                    ["Fuel Efficiency", pt.fuel_efficiency],
                    ["Engine Stress", pt.engine_stress],
                ],
            ),
            TableData(
                "Chassis",
                ["Stat", "Value"],
                [
                    ["Weight", f"{ch.weight_kg:,} kg"],
                    ["Weight Distribution", f"{front_dist:.0f}F / {rear_dist:.0f}R"],
                    ["Center of Gravity", ch.center_of_gravity],
                    ["Rigidity", ch.chassis_rigidity],
                    ["Stability", ch.stability],
                    ["Rotation", ch.rotation],
                ],
            ),
            TableData(
                "Tires",
                ["Stat", "Value"],
                [
                    ["Compound", ti.tire_compound],
                    ["Width (front)", f"{ti.tire_width_front} mm"],
                    ["Width (rear)", f"{ti.tire_width_rear} mm"],
                    ["Base Grip", ti.base_grip],
                    ["Wet Grip", ti.wet_grip],
                    ["Wear Resistance", ti.tire_wear_resistance],
                    ["Heat Resistance", ti.tire_heat_resistance],
                    ["Warmup", ti.tire_warmup],
                ],
            ),
            TableData(
                "Brakes",
                ["Stat", "Value"],
                [
                    ["Braking Power", br.braking_power],
                    ["Stability", br.brake_stability],
                    ["Cooling", br.brake_cooling],
                    ["Fade Resistance", br.brake_fade_resistance],
                ],
            ),
            TableData(
                "Suspension",
                ["Stat", "Value"],
                [
                    ["Handling", su.handling],
                    ["Mechanical Grip", su.mechanical_grip],
                    ["Compliance", su.suspension_compliance],
                    ["Curb Handling", su.curb_handling],
                    ["Bump Absorption", su.bump_absorption],
                    ["Steering Precision", su.steering_precision],
                ],
            ),
            TableData(
                "Aerodynamics",
                ["Stat", "Value"],
                [
                    ["Downforce", ae.downforce],
                    ["Drag", ae.drag],
                    ["Aero Efficiency", ae.aero_efficiency],
                    ["High Speed Stability", ae.high_speed_stability],
                ],
            ),
            TableData(
                "Durability",
                ["Stat", "Value"],
                [
                    ["Overall Reliability", du.overall_reliability],
                    ["Engine", du.engine_reliability],
                    ["Gearbox", du.gearbox_reliability],
                    ["Suspension", du.suspension_durability],
                    ["Brakes", du.brake_durability],
                    ["Cooling Capacity", du.cooling_capacity],
                    ["Mech Sympathy Modifier", f"{du.mechanical_sympathy_modifier:+d}"],
                ],
            ),
            TableData(
                "Fuel",
                ["Stat", "Value"],
                [
                    ["Tank Capacity", f"{fu.fuel_capacity_l:.1f} L"],
                    ["Base Burn Rate", f"{fu.base_fuel_burn:.2f} L/lap"],
                    ["Efficiency Rating", fu.fuel_efficiency],
                ],
            ),
            TableData(
                "Condition",
                ["Area", "Value"],
                [
                    ["Overall", f"{co.overall_condition:.0f}%"],
                    ["Engine", f"{co.engine_condition:.0f}%"],
                    ["Gearbox", f"{co.gearbox_condition:.0f}%"],
                    ["Suspension", f"{co.suspension_condition:.0f}%"],
                    ["Brakes", f"{co.brake_condition:.0f}%"],
                    ["Body", f"{co.body_condition:.0f}%"],
                    ["Tires", f"{co.tire_condition:.0f}%"],
                    ["Mileage", f"{co.mileage:,} km"],
                ],
            ),
            TableData(
                "Tune Setup",
                ["Setting", "Value"],
                [
                    ["Engine Map", tu.engine_map],
                    ["Tire Pressure (F)", f"{tu.tire_pressure_front:.1f} psi"],
                    ["Tire Pressure (R)", f"{tu.tire_pressure_rear:.1f} psi"],
                    ["Final Drive", f"{tu.final_drive:.2f}"],
                    ["Gear Bias", f"{tu.gear_bias:.2f}"],
                    ["Brake Bias", f"{tu.brake_bias:.0f}% front"],
                    ["Brake Pressure", f"{tu.brake_pressure:.0f}%"],
                    ["Ride Height (F)", f"{tu.front_ride_height} mm"],
                    ["Ride Height (R)", f"{tu.rear_ride_height} mm"],
                    ["Suspension Stiffness (F)", tu.suspension_stiffness_front],
                    ["Suspension Stiffness (R)", tu.suspension_stiffness_rear],
                    ["Anti-Roll (F)", tu.antiroll_front],
                    ["Anti-Roll (R)", tu.antiroll_rear],
                    ["Camber (F)", f"{tu.camber_front:.1f}°"],
                    ["Camber (R)", f"{tu.camber_rear:.1f}°"],
                    ["Toe (F)", f"{tu.toe_front:+.2f}°"],
                    ["Toe (R)", f"{tu.toe_rear:+.2f}°"],
                    ["Downforce (F)", tu.front_downforce],
                    ["Downforce (R)", tu.rear_downforce],
                    ["Diff Power", f"{tu.differential_power}%"],
                    ["Diff Coast", f"{tu.differential_coast}%"],
                    ["Diff Preload", f"{tu.differential_preload} Nm"],
                ],
            ),
        ],
    )


def driver_detail_screen(driver_id: str) -> ScreenData:
    driver = next((driver for driver in load_drivers() if driver.id == driver_id), None)
    if driver is None:
        raise ValueError(f"Unknown driver: {driver_id}")
    return ScreenData(
        name="driver_detail",
        title=driver.name,
        subtitle=driver.id,
        tables=[
            TableData(
                "Driver Stats",
                ["Stat", "Value"],
                [
                    ["Pace", driver.pace],
                    ["Consistency", driver.consistency],
                    ["Racecraft", driver.racecraft],
                    ["Feedback", driver.feedback],
                    ["Fitness", driver.fitness],
                    ["Aggression", driver.aggression],
                    ["Mechanical Sympathy", driver.mechanical_sympathy],
                    ["Wet Skill", driver.wet_skill],
                    ["Salary", f"${driver.salary}"],
                    ["Experience", driver.experience],
                ],
            )
        ],
    )


def event_detail_screen(event_id: str) -> ScreenData:
    event = next((event for event in load_events() if event.id == event_id), None)
    if event is None:
        raise ValueError(f"Unknown event: {event_id}")
    tracks = {track.id: track for track in load_tracks()}
    track = tracks[event.track_id]
    return ScreenData(
        name="event_detail",
        title=event.name,
        subtitle=track.name,
        tables=[
            TableData(
                "Event",
                ["Field", "Value"],
                [
                    ["ID", event.id],
                    ["Class Limit", event.car_class_limit],
                    ["Entry Fee", f"${event.entry_fee}"],
                    ["Laps", track.laps],
                    ["Length", f"{track.length_km} km"],
                    ["Opponents", event.opponent_count],
                    ["Prizes", ", ".join(f"${prize}" for prize in event.prize_money)],
                ],
            ),
            TableData(
                "Restrictions",
                ["Rule", "Value"],
                [[key, value] for key, value in event.restrictions.items()],
            ),
        ],
    )


def race_entry_screen(state: GameState, step: str = "events") -> ScreenData:
    if step == "cars":
        return garage_screen(state)
    if step == "drivers":
        drivers = state.hired_drivers or load_drivers()
        screen = drivers_screen(state)
        screen.tables[0].rows = [
            [index, driver.id, driver.name, driver.pace, driver.consistency, driver.feedback, f"${driver.salary}"]
            for index, driver in enumerate(drivers, start=1)
        ]
        return screen
    return events_screen()


def _table_title(title: str, screen: str, sort_spec: SortSpec | None) -> str:
    if sort_spec is None:
        return title
    return f"{title} (sorted by {sort_label(screen, sort_spec)})"


def tune_fields_screen(state: GameState, car_id: str) -> ScreenData:
    car = next((garage_car for garage_car in state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown garage car: {car_id}")
    fields = tune_fields_for_car(state, car_id)
    return ScreenData(
        name="tune",
        title="Tune",
        subtitle=car.identity.name,
        tables=[
            TableData(
                "Tune Fields",
                ["#", "Field", "Current", "Allowed"],
                [
                    [
                        index,
                        field.label,
                        field.current,
                        _allowed_text(field),
                    ]
                    for index, field in enumerate(fields, start=1)
                ],
            )
        ],
        fields=fields,
    )


def tune_fields_for_car(state: GameState, car_id: str) -> list[FieldData]:
    car = next((garage_car for garage_car in state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise ValueError(f"Unknown garage car: {car_id}")
    names = [
        "tire_pressure_front",
        "tire_pressure_rear",
        "final_drive",
        "brake_bias",
        "front_ride_height",
        "rear_ride_height",
        "camber_front",
        "camber_rear",
        "front_downforce",
        "rear_downforce",
        "engine_map",
    ]
    return [_field_data(name, getattr(car.tune, name)) for name in names]


def _field_data(name: str, current: Any) -> FieldData:
    if name == "engine_map":
        return FieldData(
            name=name,
            label=_field_label(name),
            current=current,
            value_type="choice",
            options=[OptionData(value=value, label=_engine_map_label(value)) for value in sorted(ENGINE_MAP_POWER)],
        )
    minimum, maximum = TUNE_FIELD_RANGES[name]
    value_type = "integer" if isinstance(current, int) else "number"
    return FieldData(
        name=name,
        label=_field_label(name),
        current=current,
        value_type=value_type,
        minimum=minimum,
        maximum=maximum,
    )


def _field_label(name: str) -> str:
    return name.replace("_", " ").title()


def _engine_map_label(value: str) -> str:
    labels = {
        "balanced": "Balanced",
        "fuel_save": "Fuel Save",
        "hot": "Hot",
        "qualifying": "Qualifying",
        "safe": "Safe",
    }
    return labels.get(value, value.replace("_", " ").title())


def _allowed_text(field: FieldData) -> str:
    if field.options:
        return ", ".join(option.label for option in field.options)
    return f"{field.minimum:g}-{field.maximum:g}"


def _gauge_bar(value: float, max_val: float = 100.0, width: int = 16) -> str:
    filled = round(max(0.0, min(value / max_val, 1.0)) * width)
    return "█" * filled + "░" * (width - filled)


_RACE_LOG_VISIBLE_EVENTS = 10


def race_screen(session: RaceSession, tick: RaceTickResult | None = None, error: str = "") -> ScreenData:
    player = next(car for car in session.cars if car.is_player)
    messages = []
    if error:
        messages.append(f"Race command error: {error}")
    if tick is None:
        messages.append("Awaiting race command.")
    tables = []
    if tick is not None:
        tables.append(
            TableData(
                "Standings",
                ["P", "Car", "Gap", "Last", "Tires", "Fuel"],
                [
                    [
                        car.position,
                        car.label,
                        f"+{car.gap_to_leader:.3f}",
                        f"{car.last_lap_time or 0.0:.3f}",
                        f"{car.tire_pct:.0f}%",
                        f"{car.fuel_pct:.0f}%",
                    ]
                    for car in tick.standings
                ],
            )
        )
    tables.append(
        TableData(
            "Player Status",
            ["", ""],
            [
                ["Tires",  f"[{_gauge_bar(player.tire_pct)}]  {player.tire_pct:3.0f}%  {player.tire_temp:.0f}°C"],
                ["Fuel",   f"[{_gauge_bar(player.fuel_pct)}]  {player.fuel_pct:3.0f}%"],
                ["Engine", f"[{_gauge_bar(player.engine_temp, ENGINE_CRITICAL_C)}]  {player.engine_temp:.0f}°C"],
                ["Energy", f"[{_gauge_bar(player.driver_energy)}]  {player.driver_energy:3.0f}%"],
                ["Focus",  f"[{_gauge_bar(player.driver_focus)}]  {player.driver_focus:3.0f}%"],
                ["Stress", f"[{_gauge_bar(player.driver_stress)}]  {player.driver_stress:3.0f}%"],
            ],
        )
    )
    if session.race_log:
        rows = [[lap, message] for lap, message in session.race_log[-_RACE_LOG_VISIBLE_EVENTS:]]
        tables.append(TableData("Race Log", ["Lap", "Event"], rows))
    return ScreenData(
        name="race",
        title="Race",
        subtitle=(
            f"Lap {session.current_lap}/{session.total_laps}"
            + (f" · S{session.current_sub_tick}/{session.ticks_per_lap}" if session.ticks_per_lap > 1 else "")
        ),
        tables=tables,
        messages=messages,
        actions=race_command_options(),
    )


def race_command_options() -> list[OptionData]:
    return [
        OptionData("normal", "Normal", "N", "Balanced pace"),
        OptionData("conserve", "Conserve", "C", "Lower tire/fuel/heat cost, slower"),
        OptionData("push", "Push", "P", "Faster, higher tire/fuel/heat cost"),
        OptionData("attack", "Attack", "A", "Faster near rivals, more risk"),
        OptionData("defend", "Defend", "D", "Protect position, modest cost"),
        OptionData("safe_map", "Safe Map", "S", "Cooler, lower fuel use, slower"),
        OptionData("hot_map", "Hot Map", "H", "More pace and heat"),
        OptionData("fuel_save", "Fuel Save", "F", "Much lower fuel use, slower"),
        OptionData("pit", "Pit", "I", "Lose pit time, restore tires and fuel"),
    ]


def hire_driver_action(state: GameState, driver_id: str) -> ActionResult:
    hire_driver(state, driver_id)
    driver = next(d for d in state.hired_drivers if d.id == driver_id)
    return ActionResult(state=state, message=f"Hired {driver.name}.", screen=drivers_screen(state))


def fire_driver_action(state: GameState, driver_id: str) -> ActionResult:
    driver = next((d for d in state.hired_drivers if d.id == driver_id), None)
    name = driver.name if driver else driver_id
    fire_driver(state, driver_id)
    return ActionResult(state=state, message=f"Released {name}.", screen=drivers_screen(state))


def buy_car_action(state: GameState, car_id: str) -> ActionResult:
    buy_car(state, car_id)
    return ActionResult(state=state, message=f"Bought {car_id}.", screen=garage_screen(state))


def sell_car_action(state: GameState, car_id: str) -> ActionResult:
    sell_car(state, car_id)
    return ActionResult(state=state, message=f"Sold {car_id}.", screen=garage_screen(state))


def repair_car_action(state: GameState, car_id: str) -> ActionResult:
    repair_car(state, car_id)
    return ActionResult(state=state, message=f"Repaired {car_id}.", screen=garage_screen(state))


def tune_car_action(state: GameState, car_id: str, field_name: str, value: Any) -> ActionResult:
    update_tune_fields(state, car_id, **{field_name: value})
    return ActionResult(state=state, message=f"Updated {field_name}.", screen=garage_screen(state))


def save_game_action(state: GameState, path: str | Path = "saves/save1.json") -> ActionResult:
    save_game(state, Path(path))
    return ActionResult(state=state, message="Saved.")


def load_game_action(path: str | Path = "saves/save1.json") -> ActionResult:
    state = load_game(Path(path))
    return ActionResult(state=state, message="Loaded.", screen=garage_screen(state))


def start_race_action(state: GameState, event_id: str, car_id: str, driver_id: str, seed: int | None = None) -> RaceActionResult:
    if seed is None:
        seed = random.randrange(1, 1_000_000)
    session = enter_event(state, event_id, car_id, driver_id, seed=seed)
    return RaceActionResult(session=session, screen=race_screen(session))


def advance_race_action(session: RaceSession, command: str) -> RaceActionResult:
    tick = apply_player_command(session, command)
    return RaceActionResult(session=session, tick=tick, screen=race_screen(session, tick))


def simulate_to_end_action(session: RaceSession, command: str = "normal") -> RaceActionResult:
    """Advance all remaining ticks instantly with the given command; return final state."""
    last_tick: RaceTickResult | None = None
    while not session.is_finished:
        result = advance_race_action(session, command)
        last_tick = result.tick
    screen = race_screen(session, last_tick)
    return RaceActionResult(session=session, tick=last_tick, screen=screen)


def finish_race_action(state: GameState, session: RaceSession) -> RaceActionResult:
    prize, progression_message = finish_event(state, session)
    screen = race_screen(session)
    if progression_message:
        screen.messages.append(progression_message)
    return RaceActionResult(session=session, screen=screen, prize_money=prize)
