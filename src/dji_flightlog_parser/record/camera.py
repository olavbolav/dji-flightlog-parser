"""Camera info record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class SDCardState(IntEnum):
    Normal = 0
    NotInserted = 1
    Invalid = 2
    WriteProtection = 3
    Unformatted = 4
    Formatting = 5
    IllegalFileSystem = 6
    Busy = 7
    Full = 8
    Slow = 9
    UnknownError = 10
    IndexFull = 11
    Initializing = 12
    Uninited = 255

    @classmethod
    def _missing_(cls, value: object) -> SDCardState:
        return cls.Uninited


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class Camera:
    is_shooting_single_photo: bool = False
    is_recording: bool = False
    is_storing: bool = False
    sd_card_state: SDCardState = SDCardState.Uninited
    has_sd_card: bool = False
    work_mode: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Camera:
        c = cls()
        if len(data) < 1:
            return c

        bp1 = data[0]
        c.is_shooting_single_photo = bool(bp1 & 0x01)
        c.is_recording = bool(bp1 & 0x02)
        c.is_storing = bool(bp1 & 0x08)

        if len(data) > 1:
            bp2 = data[1]
            c.sd_card_state = SDCardState(_sub_byte(bp2, 0x0F))
            c.has_sd_card = bool(bp2 & 0x10)

        if len(data) > 4:
            c.work_mode = data[4]

        return c
