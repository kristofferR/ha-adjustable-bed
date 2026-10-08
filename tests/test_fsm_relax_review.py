"""Real connection, paired platform, persistence and action-form boundaries."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
import yaml
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import button, const, services
from custom_components.adjustable_bed.app_state_store import (
    app_state_store,
    async_remove_app_states,
)
from custom_components.adjustable_bed.beds.fsm_relax import (
    FsmRelaxController,
    build_packet,
    decode_packet,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from tests.test_fsm_relax import make_controller


def _reply_to_queries(
    client: MagicMock,
    establish: AsyncMock,
    *,
    drop_first: bool = False,
) -> None:
    client.services = make_controller().client.services
    for service in client.services:
        for characteristic in service.characteristics:
            characteristic.descriptors = []
    callbacks: list[Callable[[object, bytearray], None]] = []
    query_count = 0

    async def subscribe(_role: object, callback: Callable[[object, bytearray], None]) -> None:
        callbacks.append(callback)

    async def write(_role: object, packet: bytes, **_kwargs: object) -> None:
        nonlocal query_count
        body = decode_packet(packet)
        assert body is not None
        if body[0] == 2:
            query_count += 1
            if drop_first and query_count == 1:
                client.is_connected = False
                establish.call_args.kwargs["disconnected_callback"](client)
            else:
                callbacks[-1](None, bytearray(build_packet(bytes.fromhex("0208000008"), 1)))

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.side_effect = write


async def test_initial_query_link_drop_uses_actual_coordinator_retry(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
    mock_establish_connection: AsyncMock,
) -> None:
    del mock_coordinator_connected
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 2
    coordinator._retry_base_delay = 0
    coordinator._post_connect_delay = 0
    coordinator._auto_reconnect_enabled = MagicMock(return_value=False)
    _reply_to_queries(mock_bleak_client, mock_establish_connection, drop_first=True)
    try:
        assert await coordinator.async_connect()
        assert mock_establish_connection.await_count == 2
        assert isinstance(coordinator.controller, FsmRelaxController)
        assert coordinator.controller._live_capabilities
        assert coordinator._connection_attempt_details[0]["error_type"] == "ConnectionError"
    finally:
        await coordinator.async_shutdown()


async def test_explicit_query_task_cancellation_still_propagates() -> None:
    controller = make_controller(cap=None)
    await controller.start_notify()
    sent = asyncio.Event()
    controller.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: sent.set()
    query = asyncio.create_task(controller._query(2))
    await sent.wait()
    query.cancel()
    with pytest.raises(asyncio.CancelledError):
        await query
    assert not controller._pending
    await controller.stop_notify()


async def test_offline_paired_first_capability_reloads_parent_and_action_entities(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
    mock_establish_connection: AsyncMock,
) -> None:
    del mock_coordinator_connected
    left_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX}
    right_data = {**left_data, CONF_ADDRESS: "11:22:33:44:55:66"}
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(left_data, right_data, name="Pair"))
    entry.add_to_hass(hass)
    children = {
        side: AdjustableBedCoordinator(hass, ChildEntryView(entry, descriptor, lambda _: None))
        for side, descriptor in zip(("left", "right"), entry.data[const.CONF_PAIR_CHILDREN], strict=True)
    }
    pair = PairedBedCoordinator(hass, entry, children)
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
    hass.data[const.DOMAIN] = {entry.entry_id: pair}
    left = children["left"]
    await left.async_prime_offline_controller()
    offline = left.capability_controller
    assert isinstance(offline, FsmRelaxController)
    initially_complete = offline.controller_entity_discovery_complete
    entities: list[ButtonEntity] = []

    def collect(added: Iterable[ButtonEntity], _update_before_add: bool = False) -> None:
        entities.extend(added)

    await button.async_setup_entry(hass, entry, collect)
    assert not any(isinstance(entity, button.ControllerActionButton) for entity in entities)
    _reply_to_queries(mock_bleak_client, mock_establish_connection)
    left._post_connect_delay = 0

    async def reload_parent(_entry_id: str) -> bool:
        left._offline_controller = None
        await left.async_prime_offline_controller()
        entities.clear()
        await button.async_setup_entry(hass, entry, collect)
        return True

    with patch.object(hass.config_entries, "async_reload", AsyncMock(side_effect=reload_parent)) as reload:
        try:
            assert await left.async_connect()
            assert await left.async_disconnect()
            await hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)
            assert not initially_complete
            assert isinstance(left.capability_controller, FsmRelaxController)
            assert left.capability_controller.controller_entity_discovery_complete
            assert any(isinstance(entity, button.ControllerActionButton) for entity in entities)
            assert any(
                isinstance(entity, button.AdjustableBedButton)
                and entity.entity_description.memory_slot == 8
                for entity in entities
            )
        finally:
            await left.async_shutdown()
            await children["right"].async_shutdown()


async def test_memory_names_come_from_config_without_app_state_writes(
    hass: HomeAssistant,
) -> None:
    address = "AA:BB:CC:DD:EE:FF"
    names = [" Sleep "] + [""] * 7
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address,
        const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_MEMORY_NAMES: names,
    })
    coordinator = AdjustableBedCoordinator(hass, entry)
    store = coordinator._app_state_store._store
    with (
        patch.object(store, "async_save", AsyncMock(side_effect=OSError("names are config"))) as save,
        patch.object(coordinator._app_state_store, "_schedule_save") as delay,
    ):
        for _ in range(2):
            controller = await create_controller(coordinator, const.BED_TYPE_FSM_RELAX, None, None)
            assert isinstance(controller, FsmRelaxController)
            assert controller.memory_slot_names == ("Sleep", *(f"M{i}" for i in range(2, 9)))
            assert "names" not in controller.persisted_app_state
        save.assert_not_awaited()
        delay.assert_not_called()


async def test_actual_reconnect_and_repeated_serial_skip_unchanged_storage(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
    mock_establish_connection: AsyncMock,
) -> None:
    del mock_coordinator_connected
    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        "capabilities": {"fsm_relax": "0208000008"},
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator._app_state_store.async_write(
        f"{const.BED_TYPE_FSM_RELAX}:auto", {"slots": {}, "serial": -1}
    )
    coordinator._max_retries = 1
    coordinator._post_connect_delay = 0
    _reply_to_queries(mock_bleak_client, mock_establish_connection)
    store = coordinator._app_state_store._store
    with (
        patch.object(store, "async_save", AsyncMock(side_effect=OSError("redundant write"))) as save,
        patch.object(coordinator._app_state_store, "_schedule_save") as delay,
        patch.object(coordinator, "_async_persist_config") as persist,
    ):
        try:
            for _ in range(2):
                assert await coordinator.async_connect()
                controller = coordinator.controller
                assert isinstance(controller, FsmRelaxController)
                assert controller._live_capabilities
                notify = mock_bleak_client.start_notify.call_args.args[1]
                for _ in range(2):
                    notify(None, bytearray(build_packet(bytes.fromhex("06ffffffff"), 2)))
                assert controller.session.serial == -1
                assert await coordinator.async_disconnect()
            assert mock_establish_connection.await_count == 2
            save.assert_not_awaited()
            delay.assert_not_called()
            assert not [call for call in persist.call_args_list if "capabilities" in call.args[0]
                        and call.args[0]["capabilities"] != entry.data["capabilities"]]
        finally:
            await coordinator.async_shutdown()


@pytest.mark.parametrize("action,fields", [
    ("hold_control", {"control": "command_12", "duration": 0.1}),
    ("fsm_relax_calibrate", {"confirmed": True}),
])
async def test_visual_action_side_options_match_registered_schema(
    hass: HomeAssistant, action: str, fields: dict[str, object],
) -> None:
    definitions = yaml.safe_load((Path(__file__).parents[1] / "custom_components/adjustable_bed/services.yaml").read_text())
    options = definitions[action]["fields"]["side"]["selector"]["select"]["options"]
    assert options == ["both", "left", "right"]
    await services.async_register_services(hass)
    schema = hass.services.async_services()[const.DOMAIN][action].schema
    assert schema is not None
    for side in options:
        validated = schema({"device_id": "parent", **fields, "side": side})
        assert isinstance(validated, dict)
        assert validated["side"] == side
    with pytest.raises(vol.Invalid):
        schema({"device_id": "parent", **fields, "side": "unknown"})


def _reply_to_saved_positions(client: MagicMock, establish: AsyncMock, raw: int) -> None:
    _reply_to_queries(client, establish)
    capability_reply = client.write_gatt_char.side_effect

    async def reply(role: object, packet: bytes, **kwargs: object) -> None:
        body = decode_packet(packet)
        assert body is not None
        if body[0] in (0x10, 0x20, 0x30, 0x40):
            callback = client.start_notify.call_args.args[1]
            callback(None, bytearray(build_packet(
                bytes((body[0],)) + raw.to_bytes(4, "big", signed=True), 9,
            )))
        else:
            await capability_reply(role, packet, **kwargs)

    client.write_gatt_char.side_effect = reply


async def _fire_default_handoff(hass: HomeAssistant, coordinator: AdjustableBedCoordinator) -> None:
    assert coordinator._disconnect_after_operation_enabled()
    assert coordinator._disconnect_timer is not None
    coordinator._disconnect_timer.cancel()
    coordinator._schedule_idle_disconnect()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.client is None and coordinator.controller is None


@pytest.mark.parametrize("service", ("goto_preset", "goto_preset"))
async def test_registered_save_disconnect_cached_preflight_reconnects_new_memory(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
    mock_establish_connection: AsyncMock,
    service: str,
) -> None:
    del mock_coordinator_connected
    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_MOTOR_PULSE_COUNT: 1, const.CONF_DISCONNECT_AFTER_COMMAND: True,
        "capabilities": {"fsm_relax": "0208000008"},
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._post_connect_delay = 0
    await coordinator.async_prime_offline_controller()
    offline = coordinator.capability_controller
    assert isinstance(offline, FsmRelaxController)
    assert not offline.session.slots
    _reply_to_saved_positions(mock_bleak_client, mock_establish_connection, -(2**31))
    await services.async_register_services(hass)
    try:
        with patch.object(services, "_resolve_sided_targets", return_value=(
            [(coordinator, const.SIDE_BOTH)], [],
        )):
            await hass.services.async_call(const.DOMAIN, "save_preset", {
                "device_id": "target", "preset": 8,
            }, blocking=True)
            live = coordinator.controller
            assert isinstance(live, FsmRelaxController)
            await _fire_default_handoff(hass, coordinator)
            assert coordinator.capability_controller is offline
            prior_writes = mock_bleak_client.write_gatt_char.call_count
            data: dict[str, object] = {"device_id": "target", "preset": 8}
            if service == "goto_preset":
                data["duration"] = 0.12
            await hass.services.async_call(const.DOMAIN, service, data, blocking=True)
            current = coordinator.controller
            assert isinstance(current, FsmRelaxController)
            assert current is not live and current.session is offline.session
            assert offline.session.slots[8] == dict.fromkeys(range(4), -(2**31))
            written = [decode_packet(call.args[1]) for call in
                       mock_bleak_client.write_gatt_char.call_args_list[prior_writes:]]
            assert [body for body in written if body is not None and body[0] in (0x11, 0x21, 0x31, 0x41)] == [
                bytes((opcode,)) + (-(2**31)).to_bytes(4, "big", signed=True)
                for opcode in (0x11, 0x21, 0x31, 0x41)
            ]
            assert mock_establish_connection.await_count == 2
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("service", ("goto_preset", "goto_preset"))
@pytest.mark.parametrize("side", (const.SIDE_LEFT, const.SIDE_RIGHT))
async def test_paired_save_replacement_keeps_asymmetric_target_memories(
    hass: HomeAssistant, service: str, side: str,
) -> None:
    left_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
                 const.CONF_DISCONNECT_AFTER_COMMAND: True,
                 "capabilities": {"fsm_relax": "0208000008"}}
    right_data = {**left_data, CONF_ADDRESS: "AA:BB:CC:DD:EE:02"}
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(left_data, right_data, name="Pair"))
    entry.add_to_hass(hass)
    children = {
        key: AdjustableBedCoordinator(hass, ChildEntryView(entry, descriptor, lambda _: None))
        for key, descriptor in zip((const.SIDE_LEFT, const.SIDE_RIGHT), entry.data[const.CONF_PAIR_CHILDREN], strict=True)
    }
    pair = PairedBedCoordinator(hass, entry, children)
    await services.async_register_services(hass)
    offline: dict[str, FsmRelaxController] = {}
    clients: dict[str, MagicMock] = {}
    raw_by_side = {const.SIDE_LEFT: -1, const.SIDE_RIGHT: 2**31 - 1}
    try:
        for key, target in children.items():
            await target.async_prime_offline_controller()
            cached = target.capability_controller
            assert isinstance(cached, FsmRelaxController)
            offline[key] = cached
            client = make_controller().client
            assert isinstance(client, MagicMock)
            client.disconnect = AsyncMock(side_effect=lambda c=client: setattr(c, "is_connected", False))
            clients[key] = client
            target._client = client
            controller = await create_controller(target, const.BED_TYPE_FSM_RELAX, None, client)
            assert isinstance(controller, FsmRelaxController)
            target._controller = controller
            _reply_to_saved_positions(client, AsyncMock(), raw_by_side[key])
            await controller.start_notify()
            await controller.async_discover_capabilities()
            with patch.object(services, "_resolve_sided_targets", return_value=([(pair, key)], [])):
                await hass.services.async_call(const.DOMAIN, "save_preset", {
                    "device_id": "parent", "preset": 8, "side": key,
                }, blocking=True)
            await _fire_default_handoff(hass, target)
        assert offline[const.SIDE_LEFT].session is not offline[const.SIDE_RIGHT].session
        for key in children:
            assert offline[key].session.slots[8] == dict.fromkeys(range(4), raw_by_side[key])
            clients[key].write_gatt_char.reset_mock()

        async def reconnect(**_kwargs: object) -> bool:
            target = children[side]
            client = clients[side]
            client.is_connected = True
            target._client = client
            replacement = await create_controller(target, const.BED_TYPE_FSM_RELAX, None, client)
            assert isinstance(replacement, FsmRelaxController)
            target._controller = replacement
            await replacement.start_notify()
            await replacement.async_discover_capabilities()
            return True

        data: dict[str, object] = {"device_id": "parent", "preset": 8, "side": side}
        if service == "goto_preset":
            data["duration"] = 0.12
        with (
            patch.object(services, "_resolve_sided_targets", return_value=([(pair, side)], [])),
            patch.object(children[side], "async_ensure_connected", side_effect=reconnect),
        ):
            await hass.services.async_call(const.DOMAIN, service, data, blocking=True)
        written = [decode_packet(call.args[1]) for call in clients[side].write_gatt_char.call_args_list]
        assert [body for body in written if body is not None and body[0] == 0x11] == [
            b"\x11" + raw_by_side[side].to_bytes(4, "big", signed=True),
        ]
        other_side = const.SIDE_RIGHT if side == const.SIDE_LEFT else const.SIDE_LEFT
        clients[other_side].write_gatt_char.assert_not_called()
    finally:
        for target in children.values():
            await target.async_shutdown()


async def test_factory_shared_sessions_isolate_addresses_and_end_with_removal(
    hass: HomeAssistant,
) -> None:
    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_MEMORY_NAMES: ["Sleep"] + [""] * 7,
        "capabilities": {"fsm_relax": "0202000008"},
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    old = await create_controller(coordinator, const.BED_TYPE_FSM_RELAX, None, None)
    assert isinstance(old, FsmRelaxController)
    coordinator._offline_controller = old
    await coordinator._async_restore_app_state(old)
    await old._save_slot(8, {0: -1})
    old.session.serial = -1
    assert old.memory_slot_count == 8 and old.key_count == 2
    assert old.controller_entity_discovery_complete
    assert old.protocol_diagnostics["fsm_relax_serial"] == -1
    other_entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
    })
    other = await create_controller(
        AdjustableBedCoordinator(hass, other_entry), const.BED_TYPE_FSM_RELAX, None, None
    )
    assert isinstance(other, FsmRelaxController) and other.session is not old.session
    generic = await create_controller(coordinator, const.BED_TYPE_LIMOSS, None, None)
    assert not isinstance(generic, FsmRelaxController)
    replacement_coordinator = AdjustableBedCoordinator(hass, entry)
    replacement = await create_controller(replacement_coordinator, const.BED_TYPE_FSM_RELAX, None, None)
    assert isinstance(replacement, FsmRelaxController) and replacement.session is old.session
    assert replacement.profile is not old.profile
    replacement_coordinator.remember_fsm_relax_capabilities(bytes.fromhex("0206040004"))
    replacement.session.serial = 2**31 - 1
    assert old.memory_slot_count == 4 and old.key_count == 6
    assert old.memory_slot_names[0] == "Sleep"
    assert old.protocol_diagnostics["fsm_relax_serial"] == 2**31 - 1
    assert old.protocol_diagnostics["fsm_relax_reported_memory_count"] == 4
    await async_remove_app_states(hass, [address])
    assert await app_state_store(hass, address).async_slot(f"{const.BED_TYPE_FSM_RELAX}:auto") == {}
    fresh = await create_controller(coordinator, const.BED_TYPE_FSM_RELAX, None, None)
    assert isinstance(fresh, FsmRelaxController)
    assert fresh.session is not old.session and fresh.session.slots == {}
