"""Octo PIN enrollment and factory reset actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import BED_TYPE_OCTO, CONF_OCTO_PIN, DOMAIN
from .octo_runtime import octo_controller
from .paired_coordinator import BedChild, SingleAddressSideCoordinator
from .services import (
    SIDE_FIELD,
    BedTarget,
    _call_targets,
    _command_targets,
    _execute_sided,
    _get_controller_for_service,
)

if TYPE_CHECKING:
    from .beds.base import BedController
    from .beds.octo import OctoController


SERVICE_OCTO_ENROLL_PIN = "octo_enroll_pin"
SERVICE_OCTO_RESET_DEFAULTS = "octo_reset_defaults"


async def _single_octo_service_target(
    call: ServiceCall,
) -> tuple[BedTarget, str, BedChild, OctoController]:
    """Connect and return exactly one physical Standard Octo target."""
    targets = _call_targets(call)
    if len(targets) != 1:
        raise ServiceValidationError("Select exactly one OCTO physical receiver")
    coordinator, side = targets[0]
    physical_targets = _command_targets(coordinator, side)
    if len(physical_targets) != 1:
        raise ServiceValidationError(
            "Select one paired side for this OCTO action",
            translation_domain=DOMAIN,
            translation_key="octo_single_side_required",
        )
    target = physical_targets[0]
    if target.bed_type != BED_TYPE_OCTO:
        raise ServiceValidationError("This action is only available for OCTO Smart Control")

    candidate = target.capability_controller
    if candidate is not None and octo_controller(candidate) is None:
        raise ServiceValidationError("This action is not available for the selected OCTO variant")
    controller = await _get_controller_for_service(target)
    octo = octo_controller(controller)
    if octo is None:
        raise ServiceValidationError("This action is not available for the selected OCTO variant")
    return coordinator, side, target, octo


async def handle_octo_enroll_pin(call: ServiceCall) -> None:
    """Enroll a matching four-digit PIN on one unlocked OCTO receiver."""
    pin = call.data[CONF_OCTO_PIN]
    confirmation = call.data["octo_pin_confirmation"]
    if not isinstance(pin, str) or len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
        raise ServiceValidationError("OCTO PIN must contain exactly four ASCII digits")
    if pin != confirmation:
        raise ServiceValidationError("OCTO PIN entries do not match")

    coordinator, side, target, _controller = await _single_octo_service_target(call)
    enrollment_completed = False

    async def enroll(controller: BedController) -> None:
        nonlocal enrollment_completed
        octo = octo_controller(controller)
        if octo is None:
            raise ServiceValidationError(
                "This action is not available for the selected OCTO variant"
            )
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
            raise ServiceValidationError(
                "OCTO PIN enrollment was cancelled before the PIN was sent"
            )
    except (PermissionError, ValueError) as err:
        raise ServiceValidationError(str(err)) from err

    physical_coordinator = (
        target._single_inner if isinstance(target, SingleAddressSideCoordinator) else target
    )
    physical_coordinator._octo_pin = pin
    entry = target.entry
    data = {**entry.data, CONF_OCTO_PIN: pin}
    if isinstance(entry, ConfigEntry):
        call.hass.config_entries.async_update_entry(entry, data=data)
    else:
        from .coordinator import ChildEntryView

        if not isinstance(entry, ChildEntryView):
            raise ServiceValidationError("Could not persist the OCTO PIN for this receiver")
        entry.persist_data(data, keys=(CONF_OCTO_PIN,))


async def handle_octo_reset_defaults(call: ServiceCall) -> None:
    """Reset one unlocked OCTO receiver after explicit user confirmation."""
    if call.data.get("confirmed") is not True:
        raise ServiceValidationError("Confirm the OCTO factory reset before continuing")
    coordinator, side, _target, _controller = await _single_octo_service_target(call)

    async def reset(controller: BedController) -> None:
        octo = octo_controller(controller)
        if octo is None:
            raise ServiceValidationError(
                "This action is not available for the selected OCTO variant"
            )
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
        raise ServiceValidationError(str(err)) from err


def async_register_octo_services(hass: HomeAssistant) -> None:
    """Register the Octo PIN enrollment and factory reset actions."""
    octo_target_fields = {
        vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
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
