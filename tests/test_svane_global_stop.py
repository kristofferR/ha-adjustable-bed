"""Proven P2 global STOP and the narrower P1 opaque-recall boundary."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import HEAD, OLD, OLD_CHAR, POSITION
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_svane import make_controller, written


@pytest.fixture
async def real_bed(hass, request):
    profile = request.param
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane",
        CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC if profile == "jmc" else SVANE_VARIANT_MULTI,
        CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(profile)
    coordinator._client = controller.client
    controller._coordinator = coordinator
    coordinator._controller = controller
    controller.session.multi_slots[1] = (b"opaque head", b"opaque feet")
    controller.session.multi_slots[2] = (b"other head", b"other feet")
    await async_register_services(hass)
    try:
        yield coordinator, controller
    finally:
        coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("real_bed", ["jmc"], indirect=True)
@pytest.mark.parametrize("slot", [1, 2])
async def test_registered_global_stop_during_validated_jmc_recall(hass, real_bed, slot):
    coordinator, controller = real_bed
    waiting = asyncio.Event()
    waits = []

    async def wait(seconds):
        waits.append(seconds)
        waiting.set()
        await coordinator.cancel_command.wait()
        return False

    controller._wait = wait
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        recall = asyncio.create_task(hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": "bed", "preset": slot}, blocking=True))
        try:
            async with asyncio.timeout(1):
                await waiting.wait()
                assert not controller._started
                await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)
                await asyncio.gather(recall, return_exceptions=True)
            assert waits == [1]
            assert written(controller) == [(OLD, OLD_CHAR, "100481388113" if slot == 1 else "100482738204"),
                                           (OLD, OLD_CHAR, "100000000000")]
            assert not controller._started
            assert not coordinator._command_lock.locked()
            assert not controller.ble_lock.locked()
        finally:
            recall.cancel()
            await asyncio.gather(recall, return_exceptions=True)


@pytest.mark.parametrize("real_bed", ["jmc"], indirect=True)
@pytest.mark.parametrize("slot", [1, 2])
async def test_completed_recall_has_no_appended_stop_but_later_public_stop_delivers(hass, real_bed, slot):
    coordinator, controller = real_bed
    controller._wait = AsyncMock(return_value=True)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "goto_preset", {"device_id": "bed", "preset": slot}, blocking=True)
        assert written(controller) == [(OLD, OLD_CHAR, "100481388113" if slot == 1 else "100482738204")]
        await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)
    assert written(controller)[-1] == (OLD, OLD_CHAR, "100000000000")
    controller._wait.assert_awaited_once_with(1)


@pytest.mark.parametrize("real_bed", ["multi"], indirect=True)
@pytest.mark.parametrize("slot", [1, 2])
async def test_p1_recall_cancel_skips_feet_without_inventing_absolute_stop(hass, real_bed, slot):
    coordinator, controller = real_bed
    waiting = asyncio.Event()

    async def wait(seconds):
        assert seconds == 1
        waiting.set()
        await coordinator.cancel_command.wait()
        return False

    controller._wait = wait
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        recall = asyncio.create_task(hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": "bed", "preset": slot}, blocking=True))
        try:
            async with asyncio.timeout(1):
                await waiting.wait()
                await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)
                await asyncio.gather(recall, return_exceptions=True)
            assert written(controller) == [(HEAD, POSITION, b"opaque head".hex() if slot == 1 else b"other head".hex())]
            assert not coordinator._command_lock.locked()
        finally:
            recall.cancel()
            await asyncio.gather(recall, return_exceptions=True)


@pytest.mark.parametrize("failure", ["write_error", "cancelled_write"])
async def test_untracked_jmc_stop_failure_retains_exact_role_for_retry(failure):
    controller = make_controller("jmc")
    error = BleakError("global STOP failed") if failure == "write_error" else asyncio.CancelledError()
    controller._coordinator.cancel_command.set()
    controller.client.write_gatt_char.side_effect = [error, None]
    with pytest.raises(type(error)):
        await controller.stop_all()
    assert controller._started == {(OLD, OLD_CHAR)}
    await controller.stop_all()
    assert written(controller) == [(OLD, OLD_CHAR, "100000000000")] * 2
    assert not controller._started


async def test_idle_notify_teardown_does_not_append_global_stop():
    controller = make_controller("jmc")
    await controller.stop_notify()
    assert written(controller) == []


@pytest.mark.parametrize("real_bed", ["jmc"], indirect=True)
async def test_admitted_stop_outlives_cancelled_caller_with_no_held_role(real_bed):
    coordinator, controller = real_bed
    writing, release = asyncio.Event(), asyncio.Event()

    async def write(role, packet, **kwargs):
        assert role.uuid == OLD_CHAR and packet == bytes.fromhex("100000000000")
        writing.set()
        await release.wait()

    controller.client.write_gatt_char.side_effect = write
    stop = asyncio.create_task(coordinator.async_stop_command())
    try:
        async with asyncio.timeout(1):
            await writing.wait()
            stop.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await stop
        assert written(controller) == [(OLD, OLD_CHAR, "100000000000")]
        assert not controller._started
        assert not coordinator._command_lock.locked()
    finally:
        release.set()
        stop.cancel()
        await asyncio.gather(stop, return_exceptions=True)
