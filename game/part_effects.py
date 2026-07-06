from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from game.models import Part


@dataclass(frozen=True)
class PartEffectMeta:
    label: str
    theme: str
    higher_is_better: bool
    unit: str = ""
    order: int = 100


@dataclass(frozen=True)
class PartOverrideMeta:
    label: str
    theme: str
    order: int = 100


@dataclass(frozen=True)
class ModifierEffect:
    path: str
    label: str
    theme: str
    delta: int | float
    unit: str
    polarity: str
    intensity: int
    order: int


@dataclass(frozen=True)
class OverrideEffect:
    path: str
    label: str
    theme: str
    value: int | float | str
    order: int


@dataclass(frozen=True)
class PartEffectDisplay:
    improves: tuple[ModifierEffect, ...]
    reduces: tuple[ModifierEffect, ...]
    numbers: tuple[OverrideEffect, ...]
    unlocks: tuple[str, ...]


PART_EFFECT_METADATA: dict[str, PartEffectMeta] = {
    "powertrain.power_hp": PartEffectMeta("Power", "Power", True, "hp", 10),
    "powertrain.torque_nm": PartEffectMeta("Torque", "Power", True, "Nm", 11),
    "powertrain.powerband": PartEffectMeta("Powerband", "Power", True, order=12),
    "powertrain.throttle_response": PartEffectMeta("Throttle Response", "Response", True, order=13),
    "powertrain.cooling": PartEffectMeta("Engine Cooling", "Cooling", True, order=20),
    "powertrain.engine_reliability": PartEffectMeta("Engine Reliability", "Durability", True, order=21),
    "powertrain.engine_stress": PartEffectMeta("Engine Stress", "Engine Stress", False, order=22),
    "chassis.weight_kg": PartEffectMeta("Weight", "Weight", False, "kg", 30),
    "chassis.chassis_rigidity": PartEffectMeta("Chassis Rigidity", "Chassis", True, order=31),
    "tires.base_grip": PartEffectMeta("Dry Grip", "Grip", True, order=40),
    "tires.wet_grip": PartEffectMeta("Wet Grip", "Wet Grip", True, order=41),
    "tires.tire_wear_resistance": PartEffectMeta("Wear Resistance", "Wear", True, order=42),
    "tires.tire_heat_resistance": PartEffectMeta("Heat Resistance", "Heat", True, order=43),
    "tires.tire_warmup": PartEffectMeta("Warmup Time", "Warmup", False, order=44),
    "brakes.braking_power": PartEffectMeta("Braking Power", "Brakes", True, order=50),
    "brakes.brake_stability": PartEffectMeta("Brake Stability", "Brakes", True, order=51),
    "brakes.brake_cooling": PartEffectMeta("Brake Cooling", "Brakes", True, order=52),
    "brakes.brake_fade_resistance": PartEffectMeta("Fade Resistance", "Brakes", True, order=53),
    "suspension.handling": PartEffectMeta("Handling", "Handling", True, order=60),
    "suspension.mechanical_grip": PartEffectMeta("Mechanical Grip", "Grip", True, order=61),
    "suspension.suspension_compliance": PartEffectMeta("Compliance", "Compliance", True, order=62),
    "suspension.curb_handling": PartEffectMeta("Curb Handling", "Handling", True, order=63),
    "suspension.bump_absorption": PartEffectMeta("Bump Absorption", "Handling", True, order=64),
    "suspension.steering_precision": PartEffectMeta("Steering Precision", "Handling", True, order=65),
    "aero.downforce": PartEffectMeta("Downforce", "Aero", True, order=70),
    "aero.drag": PartEffectMeta("Drag", "Drag", False, order=71),
    "aero.aero_efficiency": PartEffectMeta("Aero Efficiency", "Aero", True, order=72),
    "aero.high_speed_stability": PartEffectMeta("High-Speed Stability", "Aero", True, order=73),
    "durability.overall_reliability": PartEffectMeta("Overall Reliability", "Durability", True, order=80),
    "durability.engine_reliability": PartEffectMeta("Engine Durability", "Durability", True, order=81),
    "durability.gearbox_reliability": PartEffectMeta("Gearbox Reliability", "Durability", True, order=82),
    "durability.suspension_durability": PartEffectMeta("Suspension Durability", "Durability", True, order=83),
    "durability.brake_durability": PartEffectMeta("Brake Durability", "Durability", True, order=84),
    "durability.cooling_capacity": PartEffectMeta("Cooling Capacity", "Cooling", True, order=85),
    "durability.mechanical_sympathy_modifier": PartEffectMeta("Mechanical Sympathy", "Durability", True, order=86),
    "fuel.fuel_capacity_l": PartEffectMeta("Fuel Capacity", "Fuel", True, "L", 90),
    "fuel.base_fuel_burn": PartEffectMeta("Fuel Burn", "Fuel Burn", False, order=91),
    "fuel.fuel_efficiency": PartEffectMeta("Fuel Efficiency", "Fuel", True, order=92),
}

