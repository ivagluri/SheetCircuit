"""Central tuning values for SheetCircuit."""

SCHEMA_VERSION = 3
STARTING_MONEY = 8000
STARTING_WEEK = 1

# --- Team career progression -------------------------------------------------
# Team XP is a non-spendable career track. Team Level is derived from this table
# instead of stored, so pacing can be tuned without creating save-state conflicts.
TEAM_LEVEL_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 650,
    6: 850,
}
TEAM_LEVEL_BY_CLASS: dict[str, int] = {
    "E": 1,
    "D": 2,
    "C": 3,
    "B": 4,
    "A": 5,
    "S": 6,
}
EVENT_KIND_LADDER = "ladder"
EVENT_KIND_OPEN_INVITATIONAL = "open_invitational"
EVENT_KIND_PRACTICE = "practice"
EVENT_KINDS = (EVENT_KIND_LADDER, EVENT_KIND_OPEN_INVITATIONAL, EVENT_KIND_PRACTICE)
TEAM_XP_BY_CLASS: dict[str, int] = {
    "E": 25,
    "D": 45,
    "C": 70,
    "B": 105,
    "A": 150,
    "S": 210,
}
TEAM_XP_FINISH_MULTIPLIERS: dict[int | str, float] = {
    1: 1.00,
    2: 0.65,
    3: 0.45,
    "finish": 0.15,
    "dnf": 0.00,
}
TEAM_XP_EVENT_KIND_MULTIPLIER: dict[str, float] = {
    EVENT_KIND_LADDER: 1.00,
    EVENT_KIND_OPEN_INVITATIONAL: 0.70,
    EVENT_KIND_PRACTICE: 0.00,
}
# Indexed by wins already recorded for the event. The final value is reused for
# all later repeats, so favorite events stay useful but stop being optimal farms.
TEAM_XP_REPEAT_MULTIPLIERS: list[float] = [1.00, 0.85, 0.70, 0.60]
TEAM_XP_FIRST_WIN_BONUS_MULTIPLIER = 1.00

# --- Presentation / time-scale ----------------------------------------------
# Three independent layers (see memory: time-scale-model):
#   * canonical clock  -- base_lap_time, the real seconds a lap takes (intrinsic to geometry)
#   * presentation     -- PRESENTATION_SPEED_FACTOR compresses canonical -> watched wall-clock
#   * sim resolution   -- ticks_per_lap, how finely a lap is integrated
# No track-specific wall-clock target is anchored anywhere: a race's watched length is purely
# base_lap_time / PRESENTATION_SPEED_FACTOR, and the result is resolution-invariant (the live
# engine matches the one-shot instant sim at any tick count), so tick count is free to float.
PRESENTATION_SPEED_FACTOR = 13.3   # watched wall-clock = canonical lap time / this (1.0 == realtime)
# Sim ticks per second of *watched* wall-clock. With density tied to watched time the per-update
# pause is a constant 1/this on every track, so a 50s sprint and a 12-minute realtime climb both
# refresh at the same felt cadence -- no dead air, no 3-ticks-per-minute realtime.
TICK_RATE_HZ = 2.0
MIN_TICKS_PER_LAP = 8
MAX_TICKS_PER_LAP = 2400
TRACK_LENGTH_TOLERANCE = 0.001
PERCENT_MIN = 0.0
PERCENT_MAX = 100.0
PERCENT_LOW_FUEL_WARNING = 20.0
PERCENT_WORN_TIRE_WARNING = 30.0

# How much a capability edge changes lap time, as a FRACTION of the lap per composite point
# away from REFERENCE_COMPOSITE. Proportional, not a fixed-second shave: a performance edge is
# the same *percentage* on a 90s sprint and a 700s climb (the honest model -- a better car
# pulls away more over more track), where the old absolute `PERF_SCALE*composite` shave gave a
# track-length-independent ~18s that was ~20% of a sprint but ~3% of a climb. Outliers are
# corrected by tuning that track's SEGMENT_TAG_SPEED / a car's stats, never by bending this.
# The class brackets are unaffected -- they read the base_lap_time-independent composite.
PERF_FRACTION = 0.0024
# A lap (or interval) can never drop below this fraction of its base time, so a very
# high-composite custom car cannot drive the clock toward zero.
MIN_LAP_FRACTION = 0.30

# --- Derived base lap time (Phase 4.1) -------------------------------------
# base_lap_time is never stored; it is computed from a track's own geometry at load
# (game.loader.derive_base_lap_time), the way a real lap estimate falls out of the
# corner/straight sequence. Two intrinsic anchors drive it -- neither pinned to whatever
# tracks happen to be loaded:
#   * BASE_REFERENCE_SPEED -- the average speed (km/h) a notional mid-spec car holds on a
#     track whose geometry is perfectly neutral (speed_factor == 1.0).
#   * REFERENCE_COMPOSITE -- the capability composite of that notional car: the 50/100
#     design midpoint of every axis, an intrinsic anchor, NOT the catalog mean.
#   * SEGMENT_TAG_SPEED -- a dimensionless speed factor per segment tag (straights fast,
#     chicanes slow), consistent with SEGMENT_TAG_WEIGHTS. A segment's factor is the mean
#     of its tags'; the lap's speed_factor is the length-weighted mean across segments.
# base_lap_time = ref_lap = length_km / (BASE_REFERENCE_SPEED x speed_factor): the honest lap a
# design-midpoint car (composite == REFERENCE_COMPOSITE) runs on this geometry. No additive
# offset -- pace is proportional (PERF_FRACTION), so a midpoint car laps at exactly base_lap_time
# (multiplier 1.0) and weaker/stronger cars fall a consistent % slower/faster. Auto-updates for
# custom/creator tracks.
BASE_REFERENCE_SPEED = 125.0   # km/h on neutral geometry, mid-spec car
REFERENCE_COMPOSITE = 50.0     # design midpoint composite, intrinsic (not a catalog mean)
SEGMENT_TAG_SPEED: dict[str, float] = {
    "long_straight": 1.90,
    "short_straight": 1.15,
    "high_speed_corner": 1.35,
    "slow_corner": 0.50,
    "hard_braking_zone": 0.70,
    "technical_section": 0.65,
    "tight_chicane": 0.45,
    "bumpy_surface": 0.75,
    "curb_riding": 0.80,
    "narrow_track": 0.75,
    "wide_track": 1.25,
    "exposed": 1.05,
}

