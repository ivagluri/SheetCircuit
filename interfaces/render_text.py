from __future__ import annotations

from game.effective_stats import class_rating, derived_class, performance_type
from game.event_display import event_best_text, event_requirement_text, team_status_text
from game.game_state import GameState
from game.models import Driver, Event, Track
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


def garage_rows(game_state: GameState, sort_spec: SortSpec | None = None) -> list[list[object]]:
    cars = sort_items("garage", game_state.garage, sort_spec)
    return [
        [
            index,
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


