"""Legacy Limoss / Stawett route over the Limoss DD codec.

Reverse engineered from com.limoss.limossremote and com.stawett before their
audits. The capability reply sets the motor and memory counts, motor positions
come back as 32-bit raw values, and memories are kept locally as raw positions.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..codec import limoss as codec
from ..const import LIMOSS_CHAR_UUID, LIMOSS_SERVICE_UUID
from ..profiles.limoss import LEGACY
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_POSITION_QUERY_GAP = 0.03
_CAPABILITY_TIMEOUT = 2.0
_DEFAULT_MAX_RAW_ESTIMATE: dict[str, int] = {
    "back": 16000,
    "legs": 12000,
    "head": 16000,
    "feet": 12000,
}
_MAX_ESTIMATE_SHRINK_TRIGGER_RATIO = 0.7
_MAX_ESTIMATE_SHRINK_STREAK = 6
_MAX_ESTIMATE_SHRINK_DECAY = 0.9
_MAX_ESTIMATE_MIN_SHRINK_SAMPLE = 500

# Motor index (1-4) of each named position.
MOTORS: dict[str, int] = {"back": 1, "legs": 2, "head": 3, "feet": 4}
POSITION_MAP: dict[int, str] = {index * 0x10: name for name, index in MOTORS.items()}


class LimossController(BedController):
    """Controller for the legacy Limoss / Stawett route."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the controller."""
        super().__init__(coordinator)
        self.profile = LEGACY
        self._notify_callback: Callable[[str, float], None] | None = None
        self._write_with_response: bool = True
        self._counter: int = 0
        self._capabilities_received: asyncio.Event | None = None
        self._memory_slot_count: int = 0
        self._reported_motor_count: int | None = None
        self._last_positions_raw: dict[str, int] = {}
        self._memory_positions: dict[int, dict[str, int]] = {}
        self._vibration_count: int = 0
        # Position normalization state (raw 32-bit samples -> estimated angles).
        self._max_raw_estimate: dict[str, int] = _DEFAULT_MAX_RAW_ESTIMATE.copy()
        self._low_sample_streak: dict[str, int] = dict.fromkeys(_DEFAULT_MAX_RAW_ESTIMATE, 0)

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LIMOSS_CHAR_UUID

    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Limoss supports a flat movement command."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return reported memory slot count (fallback: 0)."""
        return self._memory_slot_count if self._memory_slot_count > 0 else 0

    def reset_max_raw_estimate(self) -> None:
        """Reset raw-position normalization estimates.

        Called by the coordinator on connection/reconnection to avoid carrying
        stale calibration state across sessions.
        """
        self._max_raw_estimate = _DEFAULT_MAX_RAW_ESTIMATE.copy()
        self._low_sample_streak = dict.fromkeys(_DEFAULT_MAX_RAW_ESTIMATE, 0)
        _LOGGER.debug(
            "Reset Limoss max raw position estimates for %s",
            self._coordinator.address,
        )

    def _next_counter(self) -> int:
        """Return the current sequence counter and increment it."""
        value = self._counter
        self._counter = (self._counter + 1) & 0xFF
        return value

    def _raw_to_angle(self, raw_value: int, motor: str) -> float:
        """Convert raw Limoss 32-bit position value to an estimated angle."""
        current_max = self._max_raw_estimate.get(motor, 16000)
        if raw_value > current_max:
            current_max = raw_value
            self._max_raw_estimate[motor] = raw_value
            self._low_sample_streak[motor] = 0
        else:
            current_max = self._maybe_shrink_max_raw_estimate(
                motor=motor,
                raw_value=raw_value,
                current_max=current_max,
            )

        if current_max <= 0:
            return 0.0

        percent = min(100.0, max(0.0, (raw_value / current_max) * 100.0))
        max_angle = self._coordinator.get_max_angle(motor)
        return (percent / 100.0) * max_angle

    def _maybe_shrink_max_raw_estimate(
        self,
        motor: str,
        raw_value: int,
        current_max: int,
    ) -> int:
        """Shrink overestimated max-raw values after repeated low samples."""
        if current_max <= 0:
            return current_max

        if (
            raw_value >= _MAX_ESTIMATE_MIN_SHRINK_SAMPLE
            and raw_value < (current_max * _MAX_ESTIMATE_SHRINK_TRIGGER_RATIO)
        ):
            streak = self._low_sample_streak.get(motor, 0) + 1
            self._low_sample_streak[motor] = streak

            if streak >= _MAX_ESTIMATE_SHRINK_STREAK:
                previous_max = current_max
                shrunk_max = max(
                    int(current_max * _MAX_ESTIMATE_SHRINK_DECAY),
                    1,
                )
                if shrunk_max < current_max:
                    self._max_raw_estimate[motor] = shrunk_max
                    current_max = shrunk_max
                    _LOGGER.info(
                        "Shrank Limoss max raw estimate for %s on %s: %d -> %d (streak=%d)",
                        motor,
                        self._coordinator.address,
                        previous_max,
                        shrunk_max,
                        streak,
                    )

                self._low_sample_streak[motor] = 0
        else:
            self._low_sample_streak[motor] = 0

        return current_max

    def _effective_motor_count(self) -> int:
        """Return the best available motor count for runtime command routing."""
        if self._reported_motor_count is not None:
            return max(2, min(4, self._reported_motor_count))
        return max(2, min(4, self._coordinator.motor_count))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed.

        Accepts a five-byte body, framed with the next counter value, or a
        prebuilt ten-byte frame. Repeats resend the same frame.
        """
        if len(command) == 5:
            packet = codec.frame(command, self._next_counter())
        elif len(command) == 10 and command[0] == 0xDD:
            packet = command
        else:
            raise ValueError("Limoss command must be 5-byte payload or 10-byte encrypted packet")

        _LOGGER.debug(
            "Writing Limoss packet: %s (repeat=%d, delay=%dms, response=%s)",
            packet.hex(),
            repeat_count,
            repeat_delay_ms,
            self._write_with_response,
        )

        await self._write_gatt_with_retry(
            LIMOSS_CHAR_UUID,
            packet,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    def _handle_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle Limoss notification packets."""
        raw = bytes(data)
        self.forward_raw_notification(LIMOSS_CHAR_UUID, raw)
        decoded = codec.decode(raw[:10])
        if decoded is None:
            _LOGGER.debug("Ignoring invalid Limoss frame: %s", raw.hex())
            return

        cmd, params = decoded[0], decoded[1:]

        if cmd == codec.QUERY_CAPABILITIES:
            button_count = params[0]
            system_type = params[1]
            vibration_count = params[2]
            main_and_memory = params[3]
            motor_count = system_type & 0x0F
            memory_count = main_and_memory & 0x0F

            self._reported_motor_count = motor_count if motor_count > 0 else None
            self._memory_slot_count = memory_count
            self._vibration_count = vibration_count

            _LOGGER.info(
                "Limoss capabilities: buttons=%d motors=%d vibration=%d memory=%d",
                button_count,
                motor_count,
                vibration_count,
                memory_count,
            )

            if self._capabilities_received is not None:
                self._capabilities_received.set()
            return

        position_key = POSITION_MAP.get(cmd)
        if position_key is None:
            return

        raw_position = int.from_bytes(params, byteorder="big", signed=False)
        self._last_positions_raw[position_key] = raw_position
        angle = self._raw_to_angle(raw_position, position_key)

        _LOGGER.debug(
            "Limoss position update: %s raw=%d estimated=%.1f",
            position_key,
            raw_position,
            angle,
        )

        if self._notify_callback is not None:
            self._notify_callback(position_key, angle)

    async def _query_capabilities(self) -> None:
        """Query runtime capabilities from the controller."""
        if self.client is None or not self.client.is_connected:
            return

        self._capabilities_received = asyncio.Event()
        try:
            await self.write_command(codec.query(codec.QUERY_CAPABILITIES))
            await asyncio.wait_for(self._capabilities_received.wait(), _CAPABILITY_TIMEOUT)
        except TimeoutError:
            _LOGGER.debug("Timed out waiting for Limoss capability response")
        finally:
            self._capabilities_received = None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start Limoss notifications: not connected")
            return

        # Prefer write-with-response when available, fallback to write-without-response.
        if self.client.services is not None:
            service = self.client.services.get_service(LIMOSS_SERVICE_UUID)
            if service is not None:
                char = service.get_characteristic(LIMOSS_CHAR_UUID)
                if char is not None:
                    props = {prop.lower() for prop in char.properties}
                    if "write" in props:
                        self._write_with_response = True
                    elif "write-without-response" in props:
                        self._write_with_response = False
                    _LOGGER.debug(
                        "Limoss GATT write properties for %s: %s (write_with_response=%s)",
                        self._coordinator.address,
                        sorted(props),
                        self._write_with_response,
                    )

        await self.client.start_notify(LIMOSS_CHAR_UUID, self._handle_notification)
        _LOGGER.info("Started Limoss notifications")

        await self._query_capabilities()

        if callback is not None:
            await self.read_positions()

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        self._notify_callback = None
        if self.client is None or not self.client.is_connected:
            return

        with contextlib.suppress(BleakError):
            await self.client.stop_notify(LIMOSS_CHAR_UUID)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Query current motor positions; the replies arrive as notifications.

        A reported motor count overrides ``motor_count``; either is clamped to 2-4.
        """
        if self.client is None or not self.client.is_connected:
            return

        effective_motor_count = motor_count
        if self._reported_motor_count is not None:
            effective_motor_count = self._reported_motor_count

        for index in range(1, max(2, min(4, effective_motor_count)) + 1):
            await self.write_command(codec.ask_position(index))
            await asyncio.sleep(_POSITION_QUERY_GAP)

    async def _send_stop(self) -> None:
        """Send STOP with a fresh cancel event."""
        stop = self.profile.stop
        await self.write_command(
            codec.body(stop.opcode), repeat_count=stop.frames, cancel_event=asyncio.Event()
        )

    async def _move_with_stop(self, opcode: int) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Send a hold-style movement command and then stop."""
        try:
            await self.write_command(
                codec.body(opcode),
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
        finally:
            with contextlib.suppress(BleakError, ConnectionError):
                await self._send_stop()

    # Motor control methods. Head is motor 3 on 3+ motor beds, else motor 1;
    # feet is motor 4 on 4-motor beds, else motor 2.
    async def move_head_up(self) -> None:
        await self._move_with_stop(codec.motor(3 if self._effective_motor_count() >= 3 else 1, True))

    async def move_head_down(self) -> None:
        await self._move_with_stop(codec.motor(3 if self._effective_motor_count() >= 3 else 1, False))

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self._move_with_stop(codec.motor(1, True))

    async def move_back_down(self) -> None:
        await self._move_with_stop(codec.motor(1, False))

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(codec.motor(2, True))

    async def move_legs_down(self) -> None:
        await self._move_with_stop(codec.motor(2, False))

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(codec.motor(4 if self._effective_motor_count() >= 4 else 2, True))

    async def move_feet_down(self) -> None:
        await self._move_with_stop(codec.motor(4 if self._effective_motor_count() >= 4 else 2, False))

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Send both-down movement command and then stop."""
        await self._move_with_stop(codec.FLAT)

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if positions have been saved to recall."""
        return len(self._memory_positions) > 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Limoss supports saving positions via SetPos."""
        return True

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a saved memory by sending each motor's stored raw position."""
        positions = self._memory_positions.get(memory_num)
        if not positions:
            _LOGGER.warning("No positions saved in Limoss memory slot %d (save first)", memory_num)
            return

        for motor_name, raw_pos in positions.items():
            index = MOTORS.get(motor_name)
            if index is None:
                continue
            await self.write_command(codec.set_position(index, raw_pos, signed=False))
            await asyncio.sleep(self.profile.recall_ms / 1000)

    async def program_memory(self, memory_num: int) -> None:
        """Save current motor positions to a memory slot."""
        if not self._last_positions_raw:
            _LOGGER.warning(
                "No position data available to save to Limoss memory slot %d", memory_num
            )
            return
        self._memory_positions[memory_num] = dict(self._last_positions_raw)
        _LOGGER.info(
            "Saved Limoss positions to memory slot %d: %s",
            memory_num,
            self._memory_positions[memory_num],
        )

    # Massage/vibration methods
    async def massage_toggle(self) -> None:
        """Toggle vibration zone 1."""
        await self.write_command(codec.body(codec.MASSAGE_ZONES[0]))

    async def massage_zone(self, zone: int) -> None:
        """Toggle a specific vibration zone (1-6)."""
        if (opcode := dict(enumerate(codec.MASSAGE_ZONES, 1)).get(zone)) is not None:
            await self.write_command(codec.body(opcode))
        else:
            _LOGGER.warning("Invalid Limoss vibration zone: %d (valid: 1-6)", zone)

    @property
    def supports_lights(self) -> bool:
        """Return True - Limoss supports a light toggle command."""
        return True

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(codec.body(codec.LIGHT))