# --- Hillclimb climb model --------------------------------------------------
# On a net climb the time is driven by the car's POWER-TO-WEIGHT (the real physical driver of
# climbing), not by the flat-track composite, which compresses to near-nothing over a long
# lap. We model the climb as a time adjustment to the flat-geometry lap, monotonic in the
# car's own intrinsic hp/kg:
#   adjustment(lap) = GRADIENT_PW_GAIN * ln(GRADIENT_PW_REF / power_to_weight)
#                     * climb_gradient_pct * length_km
# Below GRADIENT_PW_REF the climb adds time; above it a strong car claws time back (the flat
# composite under-rewards it on a long climb). NOTHING here is pinned to our catalog: the two
# constants are anchored to REAL-WORLD paved Pikes Peak stock times -- a ~0.09 hp/kg econobox
# at ~14:00 and a 0.39 hp/kg 911 Turbo S at 9:53 -- and the input is the car's own hp/kg, so a
# custom car gets a real climb time with nothing to look up (the de-pin principle). The curve
# is a smooth power law (no plateau, no bracket), so wild customs extrapolate sanely and the
# lap-time floor catches anything degenerate. Gated to net-climb layouts; loops return to
# start, so their stored elevation_change_m is undulation, not net gain (climb_gradient_pct 0).
NET_CLIMB_LAYOUTS = {"point_to_point", "hillclimb", "sprint"}
# Re-anchored to the real paved Pikes times AFTER pace became proportional (PERF_FRACTION):
# composite now also speeds a supercar over a long climb, so the climb term carries less of the
# spread. GAIN 0.60 lands a showroom 911-analog ~9:46 (real 9:53) and an econobox ~14:00, spread
# ~4.2 min -- both real anchors held, just split differently between pace and climb.
GRADIENT_PW_GAIN = 0.60    # seconds per (%-grade x km) per natural-log unit of the hp/kg ratio
GRADIENT_PW_REF = 0.217    # hp/kg at which the climb is time-neutral (from the real paved anchors)

# Driver pace as a FRACTION of the lap per pace point (proportional, like PERF_FRACTION). Keeps
# the same driver:car influence ratio as the old absolute scales (0.08/0.36).
DRIVER_PACE_FRACTION = PERF_FRACTION * (0.08 / 0.36)
DRIVER_XP_PER_RACE = 10
DRIVER_XP_PER_STAT_POINT = 50
DRIVER_STAT_CAP = 99
RANDOM_VARIANCE_SCALE = 1.2

NORM_POWER_REF_HP = 400
NORM_TORQUE_REF_NM = 500
NORM_ACCEL_REF_HW = 0.50
NORM_SPEED_REF_KMH = 250
NORM_AERO_MAX = 100
TOP_SPEED_COEFF = 34.0

# Worn tyres lose grip and lap time, and they lose it *progressively*: the penalty is a
# blend of a linear term (a steady tax that already bites in a sprint, so flogging a set
# all race leaves you a little slower at the flag -- but never enough to make a ~20s stop
# worth it) and a convex term that cliffs as the set nears the end of its life, so the
# last third of wear hurts far more than the first (the real "these are gone, pit now"
# pressure in an enduro). Permanent within a stint: unlike heat you cannot lift to
# recover it, so sustained attack costs grip you keep paying for to the flag.
TIRE_WEAR_PENALTY_MAX = 12.0
TIRE_WEAR_LINEAR_SHARE = 0.7        # fraction of the penalty that scales linearly with wear
TIRE_WEAR_PROGRESSION_EXP = 3.0     # exponent of the convex (end-of-life cliff) term
# Overheat is a two-band consequence (see telemetry failure model). The WARNING band --
# past the overheat threshold, ramping to critical -- is this lap-time drag: holding a
# hot pace clearly bleeds time before anything breaks, so backing off is the obvious play.
TIRE_TEMP_PENALTY_MAX = 5.0
ENGINE_TEMP_PENALTY_MAX = 5.0
# Fuel load is lap time: a FULL tank is the reference (zero adjustment), and every litre
# burned makes the car this many seconds per lap faster. Ties pit strategy to physics --
# brimming the tank at a stop buys range but costs pace until it burns off.
FUEL_WEIGHT_PENALTY_PER_L = 0.02

# --- Physical attrition ----------------------------------------------------
# Consumables are tracked in real units instead of an abstract per-lap %:
#  * Fuel is litres burned over distance, drawn against the car's tank (capacity_l),
#    so range = tank / economy and pit strategy falls out of physics.
#  * Tyres lose a distance-based share of a finite life (km), so a stint is a real
#    number of kilometres.
#  * Engine heat and driver fatigue accrue over *time* (seconds of running), which is
#    what they physically depend on -- and what readies them for duration/enduro races.
# The track tag rates (fuel/tyre/heat) stay as real per-segment multipliers on top.
# The unit constants below are calibrated against the reference car/track to land at
# realistic range/stint, then the catalog is spot-checked for sane pit/tyre counts.
# Fuel economy is affine in the car's burn rate: economy (L/km) = floor + burn_rate x unit.
# The floor is a baseline every car spends just being on track, so a frugal kei can't drift
# into hypermiling territory and a hypercar isn't absurdly thirsty -- this compresses the
# catalog from a ~3-104 L/100km spread into a realistic ~15-65 band where pit strategy
# matters across the whole field, not only at the top. Track tag rate + pace command still
# multiply the whole economy, so a thirsty track / go-all-out lap burns proportionally more.
FUEL_ECONOMY_FLOOR_L_PER_KM = 0.137   # ~15 L/100km baseline at the leanest end
FUEL_L_PER_KM_UNIT = 0.064            # slope: effective.fuel_burn_rate -> litres/km economy
# Running dry is a real failure state: an empty tank adds this fraction of base_lap_time
# per lap (the car limps on fumes -- devastating for the result, but it can still crawl
# to the pit lane and refuel rather than park on the spot).
FUEL_EMPTY_PACE_FRACTION = 0.35
TYRE_WEAR_PCT_PER_KM = 1.25        # × eff.tire_wear_rate × track tyre mult -> %/km

