#!/usr/bin/env python3
"""Capture the bytes every bed controller puts on the wire for fixed logical commands.

Purpose: refactors of a protocol family (v5 protocol split, #742) must keep the
wire output unchanged. This tool builds each bed type through the real
``create_controller`` factory, drives a fixed set of logical commands against a
recording BLE client and writes the result as a deterministic JSON snapshot.
``tests/test_wire_snapshot.py`` fails when a fresh capture differs from the
committed snapshot.

What is recorded per write: characteristic UUID, payload (hex), the
``response`` flag, the order, and the virtual time of the write. Time is virtual:
``asyncio.sleep`` is replaced by a fake clock so captures are instant and
repeatable. Consecutive identical writes with a constant spacing collapse into
one run: ``[t_ms, char, response, hex, count, interval_ms]``.

Usage::

    uv run --no-sync python scripts/wire_snapshot.py            # rewrite snapshot
    uv run --no-sync python scripts/wire_snapshot.py --check    # diff against it
    uv run --no-sync python scripts/wire_snapshot.py --list     # list scenarios

A deliberate wire change (a bug fix) regenerates the snapshot in the same PR so
the byte diff is reviewed. A pure refactor must leave it untouched.

How it works, and where it stops:

- Controllers are driven directly, not through the coordinator, so cover-level
  hold loops are not exercised. A command that repeats until STOP is stopped after
  ``HOLD_CAP_S`` of virtual time.
- ``asyncio.sleep``, ``wait_for``, ``timeout`` and the loop clock run on the fake
  clock; wall-clock time is frozen, so clock-sync frames are repeatable.
- The post-connect hooks (``async_discover_capabilities``, ``start_notify``) run
  first and their writes are recorded as the ``connect`` entry.
- Controllers resolve GATT roles from ``client.services``. The fake GATT layout is
  derived from the UUID constants the controller's modules declare, trying the
  full layout, each service alone, then a crossed pool. The layout that let the
  connect hooks succeed is recorded as ``gatt``.
- A scenario where no command succeeded is flagged ``coverage_gap`` (``gatt:
  unresolved``). Every write it did record stays in the snapshot, whatever the
  command status, so a wire change there still fails the guard. Add a
  ``Scenario.layout`` or entry data to turn a gap into full coverage.
- Every stubbed GATT write takes ``WRITE_DURATION_S`` of virtual time, so pacing that
  absorbs write latency and pacing that adds to it land at different offsets. After
  the last command the clock runs ``DRAIN_WINDOW_S`` more, so delayed work the final
  command scheduled is captured (as ``background``) before cleanup cancels it.
- ``async_execute_controller_query`` runs its callback against the constructed
  controller, like the coordinator does, so startup queries write. ``random`` and
  ``secrets`` are seeded per scenario so nonces repeat.
- ``info.gatt`` of ``all``/``pool``/a service UUID tells which layout resolved.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import contextvars
import dataclasses
import datetime
import importlib
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "wire_snapshot.json"
SCHEMA_VERSION = 1

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Per logical command watchdog (real seconds). Fake sleeps never block, so
# anything slower is waiting on an event the mock never sets.
COMMAND_TIMEOUT_S = 0.3
REAL_WAIT_FOR = asyncio.wait_for

MOTORS: tuple[str, ...] = (
    "head",
    "back",
    "legs",
    "feet",
    "lumbar",
    "neck",
    "pillow",
    "tilt",
    "hip",
    "bed_height",
)

# (logical name, controller method, positional args)
LOGICAL_COMMANDS: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    *(
        (f"{motor}_{action}", f"move_{motor}_{action}", ())
        for motor in MOTORS
        for action in ("up", "down", "stop")
    ),
    ("stop_all", "stop_all", ()),
    ("preset_flat", "preset_flat", ()),
    ("preset_zero_g", "preset_zero_g", ()),
    ("preset_anti_snore", "preset_anti_snore", ()),
    ("preset_tv", "preset_tv", ()),
    ("memory_recall_1", "preset_memory", (1,)),
    ("memory_program_1", "program_memory", (1,)),
    ("lights_toggle", "lights_toggle", ()),
    ("lights_on", "lights_on", ()),
    ("lights_off", "lights_off", ()),
    ("massage_toggle", "massage_toggle", ()),
    ("massage_off", "massage_off", ()),
)


@dataclass(frozen=True)
class Scenario:
    """One way to reach a controller: bed type plus the route that changes bytes."""

    id: str
    bed_type: str
    # None keeps the factory-contract default variant for the bed type.
    protocol_variant: str | None = None
    # Config-entry data merged over the factory-contract defaults.
    entry_data: dict[str, Any] = field(default_factory=dict)
    # Extra keyword arguments for ``create_controller``.
    factory_kwargs: dict[str, Any] = field(default_factory=dict)
    # Explicit GATT layout (service -> characteristics) when derivation cannot resolve roles.
    layout: dict[str, list[str]] | None = None


# A held command (one that repeats until STOP) is stopped after this much virtual time.
HOLD_CAP_S = 10.0


# Consecutive yields without activity (a task created, a write, a sleeper registered)
# before a sleeper may advance virtual time, and the same for a timeout guard.
SETTLE_YIELDS = 20
TIMEOUT_SETTLE_YIELDS = 200
# Every stubbed GATT write takes this long, so pacing that absorbs write latency and
# pacing that adds to it land at different offsets.
WRITE_DURATION_S = 0.007
# Virtual time a scenario keeps running after its last command, so delayed work the
# final command scheduled (a follow-up write, a retry) is captured before cleanup.
DRAIN_WINDOW_S = 2.0
# Hard cap on yields per settle, so a body that never goes quiet cannot hang a capture.
MAX_SETTLE_YIELDS = 20000
# Tasks inherit the phase that created them, so a write made later by a task from an
# earlier phase (a delayed retry, a keepalive) is recorded as background, not as
# part of the command that happens to be running.
PHASE: contextvars.ContextVar[int] = contextvars.ContextVar("wire_snapshot_phase", default=0)


class FakeClock:
    """Virtual time, advanced only to the earliest pending sleep deadline.

    Wall-clock time (``datetime``, ``time.monotonic``) is frozen by freezegun and
    moved to ``FROZEN_BASE + now`` whenever the virtual clock advances, so
    controllers that compute deadlines from either clock see the same elapsed time.
    """

    def __init__(self, frozen: Any = None) -> None:
        self.now = 0.0
        self.origin = 0.0
        self.sleepers: list[float] = []
        self.phase = 0
        # Bumped by every observable step of runnable work; see ``virtual_time``.
        self.activity = 0
        self.stop_event: asyncio.Event | None = None
        self._frozen = frozen
        if frozen is not None:
            frozen.move_to(FROZEN_BASE)

    def begin_phase(self, stop_event: asyncio.Event | None = None) -> None:
        """Start a capture phase: write offsets and the hold cap count from here."""
        self.origin = self.now
        self.stop_event = stop_event
        self.phase += 1
        PHASE.set(self.phase)

    @property
    def elapsed(self) -> float:
        return self.now - self.origin

    def advance_to(self, deadline: float) -> None:
        self.now = max(self.now, deadline)
        if self._frozen is not None:
            self._frozen.move_to(FROZEN_BASE + datetime.timedelta(seconds=self.now))
        if self.stop_event is not None and self.elapsed >= HOLD_CAP_S:
            self.stop_event.set()

    def advance(self, seconds: float) -> None:
        self.advance_to(self.now + max(seconds, 0))

    def time(self) -> float:
        return self.now


class _LoopProxy:
    """Real running loop with ``time()`` answered by the fake clock."""

    def __init__(self, loop: asyncio.AbstractEventLoop, clock: FakeClock) -> None:
        self._loop = loop
        self._clock = clock

    def time(self) -> float:
        return self._clock.time()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._loop, name)


class WriteRecorder:
    """Collects GATT writes with virtual timestamps."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.writes: list[tuple[float, str, bool | None, bytes]] = []
        self.background: list[tuple[float, str, bool | None, bytes]] = []

    def add(self, char: Any, data: Any, response: bool | None) -> None:
        uuid = str(getattr(char, "uuid", char)).lower()
        self._clock.activity += 1
        if PHASE.get() != self._clock.phase:
            self.background.append((self._clock.now, uuid, response, bytes(data)))
            return
        self.writes.append((self._clock.elapsed, uuid, response, bytes(data)))


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ALL_PROPERTIES = ["read", "write", "write-without-response", "notify", "indicate"]


