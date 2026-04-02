"""Vision/perception sensor data record parser (extended)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class Vision:
    """Extended record type: obstacle avoidance sensor distances.
    The exact binary format varies by drone model; this extracts
    what's commonly available.
    """
    raw_data: bytes = b""
    front_distance: float = 0.0
    back_distance: float = 0.0
    right_distance: float = 0.0
    left_distance: float = 0.0
    up_distance: float = 0.0
    down_distance: float = 0.0
    avoidance_active: bool = False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Vision:
        v = cls(raw_data=data)
        if len(data) >= 24:
            v.front_distance = struct.unpack_from("<f", data, 0)[0]
            v.back_distance = struct.unpack_from("<f", data, 4)[0]
            v.right_distance = struct.unpack_from("<f", data, 8)[0]
            v.left_distance = struct.unpack_from("<f", data, 12)[0]
            v.up_distance = struct.unpack_from("<f", data, 16)[0]
            v.down_distance = struct.unpack_from("<f", data, 20)[0]
        if len(data) >= 25:
            v.avoidance_active = bool(data[24])
        return v
