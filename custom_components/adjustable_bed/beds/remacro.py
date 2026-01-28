"""Remacro bed controller implementation.

Reverse engineered from com.cheers.jewmes APK (Jeromes app).
This protocol is used by multiple furniture store brands:
- CheersSleep, Jeromes, Slumberland, The Brick

These beds use the SynData protocol with 8-byte command packets.

Packet format:
- Byte 0: Serial (incrementing sequence number, 1-255)
- Byte 1: PID/CtrlType (0x01 for control commands)
- Bytes 2-3: Command code (16-bit little-endian)
- Bytes 4-7: Parameter (32-bit little-endian, usually 0)

Detection: Service UUID 6e403587-b5a3-f393-e0a9-e50e24dcca9e (unique to this protocol)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import REMACRO_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class RemacroCommands:
    """Remacro command constants (16-bit values).

    Commands are sent in little-endian byte order within the 8-byte packet.
    """

    # Control PIDs (byte 1 of packet)
    CPID_CTRL = 0x01  # Control commands
    CPID_GET_STATE = 0x02  # Get state
    CPID_SET_PARA = 0x03  # Set parameters

    # Stop commands
    STOP = 0x0000  # Stop all (CCDstop)
    STOP_MOTOR = 0x0001  # Stop motors (CCDstop_motor)
    STOP_MASSAGE = 0x0002  # Stop massage (CCDstop_massage)
    CTRL_HOLD = 0x0003  # Hold command

    # Motor 1 (Head)
    M1_STOP = 256  # 0x0100
    M1_UP = 257  # 0x0101
    M1_DOWN = 258  # 0x0102
    M1_RUN = 259  # 0x0103

    # Motor 2 (Foot)
    M2_STOP = 260  # 0x0104
    M2_UP = 261  # 0x0105
    M2_DOWN = 262  # 0x0106
    M2_RUN = 263  # 0x0107

    # Motor 3 (Lumbar)
    M3_STOP = 264  # 0x0108
    M3_UP = 265  # 0x0109
    M3_DOWN = 266  # 0x010A
    M3_RUN = 267  # 0x010B

    # Motor 4 (Tilt/Neck)
    M4_STOP = 268  # 0x010C
    M4_UP = 269  # 0x010D
    M4_DOWN = 270  # 0x010E
    M4_RUN = 271  # 0x010F

    # All motors combined
    M_UP = 272  # 0x0110 - All motors up
    M_DOWN = 273  # 0x0111 - All motors down

    # Motor combinations (for convenience, not commonly used)
    M12_UP = 274  # Head + Foot up
    M12_DOWN = 275  # Head + Foot down
    M13_UP = 276  # Head + Lumbar up
    M13_DOWN = 277  # Head + Lumbar down
    M23_UP = 278  # Foot + Lumbar up
    M23_DOWN = 279  # Foot + Lumbar down

    # Massage zone control
    MM12_RUN = 288  # 0x0120 - Both massage zones
    MM1_RUN = 289  # 0x0121 - Massage zone 1
    MM2_RUN = 290  # 0x0122 - Massage zone 2
    MM1_STOP = 291  # 0x0123
    MM2_STOP = 292  # 0x0124

    # Massage modes (patterns)
    MMODE_STOP = 512  # 0x0200 - Stop massage mode
    MMODE1_RUN = 513  # 0x0201 - Mode 1
    MMODE2_RUN = 514  # 0x0202 - Mode 2
    MMODE3_RUN = 515  # 0x0203 - Mode 3
    MMODE4_RUN = 516  # 0x0204 - Mode 4
    MMODE5_RUN = 517  # 0x0205 - Mode 5

    # Memory presets - recall (go to position)
    MOV_ML1 = 785  # 0x0311 - Memory 1
    MOV_ML2 = 787  # 0x0313 - Memory 2
    MOV_ML3 = 789  # 0x0315 - Memory 3
    MOV_ML4 = 791  # 0x0317 - Memory 4

    # Memory presets - save (program current position)
    SET_ML1 = 784  # 0x0310 - Save Memory 1
    SET_ML2 = 786  # 0x0312 - Save Memory 2
    SET_ML3 = 788  # 0x0314 - Save Memory 3
    SET_ML4 = 790  # 0x0316 - Save Memory 4

    # Default presets (factory)
    DEF_ML1 = 769  # 0x0301 - Flat
    DEF_ML2 = 770  # 0x0302 - Zero-G
    DEF_ML3 = 771  # 0x0303 - TV
    DEF_ML4 = 772  # 0x0304 - Anti-snore

    # LED control
    LED_OFF = 1280  # 0x0500
    LED_RGBV = 1281  # 0x0501 - RGB with value
    LED_W = 1282  # 0x0502 - White
    LED_R = 1283  # 0x0503 - Red
    LED_G = 1284  # 0x0504 - Green
    LED_B = 1285  # 0x0505 - Blue
    LED_RG = 1286  # 0x0506 - Red+Green
    LED_RB = 1287  # 0x0507 - Red+Blue
    LED_GB = 1288  # 0x0508 - Green+Blue
    LED_M1 = 1289  # 0x0509 - Mode 1
    LED_M2 = 1290  # 0x050A - Mode 2
    LED_M3 = 1291  # 0x050B - Mode 3

    # Heat control
    HEAT_OFF = 28672  # 0x7000
    HEAT_M1 = 28673  # 0x7001 - Heat mode 1
    HEAT_M2 = 28674  # 0x7002 - Heat mode 2
    HEAT_M3 = 28675  # 0x7003 - Heat mode 3


class RemacroController(BedController):
    """Controller for Remacro protocol beds (CheersSleep, Jeromes, Slumberland, The Brick)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Remacro controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance.
        """
        super().__init__(coordinator)
        self._serial = 1  # Packet sequence number (1-255)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("RemacroController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return REMACRO_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_light(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - Remacro beds support lumbar control."""
        return True

    @property
    def has_tilt_support(self) -> bool:
        """Return True - Remacro beds support tilt/neck control."""
        return True

    def _next_serial(self) -> int:
        """Get the next serial number and increment."""
        serial = self._serial
        self._serial = (self._serial % 255) + 1
        return serial

    def _build_packet(self, command: int, parameter: int = 0) -> bytes:
        """Build an 8-byte command packet.

        Args:
            command: 16-bit command code.
            parameter: 32-bit parameter value (default 0).

        Returns:
            8-byte packet: [serial, PID, cmd_lo, cmd_hi, param0-3]
        """
        serial = self._next_serial()
        return bytes(
            [
                serial,
                RemacroCommands.CPID_CTRL,
                command & 0xFF,
                (command >> 8) & 0xFF,
                parameter & 0xFF,
                (parameter >> 8) & 0xFF,
                (parameter >> 16) & 0xFF,
                (parameter >> 24) & 0xFF,
            ]
        )

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
            "Writing command to Remacro bed (%s): %s (repeat: %d, delay: %dms)",
            REMACRO_WRITE_CHAR_UUID,
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
                    REMACRO_WRITE_CHAR_UUID, command, response=False
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Remacro position notifications not yet implemented")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""

    async def _send_command(self, command: int, repeat_count: int = 1) -> None:
        """Build and send a command packet."""
        packet = self._build_packet(command)
        await self.write_command(packet, repeat_count=repeat_count)

    async def _move_with_stop(self, command: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            packet = self._build_packet(command)
            await self.write_command(packet, repeat_count=10, repeat_delay_ms=100)
        finally:
            try:
                stop_packet = self._build_packet(RemacroCommands.STOP_MOTOR)
                await self.write_command(
                    stop_packet,
                    cancel_event=asyncio.Event(),  # Fresh event, not affected by cancel
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(RemacroCommands.M1_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(RemacroCommands.M1_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._send_command(RemacroCommands.M1_STOP)

    async def move_back_up(self) -> None:
        """Move back up (alias for head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (alias for head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs/feet up."""
        await self._move_with_stop(RemacroCommands.M2_UP)

    async def move_legs_down(self) -> None:
        """Move legs/feet down."""
        await self._move_with_stop(RemacroCommands.M2_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._send_command(RemacroCommands.M2_STOP)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._send_command(RemacroCommands.STOP_MOTOR)

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(RemacroCommands.M3_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(RemacroCommands.M3_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._send_command(RemacroCommands.M3_STOP)

    # Tilt/Neck control
    async def move_tilt_up(self) -> None:
        """Move tilt/neck up."""
        await self._move_with_stop(RemacroCommands.M4_UP)

    async def move_tilt_down(self) -> None:
        """Move tilt/neck down."""
        await self._move_with_stop(RemacroCommands.M4_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._send_command(RemacroCommands.M4_STOP)

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (default preset 1)."""
        await self._send_command(RemacroCommands.DEF_ML1)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (default preset 2)."""
        await self._send_command(RemacroCommands.DEF_ML2)

    async def preset_tv(self) -> None:
        """Go to TV position (default preset 3)."""
        await self._send_command(RemacroCommands.DEF_ML3)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (default preset 4)."""
        await self._send_command(RemacroCommands.DEF_ML4)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset position.

        Args:
            memory_num: Memory preset number (1-4).
        """
        memory_commands = {
            1: RemacroCommands.MOV_ML1,
            2: RemacroCommands.MOV_ML2,
            3: RemacroCommands.MOV_ML3,
            4: RemacroCommands.MOV_ML4,
        }
        if memory_num in memory_commands:
            await self._send_command(memory_commands[memory_num])
        else:
            _LOGGER.warning(
                "Invalid memory preset number: %d (valid: 1-4)", memory_num
            )

    async def program_memory(self, memory_num: int) -> None:
        """Save current position to memory preset.

        Args:
            memory_num: Memory preset number to save to (1-4).
        """
        save_commands = {
            1: RemacroCommands.SET_ML1,
            2: RemacroCommands.SET_ML2,
            3: RemacroCommands.SET_ML3,
            4: RemacroCommands.SET_ML4,
        }
        if memory_num in save_commands:
            await self._send_command(save_commands[memory_num])
        else:
            _LOGGER.warning(
                "Invalid memory preset number for programming: %d (valid: 1-4)",
                memory_num,
            )

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage mode 1."""
        await self._send_command(RemacroCommands.MMODE1_RUN)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage zone."""
        await self._send_command(RemacroCommands.MM1_RUN)

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage zone."""
        await self._send_command(RemacroCommands.MM2_RUN)

    async def massage_stop(self) -> None:
        """Stop massage."""
        await self._send_command(RemacroCommands.MMODE_STOP)

    async def massage_mode_2(self) -> None:
        """Set massage mode 2."""
        await self._send_command(RemacroCommands.MMODE2_RUN)

    async def massage_mode_3(self) -> None:
        """Set massage mode 3."""
        await self._send_command(RemacroCommands.MMODE3_RUN)

    # Light control
    async def lights_toggle(self) -> None:
        """Toggle under-bed light (cycles through modes)."""
        await self._send_command(RemacroCommands.LED_W)

    async def lights_on(self) -> None:
        """Turn on under-bed light (white mode)."""
        await self._send_command(RemacroCommands.LED_W)

    async def lights_off(self) -> None:
        """Turn off under-bed light."""
        await self._send_command(RemacroCommands.LED_OFF)
