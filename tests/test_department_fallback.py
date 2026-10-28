"""Offline tests for the keychains department fallback (MSDK logs) and its caching."""

import pytest

from dji_flightlog_parser import DJILog
from dji_flightlog_parser import parser as parser_mod
from dji_flightlog_parser.decoder.feature_point import FeaturePoint
from dji_flightlog_parser.keychain.api import KeychainAPIError
from dji_flightlog_parser.keychain.models import KeychainsRequest
from dji_flightlog_parser.record.osd import OSD
from dji_flightlog_parser.record.reader import Record
from dji_flightlog_parser.record.types import RecordType

INVALID_CIPHERTEXT = "invalid ciphertext"


def _keys(department: int):
    return [{FeaturePoint.BaseFeature: (bytes([department]) * 16, bytes([department]) * 32)}]


def _osd_records(n: int, latitude: float, gps_num: int = 18) -> list[Record]:
    return [Record(RecordType.OSD, OSD(latitude=latitude, gps_num=gps_num)) for _ in range(n)]


class FakeAPI:
    """Stands in for keychain.api.fetch_keychains, answering per department."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[int] = []

    def __call__(self, request, api_key, api_url=None):
        self.calls.append(request.department)
        answer = self.answers.get(request.department, "invalid department")
        if isinstance(answer, str):
            raise KeychainAPIError(answer, 1)
        return answer


@pytest.fixture
def log(monkeypatch, tmp_path):
    """A v14 DJILog whose header department is SDK and whose records decrypt
    sanely only with the department-2 keys."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        DJILog, "keychains_request",
        lambda self: KeychainsRequest(version=1, department=1, keychains_array=[]),
    )
    monkeypatch.setattr(
        DJILog, "keychains_request_with_custom_params",
        lambda self, department=None, version=None: KeychainsRequest(
            version=version or 1, department=department or 1, keychains_array=[],
        ),
    )

    def decrypt(self, keychains):
        good = keychains == _keys(2)
        return _osd_records(50, 59.91 if good else 0.0)

    monkeypatch.setattr(DJILog, "_decrypt_records", decrypt)

    lg = DJILog.__new__(DJILog)
    lg._data = b"synthetic v14 log"
    lg.version = 14
    return lg


def _install(monkeypatch, answers: dict) -> FakeAPI:
    api = FakeAPI(answers)
    monkeypatch.setattr(parser_mod, "fetch_keychains", api)
    return api


def test_falls_back_to_first_department_with_sane_osd(log, monkeypatch):
    # department 3 returns keys too, but they do not decrypt this log
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2), 3: _keys(3)})
    assert log.fetch_keychains("key", use_cache=False) == _keys(2)
    assert api.calls == [1, 2]


def test_skips_departments_whose_keys_do_not_decrypt(log, monkeypatch):
    monkeypatch.setattr(parser_mod, "FALLBACK_DEPARTMENTS", (3, 2))
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2), 3: _keys(3)})
    assert log.fetch_keychains("key", use_cache=False) == _keys(2)
    assert api.calls == [1, 3, 2]


def test_raises_original_error_when_no_department_works(log, monkeypatch):
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 3: _keys(3)})
    with pytest.raises(KeychainAPIError, match="invalid ciphertext") as exc:
        log.fetch_keychains("key", use_cache=False)
    assert exc.value.code == 1
    assert api.calls == [1, 2, 3, 4, 5, 6, 7, 8]


def test_other_api_errors_are_not_retried(log, monkeypatch):
    api = _install(monkeypatch, {1: "invalid version", 2: _keys(2)})
    with pytest.raises(KeychainAPIError, match="invalid version"):
        log.fetch_keychains("key", use_cache=False)
    assert api.calls == [1]


def test_explicit_department_is_not_overridden(log, monkeypatch):
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2)})
    with pytest.raises(KeychainAPIError):
        log.fetch_keychains("key", use_cache=False, department=1)
    assert api.calls == [1]


def test_fallback_can_be_disabled(log, monkeypatch):
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2)})
    with pytest.raises(KeychainAPIError):
        log.fetch_keychains("key", use_cache=False, department_fallback=False)
    assert api.calls == [1]


def test_fallback_keys_are_cached_as_default_entry(log, monkeypatch):
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2)})
    assert log.fetch_keychains("key") == _keys(2)
    assert api.calls == [1, 2]

    # Served from cache: no new API calls and no fallback round trip
    assert log.fetch_keychains("key") == _keys(2)
    assert api.calls == [1, 2]


def test_department_override_uses_separate_cache_entry(log, monkeypatch):
    api = _install(monkeypatch, {1: INVALID_CIPHERTEXT, 2: _keys(2), 3: _keys(3)})
    assert log.fetch_keychains("key") == _keys(2)

    # An explicit override neither reads nor overwrites the default entry
    assert log.fetch_keychains("key", department=3) == _keys(3)
    assert log.fetch_keychains("key", department=3) == _keys(3)
    assert log.fetch_keychains("key") == _keys(2)
    assert api.calls == [1, 2, 3]


def test_api_error_is_still_a_runtime_error():
    err = KeychainAPIError("invalid ciphertext", 1)
    assert isinstance(err, RuntimeError)
    assert str(err) == "DJI API error: invalid ciphertext (code=1)"
    assert err.is_invalid_ciphertext
    assert not KeychainAPIError("invalid version", 1).is_invalid_ciphertext


class TestOsdLooksSane:
    def test_valid_positions(self):
        assert parser_mod._osd_looks_sane(_osd_records(20, 59.91))

    def test_zero_latitude(self):
        assert not parser_mod._osd_looks_sane(_osd_records(20, 0.0))

    def test_implausible_satellite_count(self):
        assert not parser_mod._osd_looks_sane(_osd_records(20, 59.91, gps_num=200))

    def test_too_few_records(self):
        assert not parser_mod._osd_looks_sane(_osd_records(5, 59.91))

    def test_majority_required(self):
        records = _osd_records(15, 59.91) + _osd_records(5, 0.0)
        assert not parser_mod._osd_looks_sane(records)
        records = _osd_records(17, 59.91) + _osd_records(3, 0.0)
        assert parser_mod._osd_looks_sane(records)
