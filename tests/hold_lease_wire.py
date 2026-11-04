"""Run a family controller's leased hold on virtual time and record its wire (#483).

The wire-snapshot tool (``scripts/wire_snapshot.py``) builds each scenario's real
controller on its stored GATT layout with a recording client and a virtual
clock. Here the hold runs inside a leased ``CommandContext``, as the scheduler
binds it, and ends the way the coordinator ends one: lease expiry sets the
cancel event and lets the operation finish; STOP also cancels the operation
task and then sends ``stop_all``. Timing is exact, and no real timer is awaited.

``virtual_clock`` puts the same fake clock under any test body, for example the
real coordinator and services, so lease, refresh and release timers are exact.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import sys
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
    CommandOutcome,
    HoldLease,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wire_snapshot.py"
End = Literal["expire", "stop"]


def _tool() -> Any:
    module = sys.modules.get("wire_snapshot")
    if module is None:
        spec = importlib.util.spec_from_file_location("wire_snapshot", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def virtual_clock() -> Iterator[Any]:
    """Run asyncio timing in the block on the wire tool's fake clock.

    Loop time, sleeps, timeouts and loop timers advance only once every task
    waits, straight to the earliest deadline. Yields the clock; ``clock.time()``
    is the virtual loop time in seconds.
    """
    tool = _tool()
    clock = tool.FakeClock()
    with tool.virtual_time(clock):
        yield clock


@dataclass(frozen=True)
class Write:
    at_ms: int
    """Virtual milliseconds since the hold started."""
    data: bytes


@dataclass(frozen=True)
class HeldWire:
    held: tuple[Write, ...]
    """Writes before the lease expired or STOP arrived."""
    after: tuple[Write, ...]
    """Writes after it: the release, and for STOP the explicit stop."""
    ended_ms: int
    profile_key: str
    """The key of the controller's profile, which names its frozen vectors."""
    pulse_count: int
    """The entry's configured pulse count, which a finite move would send."""


async def leased_hold(
    scenario_id: str,
    move: Callable[[Any], Awaitable[None]],
    *,
    end_after_s: float,
    end: End,
    leased: bool = True,
) -> HeldWire:
    """Hold ``move`` on scenario ``scenario_id`` and end it after ``end_after_s``."""
    from freezegun import freeze_time

    tool = _tool()
    scenarios = {scenario.id: scenario for scenario in tool.build_scenarios()}
    scenario = scenarios[scenario_id]
    layouts = json.loads(tool.LAYOUTS_PATH.read_text())
    layout = layouts[scenario.layout_id or scenario.id]
    if scenario.properties is not None:
        layout = {**layout, "properties": {**layout.get("properties", {}), "*": list(scenario.properties)}}
    baseline = asyncio.all_tasks()
    try:
        with freeze_time(tool.FROZEN_NOW, real_asyncio=True) as frozen:
            clock = tool.FakeClock(frozen)
            recorder = tool.Recorder(clock)
            with tool.deterministic_process_state(), tool.virtual_time(clock):
                controller = await tool._build(  # noqa: SLF001
                    scenario, tool.FakeClient(recorder, layout, scenario.replies)
                )
                await tool._connect(controller, recorder, clock)  # noqa: SLF001
                coordinator = controller._coordinator  # noqa: SLF001
                cancel = coordinator.cancel_command
                cancel.clear()
                context = CommandContext(
                    scheduler_token=coordinator._command_scheduler.token,  # noqa: SLF001
                    cancel_event=cancel,
                    admitted_stop_epoch=0,
                    intent_id="lease",
                    kind=CommandKind.HOLD if leased else CommandKind.COMMAND,
                    group_id=None,
                    resources=frozenset({"motor:back"}),
                    lease=HoldLease(owner="card", generation=1, action="up", duration_s=1)
                    if leased
                    else None,
                )
                recorder.events.clear()
                clock.begin_phase()
                token = _CURRENT_COMMAND_CONTEXT.set(context)
                try:
                    task = asyncio.ensure_future(move(controller))
                finally:
                    _CURRENT_COMMAND_CONTEXT.reset(token)
                await asyncio.wait({task}, timeout=end_after_s)
                ended = clock.elapsed
                split = len(recorder.events)
                if end == "expire":
                    # The scheduler's expiry: the cancel event alone.
                    context.cancel_reason = CommandOutcome.EXPIRED
                    cancel.set()
                    await asyncio.wait_for(task, 10)
                else:
                    context.cancel_reason = CommandOutcome.STOPPED
                    cancel.set()
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    await controller.stop_all()
                # Let delayed release frames go out.
                await asyncio.sleep(tool.DRAIN_WINDOW_S)
                pulse_count = coordinator.motor_pulse_count
                profile_key = getattr(controller.profile, "key", "")
                events = [
                    (index, Write(round(at * 1000), data))
                    for index, (at, _uuid, kind, data) in enumerate(recorder.events)
                    if kind not in ("notify", "unnotify", "read", "pair")
                ]
    finally:
        strays = [t for t in asyncio.all_tasks() if t not in baseline and t is not asyncio.current_task()]
        for stray in strays:
            stray.cancel()
        await asyncio.gather(*strays, return_exceptions=True)
    return HeldWire(
        held=tuple(write for index, write in events if index < split),
        after=tuple(write for index, write in events if index >= split),
        ended_ms=round(ended * 1000),
        profile_key=profile_key,
        pulse_count=pulse_count,
    )


def intervals(writes: tuple[Write, ...]) -> set[int]:
    """Distinct gaps between consecutive writes, in virtual milliseconds."""
    return {b.at_ms - a.at_ms for a, b in zip(writes, writes[1:], strict=False)}
