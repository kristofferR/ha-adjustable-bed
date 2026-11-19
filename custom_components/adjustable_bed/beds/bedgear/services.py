"""Public Bedgear settings, admitted and serialized through the coordinator."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid, rejected
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _preflight_and_execute,
)

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
    await _handle(call, "bedgear")


async def handle_l2motion(call: ServiceCall) -> None:
    await _handle(call, "l2motion")


async def _handle(call: ServiceCall, app: str) -> None:
    targets = _call_targets(call)
    admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side in targets
    ]
    owners = [
        tuple(child.operation_identity for child in _command_targets(parent, side))
        for parent, side in targets
    ]
    await async_import_modules(call.hass, "beds.bedgear.controller")
    from .controller import BedgearController, Link, Request

    try:
        request = Request(
            **{key: value for key, value in call.data.items() if key not in ("device_id", "side")}
        )
    except ValueError as err:
        if app == "l2motion":
            raise invalid("l2motion_control_unavailable") from err
        raise rejected(err) from err
    if request.operation == "rgb" and request.rgb is None:
        if app == "l2motion":
            raise invalid("l2motion_control_unavailable")
        raise invalid("field_required", field="a color")

    validated: list[BedgearController] = []
    links: dict[BedgearController, Link | None] = {}
    merged: set[int] = set()
    color = app == "l2motion" and request.operation == "rgb"

    def validate(controller: BedgearController) -> None:
        if controller.profile.key != app:
            raise invalid("l2motion_control_unavailable")
        try:
            controller.validate_request(request)
        except ValueError as err:
            if app != "l2motion":
                raise
            raise invalid("l2motion_control_unavailable") from err

    def snapshot(controller: BedgearController) -> None:
        validate(controller)
        validated.append(controller)
        if color:
            # Capability validation must not open a link. A live session is
            # pinned; an offline request may connect when execution starts.
            try:
                links[controller] = controller._current()
            except ConnectionError:
                links[controller] = None

    def prepare() -> None:
        if owners != [
            tuple(child.operation_identity for child in _command_targets(parent, side))
            for parent, side in targets
        ]:
            raise invalid("l2motion_control_unavailable")
        for controller in validated:
            if (link := links[controller]) is not None:
                controller._check_link(link)
        for controller in validated:
            if controller.queue_color_update(request):
                merged.add(controller._coordinator.operation_identity)

    async def execute(controller: BedgearController) -> None:
        if controller._coordinator.operation_identity not in merged:
            if color:
                admitted = next(
                    (
                        item
                        for item in validated
                        if item._coordinator.operation_identity
                        == controller._coordinator.operation_identity
                    ),
                    None,
                )
                if admitted is None or admitted.profile != controller.profile:
                    raise invalid("l2motion_control_unavailable")
                if (link := links[admitted]) is not None:
                    controller._check_link(link)
            validate(controller)
            await controller.configure(request)

    await _preflight_and_execute(
        targets,
        BedgearController,
        "L2 Motion" if app == "l2motion" else "Bedgear",
        execute,
        validate=snapshot,
        cancel_running=not color,
        admit=True,
        admissions=admissions,
        prepare=prepare if color else None,
    )


def async_register_bedgear_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "bedgear", handle, schema=SCHEMA)
    fields = {
        key: value
        for key, value in FIELDS.items()
        if str(key) in ("device_id", "side", "rgb", "brightness", "wired", "confirm")
    }
    fields[vol.Required("operation")] = vol.In(("rgb", "sync_mode"))
    hass.services.async_register(DOMAIN, "l2motion", handle_l2motion, schema=vol.Schema(fields))
