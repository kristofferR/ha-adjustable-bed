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
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
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

    async def test_movement_queued_when_stop_lands_is_dropped(self):
        log: list = []
        coord, _left, _right = _pair(log)
        # Hold the lock, queue a LEFT movement, then bump LEFT's counter (a stop
        # landed while it waited) before releasing.
        async with coord._pair_command_lock:
            queued = asyncio.ensure_future(
                coord.async_execute_controller_command(_noop, side=SIDE_LEFT)
            )
            await asyncio.sleep(0.01)  # let it queue on the lock
            coord._pair_cancel_counter[SIDE_LEFT] += 1  # a left STOP landed
        await asyncio.wait_for(queued, timeout=1)
        # The queued movement saw the bumped counter and dropped — no command ran.
        assert ("left", "command") not in log

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
