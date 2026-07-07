"""Cars chapter.

Harvests every car field from ``editor.fields.CAR_SECTIONS`` (skipping the
curated "Basics" front-door section, which only re-lists paths owned by the
detailed sections below it). Ranges/choices come straight from the schema;
per-subsystem intros and per-field prose/ideal/effect live in the authored
tables below, consolidated from the rationale comments in ``constants.py`` and
the field-help strings in ``editor.fields``.

The ``editable_in`` tag is derived, not hand-maintained: a car field is
tune-menu-editable iff it is one of the setup knobs exposed by the in-game Tune
menu. Permanent hardware/stat changes live in Upgrades. Everything in the
creator schema is creator-editable.
"""

from __future__ import annotations

from typing import Any

from game.parts import TUNE_MENU_FIELD_NAMES
from editor.fields import CAR_ARCHETYPES, CAR_SECTIONS
from compendium.harvest import entry_from_spec, slug
from compendium.model import Chapter, Entry, Section

DOMAIN = "car"
_SKIP_SECTIONS = {"Basics"}
_PRESET_SECTION = "Presets (Quick Setup)"


def _tune_section_keys() -> tuple[str, ...]:
    """The 22 TuneSetup knobs, read from the creator schema's Tune section."""
    tune = next(s for s in CAR_SECTIONS if s.title == "Tune")
    return tuple(spec.key for spec in tune.fields)


TUNE_SECTION_KEYS: tuple[str, ...] = _tune_section_keys()
_TUNE_MENU_KEYS = set(TUNE_MENU_FIELD_NAMES)


def _editable_in(spec) -> tuple[str, ...]:
    tags = ["creator"]
    if spec.key in _TUNE_MENU_KEYS:
        tags.append("tune_menu")
    return tuple(tags)


CHAPTER_INTRO: str = (
    "A car is described by many stats, but you rarely set them by hand: pick one of "
    "the five archetypes below in the creator and adjust from there. Most stats are "
    "intrinsic to how the car is *built* and are set only in the creator (engine, "
    "weight, durability, fuel hardware). In career play, Upgrades buys and equips "
    "hardware, while Tune adjusts setup knobs unlocked by that hardware; those setup "
    "rows are marked \"tune_menu\" in the Editable column. Three screens show overlapping slices of "
    "this data: the car detail screen is a quick overview (power, weight, drivetrain, "
    "condition); the extended spec sheet (\"ext\") lists every stat below; and the "
    "in-game Tune menu shows only the garage-tweakable subset. Read each row as: what "
    "it controls (Effect), its range and units, and — for tune knobs — the neutral "
    "\"ideal\" value that neither helps nor hurts, so a stock setup is neutral and "
    "only tuning away from it moves performance."
)

SECTION_INTROS: dict[str, str] = {
    _PRESET_SECTION: (
        "The fast path. Each archetype is a complete, balanced starting car you can "
        "race as-is or fine-tune; they are intrinsic designs, not copies of catalog "
        "cars. If you do not want to touch individual stats, start here."
    ),
    "Identity": (
        "Naming and cataloguing fields plus a couple of descriptors that do carry "
        "weight. Most of this section is flavour (name, manufacturer, year), but "
        "drivetrain has a real sim effect and tags can change how a car is classified."
    ),
    "Powertrain": (
        "The engine build — set only in the creator. Peak power and torque are the "
        "headline numbers; the supporting ratings (powerband, throttle response) nudge "
        "acceleration, while cooling and stress feed how hard the engine runs and how "
        "reliably it holds together."
    ),
    "Chassis": (
        "The car's mass and how it is carried. Weight is the single most universal "
        "stat — lighter is quicker everywhere — and weight distribution plus the "
        "handling-oriented ratings decide how planted and eager the car feels."
    ),
    "Tires": (
        "The contact patch: compound and width set the raw grip on offer, while the "
        "resistance ratings decide how long that grip lasts before wear and heat erode "
        "it. In career, compound changes are bought as tyre parts in Upgrades; grip is "
        "a primary cornering axis."
    ),
    "Brakes": (
        "Stopping performance and how it holds up over a stint. Braking power is the "
        "primary axis; cooling and fade resistance keep it consistent as the brakes "
        "heat up under repeated use."
    ),
    "Suspension": (
        "How the car puts its grip down and responds to inputs. Handling and mechanical "
        "grip are the primary axes; the remaining ratings are smaller composure aids "
        "that reward a well-rounded setup."
    ),
    "Aero": (
        "The trade-off between cornering grip and straight-line speed. Downforce buys "
        "high-speed grip at the cost of drag; efficiency softens that cost and stability "
        "lends a little top-speed confidence."
    ),
    "Durability": (
        "Build-quality ratings that feed in-race failure risk — set in the creator. "
        "Higher numbers mean fewer mechanical retirements; the sympathy modifier is a "
        "small overall bias on top of the per-system ratings."
    ),
    "Fuel": (
        "The fuel system. Capacity sets how far the car runs between stops; the burn "
        "hardware and efficiency rating decide how fast the tank empties."
    ),
    "Condition": (
        "Wear state, not a design choice: 100 is factory-fresh. You can set it in the "
        "creator, but in-game it degrades as the car races and is restored by repairs. "
        "Low condition quietly saps performance and reliability."
    ),
    "Tune": (
        "The setup sheet — adjustable both in the creator and, where hardware allows, "
        "the in-game Tune menu, with no lasting cost. Tyre pressures are always "
        "available; ECU maps, brake balance, suspension geometry, gearing, LSD, and "
        "downforce require installed adjustable parts."
    ),
}

