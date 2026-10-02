"""Real local edits and guarded entity reloads at standalone/paired boundaries."""

import asyncio
import logging
from contextlib import asynccontextmanager
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _async_update_listener, _build_paired_children, const
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.button import (
    AdjustableBedButton,
    ControllerActionButton,
    _button_entities_for,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
)
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.services import async_register_services
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_config import app_data

CAPS = {"key_count": 8, "system": 0x12, "vibration": 0, "configuration": 0, "memory_count": 8}


async def live_controller(coordinator):
    coordinator._client = make_controller().client
    coordinator._controller = await create_controller(
        coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client
    )
    controller = coordinator.controller
    assert isinstance(controller, LimossRemoteController)
    controller._sleep = AsyncMock()  # Literal wire frames, not host wall-clock pacing.
    coordinator.cache_capability_controller()
    return controller


async def pair_runtime(hass):
    data = []
    for index, side in enumerate((const.SIDE_LEFT, const.SIDE_RIGHT)):
        data.append(
            app_data(
                **{
                    CONF_ADDRESS: f"AA:BB:CC:DD:EE:{index + 1:02X}",
                    const.CONF_SIDE: side,
                    const.CONF_DISCONNECT_AFTER_COMMAND: False,
                    const.CONF_LIMOSS_REMOTE_LIGHT: True,
                    const.CONF_LIMOSS_REMOTE_MASSAGE: True,
                    const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
                }
            )
        )
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_PAIR_ID: "review_pair",
            const.CONF_PAIR_CHILDREN: data,
        },
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    pair = PairedBedCoordinator(hass, entry, children)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    controllers = {side: await live_controller(child) for side, child in children.items()}
    return pair, children, controllers


async def public_call(hass, target, service, data, side=None):
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, side or const.SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            const.DOMAIN, service, {"device_id": "review", **data}, blocking=True
        )


@pytest.mark.parametrize("paired", [False, True])
async def test_local_rename_offline_updates_real_button_states_without_reconnect(hass, paired):
    pair = None
    opposite = None
    if paired:
        pair, children, _ = await pair_runtime(hass)
        target, coordinator = pair, children[const.SIDE_LEFT]
        side = const.SIDE_LEFT
        opposite = deepcopy(get_child(pair.entry.data, const.SIDE_RIGHT))
    else:
        coordinator = actual_coordinator(
            hass, **{const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS}}
        )
        await live_controller(coordinator)
        target, side = coordinator, const.SIDE_BOTH
    coordinator.limoss_remote_memory_store.rename(8, "Before")
    buttons = [
        entity
        for entity in _button_entities_for(hass, coordinator)
        if isinstance(entity, AdjustableBedButton) and entity.entity_description.memory_slot == 8
    ]
    component = EntityComponent(logging.getLogger(__name__), "button", hass)
    await component.async_add_entities(buttons)
    client = coordinator.client
    coordinator._controller = coordinator._client = None
    with patch.object(
        coordinator,
        "async_ensure_connected",
        new=AsyncMock(side_effect=AssertionError("Local rename must not connect")),
    ) as connect:
        await public_call(
            hass, target, "limoss_remote_rename_memory", {"preset": 8, "name": "After"}, side
        )
    connect.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    assert {entity.name for entity in buttons} == {"After", "Save After"}
    for entity in buttons:
        state = hass.states.get(entity.entity_id)
        assert state is not None
        assert state.attributes["friendly_name"].endswith(entity.name)
    assert (
        coordinator.entry.data[const.CONF_LIMOSS_REMOTE_STATE]["memories"]["8"]["name"] == "After"
    )
    if paired:
        assert pair is not None
        assert get_child(pair.entry.data, const.SIDE_RIGHT) == opposite


async def test_local_rename_preflights_all_offline_capacities_before_mutating(hass):
    pair, children, _ = await pair_runtime(hass)
    children[const.SIDE_RIGHT]._controller.capabilities = type(
        children[const.SIDE_RIGHT]._controller.capabilities
    )(8, 0x12, 0, 0, 7)
    before = deepcopy(dict(pair.entry.data))
    for child in children.values():
        child._controller = child._client = None
    with pytest.raises(ServiceValidationError):
        await public_call(
            hass, pair, "limoss_remote_rename_memory", {"preset": 8, "name": "Invalid"}
        )
    assert pair.entry.data == before
    assert all(child.limoss_remote_memory_store.slots == {} for child in children.values())


