"""Restonic's layout controls over shared Keeson commands and captured BLE links."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_LIGHTING, CARD_MASSAGE
from ...command_scheduler import (
    CommandContext,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
)
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...errors import BedNotConnectedError
from ...profiles import restonic as app
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..keeson.controller import KeesonController
from ..lifecycle import ControllerSession
from .protocol import Parser

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

RAW_KEYS: Final = {
    name: StateKey[int | None](f"restonic_raw_{name}")
    for name in ("b", "23", "13", "1b", "2b", "43", "33", "3b")
}
SELECTED_BRANCH: Final = StateKey[str]("restonic_branch")
SELECTED_LAYOUT: Final = StateKey[str]("restonic_layout")
WRITE_TIMEOUT_S: Final = 5.0
_AXIS_ACTIONS: Final = {
    "head": ("headUp", "headDown"),
    "feet": ("footUp", "footDown"),
    "lumbar": ("lumbarUp", "lumbarDown"),
    "neck": ("neckTiltUp", "neckTiltDown"),
}


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str
    route: app.Transport


@dataclass(slots=True)
class Press:
    link: Link
    frame: bytes
    stop: bytes
    deadline: float
    cancel: asyncio.Event
    started: bool = False


class RestonicController(KeesonController):
    """The app's single refresh timer, without its mutable-target callback race."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, branch: str, layout: str) -> None:
        super().__init__(
            coordinator, char_uuid=app.TRANSPORTS.get(branch, app.TRANSPORTS["box15"]).write
        )
        if branch not in app.TRANSPORTS or layout not in app.PROFILES:
            raise self.not_supported("an unspecified Restonic layout or BLE branch")
        self.profile = app.PROFILES[layout]
        self.branch, self.layout = branch, layout
        self._link: Link | None = None
        self._cleanup: tuple[Link, CommandContext] | None = None
        self._subscribed = False
        self._parser = Parser(branch)
        self.forward_controller_state_updates(SELECTED_BRANCH(branch), SELECTED_LAYOUT(layout))

    @property
    def control_characteristic_uuid(self) -> str:
        return app.TRANSPORTS[self.branch].write

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return False

    @property
    def has_neck_support(self) -> bool:
        return self.layout == "infinity"

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "restonic_branch": self.branch,
            "restonic_layout": self.layout,
            "hardware": "UNVERIFIED",
        }

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and self._coordinator.controller is self
            and link.client.is_connected
            and self._coordinator.address == link.address
        )

    def _live(self) -> Link:
        link = self._link
        if link is None or not self._current(link):
            raise BedNotConnectedError
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        route = app.TRANSPORTS[self.branch]

        def role(service_uuid: str, uuid: str) -> BleakGATTCharacteristic:
            for service in client.services:
                if service.uuid.lower() == service_uuid:
                    char = service.get_characteristic(uuid)
                    if char is not None:
                        return char
            raise self.not_supported("the selected Restonic BLE branch's GATT roles")

        write = role(route.service, route.write)
        notify = role(route.notify_service, route.notify)
        if (
            "write" if route.response else "write-without-response"
        ) not in write.properties or not {"notify", "indicate"}.intersection(notify.properties):
            raise self.not_supported("the selected Restonic BLE branch's GATT properties")
        self._link = Link(client, write, notify, self._coordinator.address, route)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        # The app performs no startup reads, including Device Information.
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(link) or sender.handle != link.notify.handle:
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            parsed = self._parser.feed(bytes(data))
            self.forward_controller_state_updates(
                *(RAW_KEYS[key](value) for key, value in parsed.items())
            )

        await link.client.start_notify(link.notify, receive)
        if not self._current(link):
            raise BedNotConnectedError
        self._subscribed = True

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self.on_disconnect()
        if link is not None and subscribed and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link, self._subscribed = None, False
        self._cleanup = None
        self._parser = Parser(self.branch)
        self.invalidate_diagnostics()

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(*(key(None) for key in RAW_KEYS.values()))

    async def _send(self, press: Press, *, cleanup: bool = False) -> bool:
        # Waiting for the lane is cancellable. Only an actual GATT write needs
        # settlement, otherwise cancelling a queued task could start movement.
        async with self.ble_lock:
            if not self._current(press.link):
                if cleanup:
                    return False
                raise BedNotConnectedError
            context = current_command_context()
            if not cleanup and (
                press.cancel.is_set()
                or asyncio.get_running_loop().time() >= press.deadline
                or (
                    context is not None
                    and context.caller_is_cancelling is not None
                    and context.caller_is_cancelling()
                )
            ):
                note_frame_skipped()
                return False
            frame = press.stop if cleanup else press.frame
            route = press.link.route

            async def write() -> bool:
                self._record_command_trace(
                    route.write, frame, response=route.response, characteristic=press.link.write
                )
                press.started = True
                # A stuck transport gets a bounded settlement before cleanup.
                async with asyncio.timeout(WRITE_TIMEOUT_S):
                    await press.link.client.write_gatt_char(
                        press.link.write, frame, response=route.response
                    )
                note_frame_written(None if cleanup else press.cancel)
                return True

            # Start GATT before yielding after the final admission checks.
            return await settled(write(), eager_start=True)

    async def _release(self, press: Press, *, acknowledge: CommandContext | None = None) -> None:
        async def release() -> None:
            started = asyncio.get_running_loop().time()
            for index in range(app.STOP_COUNT):
                if index:
                    await asyncio.sleep(
                        max(
                            0,
                            started
                            + index * app.REFRESH_MS / 1000
                            - asyncio.get_running_loop().time(),
                        )
                    )
                if not await self._send(press, cleanup=True):
                    return
            if acknowledge is not None:
                acknowledge.cleanup_stop_sent = True
                self._cleanup = (press.link, acknowledge)

        await settled(release())

    async def _press(self, frame: bytes, duration_ms: int) -> None:
        duration_ms = self.leased_hold_ms(duration_ms)
        press = Press(
            self._live(),
            frame,
            app.encode(self.branch, "stop"),
            asyncio.get_running_loop().time() + duration_ms / 1000,
            self._coordinator.cancel_command,
        )
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        self._cleanup = None
        try:
            while not press.cancel.is_set():
                tick = asyncio.get_running_loop().time()
                if not await self._send(press):
                    return
                remaining = (
                    min(tick + app.REFRESH_MS / 1000, press.deadline)
                    - asyncio.get_running_loop().time()
                )
                if remaining > 0:
                    try:
                        await asyncio.wait_for(press.cancel.wait(), remaining)
                    except TimeoutError:
                        pass
                if asyncio.get_running_loop().time() >= press.deadline:
                    return
        finally:
            if press.started:
                await self._release(press, acknowledge=context)

    def _build_command(self, command_value: int) -> bytes:
        action = app.ACTION_BY_WORD.get(command_value)
        if action not in (*app.ACTIONS[self.layout], "stop"):
            raise self.not_supported("that Restonic control")
        assert action is not None
        return app.encode(self.branch, action)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if command == app.encode(self.branch, "stop"):
            await self.stop_all()
            return
        if command not in {app.encode(self.branch, action) for action in app.ACTIONS[self.layout]}:
            raise self.not_supported("that Restonic control")
        await self._press(command, max(1, repeat_count) * app.REFRESH_MS)

    async def _write_single_shot(self, command: bytes) -> None:
        await self._press(command, app.REFRESH_MS)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in app.AXES[self.layout]:
            raise self.not_supported("that Restonic motor")
        if direction is None:
            await self.stop_all()
        else:
            action = _AXIS_ACTIONS[motor][0 if direction else 1]
            await self._press(
                app.encode(self.branch, action),
                self._coordinator.motor_pulse_count * app.REFRESH_MS,
            )

    async def move_neck_up(self) -> None:
        await self._move_motor("neck", True)

    async def move_neck_down(self) -> None:
        await self._move_motor("neck", False)

    async def move_neck_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        link = self._link
        if link is None or not self._current(link):
            return
        context = current_command_context()
        if self._cleanup is not None and context is not None:
            owner_link, owner = self._cleanup
            if (
                owner_link is link
                and any(owner is old for old in context.preempted_contexts)
                and owner.cleanup_stop_sent
            ):
                self._cleanup = None
                owner.cleanup_stop_sent = False
                return
        press = Press(link, b"", app.encode(self.branch, "stop"), 0, asyncio.Event())
        await self._release(press)

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = {
            "preset_flat": "flatPosition",
            "preset_zero_g": "zeroGravity",
            "preset_anti_snore": "anti",
            "preset_lounge": "lounge",
            "preset_tv": "tv",
            "preset_memory_1": "m1",
        }.get(key)
        return (
            ControllerHoldSpec(action)
            if action is not None and action in app.ACTIONS[self.layout]
            else None
        )

    @property
    def supports_preset_hold(self) -> bool:
        return True

    @property
    def held_preset_options(self) -> tuple[str, ...]:
        return tuple(self.profile.presets)

    async def hold_preset(self, preset: str, duration_ms: int) -> None:
        word = next((word for name, word in self.profile.presets.items() if name == preset), None)
        if word is None:
            raise self.not_supported("that Restonic preset")
        await self.hold_control(app.ACTION_BY_WORD[word], duration_ms)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        if slot not in self.profile.memory:
            raise self.not_supported("that Restonic memory")
        await self.hold_control("m1", hold_ms)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(app.ACTIONS[self.layout]) + tuple(
            f"{axis}_{direction}" for axis in app.AXES[self.layout] for direction in ("up", "down")
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported("that Restonic held control")
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= 60000:
            raise self.not_supported("a hold outside 0.1 to 60 seconds")
        if control.endswith(("_up", "_down")):
            axis, direction = control.rsplit("_", 1)
            control = _AXIS_ACTIONS[axis][0 if direction == "up" else 1]
        await self._press(app.encode(self.branch, control), duration_ms)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        def move(axis: str, up: bool):
            async def command(controller: BedController) -> None:
                await require_controller(controller, RestonicController)._move_motor(axis, up)

            return command

        def timed(axis: str):
            async def command(controller: BedController, up: bool, duration_ms: int) -> None:
                await require_controller(controller, RestonicController).hold_control(
                    f"{axis}_{'up' if up else 'down'}", duration_ms
                )

            return command

        return tuple(
            MotorControlSpec(
                axis,
                axis,
                move(axis, True),
                move(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
                timed_move_fn=timed(axis),
            )
            for axis in app.AXES[self.layout]
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def action(name: str):
            async def command(controller: BedController) -> None:
                await require_controller(controller, RestonicController).hold_control(
                    name, app.REFRESH_MS
                )

            return command

        return tuple(
            ControllerButtonSpec(
                f"restonic_{name}",
                name,
                action(name),
                translation_key=f"restonic_{name}",
                scheduler_resource="*",
                hold=ControllerHoldSpec(name),
                card=CARD_LIGHTING if name == "underbedLighting" else CARD_MASSAGE,
            )
            for name in ("underbedLighting", *app.MASSAGE)
            if name in app.ACTIONS[self.layout]
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        raw = (
            tuple(
                ControllerStateSensorSpec(
                    f"restonic_raw_{field}", f"restonic_raw_{field}", key, "mdi:code-braces"
                )
                for field, key in RAW_KEYS.items()
            )
            if self.branch != "box1220"
            else ()
        )
        return (
            ControllerStateSensorSpec(
                "restonic_branch", "restonic_branch", SELECTED_BRANCH, "mdi:bluetooth-settings"
            ),
            ControllerStateSensorSpec(
                "restonic_layout", "restonic_layout", SELECTED_LAYOUT, "mdi:bed"
            ),
            *raw,
        )


async def build_controller(ctx: BuildContext) -> RestonicController:
    return RestonicController(
        ctx.coordinator, branch=ctx.variant or "", layout=str(ctx.data.get(CONF_PRODUCT_TYPE, ""))
    )