# --- Heat balance -----------------------------------------------------------
# Temperatures are a *balance*, not a one-way clock: heat gain (distance-based work for
# tyres, time-at-load for the engine) fights an always-on passive cooling (airflow,
# linear in seconds -- linear so the segment<->aggregate integration invariant stays
# exact). The passive rates sit near a mid-spec car's normal-pace gain, so at "normal"
# a gentle car drifts back toward its operating floor while a thermally demanding car
# (hot V12, heavy muscle) still creeps up and must lift occasionally -- thermal
# character. push/go_all_out out-heat everyone; the cooling commands multiply the
# passive rate (TIRE/ENGINE_COOLING_BOOST) and go strongly net-negative. Temps never
# cool below their operating floor (TIRE_OPTIMAL_C / INITIAL_ENGINE_TEMP_C).
# Tyres are the *uniform* thermal brake: eff.tire_heat_rate is tight across the catalog
# (~0.23-0.52), so every car crosses TIRE_OVERHEAT_C after a few laps at all-out and can
# pull it back by lifting -- even a car whose engine runs cool. Rates are set so normal
# holds near the floor, push warms slowly, and go_all_out reaches overheat in ~4 laps on
# a mid car (faster on a hot-tyre car); a cooling command clears it in ~1-2 laps.
TIRE_HEAT_PER_KM = 5.0             # tyre temp rises with work (distance × load)
TIRE_COOL_PER_S = 0.055            # passive airflow cooling, always on (time)
TIRE_COOLING_BOOST = 3.0           # save_tyres/cool_down/pit multiply passive cooling
TIRE_OPTIMAL_C = 85.0              # operating floor; passive cooling stops here
TIRE_OVERHEAT_C = 108.0
TIRE_CRITICAL_C = 130.0

# Engine is the *power-coupled* thermal brake and the star of the tactical-burst loop:
# hold all-out and a mid car redlines in ~2 laps (critical by ~4), pushing the engine
# past overheat where the failure/DNF cliff lives (see telemetry). Backing off to a
# cooling command (ENGINE_COOLING_BOOST) recovers it in ~1 lap. The raw heat rate is
# normalised + compressed (ENGINE_HEAT_REF/EXPONENT, clamped) so the ~5x catalog spread
# doesn't make supercars cook at cruise or mid cars never heat -- a hotter/less-cooled
# engine still heats faster within a bounded window, so cooling & engine-map stay levers.
ENGINE_HEAT_PER_S = 0.06           # engine temp climbs with time at load
ENGINE_COOL_PER_S = 0.074          # passive cooling, always on (time)
ENGINE_COOLING_BOOST = 3.5         # save_fuel/cool_down/pit multiply passive cooling
ENGINE_HEAT_REF = 20.0             # reference eff.engine_heat_rate (≈ catalog median)
ENGINE_HEAT_EXPONENT = 0.6         # compress the raw-rate spread (<1 flattens it)
ENGINE_HEAT_FACTOR_MIN = 0.82      # clamp the coolest engines: even a light, well-cooled
                                   # engine overheats within ~3 laps of all-out, so there is
                                   # no free sprint -- it just holds a little longer than a hot one
ENGINE_HEAT_FACTOR_MAX = 1.6       # clamp the hottest engines (still stable at cruise)
ENGINE_OVERHEAT_C = 105.0
ENGINE_CRITICAL_C = 120.0

DRIVER_ENERGY_DRAIN_PER_S = 0.032
DRIVER_FOCUS_DRAIN_PER_S = 0.026
DRIVER_STRESS_BUILD_PER_S = 0.042

# In-race driver/pit-boss intents. Engine/ECU maps are NOT changed mid-race — those
# live in the tuning menu (tune.engine_map). Each tuple is
# (pace, tire_wear, fuel_burn, engine_heat, mistake_risk, stress, overtake); pace > 1 is
# faster, the other columns are multipliers where > 1 means more of that effect. The
# overtake column tilts a contest both ways: it multiplies an attacker's pass chance and
# divides a defender's, so leaning on it makes the move AND makes it harder to be passed
# (at the cost of heat/wear/risk) -- but only push/go_all_out carry a botched-pass risk.
COMMAND_MODIFIERS: dict[str, tuple[float, ...]] = {
    "normal": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00),
    "push": (1.06, 1.45, 1.25, 2.40, 1.45, 1.40, 1.25),
    "go_all_out": (1.11, 2.10, 1.55, 4.00, 2.30, 2.00, 1.60),
    "save_tyres": (0.96, 0.55, 1.00, 0.85, 0.85, 0.85, 0.85),
    "save_fuel": (0.93, 0.90, 0.48, 0.55, 0.80, 0.85, 0.90),
    "cool_down": (0.90, 0.70, 0.80, 0.50, 0.65, 0.65, 0.80),
    "pit": (0.72, 0.20, 1.00, 0.50, 0.40, 0.45, 0.50),
}
COMMAND_PACE_INDEX = 0
COMMAND_TIRE_WEAR_INDEX = 1
COMMAND_FUEL_BURN_INDEX = 2
COMMAND_ENGINE_HEAT_INDEX = 3
COMMAND_MISTAKE_INDEX = 4
COMMAND_STRESS_INDEX = 5
COMMAND_OVERTAKE_INDEX = 6

# Botched pass: attempting a move at a hot pace can be thrown away -- the pass fails
# (as any failed contest does) AND the attacker loses time (locked up / ran wide). Only
# push/go_all_out carry it; per-lap chance, scaled by the tick slice like every contest
# roll. A hook for driver racecraft to mitigate this later, mirroring the crash roll.
OVERTAKE_BOTCH_PROB: dict[str, float] = {"push": 0.06, "go_all_out": 0.14}
OVERTAKE_BOTCH_TIME = 2.5  # seconds lost when a hot pass is botched (== MISTAKE_TIME_MEDIUM)

ENGINE_MAP_POWER: dict[str, float] = {
    "safe": 0.88,
    "balanced": 1.00,
    "hot": 1.08,
    "qualifying": 1.12,
    "fuel_save": 0.82,
}
ENGINE_MAP_FUEL: dict[str, float] = {
    "safe": 0.80,
    "balanced": 1.00,
    "hot": 1.35,
    "qualifying": 1.55,
    "fuel_save": 0.60,
}
ENGINE_MAP_HEAT: dict[str, float] = {
    "safe": 0.75,
    "balanced": 1.00,
    "hot": 1.40,
    "qualifying": 1.65,
    "fuel_save": 0.70,
}

