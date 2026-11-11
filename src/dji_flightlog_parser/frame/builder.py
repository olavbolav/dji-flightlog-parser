"""Frame builder: converts records into normalized ~10Hz frames."""

from __future__ import annotations

import math
from dataclasses import dataclass
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
from ..record.smart_battery_group import SmartBatteryGroup, SmartBatteryDynamic
from ..record.ofdm import OFDM
from ..record.custom import Custom
from ..record.recover import Recover as RecoverRecord
from ..record.app import AppTip, AppWarn, AppSeriousWarn, AppGPS
from ..record.vision import VisionGroup
from ..record.fc_common_osd import FCCommonOSD
from ..record.mc_params import FailSafe, MCParams
from ..record.firmware import Firmware
from ..record.component_serial import ComponentSerial
from ..record.adsb import ADSBFlightData
from ..record.rtk_difference import RTKDifference
from ..record.ground_station_push import AgricultureGroundStationPush
from ..record.go_business import GOBusinessData
from ..record.airlink import AirLinkDataField, SUBTYPE_LINK_STATUS, SUBTYPE_SDR_LEVEL
from .models import (
    Frame, FrameBattery, FrameBatteryPack, FrameExtended, FrameHudWarning, FrameNearbyAircraft,
)

# Plausible cell count (cell-count pre-scan only), pack voltage and pack
# temperature in a SmartBatteryGroup dynamic record.
_MIN_CELLS = 2
_MAX_CELLS = 32
_MAX_PACK_VOLTAGE = 100.0
_MIN_PACK_TEMPERATURE = -50.0
_MAX_PACK_TEMPERATURE = 150.0
# Cell voltages older than this many frames (5 s) fall back to estimates.
# Cell records come every 5-12 frames on single-battery aircraft (longest
# gap 27 s in one M4TD log); M300/M350 log a single pack-1 record per
# flight, in 2 of 24 logs, which would otherwise freeze the cells.
_CELL_STALE_FRAMES = 50


def _append_message(current: str, new: str) -> str:
    if not current:
        return new
    return f"{current} {new}"


@dataclass
class BatteryLayout:
    """Which SmartBatteryGroup records feed ``frame.battery``, decided per log.

    See ``battery_layout``. An index is None when the log has no such record.
    """
    dynamic_index: Optional[int] = None  # main battery values
    static_index: Optional[int] = None  # cycle count, designed capacity, health
    cell_index: Optional[int] = None  # single_voltage records used for cell voltages
    cell_num: Optional[int] = None  # cell count from the records; None = use ProductType
    has_packs: bool = False  # dual battery: dynamic records for pack indices >= 1


def is_valid_dynamic(d: SmartBatteryDynamic) -> bool:
    """Reject truncated and corrupt SmartBatteryGroup dynamic records.

    Truncated records (``is_truncated``: payload shorter than 21 bytes, cut
    off before the state of charge) would put 0 into the fields they lack;
    a payload under 2 bytes even reads as index 0. None occur in the 74-log
    corpus. Otherwise the check is physical plausibility only: one M350 log
    has two garbage index-0 records (about 11 kV, 1024 degC); every other
    dynamic record in the corpus (128,660) has a pack voltage below 60 V
    and a temperature of 9-49 degC. The cell-count byte is not checked here:
    it is unreliable on v12; ``battery_layout`` checks it only where it
    picks the cell count.
    """
    return (not d.is_truncated
            and abs(d.current_voltage) <= _MAX_PACK_VOLTAGE
            and _MIN_PACK_TEMPERATURE <= d.temperature <= _MAX_PACK_TEMPERATURE)


