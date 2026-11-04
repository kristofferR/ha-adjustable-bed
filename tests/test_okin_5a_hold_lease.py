"""Renewable holds (#483) on the Okin 5A ELEVATE profile, both ``star_elevate`` routes.

The M1X12 and M5X5 apps refresh a held key every 100 ms until release, then
send STOP once. No other Okin 5A profile declares a hold: the Nectar and MF900
reports reach the Okin CST frame, not the 5A keys those profiles send.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.star_elevate import StarElevateController
from custom_components.adjustable_bed.beds.starcode_m1x12 import StarElevateM1X12Controller
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.okin_5a import ELEVATE, PROFILES
from custom_components.adjustable_bed.services import async_register_services
from tests.okin_5a_vectors import FROZEN_FRAMES

HELD = ELEVATE.frame("head_up").hex()
STOP = ELEVATE.frame("stop").hex()


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


@dataclass
class Lift:
    hass: HomeAssistant
    coordinator: AdjustableBedCoordinator
    writes: list[tuple[float, str]]

    def frames(self) -> list[str]:
        return [frame for _, frame in self.writes]


@pytest.fixture(params=["default", "m1x12"])
async def lift(hass: HomeAssistant, request: pytest.FixtureRequest) -> AsyncIterator[Lift]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ELEVATE",
        unique_id="AA:BB:CC:DD:EE:5A",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:5A",
            CONF_NAME: "ELEVATE",
            CONF_BED_TYPE: BED_TYPE_STAR_ELEVATE,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            # Finite pulses at an entry cadence the app does not use.
            CONF_MOTOR_PULSE_COUNT: 3,
            CONF_MOTOR_PULSE_DELAY_MS: 250,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    writes: list[tuple[float, str]] = []

    async def write(_char, data, response=False) -> None:
        writes.append((asyncio.get_running_loop().time(), bytes(data).hex()))

    client = MagicMock(is_connected=True)
    client.write_gatt_char = AsyncMock(side_effect=write)
    client.disconnect = AsyncMock()
    client.stop_notify = AsyncMock()
    coordinator._client = client
    cls = StarElevateM1X12Controller if request.param == "m1x12" else StarElevateController
    controller = cls(coordinator)
    controller._initialized = True
    coordinator._controller = controller
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield Lift(hass, coordinator, writes)
    await coordinator.async_shutdown()


async def _move(lift: Lift, generation: int, duration_ms: int = 300) -> None:
    await lift.hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": ["lift"],
            "motor": "elevate_actuator_1",
            "direction": "up",
            "duration_ms": duration_ms,
            "hold_owner": "card",
            "hold_generation": generation,
        },
        blocking=True,
    )


async def _started(lift: Lift) -> None:
    async with asyncio.timeout(2):
        while HELD not in lift.frames():
            await asyncio.sleep(0.005)


async def test_renewals_keep_streaming_at_100_ms_then_expiry_sends_stop(lift: Lift) -> None:
    start = asyncio.create_task(_move(lift, 1))
    began = asyncio.get_running_loop().time()
    for _ in range(6):
        await asyncio.sleep(0.15)
        await asyncio.wait_for(_move(lift, 1), 1)
        assert STOP not in lift.frames()
        assert not start.done()
    await asyncio.wait_for(start, 3)

    frames = lift.frames()
    first_stop = frames.index(STOP)
    assert set(frames[:first_stop]) == {HELD}
    assert set(frames[first_stop:]) == {STOP}
    times = [at for at, frame in lift.writes if frame == HELD]
    # Renewals outlived the first lease and the entry's three 250 ms pulses.
    assert times[-1] - began >= 0.9
    mean_gap = (times[-1] - times[0]) / (len(times) - 1)
    assert 0.09 <= mean_gap <= 0.15
    record = lift.coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


async def test_lease_expiry_without_renewal_releases(lift: Lift) -> None:
    await asyncio.wait_for(_move(lift, 2, duration_ms=150), 2)
    assert lift.frames()[-1] == STOP
    assert lift.coordinator._command_scheduler.recent_records[-1].outcome is (
        CommandOutcome.EXPIRED
    )


async def test_stop_preempts_renewal(lift: Lift) -> None:
    start = asyncio.create_task(_move(lift, 3, duration_ms=5000))
    await _started(lift)
    await lift.coordinator.async_stop_command()
    await asyncio.wait_for(start, 2)
    frames = lift.frames()
    assert HELD not in frames[frames.index(STOP) :]
    count = len(frames)
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _move(lift, 3)
    await asyncio.sleep(0.3)
    assert len(lift.frames()) == count


async def test_finite_move_keeps_the_entry_pulses(lift: Lift) -> None:
    if isinstance(lift.coordinator.controller, StarElevateM1X12Controller):
        pytest.skip("The M1X12 route always holds at the app sender interval")
    await lift.coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.move_head_up(), resource="motor:elevate_actuator_1"
    )
    times = [at for at, frame in lift.writes if frame == HELD]
    assert len(times) == 3
    assert times[1] - times[0] >= 0.24
