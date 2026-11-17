"""S1–S3: real service reconnect/admission and retained light entity identities."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.goodvibe import services as configuration
from custom_components.adjustable_bed.beds.goodvibe.controller import (
    STATUS,
    GoodVibeController,
    Link,
)
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
    entity_runtimes,
)
from custom_components.adjustable_bed.paired_devices import async_register_children
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from custom_components.adjustable_bed.profiles.bobpowerbase import CATALOG
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from tests.test_bobpowerbase import fake_time as fake_time
from tests.test_bobpowerbase import runtime as base_runtime
from tests.test_entity_sweep import async_setup_platforms_and_sweep

LIGHT_REPLY = bytes.fromhex("6e0e00037f")


@pytest.fixture(autouse=True)
async def domain_bootstrap(hass, enable_custom_integrations):
    del enable_custom_integrations
    await async_setup_component(hass, "homeassistant", {})


def runtime(hass, **kwargs):
    coordinator = base_runtime(hass, **kwargs)
    client = coordinator.client

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return coordinator


def register(hass, coordinator):
    entry = coordinator.entry
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info,
    )
    if isinstance(coordinator, PairedBedCoordinator):
        async_register_children(hass, coordinator)
    return device.id


@pytest.fixture
async def disconnected_service(hass, mock_coordinator_connected, mock_bleak_client, mock_establish_connection, fake_time):
    del mock_coordinator_connected, fake_time
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bob", CONF_BED_TYPE: "bobpowerbase",
        CONF_PROTOCOL_VARIANT: "ultra_sh", CONF_PROFILE_ID: "bobpowerbase:ultra_sh",
        CONF_PRODUCT_TYPE: "standard", CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._post_connect_delay = 0
    coordinator._auto_reconnect_enabled = MagicMock(return_value=False)
    await coordinator.async_prime_offline_controller()
    device = register(hass, coordinator)
    client = mock_bleak_client
    route = codec.TRANSPORTS["w1"]
    tx = MagicMock(uuid=route.write_uuid, properties=["write"], handle=1, descriptors=[])
    rx = MagicMock(uuid=route.notify_uuid, properties=["notify"], handle=2, descriptors=[])
    client.services = [MagicMock(uuid=route.service_uuid, characteristics=[tx, rx])]
    callbacks = []
    reply = [True]

    async def notify(_characteristic, callback):
        callbacks.append(callback)

    async def write(_characteristic, packet, **_kwargs):
        if reply[0] and packet == codec.function(1, action="deviceFunctionItemCheckLight"):
            callbacks[-1](rx, bytearray(LIGHT_REPLY))

    async def disconnect():
        client.is_connected = False

    async def establish(*_args, **_kwargs):
        client.is_connected = True
        return client

    client.start_notify.side_effect = notify
    client.write_gatt_char.side_effect = write
    client.disconnect.side_effect = disconnect
    # The shared fixture already has a side_effect: replacing return_value would
    # not change the simulated connection or restore its connected flag.
    mock_establish_connection.side_effect = establish
    configuration.async_register_goodvibe_services(hass)
    try:
        yield coordinator, device, client, reply
    finally:
        await coordinator.async_shutdown()
        await entry._async_process_on_unload(hass)


@pytest.mark.parametrize("operation", ("sync", "alarms", "delete", "repeat", "light_color", "light_duration", "light_off"))
async def test_registered_service_from_offline_restore_uses_actual_connection(hass, disconnected_service, operation):
    coordinator, device, client, _reply = disconnected_service
    assert coordinator.controller is None and coordinator.capability_controller is not None
    fields = {
        "delete": {"alarm_id": 3},
        "repeat": {"alarm_id": 3, "action": "anti_snore", "datetime": "2026-11-17T07:30:00+00:00"},
        "light_color": {"rgb_color": [1, 2, 3]},
        "light_duration": {"seconds": 0},
    }.get(operation, {})
    await hass.services.async_call(DOMAIN, "bobpowerbase", {
        "device_id": device, "operation": operation, **fields,
    }, blocking=True)
    assert isinstance(coordinator.controller, GoodVibeController)
    frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert len(frames) == 5  # Three product probes, calendar sync, then this action.
    if operation == "light_duration":
        assert frames[-1].hex() == "6e0bffff77"
    elif operation == "light_color":
        assert frames[-1] == codec.rgb(1, 2, 3)


async def test_registered_light_action_reconnects_after_ordinary_idle(hass, disconnected_service):
    coordinator, device, client, _reply = disconnected_service
    await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": device, "operation": "light_off"}, blocking=True)
    original = coordinator.controller
    await coordinator.async_disconnect("idle")
    assert not coordinator.is_connected
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": device, "operation": "light_duration", "seconds": 300}, blocking=True)
    assert coordinator.controller is not original
    assert client.write_gatt_char.call_args.args[1].hex() == "6e0b012ca6"


async def test_restored_light_preferences_do_not_grant_a_missing_fresh_reply(hass, disconnected_service, monkeypatch):
    monkeypatch.setattr("custom_components.adjustable_bed.beds.goodvibe.controller.MENU_REPLY_TIMEOUT_S", 0)
    coordinator, device, client, reply = disconnected_service
    coordinator.capability_controller.restore_persisted_app_state({"light_duration": 300, "light_color": [1, 2, 3]})
    reply[0] = False
    with pytest.raises(ServiceValidationError, match="light menu"):
        await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": device, "operation": "light_color", "rgb_color": [1, 2, 3]}, blocking=True)
    assert len(client.write_gatt_char.await_args_list) == 4  # Startup only.
    assert not coordinator.controller.menu_available("light")


async def test_invalid_second_app_is_rejected_before_first_target_can_reconnect(hass, disconnected_service):
    _coordinator, first_device, client, _reply = disconnected_service
    second = runtime(hass, address="AA:BB:CC:DD:EE:97")
    second._controller = GoodVibeController(second, profile="selector-0001")
    second_device = register(hass, second)
    try:
        with pytest.raises(ServiceValidationError, match="Power Bob Base"):
            await hass.services.async_call(DOMAIN, "bobpowerbase", {
                "device_id": [first_device, second_device], "operation": "sync",
            }, blocking=True)
        client.write_gatt_char.assert_not_awaited()
        second.client.write_gatt_char.assert_not_awaited()
    finally:
        await second.async_shutdown()


@pytest.mark.parametrize("change", ("stop", "product", "session", "capability"))
async def test_all_targets_are_rechecked_after_pacing_before_actual_gatt(hass, fake_time, change):
    del fake_time
    first, second = runtime(hass), runtime(hass, address="AA:BB:CC:DD:EE:97")
    devices = [register(hass, c) for c in (first, second)]
    for child in (first, second):
        child.controller._normal.feed(LIGHT_REPLY)
    configuration.async_register_goodvibe_services(hass)

    async def pace(_cleanup):
        if change == "stop":
            second._command_scheduler._stop_epoch += 1
        elif change == "product":
            hass.config_entries.async_update_entry(second.entry, data={**second.entry.data, CONF_PROTOCOL_VARIANT: "elite"})
        elif change == "session":
            first._position_connection_generation += 1
        else:
            second.controller.choices.events.pop("deviceCharacteristicsSubscriptionLightEvent")
        return True

    with (
        patch.object(first, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(second, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(first, "_async_refresh_controller_auth", AsyncMock()),
        patch.object(second, "_async_refresh_controller_auth", AsyncMock()),
        patch.object(first.controller, "_pace", pace),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": devices, "operation": "light_color", "rgb_color": [1, 2, 3]}, blocking=True)
    first.client.write_gatt_char.assert_not_awaited()
    second.client.write_gatt_char.assert_not_awaited()
    for child in (first, second):
        await child.async_shutdown()


def pair_for(hass, topology):
    left = runtime(hass)
    if topology == "native":
        entry = MockConfigEntry(domain=DOMAIN, data={**left.entry.data, "pair_id": "bob-native", "pair_mode": "single_address"})
        entry.add_to_hass(hass)
        return SingleAddressPairedCoordinator(hass, entry, left), [left]
    right = runtime(hass, address="AA:BB:CC:DD:EE:97")
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left.entry.data, right.entry.data, name="Bob pair", connection_mode=topology))
    entry.add_to_hass(hass)
    return PairedBedCoordinator(hass, entry, {"left": left, "right": right}, connection_mode=topology), [left, right]


@pytest.mark.parametrize("topology", ("concurrent", "sequential", "native"))
async def test_registered_paired_action_admits_live_sides_and_legitimate_reconnect(hass, fake_time, topology):
    del fake_time
    pair, physical = pair_for(hass, topology)
    device = register(hass, pair)
    writes = []

    def drop(child):
        if child.controller is not None:
            child.controller.on_disconnect()
        if child.client is not None:
            child.client.is_connected = False
        child._controller = child._client = None
        child._position_connection_generation += 1

    for child in physical:
        drop(child)

        async def connect(*_args, owner=child, **_kwargs):
            if owner.controller is None:
                owner._position_connection_generation += 1
                owner._client = MagicMock(is_connected=True)
                owner._client.write_gatt_char = AsyncMock(side_effect=lambda _char, packet, **_kw: writes.append((owner.address, packet)))
                owner._client.stop_notify = AsyncMock()
                owner._controller = GoodVibeController(owner, profile="ultra_sh", catalog=CATALOG)
                owner.controller._link = Link(owner.client, MagicMock(uuid="tx", properties=["write"], handle=1), MagicMock(uuid="rx"), False)
                owner.controller._normal.feed(LIGHT_REPLY)
            return True

        async def disconnect(*_args, owner=child, **_kwargs):
            drop(owner)
            return True

        child.async_ensure_connected = AsyncMock(side_effect=connect)
        child.async_connect = AsyncMock(side_effect=connect)
        child.async_disconnect = AsyncMock(side_effect=disconnect)
        child._async_refresh_controller_auth = AsyncMock()
    configuration.async_register_goodvibe_services(hass)
    try:
        await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": device, "operation": "light_off"}, blocking=True)
        assert sorted(packet.hex() for _address, packet in writes) == (
            ["6e010075e4", "6e010175e5"] if topology == "native" else ["6e010075e4"] * 2
        )
    finally:
        await pair.async_shutdown()
        await pair.entry._async_process_on_unload(hass)


@pytest.mark.parametrize("topology", ("standalone", "sequential", "native"))
async def test_real_registry_keeps_custom_light_identity_across_unknown_sessions_and_retires_withdrawn_product(hass, fake_time, topology):
    del fake_time
    if topology == "standalone":
        owner = runtime(hass)
        physical = [owner]
    else:
        owner, physical = pair_for(hass, topology)
    register(hass, owner)
    registry = er.async_get(hass)
    rows = []
    for index, view in enumerate(entity_runtimes(owner)):
        for domain, key in (("button", "goodvibe_light_off"), ("select", "controller_select_goodvibe_light_duration")):
            row = registry.async_get_or_create(domain, DOMAIN, view.entity_unique_id(key), config_entry=owner.entry)
            row = registry.async_update_entity(row.entity_id, name=f"Custom Bob {domain} {index}", new_entity_id=f"{domain}.custom_bob_{index}")
            row = registry.async_update_entity_options(row.entity_id, "conversation", {"should_expose": False})
            rows.append(row)
    try:
        for phase in ("restore_unknown", "fresh_reply", "disconnected", "replacement_unknown"):
            for child in physical:
                if phase == "fresh_reply":
                    child.controller._normal.feed(LIGHT_REPLY)
                elif phase == "disconnected":
                    child.controller.on_disconnect()
                elif phase == "replacement_unknown":
                    child._controller = GoodVibeController(child, profile="ultra_sh", catalog=CATALOG)
            built = await async_setup_platforms_and_sweep(hass, owner.entry, owner, (Platform.BUTTON, Platform.SELECT))
            offered = {entity.unique_id for entity in built}
            assert all((row.unique_id in offered) == (phase == "fresh_reply") for row in rows)
            assert all(registry.async_get(row.entity_id) == row for row in rows)
            assert all(child.controller.menu_available("light") == (phase == "fresh_reply") for child in physical)
            await owner.entry._async_process_on_unload(hass)
        for child in physical:
            child.controller.product = replace(child.controller.product, light=False)
        await async_setup_platforms_and_sweep(hass, owner.entry, owner, (Platform.BUTTON, Platform.SELECT))
        assert all(registry.async_get(row.entity_id) is None for row in rows)
    finally:
        await owner.entry._async_process_on_unload(hass)
        await owner.async_shutdown()


async def test_mlily_late_light_reply_keeps_existing_specs_and_default_select_behavior(hass, fake_time):
    del fake_time
    from tests.test_mlily import runtime as mlily_runtime

    coordinator = mlily_runtime(hass, "l3rm")
    controller = coordinator.controller
    assert not controller.has_dynamic_controller_entities and not controller.has_dynamic_buttons
    assert not controller.menu_available("light")
    button = next(spec for spec in controller.controller_button_specs if spec.key == "goodvibe_light_off")
    spec = next(spec for spec in controller.controller_select_specs if spec.key == "goodvibe_light_duration")
    assert spec.is_available is None
    entity = AdjustableBedControllerSelect(coordinator, spec)
    assert entity.available
    controller._normal.feed(LIGHT_REPLY)
    assert controller.menu_available("light")
    assert button.key in {s.key for s in controller.controller_button_specs}
    assert spec.options == next(s for s in controller.controller_select_specs if s.key == spec.key).options
    coordinator._controller = coordinator._offline_controller = None
    assert entity.available  # Prior specs retain their default, including absent controller.
    await coordinator.async_shutdown()


async def test_bob_select_availability_reacts_to_capability_state_in_correct_native_side_scope(hass, fake_time):
    del fake_time
    pair, physical = pair_for(hass, "native")
    register(hass, pair)
    controller = physical[0].controller
    controller._normal.feed(LIGHT_REPLY)
    spec = next(s for s in controller.controller_select_specs if s.key == "goodvibe_light_duration")
    entities = [AdjustableBedControllerSelect(view, spec) for view in entity_runtimes(pair)]
    light_spec = next(s for s in controller.controller_button_specs if s.key == "goodvibe_light_off")
    buttons = [ControllerActionButton(view, light_spec) for view in entity_runtimes(pair)]
    sides = []
    original = controller.menu_available
    def menu(name):
        sides.append(controller.command_side)
        return original(name)
    try:
        with patch.object(controller, "menu_available", menu):
            assert all(entity.available for entity in entities)
        assert sides == ["left", "right"]
        controller.on_disconnect()
        assert all(not entity.available for entity in entities)
        assert all(not button.available for button in buttons)
        for entity in entities:
            with patch.object(entity, "async_write_ha_state") as refresh:
                entity._handle_controller_state_update(ControllerState({STATUS: "capability_changed"}))
            refresh.assert_called_once()
        controller._normal.feed(LIGHT_REPLY)
        assert all(entity.available for entity in entities)
        physical[0]._controller = physical[0]._offline_controller = None
        assert all(not entity.available for entity in entities)
    finally:
        await pair.async_shutdown()
