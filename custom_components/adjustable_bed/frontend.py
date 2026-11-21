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
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from homeassistant.components.frontend import DOMAIN as FRONTEND_DOMAIN
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    LOVELACE_DATA,
)
from homeassistant.components.lovelace.const import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.setup import async_when_setup

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Flag in hass.data[DOMAIN] so setup and reload paths cannot register twice.
DATA_FRONTEND_REGISTERED = "frontend_registered"

URL_BASE = "/adjustable_bed_frontend"
CARD_FILENAME = "adjustable-bed-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}"


class CardLoaderView(HomeAssistantView):
    """Resolve permanent and previously published URLs to the current bundle."""

    url = CARD_URL
    extra_urls = [f"{URL_BASE}/{{cache_key}}/{CARD_FILENAME}"]
    name = "adjustable_bed:card_loader"
    requires_auth = False

    def __init__(self, card_url: str) -> None:
        self._module = f"import {json.dumps(card_url)};\n"

    async def get(
        self, request: web.Request, cache_key: str | None = None
    ) -> web.Response:
        """Never cache the pointer to a bundle that changes after an upgrade.

        The exact current bundle URL has its own static route. Old URLs kept
        by a browser, WebView or YAML dashboard reach this loader instead of
        returning 404. The URL parameter is never used as a filesystem path.
        """
        return web.Response(
            text=self._module,
            content_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )


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


def _card_url(cache_key: str) -> str:
    """Return a content-versioned URL whose path survives cache normalization."""
    return f"{URL_BASE}/{cache_key}/{CARD_FILENAME}"


def _is_card_resource(url: object) -> bool:
    """Return whether a resource URL belongs to this integration's card."""
    path = urlsplit(str(url)).path
    return path == CARD_URL or (
        path.startswith(f"{URL_BASE}/") and path.endswith(f"/{CARD_FILENAME}")
    )


async def _async_register_lovelace_resource(
    hass: HomeAssistant,
    card_url: str,
) -> bool:
    """Create or update the card's durable Lovelace resource.

    A storage resource lets Lovelace load the card independently of frontend
    module events and preserves registration across restarts. YAML
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
    existing = [
        item
        for item in resources.async_items()
        if _is_card_resource(item.get(CONF_URL, ""))
    ]
    if not existing:
        await resources.async_create_item(
            {
                CONF_RESOURCE_TYPE_WS: "module",
                CONF_URL: card_url,
            }
        )
        return True

    current = next(
        (
            item
            for item in existing
            if item.get(CONF_URL) == card_url and item.get(CONF_TYPE) == "module"
        ),
        existing[0],
    )
    if current.get(CONF_URL) != card_url or current.get(CONF_TYPE) != "module":
        await resources.async_update_item(
            current[CONF_ID],
            {
                CONF_RESOURCE_TYPE_WS: "module",
                CONF_URL: card_url,
            },
        )

    for duplicate in existing:
        if duplicate[CONF_ID] != current[CONF_ID]:
            await resources.async_delete_item(duplicate[CONF_ID])
    return True


async def _async_add_frontend_module(
    hass: HomeAssistant,
    _component: str,
    *,
    card_url: str,
) -> None:
    """Add the module when Home Assistant's frontend is ready."""
    try:
        add_extra_js_url(hass, card_url)
    except Exception:
        _LOGGER.warning(
            "Could not add the Adjustable Bed frontend module hook; the "
            "Lovelace resource will still be attempted",
            exc_info=True,
        )


async def _async_add_lovelace_resource(
    hass: HomeAssistant,
    _component: str,
    *,
    card_url: str,
) -> None:
    """Persist the module when Home Assistant's Lovelace data is ready."""
    try:
        await _async_register_lovelace_resource(hass, card_url)
    except Exception:
        _LOGGER.warning(
            "Could not register the Adjustable Bed card as a Lovelace resource; "
            "the frontend module hook will still be attempted",
            exc_info=True,
        )


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register the static path and auto-load the card on the frontend.

    The card is a convenience; registration must never break integration setup.
    Static routes are registered once. Module and resource registration wait
    for their optional Home Assistant components instead of depending on setup
    order.
    """
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FRONTEND_REGISTERED):
        return
    exists, version, cache_key = await hass.async_add_executor_job(_gather)
    if not exists:
        _LOGGER.warning(
            "Adjustable Bed card bundle missing at %s; build it with "
            "`bun run build` in frontend/. The custom:adjustable-bed-card card "
            "will be unavailable until then",
            _dist_dir() / CARD_FILENAME,
        )
        return

    card_url = _card_url(cache_key)
    card_path = str(_dist_dir() / CARD_FILENAME)
    try:
        await hass.http.async_register_static_paths(
            [
                # Put the content identity in the path. Some webview and proxy
                # caches normalize query parameters before looking up assets.
                StaticPathConfig(card_url, card_path, True),
            ]
        )
        # Register the exact static route first, then the loader's fallback for
        # older content paths. Keep the resource URL stable across upgrades.
        hass.http.register_view(CardLoaderView(card_url))
    except Exception:
        _LOGGER.warning(
            "Could not serve the Adjustable Bed Lovelace card; bed control is "
            "unaffected",
            exc_info=True,
        )
        return

    data[DATA_FRONTEND_REGISTERED] = True

    # Keep both loading paths. The frontend hook injects the card into new pages
    # and notifies open pages, while the storage resource is durable. Waiting on
    # the component lifecycle prevents a startup-order miss from becoming
    # permanent for the rest of the Home Assistant process.
    async_when_setup(
        hass,
        FRONTEND_DOMAIN,
        partial(_async_add_frontend_module, card_url=CARD_URL),
    )
    async_when_setup(
        hass,
        LOVELACE_DOMAIN,
        partial(_async_add_lovelace_resource, card_url=CARD_URL),
    )

    _LOGGER.debug("Registered Adjustable Bed card routes and loading hooks (v%s)", version)
