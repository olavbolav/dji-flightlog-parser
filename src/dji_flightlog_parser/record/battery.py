"""Battery record parsers (CenterBattery and SmartBattery)."""

from __future__ import annotations

import struct
from dataclasses import dataclass


def _sub_byte(byte_val: int, mask: int) -> int:
    shift = 0
    m = mask
    while m and not (m & 1):
        m >>= 1
        shift += 1
    return (byte_val & mask) >> shift


@dataclass
class CenterBattery:
    relative_capacity: int = 0
    current_pv: int = 0
    current_capacity: int = 0
    full_capacity: int = 0
    life: int = 0
    loop_num: int = 0
    error_type: int = 0
    current: int = 0
    voltage_cell1: float = 0.0
    voltage_cell2: float = 0.0
    voltage_cell3: float = 0.0
    voltage_cell4: float = 0.0
    voltage_cell5: float = 0.0
    voltage_cell6: float = 0.0
    serial_no: int = 0
    product_date: int = 0
    temperature: float = 0.0
    connect_state: int = 0
    voltage: float = 0.0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> CenterBattery:
        b = cls()
        if len(data) < 2:
            return b

        offset = 0

        if len(data) > offset:
            b.relative_capacity = data[offset]
            offset += 1

        if offset + 2 <= len(data):
            b.current_pv = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if offset + 2 <= len(data):
            b.current_capacity = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if offset + 2 <= len(data):
            b.full_capacity = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if offset + 1 <= len(data):
            b.life = data[offset]
            offset += 1

        if offset + 2 <= len(data):
            b.loop_num = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if offset + 4 <= len(data):
            b.error_type = struct.unpack_from("<I", data, offset)[0]
            offset += 4

        if offset + 2 <= len(data):
            b.current = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        # Cell voltages (6 x u16)
        for i, attr in enumerate(["voltage_cell1", "voltage_cell2", "voltage_cell3",
                                   "voltage_cell4", "voltage_cell5", "voltage_cell6"]):
            if offset + 2 <= len(data):
                raw = struct.unpack_from("<H", data, offset)[0]
                setattr(b, attr, raw / 1000.0)
                offset += 2

        if offset + 2 <= len(data):
            b.serial_no = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if offset + 2 <= len(data):
            b.product_date = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        if version >= 8:
            if offset + 2 <= len(data):
                raw_temp = struct.unpack_from("<H", data, offset)[0]
                b.temperature = raw_temp / 10.0 - 273.15
                offset += 2

            if offset + 1 <= len(data):
                b.connect_state = data[offset]
                offset += 1

        # Total voltage derived from cell sum
        b.voltage = sum([b.voltage_cell1, b.voltage_cell2, b.voltage_cell3,
                         b.voltage_cell4, b.voltage_cell5, b.voltage_cell6])

        return b


@dataclass
class SmartBattery:
    """FlyC smart battery status (record type 8, DUML flyc 0x51).

    Layout (30 bytes on M300/M350; Mavic Mini v12 writes 31, the last byte is
    a framing artefact): 0 useful_time u16, 2 go_home_time u16, 4 land_time u16,
    6 go_home_battery u16, 8 land_battery u16, 10 safe_fly_radius f32,
    14 volume_consume f32, 18 status u32, 22 go_home_status u8,
    23 go_home_countdown u8, 24 voltage u16 mV, 26 percent u8, 27 low warning,
    28 serious low warning, 29 reserved (always 0).

    Bytes 0-9 are the FlyC smart-RTH estimates (the same quantities FCCommonOSD
    type 63 carries on newer aircraft, which have no type 8):

    - ``useful_time``: remaining flight time in seconds.
    - ``go_home_time`` / ``land_time``: seconds needed to return home / to land
      from the current position and height.
    - ``go_home_battery`` / ``land_battery``: battery percent needed to return
      home / to land.

    Checked on 28 logs: ``useful_time`` reads 0 for the first 22-41 s of a
    log (median about 24 s; 152 s or the whole log in two M300 logs),
    ``land_time`` is 0 until the aircraft climbs,
    and the go-home fields are filled from the first record on M300/M350
    but stay 0 on Mavic Mini. Treat 0 as "no estimate yet".

    ``status`` is the battery warning level: 0 normal, 1 low battery (the
    charge reached the low-battery threshold), 2 critically low (it reached
    the critical threshold). Checked on 24 M300/M350 logs (9 with
    transitions): every transition happens exactly at the threshold carried
    in bytes 27/28.

    ``safe_fly_radius`` and ``volume_consume`` do not match their names
    (thousands to hundreds of thousands); their meaning is unknown.
    """

    useful_time: int = 0
    go_home_time: int = 0
    land_time: int = 0
    go_home_battery: int = 0
    land_battery: int = 0
    safe_fly_radius: float = 0.0
    volume_consume: float = 0.0
    status: int = 0
    go_home_status: int = 0
    go_home_countdown: int = 0
    voltage: float = 0.0
    percent: int = 0
    low_warning: int = 0
    low_warning_go_home: int = 0
    serious_low_warning: int = 0
    serious_low_warning_landing: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> SmartBattery:
        b = cls()
        n = len(data)
        if n < 10:
            return b

        # Fixed offsets, so a truncated record leaves the missing fields at
        # their defaults instead of shifting later fields.
        b.useful_time, b.go_home_time, b.land_time, b.go_home_battery, b.land_battery = (
            struct.unpack_from("<5H", data, 0))
        if n >= 14:
            b.safe_fly_radius = struct.unpack_from("<f", data, 10)[0]
        if n >= 18:
            b.volume_consume = struct.unpack_from("<f", data, 14)[0]
        if n >= 22:
            b.status = struct.unpack_from("<I", data, 18)[0]
        if n >= 23:
            b.go_home_status = data[22]
        # go_home_countdown is a u8 (upstream smart_battery.rs, DUML flyc 0x51).
        # Reading it as u16 shifted every later field by one byte. Checked on
        # 28 logs (M300/M350/Mavic Mini): u16@24 matches the SmartBatteryGroup
        # dynamic index-0 voltage (median |diff| 5-16 mV) and byte 26 equals
        # its SOC in all 5472 ticks where both are logged.
        if n >= 24:
            b.go_home_countdown = data[23]
        if n >= 26:
            b.voltage = struct.unpack_from("<H", data, 24)[0] / 1000.0
        if n >= 27:
            b.percent = data[26]

        # Byte 27: low-battery threshold in percent (0x7F) and the "go home at
        # low battery" action flag (0x80). Byte 28: critical threshold (0x7F)
        # and the "land at critical battery" flag (0x80). Both equal OSD bytes
        # 45/46. Corpus: low 20/25/30, critical 5/10/15/20, landing flag always
        # set, go-home flag never set. Byte 29 is reserved (always 0).
        if n >= 28:
            b.low_warning = _sub_byte(data[27], 0x7F)
            b.low_warning_go_home = _sub_byte(data[27], 0x80)
        if n >= 29:
            b.serious_low_warning = _sub_byte(data[28], 0x7F)
            b.serious_low_warning_landing = _sub_byte(data[28], 0x80)

        return b
