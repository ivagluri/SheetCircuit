from __future__ import annotations

import random
from dataclasses import dataclass, field

from constants import FREE_AGENT_POOL_SIZE, STARTING_MONEY, STARTING_WEEK
from game.driver_gen import generate_market_pool
from game.loader import load_cars, load_drivers
from game.models import Car, Driver


@dataclass
class GameState:
    money: int = STARTING_MONEY
    week: int = STARTING_WEEK
    team_xp: int = 0
    garage: list[Car] = field(default_factory=list)
    hired_drivers: list[Driver] = field(default_factory=list)
    event_progress: dict[str, dict] = field(default_factory=dict)
    # Persisted rotating free-agent market (see game/market.py). market_seed makes each
    # career's market unique; free_agents_week is the week the pool last churned.
    free_agents: list[Driver] = field(default_factory=list)
    free_agents_week: int = 0
    market_seed: int = 0


def new_game() -> GameState:
    return GameState()


def _starter_car(cars: list[Car]) -> Car:
    """Cheapest entry-class car, chosen by criteria rather than a hardcoded id, so the
    career still starts even if the seed catalog changes. Prefers the lowest class
    present, then the cheapest car within it."""
    if not cars:
        raise ValueError("No cars available to start a career")
    from game.effective_stats import derived_class
    class_order = {"E": 0, "D": 1, "C": 2, "B": 3, "A": 4, "S": 5}
    return min(cars, key=lambda c: (class_order.get(derived_class(c), 99), c.value))


def _starter_driver(drivers: list[Driver]) -> Driver:
    """A rookie to start with: the cheapest-salary driver available."""
    if not drivers:
        raise ValueError("No drivers available to start a career")
    return min(drivers, key=lambda d: d.salary)


def new_career() -> GameState:
    drivers = load_drivers()
    starter = _starter_driver(drivers)
    state = GameState(
        garage=[_starter_car(load_cars())],
        hired_drivers=[starter],
        market_seed=random.randrange(1_000_000_000),
    )
    # The hand-authored seed drivers (minus the one you start with) remain in the world as
    # flavour, seeded into the opening market; procedural agents fill the rest to size.
    others = [d for d in drivers if d.id != starter.id]
    rng = random.Random(state.market_seed * 1_000_003 + state.week)
    fill = max(0, FREE_AGENT_POOL_SIZE - len(others))
    state.free_agents = others + generate_market_pool(rng, fill, id_prefix=f"fa_w{state.week}")
    state.free_agents_week = state.week
    return state
