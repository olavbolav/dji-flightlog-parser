"""Minimal schema-less protobuf wire-format reader.

DJI writes some record bodies (e.g. GOBusinessData, type 54) as protobuf
messages without publishing the schema. This reader walks the wire format
so typed record parsers can pick fields by number without generated classes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, Union

VARINT = 0
FIXED64 = 1
LENGTH_DELIMITED = 2
FIXED32 = 5

WireValue = Union[int, bytes]


class ProtobufDecodeError(ValueError):
    """Raised when bytes are not a well-formed protobuf message."""


@dataclass(frozen=True)
class WireField:
    number: int
    wire_type: int
    value: WireValue  # int for varint; raw bytes for fixed64, fixed32 and length-delimited


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ProtobufDecodeError("truncated varint")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift >= 64:
            raise ProtobufDecodeError("varint too long")


def iter_fields(data: bytes) -> Iterator[WireField]:
    """Yield the top-level fields of a protobuf message in wire order.

    Raises ProtobufDecodeError on malformed input (unknown wire type,
    truncated value, field number 0).
    """
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        number, wire_type = key >> 3, key & 0x07
        if number == 0:
            raise ProtobufDecodeError("field number 0")
        if wire_type == VARINT:
            value, pos = _read_varint(data, pos)
        elif wire_type == FIXED64:
            if pos + 8 > len(data):
                raise ProtobufDecodeError("truncated fixed64")
            value = bytes(data[pos:pos + 8])
            pos += 8
        elif wire_type == LENGTH_DELIMITED:
            length, pos = _read_varint(data, pos)
            if pos + length > len(data):
                raise ProtobufDecodeError("truncated length-delimited field")
            value = bytes(data[pos:pos + length])
            pos += length
        elif wire_type == FIXED32:
            if pos + 4 > len(data):
                raise ProtobufDecodeError("truncated fixed32")
            value = bytes(data[pos:pos + 4])
            pos += 4
        else:
            raise ProtobufDecodeError(f"unsupported wire type {wire_type}")
        yield WireField(number, wire_type, value)


def parse_message(data: bytes) -> list[WireField]:
    """Parse all top-level fields; raises ProtobufDecodeError if malformed."""
    return list(iter_fields(data))


def is_message(data: bytes) -> bool:
    """True if ``data`` parses completely as a protobuf message."""
    try:
        for _ in iter_fields(data):
            pass
        return True
    except ProtobufDecodeError:
        return False


def decode_text(value: bytes) -> str:
    """Decode a length-delimited string field, replacing invalid UTF-8."""
    return value.decode("utf-8", errors="replace")


def as_double(value: bytes) -> float:
    """Interpret a fixed64 field value as a little-endian IEEE double."""
    return struct.unpack("<d", value)[0]


def as_float(value: bytes) -> float:
    """Interpret a fixed32 field value as a little-endian IEEE float."""
    return struct.unpack("<f", value)[0]
