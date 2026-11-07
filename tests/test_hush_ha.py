"""Hush real coordinator, native paired devices, services and entity contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_ensure_paired_device_registry, button, cover
from custom_components.adjustable_bed.beds.casper_base.protocol import Request
from custom_components.adjustable_bed.beds.casper_base.services import (
    async_register_casper_base_services,
)
from custom_components.adjustable_bed.beds.casper_sleep.protocol import envelope
from custom_components.adjustable_bed.beds.hush_base.controller import HushBaseController
from custom_components.adjustable_bed.beds.hush_sleep.controller import HushSleepController
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from tests.test_hush_base import hush


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    real = asyncio.sleep

    async def tick(_):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", tick)


def runtime(hass, model="hushs575sh", kind=None):
    _, mock = hush(model, kind=kind)
    bed_type = "hush_sleep_" + kind if kind else "hush_base"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hush",
        unique_id="AA:BB:CC:DD:EE:FF",
        version=4,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Hush",
            "bed_type": bed_type,
            "protocol_variant": model,
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = mock.client
    ctrl = (
        HushSleepController(coordinator, kind=kind)
        if kind
        else HushBaseController(coordinator, product=model)
    )
    coordinator._controller = ctrl
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return entry, coordinator, ctrl


@pytest.mark.parametrize("kind", [None, "mm", "sxb"])
async def test_factory_notification_channel_and_entities(hass, kind):
    entry, c, ctrl = runtime(hass, kind=kind)
    actual = await create_controller(
        c, entry.data["bed_type"], protocol_variant=entry.data["protocol_variant"], client=c.client
    )
    assert type(actual) is type(ctrl)
    await c.async_start_notify()
    assert ctrl._write_char is not None
    assert ctrl.requires_notification_channel
    assert not ctrl.supports_casper_base_controls
    assert ctrl.supports_hush_base_controls
    await ctrl.stop_notify()


async def test_pair_entity_controls_and_release_keep_their_side(hass, enable_custom_integrations):
    entry, inner, controller = runtime(hass)
    await controller.start_notify()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "pair_sides" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pair_sides"}
    )
    with (
        patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=True)),
        patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"confirm": True}
        )
        await hass.async_block_till_done()
    paired = SingleAddressPairedCoordinator(hass, entry, inner)
    hass.data[DOMAIN][entry.entry_id] = paired
    _async_ensure_paired_device_registry(hass, entry, paired)
    entities = []
    await cover.async_setup_entry(hass, entry, entities.extend)
    assert entities
    inner.client.write_gatt_char.reset_mock()
    entity = next(e for e in entities if e.unique_id.endswith("_left"))
    with (
        patch.object(inner, "async_connect", AsyncMock(return_value=True)),
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_open_cover()
    packets = [bytes(call.args[1]) for call in inner.client.write_gatt_char.call_args_list]
    assert packets and all(p[2] == 0 for p in packets)
    assert packets[-1][3] == 0x6E
    await controller.stop_notify()
    inner._cancel_disconnect_timer()


async def test_service_preflight_and_public_buttons(hass):
    entry, c, controller = runtime(hass, "hushl400")
    await controller.start_notify()
    controller.events["light_available"] = {}
    async_register_casper_base_services(hass)
    # The public schema includes the typed Hush-only operations.
    assert hass.services.has_service(DOMAIN, "hush_base")
    entry.mock_state(hass, ConfigEntryState.LOADED)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, c.address)}
    )
    c.client.write_gatt_char.reset_mock()
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        await hass.services.async_call(
            DOMAIN,
            "hush_base",
            {"device_id": [device.id], "operation": "rgb_power", "enabled": True},
            blocking=True,
        )
    assert bytes(c.client.write_gatt_char.await_args.args[1]).hex() == "6e20090404010001a1"
    entities = []
    await button.async_setup_entry(hass, entry, entities.extend)
    assert any(e.translation_key == "hush_base_action" for e in entities)
    # Preflight capability is exposed separately from the Casper service.
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "hush_base", {"device_id": ["missing"], "operation": "rgb_power"}, blocking=True
        )
    c.client.write_gatt_char.reset_mock()
    entity = next(e for e in entities if e.translation_key == "hush_base_action")
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        await entity.async_press()
    assert c.client.write_gatt_char.await_count
    await controller.stop_notify()
    c._cancel_disconnect_timer()


async def test_ble_lock_checks_physical_client_after_wait(hass):
    _, c, controller = runtime(hass)
    await controller.start_notify()
    old = c.client
    old.write_gatt_char.reset_mock()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(
        controller._write_gatt_with_retry(
            controller.control_characteristic_uuid, b"\x24", expected_client=old
        )
    )
    await asyncio.sleep(0)
    c._client = MagicMock(is_connected=True)
    c._client.write_gatt_char = AsyncMock()
    controller.ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    old.write_gatt_char.assert_not_awaited()
    c._client.write_gatt_char.assert_not_awaited()


async def test_live_recovery_uses_each_replacement_controller(hass):
    _, coordinator, initial = runtime(hass, kind="mm")
    await initial.start_notify()
    assert coordinator._offline_controller is initial
    assert not initial.requests_connection_recovery
    initial.on_disconnect()
    for _ in range(3):
        _, mock = hush(kind="mm")
        coordinator._client = mock.client
        replacement = HushSleepController(coordinator, kind="mm")
        coordinator._controller = replacement
        replacement.restore_persisted_app_state({"live_requested": True})

        async def hold_poll():
            await asyncio.Event().wait()

        with patch.object(replacement, "_poll_live", hold_poll):
            await replacement.start_notify()
        assert coordinator._offline_controller is replacement
        coordinator._cache_persistent_connection_policy()
        client = coordinator.client
        client.is_connected = False
        coordinator._on_disconnect(client)
        assert coordinator.capability_controller is replacement
        assert coordinator.capability_controller.requests_connection_recovery
        assert coordinator._reconnect_timer is not None
        coordinator._cancel_auto_reconnect()
    coordinator._cancel_disconnect_timer()
    await hass.async_block_till_done()


@pytest.mark.parametrize("failure", [TimeoutError, ValueError, ConnectionError])
async def test_live_monitoring_retries_a_failed_sample_until_explicit_stop(hass, failure):
    _, coordinator, controller = runtime(hass, kind="mm")
    await controller.start_notify()
    samples = 0
    recovered = asyncio.Event()

    async def sample():
        nonlocal samples
        samples += 1
        if samples == 1:
            raise failure("sample unavailable")
        assert controller._live_requested
        assert controller._poll is not None
        recovered.set()

    with (
        patch.object(controller, "_query_live", sample),
        patch.object(coordinator, "async_connect", AsyncMock(return_value=True)),
    ):
        await controller.async_execute_casper_base_request(Request("sensor_live"))
        poll = controller._poll
        assert poll is not None
        async with asyncio.timeout(1):
            await recovered.wait()
        assert samples >= 2
        assert controller.requests_connection_recovery
        assert controller.requires_persistent_connection
        await controller.async_execute_casper_base_request(Request("sensor_stop"))
        await asyncio.gather(poll, return_exceptions=True)
    assert not controller.requests_connection_recovery
    assert controller._poll is None
    await controller.stop_notify()
    coordinator._cancel_disconnect_timer()


async def test_retained_notification_callbacks_cannot_overwrite_replacement_state(hass):
    _, coordinator, old = runtime(hass, model="hushl400")
    await old.start_notify()
    old_callback = coordinator.client.start_notify.await_args.args[1]
    old_sender = old._notify_char
    old.on_disconnect()
    replacement = HushBaseController(coordinator, product="hushl400")
    coordinator._controller = replacement
    await replacement.start_notify()
    current_callback = coordinator.client.start_notify.await_args.args[1]
    current_callback(replacement._notify_char, bytearray.fromhex("6e16010186"))
    assert coordinator.controller_state["casper_base_events"] == {"music_available": {}}
    old_callback(old_sender, bytearray.fromhex("6e09010078"))
    old._on_notification(old_sender, bytearray.fromhex("6e09010078"))
    assert coordinator.controller_state["casper_base_events"] == {"music_available": {}}
    # A retained callback is stale even when the same instance/client subscribes again.
    replacement.on_disconnect()
    await replacement.start_notify()
    before = dict(replacement.events)
    current_callback(replacement._notify_char, bytearray.fromhex("6e09010078"))
    assert replacement.events == before
    await replacement.stop_notify()


@pytest.mark.parametrize("failure", ["short_sxb", "bleak_write"])
async def test_monitoring_recovers_through_actual_notify_and_write_paths(hass, failure):
    _, coordinator, controller = runtime(hass, kind="sxb" if failure == "short_sxb" else "mm")
    await controller.start_notify()
    last_request = None
    attempts = 0
    recovered = asyncio.Event()

    async def write(*_args, **_kwargs):
        nonlocal last_request, attempts
        pending = controller._pending
        if pending is last_request:
            return
        last_request = pending
        attempts += 1
        if attempts == 1 and failure == "bleak_write":
            raise BleakError("temporary GATT write failure")
        val = (
            {"L": [0], "R": []}
            if attempts == 1
            else {"L": [0, 1, 65, 12, 1], "R": []}
            if controller.kind == "sxb"
            else {"L": "1-1-65-12-1-0-0-0", "R": "1-1-60-11-1-0-0-0"}
        )
        raw = envelope({"id": attempts, "cmd": "q_realtime", "val": val}, attempts)
        controller._on_notification(controller._notify_char, bytearray(raw))
        if attempts >= 2:
            recovered.set()

    with (
        patch.object(coordinator, "async_connect", AsyncMock(return_value=True)),
        patch.object(coordinator.client, "write_gatt_char", AsyncMock(side_effect=write)),
    ):
        await controller.async_execute_casper_base_request(Request("sensor_live"))
        poll = controller._poll
        assert poll is not None
        async with asyncio.timeout(1):
            await recovered.wait()
        assert attempts >= 2
        assert controller.requests_connection_recovery
        assert controller.requires_persistent_connection
        assert coordinator.controller_state["casper_sleep_L_heart"] == "65"
        await controller.async_execute_casper_base_request(Request("sensor_stop"))
        await asyncio.gather(poll, return_exceptions=True)
    assert not controller.requests_connection_recovery
    assert controller._poll is None
    await controller.stop_notify()
    coordinator._cancel_disconnect_timer()