@pytest.mark.parametrize("failure", [None, ConnectionError, TimeoutError])
async def test_paired_feature_flags_persist_only_after_all_off_bursts_succeed(hass, failure):
    pair, children, controllers = await pair_runtime(hass)
    before = deepcopy(dict(pair.entry.data))
    packets = {side: [] for side in children}

    def write_for(side):
        def write(char, packet, **kwargs):
            assert pair.entry.data == before  # Even after the first child finishes.
            inner = LimossController._tea_decrypt(packet[1:9])
            packets[side].append(inner[1:6])
            if side == const.SIDE_RIGHT and len(packets[side]) == 3 and failure:
                raise failure("Second OFF burst interrupted")

        return write

    for side, child in children.items():
        child.client.write_gatt_char.side_effect = write_for(side)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        if failure:
            with pytest.raises(PairedSideError) as raised:
                await public_call(
                    hass,
                    pair,
                    "limoss_remote_features",
                    {"underbed_light": False, "massage": False},
                )
            assert isinstance(raised.value.side_errors[const.SIDE_RIGHT], failure)
            for side in children:
                assert packets[side][-5:] == [bytes.fromhex("ff00000000")] * 5
            assert pair.entry.data == before
            assert all(ctrl.underbed_light and ctrl.massage for ctrl in controllers.values())
        else:
            await public_call(
                hass, pair, "limoss_remote_features", {"underbed_light": False, "massage": False}
            )
            for side in children:
                assert (
                    packets[side]
                    == [bytes.fromhex("7100000000")] * 10 + [bytes.fromhex("6600000000")] * 10
                )
                descriptor = get_child(pair.entry.data, side)
                assert descriptor[const.CONF_LIMOSS_REMOTE_LIGHT] is False
                assert descriptor[const.CONF_LIMOSS_REMOTE_MASSAGE] is False
            await hass.async_block_till_done()
        reload.assert_not_awaited()  # Connected children do not reload mid-command.


@pytest.mark.parametrize("cancel", [False, True])
async def test_side_feature_persistence_and_reload_wait_for_active_sibling_command(hass, cancel):
    pair, children, _ = await pair_runtime(hass)
    left, right = children[const.SIDE_LEFT], children[const.SIDE_RIGHT]
    entered, finish = asyncio.Event(), asyncio.Event()

    async def sibling(controller):
        entered.set()
        await finish.wait()

    command = asyncio.create_task(
        right.async_execute_controller_command(sibling, cancel_running=False, skip_disconnect=True)
    )
    await entered.wait()
    attempted = asyncio.Event()
    guard = pair.async_capability_reload_guard

    @asynccontextmanager
    async def guarded_reload():
        attempted.set()
        async with guard():
            yield

    with (
        patch.object(pair, "async_capability_reload_guard", guarded_reload),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
        ) as reload,
    ):
        previous = deepcopy(dict(pair.entry.data))
        feature = asyncio.create_task(
            public_call(
                hass,
                pair,
                "limoss_remote_features",
                {"underbed_light": False, "massage": False},
                const.SIDE_LEFT,
            )
        )
        await attempted.wait()
        assert not command.done() and not right.cancel_command.is_set()
        assert not feature.done()
        assert pair.entry.data == previous
        reload.assert_not_awaited()
        if cancel:
            feature.cancel()
            with pytest.raises(asyncio.CancelledError):
                await feature
            assert pair.entry.data == previous
            assert left.capability_controller.underbed_light
            assert left.capability_controller.massage
            assert not command.done() and not right.cancel_command.is_set()
        finish.set()
        await command
        if not cancel:
            await feature
            left._client = None
            left._schedule_pending_capability_reload()
        await hass.async_block_till_done()
        if cancel:
            reload.assert_not_awaited()
        else:
            reload.assert_awaited_once_with(pair.entry.entry_id)


