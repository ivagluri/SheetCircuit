from __future__ import annotations

import math
import random
from copy import deepcopy
from dataclasses import dataclass

from constants import (
    AI_COMMAND,
    AI_PIT_FUEL_PCT,
    AI_PIT_TIRE_PCT,
    COMMAND_MODIFIERS,
    COMMAND_OVERTAKE_INDEX,
    CONDITION_HIT_FAILURE,
    CONDITION_HIT_MISTAKE,
    DRIVER_ENERGY_RECOVER_PIT,
    DRIVER_FOCUS_RECOVER_PIT,
    DRIVER_STAT_CAP,
    DRIVER_STRESS_RELIEF_PIT,
    DRIVER_XP_PER_RACE,
    DRIVER_XP_PER_STAT_POINT,
    DNF_DRIVER_RELIEF,
    DNF_DRIVER_RELIEF_FLOOR,
    ENGINE_OVERHEAT_C,
    MISTAKE_DNF_PROB,
    MISTAKE_TIME_MEDIUM,
    MISTAKE_TIME_SMALL,
    MAX_TICKS_PER_LAP,
    MIN_TICKS_PER_LAP,
    OVERTAKE_BASE_CHANCE_PER_LAP,
    OVERTAKE_BOTCH_PROB,
    OVERTAKE_BOTCH_TIME,
    OVERTAKE_CONTEST_MAX_S,
    OVERTAKE_FOLLOW_GAP_S,
    OVERTAKE_GAP_JITTER_S,
    OVERTAKE_RACECRAFT_PER_POINT,
    PERCENT_MAX,
    PRESENTATION_SPEED_FACTOR,
    RIVAL_LAP_JITTER_S,
    RIVAL_REACTIVE_GAP_S,
    SALARY_WEEKLY_ENABLED,
    SALARY_WEEKLY_FRACTION,
    TICK_RATE_HZ,
    TIRE_OVERHEAT_C,
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
from game.models import CarCondition, RaceSession, RaceTickResult, TelemetryHistory
from game.opponents import build_opponent_grid, opponent_entry_labels, validate_event_entry
from game.progression import TeamXpAward, normalize_event_progress, team_level_for_xp, team_xp_award, updated_event_progress
from game.simulation import (
    SimulationError,
    _apply_lap_wear,
    _find_garage_car,
    _get,
    _initial_state,
    _prize_for_position,
    _rank,
    _segments_in_interval,
    apply_post_race_wear,
    lap_time_over_interval,
)
from game.telemetry import failure_chance, failure_dnf_chance, mistake_chance, record_telemetry, warning_messages


@dataclass
class FinishEventResult:
    prize_money: int
    driver_progression_message: str
    team_xp_award: TeamXpAward | None
    team_xp_before: int
    team_xp_after: int
    event_progress_before: dict
    event_progress_after: dict
    player_position: int
    player_is_dnf: bool
    player_total_time_s: float | None
    car_condition_before: CarCondition | None
    car_condition_after: CarCondition | None

    def __iter__(self):
        yield self.prize_money
        yield self.driver_progression_message


def ticks_per_lap_for(lap_time_s: float) -> int:
    """Sub-ticks for a lap whose real (canonical) time is ``lap_time_s``, tied to watched time.

    watched = lap_time_s / PRESENTATION_SPEED_FACTOR; ticks = watched * TICK_RATE_HZ. This keeps
    the per-update pause a constant 1/TICK_RATE_HZ (no dead air) while the total watched length
    tracks the car's actual pace, and a true realtime race (factor 1.0) gets proportionally more
    ticks. Safe because the sim is resolution-invariant: tick count does not move the result.
    """
    watched_s = lap_time_s / PRESENTATION_SPEED_FACTOR
    ticks = round(watched_s * TICK_RATE_HZ)
    return max(MIN_TICKS_PER_LAP, min(MAX_TICKS_PER_LAP, ticks))


def enter_event(game_state: GameState, event_id: str, car_id: str, driver_id: str, seed: int = 1) -> RaceSession:
    cars = {car.identity.id: deepcopy(car) for car in load_cars()}
    # The player's driver comes from their hired roster (which includes procedurally
    # generated hires), overlaid on the seed catalog so hired instances win.
    drivers = {driver.id: driver for driver in load_drivers()}
    drivers.update({driver.id: driver for driver in game_state.hired_drivers})
    events = {event.id: event for event in load_events()}
    tracks = {track.id: track for track in load_tracks()}
    parts = load_parts()
    event = _get(events, event_id, "event")
    _validate_team_level_entry(game_state, event)
    track = _get(tracks, event.track_id, "track")
    # Race-day forecast: rolled on an isolated stream (the main rng's draw sequence is
    # untouched) and applied to this session's freshly loaded track copy.
    weather = roll_race_condition(track, random.Random(seed + WEATHER_RNG_OFFSET))
    apply_race_condition(track, weather)
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
    opponent_labels = opponent_entry_labels(opponent_entries, opponent_cars)
    for label, (opponent_car_id, opponent_driver_id) in zip(opponent_labels, opponent_entries):
        opponent_state = _initial_state(opponent_car_id, opponent_driver_id, label, False)
        states.append(opponent_state)

    race_format = resolve_race(event, track)
    # Effective stats are invariant for the whole race, so compute them once per entry;
    # every tick reads this cache instead of recomputing per car.
    effective_stats = {
        state.car_id: compute_effective_stats(cars[state.car_id], parts) for state in states
    }
    # Density follows the *player's* nominal lap pace, not the neutral track reference, so the
    # watched length matches the "your car vs this event" estimate (a slow car genuinely takes
    # longer to run). Deterministic (no wear, no variance) so it is stable across seeds.
    nominal_lap_s = lap_time_over_interval(effective_stats[car_id], track, player_driver, start=0.0, length=1.0)
    ticks_per_lap = ticks_per_lap_for(nominal_lap_s)
    return RaceSession(
        event_id=event.id,
        track_id=track.id,
        current_lap=0,
        # Duration races have no fixed target; total_laps tracks the completed-lap count
        # and grows as the race runs (see simulate_tick), so it starts at 0.
        total_laps=race_format.laps or 0,
        duration_s=race_format.duration_s,
        cars=states,
        player_car_id=car_id,
        is_finished=False,
        telemetry={state.label: TelemetryHistory() for state in states},
        race_log=[(1, f"Race runs {weather}.")] if weather != "dry" else [],
        random_seed=seed,
        weather=weather,
        car_roster=cars,
        driver_roster=drivers,
        track=track,
        event=event,
        parts=parts,
        ticks_per_lap=ticks_per_lap,
        current_sub_tick=0,
        effective_stats=effective_stats,
        player_car_condition_before=deepcopy(garage_car.condition),
    )


def _validate_team_level_entry(game_state: GameState, event) -> None:
    current_level = team_level_for_xp(game_state.team_xp)
    if current_level < event.min_team_level:
        raise SimulationError(
            f"{event.name} requires Team Lv {event.min_team_level}; "
            f"current Team Lv {current_level} ({game_state.team_xp} XP)."
        )


def apply_player_command(session: RaceSession, command: str) -> RaceTickResult:
    if command not in COMMAND_MODIFIERS:
        raise SimulationError(f"Unknown race command: {command}")
    player = _player_state(session)
    player.pace_mode = command
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
    # The whole field shares one track position each tick; the last tick of a lap
    # runs to the line exactly so per-lap totals stay clean.
    seg_start = session.current_sub_tick * lap_fraction
    seg_length = (1.0 - seg_start) if is_lap_end else lap_fraction
    overlaps = (
        _segments_in_interval(session.track.segment_profiles, seg_start, seg_length)
        if session.track.segment_profiles
        else []
    )
    # Stride by more than any possible tick count so (lap, sub_tick) pairs never share
    # a seed (a stride of 100 collided once ticks_per_lap exceeded it, e.g. realtime).
    rng = random.Random(
        session.random_seed + session.current_lap * (MAX_TICKS_PER_LAP + 1) + session.current_sub_tick
    )
    lap_log: list[str] = []
    player_time = _player_state(session).total_time

    # Process the field in running order so overtaking can compare each car against the
    # one directly ahead on the road (already advanced this tick).
    field_order = sorted(
        (state for state in session.cars if not state.is_dnf),
        key=lambda state: state.total_time,
    )
    road_ahead: list[tuple[float, object, object, str]] = []  # (pre-tick time, state, driver, command) of advanced cars
    for state in field_order:
        pre_tick_time = state.total_time
        command = state.pace_mode if state.is_player else _ai_command(state, player_time)
        driver = _get(session.driver_roster, state.driver_id, "driver")
        effective = session.effective_stats.get(state.car_id)
        if effective is None:  # sessions built without the cache (tests, old saves)
            effective = compute_effective_stats(_get(session.car_roster, state.car_id, "car"), session.parts)
        tick_time = lap_time_over_interval(
            effective, session.track, driver, state, rng,
            command=command,
            start=seg_start, length=seg_length,
        )
        if not state.is_player:
            # Jitter keeps the rival pack shuffling in close battles. Scaled by sqrt(slice) so the
            # accumulated per-lap shuffle is the same at any tick count (resolution-invariant).
            tick_time += rng.uniform(-RIVAL_LAP_JITTER_S, RIVAL_LAP_JITTER_S) * math.sqrt(seg_length)
        extra_penalty = 0.0

        # Mistakes and failures can strike on any tick, scaled to the slice of track
        # covered, so a single-lap stage races the same as a multi-lap circuit.
        if rng.random() < mistake_chance(state, driver, command) * seg_length:
            penalty = MISTAKE_TIME_MEDIUM if rng.random() < 0.35 else MISTAKE_TIME_SMALL
            extra_penalty += penalty
            state.event_log.append(f"{state.label} made a mistake and lost {penalty:.1f}s.")
            if penalty == MISTAKE_TIME_MEDIUM:
                # A big moment dings the car; damage feeds failure risk and post-race wear.
                state.condition_pct = max(0.0, state.condition_pct - CONDITION_HIT_MISTAKE)
            if command == "go_all_out" and rng.random() < _dnf_chance(driver):
                state.is_dnf = True
                state.event_log.append(f"{state.label} crashed out.")
        if not state.is_dnf and rng.random() < failure_chance(state, effective, driver, command) * seg_length:
            if rng.random() < failure_dnf_chance(state):
                # Terminal failure: an overheated engine makes a mechanical issue far
                # more likely to end the race (see FAILURE_DNF_* in constants).
                state.is_dnf = True
                state.event_log.append(f"{state.label} retired with a mechanical failure.")
            else:
                state.event_log.append(f"{state.label} suffered a mechanical issue.")
                extra_penalty += MISTAKE_TIME_SMALL
                # Non-terminal issues still damage the car -- issues beget issues
                # (condition_pct feeds failure_chance) and wear carries past the flag.
                state.condition_pct = max(0.0, state.condition_pct - CONDITION_HIT_FAILURE)

        if is_lap_end and command == "pit":
            extra_penalty += session.track.pit_lane_loss_s
            state.driver_energy = min(PERCENT_MAX, state.driver_energy + DRIVER_ENERGY_RECOVER_PIT)
            state.driver_focus = min(PERCENT_MAX, state.driver_focus + DRIVER_FOCUS_RECOVER_PIT)
            state.driver_stress = max(0.0, state.driver_stress - DRIVER_STRESS_RELIEF_PIT)
            state.event_log.append(f"{state.label} pitted (+{session.track.pit_lane_loss_s:.0f}s).")

        state.total_time += tick_time + extra_penalty
        state.lap_elapsed += tick_time + extra_penalty

        if road_ahead and not state.is_dnf:
            _contest_overtakes(session.track, rng, state, driver, command, pre_tick_time, road_ahead, seg_length)

        if command == "pit" and is_lap_end:
            _apply_lap_wear(state, effective, session.track, "pit", driver_fitness=driver.fitness, seconds=tick_time)
        elif overlaps:
            # Apportion the tick's real seconds across the profiles it spans, so the
            # time-based channels (engine heat, driver fatigue) accrue correctly.
            for profile, overlap in overlaps:
                slice_seconds = tick_time * (overlap / seg_length) if seg_length > 0 else tick_time
                _apply_lap_wear(state, effective, session.track, command, fraction=overlap, profile=profile, driver_fitness=driver.fitness, seconds=slice_seconds)
        else:
            _apply_lap_wear(state, effective, session.track, command, fraction=seg_length, driver_fitness=driver.fitness, seconds=tick_time)

        if is_lap_end and command == "pit":
            # Pit is a one-shot: once the stop is done, resume normal running so the
            # car doesn't keep diving into the pits every lap.
            state.pace_mode = "normal"

        if is_lap_end:
            state.last_lap_time = state.lap_elapsed
            state.lap_elapsed = 0.0
            state.lap += 1
            state.distance += session.track.length_km
            state.event_log.extend(warning_messages(state))
        if is_lap_end or state.is_dnf:
            # Publish at lap end for running cars, and immediately on DNF -- a crashed
            # car is skipped on every later tick, so this is its last chance to speak.
            lap_log.extend(_unpublished_events(state))
        if not state.is_dnf:
            road_ahead.append((pre_tick_time, state, driver, command))

    active = [state for state in session.cars if not state.is_dnf]
    if active:
        _rank(active)  # sorts and assigns positions/gaps in one pass
    for state in active:
        if is_lap_end:
            record_telemetry(session.telemetry[state.label], state)

    session.current_sub_tick = (session.current_sub_tick + 1) % session.ticks_per_lap
    if is_lap_end:
        session.current_lap += 1
    if session.duration_s is not None:
        # Duration race (Regime A lockstep): finish at a lap boundary once the leader passes
        # the time cap. total_laps tracks the completed laps for display/result.
        leader_time = min((state.total_time for state in active), default=0.0)
        time_up = is_lap_end and session.current_lap >= 1 and leader_time >= session.duration_s
        session.is_finished = time_up or len(active) <= 1
        session.total_laps = session.current_lap
    else:
        session.is_finished = session.current_lap >= session.total_laps or len(active) <= 1

    if is_lap_end and not lap_log:
        lap_log.append(f"Lap {session.current_lap} completed.")
    log_lap = session.current_lap if is_lap_end else session.current_lap + 1
    session.race_log.extend((log_lap, msg) for msg in lap_log)
    return RaceTickResult(
        session=session, lap=session.current_lap,
        standings=active, event_log=lap_log, is_lap_end=is_lap_end,
    )


def finish_event(game_state: GameState, session: RaceSession) -> FinishEventResult:
    player = _player_state(session)
    if player.is_dnf or session.event is None or session.track is None:
        prize_money = 0
    else:
        prize_money = _prize_for_position(session.event, player.position)
    team_xp_before = game_state.team_xp
    event_progress_before: dict = {}
    event_progress_after: dict = {}
    award: TeamXpAward | None = None
    total_time_s = None if player.is_dnf else player.total_time
    if session.event is not None:
        event_progress_before = normalize_event_progress(game_state.event_progress.get(session.event.id))
        award = team_xp_award(
            session.event.car_class_limit,
            session.event.event_kind,
            position=player.position,
            is_dnf=player.is_dnf,
            event_progress_before=event_progress_before,
        )
        event_progress_after = updated_event_progress(
            event_progress_before,
            position=player.position,
            is_dnf=player.is_dnf,
            total_time_s=total_time_s,
        )
        game_state.team_xp += award.total_xp
        game_state.event_progress[session.event.id] = event_progress_after
    game_state.money += prize_money
    game_state.week += 1
    maybe_refresh_free_agents(game_state)
    if SALARY_WEEKLY_ENABLED:
        game_state.money -= sum(
            round(driver.salary * SALARY_WEEKLY_FRACTION) for driver in game_state.hired_drivers
        )
    garage_car = _find_garage_car(game_state, player.car_id)
    car_condition_after = None
    if garage_car is not None and session.track is not None:
        damage = PERCENT_MAX - player.condition_pct
        apply_post_race_wear(garage_car, session.track.length_km * session.current_lap, damage)
        car_condition_after = deepcopy(garage_car.condition)
    progression_message = ""
    if not player.is_dnf:
        hired_driver = next((d for d in game_state.hired_drivers if d.id == player.driver_id), None)
        if hired_driver is not None:
            progression_message = _apply_driver_progression(hired_driver)
    return FinishEventResult(
        prize_money=prize_money,
        driver_progression_message=progression_message,
        team_xp_award=award,
        team_xp_before=team_xp_before,
        team_xp_after=game_state.team_xp,
        event_progress_before=event_progress_before,
        event_progress_after=event_progress_after,
        player_position=player.position,
        player_is_dnf=player.is_dnf,
        player_total_time_s=total_time_s,
        car_condition_before=deepcopy(session.player_car_condition_before),
        car_condition_after=car_condition_after,
    )


_PROGRESSION_STATS = ("pace", "consistency", "racecraft", "fitness", "mechanical_sympathy", "wet_skill")


def _apply_driver_progression(driver) -> str:
    xp_before = driver.experience
    driver.experience += DRIVER_XP_PER_RACE
    gains_before = xp_before // DRIVER_XP_PER_STAT_POINT
    gains_after = driver.experience // DRIVER_XP_PER_STAT_POINT
    messages = [f"{driver.name} +{DRIVER_XP_PER_RACE} XP (total: {driver.experience})"]
    # A driver's own potential ceiling caps growth, never above the universal stat cap.
    cap = min(getattr(driver, "potential", DRIVER_STAT_CAP), DRIVER_STAT_CAP)
    for _ in range(gains_after - gains_before):
        eligible = [(getattr(driver, s), s) for s in _PROGRESSION_STATS if getattr(driver, s) < cap]
        if not eligible:
            break
        _, stat = min(eligible)
        setattr(driver, stat, getattr(driver, stat) + 1)
        messages.append(f"{driver.name} +1 {stat.replace('_', ' ')} ({getattr(driver, stat)})")
    return "  ".join(messages)


def _pass_chance(track, attacker, defender, attacker_cmd="normal", defender_cmd="normal") -> float:
    """Per-LAP chance sustained pressure converts into a pass, before slice scaling.

    Wide/easy tracks (low overtake_difficulty) let the quicker car through quickly;
    narrow ones form trains. A racecraft edge (attacker vs defender) tilts the odds, and
    pace tilts it too: leaning on it (push/go_all_out) multiplies the attacker's chance
    while a defender leaning back cuts it -- so a battle is a two-sided pace decision, at
    the cost of the heat/wear/risk those commands carry (and the botch risk, handled by
    the caller)."""
    skill = 1.0 + (attacker.racecraft - defender.racecraft) * OVERTAKE_RACECRAFT_PER_POINT
    pace = (
        COMMAND_MODIFIERS[attacker_cmd][COMMAND_OVERTAKE_INDEX]
        / COMMAND_MODIFIERS[defender_cmd][COMMAND_OVERTAKE_INDEX]
    )
    return max(0.0, OVERTAKE_BASE_CHANCE_PER_LAP * (1.0 - track.overtake_difficulty) * skill * pace)


def _complete_pass(attacker, defender) -> None:
    """A won contest reorders the road: the two cars exchange race clocks.

    The exchange conserves the pair's combined time (a pass moves cars, it does not
    mint or destroy lap time) and drops the defender into the attacker's old spot --
    inside the new leader's dirty air, where it can fight back next tick."""
    delta = defender.total_time - attacker.total_time
    attacker.total_time += delta
    attacker.lap_elapsed += delta
    defender.total_time -= delta
    defender.lap_elapsed -= delta


def _contest_overtakes(track, rng, state, driver, command, pre_tick_time, road_ahead, seg_length: float) -> None:
    """The car behind cannot simply drive through the cars ahead.

    ``road_ahead`` is the already-advanced field this tick as (pre-tick time, state,
    driver, command) tuples; ``pre_tick_time`` is the follower's own clock at tick start
    and ``command`` the follower's pace this tick. Walking up the road from the nearest
    car (largest time), every car this tick
    would put the follower within the follow gap of (or past) must be dealt with: a
    seeded roll against _pass_chance -- tilted by both cars' pace (see _pass_chance),
    scaled by the tick slice so pass rates are resolution-invariant -- completes the pass
    -- a follower still nominally behind
    exchanges clocks with the defender (_complete_pass), so the move always reorders
    the road; a failed move holds the follower in dirty air just off the follow gap
    (a breathing band of [gap, gap + OVERTAKE_GAP_JITTER_S], so trains flutter
    instead of freezing at one number) and ends its progress -- and if that failed move
    was a hot attempt (push/go_all_out) it may be *botched*, costing extra time on top of
    the failed pass. Two exemptions: a car
    swept past with more margin than the
    contest window (it pitted, crashed wide, or is crawling on fumes) is not really
    defending, and a car that was NOT strictly ahead when the tick began (a standing
    start or dead heat) holds no road to defend -- there the field spreads on pace
    alone instead of freezing in processing order."""
    for ahead_pre, ahead_state, ahead_driver, ahead_command in sorted(
        road_ahead, key=lambda entry: entry[1].total_time, reverse=True
    ):
        if ahead_pre >= pre_tick_time:
            continue  # dead heat at tick start: no established position to defend
        held = ahead_state.total_time + OVERTAKE_FOLLOW_GAP_S
        margin = held - state.total_time
        if margin <= 0.0:
            break  # clear of the nearest car ahead, so clear of everyone beyond it
        if margin > OVERTAKE_CONTEST_MAX_S:
            continue  # swept past a crippled car: free, keep driving up the road
        if rng.random() < _pass_chance(track, driver, ahead_driver, command, ahead_command) * seg_length:
            if state.total_time > ahead_state.total_time:
                _complete_pass(state, ahead_state)
                state.event_log.append(f"{state.label} passed {ahead_state.label}.")
            continue  # the move sticks; on to the next car up the road
        # Breathing room: the hold is a band, not a rail. Positive-only, so the gap
        # never dips below the follow gap (and never turns into a backdoor pass) --
        # train gaps flutter in [gap, gap + jitter] instead of freezing at 0.400.
        # Drawn BEFORE the stacking sweep so the sweep guards the final position.
        held += rng.random() * OVERTAKE_GAP_JITTER_S
        # Slot into the train: if the hold would land within the follow gap of another
        # settled car -- on either side of it (a queue has formed) -- stack behind that
        # car instead. One ascending sweep resolves the chain because the held time
        # only ever moves backward.
        for _settled_pre, settled_state, _settled_driver, _settled_command in sorted(
            road_ahead, key=lambda entry: entry[1].total_time
        ):
            settled_time = settled_state.total_time
            if settled_time - OVERTAKE_FOLLOW_GAP_S < held < settled_time + OVERTAKE_FOLLOW_GAP_S:
                held = settled_time + OVERTAKE_FOLLOW_GAP_S
        state.lap_elapsed += held - state.total_time
        state.total_time = held
        # Botched hot pass: a failed move at push/go_all_out can be thrown away, losing
        # time on top of the failed attempt (the pass already didn't stick). Scaled by
        # the tick slice like every contest roll so it is resolution-invariant.
        botch = OVERTAKE_BOTCH_PROB.get(command, 0.0)
        if botch and rng.random() < botch * seg_length:
            state.total_time += OVERTAKE_BOTCH_TIME
            state.lap_elapsed += OVERTAKE_BOTCH_TIME
            state.event_log.append(f"{state.label} ran wide attacking {ahead_state.label} (+{OVERTAKE_BOTCH_TIME:.0f}s).")
        break


def _unpublished_events(state, limit: int = 3) -> list[str]:
    """Event-log entries not yet surfaced in the session race log (at most ``limit``,
    keeping the newest). Advances the car's published watermark so nothing repeats."""
    new_events = state.event_log[state.event_log_published:]
    state.event_log_published = len(state.event_log)
    return new_events[-limit:]


def _ai_command(state, player_time: float) -> str:
    """Rule-based rival pit boss: survive first, then race.

    Pit when tyres or fuel won't last, lift to the matching cooling command when a
    temperature is past its overheat threshold, push when locked in a close battle,
    otherwise hold pace. Mirrors the tools the player has, so long races no longer
    systematically cook the AI."""
    if state.fuel_pct <= AI_PIT_FUEL_PCT or state.tire_pct <= AI_PIT_TIRE_PCT:
        return "pit"
    tires_hot = state.tire_temp >= TIRE_OVERHEAT_C
    engine_hot = state.engine_temp >= ENGINE_OVERHEAT_C
    if tires_hot and engine_hot:
        return "cool_down"
    if tires_hot:
        return "save_tyres"
    if engine_hot:
        return "save_fuel"
    if abs(state.total_time - player_time) <= RIVAL_REACTIVE_GAP_S:
        return "push"
    return AI_COMMAND


def _dnf_chance(driver) -> float:
    """Per-tick crash-out probability when going all out, eased by a composed driver.

    Consistency and mechanical sympathy reduce it; the floor leaves go-all-out a real
    gamble even for aces, and is the hook for future explicit driver skill levels.
    """
    skill = (driver.consistency + driver.mechanical_sympathy) / 2
    relief = max(DNF_DRIVER_RELIEF_FLOOR, 1.0 - skill * DNF_DRIVER_RELIEF)
    return MISTAKE_DNF_PROB * relief


def _player_state(session: RaceSession):
    return next(state for state in session.cars if state.is_player)


def _active_standings(session: RaceSession):
    active = [state for state in session.cars if not state.is_dnf]
    active.sort(key=lambda state: state.total_time)
    return active
