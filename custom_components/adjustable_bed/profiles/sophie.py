"""Sophie 1.0.6 (com.sddq.sophienew, code 8), accepted unit124 evidence.

Manually transcribed from the immutable APK Protocol Audit. No catalog generator.
The frozen commands and builder inputs live in tests/fixtures/sophie.
"""

from __future__ import annotations

from typing import Final

from ..codec import ff_frame as codec

NAME_TOKENS: Final = ("MQ", "1520", "1320")
NAMED_QUERY_TOKENS: Final = ("QMS-MQ", "QMS2", "S3-2", "QMS3")
SIDE_ALARM_TOKENS: Final = ("QMS-DFQ", "QMS-430", "QMS-444")
PRESET_KEYS: Final = ("memory_1", "memory_2", "tv", "zero_g", "anti_snore")
PRESET_CODES: Final = (0x0A, 0x0B, 0x05, 0x09, 0x0F)
ALARM_MODES: Final = {
    "zero_g": 1,
    "memory_1": 2,
    "no_action": 3,
    "zero_g_left": 4,
    "zero_g_right": 5,
    "zero_g_both": 6,
}
PRESET_HOLD_MS: Final = 2000
QUERY_DELAY_MS: Final = 300
QUERY_SPACING_MS: Final = 500
CLOCK_DELAY_MS: Final = 500
SYNC_AFTER_CLOCK_MS: Final = 500
LIGHT_QUERY_DELAY_MS: Final = 1000
# This literal's trailer is deliberately not the codec CRC. It is a separate
# app-labelled header action, with no proven STOP meaning.
HEADER_ACTION: Final = codec.STOP[:-2] + b"\xd8\x14"
SYNC_OFF: Final = codec.summed(1, 9, b"\x00")
SYNC_ON: Final = codec.summed(1, 9, b"\x01")
SYNC_QUERY: Final = codec.summed(1, 10, b"\x0f")
MASSAGE_REPLIES: Final = {
    "head": tuple(codec.control(code, arg=1) for code in (0, 0x1E, 0x1F, 0x20)),
    "foot": tuple(codec.control(code, arg=2) for code in (0, 0x21, 0x22, 0x23)),
    "wave": tuple(codec.control(code, arg=3) for code in (0x24, 0x25, 0x26, 0x27)),
}


def accepts_name(name: str | None) -> bool:
    """The raw case-sensitive app scan predicate; never identifies the app."""
    return bool(name and any(token in name for token in NAME_TOKENS))


def normalize_name(name: str) -> str:
    return name.translate(
        str.maketrans({"<": "C", ":": "A", ";": "B", "=": "D", ">": "E", "?": "F"})
    )


def named_queries(name: str) -> bool:
    return any(token in normalize_name(name) for token in NAMED_QUERY_TOKENS)


def alarm_modes(name: str) -> tuple[str, ...]:
    upper = normalize_name(name).upper()
    return (
        ("no_action", "zero_g_left", "zero_g_right", "zero_g_both")
        if any(token in upper for token in SIDE_ALARM_TOKENS)
        else ("zero_g", "memory_1", "no_action")
    )


def alarm_massage_allowed(name: str) -> bool:
    return "QMS2" not in normalize_name(name).upper()
