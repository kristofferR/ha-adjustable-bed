"""Protocol-aware position seeking.

`PositionSeekRunner` owns the generic seek lifecycle: sampling, cancellation,
timeout, progress tracking, cleanup, and a typed terminal outcome.
`PositionSeekPolicy` owns protocol-specific movement decisions and is supplied
by the controller (see `BedController.position_seek_policy`). The default
policy delegates every tuning value to the controller's existing seek
properties and reproduces the coordinator's historical serialized seek
behavior exactly. GATT writes and STOP/release semantics remain
controller-owned; a policy may only change wire behavior when the protocol
evidence supports it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from homeassistant.exceptions import HomeAssistantError

from .const import POSITION_FEEDBACK_TIMEOUT, POSITION_OVERSHOOT_TOLERANCE, POSITION_SEEK_TIMEOUT

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

# Delay after an explicit STOP before reversing direction so the stop
# completes before the opposite movement starts.
SEEK_REVERSAL_SETTLE_DELAY: Final = 0.3


class SeekOutcome(StrEnum):
    """Typed terminal result of one position seek."""

    ALREADY_AT_TARGET = "already_at_target"
    DIRECT_SET = "direct_set"
    REACHED_TARGET = "reached_target"
    CROSSED_TARGET = "crossed_target"
    ENDPOINT_REACHED = "endpoint_reached"
    CANCELLED = "cancelled"
    POSITION_LOST = "position_lost"
    TIMEOUT = "timeout"


class SeekTransitionKind(StrEnum):
    """How a starting seek relates to the previous motion on the same axis."""

    INITIAL = "initial"
    SAME_DIRECTION = "same_direction"
    OPPOSITE_DIRECTION = "opposite_direction"


@dataclass(frozen=True, slots=True)
class SeekMotion:
    """Last commanded motion on one axis, kept for transition decisions."""

    moving_up: bool
    outcome: SeekOutcome
    finished_monotonic: float


@dataclass(frozen=True, slots=True)
class SeekTransition:
    """Context handed to the policy before a seek issues its first step."""

    kind: SeekTransitionKind
    previous: SeekMotion | None


@dataclass(frozen=True, slots=True)
class SeekSample:
    """One feedback observation evaluated by the policy."""

    position_key: str
    target: float
    current: float
    previous: float | None
    moving_up: bool
    elapsed: float
    stalled_checks: int = 0

    @property
    def remaining(self) -> float:
        """Return the unsigned distance still to travel."""
        return abs(self.target - self.current)


@dataclass(frozen=True, slots=True)
class SeekResult:
    """Typed terminal outcome of one seek run."""

    position_key: str
    target: float
    outcome: SeekOutcome
    final_angle: float | None
    final_direction: bool | None
    duration: float


class SeekTimeoutError(TimeoutError):
    """Seek timeout carrying its typed terminal result."""

    def __init__(self, message: str, result: SeekResult) -> None:
        super().__init__(message)
        self.result = result


class PositionFeedbackError(HomeAssistantError):
    """A seek cannot continue without trustworthy position feedback."""


class PositionSeekPolicy:
    """Protocol movement policy for feedback-driven seeking.

    Tuning values delegate to the controller's existing seek properties, so
    per-controller overrides keep working unchanged. Controller families with
    protocol evidence for smarter behavior (coast compensation, endpoint
    completion, reversal transitions) override the hooks below.
    """

    def __init__(self, controller: BedController) -> None:
        self._controller = controller

    @property
    def tolerance(self) -> float:
        """Return the acceptable error band for target completion."""
        return self._controller.position_seek_tolerance

    @property
    def check_interval(self) -> float:
        """Return the interval between feedback polls."""
        return self._controller.position_seek_check_interval

    @property
    def prefers_cached_position_feedback(self) -> bool:
        """Return True when fresh notifications should replace active GATT reads.

        The default remains conservative for controllers whose notifications
        are missing or incomplete. Protocol policies may opt in when their
        position characteristic is proven to notify throughout movement.
        """
        return False

    @property
    def cached_position_feedback_max_age(self) -> float:
        """Bound notification age by the same budget as an active read.

        The default still attempts an active read, but notification-only
        controllers must also be able to use reports received just before it.
        The coordinator consumes fallback reports once per movement decision.
        This is an integration freshness bound, not a device reporting cadence.
        """
        return POSITION_FEEDBACK_TIMEOUT

    @property
    def stall_count(self) -> int:
        """Return how many stagnant reads confirm a stall."""
        return self._controller.position_seek_stall_count

    @property
    def stall_threshold(self) -> float:
        """Return the minimum delta that still counts as movement."""
        return self._controller.position_seek_stall_threshold

    @property
    def chains_steps_while_moving(self) -> bool:
        """Return True to reissue bursts before movement fully stalls."""
        return self._controller.chains_position_seek_steps_while_moving

    @property
    def chain_min_remaining_distance(self) -> float:
        """Return the minimum remaining error that still allows chaining."""
        return self._controller.position_seek_chain_min_remaining_distance

    @property
    def reverses_on_overshoot(self) -> bool:
        """Return True if overshoot should be corrected by reversing."""
        return self._controller.reverses_position_seek_on_overshoot

    @property
    def overshoot_tolerance(self) -> float:
        """Return how far past the target still avoids a reversal."""
        return POSITION_OVERSHOOT_TOLERANCE

    @property
    def timeout(self) -> float:
        """Return the maximum wall time for one seek."""
        return POSITION_SEEK_TIMEOUT

    @property
    def sends_explicit_stop(self) -> bool:
        """Return True if this protocol needs explicit STOP writes.

        Protocols proven to stop solely when held-command refresh ends can
        opt out through ``auto_stops_on_idle``.
        """
        return not self._controller.auto_stops_on_idle

    def accepts_position(self, sample: SeekSample) -> bool:
        """Return True when the sampled position completes the seek.

        Coast-compensating policies may accept earlier based on recent
        movement; the default is a plain tolerance band.
        """
        return sample.remaining <= self.tolerance

    def completes_on_crossing(self, sample: SeekSample) -> bool:
        """Return True when crossing the target should end the seek.

        Pulse-driven controllers evaluate whole bursts and must not hunt by
        reversing, so any crossing completes the seek for them.
        """
        if self.reverses_on_overshoot:
            return False
        return (sample.moving_up and sample.current >= sample.target) or (
            not sample.moving_up and sample.current <= sample.target
        )

    def wants_reversal(self, sample: SeekSample) -> bool:
        """Return True when overshoot should trigger a direction reversal."""
        if not self.reverses_on_overshoot:
            return False
        if sample.moving_up:
            return sample.current > sample.target + self.overshoot_tolerance
        return sample.current < sample.target - self.overshoot_tolerance

    def stall_completes_near_endpoint(self, sample: SeekSample) -> bool:
        """Return True when a confirmed stall should count as completion.

        Endpoint-aware policies can accept a persistent stall near a physical
        travel limit instead of retrying until timeout. The default never
        promotes a stall to success.
        """
        del sample
        return False

    async def async_on_seek_start(
        self,
        transition: SeekTransition,
        stop: Callable[[], Awaitable[None]],
    ) -> None:
        """Prepare the axis before the first movement step.

        Policies with evidence for a safe settle/release sequence between
        opposite-direction seeks can implement it here. The default issues
        nothing on the wire.
        """
        del transition, stop

    async def async_prepare_reversal(
        self,
        stop: Callable[[], Awaitable[None]],
    ) -> None:
        """Transition the axis before reversing direction after overshoot."""
        # Only send explicit stop for controllers that define a release frame.
        if self.sends_explicit_stop:
            await stop()
            await asyncio.sleep(SEEK_REVERSAL_SETTLE_DELAY)


class PositionSeekRunner:
    """Run one feedback-driven seek and return a typed terminal outcome."""

    def __init__(
        self,
        *,
        position_key: str,
        target_angle: float,
        policy: PositionSeekPolicy,
        cancel_event: asyncio.Event,
        read_position: Callable[[], Awaitable[float | None]],
        issue_step: Callable[[bool, float], Awaitable[None]],
        stop: Callable[[], Awaitable[None]],
        previous_motion: SeekMotion | None = None,
    ) -> None:
        self._position_key = position_key
        self._target = target_angle
        self._policy = policy
        self._cancel_event = cancel_event
        self._read_position = read_position
        self._issue_step = issue_step
        self._stop = stop
        self._previous_motion = previous_motion

    def _transition(self, moving_up: bool) -> SeekTransition:
        previous = self._previous_motion
        if previous is None:
            kind = SeekTransitionKind.INITIAL
        elif previous.moving_up == moving_up:
            kind = SeekTransitionKind.SAME_DIRECTION
        else:
            kind = SeekTransitionKind.OPPOSITE_DIRECTION
        return SeekTransition(kind=kind, previous=previous)

    async def async_run(self, initial_angle: float) -> SeekResult:
        """Seek toward the target and return the typed terminal outcome.

        Raises `SeekTimeoutError` (a `TimeoutError`) on feedback timeout after
        motor cleanup, matching the historical seek contract.
        """
        position_key = self._position_key
        target_angle = self._target
        policy = self._policy
        cancel_event = self._cancel_event
        start_time = time.monotonic()

        def result(
            outcome: SeekOutcome,
            final_angle: float | None,
            final_direction: bool | None,
        ) -> SeekResult:
            return SeekResult(
                position_key=position_key,
                target=target_angle,
                outcome=outcome,
                final_angle=final_angle,
                final_direction=final_direction,
                duration=time.monotonic() - start_time,
            )

        initial_sample = SeekSample(
            position_key=position_key,
            target=target_angle,
            current=initial_angle,
            previous=None,
            moving_up=target_angle > initial_angle,
            elapsed=0.0,
        )
        if policy.accepts_position(initial_sample):
            _LOGGER.debug(
                "Position %s already at target: %.1f (target: %.1f)",
                position_key,
                initial_angle,
                target_angle,
            )
            return result(SeekOutcome.ALREADY_AT_TARGET, initial_angle, None)

        moving_up = target_angle > initial_angle
        current_angle: float | None = initial_angle
        timeout = policy.timeout

        # Nothing has been commanded yet, so a pending cancellation ends the
        # seek without any wire traffic, including the cleanup STOP.
        if cancel_event.is_set():
            _LOGGER.debug("Position seek cancelled before first step for %s", position_key)
            return result(SeekOutcome.CANCELLED, initial_angle, None)

        # Start movement in try-finally to guarantee stop is sent
        try:
            await policy.async_on_seek_start(self._transition(moving_up), self._stop)
            # A STOP or replacement can arrive while the policy runs its start
            # transition; never begin motion after a newer safety request.
            if cancel_event.is_set():
                _LOGGER.debug(
                    "Position seek cancelled during start transition for %s",
                    position_key,
                )
                return result(SeekOutcome.CANCELLED, initial_angle, None)
            await self._issue_step(moving_up, abs(target_angle - initial_angle))

            # Tracking variables
            stall_count = 0
            last_angle: float = initial_angle

            # Position seeking loop
            while True:
                elapsed = time.monotonic() - start_time

                # Check for timeout
                if elapsed > timeout:
                    _LOGGER.warning(
                        "Position seek timeout for %s after %.0fs",
                        position_key,
                        timeout,
                    )
                    raise SeekTimeoutError(
                        f"Position seek timed out for {position_key} after {timeout:.0f}s",
                        result(SeekOutcome.TIMEOUT, current_angle, moving_up),
                    )

                # Check for cancellation
                if cancel_event.is_set():
                    _LOGGER.debug("Position seek cancelled for %s", position_key)
                    return result(SeekOutcome.CANCELLED, current_angle, moving_up)

                # Wait and poll position
                await asyncio.sleep(policy.check_interval)

                # A STOP or replacement may arrive while the runner is waiting
                # to poll. Do not make it wait behind another GATT read.
                if cancel_event.is_set():
                    _LOGGER.debug(
                        "Position seek cancelled before feedback read for %s", position_key
                    )
                    return result(SeekOutcome.CANCELLED, current_angle, moving_up)

                # Read current position
                current_angle = await self._read_position()
                # Reading feedback can itself suspend. Never issue a chained or
                # retry step after a newer STOP or replacement landed mid-read.
                if cancel_event.is_set():
                    _LOGGER.debug(
                        "Position seek cancelled during feedback read for %s", position_key
                    )
                    return result(SeekOutcome.CANCELLED, current_angle, moving_up)

                if current_angle is None:
                    _LOGGER.warning(
                        "Lost position data for %s during seek",
                        position_key,
                    )
                    return result(SeekOutcome.POSITION_LOST, None, moving_up)

                _LOGGER.debug(
                    "Position seek %s: current=%.1f, target=%.1f",
                    position_key,
                    current_angle,
                    target_angle,
                )

                sample = SeekSample(
                    position_key=position_key,
                    target=target_angle,
                    current=current_angle,
                    previous=last_angle,
                    moving_up=moving_up,
                    elapsed=time.monotonic() - start_time,
                    stalled_checks=stall_count,
                )

                # Check if at target
                if policy.accepts_position(sample):
                    _LOGGER.info(
                        "Position %s reached target: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    return result(SeekOutcome.REACHED_TARGET, current_angle, moving_up)

                # Pulse-driven controllers can only evaluate the result of a
                # whole move burst, so once they cross the target they should
                # stop rather than hunt by reversing direction.
                if policy.completes_on_crossing(sample):
                    _LOGGER.info(
                        "Position %s crossed target in single-direction seek: %.1f (target: %.1f)",
                        position_key,
                        current_angle,
                        target_angle,
                    )
                    return result(SeekOutcome.CROSSED_TARGET, current_angle, moving_up)

                # Check for overshoot (passed the target). The ticket-local
                # cancellation event stays clear during an ordinary seek and
                # is set only by replacement, STOP, caller cancellation, or
                # shutdown, so a reversal cannot erase a newer safety action.
                # Use larger overshoot tolerance to prevent oscillation
                if policy.wants_reversal(sample):
                    _LOGGER.debug(
                        "Position %s overshot target (%s), reversing",
                        position_key,
                        "up" if moving_up else "down",
                    )
                    await policy.async_prepare_reversal(self._stop)
                    # Check if a new stop was requested while we were stopping
                    if cancel_event.is_set():
                        _LOGGER.debug("New stop request during overshoot - aborting reversal")
                        return result(SeekOutcome.CANCELLED, current_angle, moving_up)
                    moving_up = not moving_up
                    await self._issue_step(moving_up, abs(target_angle - current_angle))

                remaining_distance = abs(target_angle - current_angle)
                movement = abs(current_angle - last_angle)
                if (
                    policy.chains_steps_while_moving
                    and movement >= policy.stall_threshold
                    and remaining_distance >= policy.chain_min_remaining_distance
                ):
                    _LOGGER.debug(
                        "Position %s still moving at %.1f with %.1f remaining, chaining seek step",
                        position_key,
                        current_angle,
                        remaining_distance,
                    )
                    await self._issue_step(moving_up, remaining_distance)
                    stall_count = 0
                    last_angle = current_angle
                    continue

                # Stall detection - re-issue movement if motor stopped prematurely
                if movement < policy.stall_threshold:
                    stall_count += 1
                    if stall_count >= policy.stall_count:
                        stalled_sample = SeekSample(
                            position_key=position_key,
                            target=target_angle,
                            current=current_angle,
                            previous=last_angle,
                            moving_up=moving_up,
                            elapsed=time.monotonic() - start_time,
                            stalled_checks=stall_count,
                        )
                        if policy.stall_completes_near_endpoint(stalled_sample):
                            _LOGGER.info(
                                "Position %s stalled at %.1f near endpoint, accepting (target: %.1f)",
                                position_key,
                                current_angle,
                                target_angle,
                            )
                            return result(SeekOutcome.ENDPOINT_REACHED, current_angle, moving_up)
                        # Motor appears stalled - re-issue movement command
                        # This handles pulse-based protocols where motors auto-stop
                        _LOGGER.debug(
                            "Position %s stalled at %.1f, re-issuing movement command",
                            position_key,
                            current_angle,
                        )
                        await self._issue_step(moving_up, abs(target_angle - current_angle))
                        stall_count = 0  # Reset stall count after re-issue
                else:
                    stall_count = 0

                last_angle = current_angle
        finally:
            # Stop the motor unless this protocol ends motion solely by
            # ending its held-command refresh.
            if policy.sends_explicit_stop:
                try:
                    await self._stop()
                except Exception:
                    _LOGGER.exception(
                        "CRITICAL: Failed to stop motor %s - manual intervention may be required",
                        position_key,
                    )
                    raise
