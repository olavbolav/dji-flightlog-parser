"""JSON export compatible with the Rust dji-log-parser output format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..frame.models import Frame
from ..layout.details import Details
from ..record.reader import Record
from ..record.types import RecordType
from ..record.unknown import UnknownRecord


def export_json(
    version: int,
    details: Details,
    frames: list[Frame],
    output_path: Optional[str | Path] = None,
) -> str:
    """Export frames as JSON matching the Rust parser format.

    Returns JSON string. Optionally writes to file.
    """
    frame_details = _make_frame_details(details)

    data = {
        "version": version,
        "details": frame_details,
        "frames": [f.to_dict() for f in frames],
    }

    result = json.dumps(data, ensure_ascii=False, default=str)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


def export_json_raw(
    version: int,
    details: Details,
    records: list[Record],
    output_path: Optional[str | Path] = None,
) -> str:
    """Export raw records as JSON (--raw mode).

    Filters out KeyStorage, Unknown, Invalid, and JPEG records.
    """
    filtered = []
    skip_types = {RecordType.KeyStorage, RecordType.KeyStorageRecover}

    for r in records:
        if r.record_type in skip_types:
            continue
        if isinstance(r.data, UnknownRecord):
            continue

        record_dict = {
            "type": r.type_name(),
            "content": _serialize_record_data(r.data),
        }
        filtered.append(record_dict)

    data = {
        "version": version,
        "details": details.to_dict(),
        "records": filtered,
    }

    result = json.dumps(data, ensure_ascii=False, default=str)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


def _make_frame_details(details: Details) -> dict:
    """Create FrameDetails compatible with Rust parser output."""
    return {
        "totalTime": float(details.total_time),
        "totalDistance": details.total_distance,
        "maxHeight": details.max_height,
        "maxHorizontalSpeed": details.max_horizontal_speed,
        "maxVerticalSpeed": details.max_vertical_speed,
        "photoNum": details.capture_num,
        "videoTime": details.video_time,
        "aircraftName": details.aircraft_name,
        "aircraftSn": details.aircraft_sn,
        "cameraSn": details.camera_sn,
        "rcSn": details.rc_sn,
        "appPlatform": details.app_platform.name if hasattr(details.app_platform, 'name') else str(details.app_platform),
        "appVersion": details.app_version,
    }


def _serialize_record_data(data: object) -> dict:
    """Serialize a record data object to a dict."""
    if hasattr(data, "__dataclass_fields__"):
        result = {}
        for field_name in data.__dataclass_fields__:
            val = getattr(data, field_name)
            if isinstance(val, bytes):
                continue
            if hasattr(val, 'name'):
                val = val.name
            if hasattr(val, 'isoformat'):
                val = val.isoformat().replace("+00:00", "Z")
            result[field_name] = val
        return result
    return {"raw": str(data)}
