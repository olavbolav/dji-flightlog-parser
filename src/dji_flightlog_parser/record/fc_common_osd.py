"""FlightControllerCommonOSD record parser (type 63).

Contains sub-typed data; the only sub-type seen (0, BatteryOSD, 10 bytes,
about 1 Hz) gives the FC's remaining flight time and go-home/landing
estimates. Field order matches DUML FlyC 0x51 "Battery Status": useful_time,
go_home_time, land_time, go_home_battery, land_battery.

Record bytes (sub-type 0): u16 sub_type @0, u16 remain_fly_time @2 (s),
u16 need_go_home_time @4 (s, 65535 = not available), u16 need_land_time @6 (s),
u8 go_home_capacity @8 (%), u8 land_capacity @9 (%).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

# Sentinel for "not available" in need_go_home_time. Checked on 46 logs with
# type 63 (46,636 records): 339 records in 30 logs; go_home_capacity is 0 in
# exactly those records. remain_fly_time and need_land_time never use it.
TIME_NOT_AVAILABLE = 0xFFFF


@dataclass
class FCCommonOSD:
    sub_type: int = 0
    remain_fly_time: int = 0
    # Estimated time to fly home, in seconds; None when not available (65535).
    # Range 0-336 s. Scales with distance to home on M400, most M4TD and M30
    # logs; in 5/14 M4TD logs it only tracks go_home_capacity, and it is
    # unreliable on Mini 5 Pro, Neo and Neo 2.
    need_go_home_time: Optional[int] = None
    # Estimated time to land from the current height, in seconds. Linear in
    # height (r 0.91-1.00) with a ~29-30 s floor; 0 only before take-off.
    need_land_time: Optional[int] = None
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
                go_home_time = struct.unpack_from("<H", payload, 2)[0]
                c.need_go_home_time = None if go_home_time == TIME_NOT_AVAILABLE else go_home_time
                c.need_land_time = struct.unpack_from("<H", payload, 4)[0]
                c.go_home_capacity = payload[6]
                c.land_capacity = payload[7]

        return c
