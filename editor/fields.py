"""Field metadata for the car and track editors.

Every editable knob in the car/track schemas is declared here as a ``FieldSpec``
grouped into ``Section``s. The specs drive validation, prompts and help so the
app stays a thin renderer and the *schema* (constants + models) remains the single
source of truth. ``copy.deepcopy`` of the templates gives a fresh, valid draft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from constants import (
    CONDITION_MODIFIERS,
    ENGINE_MAP_POWER,
    SEGMENT_TAG_WEIGHTS,
    SURFACE_MODIFIERS,
    TUNE_FIELD_RANGES,
)

# --- Choice vocabularies, sourced from the schema where possible -------------
SURFACES = list(SURFACE_MODIFIERS)                 # tarmac / concrete / gravel
CONDITIONS = list(CONDITION_MODIFIERS)             # dry / damp / wet
ENGINE_MAPS = list(ENGINE_MAP_POWER)               # safe / balanced / hot / ...
SEGMENT_TAGS = list(SEGMENT_TAG_WEIGHTS)           # the 12 segment tags
CAR_CLASSES = ["E", "D", "C", "B", "A", "S"]
DRIVETRAINS = ["RWD", "FWD", "AWD"]
LAYOUTS = ["front_engine", "mid_engine", "rear_engine", "front_mid", "rear_mid"]
ASPIRATIONS = ["NA", "turbo", "supercharged", "twin_turbo"]
TIRE_COMPOUNDS = ["economy", "street", "sport", "semi_slick", "slick"]
TRACK_LAYOUT_TYPES = [
    "circuit",
    "road_course",
    "point_to_point",
    "sprint",
    "rallycross",
    "oval",
    "hillclimb",
]


@dataclass(frozen=True)
class FieldSpec:
    """One editable value. ``path`` is the key chain into the draft dict."""

    path: tuple[str, ...]
    label: str
    kind: str  # int | float | str | enum | tags
    help: str = ""
    minimum: float | None = None
    maximum: float | None = None
    choices: Sequence[str] = ()
    free_choices: bool = False  # enum/tags also accepts values outside `choices`

    @property
    def key(self) -> str:
        return self.path[-1]


@dataclass(frozen=True)
class Section:
    title: str
    fields: list[FieldSpec]


@dataclass
class Schema:
    kind: str  # "car" | "track"
    template: dict[str, Any]
    sections: list[Section]
    id_path: tuple[str, ...] = field(default_factory=lambda: ("id",))


def _f(path, label, kind, help="", minimum=None, maximum=None, choices=(), free=False):
    return FieldSpec(path, label, kind, help, minimum, maximum, tuple(choices), free)


def _rng(name: str) -> tuple[float, float]:
    return TUNE_FIELD_RANGES[name]


# ---------------------------------------------------------------------------
# CAR SCHEMA
# ---------------------------------------------------------------------------
CAR_TEMPLATE: dict[str, Any] = {
    "id": "",
    "name": "",
    "year": 2005,
    "manufacturer": "",
    "model": "",
    "car_class": "B",
    "drivetrain": "RWD",
    "layout": "front_engine",
    "tags": [],
    "powertrain": {
        "power_hp": 300, "torque_nm": 380, "powerband": 60, "throttle_response": 60,
        "engine_reliability": 65, "cooling": 65, "fuel_efficiency": 45,
        "aspiration": "NA", "engine_stress": 45,
    },
    "chassis": {
        "weight_kg": 1300, "weight_distribution_front": 0.52, "center_of_gravity": 60,
        "chassis_rigidity": 65, "stability": 65, "rotation": 60,
    },
    "tires": {
        "tire_compound": "sport", "tire_width_front": 225, "tire_width_rear": 245,
        "base_grip": 65, "wet_grip": 55, "tire_wear_resistance": 55,
        "tire_heat_resistance": 60, "tire_warmup": 60,
    },
    "brakes": {
        "braking_power": 65, "brake_stability": 62, "brake_cooling": 60,
        "brake_fade_resistance": 60,
    },
    "suspension": {
        "handling": 65, "mechanical_grip": 65, "suspension_compliance": 55,
        "curb_handling": 55, "bump_absorption": 52, "steering_precision": 65,
    },
    "aero": {"downforce": 30, "drag": 40, "aero_efficiency": 45, "high_speed_stability": 60},
    "durability": {
        "overall_reliability": 68, "engine_reliability": 65, "gearbox_reliability": 68,
        "suspension_durability": 66, "brake_durability": 66, "cooling_capacity": 66,
        "mechanical_sympathy_modifier": 0,
    },
    "fuel": {"fuel_capacity_l": 62.0, "base_fuel_burn": 2.4, "fuel_efficiency": 45},
    "condition": {
        "overall_condition": 100.0, "engine_condition": 100.0, "gearbox_condition": 100.0,
        "suspension_condition": 100.0, "brake_condition": 100.0, "body_condition": 100.0,
        "tire_condition": 100.0, "mileage": 0,
    },
    "installed_parts": [],
    "tune": {
        "tire_pressure_front": 2.20, "tire_pressure_rear": 2.20, "final_drive": 4.00,
        "gear_bias": 0.0, "brake_bias": 0.58, "brake_pressure": 1.00,
        "front_ride_height": 120, "rear_ride_height": 125,
        "suspension_stiffness_front": 49, "suspension_stiffness_rear": 49,
        "antiroll_front": 4, "antiroll_rear": 4, "camber_front": -1.5, "camber_rear": -1.5,
        "toe_front": 0.0, "toe_rear": 0.0, "front_downforce": 20, "rear_downforce": 30,
        "differential_power": 34, "differential_coast": 18, "differential_preload": 15,
        "engine_map": "balanced",
    },
    "value": 50000,
}

_R100 = (0, 100)  # rating-style 0-100 axes


def _tune(name, label, help=""):
    lo, hi = _rng(name)
    kind = "float" if isinstance(lo, float) or isinstance(hi, float) else "int"
    return _f(("tune", name), label, kind, help, lo, hi)


CAR_SECTIONS: list[Section] = [
    Section("Identity", [
        _f(("id",), "id (filename slug)", "str", "lowercase_with_underscores; used for the JSON filename"),
        _f(("name",), "name", "str", "display name, e.g. '2005 Bugatti Veyron'"),
        _f(("year",), "year", "int", "", 1900, 2100),
        _f(("manufacturer",), "manufacturer", "str"),
        _f(("model",), "model", "str"),
        _f(("car_class",), "car_class", "enum", "PR bracket label; watch the live PR readout", choices=CAR_CLASSES),
        _f(("drivetrain",), "drivetrain", "enum", "AWD gains low-grip traction in the sim", choices=DRIVETRAINS),
        _f(("layout",), "layout", "enum", choices=LAYOUTS, free=True),
        _f(("tags",), "tags", "tags", "free descriptors (e.g. supercar, turbo, hillclimb)", free=True),
        _f(("value",), "value ($)", "int", "market price", 0, None),
    ]),
    Section("Powertrain", [
        _f(("powertrain", "power_hp"), "power_hp", "int", "peak power; drives top speed & power axes", 0, None),
        _f(("powertrain", "torque_nm"), "torque_nm", "int", "torque; ratio vs hp shapes acceleration", 0, None),
        _f(("powertrain", "powerband"), "powerband", "int", "", *_R100),
        _f(("powertrain", "throttle_response"), "throttle_response", "int", "", *_R100),
        _f(("powertrain", "engine_reliability"), "engine_reliability", "int", "", *_R100),
        _f(("powertrain", "cooling"), "cooling", "int", "", *_R100),
        _f(("powertrain", "fuel_efficiency"), "fuel_efficiency", "int", "", *_R100),
        _f(("powertrain", "aspiration"), "aspiration", "enum", choices=ASPIRATIONS, free=True),
        _f(("powertrain", "engine_stress"), "engine_stress", "int", "", *_R100),
    ]),
    Section("Chassis", [
        _f(("chassis", "weight_kg"), "weight_kg", "int", "lighter = quicker everywhere", 200, None),
        _f(("chassis", "weight_distribution_front"), "weight_distribution_front", "float", "front mass fraction; 0.52 ideal", 0.30, 0.70),
        _f(("chassis", "center_of_gravity"), "center_of_gravity", "int", "higher rating = lower CoG = better", *_R100),
        _f(("chassis", "chassis_rigidity"), "chassis_rigidity", "int", "", *_R100),
        _f(("chassis", "stability"), "stability", "int", "", *_R100),
        _f(("chassis", "rotation"), "rotation", "int", "", *_R100),
    ]),
    Section("Tires", [
        _f(("tires", "tire_compound"), "tire_compound", "enum", choices=TIRE_COMPOUNDS, free=True),
        _f(("tires", "tire_width_front"), "tire_width_front", "int", "mm", 120, 400),
        _f(("tires", "tire_width_rear"), "tire_width_rear", "int", "mm", 120, 400),
        _f(("tires", "base_grip"), "base_grip", "int", "dry grip", *_R100),
        _f(("tires", "wet_grip"), "wet_grip", "int", "grip on damp/wet segments", *_R100),
        _f(("tires", "tire_wear_resistance"), "tire_wear_resistance", "int", "", *_R100),
        _f(("tires", "tire_heat_resistance"), "tire_heat_resistance", "int", "", *_R100),
        _f(("tires", "tire_warmup"), "tire_warmup", "int", "", *_R100),
    ]),
    Section("Brakes", [
        _f(("brakes", "braking_power"), "braking_power", "int", "", *_R100),
        _f(("brakes", "brake_stability"), "brake_stability", "int", "", *_R100),
        _f(("brakes", "brake_cooling"), "brake_cooling", "int", "", *_R100),
        _f(("brakes", "brake_fade_resistance"), "brake_fade_resistance", "int", "", *_R100),
    ]),
    Section("Suspension", [
        _f(("suspension", "handling"), "handling", "int", "", *_R100),
        _f(("suspension", "mechanical_grip"), "mechanical_grip", "int", "", *_R100),
        _f(("suspension", "suspension_compliance"), "suspension_compliance", "int", "", *_R100),
        _f(("suspension", "curb_handling"), "curb_handling", "int", "", *_R100),
        _f(("suspension", "bump_absorption"), "bump_absorption", "int", "", *_R100),
        _f(("suspension", "steering_precision"), "steering_precision", "int", "", *_R100),
    ]),
    Section("Aero", [
        _f(("aero", "downforce"), "downforce", "int", "grip in high-speed corners", *_R100),
        _f(("aero", "drag"), "drag", "int", "hurts top speed", *_R100),
        _f(("aero", "aero_efficiency"), "aero_efficiency", "int", "trims effective drag", *_R100),
        _f(("aero", "high_speed_stability"), "high_speed_stability", "int", "", *_R100),
    ]),
    Section("Durability", [
        _f(("durability", "overall_reliability"), "overall_reliability", "int", "", *_R100),
        _f(("durability", "engine_reliability"), "engine_reliability", "int", "", *_R100),
        _f(("durability", "gearbox_reliability"), "gearbox_reliability", "int", "", *_R100),
        _f(("durability", "suspension_durability"), "suspension_durability", "int", "", *_R100),
        _f(("durability", "brake_durability"), "brake_durability", "int", "", *_R100),
        _f(("durability", "cooling_capacity"), "cooling_capacity", "int", "", *_R100),
        _f(("durability", "mechanical_sympathy_modifier"), "mechanical_sympathy_modifier", "int", "approx -4..15", -10, 20),
    ]),
    Section("Fuel", [
        _f(("fuel", "fuel_capacity_l"), "fuel_capacity_l", "float", "litres", 1.0, None),
        _f(("fuel", "base_fuel_burn"), "base_fuel_burn", "float", "litres-ish per unit load", 0.0, None),
        _f(("fuel", "fuel_efficiency"), "fuel_efficiency", "int", "", *_R100),
    ]),
    Section("Condition", [
        _f(("condition", "overall_condition"), "overall_condition", "float", "100 = brand new", 0.0, 100.0),
        _f(("condition", "engine_condition"), "engine_condition", "float", "", 0.0, 100.0),
        _f(("condition", "gearbox_condition"), "gearbox_condition", "float", "", 0.0, 100.0),
        _f(("condition", "suspension_condition"), "suspension_condition", "float", "", 0.0, 100.0),
        _f(("condition", "brake_condition"), "brake_condition", "float", "", 0.0, 100.0),
        _f(("condition", "body_condition"), "body_condition", "float", "", 0.0, 100.0),
        _f(("condition", "tire_condition"), "tire_condition", "float", "", 0.0, 100.0),
        _f(("condition", "mileage"), "mileage", "int", "km", 0, None),
    ]),
    Section("Tune", [
        _tune("tire_pressure_front", "tire_pressure_front", "bar; 2.25 ideal"),
        _tune("tire_pressure_rear", "tire_pressure_rear", "bar; 2.25 ideal"),
        _tune("final_drive", "final_drive", "lower = more top speed"),
        _tune("gear_bias", "gear_bias", "+accel / -top speed"),
        _tune("brake_bias", "brake_bias", "0.60 ideal"),
        _tune("brake_pressure", "brake_pressure"),
        _tune("front_ride_height", "front_ride_height", "mm"),
        _tune("rear_ride_height", "rear_ride_height", "mm"),
        _tune("suspension_stiffness_front", "suspension_stiffness_front"),
        _tune("suspension_stiffness_rear", "suspension_stiffness_rear"),
        _tune("antiroll_front", "antiroll_front"),
        _tune("antiroll_rear", "antiroll_rear"),
        _tune("camber_front", "camber_front", "deg"),
        _tune("camber_rear", "camber_rear", "deg"),
        _tune("toe_front", "toe_front", "deg"),
        _tune("toe_rear", "toe_rear", "deg"),
        _tune("front_downforce", "front_downforce"),
        _tune("rear_downforce", "rear_downforce"),
        _tune("differential_power", "differential_power"),
        _tune("differential_coast", "differential_coast"),
        _tune("differential_preload", "differential_preload"),
        _f(("tune", "engine_map"), "engine_map", "enum", choices=ENGINE_MAPS),
    ]),
]

CAR_SCHEMA = Schema("car", CAR_TEMPLATE, CAR_SECTIONS)


# ---------------------------------------------------------------------------
# TRACK SCHEMA
# ---------------------------------------------------------------------------
TRACK_TEMPLATE: dict[str, Any] = {
    "id": "",
    "name": "",
    "layout_type": "circuit",
    "base_lap_time": 90.0,
    "length_km": 4.0,
    "pit_lane_loss_s": 20.0,
    "overtake_difficulty": 0.5,
    "elevation_change_m": 40,
    "surface": "tarmac",
    "default_condition": "dry",
    "weather_variability": 0.2,
    "segments": [],
}

SEGMENT_TEMPLATE: dict[str, Any] = {
    "name": "New Segment",
    "length_pct": 0.10,
    "tags": ["short_straight"],
    "surface": "tarmac",
    "condition": "dry",
}

TRACK_SECTIONS: list[Section] = [
    Section("Identity & Layout", [
        _f(("id",), "id (filename slug)", "str", "lowercase_with_underscores"),
        _f(("name",), "name", "str"),
        _f(("layout_type",), "layout_type", "enum", "point_to_point runs once; circuit/oval loop", choices=TRACK_LAYOUT_TYPES, free=True),
        _f(("length_km",), "length_km", "float", "length of ONE lap; race length is set per-event", 0.1, None),
        _f(("base_lap_time",), "base_lap_time", "float", "seconds for a reference run of one lap (see suggested values in preview)", 1.0, None),
        _f(("pit_lane_loss_s",), "pit_lane_loss_s", "float", "time lost pitting", 0.0, None),
        _f(("elevation_change_m",), "elevation_change_m", "int", "sustained climb taxes fuel/heat", -2000, 5000),
        _f(("surface",), "surface (default)", "enum", "fallback surface for the track", choices=SURFACES),
        _f(("default_condition",), "default_condition", "enum", choices=CONDITIONS),
        _f(("weather_variability",), "weather_variability", "float", "0..1 chance of changing weather", 0.0, 1.0),
        _f(("overtake_difficulty",), "overtake_difficulty", "float", "0..1 base; narrow/wide tags adjust it", 0.0, 1.0),
    ]),
    # Segments are edited in a dedicated list screen, not as flat fields.
]

SEGMENT_FIELDS: list[FieldSpec] = [
    _f(("name",), "name", "str"),
    _f(("length_pct",), "length_pct", "float", "fraction of the lap; all segments must sum to 1.0", 0.0, 1.0),
    _f(("tags",), "tags", "tags", "shape the segment's demands (multi-select)", choices=SEGMENT_TAGS),
    _f(("surface",), "surface", "enum", choices=SURFACES),
    _f(("condition",), "condition", "enum", choices=CONDITIONS),
]

TRACK_SCHEMA = Schema("track", TRACK_TEMPLATE, TRACK_SECTIONS)


# ---------------------------------------------------------------------------
# EVENT SCHEMA  (race format lives here, not on the track)
# ---------------------------------------------------------------------------
def _track_ids() -> list[str]:
    """Existing track ids (filename stems), so the editor can point an event at one."""
    tracks_dir = (Path(__file__).resolve().parents[1] / "data" / "tracks")
    return sorted(p.stem for p in tracks_dir.glob("*.json"))


RACE_MODES = ["laps", "distance_km", "duration_s"]

# The editor draft carries race_mode + race_value and a few flattened restriction knobs;
# app.py translates these into the real event JSON (one race-length field, restrictions
# dict) on save. This keeps the generic field engine simple while honouring the schema.
EVENT_TEMPLATE: dict[str, Any] = {
    "id": "",
    "name": "",
    "track_id": "",
    "car_class_limit": "E",
    "entry_fee": 250,
    "prize_money": [1500, 900, 500, 200],
    "opponent_count": 7,
    "rival_skill": 0,            # 0 = use the class default
    "race_mode": "laps",
    "race_value": 5,            # laps count, or km, or seconds (per race_mode)
    "restr_max_power_hp": 0,    # 0 = no restriction
    "restr_max_class_rating": 0,
    "restr_allowed_tires": [],
}

EVENT_SECTIONS: list[Section] = [
    Section("Event", [
        _f(("id",), "id (filename slug)", "str", "lowercase_with_underscores"),
        _f(("name",), "name", "str", "e.g. 'Maple Weekender'"),
        _f(("track_id",), "track_id", "enum", "which track this race runs on", choices=_track_ids()),
        _f(("car_class_limit",), "car_class_limit", "enum", "highest car class allowed to enter", choices=CAR_CLASSES),
        _f(("entry_fee",), "entry_fee ($)", "int", "", 0, None),
        _f(("opponent_count",), "opponent_count", "int", "size of the rival field", 0, 40),
        _f(("prize_money",), "prize_money", "ints", "payouts by finishing position, comma-separated"),
        _f(("rival_skill",), "rival_skill", "int", "0 = class default; else 1-100 override", 0, 100),
    ]),
    Section("Race Length", [
        _f(("race_mode",), "race_mode", "enum", "laps | distance_km | duration_s (duration not yet raceable)", choices=RACE_MODES),
        _f(("race_value",), "race_value", "float", "laps count, OR race km, OR seconds — per race_mode", 0.0, None),
    ]),
    Section("Restrictions (optional)", [
        _f(("restr_max_power_hp",), "max_power_hp", "int", "0 = no cap", 0, None),
        _f(("restr_max_class_rating",), "max_class_rating", "int", "0 = no cap", 0, None),
        _f(("restr_allowed_tires",), "allowed_tires", "tags", "empty = any compound", choices=TIRE_COMPOUNDS),
    ]),
]

EVENT_SCHEMA = Schema("event", EVENT_TEMPLATE, EVENT_SECTIONS)
