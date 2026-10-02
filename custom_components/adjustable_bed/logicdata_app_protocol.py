"""Packets from the accepted LOGICDATA app reports.

``phone`` and ``tablet`` are MOTIONrelax 1.0.6 and 1.0.4. ``sleep_smart`` is the
bed side of Sleep Smart Air Mattress 1.0.0, which shares the transports and
framing but has its own presets, startup queries, parser and rename frame.
The selected P1/P2 family is independent of GATT transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AppProfile = Literal["phone", "tablet", "sleep_smart"]
Family = Literal["p1", "p2"]
TransportProfile = Literal["t1", "t2", "t3"]
Layout = Literal[
    "standard_2",
    "standard_3_neck",
    "standard_3_lumbar",
    "standard_3_hi_low",
    "standard_3_split_upper",
    "standard_4",
    "split_series",
    "middle",
]
Axis = Literal["back", "legs", "both", "head", "lumbar", "bed_height", "right_back", "both_backs"]
Preset = Literal["flat", "zero_g", "anti_snore"]
HeldPreset = Literal["flat", "zero_g", "anti_snore", "memory_1", "memory_2"]
MassageMode = Literal["long_interval", "short_interval", "wave", "continuous"]
Wake = Literal["flat", "zero_g", "anti_snore", "memory_1", "memory_2"]
MassageZone = Literal["back", "right", "legs"]
Action = Literal["movement", "preset", "flat", "memory", "massage_mode", "light"]
Schedule = tuple[tuple[int, bytes], ...]
APP_PROFILES: tuple[AppProfile, ...] = ("phone", "tablet", "sleep_smart")
FAMILIES: tuple[Family, ...] = ("p1", "p2")
WIRE_MASSAGE_LEVELS = (0, 2, 3, 4)
CLOCK_STARTUP_OFFSETS = (3000, 3100)
MOVEMENT_REPEAT_MS = 100
MEMORY_HOLD_REPEAT_MS = 200
# Sleep Smart: every preset and memory recall is hold-only and refreshes at 200 ms.
SLEEP_SMART_PRESET_REPEAT_MS = 200
# Subscription setup follows service discovery by 300 ms; T3's name subscription
# follows the data subscription by 100 ms.
SLEEP_SMART_SETUP_DELAY_MS = 300
SLEEP_SMART_NAME_NOTIFY_DELAY_MS = 100
SLEEP_SMART_LAYOUTS: tuple[Layout, ...] = ("standard_2", "split_series")
SLEEP_SMART_AXES: tuple[Axis, ...] = ("back", "legs", "both")
SLEEP_SMART_HELD_PRESETS: tuple[HeldPreset, ...] = ("flat", "zero_g", "anti_snore", "memory_1")
MIDDLE_HELD_PRESETS: tuple[HeldPreset, ...] = ("flat", "memory_1", "memory_2")
# Interactive rename alphabet and length from the app's edit field (maxLength 20).
SLEEP_SMART_NAME_ALPHABET = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZäöüÄÖÜß"
)
SLEEP_SMART_NAME_MAX_CHARS = 20
SLEEP_SMART_NAME_MAX_BYTES = 100


@dataclass(frozen=True)
class Transport:
    service_uuid: str
    write_uuid: str
    notify_uuid: str
    rename_uuid: str | None


TRANSPORTS: dict[TransportProfile, Transport] = {
    "t1": Transport(
        "0000ff12-0000-1000-8000-00805f9b34fb",
        "0000ff01-0000-1000-8000-00805f9b34fb",
        "0000ff02-0000-1000-8000-00805f9b34fb",
        "0000ff06-0000-1000-8000-00805f9b34fb",
    ),
    "t2": Transport(
        "88121427-11e2-52a2-4615-ff00dec16800",
        "88121427-11e2-52a2-4615-ff00dec16801",
        "88121427-11e2-52a2-4615-ff00dec16801",
        None,
    ),
    "t3": Transport(
        "0000fe60-0000-1000-8000-00805f9b34fb",
        "0000fe61-0000-1000-8000-00805f9b34fb",
        "0000fe62-0000-1000-8000-00805f9b34fb",
        "0000fe63-0000-1000-8000-00805f9b34fb",
    ),
}
_LAYOUT_AXES: dict[Layout, tuple[Axis, ...]] = {
    "standard_2": ("back", "legs", "both"),
    "standard_3_neck": ("back", "legs", "head"),
    "standard_3_lumbar": ("back", "legs", "lumbar"),
    "standard_3_hi_low": ("back", "legs", "bed_height"),
    "standard_3_split_upper": ("back", "right_back", "both_backs", "legs"),
    "standard_4": ("head", "back", "lumbar", "legs"),
    "split_series": ("back", "right_back", "legs"),
    "middle": ("back", "legs"),
}
LAYOUTS: tuple[Layout, ...] = tuple(_LAYOUT_AXES)
_AXIS_OPCODES: dict[Axis, int] = {
    "back": 1,
    "legs": 3,
    "both": 5,
    "head": 0x19,
    "bed_height": 0x19,
    "lumbar": 0x1B,
    "right_back": 0x20,
    "both_backs": 0x23,
}
_PRESET_OPCODES: dict[Preset, int] = {"zero_g": 7, "flat": 8, "anti_snore": 9}
_WAKE_CODES: dict[Wake, int] = {
    "flat": 0,
    "anti_snore": 1,
    "zero_g": 2,
    "memory_1": 3,
    "memory_2": 4,
}
_CODE_TO_WAKE: dict[int, Wake] = {code: wake for wake, code in _WAKE_CODES.items()}


def _range(name: str, value: int, lower: int, upper: int) -> None:
    if not lower <= value <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")


def frame(opcode: int, payload: bytes = b"") -> bytes:
    _range("opcode", opcode, 0, 255)
    _range("payload length", len(payload), 0, 255)
    body = bytes((opcode, len(payload))) + payload
    return b"\xf1\xf1" + body + bytes((sum(body) & 255, 0x7E))


P1_RELEASE = frame(0x4E)
P2_RELEASE = frame(0x4E, b"\x00\x00")
MASSAGE_MODE = frame(0x16, b"\x0a")
MASSAGE_STOP = frame(0x11, b"\x08")
SLEEP_SMART_MEMORY_SAVE = frame(0x0A)
FACTORY_RESET = frame(0x1D, b"\x00\x00")
QUERY_SOFTWARE = frame(0, b"\x40\x00")
QUERY_VIBRATION = frame(0, b"\x08")
QUERY_HARDWARE = frame(0, b"\x40")
QUERY_ACTUATOR = frame(0, b"\x50")
QUERY_LIGHT = frame(0, b"\x01\x00")
QUERY_STATUS = frame(0)
QUERY_MASSAGE = frame(0, b"\x08\x00")
# Entering the app's massage tab sends the massage-parameter query three times.
MASSAGE_QUERY_SCHEDULE: Schedule = ((100, QUERY_MASSAGE), (250, QUERY_MASSAGE), (450, QUERY_MASSAGE))
_MASSAGE_MODES: dict[int, MassageMode] = {
    1: "long_interval",
    2: "short_interval",
    3: "wave",
    4: "continuous",
}


def layout_axes(layout: Layout) -> tuple[Axis, ...]:
    return _LAYOUT_AXES[layout]


def sleep_smart_motion_command(family: Family, axis: Axis, up: bool) -> bytes:
    """Use the final two-motor layout; middle rail only changes back and legs."""
    if axis not in SLEEP_SMART_AXES:
        raise ValueError(f"Axis {axis} is unavailable in the Sleep Smart app")
    payload = b"\x00\x00" if family == "p2" and axis != "both" else b"\x01"
    return frame(_AXIS_OPCODES[axis] + (0 if up else 1), payload)


def held_preset_command(preset: HeldPreset) -> bytes:
    """Sleep Smart presets and memory A use P1 frames for every bed profile."""
    if preset == "memory_1":
        return memory_command("p1", 1)
    if preset == "memory_2":
        raise ValueError("Sleep Smart has one memory slot")
    return preset_command("p1", preset)


def sleep_smart_startup_schedule(family: Family) -> Schedule:
    """Both ready-event handlers; ties keep the ViewModel query first."""
    view_model = (
        (300, QUERY_SOFTWARE),
        (600, QUERY_VIBRATION),
        (900, QUERY_HARDWARE),
        (1200, QUERY_ACTUATOR),
        (1500, QUERY_ACTUATOR),
        (1800, QUERY_LIGHT),
        (2100, QUERY_LIGHT),
        (2400, QUERY_STATUS),
        (2700, QUERY_STATUS),
    )
    hardware = QUERY_SOFTWARE if family == "p2" else QUERY_HARDWARE
    activity = tuple(
        (offset + repeat, command)
        for offset, command in ((1000, QUERY_ACTUATOR), (1200, hardware), (1400, QUERY_VIBRATION))
        for repeat in (0, 100)
    )
    return tuple(sorted(view_model + activity, key=lambda item: item[0]))


def motion_command(family: Family, layout: Layout, axis: Axis, up: bool) -> bytes:
    if (family == "p2") != (layout == "middle"):
        raise ValueError("P2 uses the middle layout; P1 uses a standard or split layout")
    if axis not in layout_axes(layout):
        raise ValueError(f"Axis {axis} is unavailable in {layout}")
    return frame(_AXIS_OPCODES[axis] + (0 if up else 1), b"\x00\x00" if family == "p2" else b"\x01")


def preset_command(family: Family, preset: Preset) -> bytes:
    if family == "p2" and preset != "flat":
        raise ValueError("P2 exposes only the flat preset")
    return frame(_PRESET_OPCODES[preset], b"\x00\x00" if family == "p2" else b"\x01")


def memory_command(family: Family, slot: int, save: bool = False) -> bytes:
    _range("memory slot", slot, 1, 2)
    return frame(
        0x0A + 2 * (slot - 1) + (0 if save else 1), b"\x00\x00" if family == "p2" else b"\x01"
    )


def light_command(family: Family) -> bytes:
    return frame(0x0F, b"\x00\x00" if family == "p2" else b"")


def massage_command(zone: MassageZone, level: int) -> bytes:
    """Encode the reachable UI range, not declaration-only intensity constants."""
    _range("massage level", level, 0, 3)
    opcode = {"back": 0x12, "right": 0x22, "legs": 0x14}[zone]
    return frame(opcode, bytes((8, WIRE_MASSAGE_LEVELS[level])))


def release_schedule(action: Action, family: Family, app_profile: AppProfile) -> Schedule:
    """Offsets after the action, without Android gesture-only duplicate callbacks."""
    if action == "light":
        return ((80, P1_RELEASE), (80, P2_RELEASE), (100, P1_RELEASE))
    if action == "massage_mode":
        if app_profile == "tablet":
            return ()
        return ((1000, P2_RELEASE), (1100, P1_RELEASE))
    # P2 flat clicks omit cleanup in Android. HA uses the same packet
    # with its proven held-touch P1 release to guarantee movement cleanup.
    return ((100, P1_RELEASE),)


def startup_schedule(app_profile: AppProfile, family: Family) -> Schedule:
    actuator = frame(0, b"\x50" if app_profile == "phone" else b"\x01")
    hardware = frame(0, b"\x40\x00" if family == "p2" else b"\x40")
    return tuple(
        (offset + repeat, command)
        for offset, command in ((1000, actuator), (1200, hardware), (1400, frame(0, b"\x08")))
        for repeat in (0, 100)
    )


def clock_command(value: datetime) -> bytes:
    """The phone always builds a P1 clock, including for the P2 family."""
    _range("year", value.year, 1970, 2225)
    return frame(
        0x50,
        bytes(
            (
                value.year - 1970,
                value.month,
                value.day,
                (value.weekday() + 1) % 7,
                value.hour,
                value.minute,
                value.second,
            )
        ),
    )


def alarm_command(
    enabled: bool,
    weekdays: tuple[bool, ...],
    hour: int,
    minute: int,
    wake: Wake,
    back_level: int,
    leg_level: int,
) -> bytes:
    """Encode the phone's reachable BLE alarm configuration, not its dead worker."""
    if len(weekdays) != 7:
        raise ValueError("Weekdays must contain Monday through Sunday")
    _range("hour", hour, 0, 23)
    _range("minute", minute, 0, 59)
    _range("back level", back_level, 0, 3)
    _range("leg level", leg_level, 0, 3)
    mask = sum(1 << (index + 1) for index, selected in enumerate(weekdays) if selected)
    return frame(
        0x51,
        bytes(
            (
                int(enabled),
                int(any(weekdays)),
                mask,
                hour,
                minute,
                _WAKE_CODES[wake],
                back_level,
                leg_level,
            )
        ),
    )


