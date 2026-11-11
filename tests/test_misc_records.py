"""Unit tests for VisionGroup (17), MCParams (19), AppGPS (14) and FCCommonOSD (63).

Synthetic vectors only.
"""

from __future__ import annotations

import struct

import pytest

from dji_flightlog_parser.export.json_export import _serialize_record_data
from dji_flightlog_parser.frame.builder import records_to_frames
from dji_flightlog_parser.record.app import AppGPS
from dji_flightlog_parser.record.fc_common_osd import FCCommonOSD
from dji_flightlog_parser.record.mc_params import FailSafe, MCParams
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.reader import Record, RecordReader
from dji_flightlog_parser.record.types import RecordType
from dji_flightlog_parser.record.vision import VisionGroup, iter_blocks


# --- VisionGroup (type 17) ---------------------------------------------------

def _block(block_type: int, payload: bytes, end: bool = True) -> bytes:
    return bytes([block_type, 0, 0, 0, len(payload)]) + payload + (b"\xfe" if end else b"")


def _flags(value: int, n: int = 3) -> bytes:
    return value.to_bytes(n, "little")


def test_vision_block_framing_and_avoid_flags():
    # 0x0013 base value plus 0x0800 (ground in downward sensing range)
    v = VisionGroup.from_bytes(_block(8, _flags(0x000813)))
    assert v.avoidance_flags == 0x813
    assert v.collision_avoidance_enabled is True
    assert v.vert_low_limit_active is True


def test_vision_three_byte_flags_keep_byte_2():
    # M300/M350 set bits in payload byte 2; the raw bitfield must keep them
    v = VisionGroup.from_bytes(_block(8, _flags(0x240813)))
    assert v.avoidance_flags == 0x240813
    assert v.collision_avoidance_enabled is True
    assert v.vert_low_limit_active is True


def test_vision_flags_clear():
    # Neo-like base value: 0x10 only (no user avoidance, not near ground)
    v = VisionGroup.from_bytes(_block(8, _flags(0x10)))
    assert v.avoidance_flags == 0x10
    assert v.collision_avoidance_enabled is False
    assert v.vert_low_limit_active is False


def test_vision_two_byte_and_four_byte_payloads():
    # Mavic Mini (n=2) and Neo 2 (n=4) block-8 payload sizes
    v2 = VisionGroup.from_bytes(_block(8, _flags(0x0801, 2)), version=12)
    assert v2.avoidance_flags == 0x0801 and v2.vert_low_limit_active
    assert not v2.collision_avoidance_enabled
    v4 = VisionGroup.from_bytes(_block(8, _flags(0x0811, 4)))
    assert v4.avoidance_flags == 0x0811 and v4.vert_low_limit_active


def test_vision_chained_blocks_with_v12_trailer():
    # Block 8 then block 10 (n=15), then the v12 trailing byte
    data = _block(8, _flags(0x0002, 2)) + _block(10, bytes(range(15))) + b"\x5a"
    assert [(t, len(p)) for t, p in iter_blocks(data)] == [(8, 2), (10, 15)]
    v = VisionGroup.from_bytes(data, version=12)
    assert v.collision_avoidance_enabled is True
    assert v.detections == {}


def test_vision_block_order_does_not_matter():
    data = _block(10, bytes(15)) + _block(8, _flags(0x0802))
    v = VisionGroup.from_bytes(data)
    assert v.collision_avoidance_enabled and v.vert_low_limit_active


def test_vision_unsupported_bits_do_not_set_flags():
    # 0x0020, 0x0400 and 0x2000 were mapped to flags that the corpus does not
    # support; they only show up in the raw bitfield now.
    v = VisionGroup.from_bytes(_block(8, _flags(0x2428)))
    assert v.avoidance_flags == 0x2428
    assert not v.collision_avoidance_enabled
    assert not v.vert_low_limit_active
    # Block 9 (old guidance braking source) is not decoded
    v9 = VisionGroup.from_bytes(_block(9, b"\x01\x00"))
    assert v9.avoidance_flags is None


