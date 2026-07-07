"""Procedural driver generation.

The single source of generated `Driver`s, shared by the AI rival field
(game/opponents.py) and the hireable free-agent market (game/market.py). Both routes
roll the same seeded gaussian-around-a-skill-anchor stat core; they differ only in how
the anchor and biases are chosen (a raw event skill for rivals, an intrinsic archetype
for the market) and in whether a real name/potential/salary are wanted.
"""
from __future__ import annotations

import random

from constants import (
    DRIVER_ARCHETYPES,
    RIVAL_SKILL_SIGMA,
    SALARY_ABILITY_EXP,
    SALARY_ABILITY_REF,
    SALARY_BASE,
    SALARY_POTENTIAL_COEF,
)
from constants import DRIVER_STAT_CAP
from game.effective_stats import clamp
from game.models import Driver

# Stats that grow with XP (mirror race_session._PROGRESSION_STATS); used to compute a
# driver's current-ability mean/peak for potential and salary. feedback/aggression are
# fixed personality and excluded.
PROGRESSION_STATS = ("pace", "consistency", "racecraft", "fitness", "mechanical_sympathy", "wet_skill")

# Broad, deliberately multicultural name pools with no nationality modelling -- names are
# combined at random. Keep these long enough that repeats are rare in a small market.
FIRST_NAMES = [
    "Aiden", "Mateo", "Kenji", "Luca", "Omar", "Nikolai", "Diego", "Rohan", "Elias",
    "Marta", "Yuki", "Priya", "Ingrid", "Camila", "Nadia", "Sofia", "Amara", "Lena",
    "Hakan", "Tariq", "Bjorn", "Cesar", "Dmitri", "Felix", "Hugo", "Ivan", "Jonas",
    "Keanu", "Milos", "Pablo", "Rafael", "Sami", "Theo", "Viktor", "Xavier", "Zane",
    "Aria", "Bianca", "Chiara", "Dahlia", "Esme", "Freya", "Giulia", "Hana", "Iris",
]
LAST_NAMES = [
    "Novak", "Rashid", "Costa", "Bellamy", "Tanaka", "Okafor", "Vidal", "Sorensen",
    "Moreau", "Kovac", "Rossi", "Fischer", "Nakamura", "Delgado", "Petrov", "Haas",
    "Bauer", "Ferrari", "Lindqvist", "Marchetti", "Nguyen", "Oliveira", "Pryce",
    "Quinn", "Reyes", "Salazar", "Toure", "Ueda", "Varga", "Watanabe", "Yildiz",
    "Ziegler", "Ashworth", "Beaumont", "Cardoso", "Duval", "Engel", "Falco", "Grimaldi",
]


def _skill_roll(rng: random.Random, skill: float, sigma: float = RIVAL_SKILL_SIGMA) -> int:
    """A single 5-98 stat rolled gaussian around a skill anchor. Shared by rivals and
    the market so both fields have the same statistical character."""
    return int(round(clamp(rng.gauss(skill, sigma), 5, 98)))


def random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _roll_stats(rng: random.Random, skill: float, bias: dict[str, int]) -> dict[str, int]:
    """The stat core, lifted verbatim from the historical opponents._opponent_driver rolls
    plus an optional per-stat ``bias`` (an additive shift to the anchor)."""
    def anchor(stat: str, base: float) -> float:
        return base + bias.get(stat, 0)

    return {
        "pace": _skill_roll(rng, anchor("pace", skill)),
        "consistency": int(round(clamp(rng.gauss(anchor("consistency", skill + 6), RIVAL_SKILL_SIGMA * 0.7), 20, 98))),
        "racecraft": _skill_roll(rng, anchor("racecraft", skill)),
        "mechanical_sympathy": int(round(clamp(rng.gauss(anchor("mechanical_sympathy", skill + 2), RIVAL_SKILL_SIGMA), 20, 95))),
        "wet_skill": int(round(clamp(rng.gauss(anchor("wet_skill", skill - 2), RIVAL_SKILL_SIGMA), 15, 98))),
        "fitness": int(round(clamp(50 + skill * 0.35 + bias.get("fitness", 0) + rng.uniform(-6, 6), 45, 90))),
        "aggression": int(round(clamp(rng.gauss(anchor("aggression", 42 + skill * 0.18), 10), 20, 95))),
        # feedback is now a real roll (rivals historically hard-coded 35); a modest,
        # skill-independent personality trait, biasable per archetype.
        "feedback": int(round(clamp(rng.gauss(anchor("feedback", 48), 12), 15, 95))),
    }


