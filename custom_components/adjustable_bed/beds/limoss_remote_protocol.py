"""Limoss Remote 7.1.8 app state: capability replies and the process-wide sequence.

The rendered tables live in ``profiles/limoss.py`` and the frame in ``codec/limoss.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Product = Literal["bed", "chair"]


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
