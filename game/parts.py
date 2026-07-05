from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants import TUNE_FIELD_RANGES
from game.models import Car, Part


LEGACY_PART_ID_MAP: dict[str, str] = {
    "basic_turbo_kit": "turbo_kit_3",
    "basic_intake_1": "intake_1",
    "cooling_upgrade_1": "cooling_1",
    "performance_exhaust_1": "exhaust_1",
}


@dataclass(frozen=True)
class PartSlotRule:
    id: str
    label: str
    staged: bool = False
    description: str = ""


SLOT_RULES: tuple[PartSlotRule, ...] = (
    PartSlotRule("tires", "Tyres", description="One compound set can be fitted at a time."),
    PartSlotRule("brakes", "Brake Kit", staged=True, description="Permanent staged brake hardware."),
    PartSlotRule("intake", "Intake", staged=True, description="Permanent staged engine breathing hardware."),
    PartSlotRule("exhaust", "Exhaust", staged=True, description="Permanent staged exhaust hardware."),
    PartSlotRule("turbo", "Turbo Kit", staged=True, description="Permanent staged forced-induction hardware."),
    PartSlotRule("cooling", "Cooling", staged=True, description="Permanent staged cooling hardware."),
    PartSlotRule("weight_reduction", "Weight Reduction", staged=True, description="Permanent staged lightening."),
    PartSlotRule("fuel_cell", "Fuel Cell", staged=True, description="Permanent staged fuel-capacity hardware."),
    PartSlotRule("sport_suspension", "Sport Suspension", staged=True, description="Permanent staged suspension hardware."),
    PartSlotRule("ecu", "Sports ECU", description="Unlocks non-balanced engine maps."),
    PartSlotRule("brake_controller", "Brake Controller", description="Unlocks brake-balance setup."),
    PartSlotRule("custom_suspension", "Custom Suspension", description="Unlocks ride-height and alignment setup."),
    PartSlotRule("custom_transmission", "Custom Transmission", description="Unlocks final-drive and gear-bias setup."),
    PartSlotRule("custom_lsd", "Custom LSD", description="Unlocks differential setup."),
    PartSlotRule("aero_kit", "Aero Kit", description="Unlocks downforce setup."),
)

SLOT_RULE_BY_ID: dict[str, PartSlotRule] = {rule.id: rule for rule in SLOT_RULES}
KNOWN_SLOTS: set[str] = set(SLOT_RULE_BY_ID)

UNLOCK_ECU = "ecu"
UNLOCK_BRAKE_CONTROLLER = "brake_controller"
UNLOCK_CUSTOM_SUSPENSION = "custom_suspension"
UNLOCK_CUSTOM_TRANSMISSION = "custom_transmission"
UNLOCK_CUSTOM_LSD = "custom_lsd"
UNLOCK_AERO_KIT = "aero_kit"

TUNE_UNLOCK_LABELS: dict[str, str] = {
    UNLOCK_ECU: "Sports ECU",
    UNLOCK_BRAKE_CONTROLLER: "Brake Controller",
    UNLOCK_CUSTOM_SUSPENSION: "Custom Suspension",
    UNLOCK_CUSTOM_TRANSMISSION: "Custom Transmission",
    UNLOCK_CUSTOM_LSD: "Custom LSD",
    UNLOCK_AERO_KIT: "Aero Kit",
}

KNOWN_UNLOCKS: set[str] = set(TUNE_UNLOCK_LABELS)

