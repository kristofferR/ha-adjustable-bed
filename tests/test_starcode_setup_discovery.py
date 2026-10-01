"""Real setup routes require explicit app identity and never request an OS bond."""

from unittest.mock import AsyncMock, MagicMock, patch

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

_APP_PROBE_ROLES = {
    "BOX1220": (
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001001-0000-1000-8000-00805f9b34fb",
        "00001002-0000-1000-8000-00805f9b34fb",
    ),
    "BOX3633": (
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741525-52f9-8864-b1ab-3b3a8d65950b",
        "62741625-52f9-8864-b1ab-3b3a8d65950b",
    ),
    "BOX25": (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
    "BOX25_STAR": (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
}


def _app_probe_client(selector: str) -> MagicMock:
    service, write, notify = _APP_PROBE_ROLES[selector]
    client = _fake_connected_client()
    client.services = [
        MagicMock(
            uuid=service,
            characteristics=[
                MagicMock(uuid=write, properties=["write"]),
                MagicMock(uuid=notify, properties=["notify"]),
            ],
        )
    ]
    client.write_gatt_char = AsyncMock()
    client.pair = AsyncMock()
    return client


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
    client = _app_probe_client("BOX3633")
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


@pytest.mark.parametrize("route", ["manual", "bluetooth_full_list"])
async def test_private_star2_auto_preserves_receiver_and_pulse_defaults(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info, route: str
) -> None:
    mock_bluetooth_service_info.name = "Star2 Bed"
    mock_bluetooth_service_info.service_uuids = [const.OCTO_STAR2_SERVICE_UUID]
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[mock_bluetooth_service_info],
    ):
        if route == "manual":
            result = await hass.config_entries.flow.async_init(
                const.DOMAIN, context={"source": SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={CONF_ADDRESS: "manual"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={CONF_ADDRESS: mock_bluetooth_service_info.address}
            )
            assert result["step_id"] == "manual_config"
        else:
            # Preserve a full-list choice while the scanner gains the private service.
            mock_bluetooth_service_info.service_uuids = []
            result = await hass.config_entries.flow.async_init(
                const.DOMAIN,
                context={"source": SOURCE_BLUETOOTH},
                data=mock_bluetooth_service_info,
            )
            assert result["step_id"] == "bluetooth_disambiguate"
            mock_bluetooth_service_info.service_uuids = [const.OCTO_STAR2_SERVICE_UUID]
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"bed_type_choice": "show_all"}
            )
            assert result["step_id"] == "bluetooth_confirm"
        schema = result["data_schema"]
        assert schema is not None
        defaults = schema({})
        assert isinstance(defaults, dict)
        assert defaults[const.CONF_BED_TYPE] == const.BED_TYPE_OCTO
        assert defaults[const.CONF_MOTOR_PULSE_COUNT] == "3"
        assert defaults[const.CONF_MOTOR_PULSE_DELAY_MS] == "50"
        with (
            patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
            patch(
                "homeassistant.config_entries.ConfigEntries.async_setup",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    const.CONF_BED_TYPE: BED_TYPE_AUTO_DETECT,
                    const.CONF_PROTOCOL_VARIANT: const.OCTO_VARIANT_STAR2,
                    const.CONF_DISCONNECT_AFTER_COMMAND: False,
                },
            )
            if route == "manual":
                assert result["step_id"] == "manual_octo"
                result = await hass.config_entries.flow.async_configure(
                    result["flow_id"], user_input={}
                )
            assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_OCTO
        assert result["data"][const.CONF_MOTOR_PULSE_COUNT] == 3
        assert result["data"][const.CONF_MOTOR_PULSE_DELAY_MS] == 50


@pytest.mark.parametrize("name", ["Star254202079996", "Star352201011800"])
async def test_shared_star_uart_manual_auto_requires_explicit_choice(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info, name: str
) -> None:
    mock_bluetooth_service_info.name = name
    mock_bluetooth_service_info.service_uuids = [const.NORDIC_UART_SERVICE_UUID]
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[mock_bluetooth_service_info],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "manual"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: mock_bluetooth_service_info.address}
        )
    assert result["step_id"] == "manual_config"
    schema = result["data_schema"]
    assert schema is not None
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert defaults[const.CONF_BED_TYPE] == BED_TYPE_AUTO_DETECT
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={const.CONF_BED_TYPE: BED_TYPE_AUTO_DETECT}
    )
    assert result["step_id"] == "manual_config"
    assert result["errors"] == {"base": "auto_detect_failed"}
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize("other_ambiguity", [None, const.BED_TYPE_LINAK])
def test_confident_receiver_app_hint_preserves_other_ambiguities(
    other_ambiguity: str | None,
) -> None:
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect

    alternatives = [const.BED_TYPE_STARCODE_ABM5_4]
    if other_ambiguity:
        alternatives.append(other_ambiguity)
    result = const.DetectionResult(
        bed_type=const.BED_TYPE_OCTO, confidence=1.0, signals=[], ambiguous_types=alternatives
    )
    assert _confident_auto_detect(result) == (None if other_ambiguity else const.BED_TYPE_OCTO)


