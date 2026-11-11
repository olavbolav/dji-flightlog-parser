"""Frame data models matching the Rust parser's JSON output structure.

Default frames (``Frame.to_dict()`` on a frame built without ``extended``)
keep the Rust parser's key set; the only addition is ``appGps.altitude``.
Frames built with ``extended`` add the top-level rtk/airLink/navigation/
appHud/secondaryGimbal sections and extra keys in the existing sections
(the ``EXTENDED`` blocks in the ``to_dict`` methods below). Extra keys are
None when the log does not carry the value.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# Immutable value types in frames: a snapshot shares them with the source
_SNAPSHOT_LEAVES = frozenset({str, int, float, bool, type(None), datetime})
_is_dataclass_type: dict[type, bool] = {}  # is_dataclass() per class, cached (it is slow)


def _snapshot(value: Any) -> Any:
    """Copy one frame value for ``Frame.snapshot``: dataclasses, lists and dicts recursively."""
    cls = type(value)
    if cls in _SNAPSHOT_LEAVES:
        return value
    if cls is list:
        return [v if type(v) in _SNAPSHOT_LEAVES else _snapshot(v) for v in value]
    if cls is dict:
        return {k: _snapshot(v) for k, v in value.items()}
    is_dc = _is_dataclass_type.get(cls)
    if is_dc is None:
        is_dc = _is_dataclass_type[cls] = is_dataclass(cls)
    if is_dc and hasattr(value, "__dict__"):
        new = cls.__new__(cls)
        state = value.__dict__.copy()
        # Most sections hold leaves only; the check runs in C
        if not _SNAPSHOT_LEAVES.issuperset(map(type, state.values())):
            for k, v in state.items():
                if type(v) not in _SNAPSHOT_LEAVES:
                    state[k] = _snapshot(v)
        new.__dict__ = state
        return new
    return copy.deepcopy(value)  # any other type (none in today's frames)


@dataclass
class FrameCustom:
    date_time: datetime = field(default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc))

    def to_dict(self) -> dict:
        return {"dateTime": self.date_time.isoformat().replace("+00:00", "Z")}


@dataclass
class FrameOSD:
    fly_time: float = 0.0
    latitude: float = 0.0
    longitude: float = 0.0
    height: float = 0.0
    height_max: float = 0.0
    vps_height: float = 0.0
    altitude: float = 0.0
    x_speed: float = 0.0
    x_speed_max: float = 0.0
    y_speed: float = 0.0
    y_speed_max: float = 0.0
    z_speed: float = 0.0
    z_speed_max: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    flyc_state: Optional[str] = None
    flyc_command: Optional[str] = None
    flight_action: Optional[str] = None
    is_gpd_used: bool = False  # matches Rust typo
    non_gps_cause: Optional[str] = None
    gps_num: int = 0
    gps_level: int = 0
    drone_type: Optional[str] = None
    is_swave_work: bool = False
    wave_error: bool = False
    go_home_status: Optional[str] = None
    battery_type: Optional[str] = None
    is_on_ground: bool = False
    is_motor_on: bool = False
    is_motor_blocked: bool = False
    motor_start_failed_cause: Optional[str] = None
    is_imu_preheated: bool = False
    imu_init_fail_reason: Optional[str] = None
    is_acceletor_over_range: bool = False
    is_barometer_dead_in_air: bool = False
    is_compass_error: bool = False
    is_go_home_height_modified: bool = False
    can_ioc_work: bool = False
    is_not_enough_force: bool = False
    is_out_of_limit: bool = False
    is_propeller_catapult: bool = False
    is_vibrating: bool = False
    is_vision_used: bool = False
    voltage_warning: int = 0
    # Extended only
    # m/s, 0 = calm or no estimate; None when the OSD record has no wind
    # byte (shorter than 65 bytes) or reports 255 (no estimate)
    wind_speed: Optional[float] = None
    # Direction the wind blows from; None when calm, and in the same cases
    # as wind_speed
    wind_direction: Optional[str] = None
    position_source: Optional[str] = None  # "None", "Vision", "GNSS", "RTKFixed"
    position_source_code: Optional[int] = None
    yaw_rate: Optional[float] = None  # deg/s, positive = clockwise seen from above
    home_offset_north: Optional[float] = None  # metres from the home point
    home_offset_east: Optional[float] = None

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "flyTime": self.fly_time,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "height": self.height,
            "heightMax": self.height_max,
            "vpsHeight": self.vps_height,
            "altitude": self.altitude,
            "xSpeed": self.x_speed,
            "xSpeedMax": self.x_speed_max,
            "ySpeed": self.y_speed,
            "ySpeedMax": self.y_speed_max,
            "zSpeed": self.z_speed,
            "zSpeedMax": self.z_speed_max,
            "pitch": self.pitch,
            "roll": self.roll,
            "yaw": self.yaw,
            "flycState": self.flyc_state,
            "flycCommand": self.flyc_command,
            "flightAction": self.flight_action,
            "isGpdUsed": self.is_gpd_used,
            "nonGpsCause": self.non_gps_cause,
            "gpsNum": self.gps_num,
            "gpsLevel": self.gps_level,
            "droneType": self.drone_type,
            "isSwaveWork": self.is_swave_work,
            "waveError": self.wave_error,
            "goHomeStatus": self.go_home_status,
            "batteryType": self.battery_type,
            "isOnGround": self.is_on_ground,
            "isMotorOn": self.is_motor_on,
            "isMotorBlocked": self.is_motor_blocked,
            "motorStartFailedCause": self.motor_start_failed_cause,
            "isImuPreheated": self.is_imu_preheated,
            "imuInitFailReason": self.imu_init_fail_reason,
            "isAcceletorOverRange": self.is_acceletor_over_range,
            "isBarometerDeadInAir": self.is_barometer_dead_in_air,
            "isCompassError": self.is_compass_error,
            "isGoHomeHeightModified": self.is_go_home_height_modified,
            "canIocWork": self.can_ioc_work,
            "isNotEnoughForce": self.is_not_enough_force,
            "isOutOfLimit": self.is_out_of_limit,
            "isPropellerCatapult": self.is_propeller_catapult,
            "isVibrating": self.is_vibrating,
            "isVisionUsed": self.is_vision_used,
            "voltageWarning": self.voltage_warning,
        }
        if extended:
            d.update({
                "windSpeed": self.wind_speed,
                "windDirection": self.wind_direction,
                "positionSource": self.position_source,
                "positionSourceCode": self.position_source_code,
                "yawRate": self.yaw_rate,
                "homeOffsetNorth": self.home_offset_north,
                "homeOffsetEast": self.home_offset_east,
            })
        return d


@dataclass
class FrameGimbal:
    mode: Optional[str] = None
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    is_pitch_at_limit: bool = False
    is_roll_at_limit: bool = False
    is_yaw_at_limit: bool = False
    is_stuck: bool = False
    # Extended only
    yaw_relative_to_aircraft: Optional[float] = None  # deg, gimbal yaw joint vs aircraft heading
    joint_pitch: Optional[float] = None  # deg, pitch relative to the airframe
    is_resetting: Optional[bool] = None  # set if any Gimbal record in the frame had it

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "mode": self.mode,
            "pitch": self.pitch,
            "roll": self.roll,
            "yaw": self.yaw,
            "isPitchAtLimit": self.is_pitch_at_limit,
            "isRollAtLimit": self.is_roll_at_limit,
            "isYawAtLimit": self.is_yaw_at_limit,
            "isStuck": self.is_stuck,
        }
        if extended:
            d.update({
                "yawRelativeToAircraft": self.yaw_relative_to_aircraft,
                "jointPitch": self.joint_pitch,
                "isResetting": self.is_resetting,
            })
        return d


@dataclass
class FrameCamera:
    is_photo: bool = False
    is_video: bool = False
    sd_card_is_inserted: bool = False
    sd_card_state: Optional[str] = None
    # Extended only
    work_mode: Optional[int] = None  # 0 photo, 1 video, 2 playback, 7 new playback
    sd_card_total_mb: Optional[int] = None
    sd_card_free_mb: Optional[int] = None
    remaining_photos: Optional[int] = None
    remaining_video_seconds: Optional[int] = None

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "isPhoto": self.is_photo,
            "isVideo": self.is_video,
            "sdCardIsInserted": self.sd_card_is_inserted,
            "sdCardState": self.sd_card_state,
        }
        if extended:
            d.update({
                "workMode": self.work_mode,
                "sdCardTotalMb": self.sd_card_total_mb,
                "sdCardFreeMb": self.sd_card_free_mb,
                "remainingPhotos": self.remaining_photos,
                "remainingVideoSeconds": self.remaining_video_seconds,
            })
        return d


@dataclass
class FrameRC:
    downlink_signal: Optional[int] = None
    uplink_signal: Optional[int] = None
    aileron: int = 0
    elevator: int = 0
    throttle: int = 0
    rudder: int = 0
    # Extended only (RC display record type 62). The buttons are momentary:
    # True if any record in the frame had the button down.
    is_shutter_half_pressed: Optional[bool] = None
    is_shutter_pressed: Optional[bool] = None
    is_record_pressed: Optional[bool] = None
    is_custom_button_1_pressed: Optional[bool] = None
    is_custom_button_2_pressed: Optional[bool] = None
    left_dial: Optional[int] = None  # stick scale 364-1684, centre 1024
    right_dial: Optional[int] = None

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "downlinkSignal": self.downlink_signal,
            "uplinkSignal": self.uplink_signal,
            "aileron": self.aileron,
            "elevator": self.elevator,
            "throttle": self.throttle,
            "rudder": self.rudder,
        }
        if extended:
            d.update({
                "isShutterHalfPressed": self.is_shutter_half_pressed,
                "isShutterPressed": self.is_shutter_pressed,
                "isRecordPressed": self.is_record_pressed,
                "isCustomButton1Pressed": self.is_custom_button_1_pressed,
                "isCustomButton2Pressed": self.is_custom_button_2_pressed,
                "leftDial": self.left_dial,
                "rightDial": self.right_dial,
            })
        return d

    def release_buttons(self) -> None:
        """Clear the momentary buttons at the start of a frame (keep None = no data)."""
        for name in _RC_BUTTONS:
            if getattr(self, name) is not None:
                setattr(self, name, False)


_RC_BUTTONS = (
    "is_shutter_half_pressed", "is_shutter_pressed", "is_record_pressed",
    "is_custom_button_1_pressed", "is_custom_button_2_pressed",
)


@dataclass
class FrameBatteryPack:
    """One pack of a dual-battery aircraft (SmartBatteryGroup dynamic index >= 1)."""
    index: int = 0
    charge_level: int = 0
    voltage: float = 0.0
    current: float = 0.0
    current_capacity: int = 0
    full_capacity: int = 0
    temperature: float = 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "chargeLevel": self.charge_level,
            "voltage": self.voltage,
            "current": self.current,
            "currentCapacity": self.current_capacity,
            "fullCapacity": self.full_capacity,
            "temperature": self.temperature,
        }


@dataclass
class FrameBattery:
    charge_level: int = 0
    voltage: float = 0.0
    current: float = 0.0
    current_capacity: int = 0
    full_capacity: int = 0
    cell_num: int = 4
    is_cell_voltage_estimated: bool = True
    cell_voltages: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    cell_voltage_deviation: float = 0.0
    max_cell_voltage_deviation: float = 0.0
    temperature: float = 0.0
    min_temperature: float = 0.0
    max_temperature: float = 0.0
    cycle_count: Optional[int] = None
    designed_capacity: Optional[int] = None
    battery_serial: str = ""
    # Extended only
    state_of_health: Optional[int] = None  # %, from the static record; None when unknown (0)
    remaining_energy: Optional[float] = None  # Wh
    low_warning_threshold: Optional[int] = None  # %, OSD low-battery warning level
    critical_warning_threshold: Optional[int] = None  # %, OSD critical warning level
    packs: Optional[list[FrameBatteryPack]] = None  # dual-battery aircraft only

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "chargeLevel": self.charge_level,
            "voltage": self.voltage,
            "current": self.current,
            "currentCapacity": self.current_capacity,
            "fullCapacity": self.full_capacity,
            "cellNum": self.cell_num,
            "isCellVoltageEstimated": self.is_cell_voltage_estimated,
            "cellVoltages": list(self.cell_voltages),
            "cellVoltageDeviation": self.cell_voltage_deviation,
            "maxCellVoltageDeviation": self.max_cell_voltage_deviation,
            "temperature": self.temperature,
            "minTemperature": self.min_temperature,
            "maxTemperature": self.max_temperature,
            "cycleCount": self.cycle_count,
            "designedCapacity": self.designed_capacity,
            "batterySerial": self.battery_serial or None,
        }
        if extended:
            d.update({
                "stateOfHealth": self.state_of_health,
                "remainingEnergy": self.remaining_energy,
                "lowWarningThreshold": self.low_warning_threshold,
                "criticalWarningThreshold": self.critical_warning_threshold,
                "packs": None if self.packs is None else [p.to_dict() for p in self.packs],
            })
        return d


@dataclass
class FrameHome:
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    height_limit: float = 0.0
    is_home_record: bool = False
    go_home_mode: Optional[str] = None
    is_dynamic_home_point_enabled: bool = False
    is_near_distance_limit: bool = False
    is_near_height_limit: bool = False
    is_compass_calibrating: bool = False
    compass_calibration_state: Optional[str] = None
    is_multiple_mode_enabled: bool = False
    is_beginner_mode: bool = False
    is_ioc_enabled: bool = False
    ioc_mode: Optional[str] = None
    go_home_height: int = 0
    ioc_course_lock_angle: Optional[int] = None
    max_allowed_height: float = 0.0
    current_flight_record_index: int = 0

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "heightLimit": self.height_limit,
            "isHomeRecord": self.is_home_record,
            "goHomeMode": self.go_home_mode,
            "isDynamicHomePointEnabled": self.is_dynamic_home_point_enabled,
            "isNearDistanceLimit": self.is_near_distance_limit,
            "isNearHeightLimit": self.is_near_height_limit,
            "isCompassCalibrating": self.is_compass_calibrating,
            "compassCalibrationState": self.compass_calibration_state,
            "isMultipleModeEnabled": self.is_multiple_mode_enabled,
            "isBeginnerMode": self.is_beginner_mode,
            "isIocEnabled": self.is_ioc_enabled,
            "iocMode": self.ioc_mode,
            "goHomeHeight": self.go_home_height,
            "iocCourseLockAngle": self.ioc_course_lock_angle,
            "maxAllowedHeight": self.max_allowed_height,
            "currentFlightRecordIndex": self.current_flight_record_index,
        }


@dataclass
class FrameRecover:
    app_platform: Optional[str] = None
    app_version: str = ""
    aircraft_name: str = ""
    aircraft_sn: str = ""
    camera_sn: str = ""
    rc_sn: str = ""
    battery_sn: str = ""

    def to_dict(self) -> dict:
        return {
            "appPlatform": self.app_platform,
            "appVersion": self.app_version,
            "aircraftName": self.aircraft_name,
            "aircraftSn": self.aircraft_sn,
            "cameraSn": self.camera_sn,
            "rcSn": self.rc_sn,
            "batterySn": self.battery_sn,
        }


@dataclass
class FrameApp:
    tip: str = ""
    warn: str = ""

    def to_dict(self) -> dict:
        return {
            "tip": self.tip,
            "warn": self.warn,
        }


@dataclass
class FrameAppGPS:
    latitude: float = 0.0
    longitude: float = 0.0
    # Pilot device altitude in metres (AppGPS f32@16), same vertical frame as
    # the aircraft GNSS heights. None until the first AppGPS record.
    altitude: Optional[float] = None

    @property
    def horizontal_accuracy(self) -> float:
        """Deprecated: the old, misnamed key for ``altitude`` (-1.0 when unknown)."""
        return -1.0 if self.altitude is None else self.altitude

    @horizontal_accuracy.setter
    def horizontal_accuracy(self, value: Optional[float]) -> None:
        # Writes through to altitude; -1.0 (the old "unknown") becomes None
        self.altitude = None if value is None or value == -1.0 else value

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "horizontalAccuracy": self.horizontal_accuracy,  # deprecated alias of altitude
            "altitude": self.altitude,
        }


@dataclass
class FrameVision:
    collision_avoidance_enabled: bool = False
    is_braking: bool = False
    is_ascent_limited: bool = False
    is_landing_confirmation_needed: bool = False
    # Extended only: ground within downward sensing range (VisionGroup
    # vert_low_limit_active). None until the first VisionGroup record.
    is_near_ground: Optional[bool] = None

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "collisionAvoidanceEnabled": self.collision_avoidance_enabled,
            "isBraking": self.is_braking,
            "isAscentLimited": self.is_ascent_limited,
            "isLandingConfirmationNeeded": self.is_landing_confirmation_needed,
        }
        if extended:
            d["isNearGround"] = self.is_near_ground
        return d


@dataclass
class FrameFlightController:
    remaining_flight_time: Optional[int] = None
    battery_percent_needed_to_land: Optional[int] = None
    battery_percent_needed_to_go_home: Optional[int] = None
    # Extended only
    time_needed_to_go_home: Optional[int] = None  # s
    time_needed_to_land: Optional[int] = None  # s
    rc_lost_action: Optional[str] = None  # "Hover", "Landing" or "GoHome"

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "remainingFlightTime": self.remaining_flight_time,
            "batteryPercentNeededToLand": self.battery_percent_needed_to_land,
            "batteryPercentNeededToGoHome": self.battery_percent_needed_to_go_home,
        }
        if extended:
            d.update({
                "timeNeededToGoHome": self.time_needed_to_go_home,
                "timeNeededToLand": self.time_needed_to_land,
                "rcLostAction": self.rc_lost_action,
            })
        return d


@dataclass
class FrameNearbyAircraft:
    icao_address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: int = 0  # metres; reference in altitude_type
    heading: float = 0.0
    # Extended only
    distance: Optional[int] = None  # horizontal distance from the aircraft, m
    relative_altitude: Optional[int] = None  # m, traffic minus aircraft (positive = above)
    vertical_trend: Optional[str] = None  # "Level", "Rising", "Falling"
    warning_level: Optional[int] = None  # AirSense level: 1 tracked, 2 caution, >= 3 avoid
    altitude_type: Optional[str] = None  # "Ellipsoid" (WGS84) or "MSL"

    def to_dict(self, extended: bool = False) -> dict:
        d = {
            "icaoAddress": self.icao_address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "heading": round(self.heading, 1),
        }
        if extended:
            d.update({
                "distance": self.distance,
                "relativeAltitude": self.relative_altitude,
                "verticalTrend": self.vertical_trend,
                "warningLevel": self.warning_level,
                "altitudeType": self.altitude_type,
            })
        return d


@dataclass
class FrameRTK:
    """RTK module status (record type 45). Only emitted with --extended."""
    position_solution: Optional[str] = None
    position_solution_code: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    height: Optional[float] = None
    std_latitude: Optional[float] = None
    std_longitude: Optional[float] = None
    std_altitude: Optional[float] = None
    satellites: Optional[int] = None
    gps_satellites: Optional[int] = None
    beidou_satellites: Optional[int] = None
    glonass_satellites: Optional[int] = None
    galileo_satellites: Optional[int] = None
    has_base: Optional[bool] = None
    correction_age: Optional[float] = None
    dual_antenna_heading: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "positionSolution": self.position_solution,
            "positionSolutionCode": self.position_solution_code,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "height": self.height,
            "stdLatitude": self.std_latitude,
            "stdLongitude": self.std_longitude,
            "stdAltitude": self.std_altitude,
            "satellites": self.satellites,
            "gpsSatellites": self.gps_satellites,
            "beidouSatellites": self.beidou_satellites,
            "glonassSatellites": self.glonass_satellites,
            "galileoSatellites": self.galileo_satellites,
            "hasBase": self.has_base,
            "correctionAge": self.correction_age,
            "dualAntennaHeading": self.dual_antenna_heading,
        }


@dataclass
class FrameAirLink:
    """Radio-link status (record type 57). Only emitted with --extended."""
    sdr_link_up: Optional[bool] = None
    lte_link_up: Optional[bool] = None
    sdr_quality: Optional[int] = None
    lte_quality: Optional[int] = None
    link_quality: Optional[int] = None
    work_mode: Optional[str] = None
    lte_level_a: Optional[int] = None
    lte_level_b: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "sdrLinkUp": self.sdr_link_up,
            "lteLinkUp": self.lte_link_up,
            "sdrQuality": self.sdr_quality,
            "lteQuality": self.lte_quality,
            "linkQuality": self.link_quality,
            "workMode": self.work_mode,
            "lteLevelA": self.lte_level_a,
            "lteLevelB": self.lte_level_b,
        }


@dataclass
class FrameNavigation:
    """Flight-controller navigation state (record type 48). Only with --extended."""
    aircraft_clock: Optional[float] = None
    satellites_used: Optional[int] = None
    distance_to_home: Optional[float] = None
    is_rtk_fixed: Optional[bool] = None
    relative_height: Optional[float] = None
    gnss_height: Optional[float] = None
    geoid_undulation: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "aircraftClock": self.aircraft_clock,
            "satellitesUsed": self.satellites_used,
            "distanceToHome": self.distance_to_home,
            "isRtkFixed": self.is_rtk_fixed,
            "relativeHeight": self.relative_height,
            "gnssHeight": self.gnss_height,
            "geoidUndulation": self.geoid_undulation,
        }


@dataclass
class FrameHudWarning:
    text: str = ""
    code: str = ""
    level: int = 0

    def to_dict(self) -> dict:
        return {"text": self.text, "code": self.code, "level": self.level}


@dataclass
class FrameAppHud:
    """DJI Fly on-screen notifications (record type 54). Only with --extended."""
    status_bar: Optional[str] = None
    status_bar_level: Optional[int] = None
    tip: Optional[str] = None
    tip_code: Optional[str] = None
    warnings: Optional[list[FrameHudWarning]] = None  # None until the first warning-list update

    def to_dict(self) -> dict:
        return {
            "statusBar": self.status_bar,
            "statusBarLevel": self.status_bar_level,
            "tip": self.tip,
            "tipCode": self.tip_code,
            "warnings": None if self.warnings is None else [w.to_dict() for w in self.warnings],
        }


@dataclass
class FrameSecondaryGimbal:
    """Second gimbal device in the Gimbal records (record type 3). Only with --extended.

    Seen only on Matrice 4TD airframes with a top accessory, most likely the
    AL1 spotlight. It tilts in pitch only; its pitch and yaw follow the
    camera gimbal, with a stop at +35 deg (seen in the one log where the
    camera tilted higher). Its roll follows the aircraft. The limit flag was
    never set in the logs seen.
    """
    pitch: Optional[float] = None
    roll: Optional[float] = None
    yaw: Optional[float] = None
    is_pitch_at_limit: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "pitch": self.pitch,
            "roll": self.roll,
            "yaw": self.yaw,
            "isPitchAtLimit": self.is_pitch_at_limit,
        }


@dataclass
class FrameExtended:
    """Sections decoded from record types 45, 48, 54 and 57, plus the second gimbal."""
    rtk: FrameRTK = field(default_factory=FrameRTK)
    air_link: FrameAirLink = field(default_factory=FrameAirLink)
    navigation: FrameNavigation = field(default_factory=FrameNavigation)
    app_hud: FrameAppHud = field(default_factory=FrameAppHud)
    secondary_gimbal: FrameSecondaryGimbal = field(default_factory=FrameSecondaryGimbal)

    def to_dict(self) -> dict:
        return {
            "rtk": self.rtk.to_dict(),
            "airLink": self.air_link.to_dict(),
            "navigation": self.navigation.to_dict(),
            "appHud": self.app_hud.to_dict(),
            "secondaryGimbal": self.secondary_gimbal.to_dict(),
        }


@dataclass
class Frame:
    custom: FrameCustom = field(default_factory=FrameCustom)
    osd: FrameOSD = field(default_factory=FrameOSD)
    gimbal: FrameGimbal = field(default_factory=FrameGimbal)
    camera: FrameCamera = field(default_factory=FrameCamera)
    rc: FrameRC = field(default_factory=FrameRC)
    battery: FrameBattery = field(default_factory=FrameBattery)
    home: FrameHome = field(default_factory=FrameHome)
    recover: FrameRecover = field(default_factory=FrameRecover)
    app: FrameApp = field(default_factory=FrameApp)
    app_gps: FrameAppGPS = field(default_factory=FrameAppGPS)
    vision: FrameVision = field(default_factory=FrameVision)
    flight_controller: FrameFlightController = field(default_factory=FrameFlightController)
    nearby_aircraft: list[FrameNearbyAircraft] = field(default_factory=list)
    extended: Optional[FrameExtended] = None  # set only with --extended

    def snapshot(self) -> Frame:
        """Return an independent copy of this frame; same result as ``copy.deepcopy``, faster.

        Every dataclass instance, list and dict is copied; the immutable
        values (str, int, float, bool, None, datetime) are shared. A frame is
        a tree: the builder never puts one mutable object in two places of a
        frame and frames have no cycles (checked at every emitted frame of the
        74-log corpus, default and extended), so deepcopy's memo, which would
        keep such sharing, is not needed. The copy shares no mutable object
        with this frame, so later changes to it, its lists or its pack, nearby
        aircraft and HUD warning objects do not reach the copy. Values of any
        other type go through ``copy.deepcopy``.
        """
        return _snapshot(self)

    def reset(self) -> None:
        """Reset transient fields between frames."""
        self.camera.is_photo = False
        self.rc.release_buttons()
        if self.gimbal.is_resetting is not None:
            self.gimbal.is_resetting = False
        self.app.tip = ""
        self.app.warn = ""
        if self.battery.is_cell_voltage_estimated:
            self.battery.cell_voltages = [0.0] * len(self.battery.cell_voltages)

    def finalize(self) -> None:
        """Compute derived values before emitting a frame."""
        if self.osd.height_max < self.osd.height:
            self.osd.height_max = self.osd.height
        if abs(self.osd.x_speed_max) < abs(self.osd.x_speed):
            self.osd.x_speed_max = self.osd.x_speed
        if abs(self.osd.y_speed_max) < abs(self.osd.y_speed):
            self.osd.y_speed_max = self.osd.y_speed
        if abs(self.osd.z_speed_max) < abs(self.osd.z_speed):
            self.osd.z_speed_max = self.osd.z_speed

        cvs = self.battery.cell_voltages
        if cvs and cvs[0] == 0.0 and self.battery.voltage > 0.0:
            self.battery.is_cell_voltage_estimated = True
            fill_val = self.battery.voltage / max(self.battery.cell_num, 1)
            self.battery.cell_voltages = [fill_val] * len(cvs)

        if self.battery.temperature > self.battery.max_temperature:
            self.battery.max_temperature = self.battery.temperature
        if (self.battery.temperature < self.battery.min_temperature
                or self.battery.min_temperature == 0.0):
            self.battery.min_temperature = self.battery.temperature

        if cvs:
            max_v = max(cvs)
            min_v = min(cvs)
            self.battery.cell_voltage_deviation = round((max_v - min_v) * 1000) / 1000
            if self.battery.cell_voltage_deviation > self.battery.max_cell_voltage_deviation:
                self.battery.max_cell_voltage_deviation = self.battery.cell_voltage_deviation

    def to_dict(self) -> dict:
        extended = self.extended is not None
        d = self._base_dict(extended)
        if extended:
            d.update(self.extended.to_dict())
        return d

    def _base_dict(self, extended: bool = False) -> dict:
        return {
            "custom": self.custom.to_dict(),
            "osd": self.osd.to_dict(extended),
            "gimbal": self.gimbal.to_dict(extended),
            "camera": self.camera.to_dict(extended),
            "rc": self.rc.to_dict(extended),
            "battery": self.battery.to_dict(extended),
            "home": self.home.to_dict(),
            "recover": self.recover.to_dict(),
            "app": self.app.to_dict(),
            "appGps": self.app_gps.to_dict(),
            "vision": self.vision.to_dict(extended),
            "flightController": self.flight_controller.to_dict(extended),
            "nearbyAircraft": [a.to_dict(extended) for a in self.nearby_aircraft],
        }
