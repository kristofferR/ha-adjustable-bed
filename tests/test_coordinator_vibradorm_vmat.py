"""VMAT runtime first-bond closure and exact native-proof gating."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.bond_verification import (
    BondEvidence,
    BondEvidenceKind,
    BondOwner,
    BondVerificationStatus,
)
from custom_components.adjustable_bed.config_flow import _vibradorm_app_data
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.vibradorm_vmat_setup import QUERY_STAGES
from tests.test_vibradorm_vmat import frames, make_vmat


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [False, True])
async def test_vmat_runtime_uses_own_45_second_budget_including_retained_native_observation(hass, retained):
    data = _vibradorm_app_data({
        CONF_ADDRESS: "11:22:33:44:55:66",
        const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_vmat("07").client
    coordinator._ble_bond_established = retained
    timeout_at = asyncio.timeout_at
    captured = []

    def capture(deadline):
        captured.append(deadline - asyncio.get_running_loop().time())
        return timeout_at(deadline)

    with (
        patch.object(coordinator, "_unverified_marker_applies", return_value=retained),
        patch.object(coordinator, "_async_observe_native_bond", new=AsyncMock(return_value=True)),
        patch("custom_components.adjustable_bed.coordinator.asyncio.timeout_at", side_effect=capture),
    ):
        assert await coordinator._async_pair_vibradorm_app(
            coordinator._client, {}, onboarding_deadline=None,
            force_pairing=False, metadata_progress={},
        )
    assert len(captured) == 1
    assert 44.0 < captured[0] <= 45.0


@pytest.mark.asyncio
@pytest.mark.parametrize(("verified", "absent"), [(False, False), (False, True), (True, False)])
@pytest.mark.parametrize("cleanup", ["normal", "close_error", "close_cancel", "task_cancel", "disconnect_error", "disconnect_cancel", "disconnect_noop", "disconnect_error_without_close_cancel", "disconnect_cancel_without_close_cancel", "disconnect_noop_after_close_cancel"])
async def test_runtime_first_bond_always_closes_setup_and_unproven_rpc_is_not_a_marker(hass, verified, absent, cleanup):
    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._connection_path = path
    c = make_vmat("07")
    coordinator._client = c.client
    c.client.pair = AsyncMock()
    disconnect_attempts = 0

    async def disconnect():
        nonlocal disconnect_attempts
        disconnect_attempts += 1
        if cleanup.startswith("disconnect_error") and disconnect_attempts == 1:
            raise BleakError("disconnect failed")
        if cleanup.startswith("disconnect_cancel") and disconnect_attempts == 1:
            raise asyncio.CancelledError
        if not cleanup.startswith("disconnect_noop"):
            c.client.is_connected = False

    c.client.disconnect = AsyncMock(side_effect=disconnect)
    queried = 0

    async def write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            assert c.client.pair.await_count == 1
            if cleanup == "close_error":
                raise BleakError("close failed")
            if cleanup == "task_cancel":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)
            if cleanup in ("close_cancel", "disconnect_error", "disconnect_cancel", "disconnect_noop_after_close_cancel"):
                raise asyncio.CancelledError
            return
        field, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        c.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    c.client.write_gatt_char.side_effect = write
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    native_absent = BondEvidence(
        BondVerificationStatus.NATIVE_ABSENT, BondOwner.from_path(path), "native", "now",
        kind=BondEvidenceKind.NATIVE_OS_STATE, error="native_bond_not_stored",
    )
    details = {}
    expected_error = (
        ConnectionError if cleanup == "disconnect_noop"
        else BleakError if cleanup == "disconnect_error_without_close_cancel"
        else asyncio.CancelledError if cleanup not in ("normal", "close_error")
        else None
    )
    with (
        patch("custom_components.adjustable_bed.coordinator.async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native if verified else native_absent if absent else unknown])),
        patch.object(coordinator, "_async_raise_pairing_issue", new=AsyncMock()),
        (pytest.raises(expected_error) if expected_error is not None else nullcontext()),
    ):
        result = await coordinator._async_pair_on_live_link(
            details, onboarding_deadline=asyncio.get_running_loop().time() + 20,
        )
        assert result is verified
    assert queried == 7 and frames(c)[-1] == "01a7"
    c.client.disconnect.assert_awaited_once()
    if cleanup.startswith("disconnect_"):
        assert coordinator._client is c.client
        assert coordinator.client.is_connected
    else:
        assert coordinator._client is None
    assert not coordinator._intentional_disconnect
    assert details["vmat_setup_started"] is True
    assert bool(entry.data.get(const.CONF_BLE_BOND_ESTABLISHED)) is verified
    assert const.CONF_BLE_BOND_ATTEMPTED_SOURCE not in entry.data
    if absent:
        assert details["native_pairing"] == "not_stored"
        assert coordinator.last_bond_evidence.proves_native_bond_absent
    assert entry.data[const.CONF_VIBRADORM_APP_METADATA]["revision_string"] == "A"


@pytest.mark.parametrize("disconnect_kind", ["noop", "error", "cancel", "task_cancel"])
@pytest.mark.parametrize("max_retries", [1, 3])
async def test_public_connect_retains_failed_setup_and_denies_reuse_replacement_and_shutdown(hass, disconnect_kind, max_retries):
    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = max_retries
    coordinator._retry_base_delay = 0
    c = make_vmat("07")
    c.client.pair = AsyncMock()
    queried = 0

    async def write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            return
        _, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        c.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    async def disconnect():
        if disconnect_kind == "error":
            raise BleakError("disconnect failed")
        if disconnect_kind == "cancel":
            raise asyncio.CancelledError
        if disconnect_kind == "task_cancel":
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            await asyncio.sleep(0)

    async def recovered_disconnect():
        c.client.is_connected = False

    c.client.write_gatt_char.side_effect = write
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    device = BLEDevice(address, "Bed", {"source": source})
    adapter = AdapterSelectionResult(device, source, -50, True, [source])
    module = "custom_components.adjustable_bed.coordinator."
    cancels = disconnect_kind in ("cancel", "task_cancel")
    try:
        with (
            patch(module + "select_adapter", return_value=adapter),
            patch(module + "async_connection_paths", return_value=()),
            patch(module + "establish_connection", new=AsyncMock(return_value=c.client)) as establish,
            patch(module + "client_source", return_value=source),
            patch(module + "async_path_for_source", return_value=path),
            patch(module + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native])) as native_probe,
            patch(module + "close_stale_connections_by_address", new=AsyncMock()),
            patch(module + "connection_reachability", return_value=None),
            patch.object(coordinator, "_async_raise_pairing_issue", new=AsyncMock()),
        ):
            with pytest.raises(asyncio.CancelledError) if cancels else nullcontext():
                assert not await coordinator.async_connect()
            assert queried == 7
            establish.assert_awaited_once()
            assert coordinator.client is c.client
            assert coordinator.is_connected
            # A stale callback without observed closure cannot release ownership.
            coordinator._on_disconnect(c.client)
            assert coordinator.client is c.client
            for connect in (coordinator.async_ensure_connected, coordinator.async_connect):
                with pytest.raises(asyncio.CancelledError) if cancels else nullcontext():
                    assert not await connect()
                establish.assert_awaited_once()
                assert coordinator.client is c.client
                assert coordinator.is_connected
            command = AsyncMock()
            if not cancels:
                with pytest.raises(ConnectionError):
                    await coordinator.async_execute_controller_command(command)
                command.assert_not_awaited()
                establish.assert_awaited_once()
                from tests.test_paired_coordinator import RecordingChild, _make

                paired_log = []
                right = RecordingChild(const.SIDE_RIGHT, paired_log, connected=False)
                pair = _make(
                    {const.SIDE_LEFT: coordinator, const.SIDE_RIGHT: right},
                    connection_mode=const.PAIR_CONNECTION_MODE_SEQUENTIAL,
                )
                assert not await pair.async_connect()
                assert paired_log == []
                establish.assert_awaited_once()
            if disconnect_kind == "noop" and max_retries == 1:
                c.client.disconnect.side_effect = recovered_disconnect
                assert await coordinator.async_disconnect()
                assert coordinator._vmat_unready_client is None
                ordinary = make_vmat("07").client

                async def ordinary_disconnect():
                    ordinary.is_connected = False

                ordinary.disconnect = AsyncMock(side_effect=ordinary_disconnect)
                establish.return_value = ordinary
                native_probe.side_effect = None
                native_probe.return_value = native
                restored_command = AsyncMock()
                await coordinator.async_execute_controller_command(
                    restored_command, skip_disconnect=True,
                    read_positions_after_operation=False,
                )
                restored_command.assert_awaited_once()
                assert establish.await_count == 2
                assert coordinator.client is ordinary
                assert coordinator.controller is not None
                assert coordinator._vmat_unready_client is None
                ordinary.write_gatt_char.assert_not_awaited()
                assert await coordinator.async_disconnect()
                return
            with pytest.raises(asyncio.CancelledError) if cancels else nullcontext():
                await coordinator.async_shutdown()
            assert coordinator.client is c.client
            assert coordinator.is_connected
            assert not await coordinator.async_ensure_connected()
            establish.assert_awaited_once()
    finally:
        c.client.disconnect.side_effect = recovered_disconnect
        await coordinator.async_disconnect()
    assert coordinator.client is None
    assert coordinator._vmat_unready_client is None


@pytest.mark.parametrize("disconnect_kind", ["noop", "error", "cancel"])
async def test_vmat_half_initialized_link_cannot_be_overwritten_before_observed_close(hass, disconnect_kind):
    entry = MockConfigEntry(domain=const.DOMAIN, data={
        CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat", const.CONF_VIBRADORM_CONTROL_TYPE: "8",
        const.CONF_VIBRADORM_VMAT_REMOTE: "07",
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client = MagicMock(is_connected=True)
    client.disconnect = AsyncMock(side_effect=(BleakError("disconnect failed") if disconnect_kind == "error" else asyncio.CancelledError() if disconnect_kind == "cancel" else None))
    with patch("custom_components.adjustable_bed.coordinator.establish_connection", new=AsyncMock()) as establish:
        with pytest.raises(asyncio.CancelledError) if disconnect_kind == "cancel" else nullcontext():
            assert not await coordinator.async_connect()
        establish.assert_not_awaited()
    assert coordinator.client is client
    assert coordinator.is_connected
    client.is_connected = False
    coordinator._on_disconnect(client)
    assert coordinator.client is None
    assert coordinator._vmat_unready_client is None
