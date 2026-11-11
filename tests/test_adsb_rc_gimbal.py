"""Unit tests for the ADS-B (26), RC display (62) and Gimbal (3) records (synthetic bytes only)."""

import struct

from dji_flightlog_parser.export.json_export import _serialize_record_data
from dji_flightlog_parser.record.adsb import ENTRY_SIZE, ADSBFlightData
from dji_flightlog_parser.record.gimbal import Gimbal, GimbalMode
from dji_flightlog_parser.record.rc_display import RCDisplayField


# --- ADS-B ------------------------------------------------------------------

def _adsb_entry(icao=b"a1b2c3", level=1, lat=12.5, lon=-3.25, alt=1234, alt_type=0,
                heading=271.5, rel_alt=-56, trend=2, distance=7654) -> bytes:
    e = (icao + b"\x00" + bytes([level])
         + struct.pack("<iii", round(lat * 1e6), round(lon * 1e6), alt)
         + bytes([alt_type])
         + struct.pack("<Hh", round(heading * 10), rel_alt)
         + bytes([trend])
         + struct.pack("<H", distance))
    assert len(e) == ENTRY_SIZE
    return e


def _adsb(*entries, header=0x43) -> bytes:
    return bytes([header, len(entries)]) + b"".join(entries)


def test_adsb_entry_fields():
    r = ADSBFlightData.from_bytes(_adsb(_adsb_entry()))
    assert r.message_type == 0x43
    (a,) = r.aircraft
    assert a.icao_address == "a1b2c3"
    assert a.latitude == 12.5 and a.longitude == -3.25
    assert a.altitude == 1234
    assert a.heading == 271.5
    assert a.warning_level == 1
    assert a.altitude_type == 0 and a.altitude_type_name == "Ellipsoid"
    assert a.relative_altitude == -56
    assert a.vertical_trend == 2 and a.vertical_trend_name == "Falling"
    assert a.distance == 7654


def test_adsb_block_offsets_are_relative_to_each_entry():
    first = _adsb_entry(icao=b"aaaaaa", level=1, rel_alt=100, trend=0, distance=300, alt_type=1)
    second = _adsb_entry(icao=b"bbbbbb", level=2, rel_alt=-189, trend=1, distance=30261, alt_type=0)
    r = ADSBFlightData.from_bytes(_adsb(first, second))
    assert [a.icao_address for a in r.aircraft] == ["aaaaaa", "bbbbbb"]
    assert [a.warning_level for a in r.aircraft] == [1, 2]
    assert [a.relative_altitude for a in r.aircraft] == [100, -189]
    assert [a.vertical_trend_name for a in r.aircraft] == ["Level", "Rising"]
    assert [a.distance for a in r.aircraft] == [300, 30261]
    assert [a.altitude_type_name for a in r.aircraft] == ["MSL", "Ellipsoid"]


def test_adsb_relative_altitude_is_signed_and_distance_unsigned():
    r = ADSBFlightData.from_bytes(_adsb(_adsb_entry(rel_alt=-1, distance=0xFFFF)))
    assert r.aircraft[0].relative_altitude == -1
    assert r.aircraft[0].distance == 65535


def test_adsb_unknown_trend_has_no_name():
    a = ADSBFlightData.from_bytes(_adsb(_adsb_entry(trend=7))).aircraft[0]
    assert a.vertical_trend == 7 and a.vertical_trend_name is None


def test_adsb_empty_and_truncated_records():
    empty = ADSBFlightData.from_bytes(bytes([0x41, 0]))
    assert empty.message_type == 0x41 and empty.aircraft == []
    assert ADSBFlightData.from_bytes(b"").aircraft == []
    # Count says 2 but only one full entry is present
    r = ADSBFlightData.from_bytes(bytes([0x43, 2]) + _adsb_entry() + bytes(10))
    assert len(r.aircraft) == 1


def test_adsb_raw_json_has_new_keys():
    d = _serialize_record_data(ADSBFlightData.from_bytes(_adsb(_adsb_entry())))
    entry = d["aircraft"][0]
    for key in ("warning_level", "altitude_type", "relative_altitude", "vertical_trend", "distance"):
        assert key in entry
    assert entry["distance"] == 7654


# --- RC display -------------------------------------------------------------

def _rc_display(b2=0, b3=0, sticks=(1024, 1100, 900, 1024, 1300), right=1500, n=19) -> bytes:
    data = bytes([0, 0, b2, b3, 0, 0, 0]) + struct.pack("<5H", *sticks) + struct.pack("<H", right)
    assert len(data) == 19
    return data[:n]