BASE_MISTAKE_RATE = 0.05
BASE_FAILURE_RATE = 0.015
MISTAKE_TIME_SMALL = 0.8
MISTAKE_TIME_MEDIUM = 2.5
MISTAKE_DNF_PROB = 0.04
# A mechanical issue can be terminal: this fraction of failures retire the car outright,
# rising sharply when the engine is past overheat (the physical pressure that makes heat
# management and the AI's cooling rules matter). Applies to player and rivals alike.
FAILURE_DNF_PROB = 0.06
# The DANGER band: once the engine is into the red, a mechanical issue is roughly a
# coin-flip to end the race outright (0.06 + 0.45 at critical). Combined with the raised
# failure rate at heat below, holding all-out into critical for several laps is a real
# gamble, not a rounding error -- the teeth behind the tactical-burst loop.
FAILURE_DNF_TEMP_PROB = 0.45
# Go All Out can crash a car out. A composed/sympathetic driver trims that risk; this
# is the hook for future driver skill levels to further mitigate it. The roll is scaled
# by 1 - (consistency + mechanical_sympathy)/2 * DNF_DRIVER_RELIEF (clamped >= floor).
DNF_DRIVER_RELIEF = 0.006
DNF_DRIVER_RELIEF_FLOOR = 0.25
MISTAKE_AGGRESSION_SCALE = 0.0005
MISTAKE_CONSISTENCY_SCALE = 0.0004
MISTAKE_FOCUS_SCALE = 0.0003
MISTAKE_TIRE_WEAR_SCALE = 0.08
MISTAKE_TIRE_TEMP_SCALE = 0.04
MISTAKE_STRESS_SCALE = 0.05
# Fatigue is added *risk* (zero for a fresh driver, so baseline rates don't shift):
# an exhausted driver errs like a stressed one.
MISTAKE_FATIGUE_SCALE = 0.05
FAILURE_RELIABILITY_SCALE = 0.0008
FAILURE_CONDITION_SCALE = 0.0005
FAILURE_ENGINE_TEMP_SCALE = 0.12
FAILURE_SYMPATHY_SCALE = 0.0003

# --- Mid-race damage / driver energy ----------------------------------------
# Incidents leave a mark on RaceCarState.condition_pct, which feeds failure_chance
# (FAILURE_CONDITION_SCALE) -- issues beget issues -- and a share of the damage
# carries into post-race garage wear (RACE_DAMAGE_WEAR_FACTOR).
CONDITION_HIT_FAILURE = 5.0    # a (non-terminal) mechanical issue damages the car
CONDITION_HIT_MISTAKE = 1.5    # a medium mistake (an off-track moment) dings it
RACE_DAMAGE_WEAR_FACTOR = 0.25 # mid-race damage -> extra overall wear after the race
# An exhausted driver leaks pace: below the threshold, up to this fraction of the
# base lap is lost at zero energy (on top of the fatigue mistake risk above).
DRIVER_ENERGY_LOW_PCT = 30.0
DRIVER_ENERGY_PACE_FRACTION = 0.04

REPAIR_COST_PER_POINT = 18
REPAIR_MAX_POINTS = 25
# Post-race wear scales with real race distance (a hillclimb sprint is gentler than an
# enduro): overall wear = BASE x race_km / REFERENCE_KM, clamped to [MIN, MAX]. The
# reference is the starter sprint (~14 km), so short races keep their historical cost.
# Sub-systems wear alongside overall at their own share, so long-term upkeep is
# per-system (engines age faster than bodywork).
WEAR_PER_RACE_BASE = 4.0
WEAR_REFERENCE_RACE_KM = 15.0
WEAR_PER_RACE_MIN = 1.5
WEAR_PER_RACE_MAX = 12.0
SUBCONDITION_WEAR_FACTORS: dict[str, float] = {
    "engine_condition": 0.9,
    "gearbox_condition": 0.5,
    "suspension_condition": 0.7,
    "brake_condition": 0.8,
    "body_condition": 0.3,
    "tire_condition": 1.2,
}
MILEAGE_KM_MULTIPLIER = 1
# Resale depreciates with condition and mileage: a clean low-miler sells near the full
# factor, a thrashed high-miler well below it (mileage slides linearly to the floor at
# SELL_MILEAGE_FULL_KM).
SELL_VALUE_FACTOR = 0.70
SELL_CONDITION_WEIGHT = 0.5
SELL_MILEAGE_FULL_KM = 100000.0
SELL_MILEAGE_FLOOR = 0.6
# Each race consumes a week. When weekly salaries are enabled, every hired driver costs
# this fraction of their (hire-fee) salary per week raced.
SALARY_WEEKLY_ENABLED = False
SALARY_WEEKLY_FRACTION = 0.10

INITIAL_TIRE_TEMP_C = 85.0
INITIAL_ENGINE_TEMP_C = 90.0
PIT_TIRE_RESTORE_PCT = 100.0
PIT_FUEL_RESTORE_PCT = 100.0
PIT_TIRE_TEMP_C = 82.0
PIT_ENGINE_COOL_C = 8.0
DRIVER_ENERGY_RECOVER_PIT = 3.0
DRIVER_FOCUS_RECOVER_PIT = 3.0
DRIVER_STRESS_RELIEF_PIT = 10.0
AI_COMMAND = "normal"
# Rival pit-boss thresholds (see race_session._ai_command): survive first, then race.
# Rivals pit when tyres or fuel won't last, and lift to a cooling command when a
# temperature crosses its overheat threshold.
AI_PIT_FUEL_PCT = 8.0
AI_PIT_TIRE_PCT = 30.0
# Boosted cooling is targeted to match the command's intent: Save Tyres cools tyres,
# Save Fuel cools the engine, Cool Down and Pit cool both (every command gets the
# passive baseline; these multiply it by TIRE/ENGINE_COOLING_BOOST).
TYRE_COOLING_COMMANDS = ("save_tyres", "cool_down", "pit")
ENGINE_COOLING_COMMANDS = ("save_fuel", "cool_down", "pit")

