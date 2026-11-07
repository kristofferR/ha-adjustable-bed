"""Notification fields shared by the M5X5 and M1X12 StarCode parsers.

The two apps decode their motor, alarm, EQ and kneading frames alike. Where their
artifacts differ (field offsets, swapped nibbles), the caller passes its layout.
"""

from __future__ import annotations

from typing import Final

type StateValue = str | int | float | bool | None | list[StateValue] | dict[str, StateValue]

PALETTE: Final = (0xFFFFFF, 0xFF0000, 0xFFA500, 0xFFFF00, 0x00FF00, 0x0000FF, 0x800080)
_WAKE: Final = ("none", "zg", "lounge", "tv", "antisnore", "m1", "m2", "light", "massage", "flat")
_PRESET: Final = ("flat", "zg", "lounge", "tv", "antisnore", "m1", "m2")
_LIGHT: Final = ("off", "onOrWhite", "red", "orange", "yellow", "green", "blue", "purple")
_SONIC: Final = ("none", "normal1", "normal2", "normal3", "sonic1", "sonic2", "sonic3")
_MASSAGE: Final = ("off", "intensity1", "intensity2", "intensity3")
_DURATION: Final = ("duration10Min", "duration10Min", "duration20Min", "duration30Min")
# Motor position bytes, in the order of the caller's six field names.
_MOTOR_OFFSETS: Final = (4, 6, 8, 10, 5, 7)


def _enum(raw: int, values: tuple[str, ...], fallback: str = "none") -> str:
    return values[raw] if raw < len(values) else fallback


def closest_color(rgb: int) -> int:
    """Return the palette position nearest ``rgb``, first on ties."""
    # Squared Euclidean distance has the same ordering as the source's sqrt.
    return min(
        range(len(PALETTE)),
        key=lambda index: sum(
            (((rgb >> shift) & 0xFF) - ((PALETTE[index] >> shift) & 0xFF)) ** 2
            for shift in (16, 8, 0)
        ),
    )


def motor(data: bytes, names: tuple[str, str, str, str, str, str]) -> dict[str, StateValue]:
    """Decode a motor frame (0x0D, at least 18 bytes) into the caller's field names."""
    return {
        **{
            name: min(data[offset], 100) for name, offset in zip(names, _MOTOR_OFFSETS, strict=True)
        },
        "motor_stopped": data[17] == 0,
    }


def basic_alarm(data: bytes, starts: tuple[int, ...]) -> dict[str, StateValue]:
    """Decode the basic alarm slots beginning at ``starts`` (each six bytes)."""
    updates: dict[str, StateValue] = {}
    for index, start in enumerate(starts):
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


type AlarmOffsets = tuple[int, int, int, int, int, int, int, int, int, int]


def advanced_alarm(data: bytes, slots: tuple[AlarmOffsets, ...]) -> dict[str, StateValue]:
    """Decode advanced alarm slots.

    Each slot lists the offsets of repeat, preset, light, sonic, music, massage,
    duration, hour, minute and on.
    """
    updates: dict[str, StateValue] = {}
    for index, offsets in enumerate(slots):
        repeat, preset, light, sonic, music, massage, duration, hour, minute, on = (
            data[offset] for offset in offsets
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


def eq(data: bytes) -> dict[str, StateValue]:
    """Decode an EQ frame (0x0E, at least 22 bytes)."""
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


def kneading(data: bytes) -> dict[str, StateValue]:
    """Decode a kneading frame (0x0F, at least 8 bytes)."""
    return {
        "kneading_on": data[4] == 1,
        "kneading_demo": data[3] == 1,
        "kneading_mode": min(data[5], 2),
        "kneading_time_raw": int.from_bytes(data[6:8], "big"),
    }
