"""Public Bedgear settings, admitted and serialized through the coordinator."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(
        ("rgb", "light_timer", "alarm", "sync_mode", "toggle_sync", "save_snore", "save_memory")
    ),
    vol.Optional("rgb"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    vol.Optional("brightness", default=1): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
    vol.Optional("minutes", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=1439)),
    vol.Optional("time"): vol.All(cv.string, vol.Match(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")),
    vol.Optional("strength"): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
    vol.Optional("wired", default=False): cv.boolean,
    vol.Optional("confirm", default=False): cv.boolean,
    vol.Optional("slot", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=2)),
    vol.Optional("recall_on_release", default=False): cv.boolean,
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)


async def handle(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.bedgear.controller")
    from .controller import BedgearController, Request

    try:
        request = Request(
            **{key: value for key, value in call.data.items() if key not in ("device_id", "side")}
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    if request.operation == "rgb" and request.rgb is None:
        raise ServiceValidationError("RGB requires three color channels")
    await _preflight_and_execute(
        _call_targets(call),
        BedgearController,
        "Bedgear",
        lambda controller: controller.configure(request),
        validate=lambda controller: controller.validate_request(request),
        cancel_running=True,
        admit=True,
    )


def async_register_bedgear_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "bedgear", handle, schema=SCHEMA)
