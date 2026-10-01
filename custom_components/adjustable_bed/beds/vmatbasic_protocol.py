"""Pure V-MAT Basic app packet construction and diagnostic decoding.

Values are derived from com.vibradorm.vmatbasic 2.4.3 (14). No hardware
acknowledgement, model inference or legacy Vibradorm packet fallback is implied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

PROFILES: Final = ("basic", "cbi", "xtbox")
VENDOR_SUFFIX: Final = "-9f03-0de5-96c5-b8f4f3081186"
CONTROL_SERVICE: Final = "00001525" + VENDOR_SUFFIX
STATUS_SERVICE: Final = "00001527" + VENDOR_SUFFIX
GAP_SERVICE: Final = "00001800-0000-1000-8000-00805f9b34fb"
INFO_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MOTOR_CHAR: Final = "00001526" + VENDOR_SUFFIX
FLOOR_CHAR: Final = "00001529" + VENDOR_SUFFIX
XT_CHAR: Final = "00001550" + VENDOR_SUFFIX
TEMPERATURE_CHAR: Final = "00001532" + VENDOR_SUFFIX
ED_CHAR: Final = "00001531" + VENDOR_SUFFIX
NAME_CHAR: Final = "00002a00-0000-1000-8000-00805f9b34fb"
MODEL_CHAR: Final = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_CHAR: Final = "00002a26-0000-1000-8000-00805f9b34fb"
REQUIRED_SERVICES: Final = (CONTROL_SERVICE, STATUS_SERVICE, GAP_SERVICE)
READ_ROLES: Final = (
    ("model", INFO_SERVICE, MODEL_CHAR),
    ("temperature", STATUS_SERVICE, TEMPERATURE_CHAR),
    ("floor", CONTROL_SERVICE, FLOOR_CHAR),
    ("firmware", INFO_SERVICE, FIRMWARE_CHAR),
    ("ed", STATUS_SERVICE, ED_CHAR),
)
MOTOR_ACTIONS: Final = {
    "all_up": 0x10,
    "all_down": 0x00,
    "back_up": 0x0B,
    "back_down": 0x0A,
    "legs_up": 0x09,
    "legs_down": 0x08,
}
MASSAGE_ACTIONS: Final = {
    "back": 0x2C,
    "legs": 0x2D,
    "off": 0x34,
    "program_1": 0x31,
    "program_2": 0x28,
    "program_3": 0x29,
}
PALETTE: Final = (
    0xFFA4C400,
    0xFF60A917,
    0xFF008A00,
    0xFF00ABA9,
    0xFF1BA1E2,
    0xFF0050EF,
    0xFF6A00FF,
    0xFFAA00FF,
    0xFFF472D0,
    0xFFD80073,
    0xFFA20025,
    0xFFE51400,
    0xFFFA6800,
    0xFFF0A30A,
    0xFFE3C800,
    0xFF825A2C,
    0xFF6D8764,
    0xFF647687,
    0xFF76708A,
    0xFFFFFFFF,
)
PALETTE_OPTIONS: Final = tuple(f"col{index}" for index in range(1, 21))


def integer(value: object, minimum: int, maximum: int) -> int:
    """Validate the app's public UI domain before constructing a packet."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("A whole number is required")
    if not math.isfinite(value) or int(value) != value or not minimum <= value <= maximum:
        raise ValueError(f"Expected a whole number from {minimum} to {maximum}")
    return int(value)


def floor(level: int, minutes: int) -> bytes:
    """Raw CBI builder; public controls validate their narrower UI bounds."""
    return bytes((level & 255, (minutes & 0xFF00) >> 8, minutes & 255))


def xt_floor(level: int, minutes: int) -> bytes:
    """Raw XT builder, retaining the shipped upper clamp and byte conversion."""
    return bytes((0, 0x11, min(level, 6) & 255, min(minutes, 255) & 255))


def rgb(color: int) -> bytes:
    return bytes((0, 0x77, 1, 0, (color >> 16) & 255, (color >> 8) & 255, color & 255))


def effect(number: int) -> bytes:
    return bytes((0, 0x77, 8, number & 255))


def speed(progress: int) -> bytes:
    return bytes((0, 0x77, 9, (progress + 1) & 255))


