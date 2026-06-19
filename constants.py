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

TIRE_WEAR_BASE_PCT = 4.5
TIRE_HEAT_BASE_C = 9.0
TIRE_COOL_BASE_C = 6.0
TIRE_OPTIMAL_C = 85.0
TIRE_OVERHEAT_C = 108.0
TIRE_CRITICAL_C = 130.0

FUEL_BURN_BASE_PCT = 9.0
ENGINE_HEAT_BASE_C = 5.5
ENGINE_COOL_BASE_C = 3.5
ENGINE_OVERHEAT_C = 105.0
ENGINE_CRITICAL_C = 120.0

DRIVER_ENERGY_DRAIN_BASE = 3.0
DRIVER_FOCUS_DRAIN_BASE = 2.5
DRIVER_STRESS_BUILD_BASE = 4.0

COMMAND_MODIFIERS: dict[str, tuple[float, ...]] = {
    "conserve": (0.92, 0.70, 0.78, 0.75, 0.60, 0.70),
    "normal": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00),
    "push": (1.05, 1.45, 1.22, 1.30, 1.45, 1.45),
    "maximum_attack": (1.10, 2.10, 1.55, 1.60, 2.30, 2.00),
    "attack": (1.04, 1.30, 1.10, 1.15, 1.30, 1.30),
    "defend": (0.97, 1.20, 1.00, 1.05, 1.20, 1.20),
    "safe_map": (0.95, 1.00, 0.72, 0.65, 0.80, 0.75),
    "hot_map": (1.07, 1.05, 1.42, 1.55, 1.20, 1.30),
    "fuel_save": (0.93, 0.82, 0.48, 0.70, 0.78, 0.80),
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
COOLING_COMMANDS = ("conserve", "safe_map", "fuel_save", "pit")

# --- Rival field generation (see game/opponents.py) ---
# Per-class "center" lap offset vs the track's base_lap_time, in seconds. A more
# negative value means a faster class. These define each event's absolute pace
# band so the player can outgrow easier events. Tunable per class; extend as new
# classes/cars are added. NOT tied to any specific car.
CLASS_RIVAL_PACE_OFFSET: dict[str, float] = {
    "E": -9.0,
    "D": -13.0,
    "C": -17.0,
    "B": -21.0,
    "A": -25.0,
    "S": -29.0,
}
RIVAL_BAND_HALF_S = 4.0          # half-width of an event's absolute pace band, seconds
# Deterministic rival pace tiers, as a fraction of base_lap_time. Kept small: this
# only sets a soft finishing order, not the race-long gaps. Per-tick variance
# (RIVAL_TICK_VARIANCE_S) does the shuffling so the field stays a tight pack.
RIVAL_SPREAD_FRAC = 0.003        # ~±0.29s/lap tier on a 95s track (each side of centre)
RIVAL_TARGET_JITTER_S = 0.15     # per-rival random jitter on target lap, seconds
RIVAL_TICK_VARIANCE_S = 0.06     # per-TICK random jitter on each rival's pace (live shuffling)
RIVAL_REF_PACE = 50              # neutral driver pace used to measure a car's natural lap
RIVAL_PACE_MIN = 22              # clamp bounds for solved rival driver pace
RIVAL_PACE_MAX = 96
RIVAL_PERF_SCALAR_MIN = 0.80     # clamp bounds for per-rival car-performance scalar fallback
RIVAL_PERF_SCALAR_MAX = 1.45
RIVAL_PLAYER_EDGE_S = 0.15       # per-lap pace the field cedes the player, so skill/strategy can win
RIVAL_REACTIVE_GAP_S = 1.0       # opponents push only in an immediate battle within this gap (interactive)
RACE_DISTANCE_LAP_PROGRESS = 1.0
LOW_FEEDBACK_THRESHOLD = 50
HIGH_FEEDBACK_THRESHOLD = 75

CLASS_RATING_SCALE = 4
CLASS_RATING_WEIGHTS: dict[str, float] = {
    "acceleration": 0.20,
    "top_speed": 0.15,
    "grip": 0.20,
    "braking": 0.15,
    "handling": 0.15,
    "aero": 0.05,
    "reliability": 0.05,
    "condition": 0.05,
}
CLASS_THRESHOLDS: dict[str, int] = {
    "E": 0,
    "D": 200,
    "C": 300,
    "B": 400,
    "A": 500,
    "S": 600,
}

MIN_CONDITION_FACTOR = 0.40
BRAKE_BIAS_IDEAL = 0.60
BRAKE_BIAS_PENALTY = 0.55
PRESSURE_IDEAL_BAR = 2.25
PRESSURE_PENALTY = 0.12
CAMBER_IDEAL_DEG = 2.0
CAMBER_PENALTY = 0.08
RIDE_HEIGHT_IDEAL_MM = 135
RIDE_HEIGHT_PENALTY = 0.002
WEIGHT_REFERENCE_KG = 1100
DOWNFORCE_DRAG_PENALTY = 0.06
COOLING_HEAT_REDUCTION = 0.006
STRESS_RELIABILITY_PENALTY = 0.004
FINAL_DRIVE_IDEAL = 4.0
FINAL_DRIVE_ACCEL_FACTOR = 0.12
FINAL_DRIVE_SPEED_FACTOR = 0.08

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
