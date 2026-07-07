from __future__ import annotations

from constants import (
    ENGINE_MAP_POWER,
    TUNE_FIELD_RANGES,
)
from game.game_state import GameState
from game.loader import load_parts
from game.models import Car
from game.parts import TUNE_UNLOCK_LABELS, is_tune_setup_field, tune_unlock_required_for_value


class TuningError(ValueError):
    """Raised when a tune cannot be applied."""


def update_tune_fields(game_state: GameState, car_id: str, **fields: object) -> GameState:
    """Atomically apply setup knobs. Permanent hardware/stat changes live in Upgrades."""
    car = _garage_car(game_state, car_id)
    targets = {name: tune_target(car, name) for name in fields}
    for name, value in fields.items():
        _validate_tune_value(car, name, value, getattr(targets[name], name))
    for name, value in fields.items():
        setattr(targets[name], name, value)
    return game_state


def validate_tune_field(game_state: GameState, car_id: str, name: str, value: object) -> None:
    """Validate one prospective tune value without applying it (raises TuningError).

    Lets an editor stage a draft field-by-field with the same rules
    update_tune_fields enforces when the whole draft is applied."""
    car = _garage_car(game_state, car_id)
    _validate_tune_value(car, name, value, getattr(tune_target(car, name), name))


def tune_target(car: Car, name: str) -> object:
    """The object that owns tune field ``name``: the car's setup sheet."""
    if hasattr(car.tune, name):
        return car.tune
    raise TuningError(f"Unknown tune field: {name}")


def _garage_car(game_state: GameState, car_id: str) -> Car:
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise TuningError(f"Unknown garage car: {car_id}")
    return car


def _validate_tune_value(car: Car, name: str, value: object, current_value: object) -> None:
    if value == "":
        raise TuningError(f"{name} cannot be blank")
    if not is_tune_setup_field(name):
        raise TuningError(f"Unknown tune field: {name}")
    if name == "engine_map":
        if not isinstance(value, str) or value not in ENGINE_MAP_POWER:
            valid = ", ".join(sorted(ENGINE_MAP_POWER))
            raise TuningError(f"Invalid engine_map: {value!r}. Valid values: {valid}")
        _validate_tune_unlock(car, name, value)
        return
    if isinstance(current_value, bool):
        return
    if isinstance(current_value, int) and not isinstance(value, int):
        raise TuningError(f"{name} must be an integer")
    if isinstance(current_value, float) and not isinstance(value, (int, float)):
        raise TuningError(f"{name} must be a number")
    bounds = TUNE_FIELD_RANGES.get(name)
    if bounds is not None:
        low, high = bounds
        numeric_value = float(value)
        if numeric_value < low or numeric_value > high:
            raise TuningError(f"{name} must be between {low:g} and {high:g}")
    _validate_tune_unlock(car, name, value)


def _validate_tune_unlock(car: Car, name: str, value: object) -> None:
    required = tune_unlock_required_for_value(name, value)
    if not required:
        return
    from game.parts import installed_unlocks

    if required not in installed_unlocks(car, load_parts()):
        raise TuningError(f"{name} requires installed {TUNE_UNLOCK_LABELS[required]}")
