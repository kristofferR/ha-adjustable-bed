"""Deterministic tests for the protocol-aware position seek runner and policy."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed.position_seek import (
    SEEK_REVERSAL_SETTLE_DELAY,
    PositionSeekPolicy,
    PositionSeekRunner,
    SeekMotion,
    SeekOutcome,
    SeekSample,
    SeekTimeoutError,
    SeekTransition,
    SeekTransitionKind,
)

from .conftest import make_controller_mock


def make_policy(
    policy_type: type[PositionSeekPolicy] = PositionSeekPolicy,
    *,
    auto_stops_on_idle: bool = False,
    **tuning: float | bool,
) -> PositionSeekPolicy:
    """Return a policy bound to a contract-faithful controller mock.

    Keyword tuning overrides replace the policy's class-level tuning values.
    """
    policy = policy_type(make_controller_mock(auto_stops_on_idle=auto_stops_on_idle))
    for name, value in tuning.items():
        assert name in vars(PositionSeekPolicy), f"unknown seek tuning: {name}"
        setattr(policy, name, value)
    return policy


def make_runner(
    *,
    policy: PositionSeekPolicy,
    target: float,
    readings: list[float | None],
    cancel_event: asyncio.Event | None = None,
    previous_motion: SeekMotion | None = None,
    stop: AsyncMock | None = None,
    read_side_effect=None,
) -> tuple[PositionSeekRunner, AsyncMock, AsyncMock]:
    """Build a runner fed by a synthetic feedback sequence.

    The readings list is consumed one value per poll; the final value repeats
    once exhausted so long seeks settle deterministically.
    """
    sequence = list(readings)

    async def read_position() -> float | None:
        if read_side_effect is not None:
            await read_side_effect()
        if len(sequence) > 1:
            return sequence.pop(0)
        return sequence[0]

    issue_step = AsyncMock()
    stop = stop if stop is not None else AsyncMock()
    runner = PositionSeekRunner(
        position_key="back",
        target_angle=target,
        policy=policy,
        cancel_event=cancel_event or asyncio.Event(),
        read_position=read_position,
        issue_step=issue_step,
        stop=stop,
        previous_motion=previous_motion,
    )
    return runner, issue_step, stop


def _no_sleep():
    return patch(
        "custom_components.adjustable_bed.position_seek.asyncio.sleep",
        new=AsyncMock(),
    )


class TestSeekProgress:
    """Ordinary progress toward the target."""

    async def test_progress_reaches_target(self) -> None:
        policy = make_policy()
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[10.0, 19.0])

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        assert result.final_angle == 19.0
        assert result.final_direction is True
        issue_step.assert_awaited_once_with(True, 20.0)
        # Default controllers do not auto-stop, so cleanup sends one STOP.
        stop.assert_awaited_once_with()

    async def test_initial_sample_already_at_target(self) -> None:
        policy = make_policy()
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[20.0])

        result = await runner.async_run(19.0)

        assert result.outcome is SeekOutcome.ALREADY_AT_TARGET
        assert result.final_direction is None
        issue_step.assert_not_awaited()
        stop.assert_not_awaited()

    async def test_auto_stop_controller_skips_cleanup_stop(self) -> None:
        policy = make_policy(auto_stops_on_idle=True)
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[19.0])

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        stop.assert_not_awaited()

    async def test_crossing_completes_single_direction_seek(self) -> None:
        policy = make_policy(
            reverses_on_overshoot=False,
            auto_stops_on_idle=True,
        )
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[27.0])

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.CROSSED_TARGET
        issue_step.assert_awaited_once_with(True, 20.0)
        stop.assert_not_awaited()


class TestSeekOvershoot:
    """Overshoot reversal for controllers that correct mid-flight."""

    async def test_overshoot_reverses_with_explicit_stop(self) -> None:
        policy = make_policy(tolerance=1.0)
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[27.0, 20.5])

        with _no_sleep() as sleep:
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        assert issue_step.await_args_list[0].args == (True, 20.0)
        assert issue_step.await_args_list[1].args == (False, 7.0)
        assert result.final_direction is False
        # One STOP before the reversal, one on cleanup.
        assert stop.await_count == 2
        sleep.assert_any_await(SEEK_REVERSAL_SETTLE_DELAY)

    async def test_overshoot_on_auto_stop_controller_skips_stop(self) -> None:
        policy = make_policy(tolerance=1.0, auto_stops_on_idle=True)
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[27.0, 20.5])

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        assert issue_step.await_args_list[1].args == (False, 7.0)
        stop.assert_not_awaited()

    async def test_stop_request_during_reversal_aborts_new_direction(self) -> None:
        cancel_event = asyncio.Event()
        policy = make_policy(tolerance=1.0)
        stop = AsyncMock(side_effect=lambda: cancel_event.set())
        runner, issue_step, stop = make_runner(
            policy=policy,
            target=20.0,
            readings=[27.0],
            cancel_event=cancel_event,
            stop=stop,
        )

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.CANCELLED
        # Only the initial step went out; the reversal was aborted.
        issue_step.assert_awaited_once_with(True, 20.0)


class TestSeekStall:
    """Stall detection, reissue, and endpoint completion."""

    async def test_stall_reissues_movement(self) -> None:
        policy = make_policy()
        runner, issue_step, stop = make_runner(
            policy=policy,
            target=20.0,
            readings=[10.0, 10.1, 10.2, 10.5, 19.0],
        )

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        # Initial burst plus one reissue after three stagnant reads.
        assert issue_step.await_count == 2
        assert issue_step.await_args_list[1].args == (True, 9.5)

    async def test_endpoint_policy_completes_persistent_stall(self) -> None:
        class EndpointPolicy(PositionSeekPolicy):
            def stall_completes_near_endpoint(self, sample: SeekSample) -> bool:
                return sample.target == 0.0 and sample.current <= 2.0

        policy = make_policy(EndpointPolicy, tolerance=0.75, auto_stops_on_idle=True)
        runner, issue_step, stop = make_runner(policy=policy, target=0.0, readings=[1.0])

        with _no_sleep():
            result = await runner.async_run(40.0)

        assert result.outcome is SeekOutcome.ENDPOINT_REACHED
        assert result.final_angle == 1.0
        # The endpoint path performs bounded writes: only the initial burst.
        issue_step.assert_awaited_once_with(False, 40.0)

    async def test_endpoint_policy_still_retries_mid_range_stall(self) -> None:
        class EndpointPolicy(PositionSeekPolicy):
            def stall_completes_near_endpoint(self, sample: SeekSample) -> bool:
                return sample.target == 0.0 and sample.current <= 2.0

        policy = make_policy(EndpointPolicy, tolerance=0.75, auto_stops_on_idle=True)
        runner, issue_step, stop = make_runner(
            policy=policy, target=0.0, readings=[15.0, 15.0, 15.0, 15.0, 0.5]
        )

        with _no_sleep():
            result = await runner.async_run(40.0)

        assert result.outcome is SeekOutcome.REACHED_TARGET
        # The mid-range stall was reissued rather than promoted to success.
        assert issue_step.await_count == 2


class TestSeekTermination:
    """Timeout, cancellation, feedback loss, and cleanup failure."""

    async def test_timeout_raises_typed_result_after_cleanup(self) -> None:
        policy = make_policy(timeout=0)
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[10.0])

        with pytest.raises(TimeoutError, match="Position seek timed out") as err:
            await runner.async_run(0.0)

        assert isinstance(err.value, SeekTimeoutError)
        assert err.value.result.outcome is SeekOutcome.TIMEOUT
        stop.assert_awaited_once_with()

    async def test_cancel_before_first_step_issues_nothing(self) -> None:
        cancel_event = asyncio.Event()
        cancel_event.set()
        policy = make_policy()
        runner, issue_step, stop = make_runner(
            policy=policy, target=20.0, readings=[10.0], cancel_event=cancel_event
        )

        result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.CANCELLED
        issue_step.assert_not_awaited()
        # Nothing was commanded, so no cleanup STOP goes on the wire either.
        stop.assert_not_awaited()

    async def test_cancel_during_start_transition_never_starts_motion(self) -> None:
        cancel_event = asyncio.Event()

        class SettlingPolicy(PositionSeekPolicy):
            async def async_on_seek_start(self, transition, stop) -> None:
                # A STOP/replacement lands while the policy settles the axis.
                cancel_event.set()

        policy = make_policy(SettlingPolicy)
        runner, issue_step, stop = make_runner(
            policy=policy, target=20.0, readings=[10.0], cancel_event=cancel_event
        )

        result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.CANCELLED
        issue_step.assert_not_awaited()
        # The hook may have touched the wire, so cleanup still sends STOP for
        # explicit-stop protocols.
        stop.assert_awaited_once_with()

    async def test_stop_mid_seek_cancels(self) -> None:
        cancel_event = asyncio.Event()
        policy = make_policy()

        async def set_cancel() -> None:
            cancel_event.set()

        runner, issue_step, stop = make_runner(
            policy=policy,
            target=20.0,
            readings=[10.0],
            cancel_event=cancel_event,
            read_side_effect=set_cancel,
        )

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.CANCELLED
        issue_step.assert_awaited_once_with(True, 20.0)
        stop.assert_awaited_once_with()

    async def test_lost_feedback_ends_seek(self) -> None:
        policy = make_policy()
        runner, issue_step, stop = make_runner(policy=policy, target=20.0, readings=[10.0, None])

        with _no_sleep():
            result = await runner.async_run(0.0)

        assert result.outcome is SeekOutcome.POSITION_LOST
        assert result.final_angle is None
        stop.assert_awaited_once_with()

    async def test_disconnect_during_read_still_stops_motor(self) -> None:
        policy = make_policy()

        async def boom() -> None:
            raise RuntimeError("disconnected")

        runner, issue_step, stop = make_runner(
            policy=policy,
            target=20.0,
            readings=[10.0],
            read_side_effect=boom,
        )

        with _no_sleep(), pytest.raises(RuntimeError, match="disconnected"):
            await runner.async_run(0.0)

        stop.assert_awaited_once_with()

    async def test_cleanup_stop_failure_propagates(self, caplog: pytest.LogCaptureFixture) -> None:
        policy = make_policy()
        stop = AsyncMock(side_effect=RuntimeError("stop write failed"))
        runner, issue_step, stop = make_runner(
            policy=policy, target=20.0, readings=[19.0], stop=stop
        )

        with _no_sleep(), pytest.raises(RuntimeError, match="stop write failed"):
            await runner.async_run(0.0)

        assert "CRITICAL: Failed to stop motor back" in caplog.text


class TestSeekTransitions:
    """Transition context handed to the policy at seek start."""

    @staticmethod
    def _capture_policy(**controller_overrides: object):
        transitions: list[SeekTransition] = []

        class CapturePolicy(PositionSeekPolicy):
            async def async_on_seek_start(self, transition, stop) -> None:
                transitions.append(transition)

        controller_overrides.setdefault("auto_stops_on_idle", True)
        return CapturePolicy(make_controller_mock(**controller_overrides)), transitions

    async def test_first_seek_is_initial(self) -> None:
        policy, transitions = self._capture_policy()
        runner, _issue_step, _stop = make_runner(policy=policy, target=20.0, readings=[19.0])

        with _no_sleep():
            await runner.async_run(0.0)

        assert [t.kind for t in transitions] == [SeekTransitionKind.INITIAL]
        assert transitions[0].previous is None

    async def test_replacement_distinguishes_direction(self) -> None:
        previous = SeekMotion(
            moving_up=True,
            outcome=SeekOutcome.CANCELLED,
            finished_monotonic=0.0,
        )
        policy, transitions = self._capture_policy()

        runner, _issue_step, _stop = make_runner(
            policy=policy, target=20.0, readings=[19.0], previous_motion=previous
        )
        with _no_sleep():
            await runner.async_run(0.0)

        runner, _issue_step, _stop = make_runner(
            policy=policy, target=5.0, readings=[5.5], previous_motion=previous
        )
        with _no_sleep():
            await runner.async_run(40.0)

        assert [t.kind for t in transitions] == [
            SeekTransitionKind.SAME_DIRECTION,
            SeekTransitionKind.OPPOSITE_DIRECTION,
        ]
        assert transitions[1].previous is previous