def battery_layout(records: list[Record], version: Optional[int] = None) -> BatteryLayout:
    """Choose the battery records for the frames of one log (one pass over the records).

    Dynamic: on dual-battery aircraft (M30/M300/M350) index 0 is the
    aggregate of both packs (capacities add up, current is the sum, voltage
    the pack mean, temperature the hotter pack, and its state of charge is
    the aggregate SOC; checked on 27 dual logs). Use index 0 when the log has
    it, else index 1, else the lowest index present. Single-battery aircraft
    only log index 0.

    Static: only one static record is logged per flight. Use index 1, else
    index 2 (11 of 27 dual logs only have pack 2), else index 0 (single
    battery), else the lowest index present.

    Cells: single_voltage records carry index 0 on single-battery aircraft;
    the only cell records on M300/M350 are for pack 1 (index 1), and no log
    has index 2 cells. Use index 0, else 1, so cells always come from one pack.

    Cell count: the first ``cell_count`` of the cell records used (any
    single_voltage record if those have none), else the first plausible
    (2..32) dynamic ``cell_size``, but only when ``version`` is known and
    >= 13 (one Mavic Mini v12 log reads 3 for a 2S pack), else None (the
    caller falls back to ProductType). Checked on 74 logs: M400 13, M4TD 6,
    M30 6, M300/M350 12, Mavic Mini 2, Mini 5 Pro/Neo/Neo 2 2; this agrees
    with ProductType.battery_cell_num() for every known product, which falls
    back to 4 for the products it does not know. With ``version`` None the
    dynamic ``cell_size`` is ignored; on the corpus this gives the same cell
    count as passing the real version for every v13+ log (they all have
    single_voltage records or a ProductType with the same count).
    """
    dyn_indices: set[int] = set()
    static_indices: set[int] = set()
    sv_cells: dict[int, int] = {}  # first plausible cell_count per single_voltage index
    dyn_cells: Optional[int] = None
    use_dyn_cells = version is not None and version >= 13

    for r in records:
        if r.record_type != RecordType.SmartBatteryGroup or not isinstance(r.data, SmartBatteryGroup):
            continue
        g = r.data
        if g.static is not None:
            static_indices.add(g.static.index)
        elif g.dynamic is not None:
            d = g.dynamic
            if is_valid_dynamic(d):
                dyn_indices.add(d.index)
                if dyn_cells is None and use_dyn_cells and _MIN_CELLS <= d.cell_size <= _MAX_CELLS:
                    dyn_cells = d.cell_size
        elif g.single_voltage is not None:
            sv = g.single_voltage
            if 0 < sv.cell_count <= _MAX_CELLS:
                sv_cells.setdefault(sv.index, sv.cell_count)

    def pick(present: set[int], order: tuple[int, ...], fallback: bool = True) -> Optional[int]:
        for i in order:
            if i in present:
                return i
        return min(present) if present and fallback else None

    cell_index = pick(set(sv_cells), (0, 1), fallback=False)
    if cell_index is not None:
        cell_num: Optional[int] = sv_cells[cell_index]
    elif sv_cells:
        cell_num = next(iter(sv_cells.values()))
    else:
        cell_num = dyn_cells
    return BatteryLayout(
        dynamic_index=pick(dyn_indices, (0, 1)),
        static_index=pick(static_indices, (1, 2, 0)),
        cell_index=cell_index,
        cell_num=cell_num,
        has_packs=any(i >= 1 for i in dyn_indices),
    )


def has_fc_common_osd(records: list[Record]) -> bool:
    """True when the log has FCCommonOSD battery estimates (type 63, sub-type 0)."""
    return any(
        r.record_type == RecordType.FlightControllerCommonOSD
        and isinstance(r.data, FCCommonOSD) and r.data.sub_type == 0
        for r in records
    )


