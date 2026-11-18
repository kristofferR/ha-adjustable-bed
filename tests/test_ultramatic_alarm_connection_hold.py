"""Whole-call DAC connection ownership for the registered alarm action."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profiles import ultramatic as app
from tests.hold_lease_wire import virtual_clock
from tests.test_ultramatic_review_changes import native_pair
from tests.test_ultramatic_runtime import connected, runtime, writes  # noqa: F401 - pytest fixture

SET = {"operation": "set", "time": "21:09:00", "days": 2, "wake": "zero_g", "enabled": False}


@asynccontextmanager
async def receivers(runtime, count):  # noqa: F811 - pytest fixture data
    hass, first, client = runtime
    members = [(first, client)]
    try:
        for index in range(1, count):
            members.append(
                await connected(
                    hass,
                    address=f"AA:BB:CC:DD:EE:{0x76 + index:02X}",
                    selector=1 if index % 2 else 2,
                )
            )
        with ExitStack() as mocks:
            for coordinator, _client in members:
                coordinator._disconnect_after_command = True
                if coordinator is not first:
                    mocks.enter_context(
                        patch.object(
                            coordinator, "async_ensure_connected", AsyncMock(return_value=True)
                        )
                    )
                    mocks.enter_context(
                        patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
                    )
            yield hass, members
    finally:
        for coordinator, _client in reversed(members[1:]):
            await coordinator.async_shutdown()


def concurrent_pair(hass, left, right, suffix):
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": f"ultramatic-hold-{suffix}"})
    entry.add_to_hass(hass)
    return PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )


async def set_alarm(hass):
    await hass.services.async_call(
        DOMAIN, "ultramatic_alarm", {"device_id": ["selected"], **SET}, blocking=True
    )


def expected(coordinator):
    return [
        bytes.fromhex("0705020221090000") + bytes([app.SELECTORS[coordinator.controller._side()]])
    ] * 2 + [app.QUERY_ALARM] * 3


def restored(hass, members):
    for coordinator, _client in members:
        assert coordinator._command_connection_holds == 0
        if coordinator.is_connected:
            assert coordinator._disconnect_timer is not None
            assert coordinator._disconnect_timer.when() - hass.loop.time() == pytest.approx(
                1, abs=0.01
            )


@pytest.mark.parametrize("layout", ["three-standalone", "two-pairs-and-standalone"])
async def test_registered_alarm_retains_early_dac_receivers_until_whole_selection_finishes(
    runtime,  # noqa: F811 - pytest fixture
    layout,
):
    async with receivers(runtime, 3 if layout == "three-standalone" else 5) as (hass, members):
        coordinators = [coordinator for coordinator, _client in members]
        targets = [(coordinator, "both") for coordinator in coordinators]
        if layout == "two-pairs-and-standalone":
            targets = [
                (concurrent_pair(hass, coordinators[0], coordinators[1], "first"), "both"),
                (coordinators[2], "both"),
                (concurrent_pair(hass, coordinators[3], coordinators[4], "last"), "both"),
            ]
        frames = [expected(coordinator) for coordinator in coordinators]
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=(targets, []),
            ),
            virtual_clock() as clock,
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            await set_alarm(hass)
            assert (
                clock.elapsed >= 2.09
            )  # First group completed at700ms; its old1s deadline passed.
            assert all(coordinator.is_connected for coordinator in coordinators)
            assert [writes(client) for _coordinator, client in members] == frames
            restored(hass, members)


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "native-both-deduplicated"])
async def test_alarm_live_preflight_failure_restores_holds_without_any_command_write(
    runtime,  # noqa: F811 - pytest fixture
    native,
):
    async with receivers(runtime, 3) as (hass, members):
        first, second, last = [coordinator for coordinator, _client in members]
        targets = [
            (native_pair(hass, first) if native else first, "both"),
            (second, "both"),
            (last, "both"),
        ]

        async def unavailable(reset_timer=True):
            assert all(
                coordinator._command_connection_holds == 1 for coordinator, _client in members
            )
            raise RuntimeError("injected alarm readiness failure")

        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=(targets, []),
            ),
            patch.object(last, "async_ensure_connected", side_effect=unavailable),
            virtual_clock(),
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            with pytest.raises(RuntimeError, match="injected alarm readiness failure"):
                await set_alarm(hass)
            assert all(writes(client) == [] for _coordinator, client in members)
            restored(hass, members)


async def test_alarm_late_write_failure_releases_all_earlier_dac_connection_holds(
    runtime,  # noqa: F811 - pytest fixture
):
    async with receivers(runtime, 3) as (hass, members):
        targets = [(coordinator, "both") for coordinator, _client in members]
        first_frames, second_frames = expected(members[0][0]), expected(members[1][0])
        members[2][1].write_gatt_char.side_effect = RuntimeError("injected alarm write failure")
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=(targets, []),
            ),
            virtual_clock(),
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            with pytest.raises(RuntimeError, match="injected alarm write failure"):
                await set_alarm(hass)
            assert writes(members[0][1]) == first_frames
            assert writes(members[1][1]) == second_frames
            assert len(writes(members[2][1])) == 1
            restored(hass, members)


async def test_stop_on_completed_alarm_target_still_blocks_later_receiver_writes(
    runtime,  # noqa: F811 - pytest fixture
):
    async with receivers(runtime, 3) as (hass, members):
        first, second, last = [coordinator for coordinator, _client in members]
        targets = [(coordinator, "both") for coordinator, _client in members]
        original = last.controller.set_alarm

        async def stopped(plan, **kwargs):
            assert first._command_connection_holds == 1 and first.is_connected
            await first.async_stop_command()
            await original(plan, **kwargs)

        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=(targets, []),
            ),
            patch.object(last.controller, "set_alarm", side_effect=stopped),
            virtual_clock(),
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            with pytest.raises(ServiceValidationError, match="stopped during admission"):
                await set_alarm(hass)
            assert writes(members[0][1])[-1] == app.control("STOP")
            assert len(writes(members[1][1])) == 5
            assert writes(members[2][1]) == []
            restored(hass, members)


async def test_public_alarm_cancellation_restores_earlier_and_pending_connection_holds(
    runtime,  # noqa: F811 - pytest fixture
):
    async with receivers(runtime, 3) as (hass, members):
        targets = [(coordinator, "both") for coordinator, _client in members]
        arrived, release = asyncio.Event(), asyncio.Event()

        async def waiting(_characteristic, _frame, **_kwargs):
            arrived.set()
            await release.wait()

        members[2][1].write_gatt_char.side_effect = waiting
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=(targets, []),
            ),
            virtual_clock() as clock,
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            task = asyncio.create_task(set_alarm(hass))
            pending_write = asyncio.create_task(arrived.wait())
            try:
                done, _pending = await asyncio.wait(
                    {task, pending_write}, return_when=asyncio.FIRST_COMPLETED
                )
                if task in done:
                    await task
                    pytest.fail("Alarm call finished before pending receiver write")
                assert clock.elapsed >= 1.39
                assert all(coordinator.is_connected for coordinator, _client in members)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                restored(hass, members)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                if not pending_write.done():
                    pending_write.cancel()
                await asyncio.gather(task, pending_write, return_exceptions=True)
