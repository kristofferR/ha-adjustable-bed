"""Durable opaque local memories for the explicit Limoss Remote app profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from .app_session import app_session

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class LimossRemoteMemory:
    """A source group/name and its signed int32 values, without physical units."""

    name: str
    positions: tuple[tuple[int, int], ...]


@dataclass(slots=True)
class LimossRemoteMemoryStore:
    """Owned by one physical target and retained across controller recreation."""

    slots: dict[int, LimossRemoteMemory] = field(default_factory=dict)

    @classmethod
    def restore(cls, raw: object) -> LimossRemoteMemoryStore:
        store = cls()
        if raw is None:
            return store
        if not isinstance(raw, Mapping):
            raise ValueError("Stored memories must be a mapping")
        for key, value in raw.items():
            if not isinstance(key, str) or key not in {str(i) for i in range(1, 9)}:
                raise ValueError("Stored memory slot is outside 1..8")
            if not isinstance(value, Mapping) or set(value) != {"name", "positions"}:
                raise ValueError("Stored memory fields are invalid")
            name, positions = value["name"], value["positions"]
            if not isinstance(name, str) or not isinstance(positions, Mapping):
                raise ValueError("Stored memory name/positions are invalid")
            parsed: list[tuple[int, int]] = []
            for motor, position in positions.items():
                if not isinstance(motor, str) or motor not in ("0", "1", "2", "3"):
                    raise ValueError("Stored motor index is outside 0..3")
                if type(position) is not int or not -(2**31) <= position < 2**31:
                    raise ValueError("Stored position must be a signed int32")
                parsed.append((int(motor), position))
            store.slots[int(key)] = LimossRemoteMemory(name, tuple(sorted(parsed)))
        return store

    def serialize(self) -> dict[str, object]:
        return {
            str(slot): {
                "name": item.name,
                "positions": {str(motor): value for motor, value in item.positions},
            }
            for slot, item in sorted(self.slots.items())
        }

    def save(self, slot: int, positions: tuple[tuple[int, int], ...]) -> None:
        old = self.slots.get(slot)
        self.slots[slot] = LimossRemoteMemory(old.name if old else f"Memory {slot}", positions)

    def rename(self, slot: int, name: str) -> None:
        old = self.slots.get(slot)
        self.slots[slot] = LimossRemoteMemory(name, old.positions if old else ())


def validate_limoss_remote_metadata(raw: object) -> dict[str, str]:
    """Validate the diagnostic versions and serial read from the bed."""
    if not isinstance(raw, Mapping):
        raise ValueError("Invalid Limoss Remote diagnostic metadata")
    parsed: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ("hardware_version", "software_version", "serial") or not isinstance(value, str):
            raise ValueError("Invalid Limoss Remote diagnostic metadata")
        parsed[key] = value
    return parsed


@dataclass(slots=True)
class LimossRemoteSession:
    """App state shared by one address's offline and live controllers.

    Both fields are persisted app state; restoring updates them in place.
    """

    memories: LimossRemoteMemoryStore = field(default_factory=LimossRemoteMemoryStore)
    metadata: dict[str, str] = field(default_factory=dict)

    def persisted(self) -> dict[str, object]:
        return {"memories": self.memories.serialize(), "metadata": dict(self.metadata)}

    def restore(self, state: Mapping[str, object]) -> None:
        """Validate a stored record completely before replacing anything."""
        if set(state) - {"memories", "metadata"}:
            raise ValueError("Invalid Limoss Remote app state fields")
        memories = LimossRemoteMemoryStore.restore(state.get("memories"))
        metadata = validate_limoss_remote_metadata(state.get("metadata", {}))
        self.memories.slots = memories.slots
        self.metadata.clear()
        self.metadata.update(metadata)


def get_limoss_remote_session(hass: HomeAssistant, address: str) -> LimossRemoteSession:
    """Return the session one address's controllers share."""
    return app_session(hass, address, ("limoss_remote",), LimossRemoteSession)


class LimossRemotePersistedState(TypedDict, total=False):
    capabilities: dict[str, int]


def validate_limoss_remote_state(raw: object) -> LimossRemotePersistedState:
    """Validate the entry's capability record before restoring or updating it."""
    from .beds.limoss_remote_protocol import LimossRemoteCapabilities

    if not isinstance(raw, Mapping) or set(raw) - {"capabilities"}:
        raise ValueError("Invalid Limoss Remote state fields")
    result: LimossRemotePersistedState = {}
    if "capabilities" in raw:
        capabilities = raw["capabilities"]
        fields = ("key_count", "system", "vibration", "configuration", "memory_count")
        if not isinstance(capabilities, Mapping) or set(capabilities) != set(fields):
            raise ValueError("Invalid Limoss Remote capabilities")
        parsed_caps: dict[str, int] = {}
        for field in fields:
            value = capabilities[field]
            if type(value) is not int:
                raise ValueError("Capability fields must be integers")
            parsed_caps[field] = value
        LimossRemoteCapabilities(*(parsed_caps[field] for field in fields))
        result["capabilities"] = parsed_caps
    return result
