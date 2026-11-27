"""Innova Control direct settings with side-aware admission before any await."""

from typing import cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from ...codec.richmat import local_group
from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
)
from .homezone_services import FIELDS as SETTINGS_FIELDS
from .resource_protocol import Operation, Request

FIELDS = dict(SETTINGS_FIELDS)
FIELDS[vol.Required("operation")] = vol.In(
    (
        "query",
        "rgb",
        "lamp_timeout",
        "aroma",
        "massage_timer",
        "massage_popup",
        "join_group",
        "leave_group",
    )
)
FIELDS[vol.Optional("group")] = vol.All(str, vol.Length(min=4, max=4))


async def handle_innova_control(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(c, side, ("configuration",)) for c, side in targets]
    await async_import_modules(call.hass, "beds.richmat_classic.innova_control")
    from .innova_control import InnovaControlController

    operation = call.data["operation"]
    grouping = operation in ("join_group", "leave_group")
    name = call.data.get("group") if operation == "join_group" else None
    if operation == "join_group" and name is None:
        raise invalid("richmat_classic_control")
    if grouping:
        try:
            local_group(name)
        except ValueError as error:
            raise invalid("richmat_classic_control") from error
    request = Request(
        cast(Operation, operation if not grouping else "query"),
        color=call.data.get("rgb_color"),
        seconds=call.data.get("seconds"),
        aroma_times=call.data.get("aroma_times"),
        progress=call.data.get("progress"),
        popup=call.data.get("popup"),
    )

    def validate(controller: InnovaControlController) -> None:
        # Use current-link proof already available before the batch starts.
        # Offline preflight stays static; execution rechecks after connecting.
        if grouping:
            if controller.has_live_session:
                controller.validate_group_request()
        else:
            controller.validate_request(request, live=controller.has_live_session)

    preflighted = await _preflight_capability(
        targets,
        InnovaControlController,
        validate=validate,
    )
    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(
            InnovaControlController,
            lambda c: c.async_group(name) if grouping else c.execute_request(request),
        ),
        cancel_running=False,
        resource="configuration",
        admissions=admissions,
    )


def async_register_innova_control_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, "innova_control", handle_innova_control, schema=vol.Schema(FIELDS)
    )
