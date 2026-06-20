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
    FITNESS_DRAIN_PER_UNIT,
    FITNESS_REF,
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
from game.models import Car, Driver, EffectiveCarStats, Event, RaceCarState, RaceResult, SegmentProfile, Track
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
    """Time for one full lap. Segment-resolved when the track has segment_profiles."""
    return lap_time_over_interval(
        effective, track, driver, state, rng, command, performance_scalar,
        start=0.0, length=1.0,
    )


def lap_time_over_interval(
    effective: EffectiveCarStats,
    track: Track,
    driver: Driver | None = None,
    state: RaceCarState | None = None,
    rng: random.Random | None = None,
    command: str = "normal",
    performance_scalar: float = 1.0,
    start: float = 0.0,
    length: float = 1.0,
) -> float:
    """Time to cover the position interval ``[start, start + length)`` of one lap.

    When the track carries segment_profiles each overlapped segment contributes its
    own local pace (tag mix + surface/condition); the length-weighted integral over a
    whole lap reproduces the aggregate formula exactly on dry tarmac, so existing
    balance is preserved while composition now shapes pace within the lap. Falls back
    to the aggregate model for profile-less tracks.
    """
    pace_factor = COMMAND_MODIFIERS[command][0]
    if track.segment_profiles:
        core = 0.0
        for profile, overlap in _segments_in_interval(track.segment_profiles, start, length):
            composite = _segment_composite(effective, profile)
            driver_pace = _blended_pace(driver, profile.wet_weight)
            time_rate = (
                track.base_lap_time
                - PERF_SCALE * composite * pace_factor * performance_scalar
                - driver_pace * DRIVER_PACE_SCALE
            )
            core += time_rate * overlap
    else:
        composite = _track_composite(effective, track)
        driver_pace_bonus = driver.pace * DRIVER_PACE_SCALE if driver is not None else 0.0
        core = (
            track.base_lap_time
            - PERF_SCALE * composite * pace_factor * performance_scalar
            - driver_pace_bonus
        ) * length

    return core + (_state_penalty(state) + _lap_variance(driver, rng)) * length


def _segments_in_interval(
    profiles: list[SegmentProfile], start: float, length: float
) -> list[tuple[SegmentProfile, float]]:
    end = start + length
    overlaps: list[tuple[SegmentProfile, float]] = []
    for profile in profiles:
        overlap = min(profile.end_pct, end) - max(profile.start_pct, start)
        if overlap > 1e-12:
            overlaps.append((profile, overlap))
    return overlaps


def _segment_composite(effective: EffectiveCarStats, profile: SegmentProfile) -> float:
    weights = profile.weights
    grip = effective.grip * (1.0 - profile.wet_weight) + effective.wet_grip * profile.wet_weight
    composite = (
        effective.acceleration * weights["acceleration"]
        + effective.power * weights["power"]
        + effective.top_speed * weights["top_speed"]
        + grip * weights["grip"]
        + effective.braking * weights["braking"]
        + effective.handling * weights["handling"]
        + effective.aero_grip * weights["aero"]
    )
    return composite * profile.grip_mult


def _blended_pace(driver: Driver | None, wet_weight: float) -> float:
    if driver is None:
        return 0.0
    return driver.pace * (1.0 - wet_weight) + driver.wet_skill * wet_weight


def _state_penalty(state: RaceCarState | None) -> float:
    if state is None:
        return 0.0
    penalty = (PERCENT_MAX - state.tire_pct) / PERCENT_MAX * TIRE_WEAR_PENALTY_MAX
    if state.tire_temp > TIRE_OVERHEAT_C:
        penalty += _range_penalty(state.tire_temp, TIRE_OVERHEAT_C, TIRE_CRITICAL_C, TIRE_TEMP_PENALTY_MAX)
    if state.engine_temp > ENGINE_OVERHEAT_C:
        penalty += _range_penalty(state.engine_temp, ENGINE_OVERHEAT_C, ENGINE_CRITICAL_C, ENGINE_TEMP_PENALTY_MAX)
    return penalty


