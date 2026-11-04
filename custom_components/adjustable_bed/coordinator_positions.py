"""Motor position state, hydration and seeking for the bed coordinator."""

# Each method annotates self as the coordinator so pyright checks its body
# against the full class. Pyright reports that annotation on a mixin as a
# general type issue, the only diagnostic this disables.
# pyright: reportGeneralTypeIssues=false

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Collection, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import callback

from .command_scheduler import CommandKind, current_command_context
from .const import BED_TYPE_LINAK, POSITION_FEEDBACK_TIMEOUT, bed_type_has_position_feedback
from .position_seek import (
    PositionFeedbackError,
    PositionSeekPolicy,
    PositionSeekRunner,
    SeekMotion,
    SeekOutcome,
    SeekResult,
    SeekSample,
    SeekTimeoutError,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController
    from .coordinator import AdjustableBedCoordinator

# Log under the coordinator's own logger, as before the split.
_LOGGER = logging.getLogger(f"{__package__}.coordinator")

_INITIAL_POSITION_READ_TIMEOUT = 10.0
_INITIAL_POSITION_READ_TOTAL_TIMEOUT = 40.0
_INITIAL_POSITION_READ_RETRY_DELAY = 3.0
_INITIAL_POSITION_READ_MAX_ATTEMPTS = 6
_PASSIVE_POSITION_RECONCILIATION_IDLE_MARGIN = 15.0


class NotConnectedError(Exception):
    """Raised when bed is not connected."""


class NoControllerError(Exception):
    """Raised when no controller is available."""


class CoordinatorPositionsMixin:
    """Position reads, hydration, passive reconciliation, callbacks and seeks."""

    @property
    def position_data(self: AdjustableBedCoordinator) -> dict[str, float]:
        """Return current position data."""
        return self._position_data

    async def async_read_initial_positions(self: AdjustableBedCoordinator) -> None:
        """Read positions to initialize sensors.

        Called after a connection is established to populate position sensors
        with actual values instead of leaving them 'unknown'. Runs in background
        with short timeouts so it never blocks startup.

        Uses the command lock to prevent concurrent GATT operations with
        commands that may start immediately after connection.

        Each attempt has its own timeout, while an overall deadline keeps the
        retry window from reserving a single-connection bed indefinitely.
        """
        if self._disable_angle_sensing:
            _LOGGER.debug("Skipping initial position read (angle sensing disabled)")
            return

        expected_axes = self._expected_initial_position_axes()
        if not expected_axes:
            _LOGGER.debug("Skipping initial position read (no expected axes)")
            return

        if self._position_hydration_running:
            _LOGGER.debug("Initial position read already running for %s - skipping", self._address)
            return

        self._position_hydration_running = True
        current_task = asyncio.current_task()
        if current_task is not None:
            # Setup and reconnect paths can both request the initial read. Keep
            # whichever task actually claimed the operation discoverable so
            # diagnostics and shutdown can cancel that exact task.
            self._position_hydration_task = current_task
        try:
            # Keep the link alive for the retry window, but only own the command
            # lock during a GATT attempt so user commands and STOP can run during
            # the backoff sleeps.
            self._cancel_disconnect_timer()
            try:
                _LOGGER.debug("Reading initial positions for %s", self._address)
                try:
                    async with asyncio.timeout(_INITIAL_POSITION_READ_TOTAL_TIMEOUT):
                        for attempt in range(1, _INITIAL_POSITION_READ_MAX_ATTEMPTS + 1):
                            # A command that established this connection may
                            # have refreshed every axis while hydration waited
                            # for the command lock, or deliberately released
                            # the link. Avoid entering the query path, which
                            # would reconnect after disconnect-after-command.
                            if (
                                self._client is None
                                or not self._client.is_connected
                                or all(self._position_is_current(axis) for axis in expected_axes)
                            ):
                                return

                            def _initial_position_read_needed() -> bool:
                                return (
                                    not self._position_hydration_pause_count
                                    and self._client is not None
                                    and self._client.is_connected
                                    and not all(
                                        self._position_is_current(axis) for axis in expected_axes
                                    )
                                )

                            async def _read_initial_positions(
                                controller: BedController,
                            ) -> None:
                                # Connection preparation can produce notifications,
                                # so recheck after it as well as before reconnecting.
                                if not _initial_position_read_needed():
                                    return
                                await controller.prepare_for_position_read()
                                await self._async_read_positions()

                            try:
                                async with asyncio.timeout(_INITIAL_POSITION_READ_TIMEOUT):
                                    await self.async_execute_controller_query(
                                        _read_initial_positions,
                                        skip_disconnect=True,
                                        preemptible=True,
                                        run_if=_initial_position_read_needed,
                                    )
                            except TimeoutError:
                                _LOGGER.debug(
                                    "Initial position read attempt %d/%d for %s timed out",
                                    attempt,
                                    _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                    self._address,
                                )
                            except asyncio.CancelledError:
                                raise
                            except Exception as err:
                                _LOGGER.debug(
                                    "Initial position read attempt %d/%d for %s failed: %s",
                                    attempt,
                                    _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                    self._address,
                                    err,
                                )
                            finally:
                                # Serialized queries restart the idle timer.
                                # Hydration owns the link through its bounded
                                # retry window, including the backoff sleeps.
                                self._cancel_disconnect_timer()

                            # Checked even after a failed attempt: a partial read
                            # (or a notification that landed meanwhile) may
                            # already be enough.
                            received_axes = {
                                axis for axis in expected_axes if self._position_is_current(axis)
                            }
                            if received_axes >= expected_axes:
                                _LOGGER.info(
                                    "Initial positions read for %s: %s",
                                    self._address,
                                    {k: f"{v}°" for k, v in self._position_data.items()},
                                )
                                return

                            if self._disconnect_after_operation_enabled():
                                # Missing feedback must not reserve the link
                                # through the full hydration retry window when
                                # the user asked for prompt remote handoff.
                                return

                            if attempt >= _INITIAL_POSITION_READ_MAX_ATTEMPTS:
                                break

                            _LOGGER.debug(
                                "Initial position read for %s missing axes %s after "
                                "attempt %d/%d; retrying in %.1fs",
                                self._address,
                                sorted(expected_axes - received_axes),
                                attempt,
                                _INITIAL_POSITION_READ_MAX_ATTEMPTS,
                                _INITIAL_POSITION_READ_RETRY_DELAY,
                            )
                            await asyncio.sleep(_INITIAL_POSITION_READ_RETRY_DELAY)
                except TimeoutError:
                    _LOGGER.debug(
                        "Initial position read retry window for %s timed out after %.1fs",
                        self._address,
                        _INITIAL_POSITION_READ_TOTAL_TIMEOUT,
                    )

                if self._position_data:
                    _LOGGER.info(
                        "Initial position read for %s remained partial: %s",
                        self._address,
                        {k: f"{v}°" for k, v in self._position_data.items()},
                    )
                else:
                    _LOGGER.debug(
                        "Initial position read for %s produced no data - retrying on the "
                        "next connect",
                        self._address,
                    )
            finally:
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
        finally:
            self._position_hydration_running = False
            if self._position_hydration_task is current_task:
                self._position_hydration_task = None

    def _schedule_position_hydration(self: AdjustableBedCoordinator) -> None:
        """Refresh position axes in the background after a connect.

        Entry setup schedules the first read, but a bed that was busy, asleep or
        unreachable then would otherwise sit at "unknown" until the user moved
        it: outside a movement command nothing reads positions. Every new BLE
        session also refreshes last-known values in case another controller
        moved the bed while Home Assistant had released the link.
        """
        if self._disable_angle_sensing or self._position_hydration_pause_count:
            return

        expected_axes = self._expected_initial_position_axes()
        if not expected_axes or all(self._position_is_current(axis) for axis in expected_axes):
            return

        task = self._position_hydration_task
        if task is not None and not task.done():
            return

        self._position_hydration_task = self.entry.async_create_background_task(
            self.hass,
            self.async_read_initial_positions(),
            name=f"adjustable_bed_position_hydration_{self._address}",
        )

    def _expected_initial_position_axes(self: AdjustableBedCoordinator) -> set[str]:
        """Return the logical position axes that startup hydration should populate."""
        if not bed_type_has_position_feedback(self._bed_type, self._protocol_variant):
            return set()
        controller = self._controller
        if controller is None:
            return set()
        return {spec.position_key for spec in controller.position_number_specs}

    def _position_is_current(self: AdjustableBedCoordinator, position: str) -> bool:
        """Return whether a cached position was observed on the active BLE session."""
        if position not in self._position_data:
            return False
        # Unit tests and capability-only coordinators can operate without ever
        # establishing a BLE generation. Production connections start at one.
        if self._position_connection_generation == 0:
            return True
        return self._position_data_generation.get(position) == self._position_connection_generation

    async def _async_read_seek_position(
        self: AdjustableBedCoordinator, position: str, policy: PositionSeekPolicy, *, after: float | None = None
    ) -> float | None:
        """Read this axis without promoting retained display state to feedback."""

        def has_fresh_notification() -> bool:
            updated = self._position_data_updated_monotonic.get(position)
            return (
                self._position_is_current(position)
                and updated is not None
                and (after is None or updated > after)
                and policy.cached_position_feedback_max_age > 0
                and time.monotonic() - updated <= policy.cached_position_feedback_max_age
            )

        if policy.prefers_cached_position_feedback and has_fresh_notification():
            return self._position_data[position]

        read_started = time.monotonic()
        await self._async_read_positions()
        updated = self._position_data_updated_monotonic.get(position)
        if has_fresh_notification() or (
            policy.cached_position_feedback_max_age <= 0
            and self._position_is_current(position)
            and updated is not None
            and updated >= read_started
        ):
            return self._position_data[position]
        return None

    async def _async_cancel_position_hydration(self: AdjustableBedCoordinator) -> None:
        """Cancel and await the active position hydration task."""
        task = self._position_hydration_task
        try:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
        finally:
            if self._position_hydration_task is task:
                self._position_hydration_task = None

    async def async_pause_position_hydration(self: AdjustableBedCoordinator) -> None:
        """Suppress background position reads during external BLE diagnostics."""
        self._position_hydration_pause_count += 1
        await self._async_cancel_position_hydration()

    def resume_position_hydration(self: AdjustableBedCoordinator) -> None:
        """Resume position hydration after an external BLE diagnostic operation."""
        if self._position_hydration_pause_count == 0:
            return
        self._position_hydration_pause_count -= 1
        if self._position_hydration_pause_count:
            return
        if self._client is not None and self._client.is_connected:
            self._schedule_position_hydration()

    def _resolve_passive_position_reconciliation_interval(
        self: AdjustableBedCoordinator, requested_interval_s: float | None
    ) -> float | None:
        """Return the safe passive reconciliation interval for this entry."""
        if self._disable_angle_sensing:
            return None
        if not self._passive_position_reconciliation_enabled:
            return None
        if self._disconnect_after_operation_enabled():
            # Polling would take the link back from the physical remote while idle.
            return None
        if requested_interval_s is None or requested_interval_s <= 0:
            return None

        minimum_interval_s = float(self._idle_disconnect_seconds) + (
            _PASSIVE_POSITION_RECONCILIATION_IDLE_MARGIN
        )
        return max(float(requested_interval_s), minimum_interval_s)

    def _refresh_passive_position_reconciliation_schedule(self: AdjustableBedCoordinator) -> None:
        """Start or stop passive position reconciliation based on controller support."""
        requested_interval_s: float | None = None
        if self._controller is not None:
            requested_interval_s = self._controller.passive_position_reconciliation_interval

        interval_s = self._resolve_passive_position_reconciliation_interval(requested_interval_s)
        current_task = self._passive_position_reconciliation_task
        if (
            interval_s == self._passive_position_reconciliation_interval_s
            and current_task is not None
            and not current_task.done()
        ):
            return

        self._cancel_passive_position_reconciliation_task()
        self._passive_position_reconciliation_interval_s = interval_s
        if interval_s is None:
            return

        _LOGGER.debug(
            "Starting passive position reconciliation for %s every %.0fs",
            self._address,
            interval_s,
        )
        self._passive_position_reconciliation_task = self.hass.async_create_background_task(
            self._async_passive_position_reconciliation_loop(),
            name=f"adjustable_bed.passive_position_reconciliation[{self._address}]",
        )

    def _cancel_passive_position_reconciliation_task(self: AdjustableBedCoordinator) -> None:
        """Cancel the passive position reconciliation loop."""
        task = self._passive_position_reconciliation_task
        if task is not None:
            task.cancel()
            self._passive_position_reconciliation_task = None

    async def _async_passive_position_reconciliation_loop(self: AdjustableBedCoordinator) -> None:
        """Periodically reconcile positions so external remote moves do not stay stale."""
        try:
            while True:
                interval_s = self._passive_position_reconciliation_interval_s
                if interval_s is None:
                    return

                await asyncio.sleep(interval_s)
                await self.async_reconcile_positions()
        except asyncio.CancelledError:
            return

    async def async_reconcile_positions(self: AdjustableBedCoordinator) -> None:
        """Perform a low-frequency passive position refresh when the coordinator is idle."""
        if (
            self._disable_angle_sensing
            or self._passive_position_reconciliation_interval_s is None
            or self._disconnect_after_operation_enabled()
        ):
            return

        if self._connecting or self._command_lock.locked():
            _LOGGER.debug(
                "Skipping passive position reconciliation for %s because the coordinator is busy",
                self._address,
            )
            return

        try:
            _LOGGER.debug("Running passive position reconciliation for %s", self._address)
            await self.async_execute_controller_query(
                self._async_execute_position_reconciliation_query,
                cancel_running=False,
            )
            _LOGGER.debug("Passive position reconciliation completed for %s", self._address)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug(
                "Passive position reconciliation failed for %s: %s",
                self._address,
                err,
            )

    async def _async_execute_position_reconciliation_query(self: AdjustableBedCoordinator, controller: BedController) -> None:
        """Run a serialized passive position reconciliation read."""
        await controller.prepare_for_position_read()
        await controller.read_positions(self._motor_count)

    async def _async_read_positions(
        self: AdjustableBedCoordinator, controller: BedController | SideBoundController | None = None
    ) -> None:
        """Actively read current positions from the bed.

        Called after movement commands to ensure position data is up to date.
        Uses a short timeout to avoid blocking commands.

        Note: This method does NOT acquire the command lock. When called from
        within a command (which already holds the lock), this is correct.
        For fire-and-forget background reads, use _async_read_positions_background().
        """
        controller = controller if controller is not None else self._controller
        if controller is None:
            return

        try:
            async with asyncio.timeout(POSITION_FEEDBACK_TIMEOUT):
                await controller.read_positions(self._motor_count)
        except TimeoutError:
            _LOGGER.debug("Position read timed out")
        except Exception as err:
            _LOGGER.debug("Failed to read positions: %s", err)

    def _start_background_position_read(self: AdjustableBedCoordinator) -> None:
        """Start a fire-and-forget position read tied to the config entry.

        Skips scheduling when a previous background read is still running so
        slow beds can't pile up queued reads behind the command lock.
        """
        task = self._background_read_task
        if task is not None and not task.done():
            _LOGGER.debug(
                "Background position read already running for %s - skipping", self._address
            )
            return
        self._background_read_task = self.entry.async_create_background_task(
            self.hass,
            self._async_read_positions_background(self._cancel_counter),
            name=f"adjustable_bed_position_read_{self._address}",
        )

    async def _async_read_positions_background(self: AdjustableBedCoordinator, entry_cancel_count: int) -> None:
        """Read positions in background with proper lock serialization.

        This method acquires the command lock to prevent concurrent GATT operations.
        Use this for fire-and-forget position reads (speed mode) to avoid
        "operation in progress" errors from overlapping BLE operations.
        """
        async with self._command_lock:
            if (
                self._cancel_counter != entry_cancel_count
                or self._command_scheduler.has_pending
                or not self.is_connected
            ):
                return
            self._cancel_command.clear()
            await self._async_wait_for_controller_operation(
                asyncio.create_task(self._async_read_positions()),
                cancel_event=self._cancel_command,
                operation_name="background position read",
                raise_on_cancel=False,
            )

    async def _async_poll_positions_during_movement(self: AdjustableBedCoordinator, stop_event: asyncio.Event) -> None:
        """Poll positions periodically during movement.

        Some motors (like Linak back) don't send notifications, only support reads.
        This provides real-time position updates during movement for those motors.
        Only polls motors that don't support notifications to avoid redundant reads.
        """
        if self._controller is None:
            return

        poll_interval = 0.5  # 500ms between polls
        while not stop_event.is_set():
            try:
                # Only read motors that don't send notifications
                async with asyncio.timeout(0.4):
                    await self._controller.read_non_notifying_positions()
            except TimeoutError:
                pass  # Timeout is expected during rapid polling
            except Exception as err:
                _LOGGER.debug("Position polling error (non-fatal): %s", err)

            # Wait for interval or stop signal
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue polling

    @callback
    def _handle_position_update(self: AdjustableBedCoordinator, position: str, angle: float) -> None:
        """Handle a position update from the bed."""
        _LOGGER.debug("Position update: %s = %.1f°", position, angle)
        self._position_data[position] = angle
        self._position_data_generation[position] = self._position_connection_generation
        self._position_data_updated_monotonic[position] = time.monotonic()
        # Track notification timing for diagnostics (issue #168)
        self._last_notify_received = datetime.now(UTC)
        # Copy to safely iterate while callbacks might unregister themselves
        for callback_fn in list(self._position_callbacks):
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error: %s", err)

    @callback
    def clear_position_feedback(self: AdjustableBedCoordinator, positions: Collection[str]) -> None:
        """Invalidate only axes whose physical source generation has ended."""
        changed = False
        for position in positions:
            if position not in self._position_data:
                continue
            self._position_data.pop(position, None)
            self._position_data_generation.pop(position, None)
            self._position_data_updated_monotonic.pop(position, None)
            changed = True
        if not changed:
            return
        for callback_fn in list(self._position_callbacks):
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error during invalidation: %s", err)

    def register_position_callback(
        self: AdjustableBedCoordinator, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        """Register a callback for position updates."""
        self._position_callbacks.add(callback_fn)

        # Immediately emit current position data if available
        # This handles the race where initial read completed before registration
        if self._position_data:
            try:
                callback_fn(self._position_data)
            except Exception as err:
                _LOGGER.warning("Position callback error during registration: %s", err)

        def unregister() -> None:
            self._position_callbacks.discard(callback_fn)  # Safe removal, no error if missing

        return unregister

    async def async_seek_position(
        self: AdjustableBedCoordinator,
        position_key: str,
        target_angle: float,
        move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        *,
        resources: Collection[str] | None = None,
    ) -> None:
        """Schedule one position target with axis-scoped replacement."""

        async def operation() -> None:
            await self._async_seek_position_serial(
                position_key,
                target_angle,
                move_up_fn,
                move_down_fn,
                move_stop_fn,
            )

        await self._async_schedule_command_operation(
            operation,
            resource=None if resources is not None else f"motor:{position_key}",
            resources=resources,
            kind=CommandKind.SEEK,
            cancel_running=True,
        )

    def _record_seek_result(self: AdjustableBedCoordinator, result: SeekResult) -> None:
        """Retain the typed terminal outcome of one seek for diagnostics."""
        context = current_command_context()
        self._seek_outcomes[result.position_key] = {
            "outcome": result.outcome.value,
            "target": result.target,
            "final_angle": result.final_angle,
            "duration_seconds": round(result.duration, 3),
            "intent_id": context.intent_id if context is not None else None,
            "finished_at": datetime.now(UTC).isoformat(),
        }
        if result.final_direction is not None:
            self._last_seek_motion[result.position_key] = SeekMotion(
                moving_up=result.final_direction,
                outcome=result.outcome,
                finished_monotonic=time.monotonic(),
            )

    async def _async_seek_position_serial(
        self: AdjustableBedCoordinator,
        position_key: str,
        target_angle: float,
        move_up_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_down_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        move_stop_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    ) -> None:
        """Seek to a target position using feedback loop control.

        Owns the connection lifecycle around one seek: locking, connecting,
        initial position acquisition, and the direct-position shortcut. The
        feedback loop itself runs in `PositionSeekRunner` under the
        controller-supplied `PositionSeekPolicy`.

        Args:
            position_key: Key in position_data (e.g., "back", "legs")
            target_angle: Target position in degrees (or percentage for Keeson/Ergomotion)
            move_up_fn: Async function to move motor up
            move_down_fn: Async function to move motor down
            move_stop_fn: Async function to stop motor
        """
        cancel_event = self.cancel_command

        async with self._command_lock:
            # Cancel disconnect timer during seeking
            self._cancel_disconnect_timer()

            # Check if cancelled while waiting for lock
            if cancel_event.is_set():
                _LOGGER.debug("Position seek cancelled while waiting for lock")
                if self._client is not None and self._client.is_connected:
                    self._reset_disconnect_timer()
                return

            try:
                # Pin the controller for the whole seek. A disconnect callback can
                # clear self._controller while we await below, and every step of the
                # seek -- including the STOP in the finally block -- must keep acting
                # on the controller we validated rather than dereferencing None.
                controller = self._controller
                if controller is not None and controller.requires_disconnected_transport is True:
                    controller = await self._async_prepare_controller_operation("position seek")
                else:
                    if not await self.async_ensure_connected(reset_timer=False):
                        _LOGGER.error("Cannot seek position: not connected to bed")
                        raise NotConnectedError("Not connected to bed")
                    if self._controller is None:
                        _LOGGER.error("Cannot seek position: no controller available")
                        raise NoControllerError("No controller available")
                    controller = self._controller
                    await self._async_refresh_controller_auth()

                supports_direct_position_control = controller.supports_direct_position_control

                policy = controller.position_seek_policy

                async def read_initial_position() -> float | None:
                    # Readiness has its own controller-owned budget. Do not
                    # spend the position-read timeout waiting for cold setup.
                    await controller.prepare_for_position_read()
                    return await self._async_read_seek_position(position_key, policy)

                # Session membership alone does not establish freshness, even
                # before the first movement or an already-at-target decision.
                current_angle = await self._async_wait_for_controller_operation(
                    asyncio.create_task(read_initial_position()),
                    cancel_event=cancel_event,
                    operation_name="initial position read",
                    raise_on_cancel=False,
                )
                if cancel_event.is_set():
                    self._record_seek_result(
                        SeekResult(
                            position_key=position_key,
                            target=target_angle,
                            outcome=SeekOutcome.CANCELLED,
                            final_angle=None,
                            final_direction=None,
                            duration=0.0,
                        )
                    )
                    return
                if current_angle is None and not supports_direct_position_control:
                    raise PositionFeedbackError(
                        f"Cannot seek {position_key}: no fresh position feedback available"
                    )

                # Check if already at target (per the policy's completion band)
                if current_angle is not None and policy.accepts_position(
                    SeekSample(
                        position_key=position_key,
                        target=target_angle,
                        current=current_angle,
                        previous=None,
                        moving_up=target_angle > current_angle,
                        elapsed=0.0,
                    )
                ):
                    _LOGGER.debug(
                        "Position %s already at target: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    self._record_seek_result(
                        SeekResult(
                            position_key=position_key,
                            target=target_angle,
                            outcome=SeekOutcome.ALREADY_AT_TARGET,
                            final_angle=current_angle,
                            final_direction=None,
                            duration=0.0,
                        )
                    )
                    return  # finally block handles disconnect

                if current_angle is None:
                    _LOGGER.info(
                        "Seeking position %s to %.1f without current feedback",
                        position_key,
                        target_angle,
                    )
                else:
                    _LOGGER.info(
                        "Seeking position %s from %.1f to %.1f",
                        position_key,
                        current_angle,
                        target_angle,
                    )

                # Check if controller supports direct position control (e.g., Reverie)
                # This bypasses the incremental seek loop for beds that can set positions directly
                if supports_direct_position_control:
                    native_position = controller.angle_to_native_position(
                        position_key, target_angle
                    )
                    _LOGGER.debug(
                        "Using direct position control: %s -> %d",
                        position_key,
                        native_position,
                    )
                    await controller.set_motor_position(position_key, native_position)
                    self._record_seek_result(
                        SeekResult(
                            position_key=position_key,
                            target=target_angle,
                            outcome=SeekOutcome.DIRECT_SET,
                            final_angle=None,
                            final_direction=None,
                            duration=0.0,
                        )
                    )
                    return  # finally block handles disconnect timer

                # Only direct-position controllers may reach this point without a
                # current reading, and they returned above.
                if current_angle is None:
                    raise NotConnectedError(
                        f"Cannot seek {position_key}: no position data available"
                    )

                use_custom_seek_steps = controller.uses_custom_position_seek_steps
                feedback_after = time.monotonic()

                async def issue_seek_step(direction_up: bool, remaining_distance: float) -> None:
                    """Execute one seek movement step using controller-specific tuning."""
                    nonlocal feedback_after
                    feedback_after = time.monotonic()
                    if use_custom_seek_steps:
                        await controller.seek_position_step(
                            position_key,
                            direction_up,
                            remaining_distance,
                        )
                        return
                    if direction_up:
                        await move_up_fn(controller)
                    else:
                        await move_down_fn(controller)

                async def read_position() -> float | None:
                    nonlocal feedback_after
                    # Active-read fallback may consume a notification once, but
                    # cannot turn one pre-movement report into repeated samples.
                    # Explicit notification policies retain their own age rules.
                    result = await self._async_read_seek_position(
                        position_key,
                        policy,
                        after=None if policy.prefers_cached_position_feedback else feedback_after,
                    )
                    if result is not None:
                        feedback_after = self._position_data_updated_monotonic[position_key]
                    return result

                runner = PositionSeekRunner(
                    position_key=position_key,
                    target_angle=target_angle,
                    policy=policy,
                    cancel_event=cancel_event,
                    read_position=read_position,
                    issue_step=issue_seek_step,
                    stop=lambda: move_stop_fn(controller),
                    previous_motion=self._last_seek_motion.get(position_key),
                )
                try:
                    result = await runner.async_run(cast(float, current_angle))
                except SeekTimeoutError as err:
                    self._record_seek_result(err.result)
                    raise
                self._record_seek_result(result)
                if result.outcome is SeekOutcome.POSITION_LOST:
                    # The runner has completed protocol-owned cleanup before
                    # paired/service callers receive this failure.
                    raise PositionFeedbackError(
                        f"Lost fresh position feedback for {position_key} during seek"
                    )

            finally:
                if self._bed_type == BED_TYPE_LINAK and not self._command_scheduler.has_pending:
                    # Seeks own their lock lifecycle instead of going through
                    # _async_finish_controller_operation(), so reconcile a
                    # deferred Linak snapshot here as well.
                    self._backfill_linak_snapshot()
                if self._client is not None and self._client.is_connected:
                    if (
                        self._disconnect_after_operation_enabled()
                        and not cancel_event.is_set()
                        and not self._command_scheduler.has_pending
                        and not (
                            (context := current_command_context()) is not None
                            and context.defer_disconnect
                        )
                    ):
                        _LOGGER.debug(
                            "Scheduling disconnect after seek (disconnect_after_command=True) for %s",
                            self._address,
                        )
                        await self._async_release_command_connection()
                    else:
                        self._reset_disconnect_timer()
