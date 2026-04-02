"""Unit tests for OSD record parsing."""

import math
import struct
from dji_flightlog_parser.record.osd import (
    OSD, FlightMode, GroundOrSky, GoHomeStatus, FlightAction,
    MotorStartFailedCause, ImuInitFailReason, DroneType, BatteryType,
)


def _make_osd_data(
    lon_deg=10.0, lat_deg=60.0, alt_dm=500,
    speed_x_dm=0, speed_y_dm=0, speed_z_dm=0,
    pitch_dm=0, roll_dm=0, yaw_dm=0,
    bp1=0, app_cmd=0, bp2=0, bp3=0, bp4=0, bp5=0,
    gps_num=20, flight_action=0, motor_fail=0, bp6=0,
    battery_pct=80, swave=0, fly_time_ds=100, motor_rev=0,
    unknown1=0, unknown2=0, version_c=0, drone_type=0,
    imu_fail=0
) -> bytes:
    """Build a synthetic OSD payload."""
    buf = bytearray(50)
    struct.pack_into("<d", buf, 0, math.radians(lon_deg))
    struct.pack_into("<d", buf, 8, math.radians(lat_deg))
    struct.pack_into("<h", buf, 16, alt_dm)
    struct.pack_into("<h", buf, 18, speed_x_dm)
    struct.pack_into("<h", buf, 20, speed_y_dm)
    struct.pack_into("<h", buf, 22, speed_z_dm)
    struct.pack_into("<h", buf, 24, pitch_dm)
    struct.pack_into("<h", buf, 26, roll_dm)
    struct.pack_into("<h", buf, 28, yaw_dm)
    buf[30] = bp1
    buf[31] = app_cmd
    buf[32] = bp2
    buf[33] = bp3
    buf[34] = bp4
    buf[35] = bp5
    buf[36] = gps_num
    buf[37] = flight_action
    buf[38] = motor_fail
    buf[39] = bp6
    buf[40] = battery_pct
    buf[41] = swave
    struct.pack_into("<H", buf, 42, fly_time_ds)
    buf[44] = motor_rev
    buf[47] = version_c
    buf[48] = drone_type
    buf[49] = imu_fail
    return bytes(buf)


def test_osd_coordinates():
    data = _make_osd_data(lon_deg=10.5, lat_deg=63.4)
    osd = OSD.from_bytes(data)
    assert abs(osd.longitude - 10.5) < 1e-6
    assert abs(osd.latitude - 63.4) < 1e-6


def test_osd_altitude():
    data = _make_osd_data(alt_dm=342)
    osd = OSD.from_bytes(data)
    assert abs(osd.altitude - 34.2) < 0.01


def test_osd_flight_mode():
    data = _make_osd_data(bp1=6)
    osd = OSD.from_bytes(data)
    assert osd.flight_mode == FlightMode.GPSAtti


def test_osd_go_home_mode():
    data = _make_osd_data(bp1=15)
    osd = OSD.from_bytes(data)
    assert osd.flight_mode == FlightMode.GoHome


def test_osd_ground_or_sky():
    data_ground = _make_osd_data(bp2=0x00)
    osd_g = OSD.from_bytes(data_ground)
    assert osd_g.ground_or_sky == GroundOrSky.Ground

    data_sky = _make_osd_data(bp2=0x04)
    osd_s = OSD.from_bytes(data_sky)
    assert osd_s.ground_or_sky == GroundOrSky.Sky


def test_osd_bitpack5_order():
    """Verify bitpack5 field order matches Rust (is_out_of_limit at 0x01)."""
    data = _make_osd_data(bp5=0x01)
    osd = OSD.from_bytes(data)
    assert osd.is_out_of_limit is True
    assert osd.is_acceletor_over_range is False

    data2 = _make_osd_data(bp5=0x80)
    osd2 = OSD.from_bytes(data2)
    assert osd2.is_acceletor_over_range is True
    assert osd2.is_out_of_limit is False


def test_osd_imu_init_fail_default():
    data = _make_osd_data(imu_fail=0)
    osd = OSD.from_bytes(data)
    assert osd.imu_init_fail_reason == ImuInitFailReason.MonitorError


def test_osd_drone_type_unknown():
    data = _make_osd_data(drone_type=100)
    osd = OSD.from_bytes(data)
    assert osd.drone_type.value == 100
    assert osd.drone_type.name == "100"
