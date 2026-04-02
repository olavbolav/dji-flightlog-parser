"""Binary prefix parser for DJI flight log files."""

from __future__ import annotations

import struct
from dataclasses import dataclass

OLD_PREFIX_SIZE = 12
PREFIX_SIZE = 100


@dataclass
class Prefix:
    detail_offset: int  # u64
    _detail_length: int  # u16
    version: int  # u8

    @classmethod
    def from_bytes(cls, data: bytes) -> Prefix:
        if len(data) < OLD_PREFIX_SIZE:
            raise ValueError(f"File too small for prefix: {len(data)} bytes")

        detail_offset, detail_length, version = struct.unpack_from("<QHB", data, 0)
        return cls(
            detail_offset=detail_offset,
            _detail_length=detail_length,
            version=version,
        )

    def effective_detail_offset(self) -> int:
        if self.version < 12:
            return self.detail_offset
        return PREFIX_SIZE

    def records_offset(self) -> int:
        if self.version < 6:
            return OLD_PREFIX_SIZE
        if self.version < 12:
            return PREFIX_SIZE
        if self.version == 12:
            return PREFIX_SIZE + 436
        # v13+: detail_offset points past auxiliary blocks to records
        return self.detail_offset

    def records_end_offset(self, file_size: int) -> int:
        if self.version < 12:
            return self.detail_offset
        return file_size

    @property
    def header_size(self) -> int:
        if self.version < 6:
            return OLD_PREFIX_SIZE
        return PREFIX_SIZE
