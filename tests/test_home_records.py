"""Unit tests for Home record parsing (synthetic bytes only)."""

import math
import struct

from dji_flightlog_parser.record.home import Home, IOCMode, CompassCalibrationState


def _make_home_data(length: int = 102, bp1: int = 0, bp2: int = 0, flight_count: int = 0) -> bytes:
    buf = bytearray(length)
    struct.pack_into("<d", buf, 0, math.radians(10.0))
    struct.pack_into("<d", buf, 8, math.radians(60.0))
    struct.pack_into("<f", buf, 16, 1234.0)
    buf[20] = bp1
    buf[21] = bp2
    struct.pack_into("<H", buf, 22, 120)
    if length >= 41:
        struct.pack_into("<f", buf, 37, 500.0)
    if length >= 100:
        struct.pack_into("<H", buf, 98, flight_count)
    return bytes(buf)


def test_home_basic_fields():
    h = Home.from_bytes(_make_home_data(bp1=0x01))
    assert abs(h.longitude - 10.0) < 1e-9
    assert abs(h.latitude - 60.0) < 1e-9
    assert abs(h.altitude - 123.4) < 1e-4
    assert h.is_home_record is True
    assert h.go_home_height == 120
    assert h.max_allowed_height == 500.0


def test_home_byte20_bit7_is_has_go_home():
    h = Home.from_bytes(_make_home_data(bp1=0x80))
    assert h.has_go_home is True
    assert h.is_beginner_mode is False
    assert h.is_ioc_open is False


def test_home_byte21_bit3_is_beginner_mode():
    h = Home.from_bytes(_make_home_data(bp2=0x08))
    assert h.is_beginner_mode is True
    assert h.is_ioc_open is False
    assert h.has_go_home is False


def test_home_byte21_bit4_is_ioc_open():
    h = Home.from_bytes(_make_home_data(bp2=0x10))
    assert h.is_ioc_open is True
    assert h.is_beginner_mode is False


def test_home_byte21_other_bits_unchanged():
    h = Home.from_bytes(_make_home_data(bp2=0x20 | 0x04 | 0x02))
    assert h.ioc_mode == IOCMode.CourseLock
    assert h.is_compass_adjust is True
    assert h.compass_state == CompassCalibrationState.Step2
    assert h.is_beginner_mode is False
    assert h.is_ioc_open is False


def test_home_aircraft_flight_count():
    h = Home.from_bytes(_make_home_data(length=102, flight_count=332))
    assert h.aircraft_flight_count == 332


def test_home_aircraft_flight_count_only_in_102_byte_records():
    for length in (79, 84, 97, 101):
        h = Home.from_bytes(_make_home_data(length=length, flight_count=7))
        assert h.aircraft_flight_count is None


def test_home_short_record_does_not_raise():
    for length in (0, 10, 20, 21, 22, 30):
        h = Home.from_bytes(bytes(length))
        assert h.aircraft_flight_count is None
        assert h.has_go_home is False
