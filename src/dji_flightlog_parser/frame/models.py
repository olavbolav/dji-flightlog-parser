"""Frame data models matching the Rust parser's JSON output structure."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


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

    def to_dict(self) -> dict:
        return {
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

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "pitch": self.pitch,
            "roll": self.roll,
            "yaw": self.yaw,
            "isPitchAtLimit": self.is_pitch_at_limit,
            "isRollAtLimit": self.is_roll_at_limit,
            "isYawAtLimit": self.is_yaw_at_limit,
            "isStuck": self.is_stuck,
        }


@dataclass
class FrameCamera:
    is_photo: bool = False
    is_video: bool = False
    sd_card_is_inserted: bool = False
    sd_card_state: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "isPhoto": self.is_photo,
            "isVideo": self.is_video,
            "sdCardIsInserted": self.sd_card_is_inserted,
            "sdCardState": self.sd_card_state,
        }


@dataclass
class FrameRC:
    downlink_signal: Optional[int] = None
    uplink_signal: Optional[int] = None
    aileron: int = 0
    elevator: int = 0
    throttle: int = 0
    rudder: int = 0

    def to_dict(self) -> dict:
        return {
            "downlinkSignal": self.downlink_signal,
            "uplinkSignal": self.uplink_signal,
            "aileron": self.aileron,
            "elevator": self.elevator,
            "throttle": self.throttle,
            "rudder": self.rudder,
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

    def to_dict(self) -> dict:
        return {
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
        }


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

    def reset(self) -> None:
        """Reset transient fields between frames."""
        self.camera.is_photo = False
        self.app.tip = ""
        self.app.warn = ""
        if self.battery.is_cell_voltage_estimated:
            self.battery.cell_voltages = [0.0] * len(self.battery.cell_voltages)

    def finalize(self) -> None:
        """Compute derived values before emitting a frame."""
        if self.osd.height_max < self.osd.height:
            self.osd.height_max = self.osd.height
        if self.osd.x_speed_max < self.osd.x_speed:
            self.osd.x_speed_max = self.osd.x_speed
        if self.osd.y_speed_max < self.osd.y_speed:
            self.osd.y_speed_max = self.osd.y_speed
        if self.osd.z_speed_max < self.osd.z_speed:
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
        return {
            "custom": self.custom.to_dict(),
            "osd": self.osd.to_dict(),
            "gimbal": self.gimbal.to_dict(),
            "camera": self.camera.to_dict(),
            "rc": self.rc.to_dict(),
            "battery": self.battery.to_dict(),
            "home": self.home.to_dict(),
            "recover": self.recover.to_dict(),
            "app": self.app.to_dict(),
        }
