"""Renewable holds (#483) on latched protocols, which move until STOP arrives.

A latched bed keeps moving after its one start frame, so a vanished client
leaves it running until the lease ends. Its holds therefore stop at a shorter
ceiling than streamed holds, and the lease's end sends the protocol's own STOP.
The lease tests run each real controller on virtual time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.adjustable_bed.beds.motion_bed.actions import MOTION_BED_ACTIONS
from custom_components.adjustable_bed.beds.motion_bed.protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.codec import ff_frame
from custom_components.adjustable_bed.const import (
    BED_TYPE_ISLEEP,
    BED_TYPE_KAIDI,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    KAIDI_VARIANT_FLOYD,
    KAIDI_VARIANT_SEAT_1_2,
)
from custom_components.adjustable_bed.execution import (
    HOLD_CEILING_MS,
    LATCHED_HOLD_CEILING_MS,
    NO_EXECUTION_CAPABILITIES,
    STREAM_HOLD,
    ExecutionCapabilities,
)
from custom_components.adjustable_bed.profiles.ff_frame import (
    BEDSENSE,
    BEDSENSE_ACTIONS,
    MOTION_BED,
    SOLACE_PROFILES,
    SolaceCommands,
)
from custom_components.adjustable_bed.services import _hold_ceiling
from tests.ff_frame_vectors import FROZEN_FRAMES
from tests.hold_lease_wire import HeldWire, leased_hold
from tests.test_controller_contract import _create_controller_for_bed_type

LATCHED = ExecutionCapabilities(hold="latched")
DECLARED_SOLACE = ("common", "home_k1", "home_k2", "motion_flex", "woosa")


def test_latched_holds_have_the_shorter_ceiling() -> None:
    assert LATCHED.hold_ceiling_ms == LATCHED_HOLD_CEILING_MS == 10_000
    assert STREAM_HOLD.hold_ceiling_ms == HOLD_CEILING_MS == 30_000
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



def test_a_leased_plan_is_clamped_to_the_controller_ceiling() -> None:
    """Services bound every leased timed move and held control by the ceiling."""
    stream, latched = _Declared(STREAM_HOLD), _Declared(LATCHED)
    assert _hold_ceiling(latched, HOLD_CEILING_MS) == LATCHED_HOLD_CEILING_MS  # type: ignore[arg-type]
    assert _hold_ceiling(stream, HOLD_CEILING_MS) == HOLD_CEILING_MS  # type: ignore[arg-type]
    assert _hold_ceiling(latched, 750) == 750  # type: ignore[arg-type]


@dataclass(frozen=True)
class _Declared:
    execution: ExecutionCapabilities


Move = Callable[[Any], Awaitable[None]]


def _press(name: str) -> Move:
    async def move(controller: Any) -> None:
        await getattr(controller, name)()

    return move


async def _reverie(controller: Any) -> None:
    # Services pass the clamped ceiling to a declared held control.
    await controller.hold_control("back_up", LATCHED_HOLD_CEILING_MS)


@dataclass(frozen=True)
class Case:
    move: Move
    start: str
    """The one start frame (Kaidi's controller repeats it at the entry cadence)."""


CASES: dict[str, Case] = {
    "solace:woosa": Case(_press("move_back_up"), SolaceCommands.MOTOR_BACK_UP.hex()),
    "bedsense": Case(_press("move_back_up"), BEDSENSE_ACTIONS["back_up"].frame.hex()),
    "reverie": Case(_reverie, "550154"),
    "kaidi:seat_1": Case(_press("move_back_up"), "030403020120ffffffff01010000"),
    "isleep": Case(_press("move_back_up"), "0304030201200100000001010000"),
    "remacro": Case(_press("move_back_up"), "0201010100000000"),
}


def _frames(wire: HeldWire) -> list[str]:
    return [write.data.hex() for write in (*wire.held, *wire.after)]


def _release(wire: HeldWire, start: str) -> list[str]:
    """What follows the last start frame: the protocol's own release."""
    frames = _frames(wire)
    last = max(index for index, frame in enumerate(frames) if frame == start)
    return frames[last + 1 :]


@pytest.fixture(params=sorted(CASES))
def scenario(request: pytest.FixtureRequest) -> str:
    return request.param


async def test_a_lease_holds_past_a_finite_press_then_expiry_sends_stop(scenario: str) -> None:
    case = CASES[scenario]
    wire = await leased_hold(scenario, case.move, end_after_s=6, end="expire")
    finite = await leased_hold(scenario, case.move, end_after_s=6, end="expire", leased=False)

    # Still holding when the lease expires, then exactly the finite press's release.
    assert case.start in [write.data.hex() for write in wire.held]
    assert _release(wire, case.start) == [write.data.hex() for write in wire.after]
    assert wire.after and _release(wire, case.start) == _release(finite, case.start)


async def test_an_unrenewed_latched_hold_stops_at_its_ceiling(scenario: str) -> None:
    case = CASES[scenario]
    ceiling_ms = LATCHED_HOLD_CEILING_MS
    wire = await leased_hold(scenario, case.move, end_after_s=ceiling_ms / 1000 + 3, end="expire")
    finite = await leased_hold(scenario, case.move, end_after_s=6, end="expire", leased=False)

    # Nothing was left to end: the controller released by itself near the ceiling.
    assert wire.after == ()
    release = _release(finite, case.start)
    assert _release(wire, case.start) == release
    first_release = next(
        write.at_ms for write in wire.held if write.data.hex() == release[0]
        and write.at_ms > wire.held[0].at_ms
    )
    # Kaidi and iSleep open a session first; acknowledgements add a little per write.
    assert ceiling_ms <= first_release <= ceiling_ms + 2_000


async def test_stop_preempts_the_lease(scenario: str) -> None:
    case = CASES[scenario]
    # Kaidi and iSleep open their session first; STOP lands after motion starts.
    wire = await leased_hold(scenario, case.move, end_after_s=2, end="stop")
    after = [write.data.hex() for write in wire.after]
    assert after and case.start not in after
