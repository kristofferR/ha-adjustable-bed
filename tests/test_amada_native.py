"""Native HA setup, generic service/entity routes and selector admission."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.amada.controller import AmadaController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profiles import amada as p
from custom_components.adjustable_bed.runtime_data import entry_runtime
from tests.hold_lease_wire import virtual_clock
from tests.test_amada import gatt, notify, writes

ADDRESS = 'AA:BB:CC:DD:AA:69'


@pytest.mark.parametrize("failure", ("cancel", "error", "noop", "notify_retry"))
async def test_retained_link_restores_fresh_subscription(hass, failure):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.bed_traits import bed_traits
    from custom_components.adjustable_bed.beds.amada.state import LIGHT
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(domain=const.DOMAIN, version=5, title="Amada", data={
        CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: "amada", const.CONF_PRODUCT_TYPE: "a"
    })
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    client = MagicMock(is_connected=True, services=gatt())
    client.write_gatt_char, client.start_notify, client.stop_notify = AsyncMock(), AsyncMock(), AsyncMock()
    co._client = client
    co._position_connection_generation = 1
    controller = AmadaController(co, "a")
    controller.static_traits = bed_traits("amada")
    co._controller = controller
    await controller.async_discover_capabilities()
    await controller.start_notify()
    co._link_ready = True
    link = controller._live()
    raw = bytes.fromhex("a50b0eaa025802030601")
    notify(client, raw)
    old = client.start_notify.call_args.args[1]

    async def disconnect():
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "error":
            raise BleakError("disconnect failed")

    client.disconnect = AsyncMock(side_effect=disconnect)
    if failure == "notify_retry":
        client.start_notify.side_effect = [BleakError("restore failed"), BleakError("restore failed"), None]
    try:
        with virtual_clock():
            async with co._lock:
                if failure == "cancel":
                    with pytest.raises(asyncio.CancelledError):
                        await co._async_disconnect_locked()
                else:
                    assert await co._async_disconnect_locked() is False
            if failure == "notify_retry":
                assert not co._link_ready
                assert await co.async_ensure_connected(reset_timer=False)
        assert co._controller is controller and controller._live() is link
        assert co._link_ready
        assert co.controller_state.get(LIGHT) is None
        old(client.services[0].characteristics[1], bytearray(raw))
        assert co.controller_state.get(LIGHT) is None
        notify(client, raw)
        assert co.controller_state.get(LIGHT) is not None
        await co.async_execute_controller_command(lambda c: c.preset_flat())
        assert writes(client)
    finally:
        async def close():
            client.is_connected = False

        client.disconnect.side_effect = close
        await co.async_shutdown()


@pytest.mark.parametrize('selector', p.SELECTORS)
async def test_native_entities_and_generic_services(hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch, selector):
    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(domain=const.DOMAIN, title='Amada', unique_id=ADDRESS, data={
        CONF_ADDRESS: ADDRESS, CONF_NAME: 'Amada', const.CONF_BED_TYPE: 'amada',
        const.CONF_PRODUCT_TYPE: selector, const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_HAS_MASSAGE: True, const.CONF_MOTOR_COUNT: 3,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    })
    entry.add_to_hass(hass)
    monkeypatch.setattr(AmadaController, 'sync_clock', AsyncMock())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime.controller, AmadaController)
    assert runtime.controller._selector == p.SELECTORS[selector]
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
    device = next(e.device_id for e in entities if e.device_id)
    for axis in ('back', 'legs', 'head', 'combined'):
        assert registry.async_get_entity_id('cover', const.DOMAIN, f'{ADDRESS}_{axis}')
    assert not any('angle' in e.unique_id for e in entities)
    save = registry.async_get_entity_id('button', const.DOMAIN, f'{ADDRESS}_amada_save_zero_g')
    assert save and hass.states.get(save).attributes['requires_confirmation']
    for suffix in ('massage_all_toggle', 'massage_head_up', 'massage_head_down', 'massage_mode_step', 'toggle_light', 'amada_foot_strength_down', 'amada_timer_step'):
        assert registry.async_get_entity_id('button', const.DOMAIN, f'{ADDRESS}_{suffix}')
    with virtual_clock():
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(const.DOMAIN, 'hold_control',
            {'device_id': device, 'control': 'head_up', 'duration': 0.2}, blocking=True)
        assert writes(mock_bleak_client) == [codec.frame40(1, p.SELECTORS[selector])] * 2 + [codec.frame40(0, p.SELECTORS[selector])]
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(const.DOMAIN, 'set_alarm',
            {'device_id': device, 'enabled': True, 'time': '06:42:00',
             'weekdays': ['monday', 'sunday'], 'wake_action': 'light'}, blocking=True)
        assert writes(mock_bleak_client) == [p.alarm_frame(6, 42, 0x83, 7, True, p.SELECTORS[selector])]
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize('selector', p.SELECTORS)
async def test_explicit_setup_and_side_owned_selector(hass, selector):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.setup_questions import REQUIRED, setup_profile
    from tests.form_helpers import start_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    profile = setup_profile('amada')
    assert profile.questions[0].default is REQUIRED
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={'type': 'create_entry'})
    step = await start_new_bed(flow, 'typed', 'amada')
    assert step['step_id'] == 'profile_questions'
    step = await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: selector})
    assert step['step_id'] == 'finish_settings'
    assert (await flow.async_step_finish_settings({}))['type'] == 'create_entry'
    data = flow._finish_with_verify.await_args.args[0]
    assert data[const.CONF_PRODUCT_TYPE] == selector
    assert data[const.CONF_HAS_MASSAGE] is True
    assert const.CONF_PRODUCT_TYPE in per_side_profile('amada', 'auto').keys
    coord = _FactoryCoordinator()
    coord.entry.data.update(data)
    c = await create_controller(coord, 'amada', 'auto', None)
    assert c._selector == p.SELECTORS[selector]
    assert not c.supports_single_address_pairing
    assert not supports_single_address_pairing('amada', product_type=selector)
    assert not c.execution.concurrent


async def test_missing_selector_fails_factory_before_any_ble():
    from tests.test_controller_contract import _FactoryCoordinator
    coord = _FactoryCoordinator()
    with pytest.raises(ValueError, match='target A, AB or B'):
        await create_controller(coord, 'amada', 'auto', None)


def test_name_prefix_is_only_an_app_candidate():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info
    for name in ('Smartbed4123', 'smartbed4x', 'SMARTBED4X'):
        result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
        assert 'amada' in {result.bed_type, *(result.ambiguous_types or ())}
    for name in ('unrelated', 'prefixSmartbed4'):
        result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[p.SERVICE_UUID]))
        assert 'amada' not in {result.bed_type, *(result.ambiguous_types or ())}


async def test_multi_target_alarm_disable_preflights_all_before_mutation(hass):
    from unittest.mock import MagicMock

    from homeassistant.exceptions import HomeAssistantError

    from tests.test_shared_action_hardening import beds, set_alarm

    async with beds(hass) as made:
        clients = []
        for index, coord in enumerate(made.items):
            client = MagicMock(is_connected=True, services=gatt())
            client.start_notify, client.stop_notify, client.write_gatt_char = AsyncMock(), AsyncMock(), AsyncMock()
            client.disconnect = AsyncMock(side_effect=lambda client=client: setattr(client, "is_connected", False))
            coord._client = client
            c = AmadaController(coord, 'a' if index == 0 else 'b')
            coord._controller = coord._offline_controller = c
            await c.async_discover_capabilities()
            await c.start_notify()
            clients.append(client)
        first = clients[0]

        async def reply(*args, **kwargs):
            if bytes(args[1]) == b'\x00\xc0':
                first.start_notify.call_args.args[1](first.services[0].characteristics[1], bytearray.fromhex('a50c0eaa8301071e0001'))

        first.write_gatt_char.side_effect = reply
        with virtual_clock(), pytest.raises(HomeAssistantError):
            await set_alarm(hass, [(c, 'both') for c in made.items], enabled=False)
        assert all(all(frame == b'\x00\xc0' for frame in writes(client)) for client in clients)
