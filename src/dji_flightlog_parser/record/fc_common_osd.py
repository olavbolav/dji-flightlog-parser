"""FlightControllerCommonOSD record parser (type 63).

Contains sub-typed data; currently known sub-type is BatteryOSD
which provides remaining flight time and go-home/landing capacity.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class FCCommonOSD:
    sub_type: int = 0
    remain_fly_time: int = 0
    need_go_home_time: int = 0
    need_land_time: int = 0
    go_home_capacity: int = 0
    land_capacity: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> FCCommonOSD:
        c = cls()
        if len(data) < 2:
            return c

        c.sub_type = struct.unpack_from("<H", data, 0)[0]
        payload = data[2:]

        if c.sub_type == 0:
            if len(payload) >= 8:
                c.remain_fly_time = struct.unpack_from("<H", payload, 0)[0]
                c.need_go_home_time = struct.unpack_from("<H", payload, 2)[0]
                c.need_land_time = struct.unpack_from("<H", payload, 4)[0]
                c.go_home_capacity = payload[6]
                c.land_capacity = payload[7]

        return c
