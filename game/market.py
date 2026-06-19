from __future__ import annotations

from game.loader import load_cars
from game.models import Car


def list_market_cars() -> list[Car]:
    return load_cars()
