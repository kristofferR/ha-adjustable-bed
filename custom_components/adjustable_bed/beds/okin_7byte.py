"""Okin 7-byte protocol bed controller implementation.

Protocol reverse-engineered and documented by MaximumWorf (https://github.com/MaximumWorf)
Source: https://github.com/MaximumWorf/homeassistant-nectar

This controller handles beds that use the 7-byte command format:
    5A 01 03 10 30 [XX] A5

Two variants share this format:
- Okin 7-byte (via OKIN service UUID): Nectar and similar OKIN beds
- Okin Nordic (via Nordic UART service): Mattress Firm 900 / iFlex

The variants differ only in a few command bytes and the Nordic variant has
additional features (init handshake, incline preset, massage intensity,
light cycle). Both are parameterized via Okin7ByteConfig.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import MATTRESSFIRM_WRITE_CHAR_UUID, NECTAR_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _cmd(byte_val: int) -> bytes:
    """Build a 7-byte Okin command from the variable byte."""
    return bytes([0x5A, 0x01, 0x03, 0x10, 0x30, byte_val, 0xA5])


@dataclass(frozen=True)
class Okin7ByteConfig:
    """Configuration for Okin 7-byte protocol variants.

    All command bytes are the single variable byte (index 5) in the
    7-byte frame: [5A 01 03 10 30 XX A5].
    """

    char_uuid: str
    lumbar_up_byte: int
    lounge_byte: int
    tv_byte: int = 0
    memory_1_byte: int = 0
    memory_2_byte: int = 0
    init_commands: tuple[bytes, ...] = ()
    has_incline: bool = False
    incline_byte: int = 0
    has_light_cycle: bool = False
    has_massage_intensity: bool = False
    massage_up_byte: int = 0
    massage_down_byte: int = 0
    extra_massage_modes: tuple[int, ...] = ()
    massage_stop_byte: int = 0
    lights_off_repeat: int = 1
    supports_tv: bool = False


# Standard Okin 7-byte variant (Nectar beds)
OKIN_7BYTE_CONFIG = Okin7ByteConfig(
    char_uuid=NECTAR_WRITE_CHAR_UUID,
    lumbar_up_byte=0x06,
    lounge_byte=0x12,
    tv_byte=0x11,
    memory_1_byte=0x1A,
    memory_2_byte=0x1B,
    supports_tv=True,
)

# Nordic UART variant (Mattress Firm 900 / iFlex)
OKIN_NORDIC_CONFIG = Okin7ByteConfig(
    char_uuid=MATTRESSFIRM_WRITE_CHAR_UUID,
    lumbar_up_byte=0x06,
    lounge_byte=0x17,
    init_commands=(
        bytes.fromhex("09050A23050000"),  # 7-byte init sequence
        bytes.fromhex("5A0B00A5"),  # 4-byte secondary init
    ),
    has_incline=True,
    incline_byte=0x18,
    has_light_cycle=True,
    has_massage_intensity=True,
    massage_up_byte=0x60,  # Note: byte 4 is 0x40 for these, see _cmd_massage_intensity
    massage_down_byte=0x63,
    extra_massage_modes=(0x52, 0x53, 0x54),  # MASSAGE_1, MASSAGE_2, MASSAGE_3
    massage_stop_byte=0x6F,
    lights_off_repeat=3,
    supports_tv=True,
)


class Okin7ByteController(BedController):
    """Controller for beds using the Okin 7-byte protocol.

    Supports both the standard Okin service variant and the Nordic UART variant
    via the Okin7ByteConfig dataclass.
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        config: Okin7ByteConfig = OKIN_7BYTE_CONFIG,
    ) -> None:
        """Initialize the Okin 7-byte controller."""
        super().__init__(coordinator)
        self._config = config
        self._initialized: bool = len(config.init_commands) == 0
        _LOGGER.debug(
            "Okin7ByteController initialized (char=%s, init_needed=%s)",
            config.char_uuid,
            not self._initialized,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._config.char_uuid

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
        return self._config.supports_tv

    @property
    def supports_preset_incline(self) -> bool:
        return self._config.has_incline

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - these beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - separate LIGHT_ON/LIGHT_OFF commands."""
        return True

    @property
    def supports_light_cycle(self) -> bool:
        """Return True if this variant supports cycling through light modes."""
        return self._config.has_light_cycle

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if this variant has memory preset bytes configured."""
        return self._config.memory_1_byte != 0

    @property
    def memory_slot_count(self) -> int:
        return 2

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed, sending init sequence on first use."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        # Send init sequence on first command (Nordic variant only)
        if not self._initialized:
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled before init sequence")
                return
            _LOGGER.debug("Sending init sequence before first command")
            try:
                for init_cmd in self._config.init_commands:
                    async with self._ble_lock:
                        await self.client.write_gatt_char(
                            self._config.char_uuid, init_cmd, response=True
                        )
                    await asyncio.sleep(0.1)
                self._initialized = True
            except BleakError:
                _LOGGER.exception("Failed to send init sequence")
                raise

        await self._write_gatt_with_retry(
            self._config.char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def _send_stop(self) -> None:
        """Send STOP command with fresh cancel event."""
        await self.write_command(_cmd(0x0F), cancel_event=asyncio.Event())

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(_cmd(0x00))

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(_cmd(0x01))

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(_cmd(0x02))

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(_cmd(0x03))

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self._send_stop()

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
        await self._move_with_stop(_cmd(self._config.lumbar_up_byte))

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(_cmd(0x07))

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self._send_stop()

    # Preset positions
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._preset_with_stop(_cmd(0x10))

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self._preset_with_stop(_cmd(0x13))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._preset_with_stop(_cmd(0x16))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self._preset_with_stop(_cmd(self._config.lounge_byte))

    async def preset_tv(self) -> None:
        """Go to TV position."""
        if self._config.tv_byte:
            await self._preset_with_stop(_cmd(self._config.tv_byte))
        else:
            await self.preset_lounge()

    async def preset_incline(self) -> None:
        """Go to incline position."""
        if self._config.has_incline:
            await self._preset_with_stop(_cmd(self._config.incline_byte))
        else:
            raise NotImplementedError("Incline preset not supported on this variant")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory position (slots 1-2)."""
        memory_bytes = {
            1: self._config.memory_1_byte,
            2: self._config.memory_2_byte,
        }
        byte_val = memory_bytes.get(memory_num, 0)
        if not byte_val:
            raise NotImplementedError(
                f"Memory slot {memory_num} not supported on this variant"
            )
        await self._preset_with_stop(_cmd(byte_val))

    async def program_memory(self, memory_num: int) -> None:
        """Program memory position (not supported)."""
        raise NotImplementedError(
            f"Memory programming (slot {memory_num}) not supported on Okin 7-byte beds"
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self._send_stop()

    # Massage controls
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(_cmd(0x5A))

    async def massage_on(self) -> None:
        """Turn massage on."""
        if self._config.extra_massage_modes:
            # Nordic: use MASSAGE_1 for explicit on
            await self.write_command(_cmd(self._config.extra_massage_modes[0]))
        else:
            await self.write_command(_cmd(0x58))

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self.write_command(_cmd(0x6F))

    async def massage_mode_step(self) -> None:
        """Step through massage modes (wave pattern)."""
        await self.write_command(_cmd(0x59))

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        if self._config.has_massage_intensity:
            # Nordic: byte 4 is 0x40 instead of 0x30 for intensity commands
            await self.write_command(
                bytes([0x5A, 0x01, 0x03, 0x10, 0x40, self._config.massage_up_byte, 0xA5])
            )
        else:
            raise NotImplementedError("Massage intensity control not supported on this variant")

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        if self._config.has_massage_intensity:
            await self.write_command(
                bytes([0x5A, 0x01, 0x03, 0x10, 0x40, self._config.massage_down_byte, 0xA5])
            )
        else:
            raise NotImplementedError("Massage intensity control not supported on this variant")

    async def massage_head_toggle(self) -> None:
        """Toggle head massage (uses global massage control)."""
        await self.massage_toggle()

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage (uses global massage control)."""
        await self.massage_toggle()

    # Light controls
    async def lights_on(self) -> None:
        """Turn lights on."""
        await self.write_command(_cmd(0x73))

    async def lights_off(self) -> None:
        """Turn lights off."""
        await self.write_command(_cmd(0x74), repeat_count=self._config.lights_off_repeat)

    async def lights_toggle(self) -> None:
        """Toggle lights on/off."""
        await self.write_command(_cmd(0x71))
