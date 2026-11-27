"""Alya's actual setup conversion, shared actions and native massage entities."""

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_unpair_entry
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.alya.controller import AlyaController
from custom_components.adjustable_bed.beds.alya.protocol import TRANSPORTS, clock_frame
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    PAIR_MODE_SINGLE_ADDRESS,
)
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profiles.alya import PROFILES
from custom_components.adjustable_bed.runtime_data import entry_runtime
from tests.test_alya import NOW, PARSERS, frames, make

ADDRESS = "AA:BB:CC:DD:EE:90"


class Gatt:
    def __init__(self, **fields):
        self.__dict__.update(fields)


@pytest.fixture
def no_alya_waits(monkeypatch):
    async def pause(seconds, cancel):
        return cancel.is_set()

    monkeypatch.setattr(AlyaController, "_pause", staticmethod(pause))


def report_for(profile):
    protocol = PROFILES[profile].protocol
    key = {
        "P1": "p1-status",
        "P2": "p2-status16",
        "P3": "p3-massage",
        "P4": "p4-massage",
    }[protocol]
    if profile == "dacheng_2":
        key = "p2-status16"
    return bytes(next(v for v in PARSERS if v["id"] == key)["inputs"]["data"])


async def setup_alya(hass, client, profile):
    p = PROFILES[profile]
    route = TRANSPORTS[p.protocol]
    tx = Gatt(uuid=route.write, properties=("write",), handle=1, descriptors=[])
    rx = Gatt(uuid=route.notify, properties=("notify",), handle=2, descriptors=[])
    client.services = [
        Gatt(uuid=route.write_service, characteristics=[tx]),
        Gatt(uuid=route.notify_service, characteristics=[rx]),
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alya",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Alya",
            CONF_BED_TYPE: "alya",
            CONF_PROTOCOL_VARIANT: profile,
            CONF_MOTOR_COUNT: p.motors,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_CONNECTION_MODE: "always",
            "motor_pulse_count": 1,
        },
        unique_id=ADDRESS,
        version=5,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("profile", PROFILES)
async def test_native_entities_and_settings_menu(
    hass,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    no_alya_waits,
    profile,
):
    entry = await setup_alya(hass, mock_bleak_client, profile)
    controller = entry_runtime(hass, entry.entry_id).controller
    assert isinstance(controller, AlyaController)
    rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(
        row.unique_id.endswith(("_alya_hpsup", "_alya_hpsdown", "_alya_report")) for row in rows
    )
    timer = next(row for row in rows if row.unique_id.endswith("_massage_timer"))
    state = hass.states.get(timer.entity_id)
    assert state is not None and state.state == "unknown"
    assert state.attributes["options"] == ["10 min", "20 min", "30 min"]
    numbers = [row for row in rows if row.domain == "number" and "massage" in row.unique_id]
    expected_zones = (
        {"all"}
        if profile.startswith(("bluetooth_", "cb_"))
        else {"head"}
        if profile == "cb1221_2"
        else {"head", "foot"}
    )
    assert len(numbers) == len(expected_zones)
    assert set(controller.massage_intensity_zones) == expected_zones
    assert not any(
        row.unique_id.endswith(("_alya_time10", "_alya_set-clock", "intensity1")) for row in rows
    )

    def fresh_report():
        callback = mock_bleak_client.start_notify.call_args.args[1]
        callback(controller._session.notify, bytearray(report_for(profile)))

    fresh_report()
    mock_bleak_client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": timer.entity_id,
            "option": "20 min",
        },
        blocking=True,
    )
    assert bytes(mock_bleak_client.write_gatt_char.call_args_list[0].args[1]) == (
        controller.profile.commands["time20"].encode(controller.profile.protocol, controller._side)
    )
    assert hass.states.get(timer.entity_id).state == "unknown"
    for row in numbers:
        state = hass.states.get(row.entity_id)
        assert state is not None and state.state == "unknown"
        assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (
            1,
            3,
            1,
        )
        fresh_report()
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": row.entity_id,
                "value": 2,
            },
            blocking=True,
        )
        zone = (
            "head"
            if "massage_head_" in row.unique_id
            else "foot"
            if "massage_foot_" in row.unique_id
            else ""
        )
        assert bytes(mock_bleak_client.write_gatt_char.call_args_list[0].args[1]) == (
            controller.profile.commands[f"{zone}intensity2"].encode(
                controller.profile.protocol, controller._side
            )
        )
        assert hass.states.get(row.entity_id).state == "unknown"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert ("pair_sides" in result["menu_options"]) is (profile == "dacheng_5")
    assert supports_single_address_pairing("alya", profile) is (profile == "dacheng_5")


async def test_settings_conversion_routes_native_entities_and_reverts(
    hass,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    no_alya_waits,
):
    entry = await setup_alya(hass, mock_bleak_client, "dacheng_5")
    original = dict(entry.data)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pair_sides"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"confirm": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_PAIR_MODE] == PAIR_MODE_SINGLE_ADDRESS
    assert [child[CONF_CB24_BED_SELECTION] for child in entry.data[CONF_PAIR_CHILDREN]] == [
        0xAA,
        0xBB,
    ]
    rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    for side, selector in (("left", 1), ("right", 2)):
        timer = next(row for row in rows if row.unique_id.endswith("_massage_timer_" + side))
        paired = entry_runtime(hass, entry.entry_id)
        child = paired.child_for_side(side)
        assert child is not None
        controller = child.controller
        assert isinstance(controller, AlyaController)
        callback = mock_bleak_client.start_notify.call_args.args[1]
        callback(controller._session.notify, bytearray(report_for("dacheng_5")))
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": timer.entity_id,
                "option": "10 min",
            },
            blocking=True,
        )
        expected = controller.profile.commands["time10"].encode("P4", selector)
        assert bytes(mock_bleak_client.write_gatt_char.call_args_list[0].args[1]) == expected
    await async_unpair_entry(hass, entry)
    await hass.async_block_till_done()
    assert dict(entry.data) == original


def test_side_setting_remains_owned_and_unknown_layouts_cannot_convert():
    profile = per_side_profile("alya", "dacheng_5")
    assert profile is not None and CONF_CB24_BED_SELECTION in profile.keys
    for variant in (None, "auto", "dacheng_4", "missing"):
        assert not supports_single_address_pairing("alya", variant)


@pytest.mark.parametrize("profile", PROFILES)
async def test_native_control_validation_and_only_shared_clock(profile, no_alya_waits, monkeypatch):
    c = make(profile)
    await c.async_discover_capabilities()
    for zone, level in (("all", 0), ("head", 4), ("right", 2), ("all", True)):
        with pytest.raises(ServiceValidationError):
            await c.set_massage_intensity(zone, level)
    for minutes in (0, 15, True):
        with pytest.raises(ServiceValidationError):
            await c.set_massage_timer(minutes)
    with pytest.raises(ServiceValidationError):
        await c.execute("set-clock")
    assert frames(c) == []
    assert not any(spec.key == "alya_set-clock" for spec in c.controller_button_specs)
    if c.supports_clock_sync:
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.alya.controller.dt_util.now", lambda: NOW
        )
        await c.sync_clock()
        assert frames(c) == [clock_frame(c.profile.protocol, NOW).hex()]
