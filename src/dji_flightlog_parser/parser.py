"""Main DJILog parser class - the primary entry point for parsing flight logs."""

from __future__ import annotations

import logging
from collections import deque
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
from .keychain.api import fetch_keychains
from .keychain.cache import KeychainCache
from .record.reader import RecordReader, Record
from .record.types import RecordType
from .frame.builder import records_to_frames
from .frame.models import Frame

logger = logging.getLogger(__name__)


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
    ) -> list[Keychain]:
        """Fetch AES keychains from DJI API (sync).

        Caches results to avoid redundant API calls.
        """
        if use_cache:
            cache = KeychainCache()
            cached = cache.get(self._data)
            if cached is not None:
                logger.info("Using cached keychains")
                return cached

        if department is not None or version is not None:
            request = self.keychains_request_with_custom_params(department, version)
        else:
            request = self.keychains_request()
        keychains = fetch_keychains(request, api_key, api_url)

        if use_cache:
            cache = KeychainCache()
            cache.put(self._data, keychains)

        return keychains

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
            if len(keychains) == 0:
                logger.warning("Empty keychains list for v%d file; records will not be decrypted", self.version)
            else:
                return self._read_records_with_keychains(record_data, keychains, product_type)

        kc: Keychain = keychains[0] if keychains else {}
        reader = RecordReader(record_data, self.version, product_type)
        return reader.read_records(kc)

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

            # Skip summary/frame markers
            if record_type_val in (0xFD, 0xFE):
                offset = payload_end
                if offset < len(record_data) and record_data[offset] == 0xFF:
                    offset += 1
                continue

            # Decode payload
            from .decoder.aes import decode_record_payload
            decoded, current_kc = decode_record_payload(
                raw_payload, record_type_val, version, current_kc, length
            )

            record = record_parser._parse_record(record_type_val, decoded, length)
            all_records.append(record)

            offset = payload_end
            if offset < len(record_data) and record_data[offset] == 0xFF:
                offset += 1

        return all_records

    def frames(self, keychains: Optional[list[Keychain]] = None) -> list[Frame]:
        """Parse records and convert to normalized frames."""
        records = self.records(keychains)
        return records_to_frames(records, self.details)


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
    frames = records_to_frames(records, log.details)
    log._last_records = records

    details_dict = log.details.to_dict()

    # Build summary from details + first recover record
    summary = _build_summary(log, frames, details_dict)

    return {
        "version": log.version,
        "details": details_dict,
        "frames": [f.to_dict() for f in frames],
        "summary": summary,
    }


def _build_summary(log: DJILog, frames: list[Frame], details_dict: dict) -> dict:
    """Build a summary dict compatible with Loggflyt expectations."""
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
    """Add component serials, firmware, and battery health to summary."""
    from .record.component_serial import ComponentSerial
    from .record.firmware import Firmware

    records = getattr(log, "_last_records", None)
    if records is None:
        return

    component_serials: dict[str, str] = {}
    firmware_versions: list[dict] = []
    firmware_seen: set[tuple] = set()

    for r in records:
        if isinstance(r.data, ComponentSerial) and r.data.serial:
            comp_name = r.data.component_type.name
            component_serials[comp_name] = r.data.serial

        if isinstance(r.data, Firmware) and r.data.version:
            key = (r.data.sender_type, r.data.sub_sender_type, r.data.version)
            if key not in firmware_seen:
                firmware_seen.add(key)
                firmware_versions.append({
                    "senderType": r.data.sender_type,
                    "subSenderType": r.data.sub_sender_type,
                    "version": r.data.version,
                })

    if component_serials:
        summary["componentSerials"] = component_serials

    if firmware_versions:
        summary["firmwareVersions"] = firmware_versions

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
