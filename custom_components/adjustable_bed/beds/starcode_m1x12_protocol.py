"""Adjustable Comfort M1X12 StarCode packets and notification values.

This codec follows the accepted M1X12 artifact report. It deliberately keeps
raw Part numbers instead of assigning physical names to unverified actuators.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

type StateValue = str | int | float | bool | None | list[StateValue] | dict[str, StateValue]

PROFILES: Final = ("cb25", "f23", "kneading")
_PALETTE: Final = (0xFFFFFF, 0xFF0000, 0xFFA500, 0xFFFF00, 0x00FF00, 0x0000FF, 0x800080)
_WAKE: Final = ("none", "zg", "lounge", "tv", "antisnore", "m1", "m2", "light", "massage", "flat")
_PRESET: Final = ("flat", "zg", "lounge", "tv", "antisnore", "m1", "m2")
_LIGHT: Final = ("off", "onOrWhite", "red", "orange", "yellow", "green", "blue", "purple")
_SONIC: Final = ("none", "normal1", "normal2", "normal3", "sonic1", "sonic2", "sonic3")
_MASSAGE: Final = ("off", "intensity1", "intensity2", "intensity3")
_DURATION: Final = ("duration10Min", "duration10Min", "duration20Min", "duration30Min")


def profile_from_name(name: str) -> str | None:
    """Normalize app-name prefixes with the accepted specific-before-generic order."""
    normalized = name.upper()
    if normalized.startswith(("STAR254205", "STAR255401")):
        return "f23"
    if normalized.startswith(("STAR255402", "STAR255403")):
        return "kneading"
    if normalized.startswith("STAR25"):
        return "cb25"
    return None


def manufacturer_dialect(data: bytes) -> str:
    """Decode exact raw character codes; only case-insensitive ``star`` selects S."""
    return "star" if "".join(chr(value) for value in data).lower() == "star" else "legacy"


def _key_bytes(key: int) -> bytes:
    return (key & 0xFFFFFFFF).to_bytes(4, "big")


def normal_packet(key: int, dialect: str) -> bytes:
    """Build one accepted M1X12 normal control frame."""
    payload = _key_bytes(key)
    if dialect == "star":
        return b"\x5a\x01" + payload + b"\xa5"
    if dialect == "legacy":
        return b"\x05\x02" + payload + b"\x00"
    raise ValueError(f"Unknown M1X12 dialect: {dialect}")


def long_packet(key: int) -> bytes:
    """Build the ten-byte C-maker light command."""
    return b"\x08\x02\x00\x00\x00\x00" + _key_bytes(key)


def extended_packet(command: int, value: int, dialect: str) -> bytes:
    """Build the accepted brightness/color/duration packet."""
    payload = bytes((command & 0xFF, value & 0xFF, 0, 0))
    if dialect == "star":
        return b"\x5a\xe0\x04" + payload + b"\xa5"
    if dialect == "legacy":
        return b"\x04\xe0" + payload
    raise ValueError(f"Unknown M1X12 dialect: {dialect}")


def position_packet(axis: int, target: int, dialect: str) -> bytes:
    """Build a raw Part target frame, clamping both byte arguments."""
    pair = bytes((max(0, min(axis, 255)), max(0, min(target, 255))))
    if dialect == "star":
        return b"\x5a\xf0\x03" + pair + b"\x00\xa5"
    if dialect == "legacy":
        return b"\x03\xf0" + pair + b"\x00"
    raise ValueError(f"Unknown M1X12 dialect: {dialect}")


def query_packet(dialect: str) -> bytes:
    """Build the profile's status query."""
    if dialect == "star":
        return b"\x5a\xb0\x00\xa5"
    if dialect == "legacy":
        return b"\x00\xb0"
    raise ValueError(f"Unknown M1X12 dialect: {dialect}")


def keep_open_packet() -> bytes:
    return b"\x5a\x0b\x00\xa5"


def time_packet(
    year_argument: int,
    month: int,
    day: int,
    weekday: int,
    hour: int,
    minute: int,
    second: int,
) -> bytes:
    """Match the builder's year subtraction and weekday-before-time field order."""
    values = (year_argument - 2000, month, day, weekday, hour, minute, second)
    return bytes((0x5A, 0x14, 7, *(value & 0xFF for value in values), 0xA5))


def clock_packet(local_time: datetime) -> bytes:
    """Match the shipped caller, including its second subtraction of 2000."""
    return time_packet(
        local_time.year - 2000,
        local_time.month,
        local_time.day,
        local_time.isoweekday(),
        local_time.hour,
        local_time.minute,
        local_time.second,
    )


def _closest_color(rgb: int) -> int:
    return min(
        range(len(_PALETTE)),
        key=lambda index: sum(
            (((rgb >> shift) & 0xFF) - ((_PALETTE[index] >> shift) & 0xFF)) ** 2
            for shift in (16, 8, 0)
        ),
    )


def _motor(data: bytes) -> dict[str, StateValue]:
    return {
        **{
            key: min(data[offset], 100)
            for key, offset in (
                ("part_1_position", 4),
                ("part_2_position", 6),
                ("part_4_position", 8),
                ("part_8_position", 10),
                ("part_16_position", 5),
                ("part_32_position", 7),
            )
        },
        "motor_stopped": data[17] == 0,
    }


