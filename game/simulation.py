from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import TypeVar

from constants import (
    AWD_LOWGRIP_BONUS,
    COMMAND_MODIFIERS,
    COMMAND_ENGINE_HEAT_INDEX,
    COMMAND_FUEL_BURN_INDEX,
    COMMAND_PACE_INDEX,
    COMMAND_STRESS_INDEX,
    COMMAND_TIRE_WEAR_INDEX,
    ENGINE_COOLING_COMMANDS,
    TYRE_COOLING_COMMANDS,
    DRIVER_PACE_FRACTION,
    DRIVER_ENERGY_DRAIN_PER_S,
    DRIVER_ENERGY_LOW_PCT,
    DRIVER_ENERGY_PACE_FRACTION,
    DRIVER_FOCUS_DRAIN_PER_S,
    DRIVER_STRESS_BUILD_PER_S,
    FITNESS_DRAIN_PER_UNIT,
    FITNESS_REF,
    ENGINE_CRITICAL_C,
    ENGINE_COOL_PER_S,
    ENGINE_COOLING_BOOST,
    ENGINE_HEAT_EXPONENT,
    ENGINE_HEAT_FACTOR_MAX,
    ENGINE_HEAT_FACTOR_MIN,
    ENGINE_HEAT_PER_S,
    ENGINE_HEAT_REF,
    ENGINE_OVERHEAT_C,
    ENGINE_TEMP_PENALTY_MAX,
    FUEL_ECONOMY_FLOOR_L_PER_KM,
    FUEL_EMPTY_PACE_FRACTION,
    FUEL_L_PER_KM_UNIT,
    FUEL_WEIGHT_PENALTY_PER_L,
    INITIAL_ENGINE_TEMP_C,
    INITIAL_TIRE_TEMP_C,
    GRADIENT_PW_GAIN,
    GRADIENT_PW_REF,
    MILEAGE_KM_MULTIPLIER,
    MIN_LAP_FRACTION,
    PIT_ENGINE_COOL_C,
    PIT_FUEL_RESTORE_PCT,
    PIT_TIRE_RESTORE_PCT,
    PIT_TIRE_TEMP_C,
    PERCENT_MAX,
    PERF_FRACTION,
    RACE_DAMAGE_WEAR_FACTOR,
    RANDOM_VARIANCE_SCALE,
    REFERENCE_COMPOSITE,
    SUBCONDITION_WEAR_FACTORS,
    TIRE_CRITICAL_C,
    TIRE_COOL_PER_S,
    TIRE_COOLING_BOOST,
    TIRE_HEAT_PER_KM,
    TIRE_OPTIMAL_C,
    TIRE_OVERHEAT_C,
    TIRE_TEMP_PENALTY_MAX,
    TYRE_WEAR_PCT_PER_KM,
    TIRE_WEAR_LINEAR_SHARE,
    TIRE_WEAR_PENALTY_MAX,
    TIRE_WEAR_PROGRESSION_EXP,
    WEAR_PER_RACE_BASE,
    WEAR_PER_RACE_MAX,
    WEAR_PER_RACE_MIN,
    WEAR_REFERENCE_RACE_KM,
    WEATHER_RNG_OFFSET,
)
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.market import maybe_refresh_free_agents
from game.loader import (
    apply_race_condition,
    load_cars,
    load_drivers,
    load_events,
    load_parts,
    load_tracks,
    resolve_race,
    roll_race_condition,
)
from game.models import Car, Driver, EffectiveCarStats, Event, RaceCarState, RaceResult, SegmentProfile, Track
from game.opponents import build_opponent_grid, opponent_entry_labels, validate_event_entry
from game.progression import team_level_for_xp

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
) -> float:
    """Time for one full lap. Segment-resolved when the track has segment_profiles."""
    return lap_time_over_interval(
        effective, track, driver, state, rng, command,
        start=0.0, length=1.0,
    )


def _pace_multiplier(composite: float, pace_factor: float, driver_pace: float) -> float:
    """Proportional pace scalar on the geometry lap (base_lap_time).

    1.0 for a design-midpoint car (composite == REFERENCE_COMPOSITE) at normal pace, so it laps
    at exactly base_lap_time; a capability or driver-pace edge makes it a consistent *fraction*
    faster on any track length (the honest model). Command pace_factor amplifies the capability
    edge the same way the old absolute formula did (`composite * pace_factor`).
    """
    return 1.0 - PERF_FRACTION * (composite * pace_factor - REFERENCE_COMPOSITE) - DRIVER_PACE_FRACTION * driver_pace


