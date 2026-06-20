"""Central tuning values for SheetCircuit."""

SCHEMA_VERSION = 1
STARTING_MONEY = 8000
RACE_TICKS_PER_LAP_DIVISOR = 8.0   # base_lap_time / this = sub-ticks per lap
STARTING_WEEK = 1
TRACK_LENGTH_TOLERANCE = 0.001
PERCENT_MIN = 0.0
PERCENT_MAX = 100.0
PERCENT_LOW_FUEL_WARNING = 20.0
PERCENT_WORN_TIRE_WARNING = 30.0

PERF_SCALE = 0.25
DRIVER_PACE_SCALE = 0.08
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

TIRE_WEAR_PENALTY_MAX = 8.0
TIRE_TEMP_PENALTY_MAX = 4.0
ENGINE_TEMP_PENALTY_MAX = 3.0
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
FUEL_L_PER_KM_UNIT = 0.13          # effective.fuel_burn_rate -> litres/km economy
TYRE_WEAR_PCT_PER_KM = 1.25        # × eff.tire_wear_rate × track tyre mult -> %/km
TIRE_HEAT_PER_KM = 2.5             # tyre temp rises with work (distance × load)
TIRE_COOL_PER_S = 0.06            # tyre temp bleeds off with airflow (time)
TIRE_OPTIMAL_C = 85.0
TIRE_OVERHEAT_C = 108.0
TIRE_CRITICAL_C = 130.0

ENGINE_HEAT_PER_S = 0.06           # engine temp climbs with time at load
ENGINE_COOL_PER_S = 0.04
ENGINE_OVERHEAT_C = 105.0
ENGINE_CRITICAL_C = 120.0

DRIVER_ENERGY_DRAIN_PER_S = 0.032
DRIVER_FOCUS_DRAIN_PER_S = 0.026
DRIVER_STRESS_BUILD_PER_S = 0.042

# In-race driver/pit-boss intents. Engine/ECU maps are NOT changed mid-race — those
# live in the tuning menu (tune.engine_map). Each tuple is
# (pace, tire_wear, fuel_burn, engine_heat, mistake_risk, stress); pace > 1 is faster,
# the other columns are multipliers where > 1 means more of that effect.
COMMAND_MODIFIERS: dict[str, tuple[float, ...]] = {
    "normal": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00),
    "push": (1.06, 1.45, 1.25, 1.30, 1.45, 1.40),
    "go_all_out": (1.11, 2.10, 1.55, 1.60, 2.30, 2.00),
    "save_tyres": (0.96, 0.55, 1.00, 0.95, 0.85, 0.85),
    "save_fuel": (0.93, 0.90, 0.48, 0.70, 0.80, 0.85),
    "cool_down": (0.90, 0.70, 0.80, 0.72, 0.65, 0.65),
    "pit": (0.72, 0.20, 1.00, 0.70, 0.40, 0.45),
}
COMMAND_PACE_INDEX = 0
COMMAND_TIRE_WEAR_INDEX = 1
COMMAND_FUEL_BURN_INDEX = 2
COMMAND_ENGINE_HEAT_INDEX = 3
COMMAND_MISTAKE_INDEX = 4
COMMAND_STRESS_INDEX = 5

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
FAILURE_RELIABILITY_SCALE = 0.0008
FAILURE_CONDITION_SCALE = 0.0005
FAILURE_ENGINE_TEMP_SCALE = 0.08
FAILURE_SYMPATHY_SCALE = 0.0003

REPAIR_COST_PER_POINT = 18
REPAIR_MAX_POINTS = 25
WEAR_PER_RACE_BASE = 4.0
MILEAGE_KM_MULTIPLIER = 1
SELL_VALUE_FACTOR = 0.70
SALARY_WEEKLY_ENABLED = False

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
# Cooling is targeted to match the command's intent: Save Tyres cools tyres, Save Fuel
# cools the engine, Cool Down and Pit cool both.
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
RIVAL_TICK_VARIANCE_S = 0.06     # per-TICK random jitter on each rival's pace (live shuffling)
RIVAL_REACTIVE_GAP_S = 1.0       # opponents push only in an immediate battle within this gap (interactive)
RACE_DISTANCE_LAP_PROGRESS = 1.0
LOW_FEEDBACK_THRESHOLD = 50
HIGH_FEEDBACK_THRESHOLD = 75

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
