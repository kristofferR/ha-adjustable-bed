"""SBI/Q-Plus (Costco) bed controller implementation.

Reverse engineering from com.sbi.costco APK.

SBI/Q-Plus is sold through Costco and supports both BLE and Classic Bluetooth.
The BLE protocol uses 8 or 9-byte packets with inverted sum checksum.

Unique features:
- Dual bed control (A/B/Both modes) for split-king configurations
- Position feedback via calibrated pulse-to-angle lookup tables
- 4-motor support (head, foot, tilt, lumbar)
- Multiple massage modes

Packet formats:
- 8-byte (Both mode): [0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
- 9-byte (A/B mode): [0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
"""

from __future__ import annotations

import asyncio
import bisect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    SBI_VARIANT_BOTH,
    SBI_VARIANT_SIDE_A,
    SBI_VARIANT_SIDE_B,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# Position feedback lookup tables from APK
# Maps pulse counts to angles (index = degrees)
HEAD_PULSE_TABLE: list[int] = [
    0, 327, 577, 855, 1148, 1676, 2083, 2401, 2711, 3020, 3402, 3679, 4019, 4529,
    4864, 5262, 5633, 6024, 6453, 6826, 7239, 7611, 8015, 8423, 8862, 9240, 9632,
    10029, 10404, 10840, 11245, 11640, 11976, 12351, 12752, 13106, 13511, 13819,
    14169, 14518, 14901, 15217, 15556, 15856, 16177, 16530, 16788, 17118, 17389,
    17700, 18000, 18268, 18481, 18767, 19035, 19260, 19487, 19757, 19970, 20164, 20413,
]  # 61 values for 0-60 degrees

FOOT_PULSE_TABLE: list[int] = [
    0, 570, 784, 968, 1150, 1372, 1653, 1837, 2062, 2283, 2494, 2755, 3015, 3290,
    3578, 3819, 4039, 4261, 4544, 4895, 5170, 5461, 5723, 6020, 6334, 6631, 6922,
    7243, 7546, 7810, 8174, 8546, 8718,
]  # 33 values for 0-32 degrees


def pulse_to_angle(pulse: int, table: list[int]) -> int:
    """Convert pulse count to angle using lookup table.

    Args:
        pulse: Raw pulse value from notification
        table: Lookup table mapping pulse thresholds to angles

    Returns:
        Angle in degrees (0-60 for head, 0-32 for foot)
    """
    # Handle inverted values (>= 32768)
    if pulse >= 32768:
        pulse = 65535 - pulse

    # Find the angle using binary search
    # The table is sorted ascending, so bisect_left gives us the angle
    angle = bisect.bisect_left(table, pulse)

    # Clamp to valid range
    return min(angle, len(table) - 1)


class SBICommands:
    """SBI/Q-Plus command constants (32-bit little-endian values)."""

    # Motor commands (cmd0 byte)
    MOTOR_HEAD_UP = 0x00000001
    MOTOR_HEAD_DOWN = 0x00000002
    MOTOR_FEET_UP = 0x00000004
    MOTOR_FEET_DOWN = 0x00000008
    MOTOR_TILT_UP = 0x00000010
    MOTOR_TILT_DOWN = 0x00000020
    MOTOR_LUMBAR_UP = 0x00000040
    MOTOR_LUMBAR_DOWN = 0x00000080

    # Presets (cmd1/cmd3 bytes)
    PRESET_FLAT = 0x08000000  # cmd3=0x08
    PRESET_ZERO_G = 0x00001000  # cmd1=0x10
    PRESET_RESET = 0x08001000  # cmd1=0x10, cmd3=0x08
    PRESET_MEMORY_1 = 0x00002000  # cmd1=0x20
    PRESET_MEMORY_2 = 0x00004000  # cmd1=0x40 (TV in some remotes)
    PRESET_TV = 0x00008000  # cmd1=0x80

    # Light (cmd2 byte)
    TOGGLE_LIGHT = 0x00020000  # cmd2=0x02

    # Massage (cmd1/cmd2 bytes)
    MASSAGE_LEVEL = 0x00000100  # cmd1=0x01
    MASSAGE_FOOT = 0x00000400  # cmd1=0x04
    MASSAGE_HEAD = 0x00000800  # cmd1=0x08
    MASSAGE_MODE_1 = 0x00100000  # cmd2=0x10
    MASSAGE_MODE_2 = 0x00200000  # cmd2=0x20
    MASSAGE_MODE_3 = 0x00080000  # cmd2=0x08
    MASSAGE_LUMBAR = 0x00400000  # cmd2=0x40

    # Stop
    STOP = 0x00000000


