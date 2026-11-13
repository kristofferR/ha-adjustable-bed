"""Cluster-017's direct builders over the literal-verified Richmat codec."""

from dataclasses import dataclass
from datetime import time
from typing import Final, Literal

from ...codec import richmat as codec

# Generic BED callbacks use these resources, independently of XML buttons.
# The speech phrase "stop" schedules 47. Only 6E is the protocol release.
BED_COMMANDS: Final = {
    "head_up": (0x24, True),
    "head_down": (0x25, True),
    "foot_up": (0x26, True),
    "foot_down": (0x27, True),
    "tv": (0x58, False),
    "lounge": (0x59, False),
    "zero_gravity": (0x45, False),
    "anti_snore": (0x46, False),
    "memory_one": (0x2E, False),
    "memory_two": (0x2F, False),
    "memory_three": (0x30, False),
    "flat": (0x31, False),
    "voice_stop_request": (0x47, False),
}
MASSAGE: Final = (0x5D, 0x4C, 0x4E)
ALARM_NAMES: Final = {
    0x45: "zero_gravity",
    0x46: "anti_snore",
    0x2E: "memory_one",
    0x2F: "memory_two",
    0x58: "tv",
    0x59: "lounge",
    0x5D: "massage_all",
    0x4C: "massage_head",
    0x4E: "massage_foot",
}
COMBINATIONS: Final = {
    0x58: (0x77, 0x7A, 0x7D),
    0x46: (0x78, 0x7B, 0x7E),
    0x45: (0x79, 0x7C, 0x7F),
    0x2E: (0x81, 0x82, 0x83),
}
Operation = Literal[
    "query", "alarm", "cancel_alarm", "rgb", "lamp_timeout", "massage_timer", "bed_command"
]


@dataclass(frozen=True, slots=True)
class Request:
    operation: Operation
    actions: tuple[str, ...] = ()
    when: time | None = None
    color: tuple[int, int, int] | None = None
    seconds: int | None = None
    progress: int | None = None
    command: str | None = None
    duration_ms: int = 1000


def lamp_timeout(seconds: int) -> bytes:
    """The actual int32 byte-pair fold, including zero and the 255/256 boundary."""
    if type(seconds) is not int or not 0 <= seconds <= 300:
        raise ValueError("Choose a light timeout between 0 and 300 seconds")
    parts = seconds.to_bytes(4, "big")
    return codec.light_timer(parts[0] + parts[1], parts[2] + parts[3])


def alarm_action(available: dict[str, int], choices: tuple[str, ...]) -> int:
    """Layout-order first bed, last massage, exactly two massage entries => 5D.

    Keys identify controls, so different controls with the same tag stay
    distinct. Source helper-only bytes never expand a layout's ownership.
    """
    if (
        not choices
        or len(set(choices)) != len(choices)
        or any(key not in available for key in choices)
    ):
        raise ValueError("Choose alarm controls offered by this layout")
    selected = [code for key, code in available.items() if key in choices]
    beds = [code for code in selected if code not in MASSAGE]
    massage = [code for code in selected if code in MASSAGE]
    if len(beds) > 1:
        raise ValueError("Choose one bed preset and optional massage controls")
    bed = beds[0] if beds else None
    zone = 0x5D if len(massage) == 2 else massage[-1] if massage else None
    if zone is None:
        assert bed is not None
        return bed
    if bed is None:
        return zone
    if bed not in COMBINATIONS:
        raise ValueError("This preset and massage combination has no alarm write")
    return COMBINATIONS[bed][MASSAGE.index(zone)]
