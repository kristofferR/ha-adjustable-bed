"""Richmat MH app aroma and light colour actions (Revive, Best Mattress, Blvd Home, HARMONY, Idealbed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

if TYPE_CHECKING:
    from .controller import RichmatMhController

SERVICE_RICHMAT_MH_AROMA = "richmat_mh_aroma"
SERVICE_RICHMAT_MH_LIGHT_COLOR = "richmat_mh_light_color"

_AROMA_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("mode2_startup_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
    vol.Required("mode3_startup_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
    vol.Required("mode3_pause_hours"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
}
_AROMA_FIELDS.update(SIDE_FIELD.items())
AROMA_SCHEMA = vol.Schema(_AROMA_FIELDS)
_LIGHT_COLOR_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
}
_LIGHT_COLOR_FIELDS.update(SIDE_FIELD.items())
LIGHT_COLOR_SCHEMA = vol.Schema(_LIGHT_COLOR_FIELDS)


async def _controller_class(call: ServiceCall) -> type[RichmatMhController]:
    """Load the controller off the event loop when an action first needs it."""
    await async_import_modules(call.hass, "beds.richmat_mh.controller")
    from .controller import RichmatMhController

    return RichmatMhController


async def handle_richmat_mh_aroma(call: ServiceCall) -> None:
    """Write the aroma page's three timing sliders as the app does on release."""

    async def program(controller: RichmatMhController) -> None:
        await controller.richmat_mh_aroma(
            call.data["mode2_startup_minutes"],
            call.data["mode3_startup_minutes"],
            call.data["mode3_pause_hours"],
        )

    await _preflight_and_execute(
        _call_targets(call),
        await _controller_class(call),
        "Richmat MH aroma timing",
        program,
        supported=lambda controller: controller.supports_richmat_mh_aroma,
    )


async def handle_richmat_mh_light_color(call: ServiceCall) -> None:
    """Write the LED or button-light page's colour (one 10-byte frame)."""
    rgb: tuple[int, int, int] = call.data["rgb_color"]

    async def program(controller: RichmatMhController) -> None:
        await controller.set_light_color(rgb)

    await _preflight_and_execute(
        _call_targets(call),
        await _controller_class(call),
        "Richmat MH light colour",
        program,
        supported=lambda controller: controller.supports_richmat_mh_light_color,
    )


def async_register_richmat_mh_services(hass: HomeAssistant) -> None:
    """Register the Richmat MH configuration actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_RICHMAT_MH_AROMA, handle_richmat_mh_aroma, schema=AROMA_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RICHMAT_MH_LIGHT_COLOR, handle_richmat_mh_light_color,
        schema=LIGHT_COLOR_SCHEMA,
    )
