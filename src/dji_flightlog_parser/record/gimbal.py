"""Gimbal state record parser (type 3).

Layout used here (lengths 41 Mavic Mini v12, 45/49/50 v14):
  0-5   i16 LE pitch, roll, yaw (deg / 10). Yaw is in the gimbal's own yaw
        frame with a per-flight offset from true north, not a bearing.
  6     0xC0 mode, 0x20 reset in progress
  7     i8 roll adjust (deg / 10)
  8-9   i16 LE yaw relative to the aircraft heading (yaw joint, deg / 10)
  10    status bits
  11    0x0F version (record version >= 2)
  20-21 i16 LE pitch joint angle (pitch relative to the airframe, deg / 10)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class GimbalMode(IntEnum):
    Free = 0
    FPV = 1
    YawFollow = 2
    UNKNOWN = 3

    @classmethod
    def _missing_(cls, value: object) -> GimbalMode:
        return cls.UNKNOWN


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class Gimbal:
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    mode: GimbalMode = GimbalMode.Free
    roll_adjust: float = 0.0
    # Yaw relative to the aircraft heading (yaw joint angle, bytes 8-9). On
    # M300, M350, M30 and Mavic Mini the camera bearing is OSD yaw + yaw_angle.
    # Checked on the logs with yaw motion: gimbal yaw - OSD yaw correlates
    # with it at r 0.93-0.97 (M300, 4 logs), 0.72-0.99 (M350, 11 logs) and
    # 0.97-0.99 (Mavic Mini, 3 logs). It does not behave as a joint angle on
    # M4TD and Mini 5 Pro (r about 0), and it is always 0 on Neo, Neo 2 and
    # the M4TD accessory stream.
    yaw_angle: float = 0.0
    is_pitch_at_limit: bool = False
    is_roll_at_limit: bool = False
    is_yaw_at_limit: bool = False
    is_auto_calibration: bool = False
    is_stuck: bool = False
    version: int = 0
    # Reset command in progress (recenter or point down), byte 6 bit 0x20.
    # Checked on 37 logs of all 8 gimbal families: 122 pulses of 0.1-0.8 s
    # (median 0.2 s); the pitch moves more than 3 deg within 3 s after 108 of
    # them, ending near 0 deg (50) or -90 deg (51).
    is_resetting: bool = False
    # Pitch joint angle in degrees: gimbal pitch relative to the airframe
    # (bytes 20-21). Checked on 55 logs of all 8 gimbal families (713k
    # records, lengths 41/45/49/50): in air it tracks gimbal pitch - OSD pitch
    # with slope 0.88-1.09 and r 0.955-1.000 per log; range -126 to +74 deg.
    joint_pitch: Optional[float] = None

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Gimbal:
        g = cls()
        if len(data) < 6:
            return g

        g.pitch = struct.unpack_from("<h", data, 0)[0] / 10.0
        g.roll = struct.unpack_from("<h", data, 2)[0] / 10.0
        g.yaw = struct.unpack_from("<h", data, 4)[0] / 10.0

        if len(data) > 6:
            bp1 = data[6]
            g.mode = GimbalMode(_sub_byte(bp1, 0xC0))
            g.is_resetting = bool(bp1 & 0x20)

        if len(data) > 7:
            g.roll_adjust = struct.unpack_from("<b", data, 7)[0] / 10.0

        if len(data) > 9:
            g.yaw_angle = struct.unpack_from("<h", data, 8)[0] / 10.0

        if len(data) > 10:
            bp2 = data[10]
            g.is_pitch_at_limit = bool(bp2 & 0x01)
            g.is_roll_at_limit = bool(bp2 & 0x02)
            g.is_yaw_at_limit = bool(bp2 & 0x04)
            g.is_auto_calibration = bool(bp2 & 0x08)
            # Upstream dji-log-parser and the DUML dissector put "stuck" at
            # 0x40 (0x20 is the install direction). Neither bit is set in any
            # of the 713,120 corpus records.
            g.is_stuck = bool(bp2 & 0x40)

        if version >= 2 and len(data) > 11:
            bp3 = data[11]
            g.version = _sub_byte(bp3, 0x0F)

        if len(data) >= 22:
            g.joint_pitch = struct.unpack_from("<h", data, 20)[0] / 10.0

        return g
