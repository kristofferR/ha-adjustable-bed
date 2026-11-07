"""Hush Base MM/SXB sensors, scoped to one physical target and request."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...controller_state import StateKey
from ..casper_base.protocol import Request, SensorKind
from ..casper_sleep.controller import (
    INFO,
    PART,
    REPORT,
    STATUS,
    CasperRemoteController,
    CasperSleepController,
)
from ..casper_sleep.protocol import Json, mapping
from ..entity_specs import ControllerStateSensorSpec
from .protocol import HushReceive, build, integer, parse, report

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


SENSITIVITY: Final = StateKey[dict[str, Json]]("hush_sleep_sensitivity")
ANTI_SNORE: Final = StateKey[Json]("hush_sleep_anti_snore")
DEVICE_TIME: Final = StateKey[Json]("hush_sleep_device_time")
LIVE_REQUESTED: Final = StateKey[bool]("hush_sleep_live_requested")


class HushSleepController(CasperSleepController):
    """Independent sleep module. Actuator side and sensor partition are distinct."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, kind: SensorKind) -> None:
        super().__init__(coordinator, kind=kind)
        self._receive = HushReceive(self.kind)
        self._live_requested = False
        self._followups: set[asyncio.Task[None]] = set()

    def on_disconnect(self) -> None:
        for task in self._followups:
            task.cancel()
        self._followups.clear()
        super().on_disconnect()

    def _schedule(self, action: str) -> None:
        generation = self._generation

        async def followup() -> None:
            async def execute(controller):
                if controller is self and generation == self._generation:
                    await self._send(action, Request("sensor_time"))

            await self._coordinator.async_execute_controller_command(
                execute, cancel_running=False, resource="configuration"
            )

        task = self._coordinator.hass.async_create_background_task(
            followup(), "Hush sleep handshake"
        )
        self._followups.add(task)
        task.add_done_callback(self._followups.discard)

    @property
    def supports_hush_base_controls(self) -> bool:
        return True

    @property
    def supports_casper_base_controls(self) -> bool:
        return False

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"live_requested": self._live_requested}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        enabled = state.get("live_requested", False)
        if type(enabled) is not bool:
            raise ValueError("Invalid saved live session")
        self._live_requested = enabled

    @property
    def requests_connection_recovery(self) -> bool:
        return self._live_requested

    def on_connection_release(self, reason: str) -> None:
        self._live_requested = False
        self.on_disconnect()
        self.forward_controller_state_update(LIVE_REQUESTED, False)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            *super().controller_state_sensor_specs,
            ControllerStateSensorSpec(
                "hush_sleep_settings",
                "hush_sleep_settings",
                STATUS,
                "mdi:sleep",
                attribute_keys=(
                    SENSITIVITY,
                    ANTI_SNORE,
                    DEVICE_TIME,
                    LIVE_REQUESTED,
                ),
            ),
        )

    async def start_notify(self, callback=None) -> None:
        await super().start_notify(callback)
        self._coordinator.cache_capability_controller()
        if self._live_requested:
            await self.async_execute_casper_base_request(Request("sensor_live"))

    async def _send(self, action: str, request: Request) -> None:
        client, characteristic, generation = self.client, self._write_char, self._generation
        if client is None or characteristic is None:
            raise ConnectionError("Sensor disconnected")
        if self._sequence >= 255:
            self._sequence = 1
        now = dt_util.now()
        offset = now.utcoffset()
        zone = (
            str(now.tzinfo)
            if self.kind == "mm"
            else int((offset.total_seconds() if offset else 0) / 3600)
        )
        packet = build(
            self.kind, action, self._sequence, request, ts=int(now.timestamp()), zone=zone
        )
        self._sequence += 1
        self._receive.reset(action)
        await asyncio.sleep(0.1)
        mtu = client.mtu_size - 3
        if mtu < 1:
            raise ValueError("Invalid negotiated MTU")
        for index in range(0, len(packet), mtu):
            if (
                self.client is not client
                or generation != self._generation
                or not client.is_connected
            ):
                raise ConnectionError("Sensor operation lost its physical connection")
            await self._write_gatt_with_retry(
                characteristic.uuid,
                packet[index : index + mtu],
                characteristic=characteristic,
                expected_client=client,
                response=self.kind == "sxb",
            )

    def _consume(self, data: Json) -> None:
        action = self._receive.action
        if action == "q_report_allow":
            request = self._report_request
            if request is None:
                return
            decoded = report(data, kind=self.kind, monthly=request.report_type == 2)
            if decoded is not None:
                self.forward_controller_state_update(
                    REPORT,
                    {
                        "part": request.part,
                        "year": request.year,
                        "month": request.month,
                        "day": request.day,
                        "data": decoded,
                    },
                )
            return
        schemas = {
            "mm": {
                "s_time": "0x7add30",
                "q_part": "0x7adb98",
                "s_part": "0x7adb98",
                "q_realtime": "0x7ad7e0",
                "q_report": "0x7ad508",
            },
            "sxb": {
                "s_time": "0x7a3cbc",
                "q_time": "0x7a25cc",
                "q_part": "0x7a242c",
                "s_part": "0x7a242c",
                "q_realtime": "0x7a1de4",
                "q_report": "0x7a1a70",
                "q_sens": "0x7a0d74",
                "q_antiSnore": "0x7a08c8",
                "s_antiSnore": "0x7a08c8",
            },
        }
        if action not in schemas[self.kind]:
            return
        bean = parse(schemas[self.kind][action], data)
        val = bean.get("val")
        if action == "q_time":
            self.forward_controller_state_update(DEVICE_TIME, val)
            self._schedule("q_part")
        elif action == "s_time":
            self._info.update(mapping(val))
            self.forward_controller_state_update(INFO, dict(self._info))
            if self.kind == "sxb":
                self._schedule("q_time")
        elif action in ("q_part", "s_part"):
            self.forward_controller_state_update(PART, val)
        elif action == "q_realtime" and val is not None:
            self._live.feed(val)
            self._publish_live()
        elif action == "q_report":
            size = mapping(val).get("fsize")
            self._receive.report_size = integer(size) if size is not None else 0
        elif action == "q_sens":
            sides = mapping(val)
            settings: dict[str, Json] = {}
            for side in ("L", "R"):
                values = sides[side]
                if not isinstance(values, list) or not values:
                    raise ValueError("Missing sensitivity value")
                settings[side] = integer(values[0]) - 1
            self.forward_controller_state_update(SENSITIVITY, settings)
        elif action in ("q_antiSnore", "s_antiSnore"):
            self.forward_controller_state_update(ANTI_SNORE, val)

    def validate_casper_base_request(self, request: Request) -> None:
        op = request.operation
        if op in (
            "sensor_query_time",
            "sensor_sensitivity",
            "sensor_query_anti_snore",
            "sensor_anti_snore",
        ):
            if self.kind != "sxb":
                raise ValueError("This setting requires SXB")
            return
        if op == "sensor_info":
            raise ValueError(
                "Use sensor_time or sensor_query_time; firmware initialization is excluded"
            )
        if op == "sensor_report":
            if request.part not in ((1, 2, 3) if self.kind == "mm" else (1, 2)):
                raise ValueError("Unsupported report partition")
            return
        super().validate_casper_base_request(request)

    async def async_execute_casper_base_request(self, request: Request) -> None:
        self.validate_casper_base_request(request)
        extra = {
            "sensor_query_time": "q_time",
            "sensor_sensitivity": "q_sens",
            "sensor_query_anti_snore": "q_antiSnore",
            "sensor_anti_snore": "s_antiSnore",
        }
        if request.operation in extra:
            await self._query(extra[request.operation], request)
            return
        if request.operation in ("sensor_live", "sensor_stop"):
            self._live_requested = request.operation == "sensor_live" and request.enabled
            self.forward_controller_state_update(LIVE_REQUESTED, self._live_requested)
        await super().async_execute_casper_base_request(request)

    async def _poll_live(self) -> None:
        # Bind each admitted background callback to this controller, not a
        # replacement created while the callback was waiting for the lock.
        try:
            while self._live_requested:
                await asyncio.sleep(2)

                async def query(controller):
                    if controller is self and self._live_requested:
                        await self._query_live()

                try:
                    await self._coordinator.async_execute_controller_command(
                        query, cancel_running=False, resource="configuration"
                    )
                except (
                    ConnectionError,
                    ValueError,
                    TimeoutError,
                    IndexError,
                    OverflowError,
                    BleakError,
                ):
                    # A failed sample does not revoke the user's monitoring request.
                    continue
        finally:
            if self._poll is asyncio.current_task():
                self._poll = None
                self._coordinator.resume_disconnect_timer()


class HushRemoteController(CasperRemoteController):
    """RCRM finder is a connection only, without an invented locator frame."""

    @property
    def supports_hush_base_controls(self) -> bool:
        return True

    @property
    def supports_casper_base_controls(self) -> bool:
        return False
