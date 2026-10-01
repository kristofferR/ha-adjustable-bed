"""Exact rendered app tables from accepted com.limoss.limossremote 7.1.8."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .limoss import LimossController

Product = Literal["bed", "chair"]

# Hidden cKey4 declarations and null cells are intentionally not actions.
LAYOUTS: dict[str, tuple[int | None, ...]] = {
    "cKey2": (0x12, 0x13),
    "cKey4": (0x12, 0x13, 0x22, 0x23),
    "cKey6": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
    "cKey8": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x42, 0x43),
    "cKey8_customAlpha": (0x13, 0x12, 0x22, 0x23, 0x32, 0x33, 0x43, 0x42),
    "gKey10": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55),
    "gKey10BothUnderBedLightVibrate": (
        0x12,
        0x13,
        0x64,
        0x22,
        0x23,
        0x65,
        0x50,
        0x51,
        0x70,
        0x52,
        0x53,
        None,
        0x54,
        0x55,
        None,
    ),
    "gKey10UnderBedLight": (
        0x12,
        0x13,
        0x70,
        0x22,
        0x23,
        None,
        0x50,
        0x51,
        None,
        0x52,
        0x53,
        None,
        0x54,
        0x55,
        None,
    ),
    "gKey10Vibrate": (
        0x12,
        0x13,
        0x60,
        0x22,
        0x23,
        0x61,
        0x50,
        0x51,
        0x62,
        0x52,
        0x53,
        0x63,
        0x54,
        0x55,
        None,
    ),
    "gKey12": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53, 0x32, 0x33, 0x54, 0x55),
    "gKey12BothUnderBedLightVibrate": (
        0x12,
        0x13,
        0x64,
        0x22,
        0x23,
        0x65,
        0x50,
        0x51,
        0x70,
        0x52,
        0x53,
        None,
        0x32,
        0x33,
        None,
        0x54,
        0x55,
        None,
    ),
    "gKey12UnderBedLight": (
        0x12,
        0x13,
        0x70,
        0x22,
        0x23,
        None,
        0x50,
        0x51,
        None,
        0x52,
        0x53,
        None,
        0x32,
        0x33,
        None,
        0x54,
        0x55,
        None,
    ),
    "gKey12Vibrate": (
        0x12,
        0x13,
        0x60,
        0x22,
        0x23,
        0x61,
        0x50,
        0x51,
        0x62,
        0x52,
        0x53,
        0x63,
        0x32,
        0x33,
        None,
        0x54,
        0x55,
        None,
    ),
    "gKey2": (0x12, 0x13),
    "gKey2BothUnderBedLightVibrate": (0x12, 0x13, 0x64, 0x65, 0x70, None),
    "gKey2UnderBedLight": (0x12, 0x13, 0x70, None),
    "gKey2Vibrate": (0x12, 0x13, 0x60, 0x61, 0x62, 0x63),
    "gKey4": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
    "gKey4BothUnderBedLightVibrate": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51, 0x64, 0x65),
    "gKey4UnderBedLight": (0x12, 0x13, 0x22, 0x23, 0x70, 0x51),
    "gKey4Vibrate": (0x12, 0x13, 0x22, 0x23, 0x60, 0x61, 0x62, 0x63),
    "gKey6": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x54, 0x55),
    "gKey6BothUnderBedLightVibrate": (
        0x12,
        0x13,
        0x64,
        0x22,
        0x23,
        0x65,
        0x32,
        0x33,
        0x70,
        0x54,
        0x55,
        None,
    ),
    "gKey6UnderBedLight": (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x70, 0x54),
    "gKey6Vibrate": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x32, 0x33, 0x62, 0x54, 0x55, 0x63),
    "gKey8": (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
    "gKey8BothUnderBedLightVibrate": (
        0x12,
        0x13,
        0x64,
        0x22,
        0x23,
        0x65,
        0x50,
        0x51,
        0x70,
        0x52,
        0x53,
        None,
    ),
    "gKey8UnderBedLight": (0x12, 0x13, 0x70, 0x22, 0x23, None, 0x50, 0x51, None, 0x52, 0x53, None),
    "gKey8Vibrate": (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62, 0x52, 0x53, 0x63),
}

THEMES = (
    "bed_legacy",
    "bed_hc319",
    "bed_clear",
    "bed_red",
    "chairs_legacy",
    "chairs_hc314",
    "chairs_hc338",
    "chairs_clear",
)

# Labels describe the app channel, not an inferred physical actuator.
HELD_COMMANDS: dict[str, int] = {
    "motor_1_up": 0x12,
    "motor_1_down": 0x13,
    "motor_2_up": 0x22,
    "motor_2_down": 0x23,
    "motor_3_up": 0x32,
    "motor_3_down": 0x33,
    "motor_4_up": 0x42,
    "motor_4_down": 0x43,
    "combined_up": 0x50,
    "combined_down": 0x51,
    "lift_up": 0x52,
    "lift_down": 0x53,
    "shift_up": 0x54,
    "shift_down": 0x55,
    "massage_back_plus": 0x60,
    "massage_back_minus": 0x61,
    "massage_foot_plus": 0x62,
    "massage_foot_minus": 0x63,
    "massage_both_plus": 0x64,
    "massage_both_minus": 0x65,
    "light": 0x70,
}


def integer(value: object, minimum: int, maximum: int, label: str) -> int:
    """Reject booleans, fractional numbers and out-of-domain raw values."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


