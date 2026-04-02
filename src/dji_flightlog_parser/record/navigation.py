"""Navigation/waypoint data record parser (extended)."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class Navigation:
    """Extended record type: waypoint mission progress."""
    raw_data: bytes = b""
    waypoint_index: int = 0
    mission_id: int = 0
    running: bool = False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Navigation:
        n = cls(raw_data=data)
        if len(data) >= 4:
            n.waypoint_index = struct.unpack_from("<H", data, 0)[0]
            n.mission_id = struct.unpack_from("<H", data, 2)[0]
        if len(data) >= 5:
            n.running = bool(data[4])
        return n
