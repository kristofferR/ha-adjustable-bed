"""Serve and auto-load the Adjustable Bed Lovelace card.

The card bundle is built from ``frontend/src`` into ``frontend/dist`` and ships
with the integration. We register it as a static path and add it as a frontend
module URL so ``custom:adjustable-bed-card`` is available with zero user setup —
no manual HACS/Lovelace resource needed, in both storage and YAML dashboards.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Flag in hass.data[DOMAIN] so registration only happens once, even though
# async_setup may be invoked alongside multiple config entries.
DATA_FRONTEND_REGISTERED = "frontend_registered"

URL_BASE = "/adjustable_bed_frontend"
CARD_FILENAME = "adjustable-bed-card.js"


def _dist_dir() -> Path:
    """Path to the built card bundle directory."""
    return Path(__file__).parent / "frontend" / "dist"


def _gather() -> tuple[bool, str]:
    """Run blocking filesystem work off the event loop.

    Returns whether the bundle exists and the integration version (used to
    cache-bust the module URL when users upgrade).
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
    return exists, version


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

    exists, version = await hass.async_add_executor_job(_gather)
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
        add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={version}")
    except Exception:  # noqa: BLE001 - never let the card break setup
        _LOGGER.warning(
            "Could not register the Adjustable Bed Lovelace card; bed control is "
            "unaffected. Add it manually as a dashboard resource if needed",
            exc_info=True,
        )
        return

    _LOGGER.debug("Registered Adjustable Bed Lovelace card (v%s)", version)
