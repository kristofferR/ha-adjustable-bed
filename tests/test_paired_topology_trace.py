"""Trace identity for every paired-bed topology (#524).

Each scenario drives a real ``PairedBedCoordinator`` over real child
coordinators, schedulers and controllers. Only the BLE link is simulated: a
connect takes virtual time and installs a recording client. Under the wire
snapshot's virtual clock the trace records, with timestamps:

- every GATT write (characteristic, bytes, write mode) and link drop;
- every call the paired layer makes into a physical coordinator (connect,
  disconnect, command, reservation, commit, abort, cancel, STOP, connection
  hold, idle-timer arm, shutdown);
- each caller's outcome.

The committed fixture was recorded from the topology code before its
extraction into strategies. A routing refactor must reproduce it exactly. A
deliberate behavior change regenerates it in the same PR:

    PAIRED_TOPOLOGY_TRACE_RECORD=1 uv run --no-sync pytest -n 0 \
        tests/test_paired_topology_trace.py
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import json
import os
import sys
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    DOMAIN,
    PAIR_CONNECTION_MODE_AUTO,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_MODE_SINGLE_ADDRESS,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
    SingleAddressPairedCoordinator,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "paired_topology_traces.json"
RECORD = os.environ.get("PAIRED_TOPOLOGY_TRACE_RECORD") == "1"

CONNECT_S = 0.25
DISCONNECT_S = 0.05
SCENARIO_BUDGET_S = 30.0
ADDRESSES = {SIDE_LEFT: "AA:BB:CC:DD:EE:01", SIDE_RIGHT: "AA:BB:CC:DD:EE:02"}
SINGLE_ADDRESS = "AA:BB:CC:DD:EE:03"


def _load_wire_tool() -> Any:
    path = REPO_ROOT / "scripts" / "wire_snapshot.py"
    spec = importlib.util.spec_from_file_location("paired_trace_wire_snapshot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


WIRE = _load_wire_tool()
LAYOUTS = json.loads(WIRE.LAYOUTS_PATH.read_text())


class Trace:
    """Ordered, timestamped events from every physical coordinator."""

    def __init__(self, clock: Any) -> None:
        self.clock = clock
        self.events: list[list[Any]] = []

    def add(self, who: str, *event: Any) -> None:
        self.clock.activity += 1
        self.events.append([round(self.clock.now * 1000), who, *event])


class TraceClient:
    """A connected link whose GATT traffic and teardown are recorded."""

    def __init__(self, who: str, trace: Trace, layout: dict[str, Any]) -> None:
        self._who = who
        self._trace = trace
        self.services = WIRE.FakeServices(layout)
        self.is_connected = True
        self.address = who
        self.mtu_size = 185

    async def write_gatt_char(self, char: Any, data: Any, response: bool | None = None) -> None:
        uuid = str(getattr(char, "uuid", char)).lower()[:8]
        self._trace.add(self._who, "write", uuid, bytes(data).hex(), response)
        await asyncio.sleep(WIRE.WRITE_DURATION_S)

    async def start_notify(self, char: Any, _callback: Any, **_: Any) -> None:
        self._trace.add(self._who, "notify", str(getattr(char, "uuid", char)).lower()[:8])

    async def stop_notify(self, char: Any) -> None:
        self._trace.add(self._who, "unnotify", str(getattr(char, "uuid", char)).lower()[:8])

    async def read_gatt_char(self, char: Any, **_: Any) -> bytearray:
        self._trace.add(self._who, "read", str(getattr(char, "uuid", char)).lower()[:8])
        return bytearray()

    async def disconnect(self) -> bool:
        self._trace.add(self._who, "link_down")
        await asyncio.sleep(DISCONNECT_S)
        self.is_connected = False
        return True


def _scope(kwargs: dict[str, Any]) -> list[str] | None:
    resources = kwargs.get("resources")
    if resources is None and kwargs.get("resource") is not None:
        resources = (kwargs["resource"],)
    return None if resources is None else sorted(resources)


def _instrument(coordinator: AdjustableBedCoordinator, who: str, trace: Trace) -> None:
    """Record the paired layer's calls into one physical coordinator."""

    def wrap_async(name: str, describe: Callable[..., list[Any]]) -> None:
        original = getattr(coordinator, name)

        async def recorded(*args: Any, **kwargs: Any) -> Any:
            trace.add(who, name, *describe(*args, **kwargs))
            try:
                result = await original(*args, **kwargs)
            except asyncio.CancelledError:
                trace.add(who, f"{name}:cancelled")
                raise
            except Exception as err:
                trace.add(who, f"{name}:raised", type(err).__name__)
                raise
            trace.add(who, f"{name}:done", result if isinstance(result, bool) else None)
            return result

        object.__setattr__(coordinator, name, recorded)

    def wrap_sync(name: str, describe: Callable[..., list[Any]]) -> None:
        original = getattr(coordinator, name)

        def recorded(*args: Any, **kwargs: Any) -> Any:
            trace.add(who, name, *describe(*args, **kwargs))
            return original(*args, **kwargs)

        object.__setattr__(coordinator, name, recorded)

    def command(_fn: Any, *args: Any, **kwargs: Any) -> list[Any]:
        kind = kwargs.get("kind")
        cancel_running = args[0] if args else kwargs.get("cancel_running", True)
        return [
            _scope(kwargs),
            bool(cancel_running),
            getattr(kind, "value", None),
            kwargs.get("expected_stop_epoch"),
        ]

    def prepare(_fn: Any, **kwargs: Any) -> list[Any]:
        return [_scope(kwargs), kwargs.get("cancel_running"), kwargs.get("expected_stop_epoch")]

    def handle(handle: Any) -> list[Any]:
        return [getattr(getattr(handle, "outcome", None), "value", None)]

    def nothing(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def cancel(resource: Any = None, **kwargs: Any) -> list[Any]:
        return [_scope({"resource": resource, **kwargs})]

    wrap_async("async_connect", nothing)
    wrap_async("async_disconnect", lambda reason="intentional", **_: [reason])
    wrap_async("async_execute_controller_command", command)
    wrap_async("async_prepare_command_operation", prepare)
    wrap_async("async_wait_prepared_command", handle)
    wrap_async("async_wait_prepared_command_result", handle)
    wrap_async("async_abort_prepared_command", handle)
    wrap_async("async_stop_command", nothing)
    wrap_async("async_shutdown", nothing)
    wrap_sync("commit_prepared_command", handle)
    wrap_sync("request_command_cancel", cancel)
    wrap_sync("cache_capability_controller", nothing)
    wrap_sync("_reset_disconnect_timer", nothing)

    original_hold = coordinator.hold_command_connection

    @contextlib.contextmanager
    def hold() -> Iterator[None]:
        trace.add(who, "hold")
        try:
            with original_hold():
                yield
        finally:
            trace.add(who, "release")

    object.__setattr__(coordinator, "hold_command_connection", hold)


def _physical(
    hass: HomeAssistant,
    trace: Trace,
    who: str,
    address: str,
    bed_type: str,
    failing: frozenset[str],
    **entry_data: Any,
) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": address,
            "name": f"Bed {who}",
            CONF_BED_TYPE: bed_type,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            **entry_data,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    layout = LAYOUTS[bed_type]

    async def connect_locked(self: AdjustableBedCoordinator, reset_timer: bool = True) -> bool:
        trace.add(who, "link_up")
        self._connection_attempt_count += 1
        attempt: dict[str, Any] = {"selected_source": "proxy", "actual_source": "proxy"}
        self._connection_attempt_details.append(attempt)
        await asyncio.sleep(CONNECT_S)
        slot_exhausted = f"slot:{who}" in failing or (
            f"slot-later:{who}" in failing and self._connection_attempt_count > 1
        )
        if f"connect:{who}" in failing or slot_exhausted:
            attempt["error"] = "No free connection slot" if slot_exhausted else "Unreachable"
            trace.add(who, "link_failed", attempt["error"])
            return False
        self._connection_source = "proxy"
        client = TraceClient(who, trace, layout)
        self._client = client  # type: ignore[assignment]
        self._controller = await create_controller(self, bed_type, None, client)  # type: ignore[arg-type]
        self._notify_connection_state_change(True)
        if reset_timer:
            self._reset_disconnect_timer()
        return True

    object.__setattr__(coordinator, "_async_connect_locked", MethodType(connect_locked, coordinator))
    _instrument(coordinator, who, trace)
    return coordinator


@dataclass(frozen=True)
class Topology:
    id: str
    build: Callable[[HomeAssistant, Trace, frozenset[str]], PairedBedCoordinator]


def _two_link(mode: str) -> Callable[[HomeAssistant, Trace, frozenset[str]], PairedBedCoordinator]:
    def build(hass: HomeAssistant, trace: Trace, failing: frozenset[str]) -> PairedBedCoordinator:
        children = {
            side: _physical(hass, trace, side, ADDRESSES[side], BED_TYPE_RICHMAT, failing)
            for side in (SIDE_LEFT, SIDE_RIGHT)
        }
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: f"pair-{mode}"})
        entry.add_to_hass(hass)
        return PairedBedCoordinator(hass, entry, children, connection_mode=mode)

    return build


