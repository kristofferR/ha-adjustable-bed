"""FurniMove's advisory bond request must never gate ordinary control."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_FURNIMOVE_REMOTE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def coordinator(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_FURNIMOVE_REMOTE: "00000",
    })
    entry.add_to_hass(hass)
    result = AdjustableBedCoordinator(hass, entry)
    result._client = MagicMock()
    result._client.is_connected = True
    result._client.pair = AsyncMock()
    return result


@pytest.mark.parametrize("name,reason", [(None, "unnamed_device"), ("OkInMaT Example", "okinmat_name")])
async def test_artifact_name_bypass_does_not_request_a_bond(hass, name, reason):
    ctrl = coordinator(hass)
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, name, {}))
    assert ctrl._furnimove_bond_task is None
    ctrl._client.pair.assert_not_awaited()
    assert ctrl.pairing_diagnostics["furnimove_bond_request"]["reason"] == reason


async def test_existing_os_bond_skips_request_without_persisting_new_proof(hass):
    ctrl = coordinator(hass)
    ctrl._device_reports_existing_bond = lambda device: True
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, "OKIN-560024", {}))
    assert ctrl._furnimove_bond_task is None
    assert not ctrl.entry.data.get(CONF_BLE_BOND_ESTABLISHED)


@pytest.mark.parametrize("error,status", [
    (None, "completed"), (TimeoutError(), "timed_out"),
    (NotImplementedError(), "unsupported"),
    (BleakError("org.bluez.Error.AuthenticationFailed"), "failed"),
    (RuntimeError("backend error"), "failed"), (ValueError("backend rejected request"), "failed"),
])
async def test_optional_request_outcome_retains_link_and_never_asserts_bond(hass, error, status):
    ctrl = coordinator(hass)
    client = ctrl._client
    client.pair.side_effect = error
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, "OKIN-560024", {}))
    assert ctrl._furnimove_bond_task is not None
    await ctrl._furnimove_bond_task
    assert ctrl._client is client
    assert client.is_connected
    client.disconnect.assert_not_called()
    assert ctrl.pairing_diagnostics["furnimove_bond_request"]["status"] == status
    assert not ctrl._ble_bond_established
    assert not ctrl.entry.data.get(CONF_BLE_BOND_ESTABLISHED)
    await ctrl._async_cancel_furnimove_bond_request()
    assert ctrl._furnimove_bond_task is None


async def test_slow_request_is_background_owned_and_joined_on_cancellation(hass):
    ctrl = coordinator(hass)
    entered = asyncio.Event()
    completed = asyncio.Event()

    async def pair():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            completed.set()

    ctrl._client.pair.side_effect = pair
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, "OKIN-560024", {}))
    await entered.wait()
    assert ctrl._client.is_connected
    assert ctrl._furnimove_bond_request["status"] == "requested"
    assert not completed.is_set()
    await ctrl._async_cancel_furnimove_bond_request()
    assert completed.is_set()
    assert ctrl._furnimove_bond_task is None


async def test_old_client_completion_cannot_modify_new_client_diagnostics(hass):
    ctrl = coordinator(hass)
    old = ctrl._client
    started, release = asyncio.Event(), asyncio.Event()

    async def pair():
        started.set()
        await release.wait()

    old.pair.side_effect = pair
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, "OKIN-560024", {}))
    await started.wait()
    ctrl._client = MagicMock()
    ctrl._furnimove_bond_request = {"status": "new_generation"}
    release.set()
    assert ctrl._furnimove_bond_task is not None
    await ctrl._furnimove_bond_task
    assert ctrl._furnimove_bond_request == {"status": "new_generation"}
    await ctrl._async_cancel_furnimove_bond_request()


async def test_cancelling_bond_cleanup_propagates_to_its_caller(hass):
    ctrl = coordinator(hass)
    started, cleaning = asyncio.Event(), asyncio.Event()

    async def pair():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await asyncio.Event().wait()

    ctrl._client.pair.side_effect = pair
    ctrl._start_furnimove_bond_request(BLEDevice(ctrl.address, "OKIN-560024", {}))
    bond_task = ctrl._furnimove_bond_task
    await started.wait()
    cleanup = asyncio.create_task(ctrl._async_cancel_furnimove_bond_request())
    await cleaning.wait()
    cleanup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cleanup
    assert bond_task.done()
    assert ctrl._furnimove_bond_task is None


async def test_local_massage_state_survives_reconnect_and_home_assistant_restart(hass):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController
    from tests.test_furnimove import WRITE, char, written

    ctrl = coordinator(hass)
    hass.config_entries.async_update_entry(ctrl.entry, data={**ctrl.entry.data, CONF_FURNIMOVE_REMOTE: "12234"})
    # Construct with the selected profile's own storage key.
    ctrl = AdjustableBedCoordinator(hass, ctrl.entry)
    ctrl._client = MagicMock(is_connected=True, services=[MagicMock(characteristics=[char(WRITE)])])
    ctrl._client.write_gatt_char = AsyncMock()
    ctrl._controller = FurniMoveController(ctrl, handset_id="12234")
    await ctrl._async_restore_furnimove_local_state()
    ctrl._controller.restore_furnimove_local_state({
        "duration_minutes": 20, "running": True, "zone": "head", "intensity": 3,
    })
    expected = ctrl._controller.furnimove_local_state
    assert ctrl._furnimove_local_state == expected
    ctrl._controller = FurniMoveController(ctrl, handset_id="12234")
    await ctrl._async_restore_furnimove_local_state()
    assert ctrl._controller.furnimove_local_state == expected
    assert not ctrl._client.write_gatt_char.called
    await ctrl._furnimove_state_store.async_save(ctrl._furnimove_local_state)
    restarted = AdjustableBedCoordinator(hass, ctrl.entry)
    restarted._client = ctrl._client
    restarted._controller = FurniMoveController(restarted, handset_id="12234")
    await restarted._async_restore_furnimove_local_state()
    assert restarted._controller.furnimove_local_state == expected
    assert "furnimove_ubl" not in restarted.controller_state
    await restarted._controller.async_discover_capabilities()
    restarted._controller._pause = AsyncMock(return_value=True)
    await restarted._controller.massage_toggle()
    stop = restarted._controller.profile.first("MassagerStop")
    from custom_components.adjustable_bed.beds.furnimove import build_furnimove_command

    assert written(restarted._controller) == [build_furnimove_command(stop.keycode).hex()] * 2
    assert restarted._furnimove_local_state == {"duration_minutes": 20}


async def test_invalid_local_preferences_do_not_block_connection_startup(hass):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController

    ctrl = coordinator(hass)
    ctrl._furnimove_state_store.async_load = AsyncMock(return_value={"duration_minutes": -1})
    ctrl._controller = FurniMoveController(ctrl, handset_id="00000")
    await ctrl._async_restore_furnimove_local_state()
    assert ctrl._controller.furnimove_local_state == {"duration_minutes": 15}
    assert not ctrl._client.write_gatt_char.called
