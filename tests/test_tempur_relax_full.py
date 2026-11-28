"""Accepted full source contracts through the codec and native HA entry points."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.linak.protocol import (
    LinakModelVariant,
    build_timer_recurrence,
)
from custom_components.adjustable_bed.codec import linak as codec
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames, shutdown
from tests.test_tempur_relax import runtime

VECTORS = json.loads((Path(__file__).parent / 'fixtures/tempur_relax/full-vectors.json').read_text())


@pytest.mark.parametrize('vector', [v for v in VECTORS if v['builder'] != 'route'], ids=lambda v: v['id'])
def test_full_frozen_vectors(vector):
    args = vector['inputs']
    try:
        match vector['builder']:
            case 'alarm':
                actual = [codec.timer_event_frame(args['seconds'], tuple(map(tuple, args['actions']))).hex(' '),
                          build_timer_recurrence(31, 1440).hex(' '), codec.timer_channel_frame().hex(' ')]
            case 'configuration':
                actual = codec.configuration_response(bytes.fromhex(args['data'])).hex(' ')
            case 'timer_info':
                actual = codec.timer_info(bytes.fromhex(args['data']))
            case 'timer_notification':
                actual = codec.timer_notification(bytes.fromhex(args['data']))
            case 'discovery':
                actual = codec.manufacturer_product(None if args['data'] is None else bytes.fromhex(args['data']))
            case _:
                pytest.fail(vector['builder'])
    except codec.ArtifactParseError as error:
        actual = {'throws': error.kind}
    assert actual == vector['expected']


async def public_runtime(hass, *, alarm=True):
    c = runtime(hass)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    c.controller._capabilities = replace(
        c.controller._capabilities, timer_supported=alarm,
        model_variant=LinakModelVariant.ADVANCED_WITH_ALARM if alarm else LinakModelVariant.ADVANCED,
    )
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(const.DOMAIN, c.address)},
    )
    await services.async_register_services(hass)
    return c, device.id


@pytest.mark.parametrize('action', ['memory_4', 'none'])
async def test_shared_alarm_three_writes_no_ack_and_clear(hass, action):
    c, device = await public_runtime(hass)
    await hass.services.async_call(const.DOMAIN, 'set_alarm', {
        'device_id': [device], 'enabled': True, 'time': '06:00:00',
        'wake_action': action, 'massage': True, 'confirm_custom_position': True,
        'weekdays': list(services.ALARM_WEEKDAYS),
    }, blocking=True)
    calls = c.client.write_gatt_char.call_args_list
    timer = [call.args[1] for call in calls if call.args[0] == const.LINAK_TIMER_CHAR_UUID]
    assert timer[-2:] == [bytes.fromhex('10a0fd'), b'\x20']
    assert timer[0][4:] == (bytes.fromhex('4400050091000500') if action != 'none' else bytes.fromhex('91000500'))
    assert not c.client.read_gatt_char.called
    c.client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, 'set_alarm', {
        'device_id': [device], 'enabled': False,
    }, blocking=True)
    assert frames(c.client) == ['893b8000', '40']
    await shutdown(c)


async def test_source_negative_duration_is_not_advanced_to_tomorrow(hass):
    c = runtime(hass)
    c.controller._capabilities = replace(c.controller._capabilities, timer_supported=True)
    alarm = AlarmRequest(enabled=True, weekdays=tuple(range(7)), hour=8, minute=0, massage=True,
                         reference_time=datetime(2026, 11, 28, 9, 0))
    await c.controller.configure_alarm(alarm)
    assert frames(c.client) == ['00f0f10191000500', '10a0fd', '20']
    await shutdown(c)


async def test_failed_alarm_write_never_commits_or_clears_as_rollback(hass):
    c = runtime(hass)
    c.controller._capabilities = replace(c.controller._capabilities, timer_supported=True)
    c.client.write_gatt_char.side_effect = [None, HomeAssistantError('recurrence failed')]
    alarm = AlarmRequest(enabled=True, weekdays=tuple(range(7)), hour=10, minute=0, massage=True,
                         reference_time=datetime(2026, 11, 28, 9, 0))
    with pytest.raises(HomeAssistantError):
        await c.controller.configure_alarm(alarm)
    assert frames(c.client) == ['00100e0191000500', '10a0fd']
    await shutdown(c)


@pytest.mark.parametrize('td3,alarm,automatic,favorite,cleanup', [
    (False, False, False, False, 'ff00'), (False, True, False, False, 'fe00'),
    (True, False, False, False, 'fe00'), (True, True, False, False, 'fe00'),
    (False, False, False, True, 'ff00'), (False, True, False, True, 'fe00'),
    (True, False, False, True, None), (False, False, True, True, None),
])
async def test_native_release_dispatch(hass, td3, alarm, automatic, favorite, cleanup):
    c = runtime(hass, mask=0 if td3 else 0xC0)
    c.controller._capabilities = replace(c.controller._capabilities, timer_supported=alarm)
    c.controller._settings['automatic_drive'] = automatic
    with virtual_clock():
        if favorite:
            await c.async_execute_controller_command(lambda ctrl: ctrl.preset_memory(1))
        else:
            await c.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    sent = frames(c.client)
    opcode = '0e00' if favorite else '0b00'
    assert sent[-1] == (cleanup or opcode)
    assert set(sent) == ({opcode, cleanup} if cleanup else {opcode})
    await shutdown(c)


async def test_favorite_and_device_names_persist_before_failed_ble_write(hass):
    c, device = await public_runtime(hass)
    await hass.services.async_call(const.DOMAIN, 'name_memory', {
        'device_id': [device], 'preset': 2, 'name': 'Reading',
    }, blocking=True)
    assert c.controller.memory_slot_names[1] == 'Reading'
    assert frames(c.client) == []
    c.client.write_gatt_char.side_effect = HomeAssistantError('write failed')
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(const.DOMAIN, 'rename', {
            'device_id': [device], 'name': 'My bed',
        }, blocking=True)
    assert c.controller.persisted_app_state['name'] == 'My bed'
    saved = await c._app_state_store.async_slot('linak:tempur_relax')
    assert saved['name'] == 'My bed' and saved['memories']['2'] == 'Reading'
    await shutdown(c)


async def paired_runtime(hass, *, secondary=True, alarm=False, mode='sequential'):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.beds.linak.tempur_relax import TempurRelaxController
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_carpe_diem import runtime as carpe_runtime

    left = runtime(hass, mask=0xC0)
    right = carpe_runtime(hass, address='AA:BB:CC:DD:EE:68')
    hass.config_entries.async_update_entry(right.entry, data={**left.entry.data, 'address': right.address})
    right._controller = TempurRelaxController(right)
    right.controller._capabilities = left.controller._capabilities
    left.controller._capabilities = replace(left.controller._capabilities, timer_supported=alarm)
    receivers = {'left': left, **({'right': right} if secondary else {})}
    entry = MockConfigEntry(domain=const.DOMAIN, data={'pair_id': 'tempur-full'})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    from custom_components.adjustable_bed.coordinator import ChildEntryView

    for receiver in receivers.values():
        receiver.entry = ChildEntryView(entry, receiver.entry.data, lambda _data: None)
    pair = PairedBedCoordinator(hass, entry, receivers, connection_mode=mode)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    for receiver in (left, right):
        client = receiver.client
        client.is_connected = False

        async def connect(client=client):
            client.is_connected = True
            return True

        async def disconnect(reason='', client=client, receiver=receiver):
            client.is_connected = False
            receiver._last_disconnect_reason = reason
            return True

        receiver.async_connect = AsyncMock(side_effect=connect)
        async def ensure(*_args, connect=connect, **_kwargs):
            return await connect()
        receiver.async_ensure_connected = AsyncMock(side_effect=ensure)
        receiver.async_disconnect = AsyncMock(side_effect=disconnect)
    device = dr.async_get(hass).async_get_device_by_identifier((const.DOMAIN, 'tempur-full'), entry.entry_id)
    await services.async_register_services(hass)
    return pair, left, right, device.id


@pytest.mark.parametrize('vector', [v for v in VECTORS if v['builder'] == 'route'], ids=lambda v: v['id'])
@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
async def test_full_route_vectors_use_existing_pair_topology(hass, vector, mode):
    args = vector['inputs']
    pair, left, right, _ = await paired_runtime(hass, secondary=args.get('secondary', True), mode=mode)
    attempts = []
    frame = {'back.up': '0b00', 'back.down': '0a00', 'all.up': '0100', 'all.down': '0000'}[args['action']]
    for who, receiver in (('PRIMARY', left), ('SECONDARY', right)):
        async def write(_uuid, packet, *, who=who, **_kwargs):
            if packet.hex() == frame:
                attempts.append([who, packet.hex(' ')])
                if who == 'PRIMARY' and args.get('fail_primary'):
                    raise HomeAssistantError('primary failed')
        receiver.client.write_gatt_char.side_effect = write
    side = {'PRIMARY': 'left', 'SECONDARY': 'right', 'BOTH': 'both'}[args['target']]
    try:
        await pair.async_execute_controller_command(lambda ctrl: ctrl.write_command(bytes.fromhex(frame)), side=side)
    except (HomeAssistantError, ValueError):
        assert args.get('fail_primary') or not args.get('secondary', True)
    assert attempts == vector['expected']
    assert pair.connection_mode == mode
    await pair.async_shutdown()
    await right.async_shutdown()


async def test_public_pair_favorites_alarm_and_primary_cleanup_ownership(hass):
    pair, left, right, device = await paired_runtime(hass, alarm=True)
    assert right.controller.memory_slot_count == 0
    assert not right.controller.supports_massage
    assert right.controller.alarm_capability is None
    with virtual_clock():
        await hass.services.async_call(const.DOMAIN, 'goto_preset', {
            'device_id': [device], 'preset': 1,
        }, blocking=True)
    assert set(frames(left.client)) == {'0e00', 'fe00'}
    assert frames(right.client) == []
    left.client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, 'save_preset', {
        'device_id': [device], 'preset': 1,
    }, blocking=True)
    assert frames(left.client) == ['3800']
    assert frames(right.client) == []
    left.client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, 'set_alarm', {
        'device_id': [device], 'enabled': True, 'time': '06:00:00',
        'wake_action': 'memory_1', 'confirm_custom_position': True,
        'weekdays': list(services.ALARM_WEEKDAYS),
    }, blocking=True)
    assert frames(left.client)[0] == '893b8001'
    assert frames(left.client)[-2:] == ['10a0fd', '20']
    assert frames(right.client) == []
    # The secondary's release uses the primary flags, not its own nonalarm mode.
    right.client.is_connected = True
    with virtual_clock():
        await right.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    assert frames(right.client)[-1] == 'fe00'
    await pair.async_shutdown()


MASKS = [row for row in json.loads((Path(__file__).parent / 'fixtures/tempur_relax/variant-inventory.json').read_text())
         if row['id'].startswith('bed.mask.')]


@pytest.mark.parametrize('row', MASKS, ids=lambda row: row['id'])
async def test_complete_source_mask_census_uses_live_discovery(hass, row):
    from types import SimpleNamespace

    c = runtime(hass)
    c.client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace() if uuid == const.LINAK_POSITION_SERVICE_UUID else None
    )
    c.client.read_gatt_char = AsyncMock(return_value=bytes((row['selector'],)))
    await c.controller.async_discover_capabilities()
    assert c.controller._capabilities.model_variant.name == row['capability_without_timer']
    assert list(c.controller._capabilities.position_axes) == [axis.lower() for axis in row['mask_axes']]
    await shutdown(c)


@pytest.mark.parametrize('payload', ['050090200100', '050090200206', '050090200400', '05009020'])
async def test_excluded_or_malformed_products_never_build_tempur_controller(hass, payload):
    from custom_components.adjustable_bed.controller_factory import create_controller

    c = runtime(hass)
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await create_controller(c, 'linak', 'tempur_relax', c.client,
                                manufacturer_data={164: bytes.fromhex(payload)})
    assert frames(c.client) == []
    await shutdown(c)


async def test_forgetting_alarm_favorite_clears_only_after_local_save(hass):
    c, device = await public_runtime(hass)
    c.controller._settings.update(memories={'2': 'Reading'}, alarm_enabled=True,
                                  alarm_favorite=True, alarm_favorite_slot=2)
    order = []
    c._app_state_store._store.async_save = AsyncMock(side_effect=lambda *_: order.append('save'))
    c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: order.append('write')
    await hass.services.async_call(const.DOMAIN, 'forget_memory', {
        'device_id': [device], 'preset': 2,
    }, blocking=True)
    assert order == ['save', 'write']
    assert frames(c.client) == ['40']
    assert c.controller.memory_slot_names[1] is None
    await shutdown(c)


@pytest.mark.parametrize('enabled', [True, False])
async def test_massage_declaration_is_live_admission_not_hardware_inference(hass, enabled):
    c = runtime(hass)
    c._has_massage = enabled
    if enabled:
        with virtual_clock():
            await c.controller.massage_head_toggle()
        assert frames(c.client) == ['8900', '8c00']
    else:
        with pytest.raises(HomeAssistantError):
            await c.controller.massage_head_toggle()
        assert frames(c.client) == []
    await shutdown(c)


async def test_control_error_signed_enum_and_short_null_are_native_state(hass):
    from custom_components.adjustable_bed.beds.linak.controller import (
        PROTOCOL_ERROR_CODE,
        PROTOCOL_ERROR_PAYLOAD,
    )

    c = runtime(hass)
    for code in range(1, 105):
        c.controller._handle_error_data(bytes((1, 0, code, 0xAA)))
        assert c.controller_state.get(PROTOCOL_ERROR_CODE) == code
        assert c.controller_state.get(PROTOCOL_ERROR_PAYLOAD) == bytes((code, 0xAA)).hex()
    c.controller._handle_error_data(bytes.fromhex('0100ff'))
    assert c.controller.protocol_diagnostics['parsed']['control_error'] == 'IllegalStateException'
    c.controller._handle_error_data(b'')
    assert c.controller_state.get(PROTOCOL_ERROR_CODE) == 0
    await shutdown(c)


async def test_failed_automatic_write_keeps_local_choice_without_claiming_delivery(hass):
    from custom_components.adjustable_bed.state_keys import LINAK_AUTOMATIC_DRIVE

    c = runtime(hass)
    c.client.write_gatt_char.side_effect = HomeAssistantError('not delivered')
    with pytest.raises(HomeAssistantError):
        await c.async_execute_controller_command(lambda ctrl: ctrl.set_automatic_drive(True))
    assert c.controller.persisted_app_state['automatic_drive'] is True
    assert c.controller_state.get(LINAK_AUTOMATIC_DRIVE) is None
    await shutdown(c)


async def test_public_setup_rejects_nonbed_manufacturer_product(hass, mock_bluetooth_service_info):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import bed_type_choice
    from tests.form_helpers import form_answers, start_new_bed

    mock_bluetooth_service_info.manufacturer_data[164] = bytes.fromhex('050090200100')
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {'source': 'user'}
    flow._discovery_info = mock_bluetooth_service_info
    form = await start_new_bed(flow, 'picked', bed_type_choice('linak', 'tempur_relax'))
    result = await flow.async_step_finish_settings(form_answers(form))
    assert result['type'] == 'form'
    assert 'tempur_product_not_in_app' in result['errors'].values(), result


@pytest.mark.parametrize('allowed', [True, False])
def test_recommendations_do_not_promote_excluded_products(allowed):
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_profile_recommendations import info

    advertisement = info('Bed 1234')
    advertisement.service_uuids = [const.LINAK_CONTROL_SERVICE_UUID]
    advertisement.manufacturer_data = {} if allowed else {164: bytes.fromhex('050090200100')}
    result = recommend_profile({'bed_type': 'keeson', 'protocol_variant': 'base'}, advertisement, {})
    assert result is not None
    assert 'linak:tempur_relax' not in result.choices
    assert result.suggested == 'linak'  # Shared UUIDs identify the family, not the app.


async def test_native_favorite_entity_label_program_and_card_contract(hass):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed import button, cover

    c, device = await public_runtime(hass, alarm=False)
    buttons, covers = [], []
    await button.async_setup_entry(hass, c.entry, buttons.extend)
    await cover.async_setup_entry(hass, c.entry, covers.extend)
    favorite = next(entity for entity in buttons if entity.unique_id.endswith('_preset_memory_2'))
    program = next(entity for entity in buttons if entity.unique_id.endswith('_program_memory_2'))
    await hass.services.async_call(const.DOMAIN, 'name_memory', {
        'device_id': [device], 'preset': 2, 'name': 'Reading',
    }, blocking=True)
    assert favorite.name == 'Reading'
    assert program.name == 'Save Reading'
    assert favorite.capability_attributes['card_section'] == 'memory'
    program.hass = hass
    program.async_write_ha_state = MagicMock()
    await program.async_press()
    assert frames(c.client) == ['3900']
    back = next(entity for entity in covers if entity.entity_description.key == 'back')
    back.hass = hass
    back.async_write_ha_state = MagicMock()
    with virtual_clock():
        await back.async_open_cover()
    assert frames(c.client)[-1] == 'ff00'
    assert set(frames(c.client)[1:-1]) == {'0b00'}
    await shutdown(c)


async def test_secondary_never_chooses_cleanup_from_its_own_flags_when_primary_unknown(hass):
    pair, left, right, _ = await paired_runtime(hass, alarm=True)
    left._controller = None
    left._offline_controller = None
    right.client.is_connected = True
    with pytest.raises(HomeAssistantError):
        await right.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    assert frames(right.client) == []
    await pair.async_shutdown()


async def test_empty_device_name_remains_a_valid_zero_length_source_write(hass):
    c = runtime(hass)
    c.client.read_gatt_char = AsyncMock(return_value=b'')
    await c.controller.rename_device('')
    assert frames(c.client) == ['']
    assert c.controller.persisted_app_state['name'] == ''
    await shutdown(c)


async def test_alarm_reuses_saved_automatic_choice_without_extra_impulse_write(hass):
    c = runtime(hass)
    c.controller._capabilities = replace(c.controller._capabilities, timer_supported=True)
    c.controller._settings['automatic_drive'] = True
    await c.controller.configure_alarm(AlarmRequest(
        enabled=True, weekdays=tuple(range(7)), hour=10, minute=0, wake_action='memory_2',
        reference_time=datetime(2026, 11, 28, 9, 0),
    ))
    assert frames(c.client) == ['00100e010f000500', '10a0fd', '20']
    await shutdown(c)


async def test_reset_retains_saved_alarm_visibility_clear_without_live_capability(hass):
    c = runtime(hass)
    c.controller._settings.update(alarm_visible=True, memories={'1': 'Reading'})
    await c.controller.reset_defaults()
    assert frames(c.client) == ['40', '4e00']
    assert c.controller.persisted_app_state['memories'] == {}
    await shutdown(c)


@pytest.mark.parametrize('mode,automatic,release', [('td3', False, []), ('advanced', True, []),
                                                 ('advanced', False, ['ff00'])])
async def test_native_card_memory_release_is_distinct_from_explicit_stop(hass, mode, automatic, release):
    import asyncio
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed import button

    c, device = await public_runtime(hass, alarm=False)
    c.controller._capabilities = replace(
        c.controller._capabilities, model_variant=LinakModelVariant(mode),
    )
    c.controller._settings['automatic_drive'] = automatic
    buttons = []
    await button.async_setup_entry(hass, c.entry, buttons.extend)
    release_button = next(entity for entity in buttons if entity.unique_id.endswith('_tempur_release'))
    release_button.hass = hass
    release_button.async_write_ha_state = MagicMock()
    favorite = next(entity for entity in buttons if entity.unique_id.endswith('_preset_memory_1'))
    assert favorite.extra_state_attributes['held_control'] == 'memory_1'
    assert favorite.extra_state_attributes['hold_release_button_key'] == 'release_held_control'
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_uuid, packet, **_kwargs):
        if packet == bytes.fromhex('0e00'):
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = write
    held = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'hold_control', {
        'device_id': [device], 'control': 'memory_1', 'duration': 1,
    }, blocking=True))
    await asyncio.wait_for(entered.wait(), 1)
    ended = asyncio.create_task(release_button.async_press())
    await asyncio.sleep(0)
    finish.set()
    if automatic:
        await ended
        for _ in range(100):
            if len(frames(c.client)) > 1:
                break
            await asyncio.sleep(0.002)
        assert not held.done()
        assert set(frames(c.client)) == {'0e00'}
        await c.async_stop_command()
        await held
        await shutdown(c)
        return
    await asyncio.gather(held, ended, return_exceptions=True)
    assert frames(c.client) == ['0e00', *release]
    c.client.write_gatt_char.side_effect = None
    await c.async_stop_command()
    assert frames(c.client)[-1] == ('fe00' if mode == 'td3' else 'ff00')
    await shutdown(c)


async def test_forgetting_a_restored_favorite_does_not_leave_its_old_entity_label(hass):
    from pytest_homeassistant.common import MockEntityPlatform

    from custom_components.adjustable_bed import button

    c, device = await public_runtime(hass, alarm=False)
    c.controller.restore_persisted_app_state({'memories': {'1': 'Reading'}})
    buttons = []
    await button.async_setup_entry(hass, c.entry, buttons.extend)
    favorite = next(entity for entity in buttons if entity.unique_id.endswith('_preset_memory_1'))
    platform = MockEntityPlatform(hass, domain="button", platform_name=const.DOMAIN)
    await platform.platform_data.async_load_translations()
    await platform.async_add_entities([favorite])
    assert favorite.name == 'Reading'
    await hass.services.async_call(const.DOMAIN, 'forget_memory', {
        'device_id': [device], 'preset': 1,
    }, blocking=True)
    assert favorite.name != 'Reading'
    assert frames(c.client) == []
    await shutdown(c)


@pytest.mark.parametrize('mask,expects_error', [(None, False), (0, False), (1, True), (0xC0, True)])
async def test_error_subscription_uses_reference_capability_even_with_empty_axis_set(hass, mask, expects_error):
    c = runtime(hass, mask=mask)
    c.client.read_gatt_char = AsyncMock(return_value=b'')
    await c.controller.start_notify()
    subscribed = {call.args[0] for call in c.client.start_notify.await_args_list}
    assert (const.LINAK_ERROR_CHAR_UUID in subscribed) == expects_error
    assert ('linak_protocol_error' in {spec.key for spec in c.controller.controller_state_sensor_specs}) == expects_error
    await shutdown(c)


@pytest.mark.parametrize('days', [[], ['monday']])
async def test_shared_alarm_rejects_one_time_or_partial_week_before_writing(hass, days):
    c, device = await public_runtime(hass)
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(const.DOMAIN, 'set_alarm', {
            'device_id': [device], 'enabled': True, 'time': '07:30:00',
            'massage': True, 'weekdays': days,
        }, blocking=True)
    assert error.value.translation_key == 'tempur_alarm_daily'
    assert frames(c.client) == []
    await shutdown(c)


@pytest.mark.parametrize('mode', ['sequential', 'concurrent'])
async def test_pair_name_readback_failure_stops_secondary_after_both_names_are_saved(hass, mode):
    from bleak.exc import BleakError

    pair, left, right, device = await paired_runtime(hass, mode=mode)
    left.client.read_gatt_char = AsyncMock(side_effect=BleakError('read failed'))
    right.client.read_gatt_char = AsyncMock(return_value=b'Bed')
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(const.DOMAIN, 'rename', {
            'device_id': [device], 'name': 'Bed',
        }, blocking=True)
    assert left.controller.persisted_app_state['name'] == 'Bed'
    assert right.controller.persisted_app_state['name'] == 'Bed'
    assert frames(left.client) == [b'Bed'.hex()]
    assert frames(right.client) == []
    await pair.async_shutdown()
