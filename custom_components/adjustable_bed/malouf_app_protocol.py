"""Frozen Malouf 2.4.3 / Lucid 1.3.3 application packet and model contracts.

The package-local P1/P2 labels are inverted, so transport names describe the
wire format. Source: accepted reports' command, model and notification tables.
No dead controller constants or ambiguous multi-service hybrid is exposed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Literal

AppProfile = Literal["malouf", "lucid"]
Transport = Literal[
    "command32_legacy", "command32_middle", "command32_new", "opcode_legacy", "opcode_framed"
]
APP_PROFILES = ("malouf", "lucid")


@dataclass(frozen=True)
class TransportProfile:
    """Explicit, unmixed GATT roles recovered in each application."""

    service_uuid: str
    write_uuid: str
    notify_uuid: str | None = None
    notify_service_uuid: str | None = None


TRANSPORT_PROFILES = MappingProxyType(
    {
        "command32_legacy": TransportProfile(
            "0000ffe5-0000-1000-8000-00805f9b34fb",
            "0000ffe9-0000-1000-8000-00805f9b34fb",
            "0000ffe4-0000-1000-8000-00805f9b34fb",
            "0000ffe0-0000-1000-8000-00805f9b34fb",
        ),
        "command32_middle": TransportProfile(
            "62741523-52f9-8864-b1ab-3b3a8d65950b",
            "62741525-52f9-8864-b1ab-3b3a8d65950b",
            "62741625-52f9-8864-b1ab-3b3a8d65950b",
            "62741523-52f9-8864-b1ab-3b3a8d65950b",
        ),
        "command32_new": TransportProfile(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        ),
        "opcode_legacy": TransportProfile(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
        ),
        "opcode_framed": TransportProfile(
            "0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"
        ),
    }
)


@dataclass(frozen=True)
class ModelProfile:
    """Constructor capabilities, subsequently intersected with live transport actions."""

    manual: tuple[str, ...]
    presets: tuple[str, ...]
    other: tuple[str, ...]
    memory_slots: int
    programming_slots: tuple[int, ...]


def _model(axes: str, presets: str, other: str, slots: int = 0) -> ModelProfile:
    return ModelProfile(
        tuple(f"{axis}{direction}" for axis in axes.split() for direction in ("Up", "Down")),
        tuple(presets.split()),
        tuple(other.split()),
        slots,
        tuple(range(1, slots + 1)),
    )


_BASIC = "head foot"
_PRESETS = "zeroG antiSnore lounge tvRead"
_MASSAGE = "massageHead massageFoot massageWave"
_OPCODE_OTHER = f"{_MASSAGE} massageOff massageTimerSet lightSwitch"
_WORD_OTHER = f"{_MASSAGE} massageTimer alarm lightSwitch"
MODEL_PROFILES = MappingProxyType(
    {
        "altitude": _model(
            f"{_BASIC} dual tiltHead fullTilt",
            "zeroG antiSnore",
            f"{_MASSAGE} massageOff lightSwitch",
        ),
        "e450": _model(_BASIC, "zeroG antiSnore", ""),
        "e455": _model(_BASIC, "zeroG antiSnore", ""),
        "forte": _model(_BASIC, "zeroG", "massageHead massageWave massageOff"),
        "good_life_base": _model(f"{_BASIC} all", _PRESETS, ""),
        "good_life_premier_base": _model(f"{_BASIC} all headTilt lumbar", _PRESETS, _OPCODE_OTHER),
        "good_life_pro_base": _model(f"{_BASIC} all", _PRESETS, _OPCODE_OTHER),
        "l300": _model(_BASIC, "zeroG antiSnore", ""),
        "l600": _model(_BASIC, _PRESETS, _WORD_OTHER, 1),
        "m455": _model(
            _BASIC, "zeroG antiSnore", "massageHead massageWave massageOff massageTimerSet"
        ),
        "m550": _model(_BASIC, _PRESETS, _WORD_OTHER, 1),
        "m555": _model(f"{_BASIC} dual", _PRESETS, _OPCODE_OTHER, 1),
        "premium": _model(f"{_BASIC} dual", "zeroG antiSnore tvRead read", _WORD_OTHER, 2),
        "s655": _model(f"{_BASIC} dual headTilt", _PRESETS, _OPCODE_OTHER, 2),
        "s750": _model(f"{_BASIC} headTilt lumbar", _PRESETS, _WORD_OTHER, 2),
        "s755": _model(f"{_BASIC} dual headTilt lumbar", _PRESETS, _OPCODE_OTHER, 2),
    }
)

_COMMAND32 = {
    "stopDriver": 0,
    "headUp": 1,
    "headDown": 2,
    "footUp": 4,
    "footDown": 8,
    "dualUp": 5,
    "dualDown": 10,
    "headTiltUp": 0x10,
    "headTiltDown": 0x20,
    "lumbarUp": 0x40,
    "lumbarDown": 0x80,
    "massageTimer": 0x200,
    "massageFoot": 0x400,
    "massageHead": 0x800,
    "zeroG": 0x1000,
    "lounge": 0x2000,
    "read": 0x2000,
    "tvRead": 0x4000,
    "antiSnore": 0x8000,
    "memory1": 0x10000,
    "lightSwitch": 0x20000,
    "memory2": 0x40000,
    "allFlat": 0x08000000,
    "massageWave": 0x10000000,
    "setMemory1": 0x10000,
    "setMemory2": 0x80040000,
}
_OPCODE = {
    "headUp": 0x24,
    "headDown": 0x25,
    "footUp": 0x26,
    "footDown": 0x27,
    "dualUp": 0x29,
    "allUp": 0x29,
    "dualDown": 0x2A,
    "allDown": 0x2A,
    "setMemory1": 0x2B,
    "setMemory2": 0x2C,
    "memory1": 0x2E,
    "memory2": 0x2F,
    "allFlat": 0x31,
    "lightSwitch": 0x3C,
    "fullTiltUp": 0x3F,
    "headTiltUp": 0x3F,
    "fullTiltDown": 0x40,
    "headTiltDown": 0x40,
    "tiltHeadUp": 0x41,
    "lumbarUp": 0x41,
    "tiltHeadDown": 0x42,
    "lumbarDown": 0x42,
    "zeroG": 0x45,
    "antiSnore": 0x46,
    "massageOff": 0x47,
    "massageWave": 0x48,
    "massageHead": 0x4C,
    "massageFoot": 0x4E,
    "tvRead": 0x58,
    "lounge": 0x59,
    "massage10": 0x5F,
    "massage30": 0x61,
    "massage20": 0x63,
    "stopDriver": 0x6E,
}
_SIDE_ACTIONS = frozenset(("headUp", "headDown", "massageHead", "allFlat", "zeroG", "antiSnore"))
_QUERY_ACTIONS = frozenset(
    ("massageTimer", "massageFoot", "massageHead", "massageWave", "lightSwitch")
)


def _validate_transport(transport: str) -> None:
    if transport not in TRANSPORT_PROFILES:
        raise ValueError(f"Unknown app transport: {transport}")


def get_profile(app: str, model: str, transport: str) -> ModelProfile:
    """Intersect exact constructor actions with the chosen clean transport."""
    _validate_transport(transport)
    if app not in APP_PROFILES or model not in MODEL_PROFILES:
        raise ValueError("Unknown app or model profile")
    profile = MODEL_PROFILES[model]
    opcode = transport.startswith("opcode_")
    commands = _OPCODE if opcode else _COMMAND32
    extra = {"massageTimerSet"} if opcode else {"alarm"}
    lucid_oz = app == "lucid" and model in (
        "good_life_base",
        "good_life_premier_base",
        "good_life_pro_base",
    )
    # Both OFF and TIMER labels share onClick=massageTimer. The activity
    # remaps that callback to massageOff only for opcode transports.
    other = tuple(
        ("massageOff" if opcode else "massageTimer")
        if action in ("massageOff", "massageTimer")
        else action
        for action in profile.other
    )
    return replace(
        profile,
        manual=tuple(action for action in profile.manual if action in commands),
        presets=("allFlat",)
        + tuple(
            action
            for action in profile.presets
            if action in commands
            and (action != "read" or app == "lucid")
            and not (lucid_oz and not opcode and action in ("zeroG", "antiSnore"))
        ),
        other=tuple(action for action in other if action in commands or action in extra),
        # Lucid's unmatched Oz labels enter the memory-slot-2 long-hold UI.
        programming_slots=(2,) if lucid_oz else profile.programming_slots,
    )


def encode_command(
    action: str, transport: str, primary: bool = True, device_name: str = ""
) -> bytes:
    """Build a reachable SDK command; callers enforce model/app action gates."""
    _validate_transport(transport)
    if not isinstance(primary, bool):
        raise ValueError("Primary selector must be boolean")
    try:
        command = (_OPCODE if transport.startswith("opcode_") else _COMMAND32)[action]
    except KeyError as err:
        raise ValueError(f"Unsupported command {action} for {transport}") from err
    if transport == "opcode_legacy":
        return bytes((command,))
    if transport == "opcode_framed":
        side = int(not primary) if action in _SIDE_ACTIONS else 0
        return bytes((0x6E, 1, side, command, (0x6F + side + command) & 0xFF))
    if action == "setMemory1" and "smartbed238" in device_name.lower():
        command = 0x80010000
    if transport == "command32_legacy":
        frame = b"\xe6\xfe\x16" + command.to_bytes(4, "little") + b"\0"
        return frame + bytes((~sum(frame) & 0xFF,))
    prefix, padding = (b"\x04\x02", 4) if transport == "command32_middle" else (b"\x05\x02", 2)
    return prefix + command.to_bytes(4, "big") + bytes(padding)


def query_after(action: str, transport: str) -> bool:
    """Only the new command32 path queues an unframed status request."""
    _validate_transport(transport)
    return transport == "command32_new" and action in _QUERY_ACTIONS


def _integer(value: int, minimum: int, maximum: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _require_alarm_transport(transport: str) -> None:
    _validate_transport(transport)
    if not transport.startswith("command32_"):
        raise ValueError("This app transport has no clock or alarm command")


def encode_alarm(transport: str, hour: int, minute: int, alarm_type: int, repeats: int) -> bytes:
    """Encode raw alarm fields; (0, 0, 0, 0) is the app's clear operation."""
    _require_alarm_transport(transport)
    for value, low, high, name in (
        (hour, 0, 23, "Hour"),
        (minute, 0, 59, "Minute"),
        (alarm_type, 0, 255, "Alarm type"),
        (repeats, 0, 255, "Repeats"),
    ):
        _integer(value, low, high, name)
    if transport == "command32_new":
        transformed = (repeats & 0x7E) | int(bool(repeats & 0x80))
        return bytes(
            (7, 5, transformed, (alarm_type - 12) & 0xFF, hour, minute, 0, int(transformed > 0), 0)
        )
    frame = bytes((0xED, 0x80, 3, hour, minute, repeats, alarm_type)) + bytes(8)
    return frame + bytes((~sum(frame) & 0xFF,))