def _normalize(specifier: Any) -> Any:
    return specifier.lower() if isinstance(specifier, str) else specifier


class FakeChar:
    def __init__(self, uuid: str, handle: int, service: FakeService) -> None:
        self.uuid = uuid
        self.handle = handle
        self.properties = list(ALL_PROPERTIES)
        self.descriptors: list[Any] = []
        self.description = ""
        self.service_uuid = service.uuid
        self.service_handle = service.handle
        self.max_write_without_response_size = 180

    def __repr__(self) -> str:
        return f"<FakeChar {self.uuid}>"


class FakeService:
    def __init__(self, uuid: str, handle: int) -> None:
        self.uuid = uuid
        self.handle = handle
        self.characteristics: list[FakeChar] = []
        self.description = ""

    def get_characteristic(self, specifier: Any) -> FakeChar | None:
        specifier = _normalize(specifier)
        return next((c for c in self.characteristics if specifier in (c.uuid, c.handle)), None)


class FakeServices:
    """Minimal ``BleakGATTServiceCollection`` stand-in built from a service/char map."""

    def __init__(self, layout: dict[str, list[str]]) -> None:
        self._services: list[FakeService] = []
        self.characteristics: dict[int, FakeChar] = {}
        handle = 1
        for service_uuid, chars in layout.items():
            service = FakeService(service_uuid, handle)
            handle += 1
            for char_uuid in chars:
                char = FakeChar(char_uuid, handle, service)
                handle += 1
                service.characteristics.append(char)
                self.characteristics[char.handle] = char
            self._services.append(service)
        self.services = {s.handle: s for s in self._services}

    def __iter__(self) -> Any:
        return iter(self._services)

    def __len__(self) -> int:
        return len(self._services)

    def get_service(self, specifier: Any) -> FakeService | None:
        specifier = _normalize(specifier)
        return next((s for s in self._services if specifier in (s.uuid, s.handle)), None)

    def get_characteristic(self, specifier: Any) -> FakeChar | None:
        specifier = _normalize(specifier)
        for char in self.characteristics.values():
            if specifier in (char.uuid, char.handle):
                return char
        return None


