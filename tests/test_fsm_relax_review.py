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
from custom_components.adjustable_bed.beds.fsm_relax import (
    FsmRelaxController,
    build_packet,
    decode_packet,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.fsm_relax_state import FsmRelaxState
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


async def test_factory_reconnect_does_not_write_unchanged_normalized_names(
    hass: HomeAssistant,
) -> None:
    address = "AA:BB:CC:DD:EE:FF"
    names = [" Sleep "] + [""] * 7
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: address,
        const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_MEMORY_NAMES: names,
    })
    state = FsmRelaxState(hass, entry.entry_id, address)
    await state.async_load()
    await state.async_set_names(names)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch(
        "custom_components.adjustable_bed.fsm_relax_state.Store.async_save",
        AsyncMock(side_effect=OSError("redundant write")),
    ) as save:
        for _ in range(2):
            controller = await create_controller(coordinator, const.BED_TYPE_FSM_RELAX, None, None)
            assert isinstance(controller, FsmRelaxController)
            assert controller.memory_slot_names == ("Sleep", *(f"M{i}" for i in range(2, 9)))
        save.assert_not_awaited()
    with patch.object(state._store, "async_save", AsyncMock()) as save:
        await state.async_set_names(["New"] + [""] * 7)
        await state.async_set_names([" New "] + [""] * 7)
        save.assert_awaited_once()
        assert state.names[0] == "New"


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
    })
    entry.add_to_hass(hass)
    state = FsmRelaxState(hass, entry.entry_id, address)
    await state.async_load()
    await state.async_save_capabilities(bytes.fromhex("0208000008"))
    await state.async_save_serial(-1)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    coordinator._post_connect_delay = 0
    _reply_to_queries(mock_bleak_client, mock_establish_connection)
    with patch(
        "custom_components.adjustable_bed.fsm_relax_state.Store.async_save",
        AsyncMock(side_effect=OSError("redundant snapshot write")),
    ) as save:
        try:
            for _ in range(2):
                assert await coordinator.async_connect()
                controller = coordinator.controller
                assert isinstance(controller, FsmRelaxController)
                assert controller._live_capabilities
                notify = mock_bleak_client.start_notify.call_args.args[1]
                for _ in range(2):
                    notify(None, bytearray(build_packet(bytes.fromhex("06ffffffff"), 2)))
                await asyncio.gather(*tuple(controller._metadata_tasks))
                assert controller.local.serial == -1
                assert await coordinator.async_disconnect()
            assert mock_establish_connection.await_count == 2
            save.assert_not_awaited()
        finally:
            await coordinator.async_shutdown()


@pytest.mark.parametrize("action,fields", [
    ("fsm_relax_hold_control", {"control": "command_12", "duration": 0.1}),
    ("fsm_relax_recall_memory", {"preset": 1, "duration": 0.1}),
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
