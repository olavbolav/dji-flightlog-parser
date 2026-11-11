"""AgricultureGroundStationPush record parser (type 48, feature point Agriculture).

Despite DJI's name, on enterprise aircraft (M30, M300, M350, M4TD, M400) this
is a 71-byte flight-controller navigation-state struct written about once per
OSD record (10 Hz). It carries the fused position at full precision, a
seconds + nanoseconds aircraft-clock timestamp, satellites used, the home
point, horizontal distance to home and several heights.

Verified on 685,813 records from 57 v14 logs (one layout for all products).

Caveats from the data:

* The timestamp epoch is not uniformly UTC. On M30/M300/M350 it is UTC + 1 h;
  on M4TD/M400 it is UTC or about UTC + 18 s, decided per flight.
* A few M4TD/M400 records are byte-identical replays of an earlier record.
  Drop records whose (timestamp_sec, timestamp_nsec) was already seen.
* In about half the logs the last 1-2 records re-zero ``relative_height``
  (and shift ``takeoff_reference_height`` by the opposite amount).
* ``fc_altitude`` changes frame when RTK fixes; do not plot it as one series
  across an ``is_rtk_fixed`` 0 -> 1 transition.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Optional

RECORD_LENGTH = 71

_STRUCT = struct.Struct("<ddfhBBIIBBddfffffB")


@dataclass
class AgricultureGroundStationPush:
    longitude: float = 0.0  # degrees (stored as radians, longitude first)
    latitude: float = 0.0  # degrees
    relative_height: float = 0.0  # metres above take-off (OSD altitude, unrounded)
    yaw: float = 0.0  # degrees, -180..180, 0 = north
    rtk_flag_a: int = 0  # per-flight RTK-related flag, meaning unknown
    is_rtk_fixed: bool = False  # FC navigates on an RTK fixed solution
    timestamp_sec: int = 0  # aircraft clock, whole seconds (see module docs)
    timestamp_nsec: int = 0
    timestamp: float = 0.0  # timestamp_sec + timestamp_nsec * 1e-9
    nav_status_flags: int = 0  # bitfield, meaning mostly unknown (0x44 = RTK fixed)
    satellites_used: int = 0  # satellites in the solution in use
    home_longitude: float = 0.0  # degrees
    home_latitude: float = 0.0  # degrees
    takeoff_reference_height: float = 0.0  # metres, GNSS-frame zero for relative_height
    distance_to_home: float = 0.0  # metres, horizontal
    fc_altitude: float = 0.0  # metres, frame-dependent (baro / GNSS blend / RTK)
    gnss_height: float = 0.0  # metres, standalone GNSS height (~5 Hz updates)
    geoid_undulation: Optional[float] = None  # metres, per flight; None = unavailable
    rtk_state_b: int = 0  # 1 default, 2 only under RTK fix; meaning unknown

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """True for a decodable 71-byte v13+ record (v12 records are unrelated).

        Every real v14 record passes. The checks are region-independent and
        reject AES ciphertext passed through without a key (which is 81 bytes
        and random).
        """
        if version < 13 or len(data) != RECORD_LENGTH:
            return False
        v = _STRUCT.unpack_from(data, 0)
        floats = (v[0], v[1], v[2], v[10], v[11], v[12], v[13], v[14], v[15], v[16])
        return (
            all(math.isfinite(f) for f in floats)
            and abs(v[0]) <= math.pi and abs(v[1]) <= math.pi / 2
            and abs(v[10]) <= math.pi and abs(v[11]) <= math.pi / 2
            and -1800 <= v[3] <= 1800
            and v[5] <= 1
            and v[7] < 1_000_000_000
            and v[13] >= 0.0
        )

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> AgricultureGroundStationPush:
        p = cls()
        if len(data) < RECORD_LENGTH:
            return p

        (lon, lat, rel_h, yaw10, b22, b23, sec, nsec, status, sats,
         home_lon, home_lat, f50, f54, f58, f62, f66, b70) = _STRUCT.unpack_from(data, 0)

        p.longitude = math.degrees(lon)
        p.latitude = math.degrees(lat)
        p.relative_height = rel_h
        p.yaw = yaw10 / 10.0
        p.rtk_flag_a = b22
        p.is_rtk_fixed = bool(b23)
        p.timestamp_sec = sec
        p.timestamp_nsec = nsec
        p.timestamp = sec + nsec * 1e-9
        p.nav_status_flags = status
        p.satellites_used = sats
        p.home_longitude = math.degrees(home_lon)
        p.home_latitude = math.degrees(home_lat)
        p.takeoff_reference_height = f50
        p.distance_to_home = f54
        p.fc_altitude = f58
        p.gnss_height = f62
        p.geoid_undulation = f66 if f66 != 0.0 else None
        p.rtk_state_b = b70
        return p