def _uuid_values(value: Any, depth: int = 3) -> list[str]:
    """UUID strings held by a constant, looking inside containers and dataclasses."""
    if isinstance(value, str):
        return [value.lower()] if UUID_RE.match(value.lower()) else []
    if depth == 0:
        return []
    if isinstance(value, dict):
        items: Any = [*value.keys(), *value.values()]
    elif isinstance(value, list | tuple | frozenset | set):
        items = value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        items = [getattr(value, f.name, None) for f in dataclasses.fields(value)]
    else:
        return []
    return [u for item in items for u in _uuid_values(item, depth - 1)]


SIBLING_SKIP = frozenset(
    {
        "adapter",
        "address_lock",
        "app_session",
        "app_state_store",
        "command_scheduler",
        "coordinator",
        "detection",
        "position_seek",
        "redaction",
        "validators",
        "entity",
        "diagnostic_payloads",
    }
)


def _sibling_modules(module: Any, depth: int = 2) -> list[Any]:
    """The controller module plus the package modules it imports, a few levels deep."""
    found: dict[str, Any] = {module.__name__: module}
    frontier = [module]
    for _ in range(depth):
        nxt = []
        for mod in frontier:
            try:
                tree = ast.parse(Path(mod.__file__).read_text())
            except OSError, SyntaxError, TypeError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.ImportFrom) and node.level):
                    continue
                # ``from .x import y`` names module x; ``from .. import x`` names x directly.
                targets = [node.module] if node.module else [alias.name for alias in node.names]
                for target in targets:
                    name = importlib.util.resolve_name("." * node.level + target, mod.__package__)
                    last = name.rsplit(".", 1)[-1]
                    if name in found or last in {"base", "const"} or last in SIBLING_SKIP:
                        continue
                    try:
                        found[name] = importlib.import_module(name)
                    except ImportError:
                        continue
                    nxt.append(found[name])
        frontier = nxt
    return list(found.values())


def _uuid_rows(value: Any) -> list[list[str]]:
    """Tuples of several UUIDs read as ``(service, characteristic, ...)`` rows."""
    if not isinstance(value, list | tuple | frozenset):
        return []
    rows = []
    if value and all(isinstance(item, str) for item in value):
        uuids = _uuid_values(value)
        if len(uuids) >= 2 and len(uuids) == len(value) and isinstance(value, tuple):
            rows.append(uuids)
    for item in value:
        if isinstance(item, list | tuple):
            rows.extend(_uuid_rows(item))
    return rows


def derive_layout(module: Any | None) -> dict[str, list[str]]:
    """Guess a GATT layout from the UUID constants a controller's modules declare.

    Tuples of several UUIDs are ``(service, characteristic, ...)`` rows. Other
    constants named ``*SERVICE*`` are services and the rest characteristics; a
    characteristic joins the service whose name shares its leading name token,
    and otherwise every service. Scenarios whose roles stay unresolved set
    ``Scenario.layout``.
    """
    from custom_components.adjustable_bed import const

    modules = [const] if module is None else [const, *_sibling_modules(module)]
    own_names: set[str] = set()
    for mod in modules[1:]:
        own_names.update(vars(mod))
    layout: dict[str, list[str]] = {}
    named: dict[str, list[str]] = {}
    for mod in modules:
        for name, value in vars(mod).items():
            if name.startswith("_") and mod is const:
                continue
            if module is not None and mod is const and name not in own_names:
                continue
            for row in _uuid_rows(value):
                layout.setdefault(row[0], []).extend(row[1:])
            uuids = _uuid_values(value)
            if uuids and name not in {"VARIANT_AUTO"}:
                named[name] = uuids
    services = {n: u for n, u in named.items() if "SERVICE" in n or n.endswith("_SVC")}
    chars = {n: u for n, u in named.items() if n not in services}
    for sname, suuids in services.items():
        prefix = sname.split("SERVICE")[0].rstrip("_")
        matched = [
            c
            for cname, cu in chars.items()
            if (prefix and cname.startswith(prefix)) or cname.split("_")[0] == sname.split("_")[0]
            for c in cu
        ]
        for suuid in suuids:
            layout.setdefault(suuid, []).extend(matched)
    allchars = [c for cu in chars.values() for c in cu]
    single_service = len(layout) == 1
    for suuid in list(layout):
        layout[suuid] = list(
            dict.fromkeys(
                (layout[suuid] + allchars) if single_service else (layout[suuid] or allchars)
            )
        )
    if not layout and allchars:
        layout["0000ffff-0000-1000-8000-00805f9b34fb"] = list(dict.fromkeys(allchars))
    return layout