def _normal_rgb(data: bytes) -> dict[str, StateValue]:
    raw_head, raw_foot = data[7] & 0x0F, data[7] >> 4
    color_code = data[14] & 0x0F
    direct_rgb = color_code > 7
    rgb = int.from_bytes(data[16:19], "big") if direct_rgb else _PALETTE[max(color_code - 1, 0)]
    return {
        "massage_time_raw": int.from_bytes(data[4:6], "big"),
        "massage_mode": data[6] & 0x0F,
        "massage_head_level": max(raw_head - 1, 0),
        "massage_foot_level": max(raw_foot - 1, 0),
        "massage_active": raw_head > 0 or raw_foot > 0,
        "light_mode": data[14] >> 4,
        "light_brightness": data[15] >> 4,
        "light_on": color_code > 0,
        "light_color_index": _closest_color(rgb) if direct_rgb else color_code,
        "light_rgb": rgb,
        "light_rgb_mode": int(direct_rgb),
    }


def _sonic(data: bytes) -> dict[str, StateValue]:
    head, foot = data[11] & 0x0F, data[11] >> 4
    any_active = head > 0 or foot > 0
    return {
        "sonic_head_level": head,
        "sonic_foot_level": foot,
        "sonic_active": head > 0 and foot > 0,
        "sonic_frequency": (30 if data[12] == 5 else 40 if data[12] == 9 else 50)
        if any_active
        else 0,
        "sonic_time_raw": int.from_bytes(data[9:11], "big") if any_active else 0,
        "sonic_mode": data[6] >> 4,
        "sonic_massage_type": int((data[8] & 0x0F) > 0),
    }


def _enum(raw: int, values: tuple[str, ...], fallback: str = "none") -> str:
    return values[raw] if raw < len(values) else fallback


def _basic_alarm(data: bytes) -> dict[str, StateValue]:
    updates: dict[str, StateValue] = {}
    for index, start in enumerate((4, 11)):
        if start + 5 >= len(data):
            continue
        details: dict[str, StateValue] = {
            "index": index,
            "repeat_raw": data[start],
            "wake": _enum(data[start + 1], _WAKE),
            "hour": data[start + 2],
            "minute": data[start + 3],
            "isOn": data[start + 5] > 0,
        }
        updates[f"alarm_{index}"] = details["isOn"]
        updates[f"alarm_{index}_details"] = details
    return updates


def _advanced_alarm(data: bytes) -> dict[str, StateValue]:
    updates: dict[str, StateValue] = {}
    for index, offsets in enumerate(
        ((3, 4, 5, 6, 7, 8, 9, 10, 11, 13), (14, 15, 16, 17, 18, 19, 20, 21, 22, 24))
    ):
        if offsets[-1] >= len(data):
            continue
        repeat, preset, light, sonic, music, massage, duration, hour, minute, enabled = (
            data[offset] for offset in offsets
        )
        music_details: dict[str, StateValue] = {"music": music}
        music_value: StateValue = (
            "random" if music == 0 else "none" if music == 99 else music_details
        )
        details: dict[str, StateValue] = {
            "index": index,
            "repeat_raw": repeat,
            "preset": _enum(preset, _PRESET),
            "light": _enum(light, _LIGHT),
            "sonic": _enum(sonic, _SONIC),
            "music": music_value,
            "massage": _enum(massage, _MASSAGE),
            "duration": _enum(duration, _DURATION, "duration10Min"),
            "hour": hour,
            "minute": minute,
            "isOn": enabled > 0,
        }
        updates[f"alarm_{index}"] = details["isOn"]
        updates[f"alarm_{index}_details"] = details
    return updates


def _eq(data: bytes) -> dict[str, StateValue]:
    updates: dict[str, StateValue] = {
        "usb_on": (data[11] & 0x02) != 0,
        "eq_low_frequency": (data[19] & 0x0F) * (1 if data[18] & 1 else -1),
        "eq_high_frequency": (data[19] >> 4) * (1 if data[18] & 0x80 else -1),
        "eq_volume": data[20],
        "eq_preset": {1: "Pop", 2: "Classical", 3: "Jazz"}.get(data[21], "None"),
    }
    for index in range(8):
        magnitude = (data[14 + index // 2] >> (4 * (index % 2))) & 0x0F
        updates[f"eq_band_{index}"] = magnitude * (1 if data[13] & (1 << index) else -1)
    return updates


def parse_notification(
    data: bytes,
    *,
    profile: str,
    dialect: str,
    previous: Mapping[str, StateValue] | None = None,
) -> dict[str, StateValue]:
    """Return a safe state delta for supported M1X12 notification types."""
    del previous  # Consumers merge deltas so untouched domains retain their prior values.
    if profile not in PROFILES:
        raise ValueError(f"Unknown Adjustable Comfort M1X12 profile: {profile}")
    if dialect not in ("star", "legacy"):
        raise ValueError(f"Unknown M1X12 dialect: {dialect}")
    if len(data) < 2 or data[0] != 0xA5:
        return {}
    match data[1]:
        case 0x0D if len(data) >= 18:
            return _motor(data)
        case 0x0B if len(data) >= 20:
            return {**_normal_rgb(data), **_sonic(data)}
        case 0x0C if profile == "cb25" and len(data) >= 17:
            return _basic_alarm(data)
        case 0x0C if profile in ("f23", "kneading") and len(data) >= 25:
            return _advanced_alarm(data)
        case 0x0E if profile in ("f23", "kneading") and len(data) >= 22:
            return _eq(data)
        case 0x0F if profile == "kneading" and len(data) >= 8:
            return {
                "kneading_on": data[4] == 1,
                "kneading_demo": data[3] == 1,
                "kneading_mode": min(data[5], 2),
                "kneading_time_raw": int.from_bytes(data[6:8], "big"),
            }
        case _:
            return {}
