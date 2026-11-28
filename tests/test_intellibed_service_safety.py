"""Native Intellibed pair admission and shared-name recommendations."""

from types import SimpleNamespace

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles.intellibed import uuid
from custom_components.adjustable_bed.runtime_data import entry_runtime
from tests.test_intellibed import gatt


def observed(name, service="fff0"):
    return SimpleNamespace(
        name=name,
        service_uuids=[uuid(service)],
        manufacturer_data={},
        advertisement=SimpleNamespace(local_name=name),
        address="AA:BB:CC:DD:17:33",
    )


def test_shared_app_hint_does_not_question_existing_motosleep():
    # Same contract as test_simmons_app_hint_preserves_confirmed_profile.
    result = recommend_profile({"bed_type": "motosleep"}, observed("HHC-test"), {})
    assert result is None, result


async def test_paired_native_side_delivery_and_no_unsupported_parent_stop(
    hass,
    mock_coordinator_connected,
    mock_establish_connection,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    from unittest.mock import AsyncMock, MagicMock

    from bleak import BleakClient
    from bleak.backends.device import BLEDevice

    from tests.test_paired_setup import _paired_entry_data

    data = _paired_entry_data()
    data[const.CONF_BED_TYPE] = "intellibed"
    clients = {}
    for child, route in zip(data[const.CONF_PAIR_CHILDREN], ("old", "hhc"), strict=True):
        child.update(
            {
                const.CONF_BED_TYPE: "intellibed",
                const.CONF_PROTOCOL_VARIANT: route,
                const.CONF_HAS_MASSAGE: False,
                const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
            }
        )
        child.pop("capabilities", None)
        client = MagicMock(spec=BleakClient)
        client.is_connected = True
        client.services = gatt(route)
        client.write_gatt_char = AsyncMock()
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()

        async def disconnect(c=client):
            c.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        clients[child[CONF_ADDRESS]] = client

    def device(_hass, address, *args, **kwargs):
        return BLEDevice(address, "Review Intellibed", {})

    async def establish(_class, device, *args, **kwargs):
        clients[device.address].is_connected = True
        return clients[device.address]

    mock_async_ble_device_from_address.side_effect = device
    mock_establish_connection.side_effect = establish
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Review pair",
        data=data,
        unique_id=data[const.CONF_PAIR_ID],
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    pair = entry_runtime(hass, entry.entry_id)
    try:
        for child, route in zip(data[const.CONF_PAIR_CHILDREN], ("old", "hhc"), strict=True):
            for client in clients.values():
                client.write_gatt_char.reset_mock()
            eid = registry.async_get_entity_id(
                "button", const.DOMAIN, f"{child[CONF_ADDRESS]}_intellibed_{route}_head_up"
            )
            assert eid, [
                e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            ]
            await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
            assert clients[child[CONF_ADDRESS]].write_gatt_char.await_count == 1
            assert sum(client.write_gatt_char.await_count for client in clients.values()) == 1
            assert pair.children[child[const.CONF_SIDE]].controller.profile.key == route
        stop = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{data[const.CONF_PAIR_ID]}_stop_both"
        )
        if stop:
            for client in clients.values():
                client.write_gatt_char.reset_mock()
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(
                    "button", "press", {"entity_id": stop}, blocking=True
                )
            assert sum(client.write_gatt_char.await_count for client in clients.values()) == 0
        assert stop is None, f"Unsupported always-available parent STOP leaks as {stop}"
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
