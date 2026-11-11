"""MC (flight controller) parameters record parser (type 19)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FailSafe(IntEnum):
    """Action when the RC link is lost (byte 0).

    Order matches upstream mc_param.rs, the Payload SDK RC-lost action enum
    and the MSDK failsafe operation enum. Checked on 74 logs: constant within
    every log; 2 in 63/70 v14 logs, and the only OutOfControlGoHome event in
    the corpus happens in a value-2 log.
    """
    Hover = 0
    Landing = 1
    GoHome = 2
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> FailSafe:
        return cls.UNKNOWN


@dataclass
class MCParams:
    fail_safe: FailSafe = FailSafe.UNKNOWN
    # Byte 1 bits, deprecated names. These are misnomers with no support:
    # upstream mc_param.rs calls bits 0x01/0x02/0x04 mvo_func_enabled /
    # avoid_obstacle_enabled / user_avoid_enabled (the fields below). The
    # dynamic home point setting lives in Home.is_dynamic_home_point_enabled,
    # which is off in all 74 logs while bit 0x04 is set in 61 of them. Kept
    # as duplicates so existing raw output keys do not change; to be removed
    # in a planned raw-format change.
    e_landing: bool = False
    go_home_altitude: bool = False
    dynamic_home_point: bool = False
    # Byte 1 bits with the upstream names. Bit 0x04 agrees with VisionGroup
    # user_avoid_enable (block 8 bit 0x0002) in 44/44 logs that have both.
    mvo_func_enabled: bool = False        # 0x01
    avoid_obstacle_enabled: bool = False  # 0x02
    user_avoid_enabled: bool = False      # 0x04

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> MCParams:
        # v14 bytes 2.. are always zero; in v12 byte 2 is decoder spill-over.
        m = cls()
        if len(data) < 1:
            return m
        m.fail_safe = FailSafe(data[0])
        if len(data) > 1:
            bp = data[1]
            m.mvo_func_enabled = bool(bp & 0x01)
            m.avoid_obstacle_enabled = bool(bp & 0x02)
            m.user_avoid_enabled = bool(bp & 0x04)
            # Deprecated duplicates (see above)
            m.e_landing = m.mvo_func_enabled
            m.go_home_altitude = m.avoid_obstacle_enabled
            m.dynamic_home_point = m.user_avoid_enabled
        return m
