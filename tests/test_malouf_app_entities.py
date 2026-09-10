"""Model/transport entity gating and current-controller dispatch for the apps."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_SIDE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.malouf_app_protocol import TRANSPORT_PROFILES

ADDRESS = "AA:BB:CC:DD:EE:FF"
NEW_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NEW_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FRAMED_WRITE = "d44bc439-abfd-45a2-b575-925416129600"


def _configure_transport(client: MagicMock, transport_name: str) -> None:
    """Expose one complete transport without unproven mixed-service hybrids."""
    services = {}
    characteristics = {}
    transport = TRANSPORT_PROFILES[transport_name]
    for service_uuid, uuid in (
        (transport.service_uuid, transport.write_uuid),
        (transport.notify_service_uuid, transport.notify_uuid),
    ):
        if service_uuid is None or uuid is None:
            continue
        characteristic = SimpleNamespace(
            uuid=uuid,
            properties=["write", "write-without-response", "notify"],
            descriptors=[],
            handle=len(characteristics) + 1,
            description="App control characteristic",
        )
        characteristics[uuid] = characteristic
        if service_uuid not in services:
            services[service_uuid] = SimpleNamespace(
                uuid=service_uuid, characteristics=[], get_characteristic=characteristics.get
            )
        services[service_uuid].characteristics.append(characteristic)
    client.services.__iter__ = lambda self: iter(services.values())
    client.services.get_service = MagicMock(side_effect=services.get)
    client.services.get_characteristic = MagicMock(side_effect=characteristics.get)


@pytest.fixture
def app_ble(mock_bleak_client):
    """Return the accepted notification state on subscription."""
    mock_bleak_client.write_gatt_char.side_effect = None
    samples = {
        "0000ffe4-0000-1000-8000-00805f9b34fb": "00000000000000400200",
        "62741625-52f9-8864-b1ab-3b3a8d65950b": "0000000000000000000002",
        NEW_NOTIFY: "000b0000030000000001",
    }

    async def start_notify(uuid, callback):
        callback(SimpleNamespace(uuid=uuid), bytearray.fromhex(samples[uuid]))

    mock_bleak_client.start_notify.side_effect = start_notify
    return mock_bleak_client


def _entry(
    hass: HomeAssistant,
    client: MagicMock,
    *,
    model: str,
    transport: str,
    profile: str = "malouf",
) -> MockConfigEntry:
    _configure_transport(client, transport)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malouf app bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Malouf app bed",
            CONF_BED_TYPE: BED_TYPE_MALOUF_APP,
            CONF_MALOUF_APP_PROFILE: profile,
            CONF_MALOUF_APP_MODEL: model,
            CONF_MALOUF_APP_TRANSPORT: transport,
            CONF_MALOUF_APP_SIDE: "primary",
            # Stored generic options must not invent model capabilities.
            CONF_MOTOR_COUNT: 4,
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


async def _change_profile(
    hass: HomeAssistant, entry: MockConfigEntry, client: MagicMock, **changes: str
) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, data={**entry.data, **changes})
    _configure_transport(client, entry.data[CONF_MALOUF_APP_TRANSPORT])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("transport", ["opcode_framed", "command32_new"])
async def test_basic_model_remains_basic_on_either_command_family(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, transport
):
    entry = _entry(hass, app_ble, model="e450", transport=transport)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _keys(hass, entry, "cover") == {"back", "legs"}
    buttons = _keys(hass, entry, "button")
    assert {"preset_zero_g", "preset_anti_snore"} <= buttons
    assert not any(
        key.startswith(("massage_", "preset_memory_", "program_memory_")) for key in buttons
    )
    assert "toggle_light" not in buttons
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(
        entity.domain in {"number", "sensor"}
        and ("position" in entity.unique_id or "angle" in entity.unique_id)
        for entity in entries
    )
    for axis in ("back", "legs"):
        state = hass.states.get(_entity_id(hass, "cover", axis))
        assert not state.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
        assert "current_position" not in state.attributes


async def test_timer_setting_dispatch_and_profile_change_remove_stale_controls(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, app_ble, model="s755", transport="opcode_framed")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    timer_id = _entity_id(hass, "select", "massage_timer")
    assert hass.states.get(timer_id).attributes["options"] == ["Off", "10 min", "20 min", "30 min"]
    assert len(_keys(hass, entry, "cover")) == 5
    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": timer_id, "option": "20 min"}, blocking=True
        )
    execute.assert_awaited_once()
    app_ble.write_gatt_char.assert_awaited_once_with(
        FRAMED_WRITE, bytes.fromhex("6e010063d2"), response=False
    )

    await _change_profile(
        hass,
        entry,
        app_ble,
        **{CONF_MALOUF_APP_MODEL: "s750", CONF_MALOUF_APP_TRANSPORT: "command32_new"},
    )
    assert "massage_timer" not in _keys(hass, entry, "select")
    assert hass.states.get(timer_id) is None
    assert _keys(hass, entry, "cover") == {"back", "legs", "head", "lumbar"}
    assert {"massage_mode_step", "massage_timer_cycle"} <= _keys(hass, entry, "button")
    _entity_id(hass, "sensor", "malouf_app_massage_minutes")
    _entity_id(hass, "binary_sensor", "malouf_app_under_bed_light")

    await _change_profile(hass, entry, app_ble, **{CONF_MALOUF_APP_MODEL: "e450"})
    assert _keys(hass, entry, "cover") == {"back", "legs"}
    assert "malouf_app_massage_minutes" not in _keys(hass, entry, "sensor")
    assert "malouf_app_under_bed_light" not in _keys(hass, entry, "binary_sensor")
    assert not any(
        key.startswith(("massage_", "preset_memory_", "program_memory_"))
        for key in _keys(hass, entry, "button")
    )


async def test_live_minutes_light_and_distinct_wave_timer_actions(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, app_ble, model="s750", transport="command32_new", profile="lucid")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    minutes_id = _entity_id(hass, "sensor", "malouf_app_massage_minutes")
    light_id = _entity_id(hass, "binary_sensor", "malouf_app_under_bed_light")
    assert int(hass.states.get(minutes_id).state) == 20
    assert hass.states.get(light_id).state == "on"
    assert not _keys(hass, entry, "light")
    assert "under_bed_lights" not in _keys(hass, entry, "switch")
    coordinator = hass.data[DOMAIN][entry.entry_id]
    app_ble.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        for key in ("massage_mode_step", "massage_timer_cycle"):
            await hass.services.async_call(
                "button", "press", {"entity_id": _entity_id(hass, "button", key)}, blocking=True
            )
    assert execute.await_count == 2
    assert app_ble.write_gatt_char.await_args_list == [
        call(NEW_WRITE, bytes.fromhex("0502100000000000"), response=False),
        call(NEW_WRITE, bytes.fromhex("00b0"), response=False),
        call(NEW_WRITE, bytes.fromhex("0502000002000000"), response=False),
        call(NEW_WRITE, bytes.fromhex("00b0"), response=False),
    ]
    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(SimpleNamespace(uuid=NEW_NOTIFY), bytearray.fromhex("000b0000050000000000"))
    await hass.async_block_till_done()
    assert int(hass.states.get(minutes_id).state) == 30
    assert hass.states.get(light_id).state == "off"


async def test_altitude_axes_and_premium_read_follow_exact_model_bindings(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, app_ble, model="altitude", transport="opcode_framed")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _keys(hass, entry, "cover") == {"back", "legs", "head", "dual", "full_tilt"}
    await _change_profile(
        hass,
        entry,
        app_ble,
        **{
            CONF_MALOUF_APP_MODEL: "premium",
            CONF_MALOUF_APP_PROFILE: "lucid",
            CONF_MALOUF_APP_TRANSPORT: "command32_new",
        },
    )
    assert _keys(hass, entry, "cover") == {"back", "legs", "dual"}
    read_id = _entity_id(hass, "button", "preset_read")
    tv_id = _entity_id(hass, "button", "preset_tv")
    assert read_id != tv_id
    await _change_profile(hass, entry, app_ble, **{CONF_MALOUF_APP_PROFILE: "malouf"})
    assert "preset_read" not in _keys(hass, entry, "button")
    assert "preset_tv" in _keys(hass, entry, "button")
    assert hass.states.get(read_id) is None


async def test_middle_transport_reports_minutes_without_claiming_light_feedback(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    """The middle parser's constant zero does not mean the hardware light is off."""
    entry = _entry(hass, app_ble, model="s750", transport="command32_middle")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    minutes_id = _entity_id(hass, "sensor", "malouf_app_massage_minutes")
    assert int(hass.states.get(minutes_id).state) == 20
    assert "toggle_light" in _keys(hass, entry, "button")
    assert "malouf_app_under_bed_light" not in _keys(hass, entry, "binary_sensor")
    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(
        SimpleNamespace(uuid="62741625-52f9-8864-b1ab-3b3a8d65950b"),
        bytearray.fromhex("0000000000000000000003"),
    )
    await hass.async_block_till_done()
    assert int(hass.states.get(minutes_id).state) == 30
