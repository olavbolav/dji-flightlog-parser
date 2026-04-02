"""Unknown record type fallback."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnknownRecord:
    record_type: int = 0
    data: bytes = b""
