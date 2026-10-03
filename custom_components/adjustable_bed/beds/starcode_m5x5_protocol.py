"""AdjustableM5X5 packet and feedback fields from the accepted 1.2.3 artifact.

Feedback is a delta: callers retain fields from other domains. Short frames are
ignored safely instead of reproducing the application's out-of-bounds errors.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Final

type StateValue = str | int | float | bool | None | list[StateValue] | dict[str, StateValue]

_PALETTE: Final = (0xFFFFFF, 0xFF0000, 0xFFA500, 0xFFFF00, 0x00FF00, 0x0000FF, 0x800080)
_WAKE: Final = ("none", "zg", "lounge", "tv", "antisnore", "m1", "m2", "light", "massage", "flat")
_PRESET: Final = ("flat", "zg", "lounge", "tv", "antisnore", "m1", "m2")
_LIGHT: Final = ("off", "onOrWhite", "red", "orange", "yellow", "green", "blue", "purple")
_SONIC: Final = ("none", "normal1", "normal2", "normal3", "sonic1", "sonic2", "sonic3")
_MASSAGE: Final = ("off", "intensity1", "intensity2", "intensity3")
_DURATION: Final = ("duration10Min", "duration10Min", "duration20Min", "duration30Min")


def _is_star(dialect: str) -> bool:
    if dialect not in ("legacy", "star"):
        raise ValueError(f"Unknown AdjustableM5X5 dialect: {dialect}")
    return dialect == "star"


def manufacturer_dialect(data: bytes) -> str:
    """Use exact character-code equality; substring or UTF-8 decoding is different."""
    return "star" if "".join(chr(value) for value in data).lower() == "star" else "legacy"


def normal_packet(key: int, dialect: str) -> bytes:
    """Preserve the low 32 bits, including negative source integers."""
    payload = (key & 0xFFFFFFFF).to_bytes(4, "big")
    return b"\x5a\x01" + payload + b"\xa5" if _is_star(dialect) else b"\x05\x02" + payload + b"\x00"


def long_normal_packet(key: int) -> bytes:
    """Legacy light on/off uses the separate ten-byte builder."""
    return b"\x08\x02\x00\x00\x00\x00" + (key & 0xFFFFFFFF).to_bytes(4, "big")


def extended_packet(key: int, value: int, dialect: str) -> bytes:
    payload = bytes((key & 0xFF, value & 0xFF, 0, 0))
    return b"\x5a\xe0\x04" + payload + b"\xa5" if _is_star(dialect) else b"\x04\xe0" + payload


def query_packet(dialect: str) -> bytes:
    return b"\x5a\xb0\x00\xa5" if _is_star(dialect) else b"\x00\xb0"


def clock_packet(local_time: datetime) -> bytes:
    """Encode the supplied local clock, with Dart's Monday=1 weekday convention."""
    return bytes(
        (
            0x5A,
            0x14,
            7,
            local_time.year - 2000,
            local_time.month,
            local_time.day,
            local_time.hour,
            local_time.minute,
            local_time.second,
            local_time.isoweekday(),
            0xA5,
        )
    )


def _enum(raw: int, values: tuple[str, ...], fallback: str = "none") -> str:
    return values[raw] if raw < len(values) else fallback


def _closest_color(rgb: int) -> int:
    # Squared Euclidean distance has the same ordering as the source's sqrt.
    return min(
        range(len(_PALETTE)),
        key=lambda i: sum(
            (((rgb >> shift) & 0xFF) - ((_PALETTE[i] >> shift) & 0xFF)) ** 2 for shift in (16, 8, 0)
        ),
    )


def _motor(data: bytes) -> dict[str, StateValue]:
    return {
        **{
            key: min(data[offset], 100)
            for key, offset in (
                ("back", 4),
                ("legs", 6),
                ("lumbar", 8),
                ("motor_part4", 10),
                ("motor_part5", 5),
                ("motor_part6", 7),
            )
        },
        "motor_stopped": data[17] == 0,
    }


