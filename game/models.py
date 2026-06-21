from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CarIdentity:
    id: str
    name: str
    year: int
    manufacturer: str
    model: str
    drivetrain: str
    layout: str
    tags: list[str]


@dataclass
class PowertrainStats:
    power_hp: int
    torque_nm: int
    powerband: int
    throttle_response: int
    engine_reliability: int
    cooling: int
    aspiration: str
    engine_stress: int


@dataclass
class ChassisStats:
    weight_kg: int
    weight_distribution_front: float
    center_of_gravity: int
    chassis_rigidity: int
    stability: int
    rotation: int


@dataclass
class TireStats:
    tire_compound: str
    tire_width_front: int
    tire_width_rear: int
    base_grip: int
    wet_grip: int
    tire_wear_resistance: int
    tire_heat_resistance: int
    tire_warmup: int


@dataclass
class BrakeStats:
    braking_power: int
    brake_stability: int
    brake_cooling: int
    brake_fade_resistance: int


@dataclass
class SuspensionStats:
    handling: int
    mechanical_grip: int
    suspension_compliance: int
    curb_handling: int
    bump_absorption: int
    steering_precision: int


@dataclass
class AeroStats:
    downforce: int
    drag: int
    aero_efficiency: int
    high_speed_stability: int


@dataclass
class DurabilityStats:
    overall_reliability: int
    engine_reliability: int
    gearbox_reliability: int
    suspension_durability: int
    brake_durability: int
    cooling_capacity: int
    mechanical_sympathy_modifier: int


@dataclass
class FuelStats:
    fuel_capacity_l: float
    base_fuel_burn: float
    fuel_efficiency: int


@dataclass
class CarCondition:
    overall_condition: float
    engine_condition: float
    gearbox_condition: float
    suspension_condition: float
    brake_condition: float
    body_condition: float
    tire_condition: float
    mileage: int


@dataclass
class TuneSetup:
    tire_pressure_front: float
    tire_pressure_rear: float
    final_drive: float
    gear_bias: float
    brake_bias: float
    brake_pressure: float
    front_ride_height: int
    rear_ride_height: int
    suspension_stiffness_front: int
    suspension_stiffness_rear: int
    antiroll_front: int
    antiroll_rear: int
    camber_front: float
    camber_rear: float
    toe_front: float
    toe_rear: float
    front_downforce: int
    rear_downforce: int
    differential_power: int
    differential_coast: int
    differential_preload: int
    engine_map: str


@dataclass
class Car:
    identity: CarIdentity
    powertrain: PowertrainStats
    chassis: ChassisStats
    tires: TireStats
    brakes: BrakeStats
    suspension: SuspensionStats
    aero: AeroStats
    durability: DurabilityStats
    fuel: FuelStats
    condition: CarCondition
    installed_parts: list[str]
    tune: TuneSetup
    value: int


@dataclass
class Part:
    id: str
    name: str
    category: str
    cost: int
    modifiers: dict[str, int | float]
    class_rating_delta: int


@dataclass
class TrackSegment:
    name: str
    length_pct: float
    tags: list[str]
    surface: str
    condition: str


@dataclass
class SegmentProfile:
    """Per-segment, position-resolved data used to run a race segment by segment.

    Weights/rates are *intensive* (per unit of track position): the length-weighted
    sum across a lap's profiles reproduces the track's aggregate weights/rates, so a
    dry tarmac track integrates to exactly the same lap time and wear as the aggregate
    model. ``grip_mult``/``tire_wear_mult``/``wet_weight`` carry the resolved
    surface+condition effects (see SURFACE_MODIFIERS / CONDITION_MODIFIERS).
    """

    name: str
    length_pct: float
    start_pct: float
    end_pct: float
    surface: str
    condition: str
    weights: dict[str, float]
    tire_wear_rate: float
    fuel_burn_rate: float
    engine_heat_rate: float
    grip_mult: float
    tire_wear_mult: float
    wet_weight: float


@dataclass
class Track:
    id: str
    name: str
    layout_type: str
    base_lap_time: float
    length_km: float
    pit_lane_loss_s: float
    segments: list[TrackSegment]
    overtake_difficulty: float
    elevation_change_m: int
    surface: str
    default_condition: str
    weather_variability: float
    power_weight: float = 0.0
    acceleration_weight: float = 0.0
    top_speed_weight: float = 0.0
    grip_weight: float = 0.0
    braking_weight: float = 0.0
    handling_weight: float = 0.0
    aero_weight: float = 0.0
    tire_wear_rate: float = 0.0
    fuel_burn_rate: float = 0.0
    engine_heat_rate: float = 0.0
    # Net climb grade (%) for the per-car hillclimb time penalty. Derived at load and 0.0 for
    # loop layouts (which return to start), so it never penalises a circuit. See loader.
    climb_gradient_pct: float = 0.0
    segment_profiles: list[SegmentProfile] = field(default_factory=list)


