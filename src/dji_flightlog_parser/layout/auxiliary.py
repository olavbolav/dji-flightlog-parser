"""Auxiliary block parsing for v13+ DJI flight log files."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Department(IntEnum):
    SDK = 1
    DJIGO = 2
    DJIFly = 3
    DJIGO4 = 4
    DJIPilot = 5
    DJIGO3 = 6
    DJIMiniPilot = 7
    GSPro = 8

    @classmethod
    def from_value(cls, val: int) -> Department | int:
        try:
            return cls(val)
        except ValueError:
            return val

    def to_json(self) -> str:
        if isinstance(self, Department):
            return self.name
        return str(self)


@dataclass
class AuxiliaryInfo:
    version_data: int
    info_data: bytes
    signature_data: bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> AuxiliaryInfo:
        if len(data) < 3:
            raise ValueError(f"AuxiliaryInfo data too short: {len(data)} bytes (need >= 3)")

        offset = 0
        version_data = data[offset]
        offset += 1

        info_length = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if offset + info_length > len(data):
            raise ValueError(
                f"AuxiliaryInfo info_data truncated: need {info_length} bytes at offset {offset}, "
                f"but only {len(data) - offset} available"
            )
        info_data = data[offset:offset + info_length]
        offset += info_length

        if offset + 2 > len(data):
            raise ValueError(
                f"AuxiliaryInfo signature_length truncated at offset {offset} (data length {len(data)})"
            )
        signature_length = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if offset + signature_length > len(data):
            raise ValueError(
                f"AuxiliaryInfo signature_data truncated: need {signature_length} bytes at offset {offset}, "
                f"but only {len(data) - offset} available"
            )
        signature_data = data[offset:offset + signature_length]

        return cls(
            version_data=version_data,
            info_data=info_data,
            signature_data=signature_data,
        )


@dataclass
class AuxiliaryVersion:
    version: int  # u16
    department: Department | int

    @classmethod
    def from_bytes(cls, data: bytes) -> AuxiliaryVersion:
        version = struct.unpack_from("<H", data, 0)[0]
        dept_val = data[2] if len(data) > 2 else 3
        return cls(
            version=version,
            department=Department.from_value(dept_val),
        )


@dataclass
class Auxiliary:
    """Represents one auxiliary block from a v13+ log file."""
    kind: int  # 0=Info, 1=Version
    info: Optional[AuxiliaryInfo] = None
    version_block: Optional[AuxiliaryVersion] = None

    @classmethod
    def read_from(cls, data: bytes, offset: int) -> tuple[Auxiliary, int]:
        """Read an auxiliary block from data at offset.
        Returns (Auxiliary, new_offset)."""
        from ..decoder.xor import xor_decode_block

        if offset + 3 > len(data):
            raise ValueError(
                f"Auxiliary block truncated at offset {offset} (data length {len(data)}, need >= 3 bytes)"
            )

        kind = data[offset]
        offset += 1

        size = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        if offset + size > len(data):
            raise ValueError(
                f"Auxiliary block data truncated: need {size} bytes at offset {offset}, "
                f"but only {len(data) - offset} available"
            )
        block_data = data[offset:offset + size]

        if kind == 0:
            decoded = xor_decode_block(block_data, record_type=0)
            info = AuxiliaryInfo.from_bytes(decoded)
            return cls(kind=0, info=info), offset + size
        elif kind == 1:
            ver = AuxiliaryVersion.from_bytes(block_data)
            return cls(kind=1, version_block=ver), offset + size
        else:
            return cls(kind=kind), offset + size
