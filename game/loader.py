from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, TypeVar

from constants import (
    CONDITION_MODIFIERS,
    CONDITION_NEUTRAL,
    ELEVATION_FACTOR_CEIL,
    ELEVATION_FACTOR_FLOOR,
    ELEVATION_FUEL_PER_M,
    ELEVATION_HEAT_PER_M,
    ELEVATION_REF_M,
    OVERTAKE_DIFFICULTY_TAG_DELTA,
    SEGMENT_TAG_RATES,
    SEGMENT_TAG_WEIGHTS,
    SURFACE_MODIFIERS,
    SURFACE_NEUTRAL,
    TRACK_LENGTH_TOLERANCE,
)
from game.models import (
    AeroStats,
    BrakeStats,
    Car,
    CarCondition,
    CarIdentity,
    ChassisStats,
    Driver,
    DurabilityStats,
    Event,
    FuelStats,
    Part,
    PowertrainStats,
    SegmentProfile,
    SuspensionStats,
    TireStats,
    Track,
    TrackSegment,
    TuneSetup,
)

WEIGHT_DIMS = ["power", "top_speed", "acceleration", "grip", "braking", "handling", "aero"]
RATE_NAMES = ["tire_wear", "fuel_burn", "engine_heat"]

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
T = TypeVar("T")


class DataLoadError(ValueError):
    """Raised when game data cannot be loaded or validated."""


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"Malformed JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise DataLoadError(f"Could not read {path}: {exc}") from exc


def _objects_from_dir(subdir: str, factory: Callable[[dict[str, Any], Path], T], data_root: Path = DATA_ROOT) -> list[T]:
    directory = data_root / subdir
    if not directory.exists():
        raise DataLoadError(f"Missing data directory: {directory}")

    loaded: list[T] = []
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path)
        rows = payload if isinstance(payload, list) else [payload]
        if not isinstance(rows, list):
            raise DataLoadError(f"Expected object or list in {path}")
        for row in rows:
            if not isinstance(row, dict):
                raise DataLoadError(f"Expected JSON object in {path}")
            loaded.append(factory(row, path))
    return loaded


def _dataclass_from_dict(cls: type[T], data: dict[str, Any], path: Path) -> T:
    names = {field.name for field in fields(cls)}
    missing = names.difference(data)
    if missing:
        raise DataLoadError(f"Missing fields for {cls.__name__} in {path}: {sorted(missing)}")
    try:
        return cls(**{name: data[name] for name in names})
    except TypeError as exc:
        raise DataLoadError(f"Invalid fields for {cls.__name__} in {path}: {exc}") from exc


def car_from_dict(data: dict[str, Any], path: Path | None = None) -> Car:
    source = path or Path("<memory>")
    try:
        identity_data = data.get("identity") or {
            "id": data["id"],
            "name": data["name"],
            "year": data["year"],
            "manufacturer": data["manufacturer"],
            "model": data["model"],
            "drivetrain": data["drivetrain"],
            "layout": data["layout"],
            "tags": data["tags"],
        }
        return Car(
            identity=_dataclass_from_dict(CarIdentity, identity_data, source),
            powertrain=_dataclass_from_dict(PowertrainStats, data["powertrain"], source),
            chassis=_dataclass_from_dict(ChassisStats, data["chassis"], source),
            tires=_dataclass_from_dict(TireStats, data["tires"], source),
            brakes=_dataclass_from_dict(BrakeStats, data["brakes"], source),
            suspension=_dataclass_from_dict(SuspensionStats, data["suspension"], source),
            aero=_dataclass_from_dict(AeroStats, data["aero"], source),
            durability=_dataclass_from_dict(DurabilityStats, data["durability"], source),
            fuel=_dataclass_from_dict(FuelStats, data["fuel"], source),
            condition=_dataclass_from_dict(CarCondition, data["condition"], source),
            installed_parts=list(data.get("installed_parts", [])),
            tune=_dataclass_from_dict(TuneSetup, data["tune"], source),
            value=data["value"],
        )
    except KeyError as exc:
        raise DataLoadError(f"Missing car field {exc!s} in {source}") from exc


def driver_from_dict(data: dict[str, Any], path: Path | None = None) -> Driver:
    return _dataclass_from_dict(Driver, data, path or Path("<memory>"))


def event_from_dict(data: dict[str, Any], path: Path | None = None) -> Event:
    source = path or Path("<memory>")
    event_data = dict(data)
    event_data.setdefault("rival_skill", None)
    for field_name in ("laps", "distance_km", "duration_s"):
        event_data.setdefault(field_name, None)
    specified = [name for name in ("laps", "distance_km", "duration_s") if event_data[name] is not None]
    if len(specified) != 1:
        raise DataLoadError(
            f"Event {event_data.get('id', '?')} in {source} must set exactly one race-length "
            f"field (laps, distance_km, or duration_s); found {specified or 'none'}"
        )
    return _dataclass_from_dict(Event, event_data, source)


