from __future__ import annotations

import random
from copy import deepcopy

from constants import (
    CLASS_RIVAL_PACE_OFFSET,
    DRIVER_PACE_SCALE,
    PERF_SCALE,
    RIVAL_BAND_HALF_S,
    RIVAL_PACE_MAX,
    RIVAL_PACE_MIN,
    RIVAL_PERF_SCALAR_MAX,
    RIVAL_PERF_SCALAR_MIN,
    RIVAL_PLAYER_EDGE_S,
    RIVAL_REF_PACE,
    RIVAL_SPREAD_FRAC,
    RIVAL_TARGET_JITTER_S,
)
from game.effective_stats import class_rating, compute_effective_stats
from game.models import Car, Driver, Event, Track

CLASS_ORDER = {"E": 0, "D": 1, "C": 2, "B": 3, "A": 4, "S": 5}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class EventEntryError(ValueError):
    """Raised when a car cannot enter an event."""


def validate_event_entry(car: Car, event: Event, parts: list | None = None) -> None:
    if not _class_allowed(car, event.car_class_limit):
        raise EventEntryError(f"{car.identity.name} exceeds {event.car_class_limit} class limit")
    failed_rule = _failed_restriction(car, event, parts or [])
    if failed_rule:
        raise EventEntryError(f"{car.identity.name} fails event restriction: {failed_rule}")


def build_opponent_grid(
    event: Event,
    player_car_id: str,
    player_driver: Driver,
    cars: dict[str, Car],
    parts: list,
    track: Track,
    seed: int,
) -> tuple[dict[str, Car], dict[str, Driver], list[tuple[str, str, float]]]:
    """Build a competitive, spread-out rival field.

    Hybrid difficulty: the field centres on the player's own pace, clamped into
    the event's absolute class band so easier events can be outgrown. Rivals are
    then spread into a ladder and each target lap is realised through a real base
    car plus a solved driver pace and (fallback) car-performance scalar. Nothing
    here is tied to a specific car; richer catalogs simply yield more variety.
    """
    from game.simulation import _initial_state, _track_composite, calculate_lap_time

    rng = random.Random(seed)

    eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id and _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id] or [deepcopy(next(iter(cars.values())))]

    def natural_lap(car: Car, pace: int) -> float:
        effective = compute_effective_stats(car, parts, command="normal")
        state = _initial_state(car.identity.id, "ref", "ref", False)
        return calculate_lap_time(effective, track, _ref_driver(pace), state, None, command="normal")

    def perf_bonus(car: Car) -> float:
        effective = compute_effective_stats(car, parts, command="normal")
        return PERF_SCALE * _track_composite(effective, track)

    # Player anchor: their honest normal-pace lap on this track.
    player_car = cars[player_car_id]
    player_effective = compute_effective_stats(player_car, parts, command="normal")
    player_state = _initial_state(player_car_id, player_driver.id, "ref", False)
    player_ref = calculate_lap_time(player_effective, track, player_driver, player_state, None, command="normal")

    # Event's absolute pace band (class-based), then clamp the player into it.
    class_offset = CLASS_RIVAL_PACE_OFFSET.get(event.car_class_limit, CLASS_RIVAL_PACE_OFFSET["E"])
    event_center = track.base_lap_time + class_offset
    event_fast = event_center - RIVAL_BAND_HALF_S
    event_slow = event_center + RIVAL_BAND_HALF_S
    # Cede the player a small per-lap pace edge so skill/strategy can win events.
    center = _clamp(player_ref, event_fast, event_slow) + RIVAL_PLAYER_EDGE_S

    # Spread the rivals into a ladder of target lap times around the centre.
    spread = track.base_lap_time * RIVAL_SPREAD_FRAC
    count = event.opponent_count
    targets: list[float] = []
    for i in range(count):
        frac = i / (count - 1) if count > 1 else 0.5
        target = (center - spread) + frac * (2 * spread)
        target += rng.uniform(-RIVAL_TARGET_JITTER_S, RIVAL_TARGET_JITTER_S)
        targets.append(target)
    rng.shuffle(targets)  # decouple rival number from strength

    # Precompute each eligible car's natural lap and performance bonus.
    profiles = [(car, natural_lap(car, RIVAL_REF_PACE), perf_bonus(car)) for car in eligible]

    car_roster: dict[str, Car] = {}
    driver_roster: dict[str, Driver] = {}
    entries: list[tuple[str, str, float]] = []
    for index, target in enumerate(targets):
        base_car, natural, bonus = min(profiles, key=lambda p: abs(p[1] - target))
        source_car = deepcopy(base_car)

        # Solve driver pace first; cover any residual with a car-performance scalar.
        required_pace = RIVAL_REF_PACE + (natural - target) / DRIVER_PACE_SCALE
        pace = int(round(_clamp(required_pace, RIVAL_PACE_MIN, RIVAL_PACE_MAX)))
        lap_after_pace = natural - (pace - RIVAL_REF_PACE) * DRIVER_PACE_SCALE
        residual = lap_after_pace - target
        scalar = 1.0
        if bonus > 1e-6:
            scalar = _clamp(1.0 + residual / bonus, RIVAL_PERF_SCALAR_MIN, RIVAL_PERF_SCALAR_MAX)

        car_id = f"opponent_{index + 1}_{source_car.identity.id}"
        source_car.identity.id = car_id
        car_roster[car_id] = source_car
        driver = _opponent_driver(index, pace)
        driver_roster[driver.id] = driver
        entries.append((car_id, driver.id, scalar))
    return car_roster, driver_roster, entries


