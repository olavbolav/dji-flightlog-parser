"""Unit tests for record types 32, 45, 48, 54, 55 and 57 (synthetic vectors only)."""

import math
import struct

import pytest

from dji_flightlog_parser.decoder.protobuf import (
    ProtobufDecodeError,
    as_double,
    is_message,
    parse_message,
)
from dji_flightlog_parser.decoder.aes import decode_record_payload
from dji_flightlog_parser.decoder.feature_point import FeaturePoint
from dji_flightlog_parser.decoder.xor import xor_decode_block
from dji_flightlog_parser.export.json_export import _serialize_record_data
from dji_flightlog_parser.frame.builder import records_to_frames
from dji_flightlog_parser.record.adsb import ADSBAircraft, ADSBFlightData
from dji_flightlog_parser.record.airlink import AirLinkDataField, LinkWorkMode
from dji_flightlog_parser.record.app import AppTip
from dji_flightlog_parser.record.go_business import GOBusinessData
from dji_flightlog_parser.record.ground_station_push import AgricultureGroundStationPush
from dji_flightlog_parser.record.gs_mission_status import GSMissionStatus, GSMissionType
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.reader import Record, RecordReader
from dji_flightlog_parser.record.rtk_difference import RTKDifference, RTKSolutionType
from dji_flightlog_parser.record.security import SecurityBlock
from dji_flightlog_parser.record.types import RecordType
from dji_flightlog_parser.record.unknown import UnknownRecord


# --- protobuf helpers -------------------------------------------------------

