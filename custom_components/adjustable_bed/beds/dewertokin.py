"""DewertOkin bed controller implementation.

DewertOkin beds (A H Beard, HankookGallery) use handle-based BLE writes.

Protocol details:
    Write handle: 0x0013 (not UUID-based)
    Address type: Random
    Command format: 6-byte Okin frame [0x04, 0x02, <4-byte-command-big-endian>]
    See okin_protocol.py for shared frame building functions.

Motor timing:
    Pulse width: Single BLE write per pulse
    Inter-pulse delay: 50ms for continuous movement
    Repeat count: 25 pulses for typical motor travel
    Stop command: Send STOP (0x000000) to halt motors

Preset timing:
    Preset commands move to stored positions automatically
    Duration: Variable based on distance to target (typically 10-30 seconds)
    No debounce required between preset commands

Position feedback: Not supported
    DewertOkin beds do not report motor positions.
    The 4-byte command payload is output-only (motor commands, not position data).

Detection: By device name patterns ("dewertokin", "dewert", "a h beard", "hankook"),
not by service UUID.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import DEWERTOKIN_WRITE_HANDLE
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class DewertOkinCommands:
    """DewertOkin command constants (6-byte arrays)."""

    # Presets
    FLAT = bytes.fromhex("040210000000")
    ZERO_G = bytes.fromhex("040200004000")
    TV = bytes.fromhex("040200003000")
    QUIET_SLEEP = bytes.fromhex("040200008000")
    MEMORY_1 = bytes.fromhex("040200001000")
    MEMORY_2 = bytes.fromhex("040200002000")

    # Motor controls
    HEAD_UP = bytes.fromhex("040200000001")
    HEAD_DOWN = bytes.fromhex("040200000002")
    FOOT_UP = bytes.fromhex("040200000004")
    FOOT_DOWN = bytes.fromhex("040200000008")

    # Massage
    WAVE_MASSAGE = bytes.fromhex("040280000000")
    HEAD_MASSAGE = bytes.fromhex("040200000800")
    FOOT_MASSAGE = bytes.fromhex("040200400000")
    MASSAGE_OFF = bytes.fromhex("040202000000")

    # Lights
    UNDERLIGHT = bytes.fromhex("040200020000")

    # Stop/keepalive
    STOP = bytes.fromhex("040200000000")


class DewertOkinController(BedController):
    """Controller for DewertOkin beds.

    DewertOkin beds use handle-based writes to handle 0x0013.
    They support motor control, presets, massage, and under-bed lighting.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the DewertOkin controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("DewertOkinController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return placeholder - this controller uses handle-based writes."""
        return f"handle-0x{DEWERTOKIN_WRITE_HANDLE:04x}"

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
    def supports_lights(self) -> bool:
        """Return True - DewertOkin beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - DewertOkin only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - DewertOkin beds support memory presets (slots 1-2)."""
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed using handle 0x0013."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to DewertOkin bed (handle 0x%04x): %s (repeat: %d, delay: %dms)",
            DEWERTOKIN_WRITE_HANDLE,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                # Write to handle directly (Bleak supports integer handles)
                await self.client.write_gatt_char(
                    DEWERTOKIN_WRITE_HANDLE, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("DewertOkin beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

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
                    DewertOkinCommands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(DewertOkinCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(DewertOkinCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            DewertOkinCommands.STOP,
            cancel_event=asyncio.Event(),
        )

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
        await self._move_with_stop(DewertOkinCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self._move_with_stop(DewertOkinCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(
            DewertOkinCommands.STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(DewertOkinCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(DewertOkinCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.write_command(
            DewertOkinCommands.STOP,
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            DewertOkinCommands.STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            DewertOkinCommands.FLAT,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: DewertOkinCommands.MEMORY_1,
            2: DewertOkinCommands.MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(command, repeat_count=100, repeat_delay_ms=150)
        else:
            _LOGGER.warning("DewertOkin beds only support memory presets 1 and 2")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "DewertOkin beds don't support programming memory presets via BLE"
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            DewertOkinCommands.ZERO_G,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(
            DewertOkinCommands.TV,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_anti_snore(self) -> None:
        """Go to quiet sleep/anti-snore position."""
        await self.write_command(
            DewertOkinCommands.QUIET_SLEEP,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(DewertOkinCommands.UNDERLIGHT)

    async def lights_on(self) -> None:
        """Turn lights on.

        Note: The Okin protocol only supports toggle, so this sends a toggle command.
        Calling lights_on() when lights are already on will turn them off.
        """
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn lights off.

        Note: The Okin protocol only supports toggle, so this sends a toggle command.
        Calling lights_off() when lights are already off will turn them on.
        """
        await self.lights_toggle()

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle wave massage."""
        await self.write_command(DewertOkinCommands.WAVE_MASSAGE)

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.write_command(DewertOkinCommands.MASSAGE_OFF)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(DewertOkinCommands.HEAD_MASSAGE)

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(DewertOkinCommands.FOOT_MASSAGE)
