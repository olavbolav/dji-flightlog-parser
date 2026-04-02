"""Firmware version record parser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Firmware:
    sender_type: int = 0
    sub_sender_type: int = 0
    version: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Firmware:
        f = cls()
        if len(data) < 6:
            return f

        f.sender_type = data[0]
        f.sub_sender_type = data[1]
        ver_bytes = data[2:6]
        f.version = f"{ver_bytes[0]}.{ver_bytes[1]}.{ver_bytes[2]}"

        return f