@pytest.mark.parametrize("service_uuids", [None, []])
async def test_star_scan_without_service_list_keeps_name_based_chooser(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info, service_uuids
) -> None:
    mock_bluetooth_service_info.name = "Star254202079996"
    mock_bluetooth_service_info.service_uuids = service_uuids
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_disambiguate"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"bed_type_choice": const.BED_TYPE_STARCODE_ABM5_4}
    )
    assert result["step_id"] == "bluetooth_confirm"
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize("selected_transport", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
async def test_selected_app_transport_mismatch_cannot_create_entry(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_bluetooth_service_info,
    selected_transport: str,
) -> None:
    mock_bluetooth_service_info.name = "Star254202079996"
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: "manual"}
    )
    assert result["step_id"] == "manual_entry"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDRESS: mock_bluetooth_service_info.address,
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    assert result["step_id"] == "starcode_app"
    client = _fake_connected_client()
    # A live writable receiver is insufficient when the selected app roles are absent.
    client.write_gatt_char = AsyncMock()
    client.pair = AsyncMock()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)),
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
                const.CONF_STARCODE_TRANSPORT_SELECTOR: selected_transport,
            },
        )
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "starcode_app"
        assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_not_awaited()
    corrected = _app_probe_client(selected_transport)
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=corrected)),
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
            user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: selected_transport},
        )
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][const.CONF_STARCODE_TRANSPORT_SELECTOR] == selected_transport
        assert result["data"][const.CONF_STARCODE_COMMAND_SELECTOR] == "BOX15"
    corrected.disconnect.assert_awaited_once()
    corrected.write_gatt_char.assert_not_awaited()
    corrected.pair.assert_not_awaited()


@pytest.mark.parametrize("selected_transport", list(_APP_PROBE_ROLES))
@pytest.mark.parametrize("defect", [None, "write", "notify", "service"])
async def test_app_probe_requires_exact_selected_roles_without_commands(
    hass: HomeAssistant, selected_transport: str, defect: str | None
) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    client = _app_probe_client(selected_transport)
    service = client.services[0]
    if defect == "service":
        service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    elif defect:
        index = 0 if defect == "write" else 1
        service.characteristics.pop(index)
    with (
        _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY),
        patch(
            "bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)
        ) as connect,
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            new=AsyncMock(return_value=(None, None)),
        ),
    ):
        report = await flow._probe_capabilities(
            "AA:BB:CC:DD:EE:FF",
            "auto",
            const.BED_TYPE_STARCODE_ABM5_4,
            starcode_transport_selector=selected_transport,
        )
    assert report.connected
    assert report.starcode_transport_valid is (defect is None)
    assert bool(report.error) is (defect is not None)
    assert connect.await_args.kwargs.get("pair", False) is False
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_not_awaited()


@pytest.mark.parametrize("identity_source", ["saved", "observed"])
@pytest.mark.parametrize(
    "original,expected_transport", [("Star1", "BOX25"), ("BLE1", "BOX1220"), ("star1", "BOX3633")]
)
async def test_auto_app_probe_uses_original_advertisement_not_friendly_name(
    hass: HomeAssistant,
    mock_bluetooth_service_info,
    original: str,
    expected_transport: str,
    identity_source: str,
) -> None:
    from custom_components.adjustable_bed.config_flow import CapabilityReport

    mock_bluetooth_service_info.name = (
        original if identity_source == "observed" else "Star display alias"
    )
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._pending_entry = {
        CONF_ADDRESS: mock_bluetooth_service_info.address,
        CONF_NAME: "Star friendly label",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
    }
    if identity_source == "saved":
        flow._pending_entry[const.CONF_BLE_DEVICE_NAME] = original
    with patch.object(
        flow, "_probe_capabilities", new=AsyncMock(return_value=CapabilityReport(connected=True))
    ) as probe:
        await flow._async_probe_worker()
    assert probe.await_args.kwargs["starcode_transport_selector"] == expected_transport


@pytest.mark.parametrize("name", ["Unrelated receiver", None])
@pytest.mark.parametrize("service_uuids", [None, []])
def test_non_star_missing_service_list_preserves_original_detector(
    name: str | None, service_uuids
) -> None:
    from custom_components.adjustable_bed.detection import (
        _detect_bed_type_detailed,
        detect_bed_type_detailed,
    )
    from tests.test_detection import _make_service_info

    info = _make_service_info(name=name, service_uuids=[])
    info.service_uuids = service_uuids
    assert detect_bed_type_detailed(info) == _detect_bed_type_detailed(info)