def validate_rename(app_profile: AppProfile, name: str) -> bytes:
    """Return the encoded name, enforcing the profile's input rule before writes.

    MOTIONrelax uses a safe printable-ASCII subset, because tablet T3 has an
    unpadded UTF-16 hexadecimal encoding that can produce a null write. Sleep
    Smart uses its edit field's alphabet, 20-character and 100-byte limits.
    """
    if app_profile == "sleep_smart":
        payload = name.encode("utf-8")
        if (
            not 1 <= len(name) <= SLEEP_SMART_NAME_MAX_CHARS
            or len(payload) > SLEEP_SMART_NAME_MAX_BYTES
            or not set(name) <= SLEEP_SMART_NAME_ALPHABET
        ):
            raise ValueError("Name must contain 1..20 letters, digits, ä, ö, ü or ß")
        return payload
    if not 1 <= len(name) <= 255 or any(not 0x20 <= ord(char) <= 0x7E for char in name):
        raise ValueError("Name must contain 1..255 printable ASCII characters")
    return name.encode("ascii")


def rename_command(app_profile: AppProfile, transport: TransportProfile, name: str) -> bytes:
    """Build the name-characteristic write for the selected app and transport."""
    payload = validate_rename(app_profile, name)
    if transport == "t2":
        raise ValueError("T2 has no rename characteristic")
    if transport == "t1" and app_profile != "sleep_smart":
        return payload
    return bytes((1, 0xFC, 7, len(payload) % 256)) + payload


