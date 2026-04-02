"""Recovery record parser - contains device serial numbers and metadata."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone

from ..layout.details import ProductType, Platform, _parse_battery_sn


def _read_string(data: bytes, offset: int, length: int) -> str:
    raw = data[offset:offset + length]
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


@dataclass
class Recover:
    product_type: ProductType = ProductType.NONE
    app_platform: Platform = Platform.Unknown
    app_version: str = ""
    aircraft_sn: str = ""
    aircraft_name: str = ""
    timestamp: datetime = None  # type: ignore
    camera_sn: str = ""
    rc_sn: str = ""
    battery_sn: str = ""

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Recover:
        r = cls()
        if len(data) < 3:
            return r

        offset = 0
        r.product_type = ProductType.from_value(data[offset])
        offset += 1

        r.app_platform = Platform.from_value(data[offset])
        offset += 1

        if offset + 3 <= len(data):
            r.app_version = f"{data[offset]}.{data[offset+1]}.{data[offset+2]}"
            offset += 3

        sn_len = 10 if version <= 5 else 16
        name_len = 32

        if offset + sn_len <= len(data):
            r.aircraft_sn = _read_string(data, offset, sn_len)
            offset += sn_len

        if offset + name_len <= len(data):
            r.aircraft_name = _read_string(data, offset, name_len)
            offset += name_len

        if offset + 8 <= len(data):
            ts_ms = struct.unpack_from("<q", data, offset)[0]
            if ts_ms > 0:
                r.timestamp = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            offset += 8

        if offset + sn_len <= len(data):
            r.camera_sn = _read_string(data, offset, sn_len)
            offset += sn_len

        if offset + sn_len <= len(data):
            r.rc_sn = _read_string(data, offset, sn_len)
            offset += sn_len

        if offset + sn_len <= len(data):
            battery_buf = data[offset:offset + sn_len]
            r.battery_sn = _parse_battery_sn(r.product_type, battery_buf)
            offset += sn_len

        return r
