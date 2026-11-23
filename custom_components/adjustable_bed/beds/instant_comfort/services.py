"""Set a sleeper's main and lumbar pressure in one admitted operation."""

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def set_firmness(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [_capture_command_admission(parent, side, ("*",)) for parent, side in targets]
        await async_import_modules(call.hass, "beds.instant_comfort.air")
        from .air import InstantComfortAir

        main = call.data.get("firmness")
        lumbar = call.data.get("lumbar_firmness")
        await _preflight_and_execute(
            targets,
            InstantComfortAir,
            lambda controller: controller.set_pressures(call.data["sleeper"], main, lumbar),
            validate=lambda controller: controller.validate_pressure_targets(main, lumbar),
            cancel_running=True,
            resource="*",
            admit=True,
            admissions=admissions,
        )

    hass.services.async_register(
        DOMAIN,
        "instant_comfort_firmness",
        set_firmness,
        schema=vol.Schema(
            {
                vol.Required("device_id"): DEVICE_IDS,
                vol.Required("sleeper"): vol.In(("left", "right")),
                vol.Optional("firmness"): vol.All(vol.Coerce(float), vol.Range(min=5, max=50)),
                vol.Optional("lumbar_firmness"): vol.All(
                    vol.Coerce(float), vol.Range(min=5, max=50)
                ),
            }
        ),
    )
