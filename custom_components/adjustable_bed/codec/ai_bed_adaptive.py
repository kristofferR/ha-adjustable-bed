"""AI Bed adaptive AES/CRC builders, without a proved complete runtime route."""

from __future__ import annotations

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _tables() -> tuple[tuple[int, ...], tuple[int, ...]]:
    high, low = [], []
    for i in range(256):
        value = i
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
        high.append(value >> 8)
        low.append(0x7F if i == 6 else value & 255)
    return tuple(high), tuple(low)


HIGH, LOW = _tables()


def crc(data: bytes) -> int:
    high = low = 255
    for byte in data:
        index = (byte ^ low) & 255
        low, high = high ^ LOW[index], HIGH[index]
    return high << 8 | low


def crc_bytes(value: int) -> bytes:
    """Keep the shipped single-zero padding and odd-length failure."""
    text = format(value, "X")
    if len(text) < 4:
        text = "0" + text
    return bytes.fromhex(text)[::-1]


def frame(plain: bytes, prefix: bytes) -> bytes:
    pad = padding.PKCS7(128).padder()
    padded = pad.update(plain) + pad.finalize()
    encrypt = Cipher(algorithms.AES(b"mmzn_blue_202309"), modes.ECB()).encryptor()
    body = prefix + encrypt.update(padded) + encrypt.finalize()
    return body + crc_bytes(crc(body))


def manual(values: tuple[int, ...], use_1b: bool) -> bytes:
    if len(values) != 12:
        raise ValueError("Manual builder requires twelve values")
    plain = bytes.fromhex("1b1a62" if use_1b else "31308b")
    for value in values:
        plain += bytes((0, value)) if value > 0 else b"\xff\xff"
    return frame(plain, bytes.fromhex("aa1025"))