@pytest.mark.parametrize(
    "original,transport", [("Star1", "BOX25"), ("BLE1", "BOX1220"), ("star1", "BOX3633")]
)
async def test_manual_address_auto_probe_uses_fresh_ble_name(
    hass: HomeAssistant, original: str, transport: str
) -> None:
    gate = _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY)
    gate._result[1].name = original
    client = _app_probe_client(transport)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    with (
        gate,
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)),
        patch(
            "custom_components.adjustable_bed.config_flow.discover_services",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            new=AsyncMock(return_value=(None, None)),
        ),
    ):
        report = await flow._probe_capabilities(
            "AA:BB:CC:DD:EE:FF", "auto", const.BED_TYPE_STARCODE_ABM5_4
        )
    assert report.starcode_transport_valid is True
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_not_awaited()
    client.disconnect.assert_awaited_once()


async def test_app_unavailable_probe_still_allows_informational_finish(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info
) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDRESS: mock_bluetooth_service_info.address,
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    assert result["step_id"] == "starcode_app"
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY),
        patch(
            "bleak_retry_connector.establish_connection",
            new=AsyncMock(side_effect=BleakError("Receiver unavailable")),
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
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220",
            },
        )
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX1220"


@pytest.mark.parametrize("original", [None, "BLE1", "Star1"])
async def test_options_auto_cannot_replace_transport_with_display_alias(
    hass: HomeAssistant, original: str | None
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Star display alias",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
        const.CONF_STARCODE_UI_SELECTOR: "BOX25",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
    }
    if original is not None:
        data[const.CONF_BLE_DEVICE_NAME] = original
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        result = await flow.async_step_settings({const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto"})
        await hass.async_block_till_done()
    if original is None:
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
        assert entry.data == data
    else:
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == (
            "BOX1220" if original == "BLE1" else "BOX25"
        )
    assert entry.data[const.CONF_STARCODE_UI_SELECTOR] == "BOX25"
    coordinator = AdjustableBedCoordinator(hass, entry)
    # BOX25's catalog needs its live manufacturer route; use the actual saved D.
    coordinator._client = _app_probe_client(entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR])
    controller = await create_controller(coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, None)
    assert isinstance(controller, StarcodeAbm5_4Controller)
    assert controller.transport_selector == entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR]
    await coordinator.async_shutdown()


@pytest.mark.parametrize("available", [False, True])
@pytest.mark.parametrize("original", [None, "BLE1"])
async def test_manual_auto_entry_factory_preserves_native_transport_identity(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_bluetooth_service_info,
    original: str | None,
    available: bool,
) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDRESS: mock_bluetooth_service_info.address,
            CONF_NAME: "Star display alias",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    assert result["step_id"] == "starcode_app"
    gate = _patch_gate("nonbonding-proxy", -60, TransportClass.PROXY)
    gate._result[1].name = original
    client = _app_probe_client("BOX1220")
    connect = (
        AsyncMock(return_value=client)
        if available
        else AsyncMock(side_effect=BleakError("Receiver unavailable"))
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        gate,
        patch("bleak_retry_connector.establish_connection", new=connect),
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
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto",
            },
        )
        result = await _advance_only_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        if original is None:
            assert result["step_id"] == "starcode_app"
            assert result["errors"] == {
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"
            }
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220"}
            )
            result = await _advance_only_progress(hass, result)
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={}
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX1220"
    assert const.CONF_BLE_BOND_ESTABLISHED not in result["data"]
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_not_awaited()
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    options = AdjustableBedOptionsFlow(entry)
    options.hass = hass
    options.handler = entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        changed = await options.async_step_settings(
            {const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto"}
        )
        await hass.async_block_till_done()
    if original is None:
        assert const.CONF_BLE_DEVICE_NAME not in entry.data
        assert changed["type"] == FlowResultType.FORM
        assert changed["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
    else:
        assert entry.data[const.CONF_BLE_DEVICE_NAME] == original
        assert changed["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX1220"
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, None)
    assert isinstance(controller, StarcodeAbm5_4Controller)
    assert controller.transport_selector == "BOX1220"
    assert controller.command_selector == controller.ui_selector == "BOX15"
    await coordinator.async_shutdown()


async def test_nameless_manual_auto_without_scanner_requires_explicit_transport(
    hass: HomeAssistant, enable_custom_integrations, mock_bluetooth_service_info
) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDRESS: mock_bluetooth_service_info.address,
            CONF_NAME: "Star display alias",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock()) as connect,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_setup",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
                const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto",
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
    connect.assert_not_awaited()
    assert const.CONF_BLE_DEVICE_NAME not in result["data"]
    assert result["data"][const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX1220"
