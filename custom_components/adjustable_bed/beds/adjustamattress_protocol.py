"""AdjustaMattress 1.6.0 packet and notification contracts (APK audit row067).

Model numbers identify this artifact's enums, not a shared UUID protocol family.
See docs/beds/adjustamattress.md for the safety dispositions and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Model = Literal["P1", "P2", "P3", "P4"]
MODELS: tuple[Model, ...] = ("P1", "P2", "P3", "P4")
LAYOUTS = (
    "AdjustaLumbarHeadTilt",
    "AdjustaBed",
    "AdjustaMattress",
    "AdjustaBedLumbar",
    "FoldingBed",
    "HilowBed",
    "Lolobed",
)
MOVEMENT = {
    "headUp": 1,
    "headDown": 2,
    "footUp": 4,
    "footDown": 8,
    "unionUp": 5,
    "unionDown": 10,
    "neckTiltUp": 16,
    "neckTiltDown": 32,
    "lumbarUp": 64,
    "lumbarDown": 128,
    "stop": 0,
}
PRESETS = {"zeroGravity": 1, "flatPosition": 2, "tv": 4, "m1": 8, "lounge": 9, "anti": 9}
LIFTS = {"liftHead": 16, "liftFoot": 32, "liftUp": 64, "liftDown": 128}
CYCLIC = ("headStrengthAdd", "footStrengthAdd", "waveAdd", "massageTimer")
TIMERS = ("timer10", "timer20", "timer30")
BASE_ACTIONS = ("headUp", "headDown", "footUp", "footDown", "flatPosition", "zeroGravity")
LAYOUT_ACTIONS = (
    (
        "anti",
        "lounge",
        "tv",
        "m1",
        "neckTiltUp",
        "neckTiltDown",
        "lumbarUp",
        "lumbarDown",
        "underbedLighting",
    ),
    ("anti", "lounge", "tv", "unionUp", "unionDown", "underbedLighting"),
    ("anti", "lounge", "tv", "unionUp", "unionDown"),
    ("anti", "lounge", "tv", "lumbarUp", "lumbarDown", "unionUp", "unionDown", "underbedLighting"),
    ("anti", "lounge", "tv"),
    ("anti", "lounge", "tv", "neckTiltUp", "neckTiltDown", "underbedLighting"),
    ("liftHead", "liftFoot", "liftUp", "liftDown", "underbedLighting"),
)
DEDICATED = {
    **{
        f"{zone}Massage{word}": (prefix, 16 + i)
        for zone, prefix in (("head", 16), ("foot", 17))
        for i, word in enumerate(("One", "Two", "Three", "Four"))
    },
    **{
        name: (16, 32 + i) for i, name in enumerate(("WaveOne", "waveTwo", "waveThree", "waveFour"))
    },
}


def model_from_name(name: str | None, *, reconnect: bool = True) -> Model:
    """Preserve constructor case, independently of the scan admission rule."""
    name = name or ""
    if name.startswith("SLEEP_V") or (reconnect and name.startswith("SleepBT")):
        return "P4"
    return "P3" if name.startswith("Smartbed") else "P1"


def scan_admits(name: str | None) -> bool:
    return bool(
        name and (name.lower().startswith(("smartbed", "okin")) or name.startswith("SLEEP_V"))
    )


def dedicated_massage(model: Model, layout: int) -> bool:
    return model == "P2" and layout in (0, 1, 2, 3, 5)


def has_snore(model: Model, layout: int) -> bool:
    return model == "P4" and layout in (0, 3)


def _bytes(values: list[int]) -> bytes:
    return bytes(value & 255 for value in values)


def _summed(values: list[int]) -> bytes:
    # The complement covers source integers before Uint8List truncation.
    return _bytes([*values, ~sum(values)])


def frame(
    model: Model,
    action: str,
    *,
    now: datetime | None = None,
    hour: int = 0,
    minute: int = 0,
    repeat: int = 0,
    alarm_type: int = 0,
    enabled: bool = True,
    demonstration: bool = False,
    strength_index: int = 0,
    sleeping: bool = False,
) -> bytes | None:
    """Build a frame; None means the artifact has no new frame on this branch."""
    if action in LIFTS:
        return bytes((5, 2, 0, 0, 0, LIFTS[action], 0))
    if action in DEDICATED:
        prefix, code = DEDICATED[action]
        return _summed([229, 254, 22, prefix, 0, 0, code])
    if action in ("setAlarm", "queryAlarm", "setCurrentTime"):
        if now is None:
            raise ValueError("Clock commands require local time")
        # Dart DateTime weekday is Monday=1 through Sunday=7.
        second, weekday = now.second, now.isoweekday()
        if action == "setCurrentTime":
            if model == "P1":
                return _summed(
                    [231, 128, 1, now.year - 1900, now.month, now.day, now.hour, now.minute, second]
                )
            if model == "P2":
                return None
            return _bytes(
                [
                    7,
                    4,
                    now.year - (2000 if model == "P3" else 1900),
                    now.month - int(model == "P4"),
                    now.day,
                    weekday,
                    now.hour,
                    now.minute,
                    second,
                ]
            )
        if action == "queryAlarm":
            if model == "P1":
                return _summed([226, 128, 3, 0])
            return (
                _summed([226, 254, 22, second, now.minute, now.hour, weekday])
                if model == "P2"
                else b"\x00\xc0"
            )
        if model == "P1":
            return _summed([237, 128, 3, hour, minute, repeat, alarm_type or 19, *([0] * 8)])
        if model == "P2":
            tail = (
                [17, 17, 255]
                if alarm_type == 9
                else [255, 255, {17: 8, 19: 9}.get(alarm_type, 255)]
            )
            return _summed(
                [235, 254, 22, second, now.minute, now.hour, minute, hour, weekday, repeat, *tail]
            )
        kind = (
            8
            if alarm_type == 9
            else 5
            if alarm_type == 17
            else 6
            if model == "P3" or alarm_type == 19
            else 5
        )
        return _bytes(
            [7, 5, repeat, kind, hour, minute, 0, int(repeat != 0), 1]
            if model == "P3"
            else [8, 5, repeat, kind, hour, minute, 0, int(repeat != 0), 0, 0]
        )
    if action == "queryControlBoxStatus":
        return b"\x00\xb0" if model == "P4" else None
    if action in ("queryMassage", "queryMassageOnce"):
        return (
            _summed([230, 254, 22, 3, 0, 0, 0, 0])
            if model == "P1"
            else None
            if model == "P2"
            else b"\x00\xb0"
        )
    if action == "_sendAntiSnoreCommand":
        return (
            bytes(
                (
                    5,
                    11,
                    2 if demonstration else int(enabled),
                    {0: 1, 1: 3, 2: 6}.get(strength_index, 1),
                    1,
                    35,
                    0,
                )
            )
            if model == "P4"
            else None
        )
    if action == "toggleSleeping":
        return bytes((1, 181, int(not sleeping))) if model == "P4" else None
    if model == "P1":
        payload = [0] * 5
        if action in MOVEMENT:
            payload[0] = MOVEMENT[action]
        elif action in ("zeroGravity", "lounge", "tv", "anti"):
            payload[1] = {"zeroGravity": 16, "lounge": 32, "tv": 64, "anti": 128}[action]
        elif action == "flatPosition":
            payload[3] = 8
        elif action in ("m1", "underbedLighting"):
            payload[2] = 16 if action == "m1" else 2
        elif action in CYCLIC:
            index, value = {
                "headStrengthAdd": (1, 8),
                "footStrengthAdd": (1, 4),
                "waveAdd": (3, 16),
                "massageTimer": (1, 2),
            }[action]
            payload[index] = value
        elif action not in TIMERS:
            raise ValueError(f"Unknown action {action}")
        return _summed([230, 254, 22, *payload])
    if model == "P2":
        if action in MOVEMENT:
            return _summed([229, 254, 22, 0, 0, 0, MOVEMENT[action]])
        if action in PRESETS or action in TIMERS:
            code = PRESETS[action] if action in PRESETS else 65 + TIMERS.index(action)
            return _summed([229, 254, 22, 1, 0, 0, code])
        if action == "underbedLighting":
            return None  # Retained-frame replay is excluded from HA control.
    payload = [0] * 5
    if action in MOVEMENT:
        payload[3] = MOVEMENT[action]
    elif action in ("zeroGravity", "lounge", "tv", "anti"):
        payload[2] = {"zeroGravity": 16, "lounge": 32, "tv": 64, "anti": 128}[action]
    elif action == "flatPosition":
        payload[0] = 8
    elif action in ("m1", "underbedLighting"):
        payload[1] = 1 if action == "m1" else 2
    elif action == "waveAdd":
        return bytes((5, 2, 16, 0, 0, 0, 0))  # P4 also uses 05 here.
    elif action in CYCLIC or action in TIMERS:
        payload[2] = 8 if action == "headStrengthAdd" else 4 if action == "footStrengthAdd" else 2
    else:
        raise ValueError(f"Unknown action {action}")
    return bytes([6 if model == "P4" else 5, 2, *payload, *([0] if model == "P4" else [])])


@dataclass
class State:
    """Artifact fields, with the auxiliary bit deliberately unnamed physically."""

    massage_time: int = 0
    head_intensity: int = 0
    foot_intensity: int = 0
    wave: int = 0
    alarm_on: bool = False
    alarm_hour: int = 0
    alarm_minute: int = 0
    alarm_type: int = 0
    alarm_repeat: int = 0
    sleeping: bool = False
    snore_enabled: bool = True
    sensitivity: int = 1
    auxiliary_status_bit_1: bool = False
    strength_index: int = 0
    demonstration: bool = False
    saved_buffer: bytes = field(default=b"", repr=False)
    busy: bool = False


def parse(model: Model, data: bytes, state: State) -> set[str]:
    """Apply valid artifact payloads atomically; reject short frames safely.

    No checksum, message-length byte or motor-position semantics are inferred.
    Returned fields include on-only changes the app forgot to publish.
    """
    b = data
    values: dict[str, int | bool] = {}
    if model == "P1":
        if len(b) > 20:
            pass
        elif len(b) > 3 and b.startswith(b"\xf4\xfe\x16"):
            state.saved_buffer = b
            return set()
        elif len(b) > 3 and len(b) in (10, 16):
            pass
        else:
            b = state.saved_buffer + b
        if b.startswith(b"\xed\x80"):
            if len(b) < 7:
                return set()
            values.update(
                alarm_hour=b[3],
                alarm_minute=b[4],
                alarm_repeat=b[5],
                alarm_type=b[6],
                alarm_on=b[5] != 0,
            )
        else:
            if len(b) == 23:
                time, head, foot, wave = b[19], b[11] & 7, b[12], b[21]
            elif len(b) == 16:
                time, head, foot, wave = b[14] & 15, b[7] & 15, b[8] & 15, b[14] >> 4
            elif len(b) == 10:
                time, head, foot, wave = b[8], 0, 0, 0
            else:
                return set()  # Do not erase known state on an unknown fragment.
            values.update(
                massage_time=time,
                head_intensity={0: 0, 1: 1, 3: 2, 6: 3}.get(head, 0),
                foot_intensity={0: 0, 1: 1, 3: 2, 6: 3}.get(foot, 0),
                wave=wave if wave <= 4 else 0,
            )
    elif model == "P2":
        if len(b) < 10 or not b.startswith(b"\xe2\xfe"):
            return set()
        kind = {8: 17, 9: 19}.get(b[9] & 15, state.alarm_type)
        if 0 < b[7] < 255 and 0 < b[8] < 255:
            kind = 9
        values.update(
            alarm_hour=b[4],
            alarm_minute=b[3],
            alarm_repeat=b[6],
            alarm_type=kind,
            alarm_on=b[4] < 24 and b[3] < 60,
        )
    elif b.startswith(b"\xa5\x0c") and len(b) >= 10:
        values.update(
            alarm_repeat=b[4],
            alarm_type={5: 17, 6: 19}.get(b[5], 9),
            alarm_hour=b[6],
            alarm_minute=b[7],
            alarm_on=b[9] == 1 if model == "P4" else b[9] != 0,
        )
    elif b.startswith(b"\xa5\x0b"):
        if model == "P3" and len(b) >= 9 and b[2] == 14:
            head_raw, foot_raw = b[7] & 15, b[8]
            head = head_raw % 3 + head_raw // 3 + int(head_raw > 1)
            foot = foot_raw % 3 + foot_raw // 3 + int(foot_raw > 1)
            values.update(
                massage_time=(b[5] + (b[4] << 8) + 599) // 600,
                head_intensity=head,
                foot_intensity=foot,
                wave=b[6] if head or foot else 0,
            )
        elif model == "P4" and len(b) >= 20:
            head, foot = ({3: 2, 6: 3}.get(b[i], b[i]) for i in (7, 8))
            values.update(
                massage_time=(b[4] + (b[5] << 8) + 599) // 600,
                head_intensity=min(3, head),
                foot_intensity=min(3, foot),
                wave=min(4, b[6]) if head or foot else 0,
                sensitivity={4: 0, 3: 1, 2: 2}.get(b[14], 1),
                demonstration=b[15] == 2,
                snore_enabled=b[15] == 1,
                strength_index={1: 0, 3: 1, 6: 2}.get(b[16], 0),
                auxiliary_status_bit_1=bool(b[19] & 2),
                sleeping=bool(b[19] & 4),
            )
    elif model == "P4" and b.startswith(b"\xa6\x40"):
        values["busy"] = True
    for key, value in values.items():
        setattr(state, key, value)
    return set(values)
