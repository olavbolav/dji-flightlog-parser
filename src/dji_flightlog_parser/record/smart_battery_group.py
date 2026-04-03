"""Smart battery group record parser (static, dynamic, single voltage)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class SmartBatteryStatic:
    index: int = 0
    designed_capacity: int = 0
    loop_times: int = 0
    full_voltage: int = 0
    temperature: int = 0
    serial: int = 0
    life: int = 0
    battery_type: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SmartBatteryStatic:
        s = cls()
        if len(data) < 2:
            return s
        offset = 0
        s.index = data[offset]; offset += 1
        if offset + 4 <= len(data):
            s.designed_capacity = struct.unpack_from("<I", data, offset)[0]; offset += 4
        if offset + 2 <= len(data):
            s.loop_times = struct.unpack_from("<H", data, offset)[0]; offset += 2
        if offset + 4 <= len(data):
            s.full_voltage = struct.unpack_from("<I", data, offset)[0]; offset += 4
        if offset + 2 <= len(data):
            s.temperature = struct.unpack_from("<H", data, offset)[0]; offset += 2
        if offset + 2 <= len(data):
            s.serial = struct.unpack_from("<H", data, offset)[0]; offset += 2
        # skip 10+5 bytes
        offset += 15
        if offset + 8 <= len(data):
            offset += 8  # version bytes
        if offset + 1 <= len(data):
            s.life = data[offset]; offset += 1
        if offset + 1 <= len(data):
            s.battery_type = data[offset]
        return s


@dataclass
class SmartBatteryDynamic:
    index: int = 0
    current_voltage: float = 0.0
    current_current: float = 0.0
    full_capacity: int = 0
    remained_capacity: int = 0
    temperature: float = 0.0
    capacity_percent: int = 0
    cell_size: int = 0
    battery_state: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SmartBatteryDynamic:
        d = cls()
        if len(data) < 2:
            return d
        offset = 0
        d.index = data[offset]; offset += 1
        if offset + 4 <= len(data):
            d.current_voltage = struct.unpack_from("<i", data, offset)[0] / 1000.0; offset += 4
        if offset + 4 <= len(data):
            d.current_current = abs(struct.unpack_from("<i", data, offset)[0]) / 1000.0; offset += 4
        if offset + 4 <= len(data):
            d.full_capacity = struct.unpack_from("<I", data, offset)[0]; offset += 4
        if offset + 4 <= len(data):
            d.remained_capacity = struct.unpack_from("<I", data, offset)[0]; offset += 4
        if offset + 2 <= len(data):
            raw_temp = struct.unpack_from("<h", data, offset)[0]
            d.temperature = raw_temp / 10.0
            offset += 2
        if offset + 1 <= len(data):
            d.cell_size = data[offset]; offset += 1
        if offset + 1 <= len(data):
            d.capacity_percent = data[offset]; offset += 1
        if offset + 8 <= len(data):
            d.battery_state = struct.unpack_from("<Q", data, offset)[0]
        return d


@dataclass
class SmartBatterySingleVoltage:
    index: int = 0
    cell_count: int = 0
    cell_voltages: list[float] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes) -> SmartBatterySingleVoltage:
        v = cls()
        if len(data) < 2:
            return v
        v.index = data[0]
        v.cell_count = data[1]
        offset = 2
        for _ in range(v.cell_count):
            if offset + 2 <= len(data):
                raw = struct.unpack_from("<H", data, offset)[0]
                v.cell_voltages.append(raw / 1000.0)
                offset += 2
        return v


@dataclass
class SmartBatteryGroup:
    """Wrapper for the three smart battery group variants."""
    kind: int = 0  # 1=Static, 2=Dynamic, 3=SingleVoltage
    static: SmartBatteryStatic | None = None
    dynamic: SmartBatteryDynamic | None = None
    single_voltage: SmartBatterySingleVoltage | None = None

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> SmartBatteryGroup:
        if len(data) < 2:
            return cls()
        kind = data[0]
        payload = data[1:]
        if kind == 1:
            # Static records have an extra padding byte after the kind byte
            static_payload = data[2:] if len(data) > 2 else payload
            return cls(kind=1, static=SmartBatteryStatic.from_bytes(static_payload))
        elif kind == 2:
            return cls(kind=2, dynamic=SmartBatteryDynamic.from_bytes(payload))
        elif kind == 3:
            return cls(kind=3, single_voltage=SmartBatterySingleVoltage.from_bytes(payload))
        return cls(kind=kind)