@dataclass(frozen=True, slots=True)
class LimossRemoteCapabilities:
    """The unsigned reply02 bytes, with no guessed hardware capability."""

    key_count: int
    system: int
    vibration: int
    configuration: int
    memory_count: int

    def __post_init__(self) -> None:
        for field in (self.key_count, self.system, self.vibration):
            integer(field, 0, 255, "Capability byte")
        integer(self.configuration, 0, 15, "Configuration nibble")
        integer(self.memory_count, 0, 15, "Memory nibble")

    @classmethod
    def from_parameters(cls, raw: bytes) -> LimossRemoteCapabilities:
        if len(raw) != 4:
            raise ValueError("Capability reply needs four bytes")
        return cls(raw[0], raw[1], raw[2], raw[3] >> 4, raw[3] & 15)

    @property
    def reported_product(self) -> Product | None:
        if 0x10 <= self.system <= 0x1F:
            return "bed"
        if 0x20 <= self.system <= 0x2F:
            return "chair"
        return None

    def product(self, selected: Product | None) -> Product:
        result = self.reported_product or selected
        if result is None:
            raise ValueError("Unknown system byte: explicitly select bed or chair")
        return result

    def supported_keys(self, selected: Product | None) -> int:
        supported = (2, 4, 6, 8, 10, 12) if self.product(selected) == "bed" else (2, 4, 6, 8)
        return self.key_count if self.key_count in supported else 8

    def effective_motor_count(self, selected: Product | None) -> int:
        return (self.system & 15) or self.supported_keys(selected) // 2

    def layout(self, selected: Product | None, light: bool, massage: bool) -> str:
        count = self.supported_keys(selected)
        if self.product(selected) == "chair":
            return "cKey8_customAlpha" if count == 8 and self.configuration == 1 else f"cKey{count}"
        suffix = (
            "BothUnderBedLightVibrate"
            if light and massage
            else "UnderBedLight"
            if light
            else "Vibrate"
            if massage
            else ""
        )
        return f"gKey{count}{suffix}"


@dataclass(slots=True)
class LimossRemoteSequence:
    """App-global Java int; construction consumes it before attempted delivery."""

    value: int = 0

    def take(self) -> int:
        result = self.value & 255
        self.value = (self.value + 1) & 0xFFFFFFFF
        if self.value >= 0x80000000:
            self.value -= 0x100000000
        return result


APP_SEQUENCE = LimossRemoteSequence()


def format_command(payload: bytes, counter: int) -> bytes:
    """Only the proven pure cipher is reused from the legacy implementation."""
    if len(payload) != 5:
        raise ValueError("Logical commands need exactly five bytes")
    inner = bytes((0xAA,)) + payload + bytes((counter & 255,))
    inner += bytes((sum(inner) & 255,))
    packet = bytes((0xDD,)) + LimossController._tea_encrypt(inner)
    return packet + bytes((sum(packet) & 255,))


class LimossRemoteParser:
    """Per-target bounded stream; native checksums/header are not validated."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def clear(self) -> None:
        self.buffer.clear()

    def feed(self, raw: bytes) -> list[bytes]:
        self.buffer.extend(raw)
        result: list[bytes] = []
        while len(self.buffer) >= 10:
            marker = self.buffer.find(0xDD)
            if marker < 0:
                self.buffer.clear()
                break
            del self.buffer[:marker]
            if len(self.buffer) < 10:
                break
            result.append(LimossController._tea_decrypt(bytes(self.buffer[1:9]))[1:6])
            del self.buffer[:10]
        # At most one incomplete native frame remains; hostile noise is bounded.
        return result


def version_string(parameters: bytes) -> str:
    if len(parameters) != 4:
        raise ValueError("Version reply needs four bytes")
    a, b, c, d = (value if value < 128 else value - 256 for value in parameters)
    return (
        (str(a) if a >= 0 else "")
        + str(b)
        + "."
        + (str(c) if c >= 0 else "")
        + (str(d) if d >= 0 else "")
    )
