"""Renewable holds (#483) on the Okin N-frame profiles that declare them.

Leggett Okin and Customatic stream a held key until release in their apps. The
real controllers run through the coordinator's scheduler and the services, so
these tests see exactly the frames a held lease writes, on the hold-lease
harness's virtual clock.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.customatic.controller import CustomaticController
from custom_components.adjustable_bed.beds.leggett.okin import LeggettOkinController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_LEGGETT_OKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import okin_nframe as profiles
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.okin_nframe_vectors import FROZEN_FRAMES

ADDRESS = "AA:BB:CC:DD:EE:83"
ZERO = codec.STOP.hex()


@dataclass(frozen=True)
class Case:
    bed_type: str
    profile: str
    motor: str
    """The ``timed_move`` motor."""
    key: str
    """The profile key that motor's held frame carries."""

    def controller(self, coordinator: AdjustableBedCoordinator) -> BedController:
        if self.bed_type == BED_TYPE_LEGGETT_OKIN:
            return LeggettOkinController(coordinator, app_profile=self.profile)
        return CustomaticController(coordinator, profile=self.profile)

    @property
    def held(self) -> str:
        frame = codec.frame(profiles_for(self)[self.key]).hex()
        assert frame in FROZEN_FRAMES[self.profile]
        return frame


def profiles_for(case: Case) -> dict[str, int]:
    if case.bed_type == BED_TYPE_LEGGETT_OKIN:
        return dict(profiles.LEGGETT_PROFILES[case.profile].keys)  # type: ignore[index]
    return dict(profiles.CUSTOMATIC_PROFILES[case.profile].keys)


CASES = (
    Case(BED_TYPE_LEGGETT_OKIN, "prodigy4", "head", "head_up"),
    Case(BED_TYPE_LEGGETT_OKIN, "useries", "feet", "feet_up"),
    Case(BED_TYPE_CUSTOMATIC_CLARITY, "clarity", "back", "back_up"),
)


def _client(frames: list[str]) -> SimpleNamespace:
    """A connected client exposing the plain (revision-1) Okin command route."""

    async def write(_characteristic: object, payload: bytes, **_kwargs: object) -> None:
        frames.append(bytes(payload).hex())

    characteristics = [
        SimpleNamespace(uuid=codec.WRITE_UUID, properties=["write"], handle=1),
        SimpleNamespace(uuid=codec.REVISION_SELECTOR_UUID, properties=["read"], handle=2),
    ]
    return SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid=codec.SERVICE_UUID, characteristics=characteristics)],
        write_gatt_char=write,
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        read_gatt_char=AsyncMock(return_value=b""),
        disconnect=AsyncMock(),
    )


@pytest.fixture(params=CASES, ids=lambda case: case.profile)
async def runtime(
    hass: HomeAssistant, request: pytest.FixtureRequest
) -> AsyncIterator[tuple[HomeAssistant, AdjustableBedCoordinator, Case, list[str]]]:
    case: Case = request.param
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin hold bed",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Okin hold bed",
            CONF_BED_TYPE: case.bed_type,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    frames: list[str] = []
    coordinator._client = _client(frames)  # type: ignore[assignment]
    coordinator._controller = case.controller(coordinator)
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
        yield hass, coordinator, case, frames
    await coordinator.async_shutdown()


@pytest.fixture
async def clock(runtime) -> AsyncIterator[Any]:
    """Virtual time for the test body, after Home Assistant and the bed are set up."""
    with virtual_clock() as clock:
        yield clock


async def _hold(
    hass: HomeAssistant, case: Case, generation: int, duration_ms: int = 300
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": ["bed"],
            "motor": case.motor,
            "direction": "up",
            "duration_ms": duration_ms,
            "hold_owner": "card",
            "hold_generation": generation,
        },
        blocking=True,
    )


async def _started(frames: list[str], held: str) -> None:
    async with asyncio.timeout(2):
        while held not in frames:
            await asyncio.sleep(0.005)


def _assert_released(case: Case, frames: list[str], *, stop: bool = False) -> None:
    """Held frames, then only the profile's release: no held frame after it.

    A STOP adds the profile's own STOP word where it has one (CU170 on Prodigy CE).
    """
    released = {ZERO}
    if stop and "cu170_stop" in profiles_for(case):
        released.add(codec.frame(profiles_for(case)["cu170_stop"]).hex())
    first = next(index for index, frame in enumerate(frames) if frame in released)
    assert set(frames[:first]) == {case.held}
    tail = frames[first:]
    assert set(tail) <= released
    hold = profiles.LEGGETT_HOLD if case.bed_type == BED_TYPE_LEGGETT_OKIN else (
        profiles.CUSTOMATIC_HOLD
    )
    assert tail.count(ZERO) >= hold.releases
    assert ZERO in FROZEN_FRAMES[case.profile]


async def _assert_lease_expired(coordinator: AdjustableBedCoordinator) -> None:
    scheduler = coordinator._command_scheduler
    async with asyncio.timeout(1):
        while not scheduler.recent_records:
            await asyncio.sleep(0.001)
    record = scheduler.recent_records[-1]
    controller = coordinator.controller
    assert controller is not None
    if controller.execution.concurrent:
        # A concurrent motor holds as a member of the merged stream (#516).
        assert record.kind is CommandKind.STREAM
    else:
        assert record.kind is CommandKind.HOLD
        assert record.outcome is CommandOutcome.EXPIRED


