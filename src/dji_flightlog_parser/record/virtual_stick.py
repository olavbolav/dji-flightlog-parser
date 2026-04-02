"""Virtual stick input record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


class CoordinateMode(IntEnum):
    Ground = 0
    Body = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> CoordinateMode:
        return cls.UNKNOWN


class YawMode(IntEnum):
    Angle = 0
    AngleRate = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> YawMode:
        return cls.UNKNOWN


class VerticalMode(IntEnum):
    Velocity = 0
    Position = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> VerticalMode:
        return cls.UNKNOWN


class RollPitchMode(IntEnum):
    Angle = 0
    Velocity = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> RollPitchMode:
        return cls.UNKNOWN


@dataclass
class VirtualStick:
    coordinate_mode: CoordinateMode = CoordinateMode.Ground
    yaw_mode: YawMode = YawMode.Angle
    vertical_mode: VerticalMode = VerticalMode.Velocity
    roll_pitch_mode: RollPitchMode = RollPitchMode.Angle
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    throttle: float = 0.0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> VirtualStick:
        v = cls()
        if len(data) < 1:
            return v
        bp = data[0]
        v.coordinate_mode = CoordinateMode(_sub_byte(bp, 0x06))
        v.yaw_mode = YawMode(_sub_byte(bp, 0x08))
        v.vertical_mode = VerticalMode(_sub_byte(bp, 0x30))
        v.roll_pitch_mode = RollPitchMode(_sub_byte(bp, 0xC0))

        if len(data) >= 17:
            v.roll = struct.unpack_from("<f", data, 1)[0]
            v.pitch = struct.unpack_from("<f", data, 5)[0]
            v.yaw = struct.unpack_from("<f", data, 9)[0]
            v.throttle = struct.unpack_from("<f", data, 13)[0]

        return v
