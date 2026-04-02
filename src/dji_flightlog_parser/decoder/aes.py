"""AES-256-CBC decoder for DJI flight log records (v13+)."""

from __future__ import annotations

import logging

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from .feature_point import FeaturePoint, feature_point_from_record_type
from .xor import XorDecoder
from ..keychain.models import Keychain

logger = logging.getLogger(__name__)

AES_BLOCK_SIZE = 16  # 128-bit blocks


def aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> tuple[bytes, bytes]:
    """Decrypt AES-256-CBC with PKCS7 padding.

    Returns (plaintext, next_iv) where next_iv is the last ciphertext block
    for CBC chaining.
    """
    if len(ciphertext) == 0:
        return b"", iv

    next_iv = ciphertext[-AES_BLOCK_SIZE:] if len(ciphertext) >= AES_BLOCK_SIZE else iv

    try:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        return plaintext, next_iv
    except Exception as e:
        logger.warning("AES decryption failed (key=%d bytes, iv=%d bytes, ct=%d bytes): %s",
                       len(key), len(iv), len(ciphertext), e)
        return b"", next_iv


class AesDecoder:
    """Decodes AES-encrypted record payloads.

    After XOR decoding, the inner payload (size-2 bytes, excluding first/last
    framing bytes) is AES-256-CBC encrypted with per-feature-point keys.
    """

    def __init__(self, xor_data: bytes, iv: bytes, key: bytes, content_size: int):
        """
        Args:
            xor_data: XOR-decoded data (full payload after XOR, including first byte).
            iv: Current AES IV for this feature point.
            key: AES key for this feature point.
            content_size: Number of bytes to treat as AES ciphertext (typically record_size - 2).
        """
        ciphertext = xor_data[:content_size]

        self.plaintext, self.next_iv = aes_decrypt(ciphertext, key, iv)
        self._pos = 0

    def read(self, n: int) -> bytes:
        chunk = self.plaintext[self._pos:self._pos + n]
        self._pos += n
        return chunk

    def read_all(self) -> bytes:
        return self.read(len(self.plaintext) - self._pos)


def decode_record_payload(
    raw_payload: bytes,
    record_type: int,
    version: int,
    keychain: Keychain,
    record_size: int,
) -> tuple[bytes, Keychain]:
    """Decode a record payload through the appropriate decoder pipeline.

    Returns (decoded_payload, updated_keychain).
    The keychain is mutated (IV updated) for AES-decoded records.
    """
    if version <= 6:
        return raw_payload, keychain

    # XOR decode
    xor = XorDecoder(raw_payload, record_type)
    xor_decoded = xor.read_all()

    if version <= 12:
        return xor_decoded, keychain

    # v13+: check if AES needed
    fp = feature_point_from_record_type(record_type, version)

    if fp == FeaturePoint.PlaintextFeature:
        return xor_decoded, keychain

    pair = keychain.get(fp)
    if pair is None:
        return xor_decoded, keychain

    iv, key = pair
    content_size = max(0, record_size - 2)

    if content_size == 0 or len(xor_decoded) == 0:
        return xor_decoded, keychain

    ciphertext = xor_decoded[:content_size]
    plaintext, next_iv = aes_decrypt(ciphertext, key, iv)

    # Update keychain with next IV (CBC chaining per feature point)
    keychain[fp] = (next_iv, key)

    return plaintext, keychain
