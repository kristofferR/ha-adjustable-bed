"""Full-review probes through native services, entities and paired reservations."""

import asyncio
import contextlib
import json
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import datetime
from importlib.abc import MetaPathFinder
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockEntityPlatform

from custom_components.adjustable_bed import button, const, cover, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.linak.protocol import LinakModelVariant
from custom_components.adjustable_bed.beds.linak.tempur_relax import TempurRelaxController
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames, shutdown
from tests.test_tempur_relax_full import paired_runtime, public_runtime


@pytest.mark.parametrize('mode,lease', [('concurrent', False), ('sequential', False), ('concurrent', True)])
async def test_public_finite_both_hold_preserves_topology_and_refresh_order(hass, mode, lease):
    pair, left, right, device = await paired_runtime(hass, mode=mode)
    writes = []
    for side, receiver in [('left', left), ('right', right)]:
        async def write(_uuid, packet, *, side=side, **_kwargs):
            if packet == b'\x00\x00':
                writes.append((side, asyncio.get_running_loop().time()))
                await asyncio.sleep(0.01)
        receiver.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'flat', 'duration': 0.35,
            **({'hold_owner': 'card', 'hold_generation': 1} if lease else {}),
        }, blocking=True)
    assert pair.connection_mode == mode
    assert {side for side, _ in writes} == {'left', 'right'}
    if mode == 'concurrent':
        assert [side for side, _ in writes] == ['left', 'right'] * (len(writes) // 2)
        for index in range(2, len(writes), 2):
            assert writes[index][1] - writes[index - 1][1] >= 0.1
    else:
        assert [side for side, _ in writes] == sorted(side for side, _ in writes)
    await pair.async_shutdown()


async def test_renewable_both_hold_requires_two_live_links(hass):
    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    with pytest.raises(ServiceValidationError, match='both beds connected'):
        await hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'flat', 'duration': 0.35,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True)
    assert frames(left.client) == frames(right.client) == []
    await pair.async_shutdown()


async def test_explicit_stop_reopens_released_td3_pair(hass):
    pair, left, right, device = await paired_runtime(hass)
    for child in (left, right):
        child.controller._capabilities = replace(child.controller._capabilities,
            model_variant=LinakModelVariant.TD3, actuator_mask=0)
    with virtual_clock():
        await hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'memory_1', 'duration': 0.1,
        }, blocking=True)
    assert set(frames(left.client)) == {'0e00'} and frames(right.client) == []
    assert not left.is_connected and not right.is_connected
    await hass.services.async_call(const.DOMAIN, 'stop_all', {'device_id': [device]}, blocking=True)
    assert set(frames(left.client)[:-1]) == {'0e00'} and frames(left.client)[-1] == 'fe00'
    assert frames(right.client) == ['fe00']
    assert not left.is_connected and not right.is_connected
    await pair.async_shutdown()


@pytest.mark.parametrize('motor', [False, True])
async def test_caller_cancellation_during_primary_stop_preparation_still_stops(hass, motor):
    pair, left, right, _ = await paired_runtime(hass, mode='concurrent')
    entered, finish = asyncio.Event(), asyncio.Event()
    original = pair._async_prepare_primary_flags

    async def prepare(targets):
        entered.set()
        await finish.wait()
        await original(targets)

    pair._async_prepare_primary_flags = prepare
    task = asyncio.create_task(
        pair.async_stop_motor(lambda ctrl: ctrl.stop_all(), 'motor:back', side='both')
        if motor else pair.async_stop_command()
    )
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(left.client) == frames(right.client) == ['ff00']
    await pair.async_shutdown()


@pytest.mark.parametrize('mode', ['concurrent', 'sequential'])
@pytest.mark.parametrize('key,expected', [('preset_flat', '3400'), ('preset_both_up', '3700')])
async def test_native_both_preset_selects_primary_td3_branch(hass, mode, key, expected):
    pair, left, right, _ = await paired_runtime(hass, mode=mode)
    left.controller._capabilities = replace(left.controller._capabilities,
        model_variant=LinakModelVariant.TD3, actuator_mask=0)
    entities = []
    await button.async_setup_entry(hass, pair.entry, entities.extend)
    preset = next(entity for entity in entities if isinstance(entity, button.PairedBedCombinedButton)
                  and entity.entity_description.key == key)
    preset.hass = hass
    with virtual_clock():
        await preset.async_press()
    assert set(frames(left.client)) == {expected, 'fe00'}
    assert set(frames(right.client)) == {expected, 'fe00'}
    await pair.async_shutdown()


