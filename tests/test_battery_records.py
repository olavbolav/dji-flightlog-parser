"""Unit tests for SmartBattery (type 8) and SmartBatteryGroup (type 22). Synthetic bytes only."""

import struct

import pytest

from dji_flightlog_parser.record.battery import SmartBattery
from dji_flightlog_parser.record.smart_battery_group import (
    SmartBatteryDynamic,
    SmartBatteryGroup,
    SmartBatterySingleVoltage,
    SmartBatteryStatic,
)


# --- SmartBattery (type 8) --------------------------------------------------

def _smart_battery(useful=1500, gh_time=60, land_time=25, gh_batt=15, land_batt=6,
                   status=0, gh_status=0, countdown=0, mv=45120, pct=64,
                   low=0x19, crit=0x8F, reserve=0, trailing=None) -> bytes:
    data = struct.pack("<HHHHHffIBBHBBBB", useful, gh_time, land_time, gh_batt, land_batt,
                       1234.5, 9876.5, status, gh_status, countdown, mv, pct, low, crit, reserve)
    assert len(data) == 30
    if trailing is not None:
        data += bytes([trailing])
    return data


def test_smart_battery_layout_after_u8_countdown():
    b = SmartBattery.from_bytes(_smart_battery())
    assert b.go_home_countdown == 0
    assert b.voltage == 45.12
    assert b.percent == 64
    assert b.low_warning == 25 and b.low_warning_go_home == 0
    assert b.serious_low_warning == 15 and b.serious_low_warning_landing == 1


def test_smart_battery_countdown_is_one_byte():
    # A non-zero countdown must not bleed into the voltage
    b = SmartBattery.from_bytes(_smart_battery(countdown=7, mv=7480, pct=81))
    assert b.go_home_countdown == 7
    assert b.voltage == 7.48
    assert b.percent == 81


def test_smart_battery_warning_flags():
    b = SmartBattery.from_bytes(_smart_battery(low=0x80 | 30, crit=20))
    assert b.low_warning == 30 and b.low_warning_go_home == 1
    assert b.serious_low_warning == 20 and b.serious_low_warning_landing == 0


def test_smart_battery_rth_estimates_and_status():
    b = SmartBattery.from_bytes(_smart_battery(status=2))
    assert (b.useful_time, b.go_home_time, b.land_time) == (1500, 60, 25)
    assert (b.go_home_battery, b.land_battery) == (15, 6)
    assert b.status == 2


def test_smart_battery_v12_trailing_byte_ignored():
    # Mavic Mini v12 writes 31 bytes; the last byte is a framing artefact
    b = SmartBattery.from_bytes(_smart_battery(mv=7300, pct=70, low=20, crit=0x85, trailing=0xA7), version=12)
    assert b.voltage == 7.3 and b.percent == 70
    assert b.low_warning == 20 and b.serious_low_warning == 5 and b.serious_low_warning_landing == 1


def test_smart_battery_short_records_do_not_raise():
    full = _smart_battery()
    for n in range(len(full)):
        SmartBattery.from_bytes(full[:n])
    b = SmartBattery.from_bytes(full[:25])  # voltage incomplete
    assert b.go_home_countdown == 0 and b.voltage == 0.0 and b.percent == 0


# --- SmartBatteryGroup static (kind 1) --------------------------------------

def _dos(year, month, day) -> int:
    return ((year - 1980) << 9) | (month << 5) | day


def _static(index=1, cap=5880, cycles=42, mv=52800, date=_dos(2023, 6, 17), serial=1234,
            life=93, pack_type=67, n=46) -> bytes:
    rec = bytes([1, 0, index]) + struct.pack("<IHIHH", cap, cycles, mv, date, serial)
    rec += b"ABC\x00\x00\x00\x00\x00" + b"\x00\x00" + b"XY123"  # 17-31
    rec += bytes([1, 0, 2, 9]) + bytes([44, 0, 3, 9])  # 32-39 loader / firmware
    rec += bytes([life, pack_type]) + b"\x00" * 4
    assert len(rec) == 46
    return rec[:n]


def test_static_manufacture_date_and_life():
    g = SmartBatteryGroup.from_bytes(_static())
    s = g.static
    assert g.kind == 1 and s is not None
    assert s.index == 1
    assert s.designed_capacity == 5880 and s.loop_times == 42 and s.full_voltage == 52800
    assert s.manufacture_date == "2023-06-17"
    assert s.serial == 1234
    assert s.life == 93 and s.battery_type == 67
    assert not hasattr(s, "temperature")


def test_static_42_byte_record():
    s = SmartBatteryGroup.from_bytes(_static(index=0, life=100, pack_type=104, n=42)).static
    assert s.index == 0 and s.life == 100 and s.battery_type == 104
    assert s.manufacture_date == "2023-06-17"


def test_static_invalid_manufacture_date_is_none():
    assert SmartBatteryGroup.from_bytes(_static(date=0)).static.manufacture_date is None
    assert SmartBatteryGroup.from_bytes(_static(date=_dos(2024, 13, 1))).static.manufacture_date is None
    assert SmartBatteryGroup.from_bytes(_static(date=_dos(2023, 2, 30))).static.manufacture_date is None


