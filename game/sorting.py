from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

from constants import CLASS_THRESHOLDS
from game.effective_stats import class_rating
from game.models import Car, Driver, Event

T = TypeVar("T")

CLASS_ORDER = {class_name: index for index, class_name in enumerate(CLASS_THRESHOLDS)}


@dataclass(frozen=True)
class SortOption:
    key: str
    label: str
    getter: Callable[[Any], Any]
    default_descending: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SortSpec:
    key: str
    descending: bool


def sort_items(screen: str, items: Iterable[T], spec: SortSpec | None) -> list[T]:
    rows = list(items)
    if spec is None:
        return rows
    option = _option_for(screen, spec.key)
    return sorted(
        rows,
        key=lambda item: (_normalized_sort_value(option.getter(item)), _identity_tiebreaker(item)),
        reverse=spec.descending,
    )


def parse_sort_spec(screen: str, field: str, direction: str | None = None) -> SortSpec:
    normalized_field = field.strip().lower()
    descending_override = None
    if normalized_field.startswith("-"):
        normalized_field = normalized_field[1:]
        descending_override = True
    elif normalized_field.startswith("+"):
        normalized_field = normalized_field[1:]
        descending_override = False

    option = _option_for(screen, normalized_field)
    descending = option.default_descending if descending_override is None else descending_override
    if direction is not None:
        normalized_direction = direction.strip().lower()
        if normalized_direction in {"asc", "ascending", "up", "low", "lowest", "cheap", "cheapest"}:
            descending = False
        elif normalized_direction in {"desc", "descending", "down", "high", "highest", "expensive"}:
            descending = True
        else:
            raise ValueError(f"Unknown sort direction: {direction}")
    return SortSpec(option.key, descending)


def sort_label(screen: str, spec: SortSpec | None) -> str:
    if spec is None:
        return "Default"
    option = _option_for(screen, spec.key)
    arrow = "desc" if spec.descending else "asc"
    return f"{option.label} {arrow}"


def sort_fields(screen: str) -> list[str]:
    return [option.key for option in _options_for(screen)]


def is_sortable_screen(screen: str) -> bool:
    return screen in _SORT_OPTIONS


def _option_for(screen: str, field: str) -> SortOption:
    normalized_screen = screen.strip().lower()
    normalized_field = field.strip().lower()
    for option in _options_for(normalized_screen):
        names = {option.key, *option.aliases}
        if normalized_field in names:
            return option
    valid = ", ".join(sort_fields(normalized_screen))
    raise ValueError(f"Cannot sort {screen} by {field!r}. Try: {valid}")


def _options_for(screen: str) -> list[SortOption]:
    normalized_screen = screen.strip().lower()
    if normalized_screen not in _SORT_OPTIONS:
        raise ValueError(f"Screen does not support sorting: {screen}")
    return _SORT_OPTIONS[normalized_screen]


def _normalized_sort_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.casefold()
    return value


def _identity_tiebreaker(item: Any) -> str:
    if isinstance(item, Car):
        return item.identity.id
    if isinstance(item, Driver):
        return item.id
    if isinstance(item, Event):
        return item.id
    return repr(item)


def _class_rank(class_name: str) -> int:
    return CLASS_ORDER.get(class_name, -1)


_CAR_SORT_OPTIONS = [
    SortOption("name", "Name", lambda car: car.identity.name, aliases=("car",)),
    SortOption("class", "Class", lambda car: _class_rank(car.identity.car_class), True, ("tier",)),
    SortOption("rating", "PR", class_rating, True, ("pr", "score")),
    SortOption("hp", "HP", lambda car: car.powertrain.power_hp, True, ("power", "horsepower")),
    SortOption("torque", "Torque", lambda car: car.powertrain.torque_nm, True, ("nm",)),
    SortOption("price", "Price", lambda car: car.value, aliases=("value", "cost")),
    SortOption("condition", "Condition", lambda car: car.condition.overall_condition, True, ("cond", "health")),
    SortOption("weight", "Weight", lambda car: car.chassis.weight_kg, aliases=("mass",)),
    SortOption("mileage", "Mileage", lambda car: car.condition.mileage, aliases=("km", "odo", "odometer")),
    SortOption("year", "Year", lambda car: car.identity.year, True),
]

_DRIVER_SORT_OPTIONS = [
    SortOption("name", "Name", lambda driver: driver.name),
    SortOption("pace", "Pace", lambda driver: driver.pace, True),
    SortOption("consistency", "Consistency", lambda driver: driver.consistency, True, ("cons",)),
    SortOption("racecraft", "Racecraft", lambda driver: driver.racecraft, True, ("craft",)),
    SortOption("feedback", "Feedback", lambda driver: driver.feedback, True),
    SortOption("fitness", "Fitness", lambda driver: driver.fitness, True),
    SortOption("aggression", "Aggression", lambda driver: driver.aggression, True),
    SortOption(
        "sympathy",
        "Mechanical Sympathy",
        lambda driver: driver.mechanical_sympathy,
        True,
        ("mechanical", "mechanical_sympathy", "mech"),
    ),
    SortOption("wet", "Wet Skill", lambda driver: driver.wet_skill, True, ("wet_skill",)),
    SortOption("salary", "Salary", lambda driver: driver.salary, aliases=("cost", "pay")),
    SortOption("experience", "Experience", lambda driver: driver.experience, True, ("xp",)),
]

_EVENT_SORT_OPTIONS = [
    SortOption("name", "Name", lambda event: event.name),
    SortOption("class", "Class", lambda event: _class_rank(event.car_class_limit), True, ("tier", "limit")),
    SortOption("fee", "Entry Fee", lambda event: event.entry_fee, aliases=("entry", "price", "cost")),
    SortOption("prize", "Top Prize", lambda event: event.prize_money[0] if event.prize_money else 0, True),
    SortOption("opponents", "Opponents", lambda event: event.opponent_count, True, ("opp",)),
]

_SORT_OPTIONS = {
    "garage": _CAR_SORT_OPTIONS,
    "market": _CAR_SORT_OPTIONS,
    "drivers": _DRIVER_SORT_OPTIONS,
    "events": _EVENT_SORT_OPTIONS,
}