def color_action(color: int, brightness: int) -> bytes:
    """Use the app's double-precision HSV conversion and integer truncation.

    Scaling RGB bytes directly changes several shipped palette outputs.
    """
    red, green, blue = (((color >> shift) & 255) / 255.0 for shift in (16, 8, 0))
    maximum = max(red, max(green, blue))
    delta = maximum - min(red, min(green, blue))
    hue = saturation = 0.0
    if delta > 0:
        if maximum == red:
            hue = (green - blue) / delta
            if green < blue:
                hue += 6.0
        elif maximum == green:
            hue = 2.0 + (blue - red) / delta
        else:
            hue = 4.0 + (red - green) / delta
        hue *= 60.0
        saturation = delta / maximum
    value = (maximum * brightness) / 100.0
    chroma = saturation * value
    offset = value - chroma
    sector = (hue - 360.0 * math.floor(hue / 360.0)) / 60.0
    intermediate = (1.0 - abs((sector - 2.0 * math.floor(sector / 2.0)) - 1.0)) * chroma
    components = (
        (chroma + offset, intermediate + offset, offset),
        (intermediate + offset, chroma + offset, offset),
        (offset, chroma + offset, intermediate + offset),
        (offset, intermediate + offset, chroma + offset),
        (intermediate + offset, offset, chroma + offset),
        (chroma + offset, offset, intermediate + offset),
    )[int(sector)]
    red_byte, green_byte, blue_byte = (max(0, min(255, int(c * 255.0))) for c in components)
    return rgb((red_byte << 16) + (green_byte << 8) + blue_byte - 16777216)


def rename(name: str) -> bytes:
    name = name.strip("".join(chr(value) for value in range(33)))
    if len(name.encode("utf-16-le")) // 2 > 10:
        raise ValueError("Name must contain at most ten UTF-16 units after trimming")
    return name.encode("utf-8")


@dataclass(frozen=True, slots=True)
class FloorStatus:
    level: int
    timer_minutes: int

    @property
    def display_percent(self) -> float:
        return (self.level * 100) / 255.0


def light_status(data: bytes) -> FloorStatus:
    if len(data) < 3:
        raise ValueError("Floor status requires three bytes")
    return FloorStatus(data[0], (data[1] << 8) + data[2])


def temperature(data: bytes) -> float:
    if len(data) < 4:
        raise ValueError("Temperature requires four bytes")
    return int.from_bytes(data[:4], "little", signed=True) / 4.0 - 7.0


def motor_status(data: bytes) -> bool:
    if not data:
        raise ValueError("ED status requires one byte")
    return bool(data[0] & 1)


def decode_string(data: bytes) -> str:
    """Android UTF-8 replacement, preserving whitespace and embedded zeros."""
    parts: list[str] = []
    offset = 0
    while offset < len(data):
        remaining = data[offset:]
        try:
            parts.append(remaining.decode("utf-8"))
            break
        except UnicodeDecodeError as error:
            parts.append(remaining[: error.start].decode("utf-8"))
            consumed = error.end
            start = error.start
            if (
                remaining[start] == 0xED
                and start + 1 < len(remaining)
                and 0xA0 <= remaining[start + 1] <= 0xBF
            ):
                consumed = start + 2
                if consumed < len(remaining) and 0x80 <= remaining[consumed] <= 0xBF:
                    consumed += 1
            parts.append("\ufffd")
            offset += consumed
    return "".join(parts)


def manufacturer_payload_matches(payload: bytes) -> bool:
    """Conditional match for HA data with its two company bytes removed."""
    return (
        len(payload) >= 6
        and payload[:2] == b"\xba\xbe"
        and payload[2] & 15 == 1
        and payload[3] & 15 == 1
    )


def first_manufacturer_matches(advertisement: bytes) -> bool:
    """Preserve first-manufacturer precedence while rejecting malformed AD."""
    offset = 0
    while offset < len(advertisement):
        length = advertisement[offset]
        if length == 0:
            return False
        end = offset + 1 + length
        if length < 1 or end > len(advertisement):
            return False
        if advertisement[offset + 1] == 0xFF:
            # The source requires eight manufacturer bytes, including company.
            return manufacturer_payload_matches(advertisement[offset + 4 : end])
        offset = end
    return False