def crossed_layout(layout: dict[str, list[str]]) -> dict[str, list[str]]:
    """Every known UUID as a service holding every known UUID: a last-resort layout."""
    pool = list(dict.fromkeys([*layout, *(c for chars in layout.values() for c in chars)]))
    return dict.fromkeys(pool, pool)


def _make_client(recorder: WriteRecorder, layout: dict[str, list[str]]) -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.address = "AA:BB:CC:DD:EE:FF"
    client.mtu_size = 185
    client.services = FakeServices(layout)

    async def write_gatt_char(char: Any, data: Any, response: bool | None = None) -> None:
        recorder.add(char, data, response)
        await asyncio.sleep(WRITE_DURATION_S)

    client.write_gatt_char = AsyncMock(side_effect=write_gatt_char)
    client.read_gatt_char = AsyncMock(return_value=bytearray())
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.pair = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    return client


def _collapse(writes: list[tuple[float, str, bool | None, bytes]]) -> list[list[Any]]:
    """Collapse constant-interval repeats of one write into ``[t, char, rsp, hex, n, dt]``."""
    runs: list[list[Any]] = []
    for at, char, response, data in writes:
        t_ms = round(at * 1000)
        hex_data = data.hex()
        if runs:
            last = runs[-1]
            same = last[1] == char and last[2] == response and last[3] == hex_data
            if same and last[4] == 1:
                last[4], last[5] = 2, t_ms - last[0]
                continue
            if same and t_ms - (last[0] + last[5] * (last[4] - 1)) == last[5]:
                last[4] += 1
                continue
        runs.append([t_ms, char, response, hex_data, 1, 0])
    return runs


async def _run_command(
    controller: Any, recorder: WriteRecorder, clock: FakeClock, method: str, args: tuple[Any, ...]
) -> dict[str, Any]:
    fn: Callable[..., Awaitable[Any]] | None = getattr(controller, method, None)
    if fn is None:
        return {"status": "unsupported"}
    recorder.writes.clear()
    controller._coordinator.cancel_command.clear()  # noqa: SLF001
    clock.begin_phase(controller._coordinator.cancel_command)  # noqa: SLF001
    try:
        await REAL_WAIT_FOR(fn(*args), COMMAND_TIMEOUT_S)
    except NotImplementedError:
        if recorder.writes:
            return {"status": "not_implemented", "writes": _collapse(recorder.writes)}
        return {"status": "unsupported"}
    except TimeoutError:
        return {"status": "timeout", "writes": _collapse(recorder.writes)}
    except Exception as err:  # noqa: BLE001 - recorded, not hidden
        if os.environ.get("WIRE_SNAPSHOT_VERBOSE"):
            print(f"  {method}: {type(err).__name__}: {str(err)[:200]}", file=sys.stderr)
        return {
            "status": "error",
            "error": type(err).__name__,
            "writes": _collapse(recorder.writes),
        }
    if not recorder.writes:
        return {"status": "no_writes"}
    return {"status": "ok", "writes": _collapse(recorder.writes)}


@contextlib.contextmanager
def deterministic_randomness() -> Iterator[None]:
    """Seed ``random`` and replace ``secrets`` so nonces and session ids repeat."""
    import random
    import secrets
    from unittest.mock import patch

    rng = random.Random(0)
    random.seed(0)
    with (
        patch.object(secrets, "randbits", rng.getrandbits),
        patch.object(secrets, "token_bytes", lambda n=32: rng.randbytes(n)),
        patch.object(secrets, "token_hex", lambda n=32: rng.randbytes(n).hex()),
    ):
        yield


