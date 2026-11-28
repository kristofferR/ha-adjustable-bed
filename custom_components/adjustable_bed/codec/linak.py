"""Linak control/configuration encoders and app-specific position parsers."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Final


def control_frame(opcode: int, *, slow: bool = False) -> bytes:
    """Encode an opcode and optional slow flag, including signed JS literal -1."""
    return bytes((opcode & 0xFF, 0x40 if slow else 0))


def _float32(value: float) -> float:
    """Round an arithmetic step as an Android float, including overflow."""
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def _speed_word(value: float) -> int:
    value = _float32(_float32(_float32(value) * 32768) / 200)
    # JVM float-to-int saturates (NaN becomes zero); int-to-short retains low16.
    if math.isnan(value):
        integer = 0
    elif value >= 2147483647:
        integer = 2147483647
    elif value <= -2147483648:
        integer = -2147483648
    else:
        integer = int(value)
    return integer & 0xFFFF


def custom_speed_frame(opcode: int, speed_up: float, acceleration_up: float) -> bytes:
    """AR Connect native configuration builder, without a hardware input-range claim."""
    speed, acceleration = _speed_word(speed_up), _speed_word(acceleration_up)
    return bytes((0, opcode, 0x80)) + struct.pack(
        "<5H", speed, speed, acceleration, acceleration, 0
    )


@dataclass(frozen=True, slots=True)
class NativeReference:
    """AR Connect's unitless native sample, separate from legacy Bed Control state."""

    extension: float = 0
    position_export: float = 0
    flags: int = 0
    speed: float = 0

    @property
    def moving(self) -> bool:
        return self.speed != 0


def parse_native_reference(data: bytes | bytearray) -> NativeReference:
    """Decode four bytes, retaining signed speed and binary32 event arithmetic."""
    if len(data) != 4:
        return NativeReference()
    word = int.from_bytes(data, "little")
    extension = _float32((word & 0xFFFF) / 100)
    speed = word >> 20
    if speed & 0x800:
        speed -= 0x1000
    return NativeReference(
        extension=extension,
        position_export=_float32(extension * 100),
        flags=(word >> 16) & 0xF,
        speed=speed * 0.09765625,
    )


def selected_sections_frame(sections: frozenset[str], up: bool) -> bytes:
    """Carpe Diem's ordered same-direction selector, including three-section inputs."""
    if not sections or sections.difference({"back", "legs", "head", "feet"}):
        raise ValueError("Select back, legs, head or feet")
    if len(sections) == 4:
        return control_frame(int(up))
    for first, second in (
        ("back", "legs"),
        ("back", "feet"),
        ("back", "head"),
        ("legs", "feet"),
        ("legs", "head"),
        ("head", "feet"),
    ):
        if {first, second} <= sections:
            return build_simultaneous_command(first, up, second, up)
    axis = next(iter(sections))
    return control_frame({"back": 0x0A, "legs": 0x08, "head": 0x02, "feet": 0x04}[axis] + up)


def parse_vindo_position(data: bytes | bytearray) -> int | None:
    """Decode the first two bytes as an unsigned count, ignoring trailing data."""
    if len(data) < 2:
        return None
    return int.from_bytes(data[:2], "little")


_SIMULTANEOUS_BASES: Final[dict[tuple[str, str], int]] = {
    ("base", "feet"): 0x10,
    ("base", "head"): 0x11,
    ("base", "legs"): 0x12,
    ("base", "back"): 0x13,
    ("feet", "head"): 0x20,
    ("feet", "legs"): 0x21,
    ("feet", "back"): 0x22,
    ("head", "legs"): 0x2C,
    ("head", "back"): 0x2D,
    ("legs", "back"): 0x34,
}
_AXIS_ORDER: Final[dict[str, int]] = {
    axis: index for index, axis in enumerate(("base", "feet", "head", "legs", "back"))
}


def build_simultaneous_command(
    first_axis: str,
    first_up: bool,
    second_axis: str,
    second_up: bool,
) -> bytes:
    """Build one of the 40 reachable two-section movement commands."""
    if first_axis == second_axis:
        raise ValueError("Linak simultaneous movement requires two different axes")
    try:
        if _AXIS_ORDER[first_axis] > _AXIS_ORDER[second_axis]:
            first_axis, second_axis = second_axis, first_axis
            first_up, second_up = second_up, first_up
        base = _SIMULTANEOUS_BASES[(first_axis, second_axis)]
    except KeyError as err:
        raise ValueError(
            f"Unsupported Linak simultaneous axes: {first_axis}, {second_axis}"
        ) from err

    second_offset = 0
    if (first_axis, second_axis)[0] == "base":
        second_offset = {"feet": 0, "head": 1, "legs": 2, "back": 3}[second_axis]
        base = 0x10 + second_offset
        direction_offset = (0x08 if first_up else 0) + (0x04 if second_up else 0)
    elif first_axis == "feet":
        second_offset = {"head": 0, "legs": 1, "back": 2}[second_axis]
        base = 0x20 + second_offset
        direction_offset = (0x06 if first_up else 0) + (0x03 if second_up else 0)
    elif first_axis == "head":
        second_offset = {"legs": 0, "back": 1}[second_axis]
        base = 0x2C + second_offset
        direction_offset = (0x04 if first_up else 0) + (0x02 if second_up else 0)
    else:
        direction_offset = (0x02 if first_up else 0) + (0x01 if second_up else 0)
    return control_frame(base + direction_offset)