def _single_link(native_both: bool) -> Callable[[HomeAssistant, Trace, frozenset[str]], PairedBedCoordinator]:
    def build(hass: HomeAssistant, trace: Trace, failing: frozenset[str]) -> PairedBedCoordinator:
        inner = _physical(hass, trace, "link", SINGLE_ADDRESS, BED_TYPE_OKIN_CB24, failing)
        # Non-native Both: a profile with left/right frames but no shared one.
        # The parent runs both side frames on the one link (the Sleep Number rule).
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_PAIR_ID: "pair-single",
                CONF_BED_TYPE: BED_TYPE_OKIN_CB24 if native_both else BED_TYPE_SLEEP_NUMBER,
            },
        )
        entry.add_to_hass(hass)
        return SingleAddressPairedCoordinator(hass, entry, inner)

    return build


def _single_link_legacy_feedback(
    hass: HomeAssistant, trace: Trace, failing: frozenset[str]
) -> PairedBedCoordinator:
    """Ergomotion on one address: side frames, and feedback no side can own."""
    data = {CONF_PAIR_ID: "pair-ergomotion", CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS}
    # Angle sensing is requested; the paired entry must still never read it.
    inner = _physical(
        hass, trace, "link", SINGLE_ADDRESS, BED_TYPE_ERGOMOTION, failing,
        **data, **{CONF_DISABLE_ANGLE_SENSING: False},
    )
    entry = MockConfigEntry(domain=DOMAIN, data={**data, CONF_BED_TYPE: BED_TYPE_ERGOMOTION})
    entry.add_to_hass(hass)
    return SingleAddressPairedCoordinator(hass, entry, inner)