@contextlib.contextmanager
def virtual_time(clock: FakeClock) -> Iterator[None]:
    """Replace ``asyncio.sleep`` and the loop clock with the fake clock."""
    real_sleep = asyncio.sleep
    real_get_running_loop = asyncio.get_running_loop
    real_wait_for = REAL_WAIT_FOR
    real_timeout = asyncio.timeout

    async def settle(quiet: int, stop: Callable[[], bool] = lambda: False) -> None:
        """Yield until ``quiet`` consecutive yields saw no new activity, or ``stop()``."""
        seen, still = -1, 0
        for _ in range(MAX_SETTLE_YIELDS):
            await real_sleep(0)
            if stop():
                return
            if clock.activity == seen:
                still += 1
                if still >= quiet:
                    return
            else:
                seen, still = clock.activity, 0

    async def fake_sleep(delay: float, result: Any = None) -> Any:
        # Concurrent sleepers wake in deadline order: only the earliest pending
        # deadline may advance the clock, once the runnable work has gone quiet.
        deadline = clock.now + max(delay, 0)
        clock.sleepers.append(deadline)
        clock.activity += 1
        try:
            while True:
                await settle(SETTLE_YIELDS)
                if deadline <= min(clock.sleepers):
                    break
        finally:
            clock.sleepers.remove(deadline)
        clock.advance_to(deadline)
        return result

    class FakeTimeout:
        """``asyncio.timeout`` that fires at its virtual deadline once it is the earliest."""

        def __init__(self, delay: float | None) -> None:
            self._delay = delay
            self._task: asyncio.Task[Any] | None = None
            self._guard: asyncio.Task[None] | None = None
            self._expired = False

        def expired(self) -> bool:
            return self._expired

        async def _expire(self, deadline: float) -> None:
            clock.sleepers.append(deadline)
            try:
                while True:
                    await settle(TIMEOUT_SETTLE_YIELDS)
                    if deadline <= min(clock.sleepers):
                        break
            finally:
                clock.sleepers.remove(deadline)
            self._expired = True
            clock.advance_to(deadline)
            assert self._task is not None
            self._task.cancel()

        async def __aenter__(self) -> FakeTimeout:
            if self._delay is not None:
                self._task = asyncio.current_task()
                self._guard = asyncio.ensure_future(self._expire(clock.now + self._delay))
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
            if self._guard is not None:
                self._guard.cancel()
            if self._expired and exc_type is asyncio.CancelledError:
                self._task.uncancel()  # type: ignore[union-attr]
                raise TimeoutError from exc
            return None

    async def fake_wait_for(awaitable: Any, timeout: float | None) -> Any:
        # The wait ends at its virtual deadline once no earlier sleeper is pending, and
        # only after the cancelled awaitable finished its cleanup.
        if timeout is None:
            return await awaitable
        task = asyncio.ensure_future(awaitable)
        deadline = clock.now + timeout
        clock.sleepers.append(deadline)
        try:
            while not task.done():
                await settle(TIMEOUT_SETTLE_YIELDS, task.done)
                if not task.done() and deadline <= min(clock.sleepers):
                    break
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            clock.sleepers.remove(deadline)
        if task.done():
            return task.result()
        clock.advance_to(deadline)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise TimeoutError

    loop = real_get_running_loop()
    previous_factory = loop.get_task_factory()

    def counting_factory(loop: asyncio.AbstractEventLoop, coro: Any, **kwargs: Any) -> Any:
        clock.activity += 1
        if previous_factory is not None:
            return previous_factory(loop, coro, **kwargs)
        return asyncio.Task(coro, loop=loop, **kwargs)

    loop.set_task_factory(counting_factory)
    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    asyncio.wait_for = fake_wait_for  # type: ignore[assignment]
    asyncio.timeout = FakeTimeout  # type: ignore[assignment]
    asyncio.get_running_loop = lambda: _LoopProxy(real_get_running_loop(), clock)  # type: ignore[assignment]
    try:
        yield
    finally:
        loop.set_task_factory(previous_factory)
        asyncio.sleep = real_sleep  # type: ignore[assignment]
        asyncio.wait_for = real_wait_for  # type: ignore[assignment]
        asyncio.timeout = real_timeout  # type: ignore[assignment]
        asyncio.get_running_loop = real_get_running_loop  # type: ignore[assignment]


async def _build(scenario: Scenario, client: MagicMock) -> Any:
    """Create the controller exactly as the factory contract test does, on ``client``."""
    from tests import test_controller_contract as contract

    real_create = contract.create_controller
    built: list[Any] = []

    async def run_query(query_fn: Callable[[Any], Awaitable[Any]], **kwargs: Any) -> Any:
        """Run a query callback against the constructed controller, as the coordinator does."""
        run_if = kwargs.get("run_if")
        if run_if is not None and not run_if():
            return None
        return await query_fn(built[-1])

    async def create(coordinator: Any, bed_type: str, variant: Any, _client: Any, **kwargs: Any):
        coordinator.entry.data = {**coordinator.entry.data, **scenario.entry_data}
        coordinator.client = client
        coordinator.record_command_trace = MagicMock()
        coordinator.handle_controller_state_update = MagicMock()
        if not hasattr(coordinator.entry, "entry_id"):
            coordinator.entry.entry_id = "wire-snapshot"
        coordinator.async_execute_controller_query = run_query
        controller = await real_create(
            coordinator,
            bed_type,
            scenario.protocol_variant if scenario.protocol_variant is not None else variant,
            client,
            **{**kwargs, **scenario.factory_kwargs},
        )
        coordinator.controller = controller
        built.append(controller)
        return controller

    contract.create_controller = create
    try:
        return await contract._create_controller_for_bed_type(scenario.bed_type)  # noqa: SLF001
    finally:
        contract.create_controller = real_create


