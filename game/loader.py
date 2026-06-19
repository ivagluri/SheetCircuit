from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, TypeVar

from constants import (
    OVERTAKE_DIFFICULTY_TAG_DELTA,
    SEGMENT_TAG_RATES,
    SEGMENT_TAG_WEIGHTS,
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
    SuspensionStats,
    TireStats,
    Track,
    TrackSegment,
    TuneSetup,
)

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
            "car_class": data["car_class"],
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
    return _dataclass_from_dict(Event, data, path or Path("<memory>"))


def part_from_dict(data: dict[str, Any], path: Path | None = None) -> Part:
    return _dataclass_from_dict(Part, data, path or Path("<memory>"))


def derive_weights(segments: list[TrackSegment]) -> dict[str, float]:
    dims = ["power", "top_speed", "acceleration", "grip", "braking", "handling", "aero"]
    raw = {dim: 0.0 for dim in dims}
    for segment in segments:
        for tag in segment.tags:
            if tag not in SEGMENT_TAG_WEIGHTS:
                raise DataLoadError(f"Unknown segment tag: {tag}")
            for dim, contribution in SEGMENT_TAG_WEIGHTS[tag].items():
                raw[dim] += segment.length_pct * contribution
    total = sum(raw.values()) or 1.0
    return {dim: value / total for dim, value in raw.items()}


def derive_rates(segments: list[TrackSegment]) -> dict[str, float]:
    rates = {"tire_wear": 0.0, "fuel_burn": 0.0, "engine_heat": 0.0}
    for segment in segments:
        for tag in segment.tags:
            if tag not in SEGMENT_TAG_RATES:
                raise DataLoadError(f"Unknown segment tag: {tag}")
            for rate, contribution in SEGMENT_TAG_RATES[tag].items():
                rates[rate] += segment.length_pct * contribution
    return rates


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

    return Track(
        id=data["id"],
        name=data["name"],
        layout_type=data["layout_type"],
        base_lap_time=data["base_lap_time"],
        laps=data["laps"],
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
