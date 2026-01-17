"""Nectar bed controller implementation.

Protocol reverse-engineered and documented by MaximumWorf (https://github.com/MaximumWorf)
Source: https://github.com/MaximumWorf/homeassistant-nectar

Nectar beds (and other OKIN beds with similar protocol) use a 7-byte command format
over the OKIN BLE service. Commands follow the format: 5A 01 03 10 30 [XX] A5

This is similar to Mattress Firm 900 but uses the OKIN service UUID and has
slightly different command bytes for some functions.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NECTAR_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class NectarCommands:
    """Nectar bed command constants.

    Commands reverse-engineered by MaximumWorf.
    Source: https://github.com/MaximumWorf/homeassistant-nectar
    """

    # Motor movement
    HEAD_UP = bytes.fromhex("5A0103103000A5")
    HEAD_DOWN = bytes.fromhex("5A0103103001A5")
    FOOT_UP = bytes.fromhex("5A0103103002A5")
    FOOT_DOWN = bytes.fromhex("5A0103103003A5")
    LUMBAR_UP = bytes.fromhex("5A0103103004A5")
    LUMBAR_DOWN = bytes.fromhex("5A0103103007A5")
    STOP = bytes.fromhex("5A010310300FA5")

    # Presets
    FLAT = bytes.fromhex("5A0103103010A5")
    LOUNGE = bytes.fromhex("5A0103103011A5")
    ZERO_GRAVITY = bytes.fromhex("5A0103103013A5")
    ANTI_SNORE = bytes.fromhex("5A0103103016A5")

    # Massage
    MASSAGE_ON = bytes.fromhex("5A0103103058A5")
    MASSAGE_WAVE = bytes.fromhex("5A0103103059A5")
    MASSAGE_OFF = bytes.fromhex("5A010310305AA5")

    # Lights
    LIGHT_ON = bytes.fromhex("5A0103103073A5")
    LIGHT_OFF = bytes.fromhex("5A0103103074A5")


class NectarController(BedController):
    """Controller for Nectar beds using OKIN protocol.

    Protocol implementation based on MaximumWorf's reverse engineering work.
    https://github.com/MaximumWorf/homeassistant-nectar
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Nectar controller."""
        super().__init__(coordinator)
        _LOGGER.debug("NectarController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return NECTAR_WRITE_CHAR_UUID

    # Capability properties
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
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - Nectar beds support under-bed lighting."""
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to Nectar bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(
                    NECTAR_WRITE_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, _callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # Nectar beds don't support position feedback
        _LOGGER.debug("Nectar beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    async def read_positions(self, _motor_count: int = 2) -> None:
        """Read current motor positions."""
        # Not supported on Nectar beds

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(
                command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay
            )
        finally:
            try:
                await self.write_command(
                    NectarCommands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(NectarCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(NectarCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(NectarCommands.STOP, cancel_event=asyncio.Event())

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(NectarCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(NectarCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(NectarCommands.STOP, cancel_event=asyncio.Event())

    async def move_back_up(self) -> None:
        """Move back up (use head for 2-motor beds)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (use head for 2-motor beds)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (use feet for 2-motor beds)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (use feet for 2-motor beds)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(NectarCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(NectarCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(NectarCommands.STOP, cancel_event=asyncio.Event())

    # Preset positions
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            NectarCommands.FLAT,
            repeat_count=100,  # Presets need longer duration
            repeat_delay_ms=300,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(
            NectarCommands.ZERO_GRAVITY,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            NectarCommands.ANTI_SNORE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(
            NectarCommands.LOUNGE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_tv(self) -> None:
        """Go to TV position (alias for lounge)."""
        await self.preset_lounge()

    async def preset_memory(self, _slot: int) -> None:
        """Go to memory position.

        Note: Nectar beds don't support user-programmable memory slots.
        """
        _LOGGER.warning(
            "Nectar beds don't support programmable memory slots. "
            "Use preset positions instead."
        )
        raise NotImplementedError("Memory slots not supported on Nectar beds")

    async def program_memory(self, _slot: int) -> None:
        """Program memory position."""
        raise NotImplementedError("Memory programming not supported on Nectar beds")

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(NectarCommands.STOP, cancel_event=asyncio.Event())

    # Massage controls
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(NectarCommands.MASSAGE_ON, repeat_count=1)

    async def massage_on(self) -> None:
        """Turn massage on."""
        await self.write_command(NectarCommands.MASSAGE_ON, repeat_count=1)

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.write_command(NectarCommands.MASSAGE_OFF, repeat_count=1)

    async def massage_mode_step(self) -> None:
        """Step through massage modes (wave pattern)."""
        await self.write_command(NectarCommands.MASSAGE_WAVE, repeat_count=1)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        # Nectar uses global massage control
        await self.massage_toggle()

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.massage_toggle()

    # Light controls
    async def lights_on(self) -> None:
        """Turn lights on."""
        await self.write_command(NectarCommands.LIGHT_ON, repeat_count=1)

    async def lights_off(self) -> None:
        """Turn lights off."""
        await self.write_command(NectarCommands.LIGHT_OFF, repeat_count=1)

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        # Nectar has separate on/off, so we'll just turn on
        # The user should use the switch entity for proper on/off control
        await self.lights_on()
