"""Component serial number record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class ComponentType(IntEnum):
    FlightController = 0
    Gimbal = 1
    RightCamera = 2
    LeftCamera = 3
    RemoteController = 4
    Battery = 5
    RTK = 6
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> ComponentType:
        return cls.UNKNOWN


@dataclass
class ComponentSerial:
    component_type: ComponentType = ComponentType.UNKNOWN
    serial: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> ComponentSerial:
        c = cls()
        if len(data) < 3:
            return c

        raw_type = struct.unpack_from("<H", data, 0)[0]
        c.component_type = ComponentType(raw_type)

        length = data[2]
        if len(data) >= 3 + length:
            c.serial = data[3:3 + length].split(b"\x00", 1)[0].decode("utf-8", errors="replace")

        return c
