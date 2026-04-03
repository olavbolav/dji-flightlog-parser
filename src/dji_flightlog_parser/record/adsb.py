"""ADS-B flight data record parser (type 26).

Each record contains a snapshot of nearby aircraft detected by the
drone's ADS-B receiver (DJI AirSense). Format: 2-byte header + N * 28-byte entries.

Per-aircraft entry layout (28 bytes):
  [0:6]   ICAO hex address (6 ASCII chars)
  [6]     null terminator
  [7]     flags (0x01 = valid position)
  [8:12]  latitude  (i32 LE, degrees * 10^6)
  [12:16] longitude (i32 LE, degrees * 10^6)
  [16:20] altitude  (i32 LE, feet barometric)
  [20]    padding (always 0x00)
  [21:23] heading   (u16 LE, degrees * 10)
  [23:25] unclear   (tracks close to altitude; possibly geometric altitude)
  [25]    unclear flags
  [26]    unclear
  [27]    unclear   (correlates with distance to drone)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class ADSBAircraft:
    icao_address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: int = 0
    heading: float = 0.0

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
    message_type: int = 0
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

            a.latitude = struct.unpack_from("<i", entry, 8)[0] / 1_000_000.0
            a.longitude = struct.unpack_from("<i", entry, 12)[0] / 1_000_000.0
            a.altitude = struct.unpack_from("<i", entry, 16)[0]
            a.heading = struct.unpack_from("<H", entry, 21)[0] / 10.0

            r.aircraft.append(a)
            offset += ENTRY_SIZE

        return r
