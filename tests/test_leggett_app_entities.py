"""Home Assistant entity surfaces for the accepted Prodigy and U-series apps."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_OKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_LEGGETT_APP_PROFILE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    LEGGETT_OKIN_CHAR_UUID,
    LEGGETT_OKIN_NOTIFY_CHAR_UUID,
    LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
    LEGGETT_OKIN_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def app_ble(mock_bleak_client):
    """Supply R1 GATT roles and a frozen opaque LED/status notification."""
    uuids = (
        LEGGETT_OKIN_CHAR_UUID,
        LEGGETT_OKIN_NOTIFY_CHAR_UUID,
        LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
        OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
        OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    )
    characteristics = {
        uuid: SimpleNamespace(
            uuid=uuid,
            properties=["write", "write-without-response", "notify"],
            descriptors=[],
            handle=handle,
            description="App control characteristic",
        )
        for handle, uuid in enumerate(uuids, start=1)
    }
    service = SimpleNamespace(
        uuid=LEGGETT_OKIN_SERVICE_UUID,
        characteristics=list(characteristics.values()),
        get_characteristic=characteristics.get,
    )
    mock_bleak_client.services.__iter__ = lambda self: iter((service,))
    mock_bleak_client.services.get_service = MagicMock(
        side_effect=lambda uuid: service if uuid == service.uuid else None
    )
    mock_bleak_client.services.get_characteristic = MagicMock(side_effect=characteristics.get)
    mock_bleak_client.write_gatt_char.side_effect = None

    async def start_notify(uuid, callback):
        if uuid == LEGGETT_OKIN_NOTIFY_CHAR_UUID:
            callback(characteristics[uuid], bytearray.fromhex("0600060000017f0002"))

    mock_bleak_client.start_notify.side_effect = start_notify
    return mock_bleak_client


def _entry(hass: HomeAssistant, profile: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Leggett app bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Leggett app bed",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
            CONF_LEGGETT_APP_PROFILE: profile,
            # App-selected axes must override the legacy generic motor count.
            CONF_MOTOR_COUNT: 2,
            CONF_MOTOR_PULSE_COUNT: 1,
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


def _keys(hass: HomeAssistant, entry: MockConfigEntry, domain: str) -> set[str]:
    return {
        entity.unique_id.removeprefix(f"{ADDRESS}_")
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if entity.domain == domain
    }


@pytest.mark.parametrize(
    ("profile", "axes"),
    [
        ("prodigy2l", {"head", "feet", "lumbar"}),
        ("prodigy2", {"head", "feet", "pillow"}),
        ("prodigy4", {"head", "feet", "pillow", "lumbar"}),
        ("useries", {"head", "feet", "pillow"}),
    ],
)
async def test_profile_limits_axes_memories_and_control_modes(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, profile, axes
):
    entry = _entry(hass, profile)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _keys(hass, entry, "cover") == axes
    buttons = _keys(hass, entry, "button")
    assert {key for key in buttons if key.startswith("preset_memory_")} == {
        f"preset_memory_{slot}" for slot in range(1, 3 if profile == "useries" else 5)
    }
    assert {key for key in buttons if key.startswith("program_memory_")} == (
        set()
        if profile == "useries"
        else {"program_memory_1", "program_memory_2", "program_memory_4"}
    )
    assert {key for key in buttons if key.startswith("control_mode_")} == (
        set()
        if profile == "useries"
        else {"control_mode_press_and_hold", "control_mode_press_and_release"}
    )
    subscriptions = {call.args[0] for call in app_ble.start_notify.await_args_list}
    assert subscriptions == (
        {LEGGETT_OKIN_NOTIFY_CHAR_UUID}
        if profile == "useries"
        else {LEGGETT_OKIN_NOTIFY_CHAR_UUID, OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID}
    )
    css_writes = [
        call
        for call in app_ble.write_gatt_char.await_args_list
        if call.args[0] == OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID
    ]
    assert [call.args[1] for call in css_writes] == ([] if profile == "useries" else [b"\x01\x02"])

    for axis in axes:
        state = hass.states.get(_entity_id(hass, "cover", axis))
        assert not state.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
        assert "current_position" not in state.attributes
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(
        entity.domain in {"number", "sensor"}
        and ("position" in entity.unique_id or "angle" in entity.unique_id)
        for entity in entries
    )


async def test_raw_status_is_published_without_guessing_light_or_position_state(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "useries")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    mask_id = _entity_id(hass, "sensor", "leggett_led_mask")
    status_id = _entity_id(hass, "sensor", "leggett_status")
    assert int(hass.states.get(mask_id).state) == 0x077F0003
    assert int(hass.states.get(status_id).state) == 127
    assert not _keys(hass, entry, "light")
    assert "under_bed_lights" not in _keys(hass, entry, "switch")

    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(
        SimpleNamespace(uuid=LEGGETT_OKIN_NOTIFY_CHAR_UUID),
        bytearray.fromhex("060055aa0000fe0000"),
    )
    await hass.async_block_till_done()
    assert int(hass.states.get(mask_id).state) == 0x55AA0000
    assert int(hass.states.get(status_id).state) == -2


async def test_useries_memory_button_dispatches_through_coordinator(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "useries")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": _entity_id(hass, "button", "preset_memory_1")},
            blocking=True,
        )
    execute.assert_awaited_once()
    writes = app_ble.write_gatt_char.await_args_list
    assert all(call.args[0] == LEGGETT_OKIN_CHAR_UUID for call in writes)
    assert [call.args[1] for call in writes] == (
        [bytes.fromhex("040200001000")] * 10 + [bytes.fromhex("040200000000")] * 4
    )
    assert all(call.kwargs["response"] is False for call in writes)


@pytest.mark.parametrize("profile", ["prodigy4", "useries"])
async def test_indicator_readback_applies_only_useries_low_byte_suppression(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, profile
):
    """Preserve the raw report while applying the app's indicator display rule."""
    entry = _entry(hass, profile)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    mask_id = _entity_id(hass, "sensor", "leggett_led_mask")
    alarm_id = _entity_id(hass, "binary_sensor", "leggett_alarm_indicator")
    timer_id = _entity_id(hass, "binary_sensor", "leggett_sleep_timer_indicator")
    callback = app_ble.start_notify.await_args_list[0].args[1]
    sender = SimpleNamespace(uuid=LEGGETT_OKIN_NOTIFY_CHAR_UUID)

    callback(sender, bytearray.fromhex("0400c001000000"))
    await hass.async_block_till_done()
    assert int(hass.states.get(mask_id).state) == 0xC001
    expected = "off" if profile == "useries" else "on"
    assert hass.states.get(alarm_id).state == expected
    assert hass.states.get(timer_id).state == expected

    callback(sender, bytearray.fromhex("0400c000000000"))
    await hass.async_block_till_done()
    assert int(hass.states.get(mask_id).state) == 0xC000
    assert hass.states.get(alarm_id).state == "on"
    assert hass.states.get(timer_id).state == "on"
