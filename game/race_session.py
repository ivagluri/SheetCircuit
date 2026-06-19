from __future__ import annotations

import random
from copy import deepcopy

from constants import (
    AI_COMMAND,
    COMMAND_MODIFIERS,
    DRIVER_ENERGY_RECOVER_PIT,
    DRIVER_FOCUS_RECOVER_PIT,
    DRIVER_STAT_CAP,
    DRIVER_STRESS_RELIEF_PIT,
    DRIVER_XP_PER_RACE,
    DRIVER_XP_PER_STAT_POINT,
    MISTAKE_DNF_PROB,
    MISTAKE_TIME_MEDIUM,
    MISTAKE_TIME_SMALL,
    MILEAGE_KM_MULTIPLIER,
    PERCENT_MAX,
    RACE_TICKS_PER_LAP_DIVISOR,
    RIVAL_REACTIVE_GAP_S,
    RIVAL_TICK_VARIANCE_S,
    WEAR_PER_RACE_BASE,
)
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks
from game.models import RaceSession, RaceTickResult, TelemetryHistory
from game.opponents import build_opponent_grid, validate_event_entry
from game.simulation import (
    SimulationError,
    _apply_lap_wear,
    _find_garage_car,
    _get,
    _initial_state,
    _prize_for_position,
    _rank,
    calculate_lap_time,
)
from game.telemetry import failure_chance, mistake_chance, record_telemetry, warning_messages


def enter_event(game_state: GameState, event_id: str, car_id: str, driver_id: str, seed: int = 1) -> RaceSession:
    cars = {car.identity.id: deepcopy(car) for car in load_cars()}
    drivers = {driver.id: driver for driver in load_drivers()}
    events = {event.id: event for event in load_events()}
    tracks = {track.id: track for track in load_tracks()}
    parts = load_parts()
    event = _get(events, event_id, "event")
    track = _get(tracks, event.track_id, "track")
    garage_car = _find_garage_car(game_state, car_id)
    if garage_car is None:
        raise SimulationError(f"Unknown garage car: {car_id}")
    if game_state.money < event.entry_fee:
        raise SimulationError(f"Insufficient funds for entry fee: {event.entry_fee}")
    validate_event_entry(garage_car, event, parts)
    game_state.money -= event.entry_fee
    cars[car_id] = deepcopy(garage_car)
    player_driver = _get(drivers, driver_id, "driver")

    states = [_initial_state(car_id, player_driver.id, "YOU", True)]
    opponent_cars, opponent_drivers, opponent_entries = build_opponent_grid(
        event, car_id, player_driver, cars, parts, track, seed
    )
    cars.update(opponent_cars)
    drivers.update(opponent_drivers)
    for index, (opponent_car_id, opponent_driver_id, scalar) in enumerate(opponent_entries, start=1):
        opponent_state = _initial_state(opponent_car_id, opponent_driver_id, f"Rival {index}", False)
        opponent_state.performance_scalar = scalar
        states.append(opponent_state)

    ticks_per_lap = max(4, min(16, round(track.base_lap_time / RACE_TICKS_PER_LAP_DIVISOR)))
    return RaceSession(
        event_id=event.id,
        track_id=track.id,
        current_lap=0,
        total_laps=track.laps,
        cars=states,
        player_car_id=car_id,
        is_finished=False,
        telemetry={state.label: TelemetryHistory() for state in states},
        race_log=[],
        random_seed=seed,
        car_roster=cars,
        driver_roster=drivers,
        track=track,
        event=event,
        parts=parts,
        ticks_per_lap=ticks_per_lap,
        current_sub_tick=0,
    )


def apply_player_command(session: RaceSession, command: str) -> RaceTickResult:
    if command not in COMMAND_MODIFIERS:
        raise SimulationError(f"Unknown race command: {command}")
    player = _player_state(session)
    player.pace_mode = command
    if command == "hot_map":
        player.engine_map = "hot"
    elif command == "safe_map":
        player.engine_map = "safe"
    elif command == "fuel_save":
        player.engine_map = "fuel_save"
    return simulate_tick(session)


