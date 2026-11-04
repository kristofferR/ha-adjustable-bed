"""Reverie bed controller implementation (Protocol 108).

Reverse engineering by Vitaliy and Richard Hopton (smartbed-mqtt).
Protocol verified against Service108.java and BLEManager.java from com.reverie.reverie APK.

Reverie beds use a protocol with XOR checksum:
Command format: [0x55, ...bytes, XOR_checksum]
where checksum = bytes XOR'd together XOR 0x55

Supports both position-based motor control (0-100%) and linear motor commands.
Position notifications are 9-byte packets containing head/foot position and wave levels.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from bleak.exc import BleakError

from ..const import REVERIE_BACK_MAX_ANGLE, REVERIE_CHAR_UUID
from ..execution import ExecutionCapabilities
from .base import (
    POSITION_UNIT_DEGREES,
    BedController,
    ControllerMotorHoldSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .reverie_comfort import ReverieComfortRequest, validate_comfort_request
from .reverie_profiles import (
    REVERIE_MODEL_FALLBACK,
    ReverieModelProfile,
    resolve_reverie_model,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class ReverieCommands:
    """Reverie command constants.

    Verified from Service108.java in com.reverie.reverie APK.
    """

    # Linear motor commands (ref: Service108.headPositionLinearAdd etc.)
    HEAD_UP: ClassVar[list[int]] = [0x01]
    FOOT_UP: ClassVar[list[int]] = [0x02]
    HEAD_DOWN: ClassVar[list[int]] = [0x03]
    FOOT_DOWN: ClassVar[list[int]] = [0x04]

    # Stop all massage (ref: Service108.stopMassage)
    STOP_MASSAGE: ClassVar[list[int]] = [0x35]

    # Presets
    PRESET_ZERO_G: ClassVar[list[int]] = [0x15]
    PRESET_ANTI_SNORE: ClassVar[list[int]] = [0x16]
    PRESET_FLAT: ClassVar[list[int]] = [0x05]
    PRESET_MEMORY_1: ClassVar[list[int]] = [0x11]
    PRESET_MEMORY_2: ClassVar[list[int]] = [0x12]
    PRESET_MEMORY_3: ClassVar[list[int]] = [0x13]
    PRESET_MEMORY_4: ClassVar[list[int]] = [0x14]

    # Programming
    PROGRAM_MEMORY_1: ClassVar[list[int]] = [0x21]
    PROGRAM_MEMORY_2: ClassVar[list[int]] = [0x22]
    PROGRAM_MEMORY_3: ClassVar[list[int]] = [0x23]
    PROGRAM_MEMORY_4: ClassVar[list[int]] = [0x24]

    # Lighting
    LIGHTS_TOGGLE: ClassVar[list[int]] = [0x5B, 0x00]

    # Motor stop
    MOTOR_STOP: ClassVar[list[int]] = [0xFF]

    @staticmethod
    def massage_head(level: int) -> list[int]:
        """Create the level-times-four head massage command (0-10)."""
        return [0x53, level * 4]

    @staticmethod
    def massage_foot(level: int) -> list[int]:
        """Create the level-times-four foot massage command (0-10)."""
        return [0x54, level * 4]

    @staticmethod
    def massage_wave(level: int) -> str:
        """Keep Service108's decimal text appended to the command prefix."""
        if isinstance(level, bool) or not isinstance(level, int) or level < 0:
            raise ValueError("Reverie wave command must be a non-negative integer")
        return f"4{level}"

    @staticmethod
    def motor_head(position: int) -> list[int]:
        """Move head motor to position (0-100)."""
        return [0x51, position]

    @staticmethod
    def motor_feet(position: int) -> list[int]:
        """Move feet motor to position (0-100)."""
        return [0x52, position]


