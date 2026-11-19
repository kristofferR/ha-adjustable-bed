"""Solace (MotionFlex) audio and alarm actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    ATTR_ACTION,
    ATTR_TRACK,
    ATTR_VOLUME,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_SOLACE_AUDIO = "solace_audio"
SOLACE_AUDIO_ACTIONS = ("select", "preview", "query", "set_volume")


async def handle_solace_audio(call: ServiceCall) -> None:
    """Control MotionFlex music selection, preview, query, or volume."""
    await async_import_modules(call.hass, "beds.solace.controller")
    from .controller import SolaceController

    action = call.data[ATTR_ACTION]
    track = call.data.get(ATTR_TRACK)
    volume = call.data.get(ATTR_VOLUME)
    if action in {"select", "preview"} and track is None:
        raise invalid("field_required", field="a track")
    if action == "set_volume" and volume is None:
        raise invalid("field_required", field="a volume")
    track_value = int(track) if track is not None else 0
    volume_value = int(volume) if volume is not None else 0


    async def control(controller: SolaceController) -> None:
        if action == "query":
            await controller.solace_query_audio_volume()
        elif action == "set_volume":
            await controller.solace_set_audio_volume(volume_value)
        else:
            await controller.solace_select_music(
                track_value,
                preview=action == "preview",
            )

    await _preflight_and_execute(
        _call_targets(call),
        SolaceController,
        "Solace music/audio control",
        control,
        supported=lambda controller: controller.supports_solace_audio,
        skip_disconnect=action == "query",
        resource="audio",
    )


def async_register_solace_services(hass: HomeAssistant) -> None:
    """Register the Solace audio and alarm actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SOLACE_AUDIO,
        handle_solace_audio,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_ACTION): vol.In(SOLACE_AUDIO_ACTIONS),
                vol.Optional(ATTR_TRACK): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
                vol.Optional(ATTR_VOLUME): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
                **SIDE_FIELD,
            }
        ),
    )
