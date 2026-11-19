"""Octo PIN enrollment and factory reset actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import BED_TYPE_OCTO, CONF_OCTO_PIN, DOMAIN
from ...errors import invalid, rejected
from ...paired_coordinator import BedChild
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _command_targets,
    _execute_sided,
    _get_controller_for_service,
    _release_preflighted,
)
from .runtime import octo_controller

if TYPE_CHECKING:
    from ..base import BedController
    from .controller import OctoController


SERVICE_OCTO_ENROLL_PIN = "octo_enroll_pin"
SERVICE_OCTO_RESET_DEFAULTS = "octo_reset_defaults"


async def _single_octo_service_target(
    call: ServiceCall,
) -> tuple[BedTarget, str, BedChild, OctoController]:
    """Connect and return exactly one physical Standard Octo target."""
    targets = _call_targets(call)
    if len(targets) != 1:
        raise invalid("one_bed_only")
    coordinator, side = targets[0]
    physical_targets = _command_targets(coordinator, side)
    if len(physical_targets) != 1:
        raise invalid("one_bed_only")
    target = physical_targets[0]
    if target.bed_type != BED_TYPE_OCTO:
        raise invalid("action_for_other_beds", beds="Octo Smart Control receivers")

    candidate = target.capability_controller
    if candidate is not None and octo_controller(candidate) is None:
        raise invalid("not_supported_by_bed", feature="this action")
    controller = await _get_controller_for_service(target)
    octo = octo_controller(controller)
    if octo is None:
        # The lookup may have connected without an idle timer; hand it one.
        await _release_preflighted([(coordinator, target)])
        raise invalid("not_supported_by_bed", feature="this action")
    return coordinator, side, target, octo


async def handle_octo_enroll_pin(call: ServiceCall) -> None:
    """Enroll a matching four-digit PIN on one unlocked OCTO receiver."""
    pin = call.data[CONF_OCTO_PIN]
    confirmation = call.data["octo_pin_confirmation"]
    if not isinstance(pin, str) or len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
        raise invalid("pin_invalid")
    if pin != confirmation:
        raise invalid("pin_mismatch")

    coordinator, side, target, _controller = await _single_octo_service_target(call)
    enrollment_completed = False

    async def enroll(controller: BedController) -> None:
        nonlocal enrollment_completed
        octo = octo_controller(controller)
        if octo is None:
            raise invalid("not_supported_by_bed", feature="this action")
        await octo.enroll_pin(pin)
        enrollment_completed = True

    try:
        await _execute_sided(
            coordinator,
            side,
            enroll,
            cancel_running=False,
            resource="configuration",
        )
        if not enrollment_completed:
            raise invalid("action_stopped")
    except (PermissionError, ValueError) as err:
        raise rejected(err) from err

    entry = target.entry
    data = {**entry.data, CONF_OCTO_PIN: pin}
    if isinstance(entry, ConfigEntry):
        call.hass.config_entries.async_update_entry(entry, data=data)
    else:
        from ...coordinator import ChildEntryView

        if not isinstance(entry, ChildEntryView):
            raise invalid("pin_not_saved")
        entry.persist_data(data, keys=(CONF_OCTO_PIN,))


async def handle_octo_reset_defaults(call: ServiceCall) -> None:
    """Reset one unlocked OCTO receiver after explicit user confirmation."""
    if call.data.get("confirmed") is not True:
        raise invalid("confirmation_required", action="reset the receiver")
    coordinator, side, _target, _controller = await _single_octo_service_target(call)

    async def reset(controller: BedController) -> None:
        octo = octo_controller(controller)
        if octo is None:
            raise invalid("not_supported_by_bed", feature="this action")
        await octo.reset_defaults()

    try:
        await _execute_sided(
            coordinator,
            side,
            reset,
            cancel_running=False,
            resource="configuration",
        )
    except (PermissionError, ValueError) as err:
        raise rejected(err) from err


def async_register_octo_services(hass: HomeAssistant) -> None:
    """Register the Octo PIN enrollment and factory reset actions."""
    octo_target_fields = {
        vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_OCTO_ENROLL_PIN,
        handle_octo_enroll_pin,
        schema=vol.Schema(
            {
                **octo_target_fields,
                vol.Required(CONF_OCTO_PIN): cv.string,
                vol.Required("octo_pin_confirmation"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_OCTO_RESET_DEFAULTS,
        handle_octo_reset_defaults,
        schema=vol.Schema(
            {
                **octo_target_fields,
                vol.Required("confirmed"): vol.All(cv.boolean, vol.In((True,))),
            }
        ),
    )
