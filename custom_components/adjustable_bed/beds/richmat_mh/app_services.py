"""Declared BED callers that need an explicit service beyond native entities."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import invalid
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _preflight_and_execute,
)
from ..base import controller_as
from . import protocol

SERVICE = "richmat_mh_control"
SLEEP_MODE_SERVICE = "richmat_mh_sleep_mode"
QUERIES = {
    "version": protocol.TX_VERSION,
    "exit_one_minute": protocol.TX_EXIT_ONE_MIN,
    "alarm": protocol.TX_ALARM,
    "light": protocol.TX_LED,
    "mattress": protocol.TX_MATTRESS,
    "waist_mattress": protocol.TX_WAIST_MATTRESS,
    "snore": protocol.TX_SNORE,
    "diagnostics": protocol.TX_DETECTION,
    "motor_mode": protocol.TX_MOTOR_MODE,
    **{f"motor{index}_angle": frame for index, frame in enumerate(protocol.TX_MOTOR_ANGLES, 1)},
    "massage": protocol.TX_QUERY_MASSAGE,
    "light_lock": protocol.TX_QUERY_UBL_LOCK,
}
_FIELDS: dict[vol.Marker, object] = {
    vol.Required("device_id"): DEVICE_IDS,
    vol.Required("action"): vol.In(("press", "remote_long", "query", "app_mode")),
    # A control's name, as its button shows it; each model resolves its own.
    vol.Optional("control"): cv.string,
    vol.Optional("query"): vol.In(tuple(QUERIES)),
    # The app's local pickers, applied by later commands; "app_mode" sends nothing itself.
    vol.Optional("transmit_mode"): vol.In(("mode_0", "mode_1", "mode_2")),
    vol.Optional("motor_group"): vol.In(("single", "group_sync", "group_split")),
}
_FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(_FIELDS)
_SLEEP_FIELDS: dict[vol.Marker, object] = {
    vol.Required("device_id"): DEVICE_IDS,
    vol.Required("mode"): vol.In(("single", "double")),
}
_SLEEP_FIELDS.update(SIDE_FIELD.items())
SLEEP_SCHEMA = vol.Schema(_SLEEP_FIELDS)


async def handle_control(call: ServiceCall) -> None:
    targets = _call_targets(call)
    # Capture every physical owner and STOP epoch before the first lazy import.
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    action = str(call.data["action"])
    control = str(call.data["control"]) if "control" in call.data else None
    query = str(call.data["query"]) if "query" in call.data else None
    mode = call.data.get("transmit_mode")
    transmit_mode = str(mode).removeprefix("mode_") if mode is not None else None
    group = call.data.get("motor_group")
    motor_group = str(group).upper() if group is not None else None
    if action == "app_mode":
        if control is not None or query is not None or (transmit_mode is None and motor_group is None):
            raise invalid("field_required", field="a transmit mode or motor group")
    elif transmit_mode is not None or motor_group is not None:
        raise invalid("field_not_used", field="the transmit mode and motor group")
    elif (action == "query" and (query is None or control is not None)) or (
        action != "query" and (control is None or query is not None)
    ):
        raise invalid("field_required", field="a setting to read, or a control to run")
    await async_import_modules(call.hass, "beds.richmat_mh.app_controller")
    from .app_controller import RichmatMHAppController

    if action == "app_mode":
        # Local pickers: set them on each side's live or offline controller without
        # entering the BLE scheduler, so a write already waiting reads the new mode.
        controllers: list[RichmatMHAppController] = []
        for parent, side in targets:
            for target in _command_targets(parent, side):
                controller = controller_as(target.capability_controller, RichmatMHAppController)
                if controller is None:
                    raise invalid("action_for_other_beds", beds="Nisco and MLILY Supreme beds")
                if motor_group is not None and motor_group not in controller.motor_groups:
                    raise invalid("feature_not_supported", device_name=target.name, feature=f"the {group} motor group")
                controllers.append(controller)
        for controller in controllers:
            if transmit_mode is not None:
                controller.set_transmit_mode(transmit_mode)
            if motor_group is not None:
                controller.set_group_type(motor_group)
        return

    def validate(controller: RichmatMHAppController) -> None:
        if action != "query":
            assert control is not None
            code = controller.control_named(control)
            controller.validate_control(code, remote_long=action == "remote_long")

    async def execute(controller: RichmatMHAppController) -> None:
        if action == "query":
            assert query is not None
            controller._classifier.rx_type = "INIT"
            await controller.write_command(QUERIES[query])
        else:
            assert control is not None
            code = controller.control_named(control)
            if action == "remote_long":
                await controller.remote_long(code)
            else:
                await controller.tap(code)

    await _preflight_and_execute(
        targets, RichmatMHAppController, "Nisco / MLILY Supreme BED controls", execute,
        validate=validate, cancel_running=action != "query", resource=None,
        admit=True, admissions=admissions,
    )


async def handle_sleep_mode(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side, ("configuration",)) for parent, side in targets]
    option: str = call.data["mode"]
    await async_import_modules(call.hass, "beds.richmat_mh.app_sleep")
    from .app_sleep import RichmatMHAppSleepController

    await _preflight_and_execute(
        targets, RichmatMHAppSleepController, "Nisco direct sleep-user-mode caller",
        lambda ctrl: ctrl.direct_user_mode(option),
        validate=lambda ctrl: ctrl.validate_direct_user_mode(option),
        admit=True, admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, SERVICE, handle_control, schema=SCHEMA)
    hass.services.async_register(DOMAIN, SLEEP_MODE_SERVICE, handle_sleep_mode, schema=SLEEP_SCHEMA)
