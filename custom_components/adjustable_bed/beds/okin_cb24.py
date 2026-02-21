"""Okin CB24 protocol bed controller implementation.

Protocol reverse-engineered from SmartBed by Okin app (com.okin.bedding.smartbedwifi).
Source: disassembly/output/com.okin.bedding.smartbedwifi/ANALYSIS.md

This controller handles beds using the CB24 protocol over Nordic UART service.
Known brands using this protocol:
- SmartBed by Okin (Amada, and other OKIN-based beds)
- CB24, CB24AB, CB27, CB27New, CB1221, Dacheng profiles

Detection: Manufacturer ID 89 (OKIN Automotive)

Commands follow the format: [0x05, 0x02, cmd3, cmd2, cmd1, cmd0, bed_selection]
- Bytes 0-1: Length and type (0x05, 0x02)
- Bytes 2-5: 32-bit command in big-endian order
- Byte 6: Bed selection (0x00=default, 0xAA=bed A, 0xBB=bed B)

The 32-bit command values are identical to LeggettOkin protocol.

Protocol families detected from the OEM SmartBed app:
- NEW protocol (CB27New / CBNewProtocol): uses 0x2A/0xAA packet families.
- OLD protocol (CB24/CB27/CB24AB/CB1221/Dacheng): uses 0x05 0x02 packets.

Preset behavior in this integration:
- NEW protocol profiles use one-shot presets.
- Legacy profiles (`cb24`, `cb27`, `cb24_ab`, `cb1221`, `dacheng`) use one-shot
  presets (matching v2.4.0 behavior that worked on known hardware).
- `cb_old` compatibility variant uses continuous presets at 300ms and sends
  STOP after completion.
- Auto-detected legacy profiles can promote to continuous preset mode when the
  same preset is retried repeatedly in a short window, avoiding manual profile
  changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIN_CB24_VARIANT_CB24,
    OKIN_CB24_VARIANT_CB24_AB,
    OKIN_CB24_VARIANT_CB27,
    OKIN_CB24_VARIANT_CB27NEW,
    OKIN_CB24_VARIANT_CB1221,
    OKIN_CB24_VARIANT_DACHENG,
    OKIN_CB24_VARIANT_NEW,
    OKIN_CB24_VARIANT_OLD,
)
from .base import BedController
from .okin_protocol import int_to_bytes

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Legacy continuous preset timing for the `cb_old` compatibility variant.
# The OEM app sends continuously at 300ms intervals; the actuator moves
# incrementally per command.  55 repeats ≈ 16.5s covers typical full-travel
# preset recalls.  The cancel-event mechanism allows early interruption.
_PRESET_CONTINUOUS_COUNT = 55
_PRESET_CONTINUOUS_DELAY_MS = 300
_ADAPTIVE_PRESET_RETRY_WINDOW_SECONDS = 12.0
_ADAPTIVE_PRESET_PROMOTION_RETRY_COUNT = 2

# Device profile variants grouped by protocol and preset behavior.
_LEGACY_PROTOCOL_VARIANTS = frozenset(
    {
        OKIN_CB24_VARIANT_OLD,
        OKIN_CB24_VARIANT_CB24,
        OKIN_CB24_VARIANT_CB27,
        OKIN_CB24_VARIANT_CB24_AB,
        OKIN_CB24_VARIANT_CB1221,
        OKIN_CB24_VARIANT_DACHENG,
    }
)
_NEW_PROTOCOL_VARIANTS = frozenset({OKIN_CB24_VARIANT_NEW, OKIN_CB24_VARIANT_CB27NEW})
_CONTINUOUS_PRESET_VARIANTS = frozenset({OKIN_CB24_VARIANT_OLD})

# CBNewProtocol memory command mapping (CB24 integer command -> memory index).
_CBNEW_MEMORY_BY_COMMAND: dict[int, int] = {
    0x08000000: 9,  # Flat
    0x00001000: 1,  # Zero-G
    0x00002000: 2,  # Memory 1 / Lounge
    0x00004000: 3,  # Memory 2 / TV
    0x00008000: 4,  # Anti-snore
    0x00010000: 5,  # Memory 3
}


class OkinCB24Commands:
    """Okin CB24 command constants (32-bit values).

    These are the same command values used by LeggettOkin, CB24, and related protocols.
    The CB24 protocol uses a 7-byte format with bed selection byte.
    """

    # Presets
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000  # Also known as Lounge
    PRESET_MEMORY_2 = 0x4000  # Also known as TV/PC
    PRESET_ANTI_SNORE = 0x8000
    PRESET_MEMORY_3 = 0x10000

    # Motor controls
    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_BOTH_UP = 0x5  # HEAD_UP + FEET_UP
    MOTOR_BOTH_DOWN = 0xA  # HEAD_DOWN + FEET_DOWN
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_WAIST_UP = 0x40
    MOTOR_WAIST_DOWN = 0x80

    # Lights
    TOGGLE_LIGHTS = 0x20000

    # Stretch/other
    STRETCH_MOVE = 0x40000

    # Massage - intensity control (up = increase, minus = decrease)
    MASSAGE_HEAD_UP = 0x800  # Increase head massage intensity
    MASSAGE_HEAD_DOWN = 0x800000  # Decrease head massage intensity
    MASSAGE_FEET_UP = 0x400  # Increase foot massage intensity
    MASSAGE_FEET_DOWN = 0x1000000  # Decrease foot massage intensity
    MASSAGE_WAIST_UP = 0x400000  # Increase waist massage intensity
    MASSAGE_WAIST_DOWN = 0x10000000  # Decrease waist massage intensity

    # Massage - global controls
    MASSAGE_ALL_TOGGLE = 0x100  # Toggle all massage zones
    MASSAGE_ON_OFF = 0x4000000  # Master massage on/off toggle
    MASSAGE_STOP_ALL = 0x2000000  # Stop all massage

    # Massage - mode and timer
    MASSAGE_WAVE_STEP = 0x10000000  # Cycle through wave patterns
    MASSAGE_TIMER_UP = 0x200  # Increase massage timer
    MASSAGE_TIMER_DOWN = 0x100000  # Decrease massage timer

    # Massage - intensity levels (direct set)
    MASSAGE_INTENSITY_UP = 0xC00  # Increase overall intensity
    MASSAGE_INTENSITY_DOWN = 0x1800000  # Decrease overall intensity


class MotorDirection(Enum):
    """Direction for motor movement."""

    UP = "up"
    DOWN = "down"
    STOP = "stop"


def build_cb24_command(command_value: int, bed_selection: int = 0x00) -> bytes:
    """Build a 7-byte CB24 protocol command.

    Args:
        command_value: 32-bit integer representing the command
        bed_selection: Bed selection byte (0x00=default, 0xAA=bed A, 0xBB=bed B)

    Returns:
        7-byte command: [0x05, 0x02, cmd3, cmd2, cmd1, cmd0, bed_selection]
    """
    return bytes([0x05, 0x02, *int_to_bytes(command_value), bed_selection])


def build_cbnew_motor_command(command_value: int) -> bytes:
    """Build CBNewProtocol motor command ([0x2A, 0x00, 0x00, 0x01, 0x01, 0x04, ...])."""
    return bytes(
        [
            0x2A,
            0x00,
            0x00,
            0x01,
            0x01,
            0x04,
            command_value & 0xFF,
            (command_value >> 8) & 0xFF,
            (command_value >> 16) & 0xFF,
            (command_value >> 24) & 0xFF,
        ]
    )


def build_cbnew_memory_command(memory_index: int) -> bytes:
    """Build CBNewProtocol memory command ([0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, idx])."""
    return bytes([0x2A, 0x00, 0x00, 0x01, 0x03, 0x01, memory_index & 0xFF])


def build_cbnew_stop_command() -> bytes:
    """Build CBNewProtocol stop command ([0xAA, 0x00, 0x00, 0x01, 0x02, 0x00])."""
    return bytes([0xAA, 0x00, 0x00, 0x01, 0x02, 0x00])


def build_cbnew_massage_command(command_code: int) -> bytes:
    """Build CBNewProtocol massage command ([0x2A, 0x00, 0x00, 0x02, 0x01, 0x01, code])."""
    return bytes([0x2A, 0x00, 0x00, 0x02, 0x01, 0x01, command_code & 0xFF])


def build_cbnew_light_command(is_on: bool) -> bytes:
    """Build CBNewProtocol light command packet for discrete on/off."""
    return bytes(
        [
            0xAA,
            0x00,
            0x00,
            0x04,
            0x01,
            0x05,
            0x00,
            0x01 if is_on else 0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )


class OkinCB24Controller(BedController):
    """Controller for beds using Okin CB24 protocol over Nordic UART.

    Protocol discovered from SmartBed by Okin app analysis.
    Uses both legacy CB24 packets and CBNew packets, depending on profile variant.
    Supports dual-bed configurations via bed selection byte.
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        bed_selection: int = 0x00,
        protocol_variant: str = OKIN_CB24_VARIANT_OLD,
        *,
        adaptive_preset_fallback: bool = False,
    ) -> None:
        """Initialize the Okin CB24 controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            bed_selection: Bed selection (0x00=default, 0xAA=bed A, 0xBB=bed B)
            protocol_variant: CB24 profile variant (cb24/cb27/cb24_ab/cb1221/dacheng/cb27new)
            adaptive_preset_fallback: Enable automatic one-shot->continuous preset fallback
        """
        super().__init__(coordinator)
        self._motor_state: dict[str, MotorDirection] = {}
        self._bed_selection = bed_selection
        self._protocol_variant = protocol_variant
        self._is_new_protocol = protocol_variant in _NEW_PROTOCOL_VARIANTS
        self._continuous_presets = (
            protocol_variant in _CONTINUOUS_PRESET_VARIANTS and not self._is_new_protocol
        )
        self._adaptive_preset_fallback = (
            adaptive_preset_fallback and not self._is_new_protocol and not self._continuous_presets
        )
        self._last_one_shot_preset_command: int | None = None
        self._last_one_shot_preset_monotonic = 0.0
        self._now = time.monotonic
        self._same_preset_retry_count = 0
        if not self._is_new_protocol and protocol_variant not in _LEGACY_PROTOCOL_VARIANTS:
            _LOGGER.warning(
                "Unknown CB24 protocol variant '%s'; defaulting to OLD protocol handling",
                protocol_variant,
            )
            self._continuous_presets = True
            self._adaptive_preset_fallback = False

        self._lights_on = False
        self._massage_on = False
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_mode = 0

        _LOGGER.debug(
            "OkinCB24Controller initialized (bed_selection=%#x, variant=%s, new_protocol=%s, continuous_presets=%s, adaptive_preset_fallback=%s)",
            bed_selection,
            protocol_variant,
            self._is_new_protocol,
            self._continuous_presets,
            self._adaptive_preset_fallback,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return NORDIC_UART_WRITE_CHAR_UUID

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command using write-without-response as required by CB24 protocol."""
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - CB24 beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True for CBNew profiles, False for legacy CB24 profiles."""
        return self._is_new_protocol

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - CB24 beds support memory presets 1-3."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 3 - CB24 beds support memory slots 1-3."""
        return 3

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - CB24 beds don't support programming memory positions."""
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        """Return True - Memory 1 is often Lounge position."""
        return True

    @property
    def supports_preset_tv(self) -> bool:
        """Return True - Memory 2 is often TV/PC position."""
        return True

    @property
    def supports_massage(self) -> bool:
        """Return True - CB24 beds support massage functions."""
        return True

    def _build_command(self, command_value: int) -> bytes:
        """Build legacy CB24-style integer command packet.

        Args:
            command_value: 32-bit command value (0 to 0xFFFFFFFF)

        Returns:
            7-byte command: [0x05, 0x02, <4-byte-command-big-endian>, bed_selection]
        """
        return build_cb24_command(command_value, self._bed_selection)

    def _build_motor_command(self, command_value: int) -> bytes:
        """Build a movement command using the profile's packet family."""
        if self._is_new_protocol:
            return build_cbnew_motor_command(command_value)
        return self._build_command(command_value)

    def _build_stop_command(self) -> bytes:
        """Build a STOP packet using the profile's packet family."""
        if self._is_new_protocol:
            return build_cbnew_stop_command()
        return self._build_command(0)

    def _build_preset_command(self, command_value: int) -> bytes:
        """Build a preset packet using the profile's packet family."""
        if not self._is_new_protocol:
            return self._build_command(command_value)

        memory_index = _CBNEW_MEMORY_BY_COMMAND.get(command_value)
        if memory_index is None:
            _LOGGER.warning(
                "No CBNew memory mapping for preset %#x; falling back to legacy packet",
                command_value,
            )
            return self._build_command(command_value)
        return build_cbnew_memory_command(memory_index)

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") == MotorDirection.UP:
            command += OkinCB24Commands.MOTOR_HEAD_UP
        elif state.get("head") == MotorDirection.DOWN:
            command += OkinCB24Commands.MOTOR_HEAD_DOWN
        if state.get("feet") == MotorDirection.UP:
            command += OkinCB24Commands.MOTOR_FEET_UP
        elif state.get("feet") == MotorDirection.DOWN:
            command += OkinCB24Commands.MOTOR_FEET_DOWN
        return command

    async def _move_motor(self, motor: str, direction: MotorDirection) -> None:
        """Move a motor in a direction or stop it."""
        if direction == MotorDirection.STOP:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = direction
        command = self._get_move_command()

        try:
            if command:
                pulse_count = self._coordinator.motor_pulse_count
                pulse_delay = self._coordinator.motor_pulse_delay_ms
                await self.write_command(
                    self._build_motor_command(command),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            self._motor_state = {}
            # Shield the STOP command to ensure it runs even if cancelled
            try:
                await asyncio.shield(
                    self.write_command(
                        self._build_stop_command(),
                        cancel_event=asyncio.Event(),
                    )
                )
            except asyncio.CancelledError:
                raise
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send stop command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", MotorDirection.UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", MotorDirection.DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", MotorDirection.STOP)

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
        """Move legs up."""
        await self._move_motor("feet", MotorDirection.UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("feet", MotorDirection.DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", MotorDirection.STOP)

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
        self._motor_state = {}
        await self.write_command(
            self._build_stop_command(),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    def _should_promote_presets_to_continuous(
        self, command_value: int, *, _now: float | None = None
    ) -> bool:
        """Promote auto legacy presets after repeated quick retries."""
        if not self._adaptive_preset_fallback:
            return False

        now = _now if _now is not None else self._now()
        if (
            self._last_one_shot_preset_command == command_value
            and now - self._last_one_shot_preset_monotonic
            <= _ADAPTIVE_PRESET_RETRY_WINDOW_SECONDS
        ):
            self._same_preset_retry_count += 1
            if self._same_preset_retry_count < _ADAPTIVE_PRESET_PROMOTION_RETRY_COUNT:
                _LOGGER.debug(
                    "CB24 adaptive retry %d/%d for preset %#x before continuous promotion",
                    self._same_preset_retry_count,
                    _ADAPTIVE_PRESET_PROMOTION_RETRY_COUNT,
                    command_value,
                )
                self._last_one_shot_preset_monotonic = now
                return False

            retry_count = self._same_preset_retry_count
            self._continuous_presets = True
            self._adaptive_preset_fallback = False
            self._same_preset_retry_count = 0
            _LOGGER.debug(
                "CB24 preset mode auto-promoted to continuous after %d retries for preset %#x",
                retry_count,
                command_value,
            )
            return True

        self._same_preset_retry_count = 0
        self._last_one_shot_preset_command = command_value
        self._last_one_shot_preset_monotonic = now
        return False

    async def _send_continuous_preset(self, preset_command: bytes) -> None:
        """Send a continuous legacy preset stream followed by STOP."""
        try:
            await self.write_command(
                preset_command,
                repeat_count=_PRESET_CONTINUOUS_COUNT,
                repeat_delay_ms=_PRESET_CONTINUOUS_DELAY_MS,
            )
        finally:
            # Send STOP to signal preset completion, shielded from
            # cancellation (same pattern as _move_motor).
            try:
                await asyncio.shield(
                    self.write_command(
                        self._build_stop_command(),
                        cancel_event=asyncio.Event(),
                    )
                )
            except asyncio.CancelledError:
                raise
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send stop after preset", exc_info=True)

    async def _send_preset(self, command_value: int) -> None:
        """Send a preset command using the appropriate protocol.

        NEW_PROTOCOL (CB27New/CBNew): One-shot — the actuator receives the
        command once and moves to the saved position autonomously.

        LEGACY profiles:
        - `cb_old`: Continuous — the actuator moves incrementally per command
          and needs repeated sends at 300ms intervals; STOP is sent afterward.
        - `cb24`/`cb27`/`cb24_ab`/`cb1221`/`dacheng`: one-shot by default.
        - Auto mode can promote legacy presets to continuous when a preset is
          retried repeatedly in a short window, avoiding manual compatibility
          changes.
        """
        preset_command = self._build_preset_command(command_value)

        if self._is_new_protocol:
            await self.write_command(preset_command)
            return

        if self._continuous_presets or self._should_promote_presets_to_continuous(
            command_value
        ):
            await self._send_continuous_preset(preset_command)
            return

        await self.write_command(preset_command)

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset(OkinCB24Commands.PRESET_FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: OkinCB24Commands.PRESET_MEMORY_1,
            2: OkinCB24Commands.PRESET_MEMORY_2,
            3: OkinCB24Commands.PRESET_MEMORY_3,
        }
        if command := commands.get(memory_num):
            await self._send_preset(command)
        else:
            _LOGGER.warning("Memory slot %d not supported (valid: 1-3)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on CB24)."""
        _LOGGER.warning(
            "CB24 beds don't support programming memory presets (requested slot: %d)",
            memory_num,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_preset(OkinCB24Commands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._send_preset(OkinCB24Commands.PRESET_ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Go to lounge position (Memory 1)."""
        await self._send_preset(OkinCB24Commands.PRESET_MEMORY_1)

    async def preset_tv(self) -> None:
        """Go to TV/PC position (Memory 2)."""
        await self._send_preset(OkinCB24Commands.PRESET_MEMORY_2)

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        if self._is_new_protocol:
            if self._lights_on:
                await self.lights_off()
            else:
                await self.lights_on()
            return
        await self.write_command(self._build_command(OkinCB24Commands.TOGGLE_LIGHTS))

    async def lights_on(self) -> None:
        """Turn on lights."""
        if self._is_new_protocol:
            await self.write_command(build_cbnew_light_command(True))
            self._lights_on = True
            return
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights."""
        if self._is_new_protocol:
            await self.write_command(build_cbnew_light_command(False))
            self._lights_on = False
            return
        await self.lights_toggle()

    # Massage methods
    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        if self._is_new_protocol:
            level = min(3, self._massage_head_level + 1)
            await self.write_command(build_cbnew_massage_command(79 + level))
            self._massage_head_level = level
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        if self._is_new_protocol:
            level = max(0, self._massage_head_level - 1)
            command_code = 83 if level == 0 else 79 + level
            await self.write_command(build_cbnew_massage_command(command_code))
            self._massage_head_level = level
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_HEAD_DOWN))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage (via intensity up)."""
        await self.massage_head_up()

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        if self._is_new_protocol:
            level = min(3, self._massage_foot_level + 1)
            await self.write_command(build_cbnew_massage_command(83 + level))
            self._massage_foot_level = level
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_FEET_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        if self._is_new_protocol:
            level = max(0, self._massage_foot_level - 1)
            command_code = 87 if level == 0 else 83 + level
            await self.write_command(build_cbnew_massage_command(command_code))
            self._massage_foot_level = level
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_FEET_DOWN))

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage (via intensity up)."""
        await self.massage_foot_up()

    async def massage_toggle(self) -> None:
        """Toggle all massage zones."""
        if self._is_new_protocol:
            self._massage_on = not self._massage_on
            await self.write_command(
                build_cbnew_massage_command(64 if self._massage_on else 65)
            )
            if not self._massage_on:
                self._massage_head_level = 0
                self._massage_foot_level = 0
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_ALL_TOGGLE))

    async def massage_intensity_up(self) -> None:
        """Increase all massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_INTENSITY_UP))

    async def massage_intensity_down(self) -> None:
        """Decrease all massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_INTENSITY_DOWN))

    async def massage_off(self) -> None:
        """Turn off all massage."""
        if self._is_new_protocol:
            self._massage_on = False
            self._massage_head_level = 0
            self._massage_foot_level = 0
            await self.write_command(build_cbnew_massage_command(65))
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_STOP_ALL))

    async def massage_mode_step(self) -> None:
        """Cycle through massage wave patterns."""
        if self._is_new_protocol:
            self._massage_mode = (self._massage_mode % 4) + 1
            await self.write_command(build_cbnew_massage_command(65 + self._massage_mode))
            return
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_WAVE_STEP))
