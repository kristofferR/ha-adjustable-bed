"""Paramount P1 frames, from Bed Operation 3.0.4 (300042)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import reduce
from operator import xor
from typing import Final

SERVICE_UUID: Final = "32112022-0177-49cf-a554-254de334cae0"
CONNECT_WAIT_UUID: Final = "32112022-0177-49cf-a554-254de334cae2"
REGISTRATION_UUID: Final = "32112022-0177-49cf-a554-254de334cae3"
WRITE_UUID: Final = "34670381-0ca7-47bc-abe3-e1e0dbf25240"
NOTIFY_UUID: Final = "34670381-0ca7-47bc-abe3-e1e0dbf25241"
SERIAL_UUID: Final = "4e87d8b0-a810-44da-bd51-e4f983ed88a0"
OPERATIONS: Final = {
    "neutral": 0,
    "concurrent_push": 1,
    "head_up": 2,
    "head_down": 3,
    "legs_up": 4,
    "legs_down": 5,
    "height_up": 6,
    "height_down": 7,
    "gearing_up": 8,
    "gearing_down": 9,
}
LAYOUTS: Final = {
    31: "BUTTON10",
    29: "BUTTON8",
    21: "BUTTON6",
    1: "BUTTON2_HEAD",
    4: "BUTTON2_HEIGHT",
}
CAPABILITIES: Final = {"head": 1, "legs": 2, "height": 4, "gearing": 8, "memory": 16}
SETTING_BITS: Final = {"call_prohibition": (0, 0x20), "switch_prohibition": (3, 4), "speed": (3, 1)}
type Posture = tuple[int, int, int, int]


def frame(command: int, payload: bytes = b"") -> bytes:
    """Encode the complete XOR frame, including header and payload length."""
    body = bytes((0x40, command, len(payload))) + payload
    return body + bytes((reduce(xor, body, 0),))


def control(operation: int, posture: Posture = (0, 0, 0, 0)) -> bytes:
    """Encode movement, neutral or memory recall (0x16/0x17)."""
    return frame(0x84, bytes(value & 255 for value in (operation, *posture)))


@dataclass(frozen=True, slots=True)
class Settings:
    """All writable bytes must be read before any one setting is changed."""

    flags: Posture
    memory1: Posture
    memory2: Posture

    def encode(self) -> bytes:
        return frame(
            0x85, bytes(value & 255 for value in (*self.flags, *self.memory1, *self.memory2))
        )

    def setting(self, name: str, enabled: bool) -> Settings:
        index, mask = SETTING_BITS[name]
        flags = list(self.flags)
        flags[index] = (flags[index] & ~mask) | (mask if enabled else 0)
        return replace(self, flags=posture(bytes(flags)))

    def save(self, slot: int, value: Posture) -> Settings:
        if slot not in (1, 2):
            raise ValueError("Paramount has two memory slots")
        return replace(self, **{"memory1" if slot == 1 else "memory2": value})


def posture(data: bytes) -> Posture:
    """Read four unsigned position/setting bytes."""
    if len(data) != 4:
        raise ValueError("Expected four bytes")
    return data[0], data[1], data[2], data[3]


@dataclass(frozen=True, slots=True)
class Reply:
    opcode: int
    payload: bytes

    @property
    def settings(self) -> Settings:
        if self.opcode != 3:
            raise ValueError("Not a settings reply")
        return Settings(
            posture(self.payload[:4]), posture(self.payload[4:8]), posture(self.payload[8:12])
        )

    @property
    def rssi(self) -> int | None:
        value = self.payload[5]
        return (value & 127) - 100 if value & 128 else None


def parse(data: bytes) -> Reply | None:
    """Accept complete known responses. No received checksum contract is inferred.

    The app indexes blindly; HA drops truncated or foreign frames instead.
    A trailing firmware checksum, if supplied, is left uninterpreted.
    """
    if len(data) < 3 or data[0] != 0x40:
        return None
    size = {1: 1, 2: 14, 3: 12, 4: 7, 5: 0, 6: 1}.get(data[1])
    if size is None or data[2] != size or len(data) < size + 3:
        return None
    return Reply(data[1], data[3 : 3 + size])


def clip_memory(
    value: int, minimum: int, maximum: int, unrestricted: bool, *, height: bool = False
) -> int:
    """Preserve the app's full-range and absent-height sentinel behavior."""
    return value if unrestricted or (height and value == 255) else min(maximum, max(minimum, value))
