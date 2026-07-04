from __future__ import annotations

from copy import deepcopy

from constants import (
    PERCENT_MAX,
    REPAIR_COST_PER_POINT,
    REPAIR_MAX_POINTS,
    SELL_CONDITION_WEIGHT,
    SELL_MILEAGE_FLOOR,
    SELL_MILEAGE_FULL_KM,
    SELL_VALUE_FACTOR,
)
from game.game_state import GameState
from game.loader import load_cars, load_drivers
from game.market import list_market_cars


class EconomyError(ValueError):
    """Raised when an economy operation cannot be completed."""


def buy_car(game_state: GameState, market_car_id: str) -> GameState:
    market = {car.identity.id: car for car in list_market_cars()}
    if market_car_id not in market:
        raise EconomyError(f"Unknown market car: {market_car_id}")
    car = market[market_car_id]
    if game_state.money < car.value:
        raise EconomyError(f"Insufficient funds for {car.identity.name}")
    game_state.money -= car.value
    game_state.garage.append(deepcopy(car))
    return game_state


def sell_car(game_state: GameState, car_id: str) -> GameState:
    car = _garage_car(game_state, car_id)
    sale_price = round(car.value * SELL_VALUE_FACTOR * _resale_factor(car))
    game_state.money += sale_price
    game_state.garage.remove(car)
    return game_state


def _resale_factor(car) -> float:
    """Condition and mileage depreciate resale: a clean low-miler sells near the full
    sell factor, a thrashed high-miler well below it. Racing (which wears condition and
    adds mileage) now has a real cost on the way out of the garage."""
    condition = 1.0 - SELL_CONDITION_WEIGHT * (1.0 - car.condition.overall_condition / PERCENT_MAX)
    mileage = max(
        SELL_MILEAGE_FLOOR,
        1.0 - car.condition.mileage / SELL_MILEAGE_FULL_KM * (1.0 - SELL_MILEAGE_FLOOR),
    )
    return condition * mileage


def repair_car(game_state: GameState, car_id: str, points: float = REPAIR_MAX_POINTS) -> GameState:
    car = _garage_car(game_state, car_id)
    fields = [
        "overall_condition",
        "engine_condition",
        "brake_condition",
        "suspension_condition",
        "tire_condition",
    ]
    restorations = {
        field: min(points, PERCENT_MAX - getattr(car.condition, field))
        for field in fields
    }
    total_points = sum(restorations.values())
    cost = round(total_points * REPAIR_COST_PER_POINT)
    if game_state.money < cost:
        raise EconomyError(f"Insufficient funds for repair: {cost}")
    game_state.money -= cost
    for field, restored in restorations.items():
        setattr(car.condition, field, getattr(car.condition, field) + restored)
    return game_state


def hire_driver(game_state: GameState, driver_id: str) -> GameState:
    pool = {driver.id: driver for driver in load_drivers()}
    if driver_id not in pool:
        raise EconomyError(f"Unknown driver: {driver_id}")
    if any(d.id == driver_id for d in game_state.hired_drivers):
        raise EconomyError(f"{pool[driver_id].name} is already on your team")
    driver = pool[driver_id]
    if game_state.money < driver.salary:
        raise EconomyError(f"Insufficient funds to hire {driver.name} (salary: ${driver.salary})")
    game_state.money -= driver.salary
    game_state.hired_drivers.append(deepcopy(driver))
    return game_state


def fire_driver(game_state: GameState, driver_id: str) -> GameState:
    driver = next((d for d in game_state.hired_drivers if d.id == driver_id), None)
    if driver is None:
        raise EconomyError(f"Driver {driver_id} is not on your team")
    game_state.hired_drivers.remove(driver)
    return game_state


def _garage_car(game_state: GameState, car_id: str):
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise EconomyError(f"Unknown garage car: {car_id}")
    return car
