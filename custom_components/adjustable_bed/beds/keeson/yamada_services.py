"""Explicit Yamada bed alarm slots; validate every target before any write."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("Expected an integer")
    return value


async def handle_set_alarm(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.keeson.yamada")
    from .yamada import AlarmPlan, YamadaController

    time = call.data["time"]
    if time.second or time.microsecond:
        raise ServiceValidationError("アシステック alarms use minute precision")
    plans: dict[YamadaController, AlarmPlan] = {}

    def prepare(controller: YamadaController) -> None:
        try:
            plans[controller] = controller.prepare_alarm(
                slot=call.data["slot"],
                enabled=call.data["enabled"],
                hour=time.hour,
                minute=time.minute,
                weekday=call.data["weekday"],
                preset=call.data["preset"],
            )
        except ConnectionError as err:
            raise ServiceValidationError(
                "Refresh bed alarms on each target's current connection first"
            ) from err

    async def configure(controller: YamadaController) -> None:
        plan = plans.get(controller)
        if plan is None:
            raise ServiceValidationError(
                "The bed session changed after validation; refresh its alarms"
            )
        await controller.set_alarm(plan)

    await _preflight_and_execute(
        _call_targets(call),
        YamadaController,
        "アシステック bed alarms",
        configure,
        validate=prepare,
        admit=True,
    )


def async_register_yamada_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "yamada_set_alarm",
        handle_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("slot"): vol.All(_integer, vol.In((1, 2))),
                vol.Required("enabled"): cv.boolean,
                vol.Required("time"): cv.time,
                vol.Required("weekday"): vol.All(_integer, vol.Range(min=0, max=255)),
                vol.Required("preset"): vol.In(("memory_1", "anti_snore", "zero_g", "tv", "flat")),
                **SIDE_FIELD,
            }
        ),
    )