def _is_eligible(car: Car, event: Event, parts: list) -> bool:
    return _class_allowed(car, event.car_class_limit) and _failed_restriction(car, event, parts) == ""


def _class_allowed(car: Car, class_limit: str) -> bool:
    car_rank = CLASS_ORDER.get(car.identity.car_class, 99)
    limit_rank = CLASS_ORDER.get(class_limit, 99)
    return car_rank <= limit_rank


def _failed_restriction(car: Car, event: Event, parts: list) -> str:
    restrictions = event.restrictions or {}
    if "max_power_hp" in restrictions and car.powertrain.power_hp > restrictions["max_power_hp"]:
        return f"max_power_hp {restrictions['max_power_hp']}"
    if "max_weight_kg" in restrictions and car.chassis.weight_kg > restrictions["max_weight_kg"]:
        return f"max_weight_kg {restrictions['max_weight_kg']}"
    if "max_overall_condition" in restrictions and car.condition.overall_condition > restrictions["max_overall_condition"]:
        return f"max_overall_condition {restrictions['max_overall_condition']}"
    if "allowed_tires" in restrictions and car.tires.tire_compound not in restrictions["allowed_tires"]:
        allowed = ", ".join(restrictions["allowed_tires"])
        return f"allowed_tires {allowed}"
    if "max_class_rating" in restrictions and class_rating(car, parts) > restrictions["max_class_rating"]:
        return f"max_class_rating {restrictions['max_class_rating']}"
    return ""


def _ref_driver(pace: int) -> Driver:
    """Minimal driver used only to measure a car's natural lap time."""
    return Driver(
        id="ref",
        name="ref",
        pace=pace,
        consistency=60,
        racecraft=50,
        feedback=40,
        fitness=60,
        aggression=40,
        mechanical_sympathy=55,
        wet_skill=40,
        salary=0,
        experience=0,
    )


def _opponent_driver(index: int, pace: int) -> Driver:
    pace = int(_clamp(pace, RIVAL_PACE_MIN, RIVAL_PACE_MAX))
    return Driver(
        id=f"opponent_driver_{index + 1}",
        name=f"Rival {index + 1}",
        pace=pace,
        consistency=int(_clamp(pace + 6, 30, 95)),
        racecraft=pace,
        feedback=35,
        fitness=58,
        aggression=int(_clamp(40 + (pace - RIVAL_REF_PACE) * 0.4, 25, 85)),
        mechanical_sympathy=50,
        wet_skill=40,
        salary=0,
        experience=0,
    )
