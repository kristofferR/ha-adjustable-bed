"""Actual config-entry persistence, reconstruction and paired child isolation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children, const
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteSession,
    get_limoss_remote_session,
)
from custom_components.adjustable_bed.pairing import get_child
from tests.app_state_helpers import restart_app_state, stored_app_state
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_config import app_data


def actual_coordinator(hass, **extra):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(**extra))
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    coordinator._client = make_controller().client
    return coordinator


async def live_controller(coordinator) -> LimossRemoteController:
    """Create and restore a live controller the way a connection does."""
    controller = await create_controller(
        coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client
    )
    assert isinstance(controller, LimossRemoteController)
    coordinator._controller = controller
    await coordinator._async_restore_app_state(controller)
    return controller


async def restarted_controller(coordinator) -> tuple[AdjustableBedCoordinator, LimossRemoteController]:
    """Rebuild a coordinator and offline controller after a Home Assistant restart."""
    await restart_app_state(coordinator.hass, coordinator.address)
    reloaded = AdjustableBedCoordinator(coordinator.hass, coordinator.entry)
    restored = await create_controller(reloaded, const.BED_TYPE_LIMOSS_REMOTE, None, None)
    assert isinstance(restored, LimossRemoteController)
    reloaded._offline_controller = restored
    await reloaded._async_restore_app_state(restored)
    return reloaded, restored


@pytest.mark.parametrize("failure", [None, ConnectionError, TimeoutError, asyncio.CancelledError])
async def test_terminal_information_progress_survives_actual_reconstruction(hass, failure):
    coordinator = actual_coordinator(hass)
    controller = await live_controller(coordinator)
    controller.session.metadata.update(software_version="old", serial="-1")
    coordinator.save_app_state(controller)

    def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        if opcode == 1 and failure is not None:
            raise failure("software failed")
        reply = {
            2: bytes.fromhex("020c140028"),
            0: bytes.fromhex("00ff8000ff"),
            1: bytes.fromhex("0101020304"),
        }[opcode]
        controller._notification(char, bytearray(format_command(reply, 0)))

    coordinator.client.write_gatt_char = AsyncMock(side_effect=write)
    with patch.object(
        coordinator, "_async_persist_config", wraps=coordinator._async_persist_config
    ) as persist:
        if failure is None:
            await controller.refresh_device_info()
        else:
            with pytest.raises(failure):
                await controller.refresh_device_info()
    # Only the capability record, which decides the entities, is entry data.
    persist.assert_called_once()
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert set(coordinator.entry.data[const.CONF_LIMOSS_REMOTE_STATE]) == {"capabilities"}
    expected = {
        "hardware_version": "-128.0",
        "software_version": "12.34" if failure is None else "old",
        "serial": "-1",
    }
    assert (await stored_app_state(coordinator))["metadata"] == expected
    reloaded, restored = await restarted_controller(coordinator)
    assert restored.capabilities.memory_count == 8
    assert restored.protocol_diagnostics["metadata"] == expected
    assert all(
        reloaded.controller_state[f"limoss_remote_{field}"] == value
        for field, value in expected.items()
    )


async def test_actual_memory_capture_and_rename_survive_new_coordinator(hass):
    coordinator = actual_coordinator(hass)
    coordinator.remember_limoss_remote_capabilities(
        {
            "key_count": 8,
            "system": 0x12,
            "vibration": 0,
            "configuration": 0,
            "memory_count": 8,
        }
    )
    controller = await live_controller(coordinator)
    values = {0x10: -2147483648, 0x20: 2147483647}

    def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        controller._notification(
            char,
            bytearray(
                format_command(bytes((opcode,)) + values[opcode].to_bytes(4, "big", signed=True), 0)
            ),
        )

    coordinator.client.write_gatt_char = AsyncMock(side_effect=write)
    await controller.program_memory(8)
    await controller.rename_memory(8, "")
    assert controller.memories is get_limoss_remote_session(hass, coordinator.address).memories
    _reloaded, restored = await restarted_controller(coordinator)
    assert restored.memory_slot_names[-1] == ""
    assert restored.memories.slots[8].positions == ((0, -2147483648), (1, 2147483647))
    assert len(coordinator.client.write_gatt_char.await_args_list) == 2


async def test_paired_local_memory_update_changes_only_addressed_child(hass):
    left_data = app_data(**{const.CONF_SIDE: const.SIDE_LEFT})
    right_data = app_data(
        **{
            CONF_ADDRESS: "22:33:44:55:66:77",
            const.CONF_SIDE: const.SIDE_RIGHT,
            const.CONF_PRODUCT_TYPE: "chair",
        }
    )
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={const.CONF_PAIR_ID: "pair_local", const.CONF_PAIR_CHILDREN: [left_data, right_data]},
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    left, right = children[const.SIDE_LEFT], children[const.SIDE_RIGHT]
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = PairedBedCoordinator(
        hass, entry, children
    )
    before = dict(entry.data)
    for child in (left, right):
        await child.async_prime_offline_controller()
    controller = left.capability_controller
    assert isinstance(controller, LimossRemoteController)
    controller.memories.rename(8, "Left only")
    controller.session.metadata["serial"] = "-1"
    left.save_app_state(controller)
    # App state is stored per physical address; neither descriptor changes.
    assert entry.data == before
    assert (await stored_app_state(left))["memories"]["8"]["name"] == "Left only"
    assert (await stored_app_state(left))["metadata"] == {"serial": "-1"}
    assert (await stored_app_state(right))["memories"] == {}
    assert get_limoss_remote_session(hass, right.address).memories.slots == {}


async def test_invalid_capabilities_never_persist(hass):
    coordinator = actual_coordinator(hass)
    with patch.object(coordinator, "_async_persist_config") as persist, pytest.raises(ValueError):
        coordinator.remember_limoss_remote_capabilities({"key_count": 8})
    persist.assert_not_called()
    assert const.CONF_LIMOSS_REMOTE_STATE not in coordinator.entry.data


@pytest.mark.parametrize(
    "invalid",
    [
        {"unknown": {}},
        {"metadata": {"serial": 1}},
        {"memories": {"9": {"name": "", "positions": {}}}},
    ],
)
async def test_invalid_stored_app_state_restores_nothing(hass, invalid):
    session = LimossRemoteSession(metadata={"serial": "-1"})
    with pytest.raises(ValueError):
        session.restore(invalid)
    assert session.metadata == {"serial": "-1"} and session.memories.slots == {}


@pytest.mark.parametrize("cached", [False, True])
async def test_offline_capabilities_use_only_validated_cached_reply_without_ble(hass, cached):
    data = (
        {
            "capabilities": {
                "key_count": 8,
                "system": 0x12,
                "vibration": 0,
                "configuration": 0,
                "memory_count": 8,
            }
        }
        if cached
        else {}
    )
    coordinator = actual_coordinator(hass, **{const.CONF_LIMOSS_REMOTE_STATE: data})
    coordinator._client = None
    await coordinator.async_prime_offline_controller()
    controller = coordinator.capability_controller
    assert isinstance(controller, LimossRemoteController)
    assert controller.controller_entity_discovery_complete is cached
    assert controller.memory_slot_count == (8 if cached else 0)
    assert len(controller.motor_control_specs) == (2 if cached else 0)
    assert controller.protocol_diagnostics["hardware_validation"] == "unverified"


async def test_unpair_provenance_restores_latest_preferences_and_keeps_address_memories(hass):
    from custom_components.adjustable_bed.pairing import (
        build_pair_entry_data,
        single_data_from_child,
    )

    left_data = app_data()
    right_data = app_data(
        **{CONF_ADDRESS: "22:33:44:55:66:77", const.CONF_PRODUCT_TYPE: "chair"}
    )
    pair = build_pair_entry_data(
        left_data, right_data, name="Pair", left_origin_data=left_data, right_origin_data=right_data
    )
    entry = MockConfigEntry(domain=const.DOMAIN, data=pair)
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    left = children[const.SIDE_LEFT]
    await left.async_prime_offline_controller()
    controller = left.capability_controller
    assert isinstance(controller, LimossRemoteController)
    controller.memories.rename(8, "After pairing")
    left.save_app_state(controller)
    left.remember_limoss_remote_features(True, False)
    descriptor = get_child(entry.data, const.SIDE_LEFT)
    assert descriptor is not None
    restored = single_data_from_child(descriptor)
    assert restored[const.CONF_HAS_LIGHT] is True
    # Memories belong to the physical address, so unpairing keeps them as they are.
    assert const.CONF_LIMOSS_REMOTE_STATE not in restored
    assert (await stored_app_state(left))["memories"]["8"]["name"] == "After pairing"
    opposite = get_child(entry.data, const.SIDE_RIGHT)
    assert opposite is not None
    assert single_data_from_child(opposite) == right_data


@pytest.mark.parametrize("intentional", [False, True])
@pytest.mark.parametrize("connecting", [False, True])
async def test_native_disconnect_invalidates_callback_before_controller_is_cleared(
    hass, intentional, connecting
):
    coordinator = actual_coordinator(hass)
    controller = await create_controller(
        coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client
    )
    assert isinstance(controller, LimossRemoteController)
    coordinator._controller = controller
    controller.refresh_device_info = AsyncMock()
    client = coordinator.client
    assert client is not None
    role = client.services[0].characteristics[0]
    await controller.start_notify()
    callback = client.start_notify.await_args.args[1]
    reply = asyncio.get_running_loop().create_future()
    controller._request_reply = (6, reply)
    coordinator._intentional_disconnect = intentional
    coordinator._connecting = connecting
    with patch.object(coordinator, "_auto_reconnect_enabled", return_value=False):
        coordinator._on_disconnect(client)
    if connecting:
        assert coordinator.client is client and coordinator.controller is controller
    else:
        assert coordinator.client is None and coordinator.controller is None
    with pytest.raises(ConnectionError, match="notification channel stopped"):
        reply.result()
    callback(role, bytearray(format_command(bytes.fromhex("06ffffffff"), 0)))
    assert "limoss_remote_serial" not in coordinator.controller_state
    assert const.CONF_LIMOSS_REMOTE_STATE not in coordinator.entry.data
    controller._request_reply = None
    coordinator._cancel_disconnect_timer()
