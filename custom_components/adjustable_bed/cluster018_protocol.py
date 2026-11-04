"""Direct BLE primitives recovered from the five accepted cluster-018 apps.

These are the older resource-driven apps, not RMControl 21.3.7. Model data
selects operands and gestures; a transport match never selects a product.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

Wire = Literal["RAW", "FRAMED"]


def worker_interval(name: str | None, wire: Wire) -> int:
    """The source startup name guards, without guessing after substring failure."""
    if name is None:
        if wire == "RAW":
            raise ValueError("The raw app sender requires a Bluetooth device name")
        return 110
    if len(name.strip()) < 4:
        raise ValueError("The app sender requires at least four device-name characters")
    prefix = name.strip().upper()[:4]
    return 110 if prefix in ("TWRM", "MLRM") else 150


def decode_resource(value: str | None) -> bytes | None:
    """The shipped decoder, including its malformed-nibble truncation."""
    if not value or len(value) % 2:
        return None
    digits = "0123456789ABCDEF"
    value = value.upper()
    return bytes(
        ((digits.find(value[i]) << 4) | digits.find(value[i + 1])) & 255
        for i in range(0, len(value), 2)
    )


def direct(opcode: int, first: int = 0, second: int = 0) -> bytes:
    """Four source byte fields followed by their additive checksum."""
    body = bytes((0x6E, opcode & 255, first & 255, second & 255))
    return body + bytes((sum(body) & 255,))


def control(payload: bytes, wire: Wire, mode: int = 0) -> bytes:
    """RAW copies every byte; FRAMED consumes only the first operand."""
    return payload if wire == "RAW" else direct(1, mode, payload[0])


def release(wire: Wire, mode: int = 0) -> bytes:
    return control(b"\x6e", wire, mode)


def rgb(red: int, green: int, blue: int) -> bytes:
    return direct(0x0C, 255, red) + direct(0x0D, green, blue)


def lamp_timer(minutes: int, *, save: bool = False) -> bytes:
    """Slider uses seconds/ffff at zero; Save uses unscaled minutes."""
    if not 0 <= minutes <= 15:
        raise ValueError("Lamp timer must be between 0 and 15 minutes")
    value = minutes if save else minutes * 60 if minutes else 65535
    return direct(0x0B, value >> 8, value)


def alarm(delay_minutes: int, command: int) -> tuple[bytes, bytes]:
    if not 0 <= delay_minutes <= 1440:
        raise ValueError("Alarm delay must be between 0 and 1440 minutes")
    return direct(5, delay_minutes, 0), direct(6, delay_minutes >> 8, command)


def alarm_delay(now_minutes: int, target_minutes: int | None) -> int:
    return 1440 if target_minutes is None else (target_minutes - now_minutes) % 1440 or 1440


def aroma(opcode: int, value: int) -> bytes:
    """Source int32 byte-pair sums, including values outside the UI domain."""
    if opcode not in (0x1B, 0x1C, 0x1D):
        raise ValueError("Unknown aroma setting")
    parts = (value & 0xFFFFFFFF).to_bytes(4, "big")
    return direct(opcode, parts[0] + parts[1], parts[2] + parts[3])


def massage_timer(layout: str, progress: int) -> bytes:
    if layout not in ("D1RM", "D9RM") or not 0 <= progress <= 5:
        raise ValueError("Massage slider is unavailable")
    code = {0: 0x5E if layout == "D1RM" else 0x8B, 2: 0x5F, 3: 0x63, 5: 0x61}.get(
        progress, progress
    )
    return direct(1, 0, code)


def float32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def rounded(value: float) -> float:
    """BigDecimal(double-promoted binary32), scale 1, HALF_EVEN, floatValue."""
    return float32(float(Decimal(float32(value)).quantize(Decimal("0.1"), ROUND_HALF_EVEN)))


def _java_int(value: float) -> int:
    if value != value:
        return 0
    return min(2147483647, max(-2147483648, int(value)))


def desk_target(display_value: float) -> bytes:
    value = _java_int(float32(float32(display_value) * 10.0))
    high = abs(value) // 100 * (-1 if value < 0 else 1)
    return direct(0x88, high, value - high * 100)


def old_height(first: int, second: int) -> tuple[float, float]:
    value = first * 128 + second
    cm = rounded(
        float(value)
        if value <= 130
        else float32(float32(value) * float32(2.54))
        if value < 600
        else float32(float32(value) / 10.0)
    )
    return cm, rounded(float32(cm / float32(2.54)))


def new_height(unit: int, first: int, second: int) -> tuple[float, float]:
    value = first * 100 + second
    if unit == 0:
        cm = rounded(float32(float32(value) / 10.0))
        return cm, rounded(float32(cm / float32(2.54)))
    inches = rounded(float(value))
    return rounded(float32(float32(float32(2.54) * inches) / 10.0)), inches


@dataclass(frozen=True, slots=True)
class Emission:
    """One worker emission and its delay inside the current iteration."""

    delay_ms: int
    payload: bytes | None


@dataclass(slots=True)
class Worker:
    """Persistent counter/latch semantics, independent of radio scheduling."""

    mode: int = -1
    payload: bytes | None = None
    count: int = 20
    counter: int = 0
    fired: bool = False
    tick_ms: int = 150
    total_ms: int = 3000

    def set_count(self, milliseconds: int) -> None:
        self.count = int(milliseconds / self.tick_ms)

    def set_interval(self, milliseconds: int) -> None:
        self.tick_ms = milliseconds
        self.set_count(self.total_ms)

    def tick(self) -> tuple[Emission, ...]:
        mode = self.mode
        if mode == -1:
            return ()
        if mode == 0:
            self.mode = -1
            self.counter = 0
            return (Emission(50, b"\x6e"),)
        if mode == 1:
            return (Emission(0, self.payload),)
        if mode == 3:
            if self.counter < self.count:
                self.counter += 1
                return ()
            self.mode = -1
            self.fired = True
            return (Emission(0, self.payload),)
        if mode in (2, 4, 5):
            self.mode = -1
            result = () if mode == 4 and self.fired else (Emission(0, self.payload),)
            if mode in (2, 4):
                result += (Emission(150, b"\x6e"),)
            if mode == 4:
                self.counter = 0
                self.fired = False
            return result
        return ()

    def outside_cancel(self) -> None:
        if self.mode == 1:
            self.mode = 0

    def cancel(self) -> None:
        """Abandon an HA gesture without retaining a pending save or its latch."""
        self.mode = -1
        self.payload = None
        self.counter = 0
        self.fired = False
