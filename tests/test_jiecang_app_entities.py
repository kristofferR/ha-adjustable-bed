"""Home Assistant entities for explicit Jiecang app layouts and live capabilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jiecang_app import JiecangAppController
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_HAS_LIGHT,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def app_ble(mock_bleak_client, monkeypatch, request):
    """Supply real bootstrap notifications over a minimal discovered G3 service."""
    characteristic = SimpleNamespace(
        uuid=COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
        properties=["write", "notify"],
        descriptors=[],
        handle=1,
        description="Read/write characteristic",
    )
    service = SimpleNamespace(
        uuid=COMFORT_MOTION_LIERDA3_SERVICE_UUID,
        characteristics=[characteristic],
        get_characteristic=lambda uuid: characteristic,
    )
    mock_bleak_client.services.__iter__ = lambda self: iter((service,))
    mock_bleak_client.services.get_service = MagicMock(
        side_effect=lambda uuid: service if uuid == service.uuid else None
    )
    mock_bleak_client.write_gatt_char.side_effect = None

    async def start_notify(uuid, callback):
        if uuid != COMFORT_MOTION_LIERDA3_READ_CHAR_UUID:
            return
        if getattr(request, "param", True):
            callback(characteristic, bytearray.fromhex("f2f20e00070000"))
        callback(characteristic, bytearray.fromhex("f2f25300000000"))
        callback(characteristic, bytearray.fromhex("f2f2520733221164012c01517e"))

    mock_bleak_client.start_notify.side_effect = start_notify
    monkeypatch.setattr(JiecangAppController, "_pause", AsyncMock(return_value=False))
    return mock_bleak_client


def _entry(hass: HomeAssistant, layout: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jiecang app bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Jiecang app bed",
            CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
            CONF_JIECANG_APP_PROFILE: "dreamotion",
            CONF_JIECANG_APP_LAYOUT: layout,
            CONF_JIECANG_APP_TRANSPORT: "g3",
            CONF_JIECANG_APP_HAS_LIGHT: True,
            # The selected app layout must win over this legacy motor count.
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    return entry


def _entity_id(hass: HomeAssistant, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}")
    assert entity_id is not None, (domain, key)
    return entity_id


@pytest.mark.parametrize(
    ("layout", "axes"),
    [
        (
            "standard_4_bilateral",
            {"back", "legs", "right_back", "right_legs", "both_backs", "both_legs"},
        ),
        ("standard_3_hi_low", {"back", "legs", "bed_height"}),
    ],
)
async def test_selected_layout_exposes_only_proven_motors_and_two_memories(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, layout, axes
):
    entry = _entry(hass, layout)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert {
        entity.unique_id.removeprefix(f"{ADDRESS}_")
        for entity in entries
        if entity.domain == "cover"
    } == axes
    for axis in axes:
        state = hass.states.get(_entity_id(hass, "cover", axis))
        assert state is not None
        assert not state.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
        assert "current_position" not in state.attributes

    buttons = {
        entity.unique_id.removeprefix(f"{ADDRESS}_")
        for entity in entries
        if entity.domain == "button"
    }
    assert {key for key in buttons if key.startswith("preset_memory_")} == {
        "preset_memory_1",
        "preset_memory_2",
    }
    assert {key for key in buttons if key.startswith("program_memory_")} == {
        "program_memory_1",
        "program_memory_2",
    }
    assert not any(
        entity.domain in {"number", "sensor"}
        and ("position" in entity.unique_id or "angle" in entity.unique_id)
        for entity in entries
    )
    if layout == "standard_4_bilateral":
        # RGB capability flags do not expose the standard-only light settings here.
        assert not any(
            entity.unique_id.removeprefix(f"{ADDRESS}_") in {"automatic_light", "light_timer"}
            or entity.domain == "light"
            for entity in entries
        )


async def test_live_light_capabilities_and_serialized_entity_actions(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "standard_2")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    light_id = _entity_id(hass, "light", "under_bed_lights")
    auto_id = _entity_id(hass, "switch", "automatic_light")
    timer_id = _entity_id(hass, "select", "light_timer")
    massage_id = _entity_id(hass, "number", "massage_head_intensity")
    assert (
        er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{ADDRESS}_under_bed_lights")
        is None
    )
    light_state = hass.states.get(light_id)
    assert light_state.state == "on"
    assert light_state.attributes["supported_color_modes"] == ["rgb"]
    assert light_state.attributes["rgb_color"] == (17, 34, 51)
    assert hass.states.get(auto_id).state == "on"
    assert hass.states.get(timer_id).state == "300"
    assert hass.states.get(massage_id).attributes["max"] == 3

    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call("switch", "turn_off", {"entity_id": auto_id}, blocking=True)
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": light_id, "rgb_color": [1, 2, 3]},
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": timer_id, "option": "600"},
            blocking=True,
        )
        await hass.services.async_call(
            "number", "set_value", {"entity_id": massage_id, "value": 2}, blocking=True
        )
    assert execute.await_count == 4
    assert hass.states.get(auto_id).state == "off"
    assert hass.states.get(light_id).attributes["rgb_color"] == (1, 2, 3)
    assert hass.states.get(timer_id).state == "600"
    writes = app_ble.write_gatt_char.await_args_list
    assert all(call.args[0] == COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID for call in writes)
    assert [call.args[1].hex() for call in writes] == [
        "f1f1290200002b7e",  # Automatic-light toggle.
        "f1f1520733221164012c01517e",  # Explicit on preserves existing light settings.
        "f1f1520703020164012c01f17e",  # RGB change preserves brightness and timeout.
        "f1f15207030201640258011e7e",  # Timer change preserves RGB and brightness.
        "f1f1120208031f7e",  # UI massage level 2 maps to wire level 3.
    ]
    # A physical app change must replace the switch's optimistic command state.
    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(
        SimpleNamespace(uuid=COMFORT_MOTION_LIERDA3_READ_CHAR_UUID),
        bytearray.fromhex("f2f25300000000"),
    )
    await hass.async_block_till_done()
    assert hass.states.get(auto_id).state == "on"


@pytest.mark.parametrize("app_ble", [False], indirect=True)
async def test_light_settings_require_reported_capabilities(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    """A configured light and RGB state alone cannot authorize advanced controls."""
    entry = _entry(hass, "standard_2")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for domain, key in (
        ("light", "under_bed_lights"),
        ("switch", "automatic_light"),
        ("select", "light_timer"),
        ("number", "light_level"),
    ):
        assert registry.async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}") is None


async def test_split_series_right_massage_slider_dispatches_and_reads_its_own_zone(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    """The split app's third massage channel must remain independently reachable."""
    entry = _entry(hass, "split_series")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    right_id = _entity_id(hass, "number", "massage_right_intensity")
    head_id = _entity_id(hass, "number", "massage_head_intensity")
    foot_id = _entity_id(hass, "number", "massage_foot_intensity")
    state = hass.states.get(right_id)
    assert float(state.state) == 0
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == 3
    assert state.attributes["step"] == 1

    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": right_id, "value": 2}, blocking=True
        )
    execute.assert_awaited_once()
    app_ble.write_gatt_char.assert_awaited_once_with(
        COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
        bytes.fromhex("f1f1220208032f7e"),
        response=True,
    )
    assert float(hass.states.get(right_id).state) == 2
    assert float(hass.states.get(head_id).state) == 0
    assert float(hass.states.get(foot_id).state) == 0
    assert coordinator.controller.get_massage_state()["right_intensity"] == 2
