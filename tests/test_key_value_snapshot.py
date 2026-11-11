"""Offline tests for the KeyValueSnapshot record (type 253), synthetic bytes only."""

from __future__ import annotations

import random
import struct
from datetime import datetime, timezone

import pytest

from dji_flightlog_parser.record.key_value_snapshot import KeyValueSnapshot
from dji_flightlog_parser.record.reader import RecordReader
from dji_flightlog_parser.record.types import RecordType
from dji_flightlog_parser.record.unknown import UnknownRecord

_TS = datetime(2026, 3, 14, 9, 26, 53, 589000, tzinfo=timezone.utc)


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


def _pb_bytes(num: int, b: bytes) -> bytes:
    return _varint((num << 3) | 2) + _varint(len(b)) + b


def _pb_varint(num: int, v: int) -> bytes:
    return _varint(num << 3) + _varint(v)


def _pb_double(num: int, v: float) -> bytes:
    return _varint((num << 3) | 1) + struct.pack("<d", v)


def _pb_fixed32(num: int, v: int) -> bytes:
    return _varint((num << 3) | 5) + struct.pack("<I", v)


def snapshot(module: int, key: int, payload: bytes, ts: datetime | None = _TS) -> bytes:
    """Header (module, key, payload length, 0, flags) + optional ms timestamp + payload."""
    flags = 0x80 if ts is not None else 0
    out = struct.pack("<HHHBB", module, key, len(payload), 0, flags)
    if ts is not None:
        out += struct.pack("<Q", int(round(ts.timestamp() * 1000)))
    return out + payload


SERIALS = {1: "TESTCAM0000001", 6: "TESTACC0000006", 7: "TESTBAT0000007", 8: "TESTBAT0000008"}


def _serial_list() -> bytes:
    return b"".join(_pb_bytes(n, s.encode()) for n, s in SERIALS.items())


def test_component_serial_list():
    data = snapshot(7, 1, _serial_list())
    assert KeyValueSnapshot.accepts(data, 14)
    s = KeyValueSnapshot.from_bytes(data, 14)
    assert (s.module, s.key) == (7, 1)
    assert s.timestamp == _TS
    assert s.serials == SERIALS
    assert s.total_flight_time is None


def test_payload_starts_at_8_without_timestamp():
    data = snapshot(7, 1, _pb_bytes(2, b"TESTUNK0000002"), ts=None)
    assert KeyValueSnapshot.accepts(data, 14)
    s = KeyValueSnapshot.from_bytes(data, 14)
    assert s.timestamp is None
    assert s.serials == {2: "TESTUNK0000002"}


def test_empty_serial_list():
    data = snapshot(7, 1, b"")
    assert len(data) == 16
    assert KeyValueSnapshot.accepts(data, 14)
    s = KeyValueSnapshot.from_bytes(data, 14)
    assert s.serials == {} and s.timestamp == _TS


def test_serial_list_skips_non_strings_and_keeps_first_duplicate():
    payload = (_pb_bytes(7, b"TESTBAT0000007") + _pb_varint(3, 5) + _pb_bytes(4, b"\x01\x02\xff")
               + _pb_bytes(7, b"TESTBAT9999999") + _pb_bytes(8, b"TESTBAT0000008\x00"))
    s = KeyValueSnapshot.from_bytes(snapshot(7, 1, payload), 14)
    assert s.serials == {7: "TESTBAT0000007", 8: "TESTBAT0000008"}


def test_serial_list_skips_ascii_with_control_characters():
    payload = _pb_bytes(1, b"AB\x01CD") + _pb_bytes(6, b"AB\tCD") + _pb_bytes(7, b"TESTBAT0000007")
    s = KeyValueSnapshot.from_bytes(snapshot(7, 1, payload), 14)
    assert s.serials == {7: "TESTBAT0000007"}


def test_total_flight_time():
    data = snapshot(5, 1, _pb_double(1, 123456.75))
    assert len(data) == 25
    assert KeyValueSnapshot.accepts(data, 14)
    s = KeyValueSnapshot.from_bytes(data, 14)
    assert (s.module, s.key) == (5, 1)
    assert s.total_flight_time == 123456.75
    assert s.serials == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_total_flight_time_rejects_implausible(value):
    assert KeyValueSnapshot.from_bytes(snapshot(5, 1, _pb_double(1, value)), 14).total_flight_time is None


