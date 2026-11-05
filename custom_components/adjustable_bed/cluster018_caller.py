"""Selected getter/event semantics, separate from HA's safe command lifecycle.

Missing payload assignment and an actual null assignment are distinct. The
caller returns a transition; the worker owns the retained counter and latch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from .cluster018_profiles import Control
from .cluster018_protocol import Wire, decode_resource


class Retain(Enum):
    VALUE = "retain"


RETAIN = Retain.VALUE


@dataclass(frozen=True, slots=True)
class Selection:
    press_flag: str = "53"
    head: bool = True
    armed: bool = False
    hold: bool | None = None
    voice_permission: str = "GRANTED"


@dataclass(frozen=True, slots=True)
class Transition:
    payload: bytes | None | Retain = RETAIN
    mode: int | Retain = RETAIN
    count_ms: int | Retain = RETAIN
    press_flag: str | Retain = RETAIN
    consume_arm: bool = False
    owner: Literal["take", "clear", "retain"] = "retain"
    head: bool | None = None
    local: str | None = None
    idle_up_guard: bool = False


_HOLD_RECALL = {
    "BRRM": {"btnM1", "btnM2", "btnTv", "btnZg", "btnSnore"},
    "YFRM": {"btnM1", "btnM2"},
    "YGRM": {"btnM1", "btnM2", "btnTv", "btnZg", "btnSnore"},
}
_NAVIGATION = frozenset(
    ("b8tt", "b9tt", "zri0", "i4rm", "i5rm", "d7rm", "zr00", "zr01", "aprm", "aqrm",
     "mdrm", "merm", "mfrm", "mgrm", "j6rm", "mcrm", "kxrm")
)


def effective_status(button: Control, layout: str, selection: Selection) -> int:
    if selection.hold is not None and layout in _HOLD_RECALL:
        if button.view_id in _HOLD_RECALL[layout]:
            return 1 if selection.hold else 3
        if button.view_id == "btnFlat":
            return 1 if selection.hold else 2
    return button.status


def short_operand(button: Control, wire: Wire) -> str | None:
    return button.short_old if wire == "RAW" and button.short_old is not None else button.short


def selected_operand(
    button: Control, wire: Wire, argument: int, selection: Selection
) -> bytes | None | Retain:
    value = short_operand(button, wire)
    if argument == 1:
        tag = button.tag
        if tag is not None and tag != "50" and not (wire == "FRAMED" and tag in ("wfrm", "fwrm")):
            if tag in ("51", "52"):
                operands = {"53": ("3F", "40"), "54": ("41", "42"), "55": ("71", "72")}
                pair = operands.get(selection.press_flag)
                value = pair[tag == "52"] if pair else tag
            elif tag == "63":
                value = button.short_old if selection.head else None
            else:
                value = tag
        return decode_resource(value)
    if argument in (2, 5):
        return decode_resource(value)
    if argument == 3:
        # All accepted constructors leave the legacy-long getter uninitialized.
        return decode_resource(button.long)
    if argument == 10 and wire == "FRAMED":
        return decode_resource(button.long if button.long is not None else button.short)
    return RETAIN


def transition(
    button: Control,
    layout: str,
    wire: Wire,
    selection: Selection,
    event: Literal["DOWN", "UP"],
    *,
    app: str | None = None,
) -> Transition:
    """Call only after entry/type/owner/connection guards permit delivery."""
    if not button.rich_button:
        return Transition(local="type_guard")
    status = effective_status(button, layout, selection)
    if event == "DOWN":
        if status == 8:
            if selection.voice_permission != "DENIED_REQUEST_RETURNS":
                return Transition(local="voice_permission")
        if status in (7, 10, 11):
            return Transition(local="auxiliary")
        tag = button.tag
        if tag is not None:
            if tag.lower() in _NAVIGATION or app in ("fortywinks", "superior") and tag.lower() in ("corn", "cprn"):
                return Transition(local="navigate:" + tag.lower())
            if tag in ("61", "62"):
                return Transition(head=tag == "61", local="head_foot")
            if tag == "65":
                return Transition(local="massage_popup")
        count = button.threshold_ms
        argument = status
        consume = button.mem_special or button.select_special and selection.armed
        prior_mode: int | Retain = RETAIN
        if button.mem_special:
            argument = 3 if selection.armed else 1
            count = 0 if selection.armed else 150
            if not selection.armed:
                prior_mode = 1
        elif button.select_special and selection.armed:
            argument = 10
        payload = selected_operand(button, wire, argument, selection)
        mode = prior_mode
        if isinstance(payload, bytes):
            mode = (4 if status == 1 else 2) if argument == 10 else argument
        return Transition(payload, mode, count, consume_arm=consume, owner="take")
    if status == 8 and selection.voice_permission in ("GRANTED", "CHECK_THROWS"):
        return Transition(
            owner="clear" if selection.voice_permission == "GRANTED" else "retain",
            local="voice_permission",
        )
    if status == 11:
        return Transition(local="torch_once")
    if button.tag in ("61", "62"):
        return Transition(local="head_foot")
    if button.mem_special:
        return Transition(mode=0, owner="clear", idle_up_guard=status == 1)
    if status == 1:
        return Transition(mode=0, owner="clear", idle_up_guard=True)
    if status == 3:
        payload = decode_resource(short_operand(button, wire))
        mode = 4 if payload is not None else 0 if wire == "FRAMED" else RETAIN
        return Transition(payload, mode, press_flag=button.tag or RETAIN, owner="clear")
    return Transition(owner="clear", local="torch_off" if status == 9 else None)
