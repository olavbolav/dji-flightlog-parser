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
from .vision import VisionGroup
from .fc_common_osd import FCCommonOSD
from .adsb import ADSBFlightData
from .jpeg import JPEG
from .gs_mission_status import GSMissionStatus
from .rtk_difference import RTKDifference
from .ground_station_push import AgricultureGroundStationPush
from .go_business import GOBusinessData
from .security import SecurityBlock
from .airlink import AirLinkDataField
from .key_value_snapshot import KeyValueSnapshot
from .unknown import UnknownRecord
from ..decoder.aes import decode_record_payload
from ..decoder.feature_point import FeaturePoint
from ..keychain.models import Keychain

logger = logging.getLogger(__name__)

END_BYTE = 0xFF

# DJIFlyCustom value-change record (0xFE). Decrypted on v14 to keep the IV
# chain intact, never emitted (its wind values duplicate OSD bytes 63/64).
KEY_VALUE_CHANGE = 0xFE


def emits_key_value_record(record_type_val: int, version: int) -> bool:
    """True if a 0xFD/0xFE record is emitted: only 0xFD (KeyValueSnapshot) on v14+."""
    return record_type_val == RecordType.KeyValueSnapshot and version >= 14


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
        if offset + length > len(self.data):
            logger.warning(
                "Record payload truncated at offset %d: expected %d bytes, got %d",
                offset, length, len(self.data) - offset,
            )
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

        # On v14, records 0xFD/0xFE are AES encrypted in the DJIFlyCustom IV
        # chain, so always decrypt them: skipping one garbles the first block
        # of the next record in that chain (tips, warnings, Custom,
        # GOBusiness and the other DJIFlyCustom types). Only 0xFD on v14 is
        # emitted (KeyValueSnapshot); v13 and older emit neither.
        if record_type_val == RecordType.KeyValueSnapshot or record_type_val == KEY_VALUE_CHANGE:
            decoded = b""
            if self.version >= 13:
                decoded, keychain = decode_record_payload(
                    raw_payload, record_type_val, self.version, keychain, length
                )
            record = None
            if emits_key_value_record(record_type_val, self.version):
                record = self._parse_record(record_type_val, decoded, length)
            offset = payload_end
            if offset < len(self.data) and self.data[offset] == END_BYTE:
                offset += 1
            return record, offset, keychain

        # Decode payload
        decoded, keychain = decode_record_payload(
            raw_payload, record_type_val, self.version, keychain, length
        )

        next_offset = None
        if self.version <= 12 and record_type_val == RecordType.GOBusiness:
            recovered = self._recover_v12_length_overflow(
                offset, length, payload_end, decoded, keychain
            )
            if recovered is not None:
                decoded, next_offset = recovered

        # Parse the decoded payload
        seed = raw_payload[0] if raw_payload else None
        record = self._parse_record(record_type_val, decoded, length, seed)

        if next_offset is not None:
            return record, next_offset, keychain

        offset = payload_end
        if offset < len(self.data) and self.data[offset] == END_BYTE:
            offset += 1

        return record, offset, keychain

    def _v12_frames_ok(self, pos: int, count: int = 2) -> bool:
        """True if ``count`` consecutive v12 frames (type, u8 length, payload, 0xFF) chain from pos.

        Chaining stops after a GOBusiness frame: it may itself be an overflow
        record, whose wrapped terminator is in place but whose true end is not.
        """
        for _ in range(count):
            if pos >= len(self.data) - 1:
                return True  # end of stream
            end = pos + 2 + self.data[pos + 1]
            if end >= len(self.data):
                return True
            if self.data[end] != END_BYTE:
                return False
            if self.data[pos] == RecordType.GOBusiness:
                return True
            pos = end + 1
        return True

    def _decode_v12_go_business(self, raw: bytes, size: int, keychain: Keychain) -> bytes | None:
        decoded, _ = decode_record_payload(raw, RecordType.GOBusiness, self.version, keychain, size)
        return decoded if GOBusinessData.accepts(decoded, self.version) else None

    def _recover_v12_length_overflow(
        self,
        offset: int,
        length: int,
        payload_end: int,
        decoded: bytes,
        keychain: Keychain,
    ) -> tuple[bytes, int] | None:
        """Recover a v12 GOBusiness record whose length overflowed the u8 field.

        When a v12 type-54 payload exceeds 255 bytes, the writer stores only
        ``length & 0xFF`` but still writes the full payload, places the 0xFF
        terminator at the wrapped offset (overwriting payload byte ``length``,
        which is the XOR seed when length is 0) and leaves one non-0xFF byte
        after the true end. Without recovery the reader desyncs and loses the
        following records.

        Returns (decoded_payload, next_record_offset) or None if the record
        is not an overflow case.
        """
        primary_parses = GOBusinessData.accepts(decoded, self.version)
        primary_frames_ok = self._v12_frames_ok(payload_end + 1)
        if primary_parses and primary_frames_ok:
            return None

        for extra in (256, 512):
            true_len = length + extra
            true_end = offset + true_len
            if true_end >= len(self.data) or self.data[true_end] == END_BYTE:
                continue
            if not self._v12_frames_ok(true_end + 1):
                continue

            raw = bytearray(self.data[offset:true_end])
            candidate = self._decode_v12_go_business(bytes(raw), true_len, keychain)
            if candidate is None:
                # The terminator overwrote a protobuf structure byte (or the
                # seed) rather than text: try each value for that byte.
                for value in range(256):
                    if value == END_BYTE:
                        continue
                    raw[length] = value
                    candidate = self._decode_v12_go_business(bytes(raw), true_len, keychain)
                    if candidate is not None:
                        break
            if candidate is None:
                if primary_parses or primary_frames_ok:
                    continue  # no clear evidence of an overflow at this length
                # The framing is clear but the payload is damaged; keep the
                # stream in sync and let the record fall back to unknown.
                candidate, _ = decode_record_payload(
                    self.data[offset:true_end], RecordType.GOBusiness, self.version, keychain, true_len
                )
            logger.debug("Recovered v12 GOBusiness length overflow at offset %d (%d -> %d bytes)",
                         offset, length, true_len)
            return candidate, true_end + 1
        return None

    def _parse_record(
        self, record_type_val: int, data: bytes, length: int, seed: int | None = None
    ) -> Record:
        """Parse decoded payload into a typed Record."""
        rt = RecordType.from_value(record_type_val)
        v = self.version

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
            elif rt == RecordType.VisionGroup:
                return Record(rt, VisionGroup.from_bytes(data, self.version))
            elif rt == RecordType.FlightControllerCommonOSD:
                return Record(rt, FCCommonOSD.from_bytes(data, self.version))
            elif rt == RecordType.ADSBFlightData:
                return Record(rt, ADSBFlightData.from_bytes(data, self.version))
            elif rt == RecordType.GSMissionStatus and GSMissionStatus.accepts(data, v):
                return Record(rt, GSMissionStatus.from_bytes(data, v))
            elif rt == RecordType.RTKDifference and RTKDifference.accepts(data, v):
                return Record(rt, RTKDifference.from_bytes(data, v))
            elif rt == RecordType.AgricultureGroundStationPush and AgricultureGroundStationPush.accepts(data, v):
                return Record(rt, AgricultureGroundStationPush.from_bytes(data, v))
            elif rt == RecordType.GOBusiness and GOBusinessData.accepts(data, v):
                return Record(rt, GOBusinessData.from_bytes(data, v))
            elif rt == RecordType.Security and SecurityBlock.accepts(data, v):
                return Record(rt, SecurityBlock.from_bytes(data, v, seed))
            elif rt == RecordType.AirLinkDataField and AirLinkDataField.accepts(data, v):
                return Record(rt, AirLinkDataField.from_bytes(data, v))
            elif rt == RecordType.KeyValueSnapshot and KeyValueSnapshot.accepts(data, v):
                return Record(rt, KeyValueSnapshot.from_bytes(data, v))
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
