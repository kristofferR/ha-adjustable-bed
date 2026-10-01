"""Persistent device-local FSM Relax memories, never measured positions or units."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


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


@dataclass(slots=True)
class FsmRelaxSession:
    """Process-local per-device sequence and memory-operation ownership."""

    counter: int = 0
    quarantine_client: object | None = None
    memory_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class FsmRelaxState:
    """One physical-address store, preserved when entry ownership changes."""

    def __init__(self, hass: HomeAssistant, entry_id: str, address: str) -> None:
        identity = hashlib.sha256(address.upper().encode()).hexdigest()
        cache = hass.data.get("adjustable_bed_fsm_relax_sessions")
        if not isinstance(cache, dict):
            cache = {}
            hass.data["adjustable_bed_fsm_relax_sessions"] = cache
        session = cache.get(identity)
        if not isinstance(session, FsmRelaxSession):
            session = FsmRelaxSession()
            cache[identity] = session
        self.session = session
        self._sessions = cache
        self._identity = identity
        self._store: Store[dict[str, object]] = Store(
            hass, 1, f"adjustable_bed.fsm_relax.{identity}"
        )
        self._lock = asyncio.Lock()
        self.slots: dict[int, dict[int, int]] = {}
        self.names = validate_names([""] * 8)
        self.capability_body: bytes | None = None
        self.serial: int | None = None
        self._loaded = False

    async def async_load(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            data = await self._store.async_load()
            if isinstance(data, dict):
                try:
                    self.names = validate_names(data.get("names", [""] * 8))
                    slots = data.get("slots", {})
                    if isinstance(slots, dict):
                        for slot, positions in slots.items():
                            if (
                                isinstance(slot, str)
                                and slot.isdigit()
                                and 1 <= int(slot) <= 8
                                and isinstance(positions, dict)
                            ):
                                indexed = {
                                    int(k): v
                                    for k, v in positions.items()
                                    if isinstance(k, str) and k.isdigit()
                                }
                                self.slots[int(slot)] = validate_positions(indexed)
                    serial = data.get("serial")
                    if type(serial) is int and -(2**31) <= serial < 2**31:
                        self.serial = serial
                    cap = data.get("capability_body")
                    if isinstance(cap, str):
                        body = bytes.fromhex(cap)
                        if len(body) == 5 and body[0] == 2:
                            self.capability_body = body
                except ValueError, TypeError:
                    # A malformed local record is never sent to the bed.
                    self.slots = {}
                    self.capability_body = None
            self._loaded = True

    def _data(self, slots: dict[int, dict[int, int]], names: tuple[str, ...]) -> dict[str, object]:
        return {
            "slots": {str(s): {str(k): v for k, v in p.items()} for s, p in slots.items()},
            "names": list(names),
            "serial": self.serial,
            "capability_body": self.capability_body.hex() if self.capability_body else None,
        }

    async def async_save_slot(self, slot: int, positions: dict[int, int]) -> None:
        if type(slot) is not int or not 1 <= slot <= 8:
            raise ValueError("Memory slot must be 1..8")
        validated = validate_positions(positions)
        async with self._lock:
            candidate = {**self.slots, slot: validated}
            await self._store.async_save(self._data(candidate, self.names))
            self.slots = candidate

    async def async_set_names(self, names: object) -> None:
        validated = validate_names(names)
        async with self._lock:
            await self._store.async_save(self._data(self.slots, validated))
            self.names = validated

    async def async_save_capabilities(self, body: bytes) -> None:
        if len(body) != 5 or body[0] != 2:
            raise ValueError("Invalid capability record")
        async with self._lock:
            previous = self.capability_body
            self.capability_body = body
            try:
                await self._store.async_save(self._data(self.slots, self.names))
            except BaseException:
                self.capability_body = previous
                raise

    async def async_save_serial(self, serial: int) -> None:
        """Persist the unsolicited source serial without inventing a query."""
        if type(serial) is not int or not -(2**31) <= serial < 2**31:
            raise ValueError("Serial must be signed 32-bit")
        async with self._lock:
            previous = self.serial
            self.serial = serial
            try:
                await self._store.async_save(self._data(self.slots, self.names))
            except BaseException:
                self.serial = previous
                raise

    async def async_remove(self) -> None:
        async with self._lock:
            await self._store.async_remove()
            self.slots = {}
            self.capability_body = None
            self.serial = None
            self._sessions.pop(self._identity, None)


async def async_remove_unowned_states(hass: HomeAssistant, entry: object) -> None:
    """Remove physical records only when no surviving config entry owns them."""
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import CONF_ADDRESS

    from .const import BED_TYPE_FSM_RELAX, CONF_BED_TYPE, DOMAIN
    from .pairing import iter_children

    if not isinstance(entry, ConfigEntry):
        return

    def addresses(candidate: ConfigEntry) -> set[str]:
        records = [candidate.data, *iter_children(candidate.data)]
        return {
            address.upper()
            for record in records
            if record.get(CONF_BED_TYPE) == BED_TYPE_FSM_RELAX
            and isinstance(address := record.get(CONF_ADDRESS), str)
        }

    retained: set[str] = set()
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id:
            retained.update(addresses(other))
    for address in addresses(entry) - retained:
        await FsmRelaxState(hass, entry.entry_id, address).async_remove()
