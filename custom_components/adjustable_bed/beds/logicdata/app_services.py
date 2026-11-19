"""Logicdata app alarm and held-preset actions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    ATTR_DURATION,
    ATTR_PRESET,
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _preflight_and_execute,
)

SERVICE_LOGICDATA_HOLD_PRESET = "logicdata_hold_preset"
LOGICDATA_HOLD_PRESETS = ("flat", "zero_g", "anti_snore", "memory_1", "memory_2")


def _preset_hold_duration_seconds(value: object) -> Decimal:
    """Accept bounded seconds that convert exactly to whole milliseconds."""
    try:
        duration = Decimal(str(value))
    except InvalidOperation as err:
        raise vol.Invalid("Duration must be a number of seconds") from err
    if not duration.is_finite() or not Decimal("0.2") <= duration <= 60:
        raise vol.Invalid("Duration must be between 0.2 and 60 seconds")
    milliseconds = int(duration * 1000)
    if duration != Decimal(milliseconds) / 1000:
        raise vol.Invalid("Duration must resolve to whole milliseconds")
    return duration


async def handle_logicdata_hold_preset(call: ServiceCall) -> None:
    """Hold a MOTIONrelax P2 or Sleep Smart preset through the cancellable command queue."""
    await async_import_modules(call.hass, "beds.logicdata.app")
    from .app import LogicdataAppController

    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    preset = call.data[ATTR_PRESET]

    def validate(controller: LogicdataAppController) -> None:
        if preset not in controller.held_preset_options:
            raise invalid("not_supported_by_bed", feature=f"holding the {preset} preset")

    await _preflight_and_execute(
        _call_targets(call),
        LogicdataAppController,
        "Logicdata held preset recall",
        lambda controller: controller.hold_preset(preset, duration_ms),
        supported=lambda controller: controller.supports_preset_hold,
        validate=validate,
        cancel_running=True,
        resource=None,
    )


def async_register_logicdata_app_services(hass: HomeAssistant) -> None:
    """Register the Logicdata app alarm and held-preset actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOGICDATA_HOLD_PRESET,
        handle_logicdata_hold_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_PRESET): vol.In(LOGICDATA_HOLD_PRESETS),
                vol.Required(ATTR_DURATION): _preset_hold_duration_seconds,
                **SIDE_FIELD,
            }
        ),
    )
