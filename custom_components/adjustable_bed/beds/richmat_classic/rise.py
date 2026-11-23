"""Luuna Rise 1.0.13 and Power Cool 1.0.8 direct bed utilities.

Catalogs and gesture handlers remain member-specific. These bounded
builders are shared by both apps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Final, Literal

from ...codec import richmat as codec

Operation = Literal[
    "query", "alarm", "cancel_alarm", "rgb", "lamp_timer", "massage_timer", "massage_popup",
]
ALARM_COMBINATIONS: Final = {
    0x58: (0x77, 0x7A, 0x7D), 0x46: (0x78, 0x7B, 0x7E),
    0x45: (0x79, 0x7C, 0x7F), 0x59: (0xAC, 0xAD, 0xAE),
    0x2E: (0x81, 0x82, 0x83), 0x2F: (0xA6, 0xA7, 0xA8),
    0x30: (0xA9, 0xAA, 0xAB),
}
MASSAGE_CODES: Final = (0x5D, 0x4C, 0x4E)


@dataclass(frozen=True, slots=True)
class Request:
    operation: Operation
    actions: tuple[str, ...] = ()
    when: time | None = None
    color: tuple[int, int, int] | None = None
    seconds: int | None = None
    timer_save: bool = False
    progress: int | None = None
    popup: str | None = None


def alarm_action(available: dict[str, int], choices: tuple[str, ...]) -> int:
    """First bed choice, last traversed massage; exactly two selects all.

    Traversal is layout order, not caller order. A buzzer ignores massage;
    unsupported preset/massage combinations deliberately produce no command.
    """
    if not choices or len(set(choices)) != len(choices) or any(c not in available for c in choices):
        raise ValueError("Choose alarm actions present in the selected layout")
    selected = [code for key, code in available.items() if key in choices]
    bed = next((v for v in selected if v not in MASSAGE_CODES), None)
    massage = [v for v in selected if v in MASSAGE_CODES]
    massage_code = 0x5D if len(massage) == 2 else massage[-1] if massage else None
    if bed == 0x80 or massage_code is None:
        assert bed is not None
        return bed
    if bed is None:
        return massage_code
    if bed not in ALARM_COMBINATIONS:
        raise ValueError("The app defines no alarm packet for this preset and massage combination")
    return ALARM_COMBINATIONS[bed][MASSAGE_CODES.index(massage_code)]


def lamp_timer(seconds: int, *, save: bool) -> bytes:
    if type(seconds) is not int or not 0 <= seconds <= 300:
        raise ValueError("Lamp timer must be 0 to 300 seconds")
    value = seconds if seconds or save else 65535
    return codec.light_timer(value >> 8, value)
