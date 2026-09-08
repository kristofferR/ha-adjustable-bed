"""Real Home Assistant entity setup for the accepted Logicdata app profiles."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_LOGICDATA_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_HAS_LIGHT,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERVICE_UUID = "0000ff12-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
RENAME_UUID = "0000ff06-0000-1000-8000-00805f9b34fb"


@pytest.fixture
def app_ble(mock_bleak_client, monkeypatch):
    """Model the frozen T1 roles and an initial app-visible status notification."""
    from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController

    characteristics = {
        uuid: SimpleNamespace(
            uuid=uuid,
            properties=["write", "notify"],
            descriptors=[],
            handle=handle,
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

    async def start_notify(uuid, callback):
        if uuid == NOTIFY_UUID:
            callback(characteristics[uuid], bytearray.fromhex("aaaa06000400030040"))

    mock_bleak_client.start_notify.side_effect = start_notify
    monkeypatch.setattr(LogicdataAppController, "_pause", AsyncMock(return_value=True))
    return mock_bleak_client


def _entry(
    hass: HomeAssistant,
    *,
    family: str = "p1",
    layout: str = "standard_2",
    has_light: bool = True,
    has_massage: bool = True,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Logicdata app bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Logicdata app bed",
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_APP,
            CONF_LOGICDATA_APP_PROFILE: "phone",
            CONF_LOGICDATA_APP_FAMILY: family,
            CONF_LOGICDATA_APP_LAYOUT: layout,
            CONF_LOGICDATA_APP_TRANSPORT: "t1",
            CONF_LOGICDATA_APP_HAS_LIGHT: has_light,
            CONF_HAS_MASSAGE: has_massage,
            # Neither stale motor counts nor angle settings may invent capabilities.
            CONF_MOTOR_COUNT: 4,
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


def _keys(hass: HomeAssistant, entry: MockConfigEntry, domain: str) -> set[str]:
    return {
        entity.unique_id.removeprefix(f"{ADDRESS}_")
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if entity.domain == domain
    }


async def test_p2_middle_exposes_only_its_reachable_controls(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, family="p2", layout="middle")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _keys(hass, entry, "cover") == {"back", "legs"}
    buttons = _keys(hass, entry, "button")
    assert {key for key in buttons if key.startswith("preset_")} == {
        "preset_flat",
        "preset_memory_1",
        "preset_memory_2",
    }
    assert {key for key in buttons if key.startswith("program_memory_")} == {
        "program_memory_1",
        "program_memory_2",
    }
    assert "toggle_light" in buttons
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(
        "massage" in entity.unique_id or "alarm" in entity.unique_id for entity in entries
    )
    assert not any(
        entity.domain in {"number", "sensor"}
        and ("position" in entity.unique_id or "angle" in entity.unique_id)
        for entity in entries
    )
    for key in ("back", "legs"):
        state = hass.states.get(_entity_id(hass, "cover", key))
        assert not state.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
        assert "current_position" not in state.attributes
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.controller.supports_clock_alarm is False

    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": _entity_id(hass, "button", "preset_flat")},
            blocking=True,
        )
    execute.assert_awaited_once()
    # HA applies the proven held-flat release after its preset action too.
    assert app_ble.write_gatt_char.await_args_list == [
        call(WRITE_UUID, bytes.fromhex("f1f1080200000a7e"), response=True),
        call(WRITE_UUID, bytes.fromhex("f1f14e004e7e"), response=True),
    ]


async def test_p1_split_right_massage_uses_its_own_state_and_serialized_action(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, layout="split_series")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    right_id = _entity_id(hass, "number", "massage_right_intensity")
    head_id = _entity_id(hass, "number", "massage_head_intensity")
    assert "massage_foot_intensity" not in _keys(hass, entry, "number")
    assert float(hass.states.get(head_id).state) == 3
    assert float(hass.states.get(right_id).state) == 2
    assert hass.states.get(right_id).attributes["max"] == 3

    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": right_id, "value": 3}, blocking=True
        )
    execute.assert_awaited_once()
    app_ble.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, bytes.fromhex("f1f122020804307e"), response=True
    )
    # Sending a command does not replace the most recent hardware report.
    assert float(hass.states.get(right_id).state) == 2
    assert float(hass.states.get(head_id).state) == 3

    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(SimpleNamespace(uuid=NOTIFY_UUID), bytearray.fromhex("aaaa06000200000000"))
    await async_update_entity(hass, head_id)
    await async_update_entity(hass, right_id)
    assert float(hass.states.get(head_id).state) == 1
    assert float(hass.states.get(right_id).state) == 0


@pytest.mark.parametrize("enabled", [False, True])
async def test_p1_normal_entities_follow_explicit_light_and_massage_options(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, enabled
):
    entry = _entry(hass, has_light=enabled, has_massage=enabled)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ("toggle_light" in _keys(hass, entry, "button")) is enabled
    massage_keys = {key for key in _keys(hass, entry, "number") if key.startswith("massage_")}
    assert massage_keys == (
        {"massage_head_intensity", "massage_foot_intensity"} if enabled else set()
    )


async def test_phone_clock_reply_keeps_scheduler_out_of_its_disconnect_path(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_DISCONNECT_AFTER_COMMAND: True}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    bed = coordinator.controller
    app_ble.disconnect.reset_mock()
    bed._notification_handler(SimpleNamespace(uuid=NOTIFY_UUID), bytearray.fromhex("f2f250000000"))
    await asyncio.wait_for(bed._clock_task, timeout=1)
    assert bed._clock_task.done()
    app_ble.disconnect.assert_not_awaited()


async def test_timed_move_uses_fixed_app_cadence_despite_user_pulse_setting(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    from custom_components.adjustable_bed.services import _timed_move_plan

    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator._motor_pulse_delay_ms = 500
    _, count, delay, _ = await _timed_move_plan(coordinator, coordinator, [], "back", "up", 1000)
    assert (count, delay) == (9, 100)


async def test_new_dynamic_entities_have_localized_names(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for domain, key, name in (
        ("cover", "both", "Back and legs"),
        ("sensor", "logicdata_app_family_match", "Command family matches"),
        ("sensor", "logicdata_app_alarm", "Bed alarm"),
    ):
        entity = registry.async_get(_entity_id(hass, domain, key))
        assert entity.original_name == name


@pytest.mark.parametrize(
    ("old_layout", "new_layout", "profile", "family", "massage"),
    [
        ("standard_4", "standard_2", "phone", "p1", True),
        ("split_series", "standard_2", "tablet", "p1", True),
        ("split_series", "split_series", "phone", "p1", False),
        ("standard_2", "middle", "phone", "p2", False),
    ],
)
async def test_profile_reload_removes_obsolete_entities(
    hass,
    mock_coordinator_connected,
    app_ble,
    enable_custom_integrations,
    old_layout,
    new_layout,
    profile,
    family,
    massage,
):
    from custom_components.adjustable_bed.logicdata_app_protocol import layout_axes

    entry = _entry(hass, layout=old_layout)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "logicdata_app_alarm" in _keys(hass, entry, "sensor")
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_LOGICDATA_APP_LAYOUT: new_layout,
            CONF_LOGICDATA_APP_PROFILE: profile,
            CONF_LOGICDATA_APP_FAMILY: family,
            CONF_HAS_MASSAGE: massage,
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _keys(hass, entry, "cover") == set(layout_axes(new_layout))
    assert ("logicdata_app_alarm" in _keys(hass, entry, "sensor")) == (
        profile == "phone" and family == "p1"
    )
    assert {key for key in _keys(hass, entry, "number") if key.startswith("massage_")} == (
        {"massage_head_intensity", "massage_foot_intensity"} if massage else set()
    )


@pytest.mark.parametrize(
    ("layout", "combined", "axis"),
    [
        ("standard_2", "both", "back"),
        ("standard_2", "both", "legs"),
        ("standard_3_split_upper", "both_backs", "back"),
        ("standard_3_split_upper", "both_backs", "right_back"),
    ],
)
@pytest.mark.parametrize("action", ["stop_cover", "close_cover"])
async def test_constituent_cover_preempts_combined_movement(
    hass,
    mock_coordinator_connected,
    app_ble,
    enable_custom_integrations,
    layout,
    combined,
    axis,
    action,
):
    entry = _entry(hass, layout=layout)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def move_axis(motor, up):
        if motor == combined:
            started.set()
            await coordinator.cancel_command.wait()
            cancelled.set()
        else:
            assert cancelled.is_set()

    with patch.object(coordinator.controller, "move_axis", side_effect=move_axis):
        movement = asyncio.create_task(
            hass.services.async_call(
                "cover",
                "open_cover",
                {"entity_id": _entity_id(hass, "cover", combined)},
                blocking=True,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        try:
            await asyncio.wait_for(
                hass.services.async_call(
                    "cover",
                    action,
                    {"entity_id": _entity_id(hass, "cover", axis)},
                    blocking=True,
                ),
                timeout=1,
            )
            assert cancelled.is_set()
        finally:
            coordinator.cancel_command.set()
            await movement
