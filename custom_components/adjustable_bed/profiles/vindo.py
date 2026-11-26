"""The Carpe Diem Beds Vindö 1.0.18 profile for Linak two-byte writes."""

from __future__ import annotations

from enum import IntEnum
from typing import Final, Literal

from ..codec.linak import build_simultaneous_command, control_frame

type Axis = Literal["back", "legs"]
type Positions = tuple[int, int]

AXES: Final = ("back", "legs")
REFRESH_MS: Final = 300
HOLD_LIMIT_MS: Final = 20_000
MASSAGE_STEP_MS: Final = 800
IDENTIFY_ON_MS: Final = 1000
IDENTIFY_OFF_MS: Final = 800
TARGET_DEADBAND: Final = 15
PATTERNS: Final = ("Hard wave", "Soft wave", "Hard pulse", "Soft pulse", "Constant")


class Opcode(IntEnum):
    """Vindö control opcodes shared by this app's actions."""

    STOP = -1
    FLAT = 0x00
    LEGS_DOWN = 0x08
    LEGS_UP = 0x09
    BACK_DOWN = 0x0A
    BACK_UP = 0x0B
    MASSAGE_OFF = 0x80
    MASSAGE_NEXT = 0x81
    MASSAGE_HEAD_UP = 0x8D
    MASSAGE_HEAD_DOWN = 0x8E
    MASSAGE_FOOT_UP = 0x8F
    MASSAGE_FOOT_DOWN = 0x90
    MASSAGE_TOGGLE = 0x91
    LIGHT_ON = 0x92
    LIGHT_OFF = 0x93
    LIGHT_TOGGLE = 0x94
    LIGHT_STEP_UP = 0x9E
    LIGHT_STEP_DOWN = 0x9F


def motion(back: bool | None, legs: bool | None) -> bytes:
    """Drive the requested directions, with None for an idle axis."""
    if back is not None and legs is not None:
        return build_simultaneous_command("back", back, "legs", legs)
    if back is not None:
        return control_frame(Opcode.BACK_UP if back else Opcode.BACK_DOWN)
    if legs is not None:
        return control_frame(Opcode.LEGS_UP if legs else Opcode.LEGS_DOWN)
    return control_frame(Opcode.STOP)


def seek(current: Positions, target: Positions) -> bytes:
    """Apply the app's inclusive raw deadband, without deriving a physical unit."""

    def direction(value: int, destination: int) -> bool | None:
        return None if abs(destination - value) <= TARGET_DEADBAND else destination > value

    return motion(direction(current[0], target[0]), direction(current[1], target[1]))


def massage_pattern(index: int) -> tuple[bytes, ...]:
    """Select a default favourite by its zero-based position in the app."""
    if not 0 <= index < len(PATTERNS):
        raise ValueError("Unknown Vindö massage pattern")
    return (
        control_frame(Opcode.MASSAGE_OFF),
        control_frame(Opcode.MASSAGE_TOGGLE),
        *((control_frame(Opcode.MASSAGE_NEXT),) * (index + 1)),
    )
