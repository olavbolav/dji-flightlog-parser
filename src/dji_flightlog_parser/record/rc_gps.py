"""RC GPS position record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class RCGPS:
    hour: int = 0
    minute: int = 0
    second: int = 0
    year: int = 0
    month: int = 0
    day: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    speed_x: float = 0.0
    speed_y: float = 0.0
    gps_num: int = 0
    accuracy: float = 0.0
    valid_data: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> RCGPS:
        r = cls()
        if len(data) < 20:
            return r
        offset = 0
        r.hour = data[offset]; offset += 1
        r.minute = data[offset]; offset += 1
        r.second = data[offset]; offset += 1
        r.year = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.month = data[offset]; offset += 1
        r.day = data[offset]; offset += 1
        r.latitude = struct.unpack_from("<i", data, offset)[0] / 1e7; offset += 4
        r.longitude = struct.unpack_from("<i", data, offset)[0] / 1e7; offset += 4
        r.speed_x = struct.unpack_from("<i", data, offset)[0] / 100.0; offset += 4
        r.speed_y = struct.unpack_from("<i", data, offset)[0] / 100.0; offset += 4
        if offset < len(data):
            r.gps_num = data[offset]; offset += 1
        if offset + 4 <= len(data):
            r.accuracy = struct.unpack_from("<f", data, offset)[0]; offset += 4
        if offset + 2 <= len(data):
            r.valid_data = struct.unpack_from("<H", data, offset)[0]
        return r
