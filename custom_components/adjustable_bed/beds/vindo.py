"""Direct BLE control for the Carpe Diem Beds Vindö app."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ..card import CARD_HIDDEN, CARD_LIGHTING, CARD_MASSAGE, CARD_PRESETS
from ..codec.linak import control_frame, parse_vindo_position
from ..command_scheduler import (
    current_command_context,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ..const import (
    LINAK_CONTROL_CHAR_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_LEG_UUID,
    LINAK_POSITION_SERVICE_UUID,
)
from ..controller_state import StateKey
from ..errors import BedNotConnectedError
from ..execution import STREAM_HOLD, ExecutionCapabilities
from ..profiles import vindo as app
from ..profiles.vindo import Opcode
from .base import BedController, require_controller
from .cancellation import cancellable, settled
from .entity_specs import ControllerButtonSpec, ControllerStateSensorSpec

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTServiceCollection

    from ..coordinator import AdjustableBedCoordinator

_BACK_RAW: Final = StateKey[int | None]("vindo_back_raw")
_LEGS_RAW: Final = StateKey[int | None]("vindo_legs_raw")
# A memory must use two recent samples from this live link, even on reconnect.
_POSITION_FRESH_S: Final = 2.0
_MEMORY_SLOTS: Final = 5
_STOP: Final = control_frame(Opcode.STOP)
_POSITION_ROLES: Final = (
    (LINAK_POSITION_LEG_UUID, "legs", _LEGS_RAW),
    (LINAK_POSITION_BACK_UUID, "back", _BACK_RAW),
)


@dataclass(slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    subscribed: list[BleakGATTCharacteristic] = field(default_factory=list)
    samples: dict[str, tuple[int, float]] = field(default_factory=dict)
    position_updated: asyncio.Event = field(default_factory=asyncio.Event)
    ready: bool = False


def _role(
    services: BleakGATTServiceCollection, service_uuid: str, char_uuid: str
) -> BleakGATTCharacteristic:
    service = services.get_service(service_uuid)
    char = service.get_characteristic(char_uuid) if service is not None else None
    if char is None:
        raise BleakError(f"Vindö requires {char_uuid} under {service_uuid}")
    return char


def validate_gatt(
    services: BleakGATTServiceCollection,
) -> tuple[
    BleakGATTCharacteristic,
    tuple[tuple[BleakGATTCharacteristic, str, StateKey[int | None]], ...],
]:
    """Resolve the exact runtime roles, without subscribing or writing."""
    write = _role(services, LINAK_CONTROL_SERVICE_UUID, LINAK_CONTROL_CHAR_UUID)
    if "write" not in write.properties:
        raise BleakError("Vindö requires control writes with response")
    notifications = tuple(
        (_role(services, LINAK_POSITION_SERVICE_UUID, uuid), axis, key)
        for uuid, axis, key in _POSITION_ROLES
    )
    if any(
        not {"notify", "indicate"}.intersection(char.properties) for char, _, _ in notifications
    ):
        raise BleakError("Vindö requires both position notification characteristics")
    return write, notifications


async def _pause(event: asyncio.Event, seconds: float) -> None:
    """Wait after an acknowledged frame, waking immediately on STOP."""
    try:
        async with asyncio.timeout(seconds):
            await event.wait()
    except TimeoutError:
        pass


class VindoController(BedController):
    """Two-axis Vindö controller with raw, connection-owned position reports."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._link: _Link | None = None
        self._memories: dict[int, app.Positions] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return LINAK_CONTROL_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def execution(self) -> ExecutionCapabilities:
        return STREAM_HOLD

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_simultaneous_movement(self) -> bool:
        return True

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        return app.AXES

    def _current(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _live(self) -> _Link:
        link = self._link
        if link is None or not link.ready or not self._current(link):
            raise BedNotConnectedError
        return link

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        if self._link is not None and self._current(self._link) and self._link.ready:
            return

        write, notifications = validate_gatt(client.services)
        self.on_disconnect()
        link = self._link = _Link(client, write)
        try:
            for char, axis, key in notifications:
                if not self._current(link):
                    raise BedNotConnectedError
                link.subscribed.append(char)

                def receive(
                    sender: BleakGATTCharacteristic,
                    data: bytearray,
                    *,
                    axis: str = axis,
                    key: StateKey[int | None] = key,
                    source: BleakGATTCharacteristic = char,
                ) -> None:
                    if self._current(link) and sender.handle == source.handle:
                        self._receive(link, source.uuid, axis, key, data)

                await client.start_notify(char, receive)
            if not self._current(link):
                raise BedNotConnectedError
            link.ready = True
        except BaseException:
            if self._link is link:
                await settled(self.stop_notify())
            raise

    def _receive(
        self,
        link: _Link,
        uuid: str,
        axis: str,
        key: StateKey[int | None],
        data: bytearray,
    ) -> None:
        self.forward_raw_notification(uuid, bytes(data))
        value = parse_vindo_position(data)
        # Retain the exact unsigned diagnostic value. A short or all-ones
        # sample cannot establish a safe target or direction for a recall.
        if value is None or value == 0xFFFF:
            link.samples.pop(axis, None)
        else:
            link.samples[axis] = (value, asyncio.get_running_loop().time())
        link.position_updated.set()
        self.forward_controller_state_update(key, value)

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        if link is not None:
            link.position_updated.set()
            self.forward_controller_state_updates(_BACK_RAW(None), _LEGS_RAW(None))

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is None:
            return
        for char in link.subscribed:
            if (
                self._link is not None
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            try:
                await link.client.stop_notify(char)
            except BleakError:
                # The coordinator still owns the connection and closes it.
                continue

    async def _write(
        self,
        link: _Link,
        frame: bytes | Callable[[], bytes],
        event: asyncio.Event,
        *,
        deadline: float | None = None,
        cleanup: bool = False,
    ) -> bytes | None:
        """Admit one frame, or return a selector's STOP for the release path."""
        try:
            async with asyncio.timeout_at(deadline):
                await self._ble_lock.acquire()
        except TimeoutError:
            note_frame_skipped()
            return None
        except asyncio.CancelledError:
            note_frame_skipped()
            raise
        try:
            if event.is_set() or (
                deadline is not None and asyncio.get_running_loop().time() >= deadline
            ):
                note_frame_skipped()
                return None
            if self._live() is not link:
                raise BedNotConnectedError

            if callable(frame):
                try:
                    outbound = frame()
                except ValueError:
                    note_frame_skipped()
                    raise
                if outbound == _STOP:
                    return _STOP
            else:
                outbound = frame
            self._record_command_trace(
                link.write.uuid, outbound, response=True, characteristic=link.write
            )

            async def send() -> None:
                await link.client.write_gatt_char(link.write, outbound, response=True)
                if cleanup:
                    note_write_not_counted()
                else:
                    note_frame_written(event)

            # Reserve the lane through the acknowledgement. Eager start keeps
            # admission and backend submission in the same event-loop turn.
            await settled(send(), eager_start=True)
            return outbound
        finally:
            self._ble_lock.release()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if event.is_set():
                return
            await self._write(link, command, event)
            if index + 1 < repeat_count:
                await _pause(event, repeat_delay_ms / 1000)

    def motor_pulse_settings(self) -> tuple[int, int]:
        count, _ = super().motor_pulse_settings()
        return count, app.REFRESH_MS

    async def _stop(self, link: _Link) -> None:
        await self._write(link, _STOP, asyncio.Event(), cleanup=True)
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    async def stop_all(self) -> None:
        await self._stop(self._live())

    async def _run_motion(
        self, link: _Link, frame: Callable[[], bytes], count: int, *, duration_ms: int | None = None
    ) -> bool:
        """Refresh until the frame selector requests STOP or the movement ends."""
        event = self._coordinator.cancel_command
        if event.is_set():
            return False
        limit_ms = app.HOLD_LIMIT_MS if duration_ms is None else min(app.HOLD_LIMIT_MS, duration_ms)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limit_ms / 1000
        async with self.releasing(lambda: self._stop(link)):
            for index in range(count):
                outbound = await self._write(link, frame, event, deadline=deadline)
                if outbound is None:
                    return False
                if outbound == _STOP:
                    return True
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                if index + 1 < count:
                    await _pause(event, min(app.REFRESH_MS / 1000, remaining))
        return False

    async def _move(self, frame: bytes, count: int | None = None) -> None:
        if count is None:
            count = self.leased_hold_refreshes(app.REFRESH_MS) or self.motor_pulse_settings()[0]
        await self._run_motion(self._live(), lambda: frame, count)

    async def move_back_up(self) -> None:
        await self._move(app.motion(True, None))

    async def move_back_down(self) -> None:
        await self._move(app.motion(False, None))

    async def move_legs_up(self) -> None:
        await self._move(app.motion(None, True))

    async def move_legs_down(self) -> None:
        await self._move(app.motion(None, False))

    move_back_stop = move_legs_stop = move_head_stop = move_feet_stop = stop_all

    move_head_up = move_back_up
    move_head_down = move_back_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def preset_flat(self) -> None:
        await self._move(control_frame(Opcode.FLAT), math.ceil(app.HOLD_LIMIT_MS / app.REFRESH_MS))

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        if {first_axis, second_axis} != set(app.AXES):
            raise ValueError("Vindö simultaneous movement requires the back and legs axes")
        directions = {first_axis: first_up, second_axis: second_up}
        frame = app.motion(directions["back"], directions["legs"])
        if duration_ms is None:
            await self._move(frame)
            return
        count = self.timed_move_repeat_count(min(app.HOLD_LIMIT_MS, duration_ms), app.REFRESH_MS)
        await self._run_motion(self._live(), lambda: frame, count, duration_ms=duration_ms)

    async def lights_on(self) -> None:
        await self.write_command(control_frame(Opcode.LIGHT_ON))

    async def lights_off(self) -> None:
        await self.write_command(control_frame(Opcode.LIGHT_OFF))

    async def lights_toggle(self) -> None:
        await self.write_command(control_frame(Opcode.LIGHT_TOGGLE))

    async def _light_step(self, up: bool) -> None:
        await self.write_command(
            control_frame(Opcode.LIGHT_STEP_UP if up else Opcode.LIGHT_STEP_DOWN)
        )

    async def _identify(self) -> None:
        """Blink only this admitted device, with an awaited OFF on exit."""
        link = self._live()
        event = self._coordinator.cancel_command
        if event.is_set():
            return
        async with self.releasing(
            lambda: self._write(link, control_frame(Opcode.LIGHT_OFF), asyncio.Event())
        ):
            await self._write(link, control_frame(Opcode.LIGHT_ON), event)
            await _pause(event, app.IDENTIFY_ON_MS / 1000)
            if not event.is_set():
                await self._write(link, control_frame(Opcode.LIGHT_OFF), event)
                await _pause(event, app.IDENTIFY_OFF_MS / 1000)
                await self._write(link, control_frame(Opcode.LIGHT_ON), event)
                await _pause(event, app.IDENTIFY_ON_MS / 1000)

    async def massage_head_up(self) -> None:
        await self.write_command(control_frame(Opcode.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        await self.write_command(control_frame(Opcode.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        await self.write_command(control_frame(Opcode.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        await self.write_command(control_frame(Opcode.MASSAGE_FOOT_DOWN))

    async def massage_toggle(self) -> None:
        await self.write_command(control_frame(Opcode.MASSAGE_TOGGLE))

    async def _run_pattern(self, index: int) -> None:
        link = self._live()
        event = self._coordinator.cancel_command
        for step, frame in enumerate(app.massage_pattern(index)):
            if step:
                await _pause(event, app.MASSAGE_STEP_MS / 1000)
            if event.is_set():
                return
            await self._write(link, frame, event)

    @property
    def memory_slot_count(self) -> int:
        return _MEMORY_SLOTS

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    @property
    def persisted_app_state(self) -> dict[str, list[int]]:
        return {str(slot): list(value) for slot, value in self._memories.items()}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        memories: dict[int, app.Positions] = {}
        for slot in range(1, _MEMORY_SLOTS + 1):
            pair = state.get(str(slot))
            if (
                isinstance(pair, list)
                and len(pair) == 2
                and all(type(value) is int and 0 <= value < 0xFFFF for value in pair)
            ):
                memories[slot] = (pair[0], pair[1])
        self._memories = memories

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        if memory_num not in self._memories:
            raise ValueError("Save the current bed position in this memory before recalling it")

    def _fresh_positions(self, link: _Link) -> app.Positions | None:
        if self._live() is not link:
            raise BedNotConnectedError
        back, legs = (link.samples.get(axis) for axis in app.AXES)
        if (
            back is not None
            and legs is not None
            and asyncio.get_running_loop().time() - min(back[1], legs[1]) <= _POSITION_FRESH_S
        ):
            return back[0], legs[0]
        return None

    async def _wait_for_positions(self, link: _Link) -> app.Positions:
        async def wait() -> app.Positions:
            while True:
                link.position_updated.clear()
                if (positions := self._fresh_positions(link)) is not None:
                    return positions
                await link.position_updated.wait()

        try:
            async with asyncio.timeout(_POSITION_FRESH_S):
                return await cancellable(wait(), self._coordinator.cancel_command)
        except TimeoutError as err:
            raise ValueError(
                "Vindö needs fresh positions from both motors on the current connection"
            ) from err

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("This memory slot is unavailable")
        positions = await self._wait_for_positions(self._live())
        state = {**self.persisted_app_state, str(memory_num): list(positions)}

        async def save() -> None:
            await self._coordinator.async_write_app_state(self, state)
            self._memories[memory_num] = positions

        await settled(save())

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        link = self._live()
        target = self._memories[memory_num]
        await self._wait_for_positions(link)

        def select() -> bytes:
            current = self._fresh_positions(link)
            if current is None:
                raise ValueError("Vindö stopped receiving fresh positions during memory recall")
            return app.seek(current, target)

        reached = await self._run_motion(
            link, select, math.ceil(app.HOLD_LIMIT_MS / app.REFRESH_MS)
        )
        if not reached and not self._coordinator.cancel_command.is_set() and select() != _STOP:
            raise ValueError("Vindö did not reach the saved position before the movement ended")

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "vindo_back_raw", "vindo_back_raw", _BACK_RAW, "mdi:arrow-expand-vertical"
            ),
            ControllerStateSensorSpec(
                "vindo_legs_raw", "vindo_legs_raw", _LEGS_RAW, "mdi:arrow-expand-vertical"
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(
                ControllerButtonSpec(
                    f"vindo_massage_pattern_{index + 1}",
                    name,
                    lambda ctrl, index=index: require_controller(
                        ctrl, VindoController
                    )._run_pattern(index),
                    "mdi:vibrate",
                    f"vindo_massage_pattern_{index + 1}",
                    cancel_movement=False,
                    card=CARD_MASSAGE,
                )
                for index, name in enumerate(app.PATTERNS)
            ),
            *(
                ControllerButtonSpec(
                    f"vindo_move_{suffix}",
                    name,
                    lambda ctrl, back=back, legs=legs: ctrl.move_simultaneously(
                        "back", back, "legs", legs
                    ),
                    "mdi:bed",
                    f"vindo_move_{suffix}",
                    card=CARD_PRESETS,
                )
                for suffix, name, back, legs in (
                    ("both_up", "Raise back and legs", True, True),
                    ("both_down", "Lower back and legs", False, False),
                    ("back_up_legs_down", "Raise back and lower legs", True, False),
                    ("back_down_legs_up", "Lower back and raise legs", False, True),
                )
            ),
            ControllerButtonSpec(
                "vindo_light_brighter",
                "Increase under-bed light",
                lambda ctrl: require_controller(ctrl, VindoController)._light_step(True),
                "mdi:brightness-6",
                "vindo_light_brighter",
                cancel_movement=False,
                card=CARD_LIGHTING,
            ),
            ControllerButtonSpec(
                "vindo_light_dimmer",
                "Decrease under-bed light",
                lambda ctrl: require_controller(ctrl, VindoController)._light_step(False),
                "mdi:brightness-4",
                "vindo_light_dimmer",
                cancel_movement=False,
                card=CARD_LIGHTING,
            ),
            ControllerButtonSpec(
                "vindo_identify",
                "Identify Vindö bed",
                lambda ctrl: require_controller(ctrl, VindoController)._identify(),
                "mdi:lightbulb-on-outline",
                "vindo_identify",
                cancel_movement=False,
                diagnostic=True,
                card=CARD_HIDDEN,
            ),
        )
