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
    """App/controller GPS position. Binary: lat(f64) + lon(f64) in degrees + accuracy(f32)."""
    latitude: float = 0.0
    longitude: float = 0.0
    horizontal_accuracy: float = -1.0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> AppGPS:
        if len(data) < 16:
            return cls()
        lat = struct.unpack_from("<d", data, 0)[0]
        lon = struct.unpack_from("<d", data, 8)[0]
        accuracy = -1.0
        if len(data) >= 20:
            accuracy = struct.unpack_from("<f", data, 16)[0]
        if abs(lat) > 90.0:
            lat = math.degrees(lat)
        if abs(lon) > 180.0:
            lon = math.degrees(lon)
        return cls(latitude=lat, longitude=lon, horizontal_accuracy=accuracy)