TOPOLOGIES = (
    Topology("concurrent", _two_link(PAIR_CONNECTION_MODE_CONCURRENT)),
    Topology("auto", _two_link(PAIR_CONNECTION_MODE_AUTO)),
    Topology("sequential", _two_link(PAIR_CONNECTION_MODE_SEQUENTIAL)),
    Topology("single_native", _single_link(native_both=True)),
    Topology("single_serial", _single_link(native_both=False)),
    Topology("single_ergomotion", _single_link_legacy_feedback),
)


# ---------------------------------------------------------------------------
# Scenario steps
# ---------------------------------------------------------------------------


class Run:
    """One scenario: start callers at virtual offsets and record their outcomes."""

    def __init__(self, pair: PairedBedCoordinator, trace: Trace) -> None:
        self.pair = pair
        self.trace = trace
        self.tasks: dict[str, asyncio.Task[Any]] = {}
        self.origin = 0.0

    def start(self, name: str, awaitable: Coroutine[Any, Any, Any]) -> None:
        async def caller() -> None:
            self.trace.add("caller", name, "start")
            try:
                await awaitable
            except asyncio.CancelledError:
                self.trace.add("caller", name, "cancelled")
                raise
            except PairedSideError as err:
                self.trace.add("caller", name, "PairedSideError", sorted(err.side_errors))
            except Exception as err:  # noqa: BLE001 - outcomes are trace data
                self.trace.add("caller", name, type(err).__name__)
            else:
                self.trace.add("caller", name, "ok")

        task = asyncio.ensure_future(caller())

        def close_unstarted(_task: asyncio.Task[Any]) -> None:
            # A caller cancelled before its first step never awaited its call.
            if inspect.getcoroutinestate(awaitable) == inspect.CORO_CREATED:
                awaitable.close()

        task.add_done_callback(close_unstarted)
        self.tasks[name] = task

    def command(
        self, name: str, side: str, action: Callable[[Any], Awaitable[None]], **kwargs: Any
    ) -> None:
        self.start(name, self.pair.async_execute_controller_command(action, side=side, **kwargs))

    async def at(self, seconds: float) -> None:
        """Wait until ``seconds`` after the scenario's first step."""
        delay = self.origin + seconds - self.trace.clock.now
        if delay > 0:
            await asyncio.sleep(delay)

    async def settle(self) -> None:
        pending = [task for task in self.tasks.values() if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=SCENARIO_BUDGET_S)
        for name, task in self.tasks.items():
            if not task.done():
                self.trace.add("caller", name, "stuck")
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