def _lap_variance(driver: Driver | None, rng: random.Random | None) -> float:
    if rng is None:
        return 0.0
    consistency = driver.consistency if driver is not None else PERCENT_MAX / 2
    variance = RANDOM_VARIANCE_SCALE * (1 - consistency / PERCENT_MAX)
    return rng.uniform(-variance, variance)


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
            _apply_lap_wear(state, effective, track, driver_fitness=driver.fitness)
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


def _fitness_drain_factor(driver_fitness: float) -> float:
    """A fitter driver loses energy and focus more slowly (1.0 at the reference fitness)."""
    return max(0.5, 1.0 - (driver_fitness - FITNESS_REF) * FITNESS_DRAIN_PER_UNIT)


def _apply_lap_wear(
    state: RaceCarState,
    effective: EffectiveCarStats,
    track: Track,
    command: str = "normal",
    fraction: float = 1.0,
    profile: SegmentProfile | None = None,
    driver_fitness: float = FITNESS_REF,
) -> None:
    """Evolve tyre/fuel/engine/driver state for a slice of running.

    When ``profile`` is given the slice uses that segment's local (surface/condition
    adjusted) rates; otherwise the track aggregate is used. Local rates integrate back
    to the aggregate over a full lap, so per-segment ticks and a single whole-lap call
    wear the car by the same total on a uniform track. ``driver_fitness`` scales the
    energy/focus drain (defaults to the neutral reference for state-only callers).
    """
    modifiers = COMMAND_MODIFIERS[command]
    if command == "pit" and fraction >= 1.0:
        state.tire_pct = PIT_TIRE_RESTORE_PCT
        state.tire_temp = PIT_TIRE_TEMP_C
        state.fuel_pct = PIT_FUEL_RESTORE_PCT
        state.engine_temp = max(0.0, state.engine_temp - PIT_ENGINE_COOL_C)
        return
    tire_wear_rate = profile.tire_wear_rate if profile is not None else track.tire_wear_rate
    fuel_burn_rate = profile.fuel_burn_rate if profile is not None else track.fuel_burn_rate
    engine_heat_rate = profile.engine_heat_rate if profile is not None else track.engine_heat_rate
    state.tire_pct = max(
        0.0,
        state.tire_pct - TIRE_WEAR_BASE_PCT * tire_wear_rate * effective.tire_wear_rate * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction,
    )
    heat_gain = TIRE_HEAT_BASE_C * tire_wear_rate * effective.tire_heat_rate * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction
    tire_cooling = TIRE_COOL_BASE_C * fraction if command in COOLING_COMMANDS else 0.0
    state.tire_temp = max(0.0, state.tire_temp + heat_gain - tire_cooling)
    state.fuel_pct = max(
        0.0,
        state.fuel_pct - FUEL_BURN_BASE_PCT * fuel_burn_rate * effective.fuel_burn_rate * modifiers[COMMAND_FUEL_BURN_INDEX] * fraction,
    )
    engine_gain = ENGINE_HEAT_BASE_C * engine_heat_rate * effective.engine_heat_rate / PERCENT_MAX * modifiers[COMMAND_ENGINE_HEAT_INDEX] * fraction
    engine_cooling = ENGINE_COOL_BASE_C * fraction if command in COOLING_COMMANDS else 0.0
    state.engine_temp = max(0.0, state.engine_temp + engine_gain - engine_cooling)
    fitness_drain = _fitness_drain_factor(driver_fitness)
    state.driver_energy = max(0.0, state.driver_energy - DRIVER_ENERGY_DRAIN_BASE * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction * fitness_drain)
    state.driver_focus = max(0.0, state.driver_focus - DRIVER_FOCUS_DRAIN_BASE * modifiers[COMMAND_TIRE_WEAR_INDEX] * fraction * fitness_drain)
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
