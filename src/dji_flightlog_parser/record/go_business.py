"""GOBusinessData record parser (type 54, feature point DJIFlyCustom).

The DJI Fly app's on-screen notification state, stored as protobuf without a
published schema. It is written only by DJI Fly consumer aircraft (Mavic Mini,
Mini 5 Pro, Neo, Neo 2 in our data); enterprise logs have none. It carries no
telemetry or timestamps.

Each record updates at most one of three HUD parts, each with its own flag:

* status bar (field 2, flag 6): top label such as "In flight";
* tip (field 3, flag 5): a transient pop-up with an app code; flag without
  a tip means the tip slot is now empty;
* warnings (repeated field 4, flag 7): a full snapshot of the active warning
  list, each text ending in "(Code: X)"; flag without entries = empty list.

Parts whose flag is absent are unchanged. A separate once-per-log record
carries only fields 8 and 9. Strings follow the app's UI language, so key on
codes, not text. Verified on 431 records from 17 logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..decoder.protobuf import (
    FIXED64,
    LENGTH_DELIMITED,
    VARINT,
    ProtobufDecodeError,
    as_double,
    decode_text,
    iter_fields,
)

_CODE_RE = re.compile(r"\(Code:\s?([0-9A-Fa-f]{1,8})\)\s*$")


def warning_code(text: str) -> str:
    """Extract the '(Code: X)' suffix of a warning text, or ''."""
    m = _CODE_RE.search(text)
    return m.group(1).upper() if m else ""


@dataclass
class GOBusinessStatusBar:
    text: str = ""
    level: int = 0  # 1..3 observed, higher = more severe


@dataclass
class GOBusinessTip:
    level: int = 0  # 0..2 observed; newer apps omit 0
    code: str = ""  # app event code, decimal string
    text: str = ""
    duration_ms: float = 0.0  # nominal display time


@dataclass
class GOBusinessWarning:
    text: str = ""
    level: int = 0  # 2..3 observed, same scale as the status bar
    code: str = ""  # from the "(Code: X)" suffix; decimal or 8-hex HMS code


@dataclass
class GOBusinessData:
    ui_marker: int = 0  # field 1, always 1 on HUD updates
    status_bar_updated: bool = False
    status_bar: Optional[GOBusinessStatusBar] = None
    tip_updated: bool = False
    tip: Optional[GOBusinessTip] = None
    warnings_updated: bool = False
    warnings: list[GOBusinessWarning] = field(default_factory=list)
    flag_8: int = 0  # once-per-log session record; meaning unknown
    value_9: int = 0
    is_complete: bool = True  # False if the protobuf was truncated or malformed

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """True for an empty payload or a complete parse with real structure.

        Real records are a HUD update (field 1 = 1), the once-per-log session
        record (fields 8/9 only) or empty. AES ciphertext passed through
        without a key, or a truncated payload, fails this and stays an
        UnknownRecord.
        """
        if version < 7:
            return False
        body = data[:-1] if version <= 12 and data else data
        if not body:
            return True
        g = GOBusinessData.from_bytes(data, version)
        if not g.is_complete:
            return False
        if g.ui_marker:
            return g.ui_marker == 1
        has_parts = (g.status_bar is not None or g.tip is not None or bool(g.warnings)
                     or g.status_bar_updated or g.tip_updated or g.warnings_updated)
        return not has_parts and bool(g.flag_8 or g.value_9)

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14) -> GOBusinessData:
        g = cls()
        if version <= 12 and len(data) > 0:
            # v12 XOR output ends with one non-protobuf check byte; in v13+
            # that byte lies outside the AES content.
            data = data[:-1]
        if not data:
            return g

        try:
            for f in iter_fields(data):
                n, wt, v = f.number, f.wire_type, f.value
                if n == 1 and wt == VARINT:
                    g.ui_marker = v
                elif n == 2 and wt == LENGTH_DELIMITED:
                    g.status_bar = _parse_status_bar(v)
                elif n == 3 and wt == LENGTH_DELIMITED:
                    g.tip = _parse_tip(v)
                elif n == 4 and wt == LENGTH_DELIMITED:
                    g.warnings.append(_parse_warning(v))
                elif n == 5 and wt == VARINT:
                    g.tip_updated = bool(v)
                elif n == 6 and wt == VARINT:
                    g.status_bar_updated = bool(v)
                elif n == 7 and wt == VARINT:
                    g.warnings_updated = bool(v)
                elif n == 8 and wt == VARINT:
                    g.flag_8 = v
                elif n == 9 and wt == VARINT:
                    g.value_9 = v
                # Unknown fields are skipped (forward compatible).
        except ProtobufDecodeError:
            g.is_complete = False
        return g


def _parse_status_bar(data: bytes) -> GOBusinessStatusBar:
    sb = GOBusinessStatusBar()
    for f in iter_fields(data):
        if f.number == 1 and f.wire_type == LENGTH_DELIMITED:
            sb.text = decode_text(f.value)
        elif f.number == 3 and f.wire_type == VARINT:
            sb.level = f.value
    return sb


def _parse_tip(data: bytes) -> GOBusinessTip:
    tip = GOBusinessTip()
    for f in iter_fields(data):
        if f.number == 1 and f.wire_type == VARINT:
            tip.level = f.value
        elif f.number == 2 and f.wire_type == LENGTH_DELIMITED:
            tip.code = decode_text(f.value)
        elif f.number == 3 and f.wire_type == LENGTH_DELIMITED:
            tip.text = decode_text(f.value)
        elif f.number == 5 and f.wire_type == FIXED64:
            tip.duration_ms = as_double(f.value)
    return tip


def _parse_warning(data: bytes) -> GOBusinessWarning:
    w = GOBusinessWarning()
    for f in iter_fields(data):
        if f.number == 1 and f.wire_type == LENGTH_DELIMITED:
            w.text = decode_text(f.value)
        elif f.number == 2 and f.wire_type == VARINT:
            w.level = f.value
    w.code = warning_code(w.text)
    return w
