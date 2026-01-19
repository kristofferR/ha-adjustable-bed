"""Richmat bed controller implementation.

Reverse engineering by getrav and Richard Hopton (smartbed-mqtt).

Richmat beds have two protocol variants:
- Nordic: Simple single-byte commands
- WiLinke: 5-byte commands with checksum [110, 1, 0, command, command + 111]
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError

from ..const import (
    RICHMAT_NORDIC_CHAR_UUID,
    RICHMAT_PROTOCOL_SINGLE,
    RICHMAT_PROTOCOL_WILINKE,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTE_FEATURES,
    RICHMAT_WILINKE_CHAR_UUIDS,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RichmatFeatures,
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
        remote_code: str | None = None,
    ) -> None:
        """Initialize the Richmat controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            is_wilinke: Whether this is a WiLinke variant (uses 5-byte commands)
            char_uuid: The characteristic UUID to use for writing commands
            remote_code: The remote code for feature detection (e.g., "VIRM", "I7RM")
        """
        super().__init__(coordinator)
        self._is_wilinke = is_wilinke
        self._char_uuid = char_uuid or RICHMAT_NORDIC_CHAR_UUID
        self._notify_callback: Callable[[str, float], None] | None = None
        self._remote_code = remote_code or RICHMAT_REMOTE_AUTO
        self._features = RICHMAT_REMOTE_FEATURES.get(
            self._remote_code, RICHMAT_REMOTE_FEATURES[RICHMAT_REMOTE_AUTO]
        )

        # Determine command protocol based on variant
        self._command_protocol = (
            RICHMAT_PROTOCOL_WILINKE if is_wilinke else RICHMAT_PROTOCOL_SINGLE
        )

        _LOGGER.debug(
            "RichmatController initialized (wilinke: %s, char: %s, protocol: %s, remote: %s)",
            is_wilinke,
            self._char_uuid,
            self._command_protocol,
            self._remote_code,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    @property
    def features(self) -> RichmatFeatures:
        """Return the feature flags for this controller."""
        return self._features

    # Capability properties based on remote code features
    @property
    def supports_preset_zero_g(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_ZERO_G)

    @property
    def supports_preset_anti_snore(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_ANTI_SNORE)

    @property
    def supports_preset_tv(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_TV)

    @property
    def supports_preset_lounge(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_LOUNGE)

    @property
    def has_lumbar_support(self) -> bool:
        return bool(self._features & RichmatFeatures.MOTOR_LUMBAR)

    @property
    def has_pillow_support(self) -> bool:
        return bool(self._features & RichmatFeatures.MOTOR_PILLOW)

    @property
    def supports_lights(self) -> bool:
        """Return True if this bed supports under-bed lights."""
        return bool(self._features & RichmatFeatures.UNDER_BED_LIGHTS)

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Richmat only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if this bed supports memory presets based on detected features."""
        return bool(self._features & (RichmatFeatures.PRESET_MEMORY_1 | RichmatFeatures.PRESET_MEMORY_2))

    @property
    def memory_slot_count(self) -> int:
        """Return number of memory slots based on detected features."""
        count = 0
        if self._features & RichmatFeatures.PRESET_MEMORY_1:
            count += 1
        if self._features & RichmatFeatures.PRESET_MEMORY_2:
            count += 1
        return count

    @property
    def supports_memory_programming(self) -> bool:
        """Return True if this bed supports programming memory positions."""
        return bool(self._features & (RichmatFeatures.PROGRAM_MEMORY_1 | RichmatFeatures.PROGRAM_MEMORY_2))

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
        _LOGGER.debug(
            "Writing command to Richmat bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        try:
            await self._write_gatt_with_retry(
                self._char_uuid,
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
                cancel_event=cancel_event,
            )
        except BleakError as err:
            # Additional diagnostics for characteristic issues
            if "not found" in str(err).lower() or "invalid" in str(err).lower():
                _LOGGER.warning(
                    "Characteristic %s may not exist on this device. "
                    "Please report this to help add support for your device.",
                    self._char_uuid,
                )
                self.log_discovered_services(level=logging.INFO)
            raise

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
            # Wrap in try-except to prevent masking the original exception
            try:
                await self.write_command(
                    self._build_command(RichmatCommands.END),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send END command during cleanup")

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

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(RichmatCommands.MOTOR_LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(RichmatCommands.MOTOR_LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self.move_head_stop()

    async def move_pillow_up(self) -> None:
        """Move pillow up."""
        await self._move_with_stop(RichmatCommands.MOTOR_PILLOW_UP)

    async def move_pillow_down(self) -> None:
        """Move pillow down."""
        await self._move_with_stop(RichmatCommands.MOTOR_PILLOW_DOWN)

    async def move_pillow_stop(self) -> None:
        """Stop pillow motor."""
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

    async def lights_on(self) -> None:
        """Turn on under-bed lights (toggle-only, state unknown)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed lights (toggle-only, state unknown)."""
        await self.lights_toggle()

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


async def detect_richmat_variant(client: BleakClient) -> tuple[bool, str | None]:
    """Detect which Richmat variant this device is.

    Returns:
        Tuple of (is_wilinke, characteristic_uuid)
    """
    # Guard against missing service discovery
    if client.services is None:
        _LOGGER.warning(
            "BLE services not discovered, falling back to Nordic Richmat variant"
        )
        return False, RICHMAT_NORDIC_CHAR_UUID

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
