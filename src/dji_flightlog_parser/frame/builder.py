"""Frame builder: converts records into normalized ~10Hz frames."""

from __future__ import annotations

import copy
from typing import Optional

from ..layout.details import Details, ProductType
from ..record.reader import Record
from ..record.types import RecordType
from ..record.osd import OSD, GroundOrSky
from ..record.home import Home as HomeRecord
from ..record.gimbal import Gimbal as GimbalRecord
from ..record.camera import Camera as CameraRecord
from ..record.rc import RC as RCRecord
from ..record.rc_display import RCDisplayField
from ..record.battery import CenterBattery, SmartBattery
from ..record.smart_battery_group import SmartBatteryGroup, SmartBatteryDynamic, SmartBatterySingleVoltage
from ..record.ofdm import OFDM
from ..record.custom import Custom
from ..record.recover import Recover as RecoverRecord
from ..record.app import AppTip, AppWarn, AppSeriousWarn, AppGPS
from ..record.vision import VisionGroup
from ..record.fc_common_osd import FCCommonOSD
from ..record.firmware import Firmware
from ..record.component_serial import ComponentSerial
from ..record.adsb import ADSBFlightData
from .models import Frame, FrameBattery, FrameNearbyAircraft


def _append_message(current: str, new: str) -> str:
    if not current:
        return new
    return f"{current} {new}"


