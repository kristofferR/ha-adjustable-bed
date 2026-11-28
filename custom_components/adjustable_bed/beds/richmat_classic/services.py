"""Validated direct BLE settings for classic Richmat apps."""

from __future__ import annotations

from contextlib import ExitStack
from functools import partial
from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...command_scheduler import note_frame_skipped
from ...const import (
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
)
from ...errors import invalid
from ...import_executor import async_import_modules
from ...paired_coordinator import BedChild, SingleAddressSideCoordinator
from ...profile_id import ProfileRoute
from ...profiles.maxprime import APP as MAXPRIME
from ...profiles.tss_remote import APP as TSS_REMOTE
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _bed_changed,
    _call_targets,
    _capture_command_admission,
    _child_side,
    _execute_preflighted,
    _execute_sided_translated,
    _family_command,
    _pair_mode,
    _preflight_and_execute,
    _preflight_capability,
    _release_preflighted,
    _Selection,
)
from .requests import Operation, Request
from .transport import Transport

_MAXPRIME_PROFILE_ID = ProfileRoute(BED_TYPE_RICHMAT_CLASSIC_APPS, MAXPRIME).profile_id
_TSS_PROFILE_ID = ProfileRoute(BED_TYPE_RICHMAT_CLASSIC_APPS, TSS_REMOTE).profile_id

OPERATIONS = (
    "query", "alarm", "cancel_alarm", "rgb", "lamp_slider", "lamp_save", "aroma",
    "massage_timer", "massage_popup", "lamp_timeout", "desk_target", "desk_unit", "desk_recall", "desk_reset",
)
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("action"): cv.string,
    vol.Optional("time"): cv.time,
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=300)),
    vol.Optional("minutes"): vol.All(cv.positive_int, vol.Range(max=15)),
    vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    vol.Optional("aroma_times"): vol.All(vol.ExactSequence((cv.positive_int, cv.positive_int, cv.positive_int)), vol.Coerce(tuple)),
    vol.Optional("progress"): vol.All(cv.positive_int, vol.Range(max=5)),
    vol.Optional("height"): vol.Coerce(float),
    vol.Optional("unit"): vol.In(("cm", "inches")),
    vol.Optional("duration_ms", default=1000): vol.All(cv.positive_int, vol.Range(min=1, max=60000)),
    vol.Optional("popup"): vol.In(("15", "30", "45", "toggle")),
    vol.Optional("slot"): vol.All(cv.positive_int, vol.Range(min=1, max=4)),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_richmat_classic(call: ServiceCall) -> None:
    request = Request(
        operation=cast(Operation, call.data["operation"]), action=call.data.get("action"),
        when=call.data.get("time"), minutes=call.data.get("minutes"), seconds=call.data.get("seconds"),
        color=call.data.get("rgb_color"), aroma_values=call.data.get("aroma_times"),
        progress=call.data.get("progress"), height=call.data.get("height"),
        unit=call.data.get("unit"), slot=call.data.get("slot"), duration_ms=call.data["duration_ms"], popup=call.data.get("popup"),
    )
    targets = _call_targets(call)
    if request.operation in ("rgb", "aroma"):
        selection = _Selection.capture(targets)
        if sum(map(len, selection.children)) > 1 and any(
            _requires_live_settings(child) for group in selection.children for child in group
        ):
            await _write_live_settings(call, selection, request)
            return

    await async_import_modules(call.hass, "beds.richmat_classic.controller")
    from .controller import RichmatClassicController

    resource = "movement" if request.operation in ("desk_recall", "desk_target", "desk_reset") else "configuration"
    await _preflight_and_execute(
        targets,
        RichmatClassicController,
        lambda controller: controller.async_execute_richmat_classic_request(request),
        validate=lambda controller: controller.validate_richmat_classic_request(request),
        cancel_running=resource == "movement",
        resource=resource,
        admit=True,
    )


def _requires_live_settings(target: BedChild) -> bool:
    coordinator = target.inner if isinstance(target, SingleAddressSideCoordinator) else target
    return coordinator.profile_id in (_MAXPRIME_PROFILE_ID, _TSS_PROFILE_ID)


class _SettingsStopped(Exception):
    """A STOP reached another receiver before the next settings frame."""


async def _write_live_settings(
    call: ServiceCall, selection: _Selection, request: Request
) -> None:
    """Check and retain every selected transport before a live settings batch."""
    targets = list(selection.targets)
    checks = [
        (parent, _child_side(parent, side, child), child)
        for (parent, side), group in zip(targets, selection.children, strict=True)
        for child in group
    ]
    if any(_pair_mode(parent) == PAIR_CONNECTION_MODE_SEQUENTIAL for parent, _, _ in checks):
        # A sequential operation always releases its side when it returns.
        raise invalid("maxprime_settings_sequential")
    admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side in targets
    ]
    check_admissions = [
        _capture_command_admission(parent, side, ("configuration",)) for parent, side, _ in checks
    ]

    await async_import_modules(
        call.hass, "beds.richmat_classic.maxprime", "beds.richmat_classic.tss_remote"
    )
    from .controller import BEFORE_SETTINGS_WRITE, RichmatClassicController
    from .tss_remote import TssRemoteController

    sessions: dict[int, tuple[RichmatClassicController, Transport]] = {}

    async def check(controller: RichmatClassicController, *, target: BedChild) -> None:
        if isinstance(controller, TssRemoteController):
            link = await controller.async_prepare_settings(request)
        else:
            link = controller.settings_session(request)
        sessions[id(target)] = (controller, link)

    def verify() -> bool:
        selection.require_unchanged(call)
        if selection.stopped():
            return False
        for _, _, child in checks:
            controller, link = sessions[id(child)]
            if child.controller is not controller or controller.settings_transport is not link:
                raise _bed_changed()
            if controller.settings_session(request) is not link:
                raise _bed_changed()
        return True

    def before_write() -> bool:
        try:
            if verify():
                return True
        except ServiceValidationError:
            note_frame_skipped()
            raise
        note_frame_skipped()
        raise _SettingsStopped

    async def write(controller: RichmatClassicController) -> None:
        if not verify():
            return
        if all(checked is not controller for checked, _ in sessions.values()):
            raise _bed_changed()
        token = BEFORE_SETTINGS_WRITE.set(before_write)
        try:
            await controller.async_execute_richmat_classic_request(request)
        except _SettingsStopped:
            return
        finally:
            BEFORE_SETTINGS_WRITE.reset(token)

    with ExitStack() as held:
        for _, _, child in checks:
            held.enter_context(child.hold_command_connection())
        preflighted = await _preflight_capability(
            targets,
            RichmatClassicController,
            validate=lambda ctrl: ctrl.validate_richmat_classic_request(request),
        )
        try:
            for (parent, side, child), admission in zip(checks, check_admissions, strict=True):
                if selection.stopped():
                    break
                await _execute_sided_translated(
                    parent, side, _family_command(RichmatClassicController, partial(check, target=child)),
                    cancel_running=False, resource="configuration", admission=admission,
                )
                if id(child) not in sessions:
                    break
            if len(sessions) != len(checks) or not verify():
                await _release_preflighted(preflighted)
                return
        except BaseException:
            await _release_preflighted(preflighted)
            raise
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(RichmatClassicController, write),
            resource="configuration",
            admissions=admissions,
        )


def async_register_richmat_classic_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_classic", handle_richmat_classic, schema=vol.Schema(FIELDS))
