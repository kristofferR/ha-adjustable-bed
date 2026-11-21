"""Structured, product-gated RMControl alarm and snore configuration actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import SIDE_FIELD, _call_targets, _preflight_and_execute

if TYPE_CHECKING:
    from .controller import RmcontrolController

_ANTI_SNORE_FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): cv.ensure_list,
    vol.Required("operation"): vol.In(("switch", "configure", "query")),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("mode"): vol.In(("count", "time")),
    vol.Optional("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
}
_ANTI_SNORE_FIELDS.update(SIDE_FIELD.items())
ANTI_SNORE_SCHEMA = vol.Schema(_ANTI_SNORE_FIELDS)


async def _execute(
    call: ServiceCall,
    supported: Callable[[RmcontrolController], bool],
    command: Callable[[RmcontrolController], Awaitable[None]],
    validate: Callable[[RmcontrolController], None] | None = None,
) -> None:
    await async_import_modules(call.hass, "beds.rmcontrol.controller")
    from .controller import RmcontrolController

    await _preflight_and_execute(
        _call_targets(call),
        RmcontrolController,
        command,
        supported=supported,
        validate=validate,
        skip_disconnect=call.data["operation"] == "query",
    )


def _require(call: ServiceCall, *fields: str) -> None:
    for field in fields:
        if field not in call.data:
            raise invalid("field_required", field=field)


async def handle_rmcontrol_anti_snore(call: ServiceCall) -> None:
    """Keep intervention count/duration configuration separate from enabling it."""
    operation = call.data["operation"]
    if operation == "switch":
        _require(call, "enabled")
    elif operation == "configure":
        _require(call, "mode", "value")

    async def control(controller: RmcontrolController) -> None:
        if operation == "switch":
            await controller.rmcontrol_anti_snore_switch(call.data["enabled"])
        elif operation == "configure":
            await controller.rmcontrol_anti_snore_config(call.data["mode"], call.data["value"])
        else:
            await controller.rmcontrol_query_anti_snore()

    await _execute(call, lambda controller: controller.supports_rmcontrol_anti_snore, control)


def async_register_rmcontrol_services(hass: HomeAssistant) -> None:
    """Register the two configuration actions alongside the integration services."""
    hass.services.async_register(
        DOMAIN, "rmcontrol_anti_snore", handle_rmcontrol_anti_snore, schema=ANTI_SNORE_SCHEMA
    )
