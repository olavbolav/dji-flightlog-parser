"""AirLinkDataField record parser (type 57, DJI name GOAirLinkDataField).

Radio-link status, built as FRSubTypeBody {u16 subtype; data}. It is on the
AirLink feature point and shares its CBC IV chain with type 49 (OFDM).
Level bytes use MSDK WlmLinkQualityLevel: 0 = no usable signal, 1..5 = bars.

* Subtype 1 (3 bytes): SDR/OcuSync quality level, 1 Hz on O4 aircraft
  (M4TD, M400, Mini 5 Pro, Neo, Neo 2) and 4 Hz on O3 (M30, M300, M350).
  Only ``sdr_quality`` is set; the subtype-2 fields stay None.
* Subtype 2 (26 bytes on O3, 35 on O4, ~5 Hz): SDR and LTE (DJI Cellular)
  link state, quality levels, the fused level shown to the pilot and the
  link work mode. Bytes 0-24 mean the same in both layouts, except 19.
* Every v14 log ends its type-57 stream with a truncated, empty stub at end
  of file. The reader keeps it (and any other unrecognised payload) as an
  UnknownRecord.

Verified on 511,283 records from 70 v14 logs. The LTE labels follow MSDK
naming plus behaviour (flight continues beyond SDR range only with LTE up);
no field names a modem. ``lte_level_a``/``lte_level_b`` are probably the
aircraft and RC sides, but that is statistical, hence the neutral names.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

SUBTYPE_SDR_LEVEL = 1
SUBTYPE_LINK_STATUS = 2
LENGTH_O3 = 26
LENGTH_O4 = 35
_COMMON_LENGTH = 25  # bytes 0-24 are shared by both subtype-2 layouts
_MAX_LEVEL = 5


class LinkWorkMode(IntEnum):
    SdrOnly = 1
    SdrLte = 3  # SDR + LTE fusion ("LTE enhanced transmission")
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> LinkWorkMode:
        return cls.UNKNOWN


@dataclass
class AirLinkDataField:
    sub_type: int = 0
    length: int = 0

    # Subtype 1 and 2. On subtype 2 this is latched from the latest subtype 1.
    sdr_quality: Optional[int] = None  # 0..5 = min(uplink bar, downlink bar); 0 is not "link down"

    # Subtype 2 only (None on subtype 1)
    sdr_link_up: Optional[bool] = None  # use this, not sdr_quality, for link up/down
    lte_link_up: Optional[bool] = None
    lte_quality: Optional[int] = None  # 0..5 = min(lte_level_a, lte_level_b)
    link_quality: Optional[int] = None  # 0..5, fused level the pilot app shows
    link_work_mode: Optional[LinkWorkMode] = None
    link_work_mode_code: Optional[int] = None
    lte_level_a: Optional[int] = None  # 0..5, probably aircraft side
    lte_level_b: Optional[int] = None  # 0..5, probably RC side
    aux_level_1hz: Optional[int] = None  # 0..5 from a separate 1 Hz source; meaning unknown
    unknown_11: Optional[int] = None
    layout_code: Optional[int] = None  # 1 on the 26-byte layout, 3 on the 35-byte layout
    channel_like_19: Optional[int] = None  # O3 only, signed; maybe SDR channel index
    lte_fusion: Optional[bool] = None  # O4 only, == (link_work_mode == SdrLte)
    const_29: Optional[int] = None  # O4 only, 1 or 3 per log; meaning unknown

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """True for a recognised v13+ subtype 1 or 2 payload.

        The end-of-log stub, unknown subtypes, short payloads and AES
        ciphertext passed through without a key stay UnknownRecord (with
        their bytes). v12 type-57 records have a different, unknown layout.
        """
        if version < 13 or len(data) < 3:
            return False
        sub_type = struct.unpack_from("<H", data, 0)[0]
        if sub_type == SUBTYPE_SDR_LEVEL:
            return data[2] <= _MAX_LEVEL
        if sub_type == SUBTYPE_LINK_STATUS and len(data) >= _COMMON_LENGTH:
            return (
                data[2] <= 1 and data[3] <= 1
                and all(data[i] <= _MAX_LEVEL for i in (5, 6, 8, 23, 24))
                and len(set(data[13:19])) == 1
            )
        return False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> AirLinkDataField:
        a = cls()
        a.length = len(data)
        if len(data) < 2:
            return a

        a.sub_type = struct.unpack_from("<H", data, 0)[0]

        if a.sub_type == SUBTYPE_SDR_LEVEL:
            if len(data) >= 3:
                a.sdr_quality = data[2]

        elif a.sub_type == SUBTYPE_LINK_STATUS and len(data) >= _COMMON_LENGTH:
            a.sdr_link_up = bool(data[2])
            a.lte_link_up = bool(data[3])
            a.sdr_quality = data[5]
            a.lte_quality = data[6]
            a.link_quality = data[8]
            a.aux_level_1hz = data[10]
            a.unknown_11 = data[11]
            a.link_work_mode_code = data[13]
            a.link_work_mode = LinkWorkMode(data[13])
            a.layout_code = data[22]
            a.lte_level_a = data[23]
            a.lte_level_b = data[24]

            n = len(data)
            if n == LENGTH_O3 or (n != LENGTH_O4 and a.layout_code == 1):
                a.channel_like_19 = struct.unpack_from("<b", data, 19)[0]
            if n == LENGTH_O4:
                a.lte_fusion = bool(data[25])
                a.const_29 = data[29]
            # Unknown lengths: bytes 0-24 only; the tail is not interpreted.

        return a