# --- Rival field generation (see game/opponents.py) ---
# Per-class default rival driver skill. Events can override this with rival_skill.
CLASS_RIVAL_SKILL: dict[str, int] = {
    "E": 32,
    "D": 44,
    "C": 56,
    "B": 68,
    "A": 78,
    "S": 88,
}
# Dynamic event pace floor. Values are percentiles over the eligible event field
# after sorting by natural lap time, fastest first. E stays permissive; higher
# classes refuse to scale all the way down if a player brings a much slower car.
EVENT_PACE_FLOOR_PERCENTILE: dict[str, float] = {
    "E": 1.00,
    "D": 0.60,
    "C": 0.45,
    "B": 0.30,
    "A": 0.20,
    "S": 0.10,
}
RIVAL_SKILL_SIGMA = 8.0          # seeded spread around an event's rival_skill
# Rival cars are matched around the player's derived event pace instead of the
# fastest eligible car. The band scales with track length, and the local pool expands
# to a few nearest neighbours so tiny catalogs still have variety.
RIVAL_MATCH_LAP_BAND_FRAC = 0.025
RIVAL_MATCH_EXPANSION_FACTOR = 2.0
RIVAL_MATCH_MIN_UNIQUE = 3
RIVAL_MATCH_POOL_FACTOR = 2.0
# Per-LAP rival pace jitter amplitude (uniform +/-): a live-only shuffle so the rival pack
# reshuffles in close battles. Applied per tick scaled by sqrt(slice) so the accumulated
# per-lap spread (std ~= amp/sqrt(3) ~= 0.14s) is identical at any tick count. Cosmetic; the
# instant sim carries none, so this is not anchored to it.
RIVAL_LAP_JITTER_S = 0.25
RIVAL_REACTIVE_GAP_S = 1.0       # opponents lean in (push) within this gap of a rival (interactive)
RIVAL_ATTACK_GAP_S = 0.4         # right on someone: a healthy rival sends it (go_all_out) mid-race,
                                 # overheating within a lap or two and then lifting -- a two-sided
                                 # burst rhythm rather than a permanent hold
RIVAL_FINAL_LAP_ATTACK = 1       # laps_remaining <= this: a battling rival throws everything at it,
                                 # ignoring heat -- nothing left to save the car for
LOW_FEEDBACK_THRESHOLD = 50
HIGH_FEEDBACK_THRESHOLD = 75

# --- Procedural drivers (see game/driver_gen.py, game/market.py) ---
# Intrinsic driver archetypes, mirroring the philosophy of editor.fields.CAR_ARCHETYPES:
# each is an anchored skill band + personality bias + potential headroom, defined here
# NOT derived from the seed roster (see the project's de-pin philosophy). Generated
# drivers roll a skill in [skill_lo, skill_hi]; `bias` shifts specific stat anchors;
# `headroom` is added to the driver's peak current stat to get their potential ceiling.
DRIVER_ARCHETYPES: list[tuple[str, str, dict]] = [
    (
        "Rookie",
        "raw and cheap; wide, high ceiling that may or may not pan out",
        {"skill": (26, 46), "headroom": (20, 36), "bias": {"consistency": -6, "aggression": 4}},
    ),
    (
        "Journeyman",
        "dependable mid-pack pro with little growth left",
        {"skill": (50, 64), "headroom": (3, 11), "bias": {"consistency": 6}},
    ),
    (
        "Ace",
        "front-running talent, already near their ceiling",
        {"skill": (72, 86), "headroom": (2, 9), "bias": {"racecraft": 5, "consistency": 4}},
    ),
    (
        "Wet specialist",
        "modest in the dry, mercurial in the rain",
        {"skill": (46, 62), "headroom": (8, 18), "bias": {"wet_skill": 20, "consistency": 2}},
    ),
    (
        "Hothead",
        "blazing pace, fragile temperament",
        {"skill": (54, 70), "headroom": (10, 22), "bias": {"aggression": 24, "consistency": -14, "mechanical_sympathy": -8}},
    ),
]

# Free-agent market: a persisted, rotating hireable pool (see game/market.py). Every
# FREE_AGENT_REFRESH_WEEKS the pool churns -- up to FREE_AGENT_CHURN of the passed-over
# agents are replaced by freshly generated ones, refilling to FREE_AGENT_POOL_SIZE.
FREE_AGENT_POOL_SIZE = 6
FREE_AGENT_REFRESH_WEEKS = 4
FREE_AGENT_CHURN = 3

# Generated hire price (the Driver.salary one-off hire fee). Scales super-linearly with
# current ability and carries a premium for potential headroom, so a promising rookie is
# never a free arbitrage. Monotonic in both current ability and potential.
SALARY_BASE = 600
SALARY_ABILITY_REF = 40          # reference mean progressable stat
SALARY_ABILITY_EXP = 2.2
SALARY_POTENTIAL_COEF = 0.8

# Car class is derived at runtime (game/reference_suite.py): PR = mean capability
# composite across the drag/slalom/hybrid fixtures, scaled, then bracketed. The scale
# puts PR on a familiar ~150-1100 band; the thresholds are intrinsic capability levels
# (validated against -- not derived from -- the catalog, which lands torino=E, the
# detroit/k660 cluster=E, GT cars A/S).
CLASS_RATING_SCALE = 10
CLASS_THRESHOLDS: dict[str, int] = {
    "E": 0,
    "D": 340,
    "C": 480,
    "B": 620,
    "A": 760,
    "S": 960,
}
# Car "shape" (performance_type): where a car's pace comes from, comparing its speed axes
# (power/accel/top_speed) against its control axes (grip/braking/handling). Beyond this
# margin it reads Power or Handling; within it, Balanced. A car below the capability floor
# (or tagged challenge/joke) reads Challenge. The floor is in mean-capability units (the
# pre-scale composite), so it tracks the class brackets.
SHAPE_SPEED_CONTROL_DELTA = 10.0
SHAPE_CHALLENGE_FLOOR = 20.0

# --- Pace soft knee --------------------------------------------------------
# The performance axes that feed the pace composite (acceleration, top_speed, power,
# grip, braking, handling, aero_grip) use a no-ceiling soft knee instead of a hard
# clamp at 100. Below the knee the transform is the identity, so ordinary cars and the
# k660 reference are unchanged; above it, extra performance keeps helping with
# diminishing returns and never walls out (future upgrade parts stay meaningful). The
# dashboard and class_rating still present these axes clamped to 0-100.
PACE_SOFT_KNEE = 100.0
PACE_SOFT_SOFTNESS = 40.0

# Drivetrain traction. AWD claws back grip, and more so on low-grip surfaces (gravel/wet),
# which is what gives the AWD supercar its identity on a rally/hillclimb stage. RWD/FWD are
# neutral for now.
AWD_GRIP_BONUS = 1.02               # small everyday grip edge for AWD cars
AWD_LOWGRIP_BONUS = 0.45            # the real AWD payoff: grip multiplier per (1 - grip_mult), low-grip only