async def _connect_sequence(
    controller: Any, recorder: WriteRecorder, clock: FakeClock
) -> dict[str, Any]:
    """Replay the coordinator's post-connect hooks and record any handshake writes."""
    recorder.writes.clear()
    clock.begin_phase()
    try:
        discovery = controller.async_discover_capabilities()
        if inspect.isawaitable(discovery):
            await REAL_WAIT_FOR(discovery, COMMAND_TIMEOUT_S)
        await REAL_WAIT_FOR(controller.start_notify(lambda *_: None), COMMAND_TIMEOUT_S)
    except Exception as err:  # noqa: BLE001 - recorded, not hidden
        if os.environ.get("WIRE_SNAPSHOT_VERBOSE"):
            print(f"  connect: {type(err).__name__}: {str(err)[:200]}", file=sys.stderr)
        return {
            "status": "error",
            "error": type(err).__name__,
            "writes": _collapse(recorder.writes),
        }
    return (
        {"status": "ok", "writes": _collapse(recorder.writes)}
        if recorder.writes
        else {"status": "no_writes"}
    )


async def _cancel_strays(baseline: set[asyncio.Task[Any]]) -> None:
    """Cancel tasks a controller left running (keepalives, retries) since ``baseline``."""
    strays = [
        t for t in asyncio.all_tasks() if t not in baseline and t is not asyncio.current_task()
    ]
    for task in strays:
        task.cancel()
    await asyncio.gather(*strays, return_exceptions=True)


async def capture_scenario(scenario: Scenario, frozen: Any = None) -> dict[str, Any]:
    baseline = asyncio.all_tasks()
    try:
        return await _capture(scenario, frozen, baseline)
    finally:
        await _cancel_strays(baseline)


async def _capture(
    scenario: Scenario, frozen: Any, baseline: set[asyncio.Task[Any]]
) -> dict[str, Any]:
    """Build one controller through the factory and drive every logical command."""
    clock = FakeClock(frozen)
    recorder = WriteRecorder(clock)
    with deterministic_randomness(), virtual_time(clock):
        # Pass 1 learns which controller the route reaches; pass 2 rebuilds it on a
        # GATT layout derived from that controller's own UUID constants.
        controller = None
        try:
            controller = await _build(scenario, _make_client(recorder, derive_layout(None)))
        except Exception:  # noqa: BLE001 - retried below with a module hint
            pass
        module = None
        if controller is not None:
            module = sys.modules[type(controller).__module__]
        else:
            with contextlib.suppress(ImportError):
                module = importlib.import_module(
                    f"custom_components.adjustable_bed.beds.{scenario.bed_type}"
                )
        derived = derive_layout(module)
        candidates: list[tuple[str, dict[str, list[str]]]] = (
            [("scenario", scenario.layout)]
            if scenario.layout is not None
            else [
                ("all", derived),
                *((uuid, {uuid: chars}) for uuid, chars in derived.items()),
                ("pool", crossed_layout(derived)),
            ]
        )
        for label, layout in candidates:  # noqa: B007 - label is read after the loop
            await _cancel_strays(baseline)
            recorder.background.clear()
            controller = await _build(scenario, _make_client(recorder, layout))
            connect = await _connect_sequence(controller, recorder, clock)
            if connect["status"] != "error":
                break
        else:
            # No layout let the connect hooks succeed; commands may still work.
            label = "connect_failed"
            await _cancel_strays(baseline)
            recorder.background.clear()
            controller = await _build(scenario, _make_client(recorder, derived))
            connect = await _connect_sequence(controller, recorder, clock)
        commands = {"connect": connect}
        for name, method, args in LOGICAL_COMMANDS:
            commands[name] = await _run_command(controller, recorder, clock, method, args)
        # Let delayed work from the final command run before cleanup cancels it.
        clock.begin_phase()
        await asyncio.sleep(DRAIN_WINDOW_S)
        if recorder.background:
            # Writes from tasks of an earlier phase, at absolute virtual time.
            commands["background"] = {
                "status": "background",
                "writes": _collapse(recorder.background),
            }

    info = {
        "bed_type": scenario.bed_type,
        "controller": type(controller).__name__,
        "module": type(controller).__module__.rsplit(".", 1)[-1],
    }
    if not any(cmd["status"] == "ok" for cmd in commands.values()):
        # No command succeeded: flag the coverage gap, but keep every write that was
        # recorded so a wire change in a partly working route still fails the guard.
        # Commands that wrote nothing would only pin error noise.
        return {
            **info,
            "gatt": "unresolved",
            "coverage_gap": True,
            "connect_error": connect.get("error"),
            "commands": {name: cmd for name, cmd in commands.items() if cmd.get("writes")},
        }
    return {**info, "gatt": label, "commands": commands}


