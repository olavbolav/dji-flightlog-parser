"""RTKDifference record parser (type 45, feature point Agriculture).

RTK/GNSS module status, written at 1 Hz with no timestamp of its own (take
time from the surrounding OSD records). Bytes 0-56 follow the legacy DUML
0x0F/0x09 "Rtk Status" packet; v14 appends correction age, 1-sigma errors
and further satellite counters.

Two layouts are known, told apart by length only (M4TD/M400 logs report
product NONE, so the product cannot be used):

* 80 bytes: Matrice 30 / 300 RTK / 350 RTK.
* 83 bytes: Matrice 4TD / Matrice 400. Same as the 80-byte layout plus a
  5th satellite-counter triple, but the horizontal sigma pair at 65/69 is in
  the opposite axis order.

Verified on 68,541 records from 57 v14 logs. Satellite counters store
``count << 1 | 1``; bit 0 is always set and is not a validity flag.
Latitude/longitude are degrees (unlike OSD/Home, which store radians), and
latitude comes first. ``rover_height`` is not relative to take-off; it is
most likely ellipsoidal (unproven).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

LEGACY_LENGTH = 57
LENGTH_O3 = 80
LENGTH_O4 = 83

# 11 x u8, f64 lat, f64 lon, f32 height, f64 base lat, f64 base lon,
# u32 base param, f32 heading, u8 heading solution, u8 flag
_LEGACY = struct.Struct("<11BddfddIfBB")
# f32 correction age, u32 reserved, 3 x f32 sigma, 3 x u8 counters
_EXT = struct.Struct("<fI3f3B")


class RTKSolutionType(IntEnum):
    """Position/heading solution type (NovAtel-style codes)."""
    NONE = 0  # no solution / no heading
    Single = 16
    Float = 34
    Fixed = 50
    Code52 = 52  # undocumented; base-free, M400 only. Not shown to be precise.
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> RTKSolutionType:
        return cls.UNKNOWN


def _count(v: int) -> int:
    return v >> 1


@dataclass
class RTKDifference:
    position_solution: RTKSolutionType = RTKSolutionType.NONE
    position_solution_code: int = 0  # raw byte 1, keeps unseen codes

    # Satellite counts per receiver and constellation. rx2 = second antenna
    # (0 on single-antenna aircraft); base = reference side (0 without base).
    # GPS and BeiDou labels are confirmed; GLONASS/Galileo are plausible.
    rx1_gps_sats: int = 0
    rx1_beidou_sats: int = 0
    rx1_glonass_sats: int = 0
    rx1_galileo_sats: int = 0
    rx1_gnss5_sats: int = 0  # 83-byte layout only; system unknown
    rx2_gps_sats: int = 0
    rx2_beidou_sats: int = 0
    rx2_glonass_sats: int = 0
    rx2_galileo_sats: int = 0
    rx2_gnss5_sats: int = 0
    base_gps_sats: int = 0
    base_beidou_sats: int = 0
    base_glonass_sats: int = 0
    base_galileo_sats: int = 0
    base_gnss5_sats: int = 0

    rover_latitude: float = 0.0  # degrees, RTK antenna 1
    rover_longitude: float = 0.0  # degrees
    rover_height: float = 0.0  # metres, likely ellipsoidal; not take-off relative

    has_base: bool = False
    base_latitude: Optional[float] = None  # degrees; None without a base
    base_longitude: Optional[float] = None
    base_param_47: int = 0  # opaque u32, non-zero only with a base

    dual_antenna_heading: Optional[float] = None  # degrees, 90 deg off the nose
    heading_solution: RTKSolutionType = RTKSolutionType.NONE
    heading_solution_code: int = 0

    correction_age: Optional[float] = None  # seconds; 0 = no corrections
    std_latitude: Optional[float] = None  # metres, 1-sigma north (axis order plausible)
    std_longitude: Optional[float] = None  # metres, 1-sigma east
    std_altitude: Optional[float] = None  # metres, 1-sigma vertical

    reserved_0: int = 0  # always 0
    flag_56: int = 0  # always 1
    length: int = 0

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """Sanity gate: rejects failed decryption and unrelated layouts.

        All real v14 records pass. The single 142-byte record in a v12 log
        is not this layout.
        """
        # Real records are 80 or 83 bytes. Longer payloads are rejected: AES
        # ciphertext passed through without a key is 97 bytes and random.
        if version < 13 or not LEGACY_LENGTH <= len(data) <= LENGTH_O4:
            return False
        v = _LEGACY.unpack_from(data, 0)
        counters = list(v[2:11])
        lat, lon, height, base_lat, base_lon, _, heading = v[11:18]
        floats = [lat, lon, height, base_lat, base_lon, heading]
        if len(data) >= LENGTH_O3:
            e = _EXT.unpack_from(data, LEGACY_LENGTH)
            floats += [e[0], e[2], e[3], e[4]]
            counters += list(e[5:8])
        if len(data) >= LENGTH_O4:
            counters += list(data[80:83])
        return (
            all(math.isfinite(f) for f in floats)
            and -90.0 <= lat <= 90.0
            and -180.0 <= lon <= 180.0
            and 0.0 <= heading < 360.0
            and all(c & 1 for c in counters)
        )

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> RTKDifference:
        r = cls()
        r.length = len(data)
        if len(data) < LEGACY_LENGTH:
            return r

        (a0, sol,
         g1, b1, r1, g2, b2, r2, gb, bb, rb,
         lat, lon, height, base_lat, base_lon, base_param,
         heading, heading_sol, flag) = _LEGACY.unpack_from(data, 0)

        r.reserved_0 = a0
        r.position_solution_code = sol
        r.position_solution = RTKSolutionType(sol)
        r.rx1_gps_sats, r.rx1_beidou_sats, r.rx1_glonass_sats = _count(g1), _count(b1), _count(r1)
        r.rx2_gps_sats, r.rx2_beidou_sats, r.rx2_glonass_sats = _count(g2), _count(b2), _count(r2)
        r.base_gps_sats, r.base_beidou_sats, r.base_glonass_sats = _count(gb), _count(bb), _count(rb)

        r.rover_latitude = lat
        r.rover_longitude = lon
        r.rover_height = height

        r.has_base = base_lat != 0.0 or base_lon != 0.0
        if r.has_base:
            r.base_latitude = base_lat
            r.base_longitude = base_lon
        r.base_param_47 = base_param

        r.heading_solution_code = heading_sol
        r.heading_solution = RTKSolutionType(heading_sol)
        if heading_sol != 0:
            r.dual_antenna_heading = heading
        r.flag_56 = flag

        if len(data) >= LENGTH_O3:
            age, _reserved, s65, s69, s73, ge, be, re_ = _EXT.unpack_from(data, LEGACY_LENGTH)
            r.correction_age = age
            if len(data) >= LENGTH_O4:
                # M4TD/M400 layout: east first, then north
                r.std_longitude, r.std_latitude = s65, s69
            else:
                r.std_latitude, r.std_longitude = s65, s69
            r.std_altitude = s73
            r.rx1_galileo_sats, r.rx2_galileo_sats, r.base_galileo_sats = _count(ge), _count(be), _count(re_)

        if len(data) >= LENGTH_O4:
            r.rx1_gnss5_sats = _count(data[80])
            r.rx2_gnss5_sats = _count(data[81])
            r.base_gnss5_sats = _count(data[82])

        return r

    @property
    def rx1_total_sats(self) -> int:
        return (self.rx1_gps_sats + self.rx1_beidou_sats + self.rx1_glonass_sats
                + self.rx1_galileo_sats + self.rx1_gnss5_sats)

    @property
    def is_dual_antenna(self) -> bool:
        return self.heading_solution_code != 0
