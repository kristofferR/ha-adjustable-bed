"""Renewable holds (#483) on the Malouf profiles with stream evidence (row023).

Each case drives the scenario's real controller the way ``timed_move`` does
under a lease, on virtual time. While the lease lives the controller refreshes
its movement frame at its own interval, past the entry's pulse count; when the
lease expires it sends its STOP; STOP preempts it and motion never resumes.
Every frame is a frozen vector.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.hold_lease_wire import intervals, leased_hold
from tests.keeson_vectors import FROZEN_FRAMES as KEESON_FRAMES
from tests.malouf_vectors import FROZEN_FRAMES as MALOUF_FRAMES

FROZEN = {**MALOUF_FRAMES, **KEESON_FRAMES}
# The wire-snapshot client takes this long per write; loops that wait after
# each write add it to their interval.
WRITE_MS = 7
END_AFTER_S = 5

# Scenario -> (refresh interval in ms, the STOP that follows the hold).
CASES: dict[str, tuple[int, str]] = {
    # The app's own hold cadence, then its release.
    "malouf_app": (150, "0502000000000000"),
    # The fixed routes refresh at the entry's pulse delay, as they always have.
    "malouf_new_okin": (100, "0502000000000000"),
    "malouf_legacy_okin": (150, "e6fe16000000000005"),
}


async def _move(controller: Any) -> None:
    await controller.motor_control_specs[0].open_fn(controller)


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_lease_streams_at_the_profile_interval_then_expiry_stops(scenario: str) -> None:
    interval, stop = CASES[scenario]
    wire = await leased_hold(scenario, _move, end_after_s=END_AFTER_S, end="expire")

    held = {write.data.hex() for write in wire.held}
    assert len(held) == 1, held
    # Open-ended: the refresh outlives the entry's finite pulses and spans the lease.
    assert wire.pulse_count * interval < END_AFTER_S * 1000
    assert len(wire.held) >= END_AFTER_S * 1000 // (interval + WRITE_MS)
    assert intervals(wire.held) <= {interval, interval + WRITE_MS}
    assert [write.data.hex() for write in wire.after] == [stop]
    assert held | {stop} <= FROZEN[wire.profile_key]


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_stop_preempts_the_lease_without_resuming_motion(scenario: str) -> None:
    _interval, stop = CASES[scenario]
    wire = await leased_hold(scenario, _move, end_after_s=1, end="stop")
    (held,) = {write.data.hex() for write in wire.held}
    after = [write.data.hex() for write in wire.after]
    assert held not in after
    assert after and set(after) == {stop}


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_without_a_lease_the_move_stays_finite(scenario: str) -> None:
    wire = await leased_hold(scenario, _move, end_after_s=END_AFTER_S, end="expire", leased=False)
    assert len(wire.held) <= wire.pulse_count + 1
    assert not wire.after
