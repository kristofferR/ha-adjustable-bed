"""Leggett Okin sleep and alarm timer actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild
from ...services import (
    ATTR_ACTION,
    ATTR_MINUTES,
    ATTR_PRESET,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _execute_preflighted,
    _family_command,
    _leggett_integer,
    _preflight_each,
)
from ..base import BedController, controller_as

SERVICE_LEGGETT_SLEEP_TIMER = "leggett_sleep_timer"


async def handle_leggett_sleep_timer(call: ServiceCall) -> None:
    """Start or cancel the profile's delayed-preset timer on every validated target."""
    await async_import_modules(call.hass, "beds.leggett.okin")
    from .okin import LeggettOkinController

    start = call.data[ATTR_ACTION] == "start"
    minutes = call.data.get(ATTR_MINUTES)
    if start and minutes is None:
        from ...services import _invalid

        raise _invalid("timer_minutes_required")
    memory_num = call.data.get(ATTR_PRESET, 1)
    label = "Leggett sleep timers"

    def check(target: BedChild, controller: BedController) -> None:
        leggett = controller_as(controller, LeggettOkinController)
        if leggett is None or not leggett.supports_sleep_timer:
            raise invalid("feature_not_supported", device_name=target.name, feature=label)
        if not start:
            return
        if memory_num not in leggett.sleep_timer_memory_options:
            raise invalid("feature_not_supported", device_name=target.name, feature=f"sleep action {memory_num}")
        options = leggett.sleep_timer_duration_options
        if options and minutes not in options:
            raise invalid("choose_one_of", device_name=target.name, options=", ".join(map(str, options)) + " minutes")

    async def timer(controller: LeggettOkinController) -> None:
        if start:
            assert minutes is not None
            await controller.set_sleep_timer(minutes, memory_num)
        else:
            await controller.cancel_sleep_timer()

    targets = _call_targets(call)
    preflighted = await _preflight_each(targets, check)
    await _execute_preflighted(
        targets, preflighted, _family_command(LeggettOkinController, label, timer)
    )


def async_register_leggett_okin_services(hass: HomeAssistant) -> None:
    """Register the Leggett Okin sleep timer action."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEGGETT_SLEEP_TIMER,
        handle_leggett_sleep_timer,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_ACTION): vol.In(("start", "cancel")),
                vol.Optional(ATTR_MINUTES): vol.All(_leggett_integer, vol.Range(min=1, max=1439)),
                vol.Optional(ATTR_PRESET, default=1): vol.All(
                    _leggett_integer, vol.Range(min=0, max=4)
                ),
                **SIDE_FIELD,
            }
        ),
    )
