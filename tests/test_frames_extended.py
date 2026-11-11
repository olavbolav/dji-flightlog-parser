"""Frame wiring: default schema, battery selection (B2/B3), extended keys and summary.

All records are synthetic dataclass instances; no bytes from real logs.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import struct
from types import SimpleNamespace

import pytest

from dji_flightlog_parser.export.csv_export import HEADERS, export_csv
from dji_flightlog_parser.frame.builder import battery_layout, is_valid_dynamic, records_to_frames
from dji_flightlog_parser.frame.models import FrameAppGPS
from dji_flightlog_parser.layout.details import Details, ProductType
from dji_flightlog_parser.parser import _build_summary
from dji_flightlog_parser.record.adsb import ADSBAircraft, ADSBFlightData
from dji_flightlog_parser.record.app import AppGPS
from dji_flightlog_parser.record.battery import SmartBattery
from dji_flightlog_parser.record.camera import Camera
from dji_flightlog_parser.record.fc_common_osd import FCCommonOSD
from dji_flightlog_parser.record.gimbal import Gimbal
from dji_flightlog_parser.record.home import Home
from dji_flightlog_parser.record.key_value_snapshot import KeyValueSnapshot
from dji_flightlog_parser.record.mc_params import FailSafe, MCParams
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.rc_display import RCDisplayField
from dji_flightlog_parser.record.reader import Record
from dji_flightlog_parser.record.recover import Recover
from dji_flightlog_parser.record.smart_battery_group import (
    SmartBatteryDynamic, SmartBatteryGroup, SmartBatterySingleVoltage, SmartBatteryStatic,
)
from dji_flightlog_parser.record.types import RecordType
from dji_flightlog_parser.record.vision import VisionGroup


# --- helpers ------------------------------------------------------------------

def _osd(**kw) -> Record:
    return Record(RecordType.OSD, dataclasses.replace(OSD.from_bytes(bytes(60)), **kw))


def _dyn(index, voltage=45.0, current=10.0, full=10000, remained=6000, temp=25.0, cells=12,
         soc=60, energy=None) -> Record:
    d = SmartBatteryDynamic(index=index, current_voltage=voltage, current_current=current,
                            full_capacity=full, remained_capacity=remained, temperature=temp,
                            capacity_percent=soc, cell_size=cells, remaining_energy=energy)
    return Record(RecordType.SmartBatteryGroup, SmartBatteryGroup(kind=2, dynamic=d))


def _static(index, cycles=40, capacity=5880, life=97, date="2024-03-05") -> Record:
    s = SmartBatteryStatic(index=index, loop_times=cycles, designed_capacity=capacity, life=life,
                           manufacture_date=date)
    return Record(RecordType.SmartBatteryGroup, SmartBatteryGroup(kind=1, static=s))


def _cells(index, values, count=None, truncated=False) -> Record:
    sv = SmartBatterySingleVoltage(index=index, cell_count=count or len(values),
                                   cell_voltages=list(values), is_truncated=truncated)
    return Record(RecordType.SmartBatteryGroup, SmartBatteryGroup(kind=3, single_voltage=sv))


def _frames(records, extended=False, **kw):
    return [f.to_dict() for f in records_to_frames(records, extended=extended, **kw)]


DEFAULT_KEYS = {
    "custom": ["dateTime"],
    "osd": ["flyTime", "latitude", "longitude", "height", "heightMax", "vpsHeight", "altitude",
            "xSpeed", "xSpeedMax", "ySpeed", "ySpeedMax", "zSpeed", "zSpeedMax", "pitch", "roll",
            "yaw", "flycState", "flycCommand", "flightAction", "isGpdUsed", "nonGpsCause", "gpsNum",
            "gpsLevel", "droneType", "isSwaveWork", "waveError", "goHomeStatus", "batteryType",
            "isOnGround", "isMotorOn", "isMotorBlocked", "motorStartFailedCause", "isImuPreheated",
            "imuInitFailReason", "isAcceletorOverRange", "isBarometerDeadInAir", "isCompassError",
            "isGoHomeHeightModified", "canIocWork", "isNotEnoughForce", "isOutOfLimit",
            "isPropellerCatapult", "isVibrating", "isVisionUsed", "voltageWarning"],
    "gimbal": ["mode", "pitch", "roll", "yaw", "isPitchAtLimit", "isRollAtLimit", "isYawAtLimit",
               "isStuck"],
    "camera": ["isPhoto", "isVideo", "sdCardIsInserted", "sdCardState"],
    "rc": ["downlinkSignal", "uplinkSignal", "aileron", "elevator", "throttle", "rudder"],
    "battery": ["chargeLevel", "voltage", "current", "currentCapacity", "fullCapacity", "cellNum",
                "isCellVoltageEstimated", "cellVoltages", "cellVoltageDeviation",
                "maxCellVoltageDeviation", "temperature", "minTemperature", "maxTemperature",
                "cycleCount", "designedCapacity", "batterySerial"],
    "home": ["latitude", "longitude", "altitude", "heightLimit", "isHomeRecord", "goHomeMode",
             "isDynamicHomePointEnabled", "isNearDistanceLimit", "isNearHeightLimit",
             "isCompassCalibrating", "compassCalibrationState", "isMultipleModeEnabled",
             "isBeginnerMode", "isIocEnabled", "iocMode", "goHomeHeight", "iocCourseLockAngle",
             "maxAllowedHeight", "currentFlightRecordIndex"],
    "recover": ["appPlatform", "appVersion", "aircraftName", "aircraftSn", "cameraSn", "rcSn",
                "batterySn"],
    "app": ["tip", "warn"],
    "appGps": ["latitude", "longitude", "horizontalAccuracy", "altitude"],
    "vision": ["collisionAvoidanceEnabled", "isBraking", "isAscentLimited",
               "isLandingConfirmationNeeded"],
    "flightController": ["remainingFlightTime", "batteryPercentNeededToLand",
                         "batteryPercentNeededToGoHome"],
}

EXTENDED_KEYS = {
    "osd": ["windSpeed", "windDirection", "positionSource", "positionSourceCode", "yawRate",
            "homeOffsetNorth", "homeOffsetEast"],
    "gimbal": ["yawRelativeToAircraft", "jointPitch", "isResetting"],
    "camera": ["workMode", "sdCardTotalMb", "sdCardFreeMb", "remainingPhotos",
               "remainingVideoSeconds"],
    "rc": ["isShutterHalfPressed", "isShutterPressed", "isRecordPressed", "isCustomButton1Pressed",
           "isCustomButton2Pressed", "leftDial", "rightDial"],
    "battery": ["stateOfHealth", "remainingEnergy", "lowWarningThreshold",
                "criticalWarningThreshold", "packs"],
    "vision": ["isNearGround"],
    "flightController": ["timeNeededToGoHome", "timeNeededToLand", "rcLostAction"],
}

NEARBY_DEFAULT = ["icaoAddress", "latitude", "longitude", "altitude", "heading"]
NEARBY_EXTENDED = ["distance", "relativeAltitude", "verticalTrend", "warningLevel", "altitudeType"]


def _adsb() -> Record:
    a = ADSBAircraft(icao_address="ABC123", latitude=1.0, longitude=2.0, altitude=900, heading=90.0,
                     warning_level=2, altitude_type=1, relative_altitude=-40, vertical_trend=2,
                     distance=1500)
    return Record(RecordType.ADSBFlightData, ADSBFlightData(aircraft=[a]))


# --- output policy ------------------------------------------------------------

def test_default_frame_key_set_is_unchanged_except_app_gps_altitude():
    frame = _frames([_osd(), _adsb(), _osd()])[1]
    assert list(frame) == list(DEFAULT_KEYS) + ["nearbyAircraft"]
    for section, keys in DEFAULT_KEYS.items():
        assert list(frame[section]) == keys, section
    assert list(frame["nearbyAircraft"][0]) == NEARBY_DEFAULT


def test_extended_frames_add_keys_to_existing_sections():
    frame = _frames([_osd(), _adsb(), _osd()], extended=True)[1]
    for section, keys in DEFAULT_KEYS.items():
        assert list(frame[section]) == keys + EXTENDED_KEYS.get(section, []), section
    assert list(frame["nearbyAircraft"][0]) == NEARBY_DEFAULT + NEARBY_EXTENDED
    assert {"rtk", "airLink", "navigation", "appHud", "secondaryGimbal"} <= set(frame)


# md5 of "\n".join(HEADERS) in the pre-change baseline (112 columns)
_BASELINE_CSV_HEADERS_MD5 = "92c69e94685d6ff17bd749f4962c3740"


def test_csv_columns_unchanged_with_extended_frames():
    frames = records_to_frames([_osd(), _adsb(), _osd()], extended=True)
    rows = list(csv.reader(io.StringIO(export_csv(frames))))
    assert hashlib.md5("\n".join(rows[0]).encode()).hexdigest() == _BASELINE_CSV_HEADERS_MD5
    assert rows[0] == HEADERS and len(HEADERS) == 112
    assert all(len(row) == len(HEADERS) for row in rows[1:])
    assert not any(h.startswith(("APPGPS.altitude", "OSD.wind")) for h in HEADERS)


# --- B2 dual battery ----------------------------------------------------------

def test_dual_battery_frames_use_the_aggregate_and_list_packs():
    records = [
        _osd(),
        _dyn(1, voltage=45.10, current=5.0, full=5800, remained=3500, temp=24.0, soc=60),
        _dyn(0, voltage=45.12, current=10.1, full=11600, remained=6900, temp=25.5, soc=59),
        _dyn(2, voltage=45.14, current=5.1, full=5800, remained=3400, temp=25.5, soc=58),
        _osd(),
    ]
    plain = _frames(records)[0]["battery"]
    assert plain["fullCapacity"] == 11600 and plain["currentCapacity"] == 6900
    assert plain["chargeLevel"] == 59 and plain["voltage"] == 45.12 and plain["temperature"] == 25.5
    assert "packs" not in plain
    ext = _frames(records, extended=True)[0]["battery"]
    assert [p["index"] for p in ext["packs"]] == [1, 2]
    assert ext["packs"][0] == {"index": 1, "chargeLevel": 60, "voltage": 45.10, "current": 5.0,
                               "currentCapacity": 3500, "fullCapacity": 5800, "temperature": 24.0}
    assert ext["packs"][1]["fullCapacity"] + ext["packs"][0]["fullCapacity"] == ext["fullCapacity"]


def test_pack_1_stands_in_until_the_first_aggregate_record():
    records = [
        _osd(),
        _dyn(1, voltage=45.10, current=5.0, full=5800, remained=3500, temp=24.0, soc=60),
        _osd(),
        _dyn(1, voltage=45.08, current=5.0, full=5800, remained=3490, temp=24.5, soc=59),
        _dyn(0, voltage=45.12, current=10.1, full=11600, remained=6900, temp=25.5, soc=58),
        _dyn(1, voltage=45.00, current=5.0, full=5800, remained=3480, temp=24.0, soc=57),
        _osd(),
        _dyn(1, voltage=44.90, current=5.0, full=5800, remained=3470, temp=24.0, soc=56),
        _osd(),
        _dyn(0, voltage=45.02, current=10.0, full=11600, remained=6800, temp=26.5, soc=57),
        _osd(),
    ]
    frames = [f["battery"] for f in _frames(records)]
    # Before the aggregate: pack-1 SOC, voltage and temperature; per-pack values stay 0
    assert (frames[0]["chargeLevel"], frames[0]["voltage"], frames[0]["temperature"]) == (60, 45.10, 24.0)
    assert (frames[0]["current"], frames[0]["currentCapacity"], frames[0]["fullCapacity"]) == (0.0, 0, 0)
    assert (frames[0]["minTemperature"], frames[0]["maxTemperature"]) == (24.0, 24.0)
    # From the first aggregate record on, pack 1 never overrides it, and the
    # min/max temperature restart from the aggregate
    for b in frames[1:3]:
        assert (b["chargeLevel"], b["voltage"], b["temperature"]) == (58, 45.12, 25.5)
        assert (b["current"], b["currentCapacity"], b["fullCapacity"]) == (10.1, 6900, 11600)
        assert (b["minTemperature"], b["maxTemperature"]) == (25.5, 25.5)
    assert (frames[3]["minTemperature"], frames[3]["maxTemperature"]) == (25.5, 26.5)  # restart once only
    ext = _frames(records, extended=True)
    assert ext[0]["battery"]["packs"][0]["chargeLevel"] == 60
    assert ext[2]["battery"]["packs"][0]["chargeLevel"] == 56
    assert ext[3]["battery"]["packs"][0]["chargeLevel"] == 56


def test_pack_2_and_invalid_records_do_not_stand_in():
    pack2 = _frames([_osd(), _dyn(2, soc=50), _osd(), _dyn(0, soc=58), _osd()])[0]["battery"]
    assert pack2["chargeLevel"] == 0 and pack2["voltage"] == 0.0
    invalid = _frames([_osd(), _dyn(1, voltage=150.0, soc=55), _osd(), _dyn(0, soc=58), _osd()])
    assert invalid[0]["battery"]["chargeLevel"] == 0 and invalid[1]["battery"]["chargeLevel"] == 58


def test_dual_battery_without_aggregate_uses_pack_1():
    records = [_osd(), _dyn(2, full=5700, soc=50), _dyn(1, full=5800, soc=55), _osd()]
    assert battery_layout(records).dynamic_index == 1
    battery = _frames(records)[0]["battery"]
    assert battery["fullCapacity"] == 5800 and battery["chargeLevel"] == 55


def test_single_battery_keeps_index_0_and_has_no_packs():
    records = [_osd(), _dyn(0, cells=13, energy=512.3, soc=77), _osd()]
    layout = battery_layout(records)
    assert layout.dynamic_index == 0 and not layout.has_packs
    battery = _frames(records, extended=True)[0]["battery"]
    assert battery["chargeLevel"] == 77 and battery["remainingEnergy"] == pytest.approx(512.3)
    assert battery["packs"] is None


@pytest.mark.parametrize("voltage, temp", [
    (11011.0, 1024.0),  # the corrupt M350 pattern
    (100.5, 25.0),  # voltage bound alone
    (45.0, 150.5),  # temperature bound alone
    (45.0, -50.5),
])
def test_corrupt_dynamic_records_are_dropped(voltage, temp):
    records = [
        _osd(),
        _dyn(0, voltage=45.0, soc=60),
        _dyn(0, voltage=voltage, cells=12, temp=temp, soc=255),
        _osd(),
    ]
    battery = _frames(records)[0]["battery"]
    assert battery["voltage"] == 45.0 and battery["temperature"] == 25.0 and battery["chargeLevel"] == 60


@pytest.mark.parametrize("voltage, temp", [(100.0, 25.0), (-100.0, 25.0), (45.0, 150.0), (45.0, -50.0)])
def test_dynamic_plausibility_bounds_are_inclusive(voltage, temp):
    d = SmartBatteryDynamic(current_voltage=voltage, temperature=temp, cell_size=12)
    assert is_valid_dynamic(d)


@pytest.mark.parametrize("cells", [0, 1, 40])
def test_dynamic_record_with_implausible_cell_count_still_feeds_the_frame(cells):
    # Byte 20 is unreliable on v12; it only sizes the pack (see
    # battery_layout), it does not reject the record
    records = [_osd(), _dyn(0, voltage=15.2, current=3.0, temp=31.2, cells=cells, soc=66), _osd()]
    assert battery_layout(records, 14).dynamic_index == 0
    assert battery_layout(records, 14).cell_num is None
    battery = _frames(records, version=14)[0]["battery"]
    assert (battery["chargeLevel"], battery["voltage"], battery["current"], battery["temperature"]) == (
        66, 15.2, 3.0, 31.2)
    assert battery["cellNum"] == 4  # ProductType NONE fallback, not the dynamic byte


@pytest.mark.parametrize("indices, expected", [((2,), 2), ((2, 1), 1), ((0,), 0)])
def test_static_record_selection(indices, expected):
    records = [_osd()] + [_static(i, cycles=10 + i, capacity=5000 + i, life=90 + i) for i in indices] + [_osd()]
    battery = _frames(records, extended=True)[0]["battery"]
    assert battery["cycleCount"] == 10 + expected
    assert battery["designedCapacity"] == 5000 + expected
    assert battery["stateOfHealth"] == 90 + expected


def test_state_of_health_zero_is_unknown():
    battery = _frames([_osd(), _static(0, life=0), _osd()], extended=True)[0]["battery"]
    assert battery["stateOfHealth"] is None and battery["cycleCount"] == 40


def test_cells_come_from_one_pack():
    # Pack-2 cells (index 2) never reach the frame; pack 1 does
    records = [_osd(), _dyn(0), _cells(2, [3.70] * 12), _cells(1, [3.80] * 12), _cells(2, [3.60] * 12), _osd()]
    battery = _frames(records)[0]["battery"]
    assert battery["cellVoltages"] == [3.80] * 12 and battery["isCellVoltageEstimated"] is False


def test_cells_prefer_index_0_over_index_1():
    records = [_osd(), _cells(1, [3.70] * 6), _cells(0, [3.90] * 4), _cells(1, [3.71] * 6), _osd()]
    layout = battery_layout(records)
    assert (layout.cell_index, layout.cell_num) == (0, 4)
    assert _frames(records)[0]["battery"]["cellVoltages"] == [3.90] * 4


def test_pack_2_cells_alone_are_not_used():
    records = [_osd(), _dyn(0, voltage=48.0), _cells(2, [3.70] * 12), _osd()]
    layout = battery_layout(records)
    assert layout.cell_index is None and layout.cell_num == 12  # still sizes the pack
    battery = _frames(records)[0]["battery"]
    assert battery["isCellVoltageEstimated"] is True and battery["cellVoltages"] == [4.0] * 12


def test_packs_are_listed_in_index_order():
    records = [_osd(), _dyn(2, soc=50), _dyn(1, soc=55), _dyn(0, soc=52), _osd()]
    assert [p["index"] for p in _frames(records, extended=True)[0]["battery"]["packs"]] == [1, 2]


def test_packs_present_with_aggregate_and_pack_1_only():
    # Two M30 logs only have dynamic indices 0 and 1
    records = [_osd(), _dyn(0, soc=52), _dyn(1, soc=55), _osd()]
    layout = battery_layout(records)
    assert layout.has_packs and layout.dynamic_index == 0
    assert [p["index"] for p in _frames(records, extended=True)[0]["battery"]["packs"]] == [1]


def _dyn_bytes(index, mv, temp_dc, soc, n=None) -> Record:
    # Synthetic 45-byte dynamic record, parsed as the reader would, cut to a
    # payload of n bytes (a log that ends inside the record)
    rec = bytes([2, index]) + struct.pack("<iiIIhBB", mv, -3000, 2450, 1600, temp_dc, 4, soc)
    rec += bytes(45 - len(rec))
    if n is not None:
        rec = rec[:1 + n]
    return Record(RecordType.SmartBatteryGroup, SmartBatteryGroup.from_bytes(rec, version=12))


@pytest.mark.parametrize("n", [1, 2, 5, 19, 20])
def test_truncated_dynamic_record_does_not_zero_the_frame(n):
    records = [_osd(), _dyn_bytes(0, 15200, 300, 66), _osd(), _dyn_bytes(0, 15150, 310, 61, n=n)]
    assert records[-1].data.dynamic.is_truncated
    last = _frames(records, version=12)[-1]["battery"]
    assert (last["chargeLevel"], last["voltage"], last["temperature"]) == (66, 15.2, 30.0)
    assert (last["minTemperature"], last["fullCapacity"], last["current"]) == (30.0, 2450, 3.0)


def test_full_dynamic_record_from_bytes_feeds_the_frame():
    records = [_osd(), _dyn_bytes(0, 15200, 300, 66), _osd(), _dyn_bytes(0, 15150, 310, 61, n=21)]
    last = _frames(records, version=12)[-1]["battery"]
    assert (last["chargeLevel"], last["voltage"], last["temperature"]) == (61, 15.15, 31.0)


def test_one_byte_dynamic_payload_does_not_pick_the_aggregate():
    # Payload b"\x00" decodes to index 0 with every value 0; it must not make
    # index 0 the main battery of a dual log that only has pack records
    stub = Record(RecordType.SmartBatteryGroup, SmartBatteryGroup.from_bytes(bytes([2, 0])))
    records = [_osd(), _dyn(1, voltage=45.1, soc=60), _dyn(2, voltage=45.2, soc=59), stub,
               _osd(), _dyn(1, voltage=44.9, soc=58)]
    assert stub.data.dynamic.index == 0 and stub.data.dynamic.is_truncated
    assert battery_layout(records, 14).dynamic_index == 1
    frames = [f["battery"] for f in _frames(records, version=14)]
    assert [(b["chargeLevel"], b["voltage"]) for b in frames] == [(60, 45.1), (58, 44.9)]


def test_layout_skips_invalid_aggregate_records():
    records = [_osd(), _dyn(0, voltage=11011.0, temp=1024.0), _dyn(1, soc=55), _osd()]
    assert battery_layout(records).dynamic_index == 1
    assert _frames(records)[0]["battery"]["chargeLevel"] == 55


@pytest.mark.parametrize("indices, expected", [((0, 2), 2), ((2, 0), 2), ((0, 1, 2), 1), ((5, 3), 3)])
def test_static_index_order(indices, expected):
    records = [_osd()] + [_static(i) for i in indices] + [_osd()]
    assert battery_layout(records).static_index == expected


# --- B3 cell count ------------------------------------------------------------

def test_cell_count_from_single_voltage_records():
    records = [_osd(), _dyn(0, voltage=8.0, cells=2), _cells(0, [3.9] * 13), _osd()]
    battery = _frames(records)[0]["battery"]  # ProductType NONE would give 4
    assert battery["cellNum"] == 13 and len(battery["cellVoltages"]) == 13


def test_cell_count_follows_the_pack_used_for_cells():
    records = [_osd(), _cells(2, [3.7] * 5), _cells(1, [3.8] * 12), _osd()]
    layout = battery_layout(records)
    assert (layout.cell_index, layout.cell_num) == (1, 12)
    assert _frames(records)[0]["battery"]["cellNum"] == 12


def test_cell_count_from_dynamic_records_on_v13_plus_only():
    records = [_osd(), _dyn(0, voltage=7.8, cells=3), _osd()]
    assert _frames(records, version=13)[0]["battery"]["cellNum"] == 3
    assert _frames(records, version=14)[0]["battery"]["cellNum"] == 3
    # v12 dynamic cell counts are unreliable: fall back to the product (Mavic Mini: 2)
    details = Details(product_type=ProductType(59))
    frame = records_to_frames(records, details, version=12)[0].to_dict()
    assert frame["battery"]["cellNum"] == 2


def test_cell_count_ignores_dynamic_records_when_version_is_unknown():
    # The 2-argument call records_to_frames(records, details) must not trust
    # the dynamic cell count: it is wrong on v12
    records = [_osd(), _dyn(0, voltage=7.6, cells=3), _osd()]
    assert battery_layout(records).cell_num is None
    details = Details(product_type=ProductType(59))
    frame = records_to_frames(records, details)[0].to_dict()
    assert frame["battery"]["cellNum"] == 2 and len(frame["battery"]["cellVoltages"]) == 2
    assert _frames(records)[0]["battery"]["cellNum"] == 4  # ProductType NONE
    # Cell records still size the pack without a version
    with_cells = [_osd(), _dyn(0, voltage=7.6, cells=3), _cells(0, [3.8, 3.8]), _osd()]
    assert _frames(with_cells)[0]["battery"]["cellNum"] == 2


def test_truncated_cell_records_size_the_pack_but_are_not_used():
    records = [
        _osd(),
        _dyn(0, voltage=24.0, cells=6),
        _cells(0, [3.95], count=6, truncated=True),
        _osd(),
        _cells(0, [4.00, 4.01, 4.02, 4.03, 4.04, 4.05]),
        _cells(0, [3.50], count=6, truncated=True),
        _osd(),
    ]
    frames = _frames(records)
    assert frames[0]["battery"]["cellNum"] == 6
    assert frames[0]["battery"]["isCellVoltageEstimated"] is True
    assert frames[0]["battery"]["cellVoltages"] == [4.0] * 6  # estimated from 24 V
    assert frames[1]["battery"]["cellVoltages"] == [4.00, 4.01, 4.02, 4.03, 4.04, 4.05]
    assert frames[1]["battery"]["maxCellVoltageDeviation"] == pytest.approx(0.05)


def test_stale_cell_voltages_fall_back_to_estimates():
    records = [_osd(), _dyn(0, voltage=48.0), _cells(1, [3.9] * 12)] + [_osd() for _ in range(60)]
    frames = _frames(records)
    # Used in the frame with the record and the next 50 frames (5 s), then estimated
    assert frames[0]["battery"]["cellVoltages"] == [3.9] * 12
    assert frames[50]["battery"]["isCellVoltageEstimated"] is False
    assert frames[51]["battery"]["isCellVoltageEstimated"] is True
    assert frames[51]["battery"]["cellVoltages"] == [4.0] * 12
    assert frames[51]["battery"]["cellVoltageDeviation"] == 0.0


# --- flight controller --------------------------------------------------------

def _t8(useful=0, gh_time=0, land_time=0, gh_batt=0, land_batt=0, percent=70, voltage=46.0) -> Record:
    return Record(RecordType.SmartBattery, SmartBattery(
        useful_time=useful, go_home_time=gh_time, land_time=land_time, go_home_battery=gh_batt,
        land_battery=land_batt, percent=percent, voltage=voltage))


def test_flight_controller_filled_from_type8_without_type63():
    records = [
        _osd(), _t8(gh_time=60, gh_batt=12, land_batt=5),
        _osd(), _t8(useful=900, gh_time=61, land_time=30, gh_batt=12, land_batt=5),
        _osd(), _t8(useful=880, gh_time=61, land_time=0, gh_batt=12, land_batt=5),
        _osd(),
    ]
    frames = _frames(records, extended=True)
    fc = [f["flightController"] for f in frames]
    assert fc[0]["remainingFlightTime"] is None  # still 0: no estimate yet
    assert fc[0]["batteryPercentNeededToGoHome"] == 12 and fc[0]["batteryPercentNeededToLand"] == 5
    assert fc[0]["timeNeededToGoHome"] == 60 and fc[0]["timeNeededToLand"] is None
    assert fc[1]["remainingFlightTime"] == 900 and fc[1]["timeNeededToLand"] == 30
    assert fc[2]["timeNeededToLand"] == 0  # follows the record once it has been non-zero
    assert frames[2]["battery"]["chargeLevel"] == 70 and frames[2]["battery"]["voltage"] == 46.0


def _t63(sub_type=0, remain=1200, gh_time=137, land_time=31, gh_cap=14, land_cap=6) -> Record:
    return Record(RecordType.FlightControllerCommonOSD, FCCommonOSD(
        sub_type=sub_type, remain_fly_time=remain, need_go_home_time=gh_time, need_land_time=land_time,
        go_home_capacity=gh_cap, land_capacity=land_cap))


def test_flight_controller_from_type63():
    records = [_osd(), _t63(), _osd()]
    plain = _frames(records)[0]["flightController"]
    assert plain == {"remainingFlightTime": 1200, "batteryPercentNeededToLand": 6,
                     "batteryPercentNeededToGoHome": 14}
    fc = _frames(records, extended=True)[0]["flightController"]
    assert fc["timeNeededToGoHome"] == 137 and fc["timeNeededToLand"] == 31


def test_type63_go_home_sentinel_gives_unknown_percentage():
    # need_go_home_time 65535 (None) comes with go_home_capacity 0: no estimate, not 0 %
    records = [_osd(), _t63(gh_time=None, gh_cap=0), _osd(), _t63(gh_time=140, gh_cap=15), _osd()]
    f0, f1 = (f["flightController"] for f in _frames(records, extended=True)[:2])
    assert f0["batteryPercentNeededToGoHome"] is None and f0["timeNeededToGoHome"] is None
    assert f0["batteryPercentNeededToLand"] == 6 and f0["remainingFlightTime"] == 1200
    assert f1["batteryPercentNeededToGoHome"] == 15 and f1["timeNeededToGoHome"] == 140


def test_type8_does_not_override_type63():
    records = [_osd(), _t63(gh_time=None, gh_cap=0), _t8(useful=900, gh_batt=12, gh_time=70), _osd()]
    fc = _frames(records, extended=True)[0]["flightController"]
    assert fc["remainingFlightTime"] == 1200 and fc["batteryPercentNeededToGoHome"] is None
    assert fc["timeNeededToGoHome"] is None and fc["timeNeededToLand"] == 31


def test_type63_with_other_sub_type_leaves_flight_controller_to_type8():
    records = [_osd(), _t63(sub_type=1), _t8(useful=900, gh_time=61, land_time=30, gh_batt=12, land_batt=5),
               _osd()]
    fc = _frames(records, extended=True)[0]["flightController"]
    assert (fc["remainingFlightTime"], fc["batteryPercentNeededToGoHome"], fc["batteryPercentNeededToLand"]) == (
        900, 12, 5)
    assert (fc["timeNeededToGoHome"], fc["timeNeededToLand"]) == (61, 30)


def test_rc_lost_action():
    records = [_osd(), Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.Hover)), _osd(),
               Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.UNKNOWN)), _osd()]
    frames = _frames(records, extended=True)
    assert [f["flightController"]["rcLostAction"] for f in frames] == ["Hover", "Hover", "Hover"]


# --- other sections -----------------------------------------------------------

def test_app_gps_altitude_and_deprecated_alias():
    frames = _frames([_osd(), Record(RecordType.AppGPS, AppGPS(latitude=1.0, longitude=2.0, altitude=-12.5)), _osd()])
    assert frames[0]["appGps"]["altitude"] == -12.5
    assert frames[0]["appGps"]["horizontalAccuracy"] == -12.5
    empty = _frames([_osd()])[0]["appGps"]
    assert empty["altitude"] is None and empty["horizontalAccuracy"] == -1.0


def test_osd_extended_keys():
    records = [
        _osd(wind_speed=6.3, wind_direction="SW", wind_direction_code=6, position_source="RTKFixed",
             position_source_code=3, yaw_rate=-12.5, home_offset_north=10.5, home_offset_east=-4.0,
             is_gps_valid=True, low_battery_warning=25, critical_battery_warning=15),
        _osd(home_offset_north=0.0, home_offset_east=0.0, is_gps_valid=False),
    ]
    f0, f1 = _frames(records, extended=True)
    assert (f0["osd"]["windSpeed"], f0["osd"]["windDirection"]) == (6.3, "SW")
    assert (f0["osd"]["positionSource"], f0["osd"]["positionSourceCode"]) == ("RTKFixed", 3)
    assert f0["osd"]["yawRate"] == -12.5
    assert (f0["osd"]["homeOffsetNorth"], f0["osd"]["homeOffsetEast"]) == (10.5, -4.0)
    assert (f0["battery"]["lowWarningThreshold"], f0["battery"]["criticalWarningThreshold"]) == (25, 15)
    # No GNSS fix: 0.0/0.0 offsets are unknown; thresholds keep the last non-zero value
    assert (f1["osd"]["homeOffsetNorth"], f1["osd"]["homeOffsetEast"]) == (None, None)
    assert f1["battery"]["lowWarningThreshold"] == 25
    assert f1["battery"]["criticalWarningThreshold"] == 15


def test_gimbal_extended_keys_and_reset_pulse():
    def g(resetting):
        return Record(RecordType.Gimbal, Gimbal(pitch=-30.0, yaw_angle=12.3, joint_pitch=-28.5,
                                                 is_resetting=resetting))
    records = [_osd(), g(True), g(False), _osd(), g(False), _osd()]
    frames = _frames(records, extended=True)
    assert frames[0]["gimbal"]["isResetting"] is True  # kept for the frame
    assert frames[1]["gimbal"]["isResetting"] is False
    assert frames[0]["gimbal"]["yawRelativeToAircraft"] == 12.3
    assert frames[0]["gimbal"]["jointPitch"] == -28.5
    assert _frames([_osd()], extended=True)[0]["gimbal"]["isResetting"] is None


def test_rc_buttons_are_momentary_and_dials_follow():
    def rc(shutter=False, c1=False, left=1024, right=1024):
        return Record(RecordType.RCDisplayField, RCDisplayField(
            aileron=1024, elevator=1024, throttle=1024, rudder=1024, gimbal=left, right_dial=right,
            is_shutter_pressed=shutter, is_custom_button_1_pressed=c1))
    records = [_osd(), rc(shutter=True), rc(left=1300), _osd(), rc(c1=True, right=900), _osd(), _osd()]
    frames = _frames(records, extended=True)
    assert frames[0]["rc"]["isShutterPressed"] is True and frames[0]["rc"]["leftDial"] == 1300
    assert frames[1]["rc"]["isShutterPressed"] is False and frames[1]["rc"]["isCustomButton1Pressed"] is True
    assert frames[1]["rc"]["rightDial"] == 900
    assert frames[2]["rc"]["isCustomButton1Pressed"] is False and frames[2]["rc"]["rightDial"] == 900
    assert _frames([_osd()], extended=True)[0]["rc"]["isShutterPressed"] is None


_RC_BUTTONS = {
    "is_shutter_half_pressed": "isShutterHalfPressed",
    "is_shutter_pressed": "isShutterPressed",
    "is_record_pressed": "isRecordPressed",
    "is_custom_button_1_pressed": "isCustomButton1Pressed",
    "is_custom_button_2_pressed": "isCustomButton2Pressed",
}


@pytest.mark.parametrize("attr", list(_RC_BUTTONS))
def test_each_rc_button_maps_to_its_own_frame_key(attr):
    rc = RCDisplayField(aileron=1024, elevator=1024, throttle=1024, rudder=1024, **{attr: True})
    frames = _frames([_osd(), Record(RecordType.RCDisplayField, rc), _osd(), _osd()], extended=True)
    assert {key: frames[0]["rc"][key] for key in _RC_BUTTONS.values()} == {
        key: key == _RC_BUTTONS[attr] for key in _RC_BUTTONS.values()}
    assert not any(frames[1]["rc"][key] for key in _RC_BUTTONS.values())  # momentary


def test_camera_storage_keys_and_unknown_total():
    cam = Camera(work_mode=1, sd_card_total_mb=60000, sd_card_free_mb=50000, remaining_photos=12000,
                 remaining_video_seconds=5000)
    none = Camera(work_mode=0, sd_card_total_mb=0, sd_card_free_mb=0, remaining_photos=0,
                  remaining_video_seconds=0)
    f0, f1 = _frames([_osd(), Record(RecordType.Camera, cam), _osd(), Record(RecordType.Camera, none), _osd()],
                     extended=True)[:2]
    assert [f0["camera"][k] for k in EXTENDED_KEYS["camera"]] == [1, 60000, 50000, 12000, 5000]
    assert [f1["camera"][k] for k in EXTENDED_KEYS["camera"]] == [0, None, None, None, None]


def test_vision_near_ground_and_unsupported_flags():
    vg = VisionGroup(collision_avoidance_enabled=True, vert_low_limit_active=True, avoidance_flags=0x813)
    frames = _frames([_osd(), _osd(), Record(RecordType.VisionGroup, vg), _osd()], extended=True)
    assert frames[0]["vision"]["isNearGround"] is None  # before the first VisionGroup record
    assert frames[1]["vision"] == {"collisionAvoidanceEnabled": True, "isBraking": False,
                                   "isAscentLimited": False, "isLandingConfirmationNeeded": False,
                                   "isNearGround": True}


def test_vision_record_without_avoidance_block_keeps_previous_state():
    with_block8 = VisionGroup(collision_avoidance_enabled=True, vert_low_limit_active=True, avoidance_flags=0x813)
    # Synthetic record with only a block 10 ([type][00 00 00][n][payload][FE]): no avoidance status
    without = VisionGroup.from_bytes(bytes([10, 0, 0, 0, 2, 0x01, 0x02, 0xFE]))
    assert without.avoidance_flags is None and without.collision_avoidance_enabled is False
    records = [_osd(), Record(RecordType.VisionGroup, with_block8), _osd(),
               Record(RecordType.VisionGroup, without), _osd()]
    frames = _frames(records, extended=True)
    assert frames[1]["vision"]["collisionAvoidanceEnabled"] is True
    assert frames[1]["vision"]["isNearGround"] is True


def test_frame_app_gps_horizontal_accuracy_alias_is_settable():
    g = FrameAppGPS()
    g.horizontal_accuracy = 12.5
    assert g.altitude == 12.5 and g.horizontal_accuracy == 12.5
    g.horizontal_accuracy = -1.0  # the old "unknown"
    assert g.altitude is None and g.horizontal_accuracy == -1.0
    g.altitude = -3.0
    assert g.to_dict()["horizontalAccuracy"] == -3.0


def test_nearby_aircraft_extended_keys():
    entry = _frames([_osd(), _adsb(), _osd()], extended=True)[0]["nearbyAircraft"][0]
    assert {k: entry[k] for k in NEARBY_EXTENDED} == {
        "distance": 1500, "relativeAltitude": -40, "verticalTrend": "Falling", "warningLevel": 2,
        "altitudeType": "MSL"}


# --- summary --------------------------------------------------------------------

def _summary(records):
    log = SimpleNamespace(_last_records=records)
    return _build_summary(log, records_to_frames(records), {})


def test_summary_additions():
    records = [
        _osd(low_battery_warning=0, critical_battery_warning=0, wind_speed=None),
        _osd(low_battery_warning=30, critical_battery_warning=20, wind_speed=4.2),
        _static(2, cycles=41, capacity=5880, life=96, date="2023-11-20"),
        Record(RecordType.KeyValueSnapshot, KeyValueSnapshot(module=7, key=1, serials={1: "CAM0", 7: "BATA", 8: "BATB", 6: "ACC1"})),
        Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.GoHome)),
        Record(RecordType.Home, Home(aircraft_flight_count=310)),
        _osd(low_battery_warning=25, critical_battery_warning=10, wind_speed=7.5),
        Record(RecordType.Home, Home(aircraft_flight_count=311)),
        _osd(wind_speed=0.0),
    ]
    s = _summary(records)
    assert s["batteryCycleCount"] == 41 and s["batteryDesignedCapacity"] == 5880  # index-2-only log
    assert s["batteryStateOfHealth"] == 96 and s["batteryManufactureDate"] == "2023-11-20"
    assert s["batteries"] == [{"index": 2, "cycleCount": 41, "designedCapacity": 5880,
                               "stateOfHealth": 96, "manufactureDate": "2023-11-20"}]
    assert s["batterySns"] == ["BATA", "BATB"] and s["accessorySn"] == "ACC1"
    assert s["rcLostAction"] == "GoHome"
    assert (s["lowBatteryWarningThreshold"], s["criticalBatteryWarningThreshold"]) == (30, 20)
    assert s["aircraftFlightCount"] == 311
    assert s["maxWindSpeed"] == 7.5


def test_summary_omits_unknown_values():
    records = [
        _osd(),
        _static(0, life=0, date=None),
        _static(1, cycles=0, capacity=0, life=0, date=None),
        Record(RecordType.KeyValueSnapshot, KeyValueSnapshot(module=7, key=1, serials={})),
        Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.UNKNOWN)),
        _osd(),
    ]
    s = _summary(records)
    for key in ("batteryStateOfHealth", "batteryManufactureDate", "batterySns", "accessorySn",
                "rcLostAction", "lowBatteryWarningThreshold", "criticalBatteryWarningThreshold",
                "aircraftFlightCount", "maxWindSpeed"):
        assert key not in s, key
    assert [b["index"] for b in s["batteries"]] == [0, 1]
    assert s["batteries"][1] == {"index": 1, "cycleCount": None, "designedCapacity": None,
                                 "stateOfHealth": None, "manufactureDate": None}
    assert _summary([_osd()]).get("batteries") is None


# Summary keys that come from the log header (details), not from records
_HEADER_SUMMARY_KEYS = {
    "startTime", "startCoordinate", "totalTime", "totalDistance", "maxHeight", "maxHorizontalSpeed",
    "maxVerticalSpeed", "aircraftName", "aircraftSn", "cameraSn", "rcSn", "batterySn", "appPlatform",
    "appVersion", "productType",
}


def _rich_records():
    return [
        _osd(low_battery_warning=30, critical_battery_warning=20, wind_speed=4.2),
        _static(1, cycles=41, capacity=5880, life=96, date="2023-11-20"),
        Record(RecordType.Recover, Recover(camera_sn="CAM-PLACEHOLDER", rc_sn="RC-PLACEHOLDER")),
        Record(RecordType.Camera, Camera(camera_type=83)),
        Record(RecordType.KeyValueSnapshot, KeyValueSnapshot(module=7, key=1, serials={7: "BATA", 6: "ACC1"})),
        Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.GoHome)),
        Record(RecordType.Home, Home(aircraft_flight_count=311)),
        _osd(),
    ]


def test_summary_of_undecrypted_log_has_header_values_only():
    records = _rich_records()
    log = SimpleNamespace(_last_records=records, _undecrypted=True)
    s = _build_summary(log, records_to_frames(records), {"cameraSn": "", "rcSn": "", "aircraftName": "X"})
    assert set(s) == _HEADER_SUMMARY_KEYS
    assert (s["cameraSn"], s["rcSn"], s["aircraftName"]) == ("", "", "X")  # no Recover fill-ins
    # The same records in a decrypted log fill everything
    decrypted = _build_summary(SimpleNamespace(_last_records=records, _undecrypted=False),
                               records_to_frames(records), {"cameraSn": "", "rcSn": ""})
    assert (decrypted["cameraSn"], decrypted["rcSn"]) == ("CAM-PLACEHOLDER", "RC-PLACEHOLDER")
    for key in ("batteryCycleCount", "batteryDesignedCapacity", "batteryStateOfHealth",
                "batteryManufactureDate", "batteries", "batterySns", "accessorySn", "cameraType",
                "cameraModel", "rcLostAction", "lowBatteryWarningThreshold",
                "criticalBatteryWarningThreshold", "aircraftFlightCount", "maxWindSpeed"):
        assert key in decrypted, key


def test_summary_range_guards():
    records = [
        _osd(low_battery_warning=0, critical_battery_warning=101, wind_speed=40.5),
        _osd(low_battery_warning=120, critical_battery_warning=100, wind_speed=12.0),
        _osd(low_battery_warning=1, critical_battery_warning=5, wind_speed=40.0),
        Record(RecordType.Home, Home(aircraft_flight_count=12)),
        Record(RecordType.Home, Home(aircraft_flight_count=0)),
        Record(RecordType.Home, Home(aircraft_flight_count=1_000_001)),
        _static(1, life=111),
        _static(2, life=101),
        _osd(),
    ]
    s = _summary(records)
    assert (s["lowBatteryWarningThreshold"], s["criticalBatteryWarningThreshold"]) == (1, 100)
    assert s["maxWindSpeed"] == 40.0
    assert s["aircraftFlightCount"] == 12
    assert "batteryStateOfHealth" not in s  # pack 1 reads 111
    assert [b["stateOfHealth"] for b in s["batteries"]] == [None, 101]
    edge = _summary([_osd(low_battery_warning=100, critical_battery_warning=1, wind_speed=0.0),
                     Record(RecordType.Home, Home(aircraft_flight_count=1_000_000)), _static(0, life=1), _osd()])
    assert (edge["lowBatteryWarningThreshold"], edge["criticalBatteryWarningThreshold"]) == (100, 1)
    assert edge["maxWindSpeed"] == 0.0 and edge["aircraftFlightCount"] == 1_000_000
    assert edge["batteryStateOfHealth"] == 1
    assert _summary([_osd(wind_speed=40.1), _osd()]).get("maxWindSpeed") is None


def test_summary_selection_rules():
    def kv(module, key, serials):
        return Record(RecordType.KeyValueSnapshot, KeyValueSnapshot(module=module, key=key, serials=serials))

    records = [
        _osd(),
        kv(5, 1, {7: "WRONG-MODULE"}),
        kv(7, 2, {7: "WRONG-KEY"}),
        kv(7, 1, {7: "BAT1", 8: "BAT2", 6: "ACC1"}),
        kv(7, 1, {7: "BAT3", 6: "ACC2"}),
        Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.Landing)),
        Record(RecordType.MCParams, MCParams(fail_safe=FailSafe.GoHome)),
        _static(1, cycles=11, capacity=5000, life=91, date="2024-01-02"),
        _static(0, cycles=10, capacity=200000, life=90, date="2024-01-01"),
        _static(1, cycles=99, capacity=4000, life=50, date="2020-01-01"),
        _osd(),
    ]
    s = _summary(records)
    assert s["batterySns"] == ["BAT1", "BAT2"] and s["accessorySn"] == "ACC1"
    assert s["rcLostAction"] == "Landing"
    assert [b["index"] for b in s["batteries"]] == [0, 1]
    assert s["batteries"][0]["designedCapacity"] is None  # out of bounds
    assert s["batteries"][1] == {"index": 1, "cycleCount": 11, "designedCapacity": 5000,
                                 "stateOfHealth": 91, "manufactureDate": "2024-01-02"}
    # Primary pack = the one the frames use (index 1), not the lowest index
    assert s["batteryStateOfHealth"] == 91 and s["batteryManufactureDate"] == "2024-01-02"


# --- frame snapshots (copy per emitted frame) ---------------------------------

import copy  # noqa: E402

from dji_flightlog_parser.frame import models as frame_models  # noqa: E402
from dji_flightlog_parser.frame.models import (  # noqa: E402
    Frame, FrameBattery, FrameBatteryPack, FrameExtended, FrameHudWarning, FrameNearbyAircraft,
)
from dji_flightlog_parser.record.go_business import GOBusinessData, GOBusinessWarning  # noqa: E402


def _mutable_ids(obj, acc=None) -> list[int]:
    """ids of every dataclass instance, list and dict reachable from obj."""
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        values = obj.values()
    elif isinstance(obj, list):
        values = obj
    elif dataclasses.is_dataclass(obj):
        values = vars(obj).values()
    else:
        return acc
    acc.append(id(obj))
    for v in values:
        _mutable_ids(v, acc)
    return acc


def _full_frame() -> Frame:
    frame = Frame(battery=FrameBattery(cell_num=3, cell_voltages=[3.9, 3.8, 3.7],
                                       is_cell_voltage_estimated=False))
    frame.extended = FrameExtended()
    frame.osd.height = 12.5
    frame.osd.wind_direction = "SW"
    frame.battery.packs = [FrameBatteryPack(index=1, voltage=22.0), FrameBatteryPack(index=2, voltage=22.1)]
    frame.nearby_aircraft = [FrameNearbyAircraft(icao_address="ABC123", latitude=1.0, distance=1500)]
    frame.extended.rtk.satellites = 30
    frame.extended.app_hud.warnings = [FrameHudWarning(text="W1", code="1", level=2)]
    frame.extended.secondary_gimbal.pitch = -10.0
    return frame


def test_snapshot_equals_deepcopy_and_shares_no_mutable_object():
    frame = _full_frame()
    snap = frame.snapshot()
    assert snap == copy.deepcopy(frame)
    assert snap.to_dict() == frame.to_dict()
    assert type(snap.battery.packs[0]) is FrameBatteryPack
    assert not set(_mutable_ids(snap)) & set(_mutable_ids(frame))


def test_mutating_the_source_after_a_snapshot_leaves_the_snapshot_unchanged():
    frame = _full_frame()
    snap = frame.snapshot()
    expected = copy.deepcopy(frame).to_dict()

    # Lists changed in place
    frame.battery.cell_voltages[0] = 0.1
    frame.battery.cell_voltages.append(4.0)
    frame.battery.packs.append(FrameBatteryPack(index=3))
    frame.nearby_aircraft.append(FrameNearbyAircraft(icao_address="DEF456"))
    frame.extended.app_hud.warnings.append(FrameHudWarning(text="W2"))
    # Objects inside lists
    frame.battery.packs[0].voltage = 1.0
    frame.nearby_aircraft[0].latitude = 5.0
    frame.extended.app_hud.warnings[0].text = "changed"
    # Nested sections, default and extended
    frame.osd.height = 99.0
    frame.battery.temperature = 40.0
    frame.extended.rtk.satellites = 1
    frame.extended.secondary_gimbal.pitch = 20.0
    frame.reset()
    frame.finalize()

    assert snap.to_dict() == expected


def test_snapshot_falls_back_to_deepcopy_for_other_types():
    frame = _full_frame()
    value = ("x", [1, 2])  # no frame field holds a tuple today
    frame.osd.wind_direction = value
    snap = frame.snapshot()
    assert snap.osd.wind_direction == value
    assert snap.osd.wind_direction[1] is not value[1]


def _hud(*texts) -> Record:
    return Record(RecordType.GOBusiness, GOBusinessData(
        warnings_updated=True, warnings=[GOBusinessWarning(text=t, level=2, code="1") for t in texts]))


def _snapshot_records() -> list[Record]:
    adsb2 = _adsb()
    adsb2.data.aircraft[0] = dataclasses.replace(adsb2.data.aircraft[0], icao_address="DEF456", latitude=3.0)
    return [
        _osd(),
        _cells(0, [3.9, 3.9, 3.8, 3.8]), _dyn(0), _dyn(1, voltage=22.0), _dyn(2, voltage=22.1),
        _adsb(), _hud("W1"), _static(1),
        _osd(),  # emits frame 0
        # Cell records write into the builder's list in place
        _cells(0, [3.5, 3.5, 3.5, 3.5]), _dyn(1, voltage=20.0), adsb2, _hud(),
        _osd(),  # emits frame 1
        _osd(),
    ]


@pytest.mark.parametrize("extended", [False, True])
def test_builder_state_changes_do_not_reach_emitted_frames(extended, monkeypatch):
    frames = records_to_frames(_snapshot_records(), extended=extended)
    f0, f1 = frames[0].to_dict(), frames[1].to_dict()
    assert f0["battery"]["cellVoltages"] == [3.9, 3.9, 3.8, 3.8]
    assert f1["battery"]["cellVoltages"] == [3.5, 3.5, 3.5, 3.5]
    assert f0["nearbyAircraft"][0]["icaoAddress"] == "ABC123"
    assert f1["nearbyAircraft"][0]["icaoAddress"] == "DEF456"
    if extended:
        assert [p["voltage"] for p in f0["battery"]["packs"]] == [22.0, 22.1]
        assert [p["voltage"] for p in f1["battery"]["packs"]] == [20.0, 22.1]
        assert [w["text"] for w in f0["appHud"]["warnings"]] == ["W1"]
        assert f1["appHud"]["warnings"] == []
    # No mutable object is shared between emitted frames
    ids = [i for f in frames for i in _mutable_ids(f)]
    assert len(ids) == len(set(ids))
    # Same frames as the deepcopy the builder used before
    monkeypatch.setattr(Frame, "snapshot", lambda self: copy.deepcopy(self))
    assert [f.to_dict() for f in records_to_frames(_snapshot_records(), extended=extended)] == \
        [f.to_dict() for f in frames]
    assert [repr(f) for f in records_to_frames(_snapshot_records(), extended=extended)] == \
        [repr(f) for f in frames]


def test_builder_does_not_deepcopy_frames(monkeypatch):
    # Every value in a built frame is a dataclass, list or immutable leaf, so
    # neither the builder nor Frame.snapshot needs copy.deepcopy
    def no_deepcopy(*args, **kwargs):
        raise AssertionError("copy.deepcopy called")

    assert frame_models.copy is copy
    monkeypatch.setattr(copy, "deepcopy", no_deepcopy)
    frames = records_to_frames(_snapshot_records(), extended=True)
    assert len(frames) == 4 and frames[1].battery.packs[0].voltage == 20.0
