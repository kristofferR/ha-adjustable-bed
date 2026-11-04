"""Svane Remote head and feet together on the merged stream (#516).

P1 refreshes each axis's own direction role and releases one role; P2 sends one
mask, drops a released axis from it and ends with its global STOP. The real
controller runs through the coordinator's scheduler and the services.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.svane import FEET, HEAD, OLD, SvaneController
from custom_components.adjustable_bed.command_scheduler import CommandKind
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from tests.test_svane import written
from tests.test_svane_artifact_vectors import ROWS
from tests.test_svane_light_timed_host import runtime  # noqa: F401

FROZEN = {(row[5], row[6], row[4]) for row in ROWS}
UP = "000001ac-0000-1000-8000-00805f9b34fb"
OLD_CHAR = "00001111-0000-1000-8000-00805f9b34fb"
P1_HEAD = (HEAD, UP, "0100")
P1_FEET = (FEET, UP, "0100")
P1_HEAD_RELEASE = (HEAD, UP, "0000")
P1_FEET_RELEASE = (FEET, UP, "0000")
P2_HEAD = (OLD, OLD_CHAR, "100100000000")
P2_BOTH = (OLD, OLD_CHAR, "101100000000")
P2_STOP = (OLD, OLD_CHAR, "100000000000")

profiles = pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)


async def _move(hass, motor: str, duration_ms: int) -> None:
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(runtime_coordinator(hass), SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {"device_id": "bed", "motor": motor, "direction": "up", "duration_ms": duration_ms},
            blocking=True,
        )


def runtime_coordinator(hass):
    return hass.data["svane_test_coordinator"]


@pytest.fixture
def bed(hass, runtime):  # noqa: F811
    coordinator, controller = runtime
    hass.data["svane_test_coordinator"] = coordinator
    return hass, coordinator, controller


async def _until(controller: SvaneController, frame: tuple[str, str, str]) -> None:
    async with asyncio.timeout(2):
        while frame not in written(controller):
            await asyncio.sleep(0.005)


def _frames(controller: SvaneController) -> list[tuple[str, str, str]]:
    frames = written(controller)
    assert set(frames) <= FROZEN, set(frames) - FROZEN
    return frames


@profiles
async def test_head_and_feet_move_in_one_window(bed) -> None:
    hass, coordinator, controller = bed
    head = asyncio.create_task(_move(hass, "back", 900))
    await _until(controller, P1_HEAD if controller.profile == "multi" else P2_HEAD)
    await asyncio.wait_for(_move(hass, "legs", 400), 2)
    # Feet ended first; head is still moving.
    assert not head.done()
    await asyncio.wait_for(head, 3)
    frames = _frames(controller)
    if controller.profile == "multi":
        feet_release = frames.index(P1_FEET_RELEASE)
        # Feet refreshed between head refreshes, then released alone.
        assert P1_FEET in frames[:feet_release]
        assert P1_HEAD in frames[feet_release:]
        assert frames[-1] == P1_HEAD_RELEASE
        assert frames.count(P1_FEET_RELEASE) == frames.count(P1_HEAD_RELEASE) == 1
    else:
        first_both, last_both = frames.index(P2_BOTH), len(frames) - frames[::-1].index(P2_BOTH)
        assert set(frames[first_both:last_both]) == {P2_BOTH}
        # The mask drops feet; no STOP until head ends.
        assert frames[last_both] == P2_HEAD
        assert frames.index(P2_STOP) == len(frames) - 1
    scheduler = coordinator._command_scheduler
    async with asyncio.timeout(1):
        while not scheduler.recent_records:
            await asyncio.sleep(0.001)
    assert scheduler.recent_records[-1].kind is CommandKind.STREAM


@profiles
async def test_release_axis_ends_only_that_axis(bed) -> None:
    hass, coordinator, controller = bed
    head = asyncio.create_task(_move(hass, "back", 700))
    feet = asyncio.create_task(_move(hass, "legs", 5000))
    await _until(controller, P1_FEET if controller.profile == "multi" else P2_BOTH)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN, "svane_release_axis", {"device_id": "bed", "motor": "feet"}, blocking=True
        )
    await asyncio.wait_for(feet, 1)
    count = len(written(controller))
    await asyncio.sleep(0.25)
    assert not head.done()
    later = set(written(controller)[count:])
    assert later == ({P1_HEAD} if controller.profile == "multi" else {P2_HEAD})
    await asyncio.wait_for(head, 3)
    assert P1_FEET_RELEASE in _frames(controller) or controller.profile == "jmc"


@profiles
async def test_stop_during_interleaving_releases_every_axis(bed) -> None:
    hass, coordinator, controller = bed
    moves = asyncio.gather(_move(hass, "back", 5000), _move(hass, "legs", 5000))
    await _until(controller, P1_FEET if controller.profile == "multi" else P2_BOTH)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)
    await asyncio.wait_for(moves, 2)
    frames = _frames(controller)
    if controller.profile == "multi":
        assert {P1_HEAD_RELEASE, P1_FEET_RELEASE} <= set(frames[-2:] + frames[-3:])
        last_move = max(i for i, frame in enumerate(frames) if frame[2] == "0100")
        assert all(frame[2] == "0000" for frame in frames[last_move + 1 :])
    else:
        assert frames[-1] == P2_STOP
    assert not controller._started
    count = len(written(controller))
    await asyncio.sleep(0.25)
    assert written(controller)[count:] == []


@profiles
async def test_each_axis_feeds_the_estimate_with_its_own_duration(bed) -> None:
    hass, coordinator, controller = bed
    entry_id = coordinator.entry.entry_id
    manager = await pe.async_setup_position_estimates(
        hass, entry_id, ((coordinator.address, None),)
    )
    estimate = manager.beds[coordinator.address.upper()]
    estimate.configure({"back": (10.0, 10.0), "legs": (10.0, 10.0)})
    estimate.set_reference()
    groups = property(lambda _self: {"back": ("back",), "legs": ("legs",)})

    def travel(motor: str) -> float:
        percent = estimate.motors[motor].percent
        assert percent is not None
        return percent / 100 * 10.0

    try:
        with patch.object(SvaneController, "estimated_position_motor_groups", groups):
            head = asyncio.create_task(_move(hass, "back", 900))
            await _until(controller, P1_HEAD if controller.profile == "multi" else P2_HEAD)
            await asyncio.wait_for(_move(hass, "legs", 400), 2)
            legs_done = travel("legs")
            assert estimate.motors["back"].moves_since_reference == 0
            await asyncio.wait_for(head, 3)
        # Feet starts with its first write, 100 ms after it joins, as the app
        # sleeps before feet; a 400 ms move then drives it about 300 ms.
        assert 0.25 <= legs_done <= 0.45
        assert 0.85 <= travel("back") <= 1.05
        assert estimate.motors["legs"].moves_since_reference == 1
        assert estimate.motors["back"].moves_since_reference == 1
    finally:
        await pe.async_unload_position_estimates(hass, entry_id)


@profiles
async def test_head_joining_during_the_feet_wait_is_written_at_once(bed) -> None:
    """A head press is never left waiting for its turn while its budget runs."""
    hass, coordinator, controller = bed
    feet = asyncio.create_task(_move(hass, "legs", 600))
    await asyncio.sleep(0.02)
    assert not written(controller)  # feet waits 100 ms before its first write
    await asyncio.wait_for(_move(hass, "back", 100), 2)
    head_frame = P1_HEAD if controller.profile == "multi" else (OLD, OLD_CHAR, "101100000000")
    assert head_frame in _frames(controller)
    await asyncio.wait_for(feet, 3)


@profiles
async def test_axes_keep_the_app_pass_spacing_when_one_ends(bed) -> None:
    """Membership changes never squeeze a refresh closer than the app's 100 ms."""
    hass, coordinator, controller = bed
    loop = asyncio.get_running_loop()
    times: list[tuple[float, tuple[str, str, str]]] = []
    write = controller.client.write_gatt_char.side_effect

    async def timed(role, payload, **kwargs):
        frame = (next(s.uuid for s in controller.client.services if role in s.characteristics),
                 role.uuid, bytes(payload).hex())
        if frame[2] not in ("0000", "100000000000"):
            times.append((loop.time(), frame))
        if write is not None:
            await write(role, payload, **kwargs)

    controller.client.write_gatt_char.side_effect = timed
    feet = asyncio.create_task(_move(hass, "legs", 900))
    await asyncio.sleep(0.15)
    await asyncio.wait_for(_move(hass, "back", 300), 2)
    await asyncio.wait_for(feet, 3)
    def carries_head(frame: tuple[str, str, str]) -> bool:
        if frame[0] == OLD:
            return bool(bytes.fromhex(frame[2])[1] & 0x0F)
        return frame[0] == HEAD

    # The head press itself is written at once; every later refresh is paced.
    first_head = next(i for i, (_, frame) in enumerate(times) if carries_head(frame))
    gaps = [
        (b - a, i + 1)
        for i, ((a, _), (b, _)) in enumerate(zip(times, times[1:], strict=False))
        if i + 1 != first_head
    ]
    assert gaps and min(gap for gap, _ in gaps) >= 0.09
    feet_times = [t for t, frame in times if frame in (P1_FEET, (OLD, OLD_CHAR, "101000000000"))]
    # Feet alone refreshes every 200 ms, after the head has gone too.
    assert feet_times[-1] - feet_times[-2] >= 0.19


@profiles
async def test_release_during_preflight_restores_the_idle_disconnect(bed) -> None:
    """A release that arrives while preflight holds the link admits no motion,
    and the link still gets its normal idle disconnect."""
    from custom_components.adjustable_bed.services import _get_controller_for_service

    hass, coordinator, controller = bed

    async def live(target):
        result = await _get_controller_for_service(target)
        controller.request_svane_axis_release("head")
        return result

    ensure = AsyncMock(return_value=True)
    with (
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
        patch.object(coordinator, "async_ensure_connected", ensure),
    ):
        await asyncio.wait_for(_move(hass, "back", 300), 2)
    assert not any(
        frame[2] == "0100" or frame[2].startswith("1001") for frame in written(controller)
    )
    ensure.assert_awaited_with(reset_timer=True)
