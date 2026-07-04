"""Guards for the simulation-audit rework (see CHANGELOG): the half-wired systems are live.

Mid-race incidents damage the car (and damage feeds failure risk + post-race wear),
driver energy matters (mistakes + pace), post-race wear scales with distance and hits
sub-systems, resale depreciates with condition/mileage, races consume weeks, the car
behind must earn a pass (overtake_difficulty + racecraft are live), and race-day
weather rolls from weather_variability.
"""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest import mock

from constants import (
    CONDITION_HIT_FAILURE,
    DRIVER_ENERGY_PACE_FRACTION,
    OVERTAKE_CONTEST_MAX_S,
    OVERTAKE_FOLLOW_GAP_S,
    OVERTAKE_GAP_JITTER_S,
)
from game.economy import sell_car
from game.effective_stats import compute_effective_stats
from game.game_state import GameState, new_career
from game.loader import apply_race_condition, load_cars, load_parts, load_tracks, roll_race_condition
from game.race_session import (
    _contest_overtakes,
    _pass_chance,
    apply_player_command,
    enter_event,
    finish_event,
    simulate_tick,
)
from game.simulation import _initial_state, apply_post_race_wear, calculate_lap_time
from game.telemetry import mistake_chance


class _FixedRoll:
    """rng stub: every random() returns the same value."""

    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class WiredSystemsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {c.identity.id: c for c in load_cars()}
        self.tracks = {t.id: t for t in load_tracks()}
        self.eff = compute_effective_stats(self.cars["kanto_k660"], self.parts)
        self.track = self.tracks["maple_short"]

    def _session(self, ticks_per_lap: int = 1, seed: int = 11):
        state = GameState(garage=[deepcopy(self.cars["kanto_k660"])])
        session = enter_event(state, "sunday_cup", "kanto_k660", "driver_novak", seed=seed)
        session.ticks_per_lap = ticks_per_lap
        return state, session

    # --- Mid-race damage / driver energy -------------------------------------

    def test_mechanical_issue_damages_the_car(self) -> None:
        _state, session = self._session(ticks_per_lap=4)
        with mock.patch("game.race_session.failure_chance", return_value=1000.0), \
                mock.patch("game.race_session.failure_dnf_chance", return_value=0.0), \
                mock.patch("game.race_session.mistake_chance", return_value=0.0):
            apply_player_command(session, "normal")

        player = next(car for car in session.cars if car.is_player)
        self.assertEqual(player.condition_pct, 100.0 - CONDITION_HIT_FAILURE)

    def test_fatigue_raises_mistake_chance(self) -> None:
        fresh = _initial_state("c", "d", "Y", True)
        tired = _initial_state("c", "d", "Y", True)
        tired.driver_energy = 5.0
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        self.assertGreater(mistake_chance(tired, driver), mistake_chance(fresh, driver))

    def test_exhausted_driver_leaks_pace(self) -> None:
        fresh = _initial_state("c", "d", "Y", True)
        spent = _initial_state("c", "d", "Y", True)
        spent.driver_energy = 0.0
        fresh_lap = calculate_lap_time(self.eff, self.track, state=fresh)
        spent_lap = calculate_lap_time(self.eff, self.track, state=spent)
        self.assertAlmostEqual(
            spent_lap - fresh_lap, self.track.base_lap_time * DRIVER_ENERGY_PACE_FRACTION, places=6
        )

    # --- Post-race wear / calendar / resale -----------------------------------

    def test_post_race_wear_scales_with_distance_and_hits_subsystems(self) -> None:
        sprint = deepcopy(self.cars["kanto_k660"])
        enduro = deepcopy(self.cars["kanto_k660"])
        apply_post_race_wear(sprint, race_km=10.0)
        apply_post_race_wear(enduro, race_km=60.0)

        self.assertLess(enduro.condition.overall_condition, sprint.condition.overall_condition)
        self.assertLess(enduro.condition.engine_condition, sprint.condition.engine_condition)
        self.assertEqual(sprint.condition.mileage, self.cars["kanto_k660"].condition.mileage + 10)

    def test_mid_race_damage_carries_into_garage_wear(self) -> None:
        clean = deepcopy(self.cars["kanto_k660"])
        battered = deepcopy(self.cars["kanto_k660"])
        apply_post_race_wear(clean, race_km=15.0, damage_pct=0.0)
        apply_post_race_wear(battered, race_km=15.0, damage_pct=20.0)
        self.assertLess(battered.condition.overall_condition, clean.condition.overall_condition)

    def test_finishing_a_race_consumes_a_week(self) -> None:
        state, session = self._session()
        while not session.is_finished:
            simulate_tick(session)
        week_before = state.week
        finish_event(state, session)
        self.assertEqual(state.week, week_before + 1)

    def test_resale_depreciates_with_condition_and_mileage(self) -> None:
        fresh_state = GameState(money=0, garage=[deepcopy(self.cars["kanto_k660"])])
        worn = deepcopy(self.cars["kanto_k660"])
        worn.condition.overall_condition = 50.0
        worn.condition.mileage = 80000
        worn_state = GameState(money=0, garage=[worn])

        sell_car(fresh_state, "kanto_k660")
        sell_car(worn_state, "kanto_k660")
        self.assertLess(worn_state.money, fresh_state.money)

    # --- Overtaking -----------------------------------------------------------

    def test_pass_chance_reads_track_and_racecraft(self) -> None:
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        easy = deepcopy(self.track)
        hard = deepcopy(self.track)
        easy.overtake_difficulty = 0.1
        hard.overtake_difficulty = 0.9
        self.assertGreater(_pass_chance(easy, driver, driver), _pass_chance(hard, driver, driver))

        ace = deepcopy(driver)
        ace.racecraft = driver.racecraft + 40
        self.assertGreater(_pass_chance(easy, ace, driver), _pass_chance(easy, driver, ace))

    def _road_car(self, pre_tick_time: float, total_time: float, driver, label: str = "A"):
        """(pre-tick time, state, driver) road_ahead entry for an advanced defender."""
        ahead = _initial_state(f"car_{label}", "d", label, False)
        ahead.total_time = total_time
        return (pre_tick_time, ahead, driver)

    def test_failed_pass_holds_the_follow_gap(self) -> None:
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        behind = _initial_state("b", "d", "B", False)
        behind.total_time = 100.1  # inside the follow gap of the car at 100.0: contested
        road = [self._road_car(99.0, 100.0, driver)]

        _contest_overtakes(self.track, _FixedRoll(0.99), behind, driver, 99.5, road, 0.2)
        # Held in the breathing band: at least the follow gap, at most gap + jitter.
        self.assertGreaterEqual(behind.total_time, 100.0 + OVERTAKE_FOLLOW_GAP_S - 1e-9)
        self.assertLessEqual(behind.total_time, 100.0 + OVERTAKE_FOLLOW_GAP_S + OVERTAKE_GAP_JITTER_S + 1e-9)

    def test_successful_pass_stands(self) -> None:
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        behind = _initial_state("b", "d", "B", False)
        behind.total_time = 99.9  # would come out ahead: contested, and the roll succeeds
        road = [self._road_car(99.0, 100.0, driver)]

        _contest_overtakes(self.track, _FixedRoll(0.0), behind, driver, 99.5, road, 1.0)
        self.assertAlmostEqual(behind.total_time, 99.9, places=9)
        self.assertAlmostEqual(road[0][1].total_time, 100.0, places=9)  # defender untouched

    def test_won_contest_from_dirty_air_completes_the_pass(self) -> None:
        # The follower is nominally still behind (inside the follow gap) but wins the
        # roll: the pair exchange clocks, so the pass genuinely reorders the road
        # instead of evaporating at the ranking step.
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        behind = _initial_state("b", "d", "B", False)
        behind.total_time = 100.1
        road = [self._road_car(99.0, 100.0, driver)]

        _contest_overtakes(self.track, _FixedRoll(0.0), behind, driver, 99.5, road, 1.0)
        self.assertAlmostEqual(behind.total_time, 100.0, places=9)
        self.assertAlmostEqual(road[0][1].total_time, 100.1, places=9)
        self.assertLess(behind.total_time, road[0][1].total_time)

    def test_dead_heat_at_tick_start_is_not_contested(self) -> None:
        # Standing start: both cars began the tick on the same clock, so neither holds
        # the road -- the field spreads on pace alone, whatever the processing order.
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        behind = _initial_state("b", "d", "B", False)
        behind.total_time = 100.1  # inside the follow gap, but no one is defending
        road = [self._road_car(0.0, 100.0, driver)]

        _contest_overtakes(self.track, _FixedRoll(0.99), behind, driver, 0.0, road, 0.2)
        self.assertAlmostEqual(behind.total_time, 100.1, places=9)

    def test_lapping_a_crippled_car_is_free_but_the_next_one_defends(self) -> None:
        # The car at +7s pitted (huge margin: free pass); the healthy car 0.1s up the
        # road still has to be got past, and the failed move parks the follower in its
        # dirty air. The road is walked nearest-first, not just the last car processed.
        _state, session = self._session()
        driver = session.driver_roster["driver_novak"]
        behind = _initial_state("b", "d", "B", False)
        behind.total_time = 100.0
        crippled = 100.0 + OVERTAKE_CONTEST_MAX_S + 5.0
        road = [self._road_car(99.0, crippled, driver, "C"), self._road_car(99.0, 99.9, driver, "H")]

        _contest_overtakes(self.track, _FixedRoll(0.99), behind, driver, 99.5, road, 0.2)
        self.assertGreaterEqual(behind.total_time, 99.9 + OVERTAKE_FOLLOW_GAP_S - 1e-9)
        self.assertLessEqual(behind.total_time, 99.9 + OVERTAKE_FOLLOW_GAP_S + OVERTAKE_GAP_JITTER_S + 1e-9)

    def test_unpassable_track_keeps_the_field_at_follow_gaps(self) -> None:
        # Fine tick slices keep per-tick pace deltas inside the contest window, so no
        # "crippled car" free passes occur and every close approach must be contested.
        # The first tick is exempt: the standing start is a dead heat (nothing to
        # defend), so the field spreads on pace before dirty air starts to bite.
        _state, session = self._session(ticks_per_lap=12)
        session.track.overtake_difficulty = 1.0  # _pass_chance == 0: no move ever sticks
        ticks = 0
        with mock.patch("game.race_session.mistake_chance", return_value=0.0), \
                mock.patch("game.race_session.failure_chance", return_value=0.0):
            while not session.is_finished:
                simulate_tick(session)
                ticks += 1
                if ticks < 2:
                    continue
                times = sorted(s.total_time for s in session.cars if not s.is_dnf)
                for faster, slower in zip(times, times[1:]):
                    self.assertGreaterEqual(slower - faster, OVERTAKE_FOLLOW_GAP_S - 1e-9)

    # --- Race-day weather ------------------------------------------------------

    def test_forecast_roll_bands(self) -> None:
        track = deepcopy(self.track)
        track.weather_variability = 0.2
        self.assertEqual(roll_race_condition(track, _FixedRoll(0.01)), "wet")   # < 0.2*0.35
        self.assertEqual(roll_race_condition(track, _FixedRoll(0.10)), "damp")  # < 0.2
        self.assertEqual(roll_race_condition(track, _FixedRoll(0.90)), "dry")
        track.weather_variability = 0.0
        self.assertEqual(roll_race_condition(track, _FixedRoll(0.0)), "dry")

    def test_applying_weather_escalates_profiles_and_aggregate(self) -> None:
        track = deepcopy(self.track)
        dry_aggregate = track.tire_wear_rate
        apply_race_condition(track, "wet")

        for profile in track.segment_profiles:
            self.assertEqual(profile.condition, "wet")
            self.assertEqual(profile.wet_weight, 1.0)
            self.assertLess(profile.grip_mult, 1.0)
        self.assertGreater(track.tire_wear_rate, dry_aggregate)
        self.assertAlmostEqual(
            track.tire_wear_rate,
            sum(p.length_pct * p.tire_wear_rate for p in track.segment_profiles),
            places=9,
        )

    def test_weather_never_dries_an_authored_condition(self) -> None:
        track = deepcopy(self.track)
        apply_race_condition(track, "damp")
        damp_profiles = [deepcopy(p) for p in track.segment_profiles]
        apply_race_condition(track, "dry")  # de-escalation must be a no-op
        for before, after in zip(damp_profiles, track.segment_profiles):
            self.assertEqual(before.condition, after.condition)
            self.assertEqual(before.grip_mult, after.grip_mult)

    def test_wet_race_slows_the_field(self) -> None:
        wet_track = deepcopy(self.track)
        apply_race_condition(wet_track, "wet")
        dry_lap = calculate_lap_time(self.eff, self.track)
        wet_lap = calculate_lap_time(self.eff, wet_track)
        self.assertGreater(wet_lap, dry_lap)

    # --- Section 4/5 cleanups --------------------------------------------------

    def test_burned_fuel_lightens_the_car(self) -> None:
        full = _initial_state("c", "d", "Y", True)
        half = _initial_state("c", "d", "Y", True)
        half.fuel_pct = 50.0
        full_lap = calculate_lap_time(self.eff, self.track, state=full)
        half_lap = calculate_lap_time(self.eff, self.track, state=half)
        from constants import FUEL_WEIGHT_PENALTY_PER_L

        expected_gain = 0.5 * self.eff.fuel_capacity_l * FUEL_WEIGHT_PENALTY_PER_L
        self.assertAlmostEqual(full_lap - half_lap, expected_gain, places=6)

    def test_session_caches_effective_stats_per_entry(self) -> None:
        _state, session = self._session()
        self.assertEqual(
            set(session.effective_stats), {car.car_id for car in session.cars}
        )
        # Ticks must not recompute: poison the roster and confirm the race still runs.
        with mock.patch(
            "game.race_session.compute_effective_stats",
            side_effect=AssertionError("tick recomputed effective stats"),
        ):
            simulate_tick(session)

    def test_simulate_to_end_pit_command_is_one_shot(self) -> None:
        from game.actions import simulate_to_end_action

        _state, session = self._session(ticks_per_lap=2)
        simulate_to_end_action(session, "pit")
        pit_stops = sum("pitted" in message for _lap, message in session.race_log)
        self.assertEqual(pit_stops, 1)

    def test_session_carries_the_rolled_weather(self) -> None:
        # Alpine has weather_variability 0.65; seed 3 rolls 0.62 on the isolated
        # forecast stream -> damp. The session's track must be escalated to match.
        state = new_career()
        state.money += 10000
        session = enter_event(
            state, "alpine_hillclimb_stage", state.garage[0].identity.id,
            state.hired_drivers[0].id, seed=3,
        )
        self.assertEqual(session.weather, "damp")
        self.assertTrue(any(p.condition == "damp" for p in session.track.segment_profiles))
        self.assertTrue(any("Race runs damp" in message for _lap, message in session.race_log))


if __name__ == "__main__":
    unittest.main()
