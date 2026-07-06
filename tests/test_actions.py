from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from constants import TUNE_FIELD_RANGES
from game.actions import (
    advance_race_action,
    advance_to_lap_end_action,
    buy_car_action,
    buy_part_action,
    car_detail_screen,
    compendium_screen,
    drivers_screen,
    driver_detail_screen,
    tune_fields_for_car,
    events_screen,
    event_detail_screen,
    finish_race_action,
    garage_screen,
    market_screen,
    market_car_detail_screen,
    race_screen,
    race_command_options,
    simulate_to_end_action,
    start_race_action,
    tune_car_action,
    tune_fields_screen,
    upgrade_part_detail_screen,
    upgrades_part_screen,
    upgrades_slot_screen,
)
from game.effective_stats import compute_effective_stats
from game.game_state import GameState, new_career
from game.loader import load_cars, load_drivers
from game.sorting import parse_sort_spec
from game.simulation import SimulationError
from game.tuning import TuningError


class ActionLayerTests(unittest.TestCase):
    def test_screen_actions_return_plain_table_data(self) -> None:
        state = new_career()

        garage = garage_screen(state)
        events = events_screen()
        market = market_screen()

        self.assertEqual(garage.name, "garage")
        self.assertEqual(garage.tables[0].headers[1], "Car")
        self.assertEqual(events.tables[0].title, "Events")
        self.assertTrue(market.tables[0].rows)
        self.assertIn("tables", asdict(garage))

    def test_events_screen_shows_requirement_status_and_best_result(self) -> None:
        state = GameState(event_progress={
            "sunday_cup": {
                "starts": 2,
                "best_position": 1,
                "wins": 1,
                "podiums": 2,
                "best_time_s": 410.2,
            }
        })

        screen = events_screen(state)
        # Rows are keyed by the visible Event name now that the ID column is gone.
        rows = {row[1]: row for row in screen.tables[0].rows}

        self.assertEqual(screen.tables[0].headers[4:7], ["Req", "Status", "Best"])
        self.assertEqual(rows["Sunday Cup"][4:7], ["Lv 1", "Open", "Win"])
        self.assertEqual(rows["Clubman Trial"][4], "Lv 2")
        self.assertTrue(str(rows["Clubman Trial"][5]).startswith("Locked"))
        self.assertEqual(rows["Clubman Trial"][6], "No starts")

    def test_car_screens_can_be_sorted_by_price_and_power(self) -> None:
        price_sorted = market_screen(parse_sort_spec("market", "price"))
        power_sorted = market_screen(parse_sort_spec("market", "hp"))

        prices = [int(row[5].replace("$", "")) for row in price_sorted.tables[0].rows]
        powers = [int(row[6].replace(" hp", "")) for row in power_sorted.tables[0].rows]

        self.assertEqual(prices, sorted(prices))
        self.assertEqual(powers, sorted(powers, reverse=True))
        self.assertIn("sorted by Price asc", price_sorted.tables[0].title)
        self.assertIn("sorted by HP desc", power_sorted.tables[0].title)

    def test_driver_screen_can_be_sorted_by_pace(self) -> None:
        state = GameState()

        screen = drivers_screen(state, parse_sort_spec("drivers", "pace"))
        paces = [row[2] for row in screen.tables[0].rows]

        self.assertEqual(paces, sorted(paces, reverse=True))

    def test_tune_editor_screen_lists_sections_and_staged_counts(self) -> None:
        from game.actions import tune_editor_screen

        state = new_career()
        car_id = state.garage[0].identity.id

        screen = tune_editor_screen(state, car_id)
        sections = [row[1] for row in screen.tables[0].rows]
        self.assertEqual(sections, ["Tyres", "ECU", "Brakes", "Suspension", "Transmission", "Differential", "Aero"])
        self.assertTrue(any(line.startswith("PR ") for line in screen.messages))

        staged = tune_editor_screen(state, car_id, {"engine_map": "hot", "final_drive": 4.2})
        ecu_row = next(row for row in staged.tables[0].rows if row[1] == "ECU")
        transmission_row = next(row for row in staged.tables[0].rows if row[1] == "Transmission")
        self.assertEqual(ecu_row[3], "1 staged")
        self.assertEqual(transmission_row[3], "1 staged")
        self.assertIn("2 staged changes (not applied)", staged.subtitle)

    def test_tune_section_screen_shows_staged_values_and_deltas(self) -> None:
        from game.actions import tune_section_screen

        state = new_career()
        car_id = state.garage[0].identity.id
        buy_part_action(state, car_id, "sports_ecu", install=True)

        screen = tune_section_screen(state, car_id, "ECU", {"engine_map": "qualifying"})
        engine_row = next(row for row in screen.tables[0].rows if row[1] == "Engine Map")
        self.assertEqual(engine_row[3], "qualifying")
        # A power-map change must surface as a before→after delta in the readout.
        self.assertTrue(any("→" in line for line in screen.messages))
        # Section is addressable by 1-based index too.
        by_index = tune_section_screen(state, car_id, 2)
        self.assertEqual(by_index.tables[0].title, "ECU")

    def test_apply_tune_draft_is_atomic(self) -> None:
        from game.actions import apply_tune_draft

        state = new_career()
        car = state.garage[0]
        buy_part_action(state, car.identity.id, "sports_ecu", install=True)

        with self.assertRaises(TuningError):
            apply_tune_draft(state, car.identity.id, {"engine_map": "hot", "brake_bias": 99.0})
        # The invalid brake_bias must not let the valid engine_map slip through.
        self.assertEqual(car.tune.engine_map, "balanced")

        result = apply_tune_draft(state, car.identity.id, {"engine_map": "hot"})
        self.assertEqual(car.tune.engine_map, "hot")
        self.assertIn("Engine Map", result.message)

    def test_stage_tune_value_validates_without_applying(self) -> None:
        from game.actions import stage_tune_value

        state = new_career()
        car = state.garage[0]

        stage_tune_value(state, car.identity.id, "tire_pressure_front", 2.2)  # valid: no exception
        self.assertNotEqual(car.tune.tire_pressure_front, 2.2)  # and nothing applied
        with self.assertRaises(TuningError):
            stage_tune_value(state, car.identity.id, "brake_bias", 99.0)

    def test_upgrade_buy_install_and_uninstall_are_separate_from_ownership(self) -> None:
        state = new_career()
        car = state.garage[0]
        base_grip = compute_effective_stats(car).grip
        money = state.money

        buy = buy_part_action(state, car.identity.id, "sport_tires_1")
        self.assertIn("sport_tires_1", car.owned_parts)
        self.assertNotIn("sport_tires_1", car.installed_parts)
        self.assertEqual(state.money, money - 1400)
        self.assertEqual(buy.screen.name, "upgrades_slot")
        self.assertEqual(compute_effective_stats(car).grip, base_grip)

        from game.actions import install_part_action, uninstall_part_action
        install_part_action(state, car.identity.id, "sport_tires_1")
        self.assertIn("sport_tires_1", car.installed_parts)
        self.assertGreater(compute_effective_stats(car).grip, base_grip)

        uninstall_part_action(state, car.identity.id, "tires")
        self.assertIn("sport_tires_1", car.owned_parts)
        self.assertNotIn("sport_tires_1", car.installed_parts)
        self.assertEqual(state.money, money - 1400)

    def test_locked_tune_fields_require_installed_hardware(self) -> None:
        state = new_career()
        car = state.garage[0]

        with self.assertRaises(TuningError):
            tune_car_action(state, car.identity.id, "brake_bias", 0.62)
        buy_part_action(state, car.identity.id, "brake_controller", install=True)
        tune_car_action(state, car.identity.id, "brake_bias", 0.62)
        self.assertEqual(car.tune.brake_bias, 0.62)

    def test_intrinsic_properties_are_not_tunable(self) -> None:
        # The creator can edit these; the in-game garage cannot: identity, the engine
        # itself, weight, durability build quality, fuel hardware, and condition.
        state = new_career()
        car = state.garage[0]
        screen = tune_fields_screen(state, car.identity.id)
        offered = {field.name for field in screen.fields}

        for field in ["name", "year", "power_hp", "torque_nm", "aspiration", "weight_kg",
                      "overall_reliability", "fuel_capacity_l", "base_fuel_burn",
                      "overall_condition", "value"]:
            with self.subTest(field=field):
                self.assertNotIn(field, offered)
                with self.assertRaises(TuningError):
                    tune_car_action(state, car.identity.id, field, 1)

    def test_upgrades_part_screen_lists_tyre_compounds(self) -> None:
        state = new_career()
        car = state.garage[0]

        screen = upgrades_part_screen(state, car.identity.id, "tires")
        # The ID column is gone; the Part column (row[1]) is the display name.
        part_names = [row[1] for row in screen.tables[0].rows]
        self.assertEqual(part_names, [
            "Economy Tyres",
            "Street Performance Tyres",
            "Sport Tyres",
            "Semi-Slick Tyres",
            "Racing Slicks",
        ])
        effect_text = " ".join(str(row[5]) for row in screen.tables[0].rows)
        self.assertIn("Compound: Sport", effect_text)
        self.assertNotIn("tires.", effect_text)
        self.assertFalse(any("\n" in str(row[5]) for row in screen.tables[0].rows))

    def test_upgrade_part_detail_uses_readable_effect_rows(self) -> None:
        state = new_career()
        car_id = state.garage[0].identity.id

        screen = upgrade_part_detail_screen(state, car_id, "sports_ecu")
        rows = {row[0]: row[1] for row in screen.tables[0].rows}

        self.assertEqual(screen.name, "upgrades_action")
        self.assertEqual(rows["Status"], "shop")
        self.assertIn("Power +5 hp", rows["Improves"])
        self.assertIn("Fuel Efficiency -1", rows["Reduces"])
        self.assertEqual(rows["Unlocks"], "unlocks Engine Map")
        self.assertFalse(any("\n" in str(row[1]) for row in screen.tables[0].rows))

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

        # Career Tune is setup-only; permanent stat changes live in Upgrades.
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

    def test_team_level_gate_blocks_locked_race_without_entry_fee(self) -> None:
        car = deepcopy(next(car for car in load_cars() if car.identity.id == "kanto_k660"))
        state = GameState(garage=[car])
        money_before = state.money

        with self.assertRaisesRegex(SimulationError, "requires Team Lv 2"):
            start_race_action(state, "clubman_trial", "kanto_k660", "driver_novak", seed=3)

        self.assertEqual(state.money, money_before)

    def test_team_level_gate_allows_unlocked_race(self) -> None:
        car = deepcopy(next(car for car in load_cars() if car.identity.id == "kanto_k660"))
        state = GameState(team_xp=100, garage=[car])

        result = start_race_action(state, "clubman_trial", "kanto_k660", "driver_novak", seed=3)

        self.assertEqual(result.session.event_id, "clubman_trial")
        self.assertEqual(state.money, 8000 - 500)

    def test_open_track_day_is_zero_fee_no_xp_recovery_event(self) -> None:
        state = new_career()
        state.money = 0
        car = state.garage[0]
        driver = state.hired_drivers[0]

        started = start_race_action(state, "open_track_day", car.identity.id, driver.id, seed=1)
        self.assertEqual(state.money, 0)

        finished_session = simulate_to_end_action(started.session).session
        finished = finish_race_action(state, finished_session)

        self.assertGreater(finished.prize_money, 0)
        self.assertEqual(state.team_xp, 0)
        self.assertEqual(driver.experience, 0)
        self.assertEqual(finished.screen.messages[0], f"Race finished. Prize: ${finished.prize_money}")

    def test_event_detail_with_state_estimates_time_from_garage_car(self) -> None:
        # Regression: _estimate_entry passed EffectiveCarStats into class_rating (which
        # takes a Car), crashing event detail whenever the garage was non-empty.
        state = new_career()

        screen = event_detail_screen("sunday_cup", state)

        event_rows = next(table for table in screen.tables if table.title == "Event").rows
        self.assertIn("Est. Time", [row[0] for row in event_rows])

    def test_event_detail_shows_progression_status_and_progress(self) -> None:
        state = GameState(event_progress={
            "clubman_trial": {
                "starts": 3,
                "best_position": 2,
                "wins": 0,
                "podiums": 2,
                "best_time_s": 389.4,
            }
        })

        locked = event_detail_screen("clubman_trial", state)
        event_rows = dict(next(table for table in locked.tables if table.title == "Event").rows)
        progress_rows = dict(next(table for table in locked.tables if table.title == "Event Progress").rows)

        self.assertEqual(event_rows["Kind"], "Ladder")
        self.assertEqual(event_rows["Team Requirement"], "Team Lv 2")
        self.assertEqual(event_rows["Status"], "Locked (100 XP)")
        self.assertEqual(event_rows["XP Needed"], "100 XP")
        self.assertEqual(progress_rows["Best Result"], "P2 podium")
        self.assertEqual(progress_rows["Best Time"], "389.4s")

        invitational_rows = dict(next(
            table for table in event_detail_screen("beater_enduro", state).tables
            if table.title == "Event"
        ).rows)
        self.assertEqual(invitational_rows["Kind"], "Open Invitational")

    def test_garage_and_market_show_pr_and_type(self) -> None:
        state = new_career()

        garage = garage_screen(state)
        market = market_screen()

        self.assertEqual(garage.tables[0].headers[3:5], ["PR", "Type"])
        self.assertEqual(market.tables[0].headers[3:5], ["PR", "Type"])
        self.assertIsInstance(garage.tables[0].rows[0][3], int)
        self.assertIsInstance(market.tables[0].rows[0][3], int)
        self.assertTrue(garage.tables[0].rows[0][4])
        self.assertTrue(market.tables[0].rows[0][4])

    def test_economy_and_tune_actions_mutate_state_and_return_screen(self) -> None:
        state = GameState()
        buy_result = buy_car_action(state, "kanto_k660")
        buy_part_action(state, "kanto_k660", "brake_controller", install=True)
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

    def test_race_banner_names_event_track_and_driver(self) -> None:
        # The live race must say what you're running and who's driving — not
        # only reveal it on the results screen.
        cars = {car.identity.id: car for car in load_cars()}
        state = GameState(garage=[deepcopy(cars["kanto_k660"])])

        session = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3).session
        subtitle = race_screen(session).subtitle

        self.assertIn(session.event.name, subtitle)
        self.assertIn(session.track.name, subtitle)
        self.assertIn(session.driver_roster["driver_novak"].name, subtitle)
        self.assertIn(f"Lap {session.current_lap}/{session.total_laps}", subtitle)

    def test_finish_race_commits_team_xp_event_progress_and_post_race_summary(self) -> None:
        cars = {car.identity.id: car for car in load_cars()}
        drivers = {driver.id: driver for driver in load_drivers()}
        state = GameState(
            garage=[deepcopy(cars["kanto_k660"])],
            hired_drivers=[deepcopy(drivers["driver_novak"])],
        )

        session = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3).session
        simulate_to_end_action(session)
        result = finish_race_action(state, session)

        self.assertEqual(result.screen.name, "post_race")
        self.assertEqual(
            [table.title for table in result.screen.tables],
            ["Final Standings", "Rewards", "Team Progress", "Event Progress", "Driver Progress", "Car Condition"],
        )
        self.assertIn("Race finished. Prize: $", result.screen.messages[0])
        self.assertEqual(state.team_xp, 50)
        self.assertEqual(state.event_progress["sunday_cup"]["starts"], 1)
        self.assertEqual(state.event_progress["sunday_cup"]["wins"], 1)

        rewards = dict(next(table for table in result.screen.tables if table.title == "Rewards").rows)
        self.assertEqual(rewards["Team XP"], "+50")
        self.assertEqual(rewards["Result XP"], "+25")
        self.assertEqual(rewards["First Win Bonus"], "+25")
        self.assertEqual(rewards["Repeat Multiplier"], "1.00x")

        progress_rows = {
            row[0]: row for row in next(table for table in result.screen.tables if table.title == "Event Progress").rows
        }
        self.assertEqual(progress_rows["Starts"], ["Starts", 0, 1])
        self.assertEqual(progress_rows["Best Result"], ["Best Result", "No starts", "Win"])

        driver_rows = dict(next(table for table in result.screen.tables if table.title == "Driver Progress").rows)
        self.assertIn("+10 XP", driver_rows["Driver"])
        condition_rows = {
            row[0]: row for row in next(table for table in result.screen.tables if table.title == "Car Condition").rows
        }
        self.assertTrue(str(condition_rows["Mileage"][3]).startswith("+"))

    def test_repeat_win_uses_repeat_multiplier_without_first_win_bonus(self) -> None:
        cars = {car.identity.id: car for car in load_cars()}
        state = GameState(
            team_xp=50,
            garage=[deepcopy(cars["kanto_k660"])],
            event_progress={
                "sunday_cup": {
                    "starts": 1,
                    "best_position": 1,
                    "wins": 1,
                    "podiums": 1,
                    "best_time_s": 405.0,
                }
            },
        )

        session = start_race_action(state, "sunday_cup", "kanto_k660", "driver_novak", seed=3).session
        simulate_to_end_action(session)
        result = finish_race_action(state, session)

        rewards = dict(next(table for table in result.screen.tables if table.title == "Rewards").rows)
        self.assertEqual(state.team_xp, 71)
        self.assertEqual(state.event_progress["sunday_cup"]["starts"], 2)
        self.assertEqual(state.event_progress["sunday_cup"]["wins"], 2)
        self.assertEqual(rewards["Team XP"], "+21")
        self.assertEqual(rewards["First Win Bonus"], "-")
        self.assertEqual(rewards["Repeat Multiplier"], "0.85x")

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


