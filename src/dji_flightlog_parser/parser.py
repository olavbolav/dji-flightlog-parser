"""Main DJILog parser class - the primary entry point for parsing flight logs."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Optional

from .layout.prefix import Prefix, PREFIX_SIZE
from .layout.auxiliary import Auxiliary, Department
from .layout.details import Details
from .decoder.feature_point import FeaturePoint
from .keychain.models import (
    Keychain, KeychainsRequest, EncodedKeychainFeaturePoint,
    build_keychain,
)
from .keychain.api import KeychainAPIError, fetch_keychains
from .keychain.cache import KeychainCache
from .record.osd import OSD
from .record.reader import RecordReader, Record
from .record.types import RecordType
from .frame.builder import battery_layout, records_to_frames
from .frame.models import Frame

logger = logging.getLogger(__name__)

# Plausible ranges (inclusive) for record-derived summary values; a value
# outside its range is treated as unknown. Valid for correctly decrypted logs.
_WARNING_THRESHOLD_RANGE = (1, 100)  # OSD battery warning thresholds, %
_STATE_OF_HEALTH_RANGE = (1, 110)  # static `life`, %; M400 reads up to 101
_WIND_SPEED_RANGE = (0.0, 40.0)  # OSD wind speed, m/s
_FLIGHT_COUNT_RANGE = (1, 1_000_000)  # Home aircraft_flight_count


def _in_range(value, bounds: tuple) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


# Departments tried, in order, when the DJI API rejects the department in the
# log header. Logs recorded through the Mobile SDK carry department=SDK, which
# the keychains API answers with "invalid ciphertext"; requesting the same keys
# as DJIGO (2) returns working keys.
FALLBACK_DEPARTMENTS = (2, 3, 4, 5, 6, 7, 8)


class DJILog:
    """Main parser for DJI flight log files.

    Usage:
        log = DJILog.from_file("flight.txt")
        # or
        log = DJILog.from_bytes(raw_bytes)

        # For v13+, fetch keychains
        keychains = log.fetch_keychains(api_key="your_key")

        # Parse records and frames
        records = log.records(keychains)
        frames = log.frames(keychains)
    """

    def __init__(self, data: bytes):
        self._data = data
        self.prefix = Prefix.from_bytes(data)
        self.version = self.prefix.version
        self.details: Details = Details()

        self._aux_info = None
        self._aux_version = None

        self._parse_structure()

    @classmethod
    def from_bytes(cls, data: bytes) -> DJILog:
        return cls(data)

    @classmethod
    def from_file(cls, path: str | Path) -> DJILog:
        data = Path(path).read_bytes()
        return cls(data)

    def _parse_structure(self) -> None:
        """Parse the file structure: prefix, auxiliary blocks, details."""
        if self.version < 13:
            detail_offset = self.prefix.effective_detail_offset()
            if detail_offset < len(self._data):
                detail_data = self._data[detail_offset:]
                # Pad to at least 400 bytes as Rust does
                if len(detail_data) < 400:
                    detail_data = detail_data + b"\x00" * (400 - len(detail_data))
                self.details = Details.from_bytes(detail_data, self.version)
        else:
            self._parse_v13_structure()

    def _parse_v13_structure(self) -> None:
        """Parse v13+ structure with auxiliary blocks."""
        offset = PREFIX_SIZE

        # First auxiliary: Info
        if offset < len(self._data):
            aux1, offset = Auxiliary.read_from(self._data, offset)
            if aux1.kind == 0 and aux1.info is not None:
                self._aux_info = aux1.info
                self.details = Details.from_bytes(aux1.info.info_data, self.version)

        # Check if records_offset needs recovery
        if self.prefix.records_offset() == 0 or self.prefix.records_offset() == PREFIX_SIZE:
            # Read second auxiliary: Version
            if offset < len(self._data):
                aux2, new_offset = Auxiliary.read_from(self._data, offset)
                if aux2.kind == 1 and aux2.version_block is not None:
                    self._aux_version = aux2.version_block
                # Recover detail_offset to point past auxiliary blocks
                self.prefix.detail_offset = new_offset

    def keychains_request(self) -> KeychainsRequest:
        """Build a KeychainsRequest from the file's KeyStorage records."""
        return self._build_keychains_request(None, None)

    def keychains_request_with_custom_params(
        self,
        department: Optional[int] = None,
        version: Optional[int] = None,
    ) -> KeychainsRequest:
        """Build a KeychainsRequest with optional parameter overrides."""
        return self._build_keychains_request(department, version)

    def _build_keychains_request(
        self,
        department_override: Optional[int] = None,
        version_override: Optional[int] = None,
    ) -> KeychainsRequest:
        """Scan the record stream for KeyStorage records and build the request."""
        # Determine version and department
        req_version = version_override if version_override is not None else (self._aux_version.version if self._aux_version else self.version)
        req_department = department_override

        if req_department is None:
            if self._aux_version is not None:
                dept = self._aux_version.department
                if isinstance(dept, Department):
                    req_department = int(dept)
                else:
                    req_department = 3  # Default to DJIFly
            else:
                req_department = 3

        # Read the auxiliary version block if not done yet
        if self._aux_version is None and self.version >= 13:
            offset = PREFIX_SIZE
            # Skip first auxiliary (info)
            if offset < len(self._data):
                _, offset = Auxiliary.read_from(self._data, offset)
            if offset < len(self._data):
                aux2, _ = Auxiliary.read_from(self._data, offset)
                if aux2.kind == 1 and aux2.version_block is not None:
                    self._aux_version = aux2.version_block
                    if version_override is None:
                        req_version = self._aux_version.version
                    if department_override is None:
                        dept = self._aux_version.department
                        req_department = int(dept) if isinstance(dept, Department) else 3

        # Scan records for KeyStorage
        records_start = self.prefix.records_offset()
        records_end = self.prefix.records_end_offset(len(self._data))
        record_data = self._data[records_start:records_end]

        reader = RecordReader(record_data, self.version)
        groups = reader.read_key_storage_records()

        keychains_array: list[list[EncodedKeychainFeaturePoint]] = []
        for group in groups:
            encoded = []
            for ks in group:
                try:
                    fp = FeaturePoint(ks.feature_point)
                except ValueError:
                    continue
                encoded.append(EncodedKeychainFeaturePoint(
                    feature_point=fp,
                    aes_ciphertext=ks.data,
                ))
            if encoded:
                keychains_array.append(encoded)

        return KeychainsRequest(
            version=req_version,
            department=req_department,
            keychains_array=keychains_array,
        )

    def fetch_keychains(
        self,
        api_key: str,
        api_url: Optional[str] = None,
        use_cache: bool = True,
        department: Optional[int] = None,
        version: Optional[int] = None,
        department_fallback: bool = True,
    ) -> list[Keychain]:
        """Fetch AES keychains from DJI API (sync).

        Caches results to avoid redundant API calls. Requests with a
        department or version override are cached separately from the
        default entry for the file.

        If the API rejects the log's own department with "invalid ciphertext"
        (as it does for logs recorded through the Mobile SDK) and no department
        was given, the departments in FALLBACK_DEPARTMENTS are tried in turn.
        Keys are accepted only if the OSD records they decrypt look sane, and
        the accepted keys are cached under the default entry.
        """
        cache_variant = _cache_variant(department, version)
        if use_cache:
            cache = KeychainCache()
            cached = cache.get(self._data, cache_variant)
            if cached is not None:
                logger.info("Using cached keychains")
                return cached

        if department is not None or version is not None:
            request = self.keychains_request_with_custom_params(department, version)
        else:
            request = self.keychains_request()

        try:
            keychains = fetch_keychains(request, api_key, api_url)
        except KeychainAPIError as e:
            if not (department_fallback and department is None and e.is_invalid_ciphertext):
                raise
            keychains = self._fetch_keychains_other_department(request, api_key, api_url, e)

        if use_cache:
            cache = KeychainCache()
            cache.put(self._data, keychains, cache_variant)

        return keychains

    def _fetch_keychains_other_department(
        self,
        request: KeychainsRequest,
        api_key: str,
        api_url: Optional[str],
        error: KeychainAPIError,
    ) -> list[Keychain]:
        """Retry a rejected keychains request as other departments.

        The API can return keys for a department that do not decrypt this log,
        so each candidate is checked against the decrypted OSD records.
        Raises the original error if no department yields sane records.
        """
        for department in FALLBACK_DEPARTMENTS:
            if department == request.department:
                continue
            try:
                keychains = fetch_keychains(replace(request, department=department), api_key, api_url)
            except KeychainAPIError as e:
                logger.debug("Keychains request as department=%d failed: %s", department, e)
                continue
            if _osd_looks_sane(self._decrypt_records(keychains)):
                logger.info(
                    "DJI API rejected department=%d (%s); using keychains requested as department=%d",
                    request.department, error.msg, department,
                )
                return keychains
            logger.debug("Keychains for department=%d do not decrypt this log", department)
        raise error

    def _decrypt_records(self, keychains: list[Keychain]) -> list[Record]:
        """Decrypt records with the given keychains without touching details."""
        records_start = self.prefix.records_offset()
        records_end = self.prefix.records_end_offset(len(self._data))
        product_type = int(self.details.product_type) if self.details else 0
        return self._read_records_with_keychains(
            self._data[records_start:records_end], keychains, product_type,
        )

    def records(self, keychains: Optional[list[Keychain]] = None) -> list[Record]:
        """Parse all records from the file.

        For v13+, keychains are required for decrypting AES-protected records.
        """
        records_start = self.prefix.records_offset()
        records_end = self.prefix.records_end_offset(len(self._data))
        record_data = self._data[records_start:records_end]

        product_type = int(self.details.product_type) if self.details else 0

        # For v13+, use keychains with rotation on KeyStorageRecover
        if self.version >= 13 and keychains is not None:
            if not any(keychains):
                # [] or only empty keychains ([{}]): nothing to decrypt with
                logger.warning("No keys in keychains list for v%d file; records will not be decrypted",
                               self.version)
            if keychains:
                result = self._read_records_with_keychains(record_data, keychains, product_type)
                self.enrich_details(result)
                return result

        kc: Keychain = keychains[0] if keychains else {}
        reader = RecordReader(record_data, self.version, product_type)
        result = reader.read_records(kc)
        self.enrich_details(result)
        return result

    def _read_records_with_keychains(
        self,
        record_data: bytes,
        keychains: list[Keychain],
        product_type: int,
    ) -> list[Record]:
        """Read records with keychain rotation on KeyStorageRecover boundaries."""
        kc_queue = deque(keychains)
        current_kc: Keychain = dict(kc_queue.popleft()) if kc_queue else {}

        all_records: list[Record] = []
        offset = 0
        version = self.version
        record_parser = RecordReader(b"", version, product_type)

        import struct
        from .record.reader import KEY_VALUE_CHANGE, emits_key_value_record
        while offset < len(record_data):
            if offset >= len(record_data):
                break

            record_type_val = record_data[offset]
            start_offset = offset
            offset += 1

            # Read length
            if version <= 12:
                if offset >= len(record_data):
                    break
                length = record_data[offset]
                offset += 1
            else:
                if offset + 2 > len(record_data):
                    break
                length = struct.unpack_from("<H", record_data, offset)[0]
                offset += 2

            payload_end = min(offset + length, len(record_data))
            if offset + length > len(record_data):
                logger.warning(
                    "Record payload truncated at offset %d: expected %d bytes, got %d",
                    offset, length, len(record_data) - offset,
                )
            raw_payload = record_data[offset:payload_end]

            if record_type_val == RecordType.KeyStorageRecover:
                offset = payload_end
                if offset < len(record_data) and record_data[offset] == 0xFF:
                    offset += 1
                if kc_queue:
                    current_kc = dict(kc_queue.popleft())
                continue

            if record_type_val == RecordType.KeyStorage:
                offset = payload_end
                if offset < len(record_data) and record_data[offset] == 0xFF:
                    offset += 1
                continue

            # Records 0xFD/0xFE are always decrypted to keep the DJIFlyCustom
            # IV chain intact; only 0xFD on v14 is emitted, as
            # KeyValueSnapshot (see RecordReader._read_one)
            if record_type_val in (RecordType.KeyValueSnapshot, KEY_VALUE_CHANGE):
                from .decoder.aes import decode_record_payload
                decoded, current_kc = decode_record_payload(
                    raw_payload, record_type_val, version, current_kc, length
                )
                if emits_key_value_record(record_type_val, version):
                    all_records.append(record_parser._parse_record(record_type_val, decoded, length))
                offset = payload_end
                if offset < len(record_data) and record_data[offset] == 0xFF:
                    offset += 1
                continue

            # Decode payload
            from .decoder.aes import decode_record_payload
            decoded, current_kc = decode_record_payload(
                raw_payload, record_type_val, version, current_kc, length
            )

            seed = raw_payload[0] if raw_payload else None
            record = record_parser._parse_record(record_type_val, decoded, length, seed)
            all_records.append(record)

            offset = payload_end
            if offset < len(record_data) and record_data[offset] == 0xFF:
                offset += 1

        return all_records

    def frames(self, keychains: Optional[list[Keychain]] = None) -> list[Frame]:
        """Parse records and convert to normalized frames."""
        records = self.records(keychains)
        self._last_records = records
        return records_to_frames(records, self.details, version=self.version)

    def enrich_details(self, records: list[Record]) -> None:
        """Enrich details from ComponentSerial records.

        The Details binary block has a fixed 16-byte serial field which
        truncates longer serials on newer drones. ComponentSerial records
        use a length-prefixed format that preserves the full serial.
        """
        from .record.component_serial import ComponentSerial

        current_sn = self.details.aircraft_sn
        if not current_sn:
            return

        for r in records:
            if isinstance(r.data, ComponentSerial) and r.data.serial:
                if r.data.serial.startswith(current_sn) and len(r.data.serial) > len(current_sn):
                    self.details.aircraft_sn = r.data.serial
                    return


