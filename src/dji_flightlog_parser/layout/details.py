"""Flight details extraction from DJI log files."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional


class ProductType(IntEnum):
    NONE = 0
    Inspire1 = 1
    Phantom3Standard = 2
    Phantom3Advanced = 3
    Phantom3Pro = 4
    OSMO = 5
    Matrice100 = 6
    Phantom4 = 7
    LB2 = 8
    Inspire1Pro = 9
    A3 = 10
    Matrice600 = 11
    Phantom34K = 12
    MavicPro = 13
    ZenmuseXT = 14
    Inspire1RAW = 15
    A2 = 16
    Inspire2 = 17
    OSMOPro = 18
    OSMORaw = 19
    OSMOPlus = 20
    Mavic = 21
    OSMOMobile = 22
    OrangeCV600 = 23
    Phantom4Pro = 24
    N3FC = 25
    Spark = 26
    Matrice600Pro = 27
    Phantom4Advanced = 28
    Phantom3SE = 29
    AG405 = 30
    Matrice200 = 31
    Matrice210 = 33
    Matrice210RTK = 34
    MavicAir = 38
    Mavic2 = 42
    Phantom4ProV2 = 44
    Phantom4RTK = 46
    Phantom4Multispectral = 57
    Mavic2Enterprise = 58
    MavicMini = 59
    Matrice200V2 = 60
    Matrice210V2 = 61
    Matrice210RTKV2 = 62
    MavicAir2 = 67
    Matrice300RTK = 70
    FPV = 73
    MavicAir2S = 75
    Mini2 = 76
    Mavic3 = 77
    MiniSE = 96
    Mini3Pro = 103
    Mavic3Pro = 111
    Mini2SE = 113
    Matrice30 = 116
    Mavic3Enterprise = 118
    Avata = 121
    Mini4Pro = 126
    Avata2 = 152
    Matrice350RTK = 170

    @classmethod
    def from_value(cls, val: int) -> ProductType:
        try:
            return cls(val)
        except ValueError:
            return cls.NONE

    def battery_cell_num(self) -> int:
        _MAP = {
            1: 6, 2: 4, 3: 4, 4: 4, 6: 6, 7: 4, 9: 6, 11: 6, 12: 4,
            13: 3, 15: 6, 17: 6, 21: 3, 24: 4, 26: 3, 27: 6, 28: 4,
            29: 4, 31: 6, 33: 6, 34: 6, 38: 3, 42: 4, 44: 4, 46: 4,
            57: 4, 58: 4, 59: 2, 60: 6, 61: 6, 62: 6, 67: 3, 70: 12,
            73: 6, 75: 3, 76: 2, 77: 4, 96: 2, 103: 2, 111: 4, 113: 2,
            116: 6, 118: 4, 121: 5, 126: 2, 152: 4, 170: 12,
        }
        return _MAP.get(self.value, 4)

    def battery_num(self) -> int:
        _MAP = {
            1: 2, 6: 2, 9: 2, 11: 6, 15: 2, 17: 2, 27: 6,
            31: 2, 33: 2, 34: 2, 60: 2, 61: 2, 62: 2, 70: 2,
            116: 2, 170: 2,
        }
        return _MAP.get(self.value, 1)


class Platform(IntEnum):
    Unknown = 0
    IOS = 1
    Android = 2
    DJIFly = 6
    Windows = 10
    Mac = 11
    Linux = 12

    @classmethod
    def from_value(cls, val: int) -> Platform:
        try:
            return cls(val)
        except ValueError:
            return cls.Unknown

    def to_json(self) -> str:
        return self.name


def _read_string(data: bytes, offset: int, length: int) -> str:
    end = min(offset + length, len(data))
    raw = data[offset:end]
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _parse_battery_sn(product_type: ProductType, buf: bytes) -> str:
    bcd_types = {ProductType.Inspire1, ProductType.Inspire1Pro, ProductType.Inspire1RAW}
    if product_type in bcd_types:
        digits = []
        for b in buf:
            digits.append(chr((b & 0x0F) + ord('0')))
        digits.reverse()
        result = "".join(digits).lstrip("0")
        return result or "0"
    return buf.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


@dataclass
class Details:
    sub_street: str = ""
    street: str = ""
    city: str = ""
    area: str = ""
    is_favorite: bool = False
    is_new: bool = False
    needs_upload: bool = False
    record_line_count: int = 0
    detail_info_checksum: int = 0
    start_time: Optional[datetime] = None
    longitude: float = 0.0
    latitude: float = 0.0
    total_distance: float = 0.0
    total_time: float = 0.0
    max_height: float = 0.0
    max_horizontal_speed: float = 0.0
    max_vertical_speed: float = 0.0
    capture_num: int = 0
    video_time: int = 0
    moment_pic_longitude: list[float] = field(default_factory=list)
    moment_pic_latitude: list[float] = field(default_factory=list)
    take_off_altitude: float = 0.0
    product_type: ProductType = ProductType.NONE
    aircraft_sn: str = ""
    aircraft_name: str = ""
    app_platform: Platform = Platform.Unknown
    app_version: str = ""
    camera_sn: str = ""
    rc_sn: str = ""
    battery_sn: str = ""

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> Details:
        d = cls()
        if len(data) < 83:
            return d
        try:
            d._parse(data, version)
        except Exception:
            pass
        return d

    def _parse(self, data: bytes, version: int) -> None:
        if version <= 5:
            self._parse_legacy(data, version)
            return

        offset = 0
        self.sub_street = _read_string(data, offset, 20); offset += 20
        self.street = _read_string(data, offset, 20); offset += 20
        self.city = _read_string(data, offset, 20); offset += 20
        self.area = _read_string(data, offset, 20); offset += 20

        # 3 separate u8 flag fields
        self.is_favorite = bool(data[offset]); offset += 1
        self.is_new = bool(data[offset]); offset += 1
        self.needs_upload = bool(data[offset]); offset += 1

        self.record_line_count = struct.unpack_from("<i", data, offset)[0]; offset += 4
        self.detail_info_checksum = struct.unpack_from("<i", data, offset)[0]; offset += 4

        ts_ms = struct.unpack_from("<q", data, offset)[0]; offset += 8
        if ts_ms > 0:
            self.start_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        self.longitude = struct.unpack_from("<d", data, offset)[0]; offset += 8
        self.latitude = struct.unpack_from("<d", data, offset)[0]; offset += 8

        self.total_distance = struct.unpack_from("<f", data, offset)[0]; offset += 4

        total_time_raw = struct.unpack_from("<i", data, offset)[0]; offset += 4
        self.total_time = total_time_raw / 1000.0

        self.max_height = struct.unpack_from("<f", data, offset)[0]; offset += 4
        self.max_horizontal_speed = struct.unpack_from("<f", data, offset)[0]; offset += 4
        self.max_vertical_speed = struct.unpack_from("<f", data, offset)[0]; offset += 4

        self.capture_num = struct.unpack_from("<i", data, offset)[0]; offset += 4
        self.video_time = struct.unpack_from("<q", data, offset)[0]; offset += 8

        # moment_pic_image_buffer_len: 4 x i32
        offset += 16
        # moment_pic_shrink_image_buffer_len: 4 x i32
        offset += 16

        # Moment picture coordinates (4 x f64 longitude, 4 x f64 latitude) in radians
        for _ in range(4):
            if offset + 8 <= len(data):
                self.moment_pic_longitude.append(math.degrees(struct.unpack_from("<d", data, offset)[0]))
                offset += 8
        for _ in range(4):
            if offset + 8 <= len(data):
                self.moment_pic_latitude.append(math.degrees(struct.unpack_from("<d", data, offset)[0]))
                offset += 8

        # _analysis_offset: i64 (temp)
        offset += 8
        # _user_api_center_id_md5: [u8; 16] (temp)
        offset += 16

        if offset + 4 <= len(data):
            self.take_off_altitude = struct.unpack_from("<f", data, offset)[0]; offset += 4

        if offset + 1 <= len(data):
            self.product_type = ProductType.from_value(data[offset]); offset += 1

        # _activation_timestamp: i64 (temp)
        offset += 8

        name_len = 24 if version <= 5 else 32
        sn_len = 10 if version <= 5 else 16

        if offset + name_len <= len(data):
            self.aircraft_name = _read_string(data, offset, name_len); offset += name_len

        if offset + sn_len <= len(data):
            self.aircraft_sn = _read_string(data, offset, sn_len); offset += sn_len

        if offset + sn_len <= len(data):
            self.camera_sn = _read_string(data, offset, sn_len); offset += sn_len

        if offset + sn_len <= len(data):
            self.rc_sn = _read_string(data, offset, sn_len); offset += sn_len

        if offset + sn_len <= len(data):
            battery_buf = data[offset:offset + sn_len]
            self.battery_sn = _parse_battery_sn(self.product_type, battery_buf)
            offset += sn_len

        if offset + 1 <= len(data):
            self.app_platform = Platform.from_value(data[offset]); offset += 1

        if offset + 3 <= len(data):
            self.app_version = f"{data[offset]}.{data[offset+1]}.{data[offset+2]}"
            offset += 3

    def _parse_legacy(self, data: bytes, version: int) -> None:
        self.sub_street = _read_string(data, 0, 20)
        self.street = _read_string(data, 20, 20)
        self.city = _read_string(data, 40, 20)
        self.area = _read_string(data, 60, 20)

    def to_dict(self) -> dict:
        result = {
            "subStreet": self.sub_street,
            "street": self.street,
            "city": self.city,
            "area": self.area,
            "isFavorite": self.is_favorite,
            "isNew": self.is_new,
            "needsUpload": self.needs_upload,
            "recordLineCount": self.record_line_count,
            "startTime": self.start_time.isoformat().replace("+00:00", "Z") if self.start_time else None,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "totalDistance": self.total_distance,
            "totalTime": self.total_time,
            "maxHeight": self.max_height,
            "maxHorizontalSpeed": self.max_horizontal_speed,
            "maxVerticalSpeed": self.max_vertical_speed,
            "captureNum": self.capture_num,
            "videoTime": self.video_time,
            "aircraftSn": self.aircraft_sn,
            "aircraftName": self.aircraft_name,
            "appPlatform": self.app_platform.name if isinstance(self.app_platform, Platform) else str(self.app_platform),
            "appVersion": self.app_version,
            "cameraSn": self.camera_sn,
            "rcSn": self.rc_sn,
            "batterySn": self.battery_sn,
            "productType": self.product_type.name if isinstance(self.product_type, ProductType) else str(self.product_type),
            "startCoordinate": {
                "latitude": self.latitude,
                "longitude": self.longitude,
            },
        }
        return result
