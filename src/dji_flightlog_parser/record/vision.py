"""VisionGroup record parser (type 17) - obstacle avoidance state.

Record layout: one or more TLV blocks, each
``[u8 block type][00 00 00][u8 n][n payload bytes][0xFE]``.
Checked on 429 records in 44 of 74 logs (all 9 families): every record splits
into such blocks with nothing left over, except that v12 records carry one
extra trailing byte after the last block (a decoder artefact, not data).
Records are written only when the content changes.

Block types seen in the corpus: 8 (FC avoidance status, in every record) and
10 (n=15, two Mavic Mini records, meaning unknown, not decoded). The radar
sector blocks 0-5 never occur in the corpus, so their payload layout is
unverified.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


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
BLOCK_HEADER_SIZE = 5
BLOCK_AVOID_STATUS = 8

# Block 8 payload: FC avoidance status bitfield, little endian from payload
# byte 0 (2 bytes on Mavic Mini, 3 on M30/M300/M350/M400/M4TD/Mini 5 Pro/Neo,
# 4 on Neo 2). Bit names follow the DUML FlyC "Vis Avoidance Param" push
# (0x03/0x53) in dji-firmware-tools flyc.lua; the upstream Rust parser has no
# VisionGroup record.
#
# 0x0002 user_avoid_enable: the pilot's obstacle avoidance switch. Constant in
#   every log: set on M30/M300/M350/M400/M4TD/Mini 5 Pro, clear on Neo, Neo 2
#   and Mavic Mini. Agrees with MCParams byte 1 bit 0x04 (upstream
#   ``user_avoid_enabled``) in 44/44 logs that have both records.
AVOID_USER_ENABLE = 0x0002
# 0x0800 vert_low_limit_work_flag: downward sensing sees the ground, so the
#   vertical low limit (descent protection) is working. 357 transitions; set
#   at take-off, cleared on climb-out at 7-19 m, set again on final descent.
#   Airborne OSD altitude median while set vs clear: M400 12.3 vs 128.6 m,
#   M350 1.4 vs 99.3 m, M300 2.9 vs 85.2 m.
AVOID_VERT_LOW_LIMIT = 0x0800
# Bits not exposed as named flags (they stay readable in ``avoidance_flags``):
# 0x0001 avoid_obstacle_enable (constant per log, matches MCParams byte 1 bit
#   0x02 except in one v12 log), 0x0010 gohome_avoid_enable (constant),
# 0x0008 emergency_brake_work_flag (15 short pulses, 0.1-6 s, nearly all at
#   zero ground speed around take-off, ConfirmLanding or a flight-mode change;
#   no evidence of braking for obstacles), 0x0020 avoid_ground_force_landing
#   (once, M300, right after ConfirmLanding was confirmed at 0.5 m), byte 2
#   bits 0x04/0x20/0x40 (M300/M350 only, with 0x0008; unknown).
#
# Removed flags (no support in upstream or the corpus):
# - is_landing_confirmation_needed (was 0x0020): never set during any of the
#   43 ConfirmLanding (OSD flight mode 33) episodes in logs with this record.
# - is_ascent_limited (was 0x2000) and is_avoid_active_obstacle (was 0x0400,
#   "overshot act" in flyc.lua): never set in any record.
# - is_braking (was block 9 byte 0 bit 0x01): block 9 never occurs.


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
    """Parsed VisionGroup record (obstacle avoidance state)."""
    collision_avoidance_enabled: bool = False
    vert_low_limit_active: bool = False
    # Raw block-8 bitfield (little endian), None when the record has no block 8
    avoidance_flags: Optional[int] = None
    detections: dict[int, VisionDetectionState] = field(default_factory=dict)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> VisionGroup:
        v = cls()
        for block_type, payload in iter_blocks(data):
            if block_type <= 5:
                det = _parse_radar_detection(block_type, payload)
                if det is not None:
                    v.detections[block_type] = det
            elif block_type == BLOCK_AVOID_STATUS:
                _parse_mc_avoid_status(v, payload)
        return v


def iter_blocks(data: bytes) -> list[tuple[int, bytes]]:
    """Split a VisionGroup record into (block type, payload) pairs.

    Stops at the first block whose header is malformed or whose payload does
    not fit, and after a block that is not followed by the 0xFE end marker.
    Fewer than five remaining bytes (the v12 trailing byte) end the scan.
    """
    blocks: list[tuple[int, bytes]] = []
    offset = 0
    while offset + BLOCK_HEADER_SIZE <= len(data):
        if data[offset + 1:offset + 4] != b"\x00\x00\x00":
            break
        block_type = data[offset]
        n = data[offset + 4]
        start = offset + BLOCK_HEADER_SIZE
        if start + n > len(data):
            break
        blocks.append((block_type, bytes(data[start:start + n])))
        offset = start + n
        if offset < len(data) and data[offset] == VISION_GROUP_END:
            offset += 1
        else:
            break
    return blocks


def _parse_radar_detection(sensor_pos: int, data: bytes) -> VisionDetectionState | None:
    # Layout unverified: no block 0-5 occurs in the corpus.
    if len(data) < 3:
        return None

    det = VisionDetectionState()
    det.position = VisionSensorPosition(sensor_pos)

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
    if len(data) < 1:
        return
    flags = int.from_bytes(data[:4], "little")
    v.avoidance_flags = flags
    v.collision_avoidance_enabled = bool(flags & AVOID_USER_ENABLE)
    v.vert_low_limit_active = bool(flags & AVOID_VERT_LOW_LIMIT)