def test_vision_malformed_input_never_raises():
    assert VisionGroup.from_bytes(b"") == VisionGroup()
    assert VisionGroup.from_bytes(b"\x08") == VisionGroup()
    # Old reading of byte 1 as a block size: not a valid header any more
    assert VisionGroup.from_bytes(b"\x08\x03\x13\x08\x00\xfe").avoidance_flags is None
    # Non-zero header byte 1 with a plausible n = 2, payload and end marker:
    # only the 00 00 00 header check rejects it
    assert VisionGroup.from_bytes(b"\x08\x01\x00\x00\x02\x13\x08\xfe").avoidance_flags is None
    assert VisionGroup.from_bytes(b"\x08\x00\x00\x01\x02\x13\x08\xfe").avoidance_flags is None
    assert VisionGroup.from_bytes(b"\x08\x00\x00\x00\x02\x13\x08\xfe").avoidance_flags == 0x813
    # Payload longer than the record
    assert VisionGroup.from_bytes(bytes([8, 0, 0, 0, 9, 0x13, 0x08])).avoidance_flags is None
    # Missing end marker: the first block is used, nothing after it
    data = _block(8, _flags(0x13), end=False) + _block(8, _flags(0x813))
    assert [t for t, _ in iter_blocks(data)] == [8]
    assert VisionGroup.from_bytes(data).vert_low_limit_active is False


def test_vision_raw_serialisation_keys():
    out = _serialize_record_data(VisionGroup.from_bytes(_block(8, _flags(0x813))))
    assert out["vert_low_limit_active"] is True
    assert out["avoidance_flags"] == 0x813
    assert not {"is_braking", "is_ascent_limited", "is_landing_confirmation_needed",
                "is_avoid_active_obstacle"} & set(out)


def test_vision_through_record_reader():
    rr = RecordReader(b"", 14)
    rec = rr._parse_record(RecordType.VisionGroup, _block(8, _flags(0x813)), 9)
    assert isinstance(rec.data, VisionGroup) and rec.data.vert_low_limit_active


# --- MCParams (type 19) ------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    (0, FailSafe.Hover),
    (1, FailSafe.Landing),
    (2, FailSafe.GoHome),
    (9, FailSafe.UNKNOWN),
])
def test_mc_params_fail_safe_order(raw, expected):
    m = MCParams.from_bytes(bytes([raw, 0x07]) + bytes(27))
    assert m.fail_safe is expected


def test_mc_params_short_and_raw_name():
    assert MCParams.from_bytes(b"").fail_safe is FailSafe.UNKNOWN
    m = MCParams.from_bytes(b"\x02")
    assert m.fail_safe is FailSafe.GoHome and m.dynamic_home_point is False
    assert m.user_avoid_enabled is False
    assert _serialize_record_data(MCParams.from_bytes(b"\x02\x07"))["fail_safe"] == "GoHome"


@pytest.mark.parametrize("bit, name, old_name", [
    (0x01, "mvo_func_enabled", "e_landing"),
    (0x02, "avoid_obstacle_enabled", "go_home_altitude"),
    (0x04, "user_avoid_enabled", "dynamic_home_point"),
])
def test_mc_params_byte1_upstream_names(bit, name, old_name):
    names = ("mvo_func_enabled", "avoid_obstacle_enabled", "user_avoid_enabled")
    m = MCParams.from_bytes(bytes([2, bit]))
    assert {n: getattr(m, n) for n in names} == {n: n == name for n in names}
    # Deprecated misnamed duplicate carries the same bit
    assert getattr(m, old_name) is True
    # Bits outside 0x07 set nothing
    m = MCParams.from_bytes(bytes([2, 0xF8 | (0x07 & ~bit)]))
    assert getattr(m, name) is False and getattr(m, old_name) is False


def test_mc_params_raw_keys_add_upstream_names():
    out = _serialize_record_data(MCParams.from_bytes(bytes([2, 0x05])))
    assert list(out) == [
        "fail_safe", "e_landing", "go_home_altitude", "dynamic_home_point",
        "mvo_func_enabled", "avoid_obstacle_enabled", "user_avoid_enabled",
    ]
    assert out["mvo_func_enabled"] is True and out["e_landing"] is True
    assert out["avoid_obstacle_enabled"] is False and out["go_home_altitude"] is False
    assert out["user_avoid_enabled"] is True and out["dynamic_home_point"] is True


