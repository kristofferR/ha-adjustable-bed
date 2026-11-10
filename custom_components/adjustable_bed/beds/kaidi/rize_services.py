"""Explicit confirmation for Rize default-preset programming."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN, SIDE_LEFT, SIDE_RIGHT
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _execute_sided,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)


async def handle_rize_program_preset(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.kaidi.rize")
    from ...paired_coordinator import PairedBedCoordinator
    from .rize import RizeController

    targets = _call_targets(call)
    # E-AUDIT002: the app's Both confirmation writes one live global target,
    # not both nodes. Require a physical side instead of guessing or fan-out.
    if len(targets) != 1 or (
        isinstance(targets[0][0], PairedBedCoordinator) and targets[0][1] not in (SIDE_LEFT, SIDE_RIGHT)
    ):
        raise ServiceValidationError("Select one physical Rize bed or one paired side")
    preset, confirm = call.data["preset"], call.data["confirm"]
    label = "Rize default preset programming"
    preflighted = await _preflight_capability(
        targets, RizeController, label,
        validate=lambda c: c.validate_program_preset(preset, confirm),
    )
    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side,
                _family_command(RizeController, label, lambda c: c.program_preset(preset, confirm)),
                resource="configuration",
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_rize_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, "rize_program_preset", handle_rize_program_preset,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
            vol.Required("preset"): vol.In(("zero_g", "anti_snore", "book", "leisure")),
            vol.Required("confirm"): cv.boolean,
            **SIDE_FIELD,
        }),
    )
