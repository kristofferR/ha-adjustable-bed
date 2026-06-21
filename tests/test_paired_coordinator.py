"""Unit tests for PairedBedCoordinator side routing and the both-failure contract.

These use recording child doubles that log an ordered ``(side, method)`` trail and
raise where instructed, and assert on that trail (e.g. both STOPs attempted even
when one raises). That dodges the self-fulfilling-mock trap: a double that simply
returned the asserted value could hide broken fan-out logic.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.adjustable_bed.const import (
    CONF_PAIR_ID,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
    PairedSideProxy,
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
        self.connection_cb = None
        # When block=True a command waits on this gate; request_command_cancel /
        # async_stop_command release it (mirrors the real cancel-aware child).
        self._gate = asyncio.Event()
        self._block = block

    def request_command_cancel(self) -> None:
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
        self, command_fn, cancel_running=True, skip_disconnect=False
    ) -> None:
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
        return self.connect_result

    async def async_disconnect(self, reason: str = "intentional") -> None:
        self.log.append((self.side, "disconnect"))

    async def async_shutdown(self) -> None:
        self.log.append((self.side, "shutdown"))

    def register_connection_state_callback(self, callback_fn):
        self.connection_cb = callback_fn
        return lambda: None


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
        assert set(exc.value.side_errors) == {SIDE_RIGHT}

    async def test_seek_both_failure_stops_both(self):
        log: list = []
        coord, _, _ = _pair(log, left={"fail_command": True})
        with pytest.raises(PairedSideError):
            await coord.async_seek_position(
                "back", 30.0, _noop, _noop, _noop, side=SIDE_BOTH
            )
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
        assert (SIDE_RIGHT, "command") not in log  # never dispatched
        assert (SIDE_LEFT, "stop") in log

    async def test_right_failure_after_left_stops_both(self):
        log: list = []
        coord, _, _ = _pair(
            log, mode=PAIR_CONNECTION_MODE_SEQUENTIAL, right={"fail_command": True}
        )
        with pytest.raises(PairedSideError):
            await coord.async_execute_controller_command(_noop, side=SIDE_BOTH)
        assert log == [
            (SIDE_LEFT, "command"),
            (SIDE_RIGHT, "command"),
            (SIDE_LEFT, "stop"),
            (SIDE_RIGHT, "stop"),
        ]


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

    async def test_cancel_running_preempts_in_flight_children(self):
        log: list = []
        coord, left, right = _pair(log)
        # Simulate a whole-bed command currently executing under the lock.
        coord._active_children = {left, right}

        await coord.async_execute_controller_command(_noop, side=SIDE_LEFT)

        # The new side command cancelled the in-flight children before running.
        assert ("left", "cancel") in log
        assert ("right", "cancel") in log
        assert ("left", "command") in log

    async def test_stop_bumps_pair_cancel_counter(self):
        log: list = []
        coord, _left, _right = _pair(log)
        before = coord._pair_cancel_counter
        await coord.async_stop_command(side=SIDE_BOTH)
        assert coord._pair_cancel_counter == before + 1

    async def test_movement_queued_when_stop_lands_is_dropped(self):
        log: list = []
        coord, _left, _right = _pair(log)
        # Hold the lock, queue a movement, then bump the counter (a STOP landed
        # while the movement waited) before releasing.
        async with coord._pair_command_lock:
            queued = asyncio.ensure_future(
                coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
            )
            await asyncio.sleep(0.01)  # let it queue on the lock
            coord._pair_cancel_counter += 1  # a STOP landed
        await asyncio.wait_for(queued, timeout=1)
        # The queued movement saw the bumped counter and dropped — no command ran.
        assert ("left", "command") not in log


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
