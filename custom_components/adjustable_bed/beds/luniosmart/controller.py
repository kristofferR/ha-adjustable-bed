"""Lunio Smart+'s fixed controls on an owned, serialized physical session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...profiles.luniosmart import DIRECTIONS, PRESETS, PROFILE, RELEASE, LunioSmartProfile
from ..base import BedController, ProfileExecution, require_controller
from ..entity_specs import (
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..richmat.transport import AppLink, select_app_link
from .receive import Receiver, Value, decode

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

WRITE_TIMEOUT_S: Final = 5.0  # HA write bound, not a proven firmware timeout.


@dataclass(frozen=True, slots=True)
class Session:
    link: AppLink
    owner: AdjustableBedCoordinator


class LunioSmartController(ProfileExecution[LunioSmartProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = PROFILE
        self._session: Session | None = None
        self._receiver = Receiver()
        self._expiry: asyncio.TimerHandle | None = None
        self.observations: dict[str, Value] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return self._session.link.tx.uuid if self._session else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # No app-owned GATT reads are proven.

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[()]:
        return ()

    def validate_memory_recall(self, memory_num: int) -> None:
        if type(memory_num) is not int or memory_num != 1:
            raise ValueError("Lunio Smart+ has only memory slot 1")

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return type(memory_num) is int and memory_num == 1

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(DIRECTIONS)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                key,
                partial(_action, action=axis + "_up"),
                partial(_action, action=axis + "_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    axis + "_up", axis + "_down", press_is_native=True, stop_scope="side"
                ),
            )
            for key, axis in (("back", "head"), ("legs", "foot"))
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        # Decoded events stay out of entities; diagnostics and the support bundle keep them.
        return {"connected": self._session is not None, "observations": dict(self.observations)}

    def _live(self, session: Session | None = None) -> Session:
        current = self._session
        if (
            current is None
            or session is not None
            and session is not current
            or self._coordinator is not current.owner
            or self._coordinator.controller is not self
            or self.client is not current.link.client
            or not current.link.client.is_connected
        ):
            raise ConnectionError("Lunio Smart+ physical session changed")
        if self.command_side is not None:
            raise ValueError("This bed has no sides. Leave out the side")
        return current

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("Lunio Smart+ is disconnected")
        session = self._session = Session(
            select_app_link(client, self.profile.transports), self._coordinator
        )
        if session.link.rx is not None:

            def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
                try:
                    self._live(session)
                except ConnectionError, ValueError:
                    return
                self.forward_raw_notification(sender.uuid, bytes(data))
                if self._expiry is not None:
                    self._expiry.cancel()
                    self._expiry = None
                for packet in self._receiver.feed(bytes(data)):
                    for name, value in decode(packet):
                        self.observations[name] = value
                if self._receiver.pending:
                    self._expiry = asyncio.get_running_loop().call_later(
                        self.profile.receive_expiry_s, self._receiver.pending.clear
                    )

            # Subscription errors propagate before either startup write.
            await client.start_notify(session.link.rx, receive)
        await self._send(
            session,
            codec.function(
                0, action="deviceFunctionItemExitLimit", single=session.link.query_single
            ),
        )
        await self._send(session, codec.calendar(dt_util.now(), build=codec.record_20_len))

    async def stop_notify(self) -> None:
        session = self._session
        self.on_disconnect()
        if session is not None and session.link.rx is not None and session.link.client.is_connected:
            async with self._ble_lock:
                await session.link.client.stop_notify(session.link.rx)

    def on_disconnect(self) -> None:
        self._session = None
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        self._receiver.pending.clear()
        self.observations.clear()

    async def _send(
        self,
        session: Session,
        packet: bytes,
        *,
        release: bool = False,
        deadline: float | None = None,
        delay: float | None = None,
    ) -> None:
        cancel = asyncio.Event() if release else self._coordinator.cancel_command
        if await _pause(self.profile.tick_s if delay is None else delay, cancel):
            note_frame_skipped()
            return
        self._live(session)
        if deadline is not None and monotonic() >= deadline:
            return

        async def write() -> None:
            async with self._ble_lock:
                self._live(session)
                if cancel.is_set() or deadline is not None and monotonic() >= deadline:
                    note_frame_skipped()
                    return
                link = session.link
                response = "write-without-response" not in link.tx.properties
                self._record_command_trace(
                    link.tx.uuid, packet, response=response, characteristic=link.tx
                )
                async with asyncio.timeout(WRITE_TIMEOUT_S):
                    await link.client.write_gatt_char(link.tx, packet, response=response)
                    note_frame_written(cancel)

        await _settle(asyncio.create_task(write()))

    async def _release(self, session: Session) -> None:
        # Drain this release even under repeated cancellation. It can never
        # migrate to a replacement client, writer, owner or controller.
        task = asyncio.create_task(self._send(session, codec.command(RELEASE), release=True))
        await _settle(task)

    async def action(self, action: str) -> None:
        if action in DIRECTIONS:
            await self.hold_control(action, self._coordinator.motor_pulse_count * 100)
            return
        session = self._live()  # Capture ownership before the first await.
        if action in PRESETS:
            try:
                await self._send(session, codec.command(PRESETS[action]))
            finally:
                await self._release(session)
        else:
            raise ValueError("Unknown Lunio Smart+ action")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in DIRECTIONS
            or type(duration_ms) is not int
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Choose a direction and a duration of up to 60 seconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        session = self._live()
        deadline = monotonic() + self.leased_hold_ms(duration_ms) / 1000
        delay = 0.0
        try:
            while not self._coordinator.cancel_command.is_set() and monotonic() < deadline:
                await self._send(
                    session, codec.command(DIRECTIONS[control]), deadline=deadline, delay=delay
                )
                delay = self.profile.tick_s
        finally:
            await self._release(session)

    async def stop_all(self) -> None:
        await self._release(self._live())

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def move_back_up(self) -> None:
        await self.action("head_up")

    async def move_back_down(self) -> None:
        await self.action("head_down")

    move_head_up = move_back_up
    move_head_down = move_back_down

    async def move_legs_up(self) -> None:
        await self.action("foot_up")

    async def move_legs_down(self) -> None:
        await self.action("foot_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def preset_flat(self) -> None:
        await self.action("flat")

    async def preset_zero_g(self) -> None:
        await self.action("zero_gravity")

    async def preset_anti_snore(self) -> None:
        await self.action("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action("memory_recall_1")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action("memory_save_1")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        raise ValueError("Use a proven Lunio Smart+ action")


async def _action(controller: BedController, *, action: str) -> None:
    await require_controller(controller, LunioSmartController).action(action)


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
        return True
    except TimeoutError:
        return False


async def _settle(task: asyncio.Task[None]) -> None:
    """An invoked write must settle before cleanup can use the same BLE lane."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    task.result()
    if cancelled:
        raise asyncio.CancelledError
