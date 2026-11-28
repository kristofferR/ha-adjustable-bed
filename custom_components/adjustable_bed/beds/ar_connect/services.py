"""Concrete AR Connect multi-section holds and local headboard records."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...codec import ar_connect as codec
from ...const import DOMAIN
from ...import_executor import async_import_modules


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def handle(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [_capture_command_admission(parent, side) for parent, side in targets]
        await async_import_modules(hass, "beds.ar_connect.controller")
        from .headboard import HeadboardController
        from .native import NativeController

        if call.service == "ar_connect_move_sections":
            directions = {
                axis: direction == "up" for axis, direction in call.data["directions"].items()
            }
            await _preflight_and_execute(
                targets,
                NativeController,
                lambda c: c.move_sections(directions, call.data["duration_ms"]),
                validate=lambda c: _validate_move(c.axes, directions, call.data["duration_ms"]),
                resource=None,
                cancel_running=True,
                admissions=admissions,
            )
            return
        if call.service == "ar_connect_mood":
            colors = tuple(
                codec.rgbw(codec.hue_rgb(step["hue"]), step["tint"], step["brightness"])
                for step in call.data["colors"]
            )

            def validate_mood(controller: HeadboardController) -> None:
                codec.mood(call.data["repeat"], call.data["delay"], colors)

            await _preflight_and_execute(
                targets,
                HeadboardController,
                lambda c: c.set_mood(call.data["repeat"], call.data["delay"], colors),
                supported=lambda c: c.supports_light_color_control,
                admissions=admissions,
                validate=validate_mood,
            )
            return
        action = call.data["action"]
        if action == "refresh":
            await _preflight_and_execute(
                targets, HeadboardController, lambda c: c.refresh_routines(), admissions=admissions
            )
            return
        identity = call.data.get("id")
        routine = None
        if action != "delete":
            routine = codec.Routine(
                call.data["enabled"],
                call.data["mode"],
                call.data["hour"],
                call.data["minute"],
                call.data["duration"],
                weekdays=tuple(call.data["weekdays"]),
            )

        async def execute(controller: HeadboardController) -> None:
            if action == "delete":
                await controller.delete_routine(str(identity))
            else:
                assert routine is not None
                await controller.put_routine(routine, str(identity) if action == "update" else None)

        def validate(controller: HeadboardController) -> None:
            if action in ("update", "delete") and identity is None:
                raise ValueError("A returned routine id is required")
            if routine is not None:
                routine.validate()

        await _preflight_and_execute(
            targets, HeadboardController, execute, validate=validate, admissions=admissions
        )

    def _validate_move(axes: tuple[str, ...], directions: dict[str, bool], duration: int) -> None:
        if not directions or set(directions).difference(axes):
            raise ValueError("Select available bed sections")

    base = {vol.Required("device_id"): DEVICE_IDS, **SIDE_FIELD}
    directions_schema = vol.Schema(
        {vol.Optional(axis): vol.In(("up", "down")) for axis in ("back", "legs", "head", "feet")}
    )
    hass.services.async_register(
        DOMAIN,
        "ar_connect_move_sections",
        handle,
        schema=vol.Schema(
            {
                **base,
                vol.Required("directions"): directions_schema,
                vol.Required("duration_ms"): vol.All(vol.Coerce(int), vol.Range(min=1, max=60000)),
            }
        ),
    )
    step = vol.Schema(
        {
            vol.Required("hue"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Required("tint"): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=1)),
            vol.Required("brightness"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
        }
    )
    hass.services.async_register(
        DOMAIN,
        "ar_connect_mood",
        handle,
        schema=vol.Schema(
            {
                **base,
                vol.Required("repeat"): cv.boolean,
                vol.Required("delay"): vol.In(codec.DURATIONS),
                vol.Required("colors"): vol.All([step], vol.Length(min=5, max=5)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "ar_connect_routine",
        handle,
        schema=vol.Schema(
            {
                **base,
                vol.Required("action"): vol.In(("create", "update", "delete", "refresh")),
                vol.Optional("id"): vol.Coerce(int),
                vol.Optional("enabled", default=True): cv.boolean,
                vol.Optional("mode", default="wake"): vol.In(("wake", "sleep")),
                vol.Optional("hour", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                vol.Optional("minute", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=59)
                ),
                vol.Optional("duration", default=10): vol.In(codec.DURATIONS),
                vol.Optional("weekdays", default=[]): [vol.In(codec.DAYS)],
            }
        ),
    )
