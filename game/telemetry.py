from __future__ import annotations

from constants import (
    BASE_FAILURE_RATE,
    BASE_MISTAKE_RATE,
    COMMAND_MISTAKE_INDEX,
    COMMAND_MODIFIERS,
    ENGINE_CRITICAL_C,
    ENGINE_OVERHEAT_C,
    FAILURE_CONDITION_SCALE,
    FAILURE_ENGINE_TEMP_SCALE,
    FAILURE_RELIABILITY_SCALE,
    FAILURE_SYMPATHY_SCALE,
    HIGH_FEEDBACK_THRESHOLD,
    LOW_FEEDBACK_THRESHOLD,
    MISTAKE_AGGRESSION_SCALE,
    MISTAKE_CONSISTENCY_SCALE,
    MISTAKE_FOCUS_SCALE,
    MISTAKE_STRESS_SCALE,
    MISTAKE_TIRE_TEMP_SCALE,
    MISTAKE_TIRE_WEAR_SCALE,
    PERCENT_LOW_FUEL_WARNING,
    PERCENT_MAX,
    PERCENT_WORN_TIRE_WARNING,
    TIRE_CRITICAL_C,
    TIRE_OVERHEAT_C,
)
from game.models import Driver, EffectiveCarStats, RaceCarState, TelemetryHistory


def record_telemetry(history: TelemetryHistory, state: RaceCarState) -> None:
    history.lap_times.append(state.last_lap_time or 0.0)
    history.positions.append(state.position)
    history.engine_temps.append(state.engine_temp)
    history.fuel_pct.append(state.fuel_pct)
    history.tire_wear.append(state.tire_pct)
    history.tire_temps.append(state.tire_temp)
    history.driver_energy.append(state.driver_energy)
    history.driver_focus.append(state.driver_focus)
    history.driver_stress.append(state.driver_stress)


def warning_messages(state: RaceCarState) -> list[str]:
    messages: list[str] = []
    if state.tire_temp >= TIRE_OVERHEAT_C:
        messages.append("Tire temperature warning.")
    if state.tire_pct <= PERCENT_WORN_TIRE_WARNING:
        messages.append("Tires are badly worn.")
    if state.fuel_pct <= PERCENT_LOW_FUEL_WARNING:
        messages.append("Fuel is below 20%.")
    if state.engine_temp >= ENGINE_OVERHEAT_C:
        messages.append("Engine temperature warning.")
    return messages


def mistake_chance(state: RaceCarState, driver: Driver, command: str = "normal") -> float:
    command_risk = COMMAND_MODIFIERS[command][COMMAND_MISTAKE_INDEX]
    tire_wear_risk = max(0.0, (PERCENT_MAX - state.tire_pct) / PERCENT_MAX) * MISTAKE_TIRE_WEAR_SCALE
    tire_temp_risk = _scaled_above(state.tire_temp, TIRE_OVERHEAT_C, TIRE_CRITICAL_C) * MISTAKE_TIRE_TEMP_SCALE
    stress_risk = state.driver_stress / PERCENT_MAX * MISTAKE_STRESS_SCALE
    aggression_risk = driver.aggression * MISTAKE_AGGRESSION_SCALE
    consistency_reduction = driver.consistency * MISTAKE_CONSISTENCY_SCALE
    focus_reduction = state.driver_focus * MISTAKE_FOCUS_SCALE
    return _probability(
        BASE_MISTAKE_RATE * command_risk
        + aggression_risk
        + tire_wear_risk
        + tire_temp_risk
        + stress_risk
        - consistency_reduction
        - focus_reduction
    )


def failure_chance(state: RaceCarState, effective: EffectiveCarStats, driver: Driver, command: str = "normal") -> float:
    command_risk = COMMAND_MODIFIERS[command][COMMAND_MISTAKE_INDEX]
    reliability_penalty = (PERCENT_MAX - effective.reliability) * FAILURE_RELIABILITY_SCALE
    condition_penalty = (PERCENT_MAX - state.condition_pct) * FAILURE_CONDITION_SCALE
    temp_penalty = _scaled_above(state.engine_temp, ENGINE_OVERHEAT_C, ENGINE_CRITICAL_C) * FAILURE_ENGINE_TEMP_SCALE
    sympathy_reduction = driver.mechanical_sympathy * FAILURE_SYMPATHY_SCALE
    return _probability(BASE_FAILURE_RATE * command_risk + reliability_penalty + condition_penalty + temp_penalty - sympathy_reduction)


def generate_driver_feedback(driver: Driver, history: TelemetryHistory) -> str:
    if driver.feedback < LOW_FEEDBACK_THRESHOLD:
        return "Car feels loose in some corners."
    latest_tire_temp = history.tire_temps[-1] if history.tire_temps else 0.0
    latest_engine_temp = history.engine_temps[-1] if history.engine_temps else 0.0
    latest_fuel = history.fuel_pct[-1] if history.fuel_pct else PERCENT_MAX
    if driver.feedback >= HIGH_FEEDBACK_THRESHOLD:
        if latest_tire_temp >= TIRE_OVERHEAT_C:
            return f"Tire temp reached {latest_tire_temp:.0f}C. Try calmer pace, less front camber, or more stable pressure."
        if latest_engine_temp >= ENGINE_OVERHEAT_C:
            return f"Engine temp reached {latest_engine_temp:.0f}C. Use a safer engine map or improve cooling."
        if latest_fuel <= PERCENT_LOW_FUEL_WARNING:
            return f"Fuel dropped to {latest_fuel:.0f}%. Fuel save would protect the final laps."
        return "Telemetry is stable. Biggest gains are likely setup-specific rather than survival-related."
    if latest_tire_temp >= TIRE_OVERHEAT_C:
        return "Tires are running hot. Back off or tune for cooler tire behavior."
    if latest_engine_temp >= ENGINE_OVERHEAT_C:
        return "Engine is getting hot. A safer map should help."
    return "Balance feels workable, but there is time in the setup."


def _scaled_above(value: float, start: float, end: float) -> float:
    if value <= start:
        return 0.0
    if end <= start:
        return 1.0
    return max(0.0, min(1.0, (value - start) / (end - start)))


def _probability(value: float) -> float:
    return max(0.0, min(0.95, value))
