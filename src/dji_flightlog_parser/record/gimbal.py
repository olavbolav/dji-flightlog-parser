"""Gimbal state record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class GimbalMode(IntEnum):
    Free = 0
    FPV = 1
    YawFollow = 2
    UNKNOWN = 3

    @classmethod
    def _missing_(cls, value: object) -> GimbalMode:
        return cls.UNKNOWN


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class Gimbal:
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    mode: GimbalMode = GimbalMode.Free
    roll_adjust: float = 0.0
    yaw_angle: float = 0.0
    is_pitch_at_limit: bool = False
    is_roll_at_limit: bool = False
    is_yaw_at_limit: bool = False
    is_auto_calibration: bool = False
    is_stuck: bool = False
    version: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Gimbal:
        g = cls()
        if len(data) < 6:
            return g

        g.pitch = struct.unpack_from("<h", data, 0)[0] / 10.0
        g.roll = struct.unpack_from("<h", data, 2)[0] / 10.0
        g.yaw = struct.unpack_from("<h", data, 4)[0] / 10.0

        if len(data) > 6:
            bp1 = data[6]
            g.mode = GimbalMode(_sub_byte(bp1, 0xC0))
            # 0x20 = reset flag (not stored in frame)

        if len(data) > 7:
            g.roll_adjust = struct.unpack_from("<b", data, 7)[0] / 10.0

        if len(data) > 9:
            g.yaw_angle = struct.unpack_from("<h", data, 8)[0] / 10.0

        if len(data) > 10:
            bp2 = data[10]
            g.is_pitch_at_limit = bool(bp2 & 0x01)
            g.is_roll_at_limit = bool(bp2 & 0x02)
            g.is_yaw_at_limit = bool(bp2 & 0x04)
            g.is_auto_calibration = bool(bp2 & 0x08)
            g.is_stuck = bool(bp2 & 0x20)

        if version >= 2 and len(data) > 11:
            bp3 = data[11]
            g.version = _sub_byte(bp3, 0x0F)

        return g
