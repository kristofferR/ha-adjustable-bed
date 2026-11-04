"""DewertOkin ELEVATE two-actuator StarCode controller.

Recovered independently from the Adjustable Comfort M1X12 and AdjustableM5X5
apps. ELEVATE devices advertise an ``ELEVATE*`` name, use Nordic UART, and have
a dedicated 0x40-0x4F motor key range. They are not BOX25 bed controllers.

Frames come from the ``star_elevate`` profile over the Okin 5A codec. This
controller keeps what data cannot express: the keep-connected session and the
accessory group. See ``docs/beds/okin-5a.md``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..codec import okin_5a as codec

# starcode_m1x12 imports the RX characteristic from here.
from ..const import NORDIC_UART_READ_CHAR_UUID as NORDIC_UART_READ_CHAR_UUID
from ..execution import leased_pulses
from ..profiles.okin_5a import ELEVATE
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Kept for the M5X5 leaf proofs, which compare it with their own encoder.
_elevate_command = codec.command


class StarElevateCommands:
    """ELEVATE frames by app name, from the ``star_elevate`` profile."""

    WAKE = codec.WAKE
    ACTUATOR_1_UP = ELEVATE.frame("head_up")
    ACTUATOR_1_DOWN = ELEVATE.frame("head_down")
    ACTUATOR_2_UP = ELEVATE.frame("feet_up")
    ACTUATOR_2_DOWN = ELEVATE.frame("feet_down")
    BOTH_UP = ELEVATE.frame("both_up")
    BOTH_DOWN = ELEVATE.frame("both_down")
    FLAT = ELEVATE.frame("flat")
    STOP = ELEVATE.frame("stop")
    INTERRUPT = ELEVATE.frame("interrupt")


class StarElevateController(BedController):
    """Controller for the separate ``ELEVATE*`` Nordic UART accessory."""

    profile = ELEVATE

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._initialized = False
        self._generation = 0

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.transport_uuid

    @property
    def ready(self) -> bool:
        """Connected and past the keep-connected frame, as group members must be."""
        client = self.client
        return self._initialized and client is not None and client.is_connected

    @property
    def session_generation(self) -> int:
        """Identify the notification session a delayed group action retained."""
        return self._generation

    @property
    def requires_notification_channel(self) -> bool:
        """Keep RX enabled because the proven connect sequence enables it before wake."""
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose both physical actuators plus their proven union command."""
        return (
            MotorControlSpec(
                key="elevate_actuator_1",
                translation_key="elevate_actuator_1",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
            ),
            MotorControlSpec(
                key="elevate_actuator_2",
                translation_key="elevate_actuator_2",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
            ),
            MotorControlSpec(
                key="elevate_both",
                translation_key="elevate_both",
                open_fn=_move_elevate_both_up,
                close_fn=_move_elevate_both_down,
                stop_fn=lambda ctrl: ctrl.stop_all(),
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"back", "legs", "head", "feet"})

    def _effective_cancel_event(self, cancel_event: asyncio.Event | None) -> asyncio.Event | None:
        return cancel_event if cancel_event is not None else self._coordinator.cancel_command

    async def _ensure_initialized(self, cancel_event: asyncio.Event | None = None) -> None:
        """Send the one-time keep-connected frame used by ELEVATE sessions."""
        effective_cancel = self._effective_cancel_event(cancel_event)
        if self._initialized or (effective_cancel is not None and effective_cancel.is_set()):
            return
        for frame in self.profile.wake:
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                frame,
                cancel_event=effective_cancel,
                response=self.profile.wake_with_response,
            )
        if effective_cancel is None or not effective_cancel.is_set():
            self._initialized = True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write serialized ELEVATE frames without response."""
        effective_cancel = self._effective_cancel_event(cancel_event)
        if effective_cancel is not None and effective_cancel.is_set():
            return
        await self._ensure_initialized(effective_cancel)
        if effective_cancel is not None and effective_cancel.is_set():
            return
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=effective_cancel,
            response=self.profile.write_with_response,
        )

    def _on_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Forward raw data; both analyzed apps assign no semantic ELEVATE fields."""
        self.forward_raw_notification(characteristic.uuid, bytes(data))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Enable RX and then send keep-connected, matching the OEM sequence."""
        self._notify_callback = callback
        self._generation += 1
        client = self.client
        if client is None or not client.is_connected:
            return
        try:
            await client.start_notify(self.profile.notify_uuid, self._on_notification)
            await self._ensure_initialized()
        except BleakError:
            _LOGGER.warning("Could not initialize ELEVATE notifications", exc_info=True)

    async def stop_notify(self) -> None:
        self._notify_callback = None
        self._generation += 1
        client = self.client
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(self.profile.notify_uuid)
            except BleakError:
                _LOGGER.debug("Could not stop ELEVATE notifications", exc_info=True)

    async def _send_stop(self) -> None:
        stop = self.profile.stop
        await self.write_command(
            self.profile.frame("stop"),
            repeat_count=stop.repeats,
            repeat_delay_ms=stop.repeat_ms,
            cancel_event=asyncio.Event(),
        )

    async def interrupt(self) -> None:
        """Interrupt held motion before a grouped AdjustableM5X5 peer moves."""
        await self.write_command(self.profile.frame("interrupt"), cancel_event=asyncio.Event())

    async def _interrupt_group(self) -> None:
        """As a lift or main, ordinary motion interrupts the other group members."""
        from ..starcode_accessory_group import interrupt_conflicting_group

        await interrupt_conflicting_group(self._coordinator)

    def motor_pulse_settings(self) -> tuple[int, int]:
        """A renewable hold (#483) refreshes at the app's interval until its lease ends."""
        refresh = self.profile.hold_refresh_ms
        return (refresh and leased_pulses(refresh)) or super().motor_pulse_settings()

    async def _move_with_stop(self, command: bytes) -> None:
        await self._interrupt_group()
        try:
            pulse_count, pulse_delay = self.motor_pulse_settings()
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            await self._send_stop()

    async def move_head_up(self) -> None:
        await self._move_with_stop(self.profile.frame("head_up"))

    async def move_head_down(self) -> None:
        await self._move_with_stop(self.profile.frame("head_down"))

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(self.profile.frame("feet_up"))

    async def move_feet_down(self) -> None:
        await self._move_with_stop(self.profile.frame("feet_down"))

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_both_up(self) -> None:
        await self._move_with_stop(self.profile.frame("both_up"))

    async def move_both_down(self) -> None:
        await self._move_with_stop(self.profile.frame("both_down"))

    async def stop_all(self) -> None:
        from ..starcode_accessory_group import cancel_group_operations

        cancel_group_operations(self._coordinator.hass, self._coordinator.entry.entry_id)
        await self._send_stop()

    async def preset_flat(self) -> None:
        """ELEVATE flat is an exact one-shot command with no appended STOP."""
        await self._interrupt_group()
        recall = self.profile.recall
        await self.write_command(
            self.profile.frame("flat"),
            repeat_count=recall.repeats,
            repeat_delay_ms=recall.repeat_ms,
        )

    async def preset_memory(self, memory_num: int) -> None:
        _LOGGER.warning("ELEVATE has no memory preset %d", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        _LOGGER.warning("ELEVATE has no programmable memory slot %d", memory_num)


async def _move_elevate_both_up(controller: BedController) -> None:
    """Dispatch the ELEVATE-only union movement from a generic motor spec."""
    if not isinstance(controller, StarElevateController):
        raise TypeError("ELEVATE union control requires StarElevateController")
    await controller.move_both_up()


async def _move_elevate_both_down(controller: BedController) -> None:
    """Dispatch the ELEVATE-only union movement from a generic motor spec."""
    if not isinstance(controller, StarElevateController):
        raise TypeError("ELEVATE union control requires StarElevateController")
    await controller.move_both_down()
