"""Linak bed controller implementation.

Reverse engineering by jascdk and Richard Hopton (smartbed-mqtt).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    LINAK_BACK_MAX_POSITION,
    LINAK_CONTROL_CHAR_UUID,
    LINAK_FEET_MAX_POSITION,
    LINAK_HEAD_MAX_POSITION,
    LINAK_LEG_MAX_POSITION,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_HEAD_UUID,
    LINAK_POSITION_LEG_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

LINAK_CONTROL_READY_TIMEOUT_S = 6.0
LINAK_CONTROL_READY_RETRY_DELAY_S = 0.75
LINAK_INITIAL_POSITION_RETRY_ATTEMPTS = 3
LINAK_INITIAL_POSITION_RETRY_DELAY_S = 0.75
LINAK_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S = 120.0
LINAK_POSITION_SEEK_PULSE_DELAY_MS = 100
LINAK_POSITION_SEEK_TOLERANCE = 0.75
LINAK_POSITION_SEEK_STALL_COUNT = 1
LINAK_POSITION_SEEK_CHECK_INTERVAL_S = 0.2
LINAK_POSITION_SEEK_STALL_THRESHOLD = 0.2
LINAK_COARSE_SEEK_DISTANCE_DEGREES = 20.0
LINAK_MEDIUM_SEEK_DISTANCE_DEGREES = 10.0
LINAK_FINE_SEEK_DISTANCE_DEGREES = 4.0
LINAK_CHAINED_SEEK_MIN_REMAINING_DEGREES = LINAK_FINE_SEEK_DISTANCE_DEGREES
LINAK_COARSE_SEEK_PULSE_COUNT = 6
LINAK_MEDIUM_SEEK_PULSE_COUNT = 4
LINAK_FINE_SEEK_PULSE_COUNT = 2
LINAK_MICRO_SEEK_PULSE_COUNT = 1


@dataclass(frozen=True, slots=True)
class LinakPositionSpec:
    """Describe a Linak position characteristic and the logical axis it backs."""

    axis_name: str
    source_name: str
    uuid: str
    max_position: int
    max_angle: float


class LinakCommands:
    """Linak command constants."""

    # Presets
    PRESET_MEMORY_1 = bytes([0x0E, 0x00])
    PRESET_MEMORY_2 = bytes([0x0F, 0x00])
    PRESET_MEMORY_3 = bytes([0x0C, 0x00])
    PRESET_MEMORY_4 = bytes([0x44, 0x00])
    PRESET_MEMORY_5 = bytes([0x83, 0x00])
    PRESET_MEMORY_6 = bytes([0x84, 0x00])

    # Program presets
    PROGRAM_MEMORY_1 = bytes([0x38, 0x00])
    PROGRAM_MEMORY_2 = bytes([0x39, 0x00])
    PROGRAM_MEMORY_3 = bytes([0x3A, 0x00])
    PROGRAM_MEMORY_4 = bytes([0x45, 0x00])
    PROGRAM_MEMORY_5 = bytes([0x85, 0x00])
    PROGRAM_MEMORY_6 = bytes([0x86, 0x00])

    # Under-bed lights
    LIGHTS_ON = bytes([0x92, 0x00])
    LIGHTS_OFF = bytes([0x93, 0x00])
    LIGHTS_TOGGLE = bytes([0x94, 0x00])

    # Massage - all
    MASSAGE_ALL_OFF = bytes([0x80, 0x00])
    MASSAGE_ALL_TOGGLE = bytes([0x91, 0x00])
    MASSAGE_ALL_UP = bytes([0xA8, 0x00])
    MASSAGE_ALL_DOWN = bytes([0xA9, 0x00])

    # Massage - head
    MASSAGE_HEAD_TOGGLE = bytes([0xA6, 0x00])
    MASSAGE_HEAD_UP = bytes([0x8D, 0x00])
    MASSAGE_HEAD_DOWN = bytes([0x8E, 0x00])

    # Massage - foot
    MASSAGE_FOOT_TOGGLE = bytes([0xA7, 0x00])
    MASSAGE_FOOT_UP = bytes([0x8F, 0x00])
    MASSAGE_FOOT_DOWN = bytes([0x90, 0x00])

    # Massage mode
    MASSAGE_MODE_STEP = bytes([0x81, 0x00])

    # Motor movement commands
    # Note: 0x00 is INITIALIZE_DOWN, not stop. 0xFF is the correct stop command.
    # Using 0x00 can cause a brief reverse movement.
    MOVE_STOP = bytes([0xFF, 0x00])
    MOVE_ALL_UP = bytes([0x01, 0x00])

    # Individual motor control
    MOVE_HEAD_UP = bytes([0x03, 0x00])
    MOVE_HEAD_DOWN = bytes([0x02, 0x00])
    MOVE_FEET_UP = bytes([0x05, 0x00])
    MOVE_FEET_DOWN = bytes([0x04, 0x00])
    MOVE_LEGS_UP = bytes([0x09, 0x00])
    MOVE_LEGS_DOWN = bytes([0x08, 0x00])
    MOVE_BACK_UP = bytes([0x0B, 0x00])
    MOVE_BACK_DOWN = bytes([0x0A, 0x00])


class LinakController(BedController):
    """Controller for Linak beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Linak controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._notify_handles: dict[str, int] = {}
        self._active_position_notifications: set[str] = set()
        self._deferred_position_notifications: set[str] = set()
        self._resolved_two_motor_secondary_spec: LinakPositionSpec | None = None
        self._session_ready = False
        self._session_started_monotonic = monotonic()
        _LOGGER.debug(
            "LinakController initialized (motor_count: %d)",
            coordinator.motor_count,
        )

    @property
    def supports_preset_flat(self) -> bool:
        """Return False - Linak has no native flat command.

        Linak's preset_flat() uses Memory 1, which may not be programmed as flat.
        Users should use the memory presets directly instead.
        """
        return False

    @property
    def supports_lights(self) -> bool:
        """Return True - Linak beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Linak has separate on/off commands."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Linak beds support memory presets."""
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        """Return True - Linak motors auto-stop when commands stop arriving.

        Linak beds auto-stop within 200-500ms when commands stop. Sending an
        explicit STOP command (0x00) can cause a brief reverse movement.
        See: https://github.com/kristofferR/ha-adjustable-bed/issues/45
        """
        return True

    @property
    def reverses_position_seek_on_overshoot(self) -> bool:
        """Return False - Linak seek steps are full pulses, so reversal hunts."""
        return False

    @property
    def uses_custom_position_seek_steps(self) -> bool:
        """Return True - Linak seek steps should use short remote-like pulses."""
        return True

    @property
    def position_seek_tolerance(self) -> float:
        """Return a tighter tolerance for Linak angle seeking."""
        return LINAK_POSITION_SEEK_TOLERANCE

    @property
    def position_seek_stall_count(self) -> int:
        """Return a faster reissue threshold so Linak pulses chain smoothly."""
        return LINAK_POSITION_SEEK_STALL_COUNT

    @property
    def position_seek_check_interval(self) -> float:
        """Return a faster feedback cadence for Linak pulse chaining."""
        return LINAK_POSITION_SEEK_CHECK_INTERVAL_S

    @property
    def position_seek_stall_threshold(self) -> float:
        """Return a smaller movement threshold for Linak angle feedback."""
        return LINAK_POSITION_SEEK_STALL_THRESHOLD

    @property
    def chains_position_seek_steps_while_moving(self) -> bool:
        """Keep feeding Linak seek bursts while the motor is still advancing."""
        return True

    @property
    def position_seek_chain_min_remaining_distance(self) -> float:
        """Switch to stop-and-check micro pulses once Linak is close to target."""
        return LINAK_CHAINED_SEEK_MIN_REMAINING_DEGREES

    @property
    def passive_position_reconciliation_interval(self) -> float | None:
        """Return a low-frequency idle read interval for out-of-band movement."""
        return LINAK_PASSIVE_POSITION_RECONCILIATION_INTERVAL_S

    @property
    def allow_position_polling_during_commands(self) -> bool:
        """Return False - position reads can interrupt Linak's pulse stream."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 6 - Linak beds support memory slots 1-6."""
        return 6

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Linak beds support programming memory positions."""
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LINAK_CONTROL_CHAR_UUID

    @staticmethod
    def _is_authentication_window_error(err: BleakError) -> bool:
        """Return True when Linak rejects writes during early session setup."""
        message = str(err).lower()
        return "insufficient authentication" in message or "error=5" in message

    def _make_position_handler(
        self, spec: LinakPositionSpec
    ) -> Callable[[Any, bytearray], None]:
        """Build a notification callback for a Linak position characteristic."""

        def handler(_: Any, data: bytearray) -> None:
            angle = self._decode_position_data(
                spec.source_name,
                data,
                spec.max_position,
                spec.max_angle,
            )
            if angle is None:
                return

            _LOGGER.debug(
                "Notification received for %s: raw_data=%s (%d bytes)",
                spec.source_name,
                data.hex(),
                len(data),
            )
            self.forward_raw_notification(spec.uuid, bytes(data))
            self._maybe_resolve_two_motor_secondary_notification(spec)
            if self._notify_callback:
                self._notify_callback(spec.axis_name, angle)

        return handler

    def _back_position_spec(self) -> LinakPositionSpec:
        """Return the Linak back/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="back",
            source_name="back",
            uuid=LINAK_POSITION_BACK_UUID,
            max_position=LINAK_BACK_MAX_POSITION,
            max_angle=self._coordinator.back_max_angle,
        )

    def _legs_position_spec(self) -> LinakPositionSpec:
        """Return the default Linak legs/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="legs",
            source_name="legs",
            uuid=LINAK_POSITION_LEG_UUID,
            max_position=LINAK_LEG_MAX_POSITION,
            max_angle=self._coordinator.legs_max_angle,
        )

    def _head_position_spec(self) -> LinakPositionSpec:
        """Return the Linak head/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="head",
            source_name="head",
            uuid=LINAK_POSITION_HEAD_UUID,
            max_position=LINAK_HEAD_MAX_POSITION,
            max_angle=self._coordinator.head_max_angle,
        )

    def _feet_position_spec(self) -> LinakPositionSpec:
        """Return the Linak foot/rest position characteristic."""
        return LinakPositionSpec(
            axis_name="feet",
            source_name="feet",
            uuid=LINAK_POSITION_FEET_UUID,
            max_position=LINAK_FEET_MAX_POSITION,
            max_angle=self._coordinator.feet_max_angle,
        )

    def _two_motor_secondary_spec(self) -> LinakPositionSpec:
        """Return the currently resolved second actuator for a 2-motor bed."""
        return self._resolved_two_motor_secondary_spec or self._legs_position_spec()

    def _two_motor_secondary_candidates(self) -> list[LinakPositionSpec]:
        """Return candidate Linak reference outputs for the second 2-motor actuator."""
        return [
            self._legs_position_spec(),
            LinakPositionSpec(
                axis_name="legs",
                source_name="feet",
                uuid=LINAK_POSITION_FEET_UUID,
                max_position=LINAK_FEET_MAX_POSITION,
                max_angle=self._coordinator.legs_max_angle,
            ),
            LinakPositionSpec(
                axis_name="legs",
                source_name="head",
                uuid=LINAK_POSITION_HEAD_UUID,
                max_position=LINAK_HEAD_MAX_POSITION,
                max_angle=self._coordinator.legs_max_angle,
            ),
        ]

    def _build_position_characteristics(self, motor_count: int) -> list[LinakPositionSpec]:
        """Return the readable/notifiable position characteristics for this bed."""
        position_specs = [self._back_position_spec()]

        if motor_count <= 2:
            position_specs.append(self._two_motor_secondary_spec())
            return position_specs

        position_specs.append(self._legs_position_spec())

        if motor_count > 2:
            position_specs.append(self._head_position_spec())

        if motor_count > 3:
            position_specs.append(self._feet_position_spec())

        return position_specs

    def _build_notification_characteristics(self, motor_count: int) -> list[LinakPositionSpec]:
        """Return Linak position characteristics to subscribe for live updates."""
        if motor_count > 2:
            return self._build_position_characteristics(motor_count)

        specs_by_uuid = {self._back_position_spec().uuid: self._back_position_spec()}
        for spec in self._two_motor_secondary_candidates():
            specs_by_uuid[spec.uuid] = spec
        return list(specs_by_uuid.values())

    def _maybe_resolve_two_motor_secondary_notification(self, spec: LinakPositionSpec) -> None:
        """Lock onto the reporting second actuator for 2-motor Linak beds."""
        if self._coordinator.motor_count > 2:
            return
        if spec.axis_name != "legs":
            return
        if spec.uuid == self._two_motor_secondary_spec().uuid:
            return

        self._coordinator.hass.async_create_task(self._set_two_motor_secondary_spec(spec))

    async def _set_two_motor_secondary_spec(self, spec: LinakPositionSpec) -> None:
        """Persist the resolved second actuator for a 2-motor Linak bed."""
        current_spec = self._two_motor_secondary_spec()
        if current_spec.uuid == spec.uuid:
            return

        _LOGGER.info(
            "Resolved Linak secondary actuator for %s to %s (%s)",
            self._coordinator.address,
            spec.source_name,
            spec.uuid,
        )
        self._resolved_two_motor_secondary_spec = spec

        if self.client is None or not self.client.is_connected:
            return

        for candidate in self._two_motor_secondary_candidates():
            if candidate.uuid == spec.uuid:
                continue
            if candidate.uuid in self._active_position_notifications:
                with contextlib.suppress(BleakError):
                    await self.client.stop_notify(candidate.uuid)
            self._active_position_notifications.discard(candidate.uuid)
            self._deferred_position_notifications.discard(candidate.uuid)

        await self._ensure_position_notifications_started()

    async def _start_missing_position_notifications(
        self,
    ) -> tuple[list[str], list[str], list[str]]:
        """Start any Linak position notifications that are not already active."""
        successful: list[str] = []
        deferred: list[str] = []
        failed: list[str] = []

        if self.client is None or not self.client.is_connected:
            return successful, deferred, failed

        for spec in self._build_notification_characteristics(self._coordinator.motor_count):
            if spec.uuid in self._active_position_notifications:
                continue

            _LOGGER.debug(
                "Attempting to start notifications for %s (UUID: %s)...",
                spec.source_name,
                spec.uuid,
            )

            try:
                async with self._ble_lock:
                    await self.client.start_notify(
                        spec.uuid,
                        self._make_position_handler(spec),
                    )
            except BleakError as err:
                if self._is_authentication_window_error(err):
                    self._deferred_position_notifications.add(spec.uuid)
                    deferred.append(spec.source_name)
                    _LOGGER.debug(
                        "Deferring Linak %s notifications until control is ready: %s",
                        spec.source_name,
                        err,
                    )
                    continue

                _LOGGER.debug(
                    "Could not start notifications for %s position (UUID: %s): %s (type: %s)",
                    spec.source_name,
                    spec.uuid,
                    err,
                    type(err).__name__,
                )
                failed.append(spec.source_name)
                continue

            self._active_position_notifications.add(spec.uuid)
            self._deferred_position_notifications.discard(spec.uuid)
            successful.append(spec.source_name)
            _LOGGER.debug(
                "Successfully started notifications for %s position (UUID: %s, max_pos: %d, max_angle: %.1f°)",
                spec.source_name,
                spec.uuid,
                spec.max_position,
                spec.max_angle,
            )

        return successful, deferred, failed

    async def _ensure_position_notifications_started(self) -> None:
        """Start Linak position notifications, retrying deferred auth-window attempts."""
        if self._notify_callback is None:
            return

        successful, deferred, failed = await self._start_missing_position_notifications()

        if successful:
            _LOGGER.info(
                "Position notifications active for: %s",
                ", ".join(successful),
            )

        if deferred:
            _LOGGER.debug(
                "Linak position notifications deferred until control is ready: %s",
                ", ".join(deferred),
            )

        if failed:
            _LOGGER.warning(
                "Position notifications unavailable for: %s (bed may not support position feedback for these motors)",
                ", ".join(failed),
            )

    async def _await_control_ready(
        self, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Wait until Linak accepts control writes after a fresh BLE connect."""
        if self._session_ready:
            return

        effective_cancel = cancel_event or self._coordinator.cancel_command
        deadline = self._session_started_monotonic + LINAK_CONTROL_READY_TIMEOUT_S
        attempt = 0

        while True:
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.debug(
                    "Cancelled Linak readiness wait for %s",
                    self._coordinator.address,
                )
                return

            attempt += 1
            session_age = monotonic() - self._session_started_monotonic
            _LOGGER.debug(
                "Probing Linak control readiness for %s (attempt %d, session age %.2fs)",
                self._coordinator.address,
                attempt,
                session_age,
            )

            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()

            try:
                await self._write_gatt_with_retry(
                    self.control_characteristic_uuid,
                    LinakCommands.MOVE_STOP,
                    repeat_count=1,
                    repeat_delay_ms=0,
                    cancel_event=cancel_event,
                )
            except BleakError as err:
                if not self._is_authentication_window_error(err):
                    raise

                remaining = deadline - monotonic()
                if remaining <= 0:
                    _LOGGER.error(
                        "Linak control stayed unavailable for %s after %.2fs",
                        self._coordinator.address,
                        session_age,
                    )
                    raise

                delay = min(LINAK_CONTROL_READY_RETRY_DELAY_S, remaining)
                _LOGGER.debug(
                    "Linak control not ready for %s yet: %s; retrying in %.2fs",
                    self._coordinator.address,
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            self._session_ready = True
            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()
            _LOGGER.debug(
                "Linak control ready for %s after %.2fs (%d probe attempts)",
                self._coordinator.address,
                monotonic() - self._session_started_monotonic,
                attempt,
            )
            return

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        await self._await_control_ready(cancel_event)
        _LOGGER.debug(
            "Writing command to Linak bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )
        _LOGGER.debug("Command sequence ended (%d writes attempted)", repeat_count)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning(
                "Cannot start position notifications: BLE client not connected (client=%s, is_connected=%s)",
                self.client,
                getattr(self.client, "is_connected", "N/A") if self.client else "N/A",
            )
            return

        motor_count = self._coordinator.motor_count
        _LOGGER.info(
            "Setting up position notifications for %d-motor Linak bed at %s",
            motor_count,
            self._coordinator.address,
        )
        _LOGGER.debug(
            "Client state: is_connected=%s, mtu_size=%s",
            self.client.is_connected,
            getattr(self.client, "mtu_size", "N/A"),
        )

        position_chars = self._build_position_characteristics(motor_count)

        _LOGGER.debug(
            "Will attempt to subscribe to %d position characteristics: %s",
            len(position_chars),
            [spec.source_name for spec in position_chars],
        )
        await self._ensure_position_notifications_started()

    async def _read_position_characteristic(
        self,
        spec: LinakPositionSpec,
        timeout_seconds: float = 0.75,
    ) -> float | None:
        """Read a single Linak position characteristic without blocking others."""
        if self.client is None or not self.client.is_connected:
            return None

        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._ble_lock:
                    data = await self.client.read_gatt_char(spec.uuid)
        except TimeoutError:
            _LOGGER.debug(
                "Timed out reading position for %s (UUID: %s)",
                spec.source_name,
                spec.uuid,
            )
            return None
        except BleakError as err:
            _LOGGER.debug(
                "Could not read position for %s (UUID: %s): %s",
                spec.source_name,
                spec.uuid,
                err,
            )
            return None

        if not data:
            return None

        _LOGGER.debug("Read position for %s: %s", spec.source_name, data.hex())
        angle = self._decode_position_data(
            spec.source_name,
            bytearray(data),
            spec.max_position,
            spec.max_angle,
        )
        if angle is None:
            return None

        if self._notify_callback:
            self._notify_callback(spec.axis_name, angle)
        return angle

    def _decode_position_data(
        self,
        source_name: str,
        data: bytearray,
        max_position: int,
        max_angle: float,
    ) -> float | None:
        """Decode raw Linak position bytes into an angle."""
        if len(data) < 2:
            _LOGGER.warning(
                "Received invalid position data for %s: expected 2+ bytes, got %d",
                source_name,
                len(data),
            )
            return None

        raw_position = data[0] | (data[1] << 8)

        if raw_position > max_position * 1.1:
            _LOGGER.debug(
                "Ignoring invalid position data for %s: raw=%d exceeds max=%d by >10%%",
                source_name,
                raw_position,
                max_position,
            )
            return None

        if raw_position >= max_position:
            angle = max_angle
        else:
            angle = round(max_angle * (raw_position / max_position), 1)

        _LOGGER.debug(
            "Position update [%s]: raw=%d (max=%d), angle=%.1f° (max=%.1f°)",
            source_name,
            raw_position,
            max_position,
            angle,
            max_angle,
        )
        return angle

    def _handle_position_data(
        self,
        name: str,
        data: bytearray,
        max_position: int,
        max_angle: float,
        *,
        source_name: str | None = None,
    ) -> None:
        """Handle position notification data."""
        angle = self._decode_position_data(
            source_name or name,
            data,
            max_position,
            max_angle,
        )
        if angle is None:
            return

        if self._notify_callback:
            self._notify_callback(name, angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        self._active_position_notifications.clear()
        self._deferred_position_notifications.clear()
        uuids = [
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
            LINAK_POSITION_HEAD_UUID,
            LINAK_POSITION_FEET_UUID,
        ]

        for uuid in uuids:
            with contextlib.suppress(BleakError):
                await self.client.stop_notify(uuid)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Actively read position data from all motor position characteristics.

        This provides a way to get current positions without relying solely
        on notifications, which may not always be sent by the bed.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot read positions: not connected")
            return

        expected_axes = self._expected_position_axes(motor_count)
        received_axes = await self._read_positions_once(motor_count)
        if self._session_ready or received_axes >= expected_axes:
            return

        for attempt in range(2, LINAK_INITIAL_POSITION_RETRY_ATTEMPTS + 1):
            if self.client is None or not self.client.is_connected:
                return

            _LOGGER.debug(
                "Linak cold-session position read returned no data for %s; retrying in %.2fs (attempt %d/%d)",
                self._coordinator.address,
                LINAK_INITIAL_POSITION_RETRY_DELAY_S,
                attempt,
                LINAK_INITIAL_POSITION_RETRY_ATTEMPTS,
            )
            await asyncio.sleep(LINAK_INITIAL_POSITION_RETRY_DELAY_S)

            if self._deferred_position_notifications:
                await self._ensure_position_notifications_started()

            missing_axes = expected_axes - received_axes
            received_axes.update(
                await self._read_positions_once(motor_count, axes=missing_axes)
            )
            if received_axes >= expected_axes:
                return

    def _expected_position_axes(self, motor_count: int) -> set[str]:
        """Return the logical axes expected from a Linak position read."""
        expected_axes = {"back"}
        if motor_count <= 2:
            expected_axes.add("legs")
            return expected_axes

        expected_axes.add("legs")
        if motor_count > 2:
            expected_axes.add("head")
        if motor_count > 3:
            expected_axes.add("feet")
        return expected_axes

    async def _read_positions_once(
        self,
        motor_count: int,
        *,
        axes: set[str] | None = None,
    ) -> set[str]:
        """Read Linak positions once and return the axes that produced data."""
        if motor_count <= 2:
            received_axes: set[str] = set()
            back_angle = None
            secondary_angle = None
            if axes is None or "back" in axes:
                back_angle = await self._read_position_characteristic(self._back_position_spec())
            if axes is None or "legs" in axes:
                secondary_angle = await self._read_two_motor_secondary_position()
            if back_angle is not None:
                received_axes.add("back")
            if secondary_angle is not None:
                received_axes.add("legs")
            return received_axes

        received_axes: set[str] = set()
        for spec in self._build_position_characteristics(motor_count):
            if axes is not None and spec.axis_name not in axes:
                continue
            angle = await self._read_position_characteristic(spec)
            if angle is not None:
                received_axes.add(spec.axis_name)
        return received_axes

    async def _read_two_motor_secondary_position(self) -> float | None:
        """Read and resolve the second actuator for a 2-motor Linak bed."""
        current_spec = self._two_motor_secondary_spec()
        candidates = [current_spec] + [
            candidate
            for candidate in self._two_motor_secondary_candidates()
            if candidate.uuid != current_spec.uuid
        ]

        for spec in candidates:
            angle = await self._read_position_characteristic(spec)
            if angle is None:
                continue

            if spec.uuid != current_spec.uuid:
                await self._set_two_motor_secondary_spec(spec)
            return angle

        return None

    async def read_non_notifying_positions(self) -> None:
        """Read positions for manual refresh flows that need a back-motor read."""
        if self.client is None or not self.client.is_connected:
            return

        await self._read_position_characteristic(self._back_position_spec(), timeout_seconds=0.4)

    async def prepare_for_position_read(self) -> None:
        """Wait for Linak's post-connect auth window before passive reads."""
        await self._await_control_ready()

    # Motor control methods
    # Linak protocol requires continuous command sending to keep motors moving.
    # Using 15 repeats @ 100ms = ~1.5 seconds of movement per press.
    # Motors auto-stop when commands stop arriving - no explicit STOP needed.

    async def _move_with_stop(self, move_command: bytes) -> None:
        """Execute a movement command.

        Linak beds auto-stop when commands stop arriving (typically within 200-500ms).
        We do NOT send an explicit STOP command because it can cause a brief reverse
        movement due to how the motor controller interprets the 0x00 command.
        See: https://github.com/kristofferR/ha-adjustable-bed/issues/45
        """
        await self.write_command(move_command, repeat_count=15, repeat_delay_ms=100)

    def _seek_step_repeat_count(self, remaining_distance: float | None) -> int:
        """Return an adaptive Linak seek pulse size for the remaining error."""
        if remaining_distance is None:
            return LINAK_FINE_SEEK_PULSE_COUNT
        if remaining_distance >= LINAK_COARSE_SEEK_DISTANCE_DEGREES:
            return LINAK_COARSE_SEEK_PULSE_COUNT
        if remaining_distance >= LINAK_MEDIUM_SEEK_DISTANCE_DEGREES:
            return LINAK_MEDIUM_SEEK_PULSE_COUNT
        if remaining_distance >= LINAK_FINE_SEEK_DISTANCE_DEGREES:
            return LINAK_FINE_SEEK_PULSE_COUNT
        return LINAK_MICRO_SEEK_PULSE_COUNT

    async def seek_position_step(
        self,
        position_key: str,
        moving_up: bool,
        remaining_distance: float | None = None,
    ) -> None:
        """Execute an adaptive Linak seek pulse based on remaining distance."""
        command_map = {
            ("back", True): LinakCommands.MOVE_BACK_UP,
            ("back", False): LinakCommands.MOVE_BACK_DOWN,
            ("legs", True): LinakCommands.MOVE_LEGS_UP,
            ("legs", False): LinakCommands.MOVE_LEGS_DOWN,
            ("head", True): LinakCommands.MOVE_HEAD_UP,
            ("head", False): LinakCommands.MOVE_HEAD_DOWN,
            ("feet", True): LinakCommands.MOVE_FEET_UP,
            ("feet", False): LinakCommands.MOVE_FEET_DOWN,
        }
        command = command_map.get((position_key, moving_up))
        if command is None:
            await super().seek_position_step(
                position_key,
                moving_up,
                remaining_distance,
            )
            return

        repeat_count = self._seek_step_repeat_count(remaining_distance)
        await self.write_command(
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=LINAK_POSITION_SEEK_PULSE_DELAY_MS,
        )

    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (uses memory 1 which is typically flat)."""
        # Memory preset 1 is typically configured as flat position on Linak beds
        await self.preset_memory(1)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LinakCommands.PRESET_MEMORY_1,
            2: LinakCommands.PRESET_MEMORY_2,
            3: LinakCommands.PRESET_MEMORY_3,
            4: LinakCommands.PRESET_MEMORY_4,
            5: LinakCommands.PRESET_MEMORY_5,
            6: LinakCommands.PRESET_MEMORY_6,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LinakCommands.PROGRAM_MEMORY_1,
            2: LinakCommands.PROGRAM_MEMORY_2,
            3: LinakCommands.PROGRAM_MEMORY_3,
            4: LinakCommands.PROGRAM_MEMORY_4,
            5: LinakCommands.PROGRAM_MEMORY_5,
            6: LinakCommands.PROGRAM_MEMORY_6,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_ON)

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_OFF)

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_TOGGLE)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(LinakCommands.MASSAGE_ALL_OFF)

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(LinakCommands.MASSAGE_ALL_TOGGLE)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_TOGGLE)

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_TOGGLE)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_ALL_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_ALL_DOWN)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(LinakCommands.MASSAGE_MODE_STEP)