async def back_up(controller: Any) -> None:
    await controller.move_back_up()


async def back_down(controller: Any) -> None:
    await controller.move_back_down()


async def legs_up(controller: Any) -> None:
    await controller.move_legs_up()


def failing_right(delay: float) -> Callable[[Any], Awaitable[None]]:
    """Fail the right side mid-movement while the left keeps moving."""

    async def action(controller: Any) -> None:
        side = getattr(controller, "_side", None) or controller.client.address
        if side == SIDE_RIGHT:
            await asyncio.sleep(delay)
            raise RuntimeError("right side failed")
        await controller.move_back_up()

    return action


async def scenario_connect_and_unload(run: Run) -> None:
    run.start("disconnect", run.pair.async_disconnect())


async def scenario_independent_sides(run: Run) -> None:
    run.command("left", SIDE_LEFT, back_up, resource="motor:back")
    await run.at(0.3)
    run.command("right", SIDE_RIGHT, legs_up, resource="motor:legs")


async def scenario_linked_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")


async def scenario_both_queued_behind_side(run: Run) -> None:
    run.command("left", SIDE_LEFT, back_up, resource="motor:back")
    await run.at(0.2)
    run.command("both", SIDE_BOTH, legs_up, resource="motor:legs")


async def scenario_side_preempts_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.4)
    run.command("left", SIDE_LEFT, back_down, resource="motor:back")


async def scenario_partial_failure(run: Run) -> None:
    run.command("both", SIDE_BOTH, failing_right(0.2), resource="motor:back")


async def scenario_stop_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.5)
    run.start("stop", run.pair.async_stop_command(side=SIDE_BOTH))


async def scenario_stop_one_side(run: Run) -> None:
    run.command("left", SIDE_LEFT, back_up, resource="motor:back")
    run.command("right", SIDE_RIGHT, legs_up, resource="motor:legs")
    await run.at(0.5)
    run.start("stop", run.pair.async_stop_command(side=SIDE_LEFT))


