"""Offline tests for the DJIFlyCustom AES IV chain in v14 record streams.

Custom (5), AppTip (9), AppWarn (10) and AppSeriousWarn (24) share one IV chain
with the 0xFD (KeyValueSnapshot) and 0xFE records. If 0xFD/0xFE are skipped without decoding,
the next record in the chain decrypts with a stale IV and its first 16 bytes
come out as garbage.
"""

import struct
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from dji_flightlog_parser import DJILog
from dji_flightlog_parser.decoder.feature_point import FeaturePoint, feature_point_from_record_type
from dji_flightlog_parser.decoder.xor import xor_decode_block
from dji_flightlog_parser.record.key_value_snapshot import KEY_SNAPSHOT, MODULE_COMPONENT_SERIALS
from dji_flightlog_parser.record.reader import RecordReader
from dji_flightlog_parser.record.types import RecordType

KEY = bytes(range(32))
IV = bytes(range(100, 116))

TIMESTAMP_MS = 1_893_456_000_123  # synthetic: 2030-01-01T00:00:00.123Z

# Synthetic 0xFE payload (not parsed) and a synthetic 0xFD KeyValueSnapshot:
# header (module, key, payload length, 0, flags) + one protobuf serial field
FE_PLAINTEXT = b"\x00\x01synthetic"
_FD_SERIAL = b"TESTCAM0000001"
_FD_PAYLOAD = bytes([(1 << 3) | 2, len(_FD_SERIAL)]) + _FD_SERIAL
FD_PLAINTEXT = struct.pack("<HHHBB", MODULE_COMPONENT_SERIALS, KEY_SNAPSHOT, len(_FD_PAYLOAD), 0, 0) + _FD_PAYLOAD

SEQUENCE = [
    (RecordType.Custom, b"\x01\x00" + struct.pack("<ffq", 12.5, 340.0, TIMESTAMP_MS)),
    (0xFE, FE_PLAINTEXT),
    (RecordType.AppWarn, b"Remote Controller Signal Weak\x00"),
    (0xFD, FD_PLAINTEXT),
    (0xFE, FE_PLAINTEXT),
    (RecordType.AppTip, b"Switched to Normal (N) mode\x00"),
    (0xFE, FE_PLAINTEXT),
    (RecordType.Custom, b"\x00\x01" + struct.pack("<ffq", 3.0, 341.5, TIMESTAMP_MS + 100)),
]


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


def _stream() -> bytes:
    ciphertexts = _encrypt_chain([pt for _, pt in SEQUENCE])
    return b"".join(_frame_record(int(rt), ct) for (rt, _), ct in zip(SEQUENCE, ciphertexts))


def _v14_log() -> DJILog:
    log = DJILog.__new__(DJILog)
    log.version = 14
    return log


def _read_with_keychains(stream: bytes):
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    return _v14_log()._read_records_with_keychains(stream, [keychain], 0)


def _read_with_record_reader(stream: bytes):
    keychain = {FeaturePoint.DJIFlyCustomFeature: (IV, KEY)}
    return RecordReader(stream, 14).read_records(keychain)


def test_fd_fe_map_to_dji_fly_custom_in_v14():
    assert feature_point_from_record_type(0xFD, 14) == FeaturePoint.DJIFlyCustomFeature
    assert feature_point_from_record_type(0xFE, 14) == FeaturePoint.DJIFlyCustomFeature
    assert feature_point_from_record_type(0xFD, 13) == FeaturePoint.PlaintextFeature
    assert feature_point_from_record_type(0xFE, 13) == FeaturePoint.PlaintextFeature


@pytest.mark.parametrize("read", [_read_with_keychains, _read_with_record_reader])
def test_fd_fe_records_advance_dji_fly_custom_iv_chain(read):
    records = read(_stream())

    # 0xFE is consumed for the IV chain only; 0xFD is emitted as KeyValueSnapshot.
    assert [int(r.record_type) for r in records] == [
        RecordType.Custom, RecordType.AppWarn, RecordType.KeyValueSnapshot, RecordType.AppTip, RecordType.Custom,
    ]

    assert records[1].data.message == "Remote Controller Signal Weak"
    assert records[2].data.serials == {1: "TESTCAM0000001"}
    assert records[3].data.message == "Switched to Normal (N) mode"

    first, last = records[0].data, records[4].data
    assert (first.camera_shoot, first.video_shoot, first.h_speed, first.distance) == (True, False, 12.5, 340.0)
    assert (last.camera_shoot, last.video_shoot, last.h_speed, last.distance) == (False, True, 3.0, 341.5)
    assert last.update_timestamp == datetime.fromtimestamp((TIMESTAMP_MS + 100) / 1000, tz=timezone.utc)