class SBIController(BedController):
    """Controller for SBI/Q-Plus beds (Costco).

    Supports dual-bed A/B/Both modes for split-king configurations.
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = SBI_VARIANT_BOTH,
    ) -> None:
        """Initialize the SBI controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Bed variant (both, side_a, side_b)
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}
        self._variant = variant

        # Position state from notifications
        self._head_angle: int = 0
        self._foot_angle: int = 0

        self._char_uuid = KEESON_BASE_WRITE_CHAR_UUID
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug("SBIController initialized with variant: %s", variant)

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
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2  # Memory 1 and Memory 2

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False  # Toggle only

    @property
    def has_tilt_support(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_position_feedback(self) -> bool:
        """Return True - SBI has position feedback via lookup tables."""
        return True

    @property
    def head_angle(self) -> int:
        """Get current head angle in degrees (0-60)."""
        return self._head_angle

    @property
    def foot_angle(self) -> int:
        """Get current foot angle in degrees (0-32)."""
        return self._foot_angle

    def _build_command(self, command_value: int) -> bytes:
        """Build a command packet from a 32-bit command value.

        Uses 8-byte format for "Both" mode (0xE5 header) or
        9-byte format for A/B mode (0xE6 header with side selector).

        Format (8-byte): [0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
        Format (9-byte): [0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
        Checksum: (~sum(bytes 0 to n-1)) & 0xFF
        """
        # Extract command bytes (little-endian)
        cmd0 = command_value & 0xFF
        cmd1 = (command_value >> 8) & 0xFF
        cmd2 = (command_value >> 16) & 0xFF
        cmd3 = (command_value >> 24) & 0xFF

        if self._variant == SBI_VARIANT_BOTH:
            # 8-byte format for dual control
            header = [0xE5, 0xFE, 0x16]
            data = header + [cmd0, cmd1, cmd2, cmd3]
        else:
            # 9-byte format for single side control
            header = [0xE6, 0xFE, 0x16]
            side = 0x01 if self._variant == SBI_VARIANT_SIDE_A else 0x02
            data = header + [cmd0, cmd1, cmd2, cmd3, side]

        # Inverted sum checksum
        checksum = (~sum(data)) & 0xFF
        data.append(checksum)
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
            "Writing command to SBI bed: %s (repeat: %d, delay: %dms)",
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

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started notifications for SBI bed")
        except BleakError:
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Parse notification data for position feedback.

        The notification format contains pulse counts that can be
        converted to angles using the lookup tables.
        """
        # Position data format needs to be determined from actual device
        # Based on APK analysis, pulse values are 16-bit and may need inversion
        if len(data) < 4:
            return

        # This is a placeholder - actual format needs verification
        # The APK shows pulse values are extracted and passed to angle lookup
        try:
            # Attempt to extract head and foot pulse values
            # Exact positions depend on actual notification format
            if len(data) >= 4:
                head_pulse = int.from_bytes(data[0:2], byteorder="little", signed=False)
                foot_pulse = int.from_bytes(data[2:4], byteorder="little", signed=False)

                self._head_angle = pulse_to_angle(head_pulse, HEAD_PULSE_TABLE)
                self._foot_angle = pulse_to_angle(foot_pulse, FOOT_PULSE_TABLE)

                _LOGGER.debug(
                    "SBI position: head=%d° (pulse=%d), foot=%d° (pulse=%d)",
                    self._head_angle,
                    head_pulse,
                    self._foot_angle,
                    foot_pulse,
                )

                # Notify callback if set
                if self._notify_callback:
                    self._notify_callback("head", float(self._head_angle))
                    self._notify_callback("foot", float(self._foot_angle))
        except Exception:
            _LOGGER.debug("Failed to parse position notification")

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped notifications")
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Position is obtained via notifications, not explicit reads.
        """
        pass

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it, always sending STOP at the end."""
        self._motor_state[motor] = direction
        key = 0

        # Build combined motor command
        state = self._motor_state
        if state.get("head") is True:
            key |= SBICommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            key |= SBICommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            key |= SBICommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            key |= SBICommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            key |= SBICommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            key |= SBICommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            key |= SBICommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            key |= SBICommands.MOTOR_LUMBAR_DOWN

        try:
            if key:
                await self.write_command(
                    self._build_command(key),
                    repeat_count=self._coordinator.motor_pulse_count,
                    repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
                )
        finally:
            # Always send stop
            self._motor_state = {}
            try:
                await self.write_command(
                    self._build_command(SBICommands.STOP),
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
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
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

    # Tilt motor control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_motor("tilt", True)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_motor("tilt", False)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._move_motor("tilt", None)

    # Lumbar motor control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_motor("lumbar", True)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_motor("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._move_motor("lumbar", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(SBICommands.STOP),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(SBICommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: SBICommands.PRESET_MEMORY_1,
            2: SBICommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("SBI supports Memory 1-2, requested: %d", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("SBI doesn't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(SBICommands.PRESET_ZERO_G))

    async def preset_lounge(self) -> None:
        """Go to lounge position (not available)."""
        _LOGGER.warning("Lounge preset is not available on SBI beds")

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command(SBICommands.PRESET_TV))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (not available)."""
        _LOGGER.warning("Anti-snore preset is not available on SBI beds")

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights (toggle)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(SBICommands.TOGGLE_LIGHT))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage (cycles through levels)."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_LEVEL))

    async def massage_head_up(self) -> None:
        """Increase head massage."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_HEAD))

    async def massage_head_down(self) -> None:
        """Decrease head massage (cycles)."""
        await self.massage_head_up()

    async def massage_foot_up(self) -> None:
        """Increase foot massage."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_FOOT))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage (cycles)."""
        await self.massage_foot_up()

    async def massage_lumbar_toggle(self) -> None:
        """Toggle lumbar massage."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_LUMBAR))

    async def massage_mode_1(self) -> None:
        """Set massage to mode 1."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_MODE_1))

    async def massage_mode_2(self) -> None:
        """Set massage to mode 2."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_MODE_2))

    async def massage_mode_3(self) -> None:
        """Set massage to mode 3."""
        await self.write_command(self._build_command(SBICommands.MASSAGE_MODE_3))
