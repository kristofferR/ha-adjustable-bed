"""Sleepy's Elite BOX25 Star controller implementation.

Reverse-engineered from the Sleepy's Elite app (com.okin.bedding.sleepy)
for the DewertOkin BOX25 Star controller using Nordic UART Service.

Protocol: BOX25 Star (NUS-based, multi-subsystem)
BLE Name: Star*
Service: Nordic UART (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
Write:   TX characteristic (6e400002)
Notify:  RX characteristic (6e400003)

The BOX25 protocol uses a two-track initialization system:
- Motor/preset commands require CMD_MOTOR_INIT (0x00 0xD0)
- Massage/light commands require CMD_MASSAGE_LIGHT_INIT (0x00 0xB0)
Both tracks require a wake command (0x5A 0x0B 0x00 0xA5) first.

Command formats:
- Motor/Preset: 05 02 [b2] [b3] [b4] [b5] [b6] (7 bytes)
- Position:     03 F0 [zone] [pos 0-100] 00 (5 bytes)
- Lighting:     04 E0 [sub] [val] 00 00 (6 bytes)
- Vibration:    04 E0 06 [head 0-8] [foot 0-8] 00 (6 bytes)
- Massage:      08 02 [hAdd] [hRed] [fAdd] [fRed] [allFlags] [mode] [timer] 00 (10 bytes)

Ported from ha-dewertokin-bed standalone integration.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NORDIC_UART_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Valid massage mode flags (byte 7 of massage command)
_MASSAGE_MODES = (0x08, 0x10, 0x20)  # wave1, wave2, wave3


class Box25Commands:
    """BOX25 Star protocol command constants."""

    # ─── Initialization ──────────────────────────────────────────────────
    WAKE = bytes([0x5A, 0x0B, 0x00, 0xA5])
    MOTOR_INIT = bytes([0x00, 0xD0])
    MASSAGE_LIGHT_INIT = bytes([0x00, 0xB0])

    # ─── Motor / Preset (05 02 prefix, 7 bytes) ─────────────────────────
    MOTOR_STOP = bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])

    # Directional motor control
    HEAD_UP = bytes([0x05, 0x02, 0x00, 0x01, 0x00, 0x00, 0x00])
    HEAD_DOWN = bytes([0x05, 0x02, 0x00, 0x02, 0x00, 0x00, 0x00])
    FOOT_UP = bytes([0x05, 0x02, 0x00, 0x04, 0x00, 0x00, 0x00])
    FOOT_DOWN = bytes([0x05, 0x02, 0x00, 0x08, 0x00, 0x00, 0x00])
    LUMBAR_UP = bytes([0x05, 0x02, 0x00, 0x10, 0x00, 0x00, 0x00])
    LUMBAR_DOWN = bytes([0x05, 0x02, 0x00, 0x20, 0x00, 0x00, 0x00])
    NECK_TILT_UP = bytes([0x05, 0x02, 0x00, 0x40, 0x00, 0x00, 0x00])
    NECK_TILT_DOWN = bytes([0x05, 0x02, 0x00, 0x80, 0x00, 0x00, 0x00])

    # Presets (send command, then MOTOR_STOP to confirm)
    PRESET_FLAT = bytes([0x05, 0x02, 0x08, 0x00, 0x00, 0x00, 0x00])
    PRESET_ZERO_GRAVITY = bytes([0x05, 0x02, 0x00, 0x00, 0x10, 0x00, 0x00])
    PRESET_ANTI_SNORE = bytes([0x05, 0x02, 0x00, 0x00, 0x80, 0x00, 0x00])
    PRESET_LOUNGE = bytes([0x05, 0x02, 0x00, 0x00, 0x20, 0x00, 0x00])  # "Relax"

    # Memory recall (4 slots)
    MEMORY_RECALL_1 = bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00])
    MEMORY_RECALL_2 = bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x02, 0x00])
    MEMORY_RECALL_3 = bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x04, 0x00])
    MEMORY_RECALL_4 = bytes([0x05, 0x02, 0x00, 0x00, 0x00, 0x08, 0x00])

    # Memory store (4 slots)
    MEMORY_STORE_1 = bytes([0x05, 0x02, 0x00, 0x00, 0x01, 0x00, 0x00])
    MEMORY_STORE_2 = bytes([0x05, 0x02, 0x00, 0x00, 0x02, 0x00, 0x00])
    MEMORY_STORE_3 = bytes([0x05, 0x02, 0x00, 0x00, 0x04, 0x00, 0x00])
    MEMORY_STORE_4 = bytes([0x05, 0x02, 0x00, 0x00, 0x08, 0x00, 0x00])

    MEMORY_RECALL = {
        1: MEMORY_RECALL_1,
        2: MEMORY_RECALL_2,
        3: MEMORY_RECALL_3,
        4: MEMORY_RECALL_4,
    }

    MEMORY_STORE = {
        1: MEMORY_STORE_1,
        2: MEMORY_STORE_2,
        3: MEMORY_STORE_3,
        4: MEMORY_STORE_4,
    }

    # ─── Lighting (04 E0 prefix, 6 bytes) ────────────────────────────────
    LIGHT_OFF = bytes([0x04, 0xE0, 0x01, 0x00, 0x00, 0x00])
    LIGHT_ON_WHITE = bytes([0x04, 0xE0, 0x01, 0x01, 0x00, 0x00])

    # ─── Massage exit ────────────────────────────────────────────────────
    MASSAGE_EXIT = bytes([0x05, 0x02, 0x02, 0x00, 0x00, 0x00, 0x00])

    # ─── Massage mode commands (08 02 prefix, 10 bytes) ──────────────────
    MASSAGE_WAVE1 = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00])
    MASSAGE_WAVE2 = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00])
    MASSAGE_WAVE3 = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x00, 0x00])


# Timing constants (seconds)
_WAKE_DELAY = 0.15
_INIT_DELAY = 0.08
_COMMAND_DELAY = 0.05


class SleepysBox25Controller(BedController):
    """Controller for Sleepy's Elite BOX25 Star beds.

    Uses Nordic UART Service with a two-track initialization system:
    motor commands require 0xD0 init, massage/light commands require 0xB0 init.
    Both tracks need a wake command (5A 0B 00 A5) sent first.

    Presets use a send-then-confirm pattern: send preset command, then
    send MOTOR_STOP to trigger execution.
    """

    # Position feedback: head/feet/lumbar at 0-100 percentage
    _HEAD_MAX_ANGLE: float = 100.0
    _FEET_MAX_ANGLE: float = 100.0
    _LUMBAR_MAX_ANGLE: float = 100.0

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the BOX25 Star controller."""
        super().__init__(coordinator)
        self._motor_initialized = False
        self._massage_initialized = False
        self._head_position: float | None = None
        self._foot_position: float | None = None
        self._lumbar_position: float | None = None
        self._is_moving = False
        self._massage_active = False
        self._massage_mode_index = 0  # Index into _MASSAGE_MODES

    # ─── BLE Properties ──────────────────────────────────────────────────

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the Nordic UART TX characteristic UUID."""
        return NORDIC_UART_WRITE_CHAR_UUID

    # ─── Capability Properties ───────────────────────────────────────────

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
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_neck_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_position_feedback(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return True

    # ─── Init / Write Helpers ────────────────────────────────────────────

    async def _ensure_wake(self) -> None:
        """Send wake command to ensure the controller is responsive."""
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            Box25Commands.WAKE,
        )
        await asyncio.sleep(_WAKE_DELAY)

    async def _ensure_motor_init(self) -> None:
        """Ensure motor subsystem is initialized.

        Sets the init flag only after the write succeeds. If the write
        raises or is cancelled, the flag stays False so the next call
        retries the handshake.
        """
        if not self._motor_initialized:
            await self._ensure_wake()
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                Box25Commands.MOTOR_INIT,
            )
            await asyncio.sleep(_INIT_DELAY)
            self._motor_initialized = True

    async def _ensure_massage_light_init(self) -> None:
        """Ensure massage/light subsystem is initialized.

        Sets the init flag only after the write succeeds. If the write
        raises or is cancelled, the flag stays False so the next call
        retries the handshake.
        """
        if not self._massage_initialized:
            await self._ensure_wake()
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                Box25Commands.MASSAGE_LIGHT_INIT,
            )
            await asyncio.sleep(_INIT_DELAY)
            self._massage_initialized = True

    async def _write_motor_command(self, command: bytes) -> None:
        """Write a motor/preset command with motor init."""
        await self._ensure_motor_init()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
        )

    async def _write_massage_light_command(self, command: bytes) -> None:
        """Write a massage/light command with massage/light init."""
        await self._ensure_massage_light_init()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a motor command with init sequence."""
        await self._ensure_motor_init()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    # ─── Notification Handling ───────────────────────────────────────────

    def _on_notification(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle BLE notification data from the bed."""
        raw = bytes(data)
        self.forward_raw_notification(characteristic.uuid, raw)

        if len(raw) < 2:
            return

        length = len(raw)

        # Motor/movement status (7+ bytes with 05 prefix)
        if length >= 7 and raw[0] == 0x05:
            self._is_moving = any(b != 0 for b in raw[2:7])

        # Position report (4+ bytes with 03 prefix)
        elif length >= 4 and raw[0] == 0x03:
            zone = raw[1]
            position = raw[2]
            if 0 <= position <= 100:
                if zone == 0x00:
                    self._head_position = float(position)
                    if self._notify_callback:
                        self._notify_callback("head", float(position))
                elif zone == 0x01:
                    self._foot_position = float(position)
                    if self._notify_callback:
                        self._notify_callback("feet", float(position))
                elif zone == 0x02:
                    self._lumbar_position = float(position)
                    # No standard callback key for lumbar in BedController;
                    # store locally for future use

        # Massage mode response (10 bytes with 08 prefix)
        elif length >= 8 and raw[0] == 0x08:
            mode_byte = raw[7]
            self._massage_active = mode_byte != 0
            # Track current mode index for cycling
            if mode_byte in _MASSAGE_MODES:
                self._massage_mode_index = _MASSAGE_MODES.index(mode_byte)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications via Nordic UART RX."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            await client.start_notify(
                NORDIC_UART_READ_CHAR_UUID, self._on_notification
            )
            _LOGGER.debug("Subscribed to BOX25 notifications")
        except BleakError:
            _LOGGER.warning("Could not subscribe to BOX25 notifications")

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        self._notify_callback = None
        client = self.client
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
            except BleakError:
                pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Positions are pushed via notifications, no polling needed."""

    # ─── Direct Position Control ─────────────────────────────────────────

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor to a specific position (0-100)."""
        zone_map = {"head": 0x00, "back": 0x00, "feet": 0x01, "legs": 0x01}
        zone = zone_map.get(motor)
        if zone is None:
            raise ValueError(f"Unknown motor: {motor}")

        pos = max(0, min(100, int(position)))
        cmd = bytes([0x03, 0xF0, zone, pos, 0x00])
        await self._write_motor_command(cmd)

    def angle_to_native_position(self, motor: str, angle: float) -> int:  # noqa: ARG002
        """Convert angle to position (0-100 percentage-based)."""
        return int(max(0, min(100, angle)))

    # ─── Motor Control ───────────────────────────────────────────────────

    async def _send_stop(self) -> None:
        """Send motor stop command with a fresh cancel event."""
        stop_event = asyncio.Event()
        await self.write_command(Box25Commands.MOTOR_STOP, cancel_event=stop_event)

    async def move_head_up(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_UP)

    async def move_head_down(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_UP)

    async def move_back_down(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_UP)

    async def move_legs_down(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_UP)

    async def move_feet_down(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # ─── Lumbar Motor ────────────────────────────────────────────────────

    async def move_lumbar_up(self) -> None:
        await self._move_with_stop(Box25Commands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        await self._move_with_stop(Box25Commands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    # ─── Neck Motor ──────────────────────────────────────────────────────

    async def move_neck_up(self) -> None:
        await self._move_with_stop(Box25Commands.NECK_TILT_UP)

    async def move_neck_down(self) -> None:
        await self._move_with_stop(Box25Commands.NECK_TILT_DOWN)

    async def move_neck_stop(self) -> None:
        await self._send_stop()

    # ─── Presets ─────────────────────────────────────────────────────────

    async def _send_preset(self, preset_cmd: bytes) -> None:
        """Send a preset command with the required confirm-with-stop pattern."""
        await self._write_motor_command(preset_cmd)
        await asyncio.sleep(_COMMAND_DELAY)
        await self._write_motor_command(Box25Commands.MOTOR_STOP)

    async def preset_flat(self) -> None:
        await self._send_preset(Box25Commands.PRESET_FLAT)

    async def preset_zero_g(self) -> None:
        await self._send_preset(Box25Commands.PRESET_ZERO_GRAVITY)

    async def preset_anti_snore(self) -> None:
        await self._send_preset(Box25Commands.PRESET_ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Move bed to lounge/relax position."""
        await self._send_preset(Box25Commands.PRESET_LOUNGE)

    async def preset_memory(self, memory_num: int) -> None:
        cmd = Box25Commands.MEMORY_RECALL.get(memory_num)
        if cmd is None:
            _LOGGER.warning("Invalid memory slot %d (valid: 1-4)", memory_num)
            return
        await self._send_preset(cmd)

    async def program_memory(self, memory_num: int) -> None:
        cmd = Box25Commands.MEMORY_STORE.get(memory_num)
        if cmd is None:
            _LOGGER.warning("Invalid memory slot %d (valid: 1-4)", memory_num)
            return
        await self._write_motor_command(cmd)
        await asyncio.sleep(_COMMAND_DELAY)
        await self._write_motor_command(Box25Commands.MOTOR_STOP)

    # ─── Lights ──────────────────────────────────────────────────────────

    async def lights_on(self) -> None:
        await self._write_massage_light_command(Box25Commands.LIGHT_ON_WHITE)

    async def lights_off(self) -> None:
        await self._write_massage_light_command(Box25Commands.LIGHT_OFF)

    async def lights_toggle(self) -> None:
        # No toggle command in protocol; default to on
        await self.lights_on()

    # ─── Massage ─────────────────────────────────────────────────────────

    async def massage_off(self) -> None:
        """Exit massage mode."""
        self._massage_active = False
        await self._write_motor_command(Box25Commands.MASSAGE_EXIT)

    async def massage_toggle(self) -> None:
        """Toggle massage: start wave_1 if off, exit if on."""
        if self._massage_active:
            await self.massage_off()
        else:
            self._massage_active = True
            self._massage_mode_index = 0
            await self._write_massage_light_command(Box25Commands.MASSAGE_WAVE1)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity (both zones)."""
        cmd = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity (both zones)."""
        cmd = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_head_up(self) -> None:
        cmd = bytes([0x08, 0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_head_down(self) -> None:
        cmd = bytes([0x08, 0x02, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_foot_up(self) -> None:
        cmd = bytes([0x08, 0x02, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_foot_down(self) -> None:
        cmd = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
        await self._write_massage_light_command(cmd)

    async def massage_mode_step(self) -> None:
        """Cycle through massage wave modes (wave1 → wave2 → wave3 → wave1)."""
        self._massage_mode_index = (self._massage_mode_index + 1) % len(_MASSAGE_MODES)
        mode_flag = _MASSAGE_MODES[self._massage_mode_index]
        cmd = bytes([0x08, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, mode_flag, 0x00, 0x00])
        await self._write_massage_light_command(cmd)