def lap_time_over_interval(
    effective: EffectiveCarStats,
    track: Track,
    driver: Driver | None = None,
    state: RaceCarState | None = None,
    rng: random.Random | None = None,
    command: str = "normal",
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
    pace_factor = COMMAND_MODIFIERS[command][COMMAND_PACE_INDEX]
    if track.segment_profiles:
        core = 0.0
        for profile, overlap in _segments_in_interval(track.segment_profiles, start, length):
            composite = _segment_composite(effective, profile)
            driver_pace = _blended_pace(driver, profile.wet_weight)
            core += track.base_lap_time * _pace_multiplier(composite, pace_factor, driver_pace) * overlap
    else:
        composite = _track_composite(effective, track)
        driver_pace = driver.pace if driver is not None else 0.0
        core = track.base_lap_time * _pace_multiplier(composite, pace_factor, driver_pace) * length

    # The climb adjustment (power-to-weight driven) is applied before re-flooring, and scales
    # with the interval length so the segment-resolved and aggregate paths agree.
    core += _climb_adjustment(track, effective) * length
    core = max(core, track.base_lap_time * length * MIN_LAP_FRACTION)
    # State penalty is a deterministic drag -> scales linearly with the slice. Driver variance is
    # additive noise -> scales with sqrt(slice) so the per-lap spread is identical whether a lap is
    # one tick or a thousand (resolution-invariant; at length=1 this is the instant-sim draw).
    return core + _state_penalty(state, effective, track.base_lap_time) * length + _lap_variance(driver, rng) * math.sqrt(length)


def _climb_adjustment(track: Track, effective: EffectiveCarStats) -> float:
    """Seconds a full lap gains/loses on a net climb, driven by the car's real power-to-weight.

    Monotonic in the car's own hp/kg, anchored to real paved Pikes Peak stock times (see
    constants): below GRADIENT_PW_REF the climb adds time, above it a strong car claws time
    back. 0 for loop layouts (climb_gradient_pct == 0). Nothing references other cars."""
    if track.climb_gradient_pct <= 0.0:
        return 0.0
    pw = max(effective.power_to_weight, 1e-3)
    return GRADIENT_PW_GAIN * math.log(GRADIENT_PW_REF / pw) * track.climb_gradient_pct * track.length_km


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
    if effective.drivetrain == "AWD":
        # AWD claws back traction where grip is scarce; zero on dry tarmac (grip_mult == 1),
        # so the dry-tarmac segment/aggregate equivalence is preserved.
        grip *= 1.0 + AWD_LOWGRIP_BONUS * (1.0 - profile.grip_mult)
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


def _state_penalty(state: RaceCarState | None, effective: EffectiveCarStats, base_lap_time: float) -> float:
    if state is None:
        return 0.0
    # Progressive tyre-grip tax: a linear tax (bites steadily, incl. in a sprint) plus a
    # convex end-of-life cliff (the last third of wear hurts far more). See constants.
    wear = (PERCENT_MAX - state.tire_pct) / PERCENT_MAX
    penalty = TIRE_WEAR_PENALTY_MAX * (
        TIRE_WEAR_LINEAR_SHARE * wear
        + (1.0 - TIRE_WEAR_LINEAR_SHARE) * wear ** TIRE_WEAR_PROGRESSION_EXP
    )
    # Fuel load: a full tank is the reference; every litre burned lightens the car and
    # buys pace, so brimming at a stop costs lap time until it burns off.
    burned_l = (PERCENT_MAX - state.fuel_pct) / PERCENT_MAX * effective.fuel_capacity_l
    penalty -= burned_l * FUEL_WEIGHT_PENALTY_PER_L
    if state.tire_temp > TIRE_OVERHEAT_C:
        penalty += _range_penalty(state.tire_temp, TIRE_OVERHEAT_C, TIRE_CRITICAL_C, TIRE_TEMP_PENALTY_MAX)
    if state.engine_temp > ENGINE_OVERHEAT_C:
        penalty += _range_penalty(state.engine_temp, ENGINE_OVERHEAT_C, ENGINE_CRITICAL_C, ENGINE_TEMP_PENALTY_MAX)
    if state.fuel_pct <= 0.0:
        # Dry tank: the car limps on fumes. Proportional to the lap so it is equally
        # devastating on any track length, but the car can still crawl to the pits.
        penalty += base_lap_time * FUEL_EMPTY_PACE_FRACTION
    if state.driver_energy < DRIVER_ENERGY_LOW_PCT:
        # An exhausted driver leaks pace, ramping to the full fraction at zero energy.
        deficit = 1.0 - state.driver_energy / DRIVER_ENERGY_LOW_PCT
        penalty += base_lap_time * DRIVER_ENERGY_PACE_FRACTION * deficit
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
    # Player driver resolves from the hired roster (incl. generated hires), overlaid on
    # the seed catalog so hired instances win.
    drivers = {driver.id: driver for driver in load_drivers()}
    drivers.update({driver.id: driver for driver in game_state.hired_drivers})
    events = {event.id: event for event in load_events()}
    tracks = {track.id: track for track in load_tracks()}

    event = _get(events, event_id, "event")
    current_team_level = team_level_for_xp(game_state.team_xp)
    if current_team_level < event.min_team_level:
        raise SimulationError(
            f"{event.name} requires Team Lv {event.min_team_level}; "
            f"current Team Lv {current_team_level} ({game_state.team_xp} XP)."
        )
    track = _get(tracks, event.track_id, "track")
    # Race-day forecast: rolled on an isolated stream (the main rng's draw sequence is
    # untouched) and applied to this freshly loaded track copy.
    weather = roll_race_condition(track, random.Random(seed + WEATHER_RNG_OFFSET))
    apply_race_condition(track, weather)
    player_car = _find_garage_car(game_state, car_id) or deepcopy(_get(cars, car_id, "car"))
    player_driver = _get(drivers, driver_id, "driver")
    validate_event_entry(player_car, event, parts)
    # Same economics as the live engine (enter_event), minus the funds gate -- this is
    # the batch summary, used by tools on throwaway states.
    game_state.money -= event.entry_fee
    cars[player_car.identity.id] = deepcopy(player_car)

    race_cars = [_initial_state(player_car.identity.id, player_driver.id, "YOU", True)]
    opponent_cars, opponent_drivers, opponent_entries = build_opponent_grid(
        event, player_car.identity.id, player_driver, cars, parts, track, seed
    )
    cars.update(opponent_cars)
    drivers.update(opponent_drivers)
    opponent_labels = opponent_entry_labels(opponent_entries, opponent_cars)
    for label, (opponent_car_id, opponent_driver_id) in zip(opponent_labels, opponent_entries):
        opponent_state = _initial_state(opponent_car_id, opponent_driver_id, label, False)
        race_cars.append(opponent_state)

    race_format = resolve_race(event, track)

    lap_times: dict[str, list[float]] = {state.label: [] for state in race_cars}
    race_log: list[str] = []
    if weather != "dry":
        race_log.append(f"Race runs {weather}.")
    # Lockstep loop shared by lap and duration races: every car runs the same whole laps, so
    # a duration race (Regime A) ends on a clean lap boundary once the leader passes the cap.
    completed_laps = 0
    # Effective stats are invariant for the whole race (condition and tune don't change
    # mid-race), so compute them once per entry instead of once per lap per car.
    effective_by_car = {
        state.car_id: compute_effective_stats(player_car if state.is_player else cars[state.car_id], parts)
        for state in race_cars
    }
    while not _race_finished(race_cars, race_format, completed_laps):
        for state in race_cars:
            driver = player_driver if state.is_player else drivers[state.driver_id]
            effective = effective_by_car[state.car_id]
            lap_time = calculate_lap_time(effective, track, driver, state, rng)
            state.last_lap_time = lap_time
            state.total_time += lap_time
            state.lap += 1
            state.distance += track.length_km
            _apply_lap_wear(state, effective, track, driver_fitness=driver.fitness, seconds=lap_time)
            lap_times[state.label].append(lap_time)

        _rank(race_cars)
        race_log.append(f"Lap {race_cars[0].lap}: leader {race_cars[0].label}")
        completed_laps += 1

    _rank(race_cars)
    total_laps = completed_laps
    player_state = next(state for state in race_cars if state.is_player)
    prize_money = _prize_for_position(event, player_state.position)
    game_state.money += prize_money
    game_state.week += 1
    maybe_refresh_free_agents(game_state)
    garage_car = _find_garage_car(game_state, car_id)
    if garage_car is not None:
        damage = PERCENT_MAX - player_state.condition_pct
        apply_post_race_wear(garage_car, track.length_km * total_laps, damage)

    return RaceResult(
        event_id=event.id,
        track_id=track.id,
        total_laps=total_laps,
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
    seconds: float | None = None,
) -> None:
    """Evolve tyre/fuel/engine/driver state for a slice of running, in physical units.

    Distance covered is ``track.length_km * fraction``; tyres lose a distance-based
    share of life and fuel burns litres against the tank, so a stint and a tank are
    real kilometres regardless of lap length. Engine heat and driver fatigue accrue over
    ``seconds`` of running (the slice's real time -- callers pass the tick/lap time; it
    falls back to ``base_lap_time * fraction``), which is what they physically track and
    what makes them duration-ready. ``profile`` supplies a segment's local (surface/
    condition adjusted) tag multipliers; those still integrate to the aggregate over a
    full lap, so segment ticks and a whole-lap call wear the car by the same total.
    """
    modifiers = COMMAND_MODIFIERS[command]
    if command == "pit" and fraction >= 1.0:
        state.tire_pct = PIT_TIRE_RESTORE_PCT
        state.tire_temp = PIT_TIRE_TEMP_C
        state.fuel_pct = PIT_FUEL_RESTORE_PCT
        state.engine_temp = max(INITIAL_ENGINE_TEMP_C, state.engine_temp - PIT_ENGINE_COOL_C)
        return
    if seconds is None:
        seconds = track.base_lap_time * fraction
    distance_km = track.length_km * fraction
    tire_wear_rate = profile.tire_wear_rate if profile is not None else track.tire_wear_rate
    fuel_burn_rate = profile.fuel_burn_rate if profile is not None else track.fuel_burn_rate
    engine_heat_rate = profile.engine_heat_rate if profile is not None else track.engine_heat_rate

    # Tyres: % of a distance-based life. effective.tire_wear_rate is the car's wear
    # susceptibility (compound/resistance/width); the track tag rate adds the local
    # surface/condition load. Heat builds with work (distance) and fights an always-on
    # passive airflow cooling (time) -- a heat *balance*: gentle running drifts back
    # toward the operating floor, attacking out-heats the airflow. The cooling commands
    # multiply the passive rate. Cooling never pulls a tyre below its operating floor.
    wear_pct = TYRE_WEAR_PCT_PER_KM * effective.tire_wear_rate * tire_wear_rate * distance_km * modifiers[COMMAND_TIRE_WEAR_INDEX]
    state.tire_pct = max(0.0, state.tire_pct - wear_pct)
    heat_gain = TIRE_HEAT_PER_KM * effective.tire_heat_rate * tire_wear_rate * distance_km * modifiers[COMMAND_TIRE_WEAR_INDEX]
    tire_cooling = TIRE_COOL_PER_S * seconds
    if command in TYRE_COOLING_COMMANDS:
        tire_cooling *= TIRE_COOLING_BOOST
    tire_floor = min(state.tire_temp, TIRE_OPTIMAL_C)
    state.tire_temp = max(tire_floor, state.tire_temp + heat_gain - tire_cooling)

    # Fuel: litres over distance, drawn against the tank -> % of capacity. Economy is affine
    # in the car's burn rate (floor + rate x unit) so the catalog stays in a realistic band;
    # the track tag rate and pace command scale the whole economy (see constants).
    economy_l_per_km = FUEL_ECONOMY_FLOOR_L_PER_KM + effective.fuel_burn_rate * FUEL_L_PER_KM_UNIT
    litres = economy_l_per_km * fuel_burn_rate * distance_km * modifiers[COMMAND_FUEL_BURN_INDEX]
    state.fuel_pct = max(0.0, state.fuel_pct - litres / max(effective.fuel_capacity_l, 1.0) * PERCENT_MAX)

    # Engine heat: per second of running at load, against the same always-on passive
    # cooling balance (radiator airflow); the floor is normal operating temperature.
    # The car's raw engine_heat_rate spans ~5x across the catalog (a light four-pot vs a
    # highly-stressed V12), which is far too wide to give a consistent "all-out redlines
    # in a couple of laps" cadence -- calibrate it and a mid car never heats while a
    # supercar cooks at cruise. So normalise it against a reference and compress the
    # spread: a hotter engine still heats faster (cooling/engine-map stays a real build
    # lever), but the window stays sane at both ends.
    heat_factor = min(
        ENGINE_HEAT_FACTOR_MAX,
        max(ENGINE_HEAT_FACTOR_MIN, (effective.engine_heat_rate / ENGINE_HEAT_REF) ** ENGINE_HEAT_EXPONENT),
    )
    engine_gain = ENGINE_HEAT_PER_S * seconds * engine_heat_rate * heat_factor * modifiers[COMMAND_ENGINE_HEAT_INDEX]
    engine_cooling = ENGINE_COOL_PER_S * seconds
    if command in ENGINE_COOLING_COMMANDS:
        engine_cooling *= ENGINE_COOLING_BOOST
    engine_floor = min(state.engine_temp, INITIAL_ENGINE_TEMP_C)
    state.engine_temp = max(engine_floor, state.engine_temp + engine_gain - engine_cooling)

    # Driver: fatigue is a function of time on track.
    fitness_drain = _fitness_drain_factor(driver_fitness)
    state.driver_energy = max(0.0, state.driver_energy - DRIVER_ENERGY_DRAIN_PER_S * seconds * modifiers[COMMAND_TIRE_WEAR_INDEX] * fitness_drain)
    state.driver_focus = max(0.0, state.driver_focus - DRIVER_FOCUS_DRAIN_PER_S * seconds * modifiers[COMMAND_TIRE_WEAR_INDEX] * fitness_drain)
    state.driver_stress = min(PERCENT_MAX, state.driver_stress + DRIVER_STRESS_BUILD_PER_S * seconds * modifiers[COMMAND_STRESS_INDEX])


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
        tire_temp=INITIAL_TIRE_TEMP_C,
        fuel_pct=PERCENT_MAX,
        condition_pct=PERCENT_MAX,
        engine_temp=INITIAL_ENGINE_TEMP_C,
        driver_energy=PERCENT_MAX,
        driver_focus=PERCENT_MAX,
        driver_stress=0.0,
        pace_mode="normal",
        last_lap_time=None,
        total_time=0.0,
        event_log=[],
    )


