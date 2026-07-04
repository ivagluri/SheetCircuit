"""Events chapter.

Harvests the flattened event draft fields from ``editor.fields.EVENT_SECTIONS``
(Event / Race Length / Restrictions). These are all creator-authored; there is
no in-game event editor. The draft carries ``race_mode``/``race_value`` and
``restr_*`` knobs which ``editor.app`` translates to the stored event JSON —
the compendium documents the draft-level knobs the user actually sets.
"""

from __future__ import annotations

from typing import Any

from editor.fields import EVENT_SECTIONS
from compendium.harvest import entry_from_spec
from compendium.model import Chapter, Section

DOMAIN = "event"
_EDITABLE = ("creator",)

CHAPTER_INTRO: str = (
    "An event is a race defined on a track: who may enter, how long it runs, how big "
    "the field is, and what it pays. There are no event presets — you build each one "
    "from scratch. The creator exposes a few flattened knobs (a single race-length "
    "mode/value and optional restrictions) that are translated into the stored event "
    "on save; this chapter documents those knobs as you set them."
)

SECTION_INTROS: dict[str, str] = {
    "Event": (
        "The core definition: the host track, who is eligible (class limit and team "
        "level), the progression kind, the size of the rival field, and the money — "
        "entry fee in, prize money out."
    ),
    "Race Length": (
        "How long the race runs. Choose exactly one form — a lap count, a distance in "
        "km, or a duration in seconds — and give its value; the loader resolves it "
        "against the track's lap length."
    ),
    "Restrictions (optional)": (
        "Optional eligibility caps that shape what kind of car can enter — a spec floor "
        "for the field. Every cap defaults to 0/empty, meaning 'no restriction'."
    ),
}

FIELD_CONTENT: dict[str, dict[str, Any]] = {
    # --- Event ---
    "event.id": {"effect": "Filename slug identifying the event."},
    "event.name": {"effect": "Display name shown in the event list, e.g. 'Maple Weekender'."},
    "event.track_id": {"effect": "Which track hosts the race (an existing track id)."},
    "event.car_class_limit": {"effect": "Highest car class allowed to enter (E through S)."},
    "event.min_team_level": {"effect": "Team level required before you can enter."},
    "event.event_kind": {"effect": "ladder = counts toward progression; open_invitational = a one-off."},
    "event.entry_fee": {"effect": "Cost to enter the race.", "units": "$"},
    "event.opponent_count": {"effect": "Number of rival cars making up the field."},
    "event.prize_money": {"effect": "Payouts by finishing position, as a comma-separated list.", "units": "$"},
    "event.rival_skill": {"effect": "0 = use the class default rival skill; 1-100 overrides it."},
    # --- Race Length ---
    "event.race_mode": {
        "effect": "Which race-length form is used: laps, distance_km, or duration_s.",
        "prose": (
            "Exactly one race-length form applies. 'laps' runs a fixed number of laps; 'distance_km' runs "
            "until a total distance is covered (resolved against the track's lap length); 'duration_s' is "
            "a time-capped enduro. race_value carries the number for whichever mode you pick."
        ),
    },
    "event.race_value": {"effect": "The number for the chosen race_mode: lap count, race km, or seconds."},
    # --- Restrictions ---
    "event.restr_max_power_hp": {"effect": "Power cap; cars over this many hp cannot enter. 0 = no cap.", "units": "hp"},
    "event.restr_max_class_rating": {"effect": "Class-rating cap; cars above it cannot enter. 0 = no cap."},
    "event.restr_max_weight_kg": {"effect": "Weight cap; cars heavier than this cannot enter. 0 = no cap.", "units": "kg"},
    "event.restr_max_overall_condition": {
        "effect": "Condition ceiling; cars in better shape than this % are excluded. 0 = no cap.",
        "prose": (
            "A ceiling, not a floor: it keeps pristine cars out, which is how 'beater' events force a "
            "field of well-worn machinery. Set to the maximum overall condition a car may have to enter."
        ),
        "units": "%",
    },
    "event.restr_allowed_tires": {"effect": "Permitted tyre compounds; empty = any compound allowed."},
}


def build_chapter() -> Chapter:
    sections: list[Section] = []
    for section in EVENT_SECTIONS:
        entries = tuple(
            entry_from_spec(
                spec,
                domain=DOMAIN,
                section_title=section.title,
                id_prefix=DOMAIN,
                editable_in=_EDITABLE,
                authored=FIELD_CONTENT,
            )
            for spec in section.fields
        )
        sections.append(
            Section(title=section.title, intro=SECTION_INTROS.get(section.title, ""), entries=entries)
        )
    return Chapter(id="events", title="Events", intro=CHAPTER_INTRO, sections=tuple(sections))
