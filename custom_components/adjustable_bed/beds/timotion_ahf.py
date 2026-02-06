"""TiMOTION AHF bed controller implementation.

Protocol reverse-engineered from com.timotion.ahf.

Packet format (TX): 11 bytes, no checksum
    [0xDD, 0xDD, 0xFF, group1, group1, group2, group2, 0x00, 0x00, 0x00, 0x00]

Motor groups:
    group1 bits: motor1/motor2/motor3 up/down
    group2 bits: motor4/motor5 up/down, lights, chair mode
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    TIMOTION_AHF_NOTIFY_CHAR_UUID,
    TIMOTION_AHF_SERVICE_UUID,
    TIMOTION_AHF_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class TiMOTIONAhfCommands:
    """TiMOTION AHF command bitmasks."""

    # Group 1 (bytes 3-4): motors 1-3
    MOTOR1_UP = 0x01
    MOTOR1_DOWN = 0x02
    MOTOR2_UP = 0x04
    MOTOR2_DOWN = 0x08
    MOTOR3_UP = 0x10
    MOTOR3_DOWN = 0x20

    # Group 2 (bytes 5-6): motors 4-5 + extra controls
    MOTOR4_UP = 0x01
    MOTOR4_DOWN = 0x02
    MOTOR5_UP = 0x04
    MOTOR5_DOWN = 0x08
    NIGHT_LIGHT_TOGGLE = 0x10
    UNDER_BED_LIGHT_TOGGLE = 0x20
    CHAIR_MODE_TOGGLE = 0x40

    STOP_GROUP1 = 0x00
    STOP_GROUP2 = 0x00


def build_timotion_ahf_command(group1: int = 0, group2: int = 0) -> bytes:
    """Build an 11-byte TiMOTION AHF command packet."""
    return bytes([0xDD, 0xDD, 0xFF, group1, group1, group2, group2, 0x00, 0x00, 0x00, 0x00])


class TiMOTIONAhfController(BedController):
    """Controller for TiMOTION AHF protocol devices."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the TiMOTION AHF controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._write_with_response = False
        self._write_mode_initialized = False
        self._feature_mask = 0
        self._light_state = 0

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the write characteristic UUID."""
        return TIMOTION_AHF_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def has_pillow_support(self) -> bool:
        # Map motor5 to pillow to expose the fifth actuator on 4-motor setups.
        return self._coordinator.motor_count >= 4

    def _refresh_write_mode(self) -> None:
        """Resolve whether writes require response from discovered properties."""
        if self._write_mode_initialized:
            return

        client = self.client
        if client is None or client.services is None:
            return

        service = client.services.get_service(TIMOTION_AHF_SERVICE_UUID)
        if service is None:
            self._write_mode_initialized = True
            return

        for char in service.characteristics:
            if str(char.uuid).lower() != TIMOTION_AHF_WRITE_CHAR_UUID.lower():
                continue

            props = {prop.lower() for prop in char.properties}
            if "write" in props and "write-without-response" not in props:
                self._write_with_response = True
            elif "write-without-response" in props:
                self._write_with_response = False

            _LOGGER.debug(
                "TiMOTION AHF write mode: response=%s (props=%s)",
                self._write_with_response,
                char.properties,
            )
            break

        self._write_mode_initialized = True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write an AHF command packet."""
        self._refresh_write_mode()
        await self._write_gatt_with_retry(
            TIMOTION_AHF_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def _send_stop(self) -> None:
        """Send stop command with fresh cancel context."""
        await self.write_command(
            build_timotion_ahf_command(
                TiMOTIONAhfCommands.STOP_GROUP1,
                TiMOTIONAhfCommands.STOP_GROUP2,
            ),
            repeat_count=3,
            repeat_delay_ms=100,
            cancel_event=asyncio.Event(),
        )

    async def _move_group1(self, bitmask: int) -> None:
        await self._move_with_stop(build_timotion_ahf_command(group1=bitmask))

    async def _move_group2(self, bitmask: int) -> None:
        await self._move_with_stop(build_timotion_ahf_command(group2=bitmask))

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move motor 3 up."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR3_UP)

    async def move_head_down(self) -> None:
        """Move motor 3 down."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR3_DOWN)

    async def move_head_stop(self) -> None:
        """Stop motor movement."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move motor 1 up."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR1_UP)

    async def move_back_down(self) -> None:
        """Move motor 1 down."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR1_DOWN)

    async def move_back_stop(self) -> None:
        """Stop motor movement."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move motor 2 up."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR2_UP)

    async def move_legs_down(self) -> None:
        """Move motor 2 down."""
        await self._move_group1(TiMOTIONAhfCommands.MOTOR2_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop motor movement."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move motor 4 up."""
        await self._move_group2(TiMOTIONAhfCommands.MOTOR4_UP)

    async def move_feet_down(self) -> None:
        """Move motor 4 down."""
        await self._move_group2(TiMOTIONAhfCommands.MOTOR4_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop motor movement."""
        await self._send_stop()

    async def move_pillow_up(self) -> None:
        """Move motor 5 up."""
        await self._move_group2(TiMOTIONAhfCommands.MOTOR5_UP)

    async def move_pillow_down(self) -> None:
        """Move motor 5 down."""
        await self._move_group2(TiMOTIONAhfCommands.MOTOR5_DOWN)

    async def move_pillow_stop(self) -> None:
        """Stop motor movement."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._send_stop()

    # Preset methods (not supported by this protocol)
    async def preset_flat(self) -> None:
        _LOGGER.warning("TiMOTION AHF does not support flat preset commands")

    async def preset_memory(self, memory_num: int) -> None:
        _LOGGER.warning("TiMOTION AHF does not support memory presets (requested: %d)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        _LOGGER.warning(
            "TiMOTION AHF does not support memory programming (requested: %d)",
            memory_num,
        )

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(
            build_timotion_ahf_command(group2=TiMOTIONAhfCommands.UNDER_BED_LIGHT_TOGGLE),
            repeat_count=2,
            repeat_delay_ms=100,
        )

    async def lights_on(self) -> None:
        """Toggle light state (protocol has no discrete ON command)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Toggle light state (protocol has no discrete OFF command)."""
        await self.lights_toggle()

    def _is_valid_notification(self, data: bytes) -> bool:
        """Validate 15-byte AHF status notifications."""
        if len(data) != 15 or data[0] != 0x9D:
            return False

        checksum = sum(data[2:14]) & 0x7F
        return checksum == data[14]

    def _handle_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle status notifications from the bed."""
        raw = bytes(data)
        self.forward_raw_notification(TIMOTION_AHF_NOTIFY_CHAR_UUID, raw)

        if not self._is_valid_notification(raw):
            return

        # Byte 2: feature lock mask, Byte 3: light state (0=off, 1=white, 2=green, 3=red)
        self._feature_mask = raw[2]
        self._light_state = raw[3]
        _LOGGER.debug(
            "TiMOTION AHF status: feature_mask=0x%02X light_state=%d",
            self._feature_mask,
            self._light_state,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for AHF notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.start_notify(TIMOTION_AHF_NOTIFY_CHAR_UUID, self._handle_notification)
        except BleakError as err:
            _LOGGER.debug("Failed to start TiMOTION AHF notifications: %s", err)

    async def stop_notify(self) -> None:
        """Stop AHF notifications."""
        self._notify_callback = None
        if self.client is None or not self.client.is_connected:
            return

        with contextlib.suppress(BleakError):
            await self.client.stop_notify(TIMOTION_AHF_NOTIFY_CHAR_UUID)
