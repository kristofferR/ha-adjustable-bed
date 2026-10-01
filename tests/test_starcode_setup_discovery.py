"""Real setup routes require explicit app identity and never request an OS bond."""

from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.bluetooth_transport import TransportClass
from custom_components.adjustable_bed.config_flow import (
    BED_TYPE_AUTO_DETECT,
    AdjustableBedConfigFlow,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_config_flow import _advance_only_progress, _fake_connected_client, _patch_gate


@pytest.mark.parametrize("route", ["manual", "focused", "show_all"])
async def test_real_app_setup_over_nonbonding_proxy_verifies_then_creates_entry(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info, route: str
) -> None:
    mock_bluetooth_service_info.name = "Star254202079996"
    mock_bluetooth_service_info.service_uuids = [const.NORDIC_UART_SERVICE_UUID]
    if route == "manual":
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "manual"}
        )
        assert result["step_id"] == "manual_entry"
    else:
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN,
            context={"source": SOURCE_BLUETOOTH},
            data=mock_bluetooth_service_info,
        )
        assert result["step_id"] == "bluetooth_disambiguate"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "bed_type_choice": "show_all"
                if route == "show_all"
                else const.BED_TYPE_STARCODE_ABM5_4
            },
        )
        assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            **({CONF_ADDRESS: mock_bluetooth_service_info.address} if route == "manual" else {}),
            CONF_NAME: "Explicit app bed",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_PREFERRED_ADAPTER: "auto",
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    assert result["step_id"] == "starcode_app"
    client = _fake_connected_client()
    client.pair = AsyncMock(side_effect=BleakError("PAIRING_NOT_SUPPORTED"))

    async def connect_without_pair(*args, **kwargs):
        assert kwargs.get("pair", False) is False
        return client

    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY),
        patch(
            "bleak_retry_connector.establish_connection",
            new=AsyncMock(side_effect=connect_without_pair),
        ) as connect,
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_setup",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
            },
        )
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        assert "Bluetooth proxy" in result["description_placeholders"]["capabilities"]
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        assert result["type"] == FlowResultType.CREATE_ENTRY
    connect.assert_awaited_once()
    client.pair.assert_not_awaited()
    client.disconnect.assert_awaited_once()
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == const.BED_TYPE_STARCODE_ABM5_4
    assert (
        data[const.CONF_STARCODE_COMMAND_SELECTOR]
        == data[const.CONF_STARCODE_UI_SELECTOR]
        == "BOX15"
    )
    assert const.CONF_BLE_BOND_ESTABLISHED not in data
    assert not const.requires_pairing(const.BED_TYPE_STARCODE_ABM5_4)
    # Use the actual runtime factory on the real flow's stored selectors.
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, None)
    assert isinstance(controller, StarcodeAbm5_4Controller)
    assert controller.command_selector == controller.ui_selector == "BOX15"
    assert controller.transport_selector == "BOX3633"
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "name,receiver",
    [
        ("Star254202079996", const.BED_TYPE_SLEEPYS_BOX25),
        ("Star352201011800", const.BED_TYPE_OKIN_CB35),
    ],
)
async def test_real_discovery_preserves_receiver_choice_and_blocks_show_all_auto_guess(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_bluetooth_service_info,
    name: str,
    receiver: str,
) -> None:
    mock_bluetooth_service_info.name = name
    mock_bluetooth_service_info.service_uuids = [const.NORDIC_UART_SERVICE_UUID]
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_disambiguate"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"bed_type_choice": receiver}
    )
    assert result["step_id"] == "bluetooth_confirm"
    schema = result["data_schema"]
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert defaults[const.CONF_BED_TYPE] == receiver
    hass.config_entries.flow.async_abort(result["flow_id"])
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"bed_type_choice": "show_all"}
    )
    schema = result["data_schema"]
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert defaults[const.CONF_BED_TYPE] == BED_TYPE_AUTO_DETECT
    rejected = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={const.CONF_BED_TYPE: BED_TYPE_AUTO_DETECT}
    )
    assert rejected["type"] == FlowResultType.FORM
    assert rejected["errors"] == {"base": "auto_detect_failed"}
    hass.config_entries.flow.async_abort(rejected["flow_id"])


async def test_unrelated_unique_receiver_still_reaches_normal_confirm(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info
) -> None:
    mock_bluetooth_service_info.name = "Linak receiver"
    mock_bluetooth_service_info.service_uuids = [const.LINAK_CONTROL_SERVICE_UUID]
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"
    schema = result["data_schema"]
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert defaults[const.CONF_BED_TYPE] == const.BED_TYPE_LINAK
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_runtime_selected_app_connects_without_bond_support(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client
) -> None:
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import TRANSPORTS

    role = TRANSPORTS["BOX3633"]
    mock_bleak_client.services = [
        MagicMock(
            uuid=role.service,
            characteristics=[
                MagicMock(uuid=role.write, handle=1, properties=["write"]),
                MagicMock(uuid=role.notify, handle=2, properties=["notify"]),
            ],
        )
    ]
    mock_bleak_client.pair = AsyncMock(side_effect=BleakError("PAIRING_NOT_SUPPORTED"))
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
            const.CONF_STARCODE_UI_SELECTOR: "BOX15",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch(
        "custom_components.adjustable_bed.coordinator.establish_connection",
        new=AsyncMock(return_value=mock_bleak_client),
    ) as connect:
        assert await coordinator.async_connect()
        assert isinstance(coordinator.controller, StarcodeAbm5_4Controller)
        assert connect.await_args.kwargs["pair"] is False
        mock_bleak_client.pair.assert_not_awaited()
        await coordinator.async_shutdown()
