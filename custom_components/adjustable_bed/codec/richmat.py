"""Richmat 6E wire codec.

Every frame ends in ``sum8``, the low byte of the sum of the bytes before it.
A command is ``6E 01 side code sum8``; ``code 6E`` is the release (STOP). Other
second bytes select a function: queries, light timer and colour, countdown
alarm. Extended frames carry their own length: ``6E len 20 domain command
operation data sum8``; notifications, Good Vibe Sleep's settings and the Casper
Base and Hush Base apps' records put the length after ``20`` instead. ``6E 40``
notifications carry a two-byte length and end in a CRC-16/XMODEM. Nordic UART
transports take the bare command byte.

Legacy Richmat routes also frame the command behind a ``55`` or ``AA`` header,
and the RGB-strip remotes use ``04 len cmd 01 00 payload 00 00 sum8``. Which
transport, framing, codes and timing a bed uses belongs to its profile
(``profiles/richmat.py``), never to this module.
"""

from __future__ import annotations

import binascii
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from ..const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    RICHMAT_WILINKE_CHAR_UUIDS,
    RICHMAT_WILINKE_SERVICE_UUIDS,
)

TransportKey = Literal["n1", "w0", "w1", "w2", "w3", "w4", "w5"]
Framing = Literal["wilinke", "nordic", "prefix55", "prefixaa"]


@dataclass(frozen=True)
class Transport:
    """GATT roles of one transport. ``single`` transports take bare command bytes."""

    service_uuid: str
    write_uuid: str
    notify_uuid: str
    single: bool = False


TRANSPORTS: Final[dict[TransportKey, Transport]] = {
    "n1": Transport(
        NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID, NORDIC_UART_READ_CHAR_UUID, True
    ),
    **{
        key: Transport(service, *RICHMAT_WILINKE_CHAR_UUIDS[index])
        for index, (key, service) in enumerate(
            zip(("w0", "w1", "w2", "w3", "w4", "w5"), RICHMAT_WILINKE_SERVICE_UUIDS, strict=True)
        )
    },
}

BED: Final = 0x6E
MATTRESS: Final = 0x5E
STOP: Final = 0x6E
COMPAT_STOP: Final = 0x5E
"""``^``: the stop some WiLinke remotes need instead of ``6E``."""
_HEADERS: Final[dict[Framing, int]] = {"wilinke": BED, "prefix55": 0x55, "prefixaa": 0xAA}


def frame(*values: int) -> bytes:
    """Append ``sum8``, then keep the low byte of every value, as the apps do."""
    return bytes(value & 0xFF for value in (*values, sum(values)))


def is_valid(data: bytes) -> bool:
    """Whether the last byte is the ``sum8`` of the others."""
    return len(data) >= 2 and sum(data[:-1]) & 0xFF == data[-1]


def is_valid_crc(data: bytes) -> bool:
    """Whether a ``6E 40`` frame ends in the big-endian CRC-16/XMODEM of the others."""
    return len(data) > 2 and binascii.crc_hqx(data[:-2], 0) == int.from_bytes(data[-2:], "big")


def command(code: int, side: int = 0, *, header: int = BED) -> bytes:
    """``6E 01 side code sum8``: every motor, preset, light and massage button."""
    return frame(header, 0x01, side, code)


def encode(framing: Framing, code: int) -> bytes:
    """A command in one route's framing; Nordic routes send the bare code."""
    if framing == "nordic":
        return bytes((code & 0xFF,))
    return command(code, header=_HEADERS[framing])


# Function selectors: (header, function, argument) replacing ``6E 01 side``.
FUNCTION_PREFIXES: Final[dict[str, tuple[int, int, int]]] = {
    "deviceFunctionItemExitLimit": (BED, 0x02, 0x01),
    "deviceFunctionItemCheckClock": (BED, 0x08, 0x01),
    "deviceFunctionItemCheckLight": (BED, 0x0A, 0x00),
    "deviceFunctionItemCheckMusic": (BED, 0x15, 0x01),
    "deviceFunctionItemCheckAroma": (BED, 0x1A, 0x00),
    "deviceFunctionItemCheckMattress": (MATTRESS, 0x1A, 0x00),
    "deviceFunctionItemCheckSnore": (BED, 0x21, 0x00),
    "deviceFunctionItemCheckSpeech": (BED, 0x22, 0x00),
    "deviceFunctionItemCheckDetection": (BED, 0x9A, 0xC0),
    "deviceFunctionItemSendStartDetection": (BED, 0x88, 0xC2),
    "deviceFunctionItemQueryVersion": (BED, 0x9A, 0x00),
    "deviceFunctionVersionOneBedCurrentMode": (BED, 0x9A, 0x10),
    "deviceFunctionVersionOneMotor1CurrentAngle": (BED, 0x9A, 0x30),
    "deviceFunctionVersionOneMotor2CurrentAngle": (BED, 0x9A, 0x30),
    "deviceFunctionVersionOneMotor3CurrentAngle": (BED, 0x9A, 0x30),
    "deviceFunctionVersionOneMotor4CurrentAngle": (BED, 0x9A, 0x30),
    "deviceFunctionVersionOneCurrentMassageMode": (BED, 0x9A, 0xA0),
    "deviceFunctionVersionOneCurrentBedLightStatus": (BED, 0x9A, 0xB0),
}


