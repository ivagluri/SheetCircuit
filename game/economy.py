from __future__ import annotations

from copy import deepcopy

from constants import (
    PERCENT_MAX,
    REPAIR_COST_MIN_PER_POINT,
    REPAIR_COST_VALUE_FRACTION,
    REPAIR_MAX_POINTS,
    SELL_CONDITION_WEIGHT,
    SELL_MILEAGE_FLOOR,
    SELL_MILEAGE_FULL_KM,
    SELL_VALUE_FACTOR,
)
from game.game_state import GameState
from game.loader import load_cars, load_parts
from game.market import list_free_agents, list_market_cars
from game.models import Part
from game.parts import SLOT_RULE_BY_ID, canonical_part_id, installed_part_for_slot, normalize_part_ids, part_map


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


_REPAIR_FIELDS = [
    "overall_condition",
    "engine_condition",
    "brake_condition",
    "suspension_condition",
    "tire_condition",
]


def repair_cost(car, points: float = REPAIR_MAX_POINTS) -> int:
    total_points = sum(_repair_restorations(car, points).values())
    return round(total_points * _repair_cost_per_point(car))


def _repair_cost_per_point(car) -> float:
    return max(REPAIR_COST_MIN_PER_POINT, car.value * REPAIR_COST_VALUE_FRACTION)


def repair_car(game_state: GameState, car_id: str, points: float = REPAIR_MAX_POINTS) -> GameState:
    car = _garage_car(game_state, car_id)
    restorations = _repair_restorations(car, points)
    cost = repair_cost(car, points)
    if game_state.money < cost:
        raise EconomyError(f"Insufficient funds for repair: {cost}")
    game_state.money -= cost
    for field, restored in restorations.items():
        setattr(car.condition, field, getattr(car.condition, field) + restored)
    return game_state


def _repair_restorations(car, points: float) -> dict[str, float]:
    points = max(0.0, points)
    return {
        field: max(0.0, min(points, PERCENT_MAX - getattr(car.condition, field)))
        for field in _REPAIR_FIELDS
    }


def hire_driver(game_state: GameState, driver_id: str) -> GameState:
    pool = list_free_agents(game_state)
    driver = next((d for d in pool if d.id == driver_id), None)
    if driver is None:
        raise EconomyError(f"Driver {driver_id} is not on the market")
    if any(d.id == driver_id for d in game_state.hired_drivers):
        raise EconomyError(f"{driver.name} is already on your team")
    if game_state.money < driver.salary:
        raise EconomyError(f"Insufficient funds to hire {driver.name} (salary: ${driver.salary})")
    game_state.money -= driver.salary
    game_state.hired_drivers.append(deepcopy(driver))
    game_state.free_agents = [d for d in game_state.free_agents if d.id != driver_id]
    return game_state


def fire_driver(game_state: GameState, driver_id: str) -> GameState:
    driver = next((d for d in game_state.hired_drivers if d.id == driver_id), None)
    if driver is None:
        raise EconomyError(f"Driver {driver_id} is not on your team")
    game_state.hired_drivers.remove(driver)
    return game_state


def buy_part(game_state: GameState, car_id: str, part_id: str, *, install: bool = False) -> GameState:
    car = _garage_car(game_state, car_id)
    parts = load_parts()
    part = _part(parts, part_id)
    _normalize_car_parts(car)
    if part.id in car.owned_parts:
        raise EconomyError(f"{part.name} is already owned for {car.identity.name}")
    _validate_stage_purchase(car, part, parts)
    if game_state.money < part.cost:
        raise EconomyError(f"Insufficient funds for {part.name} (cost: ${part.cost})")
    game_state.money -= part.cost
    car.owned_parts.append(part.id)
    if install:
        _install_owned_part(car, part, parts)
    return game_state


def install_part(game_state: GameState, car_id: str, part_id: str) -> GameState:
    car = _garage_car(game_state, car_id)
    parts = load_parts()
    part = _part(parts, part_id)
    _normalize_car_parts(car)
    if part.id not in car.owned_parts:
        raise EconomyError(f"{part.name} is not owned for {car.identity.name}")
    _install_owned_part(car, part, parts)
    return game_state