TUNE_FIELD_UNLOCKS: dict[str, str] = {
    "brake_bias": UNLOCK_BRAKE_CONTROLLER,
    "brake_pressure": UNLOCK_BRAKE_CONTROLLER,
    "front_ride_height": UNLOCK_CUSTOM_SUSPENSION,
    "rear_ride_height": UNLOCK_CUSTOM_SUSPENSION,
    "suspension_stiffness_front": UNLOCK_CUSTOM_SUSPENSION,
    "suspension_stiffness_rear": UNLOCK_CUSTOM_SUSPENSION,
    "antiroll_front": UNLOCK_CUSTOM_SUSPENSION,
    "antiroll_rear": UNLOCK_CUSTOM_SUSPENSION,
    "camber_front": UNLOCK_CUSTOM_SUSPENSION,
    "camber_rear": UNLOCK_CUSTOM_SUSPENSION,
    "toe_front": UNLOCK_CUSTOM_SUSPENSION,
    "toe_rear": UNLOCK_CUSTOM_SUSPENSION,
    "final_drive": UNLOCK_CUSTOM_TRANSMISSION,
    "gear_bias": UNLOCK_CUSTOM_TRANSMISSION,
    "differential_power": UNLOCK_CUSTOM_LSD,
    "differential_coast": UNLOCK_CUSTOM_LSD,
    "differential_preload": UNLOCK_CUSTOM_LSD,
    "front_downforce": UNLOCK_AERO_KIT,
    "rear_downforce": UNLOCK_AERO_KIT,
}

TUNE_MENU_FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tyres", ("tire_pressure_front", "tire_pressure_rear")),
    ("ECU", ("engine_map",)),
    ("Brakes", ("brake_bias", "brake_pressure")),
    ("Suspension", (
        "front_ride_height",
        "rear_ride_height",
        "suspension_stiffness_front",
        "suspension_stiffness_rear",
        "antiroll_front",
        "antiroll_rear",
        "camber_front",
        "camber_rear",
        "toe_front",
        "toe_rear",
    )),
    ("Transmission", ("final_drive", "gear_bias")),
    ("Differential", ("differential_power", "differential_coast", "differential_preload")),
    ("Aero", ("front_downforce", "rear_downforce")),
)

TUNE_MENU_FIELD_NAMES: tuple[str, ...] = tuple(
    name for _category, names in TUNE_MENU_FIELD_GROUPS for name in names
)

VALID_STAT_SECTIONS = {
    "powertrain",
    "chassis",
    "tires",
    "brakes",
    "suspension",
    "aero",
    "durability",
    "fuel",
}


def canonical_part_id(part_id: str) -> str:
    return LEGACY_PART_ID_MAP.get(part_id, part_id)


def normalize_part_ids(part_ids: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_id in part_ids:
        part_id = canonical_part_id(str(raw_id))
        if part_id in seen:
            continue
        seen.add(part_id)
        normalized.append(part_id)
    return normalized


def part_map(parts: list[Part]) -> dict[str, Part]:
    return {part.id: part for part in parts}


def installed_part_for_slot(car: Car, slot: str, parts: list[Part]) -> Part | None:
    by_id = part_map(parts)
    for part_id in normalize_part_ids(car.installed_parts):
        part = by_id.get(part_id)
        if part is not None and part.slot == slot:
            return part
    return None


def installed_unlocks(car: Car, parts: list[Part]) -> set[str]:
    by_id = part_map(parts)
    unlocks: set[str] = set()
    for part_id in normalize_part_ids(car.installed_parts):
        part = by_id.get(part_id)
        if part is not None:
            unlocks.update(part.unlocks)
    return unlocks


def lock_reason_for_tune_field(car: Car, field_name: str, parts: list[Part]) -> str:
    if field_name == "engine_map":
        if UNLOCK_ECU in installed_unlocks(car, parts):
            return ""
        return f"Balanced only until {TUNE_UNLOCK_LABELS[UNLOCK_ECU]} is installed"
    unlock = TUNE_FIELD_UNLOCKS.get(field_name)
    if unlock is None or unlock in installed_unlocks(car, parts):
        return ""
    return f"Install {TUNE_UNLOCK_LABELS[unlock]} to adjust"


def tune_field_value_allowed(car: Car, field_name: str, value: Any, parts: list[Part]) -> bool:
    if field_name == "engine_map":
        return value == "balanced" or UNLOCK_ECU in installed_unlocks(car, parts)
    unlock = TUNE_FIELD_UNLOCKS.get(field_name)
    return unlock is None or unlock in installed_unlocks(car, parts)


def tune_unlock_required_for_value(field_name: str, value: Any) -> str:
    if field_name == "engine_map" and value != "balanced":
        return UNLOCK_ECU
    return TUNE_FIELD_UNLOCKS.get(field_name, "")


def is_tune_setup_field(field_name: str) -> bool:
    return field_name in TUNE_FIELD_RANGES or field_name == "engine_map"
