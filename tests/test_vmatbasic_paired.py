"""Both physical GATT sessions are ready before the linked motor stream starts."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds import vmatbasic_protocol as protocol
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
)
from tests.test_vmatbasic import written
from tests.test_vmatbasic_public import close, target


async def make_pair(hass, mode=const.PAIR_CONNECTION_MODE_CONCURRENT):
    left = await target(hass, "cbi", "AA:BB:CC:DD:EE:01")
    right = await target(hass, "xtbox", "AA:BB:CC:DD:EE:02")
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "linked-app"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {const.SIDE_LEFT: left, const.SIDE_RIGHT: right}, connection_mode=mode
    )
    return pair, left, right


async def hold(pair, side=const.SIDE_BOTH):
    await pair.async_execute_controller_command(
        lambda ctrl: ctrl.hold_control("back_up", 100), side=side
    )


async def test_actual_pair_readiness_precedes_both_generic_controller_routes(hass):
    pair, left, right = await make_pair(hass)
    checked = []
    for child in (left, right):
        original = child.controller.async_validate_linked_readiness

        async def validate(child=child, original=original):
            await original()
            checked.append(child.address)

        child.controller.async_validate_linked_readiness = validate

        async def write(char, packet, *, response):
            assert len(checked) == 2

        child.client.write_gatt_char.side_effect = write
    try:
        await hold(pair)
        assert written(left.controller)[-1][1] == written(right.controller)[-1][1] == b"\xff"
        assert set(checked) == {left.address, right.address}
    finally:
        await close(left)
        await close(right)


@pytest.mark.parametrize("missing", protocol.REQUIRED_SERVICES)
async def test_actual_right_service_failure_prevents_every_left_movement(hass, missing):
    pair, left, right = await make_pair(hass)
    right.client.services = [
        service for service in right.client.services if service.uuid != missing
    ]
    try:
        with pytest.raises(PairedSideError):
            await hold(pair)
        assert written(left.controller) == written(right.controller) == []
        assert not left._command_lock.locked() and not right._command_lock.locked()
    finally:
        await close(left)
        await close(right)


async def test_separate_side_request_does_not_require_or_command_other_receiver(hass):
    pair, left, right = await make_pair(hass)
    right.client.services = []
    right._client.is_connected = False
    try:
        await hold(pair, const.SIDE_LEFT)
        assert written(left.controller)[-1][1] == b"\xff"
        assert written(right.controller) == []
    finally:
        await close(left)
        await close(right)


async def test_sequential_link_is_rejected_before_either_move(hass):
    pair, left, right = await make_pair(hass, const.PAIR_CONNECTION_MODE_SEQUENTIAL)
    try:
        with pytest.raises(ValueError, match="concurrent"):
            await hold(pair)
        assert written(left.controller) == written(right.controller) == []
    finally:
        await close(left)
        await close(right)


async def test_queued_link_rejects_mode_change_before_sequential_admission(hass):
    pair, left, right = await make_pair(hass)
    entered = asyncio.Event()
    acquire = pair._pair_group_lock.acquire

    async def mark_entry() -> bool:
        entered.set()
        return await acquire()

    sequential = AsyncMock()
    await pair._pair_group_lock.acquire()
    task = None
    try:
        with patch.object(pair._pair_group_lock, "acquire", mark_entry), patch.object(
            pair, "_run_both_sequential", sequential
        ):
            task = asyncio.create_task(hold(pair))
            await entered.wait()
            pair._connection_mode = const.PAIR_CONNECTION_MODE_SEQUENTIAL
            pair._pair_group_lock.release()
            with pytest.raises(ValueError, match="concurrent"):
                await task
            sequential.assert_not_awaited()
            assert written(left.controller) == written(right.controller) == []
        pair._connection_mode = const.PAIR_CONNECTION_MODE_CONCURRENT
        await hold(pair, const.SIDE_LEFT)
        assert written(left.controller)[-1][1] == b"\xff"
        assert written(right.controller) == []
    finally:
        if pair._pair_group_lock.locked():
            pair._pair_group_lock.release()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await close(left)
        await close(right)


@pytest.mark.parametrize("event", ["disconnect", "cancel", "fallback"])
async def test_readiness_interruption_never_releases_a_partial_linked_group(hass, event):
    pair, left, right = await make_pair(hass)
    entered, continue_validation = asyncio.Event(), asyncio.Event()

    async def validate():
        entered.set()
        await continue_validation.wait()
        if event == "disconnect":
            left._client.is_connected = False
        elif event == "fallback":
            pair._connection_mode = const.PAIR_CONNECTION_MODE_SEQUENTIAL

    right.controller.async_validate_linked_readiness = validate
    task = asyncio.create_task(hold(pair))
    try:
        await entered.wait()
        if event == "cancel":
            task.cancel()
        continue_validation.set()
        with pytest.raises((asyncio.CancelledError, ConnectionError)):
            await task
        assert written(left.controller) == written(right.controller) == []
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await close(left)
        await close(right)


@pytest.mark.parametrize("basic_side", [const.SIDE_LEFT, const.SIDE_RIGHT])
async def test_actual_basic_profile_never_admits_linked_motion_but_side_only_remains(
    hass, basic_side
):
    from custom_components.adjustable_bed.controller_factory import create_controller

    pair, left, right = await make_pair(hass)
    basic = left if basic_side == const.SIDE_LEFT else right
    data = {**basic.entry.data, const.CONF_VMATBASIC_PROFILE: "basic"}
    hass.config_entries.async_update_entry(basic.entry, data=data)
    basic._controller = await create_controller(
        basic, const.BED_TYPE_VMATBASIC, "auto", basic.client
    )
    try:
        with pytest.raises(PairedSideError):
            await hold(pair)
        assert written(left.controller) == written(right.controller) == []
        await hold(pair, basic_side)
        assert written(basic.controller)[-1][1] == b"\xff"
        other = right if basic_side == const.SIDE_LEFT else left
        assert written(other.controller) == []
    finally:
        await close(left)
        await close(right)