def _race_finished(states: list[RaceCarState], race_format: "RaceFormat", completed_laps: int) -> bool:
    """Lockstep stop condition shared by the batch and interactive loops.

    Lap/distance races stop at the fixed lap target. A duration race (Regime A) runs whole
    laps until the leader's elapsed time crosses the cap, then finishes that lead lap -- the
    field is synchronized, so everyone completes the same number of laps. At least one lap
    always runs, even if the cap is shorter than a single lap.
    """
    if race_format.laps is not None:
        return completed_laps >= race_format.laps
    leader_time = min((state.total_time for state in states), default=0.0)
    return completed_laps >= 1 and leader_time >= (race_format.duration_s or 0.0)


def _rank(states: list[RaceCarState]) -> None:
    # Rank by laps completed first, then elapsed time. In a fixed-lap race the field runs
    # in lockstep so the lap key is always equal and this is a pure time sort; the key is
    # here so duration/enduro races (cars finishing different lap counts) rank correctly
    # once that mode is wired in. Gap stays a simple time delta while laps are uniform.
    states.sort(key=lambda state: (-state.lap, state.total_time))
    leader_time = states[0].total_time
    for index, state in enumerate(states, start=1):
        state.position = index
        state.gap_to_leader = state.total_time - leader_time


def _prize_for_position(event: Event, position: int) -> int:
    index = position - 1
    if index >= len(event.prize_money):
        return 0
    return event.prize_money[index]