def records_to_frames(
    records: list[Record],
    details: Optional[Details] = None,
    extended: bool = False,
    version: Optional[int] = None,
) -> list[Frame]:
    """Convert a list of records into normalized frames.

    A new frame is emitted each time an OSD record arrives.
    Non-OSD records update the current in-progress frame.

    With ``extended``, frames also carry the rtk, airLink, navigation and
    appHud sections decoded from record types 45, 57, 48 and 54, the
    secondaryGimbal section, and extra keys in the existing sections (see
    ``frame.models``). Without it these are left out.

    When the Gimbal records interleave two devices (Matrice 4TD with a top
    accessory), ``gimbal`` follows the camera gimbal only; see
    ``main_gimbal_stream``. The battery records used are chosen per log; see
    ``battery_layout``. ``version`` is the log format version; it only
    matters for the cell count: without it the dynamic ``cell_size`` is
    ignored and the count comes from the single_voltage records or the
    ProductType (pass it when known).

    On dual-battery logs the aggregate (dynamic index 0) can arrive a few
    frames after pack 1 (index 1). Until the first aggregate record, pack 1
    fills chargeLevel, voltage and temperature, which track the aggregate;
    current and the capacities are per pack and stay 0 until then. The
    min/max temperature restart at the first aggregate record, so every
    value from that frame on is the same as without the stand-in.
    """
    if not isinstance(records, list):
        records = list(records)  # iterated several times below
    product_type = details.product_type if details else ProductType.NONE
    layout = battery_layout(records, version)
    cell_num = layout.cell_num or product_type.battery_cell_num()
    # Families without type 63 (M300/M350/Mavic Mini) carry the same FlyC
    # estimates in SmartBattery (type 8).
    fill_fc_from_type8 = not has_fc_common_osd(records)

    frames: list[Frame] = []
    frame = Frame(
        battery=FrameBattery(
            cell_num=cell_num,
            cell_voltages=[0.0] * cell_num,
            is_cell_voltage_estimated=True,
        )
    )

    if extended:
        frame.extended = FrameExtended()
    seen_nav_clocks: set[tuple[int, int]] = set()
    main_gimbal = main_gimbal_stream(records)
    packs: dict[int, FrameBatteryPack] = {}
    cells_frame: Optional[int] = None  # frame_index of the last cell record used
    # Pack 1 stands in for the aggregate until the first index-0 record
    pack1_stands_in = layout.dynamic_index == 0
    pack1_stood_in = False  # a pack-1 temperature reached the frame

    frame_index = 0

    for record in records:
        rt = record.record_type
        data = record.data

        if rt == RecordType.OSD and isinstance(data, OSD):
            if frame_index > 0:
                frame.finalize()
                frames.append(frame.snapshot())
                if cells_frame is not None and frame_index - cells_frame >= _CELL_STALE_FRAMES:
                    frame.battery.is_cell_voltage_estimated = True
                    cells_frame = None
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
            _apply_osd_extras(frame, osd)

            frame_index += 1

        elif (rt == RecordType.Gimbal and isinstance(data, GimbalRecord)
              and main_gimbal is not None and data.version != main_gimbal):
            # Second gimbal device (M4TD top accessory, most likely the AL1
            # spotlight): keep it out of frame.gimbal
            if frame.extended is not None:
                _apply_secondary_gimbal(frame.extended, data)

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
            frame.gimbal.yaw_relative_to_aircraft = data.yaw_angle
            frame.gimbal.joint_pitch = data.joint_pitch
            # A reset pulse lasts about 0.2 s; keep it if any record in the frame had it
            frame.gimbal.is_resetting = bool(frame.gimbal.is_resetting) or data.is_resetting

        elif rt == RecordType.Camera and isinstance(data, CameraRecord):
            # Reset every frame; keep a capture reported earlier in this frame
            frame.camera.is_photo = frame.camera.is_photo or data.is_shooting_photo
            frame.camera.is_video = data.is_recording
            frame.camera.sd_card_is_inserted = data.has_sd_card
            frame.camera.sd_card_state = data.sd_card_state.name
            _apply_camera_storage(frame, data)

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
            _apply_rc_display_extras(frame, data)

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
            # Type 8 percent/voltage are the aggregate on dual-battery
            # aircraft, the same as dynamic index 0 (SOC equal in 5472/5472
            # matched ticks, voltage within about 15 mV).
            frame.battery.charge_level = data.percent
            frame.battery.voltage = data.voltage
            if fill_fc_from_type8:
                _apply_type8_estimates(frame, data)

        elif rt == RecordType.SmartBatteryGroup and isinstance(data, SmartBatteryGroup):
            if data.static is not None:
                bs = data.static
                if bs.index == layout.static_index:
                    if bs.loop_times > 0:
                        frame.battery.cycle_count = bs.loop_times
                    if bs.designed_capacity > 0 and bs.designed_capacity < 100000:
                        frame.battery.designed_capacity = bs.designed_capacity
                    if bs.life > 0:
                        frame.battery.state_of_health = bs.life
            elif data.dynamic is not None:
                bd = data.dynamic
                if is_valid_dynamic(bd):
                    if bd.index == layout.dynamic_index:
                        if pack1_stands_in and pack1_stood_in:
                            # Min/max temperature describe the aggregate:
                            # restart them from its first record
                            frame.battery.min_temperature = 0.0
                            frame.battery.max_temperature = 0.0
                        frame.battery.voltage = bd.current_voltage
                        frame.battery.current = bd.current_current
                        frame.battery.current_capacity = bd.remained_capacity
                        frame.battery.full_capacity = bd.full_capacity
                        frame.battery.charge_level = bd.capacity_percent
                        frame.battery.temperature = bd.temperature
                        frame.battery.remaining_energy = bd.remaining_energy
                        pack1_stands_in = False
                    elif pack1_stands_in and bd.index == 1:
                        # The aggregate starts 2-18 frames late in 10 of 27
                        # dual logs, and pack 1 comes first in 7 of them. Pack
                        # SOC is within 1-2 % of the aggregate. Pack voltage
                        # is not as close: at the first aggregate record of
                        # those 7 logs it differs by 0-0.2 V.
                        frame.battery.charge_level = bd.capacity_percent
                        frame.battery.voltage = bd.current_voltage
                        frame.battery.temperature = bd.temperature
                        pack1_stood_in = True
                    if layout.has_packs and bd.index >= 1:
                        packs[bd.index] = FrameBatteryPack(
                            index=bd.index,
                            charge_level=bd.capacity_percent,
                            voltage=bd.current_voltage,
                            current=bd.current_current,
                            current_capacity=bd.remained_capacity,
                            full_capacity=bd.full_capacity,
                            temperature=bd.temperature,
                        )
                        frame.battery.packs = [packs[i] for i in sorted(packs)]
            elif data.single_voltage is not None:
                sv = data.single_voltage
                # Truncated M4TD records (count 6, one cell) arrive about 1:1
                # with full ones; they would leave cells 2-6 at stale values.
                if sv.index == layout.cell_index and not sv.is_truncated:
                    n = min(len(frame.battery.cell_voltages), len(sv.cell_voltages))
                    frame.battery.is_cell_voltage_estimated = False
                    cells_frame = frame_index
                    for i in range(n):
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
                frame.app_gps.altitude = data.altitude

        elif rt == RecordType.VisionGroup and isinstance(data, VisionGroup):
            # isBraking, isAscentLimited and isLandingConfirmationNeeded have
            # no supported bit in the avoidance status (checked on 429
            # records in 44 logs), so they stay False.
            if data.avoidance_flags is not None:
                frame.vision.collision_avoidance_enabled = data.collision_avoidance_enabled
                frame.vision.is_near_ground = data.vert_low_limit_active

        elif rt == RecordType.FlightControllerCommonOSD and isinstance(data, FCCommonOSD):
            if data.sub_type == 0:
                fc = frame.flight_controller
                fc.remaining_flight_time = data.remain_fly_time
                fc.battery_percent_needed_to_land = data.land_capacity
                # go_home_capacity reads 0 exactly when need_go_home_time is
                # the 65535 sentinel (339 of 46,636 records in 74 logs): no
                # estimate, not 0 %
                fc.battery_percent_needed_to_go_home = (
                    None if data.need_go_home_time is None else data.go_home_capacity)
                fc.time_needed_to_go_home = data.need_go_home_time
                fc.time_needed_to_land = data.need_land_time

        elif rt == RecordType.MCParams and isinstance(data, MCParams):
            if data.fail_safe != FailSafe.UNKNOWN:
                frame.flight_controller.rc_lost_action = data.fail_safe.name

        elif rt == RecordType.ADSBFlightData and isinstance(data, ADSBFlightData):
            frame.nearby_aircraft = [
                FrameNearbyAircraft(
                    icao_address=a.icao_address,
                    latitude=a.latitude,
                    longitude=a.longitude,
                    altitude=a.altitude,
                    heading=a.heading,
                    distance=a.distance,
                    relative_altitude=a.relative_altitude,
                    vertical_trend=a.vertical_trend_name,
                    warning_level=a.warning_level,
                    altitude_type=a.altitude_type_name,
                )
                for a in data.aircraft
            ]

        elif frame.extended is not None:
            if rt == RecordType.RTKDifference and isinstance(data, RTKDifference):
                _apply_rtk(frame.extended, data)
            elif rt == RecordType.AirLinkDataField and isinstance(data, AirLinkDataField):
                _apply_air_link(frame.extended, data)
            elif rt == RecordType.AgricultureGroundStationPush and isinstance(data, AgricultureGroundStationPush):
                # A few M4TD/M400 records are byte-identical replays of
                # earlier ones; skip timestamps that were already seen.
                clock = (data.timestamp_sec, data.timestamp_nsec)
                if clock not in seen_nav_clocks:
                    seen_nav_clocks.add(clock)
                    _apply_navigation(frame.extended, data)
            elif rt == RecordType.GOBusiness and isinstance(data, GOBusinessData):
                _apply_app_hud(frame.extended, data)

    if frame_index > 0:
        frame.finalize()
        frames.append(frame.snapshot())

    return frames


