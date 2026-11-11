"""KeyValueSnapshot record parser (type 253 / 0xFD, feature point DJIFlyCustom).

A generic key/value container written by the app on v14 logs. Record 253
holds snapshots sent when the app connects to the aircraft (and again after
some link gaps). Its sibling record 254 holds values re-sent on change (mostly
wind, which OSD already carries) and is decrypted but not emitted.

Layout (checked on 157,096 records of types 253/254 in 70 v14 logs: the
plaintext length equals header + payload_len in every record):

* u16 LE module id at 0, u16 LE key id at 2;
* u16 LE payload length at 4;
* u8 at 6, always 0;
* u8 flags at 7: 0x80 means a u64 LE Unix epoch-millisecond timestamp follows
  at 8-15 (set on every 253 record in the corpus);
* the payload, a protobuf message, starts at 8 (no timestamp) or 16.

Only two module/key pairs occur in 253 records, and only these are decoded:

* module 7 key 1: component serial list, protobuf length-delimited strings
  keyed by field number. Field 1 = camera (same as details camera_sn),
  field 6 = accessory (M4TD, likely the AL1 spotlight), fields 7 and 8 =
  battery slots 1 and 2 (slot order: one physical battery can be in either
  field across logs). Field 2 is a serial of unknown role (2 logs). Empty
  on Mini 5 Pro, Neo and Neo 2.
* module 5 key 1: protobuf field 1 fixed64 = total accumulated flight time in
  seconds (f64). It steps up by the current flight's time when re-sent
  mid-log; whether the counter belongs to the aircraft, the RC or the app is
  unknown. Enterprise aircraft only (M30, M300, M350, M400, M4TD).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..decoder.protobuf import (
    FIXED64,
    LENGTH_DELIMITED,
    ProtobufDecodeError,
    WireField,
    as_double,
    iter_fields,
)

HEADER_SIZE = 8
TIMESTAMP_SIZE = 8
FLAG_TIMESTAMP = 0x80

MODULE_FLIGHT_STATS = 5
MODULE_COMPONENT_SERIALS = 7
KEY_SNAPSHOT = 1


def _walk(payload: bytes) -> tuple[list[WireField], bool]:
    """Collect top-level protobuf fields, stopping at the first malformed one.

    Returns (fields_read_so_far, complete). Never raises.
    """
    fields: list[WireField] = []
    try:
        for f in iter_fields(payload):
            fields.append(f)
    except ProtobufDecodeError:
        return fields, False
    return fields, True


def _decode_serial(value: bytes) -> Optional[str]:
    """Decode a serial string; None unless it is printable ASCII."""
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError:
        return None
    text = text.rstrip("\x00")
    if not text or not text.isprintable():
        return None
    return text


def _decode_timestamp(ts_ms: int) -> Optional[datetime]:
    if ts_ms <= 0:
        return None
    try:
        secs, ms = divmod(ts_ms, 1000)
        return datetime.fromtimestamp(secs, tz=timezone.utc).replace(microsecond=ms * 1000)
    except (OverflowError, OSError, ValueError):
        return None


@dataclass
class KeyValueSnapshot:
    module: int = 0
    key: int = 0
    timestamp: Optional[datetime] = None  # app wall clock (UTC) when the snapshot was written
    # module 7 key 1: protobuf field number -> serial string
    # (1 camera, 2 unknown, 6 accessory, 7 battery slot 1, 8 battery slot 2)
    serials: dict[int, str] = field(default_factory=dict)
    # module 5 key 1: total accumulated flight time, seconds
    total_flight_time: Optional[float] = None

    @staticmethod
    def _payload_bounds(data: bytes) -> Optional[tuple[int, int]]:
        """(start, end) of the protobuf payload, or None if the header is invalid."""
        if len(data) < HEADER_SIZE:
            return None
        payload_len = struct.unpack_from("<H", data, 4)[0]
        start = HEADER_SIZE + (TIMESTAMP_SIZE if data[7] & FLAG_TIMESTAMP else 0)
        return start, start + payload_len

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """True for a well-formed snapshot: consistent header and a complete protobuf.

        AES ciphertext passed through without a key, or a failed decryption,
        fails this and stays an UnknownRecord.
        """
        if version < 14:
            return False
        bounds = KeyValueSnapshot._payload_bounds(data)
        if bounds is None or data[6] != 0 or data[7] & ~FLAG_TIMESTAMP:
            return False
        start, end = bounds
        if end != len(data):
            return False
        return _walk(data[start:end])[1]

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> KeyValueSnapshot:
        s = cls()
        bounds = cls._payload_bounds(data)
        if bounds is None:
            return s

        s.module, s.key = struct.unpack_from("<HH", data, 0)
        if data[7] & FLAG_TIMESTAMP and len(data) >= HEADER_SIZE + TIMESTAMP_SIZE:
            s.timestamp = _decode_timestamp(struct.unpack_from("<Q", data, HEADER_SIZE)[0])

        start, end = bounds
        fields, _ = _walk(data[start:min(end, len(data))])

        if s.key == KEY_SNAPSHOT and s.module == MODULE_COMPONENT_SERIALS:
            for f in fields:
                if f.wire_type == LENGTH_DELIMITED and f.number not in s.serials:
                    serial = _decode_serial(f.value)
                    if serial is not None:
                        s.serials[f.number] = serial
        elif s.key == KEY_SNAPSHOT and s.module == MODULE_FLIGHT_STATS:
            for f in fields:
                if f.number == 1 and f.wire_type == FIXED64:
                    value = as_double(f.value)
                    if math.isfinite(value) and value >= 0:
                        s.total_flight_time = value
                    break
        return s
