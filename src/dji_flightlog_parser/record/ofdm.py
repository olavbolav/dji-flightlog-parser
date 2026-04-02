"""OFDM (link quality) record parser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OFDM:
    signal_percent: int = 0
    is_up: bool = False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> OFDM:
        o = cls()
        if len(data) < 1:
            return o
        bp = data[0]
        o.signal_percent = bp & 0x7F
        o.is_up = bool(bp & 0x80)
        return o
