"""Complete, explicit bed schedule, massage, scene and DIY requests."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ...codec import ergobq as codec
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.ergobq import MODES, SCENES


def register_services(hass: HomeAssistant) -> None:
    from ...services import (
        ALL_COMMAND_RESOURCES,
        DEVICE_IDS,
        SIDE_FIELD,
        _call_targets,
        _capture_command_admission,
        _preflight_and_execute,
    )

    async def handle(call: ServiceCall) -> None:
        targets = _call_targets(call)
        admissions = [
            _capture_command_admission(c, side, ALL_COMMAND_RESOURCES) for c, side in targets
        ]
        # Build and validate every byte before connecting or touching any bed.
        data = call.data
        weekdays = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
        repeat = sum(1 << (weekdays.index(day) + 1) for day in set(data.get("weekdays", ())))
        entries: tuple[codec.DP, ...] = ()
        try:
            if call.service == "ergobq_schedule":
                args = (data["task"], data["status"], repeat, data["hour"], data["minute"])
                if data["kind"] == "diy":
                    record = codec.diy_schedule(
                        *args, data["mode"], _program(data.get("program_hex"))
                    )
                else:
                    record = codec.custom_schedule(
                        *args,
                        position=data["position"],
                        scene=SCENES[data["scene"]],
                        massage=data["massage"],
                        sync=data["sync_massage"],
                        head=_massage(data["head"]),
                        legs=_massage(data["legs"]),
                        light=codec.Light(**data["light"]),
                    )
                entries = (codec.raw(41, record),)
            elif call.service == "ergobq_diy":
                entries = codec.run_diy(data["mode"], _program(data.get("program_hex")))
                if data.get("program_hex") is None:
                    codec.integer(data["mode"], 11, 30)
            elif call.service == "ergobq_scene":
                entries = (
                    codec.enumeration(
                        {"recall": 6, "save": 7, "restore": 8}[data["operation"]],
                        SCENES[data["scene"]],
                    ),
                )
            if entries:
                codec.publish(entries)
            if call.service == "ergobq_massage":
                _massage(data).encode()
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await async_import_modules(hass, "beds.ergobq.controller")
        from .controller import ErgoBQController

        async def execute(controller: ErgoBQController) -> None:
            if call.service == "ergobq_massage":
                await controller.set_massage(data["zone"], _massage(data))
            elif call.service == "ergobq_unlink":
                await controller.unlink(data["phase"])
            else:
                await controller.publish(entries)

        await _preflight_and_execute(
            targets,
            ErgoBQController,
            execute,
            cancel_running=True,
            resource=None,
            admissions=admissions,
        )

    def integer(low: int, high: int):
        return vol.All(vol.Coerce(int), vol.Range(min=low, max=high))

    massage = {
        vol.Optional("on", default=False): bool,
        vol.Optional("intensity", default=0): integer(0, 5),
        vol.Optional("mode", default="wave"): vol.In(MODES),
        vol.Optional("minutes", default=0): integer(0, 60),
    }
    light = {
        vol.Optional("on", default=False): bool,
        vol.Optional("brightness", default=0): integer(0, 100),
        vol.Optional("red", default=0): integer(0, 255),
        vol.Optional("green", default=0): integer(0, 255),
        vol.Optional("blue", default=0): integer(0, 255),
        vol.Optional("minutes", default=0): integer(0, 120),
    }
    schemas = {
        "ergobq_schedule": {
            vol.Required("task"): integer(1, 5),
            vol.Required("status"): integer(0, 2),
            vol.Optional("weekdays", default=list): [
                vol.In(
                    ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
                )
            ],
            vol.Required("hour"): integer(0, 23),
            vol.Required("minute"): integer(0, 59),
            vol.Optional("kind", default="custom"): vol.In(("custom", "diy")),
            vol.Optional("position", default=False): bool,
            vol.Optional("scene", default="flat"): vol.In(SCENES),
            vol.Optional("massage", default=False): bool,
            vol.Optional("sync_massage", default=False): bool,
            vol.Optional("head", default=dict): vol.Schema(massage),
            vol.Optional("legs", default=dict): vol.Schema(massage),
            vol.Optional("light", default=dict): vol.Schema(light),
            vol.Optional("mode", default=11): integer(11, 30),
            vol.Optional("program_hex"): str,
        },
        "ergobq_diy": {vol.Required("mode"): integer(0, 255), vol.Optional("program_hex"): str},
        "ergobq_massage": {vol.Required("zone"): vol.In(("head", "legs")), **massage},
        "ergobq_scene": {
            vol.Required("operation"): vol.In(("recall", "save", "restore")),
            vol.Required("scene"): vol.In(SCENES),
        },
        "ergobq_unlink": {vol.Required("phase"): integer(2, 3)},
    }
    for name, fields in schemas.items():
        hass.services.async_register(
            DOMAIN,
            name,
            handle,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): DEVICE_IDS,
                    **SIDE_FIELD,
                    **fields,
                }
            ),
        )


def _program(value: str | None) -> bytes | None:
    return (
        codec.diy_program(bytes.fromhex(value.strip()))
        if value is not None and value.strip()
        else None
    )


def _massage(data) -> codec.Massage:
    return codec.Massage(data["on"], data["intensity"], MODES.index(data["mode"]), data["minutes"])