def _cache_variant(department: Optional[int], version: Optional[int]) -> str:
    """Cache variant name for a keychains request with optional overrides."""
    parts = []
    if department is not None:
        parts.append(f"d{department}")
    if version is not None:
        parts.append(f"v{version}")
    return "-".join(parts)


def _osd_looks_sane(records: list[Record], min_osd: int = 10, min_fraction: float = 0.8) -> bool:
    """Heuristic check that OSD records were decrypted with the right keys.

    Wrongly decrypted OSD records come out empty or as noise, so require that
    most of them carry a valid, non-zero latitude and a plausible satellite count.
    """
    osds = [r.data for r in records if r.record_type == RecordType.OSD and isinstance(r.data, OSD)]
    if len(osds) < min_osd:
        return False
    ok = sum(1 for o in osds if -90 < o.latitude < 90 and o.latitude != 0 and 0 <= o.gps_num < 80)
    return ok / len(osds) > min_fraction


def parse_file(
    path: str | Path,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    use_cache: bool = True,
) -> dict:
    """High-level convenience function: parse a DJI flight log file to dict.

    Returns a dict with keys: version, details, frames, summary.
    This is the primary integration point for Loggflyt.
    """
    log = DJILog.from_file(path)

    keychains = None
    if log.version >= 13:
        if api_key:
            keychains = log.fetch_keychains(api_key, api_url, use_cache)
        else:
            logger.warning(
                "File is version %d (requires decryption) but no API key provided. "
                "Output will contain undecrypted records.",
                log.version,
            )

    records = log.records(keychains)
    log._last_records = records
    # No key, an empty keychain list or a list of empty keychains ([{}],
    # what the API gives when it answers with unusable items): v13+ records
    # are still encrypted, so the summary leaves out every value derived
    # from them
    log._undecrypted = log.version >= 13 and not any(keychains or [])
    frames = records_to_frames(records, log.details, version=log.version)

    details_dict = log.details.to_dict()
    summary = _build_summary(log, frames, details_dict)

    return {
        "version": log.version,
        "details": details_dict,
        "frames": [f.to_dict() for f in frames],
        "summary": summary,
    }


