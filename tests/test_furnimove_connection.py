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
from tests.app_state_helpers import restart_app_state, stored_app_state


def coordinator(hass, handset="00000"):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
        CONF_FURNIMOVE_REMOTE: handset,
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
    await ctrl._async_restore_app_state(ctrl._controller)
    ctrl._controller.restore_persisted_app_state({
        "duration_minutes": 20, "running": True, "zone": "head", "intensity": 3,
    })
    expected = ctrl._controller.persisted_app_state
    assert await stored_app_state(ctrl, "12234") == expected
    ctrl._controller = FurniMoveController(ctrl, handset_id="12234")
    await ctrl._async_restore_app_state(ctrl._controller)
    assert ctrl._controller.persisted_app_state == expected
    assert not ctrl._client.write_gatt_char.called
    await restart_app_state(hass, ctrl.address)
    restarted = AdjustableBedCoordinator(hass, ctrl.entry)
    restarted._client = ctrl._client
    restarted._controller = FurniMoveController(restarted, handset_id="12234")
    await restarted._async_restore_app_state(restarted._controller)
    assert restarted._controller.persisted_app_state == expected
    assert "furnimove_ubl" not in restarted.controller_state
    await restarted._controller.async_discover_capabilities()
    restarted._controller._pause = AsyncMock(return_value=True)
    await restarted._controller.massage_toggle()
    stop = restarted._controller.profile.first("MassagerStop")
    from custom_components.adjustable_bed.beds.furnimove import build_furnimove_command

    assert written(restarted._controller) == [build_furnimove_command(stop.keycode).hex()] * 2
    assert await stored_app_state(restarted, "12234") == {"duration_minutes": 20}


async def test_invalid_local_preferences_do_not_block_connection_startup(hass):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController

    ctrl = coordinator(hass)
    ctrl._app_state_store._store.async_load = AsyncMock(
        return_value={"furnimove:auto:00000": {"duration_minutes": -1}}
    )
    ctrl._controller = FurniMoveController(ctrl, handset_id="00000")
    await ctrl._async_restore_app_state(ctrl._controller)
    assert ctrl._controller.persisted_app_state == {"duration_minutes": 15}
    assert not ctrl._client.write_gatt_char.called


@pytest.mark.parametrize("cancelled", [False, True])
async def test_widget_dispatch_history_survives_ble_handoff(hass, cancelled):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController
    from tests.test_furnimove import WRITE, char, written

    ctrl = coordinator(hass, "82417")
    ctrl._client.services = [MagicMock(characteristics=[char(WRITE)])]
    ctrl._client.write_gatt_char = AsyncMock()
    ctrl._controller = FurniMoveController(ctrl, handset_id="82417")
    first = ctrl._controller
    await first.async_discover_capabilities()
    first._pause = AsyncMock(return_value=not cancelled)
    index = next(i for i, row in enumerate(first.profile.actions) if row.action == "Flat")
    await first.async_execute_furnimove_action(index, consumer="widget")
    frame = first._frame(first.profile.actions[index], dot=False)
    release = first._frame(first.profile.first("DisobeyStandbyTime"), dot=False)
    assert ctrl.furnimove_widget_state == (True, frame, None if cancelled else frame)
    await first.stop_notify()
    ctrl._controller = None
    ctrl._client.write_gatt_char.reset_mock()
    ctrl._controller = FurniMoveController(ctrl, handset_id="82417")
    reconnected = ctrl._controller
    await reconnected.async_discover_capabilities()
    reconnected._pause = AsyncMock(return_value=True)
    await reconnected.async_execute_furnimove_action(index, consumer="widget")
    assert written(reconnected) == (
        [release.hex()] + ([] if cancelled else [frame.hex()] * 100) + [release.hex()]
    )


async def test_feedback_does_not_rearm_local_preference_save(hass):
    from custom_components.adjustable_bed.beds.furnimove import FurniMoveController

    ctrl = coordinator(hass)
    ctrl._controller = FurniMoveController(ctrl, handset_id="12234")
    await ctrl._async_restore_app_state(ctrl._controller)
    ctrl._app_state_store._store.async_delay_save = MagicMock()
    ctrl.handle_controller_state_update("furnimove_sync", True)
    ctrl._app_state_store._store.async_delay_save.assert_not_called()
    await ctrl._controller.set_massage_timer(20)
    ctrl._app_state_store._store.async_delay_save.assert_called_once()
    ctrl.handle_controller_state_update("furnimove_sync", False)
    ctrl._app_state_store._store.async_delay_save.assert_called_once()


async def test_local_duration_waits_for_command_lock_without_connecting(hass):
    ctrl = coordinator(hass, "12234")
    ctrl._client = None
    ctrl.async_ensure_connected = AsyncMock(return_value=False)
    await ctrl.async_prime_offline_controller()
    async with ctrl._command_lock:
        update = asyncio.create_task(ctrl.async_set_furnimove_massage_duration(20))
        await asyncio.sleep(0)
        assert not update.done()
        assert ctrl.capability_controller.persisted_app_state == {"duration_minutes": 15}
    await update
    assert ctrl.capability_controller.persisted_app_state == {"duration_minutes": 20}
    ctrl.async_ensure_connected.assert_not_awaited()
