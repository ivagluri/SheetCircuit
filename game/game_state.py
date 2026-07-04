from __future__ import annotations

from dataclasses import dataclass, field

from constants import STARTING_MONEY, STARTING_WEEK
from game.loader import load_cars, load_drivers
from game.models import Car, Driver


@dataclass
class GameState:
    money: int = STARTING_MONEY
    week: int = STARTING_WEEK
    team_xp: int = 0
    garage: list[Car] = field(default_factory=list)
    hired_drivers: list[Driver] = field(default_factory=list)
    event_progress: dict[str, dict] = field(default_factory=dict)


def new_game() -> GameState:
    return GameState()


def _starter_car(cars: list[Car]) -> Car:
    """Cheapest entry-class car, chosen by criteria rather than a hardcoded id, so the
    career still starts even if the seed catalog changes. Prefers the lowest class
    present, then the cheapest car within it."""
    if not cars:
        raise ValueError("No cars available to start a career")
    from game.effective_stats import derived_class
    class_order = {"E": 0, "D": 1, "C": 2, "B": 3, "A": 4, "S": 5}
    return min(cars, key=lambda c: (class_order.get(derived_class(c), 99), c.value))


def _starter_driver(drivers: list[Driver]) -> Driver:
    """A rookie to start with: the cheapest-salary driver available."""
    if not drivers:
        raise ValueError("No drivers available to start a career")
    return min(drivers, key=lambda d: d.salary)


def new_career() -> GameState:
    return GameState(
        garage=[_starter_car(load_cars())],
        hired_drivers=[_starter_driver(load_drivers())],
    )
