from __future__ import annotations

from copy import deepcopy
import unittest

from constants import REPAIR_COST_MIN_PER_POINT, REPAIR_COST_VALUE_FRACTION
from game.economy import EconomyError, buy_car, buy_part, install_part, repair_car, repair_cost, sell_car, uninstall_part
from game.effective_stats import compute_effective_stats
from game.game_state import GameState
from game.loader import load_cars
from game.market import list_market_cars
from game.race_session import enter_event
from game.simulation import simulate_race


class EconomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {car.identity.id: car for car in load_cars()}

    def test_buying_car_deducts_money_and_adds_to_garage(self) -> None:
        state = GameState()
        buy_car(state, "kanto_k660")

        self.assertEqual(state.money, 8000 - self.cars["kanto_k660"].value)
        self.assertEqual(state.garage[0].identity.id, "kanto_k660")

    def test_buying_without_money_leaves_state_unchanged(self) -> None:
        state = GameState(money=1)

        with self.assertRaises(EconomyError):
            buy_car(state, "kanto_k660")

        self.assertEqual(state.money, 1)
        self.assertEqual(state.garage, [])

    def test_selling_car_adds_money_and_removes_from_garage(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        state = GameState(money=0, garage=[car])
        sell_car(state, "kanto_k660")

        self.assertGreater(state.money, 0)
        self.assertEqual(state.garage, [])

    def test_entry_fee_deducted_on_enter_event(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        enter_event(state, "sunday_cup", "kanto_k660", "driver_novak")

        self.assertEqual(state.money, 8000 - 250)

    def test_repair_improves_conditions_and_deducts_money(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        car.condition.overall_condition = 80.0
        car.condition.engine_condition = 80.0
        car.condition.brake_condition = 80.0
        car.condition.suspension_condition = 80.0
        car.condition.tire_condition = 80.0
        state = GameState(money=5000, garage=[car])

        repair_car(state, "kanto_k660", points=5.0)

        self.assertEqual(car.condition.overall_condition, 85.0)
        self.assertEqual(car.condition.engine_condition, 85.0)
        self.assertEqual(car.condition.brake_condition, 85.0)
        self.assertEqual(car.condition.suspension_condition, 85.0)
        self.assertEqual(car.condition.tire_condition, 85.0)
        self.assertEqual(state.money, 5000 - round(5 * 5 * max(REPAIR_COST_MIN_PER_POINT, car.value * REPAIR_COST_VALUE_FRACTION)))

    def test_repair_cost_scales_with_car_value_and_missing_condition(self) -> None:
        cheap = deepcopy(self.cars["kanto_k660"])
        expensive = deepcopy(self.cars["aichi_gt_one"])
        for car in (cheap, expensive):
            car.condition.overall_condition = 80.0
            car.condition.engine_condition = 80.0
            car.condition.brake_condition = 80.0
            car.condition.suspension_condition = 80.0
            car.condition.tire_condition = 80.0

        self.assertEqual(repair_cost(cheap, 5.0), 110)
        self.assertGreater(repair_cost(expensive, 5.0), repair_cost(cheap, 5.0))

        cheap.condition.overall_condition = 99.0
        cheap.condition.engine_condition = 100.0
        cheap.condition.brake_condition = 100.0
        cheap.condition.suspension_condition = 100.0
        cheap.condition.tire_condition = 100.0
        self.assertEqual(repair_cost(cheap, 5.0), round(max(REPAIR_COST_MIN_PER_POINT, cheap.value * REPAIR_COST_VALUE_FRACTION)))

    def test_repair_without_money_leaves_state_unchanged(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        car.condition.overall_condition = 50.0
        state = GameState(money=1, garage=[car])

        with self.assertRaises(EconomyError):
            repair_car(state, "kanto_k660", points=5.0)

        self.assertEqual(car.condition.overall_condition, 50.0)
        self.assertEqual(state.money, 1)

    def test_full_race_awards_position_prize(self) -> None:
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        result = simulate_race(state, "sunday_cup", "kanto_k660", "driver_novak", seed=4)

        # The batch summary charges the entry fee like the live engine.
        self.assertEqual(state.money, 8000 - 250 + result.prize_money)

    def test_market_list_is_non_empty_and_buyable(self) -> None:
        market = list_market_cars()
        state = GameState()

        self.assertTrue(market)
        affordable = next(car for car in market if car.value <= state.money)
        buy_car(state, affordable.identity.id)
        self.assertEqual(state.garage[0].identity.id, affordable.identity.id)

    def test_part_buy_install_and_uninstall_have_no_refund(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        state = GameState(money=5000, garage=[car])
        base_power = compute_effective_stats(car).power

        buy_part(state, car.identity.id, "turbo_kit_1")
        money_after_buy = state.money
        self.assertIn("turbo_kit_1", car.owned_parts)
        self.assertNotIn("turbo_kit_1", car.installed_parts)
        self.assertEqual(compute_effective_stats(car).power, base_power)

        install_part(state, car.identity.id, "turbo_kit_1")
        self.assertGreater(compute_effective_stats(car).power, base_power)
        self.assertEqual(state.money, money_after_buy)

        uninstall_part(state, car.identity.id, "turbo")
        self.assertEqual(state.money, money_after_buy)
        self.assertNotIn("turbo_kit_1", car.installed_parts)
        self.assertIn("turbo_kit_1", car.owned_parts)

    def test_part_duplicate_stage_skip_and_insufficient_funds_are_rejected(self) -> None:
        car = deepcopy(self.cars["kanto_k660"])
        state = GameState(money=5000, garage=[car])

        with self.assertRaises(EconomyError):
            buy_part(state, car.identity.id, "turbo_kit_2")
        self.assertEqual(car.owned_parts, [])

        buy_part(state, car.identity.id, "turbo_kit_1")
        with self.assertRaises(EconomyError):
            buy_part(state, car.identity.id, "turbo_kit_1")

        poor = GameState(money=1, garage=[deepcopy(self.cars["kanto_k660"])])
        with self.assertRaises(EconomyError):
            buy_part(poor, "kanto_k660", "sport_tires_1")
        self.assertEqual(poor.money, 1)
        self.assertEqual(poor.garage[0].owned_parts, [])


if __name__ == "__main__":
    unittest.main()
