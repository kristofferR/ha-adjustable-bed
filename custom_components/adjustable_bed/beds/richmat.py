"""Richmat bed controller implementation.

Richmat beds have two protocol variants:
- Nordic: Simple single-byte commands
- WiLinke: 5-byte commands with checksum [110, 1, 0, command, command + 111]
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import (
    RICHMAT_NORDIC_CHAR_UUID,
    RICHMAT_PROTOCOL_SINGLE,
    RICHMAT_PROTOCOL_WILINKE,
    RICHMAT_WILINKE_CHAR_UUIDS,
    RICHMAT_WILINKE_SERVICE_UUIDS,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class RichmatCommands:
    """Richmat command constants (command byte values)."""

    # Presets
    PRESET_FLAT = 0x31
    PRESET_ANTI_SNORE = 0x46
    PRESET_LOUNGE = 0x59
    PRESET_MEMORY_1 = 0x2E
    PRESET_MEMORY_2 = 0x2F
    PRESET_TV = 0x58
    PRESET_ZERO_G = 0x45

    # Program presets
    PROGRAM_ANTI_SNORE = 0x69
    PROGRAM_LOUNGE = 0x65
    PROGRAM_MEMORY_1 = 0x2B
    PROGRAM_MEMORY_2 = 0x2C
    PROGRAM_TV = 0x64
    PROGRAM_ZERO_G = 0x66

    # Massage
    MASSAGE_HEAD_STEP = 0x4C
    MASSAGE_FOOT_STEP = 0x4E
    MASSAGE_PATTERN_STEP = 0x48
    MASSAGE_TOGGLE = 0x5D

    # Lights
    LIGHTS_TOGGLE = 0x3C

    # Motors
    MOTOR_PILLOW_UP = 0x3F
    MOTOR_PILLOW_DOWN = 0x40
    MOTOR_HEAD_UP = 0x24
    MOTOR_HEAD_DOWN = 0x25
    MOTOR_FEET_UP = 0x26
    MOTOR_FEET_DOWN = 0x27
    MOTOR_LUMBAR_UP = 0x41
    MOTOR_LUMBAR_DOWN = 0x42

    # End/Stop
    END = 0x6E


class RichmatController(BedController):
    """Controller for Richmat beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        is_wilinke: bool = False,
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the Richmat controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            is_wilinke: Whether this is a WiLinke variant (uses 5-byte commands)
            char_uuid: The characteristic UUID to use for writing commands
        """
        super().__init__(coordinator)
        self._is_wilinke = is_wilinke
        self._char_uuid = char_uuid or RICHMAT_NORDIC_CHAR_UUID
        self._notify_callback: Callable[[str, float], None] | None = None

        # Determine command protocol based on variant
        self._command_protocol = (
            RICHMAT_PROTOCOL_WILINKE if is_wilinke else RICHMAT_PROTOCOL_SINGLE
        )

        _LOGGER.debug(
            "RichmatController initialized (wilinke: %s, char: %s, protocol: %s)",
            is_wilinke,
            self._char_uuid,
            self._command_protocol,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    def _build_command(self, command_byte: int) -> bytes:
        """Build command bytes based on command protocol."""
        if self._command_protocol == RICHMAT_PROTOCOL_WILINKE:
            # WiLinke: [110, 1, 0, command, checksum]
            # checksum = command + 111
            return bytes([110, 1, 0, command_byte, (command_byte + 111) & 0xFF])
        else:
            # Single/Nordic: just the command byte
            return bytes([command_byte])

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
            "Writing command to Richmat bed: %s (repeat: %d, delay: %dms)",
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
                    self._char_uuid, command, response=False
                )
            except BleakError as err:
                _LOGGER.exception("Failed to write command")
                # Log discovered services to help debug characteristic not found issues
                if "not found" in str(err).lower() or "invalid" in str(err).lower():
                    _LOGGER.warning(
                        "Characteristic %s may not exist on this device. "
                        "Please report this to help add support for your device.",
                        self._char_uuid,
                    )
                    self.log_discovered_services(level=logging.INFO)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # Richmat beds don't support position notifications
        self._notify_callback = callback
        _LOGGER.debug("Richmat beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        # Richmat beds don't support position reading
        pass

    async def _send_command(self, command_byte: int, repeat: int | None = None) -> None:
        """Send a command to the bed."""
        command = self._build_command(command_byte)
        pulse_count = repeat if repeat is not None else self._coordinator.motor_pulse_count
        pulse_delay = self._coordinator.motor_pulse_delay_ms
        await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    async def _move_with_stop(self, command_byte: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._send_command(command_byte)
        finally:
            await self.write_command(
                self._build_command(RichmatCommands.END),
                cancel_event=asyncio.Event(),
            )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(RichmatCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(RichmatCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            self._build_command(RichmatCommands.END),
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head for Richmat)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Richmat)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for Richmat)."""
        await self._move_with_stop(RichmatCommands.MOTOR_FEET_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for Richmat)."""
        await self._move_with_stop(RichmatCommands.MOTOR_FEET_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(RichmatCommands.MOTOR_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(RichmatCommands.MOTOR_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            self._build_command(RichmatCommands.END),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position.

        Presets are single-command triggered - the bed's internal controller
        handles moving to the position automatically after receiving one command.
        """
        await self.write_command(self._build_command(RichmatCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Presets are single-command triggered - the bed's internal controller
        handles moving to the position automatically after receiving one command.
        """
        commands = {
            1: RichmatCommands.PRESET_MEMORY_1,
            2: RichmatCommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: RichmatCommands.PROGRAM_MEMORY_1,
            2: RichmatCommands.PROGRAM_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position.

        Presets are single-command triggered - the bed's internal controller
        handles moving to the position automatically after receiving one command.
        """
        await self.write_command(self._build_command(RichmatCommands.PRESET_ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position.

        Presets are single-command triggered - the bed's internal controller
        handles moving to the position automatically after receiving one command.
        """
        await self.write_command(self._build_command(RichmatCommands.PRESET_ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV/lounge position.

        Presets are single-command triggered - the bed's internal controller
        handles moving to the position automatically after receiving one command.
        """
        await self.write_command(self._build_command(RichmatCommands.PRESET_TV))

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(RichmatCommands.LIGHTS_TOGGLE))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(self._build_command(RichmatCommands.MASSAGE_TOGGLE))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(self._build_command(RichmatCommands.MASSAGE_HEAD_STEP))

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(self._build_command(RichmatCommands.MASSAGE_FOOT_STEP))

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(self._build_command(RichmatCommands.MASSAGE_PATTERN_STEP))


async def detect_richmat_variant(client) -> tuple[bool, str | None]:
    """Detect which Richmat variant this device is.

    Returns:
        Tuple of (is_wilinke, characteristic_uuid)
    """
    # Try WiLinke variants first
    for i, service_uuid in enumerate(RICHMAT_WILINKE_SERVICE_UUIDS):
        try:
            service = client.services.get_service(service_uuid)
            if service:
                write_uuid = RICHMAT_WILINKE_CHAR_UUIDS[i][0]
                char = service.get_characteristic(write_uuid)
                if char:
                    _LOGGER.debug(
                        "Detected WiLinke Richmat variant (service: %s, char: %s)",
                        service_uuid,
                        write_uuid,
                    )
                    return True, write_uuid
        except Exception as err:
            _LOGGER.debug(
                "WiLinke variant check failed for service %s: %s",
                service_uuid,
                err,
            )

    # Fall back to Nordic
    _LOGGER.debug("Using Nordic Richmat variant")
    return False, RICHMAT_NORDIC_CHAR_UUID
