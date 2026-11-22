"""SILVERmotion native custom-LDP envelope, XXTEA, CRC and SLIP."""

from __future__ import annotations

import binascii
import struct
from typing import Final

SERVICE: Final = "b9934c43-5c91-462b-80a1-30fccc29d758"
CHARACTERISTIC: Final = "b9934c44-5c91-462b-80a1-30fccc29d758"
MANUFACTURER: Final = 1351
CHUNK_SIZE: Final = 20
# Fixed protocol material, independent of users, accounts and BLE bonds.
_KEY: Final = struct.unpack("<4I", bytes.fromhex("6c4f42f5676802e253ac9a2702a637ab"))
_MASK: Final = 0xFFFFFFFF
_DELTA: Final = 0x9E3779B9


def _mix(z: int, y: int, total: int, p: int, e: int) -> int:
    return (
        ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^ ((total ^ y) + (_KEY[(p & 3) ^ e] ^ z))
    ) & _MASK


def _crypt(data: bytes, *, decrypt: bool = False) -> bytes:
    if len(data) < 8 or len(data) % 4:
        raise ValueError("XXTEA requires at least two whole LE32 words")
    words = list(struct.unpack(f"<{len(data) // 4}I", data))
    n = len(words)
    rounds = 6 + 52 // n
    if decrypt:
        total = rounds * _DELTA & _MASK
        y = words[0]
        for _ in range(rounds):
            e = total >> 2 & 3
            for p in range(n - 1, 0, -1):
                words[p] = (words[p] - _mix(words[p - 1], y, total, p, e)) & _MASK
                y = words[p]
            words[0] = (words[0] - _mix(words[-1], y, total, 0, e)) & _MASK
            y = words[0]
            total = (total - _DELTA) & _MASK
    else:
        total = 0
        z = words[-1]
        for _ in range(rounds):
            total = (total + _DELTA) & _MASK
            e = total >> 2 & 3
            for p in range(n - 1):
                words[p] = (words[p] + _mix(z, words[p + 1], total, p, e)) & _MASK
                z = words[p]
            words[-1] = (words[-1] + _mix(z, words[0], total, n - 1, e)) & _MASK
            z = words[-1]
    return struct.pack(f"<{n}I", *words)


def slip(data: bytes) -> bytes:
    return b"\xc0" + data.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc") + b"\xc0"


def encode_plain(plain: bytes) -> bytes:
    """Frame one native message; length headers are outside the CRC coverage."""
    if not 8 <= len(plain) <= 256:
        raise ValueError("Native message length must be 8..256")
    encrypted = _crypt(plain + bytes(-len(plain) % 4))
    header = bytes((len(encrypted) - 4, len(plain) - 4))
    return slip(header + struct.pack("<H", binascii.crc_hqx(encrypted, 0xFFFF)) + encrypted)


def custom_plain(payload: bytes, repeat: int = 3, delay: int = 30) -> bytes:
    if not 1 <= len(payload) <= 245 or not 0 <= repeat <= 255 or not 0 <= delay <= 255:
        raise ValueError("Custom LDP requires a bounded payload and uint8 repeat/delay")
    return (
        b"\x03\x00\x00\x00\x01\x00\x00"
        + bytes((len(payload),))
        + payload
        + bytes((repeat, delay, 0))
    )


def encode(payload: bytes, repeat: int = 3, delay: int = 30) -> bytes:
    return encode_plain(custom_plain(payload, repeat, delay))


def chunks(frame: bytes) -> tuple[bytes, ...]:
    return tuple(frame[i : i + CHUNK_SIZE] for i in range(0, len(frame), CHUNK_SIZE))


def decode_body(body: bytes) -> bytes | None:
    """Safely reject invalid unauthenticated lengths instead of native overreads."""
    if len(body) < 12:
        return None
    size, plain_size = body[0] + 4, body[1] + 4
    encrypted = body[4:]
    if size != len(encrypted) or size < 8 or size % 4 or not 4 <= plain_size <= size:
        return None
    if binascii.crc_hqx(encrypted, 0xFFFF) != int.from_bytes(body[2:4], "little"):
        return None
    return _crypt(encrypted, decrypt=True)[:plain_size]


class Receiver:
    """Bounded native SLIP stream, including escape state across notifications."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._started = False
        self._escaped = False

    def feed(self, data: bytes) -> tuple[bytes, ...]:
        messages: list[bytes] = []
        for byte in data:
            if self._escaped:
                self._buffer.append({0xDC: 0xC0, 0xDD: 0xDB}.get(byte, byte))
                self._escaped = False
            elif byte == 0xC0:
                if self._buffer:
                    if (plain := decode_body(bytes(self._buffer))) is not None:
                        messages.append(plain)
                    self._buffer.clear()
                    self._started = False
                else:
                    self._started = True
            elif self._started:
                if byte == 0xDB:
                    self._escaped = True
                else:
                    self._buffer.append(byte)
            if len(self._buffer) > 264:
                self._buffer.clear()
                self._started = self._escaped = False
        return tuple(messages)