PART_OVERRIDE_METADATA: dict[str, PartOverrideMeta] = {
    "tires.tire_compound": PartOverrideMeta("Tyre Compound", "Compound", 40),
    "powertrain.aspiration": PartOverrideMeta("Aspiration", "Engine", 14),
}

UNLOCK_CONTROL_LABELS: dict[str, str] = {
    "ecu": "Engine Map",
    "brake_controller": "Brake Balance",
    "custom_suspension": "Ride Height/Alignment",
    "custom_transmission": "Final Drive/Gear Bias",
    "custom_lsd": "Differential",
    "aero_kit": "Downforce",
}


def catalog_modifier_scale(parts: Iterable[Part]) -> dict[str, float]:
    scale: dict[str, float] = {}
    for part in parts:
        for path, delta in part.modifiers.items():
            scale[path] = max(scale.get(path, 0.0), abs(float(delta)))
    return scale


def modifier_effect(path: str, delta: int | float, catalog: Iterable[Part] | None = None) -> ModifierEffect:
    meta = _modifier_meta(path)
    scale = _catalog_scale(catalog).get(path, abs(float(delta)))
    polarity = _polarity(delta, meta.higher_is_better)
    return ModifierEffect(
        path=path,
        label=meta.label,
        theme=meta.theme,
        delta=delta,
        unit=meta.unit,
        polarity=polarity,
        intensity=_intensity(delta, scale),
        order=meta.order,
    )


def part_effect_display(part: Part, catalog: Iterable[Part] | None = None) -> PartEffectDisplay:
    catalog_tuple = tuple(catalog) if catalog is not None else None
    modifier_effects = [
        modifier_effect(path, delta, catalog_tuple)
        for path, delta in part.modifiers.items()
        if delta != 0
    ]
    improves = tuple(effect for effect in modifier_effects if effect.polarity == "improves")
    reduces = tuple(effect for effect in modifier_effects if effect.polarity == "reduces")
    numbers = tuple(
        OverrideEffect(
            path=path,
            label=_override_meta(path).label,
            theme=_override_meta(path).theme,
            value=value,
            order=_override_meta(path).order,
        )
        for path, value in part.overrides.items()
    )
    unlocks = tuple(_unlock_label(unlock) for unlock in part.unlocks)
    return PartEffectDisplay(
        improves=tuple(sorted(improves, key=lambda effect: effect.order)),
        reduces=tuple(sorted(reduces, key=lambda effect: effect.order)),
        numbers=tuple(sorted(numbers, key=lambda effect: effect.order)),
        unlocks=unlocks,
    )


def compact_part_effect_summary(part: Part, catalog: Iterable[Part] | None = None) -> str:
    display = part_effect_display(part, catalog)
    chunks: list[str] = []
    chunks.extend(_theme_chunks(display.improves, "+"))
    chunks.extend(_theme_chunks(display.reduces, "-"))
    chunks.extend(f"{effect.theme}: {_format_value(effect.value)}" for effect in display.numbers)
    chunks.extend(f"unlocks {label}" for label in display.unlocks)
    return "; ".join(chunks) if chunks else "No direct stat effect"


