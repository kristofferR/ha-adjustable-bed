"""DewertOkin ELEVATE two-actuator StarCode controller.

Recovered independently from the Adjustable Comfort M1X12 and AdjustableM5X5
apps. ELEVATE devices advertise an ``ELEVATE*`` name, use Nordic UART, and have
a dedicated 0x40-0x4F motor key range. They are not BOX25 bed controllers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NORDIC_UART_READ_CHAR_UUID, NORDIC_UART_WRITE_CHAR_UUID
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _elevate_command(key: int) -> bytes:
    """Build a StarCode ELEVATE command."""
    return bytes([0x5A, 0x01, 0x03, 0x10, 0x30, key, 0xA5])


class StarElevateCommands:
    """Exact ELEVATE command vectors."""

    WAKE = bytes.fromhex("5A 0B 00 A5")
    ACTUATOR_1_UP = _elevate_command(0x40)
    ACTUATOR_1_DOWN = _elevate_command(0x41)
    ACTUATOR_2_UP = _elevate_command(0x42)
    ACTUATOR_2_DOWN = _elevate_command(0x43)
    BOTH_UP = _elevate_command(0x44)
    BOTH_DOWN = _elevate_command(0x45)
    FLAT = _elevate_command(0x46)
    STOP = _elevate_command(0x0F)
    INTERRUPT = _elevate_command(0x4F)


class StarElevateController(BedController):
    """Controller for the separate ``ELEVATE*`` Nordic UART accessory."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._initialized = False

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

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

    def _effective_cancel_event(
        self, cancel_event: asyncio.Event | None
    ) -> asyncio.Event | None:
        return cancel_event if cancel_event is not None else self._coordinator.cancel_command

    async def _ensure_initialized(self, cancel_event: asyncio.Event | None = None) -> None:
        """Send the one-time keep-connected frame used by ELEVATE sessions."""
        effective_cancel = self._effective_cancel_event(cancel_event)
        if self._initialized or (effective_cancel is not None and effective_cancel.is_set()):
            return
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            StarElevateCommands.WAKE,
            cancel_event=effective_cancel,
            response=False,
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
            response=False,
        )

    def _on_notification(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Forward raw data; both analyzed apps assign no semantic ELEVATE fields."""
        self.forward_raw_notification(characteristic.uuid, bytes(data))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Enable RX and then send keep-connected, matching the OEM sequence."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            return
        try:
            await client.start_notify(NORDIC_UART_READ_CHAR_UUID, self._on_notification)
            await self._ensure_initialized()
        except BleakError:
            _LOGGER.warning("Could not initialize ELEVATE notifications", exc_info=True)

    async def stop_notify(self) -> None:
        self._notify_callback = None
        client = self.client
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
            except BleakError:
                _LOGGER.debug("Could not stop ELEVATE notifications", exc_info=True)

    async def _send_stop(self) -> None:
        await self.write_command(StarElevateCommands.STOP, cancel_event=asyncio.Event())

    async def move_head_up(self) -> None:
        await self._move_with_stop(StarElevateCommands.ACTUATOR_1_UP)

    async def move_head_down(self) -> None:
        await self._move_with_stop(StarElevateCommands.ACTUATOR_1_DOWN)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(StarElevateCommands.ACTUATOR_2_UP)

    async def move_feet_down(self) -> None:
        await self._move_with_stop(StarElevateCommands.ACTUATOR_2_DOWN)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_both_up(self) -> None:
        await self._move_with_stop(StarElevateCommands.BOTH_UP)

    async def move_both_down(self) -> None:
        await self._move_with_stop(StarElevateCommands.BOTH_DOWN)

    async def stop_all(self) -> None:
        await self._send_stop()

    async def preset_flat(self) -> None:
        """ELEVATE flat is an exact one-shot command with no appended STOP."""
        await self.write_command(StarElevateCommands.FLAT)

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
