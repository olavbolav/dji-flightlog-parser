"""GSMissionStatus record parser (type 32, feature point Waypoint).

Legacy ground-station / MSDK v4 navigation-mission status (Waypoint 1.0,
Hotpoint, Follow-me, course/home lock). It mirrors the 7-byte FlyC DUML
0x03:0x88 "Push Navigation Status Info" packet.

What the data shows (v14, M30/M300/M350, ~162k records in 26 logs): the
record is 7 bytes at ~10 Hz and every byte has always been 0x00, including
during DJI Pilot 2 waypoint (wayline) missions. Only the record-level facts
are verified. The field layout below comes from dji-firmware-tools and the
DJI OSDK and cannot be checked against constant data, so everything except
``raw`` is per reference and unverified. Use OSD flight_mode/flight_action,
not this record, to detect waypoint missions.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

RECORD_LENGTH = 7


class GSMissionType(IntEnum):
    """Mission type per the FlyC 0x88 dissector and OSDK (unverified)."""
    NONE = 0
    Waypoint = 1
    Hotpoint = 2
    FollowMe = 3
    CourseHomeLock = 4
    TBD = 5
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> GSMissionType:
        return cls.UNKNOWN


@dataclass
class GSMissionStatus:
    raw: bytes = b""
    raw_hex: str = ""  # same bytes as hex, so JSON exports keep them
    has_content: bool = False  # any non-zero byte; never observed so far
    mission_type: GSMissionType = GSMissionType.NONE
    mission_data: bytes = b""  # bytes 1-5, a per-mission-type union
    trailing_flag: int = 0  # byte 6 ("is_tracking_enabled" in flyc.lua)

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """True for the only layout seen in real logs (v13+, 7 bytes).

        An empty plaintext means decryption failed and must not become an
        all-zero record, which would look exactly like a real one.
        """
        return version >= 13 and len(data) == RECORD_LENGTH

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> GSMissionStatus:
        g = cls()
        if len(data) < 1:
            return g

        g.raw = bytes(data[:RECORD_LENGTH])
        g.raw_hex = g.raw.hex()
        g.has_content = any(g.raw)
        g.mission_type = GSMissionType(data[0])
        if len(data) >= 6:
            g.mission_data = bytes(data[1:6])
        if len(data) >= 7:
            g.trailing_flag = data[6]
        return g

    # Experimental per-branch views. Never observed with real data.

    @property
    def wp_target_index(self) -> Optional[int]:
        """Target waypoint index (Waypoint 1.0 branch only)."""
        if self.mission_type != GSMissionType.Waypoint or len(self.mission_data) < 1:
            return None
        return self.mission_data[0]

    @property
    def hp_status(self) -> Optional[int]:
        """Hotpoint status per OSDK: 0 not running, 1 running, 2 paused."""
        if self.mission_type != GSMissionType.Hotpoint or len(self.mission_data) < 1:
            return None
        return self.mission_data[0]

    @property
    def hp_radius(self) -> Optional[int]:
        """Hotpoint radius, u16 LE (OSDK says cm; unverified)."""
        if self.mission_type != GSMissionType.Hotpoint or len(self.mission_data) < 3:
            return None
        return struct.unpack_from("<H", self.mission_data, 1)[0]

    @property
    def hp_reason(self) -> Optional[int]:
        """Hotpoint reason/error code (undocumented values)."""
        if self.mission_type != GSMissionType.Hotpoint or len(self.mission_data) < 4:
            return None
        return self.mission_data[3]

    @property
    def hp_rate_raw(self) -> Optional[int]:
        """Hotpoint speed or yaw rate, raw (unit unknown)."""
        if self.mission_type != GSMissionType.Hotpoint or len(self.mission_data) < 5:
            return None
        return self.mission_data[4]