def test_only_cu170_declares_a_sustain_window() -> None:
    declared = {
        profile.key: profile.execution
        for profile in (
            *profiles.LEGGETT_PROFILES.values(),
            *profiles.CUSTOMATIC_PROFILES.values(),
        )
    }
    # Only CU170 (Prodigy CE) has a hardware-measured watchdog.
    assert {key: e.sustain_ms for key, e in declared.items() if e.sustain_ms} == {"prodigy4": 217}


async def test_renewal_keeps_streaming_without_a_release(runtime, clock) -> None:
    hass, coordinator, case, frames = runtime
    start = asyncio.create_task(_hold(hass, case, 1))
    await _started(frames, case.held)
    loop = asyncio.get_running_loop()
    began = loop.time()
    for _ in range(6):
        await asyncio.sleep(0.15)
        await asyncio.wait_for(_hold(hass, case, 1), 0.1)
        assert ZERO not in frames
        assert not start.done()
    await asyncio.wait_for(start, 3)

    # Six renewals of a 300 ms lease outlived any one lease.
    assert loop.time() - began >= 0.9
    assert frames.count(case.held) >= 8
    _assert_released(case, frames)
    await _assert_lease_expired(coordinator)


async def test_expiry_runs_the_profile_release(runtime, clock) -> None:
    hass, coordinator, case, frames = runtime
    loop = asyncio.get_running_loop()
    began = loop.time()
    await asyncio.wait_for(_hold(hass, case, 2, duration_ms=200), 3)
    # The lease, not the 30 s ceiling, ended the hold.
    assert loop.time() - began < 1.5
    _assert_released(case, frames)
    await _assert_lease_expired(coordinator)


async def test_stop_preempts_the_hold_and_refuses_renewal(runtime, clock) -> None:
    hass, coordinator, case, frames = runtime
    start = asyncio.create_task(_hold(hass, case, 3, duration_ms=5000))
    await _started(frames, case.held)
    await coordinator.async_stop_command()
    await asyncio.wait_for(start, 2)
    _assert_released(case, frames, stop=True)
    count = len(frames)
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _hold(hass, case, 3)
    await asyncio.sleep(0.15)
    assert frames[count:] == []


async def test_hold_control_lease_streams_the_held_control(runtime, clock) -> None:
    hass, coordinator, case, frames = runtime
    if case.bed_type == BED_TYPE_LEGGETT_OKIN:
        control, word = "flat", profiles_for(case)["flat"]
    else:
        # A fixed two-motor mask the app sends as one held control.
        control = "back_up+legs_up"
        word = profiles_for(case)["back_up"] | profiles_for(case)["legs_up"]
    held = codec.frame(word).hex()
    assert held in FROZEN_FRAMES[case.profile]

    async def hold() -> None:
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": ["bed"],
                "control": control,
                "duration": 0.3,
                "hold_owner": "card",
                "hold_generation": 4,
            },
            blocking=True,
        )

    start = asyncio.create_task(hold())
    await _started(frames, held)
    for _ in range(3):
        await asyncio.sleep(0.15)
        await asyncio.wait_for(hold(), 0.1)
        assert ZERO not in frames
    await asyncio.wait_for(start, 3)
    first_zero = frames.index(ZERO)
    assert set(frames[:first_zero]) == {held}
    assert set(frames[first_zero:]) == {ZERO}
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED


async def test_held_move_feeds_the_estimate_like_a_timed_move(
    runtime, clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lease-held move feeds the estimate like a finite timed move (#601)."""
    from custom_components.adjustable_bed import position_estimate as pe

    monkeypatch.setattr(pe, "_clock", clock.time)

    hass, coordinator, case, frames = runtime
    entry_id = coordinator.entry.entry_id
    manager = await pe.async_setup_position_estimates(hass, entry_id, ((ADDRESS, None),))
    bed = manager.beds[ADDRESS]
    bed.configure({case.motor: (10.0, 10.0)})
    bed.set_reference()
    groups = property(lambda _self: {case.motor: (case.motor,)})
    try:
        with patch.object(type(coordinator.controller), "estimated_position_motor_groups", groups):
            loop = asyncio.get_running_loop()
            began = loop.time()
            start = asyncio.create_task(_hold(hass, case, 5))
            await _started(frames, case.held)
            await asyncio.sleep(0.2)
            await asyncio.wait_for(_hold(hass, case, 5), 0.1)
            await asyncio.wait_for(start, 3)
            held_s = loop.time() - began
            hold_percent = bed.motors[case.motor].percent
            assert hold_percent is not None
            # One move, timed from its start through the profile's own release.
            assert bed.motors[case.motor].moves_since_reference == 1
            assert 0.5 <= hold_percent / 100 * 10.0 <= held_s + 0.05

            # The same duration without a lease takes the same timing path.
            bed.set_reference()
            began = loop.time()
            await hass.services.async_call(
                DOMAIN,
                "timed_move",
                {"device_id": ["bed"], "motor": case.motor, "direction": "up", "duration_ms": 500},
                blocking=True,
            )
            finite_s = loop.time() - began
            finite_percent = bed.motors[case.motor].percent
            assert finite_percent is not None
            assert 0.5 <= finite_percent / 100 * 10.0 <= finite_s
            assert abs(hold_percent - finite_percent) < 2.5
    finally:
        await pe.async_unload_position_estimates(hass, entry_id)