MIN_CONDITION_FACTOR = 0.40
BRAKE_BIAS_IDEAL = 0.60
BRAKE_BIAS_PENALTY = 0.55
PRESSURE_IDEAL_BAR = 2.25
PRESSURE_PENALTY = 0.12
CAMBER_IDEAL_DEG = 2.0
CAMBER_PENALTY = 0.08
RIDE_HEIGHT_IDEAL_MM = 135
RIDE_HEIGHT_PENALTY = 0.002
WEIGHT_REFERENCE_KG = 1100   # intrinsic light-sports-car reference (not a catalog mean)
DOWNFORCE_DRAG_PENALTY = 0.06
COOLING_HEAT_REDUCTION = 0.006
STRESS_RELIABILITY_PENALTY = 0.004
FINAL_DRIVE_IDEAL = 4.0
FINAL_DRIVE_ACCEL_FACTOR = 0.12
FINAL_DRIVE_SPEED_FACTOR = 0.08

# --- Orphan-stat reference points -------------------------------------------
# Previously-unused car/tune/durability stats are folded into the existing
# effective axes as *centered* multipliers: each factor is 1.0 when a stat sits
# at its reference, and swings only a few percent either side, clamped per axis
# to [ORPHAN_FACTOR_FLOOR, _CEIL]. The references are *intrinsic design anchors*
# (the design-range midpoint of a 0-100 rating, or a documented real-world
# typical value), NOT the mean of whatever cars happen to be loaded: a car's
# effective stats must not depend on what else is in the catalog. So "neutral"
# stays put as the catalog grows or a custom out-of-distribution car is built.
# The clamp band contains any single axis; see tests/test_balance_baseline.py
# for the (deliberately re-pinned) drift tripwire.
ORPHAN_FACTOR_FLOOR = 0.88
ORPHAN_FACTOR_CEIL = 1.12

# Rating-style stats (0-100). per_unit is "fraction per point of deviation".
RATING_REF = 50.0            # design-range midpoint shared by most 0-100 ratings

# Engine character -> acceleration / response
TORQUE_RATIO_REF = 1.25      # typical road-engine torque_nm:power_hp ratio
TORQUE_RATIO_ACCEL_FACTOR = 0.06
POWERBAND_REF = RATING_REF
POWERBAND_ACCEL_PER_UNIT = 0.0010
THROTTLE_RESPONSE_REF = RATING_REF
THROTTLE_ACCEL_PER_UNIT = 0.0010

# Chassis -> handling / stability. Per-unit magnitudes are deliberately modest so a
# focus car (whose secondary stats all skew one way) does not saturate the orphan
# clamp; this keeps same-class cars competitive while still rewarding composition.
RIGIDITY_REF = RATING_REF
RIGIDITY_HANDLING_PER_UNIT = 0.00045
CENTER_OF_GRAVITY_REF = RATING_REF      # higher = lower CoG = better
COG_HANDLING_PER_UNIT = 0.0004
ROTATION_REF = RATING_REF
ROTATION_HANDLING_PER_UNIT = 0.00035
WEIGHT_DIST_IDEAL = 0.52                # intrinsic near-50/50 ideal front weight fraction
WEIGHT_DIST_HANDLING_PENALTY = 0.25     # per unit |dev| in fraction

# Tires -> grip / wear / heat. References are a typical mid-spec staggered
# performance-tyre size, not the catalog mean.
TIRE_WIDTH_FRONT_REF = 205.0
TIRE_WIDTH_REAR_REF = 225.0
TIRE_WIDTH_GRIP_PER_MM = 0.0006
TIRE_WIDTH_WEAR_PER_MM = 0.0004         # wider tyres wear/heat slightly more
TIRE_WARMUP_REF = RATING_REF
TIRE_WARMUP_HEAT_PER_UNIT = 0.0030      # higher warmup -> faster tyre heat climb

# Brakes -> braking (0-100 ratings, design-range midpoint)
BRAKE_COOLING_REF = 50.0
BRAKE_COOLING_PER_UNIT = 0.0007
BRAKE_FADE_REF = 50.0
BRAKE_FADE_PER_UNIT = 0.0007
BRAKE_STABILITY_BLEND = 0.08            # weight of computed brake_stability into braking

# Suspension -> handling / grip (0-100 ratings, design-range midpoint)
BUMP_ABSORPTION_REF = 50.0
BUMP_HANDLING_PER_UNIT = 0.0004
STEERING_PRECISION_REF = RATING_REF
STEERING_HANDLING_PER_UNIT = 0.0004
MECH_GRIP_BLEND = 0.12                  # weight of computed mechanical_grip into grip
COMPLIANCE_REF = RATING_REF
COMPLIANCE_HANDLING_PER_UNIT = 0.00035
CURB_HANDLING_REF = RATING_REF
CURB_HANDLING_PER_UNIT = 0.00035

# Aero -> drag / top speed confidence (0-100 rating, design-range midpoint)
AERO_EFFICIENCY_REF = 50.0
AERO_EFFICIENCY_DRAG_PER_UNIT = 0.0040  # higher efficiency trims effective drag
STABILITY_TOPSPEED_BLEND = 0.08         # weight of computed stability into top_speed

# Elevation -> track-level fuel/heat emphasis (folded in the loader, applied uniformly
# to the aggregate and every segment profile so the integration invariant holds). The
# reference is a circuit-typical climb; sustained-climb stages cost more, bounded.
ELEVATION_REF_M = 40
ELEVATION_HEAT_PER_M = 0.0006
ELEVATION_FUEL_PER_M = 0.0005
ELEVATION_FACTOR_FLOOR = 0.96
ELEVATION_FACTOR_CEIL = 1.20

# Tune knobs. Ideals are the *neutral street setup* -- the value that neither helps
# nor hurts -- so a stock car is neutral and only tuning away from it moves
# performance. Anchored to the setup's own meaning, not the catalog mean.
GEAR_BIAS_ACCEL_FACTOR = 0.05          # +bias -> accel, -top_speed (like a soft final drive)
GEAR_BIAS_SPEED_FACTOR = 0.04
SUSP_STIFFNESS_IDEAL = 50              # mid of the 1-100 range (neutral stiffness)
SUSP_STIFFNESS_HANDLING_PER_UNIT = 0.0010
SUSP_STIFFNESS_GRIP_PENALTY_PER_UNIT = 0.0006   # deviation from ideal hurts mechanical grip
ANTIROLL_IDEAL = 5.0                   # mid of the 1-10 range (neutral anti-roll)
ANTIROLL_HANDLING_PER_UNIT = 0.010
TOE_GRIP_PENALTY = 0.05                 # per unit total |toe| (deg) hurts grip
TOE_RESPONSE_FACTOR = 0.03              # per unit front |toe| aids turn-in handling
DIFF_POWER_IDEAL = 30                   # a modest street power-LSD lock (neutral)
DIFF_POWER_ACCEL_PER_UNIT = 0.0009
DIFF_COAST_IDEAL = 15                   # a light coast-side lock (relaxed street default)
DIFF_COAST_HANDLING_PER_UNIT = 0.0009
DIFF_PRELOAD_IDEAL = 12                 # minimal preload (gentle street default)
DIFF_PRELOAD_GRIP_PENALTY_PER_UNIT = 0.0008

