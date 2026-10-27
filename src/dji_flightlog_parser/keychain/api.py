"""DJI OpenAPI keychains client for fetching AES decryption keys."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .models import (
    KeychainsRequest,
    KeychainFeaturePoint,
    keychains_from_response,
    build_keychain,
    Keychain,
)

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://dev.dji.com/openapi/v1/flight-records/keychains"
TIMEOUT = 30.0


class KeychainAPIError(RuntimeError):
    """Error result returned by the DJI keychains API."""

    def __init__(self, msg: str, code: Optional[int] = None):
        super().__init__(f"DJI API error: {msg} (code={code})")
        self.msg = msg
        self.code = code

    @property
    def is_invalid_ciphertext(self) -> bool:
        """True when DJI could not decrypt the KeyStorage ciphertext for this department."""
        return "invalid ciphertext" in self.msg.lower()


def fetch_keychains(
    request: KeychainsRequest,
    api_key: str,
    api_url: Optional[str] = None,
) -> list[Keychain]:
    """Fetch AES keychains from DJI OpenAPI (synchronous)."""
    url = api_url or DEFAULT_API_URL
    payload = request.to_api_dict()

    headers = {
        "Content-Type": "application/json",
        "Api-Key": api_key,
    }

    logger.debug("Fetching keychains from %s", url)

    response = httpx.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()

    body = response.json()

    result = body.get("result", {})
    if result.get("code") != 0:
        raise KeychainAPIError(result.get("msg", "Unknown error"), result.get("code"))

    data = body.get("data", [])
    groups = keychains_from_response(data)
    return build_keychain(groups)


async def fetch_keychains_async(
    request: KeychainsRequest,
    api_key: str,
    api_url: Optional[str] = None,
) -> list[Keychain]:
    """Fetch AES keychains from DJI OpenAPI (async)."""
    url = api_url or DEFAULT_API_URL
    payload = request.to_api_dict()

    headers = {
        "Content-Type": "application/json",
        "Api-Key": api_key,
    }

    logger.debug("Fetching keychains (async) from %s", url)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

    body = response.json()

    result = body.get("result", {})
    if result.get("code") != 0:
        raise KeychainAPIError(result.get("msg", "Unknown error"), result.get("code"))

    data = body.get("data", [])
    groups = keychains_from_response(data)
    return build_keychain(groups)
