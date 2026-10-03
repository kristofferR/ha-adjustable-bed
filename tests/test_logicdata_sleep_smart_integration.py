"""Sleep Smart bed profile through real setup, entities and services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_HAS_LIGHT,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import (
    SERVICE_LOGICDATA_HOLD_PRESET,
    SERVICE_LOGICDATA_RENAME,
    async_register_services,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERVICE_UUID = "0000ff12-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
RENAME_UUID = "0000ff06-0000-1000-8000-00805f9b34fb"


@pytest.mark.parametrize(
    ("family", "layout", "errors"),
    [
        ("p2", "middle", {CONF_LOGICDATA_APP_LAYOUT: "logicdata_app_sleep_smart_layout"}),
        ("p1", "standard_4", {CONF_LOGICDATA_APP_LAYOUT: "logicdata_app_sleep_smart_layout"}),
        ("p2", "split_series", {}),
        ("p1", "standard_2", {}),
    ],
)
async def test_setup_accepts_only_the_two_motor_layouts(hass, family, layout, errors):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP}
    with patch.object(
        flow, "_finish_with_verify", AsyncMock(return_value={"type": "create_entry"})
    ):
        result = await flow.async_step_logicdata_app(
            {
                CONF_LOGICDATA_APP_PROFILE: "sleep_smart",
                CONF_LOGICDATA_APP_FAMILY: family,
                CONF_LOGICDATA_APP_LAYOUT: layout,
            }
        )
    assert result.get("errors", {}) == errors
    assert (CONF_LOGICDATA_APP_FAMILY in flow._manual_data) is not bool(errors)


@pytest.fixture
def sleep_smart_ble(mock_bleak_client, monkeypatch):
    characteristics = {
        uuid: SimpleNamespace(
            uuid=uuid, properties=["write", "notify"], descriptors=[], handle=handle,
            description="App control characteristic",
        )
        for handle, uuid in enumerate((WRITE_UUID, NOTIFY_UUID, RENAME_UUID), start=1)
    }
    service = SimpleNamespace(
        uuid=SERVICE_UUID,
        characteristics=list(characteristics.values()),
        get_characteristic=characteristics.get,
    )
    mock_bleak_client.services.__iter__ = lambda self: iter((service,))
    mock_bleak_client.services.get_service = MagicMock(
        side_effect=lambda uuid: service if uuid == SERVICE_UUID else None
    )
    mock_bleak_client.services.get_characteristic = MagicMock(side_effect=characteristics.get)
    mock_bleak_client.write_gatt_char.side_effect = None
    monkeypatch.setattr(LogicdataAppController, "_pause", AsyncMock(return_value=True))
    return mock_bleak_client


async def test_entities_follow_the_app_surface(
    hass, mock_coordinator_connected, sleep_smart_ble, enable_custom_integrations
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleep Smart bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Sleep Smart bed",
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
            CONF_LOGICDATA_APP_PROFILE: "sleep_smart",
            CONF_LOGICDATA_APP_FAMILY: "p1",
            CONF_LOGICDATA_APP_LAYOUT: "standard_2",
            CONF_LOGICDATA_APP_TRANSPORT: "t1",
            CONF_LOGICDATA_APP_HAS_LIGHT: True,
            CONF_HAS_MASSAGE: True,
            CONF_MOTOR_PULSE_COUNT: 1,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    rows = er.async_entries_for_config_entry(registry, entry.entry_id)
    keys = {(row.domain, row.unique_id.removeprefix(f"{ADDRESS}_")) for row in rows}
    assert {key for domain, key in keys if domain == "cover"} == {"back", "legs", "both"}
    buttons = {key for domain, key in keys if domain == "button"}
    assert {key for key in buttons if key.startswith(("preset_", "program_memory_"))} == {
        "preset_flat",
        "preset_zero_g",
        "preset_anti_snore",
        "preset_memory_1",
        "program_memory_1",
    }
    assert {"factory_reset", "logicdata_app_query_massage", "toggle_light"} <= buttons
    assert ("sensor", "logicdata_app_massage_mode") in keys
    assert ("sensor", "logicdata_app_family_match") not in keys

    sleep_smart_ble.write_gatt_char.reset_mock()
    entity_id = registry.async_get_entity_id("button", DOMAIN, f"{ADDRESS}_preset_zero_g")
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    # One pulse holds 200 ms: one refresh, then the release.
    assert sleep_smart_ble.write_gatt_char.await_args_list == [
        call(WRITE_UUID, bytes.fromhex("f1f1070101097e"), response=True),
        call(WRITE_UUID, bytes.fromhex("f1f14e004e7e"), response=True),
    ]


def _target(name, bed_type, **controller):
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = name
    coordinator.bed_type = bed_type
    coordinator.capability_controller = SimpleNamespace(**controller)
    return coordinator


@pytest.fixture
async def services(hass: HomeAssistant):
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets"
    ) as resolve:
        yield resolve


async def test_rename_validates_every_app_rule_before_any_write(hass, services):
    def strict(name):
        if not name.isalnum():
            raise ValueError("Name must contain 1..20 letters, digits, ä, ö, ü or ß")

    phone = _target(
        "Phone bed", BED_TYPE_LOGICDATA_APP, supports_device_rename=True,
        disconnects_after_rename=False,
        validate_device_rename=MagicMock(), rename_device=AsyncMock(),
    )
    pump = _target(
        "Pump", BED_TYPE_LOGICDATA_AIR_PUMP, supports_device_rename=True,
        validate_device_rename=strict, rename_device=AsyncMock(),
    )
    services.return_value = ([(phone, SIDE_BOTH), (pump, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="1..20"):
        await hass.services.async_call(
            DOMAIN, SERVICE_LOGICDATA_RENAME, {"device_id": ["a", "b"], "name": "My Bed"},
            blocking=True,
        )
    phone.async_execute_controller_command.assert_not_called()
    pump.async_execute_controller_command.assert_not_called()


async def test_hold_preset_validates_each_profile_before_dispatch(hass, services):
    smart = _target(
        "Sleep Smart", BED_TYPE_LOGICDATA_APP, supports_preset_hold=True,
        held_preset_options=("flat", "zero_g", "anti_snore", "memory_1"),
    )
    middle = _target(
        "Middle", BED_TYPE_LOGICDATA_APP, supports_preset_hold=True,
        held_preset_options=("flat", "memory_1", "memory_2"),
    )
    services.return_value = ([(smart, SIDE_BOTH), (middle, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="zero_g"):
        await hass.services.async_call(
            DOMAIN, SERVICE_LOGICDATA_HOLD_PRESET,
            {"device_id": ["a", "b"], "preset": "zero_g", "duration": 1}, blocking=True,
        )
    smart.async_execute_controller_command.assert_not_called()
    middle.async_execute_controller_command.assert_not_called()
