"""Solace (MotionFlex) audio and alarm actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    ATTR_SIDE,
    ATTR_SOUND,
    ATTR_TIME,
    ATTR_TRACK,
    ATTR_VOLUME,
    ATTR_WEEKDAYS,
    SIDE_FIELD,
    SOLACE_WEEKDAY_OPTIONS,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController


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
    action = call.data[ATTR_ACTION]
    track = call.data.get(ATTR_TRACK)
    volume = call.data.get(ATTR_VOLUME)
    if action in {"select", "preview"} and track is None:
        raise ServiceValidationError(f"Solace audio action '{action}' requires track")
    if action == "set_volume" and volume is None:
        raise ServiceValidationError("Solace audio action 'set_volume' requires volume")
    track_value = int(track) if track is not None else 0
    volume_value = int(volume) if volume is not None else 0

    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data.get(CONF_DEVICE_ID, []),
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_solace_audio",
        "Solace music/audio control",
    )

    async def control(controller: BedController | SideBoundController) -> None:
        if action == "query":
            await controller.solace_query_audio_volume()
        elif action == "set_volume":
            await controller.solace_set_audio_volume(volume_value)
        else:
            await controller.solace_select_music(
                track_value,
                preview=action == "preview",
            )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                control,
                cancel_running=False,
                skip_disconnect=action == "query",
                resource="audio",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_solace_set_alarm(call: ServiceCall) -> None:
    """Program the selected app profile's alarm packet family."""
    weekday_numbers = tuple(
        SOLACE_WEEKDAY_OPTIONS.index(day) + 1 for day in call.data[ATTR_WEEKDAYS]
    )
    alarm_time = call.data[ATTR_TIME]
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data.get(CONF_DEVICE_ID, []),
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])

    def validate_sound(controller: BedController | SideBoundController) -> None:
        if call.data[ATTR_SOUND] not in controller.solace_alarm_sound_options:
            raise ServiceValidationError(
                "This bed profile does not support the selected alarm sound"
            )

    preflighted = await _preflight_capability(
        targets,
        "supports_solace_alarm",
        "Solace alarm programming",
        validate_sound,
    )

    async def program(controller: BedController | SideBoundController) -> None:
        await controller.program_solace_alarm(
            enabled=call.data[ATTR_ENABLED],
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            weekdays=weekday_numbers,
            mode=call.data[ATTR_MODE],
            massage=call.data[ATTR_MASSAGE],
            sound=call.data[ATTR_SOUND],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                program,
                cancel_running=False,
                resource="configuration",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


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
