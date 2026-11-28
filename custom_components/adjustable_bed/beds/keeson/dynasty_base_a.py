"""Dynasty Base A session and gestures over the shared Keeson controller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS
from ...codec import keeson as codec
from ...command_scheduler import CommandContext, current_command_context, note_frame_skipped
from ...const import CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles import dynasty_base_a as app
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from .controller import KeesonController, _wait_unless_cancelled

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

TIMER: Final = StateKey[int | None]("dynasty_base_a_massage_timer")
# Home Assistant's optional-read budget, not an app protocol interval.
STATUS_READ_TIMEOUT_S: Final = 1.0


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    address: str
    write: BleakGATTCharacteristic
    receive: BleakGATTCharacteristic | None
    response: bool


@dataclass(slots=True)
class _StatusRead:
    link: _Link
    task: asyncio.Task[bytearray]
    discarded: bool = False


class _HoldExpired(Exception):
    """The bounded gesture expired while waiting for the BLE lane."""


class DynastyBaseAController(KeesonController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, layout: str) -> None:
        if layout not in app.LAYOUTS:
            raise ValueError("Choose a Dynasty Base A layout")
        super().__init__(coordinator, variant="base", char_uuid=codec.TRANSPORTS["base"].write_uuid)
        self.layout = layout
        self.route = "p1"
        self._link: _Link | None = None
        self._subscribed = False
        self._receiver = app.Receiver()
        self._massage_on: bool | None = None
        self._preset_cleanup: tuple[_Link, CommandContext] | None = None
        self._status_read: _StatusRead | None = None
        self._status_untrusted_client: BleakClient | None = None
        self._select_profile()

    def _select_profile(self) -> None:
        self.profile = replace(
            app.PROFILES[self.route],
            tilt="tilt" in app.LAYOUTS[self.layout],
            lumbar="lumbar" in app.LAYOUTS[self.layout],
        )
        transport = codec.TRANSPORTS[self.profile.transport]
        self._char_uuid, self._notify_char_uuid = transport.write_uuid, transport.notify_uuid

    @property
    def diagnostic_read_exclusions(self) -> frozenset[str]:
        # Proxy replies have no request ID; only this controller may own the
        # status waiter, including while an abandoned read is draining.
        return (
            frozenset({codec.TRANSPORTS["dynasty_p2"].notify_uuid.lower()})
            if self.route == "p2"
            else frozenset()
        )

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.route == "p1"

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"route": self.route, "layout": self.layout, "hardware": "UNVERIFIED"}

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != link.address
        ):
            raise ConnectionError("Dynasty Base A BLE session changed")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Dynasty Base A is disconnected")
        # Presence of P2's service overrides P1, even if its write role is missing.
        p2 = codec.TRANSPORTS["dynasty_p2"]
        self.route = "p2" if client.services.get_service(p2.service_uuid) is not None else "p1"
        self._select_profile()
        transport = codec.TRANSPORTS[self.profile.transport]
        tx_service = client.services.get_service(transport.service_uuid)
        rx_service = client.services.get_service(
            app.NOTIFY_SERVICE if self.route == "p1" else transport.service_uuid
        )
        write = tx_service.get_characteristic(transport.write_uuid) if tx_service else None
        receive = rx_service.get_characteristic(transport.notify_uuid) if rx_service else None
        if write is None or not {"write", "write-without-response"}.intersection(write.properties):
            raise BleakError("Dynasty Base A control characteristic is not writable")
        self._link = _Link(
            client,
            self._coordinator.address.upper(),
            write,
            receive,
            "write-without-response" not in write.properties,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        _expected: _Link | None = None,
        _deadline: float | None = None,
        _status_deadline: float | None = None,
    ) -> None:
        link = self._live(_expected)

        attempted = False

        def validate() -> None:
            nonlocal attempted
            self._live(link)
            if _deadline is not None and asyncio.get_running_loop().time() >= _deadline:
                note_frame_skipped()
                raise _HoldExpired
            attempted = True
            # A submitted change may have reached the receiver even if the
            # write fails. Only a subsequent valid status can confirm power.
            if self.route == "p2" and command != self._build_command(0):
                self._massage_on = None
                if self._status_read is not None:
                    self._status_read.discarded = True

        # Attempt optional P2 status after completed writes, including failures.
        # An earlier outstanding request retains exclusive ownership of its read.
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        read_deadline = _deadline if _status_deadline is None else _status_deadline
        for index in range(repeat_count):
            attempted = False
            if event.is_set():
                note_frame_skipped()
                return
            if index:
                await _wait_unless_cancelled(event, repeat_delay_ms / 1000)
            try:
                await self._write_gatt_with_retry(
                    link.write.uuid,
                    command,
                    cancel_event=event,
                    characteristic=link.write,
                    expected_client=link.client,
                    response=link.response,
                    before_write=validate,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # Optional status must not replace the actual write failure.
                if attempted:
                    try:
                        await self._read_status(link, cancel_event=event, deadline=read_deadline)
                    except ConnectionError:
                        pass
                raise
            else:
                self._live(link)
                if attempted:
                    await self._read_status(link, cancel_event=event, deadline=read_deadline)

    async def _read_status(
        self,
        link: _Link,
        *,
        cancel_event: asyncio.Event | None = None,
        deadline: float | None = None,
    ) -> None:
        self._live(link)
        if self.route != "p2" or link.receive is None:
            return
        # ESPHome matches replies by address/handle, without a request ID.
        # An abandoned request must drain before that key can be reused.
        if self._status_read is not None or self._status_untrusted_client is link.client:
            return
        budget = STATUS_READ_TIMEOUT_S
        if deadline is not None:
            budget = min(budget, deadline - asyncio.get_running_loop().time())
        if budget <= 0 or cancel_event is not None and cancel_event.is_set():
            return
        pending = _StatusRead(link, asyncio.create_task(link.client.read_gatt_char(link.receive)))
        self._status_read = pending
        pending.task.add_done_callback(lambda _task: self._finish_status_read(pending))
        cancelled = asyncio.create_task(cancel_event.wait()) if cancel_event is not None else None
        try:
            tasks: tuple[asyncio.Task[object], ...] = (
                (pending.task,) if cancelled is None else (pending.task, cancelled)
            )
            done, _ = await asyncio.wait(tasks, timeout=budget, return_when=asyncio.FIRST_COMPLETED)
            self._live(link)
            if pending.task not in done or cancelled is not None and cancelled in done:
                return
            if pending.discarded:
                return
            data = pending.task.result()
        except BleakError, TimeoutError:
            self._live(link)
            return
        finally:
            # Stop waiting, not the backend request: cancelling it removes the
            # proxy matcher and lets a late reply satisfy a subsequent read.
            pending.discarded = True
            if cancelled is not None:
                cancelled.cancel()
                await asyncio.gather(cancelled, return_exceptions=True)
        self._live(link)
        if cancel_event is not None and cancel_event.is_set():
            return
        self._receive(link, link.receive, data)

    def _finish_status_read(self, pending: _StatusRead) -> None:
        try:
            pending.task.result()
        except Exception, asyncio.CancelledError:
            # Backend timeout/cancellation removed its matcher. No same-link
            # response can now prove which request it belongs to.
            self._status_untrusted_client = pending.link.client
            if self.client is pending.link.client:
                self._massage_on = None
        if self._status_read is pending:
            self._status_read = None

    def _build_command(self, command_value: int) -> bytes:
        allowed = {
            0,
            app.LIGHT,
            *app.controls(self.route, self.layout).values(),
            *app.actions(self.route).values(),
        }
        if self.route == "p2":
            allowed.add(0x2000000)
        if command_value not in allowed:
            raise NotImplementedError("Unproven Dynasty Base A command")
        return app.frame(self.route, command_value)

    async def _zeros(self, link: _Link, count: int) -> None:
        # Finish all cleanup attempts on the captured connection under the command lane.
        async def cleanup() -> None:
            failure: Exception | None = None
            for _ in range(count):
                try:
                    await self.write_command(
                        self._build_command(0), cancel_event=asyncio.Event(), _expected=link
                    )
                except Exception as err:
                    failure = failure or err
            if failure is not None:
                raise failure

        task = asyncio.create_task(cleanup())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _release_motion(self, *, delay: bool = True) -> None:
        link, context = self._live(), current_command_context()
        cleanup, self._preset_cleanup = self._preset_cleanup, None
        if cleanup is not None and context is not None:
            owner_link, owner = cleanup
            if (
                owner_link is link
                and owner.scheduler_token is context.scheduler_token
                and any(owner is previous for previous in context.preempted_contexts)
            ):
                return
        await self._zeros(link, 3)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in app.LAYOUTS[self.layout]:
            raise ValueError("This layout has no such motor")
        if direction is None:
            await self.stop_all()
            return
        count = self.leased_hold_refreshes(app.REFRESH_MS) or self._coordinator.motor_pulse_count
        await self._hold_word(app.AXES[motor][not direction], count * app.REFRESH_MS, movement=True)

    async def _hold_word(self, word: int, duration_ms: int, *, movement: bool) -> None:
        link = self._live()
        self._preset_cleanup = None
        context = current_command_context()
        event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        try:
            if movement:
                await self._zeros(link, 3)
            self._live(link)
            if event.is_set():
                return
            deadline = loop.time() + duration_ms / 1000
            for _ in range(-(-duration_ms // app.REFRESH_MS)):
                if event.is_set() or loop.time() >= deadline:
                    break
                next_write = min(deadline, loop.time() + app.REFRESH_MS / 1000)
                await self.write_command(
                    self._build_command(word),
                    _expected=link,
                    _deadline=deadline,
                    _status_deadline=next_write,
                )
                await _wait_unless_cancelled(event, max(0, next_write - loop.time()))
        except _HoldExpired:
            pass
        finally:
            if movement:
                await self._zeros(link, 3)
            elif context is not None:
                # Only a STOP preempting this exact gesture ends refresh alone.
                self._preset_cleanup = (link, context)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{spec.key}_up", f"{spec.key}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for spec in super().motor_control_specs
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(app.controls(self.route, self.layout))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or isinstance(duration_ms, bool)
            or not 100 <= duration_ms <= 60000
        ):
            raise ValueError("Choose an offered control and a duration from 0.1 to 60 seconds")
        # Shared lease admission uses its full ceiling. Execution below caps
        # presets independently, including finite requests above eight seconds.

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = key.removeprefix("preset_")
        return ControllerHoldSpec(control) if control in self.held_control_options else None

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        movement = control.endswith(("_up", "_down"))
        if movement and self.leased_hold_refreshes(app.REFRESH_MS) is not None:
            axis, direction = control.rsplit("_", 1)
            await self._move_motor(axis, direction == "up")
            return
        await self._hold_word(
            app.controls(self.route, self.layout)[control],
            duration_ms
            if movement
            else min(self.leased_hold_ms(duration_ms), app.PRESET_HOLD_MAX_MS),
            movement=movement,
        )

    async def _tap(self, word: int, *, count: int = 3, zeros: int = 1) -> None:
        link = self._live()
        self._preset_cleanup = None
        try:
            await self.write_command(
                self._build_command(word), repeat_count=count, repeat_delay_ms=0, _expected=link
            )
        finally:
            if zeros:
                await self._zeros(link, zeros)

    async def _write_single_shot(self, command: bytes) -> None:
        # Shared preset/memory recall uses the app's memory-screen tap path.
        link = self._live()
        self._preset_cleanup = None
        try:
            await self.write_command(command, repeat_count=3, repeat_delay_ms=0, _expected=link)
        finally:
            await self._zeros(link, 1)

    async def lights_toggle(self) -> None:
        await self._tap(app.LIGHT, zeros=2)

    async def action(self, key: str) -> None:
        link = self._live()
        word = app.actions(self.route)[key]
        early = self.route == "p2" and key in ("foot_massage", "massage_power")
        if self.route == "p2" and key == "massage_power":
            # A remote or timer may have changed power since the last command.
            self._massage_on = None
            await self._read_status(link, cancel_event=self._coordinator.cancel_command)
            self._live(link)
            if self._coordinator.cancel_command.is_set():
                return
            if self._massage_on is None:
                raise invalid(
                    "dynasty_base_a_reconnect_required"
                    if self._status_untrusted_client is link.client
                    else "dynasty_base_a_status_required"
                )
            if self._massage_on:
                word = 0x2000000
        await self._tap(word, count=1 if early else 3, zeros=0 if early else 2)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = {
            "head_massage": "Head massage",
            "foot_massage": "Foot massage",
            "massage_power": "Toggle massage",
            "massage_timer": "Cycle massage timer",
            "massage_type": "Cycle massage type",
        }
        return tuple(
            ControllerButtonSpec(
                f"dynasty_base_a_{key}",
                label,
                lambda c, key=key: cast(DynastyBaseAController, c).action(key),
                translation_key=f"dynasty_base_a_{key}",
                card=CARD_MASSAGE,
                scheduler_resource="*",
            )
            for key, label in labels.items()
        ) + (
            ControllerButtonSpec(
                "dynasty_base_a_flat_zero_g",
                "Flat and zero gravity",
                lambda c: cast(DynastyBaseAController, c).hold_control("flat_zero_g", 100),
                translation_key="dynasty_base_a_flat_zero_g",
                card=CARD_PRESETS,
                scheduler_resource="*",
                hold=ControllerHoldSpec("flat_zero_g"),
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec(
                "dynasty_base_a_timer", "dynasty_base_a_timer", TIMER, card=CARD_MASSAGE_TIMER
            ),
        )

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self.write_command(codec.clock(dt_util.now()))

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        return AlarmCapability(
            wake_actions=tuple(app.WAKE), weekdays=True, cancel_running=True, resource=None
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link = self._live()
        try:
            if alarm.enabled:
                # Sunday is bit 0; the marker is used only for recurring alarms.
                if alarm.weekdays:
                    days = 0x80 | sum(1 << ((d + 1) % 7) for d in set(alarm.weekdays))
                else:
                    from datetime import timedelta

                    target = alarm.reference_time.replace(
                        hour=alarm.hour, minute=alarm.minute, second=0, microsecond=0
                    )
                    if target <= alarm.reference_time:
                        target += timedelta(days=1)
                    days = 1 << (target.isoweekday() % 7)
                packet = app.alarm(alarm.hour, alarm.minute, days, app.WAKE[alarm.wake_action])
                await self.write_command(codec.clock(dt_util.now()), _expected=link)
                await _wait_unless_cancelled(self._coordinator.cancel_command, app.ALARM_DELAY_S)
                await self.write_command(packet, _expected=link)
            else:
                await self.write_command(
                    app.alarm(0, 0, 0, 0), repeat_count=2, repeat_delay_ms=0, _expected=link
                )
        finally:
            await self._zeros(link, 1)

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self.route != "p1" or self._subscribed or link.receive is None:
            return
        try:
            await link.client.start_notify(
                link.receive, lambda sender, data: self._receive(link, sender, data)
            )
        except BleakError:
            return
        self._live(link)
        self._subscribed = True

    def _receive(self, link: _Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            self._live(link)
        except ConnectionError:
            return
        if link.receive is None or sender.handle != link.receive.handle:
            return
        self.forward_raw_notification(link.receive.uuid, bytes(data))
        packet = self._receiver.receive(self.route, bytes(data))
        status = app.status(self.route, packet) if packet is not None else None
        if status is not None:
            timer, light, massage = status
            self.forward_controller_state_updates(TIMER(timer))
            if light is not None:
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(light))
            if massage is not None:
                self._massage_on = massage

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self.on_disconnect()
        if (
            link is not None
            and subscribed
            and link.receive is not None
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.receive)

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(TIMER(None), UNDER_BED_LIGHTS_ON(None))

    def on_disconnect(self) -> None:
        if self._status_read is not None:
            self._status_read.discarded = True
        self._link, self._subscribed = None, False
        self._receiver = app.Receiver()
        self._massage_on = None
        self._preset_cleanup = None
        self._motor_state.clear()
        if self._coordinator.controller is self:
            self.invalidate_diagnostics()


async def build_controller(ctx: BuildContext) -> DynastyBaseAController:
    return DynastyBaseAController(ctx.coordinator, layout=ctx.data.get(CONF_PROTOCOL_VARIANT, "40"))
