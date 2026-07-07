from __future__ import annotations

import math
from copy import deepcopy

import constants as C
from constants import (
    BRAKE_BIAS_IDEAL,
    BRAKE_BIAS_PENALTY,
    CAMBER_IDEAL_DEG,
    CAMBER_PENALTY,
    CLASS_RATING_SCALE,
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
    ORPHAN_FACTOR_CEIL,
    ORPHAN_FACTOR_FLOOR,
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
from game.models import Car, EffectiveCarStats, Part
from game.parts import normalize_part_ids


def clamp(value: float, low: float = PERCENT_MIN, high: float = PERCENT_MAX) -> float:
    return max(low, min(high, value))


def _pace(value: float) -> float:
    """Soft-knee transform for a performance axis that feeds the pace composite.

    Identity at/below the knee (ordinary cars and the reference car are unchanged), then
    a logarithmic compression above it: more performance always helps with diminishing
    returns and there is no ceiling, so future upgrade parts never wall out. Lower bound
    stays at zero.
    """
    value = max(0.0, value)
    if value <= C.PACE_SOFT_KNEE:
        return value
    return C.PACE_SOFT_KNEE + C.PACE_SOFT_SOFTNESS * math.log1p((value - C.PACE_SOFT_KNEE) / C.PACE_SOFT_SOFTNESS)


def _centered_factor(value: float, reference: float, per_unit: float) -> float:
    """A multiplier that is 1.0 at ``reference`` and scales ``per_unit`` per point of
    deviation. Used to fold a stat into an effective axis without shifting the catalog
    baseline (a reference-valued car is unaffected)."""
    return 1.0 + (value - reference) * per_unit


def _combine_factor(*factors: float) -> float:
    """Multiply per-stat factors and clamp the product to the orphan swing band, so a
    single axis stacking several folded stats still moves only a few percent."""
    product = 1.0
    for factor in factors:
        product *= factor
    return max(ORPHAN_FACTOR_FLOOR, min(ORPHAN_FACTOR_CEIL, product))


def apply_part_modifiers(car: Car, parts: list[Part] | None = None) -> Car:
    modified = deepcopy(car)
    part_map = {part.id: part for part in (parts if parts is not None else load_parts())}
    for part_id in normalize_part_ids(modified.installed_parts):
        part = part_map[part_id]
        for path, delta in part.modifiers.items():
            _apply_delta(modified, path, delta)
        for path, value in part.overrides.items():
            _apply_override(modified, path, value)
    return modified


def _apply_delta(car: Car, path: str, delta: int | float) -> None:
    target_name, attr_name = path.split(".", maxsplit=1)
    target = getattr(car, target_name)
    setattr(target, attr_name, getattr(target, attr_name) + delta)


def _apply_override(car: Car, path: str, value: int | float | str) -> None:
    target_name, attr_name = path.split(".", maxsplit=1)
    target = getattr(car, target_name)
    setattr(target, attr_name, value)


def compute_effective_stats(car: Car, parts: list[Part] | None = None) -> EffectiveCarStats:
    modified = apply_part_modifiers(car, parts)
    tune = modified.tune
    # Engine map is a setup choice (tuning menu), not a mid-race command.
    engine_map = tune.engine_map
    if engine_map not in ENGINE_MAP_POWER:
        valid = ", ".join(sorted(ENGINE_MAP_POWER))
        raise ValueError(f"Invalid engine_map: {engine_map!r}. Valid values: {valid}")

    overall_factor = _condition_factor(modified.condition.overall_condition)
    engine_factor = _condition_factor(modified.condition.engine_condition)
    brake_factor = _condition_factor(modified.condition.brake_condition)
    tire_factor = _condition_factor((modified.condition.tire_condition + modified.condition.overall_condition) / 2)
    suspension_factor = _condition_factor(modified.condition.suspension_condition)

    pt = modified.powertrain
    ch = modified.chassis
    ti = modified.tires
    br = modified.brakes
    su = modified.suspension
    ae = modified.aero
    du = modified.durability
    fu = modified.fuel
    cond = modified.condition

    power = pt.power_hp * engine_factor * ENGINE_MAP_POWER[engine_map]
    torque = pt.torque_nm * engine_factor * ENGINE_MAP_POWER[engine_map]
    weight = max(ch.weight_kg, 1)

    # Aero efficiency trims effective drag; a damaged body adds a little drag.
    drag = ae.drag + (tune.front_downforce + tune.rear_downforce) * DOWNFORCE_DRAG_PENALTY
    drag *= _centered_factor(ae.aero_efficiency, C.AERO_EFFICIENCY_REF, -C.AERO_EFFICIENCY_DRAG_PER_UNIT)
    drag *= _centered_factor(cond.body_condition, C.BODY_CONDITION_REF, -C.BODY_CONDITION_DRAG_PER_UNIT)
    drag = max(0.0, drag)

    # Engine character (torque delivery, powerband, throttle) shapes acceleration.
    torque_ratio = pt.torque_nm / max(pt.power_hp, 1)
    accel_character = _combine_factor(
        _centered_factor(torque_ratio, C.TORQUE_RATIO_REF, C.TORQUE_RATIO_ACCEL_FACTOR),
        _centered_factor(pt.powerband, C.POWERBAND_REF, C.POWERBAND_ACCEL_PER_UNIT),
        _centered_factor(pt.throttle_response, C.THROTTLE_RESPONSE_REF, C.THROTTLE_ACCEL_PER_UNIT),
    )
    final_drive_delta = (tune.final_drive - FINAL_DRIVE_IDEAL) / FINAL_DRIVE_IDEAL
    acceleration = (power / weight / NORM_ACCEL_REF_HW) * PERCENT_MAX
    acceleration *= 1 + final_drive_delta * FINAL_DRIVE_ACCEL_FACTOR
    acceleration *= accel_character
    top_speed_kmh = TOP_SPEED_COEFF * (power / (drag / PERCENT_MAX + 0.5)) ** 0.333
    top_speed = top_speed_kmh / NORM_SPEED_REF_KMH * PERCENT_MAX
    top_speed *= 1 - final_drive_delta * FINAL_DRIVE_SPEED_FACTOR

    brake_bias_factor = 1 - abs(tune.brake_bias - BRAKE_BIAS_IDEAL) * BRAKE_BIAS_PENALTY
    braking = br.braking_power * brake_factor * brake_bias_factor * tune.brake_pressure
    brake_stability = br.brake_stability * brake_factor * brake_bias_factor
    # Cooling and fade resistance keep brakes effective; brake_stability now contributes.
    braking *= _combine_factor(
        _centered_factor(br.brake_cooling, C.BRAKE_COOLING_REF, C.BRAKE_COOLING_PER_UNIT),
        _centered_factor(br.brake_fade_resistance, C.BRAKE_FADE_REF, C.BRAKE_FADE_PER_UNIT),
    )
    braking = braking * (1 - C.BRAKE_STABILITY_BLEND) + brake_stability * C.BRAKE_STABILITY_BLEND

    # Setup quantities used across the grip/handling axes (Phase-2 tune knobs).
    avg_stiffness = (tune.suspension_stiffness_front + tune.suspension_stiffness_rear) / 2
    avg_antiroll = (tune.antiroll_front + tune.antiroll_rear) / 2
    total_toe = abs(tune.toe_front) + abs(tune.toe_rear)

    camber_factor = _camber_factor(tune.camber_front, tune.camber_rear)
    pressure_factor = _pressure_factor(tune.tire_pressure_front, tune.tire_pressure_rear)
    grip = ti.base_grip * tire_factor * camber_factor * pressure_factor
    wet_grip = ti.wet_grip * tire_factor * pressure_factor
    mechanical_grip = su.mechanical_grip * suspension_factor * tire_factor
    # One clamped orphan factor per axis: contact patch (tyre width) plus setup
    # (stiffness/preload/toe) shape grip; mechanical grip from the suspension blends in.
    grip *= _combine_factor(
        _centered_factor(ti.tire_width_front, C.TIRE_WIDTH_FRONT_REF, C.TIRE_WIDTH_GRIP_PER_MM),
        _centered_factor(ti.tire_width_rear, C.TIRE_WIDTH_REAR_REF, C.TIRE_WIDTH_GRIP_PER_MM),
        1 - abs(avg_stiffness - C.SUSP_STIFFNESS_IDEAL) * C.SUSP_STIFFNESS_GRIP_PENALTY_PER_UNIT,
        1 - abs(tune.differential_preload - C.DIFF_PRELOAD_IDEAL) * C.DIFF_PRELOAD_GRIP_PENALTY_PER_UNIT,
        1 - total_toe * C.TOE_GRIP_PENALTY,
    )
    grip = grip * (1 - C.MECH_GRIP_BLEND) + mechanical_grip * C.MECH_GRIP_BLEND
    drivetrain = modified.identity.drivetrain
    if drivetrain == "AWD":
        # AWD puts power down better; the surface-scaled half lives in the segment composite.
        grip *= C.AWD_GRIP_BONUS

    weight_factor = min(1.15, WEIGHT_REFERENCE_KG / weight)
    ride_factor = _ride_height_factor(tune.front_ride_height, tune.rear_ride_height)
    suspension_compliance = clamp(su.suspension_compliance * suspension_factor)
    curb_handling = clamp(su.curb_handling * suspension_factor)
    handling = su.handling * suspension_factor * overall_factor * weight_factor * ride_factor
    # Chassis (rigidity, CoG, rotation, weight balance), suspension feel (bump absorption,
    # steering precision, compliance, curb behaviour) and setup (stiffness, anti-roll,
    # coast diff, front toe) all shape handling, bounded by a single orphan clamp.
    handling *= _combine_factor(
        _centered_factor(ch.chassis_rigidity, C.RIGIDITY_REF, C.RIGIDITY_HANDLING_PER_UNIT),
        _centered_factor(ch.center_of_gravity, C.CENTER_OF_GRAVITY_REF, C.COG_HANDLING_PER_UNIT),
        _centered_factor(ch.rotation, C.ROTATION_REF, C.ROTATION_HANDLING_PER_UNIT),
        1 - abs(ch.weight_distribution_front - C.WEIGHT_DIST_IDEAL) * C.WEIGHT_DIST_HANDLING_PENALTY,
        _centered_factor(su.bump_absorption, C.BUMP_ABSORPTION_REF, C.BUMP_HANDLING_PER_UNIT),
        _centered_factor(su.steering_precision, C.STEERING_PRECISION_REF, C.STEERING_HANDLING_PER_UNIT),
        _centered_factor(suspension_compliance, C.COMPLIANCE_REF, C.COMPLIANCE_HANDLING_PER_UNIT),
        _centered_factor(curb_handling, C.CURB_HANDLING_REF, C.CURB_HANDLING_PER_UNIT),
        _centered_factor(avg_stiffness, C.SUSP_STIFFNESS_IDEAL, C.SUSP_STIFFNESS_HANDLING_PER_UNIT),
        _centered_factor(avg_antiroll, C.ANTIROLL_IDEAL, C.ANTIROLL_HANDLING_PER_UNIT),
        _centered_factor(tune.differential_coast, C.DIFF_COAST_IDEAL, C.DIFF_COAST_HANDLING_PER_UNIT),
        1 + abs(tune.toe_front) * C.TOE_RESPONSE_FACTOR,
    )
    aero_grip = (ae.downforce + tune.front_downforce + tune.rear_downforce) / NORM_AERO_MAX * PERCENT_MAX

    # Gear bias and power-diff shape accel/top-speed (neutral at default setup).
    acceleration *= 1 + tune.gear_bias * C.GEAR_BIAS_ACCEL_FACTOR
    top_speed *= 1 - tune.gear_bias * C.GEAR_BIAS_SPEED_FACTOR
    acceleration *= _centered_factor(tune.differential_power, C.DIFF_POWER_IDEAL, C.DIFF_POWER_ACCEL_PER_UNIT)

    stability = clamp(ch.stability * overall_factor + ae.high_speed_stability * 0.20)
    # High-speed stability gives a small confidence margin at the top end.
    top_speed = top_speed * (1 - C.STABILITY_TOPSPEED_BLEND) + stability * C.STABILITY_TOPSPEED_BLEND

    cooling_factor = max(0.35, 1 - pt.cooling * COOLING_HEAT_REDUCTION)
    engine_heat_rate = pt.engine_stress * ENGINE_MAP_HEAT[engine_map] * cooling_factor
    fuel_burn_rate = modified.fuel.base_fuel_burn * ENGINE_MAP_FUEL[engine_map] * max(0.50, power / NORM_POWER_REF_HP)
    # Efficiency (the fuel system) trims burn; a bigger tank drains a smaller % per lap, so
    # capacity becomes a real strategic lever (bounded to avoid extremes).
    fuel_burn_rate *= _centered_factor(fu.fuel_efficiency, C.FUEL_EFFICIENCY_REF, -C.FUEL_EFFICIENCY_BURN_PER_UNIT)
    # Tank capacity no longer fudges the burn *rate*; it sets real range at race time
    # (litres burned / capacity). A bigger tank = more laps between stops, not less burn.
    tire_wear_rate = max(0.20, (PERCENT_MAX - ti.tire_wear_resistance) / PERCENT_MAX)
    tire_heat_rate = max(0.20, (PERCENT_MAX - ti.tire_heat_resistance) / PERCENT_MAX)
    # Wider tyres run a touch hotter and wear faster; quicker-warming tyres heat sooner.
    width_load = _combine_factor(
        _centered_factor(ti.tire_width_front, C.TIRE_WIDTH_FRONT_REF, C.TIRE_WIDTH_WEAR_PER_MM),
        _centered_factor(ti.tire_width_rear, C.TIRE_WIDTH_REAR_REF, C.TIRE_WIDTH_WEAR_PER_MM),
    )
    tire_wear_rate *= width_load
    tire_heat_rate *= width_load * _centered_factor(ti.tire_warmup, C.TIRE_WARMUP_REF, C.TIRE_WARMUP_HEAT_PER_UNIT)
    reliability = du.overall_reliability * overall_factor
    reliability *= max(0.30, 1 - pt.engine_stress * STRESS_RELIABILITY_PENALTY)
    # Secondary durability (engine/gearbox/suspension/brake/cooling), the car's
    # mechanical-sympathy modifier, and gearbox condition now shape failure risk.
    secondary_durability = (
        du.engine_reliability + pt.engine_reliability + du.gearbox_reliability
        + du.suspension_durability + du.brake_durability + du.cooling_capacity
    ) / 6
    reliability *= _combine_factor(
        _centered_factor(secondary_durability, C.DURABILITY_REF, C.DURABILITY_RELIABILITY_PER_UNIT),
        1 + du.mechanical_sympathy_modifier * C.MECH_SYMPATHY_MOD_PER_UNIT,
        _centered_factor(cond.gearbox_condition, C.GEARBOX_CONDITION_REF, C.CONDITION_RELIABILITY_PER_UNIT),
    )

    # Performance axes that feed the pace composite use the no-ceiling soft knee; the rest
    # (rates/reliability and secondary readouts) keep the genuine 0-100 clamp.
    return EffectiveCarStats(
        power=_pace(power / NORM_POWER_REF_HP * PERCENT_MAX),
        torque=clamp(torque / NORM_TORQUE_REF_NM * PERCENT_MAX),
        weight=float(weight),
        acceleration=_pace(acceleration),
        top_speed=_pace(top_speed),
        braking=_pace(braking),
        brake_stability=clamp(brake_stability),
        grip=_pace(grip),
        wet_grip=_pace(wet_grip),
        handling=_pace(handling),
        mechanical_grip=clamp(mechanical_grip),
        # aero stays clamped: it isn't a supercar differentiator and its huge pre-clamp
        # values (downforce can reach ~2x) would otherwise over-inflate the aero-heavy car.
        aero_grip=clamp(aero_grip),
        drag=drag,
        stability=stability,
        tire_wear_rate=tire_wear_rate,
        tire_heat_rate=tire_heat_rate,
        fuel_burn_rate=fuel_burn_rate,
        engine_heat_rate=engine_heat_rate,
        reliability=clamp(reliability),
        suspension_compliance=suspension_compliance,
        curb_handling=curb_handling,
        drivetrain=drivetrain,
        fuel_capacity_l=float(fu.fuel_capacity_l),
        power_to_weight=power / weight,  # real hp/kg (post-parts, post-map): drives climb pace
    )


def derived_rating(car: Car, parts: list[Part] | None = None) -> int:
    """Performance rating derived from the car alone: its mean capability across the fixed
    drag/slalom/hybrid reference suite, scaled. Computed at runtime (never stored), so it
    generalises to any custom car and never goes stale. See game/reference_suite.py."""
    from game.reference_suite import mean_capability  # lazy: reference_suite -> simulation -> here

    effective = compute_effective_stats(car, parts)
    return round(mean_capability(effective) * CLASS_RATING_SCALE)


def class_rating(car: Car, parts: list[Part] | None = None) -> int:
    return derived_rating(car, parts)


def derived_class(car: Car, parts: list[Part] | None = None) -> str:
    """The car's class letter (E..S), bracketed from its derived rating. Single source of
    truth for eligibility and display -- there is no stored class."""
    return rating_class(derived_rating(car, parts))


def class_breakdown(car: Car, parts: list[Part] | None = None) -> dict:
    """Display-ready view of how the class is derived: the car's capability on each
    reference fixture, the mean, and the resulting PR / class / shape. Lets the UI explain
    a class that is computed rather than stored."""
    from game.reference_suite import archetype_capabilities  # lazy: avoid import cycle

    effective = compute_effective_stats(car, parts)
    caps = archetype_capabilities(effective)
    mean = sum(caps.values()) / len(caps)
    pr = round(mean * CLASS_RATING_SCALE)
    return {
        "drag": round(caps["power"]),
        "slalom": round(caps["technical"]),
        "hybrid": round(caps["hybrid"]),
        "mean": round(mean, 1),
        "pr": pr,
        "class": rating_class(pr),
        "shape": performance_type(car, parts),
    }


def performance_type(car: Car, parts: list[Part] | None = None) -> str:
    """The car's "shape": where its pace comes from, comparing speed axes against control
    axes. Distinguishes same-tier cars (a power specialist vs a balanced car vs a handler)."""
    from game.reference_suite import mean_capability  # lazy: avoid import cycle

    effective = compute_effective_stats(car, parts)
    if set(car.identity.tags).intersection({"challenge", "joke"}) or mean_capability(effective) < C.SHAPE_CHALLENGE_FLOOR:
        return "Challenge"
    speed = (effective.power + effective.acceleration + effective.top_speed) / 3
    control = (effective.grip + effective.braking + effective.handling) / 3
    if speed - control >= C.SHAPE_SPEED_CONTROL_DELTA:
        return "Power"
    if control - speed >= C.SHAPE_SPEED_CONTROL_DELTA:
        return "Handling"
    return "Balanced"


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
