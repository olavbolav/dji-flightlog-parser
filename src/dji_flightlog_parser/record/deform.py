"""Deform (landing gear) record parser."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class DeformStatus(IntEnum):
    Folded = 0
    Folding = 1
    Stretched = 2
    Stretching = 3
    StopDeformation = 4
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DeformStatus:
        return cls.UNKNOWN


class DeformMode(IntEnum):
    PackMode = 0
    ProtectMode = 1
    Normal = 2
    UNKNOWN = 3

    @classmethod
    def _missing_(cls, value: object) -> DeformMode:
        return cls.UNKNOWN


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class Deform:
    is_deform_protected: bool = False
    status: DeformStatus = DeformStatus.Folded
    mode: DeformMode = DeformMode.Normal

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Deform:
        d = cls()
        if len(data) < 1:
            return d
        bp = data[0]
        d.is_deform_protected = bool(bp & 0x01)
        d.status = DeformStatus(_sub_byte(bp, 0x0E))
        d.mode = DeformMode(_sub_byte(bp, 0x30))
        return d
