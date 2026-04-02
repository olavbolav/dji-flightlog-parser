"""Home point record parser."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import IntEnum


class CompassCalibrationState(IntEnum):
    NONE = 0
    Step1 = 1
    Step2 = 2
    Failed = 3
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> CompassCalibrationState:
        return cls.UNKNOWN


class GoHomeMode(IntEnum):
    Direct = 0
    Planned = 1
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> GoHomeMode:
        return cls.UNKNOWN


class IOCMode(IntEnum):
    CourseLock = 1
    HomeLock = 2
    HotpointSurround = 3
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> IOCMode:
        return cls.UNKNOWN


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class Home:
    longitude: float = 0.0
    latitude: float = 0.0
    altitude: float = 0.0
    is_home_record: bool = False
    go_home_mode: GoHomeMode = GoHomeMode.Direct
    aircraft_head_direction: int = 0
    is_dynamic_home_point_enabled: bool = False
    is_near_distance_limit: bool = False
    is_near_height_limit: bool = False
    is_multiple_mode_open: bool = False
    is_beginner_mode: bool = False
    is_ioc_open: bool = False
    ioc_mode: IOCMode = IOCMode.CourseLock
    is_compass_adjust: bool = False
    compass_state: CompassCalibrationState = CompassCalibrationState.NONE
    go_home_height: int = 0
    ioc_course_lock_angle: int = 0
    flight_record_sd_state: int = 0
    record_sd_capacity_percent: int = 0
    record_sd_left_time: int = 0
    current_flight_record_index: int = 0
    max_allowed_height: float = 0.0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Home:
        h = cls()
        if len(data) < 20:
            return h

        h.longitude = math.degrees(struct.unpack_from("<d", data, 0)[0])
        h.latitude = math.degrees(struct.unpack_from("<d", data, 8)[0])
        h.altitude = struct.unpack_from("<f", data, 16)[0] / 10.0

        if len(data) > 20:
            bp1 = data[20]
            h.is_home_record = bool(bp1 & 0x01)
            h.go_home_mode = GoHomeMode(_sub_byte(bp1, 0x02))
            h.aircraft_head_direction = _sub_byte(bp1, 0x04)
            h.is_dynamic_home_point_enabled = bool(bp1 & 0x08)
            h.is_near_distance_limit = bool(bp1 & 0x10)
            h.is_near_height_limit = bool(bp1 & 0x20)
            h.is_multiple_mode_open = bool(bp1 & 0x40)
            h.is_beginner_mode = bool(bp1 & 0x80)

        if len(data) > 21:
            bp2 = data[21]
            h.compass_state = CompassCalibrationState(_sub_byte(bp2, 0x03))
            h.is_compass_adjust = bool(bp2 & 0x04)
            h.is_ioc_open = bool(bp2 & 0x08)
            h.ioc_mode = IOCMode(_sub_byte(bp2, 0xE0))

        if len(data) > 23:
            h.go_home_height = struct.unpack_from("<H", data, 22)[0]
        if len(data) > 25:
            h.ioc_course_lock_angle = struct.unpack_from("<h", data, 24)[0]

        if len(data) > 26:
            h.flight_record_sd_state = data[26]
        if len(data) > 27:
            h.record_sd_capacity_percent = data[27]
        if len(data) > 29:
            h.record_sd_left_time = struct.unpack_from("<H", data, 28)[0]
        if len(data) > 31:
            h.current_flight_record_index = struct.unpack_from("<H", data, 30)[0]

        if version >= 8 and len(data) > 36:
            # 5 unknown bytes at offset 32
            if len(data) > 40:
                h.max_allowed_height = struct.unpack_from("<f", data, 37)[0]

        return h
