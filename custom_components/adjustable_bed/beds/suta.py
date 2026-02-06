"""SUTA Smart Home bed controller implementation.

Protocol reverse-engineered from com.shuta.smart_home.

Bed-frame controllers use an ASCII AT command protocol over BLE:
- Service UUID: 0000fff0-0000-1000-8000-00805f9b34fb
- Command format: b"AT+...\\r\\n" (UTF-8, CRLF-terminated)
- No checksum

Characteristic UUIDs are discovered dynamically based on GATT properties.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..const import SUTA_DEFAULT_WRITE_CHAR_UUID, SUTA_SERVICE_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SutaCommands:
    """SUTA AT command strings."""

    # Motor control
    BACK_UP = "AT+CTRL=BOTH BACK UP"
    BACK_DOWN = "AT+CTRL=BOTH BACK DOWN"
    FOOT_UP = "AT+CTRL=BOTH FOOT UP"
    FOOT_DOWN = "AT+CTRL=BOTH FOOT DOWN"
    TILT_LUMBAR_UP = "AT+CTRL=BOTH T/L UP"
    TILT_LUMBAR_DOWN = "AT+CTRL=BOTH T/L DOWN"
    STOP_ALL = "AT+CTRL=BOTH STOP"

    # Presets (recall)
    PRESET_FLAT = "AT+MODE=BOTH FLAT"
    PRESET_ZERO_G = "AT+MODE=BOTH ZEROG"
    PRESET_ANTI_SNORE = "AT+MODE=BOTH SNORE"
    PRESET_TV = "AT+MODE=BOTH TV"
    PRESET_MEMORY_1 = "AT+MODE=BOTH M1"
    PRESET_MEMORY_2 = "AT+MODE=BOTH M2"
    PRESET_MEMORY_3 = "AT+MODE=BOTH M3"
    PRESET_MEMORY_4 = "AT+MODE=BOTH M4"

    # Presets (save)
    PROGRAM_MEMORY_1 = "AT+SETMODE=BOTH M1"
    PROGRAM_MEMORY_2 = "AT+SETMODE=BOTH M2"
    PROGRAM_MEMORY_3 = "AT+SETMODE=BOTH M3"
    PROGRAM_MEMORY_4 = "AT+SETMODE=BOTH M4"

    # Lights
    LIGHT_ON = "AT+ENABLE=LIGHT"
    LIGHT_OFF = "AT+DISABLE=LIGHT"


class SutaController(BedController):
    """Controller for SUTA Smart Home bed-frame devices."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the SUTA controller."""
        super().__init__(coordinator)
        self._write_char_uuid = SUTA_DEFAULT_WRITE_CHAR_UUID
        self._write_with_response = True
        self._write_mode_initialized = False
        self._light_state = False

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the command characteristic UUID."""
        return self._write_char_uuid

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
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    def _build_command(self, command: str) -> bytes:
        """Build a CRLF-terminated AT command packet."""
        return f"{command}\r\n".encode()

    def _refresh_write_characteristic(self) -> None:
        """Resolve write characteristic and write mode from discovered services."""
        if self._write_mode_initialized:
            return

        client = self.client
        if client is None or client.services is None:
            return

        service = client.services.get_service(SUTA_SERVICE_UUID)
        if service is None:
            _LOGGER.debug(
                "SUTA service %s not found, using fallback characteristic %s",
                SUTA_SERVICE_UUID,
                self._write_char_uuid,
            )
            self._write_mode_initialized = True
            return

        # SUTA devices expose writable characteristics dynamically under
        # SUTA_SERVICE_UUID, so we intentionally select the first writable char
        # we find and store it in _write_char_uuid instead of matching a fixed UUID.
        for char in service.characteristics:
            props = {prop.lower() for prop in char.properties}
            if "write" in props or "write-without-response" in props:
                self._write_char_uuid = str(char.uuid)
                # Prefer write-with-response when available for acknowledgements;
                # otherwise fall back to write-without-response.
                self._write_with_response = "write" in props
                self._write_mode_initialized = True
                _LOGGER.debug(
                    "SUTA write characteristic resolved to %s (response=%s, props=%s)",
                    self._write_char_uuid,
                    self._write_with_response,
                    char.properties,
                )
                return

        _LOGGER.debug(
            "No writable characteristic found in SUTA service %s, using fallback %s",
            SUTA_SERVICE_UUID,
            self._write_char_uuid,
        )
        self._write_mode_initialized = True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a SUTA command packet."""
        self._refresh_write_characteristic()
        await self._write_gatt_with_retry(
            self._write_char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def _send_stop(self) -> None:
        """Send stop command with a fresh cancel event."""
        await self.write_command(
            self._build_command(SutaCommands.STOP_ALL),
            repeat_count=2,
            repeat_delay_ms=100,
            cancel_event=asyncio.Event(),
        )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move upper section up (mapped to BACK for compatibility)."""
        await self.move_back_up()

    async def move_head_down(self) -> None:
        """Move upper section down (mapped to BACK for compatibility)."""
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        """Stop head/back motor movement."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.BACK_UP))

    async def move_back_down(self) -> None:
        """Move back motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.BACK_DOWN))

    async def move_back_stop(self) -> None:
        """Stop back motor movement."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.FOOT_UP))

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.FOOT_DOWN))

    async def move_legs_stop(self) -> None:
        """Stop legs motor movement."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet motor up (same command as legs)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet motor down (same command as legs)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor movement."""
        await self._send_stop()

    async def move_lumbar_up(self) -> None:
        """Move tilt/lumbar motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.TILT_LUMBAR_UP))

    async def move_lumbar_down(self) -> None:
        """Move tilt/lumbar motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.TILT_LUMBAR_DOWN))

    async def move_lumbar_stop(self) -> None:
        """Stop tilt/lumbar motor movement."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motor movement."""
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._preset_with_stop(
            self._build_command(SutaCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: SutaCommands.PRESET_MEMORY_1,
            2: SutaCommands.PRESET_MEMORY_2,
            3: SutaCommands.PRESET_MEMORY_3,
            4: SutaCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self._preset_with_stop(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=150,
            )
        else:
            _LOGGER.warning("SUTA supports memory presets 1-4 only")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: SutaCommands.PROGRAM_MEMORY_1,
            2: SutaCommands.PROGRAM_MEMORY_2,
            3: SutaCommands.PROGRAM_MEMORY_3,
            4: SutaCommands.PROGRAM_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=5,
                repeat_delay_ms=150,
            )
        else:
            _LOGGER.warning("SUTA supports memory presets 1-4 only")

    async def preset_zero_g(self) -> None:
        """Go to zero-g preset."""
        await self._preset_with_stop(
            self._build_command(SutaCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore preset."""
        await self._preset_with_stop(
            self._build_command(SutaCommands.PRESET_ANTI_SNORE),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_tv(self) -> None:
        """Go to TV preset."""
        await self._preset_with_stop(
            self._build_command(SutaCommands.PRESET_TV),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed light and update local light-state tracking."""
        await self.write_command(self._build_command(SutaCommands.LIGHT_ON))
        self._light_state = True

    async def lights_off(self) -> None:
        """Turn off under-bed light and update local light-state tracking."""
        await self.write_command(self._build_command(SutaCommands.LIGHT_OFF))
        self._light_state = False

    async def lights_toggle(self) -> None:
        """Toggle under-bed light using the integration's local light-state flag."""
        if self._light_state:
            await self.lights_off()
        else:
            await self.lights_on()
