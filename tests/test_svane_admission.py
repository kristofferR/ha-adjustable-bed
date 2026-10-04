"""Actual public release admission and disconnected timed-move boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.services import _get_controller_for_service
from tests.test_svane import written
from tests.test_svane_light_timed_host import runtime as svane_runtime
from tests.test_svane_services import target

runtime = svane_runtime


def hold_data(control="head_up"):
    return {"device_id": "bed", "control": control, "duration": 0.2}


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("endpoint", ["hold_control", "timed_move"])
async def test_registered_release_survives_scheduler_admission(hass, runtime, endpoint):
    coordinator, controller = runtime
    ready = asyncio.Event()
    await coordinator._command_lock.acquire()

    async def live(target):
        result = await _get_controller_for_service(target)
        ready.set()
        return result

    data = hold_data() if endpoint == "hold_control" else {
        "device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 200,
    }
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
    ):
        held = asyncio.create_task(hass.services.async_call(DOMAIN, endpoint, data, blocking=True))
        try:
            await ready.wait()
            assert not held.done() and not written(controller)
            await hass.services.async_call(DOMAIN, "svane_release_axis", {
                "device_id": "bed", "motor": "head",
            }, blocking=True)
            coordinator._command_lock.release()
            await held
            # Timed movement retains its normal finally STOP; no MOVE is admitted.
            assert all(p in ("0000", "100000000000") for _, _, p in written(controller))
            assert not controller._started
        finally:
            if coordinator._command_lock.locked():
                coordinator._command_lock.release()
            held.cancel()
            await asyncio.gather(held, return_exceptions=True)
            await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_release_during_later_target_preflight_suppresses_only_selected_axis(hass, profile):
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first, one = target(profile)
    second, two = target(profile)
    blocked, resume = asyncio.Event(), asyncio.Event()
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)

    one._motor_wait = two._motor_wait = advance

    async def live(target):
        if target is second and not resume.is_set():
            blocked.set()
            await resume.wait()
        return target.controller

    def resolve(hass, device_ids, side):
        return ([(first, SIDE_BOTH)] if device_ids == "first" else
                [(first, SIDE_BOTH), (second, SIDE_BOTH)]), []

    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", resolve),
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
        patch("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio),
    ):
        task = asyncio.create_task(hass.services.async_call(DOMAIN, "hold_control", {
            "device_id": ["first", "second"], "control": "head_up_feet_down", "duration": 0.2,
        }, blocking=True))
        try:
            await blocked.wait()
            await hass.services.async_call(DOMAIN, "svane_release_axis", {
                "device_id": "first", "motor": "head",
            }, blocking=True)
            resume.set()
            await task
            packets = written(one)
            assert packets
            assert all(p != "100100000000" and p != "102100000000" for _, _, p in packets)
            if profile == "multi":
                from custom_components.adjustable_bed.beds.svane import FEET
                assert all(service == FEET for service, _, _ in packets)
            else:
                assert packets[0][2] == "102000000000"
            assert written(two) and not one._started and not two._started
        finally:
            resume.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_idle_release_is_not_replayed_by_next_public_hold(hass, runtime):
    coordinator, controller = runtime

    async def stop_after_first(seconds):
        coordinator.cancel_command.set()

    controller._motor_wait = stop_after_first
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "svane_release_axis", {
            "device_id": "bed", "motor": "head",
        }, blocking=True)
        await hass.services.async_call(DOMAIN, "hold_control", hold_data(), blocking=True)
    assert written(controller)[0][2] == ("0100" if controller.profile == "multi" else "100100000000")
    assert not controller._started


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_offline_timed_move_reconnects_before_live_role_preflight(hass, runtime):
    coordinator, previous = runtime
    client = previous.client
    coordinator._client = coordinator._controller = None
    await coordinator.async_prime_offline_controller()
    offline = coordinator.capability_controller
    assert isinstance(offline, SvaneController) and offline.client is None
    live = SvaneController(coordinator, profile=offline.profile, session=offline.session)

    async def reconnect(**kwargs):
        coordinator._client, coordinator._controller = client, live
        return True

    async def finish_after_first(seconds):
        coordinator.cancel_command.set()

    live._motor_wait = finish_after_first
    coordinator.async_ensure_connected = AsyncMock(side_effect=reconnect)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 200,
        }, blocking=True)
    coordinator.async_ensure_connected.assert_awaited()
    assert written(live)[0][2] == ("0100" if live.profile == "multi" else "100100000000")
    assert not live._started
    await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("failure", ["missing", "readonly", "duplicate"])
async def test_later_timed_live_role_failure_prevents_every_target_motion(hass, failure):
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first, one = target("multi")
    second, two = target("jmc")
    one._coordinator.motor_pulse_count = two._coordinator.motor_pulse_count = 10
    one._coordinator.motor_pulse_delay_ms = two._coordinator.motor_pulse_delay_ms = 100
    from custom_components.adjustable_bed.beds.svane import OLD
    service = next(s for s in two.client.services if s.uuid == OLD)
    if failure == "missing":
        service.characteristics = []
    elif failure == "readonly":
        service.characteristics[0].properties = ["read"]
    else:
        service.characteristics.append(service.characteristics[0])
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], [])),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": ["first", "second"], "motor": "back", "direction": "up", "duration_ms": 200,
        }, blocking=True)
    one.client.write_gatt_char.assert_not_awaited()
    two.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_session_reconstruction_keeps_admitted_release_boundary(hass, runtime):
    coordinator, original = runtime
    ready, resume = asyncio.Event(), asyncio.Event()

    async def live(target):
        ready.set()
        await resume.wait()
        return target.controller

    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
    ):
        task = asyncio.create_task(hass.services.async_call(
            DOMAIN, "hold_control", hold_data(), blocking=True,
        ))
        try:
            await ready.wait()
            rebuilt = SvaneController(coordinator, profile=original.profile, session=original.session)
            coordinator._controller = rebuilt
            await hass.services.async_call(DOMAIN, "svane_release_axis", {
                "device_id": "bed", "motor": "head",
            }, blocking=True)
            resume.set()
            await task
            assert not written(rebuilt) and not rebuilt._started
        finally:
            resume.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("endpoint", ["hold_control", "timed_move"])
async def test_caller_cancel_during_later_preflight_restores_idle_without_motion(hass, endpoint):
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first, one = target("multi")
    second, two = target("jmc")
    for coordinator, controller in [(first, one), (second, two)]:
        coordinator.async_ensure_connected = AsyncMock(return_value=True)
        controller._coordinator.motor_pulse_count = 10
        controller._coordinator.motor_pulse_delay_ms = 100
    blocked = asyncio.Event()

    async def live(target):
        if target is second:
            blocked.set()
            await asyncio.Event().wait()
        return target.controller

    data = hold_data() if endpoint == "hold_control" else {
        "device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 200,
    }
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], [])),
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
    ):
        task = asyncio.create_task(hass.services.async_call(DOMAIN, endpoint, data, blocking=True))
        await blocked.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    one.client.write_gatt_char.assert_not_awaited()
    two.client.write_gatt_char.assert_not_awaited()
    first.async_ensure_connected.assert_awaited_with(reset_timer=True)
    second.async_ensure_connected.assert_awaited_with(reset_timer=True)


@pytest.mark.parametrize("endpoint", ["hold_control", "timed_move"])
async def test_later_session_replacement_aborts_all_targets_before_dispatch(hass, endpoint):
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first, one = target("multi")
    second, original = target("jmc")
    for controller in (one, original):
        controller._coordinator.motor_pulse_count = 10
        controller._coordinator.motor_pulse_delay_ms = 100
    replacement = SvaneController(original._coordinator, profile="jmc")

    async def live(target):
        if target is second:
            second.controller = replacement
        return target.controller

    data = hold_data() if endpoint == "hold_control" else {
        "device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 200,
    }
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], [])),
        patch("custom_components.adjustable_bed.services._get_controller_for_service", live),
        pytest.raises(ServiceValidationError, match="physical session changed"),
    ):
        await hass.services.async_call(DOMAIN, endpoint, data, blocking=True)
    one.client.write_gatt_char.assert_not_awaited()
    replacement.client.write_gatt_char.assert_not_awaited()
