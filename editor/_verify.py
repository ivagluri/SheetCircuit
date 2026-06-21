"""Verification harness (not part of the app UI).

Recreates a Pikes Peak track and a Bugatti Veyron *only* through the editor's
field specs + coercion path — proving every knob those facsimiles need is
reachable from the editor — then confirms both load through the real game loader.

Run:  python3 -m editor._verify
"""

from __future__ import annotations

import copy

from game.loader import car_from_dict, track_from_dict
from game.effective_stats import class_rating, derived_class, performance_type

from editor.app import _set, coerce, validate
from editor.fields import (
    CAR_SCHEMA,
    CAR_SECTIONS,
    SEGMENT_FIELDS,
    SEGMENT_TEMPLATE,
    TRACK_SCHEMA,
    TRACK_SECTIONS,
)


def _spec(sections, path):
    for section in sections:
        for spec in section.fields:
            if spec.path == tuple(path):
                return spec
    raise KeyError(path)


def _apply(draft, sections, edits):
    """Apply {path: typed_string} edits via the editor's coerce(), as the UI does."""
    for path, raw in edits.items():
        spec = _spec(sections, path)
        value = coerce(spec, raw, draft)
        # `_set` walks the same path the field spec declares.
        node = draft
        for key in spec.path[:-1]:
            node = node[key]
        node[spec.path[-1]] = value


def _segment(edits):
    seg = copy.deepcopy(SEGMENT_TEMPLATE)
    by_key = {s.key: s for s in SEGMENT_FIELDS}
    for key, raw in edits.items():
        seg[key] = coerce(by_key[key], raw, seg.get(key))
    return seg


def build_pikes():
    draft = copy.deepcopy(TRACK_SCHEMA.template)
    _apply(draft, TRACK_SECTIONS, {
        ("id",): "pikes_peak_hillclimb",
        ("name",): "Pikes Peak International Hill Climb",
        ("layout_type",): "hillclimb",
        ("length_km",): "19.99",
        ("pit_lane_loss_s",): "0",
        ("elevation_change_m",): "1440",
        ("surface",): "tarmac",
        ("default_condition",): "dry",
        ("weather_variability",): "0.55",
        ("overtake_difficulty",): "0.9",
    })
    draft["segments"] = [
        _segment({"name": "The Gateway", "length_pct": "0.10", "tags": "short_straight wide_track", "surface": "tarmac", "condition": "dry"}),
        _segment({"name": "Engineers Section", "length_pct": "0.16", "tags": "technical_section slow_corner", "surface": "tarmac", "condition": "dry"}),
        _segment({"name": "The W's", "length_pct": "0.14", "tags": "tight_chicane hard_braking_zone", "surface": "tarmac", "condition": "dry"}),
        _segment({"name": "Picnic Ground Straight", "length_pct": "0.10", "tags": "long_straight exposed", "surface": "tarmac", "condition": "dry"}),
        _segment({"name": "Glen Cove Switchbacks", "length_pct": "0.14", "tags": "technical_section slow_corner", "surface": "tarmac", "condition": "damp"}),
        _segment({"name": "Devils Playground", "length_pct": "0.10", "tags": "bumpy_surface narrow_track", "surface": "gravel", "condition": "damp"}),
        _segment({"name": "Bottomless Pit", "length_pct": "0.12", "tags": "high_speed_corner exposed", "surface": "tarmac", "condition": "wet"}),
        _segment({"name": "Summit Run to 14,115ft", "length_pct": "0.14", "tags": "hard_braking_zone slow_corner curb_riding", "surface": "tarmac", "condition": "wet"}),
    ]
    return draft