def apply_post_race_wear(garage_car: Car, race_km: float, damage_pct: float = 0.0) -> float:
    """Wear a garage car after a race, in proportion to the real distance raced.

    Overall wear is distance-scaled (clamped), plus a share of any damage the car took
    mid-race (``damage_pct`` = points of RaceCarState.condition_pct lost). Sub-systems
    wear alongside at their own rates, so upkeep is per-system; mileage accrues with the
    same distance. Returns the overall wear applied."""
    wear = WEAR_PER_RACE_BASE * race_km / WEAR_REFERENCE_RACE_KM
    wear = min(WEAR_PER_RACE_MAX, max(WEAR_PER_RACE_MIN, wear))
    wear += damage_pct * RACE_DAMAGE_WEAR_FACTOR
    condition = garage_car.condition
    condition.overall_condition = max(0.0, condition.overall_condition - wear)
    for field_name, factor in SUBCONDITION_WEAR_FACTORS.items():
        setattr(condition, field_name, max(0.0, getattr(condition, field_name) - wear * factor))
    condition.mileage += round(race_km * MILEAGE_KM_MULTIPLIER)
    return wear


def _find_garage_car(game_state: GameState, car_id: str) -> Car | None:
    return next((car for car in game_state.garage if car.identity.id == car_id), None)


def _get(items: dict[str, T], item_id: str, label: str) -> T:
    try:
        return items[item_id]
    except KeyError as exc:
        raise SimulationError(f"Unknown {label}: {item_id}") from exc
