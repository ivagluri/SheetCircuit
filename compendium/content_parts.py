"""Parts chapter.

Documents the career upgrade model and generates a row for every part and slot
from the live catalog. This keeps the compendium aligned with ``data/parts`` and
the slot rules in ``game.parts``.
"""

from __future__ import annotations

from game.loader import load_parts
from game.parts import SLOT_RULES, TUNE_UNLOCK_LABELS
from compendium.model import Chapter, Entry, Section

DOMAIN = "part"

CHAPTER_INTRO = (
    "Parts are owned per car. Buying a part permanently adds it to that car's "
    "owned_parts list; installing an owned part is free and makes it the active "
    "effect in its slot. Unequipping removes the active slot effect and returns "
    "the car to stock for that slot. There are no refunds."
)

MODEL_INTRO = (
    "Owned and installed are separate. A car can own several parts in a slot, but "
    "only one part per slot is installed at a time. Staged parts are cumulative: "
    "Stage 2 stores the total Stage 1+2 effect, Stage 3 stores the total Stage "
    "1+2+3 effect, and the next stage requires the previous stage to be owned."
)

SLOTS_INTRO = (
    "Slots define replacement rules. Staged slots progress in order; equipment "
    "slots such as tyres and adjustable controllers are exclusive choices. "
    "Installing a part replaces whatever was active in the same slot."
)

CATALOG_INTRO = (
    "Tyre parts change compound through overrides and numeric grip/wear/heat "
    "tradeoffs. Fuel cells increase range at a weight cost. Adjustable hardware "
    "unlocks Tune controls: ECU maps, brake balance, suspension, transmission, "
    "LSD, and downforce."
)


def build_chapter() -> Chapter:
    return Chapter(
        id="parts",
        title="Parts",
        intro=CHAPTER_INTRO,
        sections=(
            _model_section(),
            _slots_section(),
            _catalog_section(),
        ),
    )


def _model_section() -> Section:
    entries = (
        Entry(
            id="part.model.owned_parts",
            domain=DOMAIN,
            section="Ownership Model",
            label="Owned Parts",
            effect_summary="Permanent per-car inventory; buying adds here and never refunds.",
            prose="Owned parts can be installed, removed, and reinstalled for free on the car that bought them.",
            editable_in=("upgrades",),
        ),
        Entry(
            id="part.model.installed_parts",
            domain=DOMAIN,
            section="Ownership Model",
            label="Installed Parts",
            effect_summary="Currently equipped slot effects; only installed parts affect stats and class.",
            prose="Unequipping removes the active effect for that slot and returns it to stock with no refund.",
            editable_in=("upgrades",),
        ),
        Entry(
            id="part.model.staged_cumulative",
            domain=DOMAIN,
            section="Ownership Model",
            label="Staged Cumulative Parts",
            effect_summary="Only one stage is installed; higher-stage modifiers already include lower stages.",
            prose="Stage N+1 requires owning Stage N, but Stage N does not need to be installed at purchase time.",
            editable_in=("upgrades",),
        ),
    )
    return Section("Ownership Model", MODEL_INTRO, entries)


def _slots_section() -> Section:
    entries = tuple(
        Entry(
            id=f"part.slot.{rule.id}",
            domain=DOMAIN,
            section="Slots",
            label=rule.label,
            effect_summary=("Staged slot. " if rule.staged else "Exclusive slot. ") + rule.description,
            prose=rule.description,
            editable_in=("upgrades",),
        )
        for rule in SLOT_RULES
    )
    return Section("Slots", SLOTS_INTRO, entries)


def _catalog_section() -> Section:
    entries = tuple(
        Entry(
            id=f"part.{part.id}",
            domain=DOMAIN,
            section="Catalog",
            label=part.name,
            units="$",
            value_range=(part.cost, part.cost),
            effect_summary=_part_summary(part),
            prose=_part_prose(part),
            editable_in=("upgrades",),
        )
        for part in load_parts()
    )
    return Section("Catalog", CATALOG_INTRO, entries)


def _part_summary(part) -> str:
    chunks = [f"Slot {part.slot}"]
    if part.stage:
        chunks.append(f"stage {part.stage}")
    if part.overrides:
        chunks.extend(f"{path}={value}" for path, value in part.overrides.items())
    if part.unlocks:
        chunks.append("unlocks " + ", ".join(TUNE_UNLOCK_LABELS.get(key, key) for key in part.unlocks))
    if part.modifiers:
        chunks.append(", ".join(f"{path} {delta:+g}" for path, delta in part.modifiers.items()))
    return "; ".join(chunks)


def _part_prose(part) -> str:
    if part.slot == "tires":
        return "Tyre compounds are installed as parts, not selected in Tune; the override sets the compound."
    if part.slot == "fuel_cell":
        return "Adds real tank range at a weight cost; it changes pit strategy rather than raw burn rate."
    if part.unlocks:
        labels = ", ".join(TUNE_UNLOCK_LABELS.get(key, key) for key in part.unlocks)
        return f"Installed hardware unlocks Tune controls for: {labels}."
    if part.stage > 1:
        return "Cumulative staged effect; it replaces the lower stage in the same slot when installed."
    return ""
