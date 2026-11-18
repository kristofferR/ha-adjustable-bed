"""Linx's independently selected model and BLE route, with session-owned cleanup."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...app_session import app_session
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...codec import linx as codec
from ...command_scheduler import current_command_context
from ...const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...profiles import linx as app
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
TIMER: Final = StateKey[int | None]("linx_massage_minutes")
MODE: Final = StateKey[int | None]("linx_massage_mode")
VERSION: Final = StateKey[str | None]("linx_device_version")
SETUP_RESULT: Final = StateKey[str | None]("linx_setup_reply")
CHECK: Final = StateKey[str | None]("linx_self_check")
CHECK_DETAIL: Final = StateKey[dict[str, object] | None]("linx_self_check_detail")


@dataclass(slots=True)
class _Owner:
    publisher: object | None = None


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    device: str
    owner: object


_MASSAGE_BUTTON_NAMES: Final = {
    "head": "Head massage",
    "foot": "Foot massage",
    "timer": "Cycle massage timer",
}


class _HoldExpired(Exception):
    """A queued refresh lost its elapsed-time allowance before transmission."""


class LinxController(ProfileExecution[app.LinxProfile], BedController):
    """One physical receiver, no inferred ctrm/bedmd side addressing."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, model: str, route: str, device: str
    ) -> None:
        super().__init__(coordinator)
        if model not in app.PROFILES or route not in app.ROUTES or not device:
            raise ValueError("Choose a Linx model, BLE transport and exact Bluetooth name")
        if app.ROUTES[route].event_transport == "uart":
            codec.startup_query(device)  # Refuse an unusable suffix before setup connects.
        self.profile = app.PROFILES[model]
        self.route = route
        self.transport = app.ROUTES[route].event_transport
        self.device = device
        self._owner = app_session(coordinator.hass, coordinator.address, "linx", _Owner)
        self._link: _Link | None = None
        self._notifying = False
        self._bed_mode: int | None = None
        self._head_ripple_max = self._foot_ripple_max = 0
        self._snore_task: asyncio.Task[None] | None = None
        self._check_task: asyncio.Task[None] | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.TRANSPORTS[self.transport].write

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return not self.profile.massage

    @property
    def supports_memory_presets(self) -> bool:
        return self.profile.massage

    @property
    def memory_slot_count(self) -> int:
        return 4 if self.profile.massage else 0

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return self.profile.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.profile.massage

    def _role(self, transport: codec.Transport, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Linx is disconnected")
        for service in client.services:
            if service.uuid.lower() == transport.service:
                char = service.get_characteristic(uuid)
                if char is not None:
                    return char
        raise BleakError(f"Linx requires {uuid} under {transport.service}")

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        transport = codec.TRANSPORTS[self.transport]
        write = self._role(transport, transport.write)
        notify = self._role(transport, transport.notify)
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise BleakError("Linx control characteristic is not writable")
        if transport.subscription not in notify.properties:
            raise BleakError(f"Linx requires {transport.subscription} on {notify.uuid}")
        client = self.client
        assert client is not None
        owner = object()
        self._owner.publisher = owner
        self._link = _Link(client, write, notify, self.device, owner)

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self._owner.publisher is not current.owner
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Linx operation belongs to an ended BLE session")
        transport = codec.TRANSPORTS[self.transport]
        if (
            self._role(transport, transport.write) is not current.write
            or self._role(transport, transport.notify) is not current.notify
        ):
            raise ConnectionError("Linx GATT roles changed")
        return current

    async def _send(
        self,
        link: _Link,
        frame: bytes,
        event: asyncio.Event,
        *,
        status: bool = False,
        uart: bool = False,
        before: Callable[[], None] | None = None,
    ) -> None:
        self._live(link)
        destination = (
            codec.TRANSPORTS["a00a"] if status else codec.TRANSPORTS["uart"] if uart else None
        )
        char = self._role(destination, destination.write) if destination is not None else link.write

        def check() -> None:
            self._live(link)
            if destination is not None and self._role(destination, char.uuid) is not char:
                raise ConnectionError("Linx status destination changed")
            if not {"write", "write-without-response"}.intersection(char.properties):
                raise BleakError("Linx destination is not writable")

        async def chunks() -> None:
            for offset in range(0, len(frame), app.WRITE_CHUNK_SIZE):
                written = False

                def acknowledged() -> None:
                    nonlocal written
                    written = True

                def admit(offset: int = offset) -> None:
                    check()
                    if offset == 0 and before is not None:
                        before()

                # Once a split buffer starts, complete that same buffer before
                # STOP. Neither a deadline nor cancellation may send a tail alone.
                await self._write_gatt_with_retry(
                    char.uuid,
                    frame[offset : offset + app.WRITE_CHUNK_SIZE],
                    cancel_event=event if offset == 0 else asyncio.Event(),
                    response="write" in char.properties,
                    characteristic=char,
                    expected_client=link.client,
                    before_write=admit,
                    on_write=acknowledged,
                )
                if not written:
                    return

        if len(frame) > app.WRITE_CHUNK_SIZE:
            await self._finish(asyncio.create_task(chunks()))
        else:
            await chunks()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 3,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if event.is_set():
                return
            await self._send(link, command, event)
            if index + 1 < repeat_count:
                await self._wait(event, repeat_delay_ms / 1000)

    @staticmethod
    async def _wait(event: asyncio.Event, seconds: float) -> None:
        if seconds <= 0 or event.is_set():
            return
        try:
            await asyncio.wait_for(event.wait(), seconds)
        except TimeoutError:
            pass

    async def async_on_connect(self, session: ControllerSession) -> None:
        await asyncio.sleep(app.CONNECT_SETTLE_MS / 1000)
        if not session.is_current():
            raise ConnectionError("Linx startup session ended")
        await session.async_start_notify()
        await self.query_status()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        await link.client.start_notify(
            link.notify, lambda sender, data: self._notification(link, sender, data)
        )
        self._live(link)
        self._notifying = True

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if (
            notifying
            and link is not None
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        self._notifying = False
        self._bed_mode = None
        self._head_ripple_max = self._foot_ripple_max = 0
        self._cancel_jobs()
        if link is not None and self._owner.publisher is link.owner:
            self._owner.publisher = None
            self.forward_controller_state_updates(
                TIMER(None),
                MODE(None),
                VERSION(None),
                SETUP_RESULT(None),
                CHECK(None),
                CHECK_DETAIL(None),
            )

    def _cancel_jobs(self) -> None:
        for task in (self._snore_task, self._check_task):
            if task is not None:
                task.cancel()
        self._snore_task = self._check_task = None

    async def stop_keepalive(self) -> None:
        self._cancel_jobs()

    def _notification(self, link: _Link, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            self._live(link)
        except ConnectionError, BleakError:
            return
        raw = bytes(data)
        self.forward_raw_notification(link.notify.uuid, raw)
        if self.transport == "uart":
            reply = codec.setup_reply(raw)
            if reply is not None:
                self.forward_controller_state_updates(SETUP_RESULT(reply.result))
                if reply.version is not None:
                    self.forward_controller_state_updates(VERSION(reply.version))
            # The other binary consumer only calls empty UI callbacks. Do not
            # turn its short-packet crash or unused offsets into measured state.
            return
        self._bed_mode = codec.bed_mode(raw, self._bed_mode)
        payload = codec.status(raw)
        reported = payload.get("data")
        if isinstance(reported, dict):
            timer, mode = (reported.get(key) for key in ("apld", "mgmd"))
            # ``blsw`` has no proven meaning (both Android callbacks are empty),
            # so it stays in the raw notification capture only.
            if self.profile.massage:
                if type(timer) is int and 0 <= timer <= 3:
                    self.forward_controller_state_updates(TIMER(timer * 10))
                if type(mode) is int and 0 <= mode <= 3:
                    self.forward_controller_state_updates(MODE(mode))
        result = codec.diagnostic(payload)
        if result is not None and self._check_task is not None and result.complete:
            self._check_task.cancel()
            self._check_task = None
            self._head_ripple_max = max(self._head_ripple_max, result.head_ripple)
            self._foot_ripple_max = max(self._foot_ripple_max, result.foot_ripple)
            self.forward_controller_state_updates(
                CHECK("complete"),
                CHECK_DETAIL(
                    {
                        "head_fault": result.head,
                        "foot_fault": result.foot,
                        "head_massage_connected": result.head_massage,
                        "foot_massage_connected": result.foot_massage,
                        "head_ripple": result.head_ripple,
                        "foot_ripple": result.foot_ripple,
                        "head_ripple_max": self._head_ripple_max,
                        "foot_ripple_max": self._foot_ripple_max,
                    }
                ),
            )

    async def query_status(self) -> None:
        link = self._live()
        event = self._coordinator.cancel_command
        if self.transport == "uart":
            await self._send(link, codec.startup_query(link.device), event)
        else:
            await self._send(link, codec.request(link.device, 4, {"sw": 1}), event)
        await self._send(link, codec.request(link.device, 7, {"bedmd": 100}), event)

    def _touch(self) -> int:
        mode = self._bed_mode
        if self.profile.consumes_mode:
            self._bed_mode = None
        return 6 if mode == 2 else self.profile.unknown_mode_km if mode is None else 10

    async def _release(self, link: _Link, frame: bytes) -> None:
        async def release() -> None:
            await self._send(link, frame, asyncio.Event())
            if (context := current_command_context()) is not None:
                context.cleanup_stop_sent = True

        await self._finish(asyncio.create_task(release()))

    @staticmethod
    async def _finish(task: asyncio.Task[None]) -> None:
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _gesture(self, axis: str, up: bool, duration_ms: int) -> None:
        if axis not in app.AXES:
            raise ValueError("Unknown Linx motor")
        link = self._live()
        frame = codec.control(
            link.device, app.AXES[axis][0 if up else 1], km=self._touch(), held=True
        )
        release = app.release(self.profile, link.device, axis)
        event = self._coordinator.cancel_command
        deadline: float | None = None
        loop = asyncio.get_running_loop()

        def admit_refresh() -> None:
            nonlocal deadline
            # Start a short hold at its first admitted wire write, after any
            # GATT lane wait. Later refreshes never backfill elapsed time.
            if deadline is None:
                deadline = loop.time() + duration_ms / 1000
            elif loop.time() >= deadline:
                raise _HoldExpired

        try:
            while not event.is_set():
                if deadline is not None and loop.time() >= deadline:
                    break
                await self._send(link, frame, event, before=admit_refresh)
                if event.is_set():
                    break
                assert deadline is not None
                await self._wait(
                    event, min(self.profile.refresh_ms / 1000, max(0, deadline - loop.time()))
                )
        except _HoldExpired:
            pass
        finally:
            await self._release(link, release)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, self.profile.refresh_ms

    async def move_axis(self, axis: str, up: bool) -> None:
        count = (
            self.leased_hold_refreshes(self.profile.refresh_ms)
            or self._coordinator.motor_pulse_count
        )
        await self._gesture(axis, up, count * self.profile.refresh_ms)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{direction}" for axis in app.AXES for direction in ("up", "down"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a Linx movement and a duration of 1–30000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        await self._gesture(axis, direction == "up", self.leased_hold_ms(duration_ms))

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                lambda c, axis=axis: cast(LinxController, c).move_axis(axis, True),
                lambda c, axis=axis: cast(LinxController, c).move_axis(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side"),
            )
            for axis in app.AXES
        )

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_feet_up(self) -> None:
        await self.move_axis("feet", True)

    async def move_feet_down(self) -> None:
        await self.move_axis("feet", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_back_stop = move_head_stop
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_legs_stop = move_head_stop
    move_feet_stop = move_head_stop

    async def stop_all(self) -> None:
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        link = self._live()
        # An active gesture owns its model/axis-specific release. Without one,
        # the explicit combined-axis STOP is the app's JSON zero command.
        await self._release(link, app.release(self.profile, link.device))

    async def _tap(self, word: int) -> None:
        self._touch()
        link = self._live()
        await self._send(link, codec.control(link.device, word), self._coordinator.cancel_command)

    async def preset_flat(self) -> None:
        await self._tap(app.PRESETS["flat"])

    async def preset_zero_g(self) -> None:
        await self._tap(app.PRESETS["zero_g"])

    async def preset_anti_snore(self) -> None:
        if not self.supports_preset_anti_snore:
            raise NotImplementedError("Linx 2.5 Q exposes this key as Memory 1")
        await self._tap(app.MEMORY[1])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._tap(app.MEMORY[memory_num])

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Linx has no direct BLE memory programming")

    async def lights_toggle(self) -> None:
        await self._tap(app.LIGHT)

    async def massage_action(self, action: str) -> None:
        if not self.profile.massage or action not in app.MASSAGE:
            raise ValueError("This Linx model has no such massage control")
        # statsBo is never updated in the app. Mode always sends its zero branch.
        await self._tap(app.MASSAGE[action])

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.profile.massage

    async def massage_mode_step(self) -> None:
        await self.massage_action("mode")

    async def clear_alarm(self, slot: int | None) -> None:
        slots = range(1, 7) if slot is None else (slot,)
        link = self._live()
        frames = tuple(codec.alarm_slot(link.device, number) for number in slots)
        for frame in frames:
            if self._coordinator.cancel_command.is_set():
                return
            await self._send(link, frame, self._coordinator.cancel_command)

    def validate_snore_intervention(self) -> None:
        link = self._live()
        char = (
            self._role(codec.TRANSPORTS["uart"], codec.TRANSPORTS["uart"].write)
            if app.ROUTES[self.route].snore_uart
            else link.write
        )
        if not {"write", "write-without-response"}.intersection(char.properties):
            raise ValueError("The selected Linx intervention destination is not writable")

    async def snore_intervention(
        self,
        *,
        keep: int = app.SNORE_DEFAULT,
        speed: int = app.SNORE_DEFAULT,
        lift: int = app.SNORE_DEFAULT,
    ) -> None:
        link = self._live()
        if self._snore_task is not None:
            self._snore_task.cancel()
        due = asyncio.get_running_loop().time() + max(0, codec.snore_delay_ms(keep)) / 1000
        binary = app.ROUTES[self.route].snore_uart
        await self._send(
            link,
            codec.snore(link.device, uart=binary, keep=keep, speed=speed, lift=lift),
            self._coordinator.cancel_command,
            uart=binary,
        )

        async def follow_up() -> None:
            try:
                await asyncio.sleep(max(0, due - asyncio.get_running_loop().time()))
                # Never reconnect for an old intervention; the status destination
                # is A00A even when its intervention used UART (E07).
                self._live(link)
                await self._coordinator.async_execute_controller_query(
                    lambda _c: self._send(
                        link, codec.SNORE_STATUS, self._coordinator.cancel_command, status=True
                    ),
                    cancel_running=False,
                    skip_disconnect=True,
                    preemptible=True,
                    run_if=lambda: (
                        self._link is link
                        and self._owner.publisher is link.owner
                        and self._coordinator.controller is self
                        and self.client is link.client
                        and link.client.is_connected
                    ),
                    preserve_idle_deadline=True,
                )
            except ConnectionError, BleakError:
                _LOGGER.debug("Linx intervention follow-up ended with its link", exc_info=True)

        if not self._coordinator.cancel_command.is_set():
            self._snore_task = asyncio.create_task(follow_up())

    async def self_check(self) -> None:
        link = self._live()
        if self._check_task is not None:
            self._check_task.cancel()
        self.forward_controller_state_updates(CHECK("running"), CHECK_DETAIL(None))

        async def timeout() -> None:
            await asyncio.sleep(app.DIAGNOSTIC_TIMEOUT)
            try:
                self._live(link)
            except ConnectionError, BleakError:
                return
            self.forward_controller_state_updates(CHECK("timeout"))
            self._check_task = None

        self._check_task = asyncio.create_task(timeout())
        try:
            await self._send(
                link,
                codec.request(link.device, 6, {"key": "80000000", "km": 2}),
                self._coordinator.cancel_command,
            )
        except BaseException:
            if self._check_task is not None:
                self._check_task.cancel()
                self._check_task = None
            self.forward_controller_state_updates(CHECK("write_failed"))
            raise

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Status is queried on every connect and arrives by notification, so
        # there is no refresh button.
        buttons = [
            ControllerButtonSpec(
                "linx_self_check",
                "Run self-check",
                lambda c: cast(LinxController, c).self_check(),
                translation_key="linx_self_check",
                scheduler_resource="*",
                invalidates_position=True,
            ),
        ]
        if self.profile.massage:
            buttons.extend(
                ControllerButtonSpec(
                    f"linx_massage_{key}",
                    _MASSAGE_BUTTON_NAMES[key],
                    lambda c, key=key: cast(LinxController, c).massage_action(key),
                    translation_key=f"linx_massage_{key}",
                    card=CARD_MASSAGE_TIMER if key == "timer" else CARD_MASSAGE,
                )
                for key in app.MASSAGE
                if key != "mode"
            )
        return tuple(buttons)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs: list[ControllerStateSensorSpec] = []
        if self.transport == "a00a":
            # Only A00A notifications carry the self-check reply.
            specs.append(
                ControllerStateSensorSpec(
                    key=str(CHECK),
                    translation_key=str(CHECK),
                    state_key=CHECK,
                    icon="mdi:stethoscope",
                    attribute_keys=(CHECK_DETAIL,),
                )
            )
        else:
            # Only the UART startup reply carries a version; its result rides along.
            specs.append(
                ControllerStateSensorSpec(
                    key=str(VERSION),
                    translation_key=str(VERSION),
                    state_key=VERSION,
                    icon="mdi:information-outline",
                    attribute_keys=(SETUP_RESULT,),
                    entity_registry_enabled_default=False,
                )
            )
        if self.profile.massage and self.transport == "a00a":
            specs.extend(
                (
                    ControllerStateSensorSpec(
                        "linx_massage_minutes",
                        "linx_massage_minutes",
                        TIMER,
                        "mdi:timer-outline",
                        native_unit_of_measurement="min",
                        card=CARD_MASSAGE_TIMER,
                    ),
                    ControllerStateSensorSpec(
                        "linx_massage_mode",
                        "linx_massage_mode",
                        MODE,
                        "mdi:sine-wave",
                        card=CARD_MASSAGE,
                    ),
                )
            )
        return tuple(specs)


async def build_controller(ctx: BuildContext) -> LinxController:
    return LinxController(
        ctx.coordinator,
        model=str(ctx.data.get(CONF_PRODUCT_TYPE, "")),
        route="a00a" if ctx.variant in (None, "auto") else ctx.variant,
        device=ctx.live_device_name or str(ctx.data.get(CONF_BLE_DEVICE_NAME, "")),
    )
