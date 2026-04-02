"""CSV tabular export of frame data."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

from ..frame.models import Frame

_CSV_FORMULA_CHARS = frozenset("=+@\t\r")


def _sanitize_csv(val: object) -> object:
    """Prevent CSV formula injection in spreadsheet applications."""
    if isinstance(val, str) and val and val[0] in _CSV_FORMULA_CHARS:
        return "'" + val
    return val


HEADERS = [
    "CUSTOM.dateTime",
    "OSD.flyTime", "OSD.latitude", "OSD.longitude",
    "OSD.height", "OSD.heightMax", "OSD.vpsHeight", "OSD.altitude",
    "OSD.xSpeed", "OSD.xSpeedMax", "OSD.ySpeed", "OSD.ySpeedMax",
    "OSD.zSpeed", "OSD.zSpeedMax",
    "OSD.pitch", "OSD.roll", "OSD.yaw",
    "OSD.flycState", "OSD.flycCommand", "OSD.flightAction",
    "OSD.isGPSUsed", "OSD.nonGpsCause", "OSD.gpsNum", "OSD.gpsLevel",
    "OSD.droneType", "OSD.isSwaveWork", "OSD.waveError",
    "OSD.goHomeStatus", "OSD.batteryType",
    "OSD.isOnGround", "OSD.isMotorOn", "OSD.isMotorBlocked",
    "OSD.motorStartFailedCause", "OSD.isImuPreheated", "OSD.imuInitFailReason",
    "OSD.isAcceletorOverRange", "OSD.isBarometerDeadInAir",
    "OSD.isCompassError", "OSD.isGoHomeHeightModified",
    "OSD.canIocWork", "OSD.isNotEnoughForce", "OSD.isOutOfLimit",
    "OSD.isPropellerCatapult", "OSD.isVibrating", "OSD.isVisionUsed",
    "OSD.voltageWarning",
    "GIMBAL.mode", "GIMBAL.pitch", "GIMBAL.roll", "GIMBAL.yaw",
    "GIMBAL.isPitchAtLimit", "GIMBAL.isRollAtLimit", "GIMBAL.isYawAtLimit",
    "GIMBAL.isStuck",
    "CAMERA.isPhoto", "CAMERA.isVideo", "CAMERA.sdCardIsInserted", "CAMERA.sdCardState",
    "RC.downlinkSignal", "RC.uplinkSignal",
    "RC.aileron", "RC.elevator", "RC.throttle", "RC.rudder",
    "BATTERY.chargeLevel", "BATTERY.voltage", "BATTERY.current",
    "BATTERY.currentCapacity", "BATTERY.fullCapacity",
    "BATTERY.cellNum", "BATTERY.isCellVoltageEstimated",
    "BATTERY.cellVoltageDeviation", "BATTERY.maxCellVoltageDeviation",
    "BATTERY.temperature", "BATTERY.minTemperature", "BATTERY.maxTemperature",
    "HOME.latitude", "HOME.longitude", "HOME.altitude",
    "HOME.heightLimit", "HOME.isHomeRecord", "HOME.goHomeMode",
    "HOME.isDynamicHomePointEnabled", "HOME.isNearDistanceLimit",
    "HOME.isNearHeightLimit", "HOME.isCompassCalibrating",
    "HOME.isMultipleModeEnabled", "HOME.isBeginnerMode",
    "HOME.isIocEnabled", "HOME.goHomeHeight",
    "HOME.maxAllowedHeight", "HOME.currentFlightRecordIndex",
    "RECOVER.appPlatform", "RECOVER.appVersion",
    "RECOVER.aircraftName", "RECOVER.aircraftSn",
    "RECOVER.cameraSn", "RECOVER.rcSn", "RECOVER.batterySn",
    "APP.tip", "APP.warn",
]


def _frame_to_row(f: Frame) -> list:
    return [
        f.custom.date_time.isoformat().replace("+00:00", "Z"),
        f.osd.fly_time, f.osd.latitude, f.osd.longitude,
        f.osd.height, f.osd.height_max, f.osd.vps_height, f.osd.altitude,
        f.osd.x_speed, f.osd.x_speed_max, f.osd.y_speed, f.osd.y_speed_max,
        f.osd.z_speed, f.osd.z_speed_max,
        f.osd.pitch, f.osd.roll, f.osd.yaw,
        f.osd.flyc_state, f.osd.flyc_command, f.osd.flight_action,
        f.osd.is_gpd_used, f.osd.non_gps_cause, f.osd.gps_num, f.osd.gps_level,
        f.osd.drone_type, f.osd.is_swave_work, f.osd.wave_error,
        f.osd.go_home_status, f.osd.battery_type,
        f.osd.is_on_ground, f.osd.is_motor_on, f.osd.is_motor_blocked,
        f.osd.motor_start_failed_cause, f.osd.is_imu_preheated, f.osd.imu_init_fail_reason,
        f.osd.is_acceletor_over_range, f.osd.is_barometer_dead_in_air,
        f.osd.is_compass_error, f.osd.is_go_home_height_modified,
        f.osd.can_ioc_work, f.osd.is_not_enough_force, f.osd.is_out_of_limit,
        f.osd.is_propeller_catapult, f.osd.is_vibrating, f.osd.is_vision_used,
        f.osd.voltage_warning,
        f.gimbal.mode, f.gimbal.pitch, f.gimbal.roll, f.gimbal.yaw,
        f.gimbal.is_pitch_at_limit, f.gimbal.is_roll_at_limit, f.gimbal.is_yaw_at_limit,
        f.gimbal.is_stuck,
        f.camera.is_photo, f.camera.is_video, f.camera.sd_card_is_inserted, f.camera.sd_card_state,
        f.rc.downlink_signal, f.rc.uplink_signal,
        f.rc.aileron, f.rc.elevator, f.rc.throttle, f.rc.rudder,
        f.battery.charge_level, f.battery.voltage, f.battery.current,
        f.battery.current_capacity, f.battery.full_capacity,
        f.battery.cell_num, f.battery.is_cell_voltage_estimated,
        f.battery.cell_voltage_deviation, f.battery.max_cell_voltage_deviation,
        f.battery.temperature, f.battery.min_temperature, f.battery.max_temperature,
        f.home.latitude, f.home.longitude, f.home.altitude,
        f.home.height_limit, f.home.is_home_record, f.home.go_home_mode,
        f.home.is_dynamic_home_point_enabled, f.home.is_near_distance_limit,
        f.home.is_near_height_limit, f.home.is_compass_calibrating,
        f.home.is_multiple_mode_enabled, f.home.is_beginner_mode,
        f.home.is_ioc_enabled, f.home.go_home_height,
        f.home.max_allowed_height, f.home.current_flight_record_index,
        f.recover.app_platform, f.recover.app_version,
        f.recover.aircraft_name, f.recover.aircraft_sn,
        f.recover.camera_sn, f.recover.rc_sn, f.recover.battery_sn,
        f.app.tip, f.app.warn,
    ]


def export_csv(
    frames: list[Frame],
    output_path: Optional[str | Path] = None,
) -> str:
    """Export frames as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    for f in frames:
        writer.writerow([_sanitize_csv(v) for v in _frame_to_row(f)])

    result = output.getvalue()

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result
