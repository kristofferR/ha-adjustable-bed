"""Renewable holds (#483) on latched protocols, which move until STOP arrives.

A latched bed keeps moving after its one start frame, so a vanished client
leaves it running until the lease ends. Its holds therefore stop at a shorter
ceiling than streamed holds, and the lease's end sends the protocol's own STOP.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.solace import SolaceController
from custom_components.adjustable_bed.codec import ff_frame
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
    CommandOutcome,
    HoldLease,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ISLEEP,
    BED_TYPE_KAIDI,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    KAIDI_VARIANT_FLOYD,
    KAIDI_VARIANT_SEAT_1_2,
)
from custom_components.adjustable_bed.execution import (
    LATCHED_MAX_HOLD_MS,
    MAX_HOLD_MS,
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from custom_components.adjustable_bed.motion_bed_actions import MOTION_BED_ACTIONS
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.profiles.ff_frame import (
    BEDSENSE,
    BEDSENSE_ACTIONS,
    MOTION_BED,
    SOLACE_PROFILES,
    SolaceCommands,
)
from tests.ff_frame_vectors import FROZEN_FRAMES
from tests.test_bedsense import make_controller as make_bedsense
from tests.test_controller_contract import _create_controller_for_bed_type
from tests.test_hold_lease_service import STREAM, _install, _timed, runtime  # noqa: F401

LATCHED = ExecutionCapabilities(hold="latched")
DECLARED_SOLACE = ("common", "home_k1", "home_k2", "motion_flex", "woosa")


def test_latched_holds_have_the_shorter_ceiling() -> None:
    assert LATCHED.hold_ceiling_ms == LATCHED_MAX_HOLD_MS == 10_000
    assert STREAM.hold_ceiling_ms == MAX_HOLD_MS == 30_000
    assert NO_EXECUTION_CAPABILITIES.hold_ceiling_ms is None


def test_only_report_backed_routes_declare_a_latched_hold() -> None:
    assert {k for k, p in SOLACE_PROFILES.items() if p.execution.hold} == set(DECLARED_SOLACE)
    assert all(SOLACE_PROFILES[key].execution == LATCHED for key in DECLARED_SOLACE)
    assert BEDSENSE.execution == LATCHED
    # Motion Bed's covers are not timed_move motors and it has no held controls.
    assert MOTION_BED.execution == NO_EXECUTION_CAPABILITIES


@pytest.mark.parametrize(
    "bed_type",
    [BED_TYPE_REVERIE, BED_TYPE_KAIDI, BED_TYPE_ISLEEP, BED_TYPE_REMACRO],
)
async def test_standalone_latched_controllers_declare(bed_type: str) -> None:
    controller = await _create_controller_for_bed_type(bed_type)
    assert controller.execution == LATCHED


@pytest.mark.parametrize("variant", [KAIDI_VARIANT_FLOYD, KAIDI_VARIANT_SEAT_1_2])
async def test_kaidi_floyd_and_dual_seat_declare_nothing(variant: str) -> None:
    controller = await _create_controller_for_bed_type(BED_TYPE_KAIDI)
    controller._variant = variant  # type: ignore[attr-defined]
    assert controller.execution == NO_EXECUTION_CAPABILITIES


@pytest.mark.parametrize("key", DECLARED_SOLACE)
def test_solace_held_and_stop_frames_are_frozen(key: str) -> None:
    frozen = FROZEN_FRAMES[key]
    assert SolaceCommands.MOTOR_STOP.hex() in frozen
    assert SolaceCommands.MOTOR_BACK_UP.hex() in frozen
    assert SolaceCommands.MOTOR_BACK_DOWN.hex() in frozen
    assert SolaceCommands.MOTOR_LEGS_UP.hex() in frozen


def test_bedsense_and_motion_bed_frames_are_frozen() -> None:
    assert BEDSENSE_ACTIONS["back_up"].frame.hex() in FROZEN_FRAMES["bedsense"]
    assert BEDSENSE_ACTIONS["release"].frame.hex() in FROZEN_FRAMES["bedsense"]
    assert ff_frame.STOP.hex() in FROZEN_FRAMES["motion_bed"]
    held = {
        SOURCE_COMMANDS[packet.source_id].hex()
        for action in MOTION_BED_ACTIONS
        if action.kind == "held"
        for packet in action.packets
    }
    assert held and held <= FROZEN_FRAMES["motion_bed"]


async def test_a_latched_lease_stops_at_its_ceiling_however_often_renewed(runtime) -> None:  # noqa: F811
    hass, coordinator = runtime
    controller = _install(coordinator, LATCHED)
    loop = asyncio.get_running_loop()
    with patch("custom_components.adjustable_bed.execution.LATCHED_MAX_HOLD_MS", 400):
        start = asyncio.create_task(_timed(hass, 1, duration_ms=300))
        began = loop.time()
        while not start.done():
            await asyncio.sleep(0.1)
            with contextlib.suppress(Exception):
                await _timed(hass, 1, duration_ms=300)
        await start
    # Renewed every 100 ms, it still ended near its 400 ms ceiling and released.
    assert 0.35 <= loop.time() - began < 1.0
    assert controller.frames[-1] == "stop"
    assert coordinator._command_scheduler.recent_records[-1].kind is CommandKind.HOLD


async def test_a_stream_lease_keeps_the_longer_ceiling(runtime) -> None:  # noqa: F811
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    with patch("custom_components.adjustable_bed.execution.LATCHED_MAX_HOLD_MS", 50):
        start = asyncio.create_task(_timed(hass, 1, duration_ms=300))
        for _ in range(4):
            await asyncio.sleep(0.15)
            await _timed(hass, 1, duration_ms=300)
        assert not start.done()
        await asyncio.wait_for(start, 2)
    assert controller.frames[-1] == "stop"
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED


@contextlib.contextmanager
def _leased(cancel: asyncio.Event) -> Iterator[None]:
    """Run as the scheduler runs a renewable hold."""
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="hold",
        kind=CommandKind.HOLD,
        group_id=None,
        resources=frozenset({"*"}),
        lease=HoldLease(owner="card", generation=1, action="up", duration_s=0.75),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


async def _hold_then_cancel(task: asyncio.Task[None], cancel: asyncio.Event, after: float) -> None:
    await asyncio.sleep(after)
    assert not task.done(), "a leased latched hold ended before its lease"
    cancel.set()  # The lease ran out, or STOP preempted it.
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)


async def test_solace_waits_for_its_lease_instead_of_the_press_timeout() -> None:
    coordinator = MagicMock()
    coordinator.ble_device_name = "QMS-IQ"
    coordinator.cancel_command = asyncio.Event()
    controller = SolaceController(coordinator)
    controller.write_command = AsyncMock()  # type: ignore[method-assign]
    with patch.object(SolaceController, "_MOVEMENT_SAFETY_TIMEOUT", 0.1):
        with _leased(coordinator.cancel_command):
            task = asyncio.create_task(controller.move_back_up())
        await _hold_then_cancel(task, coordinator.cancel_command, 0.4)
        # Without a lease the press still ends at its timeout.
        coordinator.cancel_command.clear()
        await asyncio.wait_for(controller.move_back_up(), 1)
    frames = [call.args[0] for call in controller.write_command.await_args_list]
    stop = SolaceCommands.MOTOR_STOP
    assert frames == [SolaceCommands.MOTOR_BACK_UP, stop, SolaceCommands.MOTOR_BACK_UP, stop]
    assert controller.write_command.await_args_list[1].kwargs["cancel_event"] is not (
        coordinator.cancel_command
    )


async def test_bedsense_holds_one_start_until_its_lease_ends() -> None:
    controller = make_bedsense()
    coordinator = controller._coordinator
    # The pulses a leased timed move plans for the latched ceiling.
    coordinator.motor_pulse_count, coordinator.motor_pulse_delay_ms = 101, 100
    with _leased(coordinator.cancel_command):
        task = asyncio.create_task(controller.move_back_up())
    await _hold_then_cancel(task, coordinator.cancel_command, 0.3)
    frames = [call.args[1] for call in coordinator.client.write_gatt_char.call_args_list]
    assert frames == [BEDSENSE_ACTIONS["back_up"].frame, BEDSENSE_ACTIONS["release"].frame]


async def test_reverie_hold_ends_when_its_command_is_cancelled() -> None:
    coordinator = SimpleNamespace(
        cancel_command=asyncio.Event(),
        hold_command_connection=contextlib.nullcontext,
        hass=SimpleNamespace(async_create_task=lambda coro, _name=None: asyncio.create_task(coro)),
        handle_controller_state_update=lambda *_args: None,
        handle_controller_state_updates=lambda *_args: None,
    )
    controller = ReverieController(coordinator, model="9T")  # type: ignore[arg-type]
    controller.write_command = AsyncMock()  # type: ignore[method-assign]
    task = asyncio.create_task(controller.hold_control("back_up", LATCHED_MAX_HOLD_MS))
    loop = asyncio.get_running_loop()
    began = loop.time()
    await _hold_then_cancel(task, coordinator.cancel_command, 0.2)
    assert loop.time() - began < 1
    calls = controller.write_command.await_args_list
    assert len(calls) == 2
    assert calls[1].kwargs["cancel_event"] is not coordinator.cancel_command

