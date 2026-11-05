"""Home Assistant entities for explicit Jiecang app layouts and live capabilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jiecang_app import JiecangAppController
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_LINAK,
    COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
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
        feature = getattr(request, "param", True)
        if feature:
            callback(
                characteristic,
                bytearray.fromhex("f2f20e00060000" if feature == "negative" else "f2f20e00070000"),
            )
        callback(characteristic, bytearray.fromhex("f2f25300000000"))
        callback(characteristic, bytearray.fromhex("f2f2520733221164012c01517e"))

    mock_bleak_client.start_notify.side_effect = start_notify
    monkeypatch.setattr(JiecangAppController, "_pause", AsyncMock(return_value=False))
    return mock_bleak_client


def _entry(hass: HomeAssistant, layout: str, profile: str = "dreamotion") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jiecang app bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Jiecang app bed",
            CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
            CONF_JIECANG_APP_PROFILE: profile,
            CONF_JIECANG_APP_LAYOUT: layout,
            CONF_JIECANG_APP_TRANSPORT: "g3",
            CONF_HAS_LIGHT: True,
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
            or (
                entity.domain == "light"
                and not entity.unique_id.endswith("_under_bed_lights_assumed")
            )
            for entity in entries
        )
        light_id = _entity_id(hass, "light", "under_bed_lights_assumed")
        assert (
            er.async_get(hass).async_get(light_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert hass.states.get(light_id) is None


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


@pytest.mark.parametrize(
    ("old_layout", "new_layout", "removed_covers", "removed_numbers", "retained_numbers"),
    [
        (
            "standard_4_bilateral",
            "standard_2",
            {"right_back", "right_legs", "both_backs", "both_legs"},
            {"massage_right_intensity"},
            {"massage_head_intensity", "massage_foot_intensity"},
        ),
        (
            "split_series",
            "standard_4_bilateral",
            set(),
            {"massage_foot_intensity", "light_level"},
            {"massage_head_intensity", "massage_right_intensity"},
        ),
        (
            "standard_2",
            "standard_3_neck",
            {"both"},
            set(),
            {"massage_head_intensity", "massage_foot_intensity", "light_level"},
        ),
    ],
)
async def test_reload_removes_entities_dropped_by_layout_change(
    hass,
    mock_coordinator_connected,
    app_ble,
    enable_custom_integrations,
    old_layout,
    new_layout,
    removed_covers,
    removed_numbers,
    retained_numbers,
):
    entry = _entry(hass, old_layout)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for domain, keys in (("cover", removed_covers), ("number", removed_numbers)):
        for key in keys:
            _entity_id(hass, domain, key)
    retained_ids = {
        key: _entity_id(hass, "number", key)
        for key in retained_numbers
        if registry.async_get_entity_id("number", DOMAIN, f"{ADDRESS}_{key}")
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_JIECANG_APP_LAYOUT: new_layout}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for domain, keys in (("cover", removed_covers), ("number", removed_numbers)):
        for key in keys:
            assert registry.async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}") is None
    for key in retained_numbers:
        actual = _entity_id(hass, "number", key)
        if key in retained_ids:
            assert actual == retained_ids[key]
        assert hass.states.get(actual).state != "unavailable"


@pytest.mark.parametrize("bed_type", [BED_TYPE_JIECANG, BED_TYPE_LINAK])
@pytest.mark.parametrize("layout", ["standard_4_bilateral", "standard_2"])
async def test_reload_removes_app_controls_after_protocol_change(
    hass,
    mock_coordinator_connected,
    app_ble,
    enable_custom_integrations,
    bed_type,
    layout,
):
    entry = _entry(hass, layout)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    removed = (
        {
            "cover": {"right_back", "right_legs", "both_backs", "both_legs"},
            "number": {"massage_right_intensity"},
        }
        if layout == "standard_4_bilateral"
        else {"cover": {"both"}}
    )
    for domain, keys in removed.items():
        for key in keys:
            _entity_id(hass, domain, key)
    retained = {key: _entity_id(hass, "cover", key) for key in ("back", "legs")}

    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_BED_TYPE: bed_type})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    for domain, keys in removed.items():
        for key in keys:
            assert registry.async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}") is None
    for key, entity_id in retained.items():
        assert _entity_id(hass, "cover", key) == entity_id
        assert hass.states.get(entity_id).state != "unavailable"


@pytest.mark.parametrize(
    ("option", "removed_keys", "retained_keys"),
    [
        (
            CONF_HAS_LIGHT,
            {"light_level"},
            {"massage_head_intensity", "massage_foot_intensity"},
        ),
        (CONF_HAS_MASSAGE, {"massage_head_intensity", "massage_foot_intensity"}, {"light_level"}),
    ],
)
async def test_reload_removes_numbers_for_disabled_optional_features(
    hass,
    mock_coordinator_connected,
    app_ble,
    enable_custom_integrations,
    option,
    removed_keys,
    retained_keys,
):
    entry = _entry(hass, "standard_2")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for key in removed_keys | retained_keys:
        _entity_id(hass, "number", key)

    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, data={**entry.data, option: False})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for key in removed_keys:
        assert registry.async_get_entity_id("number", DOMAIN, f"{ADDRESS}_{key}") is None
    for key in retained_keys:
        assert hass.states.get(_entity_id(hass, "number", key)).state != "unavailable"


async def test_dreamhd_entities_use_hd_frames_and_notification_aliases(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "standard_3_split_upper", "dreamhd")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    light_id = _entity_id(hass, "light", "under_bed_lights")
    assert hass.states.get(light_id).attributes["rgb_color"] == (17, 34, 51)
    auto_id = _entity_id(hass, "switch", "automatic_light")
    assert hass.states.get(auto_id).state == "off"
    right = _entity_id(hass, "number", "massage_right_intensity")
    foot = _entity_id(hass, "number", "massage_foot_intensity")
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _entity_id(hass, "button", "preset_memory_1")},
        blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": right, "value": 3}, blocking=True
    )
    await hass.services.async_call("switch", "turn_on", {"entity_id": auto_id}, blocking=True)
    assert [call.args[1].hex() for call in app_ble.write_gatt_char.await_args_list] == [
        "f1f10b01010d7e",
        "f1f14e004e7e",
        "f1f122020804307e",
        "f1f1290200002b7e",
        "f1f14e004e7e",
    ]
    callback = app_ble.start_notify.await_args_list[0].args[1]
    callback(
        SimpleNamespace(uuid=COMFORT_MOTION_LIERDA3_READ_CHAR_UUID),
        bytearray.fromhex("f2f206050200030040507e"),
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(right).state) == 2
    assert float(hass.states.get(foot).state) == 2


async def test_dreamhd_alarm_wake_and_rename_services(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "standard_2", "dreamhd")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    device_id = er.async_get(hass).async_get(_entity_id(hass, "cover", "back")).device_id
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "jiecang_set_alarm",
        {
            "device_id": device_id,
            "enabled": True,
            "time": "07:00:00",
            "weekdays": [],
            "preset": "zero_g",
            "head_level": 0,
            "foot_level": 0,
        },
        blocking=True,
    )
    assert app_ble.write_gatt_char.call_args.args[1].hex() == "f1f151080100000700020000637e"
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "jiecang_wake",
        {
            "device_id": device_id,
            "preset": "memory_1",
            "head_level": 0,
            "foot_level": 0,
        },
        blocking=True,
    )
    assert [call.args[1].hex() for call in app_ble.write_gatt_char.await_args_list] == [
        *(["f1f10b01010d7e"] * 5),
        "f1f14e004e7e",
    ]
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        DOMAIN, "jiecang_stop_wake", {"device_id": device_id}, blocking=True
    )
    assert app_ble.write_gatt_char.call_args.args[1].hex() == "f1f11101081a7e"
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        DOMAIN, "rename", {"device_id": device_id, "name": "Bed room"}, blocking=True
    )
    assert [call.args[1] for call in app_ble.write_gatt_char.await_args_list] == [
        b"\x01\xfc\x07\x08Bed room"
    ] * 2


@pytest.mark.parametrize(
    ("layout", "massage", "light"),
    [
        (layout, massage, light)
        for layout in (
            "standard_2",
            "standard_3_neck",
            "standard_3_lumbar",
            "standard_3_hi_low",
            "standard_3_split_upper",
            "standard_4_legacy",
        )
        for massage in (False, True)
        for light in (False, True)
    ]
    + [("split_series", True, True)],
)
async def test_dreamhd_all_25_configurations_gate_entities(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations, layout, massage, light
):
    from custom_components.adjustable_bed.profiles.jiecang import APP_LAYOUT_AXES

    entry = _entry(hass, layout, "dreamhd")
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HAS_MASSAGE: massage, CONF_HAS_LIGHT: light}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    keys = {entity.unique_id.removeprefix(f"{ADDRESS}_") for entity in entries}
    assert {
        entity.unique_id.removeprefix(f"{ADDRESS}_")
        for entity in entries
        if entity.domain == "cover"
    } == set(APP_LAYOUT_AXES[layout])
    assert ("massage_head_intensity" in keys) == massage
    assert ("massage_foot_intensity" in keys) == massage
    assert ("massage_right_intensity" in keys) == (
        massage and layout in ("standard_3_split_upper", "split_series")
    )
    assert ("under_bed_lights" in keys) == light
    assert ("automatic_light" in keys) == light
    assert ("light_timer" in keys) == light


@pytest.mark.parametrize("app_ble", ["negative", False], indirect=True)
async def test_dreamhd_late_light_and_yoga_entities_reconcile_repeated_transitions(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    entry = _entry(hass, "standard_2", "dreamhd")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    callback = app_ble.start_notify.await_args_list[0].args[1]
    sender = SimpleNamespace(uuid=COMFORT_MOTION_LIERDA3_READ_CHAR_UUID)
    controls = {
        "light": "under_bed_lights",
        "number": "light_level",
        "select": "light_timer",
        "switch": "automatic_light",
    }

    def has_control(domain, key):
        return registry.async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}") is not None

    for _ in range(2):
        callback(sender, bytearray.fromhex("f2f20e00060000"))
        await hass.async_block_till_done()
        assert all(not has_control(domain, key) for domain, key in controls.items())
        assert has_control("button", "preset_yoga")
        # A reply while suppression is sticky must not re-expose RGB controls.
        callback(sender, bytearray.fromhex("f2f2520733221164012c01517e"))
        await hass.async_block_till_done()
        assert all(not has_control(domain, key) for domain, key in controls.items())
        callback(sender, bytearray.fromhex("f2f20e00a00000"))
        await hass.async_block_till_done()
        assert all(has_control(domain, key) for domain, key in controls.items())
        assert not has_control("button", "preset_yoga")
        for domain, key in controls.items():
            assert hass.states.get(_entity_id(hass, domain, key)) is not None
        # Repeated notifications must not create duplicate unique IDs.
        callback(sender, bytearray.fromhex("f2f20e00a00000"))
        callback(sender, bytearray.fromhex("f2f2520733221164012c01517e"))
        await hass.async_block_till_done()
        entries = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len({(e.domain, e.unique_id) for e in entries}) == len(entries)


@pytest.mark.parametrize("app_ble", [False], indirect=True)
async def test_paired_dreamhd_late_yoga_reconciles_side_and_combined_buttons(
    hass, mock_coordinator_connected, app_ble, enable_custom_integrations
):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left_address = "AA:BB:CC:DD:EE:01"
    right_address = "AA:BB:CC:DD:EE:02"
    base = {
        CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
        CONF_JIECANG_APP_PROFILE: "dreamhd",
        CONF_JIECANG_APP_LAYOUT: "standard_2",
        CONF_JIECANG_APP_TRANSPORT: "g3",
        CONF_HAS_LIGHT: True,
        CONF_HAS_MASSAGE: True,
        CONF_MOTOR_COUNT: 2,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }
    data = build_pair_entry_data(
        {**base, CONF_ADDRESS: left_address, CONF_NAME: "Left"},
        {**base, CONF_ADDRESS: right_address, CONF_NAME: "Right"},
        name="HD pair",
    )
    entry = MockConfigEntry(
        domain=DOMAIN, title="HD pair", data=data, unique_id=data[CONF_PAIR_ID], version=4
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    pair = hass.data[DOMAIN][entry.entry_id]
    left = pair.children["left"].controller
    right = pair.children["right"].controller
    left_uid = f"{left_address}_preset_yoga"
    right_uid = f"{right_address}_preset_yoga"
    both_uid = f"{data[CONF_PAIR_ID]}_preset_yoga_both"

    def button(uid):
        return registry.async_get_entity_id("button", DOMAIN, uid)

    def reply(controller, value):
        controller._handle_notification(
            SimpleNamespace(uuid=COMFORT_MOTION_LIERDA3_READ_CHAR_UUID),
            bytearray.fromhex(value),
        )

    assert all(button(uid) is None for uid in (left_uid, right_uid, both_uid))
    reply(left, "f2f20e00060000")
    await hass.async_block_till_done()
    assert button(left_uid) is not None
    assert button(right_uid) is None and button(both_uid) is None
    reply(right, "f2f20e00060000")
    await hass.async_block_till_done()
    assert all(button(uid) is not None for uid in (left_uid, right_uid, both_uid))
    app_ble.write_gatt_char.reset_mock()
    await hass.services.async_call(
        "button", "press", {"entity_id": button(both_uid)}, blocking=True
    )
    assert [call.args[1].hex() for call in app_ble.write_gatt_char.await_args_list] == [
        "f1f1280200002a7e",
        "f1f14e004e7e",
    ] * 2
    reply(left, "f2f20e00a00000")
    await hass.async_block_till_done()
    assert button(left_uid) is None and button(both_uid) is None
    assert button(right_uid) is not None
    reply(left, "f2f20e00060000")
    reply(right, "f2f20e00060000")
    await hass.async_block_till_done()
    assert all(button(uid) is not None for uid in (left_uid, right_uid, both_uid))
    for uid in (left_uid, right_uid, both_uid):
        assert (
            len(
                [
                    e
                    for e in registry.entities.values()
                    if e.domain == "button" and e.unique_id == uid
                ]
            )
            == 1
        )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
