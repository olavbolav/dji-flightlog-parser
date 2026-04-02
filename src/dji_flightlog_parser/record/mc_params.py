"""MC (flight controller) parameters record parser."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FailSafe(IntEnum):
    GoHome = 0
    Landing = 1
    Hover = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> FailSafe:
        return cls.UNKNOWN


@dataclass
class MCParams:
    fail_safe: FailSafe = FailSafe.GoHome
    e_landing: bool = False
    go_home_altitude: bool = False
    dynamic_home_point: bool = False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> MCParams:
        m = cls()
        if len(data) < 1:
            return m
        m.fail_safe = FailSafe(data[0])
        if len(data) > 1:
            bp = data[1]
            m.e_landing = bool(bp & 0x01)
            m.go_home_altitude = bool(bp & 0x02)
            m.dynamic_home_point = bool(bp & 0x04)
        return m
