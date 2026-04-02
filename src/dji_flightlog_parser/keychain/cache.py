"""Optional keychain caching to avoid redundant DJI API calls."""

from __future__ import annotations

import hashlib
import json
import base64
import logging
from pathlib import Path
from typing import Optional

from ..decoder.feature_point import FeaturePoint
from .models import Keychain

logger = logging.getLogger(__name__)


class KeychainCache:
    """File-based cache for DJI keychains, keyed by file content hash."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path.home() / ".cache" / "dji-flightlog-parser"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, file_data: bytes) -> str:
        return hashlib.sha256(file_data[:1024]).hexdigest()[:32]

    def get(self, file_data: bytes) -> Optional[list[Keychain]]:
        key = self._cache_key(file_data)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            keychains = []
            for group in data:
                kc: Keychain = {}
                for fp_str, (iv_b64, key_b64) in group.items():
                    fp = FeaturePoint(int(fp_str))
                    kc[fp] = (base64.b64decode(iv_b64), base64.b64decode(key_b64))
                keychains.append(kc)
            logger.debug("Loaded cached keychains for %s", key)
            return keychains
        except Exception as e:
            logger.warning("Failed to load cached keychains: %s", e)
            return None

    def put(self, file_data: bytes, keychains: list[Keychain]) -> None:
        key = self._cache_key(file_data)
        path = self.cache_dir / f"{key}.json"

        data = []
        for kc in keychains:
            group = {}
            for fp, (iv, aes_key) in kc.items():
                group[str(int(fp))] = [
                    base64.b64encode(iv).decode("ascii"),
                    base64.b64encode(aes_key).decode("ascii"),
                ]
            data.append(group)

        path.write_text(json.dumps(data))
        logger.debug("Cached keychains for %s", key)
