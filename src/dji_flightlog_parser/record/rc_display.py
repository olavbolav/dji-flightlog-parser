"""RC display field record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class RCDisplayField:
    aileron: int = 0
    elevator: int = 0
    throttle: int = 0
    rudder: int = 0
    gimbal: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> RCDisplayField:
        r = cls()
        # 7 bytes of unknown data, then 5 x u16 stick values
        offset = 7
        if offset + 10 > len(data):
            return r
        r.aileron = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.elevator = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.throttle = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.rudder = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.gimbal = struct.unpack_from("<H", data, offset)[0]
        return r
