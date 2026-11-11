"""Smart battery group record parser (static, dynamic, single voltage).

Record type 22. Byte 0 of the record is the kind (1 static, 2 dynamic,
3 single cell voltages). Offsets in the comments below are record offsets,
i.e. they count the kind byte.
"""

from __future__ import annotations

import datetime
import struct
from dataclasses import dataclass, field
from typing import Optional


def _dos_date(raw: int) -> Optional[str]:
    """Decode a DOS date (day bits 0-4, month bits 5-8, year bits 9-15 + 1980)."""
    day = raw & 0x1F
    month = (raw >> 5) & 0x0F
    year = (raw >> 9) + 1980
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


@dataclass
class SmartBatteryStatic:
    """Static pack data (kind 1), logged once per flight at log start.

    Same layout as the DUML battery static data, shifted by one byte (record
    offset = DUML payload offset + 1): 2 index, 3 designed capacity u32 mAh,
    7 cycle count u16, 9 designed voltage u32 mV, 13 manufacture date (DOS
    date), 15 serial u16, 17-24 cell vendor ASCII, 25-26 unknown, 27-31 model
    ASCII, 32-35 loader version, 36-39 firmware version, 40 state of health,
    41 pack type code. Records are 42 or 46 bytes (43 on Mavic Mini v12).

    On dual-battery aircraft (M30/M300/M350) only one static record is logged
    per flight, for pack 1 or pack 2 (``index``).
    """

    index: int = 0
    designed_capacity: int = 0
    loop_times: int = 0
    full_voltage: int = 0
    # Bytes 13-14 were read as "temperature" before. They are the pack
    # manufacture date (DUML static dissector manufacture_date). Checked on
    # all 73 static records: every one decodes to a valid date and the years
    # match the battery generations (Mavic Mini 2019 ... M400/Neo 2 2025).
    manufacture_date: Optional[str] = None
    serial: int = 0
    # State of health in percent (DUML "State of Health (%)", upstream
    # battery_life). This is the BMS's own figure: 0 means unknown (Mini 5
    # Pro always reports 0), and TB30/TB65 packs appear to saturate at 100.
    life: int = 0
    battery_type: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SmartBatteryStatic:
        """Parse the static payload (the record without its 2-byte kind header)."""
        s = cls()
        n = len(data)
        if n < 2:
            return s
        # Fixed payload offsets (record offset - 2), so a truncated record
        # leaves the missing fields at their defaults.
        s.index = data[0]
        if n >= 5:
            s.designed_capacity = struct.unpack_from("<I", data, 1)[0]
        if n >= 7:
            s.loop_times = struct.unpack_from("<H", data, 5)[0]
        if n >= 11:
            s.full_voltage = struct.unpack_from("<I", data, 7)[0]
        if n >= 13:
            s.manufacture_date = _dos_date(struct.unpack_from("<H", data, 11)[0])
        if n >= 15:
            s.serial = struct.unpack_from("<H", data, 13)[0]
        # 15-29 cell vendor, unknown, model; 30-37 loader and firmware version
        if n >= 39:
            s.life = data[38]
        if n >= 40:
            s.battery_type = data[39]
        return s


@dataclass
class SmartBatteryDynamic:
    """Dynamic pack data (kind 2).

    Record offsets: 1 index, 2 voltage i32 mV, 6 current i32 mA, 10 full
    capacity u32 mAh, 14 remaining capacity u32 mAh, 18 temperature i16
    0.1 degC, 20 cell count, 21 state of charge %, 22 state bits u64,
    41 remaining energy (43/45-byte records). ``is_truncated`` marks
    records that end before the state of charge.

    ``index`` is 0 on single-battery aircraft. On dual-battery aircraft
    (M30/M300/M350) index 0 is the aggregate of both packs and 1/2 are the
    individual packs.
    """

    index: int = 0
    current_voltage: float = 0.0
    current_current: float = 0.0
    full_capacity: int = 0
    remained_capacity: int = 0
    temperature: float = 0.0
    capacity_percent: int = 0
    # Byte 20. Checked on all v14 records: 13 on M400, 6 on M4TD, 2 on
    # Mini 5 Pro/Neo/Neo 2, 12 on M300/M350, 6 on M30. Not reliable on v12
    # (one Mavic Mini log reads 3 for a 2S pack).
    cell_size: int = 0
    battery_state: int = 0
    # Remaining energy in Wh: (u16@41 & 0x7FFF) / 10, valid when bit 15 is
    # set. Checked on all 43/45-byte records (M400, M30, Mini 5 Pro, Neo,
    # Neo 2): bit 15 is always set and the value tracks remaining mAh. The
    # 57-byte M300/M350 aggregate and the v12 138-byte record carry 0 there.
    # It is a BMS estimate (it scales with voltage x remaining capacity).
    remaining_energy: Optional[float] = None
    # Payload shorter than 21 bytes: it ends before the state of charge
    # (payload byte 20), the last field the frames need on every family
    # (remaining_energy is optional), so the missing fields read 0. Such a
    # record comes from a log cut off inside it (the reader keeps truncated
    # payloads); every dynamic payload in the 74-log corpus is 34-137 bytes.
    is_truncated: bool = False

    @classmethod
    def from_bytes(cls, data: bytes) -> SmartBatteryDynamic:
        """Parse the dynamic payload (the record without its kind byte)."""
        d = cls()
        n = len(data)
        d.is_truncated = n < 21
        if n < 2:
            return d
        # Fixed payload offsets (record offset - 1), so a truncated record
        # leaves the missing fields at their defaults.
        d.index = data[0]
        if n >= 5:
            d.current_voltage = struct.unpack_from("<i", data, 1)[0] / 1000.0
        if n >= 9:
            d.current_current = abs(struct.unpack_from("<i", data, 5)[0]) / 1000.0
        if n >= 13:
            d.full_capacity = struct.unpack_from("<I", data, 9)[0]
        if n >= 17:
            d.remained_capacity = struct.unpack_from("<I", data, 13)[0]
        if n >= 19:
            d.temperature = struct.unpack_from("<h", data, 17)[0] / 10.0
        if n >= 20:
            d.cell_size = data[19]
        if n >= 21:
            d.capacity_percent = data[20]
        if n >= 29:
            d.battery_state = struct.unpack_from("<Q", data, 21)[0]
        # Record offset 41 = payload offset 40
        if n >= 42:
            raw_energy = struct.unpack_from("<H", data, 40)[0]
            if raw_energy & 0x8000:
                d.remaining_energy = (raw_energy & 0x7FFF) / 10.0
        return d