# Per-field authored content, keyed by full Entry.id.
#   effect:  one-line summary (table row + inline Help column) — required
#   ideal:   neutral value where one exists (mostly tune knobs)
#   units:   physical unit for the Units column (omitted for pure 0-100 ratings)
#   prose:   longer explanation — only for genuinely non-obvious fields
#   source:  dev provenance (constants symbol) — not shown to players
FIELD_CONTENT: dict[str, dict[str, Any]] = {
    # --- Identity ---
    "car.id": {"effect": "Filename slug identifying the car in data and saves; no on-track effect."},
    "car.name": {"effect": "Display name shown across menus and results; no on-track effect."},
    "car.year": {"effect": "Era label; flavour only, no performance effect."},
    "car.manufacturer": {"effect": "Marque label; flavour only, no performance effect."},
    "car.model": {"effect": "Model label; flavour only, no performance effect."},
    "car.drivetrain": {
        "effect": "AWD claws back grip — most of all on wet/gravel; RWD and FWD are neutral.",
        "source": "constants.py:424 AWD_GRIP_BONUS / AWD_LOWGRIP_BONUS",
    },
    "car.layout": {"effect": "Engine placement descriptor (front/mid/rear); flavour, no direct axis effect."},
    "car.tags": {"effect": "Free descriptors; 'challenge'/'joke' force the Challenge shape, the rest are cosmetic."},
    "car.value": {"effect": "Market price for buying and selling; no on-track effect.", "units": "$"},
    # --- Powertrain ---
    "car.powertrain.power_hp": {"effect": "Peak power — the main driver of top speed and the power axis.", "units": "hp"},
    "car.powertrain.torque_nm": {
        "effect": "Pulling force; its ratio to power (~1.25 neutral) shapes acceleration.",
        "units": "Nm",
        "prose": (
            "Acceleration keys off the torque-to-power ratio, not torque alone. A ratio near 1.25 is "
            "neutral; more torque per horsepower sharpens low-end punch, less makes a peaky, "
            "high-revving engine."
        ),
        "source": "constants.py:465 TORQUE_RATIO_REF",
    },
    "car.powertrain.powerband": {"effect": "Breadth of usable power; higher is a small acceleration aid (neutral 50)."},
    "car.powertrain.throttle_response": {"effect": "Crispness of pickup; higher is a small acceleration aid (neutral 50)."},
    "car.powertrain.engine_reliability": {"effect": "Engine build quality; higher lowers in-race engine-failure risk."},
    "car.powertrain.cooling": {"effect": "Higher sheds engine heat faster, easing overheating and stress."},
    "car.powertrain.aspiration": {"effect": "Induction type (NA/turbo/supercharged); descriptor, no direct axis effect."},
    "car.powertrain.engine_stress": {
        "effect": "How hard the engine is worked by design; higher stress cuts reliability.",
        "source": "constants.py:442 STRESS_RELIABILITY_PENALTY",
    },
    # --- Chassis ---
    "car.chassis.weight_kg": {"effect": "Lighter is quicker everywhere — accel, braking, handling (~1100 kg reference).", "units": "kg", "source": "constants.py:439 WEIGHT_REFERENCE_KG"},
    "car.chassis.weight_distribution_front": {
        "effect": "Front mass fraction; deviation from 0.52 hurts handling.",
        "ideal": 0.52,
        "prose": (
            "A near-50/50 balance (0.52 front) handles best. Nose- or tail-heavy cars pay a handling "
            "penalty that grows with the deviation, so this is a genuine sweet spot rather than a "
            "'higher is better' rating."
        ),
        "source": "constants.py:481 WEIGHT_DIST_IDEAL",
    },
    "car.chassis.center_of_gravity": {"effect": "Rating where higher = lower CoG = better handling (neutral 50)."},
    "car.chassis.chassis_rigidity": {"effect": "Stiffer shell sharpens handling response (neutral 50)."},
    "car.chassis.stability": {"effect": "High-speed composure; blends slightly into top-speed confidence (neutral 50)."},
    "car.chassis.rotation": {"effect": "Eagerness to turn in; higher aids handling (neutral 50)."},
    # --- Tires ---
    "car.tires.tire_compound": {"effect": "Grippier compounds are quicker but wear faster; also gates event tyre limits."},
    "car.tires.tire_width_front": {"effect": "Wider adds grip but wears and heats slightly more (~205 mm reference).", "units": "mm", "source": "constants.py:486 TIRE_WIDTH_FRONT_REF"},
    "car.tires.tire_width_rear": {"effect": "Wider adds grip but wears and heats slightly more (~225 mm reference).", "units": "mm", "source": "constants.py:487 TIRE_WIDTH_REAR_REF"},
    "car.tires.base_grip": {"effect": "Dry mechanical grip — a primary cornering and braking axis."},
    "car.tires.wet_grip": {"effect": "Grip on damp/wet segments; blended in by conditions and driver wet skill."},
    "car.tires.tire_wear_resistance": {"effect": "Higher slows tyre wear over a stint."},
    "car.tires.tire_heat_resistance": {"effect": "Higher resists overheating the tyres under sustained load."},
    "car.tires.tire_warmup": {"effect": "Higher warms tyres in faster but climbs toward peak heat sooner.", "source": "constants.py:491 TIRE_WARMUP_HEAT_PER_UNIT"},
    # --- Brakes ---
    "car.brakes.braking_power": {"effect": "Primary braking axis — raw stopping capability."},
    "car.brakes.brake_stability": {"effect": "Composure under braking; a small blend into the braking axis."},
    "car.brakes.brake_cooling": {"effect": "Higher sheds brake heat, resisting fade over a stint."},
    "car.brakes.brake_fade_resistance": {"effect": "Higher keeps braking consistent as the brakes heat up."},
    # --- Suspension ---
    "car.suspension.handling": {"effect": "Primary handling axis — raw cornering capability."},
    "car.suspension.mechanical_grip": {"effect": "Low-speed grip; blends into the grip axis."},
    "car.suspension.suspension_compliance": {"effect": "Soaks up bumps and kerbs; small handling aid (neutral 50)."},
    "car.suspension.curb_handling": {"effect": "Composure over kerbs; small handling aid (neutral 50)."},
    "car.suspension.bump_absorption": {"effect": "Damping over bumps; small handling aid (neutral 50)."},
    "car.suspension.steering_precision": {"effect": "Accuracy of turn-in; small handling aid (neutral 50)."},
    # --- Aero ---
    "car.aero.downforce": {"effect": "Base aero grip in high-speed corners; pairs with drag."},
    "car.aero.drag": {"effect": "Aerodynamic resistance — directly costs top speed."},
    "car.aero.aero_efficiency": {"effect": "Grip per unit drag; higher trims effective drag (neutral 50)."},
    "car.aero.high_speed_stability": {"effect": "Composure at speed; a small blend into top speed."},
    # --- Durability ---
    "car.durability.overall_reliability": {"effect": "Baseline mechanical robustness feeding overall failure risk."},
    "car.durability.engine_reliability": {"effect": "Engine-specific robustness feeding failure risk (durability build quality)."},
    "car.durability.gearbox_reliability": {"effect": "Gearbox robustness; higher lowers gearbox-failure risk."},
    "car.durability.suspension_durability": {"effect": "Suspension robustness across a stint."},
    "car.durability.brake_durability": {"effect": "Brake-system robustness across a stint."},
    "car.durability.cooling_capacity": {"effect": "Cooling headroom; resists heat-driven failures."},
    "car.durability.mechanical_sympathy_modifier": {"effect": "Design bias (~-4..15) nudging overall failure risk up or down.", "source": "constants.py:547 MECH_SYMPATHY_MOD_PER_UNIT"},
    # --- Fuel ---
    "car.fuel.fuel_capacity_l": {"effect": "Tank size; sets how far the car runs between stops.", "units": "L"},
    "car.fuel.base_fuel_burn": {"effect": "Baseline consumption hardware; higher drinks more fuel."},
    "car.fuel.fuel_efficiency": {"effect": "Higher trims fuel burn (neutral 50).", "source": "constants.py:561 FUEL_EFFICIENCY_BURN_PER_UNIT"},
    # --- Condition ---
    "car.condition.overall_condition": {"effect": "Overall wear; 100 = factory fresh. Low condition saps performance and reliability."},
    "car.condition.engine_condition": {"effect": "Engine wear; degrades with use, restored by repair."},
    "car.condition.gearbox_condition": {"effect": "Gearbox wear (~85 well-kept reference).", "source": "constants.py:550 GEARBOX_CONDITION_REF"},
    "car.condition.suspension_condition": {"effect": "Suspension wear; degrades with use."},
    "car.condition.brake_condition": {"effect": "Brake wear; degrades with use."},
    "car.condition.body_condition": {"effect": "Body wear; damage adds drag (~85 reference).", "source": "constants.py:551 BODY_CONDITION_REF"},
    "car.condition.tire_condition": {"effect": "Fitted-tyre wear; degrades over a stint."},
    "car.condition.mileage": {"effect": "Distance driven; the odometer behind long-term wear.", "units": "km"},
    # --- Tune ---
    "car.tune.tire_pressure_front": {"effect": "Front tyre pressure; deviation from ~2.25 bar loses grip.", "ideal": 2.25, "units": "bar", "source": "constants.py:433 PRESSURE_IDEAL_BAR"},
    "car.tune.tire_pressure_rear": {"effect": "Rear tyre pressure; deviation from ~2.25 bar loses grip.", "ideal": 2.25, "units": "bar", "source": "constants.py:433 PRESSURE_IDEAL_BAR"},
    "car.tune.final_drive": {"effect": "Lower = more top speed; higher = quicker off the line (neutral 4.0).", "ideal": 4.0, "source": "constants.py:443 FINAL_DRIVE_IDEAL"},
    "car.tune.gear_bias": {"effect": "+bias adds acceleration and costs top speed; 0 is neutral.", "ideal": 0.0, "source": "constants.py:528 GEAR_BIAS_ACCEL_FACTOR"},
    "car.tune.brake_bias": {"effect": "Front brake share; deviation from 0.60 hurts braking.", "ideal": 0.60, "source": "constants.py:431 BRAKE_BIAS_IDEAL"},
    "car.tune.brake_pressure": {"effect": "Overall brake force applied; too little under-brakes, too much risks lock-up."},
    "car.tune.front_ride_height": {"effect": "Front ride height; deviation from ~135 mm costs a little.", "ideal": 135, "units": "mm", "source": "constants.py:437 RIDE_HEIGHT_IDEAL_MM"},
    "car.tune.rear_ride_height": {"effect": "Rear ride height; deviation from ~135 mm costs a little.", "ideal": 135, "units": "mm", "source": "constants.py:437 RIDE_HEIGHT_IDEAL_MM"},
    "car.tune.suspension_stiffness_front": {"effect": "Front stiffness; deviation from 50 trims mechanical grip, stiffer sharpens response.", "ideal": 50, "source": "constants.py:530 SUSP_STIFFNESS_IDEAL"},
    "car.tune.suspension_stiffness_rear": {"effect": "Rear stiffness; deviation from 50 trims mechanical grip, stiffer sharpens response.", "ideal": 50, "source": "constants.py:530 SUSP_STIFFNESS_IDEAL"},
    "car.tune.antiroll_front": {"effect": "Front anti-roll; deviation from 5 trades handling response for grip.", "ideal": 5.0, "source": "constants.py:533 ANTIROLL_IDEAL"},
    "car.tune.antiroll_rear": {"effect": "Rear anti-roll; deviation from 5 trades handling response for grip.", "ideal": 5.0, "source": "constants.py:533 ANTIROLL_IDEAL"},
    "car.tune.camber_front": {"effect": "Front camber (negative); |camber| away from ~2° costs grip.", "ideal": -2.0, "units": "deg", "source": "constants.py:435 CAMBER_IDEAL_DEG"},
    "car.tune.camber_rear": {"effect": "Rear camber (negative); |camber| away from ~2° costs grip.", "ideal": -2.0, "units": "deg", "source": "constants.py:435 CAMBER_IDEAL_DEG"},
    "car.tune.toe_front": {"effect": "Front toe; any toe off 0 costs grip, a touch of front toe aids turn-in.", "ideal": 0.0, "units": "deg", "source": "constants.py:535 TOE_GRIP_PENALTY / TOE_RESPONSE_FACTOR"},
    "car.tune.toe_rear": {"effect": "Rear toe; any toe off 0 costs grip.", "ideal": 0.0, "units": "deg", "source": "constants.py:535 TOE_GRIP_PENALTY"},
    "car.tune.front_downforce": {"effect": "Front aero setting; more grip up front at some drag cost."},
    "car.tune.rear_downforce": {"effect": "Rear aero setting; more grip at the rear at some drag cost."},
    "car.tune.differential_power": {
        "effect": "On-power diff lock; deviation from 30 affects traction and accel.",
        "ideal": 30,
        "prose": (
            "The limited-slip differential's on-throttle lock. Near 30 is a modest street lock. More "
            "lock puts power down harder out of corners but can push the nose wide; less frees the car "
            "up at the cost of traction."
        ),
        "source": "constants.py:537 DIFF_POWER_IDEAL",
    },
    "car.tune.differential_coast": {
        "effect": "Off-throttle diff lock; deviation from 15 affects mid-corner handling.",
        "ideal": 15,
        "prose": (
            "The diff's off-throttle (coast) lock. Around 15 is a light street default. More coast lock "
            "stabilises the car on the way into a corner but can make it stubborn to rotate; less lets "
            "it turn more freely."
        ),
        "source": "constants.py:539 DIFF_COAST_IDEAL",
    },
    "car.tune.differential_preload": {
        "effect": "Standing diff lock; deviation from 12 trims grip.",
        "ideal": 12,
        "prose": (
            "Preload is the baseline lock the diff always carries. About 12 is a gentle street setting; "
            "adding preload makes the car's behaviour more consistent but blunts low-speed grip."
        ),
        "source": "constants.py:541 DIFF_PRELOAD_IDEAL",
    },
    "car.tune.engine_map": {
        "effect": "Power vs fuel/heat trade-off; Balanced is the neutral stock map.",
        "ideal": "balanced",
        "prose": (
            "Five maps trade power against fuel and temperature: Fuel Save (lowest power, best economy, "
            "coolest), Safe (a little less power, easier on fuel and temps), Balanced (stock — no trade-"
            "offs), Hot (more power but thirstier and hotter), and Qualifying (most power for short "
            "stints, very thirsty and very hot)."
        ),
        "source": "game/actions.py _engine_map_desc",
    },
}


def _preset_section() -> Section:
    entries = tuple(
        Entry(
            id=f"car.preset.{slug(name)}",
            domain=DOMAIN,
            section=_PRESET_SECTION,
            label=name,
            effect_summary=description,
            editable_in=("creator",),
        )
        for name, description, _overrides in CAR_ARCHETYPES
    )
    return Section(title=_PRESET_SECTION, intro=SECTION_INTROS[_PRESET_SECTION], entries=entries)


def build_chapter() -> Chapter:
    sections: list[Section] = [_preset_section()]
    for section in CAR_SECTIONS:
        if section.title in _SKIP_SECTIONS:
            continue
        entries = tuple(
            entry_from_spec(
                spec,
                domain=DOMAIN,
                section_title=section.title,
                id_prefix=DOMAIN,
                editable_in=_editable_in(spec),
                authored=FIELD_CONTENT,
            )
            for spec in section.fields
        )
        sections.append(
            Section(title=section.title, intro=SECTION_INTROS.get(section.title, ""), entries=entries)
        )
    return Chapter(id="cars", title="Cars", intro=CHAPTER_INTRO, sections=tuple(sections))
