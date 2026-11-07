"""Device-local FSM Relax memories and session, never measured positions or units."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field


def validate_names(value: object) -> tuple[str, ...]:
    """Validate all eight local labels before changing any state."""
    if not isinstance(value, (list, tuple)) or len(value) != 8:
        raise ValueError("FSM Relax requires eight local memory names")
    names: list[str] = []
    for index, name in enumerate(value, 1):
        if not isinstance(name, str) or len(name) > 80:
            raise ValueError("Memory names must be strings of at most 80 characters")
        names.append(name.strip() or f"M{index}")
    return tuple(names)


def validate_positions(value: object) -> dict[int, int]:
    """Keep signed opaque values and motor indexes, without scaling."""
    if not isinstance(value, dict):
        raise ValueError("Memory must contain indexed raw values")
    result: dict[int, int] = {}
    for index, raw in value.items():
        if type(index) is not int or not 0 <= index <= 3:
            raise ValueError("Motor index must be 0..3")
        if type(raw) is not int or not -(2**31) <= raw < 2**31:
            raise ValueError("Raw memory must be signed 32-bit")
        result[index] = raw
    if 0 not in result:
        raise ValueError("Motor zero is required for a saved memory")
    return result


def validate_capability_body(value: object) -> bytes | None:
    """Return a stored capability reply, or None when it is absent or malformed."""
    if not isinstance(value, str):
        return None
    try:
        body = bytes.fromhex(value)
    except ValueError:
        return None
    return body if len(body) == 5 and body[0] == 2 else None


def _serial(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise ValueError("Serial must be signed 32-bit")
    return value


@dataclass(slots=True)
class FsmRelaxSession:
    """One physical address's memories, serial and sequence/memory ownership.

    Shared by the offline and live controllers; ``slots`` and ``serial`` are
    the persisted app state.
    """

    counter: int = 0
    quarantine_client: object | None = None
    memory_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    persist_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    slots: dict[int, dict[int, int]] = field(default_factory=dict)
    serial: int | None = None

    def persisted(self, slots: dict[int, dict[int, int]] | None = None) -> dict[str, object]:
        """Serialize the stored state, optionally with candidate memories."""
        return {
            "slots": {
                str(slot): {str(motor): raw for motor, raw in positions.items()}
                for slot, positions in sorted((self.slots if slots is None else slots).items())
            },
            "serial": self.serial,
        }

    def restore(self, state: Mapping[str, object]) -> None:
        """Validate a stored record completely before replacing anything."""
        if set(state) - {"slots", "serial"}:
            raise ValueError("Unknown FSM Relax app state")
        raw_slots = state.get("slots", {})
        if not isinstance(raw_slots, Mapping):
            raise ValueError("FSM Relax memories must be a mapping")
        slots: dict[int, dict[int, int]] = {}
        for slot, positions in raw_slots.items():
            if not isinstance(slot, str) or not slot.isdigit() or not 1 <= int(slot) <= 8:
                raise ValueError("Memory slot must be 1..8")
            if not isinstance(positions, Mapping) or not all(
                isinstance(motor, str) and motor.isdigit() for motor in positions
            ):
                raise ValueError("Memory must contain indexed raw values")
            slots[int(slot)] = validate_positions({int(k): v for k, v in positions.items()})
        serial = _serial(state.get("serial"))
        self.slots, self.serial = slots, serial
