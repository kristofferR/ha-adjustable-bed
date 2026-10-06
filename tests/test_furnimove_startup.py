"""FurniMove startup ownership and entity creation after a failed initial link."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_FURNIMOVE_REMOTE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_furnimove import FEEDBACK, INFO, WRITE, char


def furnimove_entry(hass, handset="90167"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="OKIN-560024",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "OKIN-560024",
            CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
            CONF_FURNIMOVE_REMOTE: handset,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    return entry


def furnish_services(client):
    characteristics = [char(WRITE), char(FEEDBACK, ("read", "notify"))]
    characteristics += [char(uuid, ("read",)) for uuid in INFO.values()]
    service = MagicMock(uuid="62741523-52f9-8864-b1ab-3b3a8d65950b", characteristics=characteristics)
    client.services.__iter__ = lambda _: iter([service])
    client.services.__len__ = lambda _: 1
    client.read_gatt_char = AsyncMock(return_value=b"RF ECO BT")
    return characteristics


async def test_controller_owns_info_reads_after_subscription(
    hass, mock_coordinator_connected, mock_bleak_client
):
    """Issue #633: no generic DIS reads may precede the accepted app startup."""
    entry = furnimove_entry(hass)
    ctrl = AdjustableBedCoordinator(hass, entry)
    ctrl._max_retries = 1
    characteristics = furnish_services(mock_bleak_client)
    calls = []

    async def notify(characteristic, callback):
        calls.append(("notify", characteristic.uuid))

    async def read(characteristic):
        calls.append(("read", characteristic.uuid))
        return bytes(10)

    mock_bleak_client.start_notify.side_effect = notify
    mock_bleak_client.read_gatt_char.side_effect = read

    async def generic_read_loses_link(*args):
        mock_bleak_client.is_connected = False
        ctrl._client = None
        return None, None

    with patch(
        "custom_components.adjustable_bed.coordinator.read_ble_device_info",
        side_effect=generic_read_loses_link,
    ) as generic_read:
        try:
            assert await ctrl.async_connect()
            generic_read.assert_not_awaited()
            assert calls[:5] == [("notify", FEEDBACK)] + [
                ("read", characteristic.uuid) for characteristic in characteristics[2:]
            ]
        finally:
            await ctrl.async_shutdown()


@pytest.mark.parametrize("failure", ["disconnected", "timed_out"])
async def test_initial_connection_failure_loads_selected_layout_and_diagnostics(
    hass, mock_bluetooth_adapters, enable_custom_integrations, failure
):
    """A catalog-backed layout must remain usable for reconnect and support capture."""
    entry = furnimove_entry(hass)
    connect = AsyncMock(return_value=False)
    if failure == "timed_out":
        connect.side_effect = TimeoutError
    with patch.object(AdjustableBedCoordinator, "async_connect", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    ctrl = hass.data[DOMAIN][entry.entry_id]
    assert ctrl.controller is None
    assert ctrl.capability_controller.profile.handset_id == "90167"
    assert not ctrl.is_connected
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {entity.unique_id for entity in entities if entity.domain == "cover"} == {
        "AA:BB:CC:DD:EE:FF_head", "AA:BB:CC:DD:EE:FF_feet",
    }
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, "AA:BB:CC:DD:EE:FF_ble_connection")
    assert hass.services.has_service(DOMAIN, "generate_support_bundle")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unknown_layout_does_not_mint_guessed_entities(
    hass, mock_bluetooth_adapters, enable_custom_integrations
):
    entry = furnimove_entry(hass, "not-a-catalog-handset")
    with patch.object(AdjustableBedCoordinator, "async_connect", AsyncMock(return_value=False)):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


async def test_offline_entities_reconnect_on_command_without_changing_identity(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    entry = furnimove_entry(hass)
    with patch.object(AdjustableBedCoordinator, "async_connect", AsyncMock(return_value=False)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    ctrl = hass.data[DOMAIN][entry.entry_id]
    offline = ctrl.capability_controller
    registry = er.async_get(hass)
    before = {
        entity.unique_id: (entity.id, entity.entity_id, entity.device_id)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    furnish_services(mock_bleak_client)
    await ctrl.async_execute_controller_command(lambda controller: controller.lights_toggle())
    assert ctrl.is_connected
    assert ctrl.controller is not offline
    assert ctrl.capability_controller is ctrl.controller
    assert mock_bleak_client.write_gatt_char.await_count > 0
    assert before == {
        entity.unique_id: (entity.id, entity.entity_id, entity.device_id)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_timeout_cleanup_failure_does_not_load_an_orphaned_live_session(
    hass, mock_bluetooth_adapters, enable_custom_integrations
):
    entry = furnimove_entry(hass)

    async def failed_connect(ctrl):
        ctrl._client = MagicMock(is_connected=True)
        raise TimeoutError

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", failed_connect),
        patch.object(AdjustableBedCoordinator, "async_disconnect", AsyncMock(side_effect=TimeoutError)),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