async def scenario_replacement(run: Run) -> None:
    run.command("first", SIDE_LEFT, back_up, resource="motor:back")
    await run.at(0.4)
    run.command("second", SIDE_LEFT, back_down, resource="motor:back")


async def scenario_disjoint_resources(run: Run) -> None:
    run.command("back", SIDE_LEFT, back_up, resource="motor:back")
    await run.at(0.4)
    run.command("legs", SIDE_LEFT, legs_up, resource="motor:legs")


async def scenario_caller_cancels_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.5)
    run.tasks["both"].cancel()


async def scenario_caller_cancels_side(run: Run) -> None:
    run.command("left", SIDE_LEFT, back_up, resource="motor:back")
    await run.at(0.5)
    run.tasks["left"].cancel()


async def scenario_disconnect_during_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.5)
    run.start("disconnect", run.pair.async_disconnect())


async def scenario_unload_during_both(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.5)
    run.start("shutdown", run.pair.async_shutdown())


async def scenario_stop_during_cold_connect(run: Run) -> None:
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.at(0.1)
    run.start("stop", run.pair.async_stop_command(side=SIDE_BOTH))


async def scenario_right_drops_then_both(run: Run) -> None:
    right = run.pair.child_for_side(SIDE_RIGHT)
    assert right is not None
    run.start("drop", right.async_disconnect())
    await run.settle()
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    await run.settle()
    run.command("after", SIDE_BOTH, legs_up, resource="motor:legs")


async def scenario_queued_across_fallback(run: Run) -> None:
    right = run.pair.child_for_side(SIDE_RIGHT)
    assert right is not None
    run.start("drop", right.async_disconnect())
    await run.settle()
    run.command("both", SIDE_BOTH, back_up, resource="motor:back")
    # The failed reconnect and its STOP cleanup end 0.55 s in. Automatic
    # fallback then holds the lanes while it releases the live link, so this
    # command, queued in concurrent mode, is admitted in sequential mode.
    await run.at(0.57)
    run.command("queued", SIDE_BOTH, legs_up, resource="motor:legs")


async def scenario_seek_both(run: Run) -> None:
    run.start(
        "seek",
        run.pair.async_seek_position("back", 30.0, back_up, back_down, back_up, side=SIDE_BOTH),
    )


@dataclass(frozen=True)
class Scenario:
    id: str
    steps: Callable[[Run], Awaitable[None]]
    failing: frozenset[str] = frozenset()
    connect_first: bool = True


SCENARIOS = (
    Scenario("connect_and_unload", scenario_connect_and_unload),
    Scenario("independent_sides", scenario_independent_sides),
    Scenario("linked_both", scenario_linked_both),
    Scenario("linked_both_cold", scenario_linked_both, connect_first=False),
    Scenario("both_queued_behind_side", scenario_both_queued_behind_side),
    Scenario("side_preempts_both", scenario_side_preempts_both),
    Scenario("partial_failure", scenario_partial_failure),
    Scenario(
        "connect_failure",
        scenario_linked_both,
        failing=frozenset({"connect:right", "connect:link"}),
        connect_first=False,
    ),
    Scenario("stop_both", scenario_stop_both),
    Scenario("stop_one_side", scenario_stop_one_side),
    Scenario("replacement", scenario_replacement),
    Scenario("disjoint_resources", scenario_disjoint_resources),
    Scenario("caller_cancels_both", scenario_caller_cancels_both),
    Scenario("caller_cancels_side", scenario_caller_cancels_side),
    Scenario("disconnect_during_both", scenario_disconnect_during_both),
    Scenario("unload_during_both", scenario_unload_during_both),
    Scenario("stop_during_cold_connect", scenario_stop_during_cold_connect, connect_first=False),
    Scenario("seek_both", scenario_seek_both),
    # Automatic mode adopts sequential switching when a live sibling holds the
    # exhausted adapter slot; explicit modes treat it as an ordinary failure.
    Scenario(
        "slot_exhausted_at_connect",
        scenario_linked_both,
        failing=frozenset({"slot:right", "slot:link"}),
    ),
    Scenario(
        "slot_exhausted_at_command",
        scenario_right_drops_then_both,
        failing=frozenset({"slot-later:right", "slot-later:link"}),
    ),
    Scenario(
        "slot_exhausted_with_queued_command",
        scenario_queued_across_fallback,
        failing=frozenset({"slot-later:right", "slot-later:link"}),
    ),
)


