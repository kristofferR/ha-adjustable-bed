"""Profile-gated Comfort Enhancement 3 wake-up and relative massage actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute

    async def execute(call: ServiceCall) -> None:
        await async_import_modules(call.hass, "beds.comfort_enhancement3.controller")
        from ...codec.okin_nframe import schedule_step
        from .controller import ComfortEnhancement3Controller, selected_time, validate_massage

        operation = call.service
        effects = {
            k: call.data[k]
            for k in ("massage", "duration", "intensity", "kind", "light", "preset")
            if k in call.data
        }
        target = None
        if operation == "comfort_enhancement3_set_wakeup":
            time = call.data["time"]
            if time.second or time.microsecond:
                from homeassistant.exceptions import ServiceValidationError

                raise ServiceValidationError("Wake-up time uses minute precision")
            target = selected_time(dt_util.now(), time.hour, time.minute, call.data["next_day"])

        def validate(controller: ComfortEnhancement3Controller) -> None:
            if operation == "comfort_enhancement3_set_wakeup":
                assert target is not None
                controller.validate_wakeup(call.data["slot"], target, **effects)
            elif operation == "comfort_enhancement3_delete_wakeup":
                schedule_step(call.data["slot"], 0, 0, 0, 0)
            else:
                validate_massage(call.data["duration"], call.data["intensity"], call.data["kind"])
                if not controller.remote.massage:
                    raise ValueError("Main massage is unavailable for this remote")

        async def apply(controller: ComfortEnhancement3Controller) -> None:
            if operation == "comfort_enhancement3_set_wakeup":
                assert target is not None
                await controller.set_wakeup(call.data["slot"], target, **effects)
            elif operation == "comfort_enhancement3_delete_wakeup":
                await controller.delete_wakeup(call.data["slot"])
            else:
                await controller.start_massage(
                    call.data["duration"], call.data["intensity"], call.data["kind"]
                )

        await _preflight_and_execute(
            _call_targets(call),
            ComfortEnhancement3Controller,
            "Comfort Enhancement 3",
            apply,
            validate=validate,
            cancel_running=True,
            resource="*",
            admit=True,
        )

    massage: dict[object, object] = {
        vol.Optional("duration", default=10): vol.All(vol.Coerce(int), vol.In((10, 20, 30))),
        vol.Optional("intensity", default=1): vol.In((1, 2, 3)),
        vol.Optional("kind", default="head"): vol.In(("head", "feet", "both", "wave")),
    }
    common: dict[object, object] = {vol.Required("device_id"): DEVICE_IDS, **SIDE_FIELD}
    # These are text-width limits only. The app/SQLite proves no bed capacity.
    slot: dict[object, object] = {vol.Required("slot"): vol.All(int, vol.Range(min=0, max=99))}
    schemas: tuple[tuple[str, dict[object, object]], ...] = (
        (
            "comfort_enhancement3_set_wakeup",
            {
                **slot,
                **massage,
                vol.Required("time"): cv.time,
                vol.Optional("next_day", default=False): cv.boolean,
                vol.Optional("massage", default=False): cv.boolean,
                vol.Optional("light", default=False): cv.boolean,
                vol.Optional("preset", default="None"): vol.In(
                    ("None", "M1", "M2", "Zero Gravity", "TV", "QS")
                ),
            },
        ),
        ("comfort_enhancement3_delete_wakeup", slot),
        ("comfort_enhancement3_start_massage", massage),
    )
    for name, fields in schemas:
        hass.services.async_register(DOMAIN, name, execute, schema=vol.Schema({**common, **fields}))