def function(code: int, side: int = 0, *, action: str = "", single: bool = False) -> bytes:
    """A catalog action: its function selector, or a side-scoped command."""
    if single:
        return bytes((code & 0xFF,))
    return frame(*FUNCTION_PREFIXES.get(action, (BED, 0x01, side)), code)


def extended(*body: int) -> bytes:
    """``6E len body sum8``, where ``len`` counts the whole frame."""
    return frame(BED, len(body) + 3, *body)


def record(domain: int, command_id: int, operation: int, data: Iterable[int]) -> bytes:
    """Extended domain record: ``6E len 20 domain command operation data sum8``."""
    return extended(0x20, domain, command_id, operation, *data)


def record_20_len(domain: int, command_id: int, operation: int, data: Iterable[int]) -> bytes:
    """``6E 20 len domain command operation data sum8``; ``len`` counts the whole frame."""
    body = (domain, command_id, operation, *data)
    return frame(BED, 0x20, len(body) + 4, *body)


Record = Callable[[int, int, int, Iterable[int]], bytes]


def time_sync(
    now: datetime, zone: datetime | None = None, *, build: Record = record
) -> tuple[bytes, bytes]:
    """Unix seconds and whole-hour zone, then the local calendar, as ``build`` records.

    The zone comes from ``zone`` when the app samples the clock twice.
    """
    offset = (zone or now).utcoffset()
    if now.utcoffset() is None or offset is None:
        raise ValueError("Time synchronization requires aware datetimes")
    return (
        build(
            8, 2, 1, (*int(now.timestamp()).to_bytes(4, "big"), int(offset.total_seconds() / 3600))
        ),
        calendar(now, build=build),
    )


def calendar(now: datetime, *, build: Record = record) -> bytes:
    """The local calendar record: ``08 03 01 year-1970 month day hour minute second``."""
    return build(8, 3, 1, (now.year - 1970, now.month, now.day, now.hour, now.minute, now.second))


def light_timer(high: int, low: int) -> bytes:
    """``6E 0B high low sum8``. Each app chooses its own always-on value."""
    return frame(BED, 0x0B, high, low)


def rgb(red: int, green: int, blue: int) -> bytes:
    """Two frames in one write: ``6E 0C FF R sum8 6E 0D G B sum8``."""
    return frame(BED, 0x0C, 0xFF, red) + frame(BED, 0x0D, green, blue)


def countdown(minutes: int, action: int, slot: int = 0) -> tuple[bytes, bytes]:
    """Countdown alarm: ``6E 05 low slot`` then ``6E 06 high action``; zero cancels."""
    return frame(BED, 0x05, minutes, slot), frame(BED, 0x06, minutes >> 8, action)


def strip(command_id: int, payload: bytes) -> bytes:
    """RGB-strip frame: ``04 len command 01 00 payload 00 00 sum8``."""
    body = (0x04, len(payload) + 8, command_id, 0x01, 0x00, *payload, 0x00, 0x00)
    return frame(*body)


def packed_motor(number: int, angle: int) -> bytes:
    """Richmat 4.2.0's minimum-width strings, sliced to the first sixteen bits."""
    bits = "0011" + format(number, "02b") + "0" + format(angle, "09b")
    return frame(BED, 0x88, int(bits[:8], 2), int(bits[8:16], 2))


def packed_massage(first: int, second: int) -> bytes:
    """Two current intensities, not a zone and gear; there is no third field."""
    bits = "1010000000" + format(second, "03b") + format(first, "03b")
    return frame(BED, 0x88, int(bits[:8], 2), int(bits[8:16], 2))