def encode_time(transport: str, value: datetime) -> bytes:
    """Encode local wall time, including Java's Sunday-zero weekday convention."""
    _require_alarm_transport(transport)
    if transport == "command32_new":
        return bytes(
            (
                7,
                4,
                value.year & 0xFF,
                value.month,
                value.day,
                (value.weekday() + 1) % 7,
                value.hour,
                value.minute,
                value.second,
            )
        )
    frame = bytes(
        (
            0xE7,
            0x80,
            1,
            (value.year - 1900) & 0xFF,
            value.month - 1,
            value.day,
            value.hour,
            value.minute,
            value.second,
        )
    )
    return frame + bytes((~sum(frame) & 0xFF,))


@dataclass(frozen=True)
class NotificationState:
    """Unmodified app-parser values; consumers decide what HA can display."""

    massage_minutes: int
    light: int


def parse_notification(transport: str, data: bytes | bytearray) -> NotificationState | None:
    """Match accepted bounds and signed-byte semantics without inventing a checksum gate."""
    _validate_transport(transport)

    def signed_at(index: int) -> int:
        value = data[index] if len(data) > index else 0
        return value - 256 if value >= 128 else value

    if transport == "command32_legacy":
        offsets = {10: (8, 7), 16: (14, 13), 20: (19, 18)}.get(len(data))
        if offsets is None:
            return None
        massage, light = offsets
        return NotificationState(
            {1: 10, 2: 20, 3: 30}.get(signed_at(massage) & 15, 0), signed_at(light) >> 6
        )
    if transport == "command32_middle":
        return NotificationState(signed_at(10) * 10, 0)
    if transport == "command32_new" and len(data) > 1 and data[1] == 11:
        level = signed_at(4)
        minutes = 30 if level > 4 else 20 if level > 2 else 10 if level > 0 else 0
        light_on = (len(data) > 13 and data[13] == 1) or (len(data) > 9 and data[9] == 1)
        return NotificationState(minutes, int(light_on))
    return None


