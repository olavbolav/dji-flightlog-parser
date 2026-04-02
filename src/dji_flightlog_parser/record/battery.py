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
        if len(data) < 10:
            return b

        offset = 0
        if offset + 2 <= len(data):
            b.useful_time = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 2 <= len(data):
            b.go_home_time = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 2 <= len(data):
            b.land_time = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 2 <= len(data):
            b.go_home_battery = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 2 <= len(data):
            b.land_battery = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 4 <= len(data):
            b.safe_fly_radius = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        if offset + 4 <= len(data):
            b.volume_consume = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        if offset + 4 <= len(data):
            b.status = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        if offset + 1 <= len(data):
            b.go_home_status = data[offset]
            offset += 1
        if offset + 2 <= len(data):
            b.go_home_countdown = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 2 <= len(data):
            b.voltage = struct.unpack_from("<H", data, offset)[0] / 1000.0
            offset += 2
        if offset + 1 <= len(data):
            b.percent = data[offset]
            offset += 1

        if offset + 1 <= len(data):
            bp1 = data[offset]
            b.low_warning = _sub_byte(bp1, 0x7F)
            b.low_warning_go_home = _sub_byte(bp1, 0x80)
            offset += 1

        if offset + 1 <= len(data):
            bp2 = data[offset]
            b.serious_low_warning = _sub_byte(bp2, 0x7F)
            b.serious_low_warning_landing = _sub_byte(bp2, 0x80)

        return b
