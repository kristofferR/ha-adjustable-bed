"""Per-bed storage for app-local preferences (``BedController.persisted_app_state``).

One Home Assistant Store per physical address holds a slot for each bed type
and protocol variant, so a profile change never reads another profile's
preferences. The address already separates the sides of a two-address pair.
Coordinators sharing an address share one instance, so their saves never
overwrite each other's slot.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_REGISTRY_KEY = "app_state_stores"


def app_state_storage_key(address: str) -> str:
    """Return the storage key for one physical bed address."""
    return f"{DOMAIN}.app_state_{address.replace(':', '_').lower()}"


def app_state_slot(bed_type: str | None, variant: str | None) -> str:
    """Return the slot of one profile within an address's store."""
    return f"{bed_type}:{variant or 'auto'}"


class AppStateStore:
    """Every profile slot stored for one physical address."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._store: Store[dict[str, dict[str, Any]]] = Store(hass, 1, app_state_storage_key(address))
        self._data: dict[str, dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    async def async_slot(self, slot: str) -> dict[str, Any]:
        """Return a copy of one slot, loading the store on first use."""
        async with self._lock:
            if self._data is None:
                stored = await self._store.async_load()
                self._data = (
                    {key: dict(value) for key, value in stored.items() if isinstance(value, dict)}
                    if isinstance(stored, dict)
                    else {}
                )
        return dict(self._data.get(slot, {}))

    def update(self, slot: str, state: Mapping[str, Any]) -> None:
        """Schedule a save when a loaded slot changed."""
        if self._data is None or self._data.get(slot) == state:
            return
        self._data[slot] = dict(state)
        self._store.async_delay_save(self._snapshot, 1)

    async def async_save(self) -> None:
        """Write pending changes now (entry unload)."""
        if self._data is not None:
            await self._store.async_save(self._snapshot())

    async def async_remove(self) -> None:
        """Delete the stored file, cancel pending writes and make later saves no-ops."""
        self._data = None
        await self._store.async_remove()

    def _snapshot(self) -> dict[str, dict[str, Any]]:
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
    """Delete the stored preferences of beds no config entry owns any more."""
    registry = _registry(hass)
    for address in addresses:
        store = registry.pop(address.upper(), None) or AppStateStore(hass, address)
        await store.async_remove()
