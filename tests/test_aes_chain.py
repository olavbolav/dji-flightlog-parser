"""Offline tests for per-feature-point AES IV chaining in v14 record streams."""

import logging
import struct
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from dji_flightlog_parser import DJILog
from dji_flightlog_parser.decoder.feature_point import FeaturePoint
from dji_flightlog_parser.decoder.xor import xor_decode_block
from dji_flightlog_parser.record.airlink import AirLinkDataField
from dji_flightlog_parser.record.app import AppTip, AppWarn
from dji_flightlog_parser.record.custom import Custom
from dji_flightlog_parser.record.key_value_snapshot import KeyValueSnapshot
from dji_flightlog_parser.record.ofdm import OFDM
from dji_flightlog_parser.record.reader import RecordReader
from dji_flightlog_parser.record.types import RecordType

KEY = bytes(range(32))
IV = bytes(range(100, 116))


def _encrypt_chain(plaintexts: list[bytes]) -> list[bytes]:
    """AES-256-CBC encrypt each plaintext, chaining the IV like the aircraft does."""
    iv = IV
    out = []
    for pt in plaintexts:
        padder = PKCS7(128).padder()
        padded = padder.update(pt) + padder.finalize()
        enc = Cipher(algorithms.AES(KEY), modes.CBC(iv)).encryptor()
        ct = enc.update(padded) + enc.finalize()
        out.append(ct)
        iv = ct[-16:]
    return out


def _frame_record(record_type: int, ciphertext: bytes, seed: int = 0x5A) -> bytes:
    """Wrap ciphertext as a v14 record: type, u16 length, XOR payload, 0xFF."""
    obfuscated = xor_decode_block(bytes([seed]) + ciphertext + b"\x00", record_type)
    payload = bytes([seed]) + obfuscated
    return bytes([record_type]) + struct.pack("<H", len(payload)) + payload + b"\xff"


def _v14_log() -> DJILog:
    log = DJILog.__new__(DJILog)
    log.version = 14
    return log


def test_type_57_advances_airlink_iv_chain(caplog):
    """Type 57 shares the AirLink IV chain with OFDM (49); skipping it breaks the next OFDM."""
    signals = [0x80 | 85, 70, 0x80 | 64, 99]
    radio_levels = bytes([0x01, 0x00, 4])  # AirLink subtype 1, SDR quality level 4

    sequence = []
    for s in signals:
        sequence.append((RecordType.OFDM, bytes([s])))
        sequence.append((57, radio_levels))

    ciphertexts = _encrypt_chain([pt for _, pt in sequence])
    stream = b"".join(_frame_record(int(rt), ct) for (rt, _), ct in zip(sequence, ciphertexts))

    keychain = {FeaturePoint.AirLinkFeature: (IV, KEY)}
    with caplog.at_level(logging.WARNING, logger="dji_flightlog_parser"):
        records = _v14_log()._read_records_with_keychains(stream, [keychain], 0)

    assert not [r for r in caplog.records if "AES decryption failed" in r.getMessage()]

    ofdm = [r.data for r in records if r.record_type == RecordType.OFDM]
    assert all(isinstance(o, OFDM) for o in ofdm)
    assert [(o.signal_percent, o.is_up) for o in ofdm] == [(s & 0x7F, bool(s & 0x80)) for s in signals]

    airlink = [r.data for r in records if r.record_type == 57]
    assert all(isinstance(a, AirLinkDataField) for a in airlink)
    assert [(a.sub_type, a.sdr_quality) for a in airlink] == [(1, 4)] * len(signals)


# Records 253/254 sit in the DJIFlyCustom chain between tips, warnings and
# Custom records. On v14, 253 is emitted as KeyValueSnapshot and 254 is not
# emitted, but both must be decrypted: skipping one garbles the first block of
# the next record in the chain.
_TIP = "Synthetic tip text for the chain test"
_WARN = "Synthetic warning text for the chain test"
_TS = datetime(2030, 1, 1, 0, 0, 0, 123000, tzinfo=timezone.utc)
_SNAP_TS = _TS - timedelta(milliseconds=136)
_SERIALS = {7: "TESTBAT0000007", 8: "TESTBAT0000008"}
_TOTAL_FLIGHT_TIME = 98765.5


def _key_value(module: int, key: int, payload: bytes, ts: datetime = _SNAP_TS) -> bytes:
    """253/254 plaintext: module, key, payload length, 0, flags 0x80, ms timestamp, protobuf."""
    header = struct.pack("<HHHBB", module, key, len(payload), 0, 0x80)
    return header + struct.pack("<Q", int(round(ts.timestamp() * 1000))) + payload


def _serial_list() -> bytes:
    return b"".join(bytes([(n << 3) | 2, len(s)]) + s.encode() for n, s in _SERIALS.items())


