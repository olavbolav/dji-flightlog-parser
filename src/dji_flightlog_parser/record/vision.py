"""VisionGroup record parser (type 17) - obstacle detection and avoidance state."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum


class VisionSensorPosition(IntEnum):
    Nose = 0
    Tail = 1
    Right = 2
    Left = 3
    Top = 4
    Down = 5
    Unknown = 255

    @classmethod
    def _missing_(cls, value: object) -> VisionSensorPosition:
        return cls.Unknown


class ObstacleWarningLevel(IntEnum):
    Invalid = 0
    Safe = 1
    Warning = 2
    Danger = 3

    @classmethod
    def _missing_(cls, value: object) -> ObstacleWarningLevel:
        return cls.Invalid


VISION_GROUP_END = 0xFE


@dataclass
class ObstacleDetectionSector:
    distance_cm: int = 0
    warning_level: ObstacleWarningLevel = ObstacleWarningLevel.Invalid


@dataclass
class VisionDetectionState:
    position: VisionSensorPosition = VisionSensorPosition.Unknown
    is_sensor_used: bool = False
    obstacle_distance_m: float = 0.0
    sectors: list[ObstacleDetectionSector] = field(default_factory=list)


@dataclass
class VisionGroup:
    """Parsed VisionGroup record containing obstacle detection from multiple sensors."""
    collision_avoidance_enabled: bool = False
    is_braking: bool = False
    is_ascent_limited: bool = False
    is_avoid_active_obstacle: bool = False
    is_landing_confirmation_needed: bool = False
    detections: dict[int, VisionDetectionState] = field(default_factory=dict)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> VisionGroup:
        v = cls()
        if len(data) < 2:
            return v

        offset = 0
        while offset < len(data):
            if offset + 2 > len(data):
                break

            block_type = data[offset]
            block_size = data[offset + 1]
            offset += 2

            if block_size == 0 or offset + block_size > len(data):
                break

            block_data = data[offset:offset + block_size]

            if block_type <= 5:
                det = _parse_radar_detection(block_type, block_data)
                if det is not None:
                    v.detections[block_type] = det
            elif block_type == 8:
                _parse_mc_avoid_status(v, block_data)
            elif block_type == 9:
                _parse_guidance_detect(v, block_data)

            offset += block_size

            if offset < len(data) and data[offset] == VISION_GROUP_END:
                offset += 1

        return v


def _parse_radar_detection(sensor_pos: int, data: bytes) -> VisionDetectionState | None:
    if len(data) < 3:
        return None

    det = VisionDetectionState()
    det.position = VisionSensorPosition(sensor_pos)

    direction = data[0]
    count = data[1]

    if count == 0:
        return det

    det.is_sensor_used = True
    offset = 2
    for _ in range(count):
        if offset + 4 > len(data):
            break
        distance_cm = struct.unpack_from("<H", data, offset)[0]
        warning = data[offset + 2]
        det.sectors.append(ObstacleDetectionSector(
            distance_cm=distance_cm,
            warning_level=ObstacleWarningLevel(warning & 0x0F),
        ))
        if distance_cm > 0:
            dist_m = distance_cm / 100.0
            if det.obstacle_distance_m == 0.0 or dist_m < det.obstacle_distance_m:
                det.obstacle_distance_m = dist_m
        offset += 4

    all_far = all(s.distance_cm > 1500 for s in det.sectors)
    if all_far:
        det.is_sensor_used = False
        det.sectors.clear()

    return det


def _parse_mc_avoid_status(v: VisionGroup, data: bytes) -> None:
    if len(data) < 2:
        return
    flags = struct.unpack_from("<H", data, 0)[0]
    v.collision_avoidance_enabled = bool(flags & 0x0002)
    v.is_landing_confirmation_needed = bool(flags & 0x0020)
    v.is_ascent_limited = bool(flags & 0x2000)
    v.is_avoid_active_obstacle = bool(flags & 0x0400)


def _parse_guidance_detect(v: VisionGroup, data: bytes) -> None:
    if len(data) < 1:
        return
    flags = data[0]
    v.is_braking = bool(flags & 0x01)
