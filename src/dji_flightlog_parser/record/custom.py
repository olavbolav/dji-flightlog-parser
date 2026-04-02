"""Custom/timestamp record parser."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Custom:
    camera_shoot: bool = False
    video_shoot: bool = False
    h_speed: float = 0.0
    distance: float = 0.0
    update_timestamp: datetime = None  # type: ignore

    def __post_init__(self) -> None:
        if self.update_timestamp is None:
            self.update_timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Custom:
        c = cls()
        if len(data) < 1:
            return c

        c.camera_shoot = bool(data[0])
        if len(data) > 1:
            c.video_shoot = bool(data[1])
        if len(data) > 5:
            c.h_speed = struct.unpack_from("<f", data, 2)[0]
        if len(data) > 9:
            c.distance = struct.unpack_from("<f", data, 6)[0]
        if len(data) > 17:
            ts_ms = struct.unpack_from("<q", data, 10)[0]
            if ts_ms > 0:
                secs = ts_ms // 1000
                ns = (ts_ms % 1000) * 1_000_000
                c.update_timestamp = datetime.fromtimestamp(secs, tz=timezone.utc).replace(
                    microsecond=ns // 1000
                )
        return c
