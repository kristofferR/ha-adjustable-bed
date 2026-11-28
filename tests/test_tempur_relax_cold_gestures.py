"""Round-2 cold admission and combined gesture probes, using actual HA actions."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant.common import MockEntityPlatform

from custom_components.adjustable_bed import button, const, cover, services
from custom_components.adjustable_bed.beds.linak import controller as linak_module
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profile_id import entry_profile_id
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames
from tests.test_tempur_relax_full import paired_runtime, public_runtime


def cold_receiver(child, mask, *, peers=()):
    """Restore the configured identity and build the real controller on demand."""
    child._controller = child._offline_controller = None
    child._profile_id = entry_profile_id(child.entry.data)
    client = child.client
    client.is_connected = False
    client.services.get_service.return_value = object()
    client.read_gatt_char = AsyncMock(return_value=bytes((mask,)))

    async def connect(*_args, **_kwargs):
        assert all(not peer.is_connected for peer in peers if peer is not child)
        client.is_connected = True
        if child.controller is None:
            child._controller = await create_controller(child, 'linak', 'tempur_relax', client)
            await child._async_restore_app_state(child.controller)
            await child.controller.async_discover_capabilities()
            await child.controller.start_notify()
        return True

    child.async_connect = AsyncMock(side_effect=connect)
    child.async_ensure_connected = AsyncMock(side_effect=connect)
    return client


async def test_cold_renewable_both_rejected_before_window_routing_or_connection(hass):
    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    for child in (left, right):
        cold_receiver(child, 0xC0, peers=(left, right))
    with pytest.raises(ServiceValidationError, match='both beds connected'):
        await hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'flat', 'duration': 0.6,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True)
    assert frames(left.client) == frames(right.client) == []
    assert left.async_connect.await_count == right.async_connect.await_count == 0
    assert left.async_ensure_connected.await_count == right.async_ensure_connected.await_count == 0
    await pair.async_shutdown()


@pytest.mark.parametrize('counts', [(2, 3), (3, 2)])
async def test_native_concurrent_both_tap_has_one_admitted_refresh_plan(hass, counts):
    pair, left, right, _ = await paired_runtime(hass, mode='concurrent')
    left._motor_pulse_count, right._motor_pulse_count = counts
    left._motor_pulse_delay_ms, right._motor_pulse_delay_ms = 100, 200
    entities, ticks = [], []
    await button.async_setup_entry(hass, pair.entry, entities.extend)
    preset = next(entity for entity in entities if isinstance(entity, button.PairedBedCombinedMotorButton)
                  and entity._motor_key == 'back' and entity._direction == 'up')
    preset.hass = hass
    for side, child in [('left', left), ('right', right)]:
        async def write(_uuid, data, *, side=side, **_kwargs):
            if data == b'\x0b\x00':
                ticks.append(side)
        child.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await asyncio.wait_for(preset.async_press(), 2)
    assert ticks == ['left', 'right'] * counts[0]
    assert frames(left.client) == frames(right.client) == ['0b00'] * counts[0] + ['ff00']
    assert left.command_scheduler.active is right.command_scheduler.active is None
    await pair.async_shutdown()


@pytest.mark.parametrize('control,packet', [('flat', '0000'), ('back', '0b00')])
async def test_combined_card_gesture_release_is_single_and_never_reopens_a_link(hass, control, packet):
    pair, left, right, device = await paired_runtime(hass, mode='concurrent')
    entities = []
    await button.async_setup_entry(hass, pair.entry, entities.extend)
    preset = next(entity for entity in entities if (
        isinstance(entity, button.PairedBedCombinedButton)
        and entity.entity_description.key == 'preset_flat' and control == 'flat'
    ) or (
        isinstance(entity, button.PairedBedCombinedMotorButton)
        and entity._motor_key == 'back' and entity._direction == 'up' and control == 'back'
    ))
    release = next(entity for entity in entities if isinstance(entity, button.PairedBedGestureReleaseButton))
    assert preset.extra_state_attributes['hold_release_button_key'] == release.translation_key
    release.hass = hass
    both_written = asyncio.Event()
    right.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: both_written.set()
    # Import-executor ownership is covered separately; virtual lease time must
    # not race a real worker importing this already loaded module.
    with patch('custom_components.adjustable_bed.controller_factory._import_bed_module',
               new=AsyncMock(return_value=linak_module)), virtual_clock():
        action = 'hold_control' if control == 'flat' else 'timed_move'
        data = {'control': 'flat', 'duration': 0.6} if control == 'flat' else {
            'motor': 'back', 'direction': 'up', 'duration_ms': 600,
        }
        holding = asyncio.create_task(hass.services.async_call(const.DOMAIN, action, {
            'device_id': [device], **data,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True))
        await both_written.wait()
        await release.async_press()
        await holding
    assert frames(left.client) == frames(right.client) == [packet, 'ff00']
    connects = (left.async_ensure_connected.await_count, right.async_ensure_connected.await_count)
    for child in (left, right):
        child.client.is_connected = False
    await release.async_press()
    assert connects == (left.async_ensure_connected.await_count, right.async_ensure_connected.await_count)
    assert frames(left.client) == frames(right.client) == [packet, 'ff00']
    await hass.services.async_call(const.DOMAIN, 'stop_all', {'device_id': [device]}, blocking=True)
    assert frames(left.client) == frames(right.client) == [packet, 'ff00', 'ff00']
    await pair.async_shutdown()


@pytest.mark.parametrize('side,absent', [('both', 'both'), ('right', 'left')])
async def test_cold_explicit_stop_recovers_primary_and_uses_single_slot(hass, side, absent):
    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    cold_receiver(left, 0, peers=(left, right))
    if absent == 'both':
        cold_receiver(right, 0xC0, peers=(left, right))
    with virtual_clock():
        await hass.services.async_call(const.DOMAIN, 'stop_all', {
            'device_id': [device], 'side': side,
        }, blocking=True)
    assert left.async_ensure_connected.await_count > 0
    assert frames(right.client)[-1] == 'fe00'
    if side == 'both':
        assert frames(left.client)[-1] == 'fe00'
    assert not left.is_connected and not right.is_connected
    await pair.async_shutdown()


async def test_right_rename_has_no_primary_model_dependency(hass):
    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    left._controller = left._offline_controller = None
    left.async_connect = AsyncMock(side_effect=RuntimeError('Left unavailable'))
    left.async_ensure_connected = AsyncMock(side_effect=RuntimeError('Left unavailable'))
    right.client.read_gatt_char = AsyncMock(return_value=b'Right')
    await hass.services.async_call(const.DOMAIN, 'rename', {
        'device_id': [device], 'side': 'right', 'name': 'Right',
    }, blocking=True)
    assert frames(right.client) == [b'Right'.hex()]
    assert left.async_connect.await_count == left.async_ensure_connected.await_count == 0
    await pair.async_shutdown()


async def test_native_right_cover_stop_recovers_absent_primary_on_single_slot(hass):
    pair, left, right, _ = await paired_runtime(hass, mode='sequential')
    cold_receiver(left, 0, peers=(left, right))
    entities = []
    await cover.async_setup_entry(hass, pair.entry, entities.extend)
    back = next(entity for entity in entities if entity.entity_description.key == 'back')
    platform = MockEntityPlatform(hass, domain='cover', platform_name=const.DOMAIN)
    platform.config_entry = pair.entry
    await platform.platform_data.async_load_translations()
    await platform.async_add_entities([back])
    with virtual_clock():
        await back.async_stop_cover()
    assert left.async_ensure_connected.await_count > 0
    assert frames(right.client) == ['fe00']
    assert not left.is_connected and not right.is_connected
    await pair.async_shutdown()


@pytest.mark.parametrize("service", ["hold_control", "timed_move"])
async def test_renewable_both_rechecks_topology_after_preflight(hass, service):
    pair, left, right, device = await paired_runtime(hass, mode='auto')
    left.client.is_connected = True
    left._connection_source = 'hci0'
    original_connect = right.async_ensure_connected.side_effect

    @asynccontextmanager
    async def connection_guard(receiver):
        yield receiver.async_disconnect

    async def ensure(*args, **kwargs):
        if left.is_connected:
            right._connection_attempt_count += 1
            right._connection_attempt_details.append({'selected_source': 'hci0', 'error': 'No connection slot available'})
            raise ConnectionError('No connection slot available')
        return await original_connect(*args, **kwargs)

    right.async_ensure_connected = AsyncMock(side_effect=ensure)
    preflight_name = '_timed_move_plan' if service == 'timed_move' else '_preflight_each'
    original_plan = getattr(services, preflight_name)
    paused, resume = asyncio.Event(), asyncio.Event()
    plans = 0

    async def plan(*args, **kwargs):
        nonlocal plans
        result = await original_plan(*args, **kwargs)
        plans += 1
        if plans == (2 if service == 'timed_move' else 1):
            paused.set()
            await resume.wait()
        return result

    service_data = {'motor': 'back', 'direction': 'up', 'duration_ms': 600} if service == 'timed_move' else {'control': 'flat', 'duration': 0.6}
    try:
        with patch.object(services, preflight_name, new=plan), patch.object(type(left), 'async_connection_operation_guard', connection_guard):
            hold = asyncio.create_task(hass.services.async_call(const.DOMAIN, service, {
                'device_id': [device], **service_data, 'hold_owner': 'card', 'hold_generation': 1,
            }, blocking=True))
            await asyncio.wait_for(paused.wait(), 3)
            try:
                with pytest.raises(ConnectionError):
                    await pair.async_execute_controller_command(
                        lambda ctrl: ctrl.prepare_for_movement(), side='right', cancel_running=False,
                        resource='configuration',
                    )
                assert pair.connection_mode == 'sequential', pair.connection_mode
            finally:
                resume.set()
            result = (await asyncio.wait_for(asyncio.gather(hold, return_exceptions=True), 3))[0]
            assert frames(left.client) == frames(right.client) == [], (result, frames(left.client), frames(right.client))
            assert isinstance(result, HomeAssistantError), result
    finally:
        await pair.async_shutdown()


async def test_cold_right_stop_preempts_left_slot_owner(hass):
    pair, left, right, device = await paired_runtime(hass, mode='sequential')
    cold_receiver(right, 0xC0, peers=(left, right))
    started = asyncio.Event()
    left.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: started.set()
    with virtual_clock():
        holding = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'side': 'left', 'control': 'flat', 'duration': 1,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True))
        await asyncio.wait_for(started.wait(), 1)
        stopping = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'stop_all', {
            'device_id': [device], 'side': 'right',
        }, blocking=True))
        try:
            await asyncio.sleep(0.3)
            assert stopping.done()
            await stopping
            assert frames(right.client)[-1] == 'ff00'
            assert holding.done()
            await holding
        finally:
            await pair.async_shutdown()
            await asyncio.gather(holding, stopping, return_exceptions=True)


async def test_cold_automatic_favorite_uses_native_lease_and_outlives_expiry(hass):
    c, device = await public_runtime(hass, alarm=False)
    await c.controller.set_automatic_drive(True)
    c.client.write_gatt_char.reset_mock()
    cold_receiver(c, 0xC0)
    entered = asyncio.Event()
    c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: entered.set()
    with virtual_clock():
        holding = asyncio.create_task(hass.services.async_call(const.DOMAIN, 'hold_control', {
            'device_id': [device], 'control': 'memory_1', 'duration': 0.2,
            'hold_owner': 'card', 'hold_generation': 1,
        }, blocking=True))
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0.6)
        assert not holding.done()
        assert frames(c.client).count('0e00') >= 5
        context = c.command_scheduler.active.context
        assert context.lease is not None and context.bounded_after_lease
        await hass.services.async_call(const.DOMAIN, 'stop_all', {'device_id': [device]}, blocking=True)
        await holding
    assert frames(c.client)[-1] == 'fe00'  # Successful timer subscription in this fixture.
    c.client.is_connected = False
    await c.async_shutdown()