def _normal_and_sonic(data: bytes) -> dict[str, StateValue]:
    head, foot = data[7] & 0xF, data[7] >> 4
    color = data[14] & 0xF
    direct = color > 7
    rgb = int.from_bytes(data[16:19], "big") if direct else _PALETTE[max(color - 1, 0)]
    sonic_head, sonic_foot = data[11] & 0xF, data[11] >> 4
    sonic_any = sonic_head > 0 or sonic_foot > 0
    return {
        "massage_time_raw": int.from_bytes(data[4:6], "big"),
        "massage_mode": data[6] & 0xF,
        "massage_head_level": max(head - 1, 0),
        "massage_foot_level": max(foot - 1, 0),
        "massage_active": head > 0 or foot > 0,
        "light_mode": data[15] >> 4,
        "light_brightness": data[14] >> 4,
        "light_on": color > 0,
        # Report direct RGB in the wire numbering the palette select uses
        # (0 = off, 1 = white): palette position p is wire index p + 1.
        "light_color_index": _closest_color(rgb) + 1 if direct else color,
        "light_rgb": rgb,
        "light_rgb_mode": int(direct),
        "sonic_head_level": sonic_head,
        "sonic_foot_level": sonic_foot,
        "sonic_active": sonic_head > 0 and sonic_foot > 0,
        "sonic_frequency": (30 if data[12] == 5 else 40 if data[12] == 9 else 50)
        if sonic_any
        else 0,
        "sonic_time_raw": int.from_bytes(data[9:11], "big") if sonic_any else 0,
        "sonic_mode": int((data[8] & 0xF) > 0),
        "sonic_massage_type": data[6] >> 4,
    }


def _main_alarm(data: bytes, star: bool) -> dict[str, StateValue]:
    updates: dict[str, StateValue] = {}
    for index, start in enumerate((4, 11) if star else (4,)):
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
        ((3, 4, 5, 6, 7, 8, 9, 11, 12, 13), (14, 15, 16, 17, 18, 19, 20, 21, 22, 24))
    ):
        repeat, preset, light, sonic, music, massage, duration, hour, minute, on = (
            data[i] for i in offsets
        )
        music_value: StateValue = (
            "random" if music == 0 else "none" if music == 99 else {"music": music}
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
            "isOn": on > 0,
        }
        updates[f"alarm_{index}"] = details["isOn"]
        updates[f"alarm_{index}_details"] = details
    return updates


def _eq(data: bytes) -> dict[str, StateValue]:
    updates: dict[str, StateValue] = {
        "usb_on": (data[11] & 2) == 2,
        "eq_low_frequency": (data[19] & 0xF) * (1 if data[18] & 1 else -1),
        "eq_high_frequency": (data[19] >> 4) * (1 if data[18] & 0x80 else -1),
        "eq_volume": data[20],
        "eq_preset": {1: "Pop", 2: "Classical", 3: "Jazz"}.get(data[21], "None"),
    }
    for index in range(8):
        magnitude = (data[14 + index // 2] >> (4 * (index % 2))) & 0xF
        updates[f"eq_band_{index}"] = magnitude * (1 if data[13] & (1 << index) else -1)
    return updates


def parse_notification(
    data: bytes,
    *,
    profile: str,
    dialect: str,
    previous: Mapping[str, StateValue] | None = None,
) -> dict[str, StateValue]:
    """Return only delivered fields, without mutating previous or inventing ACKs.

    Delta application preserves prior alarm slots and sonic fields, including on
    EQ's USB-only sonic update. Elevate only logs notifications in this artifact.
    No app debounce suppression is carried into Home Assistant.
    """
    star = _is_star(dialect)
    if profile not in ("cb25", "f23", "kneading", "elevate"):
        raise ValueError(f"Unknown AdjustableM5X5 profile: {profile}")
    if profile == "elevate" or len(data) < 2 or data[0] != 0xA5:
        return {}
    match data[1]:
        case 0x0D if len(data) >= 18:
            return _motor(data)
        case 0x0B if len(data) >= 20:
            return _normal_and_sonic(data)
        case 0x0C if profile == "cb25" and len(data) >= 17:
            return _main_alarm(data, star)
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
