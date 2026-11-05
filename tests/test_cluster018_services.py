"""Whole-target validation and command admission for app-specific settings."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.command_scheduler import CommandIntent, DeviceCommandScheduler
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services

from .test_generic_services import target


@pytest.fixture
async def resolve(hass):
    await async_register_services(hass)
    with patch('custom_components.adjustable_bed.cluster018_services._resolve_sided_targets') as resolver:
        yield resolver


async def test_second_target_rejection_prevents_first_write(hass, resolve):
    one, a = target(supports_cluster018=True, validate_cluster018_request=lambda r: None, async_execute_cluster018_request=AsyncMock())
    def reject(request):
        raise ValueError('wrong layout')
    two, b = target(supports_cluster018=True, validate_cluster018_request=reject, async_execute_cluster018_request=AsyncMock())
    resolve.return_value = ([(one, 'both'), (two, 'both')], [])
    with pytest.raises(ServiceValidationError, match='wrong layout'):
        await hass.services.async_call(DOMAIN, 'richmat_classic', {'device_id':['one','two'],'operation':'lamp_save','minutes':0}, blocking=True)
    a.async_execute_cluster018_request.assert_not_awaited()
    b.async_execute_cluster018_request.assert_not_awaited()


@pytest.mark.parametrize('operation,resource,cancel', [('query','configuration',False),('desk_recall','movement',True)])
async def test_desk_hold_uses_movement_admission_and_query_does_not(hass, resolve, operation, resource, cancel):
    coordinator, ctrl = target(supports_cluster018=True, validate_cluster018_request=lambda r: None, async_execute_cluster018_request=AsyncMock())
    resolve.return_value = ([(coordinator, 'both')], [])
    await hass.services.async_call(DOMAIN, 'richmat_classic', {'device_id':'one','operation':operation,'slot':1,'duration_ms':300}, blocking=True)
    request = ctrl.async_execute_cluster018_request.await_args.args[0]
    assert request.duration_ms == 300
    assert coordinator.async_execute_controller_command.await_args.kwargs['resource'] == resource
    assert coordinator.async_execute_controller_command.await_args.kwargs['cancel_running'] is cancel


async def test_stop_on_second_target_invalidates_its_pending_desk_hold(hass, resolve):
    first_started = asyncio.Event()
    finish_first = asyncio.Event()
    events = []

    async def first(_request):
        events.append("A starts")
        first_started.set()
        await finish_first.wait()

    async def second(_request):
        events.append("B starts")

    def scheduled_target(name, action):
        scheduler = DeviceCommandScheduler(name)
        ctrl = SimpleNamespace(supports_cluster018=True, validate_cluster018_request=lambda _request: None, async_execute_cluster018_request=action)
        coord = SimpleNamespace(name=name, capability_controller=ctrl, entry=SimpleNamespace(data={}), _command_scheduler=scheduler)

        async def execute(command, *, expected_stop_epoch=None, **_kwargs):
            async def operation(_context):
                await command(ctrl)
            await scheduler.execute(CommandIntent(operation), expected_stop_epoch=expected_stop_epoch)

        coord.async_execute_controller_command = execute
        return coord

    a = scheduled_target("A", first)
    b = scheduled_target("B", second)
    resolve.return_value = ([(a, "both"), (b, "both")], [])
    task = asyncio.create_task(hass.services.async_call(DOMAIN, "richmat_classic", {
        "device_id": ["A", "B"], "operation": "desk_recall", "slot": 1,
    }, blocking=True))
    await first_started.wait()
    epoch = b._command_scheduler.request_stop()
    b._command_scheduler.finish_stop(epoch)
    events.append("B STOP completes")
    finish_first.set()
    await task
    assert events == ["A starts", "B STOP completes"]
