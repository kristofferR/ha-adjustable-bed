"""Renewable holds (#483) on standalone controllers with stream evidence.

Each declared controller runs on the wire-snapshot scenarios on virtual time
(``tests/hold_lease_wire.py``). Under a lease it streams its own held frame at
its app's refresh past any finite press until the lease ends or STOP preempts
it. Then it sends exactly the release its own finite press ends with. Lease
renewal, staleness and STOP ordering are the scheduler's, covered by
``test_hold_lease.py`` and ``test_hold_lease_service.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
)
from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from tests.hold_lease_wire import End, HeldWire, Write, intervals, leased_hold
from tests.test_controller_contract import _create_controller_for_bed_type

DECLARED = (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
)
# Past every finite press, including Leggett Gen2's 25 x 200 ms burst.
END_AFTER_S = 6


@pytest.mark.parametrize("bed_type", DECLARED)
async def test_standalone_controllers_declare_a_stream_hold(bed_type: str) -> None:
    controller = await _create_controller_for_bed_type(bed_type)
    assert controller.execution.hold == "stream"


async def test_the_generic_vibradorm_route_keeps_finite_pulses() -> None:
    controller = await _create_controller_for_bed_type(BED_TYPE_VIBRADORM)
    assert controller.execution.hold is None


Move = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class Case:
    held: str
    """The held frame the app refreshes."""
    refresh_ms: int
    """The app's refresh; one write's acknowledgement may add a few ms."""
    leased: Move
    finite: Move
    """The same press without a lease."""


def _press(name: str) -> Move:
    async def move(controller: Any) -> None:
        await getattr(controller, name)()

    return move


def _hold(control: str, duration_ms: int) -> Move:
    """``control`` names the held control; ``"*"`` takes the first one offered."""

    async def move(controller: Any) -> None:
        name = controller.held_control_options[0] if control == "*" else control
        await controller.hold_control(name, duration_ms)

    return move


def _cover(name: str, held: str, refresh_ms: int) -> Case:
    """A cover press: under a lease it streams, without one it pulses."""
    return Case(held, refresh_ms, _press(name), _press(name))


def _held_control(control: str, held: str, refresh_ms: int) -> Case:
    """A held control: the lease holds it to the ceiling, a finite press for 0.5 s."""
    return Case(held, refresh_ms, _hold(control, HOLD_CEILING_MS), _hold(control, 500))


CASES: dict[str, Case] = {
    "linak:bed_control": _cover("move_back_up", "0b00", 100),
    "linak:performance_legacy": _cover("move_back_up", "0b00", 300),
    "timotion_ahf": _cover("move_back_up", "ddddff0101000000000000", 100),
    "vibradorm_app": _cover("move_back_up", "0b", 100),
    "vmatbasic": _cover("move_back_up", "0b", 30),
    "starcode_m5x5": _cover("move_head_up", "05020000000100", 100),
    "leggett_gen2": _cover("move_head_up", "4d203a303a", 200),
    "jensen": _cover("move_head_up", "100100000000", 300),
    "furnimove": _cover("move_back_up", "e5fe160000000105", 100),
    "octo:standard": _held_control("back_up", "40027000010b0240", 350),
    "starcode_m1x12": _held_control("part_1_up", "05020000000100", 100),
    "sleepys_elite_app": _held_control("*", "05020000000100", 100),
}


def _hex(writes: tuple[Write, ...]) -> list[str]:
    return [write.data.hex() for write in writes]


def _motion(wire: HeldWire, held: str) -> tuple[Write, ...]:
    """The held frames, from the first on; some protocols release before moving."""
    return tuple(write for write in (*wire.held, *wire.after) if write.data.hex() == held)


def _finite_release(wire: HeldWire, held: str) -> list[str]:
    """What the finite press sends after its last held frame: its own release."""
    frames = _hex((*wire.held, *wire.after))
    last = max(index for index, frame in enumerate(frames) if frame == held)
    return frames[last + 1 :]


@pytest.fixture(params=sorted(CASES))
def scenario(request: pytest.FixtureRequest) -> str:
    return request.param


async def test_a_lease_streams_past_a_finite_press_then_expiry_releases(scenario: str) -> None:
    case = CASES[scenario]
    wire = await leased_hold(scenario, case.leased, end_after_s=END_AFTER_S, end="expire")
    finite = await leased_hold(
        scenario, case.finite, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    motion = _motion(wire, case.held)

    # The app's own refresh paces the stream until the lease ends.
    assert all(case.refresh_ms <= gap <= case.refresh_ms + 10 for gap in intervals(motion))
    assert motion[-1].at_ms >= wire.ended_ms - case.refresh_ms - 10
    assert len(motion) > len(_motion(finite, case.held))
    # Expiry sends exactly the release the finite press ends with, and no motion.
    assert _hex(wire.after) == _finite_release(finite, case.held)
    assert case.held not in _hex(wire.after)


@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_octo_tv_lift_hold_refreshes_and_releases(end: End) -> None:
    wire = await leased_hold(
        "octo:standard",
        lambda controller: controller.hold_control("tv_lift_up", HOLD_CEILING_MS),
        entry_data={CONF_OCTO_MOTOR_COUNT_OVERRIDE: "1"},
        end_after_s=1,
        end=end,
    )
    motion = _motion(wire, CASES["octo:standard"].held)
    assert len(motion) == 3
    assert all(350 <= gap <= 360 for gap in intervals(motion))
    assert _hex(wire.after) == ["40027300000b40"] * (2 if end == "stop" else 1)


async def test_stop_preempts_the_lease_and_releases(scenario: str) -> None:
    case = CASES[scenario]
    wire = await leased_hold(scenario, case.leased, end_after_s=1, end="stop")
    finite = await leased_hold(
        scenario, case.finite, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    after = _hex(wire.after)
    release = _finite_release(finite, case.held)
    assert case.held not in after
    # The hold's own release comes first, then the STOP's own frames.
    assert after[: len(release)] == release