async def test_public_rename_merges_concurrent_favorite_and_saves_both_names_before_ble(hass):
    pair, left, right, device = await paired_runtime(hass, mode='concurrent')
    left.client.read_gatt_char = AsyncMock(return_value=b'Bed')
    right.client.read_gatt_char = AsyncMock(return_value=b'Bed')
    writing, finish = asyncio.Event(), asyncio.Event()
    save = left._app_state_store._store.async_save
    first = True

    async def delayed_save(data):
        nonlocal first
        if first:
            first = False
            writing.set()
            await finish.wait()
        await save(data)

    left._app_state_store._store.async_save = AsyncMock(side_effect=delayed_save)
    async def write(*_args, **_kwargs):
        assert left.controller.persisted_app_state['memories'] == {'2': 'Reading'}
        assert left.controller.persisted_app_state['name'] == 'Bed'
        assert right.controller.persisted_app_state['name'] == 'Bed'
    left.client.write_gatt_char.side_effect = right.client.write_gatt_char.side_effect = write
    name = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'name_memory', {
        'device_id': [device], 'preset': 2, 'name': 'Reading',
    }, blocking=True))
    await writing.wait()
    rename = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'rename', {
        'device_id': [device], 'name': 'Bed',
    }, blocking=True))
    await asyncio.sleep(0)
    finish.set()
    await asyncio.gather(name, rename)
    saved = await left._app_state_store.async_slot('linak:tempur_relax')
    assert saved['memories'] == {'2': 'Reading'} and saved['name'] == 'Bed'
    assert frames(left.client) == frames(right.client) == ['426564']
    await pair.async_shutdown()


@pytest.mark.parametrize('cancel', [False, True])
async def test_failed_rename_preparation_releases_every_preflighted_link(hass, cancel):
    pair, left, right, device = await paired_runtime(hass, mode='concurrent')
    released = []

    async def preflight(targets, check, **kwargs):
        return [(pair, left), (pair, right)]

    async def release(targets):
        released.extend(targets)

    left.controller.prepare_device_rename = AsyncMock(side_effect=(
        asyncio.CancelledError if cancel else HomeAssistantError('storage failed')
    ))
    with patch.object(services, '_preflight_each', preflight), patch.object(
        services, '_release_preflighted', release
    ), pytest.raises(asyncio.CancelledError if cancel else HomeAssistantError):
        await hass.services.async_call(const.DOMAIN, 'rename', {
            'device_id': [device], 'name': 'Bed',
        }, blocking=True)
    assert released == [(pair, left), (pair, right)]
    assert frames(left.client) == frames(right.client) == []
    await pair.async_shutdown()


async def test_clear_known_alarm_without_notification_success_and_floor_negative_seconds(hass):
    c, device = await public_runtime(hass, alarm=False)
    c.controller._settings.update(alarm_enabled=True, alarm_visible=True)
    await hass.services.async_call(const.DOMAIN, 'set_alarm', {
        'device_id': [device], 'enabled': False,
    }, blocking=True)
    assert frames(c.client) == ['893b8000', '40']
    with pytest.raises(ServiceValidationError, match='alarm'):
        await hass.services.async_call(const.DOMAIN, 'set_alarm', {
            'device_id': [device], 'enabled': True, 'time': '08:00:00', 'massage': True,
            'weekdays': list(services.ALARM_WEEKDAYS),
        }, blocking=True)
    c.client.write_gatt_char.reset_mock()
    c.controller._capabilities = replace(c.controller._capabilities, timer_supported=True)
    await c.controller.configure_alarm(AlarmRequest(
        enabled=True, weekdays=tuple(range(7)), hour=8, minute=0, massage=True,
        reference_time=datetime(2026, 11, 28, 8, 0, 0, 500000),
    ))
    assert frames(c.client)[0].startswith('00ffff01')
    await shutdown(c)


