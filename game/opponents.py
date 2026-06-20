from __future__ import annotations

import random
from copy import deepcopy

from constants import (
    CLASS_RIVAL_SKILL,
    EVENT_PACE_FLOOR_PERCENTILE,
    RIVAL_MATCH_LAP_BAND_FRAC,
    RIVAL_MATCH_EXPANSION_FACTOR,
    RIVAL_MATCH_MIN_UNIQUE,
    RIVAL_MATCH_POOL_FACTOR,
    RIVAL_SKILL_SIGMA,
)
from game.effective_stats import compute_effective_stats, derived_rating
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
) -> tuple[dict[str, Car], dict[str, Driver], list[tuple[str, str]]]:
    """Build a seeded rival field from honest cars and real driver stats.

    The field is anchored to the player's derived event pace, not to the fastest
    eligible car. That keeps very low-end cars competitive with nearby machinery
    while still adapting when the catalog grows or a wildly faster/slower car is added.
    """
    _ = player_driver  # Skill still affects the race, just not car matchmaking.
    rng = random.Random(seed)

    eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id and _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id] or [deepcopy(next(iter(cars.values())))]

    player_car = cars.get(player_car_id)
    tier_pool = _event_peer_pool(player_car, eligible, parts, track, event) if player_car else eligible
    rival_skill = _effective_rival_skill(event)

    car_roster: dict[str, Car] = {}
    driver_roster: dict[str, Driver] = {}
    entries: list[tuple[str, str]] = []
    for index in range(event.opponent_count):
        source_car = deepcopy(rng.choice(tier_pool))
        car_id = f"opponent_{index + 1}_{source_car.identity.id}"
        source_car.identity.id = car_id
        car_roster[car_id] = source_car
        driver = _opponent_driver(index, rival_skill, rng)
        driver_roster[driver.id] = driver
        entries.append((car_id, driver.id))
    return car_roster, driver_roster, entries


def opponent_entry_labels(entries: list[tuple[str, str]], car_roster: dict[str, Car]) -> list[str]:
    """Human-readable opponent labels, numbered only when a model is reused."""
    names = [car_roster[car_id].identity.name for car_id, _driver_id in entries]
    totals = {name: names.count(name) for name in set(names)}
    seen: dict[str, int] = {}
    labels: list[str] = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        labels.append(f"{name} #{seen[name]}" if totals[name] > 1 else name)
    return labels


def _event_peer_pool(
    player_car: Car,
    eligible: list[Car],
    parts: list,
    track: Track,
    event: Event,
) -> list[Car]:
    if not eligible:
        return eligible

    player_lap = _natural_lap(player_car, parts, track)
    profiles = [
        (car, _natural_lap(car, parts, track))
        for car in eligible
    ]
    floor_lap = _event_floor_lap([lap for _car, lap in profiles], event.car_class_limit)
    anchor_lap = min(player_lap, floor_lap)
    profiles.sort(key=lambda profile: (abs(profile[1] - anchor_lap), derived_rating(profile[0], parts), profile[0].identity.id))

    band = anchor_lap * RIVAL_MATCH_LAP_BAND_FRAC
    target_unique = min(
        len(profiles),
        max(RIVAL_MATCH_MIN_UNIQUE, min(event.opponent_count, round(len(profiles) ** 0.5))),
    )
    max_pool = min(len(profiles), max(target_unique, round(event.opponent_count * RIVAL_MATCH_POOL_FACTOR)))
    pool = [car for car, lap in profiles if abs(lap - anchor_lap) <= band]
    if not pool:
        expanded = [
            car for car, lap in profiles
            if abs(lap - anchor_lap) <= band * RIVAL_MATCH_EXPANSION_FACTOR
        ]
        pool = expanded or [profiles[0][0]]
    elif len(pool) > max_pool:
        pool = pool[:max_pool]
    return pool


def _event_floor_lap(laps: list[float], class_limit: str) -> float:
    if not laps:
        return float("inf")
    ordered = sorted(laps)
    percentile = EVENT_PACE_FLOOR_PERCENTILE.get(class_limit, EVENT_PACE_FLOOR_PERCENTILE["E"])
    percentile = _clamp(percentile, 0.0, 1.0)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def _natural_lap(car: Car, parts: list, track: Track) -> float:
    from game.simulation import calculate_lap_time

    return calculate_lap_time(compute_effective_stats(car, parts), track)


def _effective_rival_skill(event: Event) -> int:
    default = CLASS_RIVAL_SKILL.get(event.car_class_limit, CLASS_RIVAL_SKILL["E"])
    skill = default if event.rival_skill is None else event.rival_skill
    return int(round(_clamp(skill, 0, 100)))


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
    if "max_class_rating" in restrictions and derived_rating(car, parts) > restrictions["max_class_rating"]:
        return f"max_class_rating {restrictions['max_class_rating']}"
    return ""


def _skill_roll(rng: random.Random, skill: int, sigma: float = RIVAL_SKILL_SIGMA) -> int:
    return int(round(_clamp(rng.gauss(skill, sigma), 5, 98)))


def _opponent_driver(index: int, skill: int, rng: random.Random) -> Driver:
    pace = _skill_roll(rng, skill)
    consistency = int(round(_clamp(rng.gauss(skill + 6, RIVAL_SKILL_SIGMA * 0.7), 20, 98)))
    racecraft = _skill_roll(rng, skill)
    mechanical_sympathy = int(round(_clamp(rng.gauss(skill + 2, RIVAL_SKILL_SIGMA), 20, 95)))
    wet_skill = int(round(_clamp(rng.gauss(skill - 2, RIVAL_SKILL_SIGMA), 15, 95)))
    fitness = int(round(_clamp(50 + skill * 0.35 + rng.uniform(-6, 6), 45, 90)))
    return Driver(
        id=f"opponent_driver_{index + 1}",
        name=f"Rival {index + 1}",
        pace=pace,
        consistency=consistency,
        racecraft=racecraft,
        feedback=35,
        fitness=fitness,
        aggression=int(round(_clamp(rng.gauss(42 + skill * 0.18, 10), 20, 85))),
        mechanical_sympathy=mechanical_sympathy,
        wet_skill=wet_skill,
        salary=0,
        experience=0,
    )
