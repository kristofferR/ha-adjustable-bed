"""Unit tests for PairedBedCoordinator side routing and the both-failure contract.

These use recording child doubles that log an ordered ``(side, method)`` trail and
raise where instructed, and assert on that trail (e.g. both STOPs attempted even
when one raises). That dodges the self-fulfilling-mock trap: a double that simply
returned the asserted value could hide broken fan-out logic.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.adjustable_bed.beds.okin_cb24 import OkinCB24Controller
from custom_components.adjustable_bed.beds.sbi import SBIController
from custom_components.adjustable_bed.beds.sleep_number import SleepNumberController
from custom_components.adjustable_bed.command_scheduler import (
    CommandContext,
    CommandHandle,
    CommandIntent,
    CommandKind,
    CommandOutcome,
    DeviceCommandScheduler,
    command_resources,
    current_command_context,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KAIDI,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_SBI,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_PAIR_ID,
    DOMAIN,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
    PairedSideProxy,
    SingleAddressPairedCoordinator,
)

ADDR = {SIDE_LEFT: "AA:BB:CC:DD:EE:01", SIDE_RIGHT: "AA:BB:CC:DD:EE:02"}


class RecordingChild:
    """A test double for a child coordinator that records an ordered trail."""

    def __init__(
        self,
        side: str,
        log: list[tuple[str, str]],
        *,
        connected: bool = True,
        fail_command: bool = False,
        fail_stop: bool = False,
        connect_result: bool = True,
        connect_raises: bool = False,
        block: bool = False,
        block_connect: bool = False,
        fail_disconnect: bool = False,
    ) -> None:
        self.side = side
        self.address = ADDR[side]
        self.name = f"Bed {side}"
        self.log = log
        self._connected = connected
        self.fail_command = fail_command
        self.fail_stop = fail_stop
        self.connect_result = connect_result
        self.connect_raises = connect_raises
        self.fail_disconnect = fail_disconnect
        self.connection_cb = None
        # When block=True a command waits on this gate; request_command_cancel /
        # async_stop_command release it (mirrors the real cancel-aware child).
        self._gate = asyncio.Event()
        self._block = block
        # When block_connect=True, async_connect waits on this gate (simulate a
        # STOP landing mid-connect).
        self._connect_gate = asyncio.Event()
        self._block_connect = block_connect

    def request_command_cancel(self, resource=None, *, resources=None) -> None:
        del resource, resources
        self.log.append((self.side, "cancel"))
        self._gate.set()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=self.name,
            manufacturer="Linak",
        )

    async def async_execute_controller_command(
        self,
        command_fn,
        cancel_running=True,
        skip_disconnect=False,
        resource=None,
        resources=None,
    ) -> None:
        del command_fn, cancel_running, skip_disconnect, resource, resources
        self.log.append((self.side, "command"))
        if self._block:
            await self._gate.wait()
        if self.fail_command:
            raise RuntimeError(f"{self.side} command boom")

    async def async_seek_position(
        self, position_key, target_angle, move_up_fn, move_down_fn, move_stop_fn
    ) -> None:
        self.log.append((self.side, "seek"))
        if self.fail_command:
            raise RuntimeError(f"{self.side} seek boom")

    async def async_stop_command(self) -> None:
        self.log.append((self.side, "stop"))
        self._gate.set()
        if self.fail_stop:
            raise RuntimeError(f"{self.side} stop boom")

    async def async_connect(self) -> bool:
        self.log.append((self.side, "connect"))
        if self.connect_raises:
            raise RuntimeError(f"{self.side} connect boom")
        if self._block_connect:
            await self._connect_gate.wait()
        self._connected = self.connect_result
        return self.connect_result

    async def async_disconnect(self, reason: str = "intentional") -> None:
        self.log.append((self.side, "disconnect"))
        if self.fail_disconnect:
            # A failed disconnect leaves the link up (is_connected stays True).
            raise RuntimeError(f"{self.side} disconnect boom")
        self._connected = False

    async def async_shutdown(self) -> None:
        self.log.append((self.side, "shutdown"))

    def cache_capability_controller(self) -> None:
        self.log.append((self.side, "cache_caps"))

    def register_connection_state_callback(self, callback_fn):
        self.connection_cb = callback_fn
        return lambda: None


class ScheduledRecordingChild(RecordingChild):
    """Recording child with the production prepare/commit scheduler surface."""

    def __init__(self, side: str, log: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(side, log, **kwargs)
        self.scheduler = DeviceCommandScheduler(side)
        self.prepared_scopes: list[frozenset[str]] = []

    def request_command_cancel(self, resource=None, *, resources=None) -> None:
        scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        self.scheduler.request_cancel(scope)
        super().request_command_cancel(resource, resources=resources)

    async def async_prepare_command_operation(
        self,
        operation,
        *,
        resource=None,
        resources=None,
        cancel_running=True,
        group_id,
    ) -> CommandHandle:
        async def scheduled(_context: CommandContext) -> None:
            await operation()

        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        self.prepared_scopes.append(command_scope)
        return await self.scheduler.enqueue(
            CommandIntent(
                scheduled,
                resources=command_scope,
                kind=CommandKind.GROUP,
                replacement_key=(resource or "*") if resources is None else None,
                cancel_running=cancel_running,
                group_id=group_id,
            ),
            prepared=True,
        )

    async def async_wait_prepared_command(self, handle: CommandHandle) -> None:
        await self.scheduler.wait_ready(handle)

    def commit_prepared_command(self, handle: CommandHandle) -> None:
        self.scheduler.commit(handle)

    async def async_wait_prepared_command_result(self, handle: CommandHandle) -> None:
        await self.scheduler.wait_prepared_result(handle)

    async def async_abort_prepared_command(self, handle: CommandHandle) -> None:
        await self.scheduler.cancel(handle, CommandOutcome.GROUP_ABORTED)

    async def async_stop_command(self) -> None:
        stop_epoch = self.scheduler.request_stop()
        try:
            await super().async_stop_command()
        finally:
            self.scheduler.finish_stop(stop_epoch)


def _make(children, *, connection_mode=None, name="Master Bed"):
    entry = SimpleNamespace(data={CONF_PAIR_ID: "pair_abc123", "name": name})
    return PairedBedCoordinator(
        None, entry, children, connection_mode=connection_mode
    )


def _pair(log, *, mode=None, **kw):
    left = RecordingChild(SIDE_LEFT, log, **kw.get("left", {}))
    right = RecordingChild(SIDE_RIGHT, log, **kw.get("right", {}))
    coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode=mode)
    return coord, left, right


async def _noop(_controller):
    return None


class TestSideRouting:
    async def test_both_success_runs_each_side_once_no_stop(self):
        log: list = []
        coord, _, _ = _pair(log)
        await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        assert log == [(SIDE_LEFT, "command"), (SIDE_RIGHT, "command")]

    async def test_both_waits_until_every_device_scheduler_is_ready(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        blocker_started = asyncio.Event()
        release_blocker = asyncio.Event()

        async def blocker(_context: CommandContext) -> None:
            blocker_started.set()
            await release_blocker.wait()

        blocker_task = asyncio.create_task(
            right.scheduler.execute(
                CommandIntent(
                    blocker,
                    resources=command_resources("maintenance"),
                    cancel_running=False,
                )
            )
        )
        await blocker_started.wait()

        both_task = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        await asyncio.sleep(0.01)
        assert (SIDE_LEFT, "command") not in log
        assert (SIDE_RIGHT, "command") not in log

        release_blocker.set()
        await blocker_task
        await both_task
        assert log.count((SIDE_LEFT, "command")) == 1
        assert log.count((SIDE_RIGHT, "command")) == 1

    async def test_single_queued_behind_prepared_group_does_not_block_commit(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        blocker_started = asyncio.Event()
        release_blocker = asyncio.Event()
        operations: list[str] = []

        async def blocker(_context: CommandContext) -> None:
            blocker_started.set()
            await release_blocker.wait()

        async def both_back(child: RecordingChild) -> None:
            operations.append(f"back:{child.side}")

        async def left_legs(_child: RecordingChild) -> None:
            operations.append("legs:left")

        blocker_task = asyncio.create_task(
            right.scheduler.execute(
                CommandIntent(
                    blocker,
                    resources=command_resources("maintenance"),
                    cancel_running=False,
                )
            )
        )
        await blocker_started.wait()
        both_task = asyncio.create_task(
            coord.async_run_child_operation(
                "back",
                both_back,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        while not right.scheduler.has_pending:
            await asyncio.sleep(0)

        legs_task = asyncio.create_task(
            coord.async_run_child_operation(
                "legs",
                left_legs,
                side=SIDE_LEFT,
                resource="motor:legs",
            )
        )
        await asyncio.sleep(0)
        release_blocker.set()

        await asyncio.wait_for(
            asyncio.gather(blocker_task, both_task, legs_task), timeout=1
        )
        assert operations == ["back:left", "back:right", "legs:left"]

    async def test_newer_same_axis_invalidates_prepared_single_side_command(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        coord = _make({SIDE_LEFT: left})
        blocker_started = asyncio.Event()
        release_blocker = asyncio.Event()
        operations: list[str] = []

        async def blocker(_context: CommandContext) -> None:
            blocker_started.set()
            await release_blocker.wait()

        async def first(_child: RecordingChild) -> None:
            operations.append("first")

        async def replacement(_child: RecordingChild) -> None:
            operations.append("replacement")

        blocker_task = asyncio.create_task(
            left.scheduler.execute(
                CommandIntent(
                    blocker,
                    resources=command_resources("maintenance"),
                    cancel_running=False,
                )
            )
        )
        await blocker_started.wait()
        first_task = asyncio.create_task(
            coord.async_run_child_operation(
                "first",
                first,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )
        while not left.scheduler.has_pending:
            await asyncio.sleep(0)
        replacement_task = asyncio.create_task(
            coord.async_run_child_operation(
                "replacement",
                replacement,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )

        release_blocker.set()
        await asyncio.gather(blocker_task, first_task, replacement_task)

        assert operations == ["replacement"]

    async def test_different_queued_axes_survive_prepared_single_side_wait(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        coord = _make({SIDE_LEFT: left})
        blocker_started = asyncio.Event()
        release_blocker = asyncio.Event()
        operations: list[str] = []

        async def blocker(_context: CommandContext) -> None:
            blocker_started.set()
            await release_blocker.wait()

        async def back(_child: RecordingChild) -> None:
            operations.append("back")

        async def legs(_child: RecordingChild) -> None:
            operations.append("legs")

        blocker_task = asyncio.create_task(
            left.scheduler.execute(
                CommandIntent(
                    blocker,
                    resources=command_resources("maintenance"),
                    cancel_running=False,
                )
            )
        )
        await blocker_started.wait()
        back_task = asyncio.create_task(
            coord.async_run_child_operation(
                "back",
                back,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )
        while not left.scheduler.has_pending:
            await asyncio.sleep(0)
        legs_task = asyncio.create_task(
            coord.async_run_child_operation(
                "legs",
                legs,
                side=SIDE_LEFT,
                resource="motor:legs",
            )
        )

        release_blocker.set()
        await asyncio.gather(blocker_task, back_task, legs_task)

        assert operations == ["back", "legs"]

    async def test_active_axis_replacement_bypasses_disjoint_waiting_group(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        legs_started = asyncio.Event()
        operations: list[str] = []

        async def active_legs(_child: RecordingChild) -> None:
            context = current_command_context()
            assert context is not None
            operations.append("legs:start")
            legs_started.set()
            await context.cancel_event.wait()
            operations.append("legs:cleanup")

        async def both_back(child: RecordingChild) -> None:
            operations.append(f"back:{child.side}")

        async def stop_legs(_child: RecordingChild) -> None:
            operations.append("legs:replacement")

        legs_task = asyncio.create_task(
            coord.async_run_child_operation(
                "legs",
                active_legs,
                side=SIDE_RIGHT,
                resource="motor:legs",
            )
        )
        await legs_started.wait()
        back_task = asyncio.create_task(
            coord.async_run_child_operation(
                "back",
                both_back,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        while not right.scheduler.has_pending:
            await asyncio.sleep(0)

        replacement_task = asyncio.create_task(
            coord.async_run_child_operation(
                "stop legs",
                stop_legs,
                side=SIDE_RIGHT,
                resource="motor:legs",
            )
        )
        await asyncio.wait_for(replacement_task, timeout=1)
        await asyncio.gather(legs_task, back_task)

        assert operations[:3] == [
            "legs:start",
            "legs:cleanup",
            "legs:replacement",
        ]
        assert operations[3:] == ["back:left", "back:right"]

    async def test_group_preemption_does_not_cancel_unrelated_child_axis(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        legs_started = asyncio.Event()
        release_legs = asyncio.Event()
        legs_context: CommandContext | None = None
        operations: list[str] = []

        async def active_legs(_child: RecordingChild) -> None:
            nonlocal legs_context
            legs_context = current_command_context()
            assert legs_context is not None
            operations.append("legs:start")
            legs_started.set()
            await release_legs.wait()
            operations.append("legs:end")

        async def both_back(child: RecordingChild) -> None:
            operations.append(f"group:{child.side}")

        async def replace_left_back(_child: RecordingChild) -> None:
            operations.append("back:left")

        legs_task = asyncio.create_task(
            coord.async_run_child_operation(
                "legs",
                active_legs,
                side=SIDE_RIGHT,
                resource="motor:legs",
            )
        )
        await legs_started.wait()
        group_task = asyncio.create_task(
            coord.async_run_child_operation(
                "back group",
                both_back,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        while not right.scheduler.has_pending:
            await asyncio.sleep(0)

        await coord.async_run_child_operation(
            "left back",
            replace_left_back,
            side=SIDE_LEFT,
            resource="motor:back",
        )
        await group_task

        assert legs_context is not None
        assert not legs_context.cancel_event.is_set()
        assert not legs_task.done()
        assert operations == ["legs:start", "back:left"]

        release_legs.set()
        await legs_task
        assert operations == ["legs:start", "back:left", "legs:end"]

    async def test_group_enqueue_cancellation_aborts_completed_reservations(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        right_prepare_started = asyncio.Event()
        original_prepare = right.async_prepare_command_operation

        async def delayed_prepare(*args, **kwargs):
            right_prepare_started.set()
            await asyncio.Event().wait()
            return await original_prepare(*args, **kwargs)

        right.async_prepare_command_operation = delayed_prepare  # type: ignore[method-assign]
        group_task = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        await right_prepare_started.wait()
        await asyncio.sleep(0)
        group_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await group_task

        ran = asyncio.Event()

        async def later(_context: CommandContext) -> None:
            ran.set()

        await asyncio.wait_for(
            left.scheduler.execute(CommandIntent(later, cancel_running=False)),
            timeout=1,
        )
        assert ran.is_set()

    async def test_linked_group_reserves_every_declared_resource(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})
        resources = {"motor:back", "motor:legs"}

        await coord.async_run_child_operation(
            "set positions",
            _noop,
            side=SIDE_BOTH,
            resources=resources,
        )

        assert left.prepared_scopes == [frozenset(resources)]
        assert right.prepared_scopes == [frozenset(resources)]
        left_record = left.scheduler.recent_records[-1]
        right_record = right.scheduler.recent_records[-1]
        assert left_record.kind is CommandKind.GROUP
        assert right_record.kind is CommandKind.GROUP
        assert left_record.group_id == right_record.group_id
        assert left_record.group_id is not None
        assert left_record.resources == ("motor:back", "motor:legs")
        assert right_record.resources == ("motor:back", "motor:legs")

    async def test_linked_group_replacement_is_normal_cancellation(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log, block=True)
        right = ScheduledRecordingChild(SIDE_RIGHT, log, block=True)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})

        both_task = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        while log.count((SIDE_LEFT, "command")) < 1 or log.count(
            (SIDE_RIGHT, "command")
        ) < 1:
            await asyncio.sleep(0)

        replacement = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )
        await asyncio.gather(both_task, replacement)

        first_left = log.index((SIDE_LEFT, "command"))
        second_left = log.index((SIDE_LEFT, "command"), first_left + 1)
        assert first_left < second_left
        assert (SIDE_LEFT, "stop") not in log
        assert (SIDE_RIGHT, "stop") not in log

    async def test_independent_single_sides_overlap(self):
        log: list[tuple[str, str]] = []
        coord, left, _right = _pair(log, left={"block": True})
        left_task = asyncio.create_task(
            coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
        )
        while (SIDE_LEFT, "command") not in log:
            await asyncio.sleep(0)

        await asyncio.wait_for(
            coord.async_execute_controller_command(_noop, side=SIDE_RIGHT),
            timeout=1,
        )
        assert (SIDE_RIGHT, "command") in log

        left._gate.set()
        await left_task

    async def test_different_axes_on_one_child_queue_without_cross_cancel(self):
        log: list[tuple[str, str]] = []
        left = ScheduledRecordingChild(SIDE_LEFT, log, block=True)
        right = ScheduledRecordingChild(SIDE_RIGHT, log)
        coord = _make({SIDE_LEFT: left, SIDE_RIGHT: right})

        back = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )
        while (SIDE_LEFT, "command") not in log:
            await asyncio.sleep(0)

        legs = asyncio.create_task(
            coord.async_execute_controller_command(
                _noop,
                side=SIDE_LEFT,
                resource="motor:legs",
            )
        )
        await asyncio.sleep(0.01)
        assert (SIDE_LEFT, "cancel") not in log
        assert log.count((SIDE_LEFT, "command")) == 1

        left._gate.set()
        await asyncio.gather(back, legs)
        assert log.count((SIDE_LEFT, "command")) == 2

    async def test_left_only_targets_left(self):
        log: list = []
        coord, _, _ = _pair(log)
        await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
        assert log == [(SIDE_LEFT, "command")]

    async def test_unknown_side_raises(self):
        coord, _, _ = _pair([])
        with pytest.raises(ValueError):
            await coord.async_execute_controller_command(_noop, side="middle")

    async def test_missing_side_raises(self):
        log: list = []
        coord = _make({SIDE_RIGHT: RecordingChild(SIDE_RIGHT, log)})
        assert coord.sides == (SIDE_RIGHT,)
        with pytest.raises(ValueError):
            await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)


class TestBothFailureContract:
    async def test_one_side_fails_stops_both_and_raises(self):
        log: list = []
        coord, _, _ = _pair(log, right={"fail_command": True})

        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)

        # Both commands dispatched, then BOTH sides stopped (incl. the healthy left).
        assert (SIDE_LEFT, "command") in log
        assert (SIDE_RIGHT, "command") in log
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "stop") in log
        assert set(exc.value.side_errors) == {SIDE_RIGHT}
        assert exc.value.action == "command"

    async def test_stop_failure_during_cleanup_still_stops_other_side(self):
        # right command fails AND left's STOP also fails — the other STOP must
        # still be attempted and the original error still surfaced.
        log: list = []
        coord, _, _ = _pair(
            log, left={"fail_stop": True}, right={"fail_command": True}
        )

        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)

        assert (SIDE_LEFT, "stop") in log  # attempted despite raising
        assert (SIDE_RIGHT, "stop") in log
        # The original command failure is surfaced AND the failed cleanup STOP,
        # so the caller knows the left side may still be moving.
        assert SIDE_RIGHT in exc.value.side_errors
        assert "left (stop)" in exc.value.side_errors

    async def test_seek_both_failure_stops_both(self):
        log: list = []
        coord, _, _ = _pair(log, left={"fail_command": True})
        with pytest.raises(PairedSideError):
            await coord.async_seek_position(
                "back", 30.0, _noop, _noop, _noop, side=SIDE_BOTH
            )
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "stop") in log

    async def test_cancelled_both_command_stops_both_sides(self):
        # If the parent command coroutine is cancelled (service cancellation /
        # unload) while both sides may be moving, an explicit STOP must reach
        # each side — cancelling the child tasks alone is not a STOP write.
        log: list = []
        coord, _, _ = _pair(log, left={"block": True}, right={"block": True})
        task = asyncio.ensure_future(
            coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        )
        await asyncio.sleep(0.01)  # both children dispatched and blocking
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "stop") in log


class TestStopAll:
    async def test_stop_both_attempts_each_side(self):
        log: list = []
        coord, _, _ = _pair(log)
        await coord.async_stop_command(side=SIDE_BOTH)
        assert sorted(log) == [(SIDE_LEFT, "stop"), (SIDE_RIGHT, "stop")]

    async def test_stop_failure_on_one_side_still_stops_other(self):
        log: list = []
        coord, _, _ = _pair(log, right={"fail_stop": True})
        with pytest.raises(PairedSideError) as exc:
            await coord.async_stop_command(side=SIDE_BOTH)
        assert (SIDE_LEFT, "stop") in log  # not skipped by right's failure
        assert (SIDE_RIGHT, "stop") in log
        assert set(exc.value.side_errors) == {SIDE_RIGHT}


class TestSequentialMode:
    async def test_left_failure_does_not_start_right(self):
        log: list = []
        coord, _, _ = _pair(
            log, mode=PAIR_CONNECTION_MODE_SEQUENTIAL, left={"fail_command": True}
        )
        with pytest.raises(PairedSideError):
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        # Left failed first -> the right side is never even connected.
        assert (SIDE_RIGHT, "connect") not in log
        assert (SIDE_RIGHT, "command") not in log
        # Left was released (disconnect halts it — no separate STOP, dead-man).
        assert (SIDE_LEFT, "disconnect") in log
        assert (SIDE_LEFT, "stop") not in log

    async def test_right_failure_after_left_stops_both(self):
        log: list = []
        coord, left, right = _pair(
            log, mode=PAIR_CONNECTION_MODE_SEQUENTIAL, right={"fail_command": True}
        )
        with pytest.raises(PairedSideError):
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        # Both sides end disconnected (halted): left released before right ran,
        # right released by the failure path — neither is left connected/moving.
        assert left.is_connected is False
        assert right.is_connected is False
        assert (SIDE_LEFT, "disconnect") in log
        assert (SIDE_RIGHT, "disconnect") in log


class TestConnectionLifecycle:
    def test_is_connected_is_any_side(self):
        log: list = []
        coord, left, right = _pair(log)
        left._connected = False
        right._connected = False
        assert coord.is_connected is False
        right._connected = True
        assert coord.is_connected is True

    async def test_connect_is_half_available(self):
        # One side connects, the other fails -> the pair is still up.
        log: list = []
        coord, _, _ = _pair(
            log, right={"connect_result": False}
        )
        assert await coord.async_connect() is True

    async def test_connect_tolerates_a_raising_child(self):
        log: list = []
        coord, _, _ = _pair(log, right={"connect_raises": True})
        assert await coord.async_connect() is True  # left still connected

    async def test_connect_all_fail_returns_false(self):
        log: list = []
        coord, _, _ = _pair(
            log,
            left={"connect_result": False},
            right={"connect_result": False},
        )
        assert await coord.async_connect() is False

    def test_connection_state_relay(self):
        log: list = []
        coord, left, _ = _pair(log)
        seen: list[bool] = []
        coord.register_connection_state_callback(seen.append)
        # A child reports a change -> the pair forwards the aggregate.
        assert left.connection_cb is not None
        left._connected = True
        left.connection_cb(True)
        assert seen == [True]


class TestPreemption:
    """STOP / cancel_running preempt the pair lock instead of queueing."""

    async def test_cancel_running_preempts_whole_active_whole_bed_move(self):
        log: list = []
        coord, left, right = _pair(log)
        # Simulate an active WHOLE-BED move (both children under one command).
        coord._active_children = {left, right}

        await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)

        # A left command that overlaps the in-flight whole-bed move preempts the
        # WHOLE move — both sides — not just left: the whole-bed command holds the
        # lock until both children finish, so a half-cancel would leave the right
        # side moving and stall this command.
        assert ("left", "cancel") in log
        assert ("right", "cancel") in log
        assert ("left", "command") in log

    async def test_cancel_running_leaves_independent_side_alone(self):
        log: list = []
        coord, left, _right = _pair(log)
        # Simulate an active LEFT-ONLY move.
        coord._active_children = {left}

        await coord.async_execute_controller_command(_noop, side=SIDE_RIGHT)

        # A right command that does NOT overlap the in-flight left-only move must
        # not cancel it — they're independent; right just waits its turn.
        assert ("left", "cancel") not in log
        assert ("right", "command") in log

    async def test_cancel_running_both_preempts_both_sides(self):
        log: list = []
        coord, left, right = _pair(log)
        coord._active_children = {left, right}

        await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)

        assert ("left", "cancel") in log
        assert ("right", "cancel") in log

    async def test_stop_bumps_pair_cancel_counter_per_side(self):
        log: list = []
        coord, _left, _right = _pair(log)
        before = dict(coord._pair_cancel_counter)
        await coord.async_stop_command(side=SIDE_LEFT)
        # A left-only stop bumps only the left counter.
        assert coord._pair_cancel_counter[SIDE_LEFT] == before[SIDE_LEFT] + 1
        assert coord._pair_cancel_counter[SIDE_RIGHT] == before[SIDE_RIGHT]

    async def test_concurrent_single_side_does_not_take_pair_lock(self):
        log: list = []
        coord, _left, _right = _pair(log)
        # Concurrent-mode children own independent physical schedulers. The
        # parent lock is now reserved for sequential connection switching, so a
        # left-only request does not wait behind unrelated pair metadata work.
        async with coord._pair_command_lock:
            command = asyncio.ensure_future(
                coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
            )
            await asyncio.wait_for(command, timeout=1)
        assert ("left", "command") in log

    async def test_queued_side_survives_other_side_preemption(self):
        log: list = []
        coord, _left, _right = _pair(log)
        # A queued RIGHT movement must NOT be dropped when LEFT's counter bumps
        # (an independent left reverse), only when RIGHT's does.
        async with coord._pair_command_lock:
            queued = asyncio.ensure_future(
                coord.async_execute_controller_command(_noop, side=SIDE_RIGHT)
            )
            await asyncio.sleep(0.01)
            coord._pair_cancel_counter[SIDE_LEFT] += 1  # independent left activity
        await asyncio.wait_for(queued, timeout=1)
        assert ("right", "command") in log


class TestDeviceInfo:
    def test_synthetic_parent_identity(self):
        log: list = []
        coord, _, _ = _pair(log)
        info = coord.device_info
        assert info["identifiers"] == {(DOMAIN, "pair_abc123")}
        assert info["model"] == "Adjustable Bed (paired)"
        assert info["manufacturer"] == "Linak"
        assert coord.name == "Master Bed"


class TestSideProxy:
    """Per-side entities route writes through the parent (pair lock), read child."""

    def _proxy(self):
        from unittest.mock import AsyncMock

        parent = SimpleNamespace(
            async_execute_controller_command=AsyncMock(),
            async_seek_position=AsyncMock(),
            async_stop_command=AsyncMock(),
        )
        child = SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="Left")
        return parent, child, PairedSideProxy(parent, child, SIDE_LEFT)

    def test_reads_delegate_to_child(self):
        _, child, proxy = self._proxy()
        assert proxy.address == child.address
        assert proxy.name == "Left"

    def test_writes_delegate_to_child(self):
        # timed_move temporarily tunes _motor_pulse_count on its coordinator.
        _, child, proxy = self._proxy()
        proxy._motor_pulse_count = 7
        assert child._motor_pulse_count == 7

    async def test_command_routes_through_parent_with_side(self):
        parent, _, proxy = self._proxy()

        async def cmd(_ctrl):
            return None

        await proxy.async_execute_controller_command(cmd, cancel_running=False)
        parent.async_execute_controller_command.assert_awaited_once_with(
            cmd, side=SIDE_LEFT, cancel_running=False
        )

    async def test_seek_and_stop_route_through_parent_with_side(self):
        parent, _, proxy = self._proxy()

        async def fn(_ctrl):
            return None

        await proxy.async_seek_position("back", 30.0, fn, fn, fn)
        parent.async_seek_position.assert_awaited_once_with(
            "back", 30.0, fn, fn, fn, side=SIDE_LEFT
        )

        await proxy.async_stop_command()
        parent.async_stop_command.assert_awaited_once_with(side=SIDE_LEFT)


class SingleAddressInner:
    """One physical coordinator double used by the Phase 3 routing tests."""

    def __init__(self, controller_type):
        self.address = "AA:BB:CC:DD:EE:50"
        self.name = "One-address bed"
        self.is_connected = True
        self.controller = controller_type(self)
        self.capability_controller = self.controller
        self.cancel_command = None
        self.motor_pulse_count = 1
        self.motor_pulse_delay_ms = 1
        self.position_data = {}
        self._position_callbacks = set()
        self.cancelled_position_hydrations = 0
        self.position_hydration_events: list[str] = []
        self.position_hydration_pause_count = 0

    @property
    def client(self):
        return None

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)}, name=self.name, manufacturer="Test"
        )

    async def async_execute_controller_command(self, command_fn, **_kwargs):
        await command_fn(self.controller)

    def request_command_cancel(self, resource=None, *, resources=None):
        del resource, resources
        return None

    def register_connection_state_callback(self, _callback):
        return lambda: None

    def register_position_callback(self, callback):
        self._position_callbacks.add(callback)

        def unregister():
            self._position_callbacks.discard(callback)

        return unregister

    def update_positions(self, positions):
        self.position_data.update(positions)
        for callback in list(self._position_callbacks):
            callback(self.position_data)

    async def async_connect(self):
        self.is_connected = True
        return True

    async def async_disconnect(self, _reason="intentional"):
        self.is_connected = False

    async def async_shutdown(self):
        self.is_connected = False

    async def _async_cancel_position_hydration(self):
        self.cancelled_position_hydrations += 1
        self.position_hydration_events.append("cancel")

    async def async_pause_position_hydration(self):
        self.position_hydration_pause_count += 1
        await self._async_cancel_position_hydration()

    def resume_position_hydration(self):
        self.position_hydration_pause_count -= 1


class RecordingLogicalController:
    """Minimal side-bindable controller for shared-scheduler tests."""

    def __init__(self, _coordinator) -> None:
        self.stop_sides: list[str] = []

    def bind_side(self, side: str):
        owner = self

        class BoundController:
            _side = side

            async def stop_all(self) -> None:
                owner.stop_sides.append(side)

        return BoundController()


class DirectPositionController:
    """Minimal side-bindable direct-position controller."""

    supports_direct_position_control = True

    def __init__(self, _coordinator) -> None:
        self.targets: list[tuple[str, str, int]] = []

    def bind_side(self, side: str):
        owner = self

        class BoundController:
            supports_direct_position_control = True

            @staticmethod
            def angle_to_native_position(_motor: str, angle: float) -> int:
                return round(angle)

            @staticmethod
            async def set_motor_position(motor: str, position: int) -> None:
                owner.targets.append((side, motor, position))

        return BoundController()


class ScheduledSingleAddressInner(SingleAddressInner):
    """Single physical coordinator double backed by the production scheduler."""

    def __init__(self) -> None:
        super().__init__(RecordingLogicalController)
        self.scheduler = DeviceCommandScheduler("single-address")
        self.cancel_requests = 0

    async def async_execute_controller_command(
        self,
        command_fn,
        *,
        cancel_running=True,
        resource=None,
        resources=None,
        **_kwargs,
    ):
        context = current_command_context()
        if context is not None and context.scheduler_token is self.scheduler.token:
            await command_fn(self.controller)
            return

        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )

        async def scheduled(_context: CommandContext) -> None:
            await command_fn(self.controller)

        await self.scheduler.execute(
            CommandIntent(
                scheduled,
                resources=command_scope,
                cancel_running=cancel_running,
            )
        )

    async def async_prepare_command_operation(
        self,
        operation,
        *,
        resource=None,
        resources=None,
        cancel_running=True,
        group_id,
        **_kwargs,
    ) -> CommandHandle:
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )

        async def scheduled(_context: CommandContext) -> None:
            await operation()

        return await self.scheduler.enqueue(
            CommandIntent(
                scheduled,
                resources=command_scope,
                cancel_running=cancel_running,
                group_id=group_id,
            ),
            prepared=True,
        )

    async def async_wait_prepared_command(self, handle: CommandHandle) -> None:
        await self.scheduler.wait_ready(handle)

    def commit_prepared_command(self, handle: CommandHandle) -> None:
        self.scheduler.commit(handle)

    async def async_wait_prepared_command_result(self, handle: CommandHandle) -> None:
        await self.scheduler.wait_prepared_result(handle)

    async def async_abort_prepared_command(self, handle: CommandHandle) -> None:
        await self.scheduler.cancel(handle, CommandOutcome.GROUP_ABORTED)

    def request_command_cancel(self, resource=None, *, resources=None):
        self.cancel_requests += 1
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        self.scheduler.request_cancel(command_scope)


class TestSingleAddressCoordinator:
    def _coordinator(self, bed_type, controller_type):
        entry = SimpleNamespace(
            data={CONF_PAIR_ID: "pair_single", "name": "Single", CONF_BED_TYPE: bed_type},
            entry_id="single_address",
            async_create_background_task=lambda _hass, coro, **_kwargs: asyncio.create_task(coro),
        )
        inner = SingleAddressInner(controller_type)
        inner.bed_type = bed_type
        return SingleAddressPairedCoordinator(None, entry, inner)

    def _scheduled_coordinator(self):
        entry = SimpleNamespace(
            data={
                CONF_PAIR_ID: "pair_single_scheduled",
                "name": "Single",
                CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER,
            },
            entry_id="single_address_scheduled",
            async_create_background_task=lambda _hass, coro, **_kwargs: asyncio.create_task(
                coro
            ),
        )
        inner = ScheduledSingleAddressInner()
        inner.bed_type = BED_TYPE_SLEEP_NUMBER
        return SingleAddressPairedCoordinator(None, entry, inner), inner

    async def test_sbi_uses_native_side_and_both_packets(self):
        coordinator = self._coordinator(BED_TYPE_SBI, SBIController)
        packets = []

        async def record(controller):
            packets.append(controller._build_command(0))

        await coordinator.async_execute_controller_command(record, side=SIDE_LEFT)
        await coordinator.async_execute_controller_command(record, side=SIDE_RIGHT)
        await coordinator.async_execute_controller_command(record, side=SIDE_BOTH)

        assert packets[0][0] == 0xE6 and packets[0][7] == 0x01
        assert packets[1][0] == 0xE6 and packets[1][7] == 0x02
        assert packets[2][0] == 0xE5

    async def test_sleep_number_both_serializes_left_then_right(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        sides = []

        async def record(controller):
            sides.append(controller._side)

        await coordinator.async_execute_controller_command(record, side=SIDE_BOTH)

        assert sides == [SIDE_LEFT, SIDE_RIGHT]

    async def test_native_both_direct_seek_updates_both_child_position_views(self):
        coordinator = self._coordinator(BED_TYPE_KAIDI, DirectPositionController)
        left = coordinator.children[SIDE_LEFT]
        right = coordinator.children[SIDE_RIGHT]
        left_updates = []
        right_updates = []
        left.register_position_callback(left_updates.append)
        right.register_position_callback(right_updates.append)

        move = AsyncMock()
        await coordinator.async_seek_position(
            "back", 42, move, move, move, side=SIDE_BOTH
        )

        assert coordinator._single_inner.controller.targets == [
            (SIDE_BOTH, "back", 42)
        ]
        assert left.position_data == {"back": 42}
        assert right.position_data == {"back": 42}
        assert left_updates == [{"back": 42}]
        assert right_updates == [{"back": 42}]

    async def test_shared_scheduler_keeps_same_axis_sides_independent(self):
        coordinator, _inner = self._scheduled_coordinator()
        left_started = asyncio.Event()
        release_left = asyncio.Event()
        right_started = asyncio.Event()
        left_context: CommandContext | None = None

        async def left(_controller) -> None:
            nonlocal left_context
            left_context = current_command_context()
            assert left_context is not None
            left_started.set()
            await release_left.wait()

        async def right(_controller) -> None:
            right_started.set()

        left_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                left,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )
        await left_started.wait()
        right_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                right,
                side=SIDE_RIGHT,
                resource="motor:back",
            )
        )
        await asyncio.sleep(0.01)

        assert left_context is not None
        assert not left_context.cancel_event.is_set()
        assert not right_started.is_set()

        release_left.set()
        await asyncio.gather(left_task, right_task)
        assert right_started.is_set()

    async def test_sleep_number_both_stop_preserves_each_side_write(self):
        coordinator, inner = self._scheduled_coordinator()

        await coordinator.async_stop_command(side=SIDE_BOTH)

        assert inner.cancel_requests == 1
        assert inner.controller.stop_sides == [SIDE_LEFT, SIDE_RIGHT]

    async def test_sleep_number_replacement_aborts_stale_both_fanout(self):
        coordinator, _inner = self._scheduled_coordinator()
        left_started = asyncio.Event()
        sides: list[str] = []

        async def old_both(controller) -> None:
            sides.append(f"old:{controller._side}")
            if controller._side == SIDE_LEFT:
                context = current_command_context()
                assert context is not None
                left_started.set()
                await context.cancel_event.wait()

        async def replacement(controller) -> None:
            sides.append(f"new:{controller._side}")

        both_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                old_both,
                side=SIDE_BOTH,
                resource="motor:back",
            )
        )
        await left_started.wait()
        replacement_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                replacement,
                side=SIDE_LEFT,
                resource="motor:back",
            )
        )

        await asyncio.gather(both_task, replacement_task)
        assert sides == ["old:left", "new:left"]

    @pytest.mark.parametrize(
        ("bed_type", "controller_type"),
        [
            (BED_TYPE_SBI, SBIController),
            (BED_TYPE_SLEEP_NUMBER, SleepNumberController),
        ],
    )
    async def test_cancelled_both_command_runs_stop_cleanup(
        self, bed_type, controller_type
    ):
        coordinator = self._coordinator(bed_type, controller_type)
        command_started = asyncio.Event()
        stop_children = AsyncMock(return_value={})
        coordinator._stop_children = stop_children

        async def block(_controller):
            command_started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(
            coordinator.async_execute_controller_command(block, side=SIDE_BOTH)
        )
        await command_started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        stop_children.assert_awaited_once()

    async def test_sleep_number_reconnect_hydrates_each_logical_side(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        events = coordinator._single_inner.position_hydration_events

        for side, child in coordinator.children.items():

            async def hydrate(*, logical_side=side):
                events.append(logical_side)

            object.__setattr__(child, "async_read_initial_positions", hydrate)

        coordinator._on_child_connection_change(True)
        task = coordinator._single_position_hydration_task
        assert task is not None
        await task

        assert events == ["cancel", SIDE_LEFT, SIDE_RIGHT]
        assert coordinator._single_inner.cancelled_position_hydrations == 1

    async def test_sleep_number_preempted_hydration_is_rescheduled(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        calls = {SIDE_LEFT: 0, SIDE_RIGHT: 0}

        for side, child in coordinator.children.items():

            async def hydrate(*, logical_side=side):
                calls[logical_side] += 1
                if calls[logical_side] == 1:
                    raise asyncio.CancelledError

            object.__setattr__(child, "async_read_initial_positions", hydrate)

        coordinator._on_child_connection_change(True)
        first_task = coordinator._single_position_hydration_task
        assert first_task is not None
        await first_task

        retry_task = coordinator._single_position_hydration_task
        assert retry_task is not None
        assert retry_task is not first_task
        await retry_task

        assert calls == {SIDE_LEFT: 2, SIDE_RIGHT: 2}
        assert coordinator._single_position_hydration_task is None

    async def test_sleep_number_reconnect_replaces_inflight_hydration(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        started = asyncio.Event()
        release = asyncio.Event()

        async def hydrate():
            started.set()
            await release.wait()

        for child in coordinator.children.values():
            object.__setattr__(child, "async_read_initial_positions", hydrate)

        coordinator._on_child_connection_change(True)
        first_task = coordinator._single_position_hydration_task
        assert first_task is not None
        await started.wait()

        coordinator._on_child_connection_change(True)
        second_task = coordinator._single_position_hydration_task
        assert second_task is not None
        assert second_task is not first_task
        release.set()
        await asyncio.gather(first_task, return_exceptions=True)
        await second_task

        assert first_task.cancelled()
        assert coordinator._single_inner.cancelled_position_hydrations == 2

    async def test_sleep_number_disconnect_cancels_queued_logical_hydration(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        hydration_queued = asyncio.Event()
        hydrated = False

        async def wait_for_command():
            hydration_queued.set()
            await asyncio.Event().wait()

        async def hydrate():
            nonlocal hydrated
            hydrated = True

        coordinator._single_inner._async_cancel_position_hydration = wait_for_command
        for child in coordinator.children.values():
            object.__setattr__(child, "async_read_initial_positions", hydrate)

        coordinator._on_child_connection_change(True)
        task = coordinator._single_position_hydration_task
        assert task is not None
        await hydration_queued.wait()

        coordinator._on_child_connection_change(False)
        with pytest.raises(asyncio.CancelledError):
            await task

        assert not hydrated
        assert coordinator._single_position_hydration_task is None

    async def test_sleep_number_diagnostics_pause_logical_hydration(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        side = coordinator.children[SIDE_LEFT]
        hydrated = asyncio.Event()

        async def hydrate():
            hydrated.set()

        for child in coordinator.children.values():
            object.__setattr__(child, "async_read_initial_positions", hydrate)

        await side.async_pause_position_hydration()
        coordinator._on_child_connection_change(True)
        await asyncio.sleep(0)

        assert not hydrated.is_set()
        assert coordinator._single_position_hydration_task is None
        assert coordinator._single_inner.position_hydration_pause_count == 1

        side.resume_position_hydration()
        task = cast(
            asyncio.Task[None], coordinator._single_position_hydration_task
        )
        await task

        assert hydrated.is_set()
        assert coordinator._single_inner.position_hydration_pause_count == 0

    async def test_cancel_hydration_preserves_callers_cancellation(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        hydration_started = asyncio.Event()
        hydration_cancelled = asyncio.Event()

        async def hydrate():
            hydration_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                hydration_cancelled.set()
                await asyncio.Event().wait()

        hydration_task = asyncio.create_task(hydrate())
        coordinator._single_position_hydration_task = hydration_task
        await hydration_started.wait()

        cancel_task = asyncio.create_task(
            coordinator._async_cancel_single_position_hydration()
        )
        await hydration_cancelled.wait()
        cancel_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await cancel_task
        assert hydration_task.cancelled()
        assert coordinator._single_position_hydration_task is None

    async def test_shutdown_cancellation_finishes_single_address_cleanup(self):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        hydration_started = asyncio.Event()
        hydration_cancelled = asyncio.Event()
        inner_shutdown = asyncio.Event()

        async def hydrate():
            hydration_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                hydration_cancelled.set()
                await asyncio.Event().wait()

        async def shutdown_inner():
            inner_shutdown.set()

        hydration_task = asyncio.create_task(hydrate())
        coordinator._single_position_hydration_task = hydration_task
        object.__setattr__(
            coordinator._single_inner,
            "async_shutdown",
            shutdown_inner,
        )
        await hydration_started.wait()

        shutdown_task = asyncio.create_task(coordinator.async_shutdown())
        await hydration_cancelled.wait()

        coordinator._on_child_connection_change(True)
        assert coordinator._single_position_hydration_task is hydration_task

        shutdown_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await shutdown_task

        assert hydration_task.cancelled()
        assert coordinator._single_position_hydration_task is None
        assert coordinator._child_unsubs == []
        assert coordinator._single_inner._position_callbacks == set()
        assert inner_shutdown.is_set()

    async def test_sleep_number_reconnect_stops_hydration_after_swallowed_cancel(
        self,
    ):
        coordinator = self._coordinator(BED_TYPE_SLEEP_NUMBER, SleepNumberController)
        cancel_started = asyncio.Event()
        cancel_calls = 0
        hydration_calls = 0

        async def cancel_inner_hydration():
            nonlocal cancel_calls
            cancel_calls += 1
            if cancel_calls != 1:
                return
            cancel_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Model an inner cancellation helper consuming the parent
                # hydration task's cancellation while awaiting its own task.
                return

        async def hydrate():
            nonlocal hydration_calls
            hydration_calls += 1

        coordinator._single_inner._async_cancel_position_hydration = (
            cancel_inner_hydration
        )
        for child in coordinator.children.values():
            object.__setattr__(child, "async_read_initial_positions", hydrate)

        coordinator._on_child_connection_change(True)
        first_task = coordinator._single_position_hydration_task
        assert first_task is not None
        await cancel_started.wait()

        coordinator._on_child_connection_change(True)
        second_task = coordinator._single_position_hydration_task
        assert second_task is not None
        await asyncio.gather(first_task, return_exceptions=True)
        await second_task

        assert first_task.cancelled()
        assert hydration_calls == 2

    async def test_bond_actions_reach_the_coordinator_that_owns_the_link(self):
        """This surface keeps the entry's address, so it is offered bond removal.

        The locks and the link live on the inner coordinator, so a gate that
        stopped at the wrapper would guard nothing, and the removal would fail
        on a missing attribute instead.
        """
        coordinator = self._coordinator(BED_TYPE_SBI, SBIController)
        inner = coordinator._single_inner
        entered: list[str] = []
        applied: list[bool] = []

        @contextlib.asynccontextmanager
        async def gate(operation: str):
            entered.append(operation)
            yield

        inner.async_transport_operation = gate
        inner.apply_confirmed_bond_removal = lambda: applied.append(True)

        async with coordinator.async_transport_operation("unpair"):
            coordinator.apply_confirmed_bond_removal()

        assert entered == ["unpair"]
        assert applied == [True]

    def test_side_and_combined_ids_share_the_mac_device(self):
        coordinator = self._coordinator(BED_TYPE_SBI, SBIController)
        left = coordinator.children[SIDE_LEFT]

        assert left.entity_unique_id("back") == "AA:BB:CC:DD:EE:50_back_left"
        assert coordinator.entity_unique_id("back_up_both") == (
            "AA:BB:CC:DD:EE:50_back_up_both"
        )
        assert coordinator.device_info["identifiers"] == {
            (DOMAIN, "AA:BB:CC:DD:EE:50")
        }

    def test_shared_cb24_position_updates_relay_to_each_side(self):
        coordinator = self._coordinator(BED_TYPE_OKIN_CB24, OkinCB24Controller)
        left = coordinator.children[SIDE_LEFT]
        right = coordinator.children[SIDE_RIGHT]
        left_updates = []
        right_updates = []
        left.register_position_callback(left_updates.append)
        right.register_position_callback(right_updates.append)

        coordinator._single_inner.update_positions({"back": 42.0})

        assert left.position_data == {"back": 42.0}
        assert right.position_data == {"back": 42.0}
        assert left_updates == [{"back": 42.0}]
        assert right_updates == [{"back": 42.0}]

    async def test_cb24_shutdown_unregisters_shared_position_relays(self):
        coordinator = self._coordinator(BED_TYPE_OKIN_CB24, OkinCB24Controller)
        inner = coordinator._single_inner

        assert len(inner._position_callbacks) == 3

        await coordinator.async_shutdown()

        assert inner._position_callbacks == set()

    async def test_sbi_position_updates_remain_side_scoped(self):
        coordinator = self._coordinator(BED_TYPE_SBI, SBIController)
        left = coordinator.children[SIDE_LEFT]
        right = coordinator.children[SIDE_RIGHT]
        left_updates = []
        right_updates = []
        left.register_position_callback(left_updates.append)
        right.register_position_callback(right_updates.append)

        async def update_position(_controller):
            coordinator._single_inner.update_positions({"back": 42.0})

        await coordinator.async_execute_controller_command(
            update_position, side=SIDE_LEFT
        )

        assert left.position_data == {"back": 42.0}
        assert right.position_data == {}
        assert left_updates == [{"back": 42.0}]
        assert right_updates == []


class TestConnectionModeResolution:
    """Phase 2.5 C1: 'auto' resolves to sequential for single-connection beds
    (Octo) and concurrent for everything else; an explicit choice is honoured."""

    def _coord(self, bed_type, *, mode=None):
        entry = SimpleNamespace(
            data={CONF_PAIR_ID: "pair_abc123", "name": "X", CONF_BED_TYPE: bed_type}
        )
        children = {
            SIDE_LEFT: RecordingChild(SIDE_LEFT, []),
            SIDE_RIGHT: RecordingChild(SIDE_RIGHT, []),
        }
        return PairedBedCoordinator(None, entry, children, connection_mode=mode)

    def test_auto_resolves_sequential_for_octo(self):
        assert (
            self._coord(BED_TYPE_OCTO).connection_mode
            == PAIR_CONNECTION_MODE_SEQUENTIAL
        )

    def test_auto_resolves_concurrent_for_linak(self):
        assert (
            self._coord(BED_TYPE_LINAK).connection_mode
            == PAIR_CONNECTION_MODE_CONCURRENT
        )

    def test_explicit_concurrent_preserved_for_octo(self):
        assert (
            self._coord(BED_TYPE_OCTO, mode=PAIR_CONNECTION_MODE_CONCURRENT).connection_mode
            == PAIR_CONNECTION_MODE_CONCURRENT
        )

    def test_explicit_sequential_preserved_for_linak(self):
        assert (
            self._coord(BED_TYPE_LINAK, mode=PAIR_CONNECTION_MODE_SEQUENTIAL).connection_mode
            == PAIR_CONNECTION_MODE_SEQUENTIAL
        )


class TestSequentialCycle:
    """Phase 2.5 C2: single-connection beds (Octo) hold ONE BLE link at a time —
    connect/op/disconnect each side in turn, never two links at once."""

    SEQ = PAIR_CONNECTION_MODE_SEQUENTIAL

    @staticmethod
    def _seq(log, **kw):
        # Sequential pair at steady state: both sides start DISCONNECTED, so the
        # pre-connect one-link release is a no-op (the realistic precondition).
        left = {**kw.pop("left", {}), "connected": False}
        right = {**kw.pop("right", {}), "connected": False}
        return _pair(log, mode=PAIR_CONNECTION_MODE_SEQUENTIAL, left=left, right=right)

    async def test_both_success_connects_acts_disconnects_each_in_turn(self):
        log: list = []
        coord, _, _ = self._seq(log)
        await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        # The one-link invariant: A is fully disconnected BEFORE B connects.
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "command"),
            (SIDE_LEFT, "disconnect"),
            (SIDE_RIGHT, "connect"),
            (SIDE_RIGHT, "command"),
            (SIDE_RIGHT, "disconnect"),
        ]

    async def test_single_side_connects_acts_disconnects(self):
        log: list = []
        coord, _, _ = self._seq(log)
        await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "command"),
            (SIDE_LEFT, "disconnect"),
        ]

    async def test_side_b_op_failure_disconnects_both_no_reconnect(self):
        log: list = []
        coord, _, _ = self._seq(log, right={"fail_command": True})
        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        # A finished + released; B connected, command failed, still disconnected
        # by the finally. The already-disconnected A is NOT reconnected to STOP.
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "command"),
            (SIDE_LEFT, "disconnect"),
            (SIDE_RIGHT, "connect"),
            (SIDE_RIGHT, "command"),
            (SIDE_RIGHT, "disconnect"),
        ]
        assert (SIDE_LEFT, "stop") not in log
        assert set(exc.value.side_errors) == {SIDE_RIGHT}

    async def test_side_b_connect_failure_breaks_no_op_on_b(self):
        log: list = []
        coord, _, _ = self._seq(log, right={"connect_raises": True})
        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        # B's connect raised -> no command/disconnect on B; A already released.
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "command"),
            (SIDE_LEFT, "disconnect"),
            (SIDE_RIGHT, "connect"),
        ]
        assert set(exc.value.side_errors) == {SIDE_RIGHT}

    async def test_stop_only_targets_a_still_connected_side(self):
        log: list = []
        # left still connected (mid-move), right already released.
        coord, left, right = _pair(log, mode=self.SEQ)
        right._connected = False
        await coord.async_stop_command(side=SIDE_BOTH)
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "stop") not in log  # not reconnected just to STOP

    async def test_async_connect_verifies_then_releases_each_side(self):
        log: list = []
        coord, _, _ = self._seq(log)
        assert await coord.async_connect() is True
        # Each side connected to verify reachability, cached its caps, then
        # released (steady state: both disconnected) — never both at once.
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "cache_caps"),
            (SIDE_LEFT, "disconnect"),
            (SIDE_RIGHT, "connect"),
            (SIDE_RIGHT, "cache_caps"),
            (SIDE_RIGHT, "disconnect"),
        ]

    async def test_async_connect_aborts_if_release_fails(self):
        # If releasing the just-verified side fails, the verify loop must NOT go
        # on to connect the other side — that would hold two links at once, which
        # the single-connection profile forbids (the reference app strictly
        # disconnects-before-connect and aborts on a genuine disconnect error).
        log: list = []
        coord, _, _ = self._seq(log, left={"fail_disconnect": True})
        # Left connected, so setup still succeeds (one side reachable)...
        assert await coord.async_connect() is True
        # ...but its failed release stops the loop: right is never connected, so
        # we never momentarily hold both links.
        assert log == [
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "cache_caps"),
            (SIDE_LEFT, "disconnect"),  # raised -> _safe_disconnect False -> break
        ]
        assert (SIDE_RIGHT, "connect") not in log

    async def test_op_and_disconnect_both_fail_surfaces_both(self):
        # If a side's command fails AND its release then also fails, the disconnect
        # failure (link may still be live/moving) must not be dropped — the side
        # error reflects both, with the original op error as its cause.
        log: list = []
        coord, _, _ = self._seq(
            log, left={"fail_command": True, "fail_disconnect": True}
        )
        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        err = exc.value.side_errors[SIDE_LEFT]
        assert "release also failed" in str(err)
        assert isinstance(err.__cause__, RuntimeError)  # the original command error
        # The loop broke on left; right is never connected.
        assert (SIDE_RIGHT, "connect") not in log

    async def test_stop_mid_cycle_aborts_remaining_side(self):
        log: list = []
        coord, left, right = self._seq(log, left={"block": True})
        cmd = asyncio.ensure_future(
            coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        )
        # Wait until the cycle has connected left and reached its blocked command.
        while (SIDE_LEFT, "command") not in log:
            await asyncio.sleep(0)
        # STOP while left is mid-command: bumps both counters, stops + releases left.
        await coord.async_stop_command(side=SIDE_BOTH)
        await cmd
        # The cycle aborts after the mid-cycle STOP — right is never connected.
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "connect") not in log

    async def test_cross_side_cancel_aborts_remaining_side(self):
        # A both-cycle where, while LEFT is mid-command, a STOP for LEFT ONLY lands.
        # RIGHT's own cancel counter is untouched, but the cycle is cancelled, so
        # RIGHT must not connect — checking only the about-to-run side would miss
        # an earlier targeted side's cancellation and open a second link.
        log: list = []
        coord, _, _ = self._seq(log, left={"block": True})
        cmd = asyncio.ensure_future(
            coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        )
        while (SIDE_LEFT, "command") not in log:
            await asyncio.sleep(0)
        await coord.async_stop_command(side=SIDE_LEFT)  # left only — not both
        await cmd
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "connect") not in log

    async def test_releases_other_connected_side_before_connecting(self):
        # A left command while the right side is already connected out-of-band
        # (e.g. its diagnostic Connect button) releases right FIRST. (#390 :370)
        log: list = []
        coord, _, _ = _pair(
            log, mode=self.SEQ, left={"connected": False}, right={"connected": True}
        )
        await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
        assert log == [
            (SIDE_RIGHT, "disconnect"),  # one-link guard: release the other first
            (SIDE_LEFT, "connect"),
            (SIDE_LEFT, "command"),
            (SIDE_LEFT, "disconnect"),
        ]

    async def test_stop_during_connect_skips_op(self):
        # A STOP accepted WHILE the side is still connecting must not then start a
        # motor command once connect completes. (#390 :380)
        log: list = []
        coord, left, _ = self._seq(log, left={"block_connect": True})
        cmd = asyncio.ensure_future(
            coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
        )
        while (SIDE_LEFT, "connect") not in log:
            await asyncio.sleep(0)
        await coord.async_stop_command(side=SIDE_LEFT)  # bumps the cancel counter
        left._connect_gate.set()  # let connect finish
        await cmd
        assert (SIDE_LEFT, "command") not in log  # op never ran after the STOP
        assert (SIDE_LEFT, "disconnect") in log  # link released

    async def test_disconnect_failure_aborts_cycle(self):
        # If releasing the just-operated side fails, abort rather than connect the
        # next side onto a still-live link. (#390 :401)
        log: list = []
        coord, _, _ = self._seq(log, left={"fail_disconnect": True})
        with pytest.raises(PairedSideError) as exc:
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        assert (SIDE_RIGHT, "connect") not in log  # never reached the second side
        assert SIDE_LEFT in exc.value.side_errors