# Durability / condition -> reliability (folded into effective.reliability)
DURABILITY_REF = 50.0                      # 0-100 build-robustness midpoint
DURABILITY_RELIABILITY_PER_UNIT = 0.0015   # blend of secondary durability stats
MECH_SYMPATHY_MOD_PER_UNIT = 0.004         # car's mechanical_sympathy_modifier (range ~ -4..15)
# Condition is wear: 100 = factory fresh. Reference is a well-kept, lived-in
# baseline; a more-worn example is penalised, a near-pristine one rewarded.
GEARBOX_CONDITION_REF = 85.0
BODY_CONDITION_REF = 85.0
BODY_CONDITION_DRAG_PER_UNIT = 0.0015      # damaged body adds drag
CONDITION_RELIABILITY_PER_UNIT = 0.0010

# Driver fitness -> energy / focus drain (folded into per-lap wear)
FITNESS_REF = 60.0
FITNESS_DRAIN_PER_UNIT = 0.006             # fitter driver drains slower

# Fuel model -> efficiency-aware burn (0-100 rating, design-range midpoint)
FUEL_EFFICIENCY_REF = 50.0
FUEL_EFFICIENCY_BURN_PER_UNIT = 0.0030     # higher efficiency trims burn

TUNE_FIELD_RANGES: dict[str, tuple[float, float]] = {
    "tire_pressure_front": (1.40, 3.20),
    "tire_pressure_rear": (1.40, 3.20),
    "final_drive": (2.00, 6.00),
    "gear_bias": (-1.00, 1.00),
    "brake_bias": (0.45, 0.75),
    "brake_pressure": (0.50, 1.20),
    "front_ride_height": (80, 220),
    "rear_ride_height": (80, 220),
    "suspension_stiffness_front": (1, 100),
    "suspension_stiffness_rear": (1, 100),
    "antiroll_front": (1, 10),
    "antiroll_rear": (1, 10),
    "camber_front": (-5.00, 0.00),
    "camber_rear": (-5.00, 0.00),
    "toe_front": (-1.00, 1.00),
    "toe_rear": (-1.00, 1.00),
    "front_downforce": (0, 100),
    "rear_downforce": (0, 100),
    "differential_power": (0, 100),
    "differential_coast": (0, 100),
    "differential_preload": (0, 100),
}

# Canonical tyre compounds, ordered soft-intent last (grip up, wear down the list is
# the design intent; the sim reads grip from the tyre ratings, events read the
# compound for allowed_tires restrictions).
TIRE_COMPOUNDS: list[str] = ["economy", "street", "sport", "semi_slick", "slick"]

# Garage-tweakable car stats beyond the TuneSetup knobs: the in-game tune menu can
# change these on an owned car (they write straight into the car's stat sections and
# persist). Intrinsic properties are deliberately absent and stay creator-only:
# identity (name/year/manufacturer/drivetrain/layout/value), the engine itself
# (hp/torque/aspiration/powerband/throttle/cooling/stress), weight_kg, the
# durability build-quality ratings, fuel hardware (capacity/base burn), and the
# whole condition section (that is wear, managed by racing and repair).
CAR_MOD_FIELD_SECTIONS: dict[str, str] = {
    "tire_compound": "tires",
    "tire_width_front": "tires",
    "tire_width_rear": "tires",
    "base_grip": "tires",
    "wet_grip": "tires",
    "tire_wear_resistance": "tires",
    "tire_heat_resistance": "tires",
    "tire_warmup": "tires",
    "braking_power": "brakes",
    "brake_stability": "brakes",
    "brake_cooling": "brakes",
    "brake_fade_resistance": "brakes",
    "weight_distribution_front": "chassis",
    "center_of_gravity": "chassis",
    "chassis_rigidity": "chassis",
    "stability": "chassis",
    "rotation": "chassis",
    "handling": "suspension",
    "mechanical_grip": "suspension",
    "suspension_compliance": "suspension",
    "curb_handling": "suspension",
    "bump_absorption": "suspension",
    "steering_precision": "suspension",
    "downforce": "aero",
    "drag": "aero",
    "aero_efficiency": "aero",
    "high_speed_stability": "aero",
    "fuel_efficiency": "fuel",
}

# Numeric bounds for the hard-mod knobs (tire_compound is an enum over
# TIRE_COMPOUNDS instead). Mirrors the creator's field specs.
CAR_MOD_FIELD_RANGES: dict[str, tuple[float, float]] = {
    "tire_width_front": (120, 400),
    "tire_width_rear": (120, 400),
    "base_grip": (0, 100),
    "wet_grip": (0, 100),
    "tire_wear_resistance": (0, 100),
    "tire_heat_resistance": (0, 100),
    "tire_warmup": (0, 100),
    "braking_power": (0, 100),
    "brake_stability": (0, 100),
    "brake_cooling": (0, 100),
    "brake_fade_resistance": (0, 100),
    "weight_distribution_front": (0.30, 0.70),
    "center_of_gravity": (0, 100),
    "chassis_rigidity": (0, 100),
    "stability": (0, 100),
    "rotation": (0, 100),
    "handling": (0, 100),
    "mechanical_grip": (0, 100),
    "suspension_compliance": (0, 100),
    "curb_handling": (0, 100),
    "bump_absorption": (0, 100),
    "steering_precision": (0, 100),
    "downforce": (0, 100),
    "drag": (0, 100),
    "aero_efficiency": (0, 100),
    "high_speed_stability": (0, 100),
    "fuel_efficiency": (0, 100),
}

