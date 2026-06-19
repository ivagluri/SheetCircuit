from __future__ import annotations

from copy import deepcopy

from constants import (
    BRAKE_BIAS_IDEAL,
    BRAKE_BIAS_PENALTY,
    CAMBER_IDEAL_DEG,
    CAMBER_PENALTY,
    CLASS_RATING_SCALE,
    CLASS_RATING_WEIGHTS,
    CLASS_THRESHOLDS,
    COOLING_HEAT_REDUCTION,
    DOWNFORCE_DRAG_PENALTY,
    ENGINE_MAP_FUEL,
    ENGINE_MAP_HEAT,
    ENGINE_MAP_POWER,
    FINAL_DRIVE_ACCEL_FACTOR,
    FINAL_DRIVE_IDEAL,
    FINAL_DRIVE_SPEED_FACTOR,
    MIN_CONDITION_FACTOR,
    NORM_ACCEL_REF_HW,
    NORM_AERO_MAX,
    NORM_POWER_REF_HP,
    NORM_SPEED_REF_KMH,
    NORM_TORQUE_REF_NM,
    PERCENT_MAX,
    PERCENT_MIN,
    PRESSURE_IDEAL_BAR,
    PRESSURE_PENALTY,
    RIDE_HEIGHT_IDEAL_MM,
    RIDE_HEIGHT_PENALTY,
    STRESS_RELIABILITY_PENALTY,
    TOP_SPEED_COEFF,
    WEIGHT_REFERENCE_KG,
)
from game.loader import load_parts
from game.models import Car, EffectiveCarStats, Part, TuneSetup


def clamp(value: float, low: float = PERCENT_MIN, high: float = PERCENT_MAX) -> float:
    return max(low, min(high, value))


def apply_part_modifiers(car: Car, parts: list[Part] | None = None) -> Car:
    modified = deepcopy(car)
    part_map = {part.id: part for part in (parts if parts is not None else load_parts())}
    for part_id in modified.installed_parts:
        part = part_map[part_id]
        for path, delta in part.modifiers.items():
            _apply_delta(modified, path, delta)
    return modified


def _apply_delta(car: Car, path: str, delta: int | float) -> None:
    target_name, attr_name = path.split(".", maxsplit=1)
    target = getattr(car, target_name)
    setattr(target, attr_name, getattr(target, attr_name) + delta)


def set_tune(car: Car, tune_setup: TuneSetup) -> Car:
    tuned = deepcopy(car)
    tuned.tune = deepcopy(tune_setup)
    return tuned


