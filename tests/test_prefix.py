"""Unit tests for prefix parsing."""

import struct
from dji_flightlog_parser.layout.prefix import Prefix, PREFIX_SIZE


def test_prefix_size():
    assert PREFIX_SIZE == 100


def test_prefix_v14():
    """Verify prefix parsing for v14 files."""
    data = bytearray(200)
    struct.pack_into("<Q", data, 0, 500)   # detail_offset (u64)
    struct.pack_into("<H", data, 8, 200)   # detail_length (u16)
    data[10] = 14                          # version (u8)

    p = Prefix.from_bytes(bytes(data))
    assert p.version == 14
    assert p.detail_offset == 500


def test_prefix_records_offset():
    """Records offset should be past the prefix for v13+."""
    data = bytearray(200)
    struct.pack_into("<Q", data, 0, 150)   # detail_offset (u64)
    struct.pack_into("<H", data, 8, 40)    # detail_length (u16)
    data[10] = 14                          # version (u8)

    p = Prefix.from_bytes(bytes(data))
    assert p.records_offset() >= PREFIX_SIZE
