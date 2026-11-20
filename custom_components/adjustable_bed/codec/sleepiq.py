"""SleepIQ's independent Fuzion blob and addressed MCR wire formats.

Fuzion is UTF-8 behind ``fUzIoN``, LE32 total length and IEEE CRC32.
MCR is ``16 16``, a ten-byte addressed header, up to fifteen payload bytes
and a big-endian weighted sum. The MCR reader deliberately compares the
unmasked sum, although the writer truncates it to sixteen bits.
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from typing import Final

FUZION_MAGIC: Final = b"fUzIoN"
FUZION_HEADER: Final = 10
FUZION_MIN: Final = 14
MCR_SYNC: Final = b"\x16\x16"


def fuzion(payload: str) -> bytes:
    encoded = payload.encode("utf-8")
    prefix = FUZION_MAGIC + struct.pack("<I", len(encoded) + FUZION_MIN) + encoded
    return prefix + struct.pack("<I", zlib.crc32(prefix))


def parse_fuzion(frame: bytes) -> str:
    if len(frame) < FUZION_MIN or not frame.startswith(FUZION_MAGIC):
        raise ValueError("Sleep Number response blob is missing the Fuzion preamble")
    if struct.unpack_from("<I", frame, 6)[0] != len(frame):
        raise ValueError("Sleep Number response blob length mismatch")
    if zlib.crc32(frame[:-4]) != struct.unpack_from("<I", frame, len(frame) - 4)[0]:
        raise ValueError("Sleep Number response blob failed CRC validation")
    return frame[FUZION_HEADER:-4].decode("utf-8", errors="replace")


def bamkey_values(text: str, count: int) -> list[str]:
    """Preserve the app's two replace-first operations, including within JSON."""
    if not text.startswith(("PASS:", "[")):
        raise ValueError("Unknown or failed Sleep Number response")
    value = text.replace("PASS:ACK", "", 1).replace("PASS:", "", 1)
    if count == 1:
        return [value]
    values = [item for item in value.split(" ") if item.strip()]
    if count > 16 or len(values) != count:
        raise ValueError(f"Sleep Number returned {len(values)} values, expected {count}")
    return values


def grouped_values(text: str) -> list[str | None]:
    values = json.loads(bamkey_values(text, 1)[0])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError("Sleep Number grouped response must contain strings")
    return [None if value.startswith("FAIL") else value.replace("PASS:", "") for value in values]


@dataclass(frozen=True, slots=True)
class McrFrame:
    command_type: int
    target: int
    sub_address: int
    status: int
    echo: int
    function_code: int
    side: int
    payload: bytes
    is_response: bool


def weighted_sum(data: bytes) -> int:
    running = total = 0
    for value in data:
        running += value
        total += running
    return total


def mcr(
    *,
    command_type: int,
    status: int,
    function_code: int,
    side: int,
    payload: bytes,
    sub_address: int,
    client_address: int = 0,
) -> bytes:
    if len(payload) > 15:
        raise ValueError("MCR payload exceeds 15 bytes")
    body = (
        bytes((command_type,))
        + client_address.to_bytes(2, "big")
        + sub_address.to_bytes(2, "big")
        + bytes((status,))
        + client_address.to_bytes(2, "big")
        + bytes((function_code, ((side & 15) << 4) | len(payload)))
        + payload
    )
    return MCR_SYNC + body + (weighted_sum(body) & 0xFFFF).to_bytes(2, "big")


def parse_mcr(data: bytes) -> McrFrame | None:
    if len(data) < 14 or not data.startswith(MCR_SYNC):
        return None
    body = data[2:-2]
    if weighted_sum(body) != int.from_bytes(data[-2:], "big"):
        return None
    length = body[9] & 15
    if len(body) != 10 + length:
        return None
    return McrFrame(
        body[0],
        int.from_bytes(body[1:3], "big"),
        int.from_bytes(body[3:5], "big"),
        body[5],
        int.from_bytes(body[6:8], "big"),
        body[8] & 127,
        body[9] >> 4,
        body[10:],
        bool(body[8] & 128),
    )


class McrMerger:
    """Nordic's byte merger: skip a third sync byte, emit one frame per callback.

    Once a complete frame is emitted, remaining bytes in that callback are
    dropped. This is observable app behavior, not a generic stream parser.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> bytes | None:
        stored_length = len(self.buffer)
        for index, value in enumerate(data):
            if stored_length + index == 2 and value == 0x16:
                continue
            self.buffer.append(value)
            if len(self.buffer) >= 12 and len(self.buffer) == 14 + (self.buffer[11] & 15):
                frame = bytes(self.buffer)
                self.buffer.clear()
                return frame
        return None
