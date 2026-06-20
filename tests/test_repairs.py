"""Tests for the Adjustable Bed repair flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    DOMAIN,
)
from custom_components.adjustable_bed.repairs import (
    PairingRequiredRepairFlow,
    async_create_fix_flow,
)

from .conftest import TEST_ADDRESS, TEST_NAME

BLEAK_DEVICE = "custom_components.adjustable_bed.repairs.bluetooth.async_ble_device_from_address"
ESTABLISH = "bleak_retry_connector.establish_connection"


async def test_async_create_fix_flow_builds_pairing_flow(hass: HomeAssistant) -> None:
    """The factory wires issue data into the pairing repair flow."""
    flow = await async_create_fix_flow(
        hass,
        f"pairing_required_{TEST_ADDRESS.replace(':', '_').lower()}",
        {"address": TEST_ADDRESS, "name": TEST_NAME, "entry_id": "abc123"},
    )
    assert isinstance(flow, PairingRequiredRepairFlow)
    assert flow._address == TEST_ADDRESS
    assert flow._name == TEST_NAME
    assert flow._entry_id == "abc123"


async def test_confirm_step_shows_form_first(hass: HomeAssistant) -> None:
    """The first step presents the pairing instructions form."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["address"] == TEST_ADDRESS


async def test_confirm_step_resolves_on_successful_pair(hass: HomeAssistant) -> None:
    """Submitting the form resolves the issue when pairing succeeds."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch.object(flow, "_async_try_pair", new=AsyncMock(return_value=True)):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_confirm_step_aborts_on_failed_pair(hass: HomeAssistant) -> None:
    """Submitting the form aborts (issue stays) when pairing fails."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch.object(flow, "_async_try_pair", new=AsyncMock(return_value=False)):
        result = await flow.async_step_confirm({})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "pairing_failed"


async def test_try_pair_returns_false_when_device_not_in_range(hass: HomeAssistant) -> None:
    """No reachable device means pairing cannot proceed."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    with patch(BLEAK_DEVICE, return_value=None):
        assert await flow._async_try_pair() is False


async def test_try_pair_succeeds_and_clears_marker(hass: HomeAssistant) -> None:
    """A successful pair + verified read persists the bond and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_ok_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(return_value=b"Model X")
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
        patch.object(
            hass.config_entries, "async_reload", new=AsyncMock()
        ) as mock_reload,
    ):
        result = await flow._async_try_pair()

    assert result is True
    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    mock_reload.assert_awaited_once_with(entry.entry_id)
    client.disconnect.assert_awaited_once()


async def test_try_pair_treats_non_auth_read_error_as_success(hass: HomeAssistant) -> None:
    """A non-auth read failure (e.g. char absent) is inconclusive, not a failure.

    It must still persist the bond marker and reload the entry so the repair
    closes for good rather than re-triggering on the next connection.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            CONF_BED_TYPE: "okimat",
            CONF_BLE_BOND_ESTABLISHED: False,
        },
        unique_id=TEST_ADDRESS,
        entry_id="repair_inconclusive_entry",
    )
    entry.add_to_hass(hass)

    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, entry.entry_id)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(side_effect=BleakError("Characteristic not found"))
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload,
    ):
        assert await flow._async_try_pair() is True

    assert entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    mock_reload.assert_awaited_once_with(entry.entry_id)
    client.disconnect.assert_awaited_once()


async def test_try_pair_returns_false_on_auth_error(hass: HomeAssistant) -> None:
    """Pairing that connects but fails the encrypted read is treated as not paired."""
    flow = PairingRequiredRepairFlow(TEST_ADDRESS, TEST_NAME, None)
    flow.hass = hass

    client = MagicMock()
    client.read_gatt_char = AsyncMock(
        side_effect=BleakError("handle=24 error=5 description=Insufficient authentication")
    )
    client.disconnect = AsyncMock()

    with (
        patch(BLEAK_DEVICE, return_value=MagicMock()),
        patch(ESTABLISH, new=AsyncMock(return_value=client)),
    ):
        assert await flow._async_try_pair() is False

    client.disconnect.assert_awaited_once()