def compute_effective_stats(car: Car, parts: list[Part] | None = None, command: str = "normal") -> EffectiveCarStats:
    modified = apply_part_modifiers(car, parts)
    tune = modified.tune
    engine_map = _engine_map_from_command(command, tune.engine_map)
    if engine_map not in ENGINE_MAP_POWER:
        valid = ", ".join(sorted(ENGINE_MAP_POWER))
        raise ValueError(f"Invalid engine_map: {engine_map!r}. Valid values: {valid}")

    overall_factor = _condition_factor(modified.condition.overall_condition)
    engine_factor = _condition_factor(modified.condition.engine_condition)
    brake_factor = _condition_factor(modified.condition.brake_condition)
    tire_factor = _condition_factor((modified.condition.tire_condition + modified.condition.overall_condition) / 2)
    suspension_factor = _condition_factor(modified.condition.suspension_condition)

    power = modified.powertrain.power_hp * engine_factor * ENGINE_MAP_POWER[engine_map]
    torque = modified.powertrain.torque_nm * engine_factor * ENGINE_MAP_POWER[engine_map]
    weight = max(modified.chassis.weight_kg, 1)
    drag = modified.aero.drag + (tune.front_downforce + tune.rear_downforce) * DOWNFORCE_DRAG_PENALTY

    final_drive_delta = (tune.final_drive - FINAL_DRIVE_IDEAL) / FINAL_DRIVE_IDEAL
    acceleration = (power / weight / NORM_ACCEL_REF_HW) * PERCENT_MAX
    acceleration *= 1 + final_drive_delta * FINAL_DRIVE_ACCEL_FACTOR
    top_speed_kmh = TOP_SPEED_COEFF * (power / (drag / PERCENT_MAX + 0.5)) ** 0.333
    top_speed = top_speed_kmh / NORM_SPEED_REF_KMH * PERCENT_MAX
    top_speed *= 1 - final_drive_delta * FINAL_DRIVE_SPEED_FACTOR

    brake_bias_factor = 1 - abs(tune.brake_bias - BRAKE_BIAS_IDEAL) * BRAKE_BIAS_PENALTY
    braking = modified.brakes.braking_power * brake_factor * brake_bias_factor * tune.brake_pressure
    brake_stability = modified.brakes.brake_stability * brake_factor * brake_bias_factor

    camber_factor = _camber_factor(tune.camber_front, tune.camber_rear)
    pressure_factor = _pressure_factor(tune.tire_pressure_front, tune.tire_pressure_rear)
    grip = modified.tires.base_grip * tire_factor * camber_factor * pressure_factor
    wet_grip = modified.tires.wet_grip * tire_factor * pressure_factor

    weight_factor = min(1.15, WEIGHT_REFERENCE_KG / weight)
    ride_factor = _ride_height_factor(tune.front_ride_height, tune.rear_ride_height)
    handling = modified.suspension.handling * suspension_factor * overall_factor * weight_factor * ride_factor
    mechanical_grip = modified.suspension.mechanical_grip * suspension_factor * tire_factor
    aero_grip = (modified.aero.downforce + tune.front_downforce + tune.rear_downforce) / NORM_AERO_MAX * PERCENT_MAX

    cooling_factor = max(0.35, 1 - modified.powertrain.cooling * COOLING_HEAT_REDUCTION)
    engine_heat_rate = modified.powertrain.engine_stress * ENGINE_MAP_HEAT[engine_map] * cooling_factor
    fuel_burn_rate = modified.fuel.base_fuel_burn * ENGINE_MAP_FUEL[engine_map] * max(0.50, power / NORM_POWER_REF_HP)
    tire_wear_rate = max(0.20, (PERCENT_MAX - modified.tires.tire_wear_resistance) / PERCENT_MAX)
    tire_heat_rate = max(0.20, (PERCENT_MAX - modified.tires.tire_heat_resistance) / PERCENT_MAX)
    reliability = modified.durability.overall_reliability * overall_factor
    reliability *= max(0.30, 1 - modified.powertrain.engine_stress * STRESS_RELIABILITY_PENALTY)

    return EffectiveCarStats(
        power=clamp(power / NORM_POWER_REF_HP * PERCENT_MAX),
        torque=clamp(torque / NORM_TORQUE_REF_NM * PERCENT_MAX),
        weight=float(weight),
        acceleration=clamp(acceleration),
        top_speed=clamp(top_speed),
        braking=clamp(braking),
        brake_stability=clamp(brake_stability),
        grip=clamp(grip),
        wet_grip=clamp(wet_grip),
        handling=clamp(handling),
        mechanical_grip=clamp(mechanical_grip),
        aero_grip=clamp(aero_grip),
        drag=max(0.0, drag),
        stability=clamp(modified.chassis.stability * overall_factor + modified.aero.high_speed_stability * 0.20),
        tire_wear_rate=tire_wear_rate,
        tire_heat_rate=tire_heat_rate,
        fuel_burn_rate=fuel_burn_rate,
        engine_heat_rate=engine_heat_rate,
        reliability=clamp(reliability),
        suspension_compliance=clamp(modified.suspension.suspension_compliance * suspension_factor),
        curb_handling=clamp(modified.suspension.curb_handling * suspension_factor),
    )


def class_rating(car: Car, parts: list[Part] | None = None) -> int:
    effective = compute_effective_stats(car, parts)
    condition_score = (
        car.condition.overall_condition
        + car.condition.engine_condition
        + car.condition.brake_condition
        + car.condition.suspension_condition
        + car.condition.tire_condition
    ) / 5
    composite = (
        effective.acceleration * CLASS_RATING_WEIGHTS["acceleration"]
        + effective.top_speed * CLASS_RATING_WEIGHTS["top_speed"]
        + effective.grip * CLASS_RATING_WEIGHTS["grip"]
        + effective.braking * CLASS_RATING_WEIGHTS["braking"]
        + effective.handling * CLASS_RATING_WEIGHTS["handling"]
        + effective.aero_grip * CLASS_RATING_WEIGHTS["aero"]
        + effective.reliability * CLASS_RATING_WEIGHTS["reliability"]
        + condition_score * CLASS_RATING_WEIGHTS["condition"]
    )
    return round(composite * CLASS_RATING_SCALE)


def rating_class(rating: int) -> str:
    current = "E"
    for class_name, threshold in CLASS_THRESHOLDS.items():
        if rating >= threshold:
            current = class_name
    return current


def _condition_factor(value: float) -> float:
    return max(MIN_CONDITION_FACTOR, value / PERCENT_MAX)


def _camber_factor(front: float, rear: float) -> float:
    average = (abs(front) + abs(rear)) / 2
    return max(0.85, 1 - abs(average - CAMBER_IDEAL_DEG) * CAMBER_PENALTY)


def _pressure_factor(front: float, rear: float) -> float:
    average = (front + rear) / 2
    return max(0.85, 1 - abs(average - PRESSURE_IDEAL_BAR) * PRESSURE_PENALTY)


def _ride_height_factor(front: int, rear: int) -> float:
    average = (front + rear) / 2
    return max(0.85, 1 - abs(average - RIDE_HEIGHT_IDEAL_MM) * RIDE_HEIGHT_PENALTY)


def _engine_map_from_command(command: str, default_map: str) -> str:
    if command == "hot_map":
        return "hot"
    if command in {"safe_map", "conserve"}:
        return "safe"
    if command == "fuel_save":
        return "fuel_save"
    return default_map