# Bed types whose protocol variants select a different controller or byte table.
# Each entry is ``bed_type -> names of const mappings holding the variants``.
VARIANT_ROUTES: dict[str, str] = {
    "keeson": "KEESON_VARIANTS",
    "richmat": "RICHMAT_VARIANTS",
    "leggett_platt": "LEGGETT_VARIANTS",
    "linak": "LINAK_VARIANTS",
    "octo": "OCTO_VARIANTS",
    "okin_cb24": "OKIN_CB24_VARIANTS",
    "okin_cst": "OKIN_CST_VARIANTS",
    "okin_64bit": "OKIN_64BIT_VARIANTS",
    "okin_dot": "OKIN_DOT_VARIANTS",
    "simmons": "SIMMONS_VARIANTS",
    "sbi": "SBI_VARIANTS",
    "rondure": "RONDURE_VARIANTS",
    "remacro": "REMACRO_VARIANTS",
    "sleepys_box25": "SLEEPYS_BOX25_VARIANTS",
    "adjustable_lumbar": "ADJUSTABLE_LUMBAR_VARIANTS",
    "bedsense": "BEDSENSE_VARIANTS",
    "comfort_enhancements": "COMFORT_ENHANCEMENTS_VARIANTS",
    "zseries": "ZSERIES_VARIANTS",
    "solace": "SOLACE_VARIANTS",
    "svane": "SVANE_VARIANTS",
    "star_elevate": "STAR_ELEVATE_VARIANTS",
    "doublesleep": "DOUBLESLEEP_VARIANTS",
    "kaidi": "KAIDI_VARIANTS",
    "adjustamattress": "ADJUSTAMATTRESS_VARIANTS",
}
# Large variant sets are sampled: the first and last keys plus the named extras.
SAMPLED_ROUTES: dict[str, int] = {"adjustamattress": 3}
RICHMAT_KWARGS: dict[str, Any] = {"richmat_remote": "auto", "device_name": "Richmat"}


