"""King Koil's direct P2 session; ending refresh is the only proven release."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_UTILITY
from ...codec import keeson as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import kingkoil as app
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

LIGHT_REPORT: Final = StateKey[bool | None]("kingkoil_light_report")
TIMER_UI: Final = StateKey[int | None]("kingkoil_timer_ui")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


def select_link(client: BleakClient) -> Link:
    """The same exact service/role gates in setup and runtime, no fallback UUIDs."""
    for service in client.services:
        if service.uuid.lower() != app.TRANSPORT.service_uuid:
            continue
        write = service.get_characteristic(app.TRANSPORT.write_uuid)
        notify = service.get_characteristic(app.TRANSPORT.notify_uuid)
        if (
            write is not None
            and notify is not None
            and {"write", "write-without-response"}.intersection(write.properties)
            and "notify" in notify.properties
        ):
            # Android never overrides the characteristic's inherited write type.
            return Link(client, write, notify, "write" in write.properties)
    raise BedNotConnectedError("kingkoil_gatt")


def _move(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        await cast(KingKoilController, controller)._move_motor(axis, up)

    return move


def _action(action: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        await cast(KingKoilController, controller).perform_action(action)

    return press


class KingKoilController(KeesonController):
    """One selected app layout, immutable for the life of this controller."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, variant: str) -> None:
        if variant not in app.LAYOUTS:
            raise invalid("kingkoil_layout")
        super().__init__(coordinator, variant="base", char_uuid=app.TRANSPORT.write_uuid)
        self.layout = app.LAYOUTS[variant]
        self.profile = self.layout.profile
        self._variant = variant
        self._link: Link | None = None
        self._address = coordinator.address.upper()
        self._subscribed = False
        self._stop_generation = 0

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        # Fences refresh only. Preset abort is not established by the artifact.
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != self._address
        ):
            raise BedNotConnectedError("kingkoil_session")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        self._link = select_link(client)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self._live(link)
            except ConnectionError:
                return
            if sender.handle != link.notify.handle:
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            status = codec.parse_kingkoil_status(bytes(data))
            if status is not None:
                self.forward_controller_state_updates(LIGHT_REPORT(status.light))
                if self.layout.massage:
                    self.forward_controller_state_updates(TIMER_UI(status.timer_ui))

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
        self._stop_generation += 1
        self._motor_state.clear()
        self.invalidate_diagnostics()

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(LIGHT_REPORT(None), TIMER_UI(None))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        generation = self._stop_generation
        context = current_command_context()
        caller = asyncio.current_task()

        def check() -> None:
            self._live(link)
            deadline = context.hold_deadline if context is not None else None
            if (
                cancel.is_set()
                or generation != self._stop_generation
                or caller is not None
                and caller.cancelling()
                or context is not None
                and (
                    not context.active
                    or context.caller_is_cancelling is not None
                    and context.caller_is_cancelling()
                )
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            ):
                raise asyncio.CancelledError

        async def send() -> None:
            check()
            await self._write_gatt_with_retry(
                link.write.uuid,
                command,
                cancel_event=cancel,
                characteristic=link.write,
                expected_client=link.client,
                response=link.response,
                before_write=check,
            )
            self._live(link)

        for index in range(repeat_count):
            started = asyncio.get_running_loop().time()
            check()
            # One submitted frame settles on its original link before STOP owns the lane.
            await settled(send())
            if index + 1 < repeat_count:
                delay = max(
                    0, repeat_delay_ms / 1000 - (asyncio.get_running_loop().time() - started)
                )
                await cancellable(asyncio.sleep(delay), cancel)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        return max(1, -(-duration_ms // app.REFRESH_MS))

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
            return
        if motor not in {axis for axis, _, _ in self.layout.axes}:
            raise invalid("kingkoil_control")
        word = next(
            up if direction else down for axis, up, down in self.layout.axes if axis == motor
        )
        # Shared Keeson movement/hold scheduling, with this app's own literal mask.
        self._motor_state = {motor: direction}
        try:
            count, delay = self._held_cadence()
            await self.write_command(self._build_command(word), count, delay)
        finally:
            self._motor_state.clear()  # No STOP/release packet exists in either live path.

    def _build_command(self, command_value: int) -> bytes:
        allowed = {
            *self.layout.actions.values(),
            *self.profile.presets.values(),
            *(word for _, up, down in self.layout.axes for word in (up, down)),
        }
        if command_value not in allowed:
            raise invalid("kingkoil_control")
        return super()._build_command(command_value)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{d}" for axis, _, _ in self.layout.axes for d in ("up", "down")) + (
            ("light",) if self.layout.held_light else ()
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 100 <= duration_ms <= 60000
        ):
            raise invalid("kingkoil_control")
        if control == "light":
            word = app.LIGHT
        else:
            axis, direction = control.rsplit("_", 1)
            word = next(
                up if direction == "up" else down
                for key, up, down in self.layout.axes
                if key == axis
            )
        # The timeout includes waiting for the BLE lane, and never cancels an
        # already-submitted write. Leased holds use the scheduler's changing deadline.
        count = self.leased_hold_refreshes(app.REFRESH_MS) or -(-duration_ms // app.REFRESH_MS)
        budget = asyncio.timeout(self.leased_hold_ms(duration_ms) / 1000)
        try:
            async with budget:
                await self.write_command(self._build_command(word), count, app.REFRESH_MS)
                await cancellable(
                    asyncio.sleep(app.REFRESH_MS / 1000), self._coordinator.cancel_command
                )
        except TimeoutError:
            if not budget.expired():
                raise

    async def perform_action(self, action: str) -> None:
        if action == "status_query":
            await self.write_command(codec.STATUS_QUERY)
        elif action in self.layout.actions:
            if action == "light" and self.layout.held_light:
                await self.hold_control("light", 300)
            else:
                await self.write_command(self._build_command(self.layout.actions[action]))
        else:
            raise invalid("kingkoil_control")

    async def stop_all(self) -> None:
        self._stop_generation += 1
        self._motor_state.clear()

    @property
    def diagnostic_poll_interval(self) -> float | None:
        return app.POLL_S

    async def async_refresh_diagnostics(self) -> None:
        await self.perform_action("status_query")

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "King Koil Bed 1.0",
            "saved_selector": self._variant,
            "layout": self.layout.label,
            "hardware": "UNVERIFIED",
            "stop": "ends refresh only; preset abort and watchdog timing unverified",
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                f"kingkoil_{axis}",
                _move(axis, True),
                _move(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis, _, _ in self.layout.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"kingkoil_{action}",
                action,
                _action(action),
                translation_key=f"kingkoil_{action}",
                card=CARD_LIGHTING
                if action == "light"
                else CARD_UTILITY
                if action == "status_query"
                else CARD_MASSAGE,
                scheduler_resource="*",
                hold=ControllerHoldSpec("light")
                if action == "light" and self.layout.held_light
                else None,
                diagnostic=action == "status_query",
                entity_registry_enabled_default=action != "status_query",
            )
            for action in (*self.layout.actions, "status_query")
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "kingkoil_light_report",
                "kingkoil_light_report",
                LIGHT_REPORT,
                "mdi:lightbulb",
                entity_registry_enabled_default=True,
                card=CARD_LIGHTING,
                entity_category=None,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            (
                ControllerStateSensorSpec(
                    "kingkoil_timer_ui",
                    "kingkoil_timer_ui",
                    TIMER_UI,
                    "mdi:timer-outline",
                    entity_registry_enabled_default=True,
                    card=CARD_MASSAGE,
                    entity_category=None,
                ),
            )
            if self.layout.massage
            else ()
        )


async def build_controller(ctx: BuildContext) -> KingKoilController:
    return KingKoilController(ctx.coordinator, variant=ctx.variant or "")
