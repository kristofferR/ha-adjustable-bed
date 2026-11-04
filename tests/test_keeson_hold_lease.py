"""Renewable holds (#483) on the Keeson codec's stream-evidence profiles.

Each case drives the scenario's real controller the way ``timed_move`` or
``hold_control`` does under a lease, on virtual time. While the lease lives the
controller refreshes its app's held frame at the app's interval, past the
entry's pulse count; when it expires the controller sends its app's release;
STOP preempts it and motion never resumes. Every frame is a frozen vector.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from tests.hold_lease_wire import intervals, leased_hold
from tests.keeson_vectors import FROZEN_FRAMES

ZERO = "e5fe160000000006"
E6_ZERO = "e6fe16000000000005"
# The wire-snapshot client takes this long per write; loops that wait after
# each write add it to their interval.
WRITE_MS = 7

# Scenario -> (app refresh interval in ms, release frames after the hold).
CASES: dict[str, tuple[int, tuple[str, ...]]] = {
    "keeson:ergomotion": (100, (ZERO,)),
    "ergomotion": (100, (ZERO,)),
    "serta": (100, (ZERO,)),
    "keeson:restonic_a": (100, (ZERO,)),
    "keeson:restonic_b": (100, (ZERO,)),
    "keeson:innova": (100, (ZERO,)),
    "keeson:simon_li": (100, (ZERO,)),
    "keeson:okin_seating": (100, (ZERO,)),
    "keeson:heal_every_night": (100, (ZERO,)),
    "keeson:americanstar": (100, (ZERO,)),
    "keeson:avanti_bases": (100, (ZERO,)),
    "keeson:bedsense_bases": (100, (ZERO,)),
    "keeson:dynasty_bases": (100, (ZERO,)),
    "keeson:maxcoil_una": (100, (ZERO,)),
    # Adjustable Lite releases by ending the refresh; there is no release frame.
    "keeson:adjustable_lite": (300, ()),
    # Direct P2 remotes end by refresh cessation, then poll status three times.
    "keeson:ksbt": (100, ("00b0",) * 3),
    # SBI and Cool Base refresh at the entry's pulse delay, as they always have.
    "sbi": (100, (ZERO,)),
    "sbi:side_a": (100, ("e6fe16000000000104",)),
    "coolbase": (100, (ZERO,)),
    "bf": (200, (ZERO,)),
    "cherish": (200, (ZERO,)),
    "comfort_enhancements": (200, (ZERO,)),
    "glideaway_motion": (300, (E6_ZERO, E6_ZERO)),
    "adjustamattress": (200, (E6_ZERO,)),
    "adjustamattress:P1_L2": (200, (E6_ZERO,)),
    "tempur_curve": (100, (ZERO,)),
    "qplus_app": (100, (ZERO,)),
    "serta_mp_remote": (100, (ZERO,)),
    "omazz_adjusto_iii": (100, (ZERO,)),
    "ergomotion_app": (100, (ZERO,)),
    "row_control": (100, (ZERO,)),
    "ergo_slim": (100, (ZERO,)),
    "tempur_au": (100, (ZERO,)),
    "ergomotion_4": (100, (ZERO,)),
}
END_AFTER_S = 5


async def _timed_move(controller: Any) -> None:
    """The first motor, as ``timed_move`` runs it under a lease."""
    specs = controller.motor_control_specs
    if not specs:
        # Ergomotion 4.0 holds its catalog controls through ``hold_control``.
        await controller.hold_control(controller.held_control_options[0], HOLD_CEILING_MS)
        return
    spec = specs[0]
    if spec.hold is not None:
        await controller.hold_control(spec.hold.up_control, HOLD_CEILING_MS)
    else:
        await spec.open_fn(controller)


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_lease_streams_at_the_app_interval_then_expiry_releases(scenario: str) -> None:
    interval, release = CASES[scenario]
    wire = await leased_hold(scenario, _timed_move, end_after_s=END_AFTER_S, end="expire")

    held = {write.data.hex() for write in wire.held}
    assert len(held) == 1, held
    # Open-ended: the refresh outlives the entry's finite pulses and spans the lease.
    assert wire.pulse_count * interval < END_AFTER_S * 1000
    assert len(wire.held) >= END_AFTER_S * 1000 // (interval + WRITE_MS)
    assert intervals(wire.held) <= {interval, interval + WRITE_MS}
    assert tuple(write.data.hex() for write in wire.after) == release
    frozen = FROZEN_FRAMES[wire.profile_key]
    assert held | set(release) <= frozen


@pytest.mark.parametrize("scenario", sorted(CASES))
async def test_stop_preempts_the_lease_without_resuming_motion(scenario: str) -> None:
    wire = await leased_hold(scenario, _timed_move, end_after_s=1, end="stop")
    (held,) = {write.data.hex() for write in wire.held}
    after = [write.data.hex() for write in wire.after]
    assert held not in after
    assert set(after) <= FROZEN_FRAMES[wire.profile_key]
    _interval, release = CASES[scenario]
    if release and release[0] != "00b0":
        assert release[0] in after


@pytest.mark.parametrize("scenario", ["keeson:ergomotion", "keeson:simon_li", "glideaway_motion"])
async def test_without_a_lease_the_move_stays_finite(scenario: str) -> None:
    wire = await leased_hold(
        scenario, _timed_move, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    # The finite pulses and the release, all before the window ends.
    assert len(wire.held) <= wire.pulse_count + 2
    assert not wire.after


async def test_adjustamattress_okin_models_stay_finite() -> None:
    """Models P3 and P4 send Okin N-frames, outside this family's declarations."""

    async def execution(controller: Any) -> None:
        assert controller.profile is None
        assert controller.execution.hold is None

    await leased_hold("adjustamattress:P4_L6", execution, end_after_s=0, end="expire")