def records_to_frames(records: list[Record], details: Optional[Details] = None) -> list[Frame]:
    """Convert a list of records into normalized frames.

    A new frame is emitted each time an OSD record arrives.
    Non-OSD records update the current in-progress frame.
    """
    product_type = details.product_type if details else ProductType.NONE
    cell_num = product_type.battery_cell_num()
    battery_num = product_type.battery_num()

    frames: list[Frame] = []
    frame = Frame(
        battery=FrameBattery(
            cell_num=cell_num,
            cell_voltages=[0.0] * cell_num,
            is_cell_voltage_estimated=True,
        )
    )

    frame_index = 0

    for record in records:
        rt = record.record_type
        data = record.data

        if rt == RecordType.OSD and isinstance(data, OSD):
            if frame_index > 0:
                frame.finalize()
                frames.append(copy.deepcopy(frame))
                frame.reset()

            osd = data
            frame.osd.fly_time = osd.fly_time
            frame.osd.latitude = osd.latitude
            frame.osd.longitude = osd.longitude
            frame.osd.altitude = osd.altitude + frame.home.altitude
            frame.osd.height = osd.altitude
            frame.osd.vps_height = osd.s_wave_height

            frame.osd.x_speed = osd.speed_x
            frame.osd.y_speed = osd.speed_y
            frame.osd.z_speed = osd.speed_z
            frame.osd.pitch = osd.pitch
            frame.osd.yaw = osd.yaw
            frame.osd.roll = osd.roll

            old_state = frame.osd.flyc_state
            new_state = osd.flight_mode.name
            if old_state != new_state:
                frame.app.tip = _append_message(
                    frame.app.tip, f"Flight mode changed to {new_state}."
                )
            frame.osd.flyc_state = new_state

            cmd_val = osd.app_command if isinstance(osd.app_command, int) else int(osd.app_command)
            if cmd_val == 0:
                frame.osd.flyc_command = None
            else:
                frame.osd.flyc_command = osd.app_command.name if hasattr(osd.app_command, 'name') else str(osd.app_command)

            fa_name = osd.flight_action.name
            frame.osd.flight_action = "None" if fa_name == "NONE" else fa_name
            frame.osd.gps_num = osd.gps_num
            frame.osd.gps_level = osd.gps_level
            frame.osd.is_gpd_used = osd.is_gps_valid
            frame.osd.non_gps_cause = osd.non_gps_cause.name
            frame.osd.drone_type = osd.drone_type.name
            frame.osd.is_swave_work = osd.is_swave_work
            frame.osd.wave_error = osd.wave_error
            frame.osd.go_home_status = osd.go_home_status.name
            frame.osd.battery_type = osd.battery_type.name
            frame.osd.is_on_ground = osd.ground_or_sky == GroundOrSky.Ground
            frame.osd.is_motor_on = osd.is_motor_up
            frame.osd.is_motor_blocked = osd.is_motor_blocked
            msfc_name = osd.motor_start_failed_cause.name
            frame.osd.motor_start_failed_cause = "None" if msfc_name == "NONE" else msfc_name
            frame.osd.is_imu_preheated = osd.is_imu_preheated
            frame.osd.imu_init_fail_reason = osd.imu_init_fail_reason.name
            frame.osd.is_acceletor_over_range = osd.is_acceletor_over_range
            frame.osd.is_barometer_dead_in_air = osd.is_barometer_dead_in_air
            frame.osd.is_compass_error = osd.is_compass_error
            frame.osd.is_go_home_height_modified = osd.is_go_home_height_modified
            frame.osd.can_ioc_work = osd.can_ioc_work
            frame.osd.is_not_enough_force = osd.is_not_enough_force
            frame.osd.is_out_of_limit = osd.is_out_of_limit
            frame.osd.is_propeller_catapult = osd.is_propeller_catapult
            frame.osd.is_vibrating = osd.is_vibrating
            frame.osd.is_vision_used = osd.is_vision_used
            frame.osd.voltage_warning = osd.voltage_warning

            frame_index += 1

        elif rt == RecordType.Gimbal and isinstance(data, GimbalRecord):
            frame.gimbal.mode = data.mode.name
            frame.gimbal.pitch = data.pitch
            frame.gimbal.roll = data.roll
            frame.gimbal.yaw = data.yaw

            if not frame.gimbal.is_pitch_at_limit and data.is_pitch_at_limit:
                frame.app.tip = _append_message(frame.app.tip, "Gimbal pitch axis endpoint reached.")
            frame.gimbal.is_pitch_at_limit = data.is_pitch_at_limit

            if not frame.gimbal.is_roll_at_limit and data.is_roll_at_limit:
                frame.app.tip = _append_message(frame.app.tip, "Gimbal roll axis endpoint reached.")
            frame.gimbal.is_roll_at_limit = data.is_roll_at_limit

            if not frame.gimbal.is_yaw_at_limit and data.is_yaw_at_limit:
                frame.app.tip = _append_message(frame.app.tip, "Gimbal yaw axis endpoint reached.")
            frame.gimbal.is_yaw_at_limit = data.is_yaw_at_limit

            frame.gimbal.is_stuck = data.is_stuck

        elif rt == RecordType.Camera and isinstance(data, CameraRecord):
            frame.camera.is_photo = data.is_shooting_single_photo
            frame.camera.is_video = data.is_recording
            frame.camera.sd_card_is_inserted = data.has_sd_card
            frame.camera.sd_card_state = data.sd_card_state.name

        elif rt == RecordType.RC and isinstance(data, RCRecord):
            frame.rc.aileron = data.aileron
            frame.rc.elevator = data.elevator
            frame.rc.throttle = data.throttle
            frame.rc.rudder = data.rudder

        elif rt == RecordType.RCDisplayField and isinstance(data, RCDisplayField):
            frame.rc.aileron = data.aileron
            frame.rc.elevator = data.elevator
            frame.rc.throttle = data.throttle
            frame.rc.rudder = data.rudder

        elif rt == RecordType.CenterBattery and isinstance(data, CenterBattery):
            frame.battery.charge_level = data.relative_capacity
            frame.battery.voltage = data.voltage
            frame.battery.current_capacity = data.current_capacity
            frame.battery.full_capacity = data.full_capacity
            frame.battery.is_cell_voltage_estimated = False
            if data.loop_num > 0:
                frame.battery.cycle_count = data.loop_num

            cell_num_actual = len(frame.battery.cell_voltages)
            cells = [data.voltage_cell1, data.voltage_cell2, data.voltage_cell3,
                     data.voltage_cell4, data.voltage_cell5, data.voltage_cell6]
            for i in range(min(cell_num_actual, 6)):
                frame.battery.cell_voltages[i] = cells[i]

        elif rt == RecordType.SmartBattery and isinstance(data, SmartBattery):
            frame.battery.charge_level = data.percent
            frame.battery.voltage = data.voltage

        elif rt == RecordType.SmartBatteryGroup and isinstance(data, SmartBatteryGroup):
            if data.static is not None:
                bs = data.static
                if battery_num < 2 or bs.index == 1:
                    if bs.loop_times > 0:
                        frame.battery.cycle_count = bs.loop_times
                    if bs.designed_capacity > 0 and bs.designed_capacity < 100000:
                        frame.battery.designed_capacity = bs.designed_capacity
            elif data.dynamic is not None:
                bd = data.dynamic
                if battery_num < 2 or bd.index == 1:
                    frame.battery.voltage = bd.current_voltage
                    frame.battery.current = bd.current_current
                    frame.battery.current_capacity = bd.remained_capacity
                    frame.battery.full_capacity = bd.full_capacity
                    frame.battery.charge_level = bd.capacity_percent
                    frame.battery.temperature = bd.temperature
            elif data.single_voltage is not None:
                sv = data.single_voltage
                n = min(len(frame.battery.cell_voltages), sv.cell_count)
                frame.battery.is_cell_voltage_estimated = False
                for i in range(n):
                    if i < len(sv.cell_voltages):
                        frame.battery.cell_voltages[i] = sv.cell_voltages[i]

        elif rt == RecordType.OFDM and isinstance(data, OFDM):
            if data.is_up:
                frame.rc.uplink_signal = data.signal_percent
            else:
                frame.rc.downlink_signal = data.signal_percent

        elif rt == RecordType.Custom and isinstance(data, Custom):
            frame.custom.date_time = data.update_timestamp

        elif rt == RecordType.Home and isinstance(data, HomeRecord):
            frame.home.latitude = data.latitude
            frame.home.longitude = data.longitude
            if frame.home.altitude == 0.0:
                frame.osd.altitude += data.altitude
            frame.home.altitude = data.altitude
            frame.home.height_limit = data.max_allowed_height
            frame.home.is_home_record = data.is_home_record
            frame.home.go_home_mode = data.go_home_mode.name
            frame.home.is_dynamic_home_point_enabled = data.is_dynamic_home_point_enabled
            frame.home.is_near_distance_limit = data.is_near_distance_limit
            frame.home.is_near_height_limit = data.is_near_height_limit
            frame.home.is_compass_calibrating = data.is_compass_adjust
            if data.is_compass_adjust:
                frame.home.compass_calibration_state = data.compass_state.name
            frame.home.is_multiple_mode_enabled = data.is_multiple_mode_open
            frame.home.is_beginner_mode = data.is_beginner_mode
            frame.home.is_ioc_enabled = data.is_ioc_open
            if data.is_ioc_open:
                frame.home.ioc_mode = data.ioc_mode.name
            frame.home.go_home_height = data.go_home_height
            if data.is_ioc_open:
                frame.home.ioc_course_lock_angle = data.ioc_course_lock_angle
            frame.home.max_allowed_height = data.max_allowed_height
            frame.home.current_flight_record_index = data.current_flight_record_index

        elif rt == RecordType.Recover and isinstance(data, RecoverRecord):
            frame.recover.app_platform = data.app_platform.name if hasattr(data.app_platform, 'name') else str(data.app_platform)
            frame.recover.app_version = data.app_version
            frame.recover.aircraft_name = data.aircraft_name
            sn = data.aircraft_sn
            if details and details.aircraft_sn and sn:
                if details.aircraft_sn.startswith(sn) and len(details.aircraft_sn) > len(sn):
                    sn = details.aircraft_sn
            frame.recover.aircraft_sn = sn
            frame.recover.camera_sn = data.camera_sn
            frame.recover.rc_sn = data.rc_sn
            frame.recover.battery_sn = data.battery_sn

        elif rt == RecordType.AppTip and isinstance(data, AppTip):
            frame.app.tip = _append_message(frame.app.tip, data.message)

        elif rt == RecordType.AppWarn and isinstance(data, AppWarn):
            frame.app.warn = _append_message(frame.app.warn, data.message)

        elif rt == RecordType.AppSeriousWarn and isinstance(data, AppSeriousWarn):
            frame.app.warn = _append_message(frame.app.warn, data.message)

        elif rt == RecordType.AppGPS and isinstance(data, AppGPS):
            if data.latitude != 0.0 and data.longitude != 0.0:
                frame.app_gps.latitude = data.latitude
                frame.app_gps.longitude = data.longitude
                frame.app_gps.horizontal_accuracy = data.horizontal_accuracy

        elif rt == RecordType.VisionGroup and isinstance(data, VisionGroup):
            frame.vision.collision_avoidance_enabled = data.collision_avoidance_enabled
            frame.vision.is_braking = data.is_braking
            frame.vision.is_ascent_limited = data.is_ascent_limited
            frame.vision.is_landing_confirmation_needed = data.is_landing_confirmation_needed

        elif rt == RecordType.FlightControllerCommonOSD and isinstance(data, FCCommonOSD):
            if data.sub_type == 0:
                frame.flight_controller.remaining_flight_time = data.remain_fly_time
                frame.flight_controller.battery_percent_needed_to_land = data.land_capacity
                frame.flight_controller.battery_percent_needed_to_go_home = data.go_home_capacity

        elif rt == RecordType.ADSBFlightData and isinstance(data, ADSBFlightData):
            frame.nearby_aircraft = [
                FrameNearbyAircraft(
                    icao_address=a.icao_address,
                    latitude=a.latitude,
                    longitude=a.longitude,
                    altitude=a.altitude,
                    heading=a.heading,
                )
                for a in data.aircraft
            ]

    if frame_index > 0:
        frame.finalize()
        frames.append(copy.deepcopy(frame))

    return frames
