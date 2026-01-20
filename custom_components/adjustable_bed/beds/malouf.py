"""Malouf bed controller implementations.

Reverse-engineered from Malouf Base app v2.4.3.

Malouf beds use two distinct protocols:
- NEW_OKIN: 8-byte commands via Nordic UART, advertises unique service UUID
- LEGACY_OKIN: 9-byte commands with checksum via FFE5 service

Both protocols share the same command values but differ in encoding.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class MaloufCommands:
    """Malouf command constants (32-bit values).

    These values are shared by both NEW_OKIN and LEGACY_OKIN protocols.
    The encoding differs but the command semantics are identical.
    """

    # Motors
    HEAD_UP = 0x1
    HEAD_DOWN = 0x2
    FOOT_UP = 0x4
    FOOT_DOWN = 0x8
    HEAD_TILT_UP = 0x10
    HEAD_TILT_DOWN = 0x20
    LUMBAR_UP = 0x40
    LUMBAR_DOWN = 0x80
    DUAL_UP = 0x5  # HEAD_UP | FOOT_UP
    DUAL_DOWN = 0xA  # HEAD_DOWN | FOOT_DOWN
    STOP = 0x0

    # Presets
    ALL_FLAT = 0x8000000
    ZERO_G = 0x1000
    LOUNGE = 0x2000
    ANTI_SNORE = 0x8000
    TV_READ = 0x4000
    MEMORY_1 = 0x10000
    MEMORY_2 = 0x40000

    # Lights & Massage
    LIGHT_SWITCH = 0x20000
    MASSAGE_HEAD = 0x800
    MASSAGE_FOOT = 0x400
    MASSAGE_HEAD_MINUS = 0x800000
    MASSAGE_FOOT_MINUS = 0x1000000
    MASSAGE_TIMER = 0x200
    MASSAGE_OFF = 0x2000000


class MaloufNewOkinController(BedController):
    """Controller for Malouf beds using NEW_OKIN protocol.

    Protocol characteristics:
    - Advertised service: 01000001-0000-1000-8000-00805f9b34fb (unique identifier)
    - Command service: Nordic UART (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
    - Write characteristic: 6e400002-b5a3-f393-e0a9-e50e24dcca9e
    - Command format: 8 bytes, no checksum
      [0x05, 0x02, (cmd>>24)&0xFF, (cmd>>16)&0xFF, (cmd>>8)&0xFF, cmd&0xFF, 0x00, 0x00]
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Malouf NEW_OKIN controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("MaloufNewOkinController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MALOUF_NEW_OKIN_WRITE_CHAR_UUID

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
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_tilt_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - these beds support lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only toggle control available."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 2 - Malouf beds support memory slots 1-2."""
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - Malouf beds don't support programming memory positions."""
        return False

    def _build_command(self, command_value: int) -> bytes:
        """Build an 8-byte NEW_OKIN command.

        Format: [0x05, 0x02, (cmd>>24)&0xFF, (cmd>>16)&0xFF, (cmd>>8)&0xFF, cmd&0xFF, 0x00, 0x00]
        """
        return bytes([
            0x05,
            0x02,
            (command_value >> 24) & 0xFF,
            (command_value >> 16) & 0xFF,
            (command_value >> 8) & 0xFF,
            command_value & 0xFF,
            0x00,
            0x00,
        ])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Malouf NEW_OKIN bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # These beds don't support position feedback
        self._notify_callback = callback
        _LOGGER.debug("Malouf NEW_OKIN beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current motor positions - not supported."""
        pass

    async def _move_with_stop(self, command_value: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        command = self._build_command(command_value)
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self.write_command(
                    self._build_command(MaloufCommands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(MaloufCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(MaloufCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(MaloufCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(MaloufCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(MaloufCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(MaloufCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Tilt control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(MaloufCommands.ALL_FLAT))

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(self._build_command(MaloufCommands.ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(MaloufCommands.ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV/reading position."""
        await self.write_command(self._build_command(MaloufCommands.TV_READ))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(MaloufCommands.LOUNGE))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: MaloufCommands.MEMORY_1,
            2: MaloufCommands.MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "Malouf beds don't support programming memory presets (requested: %d)", memory_num
        )

    # Light control
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(MaloufCommands.LIGHT_SWITCH))

    async def lights_on(self) -> None:
        """Turn on lights (toggle only)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle only)."""
        await self.lights_toggle()

    # Massage control
    async def massage_head_toggle(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_foot_toggle(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD_MINUS))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT_MINUS))

    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_OFF))

    async def massage_toggle(self) -> None:
        """Toggle massage timer."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_TIMER))


class MaloufLegacyOkinController(BedController):
    """Controller for Malouf beds using LEGACY_OKIN protocol.

    Protocol characteristics:
    - Service: 0000ffe5-0000-1000-8000-00805f9b34fb
    - Write characteristic: 0000ffe9-0000-1000-8000-00805f9b34fb
    - Command format: 9 bytes with checksum
      [0xE6, 0xFE, 0x16, cmd&0xFF, (cmd>>8)&0xFF, (cmd>>16)&0xFF, (cmd>>24)&0xFF, 0x00, checksum]
    - Checksum: (~sum(bytes[0:8])) & 0xFF
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Malouf LEGACY_OKIN controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("MaloufLegacyOkinController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID

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
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_tilt_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - these beds support lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only toggle control available."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 2 - Malouf beds support memory slots 1-2."""
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - Malouf beds don't support programming memory positions."""
        return False

    def _build_command(self, command_value: int) -> bytes:
        """Build a 9-byte LEGACY_OKIN command with checksum.

        Format: [0xE6, 0xFE, 0x16, cmd&0xFF, (cmd>>8)&0xFF, (cmd>>16)&0xFF, (cmd>>24)&0xFF, 0x00, checksum]
        Checksum: (~sum(bytes[0:8])) & 0xFF
        """
        data = [
            0xE6,
            0xFE,
            0x16,
            command_value & 0xFF,
            (command_value >> 8) & 0xFF,
            (command_value >> 16) & 0xFF,
            (command_value >> 24) & 0xFF,
            0x00,
        ]
        checksum = (~sum(data)) & 0xFF
        data.append(checksum)
        return bytes(data)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Malouf LEGACY_OKIN bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # These beds don't support position feedback
        self._notify_callback = callback
        _LOGGER.debug("Malouf LEGACY_OKIN beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current motor positions - not supported."""
        pass

    async def _move_with_stop(self, command_value: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        command = self._build_command(command_value)
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self.write_command(
                    self._build_command(MaloufCommands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(MaloufCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(MaloufCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(MaloufCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(MaloufCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(MaloufCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(MaloufCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Tilt control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(MaloufCommands.ALL_FLAT))

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(self._build_command(MaloufCommands.ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(MaloufCommands.ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV/reading position."""
        await self.write_command(self._build_command(MaloufCommands.TV_READ))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(MaloufCommands.LOUNGE))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: MaloufCommands.MEMORY_1,
            2: MaloufCommands.MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "Malouf beds don't support programming memory presets (requested: %d)", memory_num
        )

    # Light control
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(MaloufCommands.LIGHT_SWITCH))

    async def lights_on(self) -> None:
        """Turn on lights (toggle only)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle only)."""
        await self.lights_toggle()

    # Massage control
    async def massage_head_toggle(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_foot_toggle(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD_MINUS))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT_MINUS))

    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_OFF))

    async def massage_toggle(self) -> None:
        """Toggle massage timer."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_TIMER))