MOVEMENT_ACTIONS = frozenset(
    action for action in _OPCODE | _COMMAND32 if action.endswith(("Up", "Down"))
)
PRESET_ACTIONS = frozenset(
    ("allFlat", "zeroG", "antiSnore", "lounge", "tvRead", "read", "memory1", "memory2")
)
PROGRAM_ACTIONS = frozenset(("setMemory1", "setMemory2"))
ROUTABLE_ACTIONS = frozenset(_OPCODE | _COMMAND32)
BED_TYPES = ("single_bed", "split_bed", "split_head")
BED_CONFIGURATIONS = ("standard", "split_base", "dual_base")
SIDES = ("none", "left", "right", "all")


@dataclass(frozen=True)
class RoutedAction:
    """One child's SDK action and its explicit primary/secondary selector."""

    action: str
    primary: bool


def route_child_action(
    app: str,
    action: str,
    *,
    bed_type: str = "single_bed",
    configuration: str = "standard",
    active_side: str = "all",
    child_side: str = "none",
    motor_swapped: bool = False,
) -> RoutedAction | None:
    """Route one app action through ActiveBed and RemoteTabBarActivity rules.

    Accepted ActiveBed.java:37-50 defines side and selector semantics; the
    activity's command/preset/save paths intentionally select different bases.
    Capability and transport validation remains the destination's responsibility.
    """
    if app not in APP_PROFILES or action not in ROUTABLE_ACTIONS:
        raise ValueError("Unknown app or routable action")
    if bed_type not in BED_TYPES or configuration not in BED_CONFIGURATIONS:
        raise ValueError("Unknown bed type or configuration")
    if active_side not in SIDES or child_side not in SIDES:
        raise ValueError("Unknown active or child side")
    if not isinstance(motor_swapped, bool):
        raise ValueError("Motor swapped must be boolean")
    active = active_side == "all" or active_side == child_side or child_side == "none"
    native_split = bed_type == "split_head" and configuration == "split_base"
    dual_split = bed_type == "split_head" and configuration == "dual_base"
    primary = not native_split or (
        (active_side == "left" and not motor_swapped) or (active_side == "right" and motor_swapped)
    )
    if action in PROGRAM_ACTIONS:
        # Save collects active peripherals; its SDK call uses the default selector.
        return RoutedAction(action, True) if active else None
    if action in PRESET_ACTIONS:
        return RoutedAction(action, primary) if active or dual_split else None
    if native_split:
        return RoutedAction(action, primary)
    if active:
        return RoutedAction(action, True)
    if dual_split:
        if "dual" in action or "foot" in action or (app == "lucid" and "all" in action):
            routed = action.replace("dual", "foot")
            if app == "lucid":
                routed = routed.replace("all", "foot")
            return RoutedAction(routed, True)
        if "stop" in action:
            return RoutedAction(action, True)
    return None
