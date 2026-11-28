"""AR Connect headboard records over the shared compact JSON carrier."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from .json_record import compact_json

DURATIONS: Final = (1, 2, 5, 10, 20, 30, 60, 120)
DAYS: Final = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
type RGBW = tuple[int, int, int, int]


def guid(token: str) -> str:
    return f"0000{token.lower()}-0000-1000-8000-00805f9b34fb"


def state(enabled: bool) -> bytes:
    return compact_json({"state": enabled})


def color(channels: RGBW) -> dict[str, object]:
    return dict(zip(("red", "green", "blue", "white"), channels, strict=True))


def live(channels: RGBW) -> bytes:
    return compact_json(color(channels))


def _round(value: float) -> int:
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def rgbw(rgb: tuple[float, float, float], tint: float, brightness: float) -> RGBW:
    """Actual app hue/tint/brightness conversion, never four independent levels."""
    if not 0.5 <= tint <= 1 or not 0 <= brightness <= 1 or min(rgb) < 0 or sum(rgb) <= 0:
        raise ValueError("Invalid headboard color")
    white = _round((tint - 0.5) / 0.5 * 255)
    scale = (255 - white) / sum(rgb)
    r, g, b = (_round(value * scale * brightness) for value in rgb)
    return r, g, b, _round(white * brightness)


HUE_PALETTE: Final = (
    (0.0, 0.0, 1.0),
    (122 / 255, 0.0, 1.0),
    (1.0, 0.0, 1.0),
    (1.0, 0.0, 0.0),
    (1.0, 122 / 255, 0.0),
    (1.0, 1.0, 0.0),
    (0.0, 1.0, 0.0),
)


def hue_rgb(hue: float) -> tuple[float, float, float]:
    """The shipped seven Color endpoints, not a guessed circular HSV wheel."""
    if not 0 <= hue <= 1:
        raise ValueError("Hue must be between zero and one")
    index = min(5, math.floor(hue / (1 / 6)))
    part = (hue - index * (1 / 6)) / (1 / 6)
    first, second = HUE_PALETTE[index], HUE_PALETTE[index + 1]
    values = [a + (b - a) * part for a, b in zip(first, second, strict=True)]
    return values[0], values[1], values[2]


def mood(repeat: bool, delay: int, colors: tuple[RGBW, ...]) -> bytes:
    if type(repeat) is not bool or delay not in DURATIONS or len(colors) != 5:
        raise ValueError("Mood requires five colors and a supported delay")
    return compact_json(
        {
            "repeat": repeat,
            "delay": delay,
            "colors": {str(i): color(c) for i, c in enumerate(colors, 1)},
        }
    )


def clock(now: datetime) -> bytes:
    return compact_json(
        {
            "seconds": now.second,
            "minutes": now.minute,
            "hours": now.hour,
            "date": now.day,
            "day": now.isoweekday() % 7,
            "month": now.month - 1,
            "year": now.year - 1900,
        }
    )


@dataclass(frozen=True, slots=True)
class Routine:
    enabled: bool
    mode: str
    hour: int
    minute: int
    duration: int
    track: str | None = None
    volume: int = 0
    weekdays: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "hour": self.hour,
            "minute": self.minute,
            "duration": self.duration,
            "track": self.track,
            "volume": self.volume,
            "recurrence": {day: day in self.weekdays for day in DAYS},
        }

    def validate(self) -> None:
        if (
            type(self.enabled) is not bool
            or self.mode not in ("wake", "sleep")
            or type(self.hour) is not int
            or not 0 <= self.hour < 24
            or type(self.minute) is not int
            or not 0 <= self.minute < 60
            or type(self.duration) is not int
            or self.duration not in DURATIONS
            or set(self.weekdays).difference(DAYS)
        ):
            raise ValueError("Invalid headboard routine")


def routine(value: Routine) -> bytes:
    value.validate()
    return compact_json(value.payload())


def remove(identity: int) -> bytes:
    return compact_json({"id": identity})


def object_record(data: bytes) -> dict[str, object] | None:
    text = data.decode("utf-8")
    if "error" in text:
        return None
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a headboard object")
    return {str(key): item for key, item in value.items()}


def integer(record: dict[str, object], key: str) -> int:
    value = record[key]
    if type(value) is not int:
        raise ValueError(f"Expected integer {key}")
    return value


def parse_live(data: bytes) -> RGBW | None:
    if len(data) < 5:
        return None
    text = data.decode("utf-8")
    if "error" in text:
        return None
    values: list[int] = []
    for token in text.split(","):
        token = token.strip()
        if re.fullmatch(r"[+-]?[0-9]+", token):
            values.append(int(token, 10))
        elif re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", token):
            values.append(int(token, 16))
    return (values[0], values[1], values[2], values[3]) if len(values) == 4 else None


def parse_routine(value: object) -> Routine:
    if not isinstance(value, dict):
        raise ValueError("Expected routine object")
    row: dict[str, object] = dict(value)
    enabled, mode, track, recurrence = (row[k] for k in ("enabled", "mode", "track", "recurrence"))
    if (
        type(enabled) is not bool
        or mode not in ("wake", "sleep")
        or track is not None
        and not isinstance(track, str)
        or not isinstance(recurrence, dict)
        or any(day not in DAYS or type(flag) is not bool for day, flag in recurrence.items())
    ):
        raise ValueError("Invalid routine state")
    return Routine(
        enabled,
        str(mode),
        integer(row, "hour"),
        integer(row, "minute"),
        integer(row, "duration"),
        track,
        integer(row, "volume"),
        tuple(day for day in DAYS if recurrence.get(day) is True),
    )


@dataclass(slots=True)
class RoutineFramer:
    """Source event precedence and byte-count framing, bounded by a host memory limit."""

    length: int | None = None
    buffer: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> tuple[str, object] | None:
        text = data.decode("utf-8")
        if "error" in text:
            return None
        if "suppid" in text or '"createid"' in text:
            row = object_record(data)
            assert row is not None
            key = "suppid" if "suppid" in text else "createid"
            return ("deleted" if key == "suppid" else "created", str(row[key]))
        if "length" in text:
            row = object_record(data)
            assert row is not None
            value = row.get("length")
            self.length = value if type(value) is int else None
            if self.length is not None and not 0 <= self.length <= 65536:
                self.clear()
                raise ValueError("Routine list too large")
        else:
            self.buffer.extend(data)
        if len(self.buffer) > 65536:
            self.clear()
            raise ValueError("Routine list too large")
        if self.length is None or len(self.buffer) < self.length:
            return None
        try:
            rows = object_record(bytes(self.buffer))
            if rows is None:
                return None
            return "list", {key: parse_routine(value) for key, value in rows.items()}
        finally:
            self.clear()

    def clear(self) -> None:
        self.length = None
        self.buffer.clear()
