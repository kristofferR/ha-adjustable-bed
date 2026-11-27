"""Native services preserve STOP cleanup, combination locks and reconnect admission."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.active_sleep.controller import ActiveSleepController
from custom_components.adjustable_bed.codec import active_sleep as codec
from custom_components.adjustable_bed.errors import BedCommandTimedOutError
from custom_components.adjustable_bed.runtime_data import entry_runtime
from scripts.wire_snapshot import FakeServices
from tests.test_active_sleep import Bed


@pytest.mark.parametrize("case", ["ambiguous_write", "combination_lock", "disconnected_position"])
async def test_native_route(
    case,
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    simulator = Bed()
    if case == "combination_lock":
        simulator.position = replace(simulator.position, locks=8)
    mock_bleak_client.services = FakeServices(
        {
            "services": {codec.SERVICE_UUID: [codec.CHAR_UUID]},
            "properties": {codec.CHAR_UUID: ["write", "notify"]},
        }
    )
    simulator.char = mock_bleak_client.services.get_characteristic(codec.CHAR_UUID)
    mock_bleak_client.start_notify.side_effect = simulator.subscribe
    mock_bleak_client.write_gatt_char.side_effect = simulator.write
    address = "AA:BB:CC:DD:15:96"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Active Sleep",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Active Sleep",
            const.CONF_BED_TYPE: "active_sleep",
            const.CONF_DISABLE_ANGLE_SENSING: False,
            "active_sleep_auth_id": "0123456789ABCDEF",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (const.DOMAIN, address), entry.entry_id
    )
    assert device is not None
    simulator.writes.clear()
    try:
        if case == "ambiguous_write":
            original = simulator.write

            async def fail(char, raw, **kwargs):
                if raw == codec.arrow(2):
                    simulator.writes.append(raw)
                    raise TimeoutError("synthetic backend failure after delivery")
                await original(char, raw, **kwargs)

            mock_bleak_client.write_gatt_char.side_effect = fail
            with pytest.raises(BedCommandTimedOutError):
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": [device.id], "control": "head_up", "duration": 0.1},
                    blocking=True,
                )
            assert codec.arrow(2) in simulator.writes
            assert simulator.writes[-1] == codec.arrow(0)
        elif case == "combination_lock":
            with pytest.raises(ServiceValidationError, match="locked"):
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": [device.id], "control": "combination_up", "duration": 0.1},
                    blocking=True,
                )
            assert not any(raw[0] == 0xB4 for raw in simulator.writes)
        else:
            await coordinator.async_disconnect(reason="intentional")
            assert coordinator.controller is None
            assert coordinator.capability_controller is not None
            coordinator.async_ensure_connected = AsyncMock(wraps=coordinator.async_ensure_connected)
            with patch.object(
                ActiveSleepController, "_hold_movement", new_callable=AsyncMock
            ) as move:
                await hass.services.async_call(
                    const.DOMAIN,
                    "set_position",
                    {"device_id": [device.id], "motor": "head", "position": 20},
                    blocking=True,
                )
                move.assert_awaited_once()
            coordinator.async_ensure_connected.assert_awaited()
            assert coordinator.controller is not None
            assert coordinator.controller._authenticated
    finally:
        mock_bleak_client.start_notify.side_effect = None
        mock_bleak_client.write_gatt_char.side_effect = None
        assert await hass.config_entries.async_unload(entry.entry_id)
