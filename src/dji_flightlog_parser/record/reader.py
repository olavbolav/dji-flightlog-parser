"""Record stream reader with type dispatch and error recovery."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Any

from .types import RecordType
from .osd import OSD
from .home import Home
from .gimbal import Gimbal
from .rc import RC
from .battery import CenterBattery, SmartBattery
from .camera import Camera
from .app import AppTip, AppWarn, AppSeriousWarn, AppGPS
from .custom import Custom
from .recover import Recover
from .firmware import Firmware
from .component_serial import ComponentSerial
from .smart_battery_group import SmartBatteryGroup
from .deform import Deform
from .virtual_stick import VirtualStick
from .ofdm import OFDM
from .mc_params import MCParams
from .rc_gps import RCGPS
from .rc_display import RCDisplayField
from .jpeg import JPEG
from .unknown import UnknownRecord
from ..decoder.aes import decode_record_payload
from ..decoder.feature_point import FeaturePoint
from ..keychain.models import Keychain

logger = logging.getLogger(__name__)

END_BYTE = 0xFF


@dataclass
class Record:
    """Wrapper for a parsed record with its type tag."""
    record_type: RecordType | int
    data: Any = None

    def type_name(self) -> str:
        if isinstance(self.record_type, RecordType):
            return self.record_type.name
        return f"Unknown({self.record_type})"


@dataclass
class KeyStorageData:
    """Extracted KeyStorage ciphertext for building keychain requests."""
    feature_point: int  # raw u16
    data: bytes = b""


class RecordReader:
    """Reads and decodes records from the binary record stream."""

    def __init__(self, data: bytes, version: int, product_type: int = 0):
        self.data = data
        self.version = version
        self.product_type = product_type

    def read_length(self, offset: int) -> tuple[int, int]:
        """Read record length field. Returns (length, bytes_consumed)."""
        if self.version <= 12:
            if offset >= len(self.data):
                return 0, 0
            return self.data[offset], 1
        else:
            if offset + 2 > len(self.data):
                return 0, 0
            return struct.unpack_from("<H", self.data, offset)[0], 2

    def read_records(self, keychain: Keychain | None = None) -> list[Record]:
        """Read all records from the stream."""
        records: list[Record] = []
        offset = 0
        kc = dict(keychain) if keychain else {}

        while offset < len(self.data):
            try:
                record, offset, kc = self._read_one(offset, kc)
                if record is not None:
                    records.append(record)
            except Exception as e:
                logger.debug("Record parse error at offset %d: %s", offset, e)
                offset = self._seek_next(offset + 1)
                if offset < 0:
                    break

        return records

    def read_key_storage_records(self) -> list[list[KeyStorageData]]:
        """Scan for KeyStorage/KeyStorageRecover records to build keychain requests.
        Returns groups of KeyStorageData split by KeyStorageRecover markers."""
        groups: list[list[KeyStorageData]] = [[]]
        offset = 0

        while offset < len(self.data):
            if offset >= len(self.data):
                break

            record_type = self.data[offset]
            offset += 1

            length, consumed = self.read_length(offset)
            offset += consumed

            if record_type == RecordType.KeyStorage and length > 0:
                # Include the 0xFF terminator in XOR decode, matching Rust behavior
                # where XorDecoder reads seed(1) + count(length) bytes total
                payload_end = min(offset + length, len(self.data))
                term_end = min(payload_end + 1, len(self.data))
                raw_payload = self.data[offset:term_end]

                from ..decoder.xor import xor_decode_block
                decoded = xor_decode_block(raw_payload, record_type)

                if len(decoded) >= 4:
                    fp_val = struct.unpack_from("<H", decoded, 0)[0]
                    data_length = struct.unpack_from("<H", decoded, 2)[0]
                    ks_data = decoded[4:4 + data_length]
                    groups[-1].append(KeyStorageData(feature_point=fp_val, data=ks_data))

                offset = term_end

            elif record_type == RecordType.KeyStorageRecover:
                offset += length
                if offset < len(self.data) and self.data[offset] == END_BYTE:
                    offset += 1
                groups.append([])

            else:
                offset += length
                if offset < len(self.data) and self.data[offset] == END_BYTE:
                    offset += 1

        return groups

    def _read_one(self, offset: int, keychain: Keychain) -> tuple[Record | None, int, Keychain]:
        """Read one record. Returns (record_or_None, new_offset, updated_keychain)."""
        if offset >= len(self.data):
            return None, len(self.data), keychain

        record_type_val = self.data[offset]
        offset += 1

        length, consumed = self.read_length(offset)
        offset += consumed

        if length == 0 and record_type_val == END_BYTE:
            return None, offset, keychain

        payload_end = min(offset + length, len(self.data))
        raw_payload = self.data[offset:payload_end]

        # Skip KeyStorage and KeyStorageRecover during normal record reading
        if record_type_val == RecordType.KeyStorage:
            offset = payload_end
            if offset < len(self.data) and self.data[offset] == END_BYTE:
                offset += 1
            return None, offset, keychain

        if record_type_val == RecordType.KeyStorageRecover:
            offset = payload_end
            if offset < len(self.data) and self.data[offset] == END_BYTE:
                offset += 1
            return None, offset, keychain

        # JPEG/Summary records: skip payload and terminator
        if record_type_val == 0xFD or record_type_val == 0xFE:
            offset = payload_end
            if offset < len(self.data) and self.data[offset] == END_BYTE:
                offset += 1
            return None, offset, keychain

        # Decode payload
        decoded, keychain = decode_record_payload(
            raw_payload, record_type_val, self.version, keychain, length
        )

        # Parse the decoded payload
        record = self._parse_record(record_type_val, decoded, length)

        offset = payload_end
        if offset < len(self.data) and self.data[offset] == END_BYTE:
            offset += 1

        return record, offset, keychain

    def _parse_record(self, record_type_val: int, data: bytes, length: int) -> Record:
        """Parse decoded payload into a typed Record."""
        rt = RecordType.from_value(record_type_val)

        try:
            if rt == RecordType.OSD:
                return Record(rt, OSD.from_bytes(data, self.version))
            elif rt == RecordType.Home:
                return Record(rt, Home.from_bytes(data, self.version))
            elif rt == RecordType.Gimbal:
                return Record(rt, Gimbal.from_bytes(data, self.version))
            elif rt == RecordType.RC:
                return Record(rt, RC.from_bytes(data, self.version, self.product_type))
            elif rt == RecordType.Custom:
                return Record(rt, Custom.from_bytes(data, self.version))
            elif rt == RecordType.Deform:
                return Record(rt, Deform.from_bytes(data, self.version))
            elif rt == RecordType.CenterBattery:
                return Record(rt, CenterBattery.from_bytes(data, self.version))
            elif rt == RecordType.SmartBattery:
                return Record(rt, SmartBattery.from_bytes(data, self.version))
            elif rt == RecordType.AppTip:
                return Record(rt, AppTip.from_bytes(data, length))
            elif rt == RecordType.AppWarn:
                return Record(rt, AppWarn.from_bytes(data, length))
            elif rt == RecordType.AppSeriousWarn:
                return Record(rt, AppSeriousWarn.from_bytes(data, length))
            elif rt == RecordType.RCGPS:
                return Record(rt, RCGPS.from_bytes(data, self.version))
            elif rt == RecordType.Recover:
                return Record(rt, Recover.from_bytes(data, self.version))
            elif rt == RecordType.AppGPS:
                return Record(rt, AppGPS.from_bytes(data, self.version))
            elif rt == RecordType.Firmware:
                return Record(rt, Firmware.from_bytes(data, self.version))
            elif rt == RecordType.MCParams:
                return Record(rt, MCParams.from_bytes(data, self.version))
            elif rt == RecordType.SmartBatteryGroup:
                return Record(rt, SmartBatteryGroup.from_bytes(data, self.version))
            elif rt == RecordType.Camera:
                return Record(rt, Camera.from_bytes(data, self.version))
            elif rt == RecordType.VirtualStick:
                return Record(rt, VirtualStick.from_bytes(data, self.version))
            elif rt == RecordType.ComponentSerial:
                return Record(rt, ComponentSerial.from_bytes(data, self.version))
            elif rt == RecordType.OFDM:
                return Record(rt, OFDM.from_bytes(data, self.version))
            elif rt == RecordType.RCDisplayField:
                return Record(rt, RCDisplayField.from_bytes(data, self.version))
            else:
                return Record(record_type_val, UnknownRecord(record_type=record_type_val, data=data))
        except Exception as e:
            logger.debug("Failed to parse record type %s: %s", rt, e)
            return Record(record_type_val, UnknownRecord(record_type=record_type_val, data=data))

    def _seek_next(self, offset: int) -> int:
        """Seek to next likely record boundary after a parse error."""
        while offset < len(self.data) - 1:
            b = self.data[offset]
            if b == 0xFF:
                if offset + 1 < len(self.data) and self.data[offset + 1] == 0xD8:
                    return offset  # JPEG marker
                return offset + 1  # End byte, next record starts after
            offset += 1
        return -1