def readable_part_effect_rows(part: Part, catalog: Iterable[Part] | None = None) -> list[list[str]]:
    display = part_effect_display(part, catalog)
    rows: list[list[str]] = []
    if display.improves:
        rows.append(["Improves", _detail_text(display.improves)])
    if display.reduces:
        rows.append(["Reduces", _detail_text(display.reduces)])
    if display.numbers:
        rows.append(["Numbers", "; ".join(f"{effect.label}: {_format_value(effect.value)}" for effect in display.numbers)])
    if display.unlocks:
        rows.append(["Unlocks", ", ".join(f"unlocks {label}" for label in display.unlocks)])
    if not rows:
        rows.append(["Effect", "No direct stat effect"])
    return rows


def assert_catalog_display_metadata(parts: Iterable[Part]) -> None:
    missing_modifiers: set[str] = set()
    missing_overrides: set[str] = set()
    missing_unlocks: set[str] = set()
    for part in parts:
        missing_modifiers.update(path for path in part.modifiers if path not in PART_EFFECT_METADATA)
        missing_overrides.update(path for path in part.overrides if path not in PART_OVERRIDE_METADATA)
        missing_unlocks.update(unlock for unlock in part.unlocks if unlock not in UNLOCK_CONTROL_LABELS)
    problems: list[str] = []
    if missing_modifiers:
        problems.append("modifiers: " + ", ".join(sorted(missing_modifiers)))
    if missing_overrides:
        problems.append("overrides: " + ", ".join(sorted(missing_overrides)))
    if missing_unlocks:
        problems.append("unlocks: " + ", ".join(sorted(missing_unlocks)))
    if problems:
        raise AssertionError("Missing part effect display metadata for " + "; ".join(problems))


def _modifier_meta(path: str) -> PartEffectMeta:
    try:
        return PART_EFFECT_METADATA[path]
    except KeyError as exc:
        raise KeyError(f"Missing part effect display metadata for modifier {path!r}") from exc


def _override_meta(path: str) -> PartOverrideMeta:
    try:
        return PART_OVERRIDE_METADATA[path]
    except KeyError as exc:
        raise KeyError(f"Missing part effect display metadata for override {path!r}") from exc


def _unlock_label(unlock: str) -> str:
    try:
        return UNLOCK_CONTROL_LABELS[unlock]
    except KeyError as exc:
        raise KeyError(f"Missing part effect display metadata for unlock {unlock!r}") from exc


def _catalog_scale(catalog: Iterable[Part] | None) -> dict[str, float]:
    if catalog is not None:
        return catalog_modifier_scale(catalog)
    from game.loader import load_parts

    return catalog_modifier_scale(load_parts())


def _polarity(delta: int | float, higher_is_better: bool) -> str:
    if delta == 0:
        return "neutral"
    is_better = delta > 0 if higher_is_better else delta < 0
    return "improves" if is_better else "reduces"


def _intensity(delta: int | float, scale: float) -> int:
    if delta == 0:
        return 0
    if scale <= 0:
        return 1
    return 2 if abs(float(delta)) / scale >= 0.5 else 1


def _theme_chunks(effects: Iterable[ModifierEffect], sign: str) -> list[str]:
    grouped: dict[str, tuple[int, int]] = {}
    for effect in effects:
        order, intensity = grouped.get(effect.theme, (effect.order, 0))
        grouped[effect.theme] = (min(order, effect.order), max(intensity, effect.intensity))
    return [
        f"{theme} {sign * max(1, intensity)}"
        for theme, (_order, intensity) in sorted(grouped.items(), key=lambda item: item[1][0])
    ]


def _detail_text(effects: Iterable[ModifierEffect]) -> str:
    return "; ".join(_format_modifier(effect) for effect in effects)


def _format_modifier(effect: ModifierEffect) -> str:
    suffix = f" {effect.unit}" if effect.unit else ""
    return f"{effect.label} {effect.delta:+g}{suffix}"


def _format_value(value: int | float | str) -> str:
    if isinstance(value, str):
        return value.replace("_", " ").title()
    return f"{value:g}"