def test_rc_display_sticks_and_dials():
    r = RCDisplayField.from_bytes(_rc_display())
    assert (r.aileron, r.elevator, r.throttle, r.rudder) == (1024, 1100, 900, 1024)
    assert r.gimbal == 1300 and r.left_dial == 1300
    assert r.right_dial == 1500


def test_rc_display_shutter_bits():
    half = RCDisplayField.from_bytes(_rc_display(b2=0x80))
    assert half.is_shutter_half_pressed and not half.is_shutter_pressed
    full = RCDisplayField.from_bytes(_rc_display(b2=0xC0))
    assert full.is_shutter_half_pressed and full.is_shutter_pressed
    # Pause/RTH bits must not be read as shutter
    other = RCDisplayField.from_bytes(_rc_display(b2=0x30))
    assert not other.is_shutter_half_pressed and not other.is_shutter_pressed


def test_rc_display_record_and_custom_buttons():
    rec = RCDisplayField.from_bytes(_rc_display(b3=0x01))
    assert rec.is_record_pressed
    assert not rec.is_custom_button_1_pressed and not rec.is_custom_button_2_pressed
    c1 = RCDisplayField.from_bytes(_rc_display(b3=0x40))
    assert c1.is_custom_button_1_pressed and not c1.is_custom_button_2_pressed and not c1.is_record_pressed
    c2 = RCDisplayField.from_bytes(_rc_display(b3=0x80))
    assert c2.is_custom_button_2_pressed and not c2.is_custom_button_1_pressed
    # Other custom-button bits (0x08, 0x10) are not mapped
    none = RCDisplayField.from_bytes(_rc_display(b3=0x18))
    assert not (none.is_record_pressed or none.is_custom_button_1_pressed or none.is_custom_button_2_pressed)


def test_rc_display_short_records():
    no_dial = RCDisplayField.from_bytes(_rc_display(n=17))
    assert no_dial.gimbal == 1300 and no_dial.right_dial is None
    buttons_only = RCDisplayField.from_bytes(_rc_display(b2=0xC0, b3=0x01, n=5))
    assert buttons_only.is_shutter_pressed and buttons_only.is_record_pressed
    assert buttons_only.aileron == 0 and buttons_only.right_dial is None
    empty = RCDisplayField.from_bytes(b"")
    assert empty.right_dial is None and not empty.is_shutter_pressed


# --- Gimbal -----------------------------------------------------------------

def _gimbal(pitch=-30.0, roll=0.5, yaw=120.0, b6=0x00, yaw_angle=-45.5, b10=0x00, b11=0x02,
            joint_pitch=-12.3, n=50) -> bytes:
    data = bytearray(50)
    struct.pack_into("<hhh", data, 0, round(pitch * 10), round(roll * 10), round(yaw * 10))
    data[6] = b6
    data[7] = 0
    struct.pack_into("<h", data, 8, round(yaw_angle * 10))
    data[10] = b10
    data[11] = b11
    struct.pack_into("<h", data, 20, round(joint_pitch * 10))
    # Fill the roll joint with a different value so a wrong offset is caught
    struct.pack_into("<h", data, 22, 777)
    return bytes(data[:n])


def test_gimbal_yaw_angle_and_joint_pitch():
    g = Gimbal.from_bytes(_gimbal())
    assert g.pitch == -30.0 and g.yaw == 120.0
    assert g.yaw_angle == -45.5
    assert g.joint_pitch == -12.3


def test_gimbal_joint_pitch_needs_bytes_20_21():
    assert Gimbal.from_bytes(_gimbal(n=21)).joint_pitch is None
    assert Gimbal.from_bytes(_gimbal(n=22)).joint_pitch == -12.3
    # v12 Mavic Mini records are 41 bytes long and still carry it
    assert Gimbal.from_bytes(_gimbal(joint_pitch=-90.0, n=41), version=12).joint_pitch == -90.0


def test_gimbal_is_resetting_bit():
    g = Gimbal.from_bytes(_gimbal(b6=0x80 | 0x20))
    assert g.is_resetting and g.mode == GimbalMode.YawFollow
    g = Gimbal.from_bytes(_gimbal(b6=0x80))
    assert not g.is_resetting and g.mode == GimbalMode.YawFollow
    assert not Gimbal.from_bytes(_gimbal(b6=0x08)).is_resetting


def test_gimbal_stuck_bit():
    assert Gimbal.from_bytes(_gimbal(b10=0x40)).is_stuck
    # 0x20 is the install direction, not stuck
    assert not Gimbal.from_bytes(_gimbal(b10=0x20)).is_stuck


def test_gimbal_short_record():
    g = Gimbal.from_bytes(bytes(4))
    assert g.joint_pitch is None and not g.is_resetting