class ReverieController(BedController):
    """Controller for Reverie beds."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, model: str | None = None
    ) -> None:
        """Initialize the Protocol 108 controller with its model profile."""
        super().__init__(coordinator)
        self.model_id = model or REVERIE_MODEL_FALLBACK
        self.model: ReverieModelProfile = resolve_reverie_model(self.model_id)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._notify_active = False
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_wave_level = 0
        self._last_notification_hex: str | None = None
        self._comfort_request: ReverieComfortRequest | None = None
        self._comfort_writes: deque[tuple[list[int], int]] = deque()
        self._comfort_sample: bytes | None = None
        self._last_position_sample: bytes | None = None
        self._comfort_sample_stable = False
        self._comfort_sequence = 0
        self._comfort_advance_queued = False
        self._comfort_pending_sample: bytes | None = None
        self._comfort_last_progress_at: float | None = None
        self._comfort_delay_seconds = 0.0
        self._comfort_ready_generation = 0
        self._comfort_connection_release: Callable[[], None] | None = None
        self._diagnostic_timer: asyncio.TimerHandle | None = None
        self._diagnostic_connection_release: Callable[[], None] | None = None
        self._routine_timer: asyncio.TimerHandle | None = None
        self._routine_steps: list[tuple[ReverieComfortRequest, int]] = []
        self._routine_generation = 0
        self._routine_connection_release: Callable[[], None] | None = None
        _LOGGER.debug("ReverieController initialized")

    @property
    def execution(self) -> ExecutionCapabilities:
        """One press frame, then a per-axis STOP at release (#483)."""
        return ExecutionCapabilities(hold="latched")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return REVERIE_CHAR_UUID

    @property
    def motor_max_angles(self) -> dict[str, float]:
        """Reverie frames stop the head/back axis short of the standard 68 degrees."""
        return {"back": REVERIE_BACK_MAX_ANGLE, "head": REVERIE_BACK_MAX_ANGLE}

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_flat(self) -> bool:
        return self.model.presets

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Reverie beds support memory presets (slots 1-4)."""
        return self.model.memory_positions

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Reverie beds support memory slots 1-4."""
        return 4 if self.model.memory_positions else 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Reverie beds support programming memory positions."""
        return self.model.memory_positions

    @property
    def supports_lights(self) -> bool:
        """Return True - Reverie beds support under-bed lighting."""
        return self.model.nightlight

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Reverie only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.model.nightlight

    @property
    def supports_motor_control(self) -> bool:
        return self.model.positions

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self.model.positions:
            return ()
        return (
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                position_key="back",
                max_angle=REVERIE_BACK_MAX_ANGLE,
                hold=ControllerMotorHoldSpec("back_up", "back_down", stop_scope="side"),
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                position_key="legs",
                max_angle=45,
                hold=ControllerMotorHoldSpec("legs_up", "legs_down", stop_scope="side"),
            ),
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        if not self.model.positions:
            return ()
        return ("back_up", "back_down", "legs_up", "legs_down")

    @property
    def supports_position_feedback(self) -> bool:
        return self.model.positions

    @property
    def requires_notification_channel(self) -> bool:
        return self.model.positions

    @property
    def supports_direct_position_control(self) -> bool:
        """Return True - Reverie beds support direct position commands."""
        return self.model.positions

    # Massage intensity control - Reverie supports direct level setting (0-10)
    @property
    def supports_massage_intensity_control(self) -> bool:
        """Return True - Reverie supports setting massage intensity directly."""
        return self.model.massage

    @property
    def supports_massage(self) -> bool:
        return self.model.massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.model.massage

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.model.massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.model.massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.model.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.model.massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        """Return zones with direct intensity control: head, foot, wave."""
        return ["head", "foot", "wave"] if self.model.massage else []

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if not self.model.positions:
            return ()
        return (
            build_position_number_spec(
                "back",
                max_value=self._coordinator.get_max_angle("back"),
                unit=POSITION_UNIT_DEGREES,
            ),
            build_position_number_spec(
                "legs",
                max_value=self._coordinator.get_max_angle("legs"),
                unit=POSITION_UNIT_DEGREES,
            ),
        )

    @property
    def massage_intensity_max(self) -> int:
        """Retain the shared legacy HA slider ceiling, not a wave wire limit."""
        return 10

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        """Convert angle to Reverie's native 0-100 position.

        Reverses the angle conversion from _parse_position_data:
        - back: angle = position * 0.6, so position = angle / 0.6
        - legs: angle = position * 0.45, so position = angle / 0.45
        """
        if motor in ("head", "back"):
            position = angle / 0.6
        elif motor in ("feet", "legs"):
            position = angle / 0.45
        else:
            position = angle  # Fallback: assume 1:1

        # Clamp to valid range
        return max(0, min(100, int(round(position))))

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor to a specific position (0-100).

        Reverie supports direct position control via motor_head/motor_feet commands.
        This is more efficient than incremental seeking for position number entities.

        Args:
            motor: Motor name ("head", "back", "legs", "feet")
            position: Target position as percentage (0=flat, 100=max)
        """
        # Normalize motor names: back->head, legs->feet for Reverie
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no position controls")
        if motor in ("head", "back"):
            cmd = ReverieCommands.motor_head(position)
        elif motor in ("feet", "legs"):
            cmd = ReverieCommands.motor_feet(position)
        else:
            raise ValueError(f"Unknown motor {motor} for Reverie position control")
        await self.write_command(self._build_command(cmd))

    def _build_command(self, command_bytes: list[int] | str) -> bytes:
        """Build command with XOR checksum.

        Format: [0x55, ...bytes, checksum]
        Checksum = all bytes XOR'd together XOR 0x55
        """
        if isinstance(command_bytes, str):
            # BLE108CRC parses the whole command text as a Java signed int;
            # hex2Byte then consumes complete pairs, dropping an odd final digit.
            command = int(command_bytes, 16)
            if not 0 <= command <= 0x7FFFFFFF:
                raise ValueError("Reverie command text does not fit a Java integer")
            encoded = f"55{command_bytes}{0x55 ^ command:02x}"
            return bytes.fromhex(encoded[: len(encoded) // 2 * 2])
        checksum = 0x55
        for b in command_bytes:
            checksum ^= b
        return bytes([0x55] + command_bytes + [checksum])

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
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to Reverie bed (%s): %s (repeat: %d, delay: %dms, response=True)",
            REVERIE_CHAR_UUID,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        self._record_command_trace(
            REVERIE_CHAR_UUID,
            command,
            response=True,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                async with self._ble_lock:
                    if effective_cancel is not None and effective_cancel.is_set():
                        return
                    await self.client.write_gatt_char(REVERIE_CHAR_UUID, command, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if not self.model.positions:
            return

        if self._notify_active:
            return

        # Reverie uses the same characteristic for write and notify
        if self.client is None or not self.client.is_connected:
            return

        try:

            def handler(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Reverie notification: %s", data.hex())
                self.forward_raw_notification(REVERIE_CHAR_UUID, bytes(data))
                self._parse_position_data(data)

            async with self._ble_lock:
                await self.client.start_notify(REVERIE_CHAR_UUID, handler)
            self._notify_active = True
            _LOGGER.debug("Started Reverie notifications")
        except BleakError:
            _LOGGER.exception("Could not start Reverie notifications")
            self._notify_callback = None
            self._notify_active = False
            raise

    def _parse_position_data(self, data: bytearray) -> None:
        """Parse 9-byte position notification from Protocol 108.

        Verified from BLEManager.m608xa6c5dfcb in com.reverie.reverie APK.
        Notification format (9 bytes / 18 hex chars):
        - Bytes 0-1: Header (unknown)
        - Byte 2: Head position (0-100)
        - Byte 3: Foot position (0-100)
        - Byte 4: Head wave/massage level
        - Byte 5: Foot wave/massage level
        - Bytes 6-8: Unknown
        """
        if len(data) != 9:
            return

        self._last_position_sample = bytes(data)
        if self._comfort_request is not None:
            self._handle_comfort_notification(data)

        # Deduplicate identical notifications (matches APK behavior)
        hex_str = data.hex()
        if hex_str == self._last_notification_hex:
            return
        self._last_notification_hex = hex_str

        head_position = data[2]
        foot_position = data[3]
        head_wave = data[4] // 4
        foot_wave = data[5] // 4

        _LOGGER.debug(
            "Reverie position update: head=%d%%, foot=%d%%, head_wave=%d, foot_wave=%d",
            head_position,
            foot_position,
            head_wave,
            foot_wave,
        )

        # Update internal massage state from device feedback
        self._massage_head_level = head_wave
        self._massage_foot_level = foot_wave
        self.forward_controller_state_updates(
            {
                "reverie_head_position": head_position,
                "reverie_foot_position": foot_position,
                "massage_head_intensity": head_wave,
                "massage_foot_intensity": foot_wave,
                "reverie_wave_level": self._massage_wave_level,
            }
        )

        if self._notify_callback:
            self._notify_callback("back", head_position * 0.6)
            self._notify_callback("legs", foot_position * 0.45)

    def _cancel_comfort_progression(self) -> None:
        self._comfort_sequence += 1
        self._comfort_request = None
        self._comfort_writes.clear()
        self._comfort_sample = None
        self._comfort_sample_stable = False
        self._comfort_advance_queued = False
        self._comfort_pending_sample = None
        self._comfort_last_progress_at = None
        self._comfort_delay_seconds = 0.0
        self._comfort_ready_generation = 0
        release = self._comfort_connection_release
        self._comfort_connection_release = None
        if release is not None:
            release()

    def _comfort_now(self) -> float:
        """Read monotonic time through a narrow seam for exact fake-clock tests."""
        return self._coordinator.hass.loop.time()

    def _handle_comfort_notification(self, data: bytearray) -> None:
        sample = bytes(data)
        if sample != self._comfort_sample:
            self._comfort_sample = sample
            self._comfort_sample_stable = False
            self._comfort_last_progress_at = self._comfort_now()
            self._comfort_pending_sample = None
            return

        self._comfort_sample_stable = True
        if not self._comfort_writes:
            return
        now = self._comfort_now()
        if (
            self._comfort_last_progress_at is not None
            and now - self._comfort_last_progress_at <= self._comfort_delay_seconds
        ):
            return
        self._comfort_last_progress_at = now
        self._comfort_delay_seconds = 2.0
        self._comfort_ready_generation += 1
        self._comfort_pending_sample = sample
        if self._comfort_advance_queued:
            return
        sequence = self._comfort_sequence
        self._comfort_advance_queued = True
        self._coordinator.hass.async_create_task(
            self._run_comfort_write(sequence, sample),
            "adjustable_bed.reverie_comfort_step",
        )

    async def _run_comfort_write(self, sequence: int, sample: bytes) -> None:
        """Consume the latest eligible sample inside the existing command lane."""
        if sequence != self._comfort_sequence:
            return
        written_index: int | None = None
        consumed_generation: int | None = None
        visited_current_controller = False

        async def write(controller: BedController) -> None:
            nonlocal written_index, consumed_generation, visited_current_controller
            if controller is not self or sequence != self._comfort_sequence:
                return
            visited_current_controller = True
            current = self._comfort_pending_sample
            if (
                current is None
                or not self._comfort_sample_stable
                or self._comfort_sample != current
                or self._comfort_request is None
            ):
                return
            consumed_generation = self._comfort_ready_generation
            values: dict[tuple[int, ...], int] = {
                (0x51,): current[2],
                (0x52,): current[3],
                (0x53,): current[4],
                (0x54,): current[5],
            }
            for index, (command, value) in enumerate(self._comfort_writes):
                key = tuple(command)
                if key not in values:
                    self._cancel_comfort_progression()
                    raise RuntimeError("Unknown Protocol 108 comfort progression command")
                if values[key] != value:
                    await self.write_command(self._build_command(command + [value]))
                    written_index = index
                    return
            self._comfort_writes.clear()
            self._comfort_request = None

        try:
            await self._coordinator.async_execute_controller_command(
                write,
                cancel_running=False,
                resource="reverie:comfort",
                read_positions_after_operation=False,
            )
        except asyncio.CancelledError:
            if sequence == self._comfort_sequence:
                self._cancel_comfort_progression()
            raise
        except Exception:
            _LOGGER.exception("Reverie comfort setting write failed; stopping progression")
            if sequence == self._comfort_sequence:
                self._cancel_comfort_progression()
            raise
        if sequence != self._comfort_sequence:
            return
        if not visited_current_controller:
            self._cancel_comfort_progression()
            return
        if written_index is not None:
            del self._comfort_writes[written_index]
        pending = self._comfort_pending_sample
        replay_ready = (
            visited_current_controller
            and pending is not None
            and self._comfort_sample_stable
            and pending == self._comfort_sample
            and consumed_generation != self._comfort_ready_generation
        )
        self._comfort_advance_queued = False
        if not self._comfort_writes:
            self._cancel_comfort_progression()
        elif replay_ready and pending is not None:
            self._comfort_advance_queued = True
            self._coordinator.hass.async_create_task(
                self._run_comfort_write(sequence, pending),
                "adjustable_bed.reverie_comfort_step",
            )
            return
        self._comfort_pending_sample = None

    def validate_comfort_request(self, request: ReverieComfortRequest) -> None:
        if not self.model.comfort_settings:
            raise ValueError(f"Model {self.model_id} has no comfort settings")
        self._validate_composer_values(request)

    def _validate_composer_values(self, request: ReverieComfortRequest) -> None:
        if request.force:
            raise ValueError("Protocol 108 does not define forced comfort writes")
        validate_comfort_request(
            request,
            supported_fields=frozenset(
                {
                    "head_position",
                    "foot_position",
                    "head_massage",
                    "foot_massage",
                }
            ),
        )

    async def async_set_comfort(self, request: ReverieComfortRequest) -> None:
        """Stop massage, then apply changed values after stable state feedback."""
        self.validate_comfort_request(request)
        await self._apply_composer_values(request)

    async def _apply_composer_values(self, request: ReverieComfortRequest) -> None:
        self._cancel_comfort_progression()
        await self.write_command(self._build_command(ReverieCommands.STOP_MASSAGE))

        requested = (
            ("head_position", [0x51], request.head_position),
            ("foot_position", [0x52], request.foot_position),
            ("head_massage", [0x53], request.head_massage),
            ("foot_massage", [0x54], request.foot_massage),
        )
        self._comfort_writes = deque(
            (command, value)
            for key, command, value in requested
            if value is not None
        )
        if self._comfort_writes:
            context = self._coordinator.hold_command_connection()
            context.__enter__()

            def release() -> None:
                context.__exit__(None, None, None)

            self._comfort_connection_release = release
            self._comfort_request = request
            self._comfort_sample = None
            self._comfort_sample_stable = False

    def validate_routine(
        self, steps: list[tuple[ReverieComfortRequest | None, int]]
    ) -> None:
        if not self.model.routines:
            raise ValueError(f"Model {self.model_id} has no routines")
        for request, duration_minutes in steps:
            if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
                raise ValueError("Routine step duration must be an integer number of minutes")
            if request is None:
                break
            self._validate_composer_values(request)

    async def async_start_diagnostic(self) -> None:
        """Start the ten-second Protocol 108 direct BLE test route."""
        self.validate_diagnostic()
        self._cancel_diagnostic()
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._diagnostic_connection_release = release
        self._diagnostic_timer = self._coordinator.hass.loop.call_later(
            10, self._enqueue_diagnostic_stop, release
        )
        failures: list[Exception] = []
        for command in ([0x5B, 0x00], [0x41]):
            try:
                await self.write_command(self._build_command(command))
            except Exception as err:
                failures.append(err)
                _LOGGER.exception("Reverie Protocol 108 diagnostic start write failed")
        if failures:
            raise ExceptionGroup("Reverie diagnostic start writes failed", failures)

    def validate_diagnostic(self) -> None:
        if not self.model.nightlight or not self.model.massage:
            raise ValueError("Protocol 108 diagnostic test requires lights and massage")

    def _cancel_diagnostic(self) -> None:
        if self._diagnostic_timer is not None:
            self._diagnostic_timer.cancel()
            self._diagnostic_timer = None
        release = self._diagnostic_connection_release
        self._diagnostic_connection_release = None
        if release is not None:
            release()

    def _enqueue_diagnostic_stop(self, release: Callable[[], None]) -> None:
        if release is not self._diagnostic_connection_release:
            return
        self._diagnostic_timer = None
        self._coordinator.hass.async_create_task(
            self._stop_diagnostic(release), "adjustable_bed.reverie_diagnostic_stop"
        )

    async def _stop_diagnostic(self, release: Callable[[], None] | None = None) -> None:
        if release is None:
            release = self._diagnostic_connection_release
        failures: list[Exception] = []
        async def write_stops(controller: BedController) -> None:
            if controller is not self or release is not self._diagnostic_connection_release:
                return
            for command in ([0x35], [0x5B, 0x00]):
                try:
                    await self.write_command(
                        self._build_command(command), cancel_event=asyncio.Event()
                    )
                except Exception as err:
                    failures.append(err)
                    _LOGGER.exception(
                        "Reverie Protocol 108 diagnostic stop write failed"
                    )

        try:
            await self._coordinator.async_execute_controller_command(
                write_stops,
                cancel_running=False,
                resource="reverie:diagnostic",
                read_positions_after_operation=False,
            )
        finally:
            if release is self._diagnostic_connection_release:
                self._cancel_diagnostic()
        if failures:
            raise ExceptionGroup("Reverie diagnostic stop writes failed", failures)

    def on_disconnect(self) -> None:
        self._cancel_comfort_progression()
        self._cancel_diagnostic()
        self._cancel_routine()
        super().on_disconnect()

    async def async_start_routine(
        self, steps: list[tuple[ReverieComfortRequest | None, int]]
    ) -> None:
        """Replace the physical address routine queue and run its first item."""
        self.validate_routine(steps)
        if self.client is None or not self.client.is_connected:
            return
        self._cancel_routine()
        stopped_on_missing = False
        for request, duration in steps:
            if request is None:
                stopped_on_missing = True
                break
            self._routine_steps.append((request, duration))
        if stopped_on_missing or not self._routine_steps:
            return
        self._hold_routine_connection()
        await self._run_routine_step(self._routine_generation)

    def _hold_routine_connection(self) -> None:
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._routine_connection_release = release

    def _release_routine_connection(self) -> None:
        release = self._routine_connection_release
        self._routine_connection_release = None
        if release is not None:
            release()

    def _cancel_routine(self) -> None:
        self._cancel_comfort_progression()
        self._routine_generation += 1
        if self._routine_timer is not None:
            self._routine_timer.cancel()
            self._routine_timer = None
        self._routine_steps.clear()
        self._release_routine_connection()

    async def _run_routine_step(self, generation: int) -> None:
        if generation != self._routine_generation:
            return
        if not self._routine_steps:
            self._routine_timer = None
            self._release_routine_connection()
            return
        request, duration_minutes = self._routine_steps.pop(0)
        assert request is not None
        self._routine_timer = self._coordinator.hass.loop.call_later(
            duration_minutes * 60,
            self._enqueue_routine_step,
            generation,
        )
        try:
            await self._apply_composer_values(request)
        except BaseException:
            self._cancel_routine()
            raise

    def _enqueue_routine_step(self, generation: int) -> None:
        self._routine_timer = None

        async def execute(controller: BedController) -> None:
            if controller is self and generation == self._routine_generation:
                await self._run_routine_step(generation)

        self._coordinator.hass.async_create_task(
            self._coordinator.async_execute_controller_command(
                execute,
                cancel_running=False,
                resource="reverie:routine",
                read_positions_after_operation=False,
            ),
            "adjustable_bed.reverie_routine_step",
        )

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            self._notify_callback = None
            self._notify_active = False
            return
        try:
            async with self._ble_lock:
                await self.client.stop_notify(REVERIE_CHAR_UUID)
        except BleakError:
            _LOGGER.exception("Could not stop Reverie notifications")
            raise
        finally:
            self._notify_callback = None
            self._notify_active = False

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Reverie beds report positions via notifications, not direct reads.
        Position updates are handled by _parse_position_data via start_notify.
        """
        if not self.model.positions:
            return

    async def _move_linear(
        self,
        command_bytes: list[int],
    ) -> None:
        """Send one press frame; explicit STOP is the release frame."""
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no motor controls")
        await self.write_command(self._build_command(command_bytes))

    async def _send_stop(self) -> None:
        """Send motor stop command."""
        self._cancel_comfort_progression()
        await self.write_command(
            self._build_command(ReverieCommands.MOTOR_STOP),
            cancel_event=asyncio.Event(),
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported Reverie held control: {control}")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise ValueError("Reverie hold duration must be an integer number of milliseconds")
        if not 100 <= duration_ms <= 60_000:
            raise ValueError("Reverie hold duration must be between 100 and 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Send one press frame, wait for the bounded hold, then send fresh STOP."""
        self.validate_hold_control(control, duration_ms)
        command = {
            "back_up": ReverieCommands.HEAD_UP,
            "back_down": ReverieCommands.HEAD_DOWN,
            "legs_up": ReverieCommands.FOOT_UP,
            "legs_down": ReverieCommands.FOOT_DOWN,
        }[control]
        try:
            await self._move_linear(command)
            # STOP, a replacement or a renewable hold's expiry ends the wait.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._coordinator.cancel_command.wait(), duration_ms / 1000)
        except BaseException as operation_error:
            try:
                await self._send_stop()
            except BaseException as release_error:
                raise BaseExceptionGroup(
                    "Reverie hold and STOP both failed",
                    [operation_error, release_error],
                ) from operation_error
            raise
        else:
            await self._send_stop()

    # Motor control methods - uses linear commands (ref: Service108.java)
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_linear(ReverieCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_linear(ReverieCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_linear(ReverieCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_linear(ReverieCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._cancel_routine()
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._write_preset(ReverieCommands.PRESET_FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: ReverieCommands.PRESET_MEMORY_1,
            2: ReverieCommands.PRESET_MEMORY_2,
            3: ReverieCommands.PRESET_MEMORY_3,
            4: ReverieCommands.PRESET_MEMORY_4,
        }
        if not self.model.memory_positions or memory_num not in commands:
            raise ValueError("This model does not support the requested memory slot")
        await self.write_command(self._build_command(commands[memory_num]))

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: ReverieCommands.PROGRAM_MEMORY_1,
            2: ReverieCommands.PROGRAM_MEMORY_2,
            3: ReverieCommands.PROGRAM_MEMORY_3,
            4: ReverieCommands.PROGRAM_MEMORY_4,
        }
        if not self.model.memory_positions or memory_num not in commands:
            raise ValueError("This model does not support the requested memory slot")
        await self.write_command(self._build_command(commands[memory_num]))

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        if not self.model.nightlight:
            raise ValueError(f"Model {self.model_id} has no under-bed lights")
        await self.write_command(self._build_command(ReverieCommands.LIGHTS_TOGGLE))

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off all massage (ref: Service108.stopMassage, command 0x35)."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        await self.write_command(self._build_command(ReverieCommands.STOP_MASSAGE))
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_wave_level = 0
        self.forward_controller_state_updates(
            {
                "massage_head_intensity": 0,
                "massage_foot_intensity": 0,
                "reverie_wave_level": 0,
            }
        )

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = min(10, self._massage_head_level + 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_head(level))
        )
        self._massage_head_level = level
        self.forward_controller_state_update("massage_head_intensity", self._massage_head_level)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = max(0, self._massage_head_level - 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_head(level))
        )
        self._massage_head_level = level
        self.forward_controller_state_update("massage_head_intensity", self._massage_head_level)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = min(10, self._massage_foot_level + 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_foot(level))
        )
        self._massage_foot_level = level
        self.forward_controller_state_update("massage_foot_intensity", self._massage_foot_level)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = max(0, self._massage_foot_level - 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_foot(level))
        )
        self._massage_foot_level = level
        self.forward_controller_state_update("massage_foot_intensity", self._massage_foot_level)

    async def massage_mode_step(self) -> None:
        """Send the next wave level without assuming a device cycle or clamp."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        next_level = self._massage_wave_level + 1
        command = self._build_command(ReverieCommands.massage_wave(next_level))
        await self.write_command(command)
        self._massage_wave_level = next_level
        self.forward_controller_state_update("reverie_wave_level", next_level)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._write_preset(ReverieCommands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._write_preset(ReverieCommands.PRESET_ANTI_SNORE)

    async def _write_preset(self, command: list[int]) -> None:
        if not self.model.presets:
            raise ValueError(f"Model {self.model_id} has no preset modes")
        await self.write_command(self._build_command(command))

    # Direct massage intensity control
    async def set_massage_intensity(self, zone: str, level: int) -> None:
        """Set massage intensity for a specific zone.

        Args:
            zone: "head", "foot", or "wave"
            level: 0-10 (0 = off)
        """
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        if zone == "head":
            if not 0 <= level <= 10:
                raise ValueError("Reverie massage strength must be 0-10")
            await self.write_command(self._build_command(ReverieCommands.massage_head(level)))
            self._massage_head_level = level
            self.forward_controller_state_update("massage_head_intensity", level)
        elif zone == "foot":
            if not 0 <= level <= 10:
                raise ValueError("Reverie massage strength must be 0-10")
            await self.write_command(self._build_command(ReverieCommands.massage_foot(level)))
            self._massage_foot_level = level
            self.forward_controller_state_update("massage_foot_intensity", level)
        elif zone == "wave":
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("Reverie wave level must be an integer")
            await self.write_command(self._build_command(ReverieCommands.massage_wave(level)))
            self._massage_wave_level = level
            self.forward_controller_state_update("reverie_wave_level", level)
        else:
            _LOGGER.warning("Unknown massage zone: %s", zone)

    def get_massage_state(self) -> dict[str, Any]:
        """Return current massage state from internal tracking.

        Returns:
            dict with head_intensity, foot_intensity, wave_intensity
        """
        return {
            "head_intensity": self._massage_head_level,
            "foot_intensity": self._massage_foot_level,
            "wave_intensity": self._massage_wave_level,
        }
