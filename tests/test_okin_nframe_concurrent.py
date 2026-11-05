"""Concurrent motors (#516) on Leggett Okin through the merged stream.

The real controller runs through the coordinator's scheduler and services, so
these tests see every frame the composed stream writes. Timing runs on the
hold-lease harness's virtual clock: no real timer is awaited.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.leggett_okin import LeggettOkinController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import CommandKind
from custom_components.adjustable_bed.const import (
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
from tests.okin_nframe_vectors import COMPOSED_FRAMES, FROZEN_FRAMES
from tests.test_okin_nframe_hold import _client

ADDRESS = "AA:BB:CC:DD:EE:84"
KEYS = profiles.LEGGETT_PROFILES["prodigy4"].keys
HEAD = codec.frame(KEYS["head_up"]).hex()
FEET = codec.frame(KEYS["feet_up"]).hex()
CHORD = codec.frame(KEYS["head_up"] | KEYS["feet_up"]).hex()
ZERO = codec.STOP.hex()
CU170_STOP = codec.frame(KEYS["cu170_stop"]).hex()

Runtime = tuple[HomeAssistant, AdjustableBedCoordinator, list[str]]


@pytest.fixture
async def make_runtime(hass: HomeAssistant) -> AsyncIterator[Callable[[str], Runtime]]:
    coordinators: list[AdjustableBedCoordinator] = []
    with ExitStack() as stack:

        def build(app_profile: str) -> Runtime:
            entry = MockConfigEntry(
                domain=DOMAIN,
                title="Okin concurrent bed",
                unique_id=ADDRESS,
                data={
                    CONF_ADDRESS: ADDRESS,
                    CONF_NAME: "Okin concurrent bed",
                    CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_DISCONNECT_AFTER_COMMAND: False,
                },
            )
            entry.add_to_hass(hass)
            coordinator = AdjustableBedCoordinator(hass, entry)
            frames: list[str] = []
            coordinator._client = _client(frames)  # type: ignore[assignment]
            coordinator._controller = LeggettOkinController(coordinator, app_profile=app_profile)
            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
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
            coordinators.append(coordinator)
            return hass, coordinator, frames

        await async_register_services(hass)
        yield build
        for coordinator in coordinators:
            await coordinator.async_shutdown()


@pytest.fixture
async def clock(make_runtime) -> AsyncIterator[Any]:
    """Virtual time for the test body, after Home Assistant and the beds are set up."""
    with virtual_clock() as clock:
        yield clock


async def _move(
    hass: HomeAssistant,
    motor: str,
    duration_ms: int,
    *,
    generation: int | None = None,
) -> None:
    data: dict[str, object] = {
        "device_id": ["bed"],
        "motor": motor,
        "direction": "up",
        "duration_ms": duration_ms,
    }
    if generation is not None:
        data |= {"hold_owner": f"card-{motor}", "hold_generation": generation}
    await hass.services.async_call(DOMAIN, "timed_move", data, blocking=True)


async def _until(frames: list[str], frame: str) -> None:
    async with asyncio.timeout(2):
        while frame not in frames:
            await asyncio.sleep(0.005)


def _released(frames: list[str], *, stop: bool = False) -> list[str]:
    """Return the motion before the release; after it only release frames follow."""
    released = {ZERO, CU170_STOP} if stop else {ZERO}
    first = next(index for index, frame in enumerate(frames) if frame in released)
    assert set(frames[first:]) <= released
    assert frames[first:].count(ZERO) >= profiles.LEGGETT_HOLD.releases
    return frames[:first]


def test_composed_frames_are_frozen() -> None:
    assert CHORD in COMPOSED_FRAMES["prodigy4"]
    assert {HEAD, FEET, ZERO} <= FROZEN_FRAMES["prodigy4"]


async def test_both_motors_progress_in_one_window(make_runtime, clock) -> None:
    hass, coordinator, frames = make_runtime("prodigy4")
    head = asyncio.create_task(_move(hass, "head", 700))
    await _until(frames, HEAD)
    await asyncio.wait_for(_move(hass, "feet", 300), 2)
    # Feet ended first: the stream still carries head alone.
    assert not head.done()
    await asyncio.wait_for(head, 3)

    motion = _released(frames)
    chords = [index for index, frame in enumerate(motion) if frame == CHORD]
    assert len(chords) >= 2
    # Head streamed before, during and after the chord; feet only inside it.
    assert set(motion) == {HEAD, CHORD}
    assert motion[0] == HEAD and motion[-1] == HEAD
    assert set(motion[chords[0] : chords[-1] + 1]) == {CHORD}
    scheduler = coordinator._command_scheduler
    async with asyncio.timeout(1):
        while not scheduler.recent_records:
            await asyncio.sleep(0.001)
    assert scheduler.recent_records[-1].kind is CommandKind.STREAM


async def test_replacing_one_member_leaves_the_other(make_runtime, clock) -> None:
    hass, coordinator, frames = make_runtime("prodigy4")
    head = asyncio.create_task(_move(hass, "head", 900))
    await _until(frames, HEAD)
    feet = asyncio.create_task(_move(hass, "feet", 2000))
    await _until(frames, CHORD)
    # A new feet move replaces the running one; head keeps moving throughout.
    await asyncio.wait_for(_move(hass, "feet", 200), 2)
    await asyncio.wait_for(feet, 1)
    assert not head.done()
    await asyncio.wait_for(head, 3)
    motion = _released(frames)
    # Head's key never drops: every frame until the release carries it.
    assert set(motion) == {HEAD, CHORD}
    chords = [index for index, frame in enumerate(motion) if frame == CHORD]
    # The replaced feet gets its own cleanup (one head-only frame), then the
    # replacement's first tick brings feet back.
    assert motion[chords[0] : chords[-1] + 1].count(HEAD) == 1


async def test_motor_stop_ends_only_its_member(make_runtime, clock) -> None:
    hass, coordinator, frames = make_runtime("prodigy4")
    head = asyncio.create_task(_move(hass, "head", 600))
    await _until(frames, HEAD)
    feet = asyncio.create_task(_move(hass, "feet", 5000))
    await _until(frames, CHORD)
    assert coordinator.stop_stream_member("motor:feet")
    await asyncio.wait_for(feet, 1)
    count = len(frames)
    await asyncio.sleep(0.15)
    # The next frame dropped feet's bit; head streams on, with no release yet.
    assert frames[count - 1 :] and set(frames[count:]) == {HEAD}
    await asyncio.wait_for(head, 3)
    assert set(_released(frames)) == {HEAD, CHORD}


async def test_stop_during_interleaving_ends_every_member(make_runtime, clock) -> None:
    hass, coordinator, frames = make_runtime("prodigy4")
    head = asyncio.create_task(_move(hass, "head", 5000, generation=1))
    await _until(frames, HEAD)
    feet = asyncio.create_task(_move(hass, "feet", 5000))
    await _until(frames, CHORD)
    await coordinator.async_stop_command()
    await asyncio.wait_for(asyncio.gather(head, feet), 2)
    assert set(_released(frames, stop=True)) == {HEAD, CHORD}
    count = len(frames)
    await asyncio.sleep(0.15)
    assert frames[count:] == []


async def test_controller_without_concurrency_stays_serialized(make_runtime, clock) -> None:
    hass, coordinator, frames = make_runtime("prodigy2")
    keys = profiles.LEGGETT_PROFILES["prodigy2"].keys
    head = asyncio.create_task(_move(hass, "head", 300))
    await _until(frames, codec.frame(keys["head_up"]).hex())
    await asyncio.wait_for(_move(hass, "feet", 200), 3)
    await asyncio.wait_for(head, 3)
    composed = codec.frame(keys["head_up"] | keys["feet_up"]).hex()
    assert composed not in frames
    assert coordinator.stream_resources() is None
    assert all(
        record.kind is not CommandKind.STREAM
        for record in coordinator._command_scheduler.recent_records
    )


async def test_each_member_feeds_the_estimate_with_its_own_duration(
    make_runtime, clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Members ending at different moments each record their own travel (#601)."""
    # Serial moves are timed on the estimator's clock: make it the virtual one.
    monkeypatch.setattr(pe, "_clock", clock.time)
    hass, coordinator, frames = make_runtime("prodigy4")
    entry_id = coordinator.entry.entry_id
    manager = await pe.async_setup_position_estimates(hass, entry_id, ((ADDRESS, None),))
    bed = manager.beds[ADDRESS]
    bed.configure({"head": (10.0, 10.0), "feet": (10.0, 10.0)})
    groups = property(lambda _self: {"head": ("head",), "feet": ("feet",)})

    def travel(motor: str) -> float:
        percent = bed.motors[motor].percent
        assert percent is not None
        return percent / 100 * 10.0

    try:
        with patch.object(LeggettOkinController, "estimated_position_motor_groups", groups):
            # The serialized baseline: one motor at a time.
            bed.set_reference()
            await _move(hass, "head", 800)
            serial_head = travel("head")
            frames.clear()
            bed.set_reference()
            await _move(hass, "feet", 300)
            serial_feet = travel("feet")

            frames.clear()
            bed.set_reference()
            head = asyncio.create_task(_move(hass, "head", 800))
            await _until(frames, HEAD)
            await asyncio.wait_for(_move(hass, "feet", 300), 2)
            feet_done = travel("feet")
            # Feet's move ended with its own reduced frame, while head moves on.
            assert not head.done()
            assert bed.motors["head"].moves_since_reference == 0
            await asyncio.wait_for(head, 3)

            assert bed.motors["head"].moves_since_reference == 1
            assert bed.motors["feet"].moves_since_reference == 1
            assert (serial_head, serial_feet) == pytest.approx((0.8, 0.3))
            # Each member's travel equals a serialized move of the same length,
            # although feet ended while head was still moving.
            assert feet_done == pytest.approx(serial_feet)
            assert travel("head") == pytest.approx(serial_head)
    finally:
        await pe.async_unload_position_estimates(hass, entry_id)


