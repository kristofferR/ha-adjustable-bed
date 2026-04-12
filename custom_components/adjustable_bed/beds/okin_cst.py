"""OKIN CSTProtocol bed controller implementation.

CSTProtocol uses a 14-byte command format with two separate 32-bit fields:
- Motor field (bytes 2-5): Head, foot, tilt, lumbar motor control
- Control field (bytes 6-9): Presets, massage, lights

Format: [0x0C, 0x02, motor[4], control[4], 0x00, 0x00, 0x00, 0x00]

Command values are identical to existing OKIN UUID values. Only the packet
framing differs (14-byte with dual fields vs 6-byte with single field).

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
    DEFAULT_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FOOT_MAX_ANGLE,
    OKIN_FOOT_MAX_RAW,
    OKIN_HEAD_MAX_ANGLE,
    OKIN_HEAD_MAX_RAW,
    OKIN_POSITION_NOTIFY_CHAR_UUID,
)
from .base import BedController, MotorControlSpec
from .okin_protocol import build_cst_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_NOT_CONNECTED_MSG = "Not connected to bed"


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


class CstControlCommands:
    """Control field command values (bytes 6-9)."""

    STOP = 0x00000000
    FLAT = 0x08000000
    ZERO_G = 0x00001000
    MEMORY_1 = 0x00002000
    MEMORY_2 = 0x00004000
    MEMORY_3 = 0x00008000
    MEMORY_4 = 0x00010000
    LIGHT_TOGGLE = 0x00020000
    MASSAGE_ON_OFF = 0x04000000
    MASSAGE_STOP = 0x02000000
    MASSAGE_HEAD = 0x00000800
    MASSAGE_FEET = 0x00000400
    MASSAGE_WAIST = 0x00400000
    MASSAGE_TIMER = 0x00000200
    MASSAGE_HEAD_MINUS = 0x00800000
    MASSAGE_FEET_MINUS = 0x01000000
    MASSAGE_WAIST_MINUS = 0x10000000
    MASSAGE_WAVE_1 = 0x00080000
    MASSAGE_WAVE_2 = 0x00100000


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
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 4

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
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_position_feedback(self) -> bool:
        """Return True - Okin CST exposes position readback packets."""
        return True

    @property
    def passive_position_reconciliation_interval(self) -> float | None:
        """Allow conservative idle refresh for Okin CST position reads."""
        return DEFAULT_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose the CST motor surface without synthetic head/feet aliases."""
        return (
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                position_key="back",
                max_angle=68,
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                position_key="legs",
                max_angle=45,
            ),
            MotorControlSpec(
                key="tilt",
                translation_key="tilt",
                open_fn=lambda ctrl: ctrl.move_tilt_up(),
                close_fn=lambda ctrl: ctrl.move_tilt_down(),
                stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                max_angle=45,
            ),
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                max_angle=30,
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove legacy alias entities replaced by the canonical back/legs surface."""
        return frozenset({"head", "feet"})

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
                await self.write_command(
                    build_cst_command(),
                    cancel_event=asyncio.Event(),
                )

    async def _send_control(
        self,
        control_value: int,
        repeat_count: int = 100,
        repeat_delay_ms: int = 300,
    ) -> None:
        """Send a control command (preset/massage/light) with stop cleanup."""
        try:
            await self.write_command(
                build_cst_command(control_value=control_value),
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
            )
        finally:
            try:
                await self.write_command(
                    build_cst_command(),
                    cancel_event=asyncio.Event(),
                )
            except (TimeoutError, BleakError):
                _LOGGER.debug("Failed to send STOP during control cleanup", exc_info=True)

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
        await self.write_command(
            build_cst_command(),
            cancel_event=asyncio.Event(),
        )

    # Presets

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_control(CstControlCommands.FLAT)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_control(CstControlCommands.ZERO_G)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: CstControlCommands.MEMORY_1,
            2: CstControlCommands.MEMORY_2,
            3: CstControlCommands.MEMORY_3,
            4: CstControlCommands.MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self._send_control(command)
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-4)", memory_num)

    async def program_memory(self, memory_num: int) -> None:  # noqa: ARG002
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "CSTProtocol beds don't support programming memory presets via BLE"
        )

    # Lights

    async def lights_on(self) -> None:
        """Turn on lights (via toggle)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (via toggle)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.LIGHT_TOGGLE),
        )

    # Massage

    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_ON_OFF),
        )

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_HEAD),
        )

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_HEAD_MINUS),
        )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_FEET),
        )

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_FEET_MINUS),
        )

    async def massage_mode_step(self) -> None:
        """Step through massage wave modes."""
        await self.write_command(
            build_cst_command(control_value=CstControlCommands.MASSAGE_WAVE_1),
        )
