"""Remote controller input record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class FlightModeSwitch(IntEnum):
    P = 0
    S = 1
    A = 2
    F = 3
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> FlightModeSwitch:
        return cls.UNKNOWN


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class RC:
    aileron: int = 0
    elevator: int = 0
    throttle: int = 0
    rudder: int = 0
    gimbal: int = 0
    wheel: int = 0
    flight_mode_switch: FlightModeSwitch = FlightModeSwitch.P
    go_home_button: bool = False
    record_button: bool = False
    shutter_button: bool = False
    playback_button: bool = False
    bandwidth: int = 0
    gimbal_control_enable: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14, product_type: int = 0) -> RC:
        r = cls()
        if len(data) < 10:
            return r

        r.aileron = struct.unpack_from("<H", data, 0)[0]
        r.elevator = struct.unpack_from("<H", data, 2)[0]
        r.throttle = struct.unpack_from("<H", data, 4)[0]
        r.rudder = struct.unpack_from("<H", data, 6)[0]
        r.gimbal = struct.unpack_from("<H", data, 8)[0]

        if len(data) > 10:
            r.wheel = data[10]

        if len(data) > 11:
            bp = data[11]
            r.flight_mode_switch = FlightModeSwitch(_sub_byte(bp, 0x30))

        if len(data) > 12:
            bp2 = data[12]
            r.go_home_button = bool(bp2 & 0x08)
            r.record_button = bool(bp2 & 0x20)
            r.shutter_button = bool(bp2 & 0x40)
            r.playback_button = bool(bp2 & 0x80)

        offset = 13
        if version >= 6 and len(data) > offset:
            r.bandwidth = data[offset]
            offset += 1
        if version >= 7 and len(data) > offset:
            r.gimbal_control_enable = data[offset]

        return r
