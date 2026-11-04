"""Good Vibe Sleep dedicated builders, accepted package 2.0.1/code20103."""

from __future__ import annotations

import json
from datetime import datetime


def checksum(values: list[int]) -> bytes:
    return bytes(v & 255 for v in (*values, sum(values)))


def generic(code: int, side: int = 0, legacy: bool = False) -> bytes:
    return bytes((code & 255,)) if legacy else checksum([110, 1, side, code])


def clock(minutes: int, code: int) -> tuple[bytes, bytes]:
    return checksum([110, 5, minutes & 255, 0]), checksum([110, 6, int(minutes / 256), code])


def light_duration(seconds: int) -> bytes:
    high, low = (255, 255) if seconds == 0 else divmod(seconds, 256)
    return checksum([110, 11, high, low])


def color(red: int, green: int, blue: int) -> bytes:
    return checksum([110, 12, 255, red]) + checksum([110, 13, green, blue])


def snore_config(count: bool, value: int) -> bytes:
    return checksum([110, 32, 10, 6, 5, 1, 1 if count else 2, 0, value])


def snore_switch(enabled: bool) -> bytes:
    return checksum([110, 32, 9, 6, 1, 1, 0, int(enabled)])


def repeat_alarm(number: int, hour: int, minute: int, code: int, mask: int) -> bytes:
    return checksum([110, 32, 13, 5, 1, 1, number, 0, hour, minute, code, mask])


def delete_alarm(number: int) -> bytes:
    return checksum([110, 32, 8, 5, 2, 1, number])


def sync_time(now: datetime, offset_now: datetime | None = None) -> tuple[bytes, bytes]:
    offset = (offset_now or now).utcoffset()
    if offset is None:
        raise ValueError("An aware datetime is required")
    return (
        checksum(
            [
                110,
                32,
                12,
                8,
                2,
                1,
                *int(now.timestamp()).to_bytes(4, "big"),
                int(offset.total_seconds() / 3600),
            ]
        ),
        checksum(
            [
                110,
                32,
                13,
                8,
                3,
                1,
                now.year - 1970,
                now.month,
                now.day,
                now.hour,
                now.minute,
                now.second,
            ]
        ),
    )


QUERIES = {
    "alarms": bytes.fromhex("6e 20 08 05 01 00 00 9c"),
    "sleep_name": bytes.fromhex("6e 20 08 06 03 00 00 9f"),
    "snore_switch": bytes.fromhex("6e 20 08 06 01 00 00 9d"),
    "snore_config": bytes.fromhex("6e 20 09 06 05 00 00 00 a2"),
}


def sleep_packet(sequence: int, command: str, value: object) -> bytes:
    """The ordinary UTF-8 JSON envelope, without a checksum or CRC."""
    if not 1 <= sequence <= 254:
        raise ValueError("Sequence must be 1–254")
    body = json.dumps(
        {"id": sequence, "cmd": command, "val": value},
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    if len(body) > 65535:
        raise ValueError("Sleep payload exceeds the supported ordinary frame length")
    return (
        bytes(
            (
                0,
                sequence,
                1,
                0,
                (len(body) + 7) & 255,
                0,
                0,
                17,
                3,
                67,
                85,
                68,
                len(body) & 255,
                len(body) >> 8,
            )
        )
        + body
    )


def memory_eligible(model: str, action: str) -> bool:
    return (
        model in ("E3RM", "GXRM", "JDRM", "JFRM", "JGRM")
        and action
        in (
            "deviceFunctionItemMemoryPosition1",
            "deviceFunctionItemMemoryPosition2",
            "deviceFunctionItemMemoryPosition3",
            "deviceFunctionItemMemoryPosition4",
            "deviceFunctionItemAntiSnoring",
            "deviceFunctionItemZeroGravity",
            "deviceFunctionItemTVPosition",
        )
        and (model, action) != ("GXRM", "deviceFunctionItemTVPosition")
    )


EIGHT_COLORS = (
    (255, 255, 0),
    (0, 255, 0),
    (0, 127, 255),
    (0, 0, 255),
    (139, 0, 255),
    (255, 255, 255),
    (255, 0, 0),
    (255, 165, 0),
)


def light_durations(model: str, eight_color: bool) -> tuple[int, ...]:
    if eight_color:
        return (0, 1800, 3600, 14400, 28800) if model == "RNRN" else (0, 300, 600, 900)
    return tuple(range(0, 901, 60))


SNORE_MENU_EXCLUDED_MODELS = frozenset(("HNRN", "HQRN", "HSRN", "HURN", "M7RN", "MJRN"))
