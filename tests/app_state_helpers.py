"""Read and restart app-local state the way a coordinator and a restart would."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.app_session import drop_app_sessions
from custom_components.adjustable_bed.app_state_store import app_state_slot, app_state_store
from custom_components.adjustable_bed.const import DOMAIN


async def stored_app_state(coordinator: Any, key: str | None = None) -> dict[str, Any]:
    """Return the slot a coordinator's controller saves to (in memory, not yet flushed).

    ``key`` defaults to the capability controller's profile key.
    """
    if key is None and (controller := coordinator.capability_controller) is not None:
        key = controller.persisted_app_state_key
    slot = app_state_slot(coordinator.bed_type, coordinator._protocol_variant, key)
    return await coordinator._app_state_store.async_slot(slot)


async def restart_app_state(hass: HomeAssistant, address: str) -> None:
    """Flush an address's app state to storage and forget everything held in memory."""
    await app_state_store(hass, address).async_save()
    hass.data[DOMAIN]["app_state_stores"].pop(address.upper(), None)
    drop_app_sessions(hass, address)


async def write_app_state(coordinator: Any, state: dict[str, Any], key: str | None = None) -> None:
    """Store a coordinator's app state as if a previous run had saved it."""
    slot = app_state_slot(coordinator.bed_type, coordinator._protocol_variant, key)
    await coordinator._app_state_store.async_write(slot, state)
