"""Validated, named Motion Bed app configuration actions."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.base import BedController, SideBoundController
from .const import BED_TYPE_MOTION_BED, DOMAIN
from .motion_bed_protocol import (
    AirMode,
    AirTimer,
    AlarmMode,
    AlarmSound,
    AlarmSwitch,
    ModuleType,
    SleepPage,
    SleepReport,
    ThermalMode,
    build_air_query,
    build_air_save,
    build_alarm,
    build_audio_track,
    build_audio_volume,
    build_clock,
    build_module_bind,
    build_module_delete,
    build_module_query,
    build_pressure_live,
    build_pressure_save,
    build_sleep_angles,
    build_sleep_calibration,
    build_sleep_report,
    build_sleep_timer,
    build_thermal_clock,
    build_thermal_schedule,
)
from .motion_bed_requests import MotionBedWrite


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _text(data: Mapping[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def _boolean(data: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be Boolean")
    return value


def _integers(data: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = data[key]
    if not isinstance(value, (tuple, list)) or any(type(item) is not int for item in value):
        raise ValueError(f"{key} must be a list of integers")
    return tuple(value)




def build_motion_bed_request(service: str, data: Mapping[str, object]) -> MotionBedWrite:
    """Construct only one of the published domain-specific writes."""
    confirm = _boolean(data, "confirmed")
    if service == "motion_bed_alarm":
        selected = _integers(data, "weekdays")
        if any(day not in range(1, 8) for day in selected):
            raise ValueError("Weekdays use 1 (Monday) through 7 (Sunday)")
        weekdays = {day: day in selected for day in range(1, 8)} if _boolean(data, "repeat") else {}
        switch = AlarmSwitch(_integer(data, "switch")) if "switch" in data else None
        frame = build_alarm(enabled=_boolean(data, "enabled"), hour=_integer(data, "hour"),
                            minute=_integer(data, "minute"), weekdays=weekdays,
                            mode=AlarmMode(_integer(data, "mode")), massage=_boolean(data, "massage"),
                            sound=AlarmSound(_integer(data, "sound")), switch=switch,
                            audio=_boolean(data, "audio"))
        return MotionBedWrite("alarm", (frame,), "motor_settings" if "switch" in data else "home", confirmed=confirm, persistent=True, alarm_audio=_boolean(data, "audio"), alarm_switch=int(switch) if switch is not None else None)
    if service == "motion_bed_clock":
        timestamp = datetime.fromisoformat(_text(data, "timestamp"))
        frame = build_thermal_clock(timestamp) if _boolean(data, "thermal") else build_clock(timestamp)
        return MotionBedWrite("clock", (frame,), "thermal" if _boolean(data, "thermal") else "home")
    if service == "motion_bed_sleep_angles":
        frame = build_sleep_angles(SleepPage(_integer(data, "page")), _integers(data, "flat"), _integers(data, "side_positions"))
        return MotionBedWrite("sleep_angles", (frame,), "sleep_adjust", confirmed=confirm, persistent=True)
    if service == "motion_bed_calibration":
        frame = build_sleep_calibration(_integer(data, "flat"), _integer(data, "side_position"))
        return MotionBedWrite("calibration", (frame,), "calibration", confirmed=confirm, persistent=True)
    if service == "motion_bed_sleep_timer":
        return MotionBedWrite("sleep_timer", (build_sleep_timer(_integer(data, "slot"), fall=_boolean(data, "fall")),), "smart_sleep", confirmed=confirm, persistent=True)
    if service == "motion_bed_sleep_report":
        kind = SleepReport(_text(data, "kind"))
        offset = _integer(data, "offset")
        frame = build_sleep_report(kind, offset=offset)
        context = "month_report" if kind is SleepReport.MONTH else "day_report" if kind in (SleepReport.DAY, SleepReport.CURRENT) else "sleep_report"
        return MotionBedWrite("sleep_report", (frame,), context, report_offset=_integer(data, "window_offset") if "window_offset" in data else 0,
                              historical_day=kind is SleepReport.DAY)
    if service == "motion_bed_module":
        operation = _text(data, "operation")
        if operation == "query":
            frame = build_module_query()
        elif operation == "bind":
            frame = build_module_bind(ModuleType(_integer(data, "module_type")), _text(data, "address"))
        elif operation == "delete":
            frame = build_module_delete(ModuleType(_integer(data, "module_type")))
        else:
            raise ValueError("Module operation must be query, bind, or delete")
        return MotionBedWrite("module", (frame,), "module_binding" if operation == "bind" else "module_change", confirmed=confirm, persistent=operation != "query")
    if service == "motion_bed_air_setting":
        mode = AirMode(_integer(data, "mode"))
        if _boolean(data, "query"):
            return MotionBedWrite("air_setting", (build_air_query(mode),), "air_settings")
        timer = AirTimer(_integer(data, "timer")) if "timer" in data else None
        return MotionBedWrite("air_setting", (build_air_save(mode, _integer(data, "gear"), timer),), "air_settings", confirmed=confirm, persistent=True)
    if service == "motion_bed_pressure":
        if _text(data, "operation") == "save":
            return MotionBedWrite("pressure", (build_pressure_save(_integers(data, "values")),), "pressure_settings", confirmed=confirm, persistent=True)
        if _text(data, "operation") != "live":
            raise ValueError("Pressure operation must be live or save")
        frame = build_pressure_live(_integer(data, "channel"), _integer(data, "value"))
        # Source checks every 500ms and requires elapsed strictly greater than 2s.
        return MotionBedWrite("pressure", (frame,), "pressure_settings", initial_delay_ms=2500)
    if service == "motion_bed_thermal_schedule":
        frame = build_thermal_schedule(_integer(data, "hour"), _integer(data, "minute"), ThermalMode(_integer(data, "mode")), _integer(data, "gear"))
        return MotionBedWrite("thermal_schedule", (frame,), "thermal_schedule", confirmed=confirm, persistent=True)
    if service == "motion_bed_audio":
        if _text(data, "operation") == "volume":
            frame = build_audio_volume(_integer(data, "value"))
        elif _text(data, "operation") == "track":
            frame = build_audio_track(_integer(data, "value"), preview=_boolean(data, "preview"))
        else:
            raise ValueError("Audio operation must be track or volume")
        return MotionBedWrite("audio", (frame,), "preset")
    raise ValueError("Unknown Motion Bed configuration action")


async def _execute(call: ServiceCall, request: MotionBedWrite | None = None) -> None:
    # Shared targeting includes paired child routing and preflights every receiver.
    from .services import (
        ATTR_SIDE,
        CONF_DEVICE_ID,
        _command_targets,
        _execute_sided,
        _missing_device_error,
        _preflight_capability,
        _release_preflighted,
        _resolve_sided_targets,
    )
    targets, missing = _resolve_sided_targets(call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE))
    if missing:
        raise _missing_device_error(missing[0])
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            if target.bed_type != BED_TYPE_MOTION_BED:
                raise ServiceValidationError("Select a Motion Bed app device")
    def validate(controller: BedController | SideBoundController) -> None:
        if request is not None:
            controller.validate_motion_bed_write(request)
        else:
            controller.validate_motion_bed_action(call.data["action"], branch=call.data["branch"],
                duration=call.data["duration"], confirmed=call.data["confirmed"])
    async def execute(controller: BedController | SideBoundController) -> None:
        if request is not None:
            await controller.async_execute_motion_bed_write(request)
        else:
            await controller.async_execute_motion_bed_action(call.data["action"], branch=call.data["branch"],
                duration=call.data["duration"], confirmed=call.data["confirmed"])
    try:
        preflighted = await _preflight_capability(targets, "supports_motion_bed_actions", "Motion Bed app controls", validate)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, execute, resource="*")
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise


async def handle_motion_bed_action(call: ServiceCall) -> None:
    await _execute(call)


async def handle_motion_bed_configuration(call: ServiceCall) -> None:
    try:
        request = build_motion_bed_request(call.service, call.data)
    except (ValueError, KeyError) as err:
        raise ServiceValidationError(str(err)) from err
    await _execute(call, request)


def _reject_boolean(value: object) -> object:
    if isinstance(value, bool):
        raise vol.Invalid("Expected a number, not Boolean")
    return value


def async_register_motion_bed_services(hass: HomeAssistant) -> None:
    from .services import CONF_DEVICE_ID, SIDE_FIELD
    common = {vol.Required(CONF_DEVICE_ID): cv.ensure_list, **SIDE_FIELD,
              vol.Optional("confirmed", default=False): bool}
    required = vol.Required
    optional = vol.Optional
    integer_list = vol.All(cv.ensure_list, [int])
    schemas = {
        "motion_bed_action": {required("action"): str, optional("branch", default="app"): vol.In(("app", "save", "clear")), optional("duration", default=1): vol.All(vol.Coerce(float), vol.Range(min=0.01,max=10))},
        "motion_bed_alarm": {required("enabled"): bool, required("hour"): int, required("minute"): int, optional("weekdays",default=[]): integer_list, optional("repeat",default=False): bool, optional("mode",default=1): int, optional("massage",default=False): bool, optional("sound",default=0): int, optional("audio",default=False): bool, optional("switch"): int},
        "motion_bed_clock": {required("timestamp"): str, optional("thermal",default=False): bool},
        "motion_bed_sleep_angles": {required("page"): int, required("flat"): integer_list, required("side_positions"): integer_list},
        "motion_bed_calibration": {required("flat"): int, required("side_position"): int},
        "motion_bed_sleep_timer": {required("slot"): int, optional("fall",default=False): bool},
        "motion_bed_sleep_report": {required("kind"): vol.In(("month", "real", "timer", "day")), optional("offset",default=0): int, optional("window_offset",default=0): vol.All(int, vol.Range(min=0,max=4))},
        "motion_bed_module": {required("operation"): vol.In(("query", "bind", "delete")), optional("module_type"): int, optional("address"): str},
        "motion_bed_air_setting": {required("mode"): int, optional("query",default=False): bool, optional("gear"): int, optional("timer"): int},
        "motion_bed_pressure": {required("operation"): vol.In(("live", "save")), optional("channel"): int, optional("value"): int, optional("values"): integer_list},
        "motion_bed_thermal_schedule": {required("hour"): int, required("minute"): int, required("mode"): int, required("gear"): int},
        "motion_bed_audio": {required("operation"): vol.In(("track", "volume")), required("value"): int, optional("preview",default=False): bool},
    }
    for name, schema in schemas.items():
        hass.services.async_register(DOMAIN, name,
            handle_motion_bed_action if name == "motion_bed_action" else handle_motion_bed_configuration,
            schema=vol.Schema({**common, **schema}))
