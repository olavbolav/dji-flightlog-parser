"""Offline tests for per-feature-point AES IV chaining in v14 record streams."""

import logging
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from dji_flightlog_parser import DJILog
from dji_flightlog_parser.decoder.feature_point import FeaturePoint
from dji_flightlog_parser.decoder.xor import xor_decode_block
from dji_flightlog_parser.record.ofdm import OFDM
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
    radio_levels = bytes(range(1, 21))

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

    levels = [r.data.data for r in records if r.record_type == 57]
    assert levels == [radio_levels] * len(signals)