def resolve_race(event: Event, track: Track) -> "RaceFormat":
    """Resolve an event's race length against a track into a concrete RaceFormat.

    Lap- and distance-based events yield a fixed lap target (distance is divided by the
    track's lap length). Duration-based events are returned open-ended; the race loop's
    time predicate will consume them once duration is wired in.
    """
    from game.models import RaceFormat

    if event.laps is not None:
        return RaceFormat(mode="laps", laps=max(1, int(event.laps)))
    if event.distance_km is not None:
        laps = max(1, round(event.distance_km / max(track.length_km, 1e-6)))
        return RaceFormat(mode="distance", laps=laps, distance_km=event.distance_km)
    if event.duration_s is not None:
        return RaceFormat(mode="duration", laps=None, duration_s=event.duration_s)
    # event_from_dict guarantees one is set; this guards programmatic Events.
    raise DataLoadError(f"Event {event.id} has no race-length specified")


def part_from_dict(data: dict[str, Any], path: Path | None = None) -> Part:
    return _dataclass_from_dict(Part, data, path or Path("<memory>"))


def _segment_tag_weights(segment: TrackSegment) -> dict[str, float]:
    contrib = {dim: 0.0 for dim in WEIGHT_DIMS}
    for tag in segment.tags:
        if tag not in SEGMENT_TAG_WEIGHTS:
            raise DataLoadError(f"Unknown segment tag: {tag}")
        for dim, value in SEGMENT_TAG_WEIGHTS[tag].items():
            contrib[dim] += value
    return contrib


def _segment_tag_rates(segment: TrackSegment) -> dict[str, float]:
    contrib = {rate: 0.0 for rate in RATE_NAMES}
    for tag in segment.tags:
        if tag not in SEGMENT_TAG_RATES:
            raise DataLoadError(f"Unknown segment tag: {tag}")
        for rate, value in SEGMENT_TAG_RATES[tag].items():
            contrib[rate] += value
    return contrib


def _segment_modifiers(segment: TrackSegment) -> tuple[float, float, float]:
    """Resolve (grip_mult, tire_wear_mult, wet_weight) from surface + condition.

    Unknown surface/condition strings fall back to the neutral baseline so existing
    free-form data keeps loading.
    """
    surface = SURFACE_MODIFIERS.get(segment.surface, SURFACE_NEUTRAL)
    condition = CONDITION_MODIFIERS.get(segment.condition, CONDITION_NEUTRAL)
    return (
        surface["grip"] * condition["grip"],
        surface["tire_wear"] * condition["tire_wear"],
        condition["wet_weight"],
    )


def derive_weights(segments: list[TrackSegment]) -> dict[str, float]:
    raw = {dim: 0.0 for dim in WEIGHT_DIMS}
    for segment in segments:
        for dim, value in _segment_tag_weights(segment).items():
            raw[dim] += segment.length_pct * value
    total = sum(raw.values()) or 1.0
    return {dim: value / total for dim, value in raw.items()}


def derive_rates(segments: list[TrackSegment]) -> dict[str, float]:
    rates = {rate: 0.0 for rate in RATE_NAMES}
    for segment in segments:
        contrib = _segment_tag_rates(segment)
        _, tire_wear_mult, _ = _segment_modifiers(segment)
        rates["tire_wear"] += segment.length_pct * contrib["tire_wear"] * tire_wear_mult
        rates["fuel_burn"] += segment.length_pct * contrib["fuel_burn"]
        rates["engine_heat"] += segment.length_pct * contrib["engine_heat"]
    return rates


def build_segment_profiles(segments: list[TrackSegment]) -> list[SegmentProfile]:
    """Per-segment, position-resolved profiles whose length-weighted sum reproduces
    the aggregate weights/rates (see SegmentProfile). The global ``total`` divisor is
    the same one derive_weights() normalizes by, which is what keeps the integral
    consistent so dry tarmac tracks behave identically to the aggregate model."""
    raw = {dim: 0.0 for dim in WEIGHT_DIMS}
    for segment in segments:
        for dim, value in _segment_tag_weights(segment).items():
            raw[dim] += segment.length_pct * value
    total = sum(raw.values()) or 1.0

    profiles: list[SegmentProfile] = []
    cursor = 0.0
    for segment in segments:
        contrib = _segment_tag_weights(segment)
        rates = _segment_tag_rates(segment)
        grip_mult, tire_wear_mult, wet_weight = _segment_modifiers(segment)
        start = cursor
        cursor += segment.length_pct
        profiles.append(
            SegmentProfile(
                name=segment.name,
                length_pct=segment.length_pct,
                start_pct=start,
                end_pct=cursor,
                surface=segment.surface,
                condition=segment.condition,
                weights={dim: contrib[dim] / total for dim in WEIGHT_DIMS},
                tire_wear_rate=rates["tire_wear"] * tire_wear_mult,
                fuel_burn_rate=rates["fuel_burn"],
                engine_heat_rate=rates["engine_heat"],
                grip_mult=grip_mult,
                tire_wear_mult=tire_wear_mult,
                wet_weight=wet_weight,
            )
        )
    return profiles