def test_other_module_keys_decode_header_only():
    # Same wire content under another module/key is not interpreted.
    s = KeyValueSnapshot.from_bytes(snapshot(5, 2, _pb_double(1, 42.0)), 14)
    assert (s.module, s.key, s.timestamp) == (5, 2, _TS)
    assert s.total_flight_time is None and s.serials == {}
    s = KeyValueSnapshot.from_bytes(snapshot(7, 2, _serial_list()), 14)
    assert s.serials == {}


def test_all_wire_types_walked():
    payload = _pb_varint(9, 300) + _pb_fixed32(10, 7) + _pb_double(11, 1.0) + _pb_bytes(7, b"TESTBAT0000007")
    data = snapshot(7, 1, payload)
    assert KeyValueSnapshot.accepts(data, 14)
    assert KeyValueSnapshot.from_bytes(data, 14).serials == {7: "TESTBAT0000007"}


def test_truncated_protobuf_keeps_fields_before_the_damage():
    payload = _pb_bytes(7, b"TESTBAT0000007") + _varint((8 << 3) | 2) + _varint(40) + b"short"
    data = snapshot(7, 1, payload)
    assert not KeyValueSnapshot.accepts(data, 14)
    assert KeyValueSnapshot.from_bytes(data, 14).serials == {7: "TESTBAT0000007"}


def test_payload_longer_than_record_does_not_raise():
    data = snapshot(7, 1, _serial_list())
    s = KeyValueSnapshot.from_bytes(data[:-3], 14)
    assert s.serials == {n: v for n, v in SERIALS.items() if n != 8}
    assert not KeyValueSnapshot.accepts(data[:-3], 14)


def test_accepts_gate():
    good = snapshot(7, 1, _serial_list())
    assert KeyValueSnapshot.accepts(good, 14)
    assert not KeyValueSnapshot.accepts(good, 13)
    assert not KeyValueSnapshot.accepts(good + b"\x00", 14)  # length mismatch
    bad6 = bytearray(good)
    bad6[6] = 1
    assert not KeyValueSnapshot.accepts(bytes(bad6), 14)
    bad_flags = bytearray(good)
    bad_flags[7] = 0x81
    assert not KeyValueSnapshot.accepts(bytes(bad_flags), 14)
    assert not KeyValueSnapshot.accepts(b"", 14)
    assert not KeyValueSnapshot.accepts(good[:7], 14)


@pytest.mark.parametrize("ts_ms", [0, 2**64 - 1])
def test_unusable_timestamp_is_none(ts_ms):
    data = struct.pack("<HHHBBQ", 7, 1, 0, 0, 0x80, ts_ms)
    s = KeyValueSnapshot.from_bytes(data, 14)
    assert s.timestamp is None and (s.module, s.key) == (7, 1)


def test_short_and_random_input_never_raises():
    for n in range(8):
        s = KeyValueSnapshot.from_bytes(bytes(range(n)), 14)
        assert (s.module, s.key, s.timestamp, s.serials, s.total_flight_time) == (0, 0, None, {}, None)
        assert not KeyValueSnapshot.accepts(bytes(range(n)), 14)
    rng = random.Random(253)
    for _ in range(2000):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(40)))
        KeyValueSnapshot.from_bytes(data, 14)
        KeyValueSnapshot.accepts(data, 14)


def test_reader_dispatch():
    v14 = RecordReader(b"", 14)
    data = snapshot(7, 1, _serial_list())
    r = v14._parse_record(253, data, len(data) + 2)
    assert r.record_type == RecordType.KeyValueSnapshot
    assert r.type_name() == "KeyValueSnapshot"
    assert isinstance(r.data, KeyValueSnapshot) and r.data.serials == SERIALS
    # Undecryptable bytes fall back to UnknownRecord.
    assert isinstance(v14._parse_record(253, bytes(range(1, 30)), 31).data, UnknownRecord)
    assert isinstance(RecordReader(b"", 13)._parse_record(253, data, len(data) + 2).data, UnknownRecord)
