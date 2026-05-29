"""Global, user-toggleable discovery settings for the Adjustable Bed integration.

Home Assistant has no built-in per-integration "stop discovering" switch, so this
module stores one small global flag (``disable_discovery``) in its own Store. The
flag is edited via the options flow of any configured bed and read by
``config_flow.async_step_bluetooth`` to suppress automatic discovery cards.

It is intentionally global (a single source of truth shared by all beds) rather
than per-entry, so a user with several beds does not have to toggle it on each
one. Manual "Add Integration" is unaffected - only push discovery is gated.

See: https://github.com/kristofferR/ha-adjustable-bed/discussions/342
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_discovery_settings"
_DATA_KEY = f"{DOMAIN}_discovery_settings"

KEY_DISABLE_DISCOVERY = "disable_discovery"


class DiscoverySettings:
    """Persisted, integration-wide discovery preferences."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the backing store (loaded lazily on first use)."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def _async_ensure_loaded(self) -> dict[str, Any]:
        if self._data is None:
            loaded = await self._store.async_load()
            self._data = dict(loaded) if isinstance(loaded, dict) else {}
        return self._data

    async def async_is_discovery_disabled(self) -> bool:
        """Return whether automatic discovery is currently suppressed."""
        return bool((await self._async_ensure_loaded()).get(KEY_DISABLE_DISCOVERY, False))

    async def async_set_discovery_disabled(self, disabled: bool) -> None:
        """Persist the discovery-disabled flag."""
        data = await self._async_ensure_loaded()
        if bool(data.get(KEY_DISABLE_DISCOVERY, False)) == bool(disabled):
            return
        data[KEY_DISABLE_DISCOVERY] = bool(disabled)
        self._data = data
        await self._store.async_save(data)
        _LOGGER.debug("Automatic Bluetooth discovery %s", "disabled" if disabled else "enabled")


def _async_get_settings(hass: HomeAssistant) -> DiscoverySettings:
    """Return the singleton settings object for this Home Assistant instance."""
    settings: DiscoverySettings | None = hass.data.get(_DATA_KEY)
    if settings is None:
        settings = DiscoverySettings(hass)
        hass.data[_DATA_KEY] = settings
    return settings


async def async_is_discovery_disabled(hass: HomeAssistant) -> bool:
    """Return whether automatic Bluetooth discovery is suppressed."""
    return await _async_get_settings(hass).async_is_discovery_disabled()


async def async_set_discovery_disabled(hass: HomeAssistant, disabled: bool) -> None:
    """Set whether automatic Bluetooth discovery is suppressed."""
    await _async_get_settings(hass).async_set_discovery_disabled(disabled)
