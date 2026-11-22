"""Direct color and local receiver group settings for Base Remote."""

from __future__ import annotations

import asyncio

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...command_scheduler import note_frame_skipped
from ...const import DOMAIN
from ...errors import failed, invalid
from ...import_executor import async_import_modules
from ...profiles.baseremote import GROUP_TIMEOUT_S
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _child_side,
    _command_targets,
    _preflight_and_execute,
    _Selection,
)


async def handle_settings(call: ServiceCall) -> None:
    targets = _call_targets(call)
    selection = _Selection.capture(targets)
    operation = call.data["operation"]
    if operation != "set_color":
        # The parent's both-side scheduler would fan out concurrent writes.
        # Group changes require write, settle and link closure on one receiver.
        targets = [
            (parent, _child_side(parent, side, child))
            for parent, side in targets
            for child in _command_targets(parent, side)
        ]
    admissions = [
        _capture_command_admission(coordinator, side, ("configuration",))
        for coordinator, side in targets
    ]
    await async_import_modules(call.hass, "beds.baseremote.controller")
    from .controller import BaseRemoteController

    group = call.data.get("group")
    color = call.data.get("rgb_color")
    if operation == "set_color" and color is None:
        raise invalid("baseremote_control")
    if operation == "set_group" and group is None:
        raise invalid("baseremote_group")

    def validate(controller: BaseRemoteController) -> None:
        if operation != "set_color":
            from ...codec.richmat import local_group

            try:
                local_group(group if operation == "set_group" else None)
            except ValueError as error:
                raise invalid("baseremote_group") from error
            if controller.client is not None and controller.client.is_connected:
                # Every connected receiver must offer the group setting before any changes.
                controller._group_transport()

    def admitted() -> bool:
        selection.require_unchanged(call)
        return not selection.stopped()

    async def execute(controller: BaseRemoteController) -> None:
        if not admitted():
            note_frame_skipped()
            return
        if operation == "set_color":
            assert color is not None
            await controller.set_light_color(color, before_write=admitted)
        else:
            await controller.async_group(
                group if operation == "set_group" else None, before_write=admitted
            )

    try:
        async with asyncio.timeout(GROUP_TIMEOUT_S if operation != "set_color" else None):
            await _preflight_and_execute(
                targets,
                BaseRemoteController,
                execute,
                validate=validate,
                cancel_running=False,
                resource="configuration",
                admit=True,
                admissions=admissions,
            )
    except TimeoutError as error:
        raise failed("baseremote_group_timeout") from error


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "baseremote_settings",
        handle_settings,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("operation"): vol.In(("set_color", "set_group", "remove_group")),
                vol.Optional("group"): cv.string,
                vol.Optional("rgb_color"): vol.All(
                    vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
                ),
                **SIDE_FIELD,
            }
        ),
    )
