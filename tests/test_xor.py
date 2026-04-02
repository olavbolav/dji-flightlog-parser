"""Unit tests for the CRC64-based XOR decoder."""

from dji_flightlog_parser.decoder.xor import crc64, xor_decode_block, XorDecoder


def test_crc64_test_vector():
    """CRC64 of '123456789' should match the known Redis/Jones value."""
    result = crc64(0, b"123456789")
    assert result == 0xE9C6D914C4B8D9CA, f"Expected 0xe9c6d914c4b8d9ca, got {hex(result)}"


def test_crc64_empty():
    result = crc64(0, b"")
    assert result == 0


def test_crc64_with_seed():
    result = crc64(0x42, b"\x01\x02\x03")
    assert isinstance(result, int)
    assert 0 <= result < (1 << 64)


def test_xor_decode_block_roundtrip():
    """XOR encoding is its own inverse when applied with the same key."""
    original = bytes(range(20))
    record_type = 1
    payload = bytes([0x42]) + original
    decoded = xor_decode_block(payload, record_type)
    re_encoded = bytes([0x42]) + decoded
    roundtrip = xor_decode_block(re_encoded, record_type)
    assert roundtrip == original


def test_xor_decoder_read():
    payload = bytes([0x10]) + bytes(range(16))
    decoder = XorDecoder(payload, record_type=5)
    result = decoder.read_all()
    assert len(result) == 16
    assert isinstance(result, bytes)
