"""Somos's session and neutral UI axes over the proven Keeson controller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...codec import keeson as codec
from ...const import KEESON_BASE_NOTIFY_SERVICE_UUID
from ...controller_state import StateKey
from ...profiles import somos as app
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .controller import KeesonController, _wait_unless_cancelled

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

REMAINING_SECONDS: Final = StateKey[int | None]("somos_remaining_seconds")
TIMER_INDICATOR: Final = StateKey[int | None]("somos_timer_indicator")


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    address: str
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


def parse_timer(variant: str, data: bytes) -> tuple[int, int] | None:
    """Preserve Java signed/truncating arithmetic; discard short notifications."""
    if variant == "b" and len(data) >= 5:
        seconds = int.from_bytes(data[3:5], "big")
    elif variant == "c" and len(data) >= 13:
        raw = int.from_bytes(data[9:13], "little", signed=True)
        seconds = (abs(raw) // 100) * (-1 if raw < 0 else 1)
    elif variant == "e" and len(data) >= 4:
        seconds = int.from_bytes(data[2:4], "big")
    else:
        return None
    minutes = (abs(seconds) // 60) * (-1 if seconds < 0 else 1)
    return (
        seconds,
        10 if 0 < minutes <= 10 else 20 if 10 < minutes <= 20 else 30 if minutes > 20 else 0,
    )


def _move(axis: str, direction: bool) -> MotorCommandCallable:
    async def command(controller: BedController) -> None:
        await cast(SomosController, controller)._move_motor(axis, direction)

    return command


def _action(action: str) -> MotorCommandCallable:
    async def command(controller: BedController) -> None:
        await cast(SomosController, controller).perform_action(action)

    return command


class SomosController(KeesonController):
    """One physical receiver; no D/E left/right selector or inferred anatomy."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, variant: str) -> None:
        if variant not in app.PRODUCTS:
            raise ValueError("Choose a Somos product A, B, C, D or E")
        product = app.PRODUCTS[variant]
        super().__init__(
            coordinator,
            variant="base",
            char_uuid=codec.TRANSPORTS[product.profile.transport].write_uuid,
        )
        self.product = product
        self.profile = self.product.profile
        self._variant = variant
        transport = codec.TRANSPORTS[self.profile.transport]
        self._char_uuid, self._notify_char_uuid = transport.write_uuid, transport.notify_uuid
        self._link: _Link | None = None
        self._subscribed = False
        self._next_query = 0.0

    @property
    def auto_stops_on_idle(self) -> bool:
        """Ending the app's refresh is its only proven movement cleanup."""
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        # Only exact source buttons are exposed, never inferred on/off or levels.
        return False

    @property
    def supports_lights(self) -> bool:
        return False  # Expose the exact opaque light button, without assumed state.

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Favorite M",) if self._variant == "d" else ()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "somos_product": self.product.label,
            "hardware": "UNVERIFIED",
            "physical_axis_roles": "UNVERIFIED" if self._variant in ("d", "e") else "app labels",
        }

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or self._coordinator.controller is not self
            or not link.client.is_connected
            or self._coordinator.address.upper() != link.address
        ):
            raise ConnectionError("Somos physical BLE session changed")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Somos is disconnected")
        transport = codec.TRANSPORTS[self.profile.transport]
        notify_service = (
            KEESON_BASE_NOTIFY_SERVICE_UUID
            if self.profile.transport == "base"
            else transport.service_uuid
        )

        def role(service_uuid: str, uuid: str) -> BleakGATTCharacteristic:
            for service in client.services:
                if service.uuid.lower() == service_uuid:
                    char = service.get_characteristic(uuid)
                    if char is not None:
                        return char
            raise ValueError(f"Somos requires {uuid} on {service_uuid}")

        write, notify = (
            role(transport.service_uuid, transport.write_uuid),
            role(notify_service, transport.notify_uuid),
        )
        if (
            not {"write", "write-without-response"}.intersection(write.properties)
            or "notify" not in notify.properties
        ):
            raise ValueError("Somos requires writable and notifying GATT roles")
        self._link = _Link(
            client, self._coordinator.address.upper(), write, notify, "write" in write.properties
        )
        self._next_query = asyncio.get_running_loop().time() + app.QUERY_INITIAL_S

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or self._coordinator.controller is not self
                or not link.client.is_connected
                or sender.handle != link.notify.handle
                or self._coordinator.address.upper() != link.address
            ):
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            parsed = parse_timer(self._variant, bytes(data))
            if parsed is not None:
                self.forward_controller_state_updates(
                    REMAINING_SECONDS(parsed[0]), TIMER_INDICATOR(parsed[1])
                )

        await link.client.start_notify(link.notify, receive)
        self._live(link)
        self._subscribed = True

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self.on_disconnect()
        if link is not None and subscribed and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link, self._subscribed = None, False
        self._motor_state.clear()
        self.invalidate_diagnostics()

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(REMAINING_SECONDS(None), TIMER_INDICATOR(None))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command

        def validate() -> None:
            self._live(link)

        # Each refresh remains bound to the original client/characteristic/address.
        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event=cancel,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            wall_clock_pacing=True,
            before_write=validate,
        )
        self._live(link)

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        return max(1, -(-duration_ms // pulse_delay_ms))

    @property
    def diagnostic_poll_interval(self) -> float | None:
        return app.QUERY_PERIOD_S if self.product.query is not None else None

    async def async_refresh_diagnostics(self) -> None:
        if self.product.query is None or asyncio.get_running_loop().time() < self._next_query:
            return
        await self.write_command(self.product.query)

    @property
    def actions(self) -> dict[str, int]:
        return {
            **({**app.MASSAGE_ACTIONS} if self.product.massage else {}),
            **self.profile.presets,
            **{f"memory_{slot}": word for slot, word in self.profile.memory.items()},
            **({"light": app.LIGHT_BUTTON} if self.product.massage else {}),
        }

    def validate_action(self, action: str) -> None:
        if action not in self.actions and not (
            action == "status_query" and self.product.query is not None
        ):
            raise ValueError("Action unavailable on this Somos product")

    async def perform_action(self, action: str) -> None:
        self.validate_action(action)
        if action == "status_query":
            assert self.product.query is not None
            await self.write_command(self.product.query)
        else:
            await self._write_single_shot(self._build_command(self.actions[action]))

    async def _write_single_shot(self, command: bytes) -> None:
        link = self._live()
        await super()._write_single_shot(command)
        if self._variant == "b" and command in {
            self._build_command(word)
            for word in (*app.MASSAGE_ACTIONS.values(), self.profile.presets["flat"])
        }:
            for _ in range(3):
                await _wait_unless_cancelled(self._coordinator.cancel_command, 0.3)
                self._live(link)
                if self._coordinator.cancel_command.is_set():
                    return
                await self.write_command(codec.STATUS_QUERY)

    def _build_command(self, command_value: int) -> bytes:
        allowed = {
            *self.actions.values(),
            *(value for _, up, down in self.product.axes for value in (up, down)),
        }
        if command_value not in allowed:
            raise NotImplementedError("Command not proven for this Somos product")
        return super()._build_command(command_value)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    def _get_move_command(self) -> int:
        for axis, up, down in self.product.axes:
            direction = self._motor_state.get(axis)
            if direction is not None:
                return up if direction else down
        return 0

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in {axis for axis, _, _ in self.product.axes}:
            raise ValueError("Unverified Somos axis")
        link = self._live()
        try:
            if direction is not None:
                await _wait_unless_cancelled(
                    self._coordinator.cancel_command, self.product.initial_ms / 1000
                )
                self._live(link)
            await super()._move_motor(motor, direction)
        finally:
            self._next_query = asyncio.get_running_loop().time() + app.QUERY_INITIAL_S

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}"
            for axis, _, _ in self.product.axes
            for direction in ("up", "down")
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or isinstance(duration_ms, bool)
            or not 100 <= duration_ms <= 60000
        ):
            raise ValueError("Choose a supported Somos held control and 100..60000ms")
        axis, direction = control.rsplit("_", 1)
        if self.leased_hold_refreshes(app.REFRESH_MS) is not None:
            # The scheduler owns the changing deadline and absolute ceiling.
            await self._move_motor(axis, direction == "up")
            return
        link = self._live()
        cancel = self._coordinator.cancel_command
        word = next(
            up if direction == "up" else down for key, up, down in self.product.axes if key == axis
        )
        budget = asyncio.timeout(duration_ms / 1000)
        try:
            async with budget:
                await _wait_unless_cancelled(cancel, self.product.initial_ms / 1000)
                self._live(link)
                await self.write_command(
                    self._build_command(word), -(-duration_ms // app.REFRESH_MS), app.REFRESH_MS
                )
                await _wait_unless_cancelled(self._coordinator.cancel_command, duration_ms / 1000)
        except TimeoutError:
            if not budget.expired():
                raise
        finally:
            # No release packet exists. End refresh and resume delayed polling.
            self._next_query = asyncio.get_running_loop().time() + app.QUERY_INITIAL_S

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                f"somos_{axis}",
                _move(axis, True),
                _move(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis, _, _ in self.product.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"somos_{action}",
                action,
                _action(action),
                translation_key=f"somos_{action}",
                card=CARD_LIGHTING if action == "light" else CARD_MASSAGE,
                scheduler_resource="*",
            )
            for action in (*app.MASSAGE_ACTIONS, "light")
            if self.product.massage
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self.product.massage:
            return ()
        return (
            ControllerStateSensorSpec(
                "somos_timer",
                "somos_timer",
                TIMER_INDICATOR,
                "mdi:timer-outline",
                native_unit_of_measurement="min",
                attribute_keys=(REMAINING_SECONDS,),
                card=CARD_MASSAGE_TIMER,
            ),
        )

    async def stop_all(self) -> None:
        self._motor_state.clear()
        self._next_query = asyncio.get_running_loop().time() + app.QUERY_INITIAL_S


async def build_controller(ctx: BuildContext) -> SomosController:
    return SomosController(ctx.coordinator, variant=ctx.variant or "")
