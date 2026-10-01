"""Failed linked admission releases the real child idle connection lifecycle."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds import vmatbasic_protocol as protocol
from custom_components.adjustable_bed.command_scheduler import PreparedCommandInvalidated
from custom_components.adjustable_bed.paired_coordinator import PairedSideError
from tests.test_vmatbasic import written
from tests.test_vmatbasic_paired import hold, make_pair
from tests.test_vmatbasic_public import close


async def cold_pair(hass):
    pair, left, right = await make_pair(hass)
    for child in (left, right):
        client = child.client
        client.is_connected = False

        async def connect(*, reset_timer=True, child=child, client=client):
            client.is_connected = True
            if reset_timer:
                child.resume_disconnect_timer()
            return True

        async def disconnect(client=client):
            client.is_connected = False

        child._async_connect_locked = AsyncMock(side_effect=connect)
        client.disconnect = AsyncMock(side_effect=disconnect)
    return pair, left, right


async def expire_idle(child):
    assert child._disconnect_timer is not None
    child._cancel_disconnect_timer()
    await child._async_idle_disconnect()
    assert not child.is_connected
    assert child._last_disconnect_reason == "idle_timeout"


@pytest.mark.parametrize("failed_side", [const.SIDE_LEFT, const.SIDE_RIGHT])
async def test_readiness_failure_restores_idle_release_before_any_motor_write(hass, failed_side):
    pair, left, right = await cold_pair(hass)
    failed = left if failed_side == const.SIDE_LEFT else right
    failed.client.services = [
        service for service in failed.client.services if service.uuid != protocol.STATUS_SERVICE
    ]
    try:
        with pytest.raises(PairedSideError):
            await hold(pair)
        assert written(left.controller) == written(right.controller) == []
        for child in (left, right):
            child._async_connect_locked.assert_awaited_once_with(reset_timer=False)
            await expire_idle(child)
    finally:
        await close(left)
        await close(right)


@pytest.mark.parametrize("interruption", ["cancel", "mode_change", "invalidate"])
async def test_precommit_readiness_exit_restores_both_idle_lifecycles(hass, interruption):
    pair, left, right = await cold_pair(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    validate = right.controller.async_validate_linked_readiness

    async def pending_readiness():
        await validate()
        entered.set()
        await release.wait()

    right.controller.async_validate_linked_readiness = pending_readiness
    task = asyncio.create_task(hold(pair))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert left.is_connected and right.is_connected
        assert left._disconnect_timer is None and right._disconnect_timer is None
        if interruption == "cancel":
            task.cancel()
            expected = asyncio.CancelledError
        elif interruption == "mode_change":
            pair._connection_mode = const.PAIR_CONNECTION_MODE_SEQUENTIAL
            expected = ConnectionError
        else:
            left.request_command_cancel()
            expected = PreparedCommandInvalidated
        release.set()
        with pytest.raises(expected):
            await asyncio.wait_for(task, 2)
        assert written(left.controller) == written(right.controller) == []
        for child in (left, right):
            assert child._command_connection_holds == 0
            await expire_idle(child)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await close(left)
        await close(right)


async def test_repeated_cancellation_during_reservation_abort_still_restores_idle(hass):
    pair, left, right = await cold_pair(hass)
    entered, abort_entered = asyncio.Event(), asyncio.Event()
    validate = right.controller.async_validate_linked_readiness
    abort = left.async_abort_prepared_command

    async def pending_readiness():
        await validate()
        entered.set()
        await asyncio.Event().wait()

    async def pending_abort(handle):
        await abort(handle)
        abort_entered.set()
        await asyncio.Event().wait()

    right.controller.async_validate_linked_readiness = pending_readiness
    left.async_abort_prepared_command = pending_abort
    task = asyncio.create_task(hold(pair))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.wait_for(abort_entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert written(left.controller) == written(right.controller) == []
        for child in (left, right):
            assert child._command_connection_holds == 0
            await expire_idle(child)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await close(left)
        await close(right)
