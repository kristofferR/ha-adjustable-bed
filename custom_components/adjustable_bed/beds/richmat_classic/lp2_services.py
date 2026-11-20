"""Direct bed settings for the L&P Adjustable Base profile."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid, rejected
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, PairedBedCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _release_preflighted,
    _Selection,
)
from ..base import BedController
from .resource_protocol import BED_COMMANDS
from .rise import Schedule
from .rise_services import SCHEDULE

FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(
        (
            "color",
            "light_duration",
            "aromatherapy",
            "fan",
            "motor_program",
            "movement_test",
            "control",
        )
    ),
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=300)),
    vol.Optional("aroma_times"): vol.All(
        vol.ExactSequence((cv.positive_int, cv.positive_int, cv.positive_int)), vol.Coerce(tuple)
    ),
    vol.Optional("fan"): vol.In(("head", "foot")),
    vol.Optional("intensity"): vol.All(cv.positive_int, vol.In((0, 20, 40, 60, 80, 100))),
    vol.Optional("duration"): vol.All(cv.positive_int, vol.Range(max=6)),
    vol.Optional("schedule"): SCHEDULE,
    vol.Optional("confirm", default=False): cv.boolean,
    vol.Optional("control"): cv.positive_int,
    vol.Optional("mode", default=0): vol.All(cv.positive_int, vol.In((0, 1, 2))),
    vol.Optional("long", default=False): cv.boolean,
    vol.Optional("held", default=False): cv.boolean,
    vol.Optional("head", default=True): cv.boolean,
    vol.Optional("motor", default=3): vol.All(cv.positive_int, vol.In((3, 4, 5))),
    vol.Optional("duration_ms", default=1000): vol.All(
        cv.positive_int, vol.Range(min=1, max=60000)
    ),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_settings(call: ServiceCall) -> None:
    data = call.data
    op = data["operation"]
    movement = op in ("control", "motor_program", "movement_test", "bed_command")
    resource = "movement" if movement else "configuration"
    targets = _call_targets(call)
    selection = _Selection.capture(targets)
    admissions = [
        _capture_command_admission(coordinator, side, (resource,)) for coordinator, side in targets
    ]
    await async_import_modules(call.hass, "beds.richmat_classic.lp2", "beds.richmat_classic.bedsmart")
    from .bedsmart import BedSmartController
    from .lp2 import Lp2Controller

    required = {
        "color": ("rgb_color",),
        "light_duration": ("seconds",),
        "aromatherapy": ("aroma_times",),
        "fan": ("fan", "intensity", "duration"),
        "motor_program": ("schedule",),
        "movement_test": (),
        "control": ("control",),
        "bed_command": ("command",),
    }[op]

    def validate(controller: Lp2Controller) -> None:
        if isinstance(controller, BedSmartController) != (call.service == "bedsmart"):
            raise invalid("bed_changed")
        if any(key not in data for key in required):
            raise ValueError("Provide every parameter for the chosen bed setting")
        if op == "bed_command":
            if not isinstance(controller, BedSmartController) or data["command"] not in BED_COMMANDS:
                raise invalid("bedsmart_control")
        elif op == "motor_program":
            if not data["confirm"] or controller.layout != "RMCS":
                raise ValueError("Choose the motor program layout and confirm programming")
            controller.schedule_frame(Schedule(**data["schedule"]))
        elif op == "movement_test":
            if not data["confirm"] or controller.layout != "TEST":
                raise ValueError("Choose the movement-test layout and confirm the test")
        elif op == "control":
            if data["mode"] not in controller._model.modes:
                raise ValueError("Choose a mode offered by the selected layout")
            gestures = controller.validate_action(
                data["control"],
                long=data["long"],
                held=data["held"],
                head=data["head"],
                flag="5" + str(data["motor"]),
            )
            if (data["long"] or any(g.saves for g in gestures)) and not data["confirm"]:
                raise ValueError("Confirm the save or long press before sending it")
        elif op == "aromatherapy" and not all(
            1 <= n <= limit for n, limit in zip(data["aroma_times"], (60, 60, 12), strict=True)
        ):
            raise ValueError("Choose supported aromatherapy times")

    started = False

    def validate_live(controller: Lp2Controller) -> None:
        if op in ("color", "light_duration") and not controller._receive.light_capable:
            raise ValueError("The bed must report lighting support before changing lighting")
        if op == "aromatherapy" and not controller._receive.aroma_capable:
            raise ValueError("The bed must report aromatherapy support before changing it")

    def check_batch(*, before_admission: bool = True) -> bool:
        selection.require_unchanged(call)
        return not selection.stopped() and (
            not before_admission
            or all(
                _capture_command_admission(parent, side, admission.resources) == admission
                for (parent, side), admission in zip(targets, admissions, strict=True)
            )
        )

    async def execute(controller: Lp2Controller) -> None:
        nonlocal started
        # Native paired admission advances its own generation. It already
        # validated that generation; still fence every selected owner and STOP.
        if not started and not check_batch(before_admission=False):
            return
        validate(controller)
        if isinstance(controller, BedSmartController) and op in ("color", "light_duration", "aromatherapy"):
            await controller.ensure_feature(aroma=op == "aromatherapy")
            if not check_batch(before_admission=False):
                return
        validate_live(controller)
        started = True
        if op == "bed_command":
            assert isinstance(controller, BedSmartController)
            await controller.bed_command(data["command"], data["duration_ms"])
        elif op == "motor_program":
            await controller.program_schedule(Schedule(**data["schedule"]))
        elif op == "movement_test":
            await controller.diagnostic_cycle()
        elif op == "control":
            await controller.execute_action(
                data["control"],
                mode=data["mode"],
                long=data["long"],
                held=data["held"],
                head=data["head"],
                flag="5" + str(data["motor"]),
                hold_ms=data["duration_ms"],
            )
        elif op == "color":
            await controller.settings(color=cast(tuple[int, int, int], data["rgb_color"]))
        elif op == "light_duration":
            await controller.settings(seconds=data["seconds"])
        elif op == "aromatherapy":
            await controller.settings(aroma_times=cast(tuple[int, int, int], data["aroma_times"]))
        else:
            await controller.settings(
                fan=data["fan"], level=data["intensity"], duration=data["duration"]
            )

    preflighted = await _preflight_capability(
        targets,
        Lp2Controller,
        "Bed settings",
        validate=validate,
    )
    try:
        if op in ("color", "light_duration", "aromatherapy"):
            for parent, side in targets:
                for target in _command_targets(parent, side):
                    if not check_batch():
                        return
                    refreshed = False

                    async def query(controller: BedController) -> bool:
                        if not isinstance(controller, Lp2Controller):
                            raise invalid("bed_changed")
                        if isinstance(controller, BedSmartController):
                            await controller.ensure_feature(aroma=op == "aromatherapy")
                        validate_live(controller)
                        return True

                    async def inspect(child: BedChild) -> None:
                        nonlocal refreshed
                        refreshed = (
                            await child.async_execute_controller_query(
                                query,
                                cancel_running=False,
                            )
                            is True
                        )

                    if isinstance(parent, PairedBedCoordinator):
                        child_side = next(
                            key for key, child in parent.children.items() if child is target
                        )
                        await parent.async_run_child_operation(
                            "Bed settings preflight",
                            inspect,
                            side=child_side,
                            cancel_running=False,
                        )
                    else:
                        await inspect(target)
                    if not refreshed:
                        raise invalid("action_stopped")
        if not check_batch():
            return
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(Lp2Controller, "Bed settings", execute),
            cancel_running=movement,
            resource=resource,
            admissions=admissions,
        )
    except ValueError as error:
        raise rejected(error) from error
    finally:
        if not started:
            await _release_preflighted(preflighted)


def async_register_lp2_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "lp2", handle_settings, schema=vol.Schema(FIELDS))
    bedsmart = {
        key: value for key, value in FIELDS.items()
        if key.schema in (CONF_DEVICE_ID, "operation", "rgb_color", "seconds", "aroma_times", "confirm", "side", "duration_ms")
    }
    bedsmart[vol.Required("operation")] = vol.In(("color", "light_duration", "aromatherapy", "movement_test", "bed_command"))
    bedsmart[vol.Optional("command")] = vol.In(BED_COMMANDS)
    hass.services.async_register(DOMAIN, "bedsmart", handle_settings, schema=vol.Schema(bedsmart))
