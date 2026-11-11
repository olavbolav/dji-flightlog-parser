"""App message records (tips, warnings, GPS) parsers."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Optional


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
    """Pilot app/RC device position.

    Binary: lat f64 @0, lon f64 @8 (degrees, latitude first), altitude f32 @16.
    The f32 is the device altitude in metres, in the same vertical frame as the
    aircraft GNSS heights (not horizontal accuracy). Checked on 54 enterprise
    logs: the per-log median lies within median 2.4 m of the type-48 take-off
    reference height, runs 34-554 m with site elevation and goes negative.
    Type 14 is always 20 bytes and only occurs in enterprise logs.
    """
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: Optional[float] = None

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> AppGPS:
        if len(data) < 16:
            return cls()
        lat = struct.unpack_from("<d", data, 0)[0]
        lon = struct.unpack_from("<d", data, 8)[0]
        altitude = None
        if len(data) >= 20:
            altitude = struct.unpack_from("<f", data, 16)[0]
        if abs(lat) > 90.0:
            lat = math.degrees(lat)
        if abs(lon) > 180.0:
            lon = math.degrees(lon)
        return cls(latitude=lat, longitude=lon, altitude=altitude)