def _varint(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _pb_varint(num: int, v: int) -> bytes:
    return _varint(num << 3) + _varint(v)


def _pb_bytes(num: int, b: bytes) -> bytes:
    return _varint((num << 3) | 2) + _varint(len(b)) + b


def _pb_double(num: int, v: float) -> bytes:
    return _varint((num << 3) | 1) + struct.pack("<d", v)


def test_protobuf_reader_wire_types():
    msg = _pb_varint(1, 300) + _pb_bytes(2, b"abc") + _pb_double(3, 2.5) + _varint((4 << 3) | 5) + b"\x01\x02\x03\x04"
    fields = parse_message(msg)
    assert [(f.number, f.wire_type) for f in fields] == [(1, 0), (2, 2), (3, 1), (4, 5)]
    assert fields[0].value == 300
    assert fields[1].value == b"abc"
    assert as_double(fields[2].value) == 2.5
    assert fields[3].value == b"\x01\x02\x03\x04"
    assert is_message(msg)
    assert is_message(b"")


@pytest.mark.parametrize("bad", [b"\x0a\x05ab", b"\x08", b"\x00\x01", b"\x0b", b"\x09\x00\x00"])
def test_protobuf_reader_rejects_malformed(bad):
    assert not is_message(bad)
    with pytest.raises(ProtobufDecodeError):
        parse_message(bad)


# --- type 32 GSMissionStatus --------------------------------------------------

def test_gs_mission_status_all_zero():
    g = GSMissionStatus.from_bytes(bytes(7))
    assert g.raw == bytes(7)
    assert not g.has_content
    assert g.mission_type == GSMissionType.NONE
    assert g.hp_radius is None and g.wp_target_index is None


def test_gs_mission_status_hotpoint_view():
    g = GSMissionStatus.from_bytes(bytes([2, 1]) + struct.pack("<H", 1500) + bytes([7, 30, 0]))
    assert g.has_content
    assert g.mission_type == GSMissionType.Hotpoint
    assert (g.hp_status, g.hp_radius, g.hp_reason, g.hp_rate_raw) == (1, 1500, 7, 30)
    assert GSMissionStatus.from_bytes(bytes([99] + [0] * 6)).mission_type == GSMissionType.UNKNOWN


def test_gs_mission_status_accepts_only_v13_len7():
    assert GSMissionStatus.accepts(bytes(7), 14)
    assert not GSMissionStatus.accepts(b"", 14)  # failed decryption
    assert not GSMissionStatus.accepts(bytes(8), 14)
    assert not GSMissionStatus.accepts(bytes(7), 12)


# --- type 45 RTKDifference -----------------------------------------------------

def _rtk(length=80, sol=50, counts=(10, 12, 8), rx2=(10, 12, 8), base=(5, 0, 4),
         lat=59.5, lon=10.25, h=120.5, base_lat=59.4, base_lon=10.2, base_param=12345,
         heading=180.0, heading_sol=50, age=1.0, sig=(0.02, 0.01, 0.05), gal=(9, 9, 6), g5=(1, 0, 0)) -> bytes:
    enc = lambda c: (c << 1) | 1
    buf = struct.pack("<11BddfddIfBB", 0, sol, *map(enc, counts), *map(enc, rx2), *map(enc, base),
                      lat, lon, h, base_lat, base_lon, base_param, heading, heading_sol, 1)
    buf += struct.pack("<fI3f3B", age, 0, *sig, *map(enc, gal))
    if length == 83:
        buf += bytes(map(enc, g5))
    assert len(buf) == length
    return buf


def test_rtk_difference_len80():
    r = RTKDifference.from_bytes(_rtk(80))
    assert r.position_solution == RTKSolutionType.Fixed and r.position_solution_code == 50
    assert (r.rx1_gps_sats, r.rx1_beidou_sats, r.rx1_glonass_sats, r.rx1_galileo_sats) == (10, 12, 8, 9)
    assert (r.rx2_gps_sats, r.base_gps_sats, r.base_glonass_sats, r.base_galileo_sats) == (10, 5, 4, 6)
    assert r.rover_latitude == 59.5 and r.rover_longitude == 10.25
    assert r.rover_height == pytest.approx(120.5)
    assert r.has_base and r.base_latitude == 59.4 and r.base_longitude == 10.2
    assert r.base_param_47 == 12345
    assert r.dual_antenna_heading == 180.0 and r.is_dual_antenna
    assert r.correction_age == pytest.approx(1.0)
    # 80-byte layout: north sigma first
    assert r.std_latitude == pytest.approx(0.02) and r.std_longitude == pytest.approx(0.01)
    assert r.std_altitude == pytest.approx(0.05)
    assert r.rx1_gnss5_sats == 0
    assert r.rx1_total_sats == 39


def test_rtk_difference_len83_swaps_sigma_and_adds_gnss5():
    r = RTKDifference.from_bytes(_rtk(83, g5=(2, 0, 0)))
    assert r.std_longitude == pytest.approx(0.02) and r.std_latitude == pytest.approx(0.01)
    assert r.rx1_gnss5_sats == 2


def test_rtk_difference_single_antenna_no_base():
    r = RTKDifference.from_bytes(_rtk(83, sol=16, rx2=(0, 0, 0), base=(0, 0, 0), base_lat=0.0, base_lon=0.0,
                                      base_param=0, heading=0.0, heading_sol=0, age=0.0))
    assert r.position_solution == RTKSolutionType.Single
    assert not r.has_base and r.base_latitude is None and r.base_longitude is None
    assert r.dual_antenna_heading is None and not r.is_dual_antenna
    assert RTKDifference.from_bytes(_rtk(80, sol=52)).position_solution == RTKSolutionType.Code52
    assert RTKDifference.from_bytes(_rtk(80, sol=77)).position_solution == RTKSolutionType.UNKNOWN


def test_rtk_difference_sanity_gate():
    assert RTKDifference.accepts(_rtk(80), 14)
    assert RTKDifference.accepts(_rtk(83), 14)
    assert not RTKDifference.accepts(_rtk(80), 12)
    assert not RTKDifference.accepts(_rtk(83) + bytes(14), 14)  # 97 bytes: ciphertext without a key
    assert not RTKDifference.accepts(b"", 14)
    assert not RTKDifference.accepts(_rtk(80, lat=95.0), 14)
    assert not RTKDifference.accepts(_rtk(80, lon=float("nan")), 14)
    assert not RTKDifference.accepts(_rtk(80, heading=360.0), 14)
    even = bytearray(_rtk(80))
    even[2] = 20  # counter without bit 0
    assert not RTKDifference.accepts(bytes(even), 14)


# --- type 48 AgricultureGroundStationPush --------------------------------------

def _nav(lon=10.5, lat=59.9, rel_h=42.25, yaw10=-1234, b22=0, b23=1, sec=1_700_000_000, nsec=250_000_000,
         status=0x44, sats=18, home_lon=10.4, home_lat=59.8, f50=60.0, f54=123.5, f58=102.25, f62=100.0,
         f66=39.5, b70=2) -> bytes:
    return struct.pack("<ddfhBBIIBBddfffffB", math.radians(lon), math.radians(lat), rel_h, yaw10, b22, b23,
                       sec, nsec, status, sats, math.radians(home_lon), math.radians(home_lat),
                       f50, f54, f58, f62, f66, b70)


def test_ground_station_push_fields():
    p = AgricultureGroundStationPush.from_bytes(_nav())
    assert p.longitude == pytest.approx(10.5) and p.latitude == pytest.approx(59.9)
    assert p.relative_height == pytest.approx(42.25)
    assert p.yaw == pytest.approx(-123.4)
    assert p.is_rtk_fixed and p.rtk_flag_a == 0
    assert p.timestamp == pytest.approx(1_700_000_000.25)
    assert p.nav_status_flags == 0x44 and p.satellites_used == 18
    assert p.home_longitude == pytest.approx(10.4) and p.home_latitude == pytest.approx(59.8)
    assert p.distance_to_home == pytest.approx(123.5)
    assert p.fc_altitude == pytest.approx(102.25) and p.gnss_height == pytest.approx(100.0)
    assert p.geoid_undulation == pytest.approx(39.5)
    assert p.rtk_state_b == 2
    assert AgricultureGroundStationPush.from_bytes(_nav(f66=0.0)).geoid_undulation is None


def test_ground_station_push_accepts():
    assert AgricultureGroundStationPush.accepts(_nav(), 14)
    assert not AgricultureGroundStationPush.accepts(_nav(), 12)
    assert not AgricultureGroundStationPush.accepts(_nav()[:25], 14)
    assert not AgricultureGroundStationPush.accepts(_nav(nsec=1_000_000_000), 14)
    bad = bytearray(_nav())
    struct.pack_into("<d", bad, 8, 3.0)  # latitude beyond pi/2 rad
    assert not AgricultureGroundStationPush.accepts(bytes(bad), 14)
    assert not AgricultureGroundStationPush.accepts(_nav(yaw10=1801), 14)
    assert not AgricultureGroundStationPush.accepts(_nav(b23=2), 14)
    assert not AgricultureGroundStationPush.accepts(_nav(f54=-1.0), 14)
    # AES ciphertext passed through without a key is 16k+1 bytes long
    assert not AgricultureGroundStationPush.accepts(_nav() + bytes(10), 14)


# --- type 57 AirLinkDataField --------------------------------------------------

def _link_status(length: int, mode=3, sdr_up=1, lte_up=1, sdr_q=2, lte_a=5, lte_b=4, b19=0xF0) -> bytes:
    buf = bytearray(length)
    struct.pack_into("<H", buf, 0, 2)
    lte_q = min(lte_a, lte_b)
    fused = max(sdr_q, lte_q) if mode == 3 else sdr_q
    buf[2], buf[3], buf[5], buf[6], buf[8], buf[9], buf[12] = sdr_up, lte_up, sdr_q, lte_q, fused, sdr_q, fused
    buf[10] = 3
    for i in range(13, 19):
        buf[i] = mode
    buf[20] = 1
    buf[22] = 1 if length == 26 else 3
    buf[23], buf[24] = lte_a, lte_b
    if length == 26:
        buf[19] = b19
    else:
        buf[25] = buf[26] = int(mode == 3)
        buf[29] = 1
    return bytes(buf)


def test_airlink_subtype1():
    a = AirLinkDataField.from_bytes(b"\x01\x00\x04")
    assert (a.sub_type, a.sdr_quality) == (1, 4)
    # Subtype-2 fields are absent, not "link down"
    assert a.sdr_link_up is None and a.link_quality is None and a.link_work_mode is None


def test_airlink_subtype2_o3():
    a = AirLinkDataField.from_bytes(_link_status(26))
    assert a.sub_type == 2 and a.sdr_link_up and a.lte_link_up
    assert (a.sdr_quality, a.lte_quality, a.link_quality) == (2, 4, 4)
    assert a.link_work_mode == LinkWorkMode.SdrLte
    assert (a.lte_level_a, a.lte_level_b, a.aux_level_1hz) == (5, 4, 3)
    assert a.channel_like_19 == -16
    assert a.lte_fusion is None and a.const_29 is None and a.layout_code == 1


def test_airlink_subtype2_o4():
    a = AirLinkDataField.from_bytes(_link_status(35, mode=1, lte_up=0, lte_a=0, lte_b=0))
    assert a.link_work_mode == LinkWorkMode.SdrOnly and not a.lte_link_up
    assert a.link_quality == 2 and a.lte_fusion is False and a.const_29 == 1
    assert a.channel_like_19 is None and a.layout_code == 3


def test_airlink_unknown_length_parses_common_block_only():
    buf = bytearray(_link_status(26)) + bytes(14)  # 40 bytes, layout code 1
    buf[25] = 1
    a = AirLinkDataField.from_bytes(bytes(buf))
    assert a.channel_like_19 == -16 and a.lte_fusion is None and a.const_29 is None
    o4_long = AirLinkDataField.from_bytes(_link_status(35) + bytes(5))
    assert o4_long.lte_fusion is None and o4_long.channel_like_19 is None


def test_airlink_gate():
    assert AirLinkDataField.accepts(b"\x01\x00\x04", 14)
    assert AirLinkDataField.accepts(_link_status(26), 14)
    assert AirLinkDataField.accepts(_link_status(35), 14)
    assert not AirLinkDataField.accepts(b"", 14)  # end-of-log stub / failed decryption
    assert not AirLinkDataField.accepts(b"\x01\x00\x04", 12)  # v12 layout is unrelated
    assert not AirLinkDataField.accepts(b"\x07\x00\x01\x02", 14)  # unknown subtype
    assert not AirLinkDataField.accepts(b"\x02\x00\x01\x00\x00\x05", 14)  # short subtype 2
    assert not AirLinkDataField.accepts(b"\x01\x00\xc8", 14)  # level out of range
    # Ciphertext that happens to start with subtype 2 fails the structure checks
    noise = bytes([2, 0]) + bytes((i * 97 + 13) & 0xFF for i in range(31))
    assert not AirLinkDataField.accepts(noise, 14)


# --- type 54 GOBusinessData ----------------------------------------------------

def _warning(text: str, level: int) -> bytes:
    return _pb_bytes(4, _pb_bytes(1, text.encode()) + _pb_varint(2, level))


def test_go_business_warnings_snapshot():
    msg = (_pb_varint(1, 1) + _warning("Compass error (Code: 30004)", 3)
           + _warning("No SD card (Code: 1B030014)", 2) + _pb_varint(7, 1))
    g = GOBusinessData.from_bytes(msg)
    assert g.is_complete and g.ui_marker == 1 and g.warnings_updated
    assert [(w.code, w.level) for w in g.warnings] == [("30004", 3), ("1B030014", 2)]
    assert g.status_bar is None and g.tip is None


def test_go_business_status_bar_and_tip():
    sb = GOBusinessData.from_bytes(_pb_varint(1, 1) + _pb_bytes(2, _pb_bytes(1, b"In flight") + _pb_varint(3, 1))
                                   + _pb_varint(6, 1))
    assert sb.status_bar.text == "In flight" and sb.status_bar.level == 1 and sb.status_bar_updated

    tip_body = _pb_bytes(2, b"30800") + _pb_bytes(3, b"Home Point updated") + _pb_double(5, 3000.0)
    t = GOBusinessData.from_bytes(_pb_varint(1, 1) + _pb_bytes(3, tip_body) + _pb_varint(5, 1))
    assert (t.tip.level, t.tip.code, t.tip.text, t.tip.duration_ms) == (0, "30800", "Home Point updated", 3000.0)

    cleared = GOBusinessData.from_bytes(_pb_varint(1, 1) + _pb_varint(5, 1))
    assert cleared.tip_updated and cleared.tip is None


def test_go_business_session_v12_trailer_and_truncation():
    session = GOBusinessData.from_bytes(b"\x40\x01\x48\x02")
    assert (session.flag_8, session.value_9, session.ui_marker) == (1, 2, 0)
    assert GOBusinessData.from_bytes(b"\x40\x01\x48\x02\x99", version=12).value_9 == 2
    assert GOBusinessData.from_bytes(b"").is_complete

    msg = _pb_varint(1, 1) + _warning("Low battery (Code: 30002)", 2)
    truncated = GOBusinessData.from_bytes(msg[:-4])
    assert not truncated.is_complete and truncated.ui_marker == 1

    with_unknown = GOBusinessData.from_bytes(_pb_varint(1, 1) + _pb_varint(15, 9) + _pb_varint(7, 1))
    assert with_unknown.is_complete and with_unknown.warnings_updated


def test_go_business_gate():
    assert GOBusinessData.accepts(_pb_varint(1, 1) + _pb_varint(7, 1), 14)
    assert GOBusinessData.accepts(b"\x40\x01\x48\x02", 14)  # session record
    assert GOBusinessData.accepts(b"\x40\x01\x48\x02\x99", 12)  # v12 with trailer
    assert GOBusinessData.accepts(b"", 14)
    assert not GOBusinessData.accepts(_pb_varint(1, 1) + _pb_varint(7, 1), 6)
    msg = _pb_varint(1, 1) + _warning("Low battery (Code: 30002)", 2)
    assert not GOBusinessData.accepts(msg[:-4], 14)  # truncated
    assert not GOBusinessData.accepts(_pb_varint(1, 7) + _pb_varint(7, 1), 14)  # unexpected marker
    assert not GOBusinessData.accepts(_pb_varint(12, 3), 14)  # parses, but no real structure
    assert not GOBusinessData.accepts(_pb_varint(7, 1), 14)  # HUD part without field 1
    assert not GOBusinessData.accepts(bytes((i * 89 + 7) & 0xFF for i in range(33)), 14)


# --- type 55 SecurityBlock -----------------------------------------------------

def test_security_block():
    seed = 0x30
    block = bytes([0xC7, 0x70]) + bytes(range(254))
    s = SecurityBlock.from_bytes(block + bytes([(seed + 55) & 0xFF]), seed=seed)
    assert s.block == block and s.check_ok is True and s.in_range
    assert s.block_hex.startswith("c770")
    assert SecurityBlock.from_bytes(block + b"\x00", seed=seed).check_ok is False
    assert not SecurityBlock.from_bytes(b"\xff" * 257).in_range
    assert SecurityBlock.accepts(bytes(257), 14)
    assert not SecurityBlock.accepts(bytes(257), 12)
    assert not SecurityBlock.accepts(bytes(256), 14)


# --- reader dispatch ------------------------------------------------------------

def test_reader_dispatch_and_fallback():
    reader = RecordReader(b"", 14)
    assert isinstance(reader._parse_record(45, _rtk(83), 99).data, RTKDifference)
    assert isinstance(reader._parse_record(48, _nav(), 74).data, AgricultureGroundStationPush)
    assert isinstance(reader._parse_record(32, bytes(7), 18).data, GSMissionStatus)
    assert isinstance(reader._parse_record(57, b"\x01\x00\x03", 18).data, AirLinkDataField)
    assert isinstance(reader._parse_record(57, b"", 48).data, UnknownRecord)  # end-of-log stub
    sec = reader._parse_record(55, bytes(256) + b"\x40", 258, seed=9)
    assert isinstance(sec.data, SecurityBlock) and sec.data.check_ok

    # Failed decryption or unrelated layouts stay unknown instead of becoming zero rows
    assert isinstance(reader._parse_record(45, b"", 99).data, UnknownRecord)
    assert isinstance(reader._parse_record(32, b"", 18).data, UnknownRecord)
    assert isinstance(reader._parse_record(55, bytes(10), 258).data, UnknownRecord)

    v12 = RecordReader(b"", 12)
    assert isinstance(v12._parse_record(48, bytes(20), 21).data, UnknownRecord)
    assert isinstance(v12._parse_record(57, b"\x63", 2).data, UnknownRecord)


def _v12_record(record_type: int, plaintext: bytes, seed: int = 0x21) -> bytes:
    """A well-formed v12 record: type, u8 length, seed + XOR payload + check byte, 0xFF."""
    body = bytes([seed]) + xor_decode_block(bytes([seed]) + plaintext + b"\x00", record_type)
    assert len(body) <= 255
    return bytes([record_type, len(body)]) + body + b"\xff"


def test_v12_go_business_length_overflow_is_recovered():
    text = "Extra payload detected. " * 12 + "(Code: 30231)"
    pb = _pb_varint(1, 1) + _warning(text, 2) + _pb_varint(7, 1)
    seed = 0x5C
    body = bytearray([seed]) + xor_decode_block(bytes([seed]) + pb + b"\x00", 54)
    true_len = len(body)
    assert true_len > 255
    stored = true_len & 0xFF
    body[stored] = 0xFF  # the writer's terminator lands inside the payload
    stream = bytes([54, stored]) + bytes(body) + b"\x00" + _v12_record(9, b"hello")

    records = RecordReader(stream, 12).read_records({})
    go = [r.data for r in records if isinstance(r.data, GOBusinessData)]
    tips = [r.data for r in records if isinstance(r.data, AppTip)]
    assert len(go) == 1 and go[0].is_complete and go[0].warnings_updated
    assert go[0].warnings[0].code == "30231" and go[0].warnings[0].level == 2
    assert [t.message for t in tips] == ["hello"]


def _overflow_stream(text_len: int, seed: int = 0x5C) -> tuple[bytes, int]:
    """A v12 type-54 record longer than 255 bytes, written with the writer's bug."""
    pb = _pb_varint(1, 1) + _warning("x" * (text_len - 13) + "(Code: 30231)", 2) + _pb_varint(7, 1)
    body = bytearray([seed]) + xor_decode_block(bytes([seed]) + pb + b"\x00", 54)
    stored = len(body) & 0xFF
    body[stored] = 0xFF
    return bytes([54, stored]) + bytes(body) + b"\x00" + _v12_record(9, b"hello"), stored


@pytest.mark.parametrize("text_len, expected_stored", [(246, 4), (242, 0)])
def test_v12_overflow_where_terminator_hits_structure(text_len, expected_stored):
    # stored 4: the 0xFF lands on the outer length varint; stored 0: on the XOR seed
    stream, stored = _overflow_stream(text_len)
    assert stored == expected_stored
    records = RecordReader(stream, 12).read_records({})
    go = [r.data for r in records if isinstance(r.data, GOBusinessData)]
    assert len(go) == 1 and go[0].is_complete and go[0].warnings[0].code == "30231"
    assert [r.data.message for r in records if isinstance(r.data, AppTip)] == ["hello"]


def test_v12_consecutive_overflow_records_are_recovered():
    # The app writes several long warning snapshots in one burst
    first, _ = _overflow_stream(250, seed=0x31)
    second, _ = _overflow_stream(270, seed=0x47)
    tail = _v12_record(9, b"hello")
    stream = first[:-len(tail)] + second
    records = RecordReader(stream, 12).read_records({})
    go = [r.data for r in records if isinstance(r.data, GOBusinessData)]
    assert len(go) == 2 and all(g.is_complete for g in go)
    assert [r.data.message for r in records if isinstance(r.data, AppTip)] == ["hello"]
    assert not [r for r in records if isinstance(r.data, UnknownRecord)]


def test_v12_normal_go_business_is_unchanged():
    pb = _pb_varint(1, 1) + _pb_bytes(2, _pb_bytes(1, b"GPS") + _pb_varint(3, 2)) + _pb_varint(6, 1)
    stream = _v12_record(54, pb) + _v12_record(9, b"next")
    records = RecordReader(stream, 12).read_records({})
    assert records[0].data.status_bar.text == "GPS"
    assert records[1].data.message == "next"


# --- frames and JSON ------------------------------------------------------------

def _osd() -> OSD:
    return OSD.from_bytes(bytes(60))


def test_extended_frames_only_with_flag():
    # A frame is emitted per OSD record and collects the records that follow it.
    records = [
        Record(RecordType.OSD, _osd()),
        Record(RecordType.OSD, _osd()),
        Record(RecordType.RTKDifference, RTKDifference.from_bytes(_rtk(83))),
        Record(RecordType.AirLinkDataField, AirLinkDataField.from_bytes(_link_status(35))),
        Record(RecordType.AgricultureGroundStationPush, AgricultureGroundStationPush.from_bytes(_nav())),
        Record(RecordType.GOBusiness, GOBusinessData.from_bytes(
            _pb_varint(1, 1) + _warning("Compass error (Code: 30004)", 3) + _pb_varint(7, 1))),
        Record(RecordType.OSD, _osd()),
        # Replay of an earlier record (same aircraft clock) is ignored
        Record(RecordType.AgricultureGroundStationPush, AgricultureGroundStationPush.from_bytes(_nav(f54=1.0))),
        Record(RecordType.GOBusiness, GOBusinessData.from_bytes(_pb_varint(1, 1) + _pb_varint(7, 1))),
        Record(RecordType.OSD, _osd()),
    ]
    plain = records_to_frames(records)
    assert not {"rtk", "airLink", "navigation", "appHud"} & set(plain[0].to_dict())

    frames = [f.to_dict() for f in records_to_frames(records, extended=True)]
    assert frames[0]["rtk"]["positionSolution"] is None  # before the first RTK record
    assert frames[0]["appHud"]["warnings"] is None
    f1 = frames[1]
    assert f1["rtk"]["positionSolution"] == "Fixed" and f1["rtk"]["satellites"] == 40
    assert f1["airLink"]["workMode"] == "SdrLte" and f1["airLink"]["linkQuality"] == 4
    assert f1["navigation"]["distanceToHome"] == pytest.approx(123.5)
    assert f1["appHud"]["warnings"] == [{"text": "Compass error (Code: 30004)", "code": "30004", "level": 3}]
    f2 = frames[2]
    assert f2["navigation"]["distanceToHome"] == pytest.approx(123.5)
    assert f2["appHud"]["warnings"] == []


def test_extended_air_link_keeps_subtype2_state():
    records = [
        Record(RecordType.OSD, _osd()),
        Record(RecordType.AirLinkDataField, AirLinkDataField.from_bytes(
            _link_status(35, mode=1, sdr_q=5, lte_up=0, lte_a=0, lte_b=0))),
        Record(RecordType.OSD, _osd()),
        Record(RecordType.AirLinkDataField, AirLinkDataField.from_bytes(b"\x01\x00\x03")),
        Record(RecordType.AirLinkDataField, AirLinkDataField.from_bytes(b"\x02\x00\x01\x00\x00\x05")),
        Record(57, UnknownRecord(record_type=57, data=b"")),
        Record(RecordType.AirLinkDataField, AirLinkDataField.from_bytes(b"\x07\x00\x01")),
    ]
    last = records_to_frames(records, extended=True)[-1].to_dict()["airLink"]
    assert last["sdrLinkUp"] is True and last["workMode"] == "SdrOnly" and last["linkQuality"] == 5
    assert last["sdrQuality"] == 3  # newest SDR level from subtype 1


def test_security_never_uses_aes():
    seed = 0x11
    plain = bytes(256) + bytes([(seed + 55) & 0xFF])
    raw = bytes([seed]) + xor_decode_block(bytes([seed]) + plain, 55)
    keychain = {FeaturePoint.SecurityFeature: (bytes(16), bytes(32))}
    decoded, kc = decode_record_payload(raw, 55, 14, keychain, len(raw))
    assert decoded == plain
    assert kc[FeaturePoint.SecurityFeature] == (bytes(16), bytes(32))  # IV chain untouched


def test_raw_json_serializes_nested_records():
    g = GOBusinessData.from_bytes(_pb_varint(1, 1) + _warning("No SD card (Code: 10022)", 2) + _pb_varint(7, 1))
    d = _serialize_record_data(g)
    assert d["warnings"] == [{"text": "No SD card (Code: 10022)", "level": 2, "code": "10022"}]
    assert d["status_bar"] is None
    r = _serialize_record_data(RTKDifference.from_bytes(_rtk(80)))
    assert r["position_solution"] == "Fixed" and r["heading_solution"] == "Fixed"
    s = _serialize_record_data(SecurityBlock.from_bytes(bytes(257), seed=-55))
    assert "block" not in s and s["check_ok"] is True
    gs = _serialize_record_data(GSMissionStatus.from_bytes(bytes([2, 1, 0, 0, 0, 0, 0])))
    assert gs["raw_hex"] == "02010000000000" and gs["mission_type"] == "Hotpoint"


def test_raw_json_expands_existing_nested_records():
    adsb = ADSBFlightData(aircraft=[ADSBAircraft(icao_address="abc123")])
    d = _serialize_record_data(adsb)
    assert isinstance(d["aircraft"][0], dict) and d["aircraft"][0]["icao_address"] == "abc123"
