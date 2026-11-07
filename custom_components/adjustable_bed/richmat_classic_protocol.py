"""Direct BLE primitives recovered from the five accepted cluster-018 apps.

These are the older resource-driven apps, not RMControl 21.3.7. Model data
selects operands and gestures; a transport match never selects a product.
Every frame is built by the Richmat 6E codec (``codec/richmat.py``); this module
names the classic apps' own opcodes and their source quirks.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, Literal

from .codec import richmat as codec

Wire = Literal["RAW", "FRAMED"]

# Source timing, in milliseconds.
TICK_MS: Final = 150
"""The ordinary worker tick."""
FAST_TICK_MS: Final = 110
"""The worker tick for TWRM and MLRM names, and a FRAMED link without a name."""
FAST_TICK_NAMES: Final = ("TWRM", "MLRM")
HELD_RELEASE_MS: Final = 50
"""Release after a held control ends."""
TAP_RELEASE_MS: Final = 150
"""Release after a once or short press."""
LONG_PRESS_MS: Final = 3000
"""The default long-press threshold; a node can set its own."""
STARTUP_MS: Final = 300
"""FRAMED startup frame after notifications start."""
ALARM_SPACING_MS: Final = 300
QUERY_SPACING_MS: Final = 500
SETTINGS_SPACING_MS: Final = 150
"""Aroma writes and the RGB busy interval."""
DESK_REFRESH_MS: Final = 200


def worker_interval(name: str | None, wire: Wire) -> int:
    """The source startup name guards, without guessing after substring failure."""
    if name is None:
        if wire == "RAW":
            raise ValueError("The raw app sender requires a Bluetooth device name")
        return FAST_TICK_MS
    if len(name.strip()) < 4:
        raise ValueError("The app sender requires at least four device-name characters")
    prefix = name.strip().upper()[:4]
    return FAST_TICK_MS if prefix in FAST_TICK_NAMES else TICK_MS


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
    """``6E opcode first second sum8``: the settings frames, independent of the wire."""
    return codec.frame(codec.BED, opcode, first, second)


RELEASE: Final = bytes((codec.STOP,))
"""The release operand, which RAW sends bare and FRAMED wraps in the current mode."""
INITIALIZE: Final = direct(0x02, 0x01)
DESK_QUERY: Final = direct(0x94)
ALARM_QUERY: Final = direct(0x08, 0x01, 0x01)
LAMP_QUERY: Final = direct(0x0A, 0x00, 0x01)
AROMA_QUERY: Final = direct(0x1A)
DESK_CONFIRM: Final = direct(0x95)
"""Desk fourth button, and the confirmation of a newly reported desk error."""
MASSAGE_POPUP: Final = {"15": 0x5F, "30": 0x63, "45": 0x61, "toggle": 0x5E}


def control(payload: bytes, wire: Wire, mode: int = 0) -> bytes:
    """RAW copies every resource byte; FRAMED consumes only the first operand."""
    return payload if wire == "RAW" else codec.command(payload[0], mode)


def release(wire: Wire, mode: int = 0) -> bytes:
    return control(RELEASE, wire, mode)


def rgb(red: int, green: int, blue: int) -> bytes:
    return codec.rgb(red, green, blue)


def lamp_timer(minutes: int, *, save: bool = False) -> bytes:
    """Slider uses seconds/ffff at zero; Save uses unscaled minutes."""
    if not 0 <= minutes <= 15:
        raise ValueError("Lamp timer must be between 0 and 15 minutes")
    value = minutes if save else minutes * 60 if minutes else 65535
    return codec.light_timer(value >> 8, value)


def alarm(delay_minutes: int, command: int) -> tuple[bytes, bytes]:
    if not 0 <= delay_minutes <= 1440:
        raise ValueError("Alarm delay must be between 0 and 1440 minutes")
    return codec.countdown(delay_minutes, command)


def massage_popup(choice: str) -> bytes:
    """The massage popup's 15, 30 and 45 minute timers and its toggle."""
    return codec.command(MASSAGE_POPUP[choice])


def desk_unit(inches: bool) -> bytes:
    return direct(0x91, 0, int(inches))


def desk_button(slot: int) -> bytes:
    """Desk recall buttons 1 to 3; the fourth button is :data:`DESK_CONFIRM`."""
    return DESK_CONFIRM if slot == 4 else direct(0x96, 0, (4, 8, 16)[slot - 1])


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
    return codec.command(code)


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
    tick_ms: int = TICK_MS
    total_ms: int = LONG_PRESS_MS

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
            return (Emission(HELD_RELEASE_MS, RELEASE),)
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
                result += (Emission(TAP_RELEASE_MS, RELEASE),)
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
