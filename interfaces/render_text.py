from __future__ import annotations

from game.effective_stats import class_rating, derived_class, performance_type
from game.event_display import event_best_text, event_requirement_text, team_status_text
from game.game_state import GameState
from game.models import Car, Driver, Event, Part, RaceCarState, RaceSession, Track
from game.sorting import SortSpec, sort_items


def render_garage(game_state: GameState) -> str:
    if not game_state.garage:
        return "Garage is empty."
    return "\n".join(
        f"{car.identity.id}: {car.identity.name} ({derived_class(car)}) "
        f"PR {class_rating(car)} {performance_type(car)} condition {car.condition.overall_condition:.0f}%"
        for car in game_state.garage
    )


def render_drivers(drivers: list[Driver]) -> str:
    return "\n".join(f"{driver.id}: {driver.name} pace {driver.pace}" for driver in drivers)


def render_events(events: list[Event]) -> str:
    return "\n".join(f"{event.id}: {event.name} entry ${event.entry_fee}" for event in events)


def render_market(game_state: GameState) -> str:
    from game.market import list_market_cars

    return "\n".join(
        f"{car.identity.id}: {car.identity.name} ${car.value} class {derived_class(car)} "
        f"PR {class_rating(car)} {performance_type(car)}"
        for car in list_market_cars()
    )


def render_parts(parts: list[Part]) -> str:
    return "\n".join(f"{part.id}: {part.name} ${part.cost}" for part in parts)


def render_standings(cars: list[RaceCarState]) -> str:
    return "\n".join(
        f"P{car.position} {car.label:8} +{car.gap_to_leader:.3f} last {car.last_lap_time or 0.0:.3f}"
        for car in cars
    )


def render_race_status(session: RaceSession) -> str:
    player = next(car for car in session.cars if car.is_player)
    return (
        f"Lap {session.current_lap}/{session.total_laps}\n"
        f"Tires {player.tire_pct:.0f}% {player.tire_temp:.0f}C | "
        f"Fuel {player.fuel_pct:.0f}% | Engine {player.engine_temp:.0f}C\n"
        f"Driver energy {player.driver_energy:.0f}% focus {player.driver_focus:.0f}% stress {player.driver_stress:.0f}%"
    )


def garage_rows(game_state: GameState, sort_spec: SortSpec | None = None) -> list[list[object]]:
    cars = sort_items("garage", game_state.garage, sort_spec)
    return [
        [
            index,
            car.identity.id,
            car.identity.name,
            derived_class(car),
            class_rating(car),
            performance_type(car),
            f"{car.condition.overall_condition:.0f}%",
            f"{car.powertrain.power_hp} hp",
        ]
        for index, car in enumerate(cars, start=1)
    ]


def driver_rows(drivers: list[Driver], sort_spec: SortSpec | None = None) -> list[list[object]]:
    sorted_drivers = sort_items("drivers", drivers, sort_spec)
    return [
        [
            index,
            driver.id,
            driver.name,
            driver.pace,
            driver.consistency,
            driver.feedback,
            driver.potential,
            f"${driver.salary}",
        ]
        for index, driver in enumerate(sorted_drivers, start=1)
    ]


def event_rows(
    events: list[Event],
    tracks: dict[str, Track],
    sort_spec: SortSpec | None = None,
    state: GameState | None = None,
) -> list[list[object]]:
    sorted_events = sort_items("events", events, sort_spec)
    return [
        [
            index,
            event.id,
            event.name,
            tracks[event.track_id].name if event.track_id in tracks else event.track_id,
            event.car_class_limit,
            event_requirement_text(event),
            team_status_text(state, event) if state is not None else "-",
            event_best_text(state.event_progress.get(event.id)) if state is not None else "-",
            f"${event.entry_fee}",
            event.opponent_count,
        ]
        for index, event in enumerate(sorted_events, start=1)
    ]


def market_rows(cars: list[Car], sort_spec: SortSpec | None = None) -> list[list[object]]:
    sorted_cars = sort_items("market", cars, sort_spec)
    return [
        [
            index,
            car.identity.id,
            car.identity.name,
            derived_class(car),
            class_rating(car),
            performance_type(car),
            f"${car.value}",
            f"{car.powertrain.power_hp} hp",
            f"{car.condition.overall_condition:.0f}%",
        ]
        for index, car in enumerate(sorted_cars, start=1)
    ]


def standings_rows(cars: list[RaceCarState]) -> list[list[object]]:
    return [
        [
            car.position,
            car.label,
            f"+{car.gap_to_leader:.3f}",
            f"{car.last_lap_time or 0.0:.3f}",
            f"{car.tire_pct:.0f}%",
            f"{car.fuel_pct:.0f}%",
        ]
        for car in cars
    ]
