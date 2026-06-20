from __future__ import annotations

import random
from copy import deepcopy

from constants import (
    CLASS_RIVAL_SKILL,
    RIVAL_SKILL_SIGMA,
    RIVAL_TIER_RATING_BAND,
)
from game.effective_stats import class_rating
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
    """Build a seeded rival field from honest cars and real driver stats."""
    _ = player_driver, track  # Kept in the API because callers already have this context.
    rng = random.Random(seed)

    eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id and _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if _is_eligible(car, event, parts)]
    if not eligible:
        eligible = [deepcopy(car) for car in cars.values() if car.identity.id != player_car_id] or [deepcopy(next(iter(cars.values())))]

    best_rating = max(class_rating(car, parts) for car in eligible)
    tier_pool = [
        car for car in eligible
        if best_rating - class_rating(car, parts) <= RIVAL_TIER_RATING_BAND
    ] or eligible
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
    if "max_class_rating" in restrictions and class_rating(car, parts) > restrictions["max_class_rating"]:
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
