"""VMAT runtime first-bond closure and exact native-proof gating."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
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