# --- AppGPS (type 14) --------------------------------------------------------

def _app_gps(lat: float, lon: float, alt: float | None) -> bytes:
    data = struct.pack("<dd", lat, lon)
    if alt is not None:
        data += struct.pack("<f", alt)
    return data


def test_app_gps_altitude():
    a = AppGPS.from_bytes(_app_gps(10.25, 20.5, 123.5))
    assert a.latitude == pytest.approx(10.25)
    assert a.longitude == pytest.approx(20.5)
    assert a.altitude == pytest.approx(123.5)
    assert AppGPS.from_bytes(_app_gps(10.25, 20.5, -42.0)).altitude == pytest.approx(-42.0)


def test_app_gps_short_records():
    assert AppGPS.from_bytes(_app_gps(10.25, 20.5, None)).altitude is None
    assert AppGPS.from_bytes(b"\x00" * 8) == AppGPS()


def test_app_gps_raw_serialisation_key():
    out = _serialize_record_data(AppGPS.from_bytes(_app_gps(10.25, 20.5, 77.0)))
    assert out["altitude"] == pytest.approx(77.0)
    assert "horizontal_accuracy" not in out


# --- FCCommonOSD (type 63) ---------------------------------------------------

def _fc63(remain: int, go_home: int, land: int, ghc: int, lc: int, sub_type: int = 0) -> bytes:
    return struct.pack("<HHHHBB", sub_type, remain, go_home, land, ghc, lc)


def test_fc_common_osd_times():
    c = FCCommonOSD.from_bytes(_fc63(1500, 137, 45, 15, 7))
    assert c.remain_fly_time == 1500
    assert c.need_go_home_time == 137
    assert c.need_land_time == 45
    assert c.go_home_capacity == 15 and c.land_capacity == 7


def test_fc_common_osd_go_home_time_not_available():
    c = FCCommonOSD.from_bytes(_fc63(1500, 0xFFFF, 30, 0, 7))
    assert c.need_go_home_time is None
    assert c.need_land_time == 30
    assert _serialize_record_data(c)["need_go_home_time"] is None


def test_fc_common_osd_short_or_other_subtype():
    short = FCCommonOSD.from_bytes(_fc63(1500, 137, 45, 15, 7)[:9])
    assert short.need_go_home_time is None and short.need_land_time is None
    other = FCCommonOSD.from_bytes(_fc63(1500, 137, 45, 15, 7, sub_type=1))
    assert other.sub_type == 1 and other.need_go_home_time is None
    assert FCCommonOSD.from_bytes(b"\x00") == FCCommonOSD()


# --- Frame wiring ---------------------------------------------------------------

def test_removed_record_aliases_are_gone():
    assert not hasattr(AppGPS.from_bytes(_app_gps(10.25, 20.5, 88.0)), "horizontal_accuracy")
    v = VisionGroup.from_bytes(_block(8, _flags(0x2428)))
    assert not any(hasattr(v, n) for n in ("is_braking", "is_ascent_limited",
                                            "is_landing_confirmation_needed"))


def test_frames_still_read_vision_and_app_gps():
    records = [
        Record(RecordType.OSD, OSD.from_bytes(bytes(60))),
        Record(RecordType.VisionGroup, VisionGroup.from_bytes(_block(8, _flags(0x813)))),
        Record(RecordType.AppGPS, AppGPS.from_bytes(_app_gps(10.25, 20.5, 66.0))),
        Record(RecordType.FlightControllerCommonOSD, FCCommonOSD.from_bytes(_fc63(900, 0xFFFF, 31, 0, 6))),
        Record(RecordType.OSD, OSD.from_bytes(bytes(60))),
    ]
    frame = records_to_frames(records)[0].to_dict()
    assert frame["vision"]["collisionAvoidanceEnabled"] is True
    assert frame["vision"]["isBraking"] is False
    assert frame["appGps"]["horizontalAccuracy"] == pytest.approx(66.0)
    assert frame["flightController"]["remainingFlightTime"] == 900