def main_gimbal_stream(records: list[Record]) -> Optional[int]:
    """Return the stream id of the camera gimbal when a log has several gimbal devices.

    Matrice 4TD airframes with a top accessory (most likely the AL1
    spotlight) interleave two devices in the Gimbal records, told apart by
    the low nibble of byte 11 (``Gimbal.version``; 2 = camera, 1 = accessory
    in all such logs seen). The camera gimbal keeps the horizon level, so its
    roll stays near 0 (RMS 0.01-0.11 deg), while the accessory's roll follows
    the aircraft (RMS 3.6-7.8 deg). The stream with the smallest roll RMS is
    taken as the camera gimbal; streams with less than 10% of the records are
    not considered. Returns None when the log has only one stream, so every
    Gimbal record is used.
    """
    rolls: dict[int, list[float]] = {}
    for r in records:
        if r.record_type == RecordType.Gimbal and isinstance(r.data, GimbalRecord):
            rolls.setdefault(r.data.version, []).append(r.data.roll)
    if len(rolls) < 2:
        return None

    total = sum(len(v) for v in rolls.values())
    candidates = {k: v for k, v in rolls.items() if len(v) * 10 >= total} or rolls

    def roll_rms(values: list[float]) -> float:
        return math.sqrt(sum(x * x for x in values) / len(values))

    return min(candidates, key=lambda k: (roll_rms(candidates[k]), -k))


