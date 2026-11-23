"""Renewable holds (#483) on the Okin 5A ELEVATE profile, both ``star_elevate`` routes.

The M1X12 and M5X5 apps refresh a held key every 100 ms until release, then
send STOP once. No other Okin 5A profile declares a hold: the Nectar and MF900
reports reach the Okin CST frame, not the 5A keys those profiles send. The
lease tests run the real controllers on virtual time.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adjustable_bed.execution import HOLD_CEILING_MS
from custom_components.adjustable_bed.profiles.okin_5a import ELEVATE, PROFILES
from tests.hold_lease_wire import intervals, leased_hold
from tests.okin_5a_vectors import FROZEN_FRAMES

HELD = ELEVATE.frame("head_up").hex()
STOP = ELEVATE.frame("stop").hex()
END_AFTER_S = 3


def test_only_elevate_declares_a_stream_hold() -> None:
    assert {key for key, p in PROFILES.items() if p.execution.hold} == {"star_elevate"}
    assert ELEVATE.execution.hold == "stream"
    assert ELEVATE.hold_refresh_ms == 100


def test_held_and_release_frames_are_frozen() -> None:
    frozen = FROZEN_FRAMES["star_elevate"]
    for action in ("head_up", "head_down", "feet_up", "feet_down", "both_up", "both_down"):
        assert ELEVATE.frame(action).hex() in frozen
    assert STOP in frozen
    assert ELEVATE.stop.repeats == 1


async def _default(controller: Any) -> None:
    await controller.move_head_up()


async def _m1x12(controller: Any) -> None:
    await controller.hold_control("actuator_1_up", HOLD_CEILING_MS)


ROUTES = {
    "star_elevate": _default,
    "star_elevate:adjustable_comfort_m1x12": _m1x12,
}


@pytest.mark.parametrize("scenario", ROUTES)
async def test_lease_streams_at_100_ms_then_expiry_sends_one_stop(scenario: str) -> None:
    wire = await leased_hold(scenario, ROUTES[scenario], end_after_s=END_AFTER_S, end="expire")

    assert {write.data.hex() for write in wire.held} == {HELD}
    # The apps' 100 ms refresh outlives the entry's configured pulses.
    assert wire.pulse_count * 100 < END_AFTER_S * 1000
    if scenario == "star_elevate":
        # The shared repeat loop waits 100 ms after each acknowledged write.
        assert all(100 <= gap <= 110 for gap in intervals(wire.held))
    else:
        # The M1X12 sender ticks every 100 ms, first 100 ms after the press.
        assert intervals(wire.held) == {100}
        assert wire.held[0].at_ms == 100
    assert len(wire.held) >= END_AFTER_S * 1000 // 110
    # Expiry sends the profile's complete release, STOP once, within one refresh.
    assert [w.data.hex() for w in wire.after] == [STOP]
    assert wire.after[0].at_ms - wire.ended_ms <= 110


@pytest.mark.parametrize("scenario", ROUTES)
async def test_stop_preempts_the_lease(scenario: str) -> None:
    wire = await leased_hold(scenario, ROUTES[scenario], end_after_s=1, end="stop")
    after = [write.data.hex() for write in wire.after]
    assert {write.data.hex() for write in wire.held} == {HELD}
    assert after and set(after) == {STOP}


async def test_default_route_finite_move_keeps_the_entry_pulses() -> None:
    wire = await leased_hold(
        "star_elevate", _default, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    frames = [write.data.hex() for write in (*wire.held, *wire.after)]
    assert frames == [HELD] * wire.pulse_count + [STOP]
