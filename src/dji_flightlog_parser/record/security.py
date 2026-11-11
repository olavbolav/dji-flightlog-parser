"""Security record (type 55, feature point Security in v13+).

An opaque 256-byte block written once per 10 OSD records in every v14 log,
on all products. It cannot be decoded:

* No log carries a KeyStorage entry for feature point 15, so DJI's keychain
  API returns no key.
* The block is not AES output in any case. Read as a big-endian 2048-bit
  integer it is uniform below a fixed bound M ~ 0.779 * 2**2048 (top byte
  never above 0xC7), which no symmetric cipher can produce. It is consistent
  with an RSA-2048 ciphertext or signature, but that is unproven.

The XOR layer is the only encoding: the plaintext is 257 bytes, the 256-byte
block followed by the XOR check byte, which equals (seed + 55) & 0xFF.
Verified on 73,011 records from 70 v14 logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BLOCK_LENGTH = 256
RECORD_LENGTH = BLOCK_LENGTH + 1
_TOP16_BOUND = 0xC773  # conservative upper bound for the block's top 16 bits


@dataclass
class SecurityBlock:
    block: bytes = b""
    check_ok: Optional[bool] = None  # XOR check byte; None when the seed is unknown
    in_range: bool = True  # block below the observed modulus bound

    @staticmethod
    def accepts(data: bytes, version: int) -> bool:
        """v13+ records of the expected size. v12 hits are misframing artefacts."""
        return version >= 13 and len(data) == RECORD_LENGTH

    @classmethod
    def from_bytes(cls, data: bytes, version: int = 14, seed: Optional[int] = None) -> SecurityBlock:
        s = cls()
        if len(data) < RECORD_LENGTH:
            s.block = bytes(data)
            s.in_range = False
            return s

        s.block = bytes(data[:BLOCK_LENGTH])
        s.in_range = ((s.block[0] << 8) | s.block[1]) <= _TOP16_BOUND
        if seed is not None:
            s.check_ok = data[BLOCK_LENGTH] == (seed + 55) & 0xFF
        return s

    @property
    def block_hex(self) -> str:
        return self.block.hex()
