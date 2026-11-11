"""Camera info record parser (type 25).

The record follows the DUML camera "state info" push (cmd set 0x02, cmd 0x80)
as documented in o-gs/dji-firmware-tools, shortened after the remaining-video
field::

    0-3   u32 status bits (see below)
    4     u8  work mode
    5-8   u32 SD card total size, MB
    9-12  u32 SD card free size, MB
    13-16 u32 remaining photos
    17-20 u32 remaining video time, seconds
    21-22 u16 current recording time, seconds
    23    u8  camera type (DJI payload type code, see CAMERA_TYPE_NAMES)

Status bits used here: byte 0 = connected 0x01, USB 0x02, time synced 0x04,
photo state 0x38, record state 0xC0; byte 1 = SD card inserted 0x02, SD card
state 0x3C; byte 2 = storing 0x08. The same layout is used by the upstream
Rust dji-log-parser.

Checked on 71 logs (67 v14, 4 v12) with 67,517 camera records:
is_recording (record state != 0) matches a running recording time in all but
29 records, all with the state set while the time is still 0 (5 of them are
the one-record start state 1).
Storage fields (bytes 5-20) on the same records: SD free never exceeds SD
total, SD free drops in 29 of 30 recording runs of 3+ records, and free MB
against remaining video / photos implies a median 59 Mbit/s and 4.0 MB per
photo. SD total is 0 on Mavic Mini and on one M350 log.
Earlier versions of this parser read the connected/USB bits as photo and
recording flags and the SD bits from the wrong positions.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


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
    SuggestFormat = 13
    Repairing = 14
    BecomeSlow = 15
    Uninited = 255

    @classmethod
    def _missing_(cls, value: object) -> SDCardState:
        return cls.Uninited


class PhotoState(IntEnum):
    NONE = 0
    Single = 1
    Multiple = 2
    HDR = 3
    FullView = 4  # panorama
    Other = 6
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> PhotoState:
        return cls.UNKNOWN


# DJI payload type codes (byte 23). Sources: DJI Cloud API product support
# table and DeviceTypeEnum (dji-sdk/DJI-Cloud-API-Demo); 99 and the consumer
# codes are taken from logs of the named aircraft.
CAMERA_TYPE_NAMES: dict[int, str] = {
    20: "Zenmuse Z30",
    26: "Zenmuse XT2",
    41: "Zenmuse XT S",
    42: "Zenmuse H20",
    43: "Zenmuse H20T",
    50: "Zenmuse P1",
    52: "Matrice 30 Camera",
    53: "Matrice 30T Camera",
    61: "Zenmuse H20N",
    66: "Mavic 3E Camera",
    67: "Mavic 3T Camera",
    68: "Mavic 3M Camera",
    80: "Matrice 3D Camera",
    81: "Matrice 3TD Camera",
    82: "Zenmuse H30",
    83: "Zenmuse H30T",
    99: "Matrice 4TD Camera",
    # Seen in logs only
    44: "Mavic Mini Camera",
    96: "DJI Neo Camera",
    108: "DJI Mini 5 Pro Camera",
    115: "DJI Neo 2 Camera",
}

_SIZES = struct.Struct("<IIIIH")  # bytes 5-22
_FULL_LENGTH = 24


def camera_model_name(camera_type: Optional[int]) -> Optional[str]:
    """Return the model name for a camera type code, or None if unknown."""
    if camera_type is None:
        return None
    return CAMERA_TYPE_NAMES.get(camera_type)


@dataclass
class Camera:
    is_shooting_single_photo: bool = False  # photo state == Single
    is_recording: bool = False  # record state != 0
    is_storing: bool = False
    sd_card_state: SDCardState = SDCardState.Uninited
    has_sd_card: bool = False
    work_mode: int = 0  # 0 photo, 1 record, 2 playback, 7 new playback, ...

    is_connected: bool = False
    is_usb_connected: bool = False  # constant per platform in practice
    is_time_synced: bool = False
    photo_state: PhotoState = PhotoState.NONE
    # 0 idle, 2 recording; 1 and 3 appear for one record at the start and
    # end of a recording (names not documented)
    record_state: int = 0

    sd_card_total_mb: Optional[int] = None
    sd_card_free_mb: Optional[int] = None
    remaining_photos: Optional[int] = None
    remaining_video_seconds: Optional[int] = None
    # Seconds since the recording started. On Matrice 4TD, Matrice 400 and
    # some M350 logs it sticks at 30 s (15 s in some 4TD logs) until the
    # recording ends; use record_state for the recording status.
    record_time: Optional[int] = None
    camera_type: Optional[int] = None  # DJI payload type code of the main camera
    camera_model: Optional[str] = None

    @property
    def is_shooting_photo(self) -> bool:
        """Any photo capture in progress (single, burst, HDR, panorama...)."""
        return self.photo_state != PhotoState.NONE

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Camera:
        c = cls()
        if len(data) < 1:
            return c

        bp1 = data[0]
        c.is_connected = bool(bp1 & 0x01)
        c.is_usb_connected = bool(bp1 & 0x02)
        c.is_time_synced = bool(bp1 & 0x04)
        c.photo_state = PhotoState((bp1 >> 3) & 0x07)
        c.record_state = (bp1 >> 6) & 0x03
        c.is_shooting_single_photo = c.photo_state == PhotoState.Single
        c.is_recording = c.record_state != 0

        if len(data) > 1:
            bp2 = data[1]
            c.has_sd_card = bool(bp2 & 0x02)
            c.sd_card_state = SDCardState((bp2 >> 2) & 0x0F)

        if len(data) > 2:
            c.is_storing = bool(data[2] & 0x08)

        if len(data) > 4:
            c.work_mode = data[4]

        if len(data) >= _FULL_LENGTH:
            (c.sd_card_total_mb, c.sd_card_free_mb, c.remaining_photos,
             c.remaining_video_seconds, c.record_time) = _SIZES.unpack_from(data, 5)
            c.camera_type = data[23]
            c.camera_model = camera_model_name(c.camera_type)

        return c
