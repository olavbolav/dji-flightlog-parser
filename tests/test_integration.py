"""Integration tests against example DJI flight log files.

These tests require:
- Example files in example_files/
- DJI API key in .env (app_key)
"""

import os
import json
import glob
import pytest
from pathlib import Path
from dotenv import load_dotenv

from dji_flightlog_parser import DJILog
from dji_flightlog_parser.export.json_export import export_json, export_json_raw
from dji_flightlog_parser.export.geojson import export_geojson
from dji_flightlog_parser.export.kml import export_kml
from dji_flightlog_parser.export.csv_export import export_csv

load_dotenv()

EXAMPLE_DIR = Path(__file__).parent.parent / "example_files"
API_KEY = os.getenv("app_key")


def _get_example_files():
    files = sorted(EXAMPLE_DIR.glob("*.txt"))
    if not files:
        pytest.skip("No example files in example_files/")
    return files


def _get_api_key():
    if not API_KEY:
        pytest.skip("No app_key in .env")
    return API_KEY


class TestFileLoading:
    def test_load_all_files(self):
        for f in _get_example_files():
            log = DJILog.from_file(f)
            assert log.version >= 13
            assert log.prefix is not None

    def test_details_parsing(self):
        for f in _get_example_files():
            log = DJILog.from_file(f)
            assert log.details is not None
            assert log.details.aircraft_name != ""

    def test_version_detection(self):
        for f in _get_example_files():
            log = DJILog.from_file(f)
            assert log.version == 14


class TestKeychainAPI:
    def test_keychains_request_structure(self):
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            req = log.keychains_request()
            assert req.version > 0
            assert req.department > 0
            assert len(req.keychains_array) >= 1
            assert len(req.keychains_array[0]) >= 1

    def test_fetch_keychains(self):
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            keychains = log.fetch_keychains(api_key)
            assert len(keychains) >= 1
            for kc in keychains:
                for fp, (iv, key) in kc.items():
                    assert len(key) == 32
                    assert len(iv) == 16


class TestRecordParsing:
    def test_parse_records(self):
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            keychains = log.fetch_keychains(api_key)
            records = log.records(keychains)
            assert len(records) > 0

    def test_osd_records_present(self):
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            keychains = log.fetch_keychains(api_key)
            records = log.records(keychains)
            from dji_flightlog_parser.record.types import RecordType
            osd_count = sum(1 for r in records if r.record_type == RecordType.OSD)
            assert osd_count > 0, f"No OSD records found in {f.name}"


class TestFrameBuilding:
    def test_frames_from_all_files(self):
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            keychains = log.fetch_keychains(api_key)
            frames = log.frames(keychains)
            assert len(frames) > 0, f"No frames from {f.name}"

    def test_frame_coordinates(self):
        """First frame with GPS should have valid coordinates."""
        api_key = _get_api_key()
        for f in _get_example_files():
            log = DJILog.from_file(f)
            keychains = log.fetch_keychains(api_key)
            frames = log.frames(keychains)
            for frame in frames:
                if frame.osd.latitude != 0.0:
                    assert -90 <= frame.osd.latitude <= 90
                    assert -180 <= frame.osd.longitude <= 180
                    break


class TestExporters:
    def test_json_export(self):
        api_key = _get_api_key()
        f = _get_example_files()[0]
        log = DJILog.from_file(f)
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        result = export_json(log.version, log.details, frames)
        data = json.loads(result)
        assert "version" in data
        assert "details" in data
        assert "frames" in data
        assert len(data["frames"]) == len(frames)

    def test_json_raw_export(self):
        api_key = _get_api_key()
        f = _get_example_files()[0]
        log = DJILog.from_file(f)
        keychains = log.fetch_keychains(api_key)
        records = log.records(keychains)
        result = export_json_raw(log.version, log.details, records)
        data = json.loads(result)
        assert "records" in data
        assert len(data["records"]) > 0

    def test_geojson_export(self):
        api_key = _get_api_key()
        f = _get_example_files()[0]
        log = DJILog.from_file(f)
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        result = export_geojson(log.details, frames)
        data = json.loads(result)
        assert data["type"] == "FeatureCollection"

    def test_kml_export(self):
        api_key = _get_api_key()
        f = _get_example_files()[0]
        log = DJILog.from_file(f)
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        result = export_kml(log.details, frames)
        assert "<kml" in result
        assert "coordinates" in result

    def test_csv_export(self):
        api_key = _get_api_key()
        f = _get_example_files()[0]
        log = DJILog.from_file(f)
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        result = export_csv(frames)
        lines = result.strip().split("\n")
        assert len(lines) > 1
        assert "latitude" in lines[0]


class TestRustCompatibility:
    """Test specific values match Rust parser output."""

    def test_trondelag_frame_count(self):
        api_key = _get_api_key()
        target = list(EXAMPLE_DIR.glob("*trondelag*"))
        if not target:
            pytest.skip("Trondelag example file not found")
        log = DJILog.from_file(target[0])
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        assert len(frames) >= 7548

    def test_trondelag_coordinates(self):
        api_key = _get_api_key()
        target = list(EXAMPLE_DIR.glob("*trondelag*"))
        if not target:
            pytest.skip("Trondelag example file not found")
        log = DJILog.from_file(target[0])
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        f0 = frames[0]
        assert abs(f0.osd.latitude - 63.31886391326526) < 1e-10
        assert abs(f0.osd.longitude - 10.300296306688862) < 1e-10

    def test_trondelag_osd_fields(self):
        api_key = _get_api_key()
        target = list(EXAMPLE_DIR.glob("*trondelag*"))
        if not target:
            pytest.skip("Trondelag example file not found")
        log = DJILog.from_file(target[0])
        keychains = log.fetch_keychains(api_key)
        frames = log.frames(keychains)
        f0 = frames[0]
        assert f0.osd.flyc_state == "GPSAtti"
        assert f0.osd.flyc_command is None
        assert f0.osd.flight_action == "None"
        assert f0.osd.motor_start_failed_cause == "None"
        assert f0.osd.gps_num == 30
        assert f0.osd.gps_level == 5