def rename_schedule(app_profile: AppProfile, transport: TransportProfile, name: str) -> Schedule:
    command = rename_command(app_profile, transport, name)
    return tuple((offset, command) for offset in ((0, 500) if app_profile == "tablet" else (0,)))


@dataclass(frozen=True)
class AlarmState:
    enabled: bool
    weekdays: tuple[bool, ...]
    hour: int
    minute: int
    wake: Wake | None
    back_level: int
    leg_level: int


@dataclass(frozen=True)
class Notification:
    middle: bool | None = None
    hardware_ack: bool = False
    clock_requested: bool = False
    alarm: AlarmState | None = None
    massage_back: int | None = None
    massage_legs: int | None = None
    light_on: bool | None = None
    # A reported massage mode; None with ``massage_mode_reported`` is the app's "--".
    massage_mode: MassageMode | None = None
    massage_mode_reported: bool = False


def _parse_status(data: bytes) -> Notification | None:
    """Opcode 05/06 status under any header: light bit and 06 massage levels."""
    if len(data) >= 9 and data[2] in (5, 6):
        return Notification(
            light_on=bool(data[8] & 0x40),
            massage_back=data[4] if data[2] == 6 and data[4] in WIRE_MASSAGE_LEVELS else None,
            massage_legs=data[6] if data[2] == 6 and data[6] in WIRE_MASSAGE_LEVELS else None,
        )
    return None