@dataclass
class Driver:
    id: str
    name: str
    pace: int
    consistency: int
    racecraft: int
    feedback: int
    fitness: int
    aggression: int
    mechanical_sympathy: int
    wet_skill: int
    salary: int
    experience: int = 0


@dataclass
class Event:
    id: str
    name: str
    track_id: str
    car_class_limit: str
    entry_fee: int
    prize_money: list[int]
    opponent_count: int
    restrictions: dict
    rival_skill: int | None = None
    # Race length lives on the event, not the track: one track hosts a 5-lap sprint and a
    # 24h enduro. Exactly one of these is set (validated in the loader). distance_km is
    # resolved against the track's length_km; duration_s is time-based (structurally
    # supported but not yet wired into the race loop).
    laps: int | None = None
    distance_km: float | None = None
    duration_s: float | None = None


@dataclass
class RaceFormat:
    """How long a race runs, resolved from an event against its track.

    ``laps`` is the fixed lap target for lap- and distance-based races (the loop runs
    exactly that many). ``mode`` records how it was specified; for ``duration`` the race
    is open-ended (``laps`` is None) and the loop stops on the time predicate.
    """

    mode: str  # "laps" | "distance" | "duration"
    laps: int | None
    distance_km: float | None = None
    duration_s: float | None = None


@dataclass
class EffectiveCarStats:
    power: float
    torque: float
    weight: float
    acceleration: float
    top_speed: float
    braking: float
    brake_stability: float
    grip: float
    wet_grip: float
    handling: float
    mechanical_grip: float
    aero_grip: float
    drag: float
    stability: float
    tire_wear_rate: float
    tire_heat_rate: float
    fuel_burn_rate: float
    engine_heat_rate: float
    reliability: float
    suspension_compliance: float
    curb_handling: float
    drivetrain: str = "RWD"
    # Physical attrition inputs: fuel economy is fuel_burn_rate × FUEL_L_PER_KM_UNIT
    # (litres/km), drawn against this tank; tyre life derives from tire_wear_rate.
    fuel_capacity_l: float = 0.0


@dataclass
class TelemetryHistory:
    lap_times: list[float] = field(default_factory=list)
    positions: list[int] = field(default_factory=list)
    engine_temps: list[float] = field(default_factory=list)
    fuel_pct: list[float] = field(default_factory=list)
    tire_wear: list[float] = field(default_factory=list)
    tire_temps: list[float] = field(default_factory=list)
    driver_energy: list[float] = field(default_factory=list)
    driver_focus: list[float] = field(default_factory=list)
    driver_stress: list[float] = field(default_factory=list)


@dataclass
class RaceCarState:
    car_id: str
    driver_id: str
    label: str
    is_player: bool
    position: int
    lap: int
    distance: float
    gap_to_leader: float
    tire_pct: float
    tire_temp: float
    fuel_pct: float
    condition_pct: float
    engine_temp: float
    driver_energy: float
    driver_focus: float
    driver_stress: float
    pace_mode: str
    last_lap_time: float | None
    total_time: float
    event_log: list[str]
    is_dnf: bool = False
    lap_elapsed: float = 0.0


@dataclass
class RaceSession:
    event_id: str
    track_id: str
    current_lap: int
    total_laps: int
    cars: list[RaceCarState]
    player_car_id: str
    is_finished: bool
    telemetry: dict[str, TelemetryHistory]
    race_log: list[tuple[int, str]]
    random_seed: int
    car_roster: dict[str, Car] = field(default_factory=dict)
    driver_roster: dict[str, Driver] = field(default_factory=dict)
    track: Track | None = None
    event: Event | None = None
    parts: list[Part] = field(default_factory=list)
    ticks_per_lap: int = 1
    current_sub_tick: int = 0
    # Set for duration (Regime A) races: the time cap the leader must cross before the
    # lockstep field finishes the lead lap. None for lap/distance races, where total_laps is
    # the fixed target. For duration races total_laps instead tracks the completed lap count.
    duration_s: float | None = None


@dataclass
class RaceTickResult:
    session: RaceSession
    lap: int
    standings: list[RaceCarState]
    event_log: list[str]
    is_lap_end: bool = False


@dataclass
class RaceResult:
    event_id: str
    track_id: str
    total_laps: int
    standings: list[RaceCarState]
    player_position: int
    prize_money: int
    lap_times: dict[str, list[float]]
    race_log: list[str]
