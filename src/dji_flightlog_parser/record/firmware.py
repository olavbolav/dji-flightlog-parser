"""Firmware version record parser (type 15).

The payload is a list of 6-byte entries, one per module::

    u8 device type (DUML sender type), u8 index, u8 v0, u8 v1, u8 v2, u8 v3

Logs hold 3 to 6 entries (Camera, Flight Controller, Gimbal, Remote Control,
Battery, ...). The index tells modules of the same type apart. For batteries
it is the slot. For Camera and Gimbal entries on M300/M350 it is the gimbal
port of the payload (0, 1 = port 1, 2; DJI Cloud API calls 0/1/2 portside,
starboard and upside). Matrice 4TD lists its built-in camera at 0 and, on
airframes with a top accessory (most likely the AL1 spotlight), a second
Gimbal at 2. Matrice 400 reports a single H30T at 1 or 2, so the numbering
there is not confirmed. v12 records carry one extra trailing byte, which is
ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

ENTRY_SIZE = 6


class DeviceType(IntEnum):
    """DUML device (sender) types, from o-gs/dji-firmware-tools."""
    Any = 0
    Camera = 1
    App = 2
    FlightController = 3
    Gimbal = 4
    CenterBoard = 5
    RemoteController = 6
    WifiAir = 7
    TranscoderAir = 8
    HDTransmissionAir = 9
    PC = 10
    Battery = 11
    ESC = 12
    TranscoderGround = 13
    HDTransmissionGround = 14
    UsbControllerAir = 15
    UsbControllerGround = 16
    Monocular = 17
    Binocular = 18
    FpgaAir = 19
    FpgaGround = 20
    Simulator = 21
    BaseStation = 22
    ComputingPlatform = 23
    RCBattery = 24
    IMU = 25
    GpsRtk = 26
    WifiGround = 27
    SignalConverter = 28
    PMU = 29
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, value: object) -> DeviceType:
        return cls.UNKNOWN


@dataclass
class FirmwareEntry:
    sender_type: int = 0  # DUML device type
    sender_name: str = ""  # DeviceType name
    sub_sender_type: int = 0  # module index (battery slot; gimbal port on M300/M350)
    version: str = ""  # first three version bytes (legacy format)
    full_version: str = ""  # all four version bytes

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> FirmwareEntry:
        b = data[offset:offset + ENTRY_SIZE]
        return cls(
            sender_type=b[0],
            sender_name=DeviceType(b[0]).name,
            sub_sender_type=b[1],
            version=f"{b[2]}.{b[3]}.{b[4]}",
            full_version=f"{b[2]}.{b[3]}.{b[4]}.{b[5]}",
        )


@dataclass
class Firmware:
    # First entry, kept for compatibility
    sender_type: int = 0
    sub_sender_type: int = 0
    version: str = ""
    entries: list[FirmwareEntry] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Firmware:
        f = cls()
        if len(data) < ENTRY_SIZE:
            return f

        f.entries = [
            FirmwareEntry.from_bytes(data, off)
            for off in range(0, len(data) - ENTRY_SIZE + 1, ENTRY_SIZE)
        ]
        first = f.entries[0]
        f.sender_type = first.sender_type
        f.sub_sender_type = first.sub_sender_type
        f.version = first.version

        return f
