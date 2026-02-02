"""OKIN ORE (OREBedBleProtocol) bed controller implementation.

Protocol reverse-engineered from com.ore.bedding.glideawaymontion APK.
See disassembly/output/com.ore.bedding.glideawaymontion/ANALYSIS.md for details.

This controller handles beds that use the OREBedBleProtocol A5 5A packet format:
- Dynasty beds
- INNOVA beds
- Other ORE/OKIN beds with service UUID 00001000-0000-1000-8000-00805f9b34fb

Packet format: [0xA5, 0x5A, checksum, 0x00, param_length, cmd_hi, cmd_lo, ...params]
Checksum: ~(SUM of bytes from index 3) & 0xFF
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import OKIN_ORE_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class OkinOreCommands:
    """OKIN ORE protocol command constants.

    Commands are 16-bit values that get encoded into the A5 5A packet format.
    Values extracted from OREBedBleProtocol.java in the APK.
    """

    # Motor movement (0x2000 series)
    STOP = 0x2000  # 8192
    HEAD_UP = 0x2001  # 8193
    HEAD_DOWN = 0x2002  # 8194
    FOOT_UP = 0x2003  # 8195
    FOOT_DOWN = 0x2004  # 8196
    BACK_UP = 0x2005  # 8197
    BACK_DOWN = 0x2006  # 8198
    LUMBAR_UP = 0x2007  # 8199
    LUMBAR_DOWN = 0x2008  # 8200
    ALL_UP = 0x200B  # 8203
    ALL_DOWN = 0x200C  # 8204

    # Massage intensity step (0x2020/0x2030 series)
    HEAD_MASSAGE_UP = 0x2020  # 8224 - increase head massage intensity
    HEAD_MASSAGE_DOWN = 0x2021  # 8225 - decrease head massage intensity
    FOOT_MASSAGE_UP = 0x2030  # 8240 - increase foot massage intensity
    FOOT_MASSAGE_DOWN = 0x2031  # 8241 - decrease foot massage intensity

    # Preset positions (0x2060 series)
    ZERO_G = 0x2060  # 8288
    LOUNGE = 0x2061  # 8289
    TV = 0x2062  # 8290
    ANTI_SNORE = 0x2063  # 8291
    MEMORY_1 = 0x2064  # 8292
    MEMORY_2 = 0x2065  # 8293
    FLAT = 0x2066  # 8294

    # Light and massage controls (0x2080 series)
    LIGHT_TOGGLE = 0x2080  # 8320
    MASSAGE_ON_OFF = 0x2081  # 8321 - toggle massage on/off
    MASSAGE_TIMER = 0x2082  # 8322 - cycle through timer options


class OkinOreController(BedController):
    """Controller for OKIN ORE protocol beds.

    These beds use the A5 5A packet format with checksum over
    the unique 00001000 service UUID.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the OKIN ORE controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._head_massage: int = 0
        self._foot_massage: int = 0
        _LOGGER.debug("OkinOreController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIN_ORE_WRITE_CHAR_UUID

    def _build_command(self, cmd_value: int, params: bytes = b"") -> bytes:
        """Build an A5 5A format command packet.

        Packet format: [0xA5, 0x5A, checksum, 0x00, param_length, cmd_hi, cmd_lo, ...params]
        Checksum: ~(SUM of bytes from index 3) & 0xFF

        Args:
            cmd_value: 16-bit command value (e.g., 0x2000 for STOP)
            params: Optional parameter bytes to append after command

        Returns:
            Complete packet bytes ready to send
        """
        cmd_hi = (cmd_value >> 8) & 0xFF
        cmd_lo = cmd_value & 0xFF
        param_length = len(params)

        # Build payload (bytes 3 onwards for checksum calculation)
        payload = bytes([0x00, param_length, cmd_hi, cmd_lo]) + params

        # Calculate checksum: ~(sum of payload bytes) & 0xFF
        checksum = (~sum(payload)) & 0xFF

        # Build complete packet
        return bytes([0xA5, 0x5A, checksum]) + payload

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
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - ORE beds support Memory 1 and Memory 2."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 2 - ORE beds support Memory 1 and Memory 2."""
        return 2

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - ORE beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - ORE beds only have toggle, no discrete on/off."""
        return False

    @property
    def supports_stop_all(self) -> bool:
        """Return True - ORE beds have a dedicated STOP command."""
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        """Return True - ORE beds support step up/down intensity control."""
        return True

    @property
    def massage_intensity_max(self) -> int:
        """Return max massage intensity (10 levels)."""
        return 10

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        await self._write_gatt_with_retry(
            OKIN_ORE_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
        )

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        # ORE beds don't support position feedback via notifications
        self._notify_callback = callback
        _LOGGER.debug("OKIN ORE beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current motor positions."""
        # Not supported on ORE beds

    async def _move_with_stop(self, cmd_value: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(
                self._build_command(cmd_value),
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            try:
                await self.write_command(
                    self._build_command(OkinOreCommands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(OkinOreCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(OkinOreCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_command(OkinOreCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(OkinOreCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(OkinOreCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_command(OkinOreCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(OkinOreCommands.BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(OkinOreCommands.BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.write_command(
            self._build_command(OkinOreCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_legs_up(self) -> None:
        """Move legs up (alias for feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (alias for feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(OkinOreCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(OkinOreCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(
            self._build_command(OkinOreCommands.STOP), cancel_event=asyncio.Event()
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_command(OkinOreCommands.STOP), cancel_event=asyncio.Event()
        )

    # Preset positions
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(OkinOreCommands.FLAT))

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self.write_command(self._build_command(OkinOreCommands.ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(OkinOreCommands.ANTI_SNORE))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(OkinOreCommands.LOUNGE))

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command(OkinOreCommands.TV))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory position."""
        if memory_num == 1:
            await self.write_command(self._build_command(OkinOreCommands.MEMORY_1))
        elif memory_num == 2:
            await self.write_command(self._build_command(OkinOreCommands.MEMORY_2))
        else:
            _LOGGER.warning(
                "OKIN ORE beds only support Memory 1 and Memory 2 (requested: %d)",
                memory_num,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program memory position (not supported)."""
        _LOGGER.warning(
            "OKIN ORE beds don't support programming memory positions (requested: %d)",
            memory_num,
        )

    # Light controls
    async def lights_on(self) -> None:
        """Turn lights on (toggle)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn lights off (toggle)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(OkinOreCommands.LIGHT_TOGGLE))

    # Massage controls
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(self._build_command(OkinOreCommands.MASSAGE_ON_OFF))

    async def massage_on(self) -> None:
        """Turn massage on."""
        await self.massage_toggle()

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.massage_toggle()

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(OkinOreCommands.HEAD_MASSAGE_UP))
        self._head_massage = min(10, self._head_massage + 1)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(OkinOreCommands.HEAD_MASSAGE_DOWN))
        self._head_massage = max(0, self._head_massage - 1)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(OkinOreCommands.FOOT_MASSAGE_UP))
        self._foot_massage = min(10, self._foot_massage + 1)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(OkinOreCommands.FOOT_MASSAGE_DOWN))
        self._foot_massage = max(0, self._foot_massage - 1)

    async def massage_intensity_up(self) -> None:
        """Increase all massage intensity."""
        await self.massage_head_up()
        await self.massage_foot_up()

    async def massage_intensity_down(self) -> None:
        """Decrease all massage intensity."""
        await self.massage_head_down()
        await self.massage_foot_down()

    async def massage_mode_step(self) -> None:
        """Step through massage timer options."""
        await self.write_command(self._build_command(OkinOreCommands.MASSAGE_TIMER))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        if self._head_massage > 0:
            await self.massage_head_down()
        else:
            await self.massage_head_up()

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        if self._foot_massage > 0:
            await self.massage_foot_down()
        else:
            await self.massage_foot_up()