def build_veyron():
    draft = copy.deepcopy(CAR_SCHEMA.template)
    _apply(draft, CAR_SECTIONS, {
        ("id",): "bugatti_veyron_164",
        ("name",): "2005 Bugatti Veyron 16.4",
        ("year",): "2005",
        ("manufacturer",): "Bugatti",
        ("model",): "Veyron 16.4",
        ("drivetrain",): "AWD",
        ("layout",): "rear_mid",
        ("tags",): "supercar, hypercar, w16, quad_turbo, awd, high_speed",
        ("value",): "1700000",
        ("powertrain", "power_hp"): "1001",
        ("powertrain", "torque_nm"): "1250",
        ("powertrain", "powerband"): "82",
        ("powertrain", "throttle_response"): "78",
        ("powertrain", "engine_reliability"): "60",
        ("powertrain", "cooling"): "88",
        ("powertrain", "fuel_efficiency"): "14",
        ("powertrain", "aspiration"): "twin_turbo",
        ("powertrain", "engine_stress"): "82",
        ("chassis", "weight_kg"): "1888",
        ("chassis", "weight_distribution_front"): "0.45",
        ("chassis", "center_of_gravity"): "70",
        ("chassis", "chassis_rigidity"): "88",
        ("chassis", "stability"): "90",
        ("chassis", "rotation"): "62",
        ("tires", "tire_compound"): "sport",
        ("tires", "tire_width_front"): "265",
        ("tires", "tire_width_rear"): "365",
        ("tires", "base_grip"): "88",
        ("tires", "wet_grip"): "72",
        ("tires", "tire_wear_resistance"): "30",
        ("tires", "tire_heat_resistance"): "70",
        ("tires", "tire_warmup"): "68",
        ("brakes", "braking_power"): "94",
        ("brakes", "brake_stability"): "88",
        ("brakes", "brake_cooling"): "86",
        ("brakes", "brake_fade_resistance"): "84",
        ("suspension", "handling"): "74",
        ("suspension", "mechanical_grip"): "82",
        ("suspension", "suspension_compliance"): "60",
        ("suspension", "curb_handling"): "50",
        ("suspension", "bump_absorption"): "58",
        ("suspension", "steering_precision"): "80",
        ("aero", "downforce"): "60",
        ("aero", "drag"): "52",
        ("aero", "aero_efficiency"): "66",
        ("aero", "high_speed_stability"): "98",
        ("durability", "overall_reliability"): "62",
        ("durability", "engine_reliability"): "56",
        ("durability", "gearbox_reliability"): "70",
        ("durability", "suspension_durability"): "72",
        ("durability", "brake_durability"): "74",
        ("durability", "cooling_capacity"): "88",
        ("durability", "mechanical_sympathy_modifier"): "-2",
        ("fuel", "fuel_capacity_l"): "100.0",
        ("fuel", "base_fuel_burn"): "5.2",
        ("fuel", "fuel_efficiency"): "14",
        ("tune", "final_drive"): "3.10",
        ("tune", "brake_bias"): "0.60",
        ("tune", "front_downforce"): "40",
        ("tune", "rear_downforce"): "55",
        ("tune", "differential_power"): "60",
        ("tune", "engine_map"): "balanced",
    })
    return draft


def main() -> None:
    track_draft = build_pikes()
    ok, msg = validate(TRACK_SCHEMA, track_draft)
    assert ok, f"Pikes track invalid: {msg}"
    track = track_from_dict(copy.deepcopy(track_draft))
    print(f"TRACK  {track.name}")
    print(f"  length={track.length_km}km elev={track.elevation_change_m}m "
          f"segments={len(track.segments)} overtake={track.overtake_difficulty:.2f} (race length is per-event)")
    print(f"  emphasis: top_speed={track.top_speed_weight:.0%} grip={track.grip_weight:.0%} "
          f"handling={track.handling_weight:.0%} braking={track.braking_weight:.0%}")

    car_draft = build_veyron()
    ok, msg = validate(CAR_SCHEMA, car_draft)
    assert ok, f"Veyron car invalid: {msg}"
    car = car_from_dict(copy.deepcopy(car_draft))
    print(f"CAR    {car.identity.name}")
    print(f"  class={derived_class(car)} drivetrain={car.identity.drivetrain} "
          f"PR={class_rating(car)} type={performance_type(car)}")
    print(f"  power={car.powertrain.power_hp}hp weight={car.chassis.weight_kg}kg")
    print("\nBoth facsimiles built only from editor field specs and load through the game loader.")


if __name__ == "__main__":
    main()
