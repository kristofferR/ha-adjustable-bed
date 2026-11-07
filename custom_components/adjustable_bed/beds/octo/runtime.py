"""Standard OCTO runtime narrowing and its setup-time PIN repair."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant

from ...const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_OCTO_PIN,
    CONF_PROTOCOL_VARIANT,
    OCTO_VARIANT_STAR2,
)
from ...unsupported import clear_octo_pin_required_issue, link_octo_pin_required_issue

if TYPE_CHECKING:
    from .controller import OctoController


def octo_controller(controller: object | None) -> OctoController | None:
    """Return the Standard OCTO controller when present."""
    if not getattr(controller, "is_octo_smart_control", False):
        return None

    # Keep the protocol module lazy for integrations that do not use Standard
    # OCTO. The marker only selects the candidate; isinstance establishes its
    # actual runtime type before exposing OCTO-specific attributes.
    from .controller import OctoController

    return controller if isinstance(controller, OctoController) else None


async def async_refresh_octo_pin_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the Octo PIN repair when the configuration already resolves it.

    Runs on every setup, so saving a PIN (which reloads the entry) clears the
    issue even when the bed is unreachable and the connect path never runs. A
    repair that still applies is linked to the entry instead.
    """
    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return
    # Star2 has no PIN mechanism at all, and OctoStar2Controller has no
    # pin_locked_without_pin, so the connect path could never clear a stale
    # issue left behind by a variant switch.
    is_standard_octo = (
        entry.data.get(CONF_BED_TYPE) == BED_TYPE_OCTO
        and entry.data.get(CONF_PROTOCOL_VARIANT) != OCTO_VARIANT_STAR2
    )
    if not is_standard_octo or entry.data.get(CONF_OCTO_PIN):
        clear_octo_pin_required_issue(hass, address)
    else:
        link_octo_pin_required_issue(
            hass, address, entry.data.get(CONF_NAME, entry.title), entry.entry_id
        )
