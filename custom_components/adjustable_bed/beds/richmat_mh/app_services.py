"""Declared BED callers that need an explicit service beyond native entities."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _preflight_and_execute,
)
from . import protocol
from .services import ALARM_SCHEMA

SERVICE = "richmat_mh_control"
MODE_ALARM_SERVICE = "richmat_mh_mode_alarm"
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
    vol.Required("action"): vol.In(("press", "remote_long", "voice_queue", "query", "app_mode")),
    vol.Optional("opcode"): cv.byte,
    vol.Optional("query"): vol.In(tuple(QUERIES)),
    # The app's local pickers, applied by later commands; "app_mode" sends nothing itself.
    vol.Optional("transmit_mode"): vol.In(("0", "1", "2")),
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
    opcode = int(call.data["opcode"]) if "opcode" in call.data else None
    query = str(call.data["query"]) if "query" in call.data else None
    transmit_mode: str | None = call.data.get("transmit_mode")
    group = call.data.get("motor_group")
    motor_group = str(group).upper() if group is not None else None
    if action == "app_mode":
        if opcode is not None or query is not None or (transmit_mode is None and motor_group is None):
            raise ServiceValidationError("Choose a transmit mode or motor group")
    elif transmit_mode is not None or motor_group is not None:
        raise ServiceValidationError("Transmit mode and motor group belong to the app_mode action")
    elif (action == "query" and (query is None or opcode is not None)) or (
        action != "query" and (opcode is None or query is not None)
    ):
        raise ServiceValidationError("Choose one query or one declared control opcode")
    await async_import_modules(call.hass, "beds.richmat_mh.app_controller")
    from .app_controller import RichmatMHAppController

    def validate(controller: RichmatMHAppController) -> None:
        if action == "app_mode":
            if motor_group is not None and motor_group not in controller.motor_groups:
                raise ValueError("Choose a motor group this model declares")
        elif action != "query":
            assert opcode is not None
            if action == "voice_queue":
                controller.validate_voice(opcode)
            else:
                controller.validate_control(opcode, remote_long=action == "remote_long")

    async def execute(controller: RichmatMHAppController) -> None:
        if action == "app_mode":
            if transmit_mode is not None:
                controller.set_transmit_mode(transmit_mode)
            if motor_group is not None:
                controller.set_group_type(motor_group)
        elif action == "query":
            assert query is not None
            controller._classifier.rx_type = "INIT"
            await controller.write_command(QUERIES[query])
        else:
            assert opcode is not None
            if action == "remote_long":
                await controller.remote_long(opcode)
            elif action == "voice_queue":
                await controller.voice_queue(opcode)
            else:
                await controller.tap(opcode)

    await _preflight_and_execute(
        targets, RichmatMHAppController, "Nisco / MLILY Supreme BED controls", execute,
        validate=validate, cancel_running=action not in ("query", "app_mode"), resource=None,
        admit=True, admissions=admissions,
    )


async def handle_mode_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side, ("configuration",)) for parent, side in targets]
    enabled: bool = call.data["enabled"]
    position: str | None = call.data.get("position")
    massage: list[str] = call.data["massage"]
    when = call.data.get("time")
    if enabled and when is None:
        raise ServiceValidationError("Setting an alarm requires a time")
    if when is not None and (when.second or when.microsecond):
        raise ServiceValidationError("This alarm uses minute precision")
    if call.data.get("slot") is not None:
        raise ServiceValidationError("The ModeFrag caller has no alarm-slot field")
    await async_import_modules(call.hass, "beds.richmat_mh.app_controller")
    from .app_controller import RichmatMHAppController

    async def execute(controller: RichmatMHAppController) -> None:
        minutes = 0
        if enabled and when is not None:
            now = dt_util.now()
            minutes = protocol.alarm_countdown_minutes(when.hour * 60 + when.minute, now.hour * 60 + now.minute)
        await controller.mode_alarm(enabled, minutes, position, massage)

    await _preflight_and_execute(
        targets, RichmatMHAppController, "Nisco ModeFrag alarm", execute,
        validate=lambda ctrl: ctrl.validate_mode_alarm(enabled, position, massage),
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
    hass.services.async_register(DOMAIN, MODE_ALARM_SERVICE, handle_mode_alarm, schema=ALARM_SCHEMA)
    hass.services.async_register(DOMAIN, SLEEP_MODE_SERVICE, handle_sleep_mode, schema=SLEEP_SCHEMA)
