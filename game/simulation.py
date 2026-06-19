from __future__ import annotations

import random
from copy import deepcopy
from typing import TypeVar

from constants import (
    COMMAND_MODIFIERS,
    COMMAND_ENGINE_HEAT_INDEX,
    COMMAND_FUEL_BURN_INDEX,
    COMMAND_TIRE_WEAR_INDEX,
    COOLING_COMMANDS,
    DRIVER_PACE_SCALE,
    DRIVER_ENERGY_DRAIN_BASE,
    DRIVER_FOCUS_DRAIN_BASE,
    DRIVER_STRESS_BUILD_BASE,
    ENGINE_CRITICAL_C,
    ENGINE_COOL_BASE_C,
    ENGINE_HEAT_BASE_C,
    ENGINE_OVERHEAT_C,
    ENGINE_TEMP_PENALTY_MAX,
    FUEL_BURN_BASE_PCT,
    MILEAGE_KM_MULTIPLIER,
    PIT_ENGINE_COOL_C,
    PIT_FUEL_RESTORE_PCT,
    PIT_TIRE_RESTORE_PCT,
    PIT_TIRE_TEMP_C,
    PERCENT_MAX,
    PERF_SCALE,
    RANDOM_VARIANCE_SCALE,
    TIRE_CRITICAL_C,
    TIRE_COOL_BASE_C,
    TIRE_HEAT_BASE_C,
    TIRE_OVERHEAT_C,
    TIRE_TEMP_PENALTY_MAX,
    TIRE_WEAR_BASE_PCT,
    TIRE_WEAR_PENALTY_MAX,
    WEAR_PER_RACE_BASE,
)
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks
from game.models import Car, Driver, EffectiveCarStats, Event, RaceCarState, RaceResult, Track
from game.opponents import build_opponent_grid, validate_event_entry

T = TypeVar("T")


class SimulationError(ValueError):
    """Raised when a race cannot be simulated from the supplied state."""


def calculate_lap_time(
    effective: EffectiveCarStats,
    track: Track,
    driver: Driver | None = None,
    state: RaceCarState | None = None,
    rng: random.Random | None = None,
    command: str = "normal",
    performance_scalar: float = 1.0,
) -> float:
    pace_factor = COMMAND_MODIFIERS[command][0]
    car_performance_bonus = PERF_SCALE * _track_composite(effective, track) * pace_factor * performance_scalar
    driver_pace_bonus = driver.pace * DRIVER_PACE_SCALE if driver is not None else 0.0
    tire_wear_penalty = 0.0
    tire_temp_penalty = 0.0
    engine_temp_penalty = 0.0

    if state is not None:
        tire_wear_penalty = (PERCENT_MAX - state.tire_pct) / PERCENT_MAX * TIRE_WEAR_PENALTY_MAX
        if state.tire_temp > TIRE_OVERHEAT_C:
            tire_temp_penalty = _range_penalty(state.tire_temp, TIRE_OVERHEAT_C, TIRE_CRITICAL_C, TIRE_TEMP_PENALTY_MAX)
        if state.engine_temp > ENGINE_OVERHEAT_C:
            engine_temp_penalty = _range_penalty(
                state.engine_temp,
                ENGINE_OVERHEAT_C,
                ENGINE_CRITICAL_C,
                ENGINE_TEMP_PENALTY_MAX,
            )

    random_variance = 0.0
    if rng is not None:
        consistency = driver.consistency if driver is not None else PERCENT_MAX / 2
        variance = RANDOM_VARIANCE_SCALE * (1 - consistency / PERCENT_MAX)
        random_variance = rng.uniform(-variance, variance)

    return (
        track.base_lap_time
        - car_performance_bonus
        - driver_pace_bonus
        + tire_wear_penalty
        + tire_temp_penalty
        + engine_temp_penalty
        + random_variance
    )


def simulate_race(game_state: GameState, event_id: str, car_id: str, driver_id: str, seed: int = 1) -> RaceResult:
    rng = random.Random(seed)
    parts = load_parts()
    cars = {car.identity.id: car for car in load_cars()}
    drivers = {driver.id: driver for driver in load_drivers()}
    events = {event.id: event for event in load_events()}
    tracks = {track.id: track for track in load_tracks()}

    event = _get(events, event_id, "event")
    track = _get(tracks, event.track_id, "track")
    player_car = _find_garage_car(game_state, car_id) or deepcopy(_get(cars, car_id, "car"))
    player_driver = _get(drivers, driver_id, "driver")
    validate_event_entry(player_car, event, parts)

    race_cars = [_initial_state(player_car.identity.id, player_driver.id, "YOU", True)]
    opponent_cars, opponent_drivers, opponent_entries = build_opponent_grid(
        event, player_car.identity.id, player_driver, cars, parts, track, seed
    )
    cars.update(opponent_cars)
    drivers.update(opponent_drivers)
    for index, (opponent_car_id, opponent_driver_id, scalar) in enumerate(opponent_entries, start=1):
        opponent_state = _initial_state(opponent_car_id, opponent_driver_id, f"Rival {index}", False)
        opponent_state.performance_scalar = scalar
        race_cars.append(opponent_state)

    lap_times: dict[str, list[float]] = {state.label: [] for state in race_cars}
    race_log: list[str] = []
    for _lap in range(track.laps):
        for state in race_cars:
            car = player_car if state.is_player else cars[state.car_id]
            driver = player_driver if state.is_player else drivers[state.driver_id]
            effective = compute_effective_stats(car, parts)
            lap_time = calculate_lap_time(effective, track, driver, state, rng, performance_scalar=state.performance_scalar)
            state.last_lap_time = lap_time
            state.total_time += lap_time
            state.lap += 1
            state.distance += track.length_km
            _apply_lap_wear(state, effective, track)
            lap_times[state.label].append(lap_time)

        _rank(race_cars)
        race_log.append(f"Lap {race_cars[0].lap}: leader {race_cars[0].label}")

    _rank(race_cars)
    player_state = next(state for state in race_cars if state.is_player)
    prize_money = _prize_for_position(event, player_state.position)
    game_state.money += prize_money
    garage_car = _find_garage_car(game_state, car_id)
    if garage_car is not None:
        garage_car.condition.mileage += round(track.length_km * track.laps * MILEAGE_KM_MULTIPLIER)
        garage_car.condition.overall_condition = max(0.0, garage_car.condition.overall_condition - WEAR_PER_RACE_BASE)

    return RaceResult(
        event_id=event.id,
        track_id=track.id,
        total_laps=track.laps,
        standings=race_cars,
        player_position=player_state.position,
        prize_money=prize_money,
        lap_times=lap_times,
        race_log=race_log,
    )


