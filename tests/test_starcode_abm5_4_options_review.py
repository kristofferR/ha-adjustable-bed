"""Options transport changes validate only an already live receiver's exact roles."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _async_update_listener, const
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_config_flow import _open_options_form
from tests.test_starcode_setup_discovery import _app_probe_client


def runtime_entry(hass: HomeAssistant, selected: str):
    stored = "BOX3633" if selected == "BOX1220" else "BOX1220"
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_NAME: "Star friendly label",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
        const.CONF_STARCODE_UI_SELECTOR: "BOX25",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: stored,
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_DISABLE_ANGLE_SENSING: True,
    }
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _app_probe_client(stored)
    client.read_gatt_char = AsyncMock()
    coordinator._client = client
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return entry, coordinator, client


@pytest.mark.parametrize("selected", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
@pytest.mark.parametrize("defect", ["service", "write", "notify"])
async def test_public_options_live_transport_mismatch_leaves_entry_and_reload_untouched(
    hass: HomeAssistant, enable_custom_integrations, selected: str, defect: str
) -> None:
    entry, _, client = runtime_entry(hass, selected)
    selected_role = _app_probe_client(selected).services[0]
    if defect == "service":
        selected_role.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    else:
        selected_role.characteristics.pop(0 if defect == "write" else 1)
    client.services.append(selected_role)
    data, options = dict(entry.data), dict(entry.options)
    with (
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload,
        patch("bleak_retry_connector.establish_connection", new=AsyncMock()) as connect,
    ):
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: selected}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "settings"
    assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
    assert entry.data == data and entry.options == options
    reload.assert_not_awaited()
    connect.assert_not_awaited()
    client.pair.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_not_awaited()


@pytest.mark.parametrize("selected", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
async def test_public_options_compatible_transport_saves_without_BLE_operations(
    hass: HomeAssistant, enable_custom_integrations, selected: str
) -> None:
    entry, _, client = runtime_entry(hass, selected)
    client.services.extend(_app_probe_client(selected).services)
    with (
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload,
        patch("bleak_retry_connector.establish_connection", new=AsyncMock()) as connect,
    ):
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: selected}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == selected
    assert entry.data[const.CONF_STARCODE_UI_SELECTOR] == "BOX25"
    reload.assert_awaited_once()
    connect.assert_not_awaited()
    client.pair.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.read_gatt_char.assert_not_awaited()
    client.disconnect.assert_not_awaited()


@pytest.mark.parametrize(
    "original,selected", [("BLE1", "BOX1220"), ("Star1", "BOX25"), ("star1", "BOX3633")]
)
@pytest.mark.parametrize("compatible", [False, True])
async def test_public_options_Auto_checks_original_name_resolved_transport(
    hass: HomeAssistant, enable_custom_integrations, original: str, selected: str, compatible: bool
) -> None:
    entry, _, client = runtime_entry(hass, selected)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, const.CONF_BLE_DEVICE_NAME: original}
        )
        await hass.async_block_till_done()
    if compatible:
        client.services.extend(_app_probe_client(selected).services)
    data = dict(entry.data)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto"}
        )
        await hass.async_block_till_done()
    if compatible:
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == selected
        assert entry.data[const.CONF_BLE_DEVICE_NAME] == original
        reload.assert_awaited_once()
    else:
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
        assert entry.data == data
        reload.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_not_awaited()


async def test_public_options_unknown_Auto_does_not_use_alias_or_live_service_as_identity(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry, _, client = runtime_entry(hass, "BOX25")
    client.services.extend(_app_probe_client("BOX25").services)
    data = dict(entry.data)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "auto"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {const.CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"}
    assert entry.data == data
    reload.assert_not_awaited()


@pytest.mark.parametrize(
    "unavailable", ["runtime", "client", "disconnected", "services", "discovery_pending"]
)
async def test_public_options_unavailable_GATT_is_unverified_without_reconnect(
    hass: HomeAssistant, enable_custom_integrations, unavailable: str
) -> None:
    from unittest.mock import PropertyMock

    from bleak.exc import BleakError

    entry, coordinator, client = runtime_entry(hass, "BOX25")
    if unavailable == "runtime":
        hass.data[const.DOMAIN].pop(entry.entry_id)
    elif unavailable == "client":
        coordinator._client = None
    elif unavailable == "disconnected":
        client.is_connected = False
    elif unavailable == "services":
        client.services = None
    with (
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock()) as connect,
    ):
        from contextlib import nullcontext

        property_guard = (
            patch.object(
                type(client),
                "services",
                new_callable=PropertyMock,
                side_effect=BleakError("GATT discovery pending"),
                create=True,
            )
            if unavailable == "discovery_pending"
            else nullcontext()
        )
        with property_guard:
            result = await _open_options_form(hass, entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX25"}
            )
            await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX25"
    connect.assert_not_awaited()
    client.pair.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_not_awaited()


async def test_public_options_corrected_selection_rechecks_same_current_receiver(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry, _, client = runtime_entry(hass, "BOX25")
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX25"}
        )
        assert result["type"] == FlowResultType.FORM
        client.services.extend(_app_probe_client("BOX3633").services)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == "BOX3633"
    reload.assert_awaited_once()
    client.write_gatt_char.assert_not_awaited()


async def test_public_options_unrelated_save_does_not_validate_unchanged_transport(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    entry, _, _ = runtime_entry(hass, "BOX25")
    stored = entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR]
    with (
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
        patch.object(
            AdjustableBedOptionsFlow,
            "_starcode_live_transport_valid",
            side_effect=AssertionError("Unchanged transport should not be probed"),
        ),
    ):
        result = await _open_options_form(hass, entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                const.CONF_STARCODE_TRANSPORT_SELECTOR: stored,
                const.CONF_IDLE_DISCONNECT_SECONDS: 50,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_STARCODE_TRANSPORT_SELECTOR] == stored
    assert entry.data[const.CONF_IDLE_DISCONNECT_SECONDS] == 50


@pytest.mark.parametrize(
    "key,value",
    [
        (const.CONF_STARCODE_TRANSPORT_SELECTOR, "BOX25"),
        (const.CONF_STARCODE_COMMAND_SELECTOR, "BOX25"),
        (const.CONF_STARCODE_UI_SELECTOR, "BOX25"),
    ],
)
async def test_public_pair_options_cannot_copy_app_selectors_between_addresses(
    hass: HomeAssistant, enable_custom_integrations, key: str, value: str
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    first, _, _ = runtime_entry(hass, "BOX25")
    right = {
        **first.data,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
    }
    entry = MockConfigEntry(
        domain=const.DOMAIN, data=build_pair_entry_data(dict(first.data), right, name="Pair")
    )
    entry.add_to_hass(hass)
    original = dict(entry.data)
    with (
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload,
        patch.object(
            AdjustableBedOptionsFlow,
            "_starcode_live_transport_valid",
            side_effect=AssertionError("Paired selectors must remain side-local"),
        ),
    ):
        result = await _open_options_form(hass, entry.entry_id)
        assert not const.STARCODE_APP_CONFIG_KEYS.intersection(
            marker.schema for marker in result["data_schema"].schema
        )
        with pytest.raises(InvalidData, match="Schema validation failed"):
            await hass.config_entries.options.async_configure(
                result["flow_id"], user_input={key: value}
            )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.FORM
    assert entry.data == original and not entry.options
    reload.assert_not_awaited()