@pytest.mark.parametrize('cancel', [False, True])
async def test_forget_favorite_retries_pending_alarm_clear_after_rebuild(hass, cancel):
    c, device = await public_runtime(hass)
    ctrl = c.controller
    ctrl._settings.update(memories={'2': 'Reading'}, alarm_enabled=True,
                          alarm_favorite=True, alarm_favorite_slot=2)
    c.client.write_gatt_char.side_effect = (
        asyncio.CancelledError if cancel else HomeAssistantError('clear failed')
    )
    with contextlib.nullcontext() if cancel else pytest.raises(HomeAssistantError):
        await hass.services.async_call(const.DOMAIN, 'forget_memory', {
            'device_id': [device], 'preset': 2,
        }, blocking=True)
    saved = await c._app_state_store.async_slot('linak:tempur_relax')
    assert saved['memories'] == {} and saved['alarm_enabled'] is False
    assert saved['pending_alarm_clear_slot'] == 2
    c._controller = TempurRelaxController(c)
    c.controller._capabilities = ctrl._capabilities
    c.controller.restore_persisted_app_state(saved)
    c.client.write_gatt_char.side_effect = None
    await hass.services.async_call(const.DOMAIN, 'forget_memory', {
        'device_id': [device], 'preset': 2,
    }, blocking=True)
    assert frames(c.client) == ['40', '40']
    assert c.controller.persisted_app_state['pending_alarm_clear_slot'] is None
    assert c.controller.persisted_app_state['memories'] == {}
    await shutdown(c)


async def test_skipped_alarm_clear_preserves_forgotten_favorite_retry(hass):
    c, _ = await public_runtime(hass)
    ctrl = c.controller
    ctrl._settings.update(memories={'2': 'Reading'}, alarm_enabled=True,
                          alarm_favorite=True, alarm_favorite_slot=2)
    stored = asyncio.Event()
    save = c._app_state_store._store.async_save

    async def saving(data):
        await save(data)
        stored.set()

    c._app_state_store._store.async_save = saving
    async with ctrl._ble_lock:
        task = asyncio.create_task(c.async_execute_controller_command(
            lambda current: current.forget_memory(2), cancel_running=False,
            resource='configuration',
        ))
        await stored.wait()
        c.request_command_cancel()
    await task
    assert frames(c.client) == []
    assert ctrl.persisted_app_state['pending_alarm_clear_slot'] == 2
    await c.async_execute_controller_command(lambda current: current.forget_memory(2))
    assert frames(c.client) == ['40']
    assert ctrl.persisted_app_state['pending_alarm_clear_slot'] is None
    await shutdown(c)


async def test_absent_controller_at_platform_start_still_registers_late_entities(hass):
    c, _ = await public_runtime(hass)
    c._controller = c._offline_controller = None
    covers, buttons = [], []
    await cover.async_setup_entry(hass, c.entry, covers.extend)
    await button.async_setup_entry(hass, c.entry, buttons.extend)
    assert not covers
    assert not any(entity.unique_id.endswith('_preset_memory_1') for entity in buttons)
    c._controller = TempurRelaxController(c)
    c.client.services.get_service.return_value = object()
    c.client.read_gatt_char = AsyncMock(return_value=b'\xc0')
    await c.controller.async_discover_capabilities()
    assert {entity.entity_description.key for entity in covers} == {'back', 'legs'}
    assert any(entity.unique_id.endswith('_preset_memory_1') for entity in buttons)
    await shutdown(c)


async def test_right_only_cold_recovery_inspects_primary_on_single_slot_and_adds_entities(hass):
    from custom_components.adjustable_bed.controller_factory import create_controller

    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    connections = []
    for child, mask in [(left, 0), (right, 0xC0)]:
        child._controller = child._offline_controller = None
        client = child.client
        client.services.get_service.return_value = object()
        client.read_gatt_char = AsyncMock(return_value=bytes((mask,)))

        async def connect(*_args, child=child, client=client, **_kwargs):
            assert all(not peer.is_connected for peer in (left, right) if peer is not child)
            connections.append(child.address)
            client.is_connected = True
            if child.controller is None:
                child._controller = await create_controller(child, 'linak', 'tempur_relax', client)
                await child.controller.async_discover_capabilities()
                await child.controller.start_notify()
            return True
        child.async_connect = AsyncMock(side_effect=connect)
        child.async_ensure_connected = AsyncMock(side_effect=connect)
    covers, buttons = [], []
    await cover.async_setup_entry(hass, pair.entry, covers.extend)
    await button.async_setup_entry(hass, pair.entry, buttons.extend)
    assert not covers
    with virtual_clock():
        await hass.services.async_call(const.DOMAIN, 'timed_move', {
            'device_id': [device], 'side': 'right', 'motor': 'back',
            'direction': 'up', 'duration_ms': 250,
        }, blocking=True)
    assert left.address in connections[:-1] and connections[-1] == right.address
    assert '0b00' not in frames(left.client)
    assert frames(right.client)[-1] == 'fe00'  # Primary TD3, secondary Advanced.
    assert any(entity._coordinator.entity_side == 'right' and entity.entity_description.key == 'back'
               for entity in covers)
    assert any(entity.unique_id.endswith('_preset_memory_1') for entity in buttons)
    assert not left.is_connected and not right.is_connected
    await pair.async_shutdown()