def _apply_osd_extras(frame: Frame, osd: OSD) -> None:
    o = frame.osd
    o.wind_speed = osd.wind_speed
    o.wind_direction = osd.wind_direction
    o.position_source = osd.position_source
    o.position_source_code = osd.position_source_code
    o.yaw_rate = osd.yaw_rate
    north, east = osd.home_offset_north, osd.home_offset_east
    # Without a GNSS fix (vision-only Neo/Neo 2) the offsets read 0.0/0.0
    if north == 0.0 and east == 0.0 and not osd.is_gps_valid:
        north = east = None
    o.home_offset_north = north
    o.home_offset_east = east
    # Battery warning thresholds (%), constant within every log in the corpus
    if osd.low_battery_warning:
        frame.battery.low_warning_threshold = osd.low_battery_warning
    if osd.critical_battery_warning:
        frame.battery.critical_warning_threshold = osd.critical_battery_warning


def _apply_camera_storage(frame: Frame, d: CameraRecord) -> None:
    c = frame.camera
    c.work_mode = d.work_mode
    # Total 0 means no storage data (Mavic Mini, one M350 log), not an empty card
    if d.sd_card_total_mb:
        c.sd_card_total_mb = d.sd_card_total_mb
        c.sd_card_free_mb = d.sd_card_free_mb
        c.remaining_photos = d.remaining_photos
        c.remaining_video_seconds = d.remaining_video_seconds
    else:
        c.sd_card_total_mb = c.sd_card_free_mb = None
        c.remaining_photos = c.remaining_video_seconds = None


def _apply_rc_display_extras(frame: Frame, d: RCDisplayField) -> None:
    rc = frame.rc
    rc.left_dial = d.left_dial
    rc.right_dial = d.right_dial
    # Presses last 0.1-0.6 s, often a single record: keep them for the frame
    rc.is_shutter_half_pressed = bool(rc.is_shutter_half_pressed) or d.is_shutter_half_pressed
    rc.is_shutter_pressed = bool(rc.is_shutter_pressed) or d.is_shutter_pressed
    rc.is_record_pressed = bool(rc.is_record_pressed) or d.is_record_pressed
    rc.is_custom_button_1_pressed = bool(rc.is_custom_button_1_pressed) or d.is_custom_button_1_pressed
    rc.is_custom_button_2_pressed = bool(rc.is_custom_button_2_pressed) or d.is_custom_button_2_pressed


