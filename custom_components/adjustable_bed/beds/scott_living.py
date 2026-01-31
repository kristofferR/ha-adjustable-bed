"""Scott Living bed controller implementation.

Reverse engineering from com.keeson.scottlivingrelease APK.

Scott Living uses a 9-byte Keeson variant with inverted sum checksum.
Packet format: [0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]

The side byte is always 0x01 in this implementation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class ScottLivingCommands:
    """Scott Living command key values.

    Commands are 32-bit values where a single bit indicates the action.
    The buildInstruct function maps these to command bytes.
    """

    # Motor commands (cmd0 byte)
    MOTOR_HEAD_UP = 1  # 0x01
    MOTOR_HEAD_DOWN = 2  # 0x02
    MOTOR_FEET_UP = 4  # 0x04
    MOTOR_FEET_DOWN = 8  # 0x08
    MOTOR_TILT_UP = 16  # 0x10
    MOTOR_TILT_DOWN = 32  # 0x20
    MOTOR_LUMBAR_UP = 64  # 0x40
    MOTOR_LUMBAR_DOWN = 128  # 0x80

    # cmd1 byte commands
    MEMORY_1 = 256  # 0x100 -> cmd1=0x01
    LIGHT = 512  # 0x200 -> cmd1=0x02
    ZERO_G = 4096  # 0x1000 -> cmd1=0x10
    MEMORY_2 = 8192  # 0x2000 -> cmd1=0x20
    MEMORY_3 = 16384  # 0x4000 -> cmd1=0x40 (also TV)
    ANTI_SNORE = 32768  # 0x8000 -> cmd1=0x80

    # Presets
    PRESET_FLAT = 134217728  # 0x8000000 -> cmd3=0x08


class ScottLivingController(BedController):
    """Controller for Scott Living beds (9-byte Keeson variant)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Scott Living controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        self._char_uuid = KEESON_BASE_WRITE_CHAR_UUID
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug("ScottLivingController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return True  # Memory 3 / TV

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 3  # Memory 1, 2, 3 (TV)

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False  # Toggle only

    @property
    def has_tilt_support(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    def _build_command(self, key: int) -> bytes:
        """Build a 9-byte command packet from a key value.

        Format: [0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
        Checksum: (~sum(bytes 0-7)) & 0xFF
        """
        # Convert key to command bytes using bit positions
        cmd0 = key & 0xFF
        cmd1 = (key >> 8) & 0xFF
        cmd2 = (key >> 16) & 0xFF
        cmd3 = (key >> 24) & 0xFF
        side = 0x01  # Always side 1 in this app

        header = [0xE6, 0xFE, 0x16]
        data = header + [cmd0, cmd1, cmd2, cmd3, side]
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
            "Writing command to Scott Living bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started notifications for Scott Living bed")
        except BleakError:
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped notifications")
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data (not supported)."""
        pass

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it, always sending STOP at the end."""
        self._motor_state[motor] = direction
        key = 0

        # Build combined motor command
        state = self._motor_state
        if state.get("head") is True:
            key += ScottLivingCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            key += ScottLivingCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            key += ScottLivingCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            key += ScottLivingCommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            key += ScottLivingCommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            key += ScottLivingCommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            key += ScottLivingCommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            key += ScottLivingCommands.MOTOR_LUMBAR_DOWN

        try:
            if key:
                await self.write_command(
                    self._build_command(key),
                    repeat_count=self._coordinator.motor_pulse_count,
                    repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
                )
        finally:
            # Always send stop
            self._motor_state = {}
            try:
                await self.write_command(
                    self._build_command(0),  # Zero = stop
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", True)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", False)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", None)

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("feet", True)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("feet", False)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("feet", None)

    # Tilt motor control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_motor("tilt", True)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_motor("tilt", False)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._move_motor("tilt", None)

    # Lumbar motor control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_motor("lumbar", True)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_motor("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._move_motor("lumbar", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(0),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(ScottLivingCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: ScottLivingCommands.MEMORY_1,
            2: ScottLivingCommands.MEMORY_2,
            3: ScottLivingCommands.MEMORY_3,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Scott Living supports Memory 1-3, requested: %d", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Scott Living doesn't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(ScottLivingCommands.ZERO_G))

    async def preset_lounge(self) -> None:
        """Go to lounge position (not available)."""
        _LOGGER.warning("Lounge preset is not available on Scott Living beds")

    async def preset_tv(self) -> None:
        """Go to TV position (same as Memory 3)."""
        await self.write_command(self._build_command(ScottLivingCommands.MEMORY_3))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(ScottLivingCommands.ANTI_SNORE))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights (toggle)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(ScottLivingCommands.LIGHT))

    # Massage methods (not explicitly in the 8-button remote but may be available)
    async def massage_toggle(self) -> None:
        """Toggle massage (not implemented for Scott Living)."""
        _LOGGER.debug("Massage not implemented for Scott Living")
