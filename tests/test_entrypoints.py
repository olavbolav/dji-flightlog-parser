"""Entry points (parse_file, DJILog.frames, the CLI) forward the log version and decryption state.

DJILog loading and record parsing are monkeypatched with synthetic records:
no real files, no network.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import dji_flightlog_parser.parser as parser_mod
from dji_flightlog_parser.cli import main as cli_main
from dji_flightlog_parser.layout.details import Details, ProductType
from dji_flightlog_parser.parser import DJILog, parse_file
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.reader import Record
from dji_flightlog_parser.record.smart_battery_group import SmartBatteryDynamic, SmartBatteryGroup
from dji_flightlog_parser.record.types import RecordType

_KEYCHAINS = [{"synthetic": "keychain"}]  # opaque to the patched DJILog.records


def _records() -> list[Record]:
    # One dynamic record with cell_size 3 and no single_voltage records: only
    # the dynamic byte can size the pack, and only when the version is >= 13
    osd = dataclasses.replace(OSD.from_bytes(bytes(60)), low_battery_warning=30)
    dyn = SmartBatteryDynamic(index=0, current_voltage=7.6, current_current=1.5, full_capacity=2400,
                              remained_capacity=1800, temperature=25.0, capacity_percent=75, cell_size=3)
    return [Record(RecordType.OSD, osd), Record(RecordType.SmartBatteryGroup, SmartBatteryGroup(kind=2, dynamic=dyn)),
            Record(RecordType.OSD, osd)]


def _fake_log(version: int, product_type: ProductType) -> DJILog:
    log = DJILog.__new__(DJILog)  # skip header parsing
    log._data = b""
    log.version = version
    log.details = Details(product_type=product_type)
    log._aux_info = log._aux_version = None
    return log


@pytest.fixture
def fake(monkeypatch):
    """Install a synthetic log; returns a setter and the list of fetch_keychains calls."""
    calls: list[str] = []
    state: dict = {"keychains": _KEYCHAINS}

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(parser_mod, "fetch_keychains", no_network)

    def fetch(self, api_key, *args, **kwargs):
        calls.append(api_key)
        return state["keychains"]

    monkeypatch.setattr(DJILog, "fetch_keychains", fetch)
    monkeypatch.setattr(DJILog, "records", lambda self, keychains=None: _records())

    def install(version: int, product_type: ProductType, keychains=_KEYCHAINS) -> DJILog:
        log = _fake_log(version, product_type)
        state["keychains"] = keychains
        monkeypatch.setattr(DJILog, "from_file", classmethod(lambda cls, path: log))
        return log

    return install, calls


# Mavic Mini (ProductType 59) has 2 cells; ProductType NONE falls back to 4
_V12 = (12, ProductType(59), 2)
_V14 = (14, ProductType.NONE, 3)


@pytest.mark.parametrize("version, product, cells", [_V12, _V14])
def test_parse_file_forwards_version(fake, version, product, cells):
    install, _ = fake
    install(version, product)
    result = parse_file("synthetic.txt", api_key="test-key")
    battery = result["frames"][0]["battery"]
    assert result["version"] == version
    assert battery["cellNum"] == cells and len(battery["cellVoltages"]) == cells


@pytest.mark.parametrize("version, product, cells", [_V12, _V14])
def test_djilog_frames_forwards_version(fake, version, product, cells):
    install, _ = fake
    log = install(version, product)
    frame = log.frames(None)[0]
    assert frame.battery.cell_num == cells and len(frame.battery.cell_voltages) == cells


@pytest.mark.parametrize("version, product, cells", [_V12, _V14])
def test_cli_forwards_version(fake, tmp_path, version, product, cells):
    install, calls = fake
    install(version, product)
    path = tmp_path / "synthetic.txt"
    path.write_bytes(b"\x00")  # click checks that the file exists; its content is never read
    args = [str(path)] + (["-a", "test-key"] if version >= 13 else [])
    result = CliRunner().invoke(cli_main, args)
    assert result.exit_code == 0, result.output
    battery = json.loads(result.output)["frames"][0]["battery"]
    assert battery["cellNum"] == cells and len(battery["cellVoltages"]) == cells
    assert calls == (["test-key"] if version >= 13 else [])


def test_parse_file_v13_without_key_leaves_record_values_out_of_summary(fake):
    install, calls = fake
    log = install(14, ProductType.NONE)
    result = parse_file("synthetic.txt")
    assert calls == [] and log._undecrypted is True
    assert "lowBatteryWarningThreshold" not in result["summary"]
    assert len(result["frames"]) == 2  # frames are still built


# Summary keys taken from the log header; everything else comes from records
_HEADER_SUMMARY_KEYS = {
    "startTime", "startCoordinate", "totalTime", "totalDistance", "maxHeight", "maxHorizontalSpeed",
    "maxVerticalSpeed", "aircraftName", "aircraftSn", "cameraSn", "rcSn", "batterySn", "appPlatform",
    "appVersion", "productType",
}


# [{}]: what build_keychain returns when the API answers with items the
# parser cannot use (missing aesKey/aesIv, unknown feature point name)
@pytest.mark.parametrize("keychains", [[], [{}], [{}, {}]], ids=["empty", "one_empty", "two_empty"])
def test_parse_file_v13_with_keyless_keychains_counts_as_undecrypted(fake, keychains):
    install, calls = fake
    log = install(14, ProductType.NONE, keychains=keychains)
    result = parse_file("synthetic.txt", api_key="test-key")
    assert calls == ["test-key"] and log._undecrypted is True
    assert set(result["summary"]) == _HEADER_SUMMARY_KEYS


# One API segment the parser cannot use next to a usable one: any key in any
# group counts as decrypted, so the summary keeps its record-derived keys
def test_parse_file_v13_with_one_keyed_keychain_counts_as_decrypted(fake):
    install, calls = fake
    log = install(14, ProductType.NONE, keychains=[{"synthetic": "keychain"}, {}])
    result = parse_file("synthetic.txt", api_key="test-key")
    assert calls == ["test-key"] and log._undecrypted is False
    assert result["summary"]["lowBatteryWarningThreshold"] == 30


@pytest.mark.parametrize("keychains", [[], [{}]], ids=["empty", "one_empty"])
def test_records_warn_when_keychains_hold_no_keys(caplog, keychains):
    log = _fake_log(14, ProductType.NONE)
    log.prefix = SimpleNamespace(records_offset=lambda: 0, records_end_offset=lambda size: size)
    with caplog.at_level(logging.WARNING, logger="dji_flightlog_parser"):
        assert log.records(keychains) == []
    assert [r for r in caplog.records if "records will not be decrypted" in r.getMessage()]


@pytest.mark.parametrize("version, api_key", [(14, "test-key"), (12, None)])
def test_parse_file_decrypted_or_v12_keeps_record_values(fake, version, api_key):
    install, _ = fake
    log = install(version, ProductType.NONE)
    result = parse_file("synthetic.txt", api_key=api_key)
    assert log._undecrypted is False
    assert result["summary"]["lowBatteryWarningThreshold"] == 30