def _djiflycustom_sequence() -> list[tuple[int, bytes]]:
    ts_ms = int(_TS.timestamp() * 1000)
    custom = struct.pack("<BBffq", 0, 1, 3.5, 120.0, ts_ms)
    return [
        (0xFD, _key_value(7, 1, _serial_list())),
        (RecordType.AppTip, _TIP.encode() + b"\x00"),
        (0xFE, _key_value(5, 4, b"\x09" + struct.pack("<d", 12.5))),
        (RecordType.Custom, custom),
        (0xFD, _key_value(5, 1, b"\x09" + struct.pack("<d", _TOTAL_FLIGHT_TIME))),
        (RecordType.AppWarn, _WARN.encode() + b"\x00"),
    ]


def _djiflycustom_stream() -> bytes:
    sequence = _djiflycustom_sequence()
    ciphertexts = _encrypt_chain([pt for _, pt in sequence])
    return b"".join(_frame_record(int(rt), ct) for (rt, _), ct in zip(sequence, ciphertexts))


def _check_djiflycustom_records(records, caplog):
    assert not [r for r in caplog.records if "AES decryption failed" in r.getMessage()]
    assert [r.record_type for r in records] == [
        RecordType.KeyValueSnapshot, RecordType.AppTip, RecordType.Custom,
        RecordType.KeyValueSnapshot, RecordType.AppWarn,
    ]
    assert 0xFE not in [int(r.record_type) for r in records]

    serials, tip, custom, flight_time, warn = (r.data for r in records)
    assert isinstance(serials, KeyValueSnapshot)
    assert (serials.module, serials.key, serials.timestamp) == (7, 1, _SNAP_TS)
    assert serials.serials == _SERIALS and serials.total_flight_time is None
    assert isinstance(tip, AppTip) and tip.message == _TIP
    assert isinstance(custom, Custom)
    assert custom.update_timestamp == _TS
    assert (custom.video_shoot, custom.h_speed, custom.distance) == (True, 3.5, 120.0)
    assert isinstance(flight_time, KeyValueSnapshot)
    assert (flight_time.module, flight_time.key) == (5, 1)
    assert flight_time.total_flight_time == _TOTAL_FLIGHT_TIME and flight_time.serials == {}
    assert isinstance(warn, AppWarn) and warn.message == _WARN


def test_253_254_advance_djiflycustom_iv_chain(caplog):
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    with caplog.at_level(logging.WARNING, logger="dji_flightlog_parser"):
        records = _v14_log()._read_records_with_keychains(_djiflycustom_stream(), [keychain], 0)
    _check_djiflycustom_records(records, caplog)


def test_253_254_advance_djiflycustom_iv_chain_record_reader(caplog):
    """Same stream through RecordReader, which callers can use directly with one keychain."""
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    with caplog.at_level(logging.WARNING, logger="dji_flightlog_parser"):
        records = RecordReader(_djiflycustom_stream(), 14).read_records(keychain)
    _check_djiflycustom_records(records, caplog)


def test_skipping_253_254_would_garble_the_chain():
    """Control: the stream really chains, so a 253/254 that is not decrypted breaks the next record."""
    sequence = _djiflycustom_sequence()
    ciphertexts = _encrypt_chain([pt for _, pt in sequence])
    kept = [(rt, ct) for (rt, _), ct in zip(sequence, ciphertexts) if rt not in (0xFD, 0xFE)]
    stream = b"".join(_frame_record(int(rt), ct) for rt, ct in kept)
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    records = RecordReader(stream, 14).read_records(keychain)
    tip = records[0].data
    assert not (isinstance(tip, AppTip) and tip.message == _TIP)


def _v13_log() -> DJILog:
    log = DJILog.__new__(DJILog)
    log.version = 13
    return log


def test_253_254_not_emitted_on_v13(caplog):
    """v13 maps 253/254 to Plaintext (unverified): XOR only, outside the chain, never emitted."""
    sequence = _djiflycustom_sequence()
    chained = [(rt, pt) for rt, pt in sequence if rt not in (0xFD, 0xFE)]
    ciphertexts = iter(_encrypt_chain([pt for _, pt in chained]))
    stream = b"".join(
        _frame_record(int(rt), pt if rt in (0xFD, 0xFE) else next(ciphertexts)) for rt, pt in sequence
    )
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    with caplog.at_level(logging.WARNING, logger="dji_flightlog_parser"):
        for records in (
            _v13_log()._read_records_with_keychains(stream, [dict(keychain)], 0),
            RecordReader(stream, 13).read_records(dict(keychain)),
        ):
            assert [r.record_type for r in records] == [RecordType.AppTip, RecordType.Custom, RecordType.AppWarn]
            assert records[0].data.message == _TIP and records[2].data.message == _WARN
    assert not [r for r in caplog.records if "AES decryption failed" in r.getMessage()]


def _v12_record(record_type: int, plaintext: bytes, seed: int = 0x21) -> bytes:
    body = bytes([seed]) + xor_decode_block(bytes([seed]) + plaintext + b"\x00", record_type)
    return bytes([record_type, len(body)]) + body + b"\xff"


def test_253_254_not_emitted_on_v12():
    sequence = _djiflycustom_sequence()
    stream = b"".join(_v12_record(int(rt), pt) for rt, pt in sequence)
    records = RecordReader(stream, 12).read_records({})
    assert [r.record_type for r in records] == [RecordType.AppTip, RecordType.Custom, RecordType.AppWarn]
