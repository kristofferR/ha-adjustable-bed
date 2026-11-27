"""Scott Living's explicit layouts over the shared Keeson app controller.

Release ends the 100 ms refresh. The accepted artifact defines no STOP packet,
physical memory slots, save action, position feedback or light state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..card import CARD_MASSAGE_TIMER
from ..codec import keeson as codec
from ..command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ..const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE
from ..controller_state import StateKey
from ..profiles import scott_living as profiles
from .builder import BuildContext
from .cancellation import settled
from .entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .keeson.layout_app import AppController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

TIMER_INDICATOR = StateKey[int | None]("scott_living_timer_indicator")


def select_roles(client: BleakClient) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
    """Require the exact app service/characteristic pairs and their actual properties."""
    roles = codec.TRANSPORTS["base"]
    tx = rx = None
    for service in client.services:
        for char in service.characteristics:
            if service.uuid.lower() == roles.service_uuid and char.uuid.lower() == roles.write_uuid:
                tx = char
            if (
                service.uuid.lower() == "0000ffe0-0000-1000-8000-00805f9b34fb"
                and char.uuid.lower() == roles.notify_uuid
            ):
                rx = char
    if (
        tx is None
        or rx is None
        or not {"write", "write-without-response"}.intersection(tx.properties)
        or "notify" not in rx.properties
    ):
        raise ConnectionError("Scott Living requires writable FFE5/FFE9 and notify FFE0/FFE4")
    return tx, rx


class ScottLivingController(AppController):
    """Exact GATT roles and original-link writes, serialized by HA's scheduler."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str = "A",
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator, profiles.profile(layout))
        self._device_name = device_name
        self._refresh_stop = asyncio.Event()

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        basic = super().motor_control_specs
        if self.profile.layout != "C":
            return basic
        return (
            *basic,
            MotorControlSpec(
                "head",
                "head",
                lambda c: c.move_tilt_up(),
                lambda c: c.move_tilt_down(),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec("tilt_up", "tilt_down", 0, 0, stop_scope="side"),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            s for s in super().controller_button_specs if s.key not in ("tilt_up", "tilt_down")
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.profile.layout == "A":
            return ()
        # These are the app's graphic labels, not a measured countdown duration.
        return (
            ControllerStateSensorSpec(
                "scott_living_timer_indicator",
                "scott_living_timer_indicator",
                TIMER_INDICATOR,
                "mdi:timer-outline",
                entity_registry_enabled_default=True,
                entity_category=None,
                card=CARD_MASSAGE_TIMER,
            ),
        )

    def _ready(self) -> None:
        super()._ready()
        if self._coordinator.controller is not self:
            raise ConnectionError("Scott Living controller has been replaced")

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, profiles.REFRESH_MS

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        return max(1, -(-duration_ms // profiles.REFRESH_MS))

    def _frame(self, mask: int) -> bytes:
        return codec.frame(mask, header=0xE6, side=1)

    async def _release(self) -> None:
        """No release frame exists in this artifact."""

    async def stop_all(self) -> None:
        """Fence queued refresh and settle the submitted frame on its original link."""
        self._refresh_stop.set()
        async with self.ble_lock:
            pass

    async def _wait(self, milliseconds: float, *, cleanup: bool = False) -> bool:
        events = (self._coordinator.cancel_command, self._session_cancel, self._refresh_stop)
        if any(event.is_set() for event in events):
            return True
        waits = [asyncio.create_task(event.wait()) for event in events]
        try:
            done, _ = await asyncio.wait(
                waits, timeout=milliseconds / 1000, return_when=asyncio.FIRST_COMPLETED
            )
            return bool(done)
        finally:
            for task in waits:
                task.cancel()
            await asyncio.gather(*waits, return_exceptions=True)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        self._ready()
        self._refresh_stop = stop = asyncio.Event()
        session = self._session_cancel
        action = self._action(control)
        context = current_command_context()
        # A renewable hold is ended by the scheduler, not its first lease window.
        if context is not None and context.lease is not None:
            duration_ms = self.execution.hold_ceiling_ms or duration_ms
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        try:
            while loop.time() < deadline:
                if session is not self._session_cancel:
                    raise ConnectionError("Scott Living hold belongs to an expired session")
                if stop.is_set() or session.is_set() or self._coordinator.cancel_command.is_set():
                    note_frame_skipped()
                    return
                started = loop.time()
                await self.write_command(self._frame(action.mask))
                delay = max(0, min(deadline, started + profiles.REFRESH_MS / 1000) - loop.time())
                if await self._wait(delay * 1000):
                    return
        finally:
            stop.set()  # Ending refresh is the complete, packet-free release.

    async def _run_action(self, key: str) -> None:
        self._action(key)  # Reject stale layout controls before touching the link.
        self._refresh_stop = asyncio.Event()
        await super()._run_action(key)

    async def move_tilt_up(self) -> None:
        await self._run_action("tilt_up")

    async def move_tilt_down(self) -> None:
        await self._run_action("tilt_down")

    async def move_tilt_stop(self) -> None:
        await self.stop_all()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._ready()
        client, tx, session = self._session_client, self._tx, self._session_cancel
        refresh_stop = self._refresh_stop
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        assert client is not None and tx is not None
        context, caller = current_command_context(), asyncio.current_task()

        def cancelled() -> bool:
            deadline = context.hold_deadline if context is not None else None
            return (
                event.is_set()
                or refresh_stop.is_set()
                or caller is not None
                and bool(caller.cancelling())
                or context is not None
                and (
                    not context.active
                    or context.caller_is_cancelling is not None
                    and context.caller_is_cancelling()
                )
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            )

        for index in range(repeat_count):
            async with self.ble_lock:
                if cancelled():
                    note_frame_skipped()
                    raise asyncio.CancelledError
                self._ready()
                if session is not self._session_cancel or client is not self.client:
                    raise ConnectionError("Scott Living write belongs to an expired session")
                # Android inherits the discovered characteristic type. A no-response
                # property selects that mode, including when both modes are offered.
                response = "write-without-response" not in tx.properties
                payload = self._format_command_trace_payload(command)
                if payload is not None:
                    self._coordinator.record_command_trace(
                        payload=payload,
                        characteristic_uuid=tx.uuid,
                        characteristic_handle=tx.handle,
                        response=response,
                        repeat_count=repeat_count,
                        repeat_delay_ms=repeat_delay_ms,
                        command_origin="app_profile",
                        controller_class=type(self).__name__,
                    )

                async def write(response: bool = response) -> None:
                    await client.write_gatt_char(tx, command, response=response)
                    note_frame_written(event)

                await settled(write())
            if index + 1 < repeat_count and await self._wait(repeat_delay_ms):
                note_frame_skipped()
                return

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Scott Living session is disconnected")
        select_roles(client)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if (
            self.client is self._session_client
            and self.client is not None
            and self.client.is_connected
            and self._rx is not None
            and not self._session_cancel.is_set()
        ):
            self._notify_callback = callback
            return
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Scott Living session is disconnected")
        tx, rx = select_roles(client)
        self._session_client, self._tx, self._rx = client, tx, rx
        self._session_cancel = asyncio.Event()
        self._refresh_stop = asyncio.Event()
        self._notify_callback = callback
        session = self._session_cancel

        def notify(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                client is self.client
                and client is self._session_client
                and self._coordinator.controller is self
                and not session.is_set()
            ):
                self._on_notification(sender, data)

        try:
            async with self.ble_lock:
                self._ready()
                await settled(client.start_notify(rx, notify))
            if not await self._wait(profiles.REFRESH_MS):
                if session is not self._session_cancel or client is not self.client:
                    raise ConnectionError("Scott Living startup belongs to an expired session")
                await self.write_command(codec.scott_living_query(self._device_name))
        except BaseException:
            if session is self._session_cancel:
                self.on_disconnect()
            raise

    def on_disconnect(self) -> None:
        self._refresh_stop.set()
        self._timer_status = None
        if self._coordinator.controller is self:
            self.forward_controller_state_updates(TIMER_INDICATOR(None))
        super().on_disconnect()

    def _parse_notification(self, data: bytes | None) -> None:
        if self.profile.layout == "A" or data is None:
            return
        indicator = codec.scott_living_timer_indicator(data)
        if indicator is not None:
            self._timer_status = indicator
            self.forward_controller_state_updates(TIMER_INDICATOR(indicator))


async def build_controller(ctx: BuildContext) -> ScottLivingController:
    return ScottLivingController(
        ctx.coordinator,
        layout=ctx.data.get(CONF_PRODUCT_TYPE, "A"),
        device_name=ctx.live_device_name or ctx.data.get(CONF_BLE_DEVICE_NAME),
    )
