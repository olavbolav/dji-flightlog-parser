"""App message records (tips, warnings, GPS) parsers."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass
class AppTip:
    message: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, length: int = 0) -> AppTip:
        msg = data[:length].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return cls(message=msg)


@dataclass
class AppWarn:
    message: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, length: int = 0) -> AppWarn:
        msg = data[:length].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return cls(message=msg)


@dataclass
class AppSeriousWarn:
    message: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, length: int = 0) -> AppSeriousWarn:
        msg = data[:length].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        return cls(message=msg)


@dataclass
class AppGPS:
    longitude: float = 0.0
    latitude: float = 0.0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> AppGPS:
        if len(data) < 16:
            return cls()
        lon = math.degrees(struct.unpack_from("<d", data, 0)[0])
        lat = math.degrees(struct.unpack_from("<d", data, 8)[0])
        return cls(longitude=lon, latitude=lat)