def route_scenarios() -> list[Scenario]:
    """Protocol-variant and app-profile routes, one scenario each."""
    from custom_components.adjustable_bed import const

    scenarios: list[Scenario] = []
    for bed_type, table in VARIANT_ROUTES.items():
        if bed_type not in const.SUPPORTED_BED_TYPES:
            continue
        variants = [v for v in getattr(const, table) if v != const.VARIANT_AUTO]
        if (sample := SAMPLED_ROUTES.get(bed_type)) is not None:
            variants = [*variants[:sample], variants[-1]]
        for variant in variants:
            scenarios.append(
                Scenario(
                    id=f"{bed_type}:{variant}",
                    bed_type=bed_type,
                    protocol_variant=variant,
                    factory_kwargs=RICHMAT_KWARGS if bed_type == "richmat" else {},
                )
            )
    # Richmat app family: the picker model selects the byte table within one controller.
    from custom_components.adjustable_bed.beds.richmat_mh import (
        MODEL_VARIANT_PREFIX,
        selectable_models,
    )

    for bed_type in sorted(const.RICHMAT_MH_BED_TYPES):
        models = selectable_models(const.RICHMAT_MH_APPS[bed_type])
        for model in dict.fromkeys([models[0], models[len(models) // 2]]):
            scenarios.append(
                Scenario(
                    id=f"{bed_type}:model_{model}",
                    bed_type=bed_type,
                    protocol_variant=f"{MODEL_VARIANT_PREFIX}{model}",
                )
            )
    # Jiecang family: one app, four profiles, shared and distinct layouts.
    for profile in ("dreamask", "dreamotion", "dreamhd", "comfort_motion"):
        second = "g2" if profile == "comfort_motion" else "g3"
        for layout, transport in (
            ("standard_2", "g1"),
            ("standard_2", second),
            ("standard_3_neck", "g1"),
            ("standard_4_legacy", "g1"),
        ):
            scenarios.append(
                Scenario(
                    id=f"jiecang_app:{profile}:{layout}:{transport}",
                    bed_type="jiecang_app",
                    entry_data={
                        const.CONF_JIECANG_APP_PROFILE: profile,
                        const.CONF_JIECANG_APP_LAYOUT: layout,
                        const.CONF_JIECANG_APP_TRANSPORT: transport,
                    },
                )
            )
    # LOGICDATA apps: phone, tablet and Sleep Smart over the three transports.
    for profile, family, layout, transport in (
        ("phone", "p1", "standard_2", "t1"),
        ("phone", "p2", "middle", "t1"),
        ("phone", "p1", "standard_2", "t3"),
        ("tablet", "p1", "standard_2", "t1"),
        ("tablet", "p2", "middle", "t1"),
        ("sleep_smart", "p1", "standard_2", "t1"),
        ("sleep_smart", "p1", "standard_2", "t2"),
        ("sleep_smart", "p1", "standard_2", "t3"),
    ):
        scenarios.append(
            Scenario(
                id=f"logicdata_app:{profile}:{family}:{layout}:{transport}",
                bed_type="logicdata_app",
                entry_data={
                    const.CONF_LOGICDATA_APP_PROFILE: profile,
                    const.CONF_LOGICDATA_APP_FAMILY: family,
                    const.CONF_LOGICDATA_APP_LAYOUT: layout,
                    const.CONF_LOGICDATA_APP_TRANSPORT: transport,
                },
            )
        )
    return scenarios


def build_scenarios() -> list[Scenario]:
    """Every bed type once, plus the routes that change the controller or its bytes."""
    from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES

    scenarios = [Scenario(id=bed_type, bed_type=bed_type) for bed_type in SUPPORTED_BED_TYPES]
    scenarios.extend(route_scenarios())
    ids = [scenario.id for scenario in scenarios]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    return scenarios


FROZEN_NOW = "2026-01-02 03:04:05"
FROZEN_BASE = datetime.datetime.fromisoformat(FROZEN_NOW)


async def capture_all(only: list[str] | None = None) -> dict[str, Any]:
    """Capture every scenario with wall-clock time frozen (clock-sync frames carry it)."""
    from freezegun import freeze_time

    scenarios = [s for s in build_scenarios() if not only or s.id in only]
    result: dict[str, Any] = {}
    with freeze_time(FROZEN_NOW, real_asyncio=True) as frozen:
        await _capture_each(scenarios, result, frozen)
    return {"schema": SCHEMA_VERSION, "scenarios": result}


async def _capture_each(scenarios: list[Scenario], result: dict[str, Any], frozen: Any) -> None:
    for scenario in scenarios:
        started = time.monotonic()
        try:
            result[scenario.id] = await capture_scenario(scenario, frozen)
        except Exception as err:  # noqa: BLE001 - a scenario that cannot build is data too
            result[scenario.id] = {
                "bed_type": scenario.bed_type,
                "build_error": f"{type(err).__name__}: {err}",
            }
        if os.environ.get("WIRE_SNAPSHOT_VERBOSE"):
            print(f"{scenario.id} {time.monotonic() - started:.1f}s", file=sys.stderr, flush=True)


def render(snapshot: dict[str, Any]) -> str:
    """Stable text form: one line per command so diffs stay reviewable.

    Characteristic UUIDs are replaced by their first eight hex digits (or the
    full UUID when those collide) and listed once under ``chars``. Commands a
    controller does not support are omitted.
    """
    uuids = sorted(
        {
            write[1]
            for entry in snapshot["scenarios"].values()
            for cmd in entry.get("commands", {}).values()
            for write in cmd.get("writes", [])
        }
    )
    short = {u: u[:8] for u in uuids}
    if len(set(short.values())) != len(short):
        short = {u: u for u in uuids}
    lines = ["{", f'"schema": {snapshot["schema"]},']
    lines.append('"chars": ' + json.dumps({short[u]: u for u in uuids}, sort_keys=True) + ",")
    lines.append('"scenarios": {')
    blocks: list[str] = []
    for sid, entry in sorted(snapshot["scenarios"].items()):
        head = {k: v for k, v in entry.items() if k != "commands"}
        block = [f"{json.dumps(sid)}: {{", f'"info": {json.dumps(head, sort_keys=True)},']
        rows = []
        for name, cmd in entry.get("commands", {}).items():
            if cmd["status"] == "unsupported":
                continue
            cmd = {
                **cmd,
                **(
                    {"writes": [[w[0], short[w[1]], *w[2:]] for w in cmd["writes"]]}
                    if "writes" in cmd
                    else {}
                ),
            }
            rows.append(
                f"{json.dumps(name)}: {json.dumps(cmd, sort_keys=True, separators=(',', ':'))}"
            )
        block.append('"commands": {' + (("\n" + ",\n".join(rows) + "\n") if rows else "") + "}}")
        blocks.append("\n".join(block))
    lines.append(",\n".join(blocks))
    lines.append("}}")
    return "\n".join(lines) + "\n"


def main() -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the snapshot is stale")
    parser.add_argument("--list", action="store_true", help="list scenario ids")
    parser.add_argument("--only", nargs="*", help="limit to these scenario ids (no write)")
    args = parser.parse_args()

    if args.list:
        for scenario in build_scenarios():
            print(scenario.id)
        return 0

    snapshot = asyncio.run(capture_all(args.only))
    text = render(snapshot)
    if args.only:
        print(text)
        return 0
    if args.check:
        if SNAPSHOT_PATH.read_text() != text:
            print("wire snapshot is stale; rerun without --check and review the diff")
            return 1
        return 0
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(text)
    print(f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)} ({len(snapshot['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
