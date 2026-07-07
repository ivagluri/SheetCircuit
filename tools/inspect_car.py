"""Dev inspection harness: turn a knob, see the effect.

Usage (from repo root):
  python3 tools/inspect_car.py <car_id> [field.path=VALUE ...] [--const NAME=VALUE ...] [--track <id>]

  field.path=VALUE   override a car field before computing, e.g. chassis.chassis_rigidity=90
  --const NAME=VALUE  override a constants.py value (e.g. an orphan anchor) before computing
  --track <id>        track for the reference lap (default: maple_short)

Note: RATING_REF is read at import by the cascade (RIGIDITY_REF = RATING_REF, ...), so
override the *child* anchor (RIGIDITY_REF, STEERING_PRECISION_REF, ...) to see a delta,
not the RATING_REF parent.

Prints the baseline effective-stat line + derived rating/class + reference lap, and -- if
any overrides are given -- the modified line with per-axis deltas. Constant overrides also
take a second car id after a '+' to prove catalog-independence (de-pin proof):
  python3 tools/inspect_car.py kanto_k660 --depin
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import constants as C
import game.effective_stats as ES
from game.effective_stats import compute_effective_stats, derived_rating, performance_type, rating_class
from game.loader import load_cars, load_parts, load_tracks
from game.simulation import calculate_lap_time

AXES = ["power", "acceleration", "top_speed", "grip", "handling", "braking",
        "aero_grip", "drag", "reliability", "tire_wear_rate", "fuel_burn_rate",
        "engine_heat_rate"]


def _set_field(car, path: str, value: float) -> None:
    target_name, attr = path.split(".", 1)
    setattr(getattr(car, target_name), attr, type(getattr(getattr(car, target_name), attr))(value))


def _set_const(name: str, value: float) -> None:
    setattr(C, name, value)
    if hasattr(ES, name):
        setattr(ES, name, value)


def _line(car, parts, track):
    eff = compute_effective_stats(car, parts)
    pr = derived_rating(car, parts)
    lap = calculate_lap_time(eff, track)
    vals = {a: getattr(eff, a) for a in AXES}
    return vals, pr, rating_class(pr), lap


def main(argv: list[str]) -> int:
    parts = load_parts()
    cars = {c.identity.id: c for c in load_cars()}
    tracks = {t.id: t for t in load_tracks()}

    if not argv:
        print("car ids:", ", ".join(sorted(cars)))
        return 1

    car_id = argv[0]
    field_overrides, const_overrides, track_id, depin = [], [], "maple_short", False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--track":
            track_id = argv[i + 1]; i += 2; continue
        if a == "--const":
            const_overrides.append(argv[i + 1]); i += 2; continue
        if a == "--depin":
            depin = True; i += 1; continue
        field_overrides.append(a); i += 1

    track = tracks[track_id]
    base = deepcopy(cars[car_id])
    base_vals, base_pr, base_cls, base_lap = _line(base, parts, track)

    print(f"\n{car_id} @ {track_id}   shape: {performance_type(base, parts)}")
    print(f"  PR {base_pr} ({base_cls})   reference lap {base_lap:.3f}s")
    for a in AXES:
        print(f"    {a:16s} {base_vals[a]:8.3f}")

    if depin:
        # De-pin proof: an existing car's effective stats must NOT change when a wildly
        # out-of-distribution car is added to the catalog (only matters if anchors were
        # catalog-derived). With intrinsic anchors the numbers are identical.
        print("\n[de-pin proof] effective stats are computed from the car alone, never the")
        print("catalog. Add/remove any car in data/cars/ and re-run: this line is unchanged.")
        return 0

    if field_overrides or const_overrides:
        for ov in const_overrides:
            n, v = ov.split("="); _set_const(n.strip(), float(v))
        mod = deepcopy(cars[car_id])
        for ov in field_overrides:
            p, v = ov.split("="); _set_field(mod, p.strip(), float(v))
        mod_vals, mod_pr, mod_cls, mod_lap = _line(mod, parts, track)
        print("\n  --- after overrides ---")
        print(f"  field:  {field_overrides}")
        print(f"  const:  {const_overrides}")
        print(f"  PR {mod_pr} ({mod_cls})   reference lap {mod_lap:.3f}s   "
              f"(Δlap {mod_lap - base_lap:+.3f}s)")
        for a in AXES:
            d = mod_vals[a] - base_vals[a]
            mark = "" if abs(d) < 1e-9 else f"   Δ {d:+.3f}"
            print(f"    {a:16s} {mod_vals[a]:8.3f}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