def simulate_tick(session: RaceSession) -> RaceTickResult:
    if session.is_finished:
        return RaceTickResult(
            session=session, lap=session.current_lap,
            standings=_active_standings(session), event_log=[], is_lap_end=False,
        )
    if session.track is None:
        raise SimulationError("RaceSession is missing track data")

    lap_fraction = 1.0 / session.ticks_per_lap
    is_lap_end = (session.current_sub_tick + 1) >= session.ticks_per_lap
    rng = random.Random(session.random_seed + session.current_lap * 100 + session.current_sub_tick)
    lap_log: list[str] = []
    player_time = _player_state(session).total_time

    for state in session.cars:
        if state.is_dnf:
            continue
        command = state.pace_mode if state.is_player else _ai_command(state, player_time)
        car = _get(session.car_roster, state.car_id, "car")
        driver = _get(session.driver_roster, state.driver_id, "driver")
        effective = compute_effective_stats(car, session.parts, command=command)
        full_lap_time = calculate_lap_time(
            effective, session.track, driver, state, rng,
            command=command, performance_scalar=state.performance_scalar,
        )

        tick_time = full_lap_time * lap_fraction
        if not state.is_player:
            # Per-tick jitter keeps the rival pack shuffling in close battles.
            tick_time += rng.uniform(-RIVAL_TICK_VARIANCE_S, RIVAL_TICK_VARIANCE_S)
        extra_penalty = 0.0

        if is_lap_end:
            if command == "pit":
                extra_penalty += session.track.pit_lane_loss_s
                state.driver_energy = min(PERCENT_MAX, state.driver_energy + DRIVER_ENERGY_RECOVER_PIT)
                state.driver_focus = min(PERCENT_MAX, state.driver_focus + DRIVER_FOCUS_RECOVER_PIT)
                state.driver_stress = max(0.0, state.driver_stress - DRIVER_STRESS_RELIEF_PIT)

            mistake_roll = rng.random()
            if mistake_roll < mistake_chance(state, driver, command):
                penalty = MISTAKE_TIME_MEDIUM if rng.random() < 0.35 else MISTAKE_TIME_SMALL
                extra_penalty += penalty
                state.event_log.append(f"{state.label} made a mistake and lost {penalty:.1f}s.")
                if command == "maximum_attack" and rng.random() < MISTAKE_DNF_PROB:
                    state.is_dnf = True
                    state.event_log.append(f"{state.label} crashed out.")

            if not state.is_dnf and rng.random() < failure_chance(state, effective, driver, command):
                state.event_log.append(f"{state.label} suffered a mechanical issue.")
                extra_penalty += MISTAKE_TIME_SMALL

        state.total_time += tick_time + extra_penalty

        if command == "pit" and is_lap_end:
            _apply_lap_wear(state, effective, session.track, "pit")
        else:
            _apply_lap_wear(state, effective, session.track, command, fraction=lap_fraction)

        if is_lap_end:
            state.last_lap_time = full_lap_time + extra_penalty
            state.lap += 1
            state.distance += session.track.length_km
            state.event_log.extend(warning_messages(state))
            lap_log.extend(state.event_log[-3:])

    active = _active_standings(session)
    if active:
        _rank(active)
    for state in active:
        if is_lap_end:
            record_telemetry(session.telemetry[state.label], state)

    session.current_sub_tick = (session.current_sub_tick + 1) % session.ticks_per_lap
    if is_lap_end:
        session.current_lap += 1
    session.is_finished = session.current_lap >= session.total_laps or len(active) <= 1

    if is_lap_end and not lap_log:
        lap_log.append(f"Lap {session.current_lap} completed.")
    log_lap = session.current_lap if is_lap_end else session.current_lap + 1
    session.race_log.extend((log_lap, msg) for msg in lap_log)
    return RaceTickResult(
        session=session, lap=session.current_lap,
        standings=active, event_log=lap_log, is_lap_end=is_lap_end,
    )


def finish_event(game_state: GameState, session: RaceSession) -> tuple[int, str]:
    player = _player_state(session)
    if player.is_dnf or session.event is None or session.track is None:
        prize_money = 0
    else:
        prize_money = _prize_for_position(session.event, player.position)
    game_state.money += prize_money
    garage_car = _find_garage_car(game_state, player.car_id)
    if garage_car is not None and session.track is not None:
        garage_car.condition.mileage += round(session.track.length_km * session.current_lap * MILEAGE_KM_MULTIPLIER)
        garage_car.condition.overall_condition = max(0.0, garage_car.condition.overall_condition - WEAR_PER_RACE_BASE)
    progression_message = ""
    if not player.is_dnf:
        hired_driver = next((d for d in game_state.hired_drivers if d.id == player.driver_id), None)
        if hired_driver is not None:
            progression_message = _apply_driver_progression(hired_driver)
    return prize_money, progression_message


_PROGRESSION_STATS = ("pace", "consistency", "racecraft", "fitness", "mechanical_sympathy", "wet_skill")


def _apply_driver_progression(driver) -> str:
    xp_before = driver.experience
    driver.experience += DRIVER_XP_PER_RACE
    gains_before = xp_before // DRIVER_XP_PER_STAT_POINT
    gains_after = driver.experience // DRIVER_XP_PER_STAT_POINT
    messages = [f"{driver.name} +{DRIVER_XP_PER_RACE} XP (total: {driver.experience})"]
    for _ in range(gains_after - gains_before):
        eligible = [(getattr(driver, s), s) for s in _PROGRESSION_STATS if getattr(driver, s) < DRIVER_STAT_CAP]
        if not eligible:
            break
        _, stat = min(eligible)
        setattr(driver, stat, getattr(driver, stat) + 1)
        messages.append(f"{driver.name} +1 {stat.replace('_', ' ')} ({getattr(driver, stat)})")
    return "  ".join(messages)


def _ai_command(state, player_time: float) -> str:
    """Opponents race the player back: push when locked in a close battle, else hold pace."""
    if abs(state.total_time - player_time) <= RIVAL_REACTIVE_GAP_S:
        return "push"
    return AI_COMMAND


def _player_state(session: RaceSession):
    return next(state for state in session.cars if state.is_player)


def _active_standings(session: RaceSession):
    active = [state for state in session.cars if not state.is_dnf]
    active.sort(key=lambda state: state.total_time)
    return active