def _mean_ability(stats: dict[str, int]) -> float:
    return sum(stats[s] for s in PROGRESSION_STATS) / len(PROGRESSION_STATS)


def compute_potential(stats: dict[str, int], headroom: int) -> int:
    """A single 0-99 ceiling: the driver's current peak progressable stat plus headroom.
    Always >= the current peak (a ceiling below current ability is meaningless)."""
    peak = max(stats[s] for s in PROGRESSION_STATS)
    return int(clamp(round(peak + headroom), peak, DRIVER_STAT_CAP))


def compute_salary(stats: dict[str, int], potential: int) -> int:
    """One-off hire fee. Super-linear in current ability, with a potential premium.
    Monotonic non-decreasing in both mean ability and potential."""
    mean = _mean_ability(stats)
    ability = (mean / SALARY_ABILITY_REF) ** SALARY_ABILITY_EXP
    premium = 1.0 + SALARY_POTENTIAL_COEF * (potential / DRIVER_STAT_CAP)
    return int(round(SALARY_BASE * ability * premium))


def generate_driver(
    rng: random.Random,
    *,
    skill: float,
    bias: dict[str, int] | None = None,
    headroom: int = 0,
    driver_id: str,
    name: str | None = None,
    with_economics: bool = True,
) -> Driver:
    """Roll a complete Driver around ``skill``.

    ``with_economics`` computes potential + salary (the hireable-market path); rivals pass
    it False and keep the default potential/salary (they never progress or get hired).
    """
    bias = bias or {}
    stats = _roll_stats(rng, skill, bias)
    potential = compute_potential(stats, headroom) if with_economics else DRIVER_STAT_CAP
    salary = compute_salary(stats, potential) if with_economics else 0
    return Driver(
        id=driver_id,
        name=name if name is not None else random_name(rng),
        pace=stats["pace"],
        consistency=stats["consistency"],
        racecraft=stats["racecraft"],
        feedback=stats["feedback"],
        fitness=stats["fitness"],
        aggression=stats["aggression"],
        mechanical_sympathy=stats["mechanical_sympathy"],
        wet_skill=stats["wet_skill"],
        salary=salary,
        experience=0,
        potential=potential,
    )


def generate_from_archetype(rng: random.Random, archetype: tuple, driver_id: str) -> Driver:
    """Generate a hireable driver from a DRIVER_ARCHETYPES entry (name, help, spec)."""
    _name, _help, spec = archetype
    lo, hi = spec["skill"]
    skill = rng.uniform(lo, hi)
    head_lo, head_hi = spec["headroom"]
    headroom = int(round(rng.uniform(head_lo, head_hi)))
    return generate_driver(
        rng,
        skill=skill,
        bias=spec.get("bias", {}),
        headroom=headroom,
        driver_id=driver_id,
        with_economics=True,
    )


def generate_market_pool(rng: random.Random, count: int, id_prefix: str = "free_agent") -> list[Driver]:
    """A fresh batch of ``count`` hireable free agents spread across the archetypes."""
    pool: list[Driver] = []
    for i in range(count):
        archetype = rng.choice(DRIVER_ARCHETYPES)
        # A stable-ish unique id; the market reseeds per refresh so ids are namespaced by
        # a running counter provided by the caller via id_prefix.
        pool.append(generate_from_archetype(rng, archetype, f"{id_prefix}_{i}"))
    return pool
