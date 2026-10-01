"""VMAT runtime first-bond closure and exact native-proof gating."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
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
@pytest.mark.parametrize("verified", [False, True])
async def test_runtime_first_bond_always_closes_setup_and_unproven_rpc_is_not_a_marker(hass, verified):
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
    c.client.disconnect = AsyncMock()
    queried = 0

    async def write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            assert c.client.pair.await_count == 1
            return
        field, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        c.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    c.client.write_gatt_char.side_effect = write
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    details = {}
    with (
        patch("custom_components.adjustable_bed.coordinator.async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native if verified else unknown])),
        patch.object(coordinator, "_async_raise_pairing_issue", new=AsyncMock()),
    ):
        result = await coordinator._async_pair_on_live_link(
            details, onboarding_deadline=asyncio.get_running_loop().time() + 20,
        )
    assert result is verified
    assert queried == 7 and frames(c)[-1] == "01a7"
    c.client.disconnect.assert_awaited_once()
    assert coordinator._client is None
    assert not coordinator._intentional_disconnect
    assert details["vmat_setup_started"] is True
    assert bool(entry.data.get(const.CONF_BLE_BOND_ESTABLISHED)) is verified
    assert const.CONF_BLE_BOND_ATTEMPTED_SOURCE not in entry.data
    assert entry.data[const.CONF_VIBRADORM_APP_METADATA]["revision_string"] == "A"
