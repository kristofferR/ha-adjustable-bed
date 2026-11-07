"""Solace (MotionFlex) audio and alarm actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .services import (
    ATTR_ACTION,
    ATTR_ENABLED,
    ATTR_MASSAGE,
    ATTR_MODE,
    ATTR_SOUND,
    ATTR_TIME,
    ATTR_TRACK,
    ATTR_VOLUME,
    ATTR_WEEKDAYS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_SOLACE_AUDIO = "solace_audio"
SERVICE_SOLACE_SET_ALARM = "solace_set_alarm"
SOLACE_AUDIO_ACTIONS = ("select", "preview", "query", "set_volume")
SOLACE_ALARM_MODES = ("zero_g", "memory_1", "no_action")
SOLACE_ALARM_SOUNDS = (
    "none",
    "alarm",
    "music_1",
    "music_2",
    "music_3",
    "music_4",
    "music_5",
)


async def handle_solace_audio(call: ServiceCall) -> None:
    """Control MotionFlex music selection, preview, query, or volume."""
    from .beds.solace import SolaceController

    action = call.data[ATTR_ACTION]
    track = call.data.get(ATTR_TRACK)
    volume = call.data.get(ATTR_VOLUME)
    if action in {"select", "preview"} and track is None:
        raise ServiceValidationError(f"Solace audio action '{action}' requires track")
    if action == "set_volume" and volume is None:
        raise ServiceValidationError("Solace audio action 'set_volume' requires volume")
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


async def handle_solace_set_alarm(call: ServiceCall) -> None:
    """Program the selected app profile's alarm packet family."""
    from .beds.solace import SolaceController

    weekday_numbers = tuple(
        SOLACE_WEEKDAY_OPTIONS.index(day) + 1 for day in call.data[ATTR_WEEKDAYS]
    )
    alarm_time = call.data[ATTR_TIME]

    def validate_sound(controller: SolaceController) -> None:
        if call.data[ATTR_SOUND] not in controller.solace_alarm_sound_options:
            raise ServiceValidationError(
                "This bed profile does not support the selected alarm sound"
            )

    async def program(controller: SolaceController) -> None:
        await controller.program_solace_alarm(
            enabled=call.data[ATTR_ENABLED],
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            weekdays=weekday_numbers,
            mode=call.data[ATTR_MODE],
            massage=call.data[ATTR_MASSAGE],
            sound=call.data[ATTR_SOUND],
        )

    await _preflight_and_execute(
        _call_targets(call),
        SolaceController,
        "Solace alarm programming",
        program,
        supported=lambda controller: controller.supports_solace_alarm,
        validate=validate_sound,
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SOLACE_SET_ALARM,
        handle_solace_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list,
                    [vol.In(SOLACE_WEEKDAY_OPTIONS)],
                ),
                vol.Optional(ATTR_MODE, default="no_action"): vol.In(SOLACE_ALARM_MODES),
                vol.Optional(ATTR_MASSAGE, default=False): cv.boolean,
                vol.Optional(ATTR_SOUND, default="alarm"): vol.In(SOLACE_ALARM_SOUNDS),
                **SIDE_FIELD,
            }
        ),
    )
