"""Renewable holds (#483) on the Richmat 6E codec's stream-evidence profiles.

Each case drives the scenario's real controller the way ``timed_move`` does
under a lease, on virtual time. While the lease lives the controller refreshes
its held code at its own interval, past the entry's pulse count; when the lease
expires it sends its STOP; STOP preempts it and motion never resumes. Every
frame is a frozen vector. BedTech, GM Motor and Casper Base declare nothing.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from custom_components.adjustable_bed.profiles import richmat as profiles
from tests.hold_lease_wire import intervals, leased_hold
from tests.richmat_vectors import FROZEN_FRAMES

WILINKE_STOP = "6e01006edd"
# The wire-snapshot client takes this long per write; loops that wait after
# each write add it to their interval.
WRITE_MS = 7
END_AFTER_S = 5

# Scenario -> (refresh interval in ms, the STOP that follows the hold).
CASES: dict[str, tuple[int, str]] = {
    # The fixed-table routes refresh at the entry's pulse delay, as they always have.
    "richmat:wilinke": (150, WILINKE_STOP),
    "richmat:nordic": (150, "6e"),
    "richmat:prefix55": (150, "5501006ec4"),
    "richmat:prefixaa": (150, "aa01006e19"),
    # The automatic remote code of this scenario selects the compatibility STOP.
    "richmat": (150, "6e01005ecd"),
    "richmat_revive:model_vorm": (100, WILINKE_STOP),
    "richmat_best_mattress:model_bfrm": (100, WILINKE_STOP),
    "richmat_blvd_home:model_eorm": (100, WILINKE_STOP),
    "richmat_harmony:model_t3rm": (100, WILINKE_STOP),
    "richmat_idealbed:model_p6rm": (100, WILINKE_STOP),
    "leggett_wilinke": (110, WILINKE_STOP),
    "leggett_platt:mlrm": (100, WILINKE_STOP),
    "hjbed": (100, WILINKE_STOP),
}


def test_only_the_stream_rows_declare_a_hold() -> None:
    declared = {
        profile.key
        for profile in (
            *profiles.RICHMAT.values(),
            *profiles.RICHMAT_MH.values(),
            profiles.BEDTECH,
            profiles.LEGGETT_WILINKE,
            profiles.HJBED,
        )
        if profile.execution.hold == "stream"
    }
    assert profiles.BEDTECH.key not in declared
    assert len(declared) == 11


async def _timed_move(controller: Any) -> None:
    """The first motor, as ``timed_move`` runs it under a lease."""
    spec = controller.motor_control_specs[0]
    if spec.hold is not None:
        await controller.hold_control(spec.hold.up_control, HOLD_CEILING_MS)
    else:
        await spec.open_fn(controller)


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_lease_streams_at_the_profile_interval_then_expiry_stops(scenario: str) -> None:
    interval, stop = CASES[scenario]
    wire = await leased_hold(scenario, _timed_move, end_after_s=END_AFTER_S, end="expire")

    held = {write.data.hex() for write in wire.held}
    assert len(held) == 1, held
    # Open-ended: the refresh outlives the entry's finite pulses and spans the lease.
    assert wire.pulse_count * interval < END_AFTER_S * 1000
    assert len(wire.held) >= END_AFTER_S * 1000 // (interval + WRITE_MS)
    assert intervals(wire.held) <= {interval, interval + WRITE_MS}
    assert [write.data.hex() for write in wire.after] == [stop]
    assert held | {stop} <= FROZEN_FRAMES[wire.profile_key]


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_stop_preempts_the_lease_without_resuming_motion(scenario: str) -> None:
    _interval, stop = CASES[scenario]
    wire = await leased_hold(scenario, _timed_move, end_after_s=1, end="stop")
    (held,) = {write.data.hex() for write in wire.held}
    after = [write.data.hex() for write in wire.after]
    assert held not in after
    assert after and set(after) == {stop}


@pytest.mark.parametrize("scenario", ["richmat:wilinke", "richmat_revive:model_vorm"])
async def test_without_a_lease_the_move_stays_finite(scenario: str) -> None:
    wire = await leased_hold(
        scenario, _timed_move, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    assert len(wire.held) <= wire.pulse_count + 1
    assert not wire.after


@pytest.mark.parametrize("leased", [True, False])
async def test_rmcontrol_sustain_press_refreshes_until_the_lease_ends(leased: bool) -> None:
    """RMControl (rmc2) holds its catalog motion at the app's 100 ms cadence."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.adjustable_bed.beds.rmcontrol import RmcontrolController
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        HoldLease,
    )

    coordinator = MagicMock()
    coordinator.motor_pulse_count = 2
    coordinator.cancel_command = asyncio.Event()
    controller = RmcontrolController(coordinator, "A0RM", is_wilinke=True)
    assert controller.execution.hold == "stream"
    controller.write_command = AsyncMock()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=coordinator.cancel_command,
        admitted_stop_epoch=0,
        intent_id="lease",
        kind=CommandKind.HOLD if leased else CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"motor:feet"}),
        lease=HoldLease(owner="card", generation=1, action="up", duration_s=1) if leased else None,
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        await controller.move_feet_up()
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    held, release = controller.write_command.call_args_list
    expected = HOLD_CEILING_MS // 100 + 1 if leased else 2
    assert held.kwargs == {"repeat_count": expected, "repeat_delay_ms": 100}
    assert release.args == (bytes.fromhex("6e 01 00 6e dd"),)
    assert {held.args[0].hex(), release.args[0].hex()} <= FROZEN_FRAMES["richmat_wilinke"]
