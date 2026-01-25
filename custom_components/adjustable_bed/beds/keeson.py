"""Keeson bed controller implementation.

Reverse engineering by alanbixby and Richard Hopton (smartbed-mqtt).

Keeson beds (Member's Mark, Purple, Ergomotion, GhostBed) have several protocol variants:
- KSBT: Simple 6-byte commands [0x04, 0x02, ...int_to_bytes(command)]
- BaseI4: 8-byte commands with XOR checksum
- BaseI5: Same as BaseI4 with notification support
- Ergomotion: Same as BaseI4/I5 but with position feedback via BLE notifications

All use 32-bit command values for motor and preset operations.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_KSBT_CHAR_UUID,
    KEESON_KSBT_FALLBACK_GATT_PAIRS,
    KEESON_KSBT_SERVICE_UUID,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_OKIN,
)
from .base import BedController
from .okin_protocol import int_to_bytes

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class KeesonCommands:
    """Keeson command constants (32-bit values)."""

    # Presets - common
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000

    # KSBT-specific presets (not available on BaseI4/I5)
    PRESET_MEMORY_1 = 0x2000  # KSBT "M" button
    PRESET_TV = 0x4000  # KSBT only
    PRESET_ANTI_SNORE = 0x8000  # KSBT only

    # BaseI4/I5-specific presets (0x8000 means Memory 3 on BaseI4/I5, Snore on KSBT)
    PRESET_MEMORY_3_BASE = 0x8000  # BaseI4/I5 only
    PRESET_MEMORY_3 = 0x8000  # Alias for backward compatibility

    # Memory presets (availability varies by variant)
    PRESET_MEMORY_2 = 0x4000  # Same as TV on KSBT
    PRESET_MEMORY_4 = 0x10000  # May work on some beds

    # Aliases
    PRESET_LOUNGE = 0x2000  # Same as Memory 1 / KSBT "M" button

    # Motors
    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_LUMBAR_UP = 0x40
    MOTOR_LUMBAR_DOWN = 0x80

    # Massage
    MASSAGE_HEAD_UP = 0x800
    MASSAGE_HEAD_DOWN = 0x800000
    MASSAGE_FOOT_UP = 0x400
    MASSAGE_FOOT_DOWN = 0x1000000
    MASSAGE_STEP = 0x100
    MASSAGE_TIMER_STEP = 0x200
    MASSAGE_WAVE_STEP = 0x10000000

    # Lights
    TOGGLE_SAFETY_LIGHTS = 0x20000
    TOGGLE_LIGHTS = 0x20000  # Alias for Ergomotion compatibility


class KeesonController(BedController):
    """Controller for Keeson beds (including Ergomotion variant with position feedback)."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = "base",
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the Keeson controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Protocol variant ('ksbt', 'base', or 'ergomotion')
            char_uuid: The characteristic UUID to use for writing commands
        """
        super().__init__(coordinator)
        self._variant = variant
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        # Position feedback state (for ergomotion variant)
        self._head_position: int | None = None
        self._foot_position: int | None = None
        self._head_moving: bool = False
        self._foot_moving: bool = False
        self._head_massage: int = 0
        self._foot_massage: int = 0
        self._led_on: bool = False
        self._timer_mode: str | None = None

        # Determine the characteristic UUID
        if char_uuid:
            self._char_uuid = char_uuid
        elif variant == "ksbt":
            # For KSBT variant, try to find a working characteristic UUID
            self._char_uuid = self._detect_ksbt_characteristic_uuid()
        else:
            # For base/ergomotion variant, try to find a working characteristic UUID
            self._char_uuid = self._detect_characteristic_uuid()

        # Notify characteristic for ergomotion variant
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug(
            "KeesonController initialized (variant: %s, char: %s)",
            variant,
            self._char_uuid,
        )

    def _detect_characteristic_uuid(self) -> str:
        """Detect the correct write characteristic UUID from available services.

        Tries the primary UUID first, then falls back to alternative UUIDs
        if the primary service is not available. Verifies that the characteristic
        actually exists within the service before returning.
        """
        client = self.client
        if client is None or client.services is None:
            _LOGGER.debug("No BLE services available, using default UUID")
            return KEESON_BASE_WRITE_CHAR_UUID

        # Build a map of service UUID -> service object for efficient lookup
        services_map = {str(service.uuid).lower(): service for service in client.services}
        _LOGGER.debug("Available Keeson services: %s", list(services_map.keys()))

        # Check if primary service is available and has the expected characteristic
        primary_service = services_map.get(KEESON_BASE_SERVICE_UUID.lower())
        if primary_service is not None:
            char = primary_service.get_characteristic(KEESON_BASE_WRITE_CHAR_UUID)
            if char is not None:
                _LOGGER.debug("Found primary Keeson service with expected characteristic")
                return KEESON_BASE_WRITE_CHAR_UUID
            _LOGGER.debug(
                "Primary service found but characteristic %s not present",
                KEESON_BASE_WRITE_CHAR_UUID,
            )

        # Try fallback service/characteristic pairs, verifying characteristic exists
        for fallback_service, fallback_char in KEESON_FALLBACK_GATT_PAIRS:
            service = services_map.get(fallback_service.lower())
            if service is not None:
                char = service.get_characteristic(fallback_char)
                if char is not None:
                    _LOGGER.info(
                        "Using fallback service/characteristic: %s/%s",
                        fallback_service,
                        fallback_char,
                    )
                    return fallback_char
                _LOGGER.debug(
                    "Fallback service %s found but characteristic %s not present",
                    fallback_service,
                    fallback_char,
                )

        # No matching service/characteristic found, log all services for debugging
        _LOGGER.warning(
            "No recognized Keeson service/characteristic found. "
            "Please report this to help add support for your device."
        )
        self.log_discovered_services(level=logging.INFO)
        return KEESON_BASE_WRITE_CHAR_UUID

    def _detect_ksbt_characteristic_uuid(self) -> str:
        """Detect the correct write characteristic UUID for KSBT variant.

        Tries the primary Nordic UART service first, then falls back to alternative
        UUIDs if the primary service is not available.
        """
        client = self.client
        if client is None or client.services is None:
            _LOGGER.debug("No BLE services available, using default KSBT UUID")
            return KEESON_KSBT_CHAR_UUID

        # Build a map of service UUID -> service object for efficient lookup
        services_map = {str(service.uuid).lower(): service for service in client.services}
        _LOGGER.debug("Available KSBT services: %s", list(services_map.keys()))

        # Check if primary KSBT service (Nordic UART) is available
        primary_service = services_map.get(KEESON_KSBT_SERVICE_UUID.lower())
        if primary_service is not None:
            char = primary_service.get_characteristic(KEESON_KSBT_CHAR_UUID)
            if char is not None:
                _LOGGER.debug("Found primary KSBT service with expected characteristic")
                return KEESON_KSBT_CHAR_UUID
            _LOGGER.debug(
                "Primary KSBT service found but characteristic %s not present",
                KEESON_KSBT_CHAR_UUID,
            )

        # Try fallback service/characteristic pairs
        for fallback_service, fallback_char in KEESON_KSBT_FALLBACK_GATT_PAIRS:
            service = services_map.get(fallback_service.lower())
            if service is not None:
                char = service.get_characteristic(fallback_char)
                if char is not None:
                    _LOGGER.info(
                        "Using KSBT fallback service/characteristic: %s/%s",
                        fallback_service,
                        fallback_char,
                    )
                    return fallback_char
                _LOGGER.debug(
                    "KSBT fallback service %s found but characteristic %s not present",
                    fallback_service,
                    fallback_char,
                )

        # No matching service/characteristic found, log all services for debugging
        _LOGGER.warning(
            "No recognized KSBT service/characteristic found. "
            "Please report this to help add support for your device."
        )
        self.log_discovered_services(level=logging.INFO)
        return KEESON_KSBT_CHAR_UUID

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        """KSBT and Ergomotion have the Lounge preset; BaseI4/I5 does not."""
        return self._variant != "base"

    @property
    def supports_preset_tv(self) -> bool:
        """KSBT and Ergomotion have TV preset; BaseI4/I5 does not."""
        return self._variant != "base"

    @property
    def supports_preset_anti_snore(self) -> bool:
        """KSBT and Ergomotion have anti-snore preset; BaseI4/I5 does not."""
        return self._variant != "base"

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Keeson beds support memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return memory slot count based on variant.

        KSBT: Slots 1-2 (M button = slot 1, TV = slot 2)
        BaseI4/I5: Slot 3 only (from APK analysis)
        Ergomotion: 4 slots (needs verification)
        """
        if self._variant == "ksbt":
            return 2  # Memory 1 (M button) and Memory 2 (TV button)
        elif self._variant == "ergomotion":
            return 4  # Ergomotion may support all 4
        else:
            # BaseI4/I5 - the APK only shows Memory 3 button
            # But we'll expose all 4 as they may work
            return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - Keeson beds don't support programming memory positions."""
        return False

    @property
    def supports_lights(self) -> bool:
        """Return True - Keeson beds support under-bed/safety lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Keeson only supports toggle, not discrete on/off."""
        return False

    @property
    def has_tilt_support(self) -> bool:
        """Return True - Keeson beds have tilt motor control."""
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - Keeson beds have lumbar motor control."""
        return True

    @property
    def supports_stop_all(self) -> bool:
        """Return False - Keeson beds don't have a dedicated stop command."""
        return False

    @property
    def reports_percentage_position(self) -> bool:
        """Return True - Keeson/Ergomotion report 0-100 percentage, not angle degrees."""
        return True

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        """Return Keeson-specific translation keys for motor cover entities.

        Keeson motor naming differs from standard naming:
        - "head" motor → controls back/upper body → use "keeson_back"
        - "tilt" motor → controls head/pillow → use "keeson_head"
        - "feet" motor → controls legs → use "keeson_legs"
        """
        return {
            "head": "keeson_back",
            "tilt": "keeson_head",
            "feet": "keeson_legs",
        }

    # Massage timer - Keeson only has step command, no direct timer set
    # We cannot reliably emulate stepping without knowing current state
    @property
    def supports_massage_timer(self) -> bool:
        """Return False - Keeson can only step through timer, not set directly."""
        return False

    @property
    def massage_intensity_max(self) -> int:
        """Return 6 - Keeson/Ergomotion use 0-6 intensity scale."""
        return 6

    def _build_command(self, command_value: int) -> bytes:
        """Build command bytes based on protocol variant."""
        if self._variant == "ksbt":
            # KSBT: [0x04, 0x02, ...int_to_bytes(command)]
            return bytes([0x04, 0x02] + int_to_bytes(command_value))
        else:
            # BaseI4/I5/OKIN/Serta/Ergomotion: [prefix, 0xfe, 0x16, ...int_bytes, checksum]
            # OKIN FFE (13/15 series) uses 0xE6 prefix, others use 0xE5
            # All variants use little-endian byte order (cmd_lo first)
            int_bytes = int_to_bytes(command_value)
            int_bytes.reverse()  # Little-endian for all variants
            prefix = 0xE6 if self._variant == KEESON_VARIANT_OKIN else 0xE5
            data = [prefix, 0xFE, 0x16] + int_bytes
            checksum = sum(data) ^ 0xFF
            data.append(checksum & 0xFF)
            return bytes(data)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Keeson bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications (ergomotion variant only)."""
        self._notify_callback = callback

        if self._variant != KEESON_VARIANT_ERGOMOTION:
            _LOGGER.debug(
                "Keeson beds don't support position notifications (variant: %s)", self._variant
            )
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started position notifications for Keeson/Ergomotion bed")
        except BleakError:
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications (ergomotion variant)."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Parse notification data from the bed (ergomotion variant).

        Data formats based on header byte:
        - 0xED: 16-byte messages
        - 0xF0: 19-byte messages
        - 0xF1: 20-byte messages
        """
        if len(data) < 1:
            return

        header = data[0]

        if header == 0xED and len(data) >= 16:
            self._parse_position_message(data, 16)
        elif header == 0xF0 and len(data) >= 19:
            self._parse_position_message(data, 19)
        elif header == 0xF1 and len(data) >= 20:
            self._parse_position_message(data, 20)
        else:
            _LOGGER.debug("Unknown notification format: header=0x%02X len=%d", header, len(data))

    def _parse_position_message(self, data: bytes, msg_len: int) -> None:
        """Parse position message from ergomotion bed."""
        # data1 starts at offset 1
        data1 = data[1:9]

        # Head position: bytes 0-1 (little-endian)
        head_pos = int.from_bytes(data1[0:2], "little")
        if head_pos != 0xFFFF:
            self._head_position = head_pos
        else:
            self._head_position = 0

        # Foot position: bytes 2-3 (little-endian)
        foot_pos = int.from_bytes(data1[2:4], "little")
        if foot_pos != 0xFFFF:
            self._foot_position = foot_pos
        else:
            self._foot_position = 0

        # Massage levels: bytes 4-5 (0-6 scale)
        self._head_massage = data1[4] if len(data1) > 4 else 0
        self._foot_massage = data1[5] if len(data1) > 5 else 0

        # data2 starts at offset 9
        data2 = data[9:msg_len]

        # Movement status and LED: byte 4
        if len(data2) > 4:
            move = data2[4] & 0xF
            self._head_moving = move != 0xF and (move & 1) > 0
            self._foot_moving = move != 0xF and (move & 2) > 0
            self._led_on = (data2[4] & 0x40) > 0

        # Timer: byte 5
        if len(data2) > 5:
            timer_val = data2[5]
            timer_options = ["10", "20", "30"]
            if 1 <= timer_val <= 3:
                self._timer_mode = timer_options[timer_val - 1]
            else:
                self._timer_mode = None

        self._notify_position_update()

    def _notify_position_update(self) -> None:
        """Notify callback with position updates.

        Note: Ergomotion positions are 0-100 (percentage), not angles in degrees.
        We use "back"/"legs" keys to match 2-motor sensor/cover entity expectations.
        """
        if self._notify_callback is None:
            return

        # Notify back (head) position - use "back" key for 2-motor compatibility
        if self._head_position is not None:
            self._notify_callback("back", float(self._head_position))

        # Notify legs (foot) position - use "legs" key for 2-motor compatibility
        if self._foot_position is not None:
            self._notify_callback("legs", float(self._foot_position))

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self._variant != KEESON_VARIANT_ERGOMOTION:
            return

        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped position notifications")
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Ergomotion beds report positions via notifications, not direct reads.
        """
        pass

    # Position feedback properties (for ergomotion variant)
    @property
    def head_position(self) -> int | None:
        """Get current head position (0-100)."""
        return self._head_position

    @property
    def foot_position(self) -> int | None:
        """Get current foot position (0-100)."""
        return self._foot_position

    @property
    def head_moving(self) -> bool:
        """Check if head motor is currently moving."""
        return self._head_moving

    @property
    def foot_moving(self) -> bool:
        """Check if foot motor is currently moving."""
        return self._foot_moving

    @property
    def head_massage_level(self) -> int:
        """Get head massage level (0-6)."""
        return self._head_massage

    @property
    def foot_massage_level(self) -> int:
        """Get foot massage level (0-6)."""
        return self._foot_massage

    @property
    def led_on(self) -> bool:
        """Check if LED is on."""
        return self._led_on

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") is True:
            command += KeesonCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += KeesonCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += KeesonCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += KeesonCommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            command += KeesonCommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            command += KeesonCommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            command += KeesonCommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            command += KeesonCommands.MOTOR_LUMBAR_DOWN
        return command

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it, always sending STOP at the end."""
        self._motor_state[motor] = direction
        command = self._get_move_command()

        try:
            if command:
                await self.write_command(
                    self._build_command(command),
                    repeat_count=self._coordinator.motor_pulse_count,
                    repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
                )
        finally:
            # Always send stop with a fresh event so it's not affected by cancellation
            self._motor_state = {}
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", True)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", False)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", None)

    async def move_back_up(self) -> None:
        """Move back up (same as head for Keeson)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Keeson)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for Keeson)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for Keeson)."""
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("feet", True)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("feet", False)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("feet", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(0),
            cancel_event=asyncio.Event(),
        )

    # Tilt motor control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_motor(motor="tilt", direction=True)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_motor(motor="tilt", direction=False)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._move_motor(motor="tilt", direction=None)

    # Lumbar motor control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_motor(motor="lumbar", direction=True)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_motor(motor="lumbar", direction=False)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._move_motor(motor="lumbar", direction=None)

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(KeesonCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Note: Command values vary by protocol variant:
        - KSBT: Memory 1 (0x2000) = M button, Memory 2 (0x4000) = TV button
        - BaseI4/I5: Memory 3 (0x8000) is the only confirmed memory preset
        - Memory 3 (0x8000) on KSBT is actually anti-snore, not memory
        """
        # Warn about variant-specific behavior
        if self._variant != "base" and memory_num == 3:
            _LOGGER.warning(
                "Memory 3 on KSBT/Ergomotion beds triggers anti-snore, not a memory preset. "
                "Use Memory 1 or Memory 2 instead."
            )
        elif self._variant == "base" and memory_num in (1, 2):
            _LOGGER.debug(
                "Memory %d may not work on BaseI4/I5 beds. Memory 3 is more reliable.",
                memory_num,
            )

        commands = {
            1: KeesonCommands.PRESET_MEMORY_1,
            2: KeesonCommands.PRESET_MEMORY_2,
            3: KeesonCommands.PRESET_MEMORY_3,
            4: KeesonCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on Keeson)."""
        _LOGGER.warning(
            "Keeson beds don't support programming memory presets (requested: %d)", memory_num
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(KeesonCommands.PRESET_ZERO_G))

    async def preset_lounge(self) -> None:
        """Go to lounge position (KSBT/Ergomotion 'M' button / Memory 1)."""
        if self._variant == "base":
            _LOGGER.warning("Lounge preset is not available on BaseI4/I5 beds")
            return
        await self.write_command(self._build_command(KeesonCommands.PRESET_LOUNGE))

    async def preset_tv(self) -> None:
        """Go to TV position (KSBT/Ergomotion only)."""
        if self._variant == "base":
            _LOGGER.warning("TV preset is not available on BaseI4/I5 beds")
            return
        await self.write_command(self._build_command(KeesonCommands.PRESET_TV))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (KSBT/Ergomotion only)."""
        if self._variant == "base":
            _LOGGER.warning("Anti-snore preset is not available on BaseI4/I5 beds")
            return
        await self.write_command(self._build_command(KeesonCommands.PRESET_ANTI_SNORE))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on safety lights (toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off safety lights (toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle safety lights."""
        await self.write_command(self._build_command(KeesonCommands.TOGGLE_SAFETY_LIGHTS))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_STEP))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_FOOT_DOWN))

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_TIMER_STEP))

    def get_massage_state(self) -> dict[str, Any]:
        """Return current massage state from BLE notification feedback.

        Only populated for ergomotion variant which has state notifications.

        Returns:
            dict with head_intensity, foot_intensity, timer_mode
        """
        return {
            "head_intensity": self._head_massage,
            "foot_intensity": self._foot_massage,
            "timer_mode": self._timer_mode,
            "led_on": self._led_on,
        }
