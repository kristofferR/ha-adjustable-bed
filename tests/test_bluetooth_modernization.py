"""User-triggered scans and best-effort reachability evidence."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.bluetooth_diagnostics import connection_reachability
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.redaction import redact_data


@pytest.mark.parametrize("cancel", [False, True])
async def test_explicit_scan_is_one_cancellable_progress_operation(hass, cancel):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    completed = asyncio.Event()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def scan(_hass):
        started.set()
        try:
            await completed.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch(
        "custom_components.adjustable_bed.config_flow.bluetooth.async_request_active_scan",
        side_effect=scan,
    ) as request:
        result = await flow.async_step_user({CONF_ADDRESS: "scan"})
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        task = result["progress_task"]
        assert task is not None
        await started.wait()
        again = await flow.async_step_scan()
        assert again["progress_task"] is task
        request.assert_called_once_with(hass)
        if cancel:
            flow.async_remove()
            await hass.async_block_till_done()
            assert cancelled.is_set()
        else:
            completed.set()
            await task
            result = await flow.async_step_scan()
            assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
            assert result["step_id"] == "scan_result"


def test_reachability_is_redacted_and_optional(hass):
    with patch(
        "custom_components.adjustable_bed.bluetooth_diagnostics.bluetooth.async_address_reachability_diagnostics",
        return_value="No path for AA:BB:CC:DD:EE:FF through 11:22:33:44:55:66",
    ):
        reason = connection_reachability(hass, "AA:BB:CC:DD:EE:FF")
        report = redact_data({"reachability": reason, "serial_number": "private serial"})
        assert "DD:EE:FF" not in report["reachability"]
        assert "44:55:66" not in report["reachability"]
        assert report["serial_number"] == "**REDACTED**"
    with patch(
        "custom_components.adjustable_bed.bluetooth_diagnostics.bluetooth.async_address_reachability_diagnostics",
        side_effect=RuntimeError("manager unloaded"),
    ):
        assert connection_reachability(hass, "AA:BB:CC:DD:EE:FF") is None


@pytest.mark.parametrize("phase", ["waiting_for_proxy", "after_link_established"])
async def test_cancelled_connect_releases_state_and_can_reconnect(
    hass,
    mock_config_entry,
    mock_coordinator_connected,
    mock_bleak_client,
    phase,
):
    from custom_components.adjustable_bed.address_lock import async_get_connect_lock
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    target = (
        "custom_components.adjustable_bed.coordinator_connection.establish_connection"
        if phase == "waiting_for_proxy"
        else "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info"
    )
    with patch(target, side_effect=blocked):
        task = hass.async_create_task(coordinator.async_connect())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not coordinator.is_connecting
    assert not coordinator.is_connected
    assert coordinator.client is None
    assert coordinator._disconnect_timer is None
    assert coordinator._reconnect_timer is None
    async with asyncio.timeout(1):
        async with async_get_connect_lock(hass, coordinator.address):
            pass
    if phase == "after_link_established":
        mock_bleak_client.disconnect.assert_awaited()
    assert await coordinator.async_connect()
    await coordinator.async_shutdown()


async def test_proxy_loss_during_slot_wait_records_failure_and_allows_retry(
    hass,
    mock_config_entry,
    mock_coordinator_connected,
    mock_establish_connection,
    mock_bleak_client,
):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    coordinator._max_retries = 1
    mock_establish_connection.side_effect = [
        BleakError("Proxy removed while waiting for connection slot"),
        mock_bleak_client,
    ]
    with patch(
        "custom_components.adjustable_bed.coordinator_connection.connection_reachability",
        return_value="No scanner currently reachable",
    ):
        assert not await coordinator.async_connect()
    assert not coordinator.is_connected
    assert not coordinator.is_connecting
    details = coordinator.connection_attempt_details[-1]
    assert details["error"] == "Proxy removed while waiting for connection slot"
    assert details["reachability"] == "No scanner currently reachable"
    assert await coordinator.async_connect()
    await coordinator.async_shutdown()


async def test_scan_failure_returns_to_selection_with_actionable_error(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    with patch(
        "custom_components.adjustable_bed.config_flow.bluetooth.async_request_active_scan",
        side_effect=RuntimeError("unloaded"),
    ) as request:
        result = await flow.async_step_user({CONF_ADDRESS: "scan"})
        task = result["progress_task"]
        assert task is not None
        await task
        result = await flow.async_step_scan()
        assert result["type"] == FlowResultType.SHOW_PROGRESS_DONE
        assert result["step_id"] == "scan_result"
        result = await flow.async_step_scan_result({CONF_ADDRESS: "scan"})
        request.assert_awaited_once_with(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "scan_failed"}


@pytest.mark.parametrize("found", [False, True])
async def test_scan_refreshes_candidates_and_keeps_manual_setup(
    hass,
    mock_bluetooth_service_info,
    found,
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    visible = []

    async def scan(_hass):
        if found:
            visible.append(mock_bluetooth_service_info)

    with (
        patch(
            "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
            side_effect=lambda *args, **kwargs: visible,
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.bluetooth.async_request_active_scan",
            side_effect=scan,
        ) as request,
    ):
        first = await flow.async_step_user()
        assert first["type"] == FlowResultType.FORM
        assert not flow._discovered_devices
        progress = await flow.async_step_user({CONF_ADDRESS: "scan"})
        task = progress["progress_task"]
        assert task is not None
        await task
        await flow.async_step_scan()
        refreshed = await flow.async_step_scan_result({CONF_ADDRESS: "scan"})
        assert refreshed["type"] == FlowResultType.FORM
        assert refreshed["step_id"] == "user"
        request.assert_awaited_once_with(hass)
        schema = refreshed["data_schema"]
        assert schema is not None
        assert schema({CONF_ADDRESS: "manual"}) == {CONF_ADDRESS: "manual"}
        assert bool(flow._discovered_devices) is found
        if found:
            assert schema({CONF_ADDRESS: mock_bluetooth_service_info.address})
        # A subsequent deliberate scan still starts a fresh operation.
        progress = await flow.async_step_user({CONF_ADDRESS: "scan"})
        task = progress["progress_task"]
        assert task is not None
        await task
        assert request.await_count == 2


async def test_raw_bundle_preserves_reachability_addresses_without_loaded_entry(hass):
    from unittest.mock import AsyncMock

    from custom_components.adjustable_bed.support_bundle import _build_bluetooth_section

    with (
        patch(
            "custom_components.adjustable_bed.support_bundle.connection_reachability",
            return_value="No scanner sees AA:BB:CC:DD:EE:FF",
        ),
        patch(
            "custom_components.adjustable_bed.support_bundle._build_nearby_device_inventory",
            return_value={},
        ),
        patch(
            "custom_components.adjustable_bed.support_bundle._build_scanner_status",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        section = await _build_bluetooth_section(hass, "AA:BB:CC:DD:EE:FF", {}, None)
    assert section["reachability"] == "No scanner sees AA:BB:CC:DD:EE:FF"
