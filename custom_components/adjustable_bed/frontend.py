"""Serve and auto-load the Adjustable Bed Lovelace card.

The card bundle is built from ``frontend/src`` into ``frontend/dist`` and ships
with the integration. We register it as a static path and Lovelace module
resource so ``custom:adjustable-bed-card`` is available with zero user setup.
YAML resource mode retains Home Assistant's frontend module fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    LOVELACE_DATA,
)
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Flag in hass.data[DOMAIN] so setup and reload paths cannot register twice.
DATA_FRONTEND_REGISTERED = "frontend_registered"

URL_BASE = "/adjustable_bed_frontend"
CARD_FILENAME = "adjustable-bed-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}"


def _dist_dir() -> Path:
    """Path to the built card bundle directory."""
    return Path(__file__).parent / "frontend" / "dist"


def _gather() -> tuple[bool, str, str]:
    """Run blocking filesystem work off the event loop.

    Return bundle availability, integration version, and a module cache key.

    The bundle digest handles reinstalls or development builds where the card
    changes without an integration version bump.
    """
    card = _dist_dir() / CARD_FILENAME
    exists = card.is_file()
    version = "dev"
    try:
        manifest = json.loads(
            (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
        version = str(manifest.get("version", "dev"))
    except (OSError, ValueError):  # pragma: no cover - defensive
        pass
    cache_key = version
    if exists:
        try:
            digest = hashlib.sha256(card.read_bytes()).hexdigest()[:12]
            cache_key = f"{version}-{digest}"
        except OSError:  # pragma: no cover - file disappeared after is_file()
            pass
    return exists, version, cache_key


async def _async_register_lovelace_resource(
    hass: HomeAssistant,
    card_url: str,
) -> bool:
    """Create or update the card's durable Lovelace resource.

    ``add_extra_js_url`` only injects modules into a newly loaded frontend
    document. A storage resource lets Lovelace load the card independently of
    that initial page render and preserves registration across restarts. YAML
    resource collections cannot be changed, so callers fall back to the
    frontend module hook for those installations.
    """
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or not isinstance(
        resources := lovelace.resources,
        ResourceStorageCollection,
    ):
        return False

    # async_items() is synchronous and does not load storage itself.
    await resources.async_get_info()
    existing = next(
        (
            item
            for item in resources.async_items()
            if str(item.get(CONF_URL, "")).partition("?")[0] == CARD_URL
        ),
        None,
    )
    if existing is None:
        await resources.async_create_item(
            {
                CONF_RESOURCE_TYPE_WS: "module",
                CONF_URL: card_url,
            }
        )
        return True

    if existing.get(CONF_URL) != card_url or existing.get(CONF_TYPE) != "module":
        await resources.async_update_item(
            existing[CONF_ID],
            {
                CONF_RESOURCE_TYPE_WS: "module",
                CONF_URL: card_url,
            },
        )
    return True


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register the static path and auto-load the card on the frontend.

    The card is a convenience; registration must never break integration setup.
    We attempt it at most once and swallow any failure (e.g. the frontend
    component not being available in a minimal/test environment).
    """
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FRONTEND_REGISTERED):
        return
    # Mark as attempted up front so a failure can't trigger repeated
    # (and potentially double-registering) attempts across entry setups.
    data[DATA_FRONTEND_REGISTERED] = True

    exists, version, cache_key = await hass.async_add_executor_job(_gather)
    if not exists:
        _LOGGER.warning(
            "Adjustable Bed card bundle missing at %s; build it with "
            "`bun run build` in frontend/. The custom:adjustable-bed-card card "
            "will be unavailable until then",
            _dist_dir() / CARD_FILENAME,
        )
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(_dist_dir()), False)]
        )
    except Exception:  # noqa: BLE001 - never let the card break setup
        _LOGGER.warning(
            "Could not serve the Adjustable Bed Lovelace card; bed control is "
            "unaffected",
            exc_info=True,
        )
        return

    card_url = f"{CARD_URL}?v={cache_key}"
    try:
        resource_registered = await _async_register_lovelace_resource(hass, card_url)
    except Exception:  # noqa: BLE001 - fall back to the frontend module hook
        resource_registered = False
        _LOGGER.warning(
            "Could not register the Adjustable Bed card as a Lovelace resource; "
            "falling back to frontend module loading",
            exc_info=True,
        )

    # Keep the frontend hook as well as the durable storage resource. Browsers
    # deduplicate identical module imports, and this preserves early loading on
    # fresh pages while the resource covers Lovelace's independent load path.
    try:
        add_extra_js_url(hass, card_url)
    except Exception:  # noqa: BLE001 - never let the card break setup
        if not resource_registered:
            _LOGGER.warning(
                "Could not auto-load the Adjustable Bed Lovelace card; bed "
                "control is unaffected. Add %s manually as a dashboard resource "
                "if needed",
                card_url,
                exc_info=True,
            )
            return
        _LOGGER.debug(
            "Could not add the Adjustable Bed frontend module hook; the "
            "Lovelace resource is registered",
            exc_info=True,
        )

    _LOGGER.debug("Registered Adjustable Bed Lovelace card (v%s)", version)