async def test_slow_writes_keep_the_start_to_start_cadence(make_runtime, clock) -> None:
    """A proxy's write time is absorbed, as wall-clock pacing does for serial moves.

    The stream's fixed-rate ticks (#795) keep CU170 inside its watchdog.
    """
    hass, coordinator, frames = make_runtime("prodigy4")
    loop = asyncio.get_running_loop()
    starts: list[float] = []
    write = coordinator.client.write_gatt_char

    async def slow(characteristic, payload, **kwargs) -> None:
        starts.append(loop.time())
        await asyncio.sleep(0.06)
        await write(characteristic, payload, **kwargs)

    coordinator.client.write_gatt_char = slow
    await asyncio.wait_for(_move(hass, "head", 600), 3)
    held = [start for start, frame in zip(starts, frames, strict=True) if frame == HEAD]
    gaps = [b - a for a, b in zip(held, held[1:], strict=False)]
    assert len(gaps) >= 4
    # Fixed-rate ticks: 100 ms apart, not 100 ms after each 60 ms write.
    assert all(gap == pytest.approx(0.1, abs=1e-6) for gap in gaps)


async def test_a_newcomer_starts_with_a_tick_not_a_cleanup_frame(
    make_runtime, clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member joining just before another ends is introduced by a timed tick.

    With slow writes, feet joins while head's tick is on the wire, and head
    expires before feet's first tick. Head's reduced frame must not start feet
    early, or feet would move before the stream starts timing it.
    """
    monkeypatch.setattr(pe, "_clock", clock.time)
    hass, coordinator, frames = make_runtime("prodigy4")
    loop = asyncio.get_running_loop()
    written: list[tuple[float, str]] = []
    write = coordinator.client.write_gatt_char

    async def slow(characteristic, payload, **kwargs) -> None:
        written.append((loop.time(), bytes(payload).hex()))
        await asyncio.sleep(0.06)
        await write(characteristic, payload, **kwargs)

    coordinator.client.write_gatt_char = slow
    entry_id = coordinator.entry.entry_id
    manager = await pe.async_setup_position_estimates(hass, entry_id, ((ADDRESS, None),))
    bed = manager.beds[ADDRESS]
    bed.configure({"head": (10.0, 10.0), "feet": (10.0, 10.0)})
    bed.set_reference()
    groups = property(lambda _self: {"head": ("head",), "feet": ("feet",)})
    try:
        with patch.object(LeggettOkinController, "estimated_position_motor_groups", groups):
            head = asyncio.create_task(_move(hass, "head", 140))
            await asyncio.sleep(0.12)
            await asyncio.wait_for(_move(hass, "feet", 300), 2)
            await asyncio.wait_for(head, 2)
        first_feet = next(at for at, frame in written if frame in (FEET, CHORD))
        # Head's reduced frame carries no started member: the zero word. The
        # release that ends feet is the zero burst after feet's frames.
        release = next(at for at, frame in written if frame == ZERO and at > first_feet)
        feet_percent = bed.motors["feet"].percent
        assert feet_percent is not None
        # Feet moves from its first frame to its release, exactly its 300 ms,
        # and the estimate records that same span.
        assert release - first_feet == pytest.approx(0.3)
        assert feet_percent / 100 * 10.0 == pytest.approx(0.3)
    finally:
        await pe.async_unload_position_estimates(hass, entry_id)
