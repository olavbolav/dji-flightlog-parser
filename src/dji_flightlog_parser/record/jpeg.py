"""JPEG image extraction from flight log records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JPEG:
    data: bytes = b""

    @classmethod
    def from_bytes(cls, data: bytes) -> JPEG:
        """Extract JPEG from data by finding SOI (0xFFD8) and EOI (0xFFD9) markers."""
        start = -1
        for i in range(len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD8:
                start = i
                break
        if start < 0:
            return cls()

        end = -1
        for i in range(start + 2, len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD9:
                end = i + 2
                break

        if end < 0:
            return cls(data=data[start:])

        return cls(data=data[start:end])