class CompendiumScreenTests(unittest.TestCase):
    def test_index_lists_all_chapters(self) -> None:
        screen = compendium_screen()
        titles = [row[1] for row in screen.tables[0].rows]
        self.assertEqual(titles, ["Cars", "Parts", "Drivers", "Tracks", "Events"])

    def test_chapter_view_lists_sections(self) -> None:
        screen = compendium_screen(("cars",))
        self.assertEqual(screen.title, "Cars")
        section_titles = [row[1] for row in screen.tables[0].rows]
        self.assertIn("Tune", section_titles)

    def test_section_view_has_effect_and_editable_columns(self) -> None:
        screen = compendium_screen(("cars", "Tune"))
        headers = screen.tables[0].headers
        self.assertIn("Effect", headers)
        self.assertIn("Editable", headers)
        labels = [row[1] for row in screen.tables[0].rows]
        self.assertIn("final_drive", labels)

    def test_direct_jump_resolves_field_by_name(self) -> None:
        screen = compendium_screen(query="final_drive")
        self.assertEqual(screen.title, "final_drive")
        self.assertTrue(screen.messages[0])  # effect summary present

    def test_unknown_query_falls_back_to_index(self) -> None:
        screen = compendium_screen(query="no_such_field")
        self.assertEqual(screen.tables[0].title, "Chapters")


class DriverAndTuneHelpTests(unittest.TestCase):
    def test_driver_detail_has_help_column_with_text(self) -> None:
        driver = load_drivers()[0]
        screen = driver_detail_screen(driver.id)
        self.assertEqual(screen.tables[0].headers, ["Stat", "Value", "Help"])
        pace_row = next(row for row in screen.tables[0].rows if row[0] == "Pace")
        self.assertTrue(pace_row[2].strip())

    def test_tune_field_data_carries_help(self) -> None:
        state = new_career()
        car_id = state.garage[0].identity.id
        fields = {field.name: field for field in tune_fields_for_car(state, car_id)}
        self.assertTrue(fields["final_drive"].help.strip())
        self.assertTrue(fields["engine_map"].help.strip())


if __name__ == "__main__":
    unittest.main()
