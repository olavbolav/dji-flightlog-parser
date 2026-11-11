"""ADS-B flight data record parser (type 26).

Each record contains a snapshot of nearby aircraft detected by the
drone's ADS-B receiver (DJI AirSense). Format: 2-byte header + N * 28-byte entries.

Header:
  [0]     status byte, kept as ``message_type``. (b >> 1) & 7 equals the
          highest per-aircraft warning level in every corpus record and
          0x20 is set only while a level-2 alert is shown; 0x41 = no traffic.
          Other bits are unverified.
  [1]     number of aircraft entries

Per-aircraft entry layout (28 bytes). The field order matches the DJI Cloud
API ``AirsenseWarning`` struct (icao, warning_level, latitude, longitude,
altitude, altitude_type, heading, relative_altitude, vert_trend, distance):
  [0:6]   ICAO hex address (6 ASCII chars)
  [6]     null terminator
  [7]     warning level (u8, 0-4 as in the Cloud API WarningLevelEnum)
  [8:12]  latitude  (i32 LE, degrees * 10^6)
  [12:16] longitude (i32 LE, degrees * 10^6)
  [16:20] altitude  (i32 LE, metres; reference given by altitude_type)
  [20]    altitude type (u8, 0 = WGS84 ellipsoid height, 1 = above mean sea level)
  [21:23] heading   (u16 LE, degrees * 10)
  [23:25] relative altitude (i16 LE, metres, traffic minus drone, + = above)
  [25]    vertical trend (u8, 0 = unchanged, 1 = rising, 2 = falling)
  [26:28] horizontal distance from the drone (u16 LE, metres)

Checked on the 57 logs with type 26 (all M300/M30/M350/M400/M4TD logs,
22,120 records); 29 of them have traffic (M400 13, M4TD 11, M350 RTK 5,
43,019 entries):
- header: (b0 >> 1) & 7 equals the highest entry warning level in all records.
- altitude: 97.5 % of the altitude changes within a track are multiples of
  7.62 m (25 ft, +/- 1 m) and the maximum is 11,909 (FL390 in metres), so
  the unit is metres, not feet. All other changes are on ellipsoid heights.
- warning level: 1 in 43,011 entries; 2 in 8 records of one M400 log, in two
  bursts that start at the exact OSD tick of the two "Manned aircraft
  detected nearby. Fly with caution" app warnings. 0, 3 and 4 never seen.
- altitude type: 1 on every M350 RTK entry, 0 on every M400/M4TD entry.
- relative altitude: per-log fit gives slope 0.996-1.005 against the traffic
  altitude and about -1 against OSD height; range -189 to 11,680 m with
  1,811 negative values (low traffic), so it is signed.
- vertical trend: the trend of the relative altitude. Against the track's
  own vertical rate, 1 is climbing in 79 % (median +9.9 m/s) and 2 is
  descending in 66 % (median -3.8 m/s); 1 and 2 are swapped in only 35 of
  39,745 samples. 0 has median 0.0 m/s.
- distance: matches the haversine distance from the OSD drone position to
  the entry's own position (median residual 3.1 m, MAD 9.4 m; range 86 m to
  30.3 km).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional


VERTICAL_TREND_NAMES: dict[int, str] = {
    0: "Level",
    1: "Rising",
    2: "Falling",
}

ALTITUDE_TYPE_NAMES: dict[int, str] = {
    0: "Ellipsoid",
    1: "MSL",
}


@dataclass
class ADSBAircraft:
    icao_address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: int = 0  # metres, reference given by altitude_type
    heading: float = 0.0
    # AirSense warning level 0-4 (1 = tracked, 2 = caution, >= 3 = evasive action)
    warning_level: Optional[int] = None
    altitude_type: Optional[int] = None  # 0 = WGS84 ellipsoid, 1 = above MSL
    relative_altitude: Optional[int] = None  # metres, traffic minus drone
    vertical_trend: Optional[int] = None  # 0 = level, 1 = rising, 2 = falling
    distance: Optional[int] = None  # horizontal distance from the drone, metres

    @property
    def vertical_trend_name(self) -> Optional[str]:
        """Name of the vertical trend ("Level", "Rising", "Falling"), None if unknown."""
        if self.vertical_trend is None:
            return None
        return VERTICAL_TREND_NAMES.get(self.vertical_trend)

    @property
    def altitude_type_name(self) -> Optional[str]:
        """Reference of ``altitude`` ("Ellipsoid" or "MSL"), None if unknown."""
        if self.altitude_type is None:
            return None
        return ALTITUDE_TYPE_NAMES.get(self.altitude_type)

    def to_dict(self) -> dict:
        return {
            "icaoAddress": self.icao_address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "heading": round(self.heading, 1),
        }


ENTRY_SIZE = 28


@dataclass
class ADSBFlightData:
    message_type: int = 0  # header status byte, see the module docstring
    aircraft: list[ADSBAircraft] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> ADSBFlightData:
        r = cls()
        if len(data) < 2:
            return r

        r.message_type = data[0]
        count = data[1]

        offset = 2
        for _ in range(count):
            if offset + ENTRY_SIZE > len(data):
                break

            entry = data[offset:offset + ENTRY_SIZE]
            a = ADSBAircraft()

            null_pos = entry.find(0x00, 0, 7)
            if null_pos > 0:
                a.icao_address = entry[:null_pos].decode("ascii", errors="replace").lower()

            a.warning_level = entry[7]
            a.latitude = struct.unpack_from("<i", entry, 8)[0] / 1_000_000.0
            a.longitude = struct.unpack_from("<i", entry, 12)[0] / 1_000_000.0
            a.altitude = struct.unpack_from("<i", entry, 16)[0]
            a.altitude_type = entry[20]
            a.heading = struct.unpack_from("<H", entry, 21)[0] / 10.0
            a.relative_altitude = struct.unpack_from("<h", entry, 23)[0]
            a.vertical_trend = entry[25]
            a.distance = struct.unpack_from("<H", entry, 26)[0]

            r.aircraft.append(a)
            offset += ENTRY_SIZE

        return r
