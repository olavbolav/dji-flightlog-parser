"""CRC64-based XOR decoder for DJI flight log obfuscation (v7+).

Uses the Redis/Jones CRC64 polynomial to match the Rust crc64 crate.
"""

from __future__ import annotations

# Redis/Jones CRC64 lookup table.
# Normal polynomial: 0xad93d23594c935a9
# Reflected polynomial for table-based (right-shift) computation: 0x95AC9329AC4BC9B5
_CRC64_TABLE: list[int] = []

def _init_table() -> None:
    poly = 0x95AC9329AC4BC9B5
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
        _CRC64_TABLE.append(crc & 0xFFFFFFFFFFFFFFFF)

_init_table()


def crc64(init: int, data: bytes) -> int:
    """Compute CRC64 (Redis/Jones) with an initial value."""
    crc = init & 0xFFFFFFFFFFFFFFFF
    for b in data:
        crc = _CRC64_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
        crc &= 0xFFFFFFFFFFFFFFFF
    return crc


def _make_xor_key(first_byte: int, record_type: int) -> bytes:
    """Derive the 8-byte XOR key from first_byte and record_type."""
    magic = 0x123456789ABCDEF0

    seed = (first_byte + record_type) & 0xFF
    mul_val = (magic * first_byte) & 0xFFFFFFFFFFFFFFFF
    mul_bytes = mul_val.to_bytes(8, byteorder="little")
    key_u64 = crc64(seed, mul_bytes)
    return key_u64.to_bytes(8, byteorder="little")


def xor_decode_block(data: bytes, record_type: int) -> bytes:
    """Decode a full block of XOR-obfuscated data.

    The first byte of data is consumed as the XOR seed and is not part
    of the returned plaintext.
    """
    if not data:
        return b""

    first_byte = data[0]
    key = _make_xor_key(first_byte, record_type)
    payload = data[1:]

    result = bytearray(len(payload))
    for i, b in enumerate(payload):
        result[i] = b ^ key[i % 8]
    return bytes(result)


class XorDecoder:
    """Streaming XOR decoder that wraps a bytes buffer.

    Mirrors the Rust XorDecoder: reads a first byte to derive the key,
    then XOR-decodes all subsequent reads using position-based key cycling.
    """

    def __init__(self, data: bytes, record_type: int):
        if not data:
            self._key = b"\x00" * 8
            self._data = b""
            self._pos = 0
            return

        first_byte = data[0]
        self._key = _make_xor_key(first_byte, record_type)
        self._data = data[1:]
        self._pos = 0

    def read(self, n: int) -> bytes:
        """Read and decode n bytes from current position."""
        chunk = self._data[self._pos:self._pos + n]
        result = bytearray(len(chunk))
        for i, b in enumerate(chunk):
            result[i] = b ^ self._key[(self._pos + i) % 8]
        self._pos += len(chunk)
        return bytes(result)

    def read_all(self) -> bytes:
        """Read and decode all remaining bytes."""
        return self.read(len(self._data) - self._pos)

    def seek(self, pos: int) -> None:
        """Seek to absolute position (relative to after first_byte)."""
        self._pos = pos

    @property
    def remaining(self) -> int:
        return max(0, len(self._data) - self._pos)

    @property
    def position(self) -> int:
        return self._pos
