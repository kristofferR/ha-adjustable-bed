"""Native HA entities, shared actions, explicit setup and pair ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.superior_sleep.controller import SuperiorSleepController
from custom_components.adjustable_bed.profiles import superior_sleep as p
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.setup_questions import setup_profile
from tests.hold_lease_wire import virtual_clock
from tests.test_superior_sleep import gatt

ADDRESS = "AA:BB:CC:DD:AA:14"


@pytest.mark.parametrize("product", p.PROFILES)
async def test_actual_native_entity_and_service_routes(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, product
):
    mock_bleak_client.services = gatt()
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Superior Sleep",
        const.CONF_BED_TYPE: "superior_sleep",
        const.CONF_PROTOCOL_VARIANT: product,
        const.CONF_BLE_DEVICE_NAME: "Smartbed123",
        const.CONF_HAS_MASSAGE: True,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_MOTOR_COUNT: 2,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Superior Sleep", unique_id=ADDRESS, data=data
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    controller = runtime.controller
    assert isinstance(controller, SuperiorSleepController)
    assert controller.profile is p.PROFILES[product]
    registry = er.async_get(hass)
    entities = [
        item for item in registry.entities.values() if item.config_entry_id == entry.entry_id
    ]
    device = next(item.device_id for item in entities if item.device_id)
    for axis in ("back", "legs", *(("head", "lumbar") if product == "ss650" else ())):
        assert registry.async_get_entity_id("cover", const.DOMAIN, f"{ADDRESS}_{axis}")
    assert bool(
        registry.async_get_entity_id("button", const.DOMAIN, f"{ADDRESS}_preset_memory_1")
    ) == (product == "ss350")
    assert not any("voice_" in item.unique_id or "clock" in item.unique_id for item in entities)
    for action in ("query_massage", "query_alarm", "speech_stop", "reset_memories"):
        entity_id = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_superior_sleep_{action}"
        )
        assert entity_id and registry.async_get(entity_id).disabled_by is not None
    saves = [
        item
        for item in entities
        if "program_memory" in item.unique_id or "superior_sleep_save_" in item.unique_id
    ]
    assert len(saves) == (4 if product == "ss350" else 1)
    for item in saves:
        attrs = hass.states.get(item.entity_id).attributes
        if "program_memory" in item.unique_id:
            assert attrs["card_role"] == "save"
        else:
            assert attrs["requires_confirmation"]
    with virtual_clock():
        for action in p.SPEECH_ACTIONS:
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "superior_sleep_speech",
                {"device_id": device, "action": action, "duration_ms": 200},
                blocking=True,
            )
            frames = [
                bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.await_args_list
            ]
            assert frames and frames[0] == p.FRAMES[action]
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device, "control": "head_up", "duration": 0.2},
            blocking=True,
        )
        assert [
            bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.await_args_list
        ] == [p.FRAMES["head_up"]] * 2 + [p.FRAMES["stop"]] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device,
                "enabled": True,
                "time": "06:42:00",
                "weekdays": ["monday", "wednesday", "sunday"],
                "wake_action": "wake_mode_1",
            },
            blocking=True,
        )
        assert (
            bytes(mock_bleak_client.write_gatt_char.await_args_list[0].args[1]).hex()
            == "07058b06062a000101"
        )
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN, "sync_clock", {"device_id": device}, blocking=True
        )
        assert mock_bleak_client.write_gatt_char.await_count == 2
        assert all(
            bytes(call.args[1])[:2] == b"\x07\x04"
            for call in mock_bleak_client.write_gatt_char.await_args_list
        )
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("product", p.PROFILES)
async def test_explicit_setup_and_per_side_settings(hass, product):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import start_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    assert "Superior sleep" in BED_TYPE_DISPLAY_NAMES["superior_sleep"]
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    step = await start_new_bed(flow, "typed", "superior_sleep")
    assert step["step_id"] == "profile_questions"
    step = await flow.async_step_profile_questions(
        {
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_BLE_DEVICE_NAME: "BLE123",
        }
    )
    assert step["step_id"] == "finish_settings"
    result = await flow.async_step_finish_settings({})
    assert result["type"] == "create_entry"
    data = flow._finish_with_verify.await_args.args[0]
    assert data[const.CONF_PROTOCOL_VARIANT] == product
    assert data[const.CONF_HAS_MASSAGE] is True
    assert resolve_profile_id(data) == f"superior_sleep:{product}"
    profile = per_side_profile("superior_sleep", product)
    assert (
        profile is not None and const.CONF_BLE_DEVICE_NAME in profile.keys and profile.variant_owned
    )
    coord = _FactoryCoordinator()
    coord.entry.data.update(data)
    offline = await create_controller(coord, "superior_sleep", product, None)
    assert offline.profile is p.PROFILES[product]
    assert offline.transport == p.TRANSPORTS["ble"]
    assert not offline.supports_single_address_pairing
    assert not offline.supports_position_feedback
    title = setup_profile("superior_sleep").title
    assert title is not None and title(data) == "Superior sleep"


def test_discovery_is_only_a_weak_app_candidate():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    for name in ("Smartbed123", "BLE123"):
        route = p.transport_for_name(name)
        result = detect_bed_type_detailed(
            _make_service_info(name=name, service_uuids=[route.service])
        )
        assert "superior_sleep" in {result.bed_type, *(result.ambiguous_types or ())}
        result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
        assert "superior_sleep" not in {result.bed_type, *(result.ambiguous_types or ())}
    result = detect_bed_type_detailed(_make_service_info(name="BLE Tag", service_uuids=[]))
    assert "superior_sleep" not in {result.bed_type, *(result.ambiguous_types or ())}
    result = detect_bed_type_detailed(_make_service_info(name="Random gadget", service_uuids=[]))
    assert "superior_sleep" not in {result.bed_type, *(result.ambiguous_types or ())}
    # A known receiver wins even though its shared name is accepted by the app.
    result = detect_bed_type_detailed(
        _make_service_info(name="Smartbed123", service_uuids=[const.OKIMAT_SERVICE_UUID])
    )
    assert result.bed_type != "superior_sleep" and "superior_sleep" not in (
        result.ambiguous_types or ()
    )


async def test_failed_disconnect_retains_command_binding(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Superior Sleep",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Superior Sleep",
            const.CONF_BED_TYPE: "superior_sleep",
            const.CONF_PROTOCOL_VARIANT: "ss350",
            const.CONF_BLE_DEVICE_NAME: "Smartbed123",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime, AdjustableBedCoordinator)
    owning_controller = runtime.controller
    original = mock_bleak_client.disconnect.side_effect
    subscriptions = mock_bleak_client.start_notify.await_count
    mock_bleak_client.disconnect.side_effect = BleakError("disconnect refused")
    try:
        assert not await runtime.async_disconnect(serialize_with_commands=True)
        assert runtime.controller is owning_controller
        assert mock_bleak_client.start_notify.await_count == subscriptions + 1
        notify = mock_bleak_client.start_notify.await_args.args[1]
        notify(
            mock_bleak_client.services[0].characteristics[1],
            bytearray.fromhex("a50b0e000258020203"),
        )
        from custom_components.adjustable_bed.beds.superior_sleep import state_keys

        assert runtime.controller_state[state_keys.TIMER] == 10
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_clock():
            await runtime.async_execute_controller_command(lambda c: c.move_back_up())
        assert (
            bytes(mock_bleak_client.write_gatt_char.await_args_list[0].args[1])
            == p.FRAMES["head_up"]
        )
    finally:
        mock_bleak_client.disconnect.side_effect = original
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_speech_action_selector_keeps_its_translated_labels(caplog):
    from pathlib import Path

    from homeassistant.util.yaml import load_yaml_dict

    schema = load_yaml_dict(
        str(Path(__file__).parents[1] / "custom_components/adjustable_bed/services.yaml")
    )
    fields = schema["superior_sleep_speech"]["fields"]
    assert (
        fields["action"]["selector"]["select"]["translation_key"] == "superior_sleep_speech_action"
    )
    assert fields["side"]["selector"]["select"]["translation_key"] == "side"
    assert not any("duplicate" in record.message.lower() for record in caplog.records)


@pytest.mark.parametrize("callback", [False, True])
async def test_transport_gate_keeps_delayed_restoration_close_intentional(
    hass, mock_config_entry, callback
):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    client = MagicMock()
    client.is_connected = True
    client.disconnect = AsyncMock()  # First close returns before the OS closes.
    controller = MagicMock()
    controller.stop_keepalive = AsyncMock()
    controller.stop_notify = AsyncMock()
    coordinator._client, coordinator._controller = client, controller
    coordinator._link_ready = True
    intentional = []

    async def restore():
        intentional.append(coordinator._intentional_disconnect)
        client.is_connected = False
        if callback:
            coordinator._on_disconnect(client)

    coordinator.async_start_notify = AsyncMock(side_effect=restore)
    async with coordinator.async_transport_operation("unpair"):
        assert coordinator.client is None
        assert coordinator.controller is None
        assert coordinator._reconnect_timer is None
        assert coordinator._last_disconnect_reason == "transport_operation_unpair"
    assert intentional == [True]
    assert coordinator._intentional_disconnect is False
    await coordinator.async_shutdown()


async def test_shutdown_never_restores_a_retained_notification_channel(hass, mock_config_entry):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    client = MagicMock()
    client.is_connected = True
    client.disconnect = AsyncMock()
    controller = MagicMock()
    controller.stop_keepalive = AsyncMock()
    controller.stop_notify = AsyncMock()
    coordinator._client, coordinator._controller = client, controller
    coordinator._shutting_down = True
    coordinator.async_start_notify = AsyncMock()
    assert not await coordinator.async_disconnect()
    controller.stop_notify.assert_awaited_once()
    coordinator.async_start_notify.assert_not_awaited()
    assert coordinator._intentional_disconnect is False
    client.is_connected = False
    await coordinator.async_shutdown()