def _apply_type8_estimates(frame: Frame, d: SmartBattery) -> None:
    """Fill the flight controller estimates from SmartBattery (type 8).

    The values read 0 until the FC has an estimate (remaining flight time
    for the first 22-41 s of a log, time to land until take-off), so a key
    stays None until its first non-zero value and follows the record after
    that. Checked on 28 M300/M350/Mavic Mini logs: once non-zero, the
    battery percentages never return to 0, remaining flight time does in 4
    single records, and time to land reads 0 in the last 1-2 s before
    touchdown (7-86 records per log).
    """
    fc = frame.flight_controller
    for attr, value in (
        ("remaining_flight_time", d.useful_time),
        ("battery_percent_needed_to_land", d.land_battery),
        ("battery_percent_needed_to_go_home", d.go_home_battery),
        ("time_needed_to_go_home", d.go_home_time),
        ("time_needed_to_land", d.land_time),
    ):
        if value or getattr(fc, attr) is not None:
            setattr(fc, attr, value)


def _apply_secondary_gimbal(ext: FrameExtended, d: GimbalRecord) -> None:
    g = ext.secondary_gimbal
    g.pitch = d.pitch
    g.roll = d.roll
    g.yaw = d.yaw
    g.is_pitch_at_limit = d.is_pitch_at_limit


def _apply_rtk(ext: FrameExtended, d: RTKDifference) -> None:
    r = ext.rtk
    r.position_solution = d.position_solution.name
    r.position_solution_code = d.position_solution_code
    r.latitude = d.rover_latitude
    r.longitude = d.rover_longitude
    r.height = d.rover_height
    r.std_latitude = d.std_latitude
    r.std_longitude = d.std_longitude
    r.std_altitude = d.std_altitude
    r.satellites = d.rx1_total_sats
    r.gps_satellites = d.rx1_gps_sats
    r.beidou_satellites = d.rx1_beidou_sats
    r.glonass_satellites = d.rx1_glonass_sats
    r.galileo_satellites = d.rx1_galileo_sats
    r.has_base = d.has_base
    r.correction_age = d.correction_age
    r.dual_antenna_heading = d.dual_antenna_heading


def _apply_air_link(ext: FrameExtended, d: AirLinkDataField) -> None:
    a = ext.air_link
    if d.sub_type == SUBTYPE_SDR_LEVEL and d.sdr_quality is not None:
        a.sdr_quality = d.sdr_quality
    elif d.sub_type == SUBTYPE_LINK_STATUS and d.link_work_mode is not None:
        a.sdr_link_up = d.sdr_link_up
        a.lte_link_up = d.lte_link_up
        a.sdr_quality = d.sdr_quality
        a.lte_quality = d.lte_quality
        a.link_quality = d.link_quality
        a.work_mode = d.link_work_mode.name
        a.lte_level_a = d.lte_level_a
        a.lte_level_b = d.lte_level_b


def _apply_navigation(ext: FrameExtended, d: AgricultureGroundStationPush) -> None:
    n = ext.navigation
    n.aircraft_clock = d.timestamp
    n.satellites_used = d.satellites_used
    n.distance_to_home = d.distance_to_home
    n.is_rtk_fixed = d.is_rtk_fixed
    n.relative_height = d.relative_height
    n.gnss_height = d.gnss_height
    n.geoid_undulation = d.geoid_undulation


def _apply_app_hud(ext: FrameExtended, d: GOBusinessData) -> None:
    # Each record is a diff: only the parts whose flag is set change.
    h = ext.app_hud
    if d.status_bar_updated or d.status_bar is not None:
        h.status_bar = d.status_bar.text if d.status_bar else None
        h.status_bar_level = d.status_bar.level if d.status_bar else None
    if d.tip_updated or d.tip is not None:
        h.tip = d.tip.text if d.tip else None
        h.tip_code = d.tip.code if d.tip else None
    if d.warnings_updated or d.warnings:
        h.warnings = [FrameHudWarning(text=w.text, code=w.code, level=w.level) for w in d.warnings]
