#!/usr/bin/env python3
"""Pace / thermal instrumentation harness.

Runs a chosen car through N laps at a *fixed* pace command and prints a per-lap
table of the thermal/wear state plus the incident probabilities. Deterministic
(seeded rng) so tuning changes to constants.py are directly comparable. This is
the measurement tool the tactical-pace model was tuned against.

    python tools/pace_probe.py                      # reference car, key commands
    python tools/pace_probe.py --car kanto_k660     # a different car
    python tools/pace_probe.py --track maple_short --laps 8
    python tools/pace_probe.py --commands normal,push,go_all_out,cool_down

Cadence targets (reference mid car, ~composite 50):
  * go_all_out: engine reaches OVERHEAT (~105C) by ~lap 2, CRITICAL (~120C) ~lap 4
  * normal:     temps stable at/below overheat indefinitely
  * one cool_down/save lap after overheat pulls temps back under the line
"""
from __future__ import annotations

from pathlib import Path
import argparse
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from constants import (
    ENGINE_CRITICAL_C,
    ENGINE_OVERHEAT_C,
    TIRE_CRITICAL_C,
    TIRE_OVERHEAT_C,
)
from game.effective_stats import compute_effective_stats
from game.loader import load_cars, load_drivers, load_parts, load_tracks
from game.reference_suite import mean_capability
from game.simulation import _apply_lap_wear, _initial_state, calculate_lap_time
from game.telemetry import failure_chance, failure_dnf_chance, mistake_chance

# Closest catalog car to REFERENCE_COMPOSITE (50): suzuka_roadster ~52.7.
DEFAULT_CAR = "suzuka_roadster"
DEFAULT_TRACK = "maple_short"
DEFAULT_DRIVER = "driver_novak"  # mid driver: consistency 58, mech_symp 55


def _flag(temp: float, overheat: float, critical: float) -> str:
    if temp >= critical:
        return "!!"  # critical / danger band
    if temp >= overheat:
        return "! "  # overheat / warning band
    return "  "


def probe(car_id: str, track_id: str, driver_id: str, command: str, laps: int, seed: int) -> None:
    parts = load_parts()
    cars = {c.identity.id: c for c in load_cars()}
    tracks = {t.id: t for t in load_tracks()}
    drivers = {d.id: d for d in load_drivers()}

    car = cars[car_id]
    track = tracks[track_id]
    driver = drivers[driver_id]
    eff = compute_effective_stats(car, parts)
    rng = random.Random(seed)

    state = _initial_state(car_id, driver_id, "Y", True)

    print(f"\n=== {command}  |  car={car_id} (composite {mean_capability(eff):.1f})  "
          f"track={track_id} (base_lap {track.base_lap_time:.1f}s, {track.length_km:.2f}km)  "
          f"driver={driver_id} ===")
    print(f"{'lap':>3} {'lap_s':>7} {'eng°C':>7} {'tyr°C':>7} {'tyr%':>6} {'fuel%':>6} "
          f"{'miss':>6} {'fail':>6} {'dnf':>6}")
    for lap in range(1, laps + 1):
        lap_s = calculate_lap_time(eff, track, driver=driver, state=state, rng=rng, command=command)
        _apply_lap_wear(state, eff, track, command, seconds=lap_s)
        miss = mistake_chance(state, driver, command)
        fail = failure_chance(state, eff, driver, command)
        dnf = failure_dnf_chance(state)
        eflag = _flag(state.engine_temp, ENGINE_OVERHEAT_C, ENGINE_CRITICAL_C)
        tflag = _flag(state.tire_temp, TIRE_OVERHEAT_C, TIRE_CRITICAL_C)
        print(f"{lap:>3} {lap_s:>7.2f} {state.engine_temp:>5.0f}{eflag} {state.tire_temp:>5.0f}{tflag} "
              f"{state.tire_pct:>6.1f} {state.fuel_pct:>6.1f} {miss:>6.3f} {fail:>6.3f} {dnf:>6.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=DEFAULT_CAR)
    ap.add_argument("--track", default=DEFAULT_TRACK)
    ap.add_argument("--driver", default=DEFAULT_DRIVER)
    ap.add_argument("--laps", type=int, default=8)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--commands", default="normal,push,go_all_out")
    args = ap.parse_args()
    for command in args.commands.split(","):
        probe(args.car, args.track, args.driver, command.strip(), args.laps, args.seed)


if __name__ == "__main__":
    main()
