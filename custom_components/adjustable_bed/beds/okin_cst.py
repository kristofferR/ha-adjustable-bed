"""OKIN CSTProtocol bed controller implementation.

CSTProtocol uses a 14-byte command format with two separate 32-bit fields:
- Primary field (bytes 2-5): Motor control and several remote button actions
- Secondary field (bytes 6-9): Discrete light and massage-wave actions

Format: [0x0C, 0x02, motor[4], control[4], 0x00, 0x00, 0x00, 0x00]

Most command values are identical to existing OKIN UUID values, but the MFirm
app routes remote actions across both CST fields. Do not infer field placement
from the feature type alone.

Protocol reverse-engineered from com.okin.bedding.rizemf900 app (CSTProtocol.java).
Known devices: Rize MF900, other CSTProtocol-based Okin beds.

Uses standard OKIN service: 62741523-52f9-8864-b1ab-3b3a8d65950b
Requires BLE pairing before use (same as OkinUuidController).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FOOT_MAX_ANGLE,
    OKIN_FOOT_MAX_RAW,
    OKIN_HEAD_MAX_ANGLE,
    OKIN_HEAD_MAX_RAW,
    OKIN_POSITION_NOTIFY_CHAR_UUID,
)
from .base import BedController
from .okin_protocol import build_cst_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_NOT_CONNECTED_MSG = "Not connected to bed"
_PRESET_REPEAT_COUNT = 100
_PRESET_REPEAT_DELAY_MS = 300
_BUTTON_PRESS_REPEAT_COUNT = 3
_BUTTON_PRESS_REPEAT_DELAY_MS = 100
_STOP_REPEAT_COUNT = 2
_STOP_REPEAT_DELAY_MS = 100


class CstMotorCommands:
    """Motor field command values (bytes 2-5)."""

    STOP = 0x00000000
    HEAD_UP = 0x00000001
    HEAD_DOWN = 0x00000002
    FOOT_UP = 0x00000004
    FOOT_DOWN = 0x00000008
    HEAD_TILT_UP = 0x00000010
    HEAD_TILT_DOWN = 0x00000020
    LUMBAR_UP = 0x00000040
    LUMBAR_DOWN = 0x00000080


class CstRemoteCommands:
    """Remote action command values.

    The CST app chooses the first or second 32-bit field per action. Call sites
    pass these values to build_cst_command() using the matching field.
    """

    STOP = 0x00000000
    FLAT = 0x08000000
    ZERO_G = 0x00001000
    LOUNGE = 0x00002000
    INCLINE = 0x00004000
    ANTI_SNORE = 0x00008000
    MEMORY_1 = 0x00010000
    LIGHT_TOGGLE = 0x00020000
    LIGHT_ON = 0x00000040
    LIGHT_OFF = 0x00000080
    MASSAGE_TOGGLE = 0x02000000
    MASSAGE_OFF = 0x02000000
    MASSAGE_INTENSITY = 0x00000C00
    MASSAGE_INTENSITY_MINUS = 0x01800000
    MASSAGE_HEAD = 0x00000800
    MASSAGE_FEET = 0x00000400
    MASSAGE_HEAD_MINUS = 0x00800000
    MASSAGE_FEET_MINUS = 0x01000000
    MASSAGE_WAVE_1 = 0x00080000
    MASSAGE_WAVE_2 = 0x00100000
    MASSAGE_WAVE_3 = 0x00200000


CstControlCommands = CstRemoteCommands


class OkinCstController(BedController):
    """Controller for OKIN CSTProtocol beds (Rize MF900, etc.).

    Uses 14-byte packets with separate motor and control fields.
    Requires BLE pairing before use.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the OKIN CST controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, int] = {}
        self._massage_wave_index = 0

        _LOGGER.debug("OkinCstController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIMAT_WRITE_CHAR_UUID

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
    def supports_preset_incline(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        return False

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
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

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
            raise ConnectionError(_NOT_CONNECTED_MSG)

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing CST command (%s): %s (repeat: %d, delay: %dms, response=True)",
            OKIMAT_WRITE_CHAR_UUID,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                async with self._ble_lock:
                    await self.client.write_gatt_char(
                        OKIMAT_WRITE_CHAR_UUID, command, response=True
                    )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    # Position feedback (same as OkinUuidController)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start position notifications: not connected")
            return

        try:
            async with self._ble_lock:
                await self.client.start_notify(
                    OKIN_POSITION_NOTIFY_CHAR_UUID,
                    self._handle_position_notification,
                )
            _LOGGER.info("Position notifications active for OKIN CST bed")
        except BleakError as err:
            _LOGGER.debug(
                "Could not start position notifications: %s",
                err,
            )

    def _handle_position_notification(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle position notification data."""
        self.forward_raw_notification(OKIN_POSITION_NOTIFY_CHAR_UUID, bytes(data))

        if len(data) < 7:
            return

        _LOGGER.debug("OKIN CST position notification: %s", data.hex())

        head_raw = data[3] | (data[4] << 8)
        head_angle = min(
            round((head_raw / OKIN_HEAD_MAX_RAW) * OKIN_HEAD_MAX_ANGLE, 1),
            OKIN_HEAD_MAX_ANGLE,
        )

        foot_raw = data[5] | (data[6] << 8)
        foot_angle = min(
            round((foot_raw / OKIN_FOOT_MAX_RAW) * OKIN_FOOT_MAX_ANGLE, 1),
            OKIN_FOOT_MAX_ANGLE,
        )

        if self._notify_callback:
            self._notify_callback("back", head_angle)
            self._notify_callback("legs", foot_angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            async with self._ble_lock:
                await self.client.stop_notify(OKIN_POSITION_NOTIFY_CHAR_UUID)
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current position data."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            async with self._ble_lock:
                data = await self.client.read_gatt_char(OKIN_POSITION_NOTIFY_CHAR_UUID)
            if data:
                self._handle_position_notification(0, bytearray(data))  # type: ignore[arg-type]
        except BleakError as err:
            _LOGGER.debug("Could not read position data: %s", err)

    # Motor movement helpers

    def _get_motor_command(self) -> int:
        """Calculate combined motor command from active motor states."""
        command = 0
        for value in self._motor_state.values():
            command += value
        return command

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        """Move a motor or stop it."""
        if command_value is None or command_value == 0:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = command_value

        combined = self._get_motor_command()
        pulse_count = getattr(self._coordinator, "motor_pulse_count", 25)
        pulse_delay = getattr(self._coordinator, "motor_pulse_delay_ms", 200)

        try:
            if combined:
                await self.write_command(
                    build_cst_command(motor_value=combined),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            self._motor_state.pop(motor, None)
            if not self._motor_state:
                await self._send_stop_sequence()

    async def _send_stop_sequence(self) -> None:
        """Send the app-style CST STOP sequence."""
        stop_event = asyncio.Event()
        for index in range(_STOP_REPEAT_COUNT):
            if index:
                await asyncio.sleep(_STOP_REPEAT_DELAY_MS / 1000)
            await self.write_command(build_cst_command(), cancel_event=stop_event)

    async def _send_repeated_command(
        self,
        *,
        motor_value: int = 0,
        control_value: int = 0,
        repeat_count: int,
        repeat_delay_ms: int,
    ) -> None:
        """Send a CST command with stop cleanup."""
        try:
            await self.write_command(
                build_cst_command(motor_value=motor_value, control_value=control_value),
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
            )
        finally:
            try:
                await self._send_stop_sequence()
            except (TimeoutError, BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP during CST cleanup", exc_info=True)

    async def _send_preset(self, motor_value: int) -> None:
        """Send a long-running preset recall command."""
        await self._send_repeated_command(
            motor_value=motor_value,
            repeat_count=_PRESET_REPEAT_COUNT,
            repeat_delay_ms=_PRESET_REPEAT_DELAY_MS,
        )

    async def _send_button_press(
        self, *, motor_value: int = 0, control_value: int = 0
    ) -> None:
        """Send a short app-style button press."""
        await self._send_repeated_command(
            motor_value=motor_value,
            control_value=control_value,
            repeat_count=_BUTTON_PRESS_REPEAT_COUNT,
            repeat_delay_ms=_BUTTON_PRESS_REPEAT_DELAY_MS,
        )

    # Motor control - Back/Head (primary)

    async def move_head_up(self) -> None:
        """Move head/back up."""
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head/back down."""
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head/back motor."""
        await self._move_motor("back", None)

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._move_motor("back", None)

    # Motor control - Legs/Feet

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("legs", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("legs", None)

    # Motor control - Tilt (head tilt / 4th motor)

    async def move_tilt_up(self) -> None:
        """Move head tilt up."""
        await self._move_motor("head", CstMotorCommands.HEAD_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Move head tilt down."""
        await self._move_motor("head", CstMotorCommands.HEAD_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._move_motor("head", None)

    # Motor control - Lumbar

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._move_motor("lumbar", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self._send_stop_sequence()

    # Presets

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset(CstRemoteCommands.FLAT)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_preset(CstRemoteCommands.ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._send_preset(CstRemoteCommands.ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self._send_preset(CstRemoteCommands.LOUNGE)

    async def preset_incline(self) -> None:
        """Go to incline/TV position."""
        await self._send_preset(CstRemoteCommands.INCLINE)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        if memory_num == 1:
            await self._send_preset(CstRemoteCommands.MEMORY_1)
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1)", memory_num)

    async def program_memory(self, memory_num: int) -> None:  # noqa: ARG002
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "CSTProtocol beds don't support programming memory presets via BLE"
        )

    # Lights

    async def lights_on(self) -> None:
        """Turn on lights."""
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_ON)

    async def lights_off(self) -> None:
        """Turn off lights."""
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_OFF)

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self._send_button_press(motor_value=CstRemoteCommands.LIGHT_TOGGLE)

    # Massage

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_OFF)

    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_TOGGLE)

    async def massage_intensity_up(self) -> None:
        """Increase overall massage intensity."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_INTENSITY)

    async def massage_intensity_down(self) -> None:
        """Decrease overall massage intensity."""
        await self._send_button_press(
            motor_value=CstRemoteCommands.MASSAGE_INTENSITY_MINUS
        )

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_HEAD)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self._send_button_press(
            motor_value=CstRemoteCommands.MASSAGE_HEAD_MINUS
        )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_FEET)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self._send_button_press(
            motor_value=CstRemoteCommands.MASSAGE_FEET_MINUS
        )

    async def massage_mode_step(self) -> None:
        """Step through massage wave modes."""
        commands = (
            CstRemoteCommands.MASSAGE_WAVE_1,
            CstRemoteCommands.MASSAGE_WAVE_2,
            CstRemoteCommands.MASSAGE_WAVE_3,
        )
        command = commands[self._massage_wave_index]
        self._massage_wave_index = (self._massage_wave_index + 1) % len(commands)
        await self._send_button_press(control_value=command)