async def capture(hass: HomeAssistant, topology: Topology, scenario: Scenario) -> list[list[Any]]:
    clock = WIRE.FakeClock()
    trace = Trace(clock)
    baseline = asyncio.all_tasks()
    async def import_inline(func: Callable[..., Any], *args: Any) -> Any:
        # A real executor thread would race the virtual clock.
        return func(*args)

    with (
        patch.object(hass, "async_add_import_executor_job", import_inline),
        WIRE.virtual_time(clock),
    ):
        pair = topology.build(hass, trace, scenario.failing)
        run = Run(pair, trace)
        if scenario.connect_first:
            run.start("connect", pair.async_connect())
            await run.settle()
        run.origin = clock.now
        await scenario.steps(run)
        await run.settle()
        # Every scenario ends with an unload, so teardown ordering is covered too.
        if isinstance(pair, SingleAddressPairedCoordinator):
            for side, child in pair.children.items():
                trace.add(side, "positions", child.position_data)
        run.tasks.clear()
        run.start("unload", pair.async_shutdown())
        await run.settle()
    strays = [t for t in asyncio.all_tasks() if t not in baseline and t is not asyncio.current_task()]
    for task in strays:
        task.cancel()
    await asyncio.gather(*strays, return_exceptions=True)
    return _canonical(trace.events)


def _canonical(events: list[list[Any]]) -> list[list[Any]]:
    """Order synchronous preemption cancels by side.

    Preemption cancels the active children of a set, without an await between
    them, so their relative order follows object ids rather than routing.
    """
    result: list[list[Any]] = []
    for event in events:
        run_start = len(result)
        while (
            event[2] == "request_command_cancel"
            and run_start > 0
            and result[run_start - 1][2] == "request_command_cancel"
            and result[run_start - 1][0] == event[0]
        ):
            run_start -= 1
        result.append(event)
        if run_start < len(result) - 1:
            result[run_start:] = sorted(result[run_start:], key=lambda item: item[1])
    return result


CASES = [(topology, scenario) for topology in TOPOLOGIES for scenario in SCENARIOS]


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    if RECORD:
        return {}
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module", autouse=True)
def _write_recording(recorded: dict[str, Any]) -> Iterator[None]:
    yield
    if RECORD:
        FIXTURE.write_text(_render(recorded))


def _render(traces: dict[str, Any]) -> str:
    """One event per line, so a trace diff reads like a timeline."""
    blocks = []
    for key, events in sorted(traces.items()):
        lines = ",\n".join(f"  {json.dumps(event)}" for event in events)
        blocks.append(f" {json.dumps(key)}: [\n{lines}\n ]")
    return "{\n" + ",\n".join(blocks) + "\n}\n"


@pytest.mark.parametrize(
    ("topology", "scenario"), CASES, ids=[f"{t.id}-{s.id}" for t, s in CASES]
)
async def test_paired_topology_trace_is_unchanged(
    hass: HomeAssistant, recorded: dict[str, Any], topology: Topology, scenario: Scenario
) -> None:
    key = f"{topology.id}/{scenario.id}"
    events = await capture(hass, topology, scenario)
    # Round-trip through JSON so tuples and lists compare like the fixture.
    events = json.loads(json.dumps(events))
    if RECORD:
        recorded[key] = events
        return
    assert key in recorded, f"no recorded trace for {key}"
    assert events == recorded[key]
