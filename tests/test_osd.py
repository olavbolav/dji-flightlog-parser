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
    data = _make_osd_data(drone_type=250)
    osd = OSD.from_bytes(data)
    assert osd.drone_type.value == 250
    assert osd.drone_type.name == "250"


def test_osd_drone_type_new_names():
    expected = {
        53: "MavicMini", 60: "Matrice300RTK", 67: "Matrice30", 89: "Matrice350RTK",
        100: "Matrice4D", 103: "Matrice400", 104: "Neo", 112: "Mini5Pro", 124: "Neo2",
    }
    for code, name in expected.items():
        osd = OSD.from_bytes(_make_osd_data(drone_type=code))
        assert osd.drone_type == DroneType(code)
        assert osd.drone_type.name == name


def _extend(data: bytes, length: int) -> bytearray:
    """Pad a 50-byte synthetic OSD payload to a full record length."""
    buf = bytearray(data)
    buf.extend(b"\x00" * (length - len(buf)))
    return buf


def test_osd_sequence_counter_replaces_battery():
    osd = OSD.from_bytes(_make_osd_data(battery_pct=137))
    assert osd.sequence_counter == 137
    assert not hasattr(osd, "battery")


def test_osd_battery_warning_levels():
    buf = bytearray(_make_osd_data())
    buf[45] = 0x80 | 25
    buf[46] = 0x80 | 15
    osd = OSD.from_bytes(bytes(buf))
    assert osd.low_battery_warning == 25
    assert osd.low_battery_warning_go_home is True
    assert osd.critical_battery_warning == 15
    assert osd.critical_battery_warning_landing is True

    buf[45] = 20
    buf[46] = 10
    osd = OSD.from_bytes(bytes(buf))
    assert osd.low_battery_warning == 20
    assert osd.low_battery_warning_go_home is False
    assert osd.critical_battery_warning == 10
    assert osd.critical_battery_warning_landing is False


def test_osd_battery_warning_flags_are_per_byte():
    # Only byte 45 has bit 7: go home set, landing clear
    buf = bytearray(_make_osd_data())
    buf[45] = 0x80 | 25
    buf[46] = 15
    osd = OSD.from_bytes(bytes(buf))
    assert (osd.low_battery_warning, osd.critical_battery_warning) == (25, 15)
    assert osd.low_battery_warning_go_home is True
    assert osd.critical_battery_warning_landing is False

    # Only byte 46 has bit 7: the reverse
    buf[45] = 25
    buf[46] = 0x80 | 15
    osd = OSD.from_bytes(bytes(buf))
    assert (osd.low_battery_warning, osd.critical_battery_warning) == (25, 15)
    assert osd.low_battery_warning_go_home is False
    assert osd.critical_battery_warning_landing is True


def test_osd_battery_warning_short_record():
    osd = OSD.from_bytes(_make_osd_data()[:46])
    assert osd.low_battery_warning == 0
    assert osd.critical_battery_warning == 0


def test_osd_yaw_rate():
    buf = _extend(_make_osd_data(), 56)
    struct.pack_into("<h", buf, 53, -1234)
    osd = OSD.from_bytes(bytes(buf))
    assert osd.yaw_rate == -123.4
    # A 56-byte v12 record has yaw rate but none of the v14 fields
    assert osd.position_source is None
    assert osd.position_source_code is None
    assert osd.wind_speed is None
    assert osd.wind_direction is None
    assert osd.home_offset_north is None


def test_osd_yaw_rate_missing_in_short_record():
    osd = OSD.from_bytes(_make_osd_data())
    assert osd.yaw_rate is None


def test_osd_position_source():
    names = {0: "None", 1: "Vision", 2: "GNSS", 3: "RTKFixed", 9: "Unknown(9)"}
    for code, name in names.items():
        buf = _extend(_make_osd_data(), 68)
        buf[60] = code
        osd = OSD.from_bytes(bytes(buf))
        assert osd.position_source_code == code
        assert osd.position_source == name


def test_osd_wind():
    buf = _extend(_make_osd_data(), 68)
    buf[63] = 87
    buf[64] = 3
    osd = OSD.from_bytes(bytes(buf))
    assert osd.wind_speed == 8.7
    assert osd.wind_direction_code == 3
    assert osd.wind_direction == "E"
    # 68-byte records have no home offsets
    assert osd.home_offset_north is None
    assert osd.home_offset_east is None


def test_osd_wind_direction_sectors_from_convention():
    expected = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    for code, name in enumerate(expected, start=1):
        buf = _extend(_make_osd_data(), 85)
        buf[63] = 20
        buf[64] = code
        assert OSD.from_bytes(bytes(buf)).wind_direction == name


def test_osd_wind_calm_maps_to_none():
    buf = _extend(_make_osd_data(), 70)
    buf[63] = 0
    buf[64] = 0
    osd = OSD.from_bytes(bytes(buf))
    assert osd.wind_speed == 0.0
    assert osd.wind_direction_code == 0
    assert osd.wind_direction is None


def test_osd_wind_direction_ignores_high_nibble():
    buf = _extend(_make_osd_data(), 71)
    buf[63] = 5
    buf[64] = 0xA6
    osd = OSD.from_bytes(bytes(buf))
    assert osd.wind_direction_code == 6
    assert osd.wind_direction == "SW"


def test_osd_wind_speed_255_is_no_estimate():
    for length in (68, 71, 85):
        buf = _extend(_make_osd_data(), length)
        buf[63] = 255
        buf[64] = 3
        osd = OSD.from_bytes(bytes(buf))
        assert osd.wind_speed is None
        assert osd.wind_direction_code is None
        assert osd.wind_direction is None
        # Neighbouring fields are still read
        assert osd.position_source_code == 0
    # 254 is still a value (25.4 m/s)
    buf = _extend(_make_osd_data(), 85)
    buf[63] = 254
    buf[64] = 3
    osd = OSD.from_bytes(bytes(buf))
    assert osd.wind_speed == 25.4 and osd.wind_direction == "E"


def test_osd_wind_missing_before_byte_64():
    buf = _extend(_make_osd_data(), 64)
    buf[63] = 50
    osd = OSD.from_bytes(bytes(buf))
    assert osd.wind_speed is None
    assert osd.wind_direction_code is None
    assert osd.position_source_code is not None


def test_osd_home_offsets():
    for length in (84, 85):
        buf = _extend(_make_osd_data(), length)
        struct.pack_into("<f", buf, 74, 123.5)
        struct.pack_into("<f", buf, 78, -42.25)
        osd = OSD.from_bytes(bytes(buf))
        assert osd.home_offset_north == 123.5
        assert osd.home_offset_east == -42.25


def test_osd_home_offsets_non_finite_is_none():
    buf = _extend(_make_osd_data(), 85)
    struct.pack_into("<f", buf, 74, float("nan"))
    struct.pack_into("<f", buf, 78, float("inf"))
    osd = OSD.from_bytes(bytes(buf))
    assert osd.home_offset_north is None
    assert osd.home_offset_east is None


def test_osd_home_offsets_missing_in_m30_record():
    buf = _extend(_make_osd_data(), 71)
    osd = OSD.from_bytes(bytes(buf))
    assert osd.home_offset_north is None
    assert osd.home_offset_east is None
    assert osd.wind_speed == 0.0
