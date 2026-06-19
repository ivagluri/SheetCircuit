from __future__ import annotations

from copy import deepcopy
from dataclasses import fields

from constants import ENGINE_MAP_POWER, TUNE_FIELD_RANGES
from game.game_state import GameState
from game.models import TuneSetup


class TuningError(ValueError):
    """Raised when a tune cannot be applied."""


def set_tune(game_state: GameState, car_id: str, tune_setup: TuneSetup) -> GameState:
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise TuningError(f"Unknown garage car: {car_id}")
    for field in fields(TuneSetup):
        _validate_tune_value(field.name, getattr(tune_setup, field.name), getattr(car.tune, field.name))
    car.tune = deepcopy(tune_setup)
    return game_state


def update_tune_fields(game_state: GameState, car_id: str, **fields: object) -> GameState:
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise TuningError(f"Unknown garage car: {car_id}")
    for name, value in fields.items():
        if not hasattr(car.tune, name):
            raise TuningError(f"Unknown tune field: {name}")
        _validate_tune_value(name, value, getattr(car.tune, name))
    for name, value in fields.items():
        setattr(car.tune, name, value)
    return game_state


def _validate_tune_value(name: str, value: object, current_value: object) -> None:
    if value == "":
        raise TuningError(f"{name} cannot be blank")
    if name == "engine_map":
        if not isinstance(value, str) or value not in ENGINE_MAP_POWER:
            valid = ", ".join(sorted(ENGINE_MAP_POWER))
            raise TuningError(f"Invalid engine_map: {value!r}. Valid values: {valid}")
        return
    if isinstance(current_value, bool):
        return
    if isinstance(current_value, int) and not isinstance(value, int):
        raise TuningError(f"{name} must be an integer")
    if isinstance(current_value, float) and not isinstance(value, (int, float)):
        raise TuningError(f"{name} must be a number")
    if name in TUNE_FIELD_RANGES:
        low, high = TUNE_FIELD_RANGES[name]
        numeric_value = float(value)
        if numeric_value < low or numeric_value > high:
            raise TuningError(f"{name} must be between {low:g} and {high:g}")
