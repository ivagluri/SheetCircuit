from __future__ import annotations

from dataclasses import dataclass, field

from constants import STARTING_MONEY, STARTING_WEEK
from game.loader import load_cars, load_drivers
from game.models import Car, Driver


@dataclass
class GameState:
    money: int = STARTING_MONEY
    week: int = STARTING_WEEK
    garage: list[Car] = field(default_factory=list)
    hired_drivers: list[Driver] = field(default_factory=list)


def new_game() -> GameState:
    return GameState()


def new_career() -> GameState:
    cars = {car.identity.id: car for car in load_cars()}
    drivers = {driver.id: driver for driver in load_drivers()}
    return GameState(garage=[cars["kanto_k660"]], hired_drivers=[drivers["driver_novak"]])