@dataclass
class SmartBatterySingleVoltage:
    """Per-cell voltages (kind 3).

    Two layouts exist:

    - standard ``[kind][index][count][count x u16 mV]`` (M400 29 bytes,
      M4TD 15, Mini 5 Pro/Neo/Neo 2 7; Mavic Mini v12 writes 12 bytes with
      four cell slots and a trailing byte);
    - a variant with a 2-byte header ``[kind][0][index][count][cells]``
      (M400 30 bytes, M4TD 16, M300/M350 28). The DUML cell-voltage dissector
      documents the same variant. Before, the parser read count 0 (M400/M4TD)
      or a garbage cell (M300/M350) from these.

    M4TD also writes a truncated 6-byte record whose count says 6 but only
    cell 1 follows; ``cell_voltages`` then holds fewer than ``cell_count``
    values and ``is_truncated`` is set. Its single value matches cell 1 of
    the neighbouring full record (median diff 0 mV).

    ``index`` is 0 on single-battery aircraft; the M300/M350 variant records
    carry index 1 (pack 1).
    """

    index: int = 0
    cell_count: int = 0
    cell_voltages: list[float] = field(default_factory=list)
    is_truncated: bool = False

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> SmartBatterySingleVoltage:
        """Parse the cell payload (the record without its kind byte)."""
        v = cls()
        if len(data) < 2:
            return v
        offset = 2
        v.index = data[0]
        v.cell_count = data[1]
        # The 2-byte-header variant: payload length is exactly 3 + 2*count
        # with count at payload byte 2. Checked on the corpus: 8159 M400,
        # 46 M4TD and 2 M300/M350 records. Not seen on v12, where padded
        # 12-byte records could match by chance.
        # - The "not the standard length" clause is defensive only: a variant
        #   payload has odd length (3 + 2n) and a standard one even length
        #   (2 + 2n), so it can never decide on its own.
        # - index (payload byte 1) <= 2 rejects truncated records of packs
        #   with more than 2 cells whose cell-1 low byte happens to fit the
        #   variant length (e.g. 6 cells, 2 present, low byte 2).
        # - count (payload byte 2) >= 2 rejects truncated records of packs
        #   with 2 or fewer cells, whose payload byte 2 is the low byte of
        #   cell 1 and can be 1.
        # - Both reject the 6-byte truncated M4TD record (count 6, one
        #   cell): its payload length fits the variant only when cell 1's
        #   low byte is 1, and then the count guard rejects it as well.
        if (
            version >= 13
            and len(data) != 2 + 2 * data[1]
            and len(data) >= 4
            and data[0] == 0
            and data[1] <= 2
            and data[2] >= 2
            and len(data) == 3 + 2 * data[2]
        ):
            v.index = data[1]
            v.cell_count = data[2]
            offset = 3
        for _ in range(v.cell_count):
            if offset + 2 <= len(data):
                raw = struct.unpack_from("<H", data, offset)[0]
                v.cell_voltages.append(raw / 1000.0)
                offset += 2
        v.is_truncated = len(v.cell_voltages) < v.cell_count
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
            return cls(kind=3, single_voltage=SmartBatterySingleVoltage.from_bytes(payload, version))
        return cls(kind=kind)
