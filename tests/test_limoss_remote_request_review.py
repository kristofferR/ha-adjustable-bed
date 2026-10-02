"""Public save, paired profile and offline layout review boundaries."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.button import AdjustableBedButton, _button_entities_for
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.pairing import get_child
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote_review_lifecycle import (
    CAPS,
    live_controller,
    pair_runtime,
    public_call,
)


@pytest.mark.parametrize("blocked", ["lane", "pacing"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_public_save_ignores_registered_pre_query_pose(hass, blocked, cancel):
    coordinator = actual_coordinator(hass, **{const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS}})
    controller = await live_controller(coordinator)
    client = coordinator.client
    entered, release = asyncio.Event(), asyncio.Event()
    received = []

    # Register the real owner callback; its startup reads get actual replies.
    def startup(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        raw = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
        callback = client.start_notify.call_args.args[1]
        callback(char, bytearray(format_command(bytes.fromhex(raw), 0)))

    client.write_gatt_char.side_effect = startup
    await controller.start_notify()
    client.write_gatt_char.reset_mock()
    char, callback = client.start_notify.call_args.args

    def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        received.append(opcode)
        callback(role, bytearray(format_command(bytes((opcode, 0, 0, 0, 7)), 0)))

    client.write_gatt_char.side_effect = write
    if blocked == "pacing":
        controller._last_write_started = asyncio.get_running_loop().time()

        async def pacing(seconds, event=None):
            assert 0 < seconds <= 0.08
            entered.set()
            await release.wait()

        controller._sleep = pacing
    else:
        await controller._ble_lock.acquire()
        construct = controller._construct

        def constructed(payload, event=None):
            packet = construct(payload, event)
            entered.set()
            return packet

        controller._construct = constructed
    save = next(
        entity for entity in _button_entities_for(hass, coordinator)
        if isinstance(entity, AdjustableBedButton) and entity.entity_description.key == "program_memory_8"
    )
    operation = asyncio.create_task(save.async_press())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        # This valid owner frame arrives before the query can reach ATT.
        callback(char, bytearray(format_command(bytes.fromhex("10ffffffff"), 0)))
        assert controller._request_reply is None
        assert coordinator.limoss_remote_memory_store.slots == {}
        client.write_gatt_char.assert_not_awaited()
        with pytest.raises(RuntimeError, match="Another app"):
            await controller._request(0x20, bytes.fromhex("2000000000"))
        if cancel:
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
        else:
            release.set()
            if blocked == "lane":
                controller._ble_lock.release()
            await asyncio.wait_for(operation, 1)
            assert coordinator.limoss_remote_memory_store.slots[8].positions == ((0, 7), (1, 7))
            assert received == [0x10, 0x20]
    finally:
        release.set()
        if controller._ble_lock.locked() and blocked == "lane":
            controller._ble_lock.release()
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
    assert controller._request_reply is None and not controller._request_active
    if cancel:
        assert coordinator.limoss_remote_memory_store.slots == {}


@pytest.mark.parametrize("paired", [False, True])
async def test_public_enable_only_features_offline_never_connect_or_write(hass, paired):
    if paired:
        target, children, controllers = await pair_runtime(hass)
        coordinators = list(children.values())
        data = deepcopy(dict(target.entry.data))
        for descriptor in data[const.CONF_PAIR_CHILDREN]:
            descriptor[const.CONF_LIMOSS_REMOTE_LIGHT] = False
            descriptor[const.CONF_LIMOSS_REMOTE_MASSAGE] = False
        hass.config_entries.async_update_entry(target.entry, data=data)
        for controller in controllers.values():
            controller.underbed_light = controller.massage = False
    else:
        target = actual_coordinator(hass, **{const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS}})
        await live_controller(target)
        coordinators = [target]
    clients = [child.client for child in coordinators]
    for child in coordinators:
        child._controller = child._client = None
        child.async_ensure_connected = AsyncMock(side_effect=AssertionError("Enable-only must stay offline"))
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        await public_call(hass, target, "limoss_remote_features", {"underbed_light": True, "massage": True})
        for child, client in zip(coordinators, clients, strict=True):
            child.async_ensure_connected.assert_not_awaited()
            client.write_gatt_char.assert_not_awaited()
            assert child.capability_controller.underbed_light and child.capability_controller.massage
            assert child.entry.data[const.CONF_LIMOSS_REMOTE_LIGHT] is True
            assert child.entry.data[const.CONF_LIMOSS_REMOTE_MASSAGE] is True
        await hass.async_block_till_done()


async def test_mixed_pair_features_connect_only_receiver_requiring_off(hass):
    pair, children, controllers = await pair_runtime(hass)
    left, right = children[const.SIDE_LEFT], children[const.SIDE_RIGHT]
    controllers[const.SIDE_LEFT].underbed_light = False
    controllers[const.SIDE_LEFT].massage = False
    left._controller = left._client = None
    left.async_ensure_connected = AsyncMock(side_effect=AssertionError("This side only enables"))
    right_packets = []
    right.client.write_gatt_char.side_effect = lambda role, packet, **kwargs: right_packets.append(LimossController._tea_decrypt(packet[1:9])[1:6])
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        await public_call(hass, pair, "limoss_remote_features", {"underbed_light": True, "massage": False})
        left.async_ensure_connected.assert_not_awaited()
        assert right_packets == [bytes.fromhex("6600000000")] * 10
        assert left.entry.data[const.CONF_LIMOSS_REMOTE_LIGHT] is True
        assert right.entry.data[const.CONF_LIMOSS_REMOTE_MASSAGE] is False
        await hass.async_block_till_done()


@pytest.mark.parametrize("current", [const.BED_TYPE_LIMOSS, const.BED_TYPE_KEESON])
async def test_paired_options_reject_profile_conversion_before_entry_change(hass, current):
    children = [
        {CONF_ADDRESS: address, CONF_NAME: side, const.CONF_SIDE: side, const.CONF_BED_TYPE: current}
        for side, address in ((const.SIDE_LEFT, "11:22:33:44:55:66"), (const.SIDE_RIGHT, "11:22:33:44:55:77"))
    ]
    entry = MockConfigEntry(domain=const.DOMAIN, data={CONF_NAME: "Pair", const.CONF_BED_TYPE: current, const.CONF_PAIR_ID: "review", const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS, const.CONF_PAIR_CHILDREN: children})
    entry.add_to_hass(hass)
    before = deepcopy(dict(entry.data))
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        result = await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE})
    assert result.get("errors") == {"base": "limoss_remote_pair_settings"}
    assert entry.data == before
    reload.assert_not_awaited()


async def test_existing_pair_options_keep_bed_chair_profiles_and_shared_setting(hass):
    pair, children, _ = await pair_runtime(hass)
    descriptors = deepcopy(dict(pair.entry.data))
    descriptors[const.CONF_PAIR_CHILDREN][1][const.CONF_LIMOSS_REMOTE_PRODUCT] = "chair"
    hass.config_entries.async_update_entry(pair.entry, data=descriptors)
    before = [deepcopy(get_child(pair.entry.data, side)) for side in (const.SIDE_LEFT, const.SIDE_RIGHT)]
    flow = AdjustableBedOptionsFlow(pair.entry)
    flow.hass = hass
    flow.handler = pair.entry.entry_id
    result = await flow.async_step_settings({const.CONF_IDLE_DISCONNECT_SECONDS: 55})
    assert result["type"] == "create_entry"
    for side, previous in zip((const.SIDE_LEFT, const.SIDE_RIGHT), before, strict=True):
        updated = get_child(pair.entry.data, side)
        assert updated[const.CONF_LIMOSS_REMOTE_PRODUCT] == previous[const.CONF_LIMOSS_REMOTE_PRODUCT]
        assert updated.get(const.CONF_IDLE_DISCONNECT_SECONDS) == 55
    result = await flow.async_step_settings({const.CONF_LIMOSS_REMOTE_PRODUCT: "chair"})
    assert result.get("errors") == {"base": "limoss_remote_pair_settings"}


@pytest.mark.parametrize("cancel", [False, True])
async def test_offline_enable_waits_sibling_lane_before_any_local_edit(hass, cancel):
    from contextlib import asynccontextmanager

    pair, children, controllers = await pair_runtime(hass)
    left, right = children[const.SIDE_LEFT], children[const.SIDE_RIGHT]
    controllers[const.SIDE_LEFT].underbed_light = controllers[const.SIDE_LEFT].massage = False
    left._controller = left._client = None
    left.async_ensure_connected = AsyncMock(side_effect=AssertionError("Enable must not connect"))
    entered, finished, guarded = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def moving(controller):
        entered.set()
        await finished.wait()

    movement = asyncio.create_task(right.async_execute_controller_command(moving, cancel_running=False, skip_disconnect=True))
    await entered.wait()
    existing = pair.async_capability_reload_guard

    @asynccontextmanager
    async def guard():
        guarded.set()
        async with existing():
            yield

    before = deepcopy(dict(pair.entry.data))
    with patch.object(pair, "async_capability_reload_guard", guard), patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        feature = asyncio.create_task(public_call(hass, pair, "limoss_remote_features", {"underbed_light": True, "massage": True}, const.SIDE_LEFT))
        try:
            await asyncio.wait_for(guarded.wait(), 1)
            assert not feature.done() and not movement.done()
            assert not right.cancel_command.is_set()
            assert pair.entry.data == before
            assert not left.capability_controller.underbed_light
            assert not left.capability_controller.massage
            if cancel:
                feature.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await feature
                assert pair.entry.data == before
                assert not left.capability_controller.underbed_light
            finished.set()
            await movement
            if not cancel:
                await feature
                assert left.capability_controller.underbed_light
            left.async_ensure_connected.assert_not_awaited()
            await hass.async_block_till_done()
        finally:
            finished.set()
            feature.cancel()
            await asyncio.gather(feature, movement, return_exceptions=True)


async def test_offline_disable_still_requires_receiver_and_keeps_selection_on_failure(hass):
    coordinator = actual_coordinator(hass, **{const.CONF_LIMOSS_REMOTE_LIGHT: True, const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS}})
    controller = await live_controller(coordinator)
    client = coordinator.client
    coordinator._controller = coordinator._client = None
    before = deepcopy(dict(coordinator.entry.data))
    with (
        patch.object(coordinator, "async_ensure_connected", new=AsyncMock(return_value=False)) as connect,
        pytest.raises(ConnectionError, match="Not connected to bed"),
    ):
        await public_call(hass, coordinator, "limoss_remote_features", {"underbed_light": False, "massage": False})
    connect.assert_awaited()
    assert coordinator.entry.data == before and controller.underbed_light
    client.write_gatt_char.assert_not_awaited()


async def test_reserved_query_teardown_before_emission_never_writes():
    from tests.test_limoss_remote import make_controller

    controller = make_controller()
    entered, release = asyncio.Event(), asyncio.Event()
    controller._last_write_started = asyncio.get_running_loop().time()

    async def pacing(seconds, event=None):
        entered.set()
        await release.wait()

    controller._sleep = pacing
    operation = asyncio.create_task(controller._request(0x10, bytes.fromhex("1000000000")))
    await entered.wait()
    assert controller._request_reply is None
    controller.on_disconnect()
    release.set()
    with pytest.raises(ConnectionError, match="notification channel stopped"):
        await operation
    controller.client.write_gatt_char.assert_not_awaited()
    assert controller._request_active is None and controller._request_reply is None