async def test_changed_capability_reply_refreshes_offline_layout_and_defers_reload(hass):
    coordinator = actual_coordinator(
        hass,
        **{
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
        },
    )
    coordinator.entry.async_on_unload(coordinator.entry.add_update_listener(_async_update_listener))
    controller = await live_controller(coordinator)
    old_cache = make_controller()
    coordinator._offline_controller = old_cache
    role = coordinator.client.services[0].characteristics[0]
    refresh = next(
        entity
        for entity in _button_entities_for(hass, coordinator)
        if isinstance(entity, ControllerActionButton) and entity.unique_id.endswith("refresh_info")
    )

    def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        response = {2: "020c140004", 0: "0001020304", 1: "0101020304"}[opcode]
        controller._notification(char, bytearray(format_command(bytes.fromhex(response), 0)))

    coordinator.client.write_gatt_char.side_effect = write
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload:
        await refresh.async_press()
        await hass.async_block_till_done()
        assert coordinator.capability_controller is controller
        assert coordinator._offline_controller is controller
        assert controller.memory_slot_count == 4
        assert {
            cover.entity_description.key for cover in _cover_entities_for(hass, coordinator)
        } == {"motor_1", "motor_2", "motor_3"}
        assert not any(
            isinstance(entity, AdjustableBedButton) and entity.entity_description.memory_slot == 8
            for entity in _button_entities_for(hass, coordinator)
        )
        reload.assert_not_awaited()
        coordinator._client = coordinator._controller = None
        coordinator._schedule_pending_capability_reload()
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(coordinator.entry.entry_id)
        assert coordinator.capability_controller is controller
        assert (
            coordinator.entry.data[const.CONF_LIMOSS_REMOTE_STATE]["capabilities"]["memory_count"]
            == 4
        )
        reload.reset_mock()
        controller._notification(role, bytearray(format_command(bytes.fromhex("020c140004"), 0)))
        coordinator._schedule_pending_capability_reload()
        await hass.async_block_till_done()
        reload.assert_not_awaited()


async def test_public_paired_feature_task_cancel_preserves_flags_and_required_stop(hass):
    pair, children, controllers = await pair_runtime(hass)
    before = deepcopy(dict(pair.entry.data))
    entered = asyncio.Event()
    wait = asyncio.Event()

    async def blocked_write(char, packet, **kwargs):
        entered.set()
        await wait.wait()

    children[const.SIDE_RIGHT].client.write_gatt_char.side_effect = blocked_write
    task = asyncio.create_task(
        public_call(
            hass, pair, "limoss_remote_features", {"underbed_light": False, "massage": False}
        )
    )
    await entered.wait()
    children[const.SIDE_RIGHT].client.write_gatt_char.side_effect = None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pair.entry.data == before
    assert all(ctrl.underbed_light and ctrl.massage for ctrl in controllers.values())
    for child in children.values():
        frames = [
            LimossController._tea_decrypt(call.args[1][1:9])[1:6]
            for call in child.client.write_gatt_char.await_args_list
        ]
        assert frames[-5:] == [bytes.fromhex("ff00000000")] * 5


async def test_partial_refresh_capability_change_persists_and_reconciles_after_failure(hass):
    coordinator = actual_coordinator(
        hass,
        **{
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
        },
    )
    coordinator.entry.async_on_unload(coordinator.entry.add_update_listener(_async_update_listener))
    controller = await live_controller(coordinator)

    def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        if opcode == 0:
            raise ConnectionError("Hardware information read failed")
        controller._notification(char, bytearray(format_command(bytes.fromhex("020c140004"), 0)))

    coordinator.client.write_gatt_char.side_effect = write
    refresh = next(
        entity
        for entity in _button_entities_for(hass, coordinator)
        if isinstance(entity, ControllerActionButton) and entity.unique_id.endswith("refresh_info")
    )
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as reload:
        with pytest.raises(ConnectionError):
            await refresh.async_press()
        assert coordinator._offline_controller is controller
        assert (
            coordinator.entry.data[const.CONF_LIMOSS_REMOTE_STATE]["capabilities"]["memory_count"]
            == 4
        )
        assert coordinator._pending_capability_reload
        coordinator._client = coordinator._controller = None
        coordinator._schedule_pending_capability_reload()
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(coordinator.entry.entry_id)
