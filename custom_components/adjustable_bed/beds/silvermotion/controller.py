"""SILVERmotion Android control, with transactions owned by one physical session."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...app_session import app_session
from ...codec import silvermotion as codec
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
    note_frame_written,
)
from ...const import CONF_HAS_MASSAGE, CONF_PRODUCT_TYPE, RUNTIME_BOND_KEYS
from ...profiles import silvermotion as app
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _Owner:
    publisher: object | None = None
    minutes: int = 10
    deadline: float | None = None


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    characteristic: BleakGATTCharacteristic
    owner: object
    address: str
    config: dict[str, object]


@dataclass(frozen=True, slots=True)
class _Operation:
    link: _Link
    cancel: asyncio.Event
    generation: int
    side: str | None


def _press(action: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        if not isinstance(controller, SilvermotionController):
            raise TypeError("SILVERmotion control requires its app controller")
        if action in app.MOVEMENTS:
            await controller._move(action)
        elif action == "release":
            await controller.stop_all()
        else:
            await controller.press(action)

    return press


class SilvermotionController(ProfileExecution[app.SilvermotionProfile], BedController):
    """One receiver with two movement groups, without measured position state."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.ANDROID
        self.size = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, "queen"))
        if self.size not in app.SIZES:
            raise ValueError("Choose Queen, King or Twin XL for SILVERmotion")
        self._massage = bool(coordinator.entry.data.get(CONF_HAS_MASSAGE, True))
        self._owner = app_session(coordinator.hass, coordinator.address, "silvermotion", _Owner)
        self._link: _Link | None = None
        self._generation = 0
        self._receiver = codec.Receiver()
        self._ack = asyncio.Event()
        self._timer: asyncio.Task[None] | None = None
        self._notifying = False
        self._releasing = False

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.CHARACTERISTIC

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def startup_verifies_control_access(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    def _configuration(self) -> dict[str, object]:
        # Bond evidence is updated by shared setup/repair after discovery.
        # It does not change the app profile or the physical command owner.
        return {
            key: value
            for key, value in self._coordinator.entry.data.items()
            if key not in RUNTIME_BOND_KEYS
        }

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
            or self._owner.publisher is not current.owner
            or self._coordinator.controller is not self
            or self._coordinator.address != current.address
            or self._configuration() != current.config
        ):
            raise ConnectionError("SILVERmotion physical session or configuration changed")
        char = self._role(current.client)
        if char is not current.characteristic:
            raise ConnectionError("SILVERmotion GATT role changed")
        return current

    @staticmethod
    def _role(client: BleakClient) -> BleakGATTCharacteristic:
        for service in client.services:
            if service.uuid.lower() == codec.SERVICE:
                for char in service.characteristics:
                    if char.uuid.lower() == codec.CHARACTERISTIC:
                        if (
                            "write-without-response" in char.properties
                            and "notify" in char.properties
                        ):
                            return char
        raise ConnectionError(
            "SILVERmotion requires its write-without-response/notify characteristic"
        )

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("SILVERmotion is disconnected")
        char = self._role(client)
        owner = object()
        self._owner.publisher = owner
        self._link = _Link(client, char, owner, self._coordinator.address, self._configuration())
        self._releasing = False

    def _operation(self, cancel: asyncio.Event | None = None) -> _Operation:
        return _Operation(
            self._live(),
            self._coordinator.cancel_command if cancel is None else cancel,
            self._generation,
            self.command_side,
        )

    def _admit(self, op: _Operation) -> bool:
        self._live(op.link)
        if (
            self._releasing
            or op.side != self.command_side
            or op.generation != self._generation
            or op.cancel.is_set()
        ):
            note_frame_skipped()
            return False
        return True

    async def _frame(
        self,
        op: _Operation,
        payload: bytes,
        repeat: int,
        *,
        admit: Callable[[], bool] | None = None,
        on_sent: Callable[[], None] | None = None,
    ) -> bool:
        """Once accepted, finish every fragment to this client before STOP can run."""
        if not self._admit(op):
            return False
        if admit is not None and not admit():
            note_frame_skipped()
            return False
        if not self._notifying:
            await self.start_notify()
        async with self.ble_lock:
            if admit is not None and not admit():
                note_frame_skipped()
                return False
            if not self._admit(op):
                return False
            self._ack.clear()
            frame = codec.encode(payload, repeat, self.profile.delay)

            async def transaction() -> bool:
                # settled() starts a task. Admission belongs inside that task,
                # immediately before its first write, rather than before scheduling it.
                if not self._admit(op):
                    return False
                if admit is not None and not admit():
                    note_frame_skipped()
                    return False
                chunks = codec.chunks(frame)
                for index, chunk in enumerate(chunks):
                    self._live(op.link)
                    char = op.link.characteristic
                    self._record_command_trace(
                        char.uuid, chunk, response=False, characteristic=char
                    )
                    await op.link.client.write_gatt_char(char, chunk, response=False)
                    note_frame_written(op.cancel)
                    self._live(op.link)
                    if index == len(chunks) - 1:
                        if on_sent is not None:
                            on_sent()
                        await self._coordinator.async_note_control_access_succeeded()
                    await asyncio.sleep(self.profile.chunk_ms / 1000)
                    self._live(op.link)
                return True

            if not await settled(transaction()):
                return False
        # An acknowledgement only ends the native response wait. It does not
        # prove the bed accepted the action, or carry measured state.
        try:
            async with asyncio.timeout(self.profile.response_ms / 1000):
                await cancellable(self._ack.wait(), op.cancel)
        except TimeoutError:
            pass
        self._live(op.link)
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 150,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        op = self._operation(cancel_event)
        for index in range(repeat_count):
            if index:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), op.cancel)
            if not await self._frame(op, command, 3):
                return

    async def _action(self, op: _Operation, action: str) -> bool:
        return await self._frame(op, app.COMMANDS[action], app.repeat_count(action))

    async def _release(self, link: _Link, generation: int | None = None) -> None:
        # Release belongs to its captured link. A replacement never receives it.
        try:
            self._live(link)
        except ConnectionError:
            return
        if generation is not None and generation != self._generation:
            return
        op = _Operation(link, asyncio.Event(), self._generation, self.command_side)
        sent = await settled(self._action(op, "release"))
        if sent and (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(sorted(app.MOVEMENTS))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in app.MOVEMENTS
            or isinstance(duration_ms, bool)
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a SILVERmotion direction and a hold of 1..30000 milliseconds")

    async def _before_motion(self, op: _Operation) -> None:
        deadline = self._owner.deadline
        if deadline is None or not self._massage:
            return
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 30:
            await self._send_feature(op, "massage_off")
            if remaining > 0:
                await cancellable(asyncio.sleep(0.5), op.cancel)
            self._admit(op)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        op = self._operation()
        await self._before_motion(op)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + min(self.leased_hold_ms(duration_ms), 30000) / 1000
        started = False
        try:
            while loop.time() < deadline:
                if not self._admit(op):
                    return
                tick = loop.time()
                started = True
                await self._action(op, control)
                if not self._admit(op):
                    return
                await cancellable(
                    asyncio.sleep(
                        max(0, min(deadline, tick + self.profile.refresh_ms / 1000) - loop.time())
                    ),
                    op.cancel,
                )
        except asyncio.CancelledError:
            if loop.time() < deadline:
                note_frame_skipped()
            raise
        finally:
            if started:
                await self._release(op.link, op.generation)

    async def _move(self, control: str) -> None:
        await self.hold_control(
            control, min(30000, max(1, self._coordinator.motor_pulse_count) * 150)
        )

    async def stop_all(self) -> None:
        self._generation += 1
        await self._release(self._live())

    async def press(self, action: str) -> None:
        if action not in app.COMMANDS or action in (*app.MOVEMENTS, "release", "any_key"):
            raise ValueError("Choose an available SILVERmotion app control")
        if action.startswith("massage_") and not self.supports_massage:
            raise ValueError("Massage is disabled for this SILVERmotion bed")
        op = self._operation()
        if action in (*app.PRESETS, "memory_1", "memory_2"):
            await self._before_motion(op)
        if action in ("flat", "memory_1", "memory_2"):
            try:
                if not await self._action(op, "any_key"):
                    return
                await cancellable(asyncio.sleep(self.profile.recall_gap_ms / 1000), op.cancel)
            except asyncio.CancelledError:
                note_frame_skipped()
                raise
        await self._send_feature(op, action)

    async def _send_feature(self, op: _Operation, action: str) -> bool:
        sent = False

        def completed(delivery: Delivery) -> None:
            nonlocal sent
            sent = delivery is Delivery.SENT
            if not sent:
                return
            try:
                self._live(op.link)
            except ConnectionError:
                return
            if action == "massage_off":
                self._clear_timer()
            elif action.startswith("massage_"):
                self._owner.deadline = asyncio.get_running_loop().time() + self._owner.minutes * 60
                self._arm_timer(op.link)

        with delivered(completed):
            await self._action(op, action)
        return sent

    def _clear_timer(self) -> None:
        self._owner.deadline = None
        if self._timer is not None and self._timer is not asyncio.current_task():
            self._timer.cancel()
        self._timer = None

    def _arm_timer(self, link: _Link) -> None:
        if self._timer is not None:
            self._timer.cancel()
        deadline = self._owner.deadline
        if deadline is None:
            return
        # Acquire synchronously so command completion cannot hand the link off
        # before the countdown task starts. The callback also covers pre-start cancellation.
        connection = self._coordinator.hold_command_connection()
        connection.__enter__()

        async def expire() -> None:
            try:
                await asyncio.sleep(max(0, deadline - asyncio.get_running_loop().time()))
                self._live(link)
                if self._owner.deadline != deadline:
                    return
                generation = self._generation
                stop_epoch = self._coordinator.command_scheduler.stop_epoch

                def current() -> bool:
                    try:
                        self._live(link)
                    except ConnectionError:
                        return False
                    return (
                        self._notifying
                        and not self._coordinator.is_shutting_down
                        and not self._releasing
                        and self._owner.deadline == deadline
                        and self._generation == generation
                        and not self._coordinator.command_scheduler.has_pending_stop
                        and self._coordinator.command_scheduler.stop_epoch == stop_epoch
                    )

                async def off(controller: BedController) -> None:
                    if controller is self and current():

                        def sent() -> None:
                            if self._owner.deadline == deadline:
                                self._clear_timer()

                        op = _Operation(link, asyncio.Event(), generation, self.command_side)
                        await self._frame(
                            op, app.COMMANDS["massage_off"], 3, admit=current, on_sent=sent
                        )

                self._timer = None
                await self._coordinator.async_execute_controller_query(
                    off,
                    cancel_running=False,
                    preemptible=False,
                    run_if=current,
                    skip_disconnect=True,
                    preserve_idle_deadline=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # An incomplete frame leaves the deadline for the next motion's off retry.
                _LOGGER.debug("SILVERmotion local massage timer could not send off", exc_info=True)

        self._timer = asyncio.create_task(expire())
        self._timer.add_done_callback(lambda _task: connection.__exit__(None, None, None))

    @property
    def supports_massage_timer(self) -> bool:
        return self.supports_massage

    @property
    def massage_timer_options(self) -> list[int]:
        return list(range(1, 41))

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage or isinstance(minutes, bool) or minutes not in range(1, 41):
            raise ValueError("SILVERmotion massage timer must be 1..40 minutes")
        link = self._live()
        self._owner.minutes = minutes
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(minutes))
        if self._owner.deadline is not None:
            self._owner.deadline = asyncio.get_running_loop().time() + minutes * 60
            self._arm_timer(link)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        self._receiver = codec.Receiver()
        self._ack.clear()
        async with self.ble_lock:
            await settled(
                link.client.start_notify(
                    link.characteristic, lambda sender, data: self._notification(link, sender, data)
                )
            )
        self._live(link)
        self._notifying = True
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(self._owner.minutes))
        if (
            self._massage
            and self._owner.deadline is not None
            and self._owner.deadline > asyncio.get_running_loop().time()
        ):
            self._arm_timer(link)

    def _notification(self, link: _Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            self._live(link)
        except ConnectionError:
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        for plain in self._receiver.feed(bytes(data)):
            if len(plain) >= 5 and plain[0] == 3:
                self._ack.set()

    async def stop_notify(self) -> None:
        link = self._link
        if link is None:
            return
        async with self.ble_lock:
            try:
                self._live(link)
            except ConnectionError:
                return
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._notifying = False
            self._receiver = codec.Receiver()
            self._ack.set()
            # A failed backend disconnect can retain this physical link. Keep
            # its identity; the next frame restores its notification subscription.
            await settled(link.client.stop_notify(link.characteristic))

    async def async_resume_session(self) -> None:
        """Restore a subscription/countdown when teardown retained the same link."""
        if self._coordinator.is_shutting_down:
            return
        link = self._live()
        self._releasing = False
        await self.start_notify()
        if self._massage and self._owner.deadline is not None and self._timer is None:
            self._arm_timer(link)

    def on_connection_release(self, reason: str) -> None:
        self._releasing = True

    def on_disconnect(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._link is not None and self._owner.publisher is self._link.owner:
            self._owner.publisher = None
        self._link = None
        self._notifying = False
        self._releasing = True
        self._receiver = codec.Receiver()
        self._ack.set()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                _press(f"{axis}_up"),
                _press(f"{axis}_down"),
                _press("release"),
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side"),
            )
            for axis in ("back", "legs")
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return unique_buttons(
            catalog_button(
                action,
                label,
                _press(action),
                kind=Kind.PRESET if action in ("leg_up", "breakfast") else None,
                requires_confirmation=action.endswith("reset"),
                diagnostic=action.endswith("reset"),
            )
            for action, label in app.LABELS.items()
            if not action.startswith("massage_") or self.supports_massage
        )

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return self._massage

    @property
    def supports_lights(self) -> bool:
        return True

    async def preset_flat(self) -> None:
        await self.press("flat")

    async def preset_zero_g(self) -> None:
        await self.press("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.press("anti_snore")

    async def preset_lounge(self) -> None:
        await self.press("lounge")

    async def preset_memory(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or memory_num not in (1, 2):
            raise ValueError("SILVERmotion has memory slots 1 and 2")
        await self.press(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or memory_num not in (1, 2):
            raise ValueError("SILVERmotion has memory slots 1 and 2")
        await self.press(f"save_memory_{memory_num}")

    async def lights_toggle(self) -> None:
        await self.press("light_toggle")

    async def lights_off(self) -> None:
        await self.press("light_off")

    async def massage_intensity_up(self) -> None:
        await self.press("massage_up")

    async def massage_intensity_down(self) -> None:
        await self.press("massage_down")

    async def massage_off(self) -> None:
        await self.press("massage_off")

    async def move_back_up(self) -> None:
        await self._move("back_up")

    async def move_back_down(self) -> None:
        await self._move("back_down")

    async def move_legs_up(self) -> None:
        await self._move("legs_up")

    async def move_legs_down(self) -> None:
        await self._move("legs_down")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        raise NotImplementedError("SILVERmotion has no separate head axis")

    async def move_head_down(self) -> None:
        raise NotImplementedError("SILVERmotion has no separate head axis")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("SILVERmotion has no separate feet axis")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("SILVERmotion has no separate feet axis")

    async def move_feet_stop(self) -> None:
        await self.stop_all()


def require_transport(client: BleakClient) -> None:
    """Check the same service and characteristic as runtime before changing apps."""
    SilvermotionController._role(client)  # noqa: SLF001 - shared route validation