def _elevation_factor(elevation_m: float, per_m: float) -> float:
    """Bounded multiplier for elevation-driven fuel/heat load (1.0 at the reference)."""
    factor = 1.0 + (elevation_m - ELEVATION_REF_M) * per_m
    return max(ELEVATION_FACTOR_FLOOR, min(ELEVATION_FACTOR_CEIL, factor))


def track_from_dict(data: dict[str, Any], path: Path | None = None) -> Track:
    source = path or Path("<memory>")
    try:
        segments = [_dataclass_from_dict(TrackSegment, item, source) for item in data["segments"]]
    except KeyError as exc:
        raise DataLoadError(f"Missing track field {exc!s} in {source}") from exc

    length_total = sum(segment.length_pct for segment in segments)
    if abs(length_total - 1.0) > TRACK_LENGTH_TOLERANCE:
        raise DataLoadError(f"Track segment length_pct values in {source} sum to {length_total:.3f}, not 1.0")

    weights = derive_weights(segments)
    rates = derive_rates(segments)
    overtake = float(data["overtake_difficulty"])
    for segment in segments:
        for tag in segment.tags:
            overtake += OVERTAKE_DIFFICULTY_TAG_DELTA.get(tag, 0.0) * segment.length_pct
    overtake = max(0.0, min(1.0, overtake))

    # Sustained elevation change taxes fuel and engine heat. Applied uniformly to the
    # aggregate rates and to every segment profile so the segment-resolved race wears
    # the car identically to the aggregate model (the documented integration invariant).
    # Distance no longer scales these here -- attrition is resolved per-kilometre at race
    # time (see _apply_lap_wear), so a track's rates stay intensive tag multipliers.
    elevation = data["elevation_change_m"]
    elev_heat = _elevation_factor(elevation, ELEVATION_HEAT_PER_M)
    elev_fuel = _elevation_factor(elevation, ELEVATION_FUEL_PER_M)
    rates["engine_heat"] *= elev_heat
    rates["fuel_burn"] *= elev_fuel
    profiles = build_segment_profiles(segments)
    for profile in profiles:
        profile.engine_heat_rate *= elev_heat
        profile.fuel_burn_rate *= elev_fuel

    return Track(
        id=data["id"],
        name=data["name"],
        layout_type=data["layout_type"],
        base_lap_time=data["base_lap_time"],
        length_km=data["length_km"],
        pit_lane_loss_s=data["pit_lane_loss_s"],
        segments=segments,
        overtake_difficulty=overtake,
        elevation_change_m=data["elevation_change_m"],
        surface=data["surface"],
        default_condition=data["default_condition"],
        weather_variability=data["weather_variability"],
        power_weight=weights["power"],
        acceleration_weight=weights["acceleration"],
        top_speed_weight=weights["top_speed"],
        grip_weight=weights["grip"],
        braking_weight=weights["braking"],
        handling_weight=weights["handling"],
        aero_weight=weights["aero"],
        tire_wear_rate=rates["tire_wear"],
        fuel_burn_rate=rates["fuel_burn"],
        engine_heat_rate=rates["engine_heat"],
        segment_profiles=profiles,
    )


def load_cars(data_root: Path = DATA_ROOT) -> list[Car]:
    return _objects_from_dir("cars", car_from_dict, data_root)


def load_drivers(data_root: Path = DATA_ROOT) -> list[Driver]:
    return _objects_from_dir("drivers", driver_from_dict, data_root)


def load_tracks(data_root: Path = DATA_ROOT) -> list[Track]:
    return _objects_from_dir("tracks", track_from_dict, data_root)


def load_events(data_root: Path = DATA_ROOT) -> list[Event]:
    return _objects_from_dir("events", event_from_dict, data_root)


def load_parts(data_root: Path = DATA_ROOT) -> list[Part]:
    return _objects_from_dir("parts", part_from_dict, data_root)


def load_all_data(data_root: Path = DATA_ROOT) -> dict[str, list[Any]]:
    return {
        "cars": load_cars(data_root),
        "drivers": load_drivers(data_root),
        "tracks": load_tracks(data_root),
        "events": load_events(data_root),
        "parts": load_parts(data_root),
    }
