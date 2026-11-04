"""Limoss DD wire codec.

Every frame is ten bytes: ``DD``, an eight-byte TEA block and a trailer, the low
byte of the sum of the first nine bytes. The block encrypts ``AA body counter
check``: a five-byte body (opcode and four parameters), the low byte of the
sender's counter, and the low byte of the sum of the seven plaintext bytes
before it. The key is static; there is no session key or nonce. Replies use the
same frame on the same FFE0/FFE1 characteristic.

Which bodies an app sends, who owns its counter, its write mode and its timing
belong to its profile (``profiles/limoss.py``), never to this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from ..const import LIMOSS_CHAR_UUID, LIMOSS_SERVICE_UUID

SERVICE_UUID: Final = LIMOSS_SERVICE_UUID
CHAR_UUID: Final = LIMOSS_CHAR_UUID

KEY: Final = (0x55551494, 0x74385555, 0x55551494, 0x74385555)
_DELTA: Final = 0x9E3779B9
_ROUNDS: Final = 16
_MASK: Final = 0xFFFFFFFF

# Requests whose replies carry the same opcode.
QUERY_HARDWARE: Final = 0x00
QUERY_SOFTWARE: Final = 0x01
QUERY_CAPABILITIES: Final = 0x02
# Ends a memory recall; the apps call it release or stop-both.
RECALL_RELEASE: Final = 0x03
ACKNOWLEDGE: Final = 0x04
CALIBRATE: Final = 0x05
SERIAL: Final = 0x06
FLAT: Final = 0x51
MASSAGE_ZONES: Final = (0x60, 0x61, 0x62, 0x63, 0x64, 0x65)
MASSAGE_OFF: Final = 0x66
LIGHT: Final = 0x70
LIGHT_OFF: Final = 0x71
STOP: Final = 0xFF
POSITION_OPCODES: Final = (0x10, 0x20, 0x30, 0x40)


def encrypt(block: bytes) -> bytes:
    """Encrypt one 8-byte block with 16-round TEA over big-endian words."""
    v0, v1 = _words(block)
    k0, k1, k2, k3 = KEY
    total = 0
    for _ in range(_ROUNDS):
        total = (total + _DELTA) & _MASK
        v0 = (v0 + (((v1 << 4) + k0) ^ (v1 + total) ^ ((v1 >> 5) + k1))) & _MASK
        v1 = (v1 + (((v0 << 4) + k2) ^ (v0 + total) ^ ((v0 >> 5) + k3))) & _MASK
    return v0.to_bytes(4, "big") + v1.to_bytes(4, "big")


def decrypt(block: bytes) -> bytes:
    v0, v1 = _words(block)
    k0, k1, k2, k3 = KEY
    total = (_DELTA * _ROUNDS) & _MASK
    for _ in range(_ROUNDS):
        v1 = (v1 - (((v0 << 4) + k2) ^ (v0 + total) ^ ((v0 >> 5) + k3))) & _MASK
        v0 = (v0 - (((v1 << 4) + k0) ^ (v1 + total) ^ ((v1 >> 5) + k1))) & _MASK
        total = (total - _DELTA) & _MASK
    return v0.to_bytes(4, "big") + v1.to_bytes(4, "big")


def _words(block: bytes) -> tuple[int, int]:
    if len(block) != 8:
        raise ValueError("TEA block must be exactly 8 bytes")
    return int.from_bytes(block[:4], "big"), int.from_bytes(block[4:], "big")


def frame(body: bytes, counter: int) -> bytes:
    """Encode one five-byte body with the low byte of ``counter``."""
    if len(body) != 5:
        raise ValueError("A Limoss body is five bytes")
    plain = b"\xaa" + body + bytes((counter & 0xFF,))
    packet = b"\xdd" + encrypt(plain + bytes((sum(plain) & 0xFF,)))
    return packet + bytes((sum(packet) & 0xFF,))


def decode(packet: bytes) -> bytes | None:
    """Return the body of a valid frame: header, both checksums and plaintext marker."""
    if len(packet) != 10 or packet[0] != 0xDD or sum(packet[:9]) & 0xFF != packet[9]:
        return None
    plain = decrypt(packet[1:9])
    if plain[0] != 0xAA or sum(plain[:7]) & 0xFF != plain[7]:
        return None
    return plain[1:6]


def body(opcode: int, parameters: bytes = bytes(4)) -> bytes:
    if len(parameters) != 4:
        raise ValueError("A Limoss body has four parameters")
    return bytes((opcode,)) + parameters


def query(opcode: int) -> bytes:
    """Hardware, software and capability requests end in ``03``."""
    return bytes((opcode, 0, 0, 0, 3))


def flagged(opcode: int, reversals: Sequence[bool]) -> bytes:
    """Held controls, STOP and calibration carry the four motor reversal flags."""
    if len(reversals) != 4:
        raise ValueError("Exactly four reversal flags are required")
    return bytes((opcode, *reversals))


def release(opcode: int, reversals: Sequence[bool]) -> bytes:
    """STOP carries the reversal flags; the recall release carries none."""
    return flagged(opcode, reversals) if opcode == STOP else body(opcode)


def motor(index: int, up: bool) -> int:
    """Held opcode of motor 1..4."""
    if not 1 <= index <= 4:
        raise ValueError("Motor must be 1..4")
    return index * 0x10 + (2 if up else 3)


def ask_position(index: int) -> bytes:
    """Request the raw position of motor 1..4; the reply carries the same opcode."""
    if not 1 <= index <= 4:
        raise ValueError("Motor must be 1..4")
    return body(index * 0x10)


def set_position(index: int, value: int, *, signed: bool = True) -> bytes:
    """Drive motor 1..4 toward a raw 32-bit big-endian position."""
    if not 1 <= index <= 4:
        raise ValueError("Motor must be 1..4")
    return body(index * 0x10 + 1, value.to_bytes(4, "big", signed=signed))


def version(parameters: bytes) -> str:
    """Join four signed bytes as the apps do: ``a`` and ``c``/``d`` only when non-negative."""
    if len(parameters) != 4:
        raise ValueError("Version reply needs four bytes")
    a, b, c, d = (value if value < 128 else value - 256 for value in parameters)
    return (
        (str(a) if a >= 0 else "")
        + str(b)
        + "."
        + (str(c) if c >= 0 else "")
        + (str(d) if d >= 0 else "")
    )


class StreamParser:
    """Reassemble reply bodies from notification chunks.

    ``verify`` checks each frame and resynchronizes one byte past an invalid
    one. Without it, every ten bytes from a ``DD`` header are decrypted as they
    are, as the Limoss Remote app does. Either way at most one partial frame is
    kept.
    """

    def __init__(self, *, verify: bool) -> None:
        self.verify = verify
        self.buffer = bytearray()

    def clear(self) -> None:
        self.buffer.clear()

    def feed(self, raw: bytes) -> list[bytes]:
        self.buffer.extend(raw)
        return self._verified() if self.verify else self._unverified()

    def _verified(self) -> list[bytes]:
        result: list[bytes] = []
        while self.buffer:
            if self.buffer[0] != 0xDD:
                del self.buffer[0]
                continue
            if len(self.buffer) < 10:
                break
            decoded = decode(bytes(self.buffer[:10]))
            if decoded is None:
                del self.buffer[0]
                continue
            del self.buffer[:10]
            result.append(decoded)
        return result

    def _unverified(self) -> list[bytes]:
        result: list[bytes] = []
        while len(self.buffer) >= 10:
            marker = self.buffer.find(0xDD)
            if marker < 0:
                self.buffer.clear()
                break
            del self.buffer[:marker]
            if len(self.buffer) < 10:
                break
            result.append(decrypt(bytes(self.buffer[1:9]))[1:6])
            del self.buffer[:10]
        return result
