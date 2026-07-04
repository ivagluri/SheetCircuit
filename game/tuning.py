from __future__ import annotations

from copy import deepcopy
from dataclasses import fields

from constants import (
    CAR_MOD_FIELD_RANGES,
    CAR_MOD_FIELD_SECTIONS,
    ENGINE_MAP_POWER,
    TIRE_COMPOUNDS,
    TUNE_FIELD_RANGES,
)
from game.game_state import GameState
from game.models import Car, TuneSetup


class TuningError(ValueError):
    """Raised when a tune cannot be applied."""


def set_tune(game_state: GameState, car_id: str, tune_setup: TuneSetup) -> GameState:
    car = _garage_car(game_state, car_id)
    for field in fields(TuneSetup):
        _validate_tune_value(field.name, getattr(tune_setup, field.name), getattr(car.tune, field.name))
    car.tune = deepcopy(tune_setup)
    return game_state


def update_tune_fields(game_state: GameState, car_id: str, **fields: object) -> GameState:
    """Atomically apply setup knobs (TuneSetup) and/or hard-mod stats (CAR_MOD_FIELD_SECTIONS)."""
    car = _garage_car(game_state, car_id)
    targets = {name: tune_target(car, name) for name in fields}
    for name, value in fields.items():
        _validate_tune_value(name, value, getattr(targets[name], name))
    for name, value in fields.items():
        setattr(targets[name], name, value)
    return game_state


def validate_tune_field(game_state: GameState, car_id: str, name: str, value: object) -> None:
    """Validate one prospective tune value without applying it (raises TuningError).

    Lets an editor stage a draft field-by-field with the same rules
    update_tune_fields enforces when the whole draft is applied."""
    car = _garage_car(game_state, car_id)
    _validate_tune_value(name, value, getattr(tune_target(car, name), name))


def tune_target(car: Car, name: str) -> object:
    """The object that owns tune field ``name``: the TuneSetup for setup knobs, or the
    car stat section (tires/brakes/chassis/...) for garage-tweakable hard mods."""
    if hasattr(car.tune, name):
        return car.tune
    section = CAR_MOD_FIELD_SECTIONS.get(name)
    if section is not None:
        return getattr(car, section)
    raise TuningError(f"Unknown tune field: {name}")


def _garage_car(game_state: GameState, car_id: str) -> Car:
    car = next((garage_car for garage_car in game_state.garage if garage_car.identity.id == car_id), None)
    if car is None:
        raise TuningError(f"Unknown garage car: {car_id}")
    return car


def _validate_tune_value(name: str, value: object, current_value: object) -> None:
    if value == "":
        raise TuningError(f"{name} cannot be blank")
    if name == "engine_map":
        if not isinstance(value, str) or value not in ENGINE_MAP_POWER:
            valid = ", ".join(sorted(ENGINE_MAP_POWER))
            raise TuningError(f"Invalid engine_map: {value!r}. Valid values: {valid}")
        return
    if name == "tire_compound":
        if not isinstance(value, str) or value not in TIRE_COMPOUNDS:
            valid = ", ".join(TIRE_COMPOUNDS)
            raise TuningError(f"Invalid tire_compound: {value!r}. Valid values: {valid}")
        return
    if isinstance(current_value, bool):
        return
    if isinstance(current_value, int) and not isinstance(value, int):
        raise TuningError(f"{name} must be an integer")
    if isinstance(current_value, float) and not isinstance(value, (int, float)):
        raise TuningError(f"{name} must be a number")
    bounds = TUNE_FIELD_RANGES.get(name) or CAR_MOD_FIELD_RANGES.get(name)
    if bounds is not None:
        low, high = bounds
        numeric_value = float(value)
        if numeric_value < low or numeric_value > high:
            raise TuningError(f"{name} must be between {low:g} and {high:g}")