def test_static_short_records_do_not_raise():
    full = _static()
    for n in range(len(full)):
        SmartBatteryGroup.from_bytes(full[:n])
    assert SmartBatteryStatic.from_bytes(b"").manufacture_date is None


def test_static_truncated_record_does_not_shift_fields():
    # Cut inside the version bytes: state of health must stay unknown, not
    # be read from the model text
    s = SmartBatteryGroup.from_bytes(_static(n=37)).static
    assert s.life == 0 and s.battery_type == 0
    assert s.loop_times == 42 and s.manufacture_date == "2023-06-17"


# --- SmartBatteryGroup dynamic (kind 2) -------------------------------------

def _dynamic(index=0, mv=52200, ma=-21500, full=9800, rem=6300, temp=315, cells=13, soc=64,
             state=0, energy=None, n=43) -> bytes:
    rec = bytes([2, index]) + struct.pack("<iiIIhBBQ", mv, ma, full, rem, temp, cells, soc, state)
    assert len(rec) == 30
    rec += b"\x00" * 15  # 30-44
    rec = bytearray(rec)
    if energy is not None:
        struct.pack_into("<H", rec, 41, energy)
    return bytes(rec[:n])


def test_dynamic_fields_and_cell_size_at_byte_20():
    d = SmartBatteryGroup.from_bytes(_dynamic(energy=0x8000 | 2873)).dynamic
    assert d.index == 0
    assert d.current_voltage == 52.2 and d.current_current == 21.5
    assert d.full_capacity == 9800 and d.remained_capacity == 6300
    assert d.temperature == 31.5
    assert d.cell_size == 13
    assert d.capacity_percent == 64
    assert d.remaining_energy == 287.3


def test_dynamic_negative_temperature_is_signed():
    d = SmartBatteryGroup.from_bytes(_dynamic(temp=-52)).dynamic
    assert d.temperature == -5.2
    assert d.cell_size == 13 and d.capacity_percent == 64


def test_dynamic_remaining_energy_needs_flag_bit():
    # 57-byte M300/M350 aggregate: bytes 41-42 are 0
    assert SmartBatteryGroup.from_bytes(_dynamic(energy=0, n=45)).dynamic.remaining_energy is None
    assert SmartBatteryGroup.from_bytes(_dynamic(energy=2873)).dynamic.remaining_energy is None


def test_dynamic_remaining_energy_needs_long_record():
    # 39/41-byte (M4TD) and 35-byte (M300/M350 per pack) records end before byte 41
    for n in (35, 39, 41, 42):
        rec = _dynamic(energy=0x8000 | 2873, n=45)[:n]
        d = SmartBatteryGroup.from_bytes(rec).dynamic
        assert d.remaining_energy is None
        assert d.cell_size == 13


def test_dynamic_truncated_record_does_not_shift_fields():
    d = SmartBatteryGroup.from_bytes(_dynamic(n=8)).dynamic
    assert d.current_voltage == 52.2
    assert d.current_current == 0.0 and d.temperature == 0.0 and d.cell_size == 0


def test_dynamic_short_records_do_not_raise():
    full = _dynamic(energy=0x8000 | 100, n=45)
    for n in range(len(full)):
        SmartBatteryGroup.from_bytes(full[:n])
    assert SmartBatteryDynamic.from_bytes(b"").remaining_energy is None


@pytest.mark.parametrize("n", [0, 1, 2, 5, 19, 20])
def test_dynamic_payload_without_state_of_charge_is_truncated(n):
    # The state of charge is payload byte 20: a shorter payload (a log cut
    # off inside the record) reads 0 for it and every later field
    payload = _dynamic(soc=64, n=45)[1:1 + n]
    assert len(payload) == n
    assert SmartBatteryDynamic.from_bytes(payload).is_truncated


@pytest.mark.parametrize("n", [21, 34, 44])
def test_dynamic_payload_with_state_of_charge_is_not_truncated(n):
    # 21 = threshold, 34 = shortest corpus payload (M300/M350 pack), 44 = full
    d = SmartBatteryDynamic.from_bytes(_dynamic(soc=64, n=45)[1:1 + n])
    assert not d.is_truncated and d.capacity_percent == 64


def test_dynamic_one_byte_payload_is_truncated_with_default_index():
    g = SmartBatteryGroup.from_bytes(bytes([2, 5]))
    assert g.dynamic.index == 0 and g.dynamic.is_truncated


# --- SmartBatteryGroup single voltage (kind 3) ------------------------------

def _cells(mvs) -> bytes:
    return b"".join(struct.pack("<H", v) for v in mvs)


M400_CELLS = [3790 + i for i in range(13)]


def test_single_voltage_standard_layout():
    rec = bytes([3, 0, 13]) + _cells(M400_CELLS)
    assert len(rec) == 29
    sv = SmartBatteryGroup.from_bytes(rec).single_voltage
    assert (sv.index, sv.cell_count, sv.is_truncated) == (0, 13, False)
    assert sv.cell_voltages == [v / 1000 for v in M400_CELLS]


