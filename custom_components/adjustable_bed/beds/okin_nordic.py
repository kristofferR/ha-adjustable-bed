"""Okin Nordic UART protocol bed controller implementation.

Reverse-engineered by @kristofferR based on discovery from @Zrau5454.
Source: https://github.com/kristofferR/ha-adjustable-bed/issues/50

This controller handles beds that use the 7-byte command format over Nordic UART service.
Known brands using this protocol:
- Mattress Firm 900 / iFlex

Commands follow the format: 5A 01 03 10 30 [XX] A5
Very similar to Okin 7-byte protocol (okin_7byte.py) but uses Nordic UART service.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import MATTRESSFIRM_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class OkinNordicCommands:
    """Okin Nordic UART command constants.

    7-byte commands in format: 5A 01 03 10 30 [XX] A5
    Protocol reverse-engineered by David Delahoz (https://github.com/daviddelahoz/BLEAdjustableBase)
    """

    # Initialization commands (different format)
    INIT_1 = bytes.fromhex("09050A23050000")  # 7-byte init sequence
    INIT_2 = bytes.fromhex("5A0B00A5")  # 4-byte secondary init

    # Motor movement
    HEAD_UP = bytes.fromhex("5A0103103000A5")
    HEAD_DOWN = bytes.fromhex("5A0103103001A5")
    FOOT_UP = bytes.fromhex("5A0103103002A5")
    FOOT_DOWN = bytes.fromhex("5A0103103003A5")
    LUMBAR_UP = bytes.fromhex("5A0103103006A5")
    LUMBAR_DOWN = bytes.fromhex("5A0103103007A5")
    STOP = bytes.fromhex("5A010310300FA5")

    # Presets
    FLAT = bytes.fromhex("5A0103103010A5")
    ZERO_GRAVITY = bytes.fromhex("5A0103103013A5")
    ANTI_SNORE = bytes.fromhex("5A0103103016A5")
    LOUNGE = bytes.fromhex("5A0103103017A5")
    INCLINE = bytes.fromhex("5A0103103018A5")

    # Massage
    MASSAGE_1 = bytes.fromhex("5A0103103052A5")
    MASSAGE_2 = bytes.fromhex("5A0103103053A5")
    MASSAGE_3 = bytes.fromhex("5A0103103054A5")
    MASSAGE_ON = bytes.fromhex("5A0103103058A5")
    MASSAGE_WAVE = bytes.fromhex("5A0103103059A5")
    MASSAGE_OFF = bytes.fromhex("5A010310305AA5")
    MASSAGE_STOP = bytes.fromhex("5A010310306FA5")
    MASSAGE_UP = bytes.fromhex("5A0103104060A5")
    MASSAGE_DOWN = bytes.fromhex("5A0103104063A5")

    # Lights
    LIGHT_ON = bytes.fromhex("5A0103103073A5")
    LIGHT_OFF = bytes.fromhex("5A0103103074A5")
    LIGHT_CYCLE = bytes.fromhex("5A0103103070A5")
    LIGHT_OFF_HOLD = bytes.fromhex("5A0103103074A5")


class OkinNordicController(BedController):
    """Controller for beds using Okin protocol over Nordic UART.

    Protocol discovered from Mattress Firm 900 (iFlex) beds.
    Very similar to Nectar/Okin 7-byte but uses Nordic UART service.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Okin Nordic UART controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._initialized: bool = False
        _LOGGER.debug("OkinNordicController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MATTRESSFIRM_WRITE_CHAR_UUID

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
        """Return True - these beds support under-bed lighting."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - these beds don't support programmable memory presets."""
        return False

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

        # Send init sequence on first command
        if not self._initialized:
            _LOGGER.debug("Sending init sequence before first command")
            try:
                await self.client.write_gatt_char(
                    MATTRESSFIRM_WRITE_CHAR_UUID, OkinNordicCommands.INIT_1, response=True
                )
                await self.client.write_gatt_char(
                    MATTRESSFIRM_WRITE_CHAR_UUID, OkinNordicCommands.INIT_2, response=True
                )
                self._initialized = True
            except BleakError:
                _LOGGER.exception("Failed to send init sequence")
                raise

        _LOGGER.debug(
            "Writing command to Okin Nordic bed: %s (repeat: %d, delay: %dms)",
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
                    MATTRESSFIRM_WRITE_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # These beds don't support position feedback
        self._notify_callback = callback
        _LOGGER.debug("Okin Nordic beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current motor positions."""
        # Not supported on these beds

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
                    OkinNordicCommands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(OkinNordicCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(OkinNordicCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(OkinNordicCommands.STOP, cancel_event=asyncio.Event())

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(OkinNordicCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(OkinNordicCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(OkinNordicCommands.STOP, cancel_event=asyncio.Event())

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
        await self._move_with_stop(OkinNordicCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(OkinNordicCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(OkinNordicCommands.STOP, cancel_event=asyncio.Event())

    # Preset positions
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            OkinNordicCommands.FLAT,
            repeat_count=100,  # Presets need longer duration
            repeat_delay_ms=300,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(
            OkinNordicCommands.ZERO_GRAVITY,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            OkinNordicCommands.ANTI_SNORE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(
            OkinNordicCommands.LOUNGE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_tv(self) -> None:
        """Go to TV position (alias for lounge)."""
        await self.preset_lounge()

    async def preset_incline(self) -> None:
        """Go to incline position."""
        await self.write_command(
            OkinNordicCommands.INCLINE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory position."""
        _LOGGER.warning(
            "Okin Nordic beds don't support programmable memory slots. "
            "Use preset positions instead."
        )
        raise NotImplementedError("Memory slots not supported on Okin Nordic beds")

    async def program_memory(self, memory_num: int) -> None:
        """Program memory position."""
        raise NotImplementedError("Memory programming not supported on Okin Nordic beds")

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(OkinNordicCommands.STOP, cancel_event=asyncio.Event())

    # Massage controls
    async def massage_toggle(self) -> None:
        """Cycle massage (sends on command - use massage_on/massage_off for explicit control)."""
        await self.write_command(OkinNordicCommands.MASSAGE_ON, repeat_count=1)

    async def massage_on(self) -> None:
        """Turn massage on."""
        await self.write_command(OkinNordicCommands.MASSAGE_1, repeat_count=1)

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.write_command(OkinNordicCommands.MASSAGE_OFF, repeat_count=1)

    async def massage_mode_step(self) -> None:
        """Step through massage modes (wave pattern)."""
        await self.write_command(OkinNordicCommands.MASSAGE_WAVE, repeat_count=1)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        await self.write_command(OkinNordicCommands.MASSAGE_UP, repeat_count=1)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        await self.write_command(OkinNordicCommands.MASSAGE_DOWN, repeat_count=1)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        # Uses global massage control
        await self.massage_toggle()

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.massage_toggle()

    # Light controls
    async def lights_on(self) -> None:
        """Turn lights on (cycles through modes)."""
        await self.write_command(OkinNordicCommands.LIGHT_CYCLE, repeat_count=1)

    async def lights_off(self) -> None:
        """Turn lights off (requires hold)."""
        await self.write_command(OkinNordicCommands.LIGHT_OFF_HOLD, repeat_count=3)

    async def lights_toggle(self) -> None:
        """Cycle lights (sends on command - use switch entity for true toggle)."""
        await self.lights_on()
