"""Keychain data models for DJI API communication."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

from ..decoder.feature_point import FeaturePoint

logger = logging.getLogger(__name__)


Keychain = dict[FeaturePoint, tuple[bytes, bytes]]  # {feature_point: (iv, key)}


@dataclass
class EncodedKeychainFeaturePoint:
    feature_point: FeaturePoint
    aes_ciphertext: bytes  # raw bytes from KeyStorage record

    def to_api_dict(self) -> dict:
        return {
            "featurePoint": self.feature_point.api_name(),
            "aesCiphertext": base64.b64encode(self.aes_ciphertext).decode("ascii"),
        }


@dataclass
class KeychainsRequest:
    version: int
    department: int
    keychains_array: list[list[EncodedKeychainFeaturePoint]] = field(default_factory=list)

    def to_api_dict(self) -> dict:
        return {
            "version": self.version,
            "department": self.department,
            "keychainsArray": [
                [fp.to_api_dict() for fp in group]
                for group in self.keychains_array
            ],
        }


@dataclass
class KeychainFeaturePoint:
    feature_point: FeaturePoint
    aes_key: bytes
    aes_iv: bytes


def keychains_from_response(
    data: list[list[dict]],
) -> list[list[KeychainFeaturePoint]]:
    """Parse the DJI API response data into keychain feature points."""
    result = []
    for group in data:
        group_fps = []
        for item in group:
            try:
                fp_name = item.get("featurePoint")
                aes_key_b64 = item.get("aesKey")
                aes_iv_b64 = item.get("aesIv")
                if not all((fp_name, aes_key_b64, aes_iv_b64)):
                    logger.warning("Skipping keychain item with missing fields: %s", list(item.keys()))
                    continue
                fp = FeaturePoint.from_api_name(fp_name)
                aes_key = base64.b64decode(aes_key_b64)
                aes_iv = base64.b64decode(aes_iv_b64)
                group_fps.append(KeychainFeaturePoint(
                    feature_point=fp,
                    aes_key=aes_key,
                    aes_iv=aes_iv,
                ))
            except Exception as e:
                logger.warning("Skipping invalid keychain item: %s", e)
                continue
        result.append(group_fps)
    return result


def build_keychain(groups: list[list[KeychainFeaturePoint]]) -> list[Keychain]:
    """Convert API response groups into list of Keychain dicts (one per segment)."""
    keychains = []
    for group in groups:
        kc: Keychain = {}
        for fp_item in group:
            kc[fp_item.feature_point] = (fp_item.aes_iv, fp_item.aes_key)
        keychains.append(kc)
    return keychains
