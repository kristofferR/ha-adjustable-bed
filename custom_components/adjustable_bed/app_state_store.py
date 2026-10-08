"""Per-bed storage for app-local state (``BedController.persisted_app_state``).

One Home Assistant Store per physical address holds a slot for each bed type
and app profile (the protocol variant, unless the controller supplies a finer
key), so a profile change never reads another profile's state. The address
already separates the sides of a two-address pair. Coordinators sharing an
address share one instance, so their saves never overwrite each other's slot.
The coordinator restores a slot into every new controller and saves it whenever
the controller publishes state. Changing profile keeps every profile's slot,
so changing back restores that profile's preferences.
The reserved profile-recommendation slot retains support decision history even
after the last config entry is removed; ordinary app preferences are forgotten.

Where a value belongs:

- Config entry data/options hold configuration: what the user chooses in the
  config or options flow, and capability snapshots that decide which entities
  exist (a change there reloads the entry).
- This store holds everything else a controller remembers for its app across
  restarts: values the user changes through entities or actions (levels,
  intensities, timers, movement settings), saved memories and their runtime
  names, and passive records read from the bed such as serials and versions.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .app_session import drop_app_sessions
from .const import DOMAIN

_REGISTRY_KEY = "app_state_stores"
_LOGGER = logging.getLogger(__name__)
PROFILE_DECISIONS_SLOT: Final = "profile_recommendations"


def app_state_storage_key(address: str) -> str:
    """Return the storage key for one physical bed address."""
    return f"{DOMAIN}.app_state_{address.replace(':', '_').lower()}"


def app_state_slot(bed_type: str | None, variant: str | None, key: str | None = None) -> str:
    """Return the slot of one profile within an address's store."""
    return f"{bed_type}:{key or variant or 'auto'}"


class AppStateStore:
    """Every profile slot stored for one physical address."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._store: Store[dict[str, dict[str, Any]]] = Store(hass, 1, app_state_storage_key(address))
        self._data: dict[str, dict[str, Any]] | None = None
        self._pending = False
        self._lock = asyncio.Lock()

    async def _async_load(self) -> dict[str, dict[str, Any]]:
        if self._data is None:
            stored = await self._store.async_load()
            self._data = (
                {key: dict(value) for key, value in stored.items() if isinstance(value, dict)}
                if isinstance(stored, dict)
                else {}
            )
        return self._data

    async def async_slot(self, slot: str) -> dict[str, Any]:
        """Return a copy of one slot, loading the store on first use."""
        async with self._lock:
            data = await self._async_load()
        return dict(data.get(slot, {}))

    def update(self, slot: str, state: Mapping[str, Any]) -> None:
        """Schedule a save when a loaded slot changed."""
        if self._data is None or self._data.get(slot) == state:
            return
        self._data[slot] = dict(state)
        self._schedule_save()

    async def async_write(self, slot: str, state: Mapping[str, Any]) -> None:
        """Write one slot now; on failure raise and keep the previous value."""
        await self.async_update(slot, lambda _: state)

    async def async_update(
        self,
        slot: str,
        update: Callable[[dict[str, Any]], Mapping[str, Any]],
        *,
        defer_on_error: bool = False,
    ) -> dict[str, Any]:
        """Read, update and save a slot under one lock, without losing concurrent edits."""
        async with self._lock:
            data = await self._async_load()
            state = dict(update(dict(data.get(slot, {}))))
            if data.get(slot) == state:
                return dict(state)
            try:
                await self._store.async_save({**data, slot: state})
            except OSError:
                if not defer_on_error:
                    raise
                # The associated settings have already committed. Retain their
                # history in memory and retry rather than pretending they failed.
                data[slot] = state
                self._schedule_save()
                _LOGGER.warning(
                    "Unable to persist committed profile history; retry scheduled", exc_info=True
                )
                return dict(state)
            data[slot] = state
            # The write included every pending change and cancelled the delayed one.
            self._pending = False
            return dict(state)

    async def async_save(self) -> None:
        """Flush pending changes at unload; retain failures for a later retry."""
        # Reloads can unload the entry while a profile decision is being saved.
        async with self._lock:
            if self._data is not None and self._pending:
                self._pending = False
                try:
                    await self._store.async_save(self._snapshot())
                except OSError:
                    self._schedule_save()
                    _LOGGER.warning(
                        "Unable to persist app state during unload; retry scheduled", exc_info=True
                    )

    async def async_remove(self, *, keep_slots: Iterable[str] = ()) -> None:
        """Forget app preferences, optionally retaining durable support evidence."""
        async with self._lock:
            slots = frozenset(keep_slots)
            data = await self._async_load() if slots else {}
            retained = {slot: state for slot, state in data.items() if slot in slots}
            if retained:
                await self._store.async_save(retained)
            else:
                await self._store.async_remove()
            self._data = None
            self._pending = False

    def _schedule_save(self) -> None:
        self._pending = True
        self._store.async_delay_save(self._snapshot, 1)

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        """Copy loaded slots; taking a delayed snapshot cannot confirm persistence."""
        return dict(self._data or {})


def _registry(hass: HomeAssistant) -> dict[str, AppStateStore]:
    registry: dict[str, AppStateStore] = hass.data.setdefault(DOMAIN, {}).setdefault(_REGISTRY_KEY, {})
    return registry


def app_state_store(hass: HomeAssistant, address: str) -> AppStateStore:
    """Return the shared store for one physical address."""
    key = address.upper()
    registry = _registry(hass)
    if key not in registry:
        registry[key] = AppStateStore(hass, address)
    return registry[key]


async def async_remove_app_states(hass: HomeAssistant, addresses: Iterable[str]) -> None:
    """Forget the app state and sessions of beds no config entry owns any more."""
    registry = _registry(hass)
    addresses = list(addresses)
    for address in addresses:
        drop_app_sessions(hass, address)
    for address in addresses:
        store = registry.pop(address.upper(), None) or AppStateStore(hass, address)
        await store.async_remove(keep_slots=(PROFILE_DECISIONS_SLOT,))
