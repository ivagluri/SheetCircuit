from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from constants import TUNE_FIELD_RANGES
from game.actions import (
    advance_race_action,
    advance_to_lap_end_action,
    buy_car_action,
    car_detail_screen,
    drivers_screen,
    driver_detail_screen,
    events_screen,
    event_detail_screen,
    garage_screen,
    market_screen,
    market_car_detail_screen,
    race_screen,
    race_command_options,
    start_race_action,
    tune_car_action,
    tune_fields_screen,
)
from game.game_state import GameState, new_career
from game.loader import load_cars
from game.sorting import parse_sort_spec
from game.tuning import TuningError


class ActionLayerTests(unittest.TestCase):
    def test_screen_actions_return_plain_table_data(self) -> None:
        state = new_career()

        garage = garage_screen(state)
        events = events_screen()
        market = market_screen()

        self.assertEqual(garage.name, "garage")
        self.assertEqual(garage.tables[0].headers[1], "ID")
        self.assertEqual(events.tables[0].title, "Events")
        self.assertTrue(market.tables[0].rows)
        self.assertIn("tables", asdict(garage))

    def test_car_screens_can_be_sorted_by_price_and_power(self) -> None:
        price_sorted = market_screen(parse_sort_spec("market", "price"))
        power_sorted = market_screen(parse_sort_spec("market", "hp"))

        prices = [int(row[6].replace("$", "")) for row in price_sorted.tables[0].rows]
        powers = [int(row[7].replace(" hp", "")) for row in power_sorted.tables[0].rows]

        self.assertEqual(prices, sorted(prices))
        self.assertEqual(powers, sorted(powers, reverse=True))
        self.assertIn("sorted by Price asc", price_sorted.tables[0].title)
        self.assertIn("sorted by HP desc", power_sorted.tables[0].title)

    def test_driver_screen_can_be_sorted_by_pace(self) -> None:
        state = GameState()

        screen = drivers_screen(state, parse_sort_spec("drivers", "pace"))
        paces = [row[3] for row in screen.tables[0].rows]

        self.assertEqual(paces, sorted(paces, reverse=True))

    def test_tune_screen_surfaces_ranges_and_choice_options(self) -> None:
        state = new_career()

        screen = tune_fields_screen(state, state.garage[0].identity.id)
        fields = {field.name: field for field in screen.fields}

        self.assertEqual(screen.tables[0].headers, ["#", "Field", "Current", "Allowed"])
        self.assertEqual(fields["engine_map"].value_type, "choice")
        self.assertTrue(fields["engine_map"].options)
        self.assertIn("Balanced", [option.label for option in fields["engine_map"].options])
        self.assertEqual(fields["brake_bias"].value_type, "number")
        self.assertIsNotNone(fields["brake_bias"].minimum)
        self.assertIsNotNone(fields["brake_bias"].maximum)

    def test_tune_screen_exposes_every_editable_field_with_continuous_numbering(self) -> None:
        from dataclasses import fields as dataclass_fields
        from game.models import TuneSetup

        state = new_career()
        screen = tune_fields_screen(state, state.garage[0].identity.id)

        # Every editable TuneSetup field is offered (was previously only 11 of 22).
        expected = {f.name for f in dataclass_fields(TuneSetup)}
        self.assertEqual({field.name for field in screen.fields}, expected)

        # The grouped tables share one continuous 1..N numbering that indexes the
        # flat field list the CLI selects from.
        numbers = [row[0] for table in screen.tables for row in table.rows]
        self.assertEqual(numbers, list(range(1, len(screen.fields) + 1)))

    def test_detail_screens_surface_row_information(self) -> None:
        state = new_career()

        driver = driver_detail_screen("driver_novak")
        event = event_detail_screen("sunday_cup")
        garage_car = car_detail_screen(state, state.garage[0].identity.id)
        market_car = market_car_detail_screen("kanto_k660")

        self.assertEqual(driver.title, "Pete Novak")
        self.assertEqual(event.title, "Sunday Cup")
        self.assertEqual(garage_car.title, state.garage[0].identity.name)
        self.assertEqual(market_car.title, "1994 Kanto K660")
        self.assertIn("Driver Stats", [table.title for table in driver.tables])

    def test_event_detail_with_state_estimates_time_from_garage_car(self) -> None:
        # Regression: _estimate_entry passed EffectiveCarStats into class_rating (which
        # takes a Car), crashing event detail whenever the garage was non-empty.
        state = new_career()

        screen = event_detail_screen("sunday_cup", state)

        event_rows = next(table for table in screen.tables if table.title == "Event").rows
        self.assertIn("Est. Time", [row[0] for row in event_rows])

    def test_garage_and_market_show_pr_and_type(self) -> None:
        state = new_career()

        garage = garage_screen(state)
        market = market_screen()

        self.assertEqual(garage.tables[0].headers[4:6], ["PR", "Type"])
        self.assertEqual(market.tables[0].headers[4:6], ["PR", "Type"])
        self.assertIsInstance(garage.tables[0].rows[0][4], int)
        self.assertIsInstance(market.tables[0].rows[0][4], int)
        self.assertTrue(garage.tables[0].rows[0][5])
        self.assertTrue(market.tables[0].rows[0][5])

    def test_economy_and_tune_actions_mutate_state_and_return_screen(self) -> None:
        state = GameState()
        buy_result = buy_car_action(state, "kanto_k660")
        tune_result = tune_car_action(state, "kanto_k660", "brake_bias", 0.62)

        self.assertEqual(buy_result.state.garage[0].identity.id, "kanto_k660")
        self.assertEqual(tune_result.state.garage[0].tune.brake_bias, 0.62)
        self.assertEqual(tune_result.screen.name, "garage")

    def test_invalid_engine_map_is_rejected_before_mutation(self) -> None:
        state = new_career()
        original = state.garage[0].tune.engine_map

        with self.assertRaises(TuningError):
            tune_car_action(state, state.garage[0].identity.id, "engine_map", "")

        self.assertEqual(state.garage[0].tune.engine_map, original)

    def test_all_tune_fields_reject_invalid_values_without_mutation(self) -> None:
        state = new_career()
        car = state.garage[0]
        invalid_by_field = {
            "engine_map": "ludicrous",
            **{field: "" for field in TUNE_FIELD_RANGES},
        }

        for field, invalid_value in invalid_by_field.items():
            with self.subTest(field=field):
                original = getattr(car.tune, field)
                with self.assertRaises(TuningError):
                    tune_car_action(state, car.identity.id, field, invalid_value)
                self.assertEqual(getattr(car.tune, field), original)

    def test_tune_numeric_fields_reject_wrong_type_and_out_of_range(self) -> None:
        state = new_career()
        car = state.garage[0]

        for field, (low, high) in TUNE_FIELD_RANGES.items():
            with self.subTest(field=field, bad_value="not-number"):
                original = getattr(car.tune, field)
                with self.assertRaises(TuningError):
                    tune_car_action(state, car.identity.id, field, "not-number")
                self.assertEqual(getattr(car.tune, field), original)

            with self.subTest(field=field, bad_value="below-range"):
                original = getattr(car.tune, field)
                below_range = int(low - 1) if isinstance(original, int) else low - 1
                with self.assertRaises(TuningError):
                    tune_car_action(state, car.identity.id, field, below_range)
                self.assertEqual(getattr(car.tune, field), original)

            with self.subTest(field=field, bad_value="above-range"):
                original = getattr(car.tune, field)
                above_range = int(high + 1) if isinstance(original, int) else high + 1
                with self.assertRaises(TuningError):
                    tune_car_action(state, car.identity.id, field, above_range)
                self.assertEqual(getattr(car.tune, field), original)

    def test_multi_field_tune_update_is_atomic(self) -> None:
        from game.tuning import update_tune_fields

        state = new_career()
        car = state.garage[0]
        original_brake_bias = car.tune.brake_bias
        original_engine_map = car.tune.engine_map

        with self.assertRaises(TuningError):
            update_tune_fields(state, car.identity.id, brake_bias=0.62, engine_map="bad")

        self.assertEqual(car.tune.brake_bias, original_brake_bias)
        self.assertEqual(car.tune.engine_map, original_engine_map)

    def test_race_actions_return_serializable_screen_data(self) -> None:
        cars = {car.identity.id: car for car in load_cars()}
        state = GameState(garage=[deepcopy(cars["kanto_k660"])])

        started = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3)
        advanced = advance_race_action(started.session, "normal")
        screen = race_screen(started.session, advanced.tick)

        self.assertEqual(started.screen.name, "race")
        self.assertEqual(advanced.screen.name, "race")
        self.assertEqual(screen.tables[0].title, "Standings")
        self.assertIn("subtitle", asdict(screen))

    def test_race_screen_caps_log_to_recent_events(self) -> None:
        cars = {car.identity.id: car for car in load_cars()}
        state = GameState(garage=[deepcopy(cars["kanto_k660"])])
        started = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3)
        started.session.race_log = [(lap, f"event {lap}") for lap in range(1, 16)]

        screen = race_screen(started.session)
        race_log = next(table for table in screen.tables if table.title == "Race Log")

        self.assertEqual(race_log.headers, ["Lap", "Event"])
        self.assertEqual(len(race_log.rows), 10)
        # Event cells are space-padded to a constant width so the panel never resizes mid-race.
        self.assertEqual(race_log.rows[0][0], 6)
        self.assertEqual(race_log.rows[0][1].rstrip(), "event 6")
        self.assertEqual(race_log.rows[-1][0], 15)
        self.assertEqual(race_log.rows[-1][1].rstrip(), "event 15")
        self.assertEqual(len({len(row[1]) for row in race_log.rows}), 1)

    def test_track_strip_gives_unequal_times_distinct_rows(self) -> None:
        # Cosmetic contract: two dots share a strip row only on a true dead heat, so the
        # field never reads as an equal-times procession.
        cars = {car.identity.id: car for car in load_cars()}
        state = GameState(garage=[deepcopy(cars["kanto_k660"])])
        started = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3)
        tick = None
        for _ in range(10):
            tick = advance_race_action(started.session, "push").tick
        times = [car.total_time for car in started.session.cars]
        self.assertEqual(len(set(times)), len(times))  # jitter makes a fluke tie ~impossible

        strip = next(table for table in race_screen(started.session, tick).tables if table.title == "Track")
        # rows[0] is the finish line and the last two are the lane tags and legend.
        for row in strip.rows[1:-2]:
            dots = row[0].count("●") + row[0].count("○")
            self.assertLessEqual(dots, 1, f"unequal times share a strip row: {row[0]!r}")

    def test_fast_forward_to_lap_end_matches_ticking_by_hand(self) -> None:
        # Presentation fast-forward must have zero effect on the result: skipping to the lap
        # end produces the exact same per-car state as ticking the lap one sub-tick at a time.
        cars = {car.identity.id: car for car in load_cars()}

        def by_hand() -> dict[str, float]:
            state = GameState(garage=[deepcopy(cars["kanto_k660"])])
            session = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=5).session
            while True:
                result = advance_race_action(session, "normal")
                if result.tick is not None and result.tick.is_lap_end:
                    break
            return session.current_lap, {s.label: round(s.total_time, 6) for s in session.cars}

        def fast_forward() -> dict[str, float]:
            state = GameState(garage=[deepcopy(cars["kanto_k660"])])
            session = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=5).session
            advance_to_lap_end_action(session, "normal")
            return session.current_lap, {s.label: round(s.total_time, 6) for s in session.cars}

        self.assertEqual(by_hand(), fast_forward())

    def test_cycle_speed_wraps_through_the_presentation_multipliers(self) -> None:
        from interfaces.cli import _RACE_SPEEDS, _cycle_speed

        seen = [1.0]
        for _ in range(len(_RACE_SPEEDS)):
            seen.append(_cycle_speed(seen[-1]))
        # Steps through every speed and wraps back to the first.
        self.assertEqual(seen[:-1], list(_RACE_SPEEDS))
        self.assertEqual(seen[-1], _RACE_SPEEDS[0])

    def test_race_screen_surfaces_labelled_command_options(self) -> None:
        options = race_command_options()
        values = {option.value for option in options}

        # Driver/pit-boss intents only — no engine-map commands (those live in tuning).
        self.assertEqual(
            values,
            {"normal", "push", "go_all_out", "save_tyres", "save_fuel", "cool_down", "pit"},
        )
        self.assertIn("Go All Out", [option.label for option in options])
        self.assertTrue(all(option.description for option in options))
        self.assertTrue(all(option.key for option in options))


if __name__ == "__main__":
    unittest.main()