async def test_automatic_favorite_survives_card_release_and_lease_expiry_but_explicit_stop_wins(hass):
    c, device = await public_runtime(hass, alarm=False)
    c.controller._settings['automatic_drive'] = True
    entered = asyncio.Event()
    c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: entered.set()
    release = button.ControllerActionButton(c, c.controller.controller_button_specs[0])
    release.hass = hass
    with virtual_clock():
        hold = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'memory_1', 'duration': 0.1,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True))
        await entered.wait()
        await release.async_press()
        await asyncio.sleep(0.35)
        assert not hold.done() and len(frames(c.client)) >= 3
        assert set(frames(c.client)) == {'0e00'}
        await hass.services.async_call(const.DOMAIN, 'stop_all', {'device_id': [device]}, blocking=True)
        await hold
    assert frames(c.client)[-1] == 'ff00'
    await shutdown(c)


@pytest.mark.parametrize('combined', [False, True])
async def test_shipped_card_resolves_actual_registry_release_metadata(hass, combined):
    if combined:
        c, _, _, _ = await paired_runtime(hass, mode='concurrent')
    else:
        c, _ = await public_runtime(hass)
    entities = []
    await button.async_setup_entry(hass, c.entry, entities.extend)
    favorite = next(entity for entity in entities if entity.unique_id.endswith(
        '_preset_flat_both' if combined else '_preset_memory_1'))
    release = next(entity for entity in entities if isinstance(entity, button.PairedBedGestureReleaseButton)) if combined else next(
        entity for entity in entities if entity.unique_id.endswith('_tempur_release'))
    platform = MockEntityPlatform(hass, domain='button', platform_name=const.DOMAIN)
    platform.config_entry = c.entry
    await platform.platform_data.async_load_translations()
    await platform.async_add_entities([favorite, release])
    registry = er.async_get(hass)
    data = {'entities': {}, 'states': {}}
    for entity in (favorite, release):
        row = registry.async_get(entity.entity_id)
        data['entities'][entity.entity_id] = {'entity_id': row.entity_id,
            'device_id': row.device_id, 'translation_key': row.translation_key}
        data['states'][entity.entity_id] = {'attributes': dict(hass.states.get(entity.entity_id).attributes)}
    assert data['states'][favorite.entity_id]['attributes']['hold_release_button_key'] == row.translation_key
    script = '''import { heldButtonMotor } from './custom_components/adjustable_bed/frontend/src/hold.ts';
const {hass, favorite} = JSON.parse(await Bun.stdin.text());
console.log(JSON.stringify(heldButtonMotor(hass, favorite)));'''
    result = await hass.async_add_executor_job(lambda: subprocess.run(
        ['bun', '-e', script], input=json.dumps({'hass': data, 'favorite': favorite.entity_id}),
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True,
    ))
    assert result.stdout.strip() != 'undefined', data
    assert json.loads(result.stdout)['releaseButton'] == release.entity_id
    if combined:
        await c.async_shutdown()
    else:
        await shutdown(c)


async def test_public_setup_imports_tempur_codec_and_profile_off_loop(hass, mock_bluetooth_service_info):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import bed_type_choice
    from tests.form_helpers import form_answers, start_new_bed

    names = {'custom_components.adjustable_bed.profiles.linak', 'custom_components.adjustable_bed.codec.linak'}
    seen = []
    main_thread = threading.get_ident()
    class Observer(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in names:
                seen.append((fullname, threading.get_ident()))
            return None
    observer = Observer()
    with patch.dict(sys.modules):
        for name in names:
            sys.modules.pop(name, None)
        sys.meta_path.insert(0, observer)
        try:
            flow = AdjustableBedConfigFlow()
            flow.hass, flow.context = hass, {'source': 'user'}
            flow._discovery_info = mock_bluetooth_service_info
            form = await start_new_bed(flow, 'picked', bed_type_choice('linak', 'tempur_relax'))
            await flow.async_step_finish_settings(form_answers(form))
        finally:
            sys.meta_path.remove(observer)
    assert {name for name, _ in seen} == names
    assert all(thread != main_thread for _, thread in seen)
