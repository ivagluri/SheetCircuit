"""Direction tests for previously-orphan stats now folded into effective stats.

Each test isolates one stat (deep-copying a seed car and changing only that field) and
asserts the intended monotonic effect on the relevant effective axis or rate. These lock
the wiring direction; magnitudes are governed by the centered factors in constants.py and
guarded for balance by tests/test_balance_baseline.py.
"""

from __future__ import annotations

from copy import deepcopy
import unittest

from game.effective_stats import compute_effective_stats
from game.loader import load_cars, load_parts


class OrphanStatPhase1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}

    def _eff(self, car):
        return compute_effective_stats(car, self.parts)

    def test_chassis_rigidity_raises_handling(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        stiff = deepcopy(base)
        stiff.chassis.chassis_rigidity = min(99, base.chassis.chassis_rigidity + 25)
        self.assertGreater(self._eff(stiff).handling, self._eff(base).handling)

    def test_wider_tires_raise_grip_and_wear(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        wide = deepcopy(base)
        wide.tires.tire_width_front += 40
        wide.tires.tire_width_rear += 40
        base_e, wide_e = self._eff(base), self._eff(wide)
        self.assertGreater(wide_e.grip, base_e.grip)
        self.assertGreater(wide_e.tire_wear_rate, base_e.tire_wear_rate)

    def test_brake_cooling_and_fade_raise_braking(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        better = deepcopy(base)
        better.brakes.brake_cooling = min(99, base.brakes.brake_cooling + 25)
        better.brakes.brake_fade_resistance = min(99, base.brakes.brake_fade_resistance + 25)
        self.assertGreater(self._eff(better).braking, self._eff(base).braking)

    def test_aero_efficiency_lowers_drag_and_raises_top_speed(self) -> None:
        base = deepcopy(self.cars["detroit_v8"])
        slippery = deepcopy(base)
        slippery.aero.aero_efficiency = min(99, base.aero.aero_efficiency + 30)
        base_e, slip_e = self._eff(base), self._eff(slippery)
        self.assertLess(slip_e.drag, base_e.drag)
        self.assertGreater(slip_e.top_speed, base_e.top_speed)

    def test_torque_raises_acceleration(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        torquey = deepcopy(base)
        torquey.powertrain.torque_nm += 120
        self.assertGreater(self._eff(torquey).acceleration, self._eff(base).acceleration)

    def test_tire_warmup_raises_heat_rate(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        hot = deepcopy(base)
        hot.tires.tire_warmup = min(99, base.tires.tire_warmup + 25)
        self.assertGreater(self._eff(hot).tire_heat_rate, self._eff(base).tire_heat_rate)

    def test_steering_precision_raises_handling(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        sharp = deepcopy(base)
        sharp.suspension.steering_precision = min(99, base.suspension.steering_precision + 25)
        self.assertGreater(self._eff(sharp).handling, self._eff(base).handling)


class OrphanStatPhase2TuneTests(unittest.TestCase):
    """Tune knobs that previously did nothing now trade off effective axes."""

    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}

    def _eff(self, car):
        return compute_effective_stats(car, self.parts)

    def test_gear_bias_trades_acceleration_for_top_speed(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        short = deepcopy(base)
        short.tune.gear_bias = 0.8
        base_e, short_e = self._eff(base), self._eff(short)
        self.assertGreater(short_e.acceleration, base_e.acceleration)
        self.assertLess(short_e.top_speed, base_e.top_speed)

    def test_differential_power_raises_acceleration(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        locked = deepcopy(base)
        locked.tune.differential_power = base.tune.differential_power + 30
        self.assertGreater(self._eff(locked).acceleration, self._eff(base).acceleration)

    def test_excess_toe_reduces_grip(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        toed = deepcopy(base)
        toed.tune.toe_front = 0.8
        toed.tune.toe_rear = 0.8
        self.assertLess(self._eff(toed).grip, self._eff(base).grip)

    def test_stiffness_away_from_ideal_reduces_grip(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        stiff = deepcopy(base)
        stiff.tune.suspension_stiffness_front = 95
        stiff.tune.suspension_stiffness_rear = 95
        self.assertLess(self._eff(stiff).grip, self._eff(base).grip)


class OrphanStatPhase3Tests(unittest.TestCase):
    """Durability/condition -> reliability, capacity/efficiency -> fuel, fitness -> drain,
    elevation -> track load."""

    def setUp(self) -> None:
        self.parts = load_parts()
        self.cars = {car.identity.id: car for car in load_cars()}

    def _eff(self, car):
        return compute_effective_stats(car, self.parts)

    def test_secondary_durability_raises_reliability(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        tough = deepcopy(base)
        tough.durability.gearbox_reliability = min(99, base.durability.gearbox_reliability + 20)
        tough.durability.suspension_durability = min(99, base.durability.suspension_durability + 20)
        tough.durability.brake_durability = min(99, base.durability.brake_durability + 20)
        tough.durability.cooling_capacity = min(99, base.durability.cooling_capacity + 20)
        self.assertGreater(self._eff(tough).reliability, self._eff(base).reliability)

    def test_mechanical_sympathy_modifier_raises_reliability(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        kind = deepcopy(base)
        kind.durability.mechanical_sympathy_modifier = base.durability.mechanical_sympathy_modifier + 12
        self.assertGreater(self._eff(kind).reliability, self._eff(base).reliability)

    def test_bigger_tank_and_efficiency_lower_fuel_burn(self) -> None:
        base = deepcopy(self.cars["kanto_k660"])
        thrifty = deepcopy(base)
        thrifty.fuel.fuel_capacity_l = base.fuel.fuel_capacity_l + 30
        thrifty.fuel.fuel_efficiency = min(99, base.fuel.fuel_efficiency + 25)
        self.assertLess(self._eff(thrifty).fuel_burn_rate, self._eff(base).fuel_burn_rate)

    def test_body_damage_raises_drag(self) -> None:
        base = deepcopy(self.cars["suzuka_roadster"])
        damaged = deepcopy(base)
        damaged.condition.body_condition = max(10.0, base.condition.body_condition - 40)
        self.assertGreater(self._eff(damaged).drag, self._eff(base).drag)

    def test_fitter_driver_drains_energy_slower(self) -> None:
        from game.loader import load_tracks
        from game.simulation import _apply_lap_wear, _initial_state

        track = {t.id: t for t in load_tracks()}["maple_short"]
        effective = self._eff(self.cars["kanto_k660"])

        fit_state = _initial_state("c", "d", "YOU", True)
        unfit_state = _initial_state("c", "d", "YOU", True)
        _apply_lap_wear(fit_state, effective, track, driver_fitness=95)
        _apply_lap_wear(unfit_state, effective, track, driver_fitness=30)
        self.assertGreater(fit_state.driver_energy, unfit_state.driver_energy)
        self.assertGreater(fit_state.driver_focus, unfit_state.driver_focus)

    def test_elevation_raises_track_fuel_and_heat_load(self) -> None:
        from copy import deepcopy as _dc
        from game.loader import track_from_dict

        payload = {
            "id": "t", "name": "T", "layout_type": "circuit", "base_lap_time": 90.0,
            "laps": 5, "length_km": 4.0, "pit_lane_loss_s": 20.0, "overtake_difficulty": 0.5,
            "surface": "tarmac", "default_condition": "dry", "weather_variability": 0.1,
            "segments": [
                {"name": "s1", "length_pct": 0.5, "tags": ["long_straight"], "surface": "tarmac", "condition": "dry"},
                {"name": "s2", "length_pct": 0.5, "tags": ["slow_corner"], "surface": "tarmac", "condition": "dry"},
            ],
        }
        flat = track_from_dict({**_dc(payload), "elevation_change_m": 10})
        climb = track_from_dict({**_dc(payload), "elevation_change_m": 500})
        self.assertGreater(climb.engine_heat_rate, flat.engine_heat_rate)
        self.assertGreater(climb.fuel_burn_rate, flat.fuel_burn_rate)
        # tyre wear is elevation-independent
        self.assertAlmostEqual(climb.tire_wear_rate, flat.tire_wear_rate, places=9)


if __name__ == "__main__":
    unittest.main()