SEGMENT_TAG_WEIGHTS: dict[str, dict[str, float]] = {
    "long_straight": {"power": 0.8, "top_speed": 0.9, "acceleration": 0.2, "grip": 0.0, "braking": 0.0, "handling": 0.0, "aero": 0.1},
    "short_straight": {"power": 0.5, "top_speed": 0.2, "acceleration": 0.6, "grip": 0.0, "braking": 0.0, "handling": 0.0, "aero": 0.0},
    "high_speed_corner": {"power": 0.1, "top_speed": 0.1, "acceleration": 0.0, "grip": 0.5, "braking": 0.1, "handling": 0.3, "aero": 0.9},
    "slow_corner": {"power": 0.1, "top_speed": 0.0, "acceleration": 0.7, "grip": 0.8, "braking": 0.2, "handling": 0.7, "aero": 0.0},
    "hard_braking_zone": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.1, "grip": 0.3, "braking": 0.9, "handling": 0.4, "aero": 0.0},
    "technical_section": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.2, "grip": 0.5, "braking": 0.3, "handling": 0.9, "aero": 0.1},
    "tight_chicane": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.1, "grip": 0.4, "braking": 0.6, "handling": 0.9, "aero": 0.0},
    "bumpy_surface": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.0, "grip": 0.3, "braking": 0.2, "handling": 0.5, "aero": 0.0},
    "curb_riding": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.1, "grip": 0.3, "braking": 0.2, "handling": 0.6, "aero": 0.0},
    "narrow_track": {"power": 0.0, "top_speed": 0.0, "acceleration": 0.0, "grip": 0.2, "braking": 0.1, "handling": 0.4, "aero": 0.0},
    "wide_track": {"power": 0.2, "top_speed": 0.2, "acceleration": 0.0, "grip": 0.0, "braking": 0.0, "handling": 0.0, "aero": 0.0},
    "exposed": {"power": 0.0, "top_speed": 0.1, "acceleration": 0.0, "grip": 0.1, "braking": 0.0, "handling": 0.1, "aero": 0.5},
}

SEGMENT_TAG_RATES: dict[str, dict[str, float]] = {
    "long_straight": {"tire_wear": 0.3, "fuel_burn": 0.9, "engine_heat": 0.9},
    "short_straight": {"tire_wear": 0.2, "fuel_burn": 0.5, "engine_heat": 0.5},
    "high_speed_corner": {"tire_wear": 0.9, "fuel_burn": 0.6, "engine_heat": 0.7},
    "slow_corner": {"tire_wear": 0.7, "fuel_burn": 0.4, "engine_heat": 0.4},
    "hard_braking_zone": {"tire_wear": 0.7, "fuel_burn": 0.3, "engine_heat": 0.3},
    "technical_section": {"tire_wear": 0.7, "fuel_burn": 0.5, "engine_heat": 0.5},
    "tight_chicane": {"tire_wear": 0.8, "fuel_burn": 0.4, "engine_heat": 0.4},
    "bumpy_surface": {"tire_wear": 0.9, "fuel_burn": 0.3, "engine_heat": 0.3},
    "curb_riding": {"tire_wear": 0.8, "fuel_burn": 0.3, "engine_heat": 0.3},
    "narrow_track": {"tire_wear": 0.5, "fuel_burn": 0.4, "engine_heat": 0.4},
    "wide_track": {"tire_wear": 0.3, "fuel_burn": 0.5, "engine_heat": 0.5},
    "exposed": {"tire_wear": 0.4, "fuel_burn": 0.5, "engine_heat": 0.5},
}

OVERTAKE_DIFFICULTY_TAG_DELTA: dict[str, float] = {
    "narrow_track": +0.15,
    "wide_track": -0.15,
}

# --- Overtaking (live races only, like rival jitter) -------------------------
# The car behind cannot simply drive through the one ahead: a tick that would put it
# within the follow gap contests the pass. Chance per LAP of sustained pressure =
# BASE x (1 - track.overtake_difficulty) x racecraft edge (scaled by the tick slice, so
# it is resolution-invariant). A won contest COMPLETES the pass: a follower still
# nominally behind exchanges race clocks with the defender, so the move always reorders
# the road. Only close battles between established positions are contested: if the
# follower would sweep past by more than the contest window (the leader pitted, crashed
# wide, or is crawling on fumes) the pass is free, and a car that was not strictly
# ahead when the tick began (standing start / dead heat) holds no road to defend -- the
# field spreads on pace alone. The instant sim carries none of this, same as
# jitter/reactive push.
OVERTAKE_FOLLOW_GAP_S = 0.4      # dirty-air gap a blocked car is held at (minimum)
OVERTAKE_GAP_JITTER_S = 0.2      # breathing room above the gap: a hold lands in [gap, gap+jitter]
OVERTAKE_CONTEST_MAX_S = 2.0     # only contest passes with less margin than this
OVERTAKE_BASE_CHANCE_PER_LAP = 1.4
OVERTAKE_RACECRAFT_PER_POINT = 0.006  # attacker-vs-defender racecraft edge per point

# Per-segment surface/condition effects, applied locally as a race is run.
# `grip` multiplies a segment's whole pace contribution (less traction -> slower).
# `tire_wear` multiplies the segment's tyre-wear rate. tarmac/concrete and `dry`
# are the neutral 1.0 baseline so existing dry tracks are unchanged; gravel and
# damp/wet make those segments meaningfully different. `wet_weight` blends a car's
# dry `grip` toward its `wet_grip` and a driver's `pace` toward their `wet_skill`.
SURFACE_NEUTRAL = {"grip": 1.00, "tire_wear": 1.00}
SURFACE_MODIFIERS: dict[str, dict[str, float]] = {
    "tarmac": {"grip": 1.00, "tire_wear": 1.00},
    "concrete": {"grip": 1.00, "tire_wear": 1.00},
    "gravel": {"grip": 0.82, "tire_wear": 1.35},
}
CONDITION_NEUTRAL = {"grip": 1.00, "tire_wear": 1.00, "wet_weight": 0.00}
CONDITION_MODIFIERS: dict[str, dict[str, float]] = {
    "dry": {"grip": 1.00, "tire_wear": 1.00, "wet_weight": 0.00},
    "damp": {"grip": 0.90, "tire_wear": 1.05, "wet_weight": 0.50},
    "wet": {"grip": 0.75, "tire_wear": 1.10, "wet_weight": 1.00},
}

# --- Race-day weather --------------------------------------------------------
# One pre-race forecast roll per race (both engines, seeded off the race seed on an
# isolated stream so the pace/mistake draws are untouched): weather_variability is the
# chance the race does NOT run in the track's default condition; a change is usually
# damp, sometimes full wet (WEATHER_WET_SHARE of the change band). The rolled condition
# only ever *escalates* a segment (an authored-wet segment never dries out). Mid-race
# weather changes are a future step.
CONDITION_SEVERITY: dict[str, int] = {"dry": 0, "damp": 1, "wet": 2}
WEATHER_WET_SHARE = 0.35
WEATHER_RNG_OFFSET = 7919  # isolates the forecast stream from the race's main rng
