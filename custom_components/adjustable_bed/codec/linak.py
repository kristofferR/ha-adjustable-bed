"""Linak control/configuration encoders and Vindö position samples."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final


def control_frame(opcode: int, *, side: int = 0, modifier: bool = False) -> bytes:
    """Encode a control opcode, including STOP's signed JS literal (-1)."""
    return bytes((opcode & 0xFF, (side | (0x40 if modifier else 0)) & 0xFF))


def configuration_frame(code: int, data: bytes = b"", *, write: bool = False, prefix: int = 0x7F) -> bytes:
    """Encode the SDK's prefix/code/type configuration record."""
    return bytes((prefix, code, 0x80 if write else 0)) + data


def massage_selection_frames(sections: frozenset[str], *, enabled: bool = True) -> tuple[bytes, ...]:
    """Encode membership-based massage selection as separate writes."""
    back, legs = "back" in sections, "legs" in sections
    if not enabled:
        return (control_frame(0x8A if back and not legs else 0x8C if legs and not back else 0x80),)
    if not back and not legs:
        return (control_frame(0x80),)
    return control_frame(0x89 if back else 0x8A), control_frame(0x8B if legs else 0x8C)


def selected_directions_frame(directions: Mapping[str, bool], *, modifier: bool = False) -> bytes:
    """Linak SDK's ordered selector, including its four-axis override of BASE."""
    if directions.keys() - _AXIS_ORDER.keys():
        raise ValueError("Unknown Linak axis")
    for up in (True, False):
        if all(directions.get(axis) is up for axis in ("head", "back", "legs", "feet")):
            return control_frame(int(up), modifier=modifier)
    for first, second in (
        ("back", "legs"), ("back", "feet"), ("back", "head"),
        ("legs", "feet"), ("legs", "head"), ("head", "feet"),
        ("base", "back"), ("base", "legs"), ("base", "head"), ("base", "feet"),
    ):
        if first in directions and second in directions:
            opcode = build_simultaneous_command(first, directions[first], second, directions[second])[0]
            return control_frame(opcode, modifier=modifier)
    for axis in ("back", "legs", "head", "feet", "base"):
        if axis in directions:
            opcode = {"back": 0x0A, "legs": 0x08, "head": 0x02, "feet": 0x04, "base": 0x06}[axis]
            return control_frame(opcode + directions[axis], modifier=modifier)
    return control_frame(0xFF, modifier=modifier)


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


class ArtifactParseError(ValueError):
    """A rejected artifact input, retaining its original exception category."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def configuration_response(data: bytes) -> bytes:
    """Tempur's signed length slice; header and trailing bytes are ignored."""
    if len(data) < 2:
        raise ArtifactParseError("ArrayIndexOutOfBoundsException")
    size = int.from_bytes(data[1:2], signed=True)
    if size < 0:
        raise ArtifactParseError("IllegalArgumentException")
    if size + 2 > len(data):
        raise ArtifactParseError("IndexOutOfBoundsException")
    return data[2:2 + size]


def timer_event_frame(seconds: int, actions: tuple[tuple[int, int, int], ...]) -> bytes:
    """Encode the SDK timer, including its negative-duration truncation."""
    if len(actions) > 4:
        raise ValueError("At most four alarm actions")
    return bytes((int(seconds > 65535), seconds & 255, (seconds >> 8) & 255, 1)) + b"".join(
        bytes((opcode, 0, lifetime & 255, pause & 255)) for opcode, lifetime, pause in actions
    )


def timer_channel_frame(*, clear: bool = False) -> bytes:
    """Current Bed API's channel-one query or clear command."""
    return bytes((0x40 if clear else 0x20,))


def timer_info(data: bytes) -> dict[str, object]:
    """Decode Tempur's signed time and exactly one action, ignoring the count."""
    if len(data) < 4:
        raise ArtifactParseError("EOFException")
    seconds = int.from_bytes(data[1:3], "little", signed=True) + (65536 if data[0] & 1 else 0)
    actions: list[list[str | int]] = []
    if seconds > 0:
        if len(data) < 8:
            raise ArtifactParseError("EOFException")
        action = {0x0E: "FAVORITE_1", 0x0F: "FAVORITE_2", 0x0C: "FAVORITE_3",
                  0x44: "FAVORITE_4", 0x94: "AUX_TOGGLE", 0x91: "MASSAGE"}.get(data[4])
        if action is None:
            raise ArtifactParseError("IllegalStateException")
        actions.append([action, int.from_bytes(data[6:7], signed=True), int.from_bytes(data[7:8], signed=True)])
    return {"enabled": seconds > 0, "timer": seconds, "actions": actions}


def timer_notification(data: bytes) -> dict[str, object]:
    """Decode the app's timer event classifier, separately from query contents."""
    if not data:
        return {"kind": "ERROR", "error": None}
    event = data[0]
    if event in (0x20, 0x21):
        return {"kind": "GET_TIMER1", "error": None}
    for first, kind in ((0x80, "ELAPSED"), (0x90, "INTERRUPTED"), (0xA0, "ACT_DONE")):
        if first <= event <= first + 3:
            return {"kind": kind, "channel": event - first + 1, "error": None}
    if event == 0xFF:
        if len(data) < 2:
            raise ArtifactParseError("ArrayIndexOutOfBoundsException")
        error = {1: "UNSUPPORTED_EVENT_ACTION_TYPE", 2: "ILLEGAL_LENGTH", 3: "ILLEGAL_EVENT_ACTION_TYPE",
                 4: "ILLEGAL_RECURRENCE_SETTING"}.get(data[1])
        if error is not None:
            return {"kind": "ERROR", "error": error}
    raise ArtifactParseError("IllegalStateException")


def manufacturer_product(data: bytes | None) -> dict[str, object]:
    """Tempur's first manufacturer value filter, without inferring a bed model."""
    product = None
    if data is None:
        return {"accepted": True, "sdk_product": None}
    if len(data) < 2:
        raise ArtifactParseError("EOFException")
    if data[:2] == b"\xff\xff":
        return {"accepted": True, "sdk_product": None}
    index = 0
    while index < len(data):
        if len(data) - index < 3:
            raise ArtifactParseError("EOFException")
        length = int.from_bytes(data[index:index + 1], signed=True)
        if length < 2:
            raise ArtifactParseError("IllegalArgumentException")
        kind = int.from_bytes(data[index + 1:index + 3], "little")
        if index + length + 1 > len(data):
            if kind not in (0x9000, 0x9010):
                break
            raise ArtifactParseError("EOFException")
        value = data[index + 3:index + 1 + length]
        if kind == 0x9000:
            if len(value) != 3:
                raise ArtifactParseError("IllegalArgumentException")
            product = None
            if value[0] >> 4 == 2:
                product = {1: "WIFI2LIN", 0x101: "WIFI2LIN", 0x201: "WIFI2LIN",
                           2: "DESK", 0x602: "DPI", 4: "RECLINER", 0x104: "RECLINER",
                           0x204: "RECLINER"}.get(int.from_bytes(value[1:], "little", signed=True))
        elif kind == 0x9010 and len(value) != 1:
            raise ArtifactParseError("IllegalStateException")
        index += length + 1
    return {"accepted": product not in {"WIFI2LIN", "DPI", "RECLINER"}, "sdk_product": product}