def _track_composite(effective: EffectiveCarStats, track: Track) -> float:
    return (
        effective.acceleration * track.acceleration_weight
        + effective.power * track.power_weight
        + effective.top_speed * track.top_speed_weight
        + effective.grip * track.grip_weight
        + effective.braking * track.braking_weight
        + effective.handling * track.handling_weight
        + effective.aero_grip * track.aero_weight
    )


def _range_penalty(value: float, start: float, end: float, maximum: float) -> float:
    if end <= start:
        return maximum
    return max(0.0, min(1.0, (value - start) / (end - start))) * maximum


def _apply_lap_wear(
    state: RaceCarState,
    effective: EffectiveCarStats,
    track: Track,
    command: str = "normal",
    fraction: float = 1.0,
) -> None:
    modifiers = COMMAND_MODIFIERS[command]
    if command == "pit" and fraction >= 1.0:
        state.tire_pct = PIT_TIRE_RESTORE_PCT
        state.tire_temp = PIT_TIRE_TEMP_C
        state.fuel_pct = PIT_FUEL_RESTORE_PCT
        state.engine_temp = max(0.0, state.engine_temp - PIT_ENGINE_COOL_C)
        return
    state.tire_pct = max(
        0.0,
        state.tire_pct - TIRE_WEAR_BASE_PCT * track.tire_wear_rate * effective.tire_wear_rate * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction,
    )
    heat_gain = TIRE_HEAT_BASE_C * track.tire_wear_rate * effective.tire_heat_rate * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction
    tire_cooling = TIRE_COOL_BASE_C * fraction if command in COOLING_COMMANDS else 0.0
    state.tire_temp = max(0.0, state.tire_temp + heat_gain - tire_cooling)
    state.fuel_pct = max(
        0.0,
        state.fuel_pct - FUEL_BURN_BASE_PCT * track.fuel_burn_rate * effective.fuel_burn_rate * modifiers[COMMAND_FUEL_BURN_INDEX] * fraction,
    )
    engine_gain = ENGINE_HEAT_BASE_C * track.engine_heat_rate * effective.engine_heat_rate / PERCENT_MAX * modifiers[COMMAND_ENGINE_HEAT_INDEX] * fraction
    engine_cooling = ENGINE_COOL_BASE_C * fraction if command in COOLING_COMMANDS else 0.0
    state.engine_temp = max(0.0, state.engine_temp + engine_gain - engine_cooling)
    state.driver_energy = max(0.0, state.driver_energy - DRIVER_ENERGY_DRAIN_BASE * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction)
    state.driver_focus = max(0.0, state.driver_focus - DRIVER_FOCUS_DRAIN_BASE * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction)
    state.driver_stress = min(PERCENT_MAX, state.driver_stress + DRIVER_STRESS_BUILD_BASE * modifiers[COMMAND_ENGINE_HEAT_INDEX] * fraction)


def _initial_state(car_id: str, driver_id: str, label: str, is_player: bool) -> RaceCarState:
    return RaceCarState(
        car_id=car_id,
        driver_id=driver_id,
        label=label,
        is_player=is_player,
        position=1,
        lap=0,
        distance=0.0,
        gap_to_leader=0.0,
        tire_pct=PERCENT_MAX,
        tire_temp=85.0,
        fuel_pct=PERCENT_MAX,
        condition_pct=PERCENT_MAX,
        engine_temp=90.0,
        driver_energy=PERCENT_MAX,
        driver_focus=PERCENT_MAX,
        driver_stress=0.0,
        pace_mode="normal",
        combat_mode="normal",
        engine_map="balanced",
        last_lap_time=None,
        total_time=0.0,
        event_log=[],
    )


def _rank(states: list[RaceCarState]) -> None:
    states.sort(key=lambda state: state.total_time)
    leader_time = states[0].total_time
    for index, state in enumerate(states, start=1):
        state.position = index
        state.gap_to_leader = state.total_time - leader_time


def _prize_for_position(event: Event, position: int) -> int:
    index = position - 1
    if index >= len(event.prize_money):
        return 0
    return event.prize_money[index]


def _find_garage_car(game_state: GameState, car_id: str) -> Car | None:
    return next((car for car in game_state.garage if car.identity.id == car_id), None)


def _get(items: dict[str, T], item_id: str, label: str) -> T:
    try:
        return items[item_id]
    except KeyError as exc:
        raise SimulationError(f"Unknown {label}: {item_id}") from exc