def uninstall_part(game_state: GameState, car_id: str, slot_or_part_id: str) -> GameState:
    car = _garage_car(game_state, car_id)
    parts = load_parts()
    by_id = part_map(parts)
    _normalize_car_parts(car)
    token = canonical_part_id(slot_or_part_id)
    slot = by_id[token].slot if token in by_id else token
    if slot not in SLOT_RULE_BY_ID:
        raise EconomyError(f"Unknown part slot or part id: {slot_or_part_id}")
    installed = installed_part_for_slot(car, slot, parts)
    if installed is None:
        raise EconomyError(f"No part installed in {SLOT_RULE_BY_ID[slot].label}")
    car.installed_parts = [
        part_id
        for part_id in normalize_part_ids(car.installed_parts)
        if by_id.get(part_id) is None or by_id[part_id].slot != slot
    ]
    _reset_tune_fields_for_removed_unlocks(car, installed.unlocks)
    return game_state


def _garage_car(game_state: GameState, car_id: str):
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise EconomyError(f"Unknown garage car: {car_id}")
    return car


def _part(parts: list[Part], part_id: str) -> Part:
    by_id = part_map(parts)
    canonical = canonical_part_id(part_id)
    part = by_id.get(canonical)
    if part is None:
        raise EconomyError(f"Unknown part: {part_id}")
    return part


def _normalize_car_parts(car) -> None:
    car.installed_parts = normalize_part_ids(car.installed_parts)
    car.owned_parts = normalize_part_ids(getattr(car, "owned_parts", []))
    for part_id in car.installed_parts:
        if part_id not in car.owned_parts:
            car.owned_parts.append(part_id)


def _validate_stage_purchase(car, part: Part, parts: list[Part]) -> None:
    rule = SLOT_RULE_BY_ID[part.slot]
    if not rule.staged or part.stage <= 1:
        return
    previous = next((candidate for candidate in parts if candidate.slot == part.slot and candidate.stage == part.stage - 1), None)
    if previous is None:
        raise EconomyError(f"{part.name} has no previous stage in the catalog")
    if previous.id not in car.owned_parts:
        raise EconomyError(f"{part.name} requires owning {previous.name} first")


def _install_owned_part(car, part: Part, parts: list[Part]) -> None:
    by_id = part_map(parts)
    car.installed_parts = [
        part_id
        for part_id in normalize_part_ids(car.installed_parts)
        if by_id.get(part_id) is None or by_id[part_id].slot != part.slot
    ]
    car.installed_parts.append(part.id)


def _reset_tune_fields_for_removed_unlocks(car, unlocks: list[str]) -> None:
    if not unlocks:
        return
    from game.parts import TUNE_FIELD_UNLOCKS, UNLOCK_ECU

    if UNLOCK_ECU in unlocks:
        car.tune.engine_map = "balanced"
    for field_name, unlock in TUNE_FIELD_UNLOCKS.items():
        if unlock in unlocks:
            _reset_tune_field_to_stock(car, field_name)


def _reset_tune_field_to_stock(car, field_name: str) -> None:
    stock = next((candidate for candidate in load_cars() if candidate.identity.id == car.identity.id), None)
    if stock is not None:
        setattr(car.tune, field_name, getattr(stock.tune, field_name))
        return
    fallback = {
        "final_drive": 4.0,
        "gear_bias": 0.0,
        "brake_bias": 0.60,
        "brake_pressure": 1.0,
        "front_ride_height": 135,
        "rear_ride_height": 135,
        "suspension_stiffness_front": 50,
        "suspension_stiffness_rear": 50,
        "antiroll_front": 5,
        "antiroll_rear": 5,
        "camber_front": -2.0,
        "camber_rear": -2.0,
        "toe_front": 0.0,
        "toe_rear": 0.0,
        "front_downforce": 0,
        "rear_downforce": 0,
        "differential_power": 30,
        "differential_coast": 15,
        "differential_preload": 12,
    }
    if field_name in fallback:
        setattr(car.tune, field_name, fallback[field_name])