def _parse_sleep_smart(data: bytes) -> Notification | None:
    """Sleep Smart decodes no family selector, but adds clock and massage-mode events."""
    prefix = data[:3]
    if prefix == b"\xf2\xf2\x50":
        return Notification(clock_requested=True)
    if prefix == b"\xf2\xf2\x0d" and len(data) >= 5:
        text = f"{data[4]:02X}"
        if not text.isdigit():
            # The app's decimal parse of this hex text throws; nothing is shown.
            return None
        return Notification(massage_mode=_MASSAGE_MODES.get(int(text)), massage_mode_reported=True)
    return _parse_status(data)


def parse_notification(app_profile: AppProfile, data: bytes) -> Notification | None:
    """Decode a complete callback, guarding field bounds without invented checksums.

    The apps accept arbitrary headers for 05/06 status. They do not validate
    checksum/trailer or declared payload lengths; we preserve those semantics.
    """
    if app_profile == "sleep_smart":
        return _parse_sleep_smart(data)
    prefix = data[:3]
    if prefix == b"\xf2\xf2\x11" and len(data) >= 5:
        return Notification(middle=data[4] == 1)
    if prefix == b"\xf2\xf2\x0f" and len(data) >= 7:
        return Notification(hardware_ack=True)
    if app_profile == "phone":
        if prefix == b"\xf2\xf2\x50" and len(data) >= 6:
            return Notification(clock_requested=True)
        if prefix == b"\xf2\xf2\x51" and len(data) >= 14:
            if data[7] > 23 or data[8] > 59 or max(data[10:12]) > 3:
                return None
            return Notification(
                alarm=AlarmState(
                    data[4] == 1,
                    tuple(bool(data[6] & (1 << bit)) for bit in range(1, 8)),
                    data[7],
                    data[8],
                    _CODE_TO_WAKE.get(data[9]),
                    data[10],
                    data[11],
                )
            )
    return _parse_status(data)
