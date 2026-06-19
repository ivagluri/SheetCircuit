from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from constants import SCHEMA_VERSION
from game.game_state import GameState
from game.loader import DataLoadError, car_from_dict, driver_from_dict


class SaveVersionError(ValueError):
    """Raised when a save file has an unsupported schema version."""


def game_state_to_dict(game_state: GameState) -> dict[str, Any]:
    return {
        "money": game_state.money,
        "week": game_state.week,
        "garage": [asdict(car) for car in game_state.garage],
        "hired_drivers": [asdict(driver) for driver in game_state.hired_drivers],
    }


def game_state_from_dict(data: dict[str, Any]) -> GameState:
    return GameState(
        money=data["money"],
        week=data["week"],
        garage=[car_from_dict(car_data) for car_data in data.get("garage", [])],
        hired_drivers=[driver_from_dict(driver_data) for driver_data in data.get("hired_drivers", [])],
    )


def save_game(game_state: GameState, path: str | Path) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "game_state": game_state_to_dict(game_state),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_game(path: str | Path) -> GameState:
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"Malformed save JSON in {source}: {exc}") from exc
    except OSError as exc:
        raise DataLoadError(f"Could not read save {source}: {exc}") from exc

    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SaveVersionError(f"Unsupported save schema_version {version}; expected {SCHEMA_VERSION}")
    return game_state_from_dict(payload["game_state"])
