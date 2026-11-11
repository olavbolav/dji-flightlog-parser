"""RC display field record parser (type 62).

Layout (v14 logs):
  [0:2]   unknown
  [2]     buttons: 0x80 shutter half press (focus), 0x40 shutter full press
          (0x40 is never set without 0x80)
  [3]     buttons: 0x01 record, 0x40 custom button 1, 0x80 custom button 2
  [4:7]   unknown (byte 4 & 0x03 is the flight-mode switch channel)
  [7:17]  5 x u16 LE: aileron, elevator, throttle, rudder, left dial ("gimbal")
  [17:19] u16 LE right dial

Sticks and dials share one scale: 364..1684 with 1024 at centre.

Checked on all 69 logs with type 62 (318,537 records, always 19 bytes; every
v14 family): sticks and both dials stay within 364..1684 with median 1024.
- shutter: byte 2 & 0xC0 is only ever 0x00, 0x80 or 0xC0. A full press is
  followed by photo_state != 0 within 3 s in 73 of 97 presses (3.5 % of
  random 3 s windows).
- record: a press is followed by a recording start or stop within 3 s in 19
  of 24 presses with camera data (misses: 3 M400, 2 Mini 5 Pro).
- custom buttons: in these logs button 1 (0x40) is assigned to "gimbal down"
  and button 2 (0x80) to "gimbal recenter": the pitch ends near -90 deg in 23
  of 29 and near 0 deg in 11 of 16 presses. The assignment and the C1/C2
  labels are user-configurable per RC.
- left dial (bytes 15-16): the gimbal pitch rate follows its sign (about
  +/-6 deg/s, 0 when centred) in all 7 families with gimbal records.
- right dial (bytes 17-18): the gimbal yaw rate relative to the aircraft
  follows its sign on M300/M350 (+5.7/-4.3 and +7.2/-10.7 deg/s); no gimbal
  effect on M4TD; constant 1024 on Neo / Neo 2 (no right dial).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional


@dataclass
class RCDisplayField:
    aileron: int = 0  # right stick, horizontal
    elevator: int = 0  # right stick, vertical
    throttle: int = 0  # left stick, vertical
    rudder: int = 0  # left stick, horizontal
    gimbal: int = 0  # left dial (gimbal pitch), same scale as the sticks
    right_dial: Optional[int] = None  # same scale; pans the gimbal on M300/M350
    is_shutter_half_pressed: bool = False
    is_shutter_pressed: bool = False
    is_record_pressed: bool = False
    is_custom_button_1_pressed: bool = False
    is_custom_button_2_pressed: bool = False

    @property
    def left_dial(self) -> int:
        """Left dial position (alias of ``gimbal``)."""
        return self.gimbal

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> RCDisplayField:
        r = cls()

        if len(data) > 2:
            b2 = data[2]
            r.is_shutter_half_pressed = bool(b2 & 0x80)
            r.is_shutter_pressed = bool(b2 & 0x40)

        if len(data) > 3:
            b3 = data[3]
            r.is_record_pressed = bool(b3 & 0x01)
            r.is_custom_button_1_pressed = bool(b3 & 0x40)
            r.is_custom_button_2_pressed = bool(b3 & 0x80)

        # 7 bytes of button/switch data, then 5 x u16 stick values
        offset = 7
        if offset + 10 > len(data):
            return r
        r.aileron = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.elevator = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.throttle = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.rudder = struct.unpack_from("<H", data, offset)[0]; offset += 2
        r.gimbal = struct.unpack_from("<H", data, offset)[0]; offset += 2

        if len(data) >= 19:
            r.right_dial = struct.unpack_from("<H", data, 17)[0]
        return r