def test_single_voltage_two_byte_header_variant():
    # M400 30-byte variant: [kind][0][index 0][count][cells]
    rec = bytes([3, 0, 0, 13]) + _cells(M400_CELLS)
    assert len(rec) == 30
    sv = SmartBatteryGroup.from_bytes(rec).single_voltage
    assert (sv.index, sv.cell_count, sv.is_truncated) == (0, 13, False)
    assert sv.cell_voltages == [v / 1000 for v in M400_CELLS]


def test_single_voltage_variant_dual_battery_pack_index():
    # M300/M350 28-byte variant carries the pack index (1)
    cells = [3600 + i for i in range(12)]
    rec = bytes([3, 0, 1, 12]) + _cells(cells)
    assert len(rec) == 28
    sv = SmartBatteryGroup.from_bytes(rec).single_voltage
    assert (sv.index, sv.cell_count) == (1, 12)
    assert sv.cell_voltages == [v / 1000 for v in cells]


def test_single_voltage_variant_m4td_16_bytes():
    cells = [3700 + i for i in range(6)]
    sv = SmartBatteryGroup.from_bytes(bytes([3, 0, 0, 6]) + _cells(cells)).single_voltage
    assert sv.cell_count == 6 and sv.cell_voltages == [v / 1000 for v in cells]


def test_single_voltage_m4td_truncated_record():
    # Count says 6 but only cell 1 follows. The payload length (5) fits the
    # 2-byte-header variant only when the low byte of cell 1 is 1 (0x0E01 =
    # 3585 mV), and then both guards reject it: the index guard (payload
    # byte 1 = 6 > 2) and the count guard (payload byte 2 = 1 < 2).
    rec = bytes([3, 0, 6]) + struct.pack("<H", 3585) + b"\x00"
    assert len(rec) == 6
    sv = SmartBatteryGroup.from_bytes(rec).single_voltage
    assert (sv.index, sv.cell_count) == (0, 6)
    assert sv.cell_voltages == [3.585]
    assert sv.is_truncated


def test_single_voltage_truncated_six_cell_record_needs_index_guard():
    # 6-cell pack, count 6 but only cells 1-2 and a trailing byte follow.
    # Payload [0, 6, 0x02, 0x0E, 0x10, 0x0E, 0] fits the variant length with
    # count 2 (low byte of cell 1) and passes the count guard; only the index
    # guard (payload byte 1 = 6 > 2) keeps it standard.
    rec = bytes([3, 0, 6]) + struct.pack("<HH", 0x0E02, 0x0E10) + b"\x00"
    sv = SmartBatteryGroup.from_bytes(rec, version=14).single_voltage
    assert (sv.index, sv.cell_count, len(sv.cell_voltages), sv.is_truncated) == (0, 6, 2, True)
    assert sv.cell_voltages == [3.586, 3.6]


def test_single_voltage_truncated_two_cell_record_is_not_the_variant():
    # 2S pack, count 2 but only cell 1 follows. Payload [0, 2, 0x01, 0x0E, 0]
    # passes the variant's index guard (2 <= 2) and fits its length with
    # count 1; only the count guard (payload byte 2 >= 2) keeps it standard.
    rec = bytes([3, 0, 2]) + struct.pack("<H", 0x0E01) + b"\x00"
    sv = SmartBatteryGroup.from_bytes(rec, version=14).single_voltage
    assert (sv.index, sv.cell_count, sv.is_truncated) == (0, 2, True)
    assert sv.cell_voltages == [3.585]


def test_single_voltage_two_cells():
    sv = SmartBatteryGroup.from_bytes(bytes([3, 0, 2]) + _cells([3801, 3799])).single_voltage
    assert (sv.cell_count, sv.cell_voltages, sv.is_truncated) == (2, [3.801, 3.799], False)


def test_single_voltage_v12_padded_record_is_not_the_variant():
    # Mavic Mini v12: [kind][0][2][2 cells][2 empty slots][trailing byte]. Cell 1
    # = 0x0E04 has low byte 4, so the length would fit the variant with count 4.
    rec = bytes([3, 0, 2]) + _cells([3588, 3800, 0, 0]) + b"\x5a"
    assert len(rec) == 12
    sv = SmartBatteryGroup.from_bytes(rec, version=12).single_voltage
    assert (sv.index, sv.cell_count) == (0, 2)
    assert sv.cell_voltages == [3.588, 3.8]


def test_single_voltage_short_records_do_not_raise():
    full = bytes([3, 0, 0, 13]) + _cells(M400_CELLS)
    for n in range(len(full)):
        SmartBatteryGroup.from_bytes(full[:n])
    assert SmartBatterySingleVoltage.from_bytes(b"\x00").cell_voltages == []


def test_group_unknown_kind():
    g = SmartBatteryGroup.from_bytes(bytes([9, 1, 2, 3]))
    assert g.kind == 9 and g.static is None and g.dynamic is None and g.single_voltage is None
