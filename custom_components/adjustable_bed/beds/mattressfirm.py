"""Mattress Firm 900 bed controller implementation.

Protocol reverse-engineered and documented by David Delahoz (https://github.com/daviddelahoz)
Source: https://github.com/daviddelahoz/BLEAdjustableBase

Mattress Firm 900 (iFlex) beds use a 7-byte command protocol over Nordic UART Service.
Commands follow the format: 5A 01 03 10 [XX] [YY] A5

Special thanks to David Delahoz for reverse-engineering this protocol in 2020 and
making it available to the community under the MIT license.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import MATTRESSFIRM_CHAR_UUID, MATTRESSFIRM_SERVICE_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class MattressFirmCommands:
    """Mattress Firm 900 command constants.

    All commands reverse-engineered by David Delahoz.
    Source: https://github.com/daviddelahoz/BLEAdjustableBase
    """

    # Initialization (required on connection)
    INIT_1 = bytes.fromhex("09050A23050000")
    INIT_2 = bytes.fromhex("5A0B00A5")

    # Motor movement
    HEAD_UP = bytes.fromhex("5A0103103000A5")
    HEAD_DOWN = bytes.fromhex("5A0103103001A5")
    FOOT_UP = bytes.fromhex("5A0103103002A5")
    FOOT_DOWN = bytes.fromhex("5A0103103003A5")
    LUMBAR_UP = bytes.fromhex("5A0103103006A5")
    LUMBAR_DOWN = bytes.fromhex("5A0103103007A5")

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
    MASSAGE_STOP = bytes.fromhex("5A010310306FA5")
    MASSAGE_UP = bytes.fromhex("5A0103104060A5")
    MASSAGE_DOWN = bytes.fromhex("5A0103104063A5")

    # Lights
    LIGHT_CYCLE = bytes.fromhex("5A0103103070A5")
    LIGHT_OFF_HOLD = bytes.fromhex("5A0103103074A5")


class MattressFirmController(BedController):
    """Controller for Mattress Firm 900 (iFlex) beds.

    Protocol implementation based on David Delahoz's reverse engineering work.
    https://github.com/daviddelahoz/BLEAdjustableBase
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Mattress Firm controller."""
        super().__init__(coordinator)
        self._initialized = False
        _LOGGER.debug("MattressFirmController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MATTRESSFIRM_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_incline(self) -> bool:
        return True

    @property
    def supports_light_cycle(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - Mattress Firm beds support under-bed lighting."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - Mattress Firm 900 doesn't support programmable memory slots."""
        return False

    async def initialize(self) -> None:
        """Initialize the bed connection.

        Mattress Firm beds require a specific initialization sequence
        before they will accept commands.
        """
        if self._initialized:
            _LOGGER.debug("Bed already initialized, skipping")
            return

        _LOGGER.info("Initializing Mattress Firm 900 bed")

        try:
            # Send INIT_1 command
            await self.write_command(MattressFirmCommands.INIT_1, repeat_count=1)
            await asyncio.sleep(0.1)

            # Send INIT_2 command
            await self.write_command(MattressFirmCommands.INIT_2, repeat_count=1)
            await asyncio.sleep(0.1)

            self._initialized = True
            _LOGGER.info("Mattress Firm 900 bed initialized successfully")
        except Exception:
            _LOGGER.exception("Failed to initialize bed")
            raise

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

        # Ensure bed is initialized before sending commands (except init commands)
        if not self._initialized and command not in (
            MattressFirmCommands.INIT_1,
            MattressFirmCommands.INIT_2,
        ):
            await self.initialize()

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to Mattress Firm bed: %s (repeat: %d, delay: %dms)",
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
                    MATTRESSFIRM_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # Mattress Firm 900 beds don't support position feedback
        _LOGGER.debug("Mattress Firm 900 beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current motor positions."""
        # Not supported on Mattress Firm 900
        pass

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self.write_command(
            MattressFirmCommands.HEAD_UP,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_head_down(self) -> None:
        """Move head down."""
        await self.write_command(
            MattressFirmCommands.HEAD_DOWN,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        # Mattress Firm beds stop automatically when command stream ends
        pass

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.write_command(
            MattressFirmCommands.FOOT_UP,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.write_command(
            MattressFirmCommands.FOOT_DOWN,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        pass

    async def move_back_up(self) -> None:
        """Move back up (use head for 2-motor beds)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (use head for 2-motor beds)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        pass

    async def move_legs_up(self) -> None:
        """Move legs up (use feet for 2-motor beds)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (use feet for 2-motor beds)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        pass

    # Lumbar control (special for Mattress Firm)
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self.write_command(
            MattressFirmCommands.LUMBAR_UP,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self.write_command(
            MattressFirmCommands.LUMBAR_DOWN,
            repeat_count=self._coordinator.motor_pulse_count,
            repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
        )

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        pass

    # Preset positions
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            MattressFirmCommands.FLAT,
            repeat_count=100,  # Presets need longer duration
            repeat_delay_ms=300,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(
            MattressFirmCommands.ZERO_GRAVITY,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            MattressFirmCommands.ANTI_SNORE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(
            MattressFirmCommands.LOUNGE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_incline(self) -> None:
        """Go to incline position."""
        await self.write_command(
            MattressFirmCommands.INCLINE,
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_tv(self) -> None:
        """Go to TV position (alias for lounge)."""
        await self.preset_lounge()

    async def preset_memory(self, slot: int) -> None:
        """Go to memory position.

        Note: Mattress Firm 900 doesn't support user-programmable memory slots.
        The preset positions (Flat, Zero-G, Lounge, Incline, Anti-Snore) are
        the built-in options.
        """
        _LOGGER.warning(
            "Mattress Firm 900 doesn't support programmable memory slots. "
            "Use preset positions instead."
        )
        raise NotImplementedError("Memory slots not supported on Mattress Firm 900")

    async def program_memory(self, slot: int) -> None:
        """Program memory position."""
        raise NotImplementedError("Memory programming not supported on Mattress Firm 900")

    async def stop_all(self) -> None:
        """Stop all movement."""
        # Mattress Firm beds stop when command stream ends
        # We signal cancellation to stop any ongoing command repetitions
        self._coordinator.cancel_command.set()

    # Massage controls
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(MattressFirmCommands.MASSAGE_1, repeat_count=1)

    async def massage_on(self) -> None:
        """Turn massage on."""
        await self.write_command(MattressFirmCommands.MASSAGE_1, repeat_count=1)

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.write_command(MattressFirmCommands.MASSAGE_STOP, repeat_count=1)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        await self.write_command(MattressFirmCommands.MASSAGE_UP, repeat_count=1)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        await self.write_command(MattressFirmCommands.MASSAGE_DOWN, repeat_count=1)

    async def massage_mode_step(self) -> None:
        """Step through massage modes (1 -> 2 -> 3)."""
        # Cycle through massage levels
        await self.massage_intensity_up()

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        # Mattress Firm uses global massage control, not zone-specific
        await self.massage_toggle()

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.massage_intensity_up()

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.massage_intensity_down()

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.massage_toggle()

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.massage_intensity_up()

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.massage_intensity_down()

    # Light controls
    async def lights_on(self) -> None:
        """Turn lights on (cycle mode)."""
        await self.write_command(MattressFirmCommands.LIGHT_CYCLE, repeat_count=1)

    async def lights_off(self) -> None:
        """Turn lights off (hold mode)."""
        await self.write_command(MattressFirmCommands.LIGHT_OFF_HOLD, repeat_count=3)

    async def lights_toggle(self) -> None:
        """Toggle lights (cycle mode)."""
        await self.lights_on()
