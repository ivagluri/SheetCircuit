from __future__ import annotations

import random

from constants import FREE_AGENT_CHURN, FREE_AGENT_POOL_SIZE, FREE_AGENT_REFRESH_WEEKS
from game.driver_gen import generate_market_pool
from game.loader import load_cars
from game.models import Car, Driver


def list_market_cars() -> list[Car]:
    return load_cars()


def _market_rng(game_state) -> random.Random:
    # Deterministic per (career, week) so refreshes replay identically after a load.
    return random.Random(game_state.market_seed * 1_000_003 + game_state.week)


def refresh_free_agents(game_state):
    """Churn the free-agent pool: drop up to FREE_AGENT_CHURN of the longest-lingering
    (oldest) agents, then refill to FREE_AGENT_POOL_SIZE with freshly generated drivers.
    Agents you passed over may still be there next visit, but not forever."""
    rng = _market_rng(game_state)
    kept = game_state.free_agents[FREE_AGENT_CHURN:]
    needed = max(0, FREE_AGENT_POOL_SIZE - len(kept))
    game_state.free_agents = kept + generate_market_pool(rng, needed, id_prefix=f"fa_w{game_state.week}")
    game_state.free_agents_week = game_state.week
    return game_state


def maybe_refresh_free_agents(game_state):
    """Refresh when the pool has never been populated or a full refresh interval has
    elapsed. Idempotent within a week (the interval guard makes repeat calls no-ops)."""
    if not game_state.free_agents:
        return refresh_free_agents(game_state)
    if game_state.week - game_state.free_agents_week >= FREE_AGENT_REFRESH_WEEKS:
        return refresh_free_agents(game_state)
    return game_state


def list_free_agents(game_state) -> list[Driver]:
    maybe_refresh_free_agents(game_state)
    return game_state.free_agents
