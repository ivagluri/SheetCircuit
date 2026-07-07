from __future__ import annotations

import random
import unittest

from constants import (
    DRIVER_ARCHETYPES,
    DRIVER_STAT_CAP,
    FREE_AGENT_CHURN,
    FREE_AGENT_POOL_SIZE,
    FREE_AGENT_REFRESH_WEEKS,
)
from game.driver_gen import (
    PROGRESSION_STATS,
    compute_salary,
    generate_driver,
    generate_from_archetype,
    generate_market_pool,
)
from game.economy import EconomyError, hire_driver
from game.game_state import new_career
from game.market import list_free_agents, maybe_refresh_free_agents, refresh_free_agents
from game.models import Driver
from game.race_session import _apply_driver_progression
from game.save_load import game_state_from_dict, game_state_to_dict


def _peak(driver: Driver) -> int:
    return max(getattr(driver, s) for s in PROGRESSION_STATS)


class GeneratorTests(unittest.TestCase):
    def test_generation_is_deterministic_for_a_seed(self) -> None:
        a = generate_from_archetype(random.Random(99), DRIVER_ARCHETYPES[0], "x")
        b = generate_from_archetype(random.Random(99), DRIVER_ARCHETYPES[0], "x")
        self.assertEqual(a, b)

    def test_generated_driver_has_real_name_and_valid_stats(self) -> None:
        d = generate_from_archetype(random.Random(3), DRIVER_ARCHETYPES[2], "fa")
        self.assertIn(" ", d.name)  # first + last
        self.assertNotEqual(d.name, d.id)
        for stat in PROGRESSION_STATS + ("feedback", "aggression"):
            self.assertGreaterEqual(getattr(d, stat), 0)
            self.assertLessEqual(getattr(d, stat), DRIVER_STAT_CAP)

    def test_potential_is_never_below_current_peak_or_above_cap(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            arch = rng.choice(DRIVER_ARCHETYPES)
            d = generate_from_archetype(rng, arch, "fa")
            self.assertGreaterEqual(d.potential, _peak(d))
            self.assertLessEqual(d.potential, DRIVER_STAT_CAP)

    def test_rival_path_skips_economics(self) -> None:
        d = generate_driver(random.Random(1), skill=60, driver_id="opponent_driver_1", with_economics=False)
        self.assertEqual(d.salary, 0)
        self.assertEqual(d.potential, DRIVER_STAT_CAP)
        self.assertNotEqual(d.name, "Rival 1")

    def test_salary_is_monotonic_in_ability_and_potential(self) -> None:
        base = {s: 50 for s in PROGRESSION_STATS}
        low_ability = compute_salary(base, potential=70)
        high_ability = compute_salary({s: 70 for s in PROGRESSION_STATS}, potential=70)
        self.assertGreater(high_ability, low_ability)

        low_pot = compute_salary(base, potential=60)
        high_pot = compute_salary(base, potential=90)
        self.assertGreater(high_pot, low_pot)

    def test_market_pool_ids_are_unique_within_a_batch(self) -> None:
        pool = generate_market_pool(random.Random(5), FREE_AGENT_POOL_SIZE, id_prefix="fa_w1")
        self.assertEqual(len(pool), FREE_AGENT_POOL_SIZE)
        self.assertEqual(len({d.id for d in pool}), FREE_AGENT_POOL_SIZE)


class PotentialClampTests(unittest.TestCase):
    def _driver(self, potential: int, start: int = 40) -> Driver:
        return Driver(
            id="t", name="Test", pace=start, consistency=start, racecraft=start,
            feedback=30, fitness=start, aggression=30, mechanical_sympathy=start,
            wet_skill=start, salary=0, experience=0, potential=potential,
        )

    def test_progression_never_exceeds_potential(self) -> None:
        d = self._driver(potential=70)
        for _ in range(2000):  # far more XP than needed to hit the ceiling
            _apply_driver_progression(d)
        for stat in PROGRESSION_STATS:
            self.assertLessEqual(getattr(d, stat), 70)
        self.assertEqual(_peak(d), 70)  # actually reaches the ceiling
        # fixed personality is untouched by the cap logic
        self.assertEqual(d.feedback, 30)
        self.assertEqual(d.aggression, 30)

    def test_default_potential_caps_at_stat_cap(self) -> None:
        d = self._driver(potential=DRIVER_STAT_CAP, start=95)
        for _ in range(3000):
            _apply_driver_progression(d)
        self.assertEqual(d.pace, DRIVER_STAT_CAP)
        self.assertEqual(d.wet_skill, DRIVER_STAT_CAP)


class MarketTests(unittest.TestCase):
    def test_new_career_seeds_a_full_pool(self) -> None:
        state = new_career()
        self.assertEqual(len(state.free_agents), FREE_AGENT_POOL_SIZE)
        self.assertEqual(state.free_agents_week, state.week)
        # every generated agent carries a real potential and hire price
        for d in state.free_agents:
            self.assertGreaterEqual(d.potential, 0)

    def test_hire_removes_from_pool_and_charges_salary(self) -> None:
        state = new_career()
        target = min(state.free_agents, key=lambda d: d.salary)
        money_before = state.money
        n_before = len(state.free_agents)

        hire_driver(state, target.id)

        self.assertEqual(state.money, money_before - target.salary)
        self.assertTrue(any(d.id == target.id for d in state.hired_drivers))
        self.assertFalse(any(d.id == target.id for d in state.free_agents))
        self.assertEqual(len(state.free_agents), n_before - 1)

    def test_hiring_unknown_driver_raises(self) -> None:
        state = new_career()
        with self.assertRaises(EconomyError):
            hire_driver(state, "does_not_exist")

    def test_refresh_churns_no_more_than_churn_limit(self) -> None:
        state = new_career()
        before_ids = {d.id for d in state.free_agents}
        state.week += FREE_AGENT_REFRESH_WEEKS
        maybe_refresh_free_agents(state)
        self.assertEqual(len(state.free_agents), FREE_AGENT_POOL_SIZE)
        after_ids = {d.id for d in state.free_agents}
        dropped = before_ids - after_ids
        self.assertLessEqual(len(dropped), FREE_AGENT_CHURN)

    def test_refresh_is_a_noop_within_the_interval(self) -> None:
        state = new_career()
        ids_before = [d.id for d in state.free_agents]
        state.week += 1  # below the refresh interval
        maybe_refresh_free_agents(state)
        self.assertEqual([d.id for d in state.free_agents], ids_before)

    def test_refresh_is_deterministic_per_week(self) -> None:
        state = new_career()
        state.week += FREE_AGENT_REFRESH_WEEKS
        clone = game_state_from_dict(game_state_to_dict(state))
        refresh_free_agents(state)
        refresh_free_agents(clone)
        self.assertEqual([d.id for d in state.free_agents], [d.id for d in clone.free_agents])
        self.assertEqual(
            [d.name for d in state.free_agents], [d.name for d in clone.free_agents]
        )


class RaceWithGeneratedDriverTests(unittest.TestCase):
    """Regression: a hired procedurally-generated driver is not in the seed catalog, so
    the race entry points must resolve the player driver from the hired roster."""

    def _enterable_event(self, state, car_id, driver_id):
        from game.loader import load_events
        from game.opponents import EventEntryError
        from game.race_session import enter_event
        from game.simulation import SimulationError

        for event in load_events():
            try:
                enter_event(state, event.id, car_id, driver_id, seed=1)
                return event.id
            except (SimulationError, EventEntryError):
                continue
        self.fail("no enterable event for the starter car at team level 1")

    def test_enter_event_resolves_a_hired_generated_driver(self) -> None:
        state = new_career()
        agent = state.free_agents[-1]  # a generated free agent
        self.assertTrue(agent.id.startswith("fa_"))
        hire_driver(state, agent.id)
        car_id = state.garage[0].identity.id
        # Should not raise "Unknown driver: <generated id>".
        event_id = self._enterable_event(state, car_id, agent.id)
        self.assertIsInstance(event_id, str)

    def test_simulate_race_resolves_a_hired_generated_driver(self) -> None:
        from game.loader import load_events
        from game.opponents import EventEntryError
        from game.simulation import SimulationError, simulate_race

        state = new_career()
        agent = state.free_agents[-1]
        hire_driver(state, agent.id)
        car_id = state.garage[0].identity.id
        for event in load_events():
            try:
                result = simulate_race(state, event.id, car_id, agent.id, seed=1)
            except (SimulationError, EventEntryError):
                continue
            self.assertIsNotNone(result)
            return
        self.fail("no enterable event for the starter car at team level 1")


class SaveRoundTripTests(unittest.TestCase):
    def test_free_agents_and_potential_survive_round_trip(self) -> None:
        state = new_career()
        hire_driver(state, min(state.free_agents, key=lambda d: d.salary).id)
        restored = game_state_from_dict(game_state_to_dict(state))
        self.assertEqual([d.id for d in restored.free_agents], [d.id for d in state.free_agents])
        self.assertEqual(restored.market_seed, state.market_seed)
        self.assertEqual(restored.free_agents_week, state.free_agents_week)
        self.assertEqual(restored.hired_drivers[-1].potential, state.hired_drivers[-1].potential)

    def test_pre_feature_save_loads_and_lazily_populates(self) -> None:
        state = new_career()
        payload = game_state_to_dict(state)
        for key in ("free_agents", "free_agents_week", "market_seed"):
            payload.pop(key, None)
        legacy = game_state_from_dict(payload)
        self.assertEqual(legacy.free_agents, [])
        self.assertEqual(legacy.market_seed, 0)
        # opening the market lazily fills the pool
        self.assertEqual(len(list_free_agents(legacy)), FREE_AGENT_POOL_SIZE)


if __name__ == "__main__":
    unittest.main()