def _build_summary(log: DJILog, frames: list[Frame], details_dict: dict) -> dict:
    """Build a summary dict compatible with Loggflyt expectations.

    When ``log._undecrypted`` is set (v13+ parsed without keys, see
    ``parse_file``), only the values from the log header (details) are used;
    every value derived from the still-encrypted records is left out.
    """
    summary = {
        "startTime": details_dict.get("startTime"),
        "startCoordinate": details_dict.get("startCoordinate"),
        "totalTime": details_dict.get("totalTime"),
        "totalDistance": details_dict.get("totalDistance"),
        "maxHeight": details_dict.get("maxHeight"),
        "maxHorizontalSpeed": details_dict.get("maxHorizontalSpeed"),
        "maxVerticalSpeed": details_dict.get("maxVerticalSpeed"),
        "aircraftName": details_dict.get("aircraftName", ""),
        "aircraftSn": details_dict.get("aircraftSn", ""),
        "cameraSn": details_dict.get("cameraSn", ""),
        "rcSn": details_dict.get("rcSn", ""),
        "batterySn": details_dict.get("batterySn", ""),
        "appPlatform": details_dict.get("appPlatform", ""),
        "appVersion": details_dict.get("appVersion", ""),
        "productType": details_dict.get("productType", ""),
    }

    if getattr(log, "_undecrypted", False):
        return summary

    # Try to fill in from recover records in frames (often more complete)
    for f in frames:
        r = f.recover
        if r.rc_sn and not summary.get("rcSn"):
            summary["rcSn"] = r.rc_sn
        if r.aircraft_sn and not summary.get("aircraftSn"):
            summary["aircraftSn"] = r.aircraft_sn
        if r.battery_sn and not summary.get("batterySn"):
            summary["batterySn"] = r.battery_sn
        if r.camera_sn and not summary.get("cameraSn"):
            summary["cameraSn"] = r.camera_sn
        if r.aircraft_name and not summary.get("aircraftName"):
            summary["aircraftName"] = r.aircraft_name
        if any([r.rc_sn, r.aircraft_sn, r.battery_sn]):
            break  # Found recover data

    _enrich_summary(log, frames, summary)

    return summary


