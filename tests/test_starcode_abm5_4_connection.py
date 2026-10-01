"""The selected app's eight-second connection deadline reaches the BLE driver."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.address_lock import ReentrantAddressLock
from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import (
    TRANSPORTS,
    initial_fields,
)
from custom_components.adjustable_bed.bond_verification import BondVerificationStatus
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.mark.real_connect_delays
@pytest.mark.parametrize("profile", list(const.CONNECTION_PROFILES))
@pytest.mark.parametrize("bed_type", [const.BED_TYPE_STARCODE_ABM5_4, const.BED_TYPE_LINAK])
@pytest.mark.parametrize("transport", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
async def test_connection_driver_receives_exact_app_deadline_without_changing_other_profiles(
    hass, mock_coordinator_connected, mock_bleak_client, profile, bed_type, transport
):
    if bed_type == const.BED_TYPE_STARCODE_ABM5_4:
        role = TRANSPORTS[transport]
        mock_bleak_client.services = [
            MagicMock(
                uuid=role.service,
                characteristics=[
                    MagicMock(uuid=role.write, handle=1),
                    MagicMock(uuid=role.notify, handle=2),
                ],
            )
        ]
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Explicit app bed",
            const.CONF_BED_TYPE: bed_type,
            const.CONF_CONNECTION_PROFILE: profile,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
            const.CONF_STARCODE_UI_SELECTOR: "BOX15",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    settings = const.CONNECTION_PROFILES[profile]
    with (
        patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            new_callable=AsyncMock,
            return_value=mock_bleak_client,
        ) as connect,
        patch("custom_components.adjustable_bed.coordinator.asyncio.sleep", new_callable=AsyncMock),
    ):
        assert await coordinator.async_connect()
    expected = 8.0 if bed_type == const.BED_TYPE_STARCODE_ABM5_4 else settings.connection_timeout
    assert connect.await_args.kwargs["timeout"] == expected
    assert connect.await_args.kwargs["max_attempts"] == 1
    assert coordinator._max_retries == settings.max_retries
    assert coordinator._retry_base_delay == settings.retry_base_delay
    await coordinator.async_shutdown()


@pytest.mark.parametrize("request_bond", [False, True])
@pytest.mark.parametrize("bed_type", [const.BED_TYPE_STARCODE_ABM5_4, const.BED_TYPE_LINAK])
async def test_first_setup_connection_uses_selected_app_timeout(hass, request_bond, bed_type):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    address = "AA:BB:CC:DD:EE:FF"
    flow._manual_data = {CONF_ADDRESS: address, const.CONF_BED_TYPE: bed_type}
    flow.async_report_action = MagicMock()
    flow.async_report_path = MagicMock()
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    evidence = SimpleNamespace(status=BondVerificationStatus.INCONCLUSIVE, error=None)
    prefix = "custom_components.adjustable_bed.config_flow."
    with (
        patch(
            "bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)
        ) as connect,
        patch(prefix + "async_predict_path", return_value=SimpleNamespace(chosen=None)),
        patch(prefix + "async_get_connect_lock", return_value=ReentrantAddressLock()),
        patch(prefix + "client_source", return_value=None),
        patch(prefix + "async_verify_authenticated_access", new=AsyncMock(return_value=evidence)),
    ):
        assert (
            await flow._attempt_pairing_with_capture(
                address,
                request_bond=request_bond,
                track_for_flow_cleanup=False,
                device=BLEDevice(address, "Star test", {}),
                preferred_adapter="auto",
            )
            is evidence
        )
    client.disconnect.assert_awaited_once()
    expected = (
        8.0
        if bed_type == const.BED_TYPE_STARCODE_ABM5_4
        else const.CONNECTION_PROFILES[const.DEFAULT_CONNECTION_PROFILE].connection_timeout
    )
    assert connect.await_args.kwargs["timeout"] == expected
    assert connect.await_args.kwargs.get("pair", False) is request_bond


@pytest.mark.parametrize("bed_type", [const.BED_TYPE_STARCODE_ABM5_4, const.BED_TYPE_LINAK])
async def test_capability_probe_uses_selected_app_timeout(hass, bed_type):
    from tests.test_config_flow import _fake_connected_client, _patch_gate

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    client = _fake_connected_client()
    with (
        _patch_gate("hci0", -55),
        patch(
            "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
        ) as connect,
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        report = await flow._probe_capabilities("AA:BB:CC:DD:EE:FF", "auto", bed_type)
    assert report.connected
    client.disconnect.assert_awaited_once()
    assert connect.await_args.kwargs["timeout"] == (
        8.0 if bed_type == const.BED_TYPE_STARCODE_ABM5_4 else 15.0
    )


@pytest.mark.parametrize("transport", ["BOX1220", "BOX3633"])
async def test_real_reconnect_retains_only_same_address_observed_app_state(
    hass, mock_coordinator_connected, mock_bleak_client, transport
):
    role = TRANSPORTS[transport]
    mock_bleak_client.services = [
        MagicMock(
            uuid=role.service,
            characteristics=[
                MagicMock(uuid=role.write, handle=1),
                MagicMock(uuid=role.notify, handle=2),
            ],
        )
    ]
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Own app bed",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25_STAR",
            const.CONF_STARCODE_UI_SELECTOR: "BOX25_STAR",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)

    async def connect(*_args, **_kwargs):
        mock_bleak_client.is_connected = True
        return mock_bleak_client

    with (
        patch(
            "custom_components.adjustable_bed.coordinator.establish_connection",
            AsyncMock(side_effect=connect),
        ),
        patch("custom_components.adjustable_bed.coordinator.asyncio.sleep", AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.starcode_abm5_4.StarcodeAbm5_4Controller._spawn"
        ) as spawn,
    ):
        assert await coordinator.async_connect()
        original = coordinator.controller
        original._notification(
            original.client,
            original._session_generation,
            mock_bleak_client.services[0].characteristics[1],
            bytearray.fromhex("a50b0000006404030300000000002110"),
        )
        assert (
            original._massage_on,
            original._light_on,
            original._level,
            original._timer_index,
        ) == (True, True, 2, 1)
        await coordinator.async_disconnect()
        spawn.reset_mock()
        assert await coordinator.async_connect()
        replacement = coordinator.controller
        assert replacement is not original
        assert (
            replacement._massage_on,
            replacement._light_on,
            replacement._level,
            replacement._timer_index,
        ) == (True, True, 2, 1)
        # Required initialization is awaited; only the two optional operations
        # are scheduled, with no replay of the cached automatic-white callback.
        assert [call.args[0].__name__ for call in spawn.call_args_list] == [
            "classify",
            "connected_reads",
        ]
        assert replacement._raw_fields == initial_fields()
        assert not replacement._parser_state_observed
        retained_values = {
            "wave": 4,
            "head_intensity": 2,
            "low_4b": 1,
            "automatic_white_flag": True,
        }
        for key, value in retained_values.items():
            assert coordinator.controller_state["starcode_abm5_4_" + key] == value
        assert coordinator.controller_state["starcode_abm5_4_raw_53"] is None
        await replacement.adopt_transport_profile()
        assert (replacement.command_selector, replacement.ui_selector) == (transport, transport)
        replacement._require_positive()
        replacement._require_positive(light=True)
        for key, value in retained_values.items():
            assert coordinator.controller_state["starcode_abm5_4_" + key] == value
        await replacement.set_app_brightness(6)
        assert mock_bleak_client.write_gatt_char.call_args.args[1] == bytes.fromhex("04e000060000")
        await replacement.set_app_timer("10")
        await coordinator.async_shutdown()
