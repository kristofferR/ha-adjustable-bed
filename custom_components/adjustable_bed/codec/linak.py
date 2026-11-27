"""Encoders for Linak's two-byte control words and Vindö position samples."""

from __future__ import annotations

from typing import Final


def control_frame(opcode: int) -> bytes:
    """Encode a control opcode, including STOP's signed JS literal (-1)."""
    return bytes((opcode & 0xFF, 0))


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