def _enrich_summary(log: DJILog, frames: list[Frame], summary: dict) -> None:
    """Add component serials, firmware, battery health and per-log settings to summary.

    Keys are added only when the log carries the value, and none at all when
    ``log._undecrypted`` is set (the records are encrypted noise then).
    """
    from .record.camera import Camera, camera_model_name
    from .record.component_serial import ComponentSerial
    from .record.firmware import Firmware
    from .record.home import Home
    from .record.key_value_snapshot import KEY_SNAPSHOT, MODULE_COMPONENT_SERIALS, KeyValueSnapshot
    from .record.mc_params import FailSafe, MCParams
    from .record.smart_battery_group import SmartBatteryGroup, SmartBatteryStatic

    records = getattr(log, "_last_records", None)
    if records is None or getattr(log, "_undecrypted", False):
        return

    component_serials: dict[str, str] = {}
    firmware_versions: list[dict] = []
    firmware_seen: set[tuple] = set()
    camera_type = None
    statics: dict[int, SmartBatteryStatic] = {}  # first static record per pack index
    serial_snapshot: Optional[KeyValueSnapshot] = None
    rc_lost_action: Optional[str] = None
    low_threshold: Optional[int] = None
    critical_threshold: Optional[int] = None
    aircraft_flight_count: Optional[int] = None
    max_wind_speed: Optional[float] = None

    for r in records:
        d = r.data
        if isinstance(d, OSD):
            # Thresholds are constant within every log and set from the first
            # record (checked on 74 logs); take the first plausible value.
            if low_threshold is None and _in_range(d.low_battery_warning, _WARNING_THRESHOLD_RANGE):
                low_threshold = d.low_battery_warning
            if critical_threshold is None and _in_range(d.critical_battery_warning, _WARNING_THRESHOLD_RANGE):
                critical_threshold = d.critical_battery_warning
            if (_in_range(d.wind_speed, _WIND_SPEED_RANGE)
                    and (max_wind_speed is None or d.wind_speed > max_wind_speed)):
                max_wind_speed = d.wind_speed

        elif isinstance(d, SmartBatteryGroup):
            if d.static is not None:
                statics.setdefault(d.static.index, d.static)

        elif isinstance(d, Home):
            # Goes up by one at take-off; the last value includes this flight
            if _in_range(d.aircraft_flight_count, _FLIGHT_COUNT_RANGE):
                aircraft_flight_count = d.aircraft_flight_count

        elif isinstance(d, MCParams):
            if rc_lost_action is None and d.fail_safe != FailSafe.UNKNOWN:
                rc_lost_action = d.fail_safe.name

        elif isinstance(d, KeyValueSnapshot):
            # Repeated snapshots within a log are identical; take the first
            if serial_snapshot is None and (d.module, d.key) == (MODULE_COMPONENT_SERIALS, KEY_SNAPSHOT):
                serial_snapshot = d

        elif isinstance(r.data, ComponentSerial) and r.data.serial:
            comp_name = r.data.component_type.name
            component_serials[comp_name] = r.data.serial

        elif isinstance(r.data, Firmware):
            for e in r.data.entries:
                key = (e.sender_type, e.sub_sender_type, e.full_version)
                if key not in firmware_seen:
                    firmware_seen.add(key)
                    firmware_versions.append({
                        "senderType": e.sender_type,
                        "subSenderType": e.sub_sender_type,
                        "version": e.version,
                        "senderName": e.sender_name,
                        "fullVersion": e.full_version,
                    })

        elif camera_type is None and isinstance(r.data, Camera):
            camera_type = r.data.camera_type

    if component_serials:
        summary["componentSerials"] = component_serials

    if firmware_versions:
        summary["firmwareVersions"] = firmware_versions

    if camera_type is not None:
        summary["cameraType"] = camera_type
        summary["cameraModel"] = camera_model_name(camera_type)

    for f in frames:
        b = f.battery
        if b.cycle_count is not None:
            summary["batteryCycleCount"] = b.cycle_count
        if b.designed_capacity is not None:
            summary["batteryDesignedCapacity"] = b.designed_capacity
        if b.battery_serial:
            summary["batterySerial"] = b.battery_serial
        if b.cycle_count is not None:
            break

    if statics:
        # The pack the frames use: index 1, else 2 (dual battery), else 0
        primary = statics.get(battery_layout(records).static_index)
        if primary is not None:
            if _in_range(primary.life, _STATE_OF_HEALTH_RANGE):  # 0 = unknown (Mini 5 Pro)
                summary["batteryStateOfHealth"] = primary.life
            if primary.manufacture_date:
                summary["batteryManufactureDate"] = primary.manufacture_date
        summary["batteries"] = [_static_summary(statics[i]) for i in sorted(statics)]

    if serial_snapshot is not None:
        # Fields 7 and 8 are battery slots 1 and 2 (slot order, not pack
        # index); field 6 is an accessory, only seen on M4TD.
        battery_sns = [serial_snapshot.serials[n] for n in (7, 8) if serial_snapshot.serials.get(n)]
        if battery_sns:
            summary["batterySns"] = battery_sns
        accessory_sn = serial_snapshot.serials.get(6)
        if accessory_sn:
            summary["accessorySn"] = accessory_sn

    if rc_lost_action is not None:
        summary["rcLostAction"] = rc_lost_action
    if low_threshold is not None:
        summary["lowBatteryWarningThreshold"] = low_threshold
    if critical_threshold is not None:
        summary["criticalBatteryWarningThreshold"] = critical_threshold
    if aircraft_flight_count is not None:
        summary["aircraftFlightCount"] = aircraft_flight_count
    if max_wind_speed is not None:
        summary["maxWindSpeed"] = max_wind_speed


def _static_summary(s) -> dict:
    """Summary entry for one SmartBatteryGroup static record (unknown values are None)."""
    return {
        "index": s.index,
        "cycleCount": s.loop_times if s.loop_times > 0 else None,
        "designedCapacity": s.designed_capacity if 0 < s.designed_capacity < 100000 else None,
        "stateOfHealth": s.life if _in_range(s.life, _STATE_OF_HEALTH_RANGE) else None,
        "manufactureDate": s.manufacture_date,
    }
