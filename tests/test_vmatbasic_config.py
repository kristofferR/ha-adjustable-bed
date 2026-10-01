"""Explicit profiles and saved settings across real setup and options forms."""

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    CONF_PAIR_SELECTION,
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.pairing_candidates import encode_pair_selection
from tests.test_vmatbasic import make_controller

ADDRESS = "11:22:33:44:55:66"


def app_data(profile="basic", **extra):
    return {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "App receiver",
        const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
        const.CONF_VMATBASIC_PROFILE: profile,
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        **extra,
    }


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_all_setup_routes_collect_explicit_profile_without_bond(
    hass, mock_bluetooth_service_info, step
):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, "async_step_" + step)(
        {
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Basic",
            const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    # The first editable selector change rebuilds its formerly generic form.
    if result["step_id"] == step:
        values = result["data_schema"]({CONF_ADDRESS: ADDRESS} if step == "manual_entry" else {})
        assert const.CONF_MOTOR_COUNT not in values
        assert const.CONF_MOTOR_PULSE_DELAY_MS not in values
        result = await getattr(flow, "async_step_" + step)(values)
    assert result["step_id"] == "vmatbasic"
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        result = await flow.async_step_vmatbasic({const.CONF_VMATBASIC_PROFILE: "basic"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = finish.call_args.args[0]
    assert data[const.CONF_VMATBASIC_PROFILE] == "basic"
    assert data[const.CONF_MOTOR_PULSE_DELAY_MS] == 30
    assert data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert not const.requires_pairing(const.BED_TYPE_VMATBASIC)
    assert not const.requires_pairing_after_service_discovery(const.BED_TYPE_VMATBASIC)


@pytest.mark.parametrize("profile", ["cbi", "xtbox"])
async def test_profile_selection_rebuilds_exact_floor_domain_before_finish(hass, profile):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context, flow._manual_data = hass, {}, app_data()
    result = await flow.async_step_vmatbasic({const.CONF_VMATBASIC_PROFILE: profile})
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    values = schema({const.CONF_VMATBASIC_FLOOR_LEVEL: 6 if profile == "xtbox" else 255})
    assert isinstance(values, dict)
    assert values[const.CONF_VMATBASIC_PROFILE] == profile
    with patch.object(
        flow,
        "_finish_with_verify",
        new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
    ) as finish:
        await flow.async_step_vmatbasic(values)
    assert (
        finish.call_args.args[0][const.CONF_VMATBASIC_FLOOR_LEVEL]
        == values[const.CONF_VMATBASIC_FLOOR_LEVEL]
    )


@pytest.mark.parametrize("options", [False, True])
@pytest.mark.parametrize("old,new", [("cbi", "xtbox"), ("xtbox", "cbi"), ("xtbox", "basic")])
async def test_full_rendered_profile_change_discards_all_old_dependent_defaults(
    hass, options, old, new
):
    data = app_data(
        old, **{const.CONF_VMATBASIC_FLOOR_LEVEL: 6, const.CONF_VMATBASIC_FLOOR_MINUTES: 123}
    )
    entry = None
    if options:
        entry = MockConfigEntry(domain=const.DOMAIN, data=data)
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.handler, flow.hass = entry.entry_id, hass
        step = flow.async_step_settings
    else:
        flow = AdjustableBedConfigFlow()
        flow.context, flow.hass, flow._manual_data = {}, hass, data
        step = flow.async_step_vmatbasic
    rendered = await step()
    schema = rendered["data_schema"]
    assert isinstance(schema, vol.Schema)
    submitted = schema({})
    assert isinstance(submitted, dict)
    submitted[const.CONF_VMATBASIC_PROFILE] = new
    with (
        patch.object(
            flow,
            "_finish_with_verify",
            new=AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY}),
        )
        if not options
        else patch("custom_components.adjustable_bed.config_flow._LOGGER")
    ):
        rebuilt = await step(submitted)
    retained = flow._pending_data if options else flow._manual_data
    assert retained[const.CONF_VMATBASIC_PROFILE] == new
    assert const.CONF_VMATBASIC_FLOOR_LEVEL not in retained
    assert const.CONF_VMATBASIC_FLOOR_MINUTES not in retained
    if options or new != "basic":
        assert rebuilt["type"] == FlowResultType.FORM
        assert not rebuilt["errors"]
    if options:
        schema = rebuilt["data_schema"]
        assert isinstance(schema, vol.Schema)
        next_submission = schema({})
        assert isinstance(next_submission, dict)
        assert const.CONF_VMATBASIC_FLOOR_LEVEL not in next_submission
        if new != "basic":
            assert next_submission[const.CONF_VMATBASIC_FLOOR_MINUTES] == 0
        completed = await step(next_submission)
        assert completed["type"] == FlowResultType.CREATE_ENTRY
        assert entry is not None
        assert entry.data[const.CONF_VMATBASIC_PROFILE] == new
        assert const.CONF_VMATBASIC_FLOOR_LEVEL not in entry.data
        assert entry.data.get(const.CONF_VMATBASIC_FLOOR_MINUTES) == (None if new == "basic" else 0)


@pytest.mark.parametrize("profile", const.VMATBASIC_PROFILES)
async def test_real_factory_profile_offline_exposure_and_no_model_inference(hass, profile):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(profile))
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator,
        const.BED_TYPE_VMATBASIC,
        "auto",
        None,
        ble_model="XT-Box",
        manufacturer_data={0xFFFF: b"\xba\xbe\x11\x11\x00\x00"},
    )
    assert controller.profile == profile
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert controller.memory_slot_count == 0
    assert const.BED_TYPE_VMATBASIC in const.OFFLINE_CAPABILITY_SAFE_BED_TYPES
    await coordinator._command_scheduler.async_shutdown()


async def test_saved_zero_and_timer_survive_real_factory_reconstruction(hass):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data("cbi"))
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_controller("cbi").client
    first = await create_controller(
        coordinator, const.BED_TYPE_VMATBASIC, "auto", coordinator.client
    )
    coordinator._controller = first
    await first.set_floor_level(0)
    await first.set_floor_minutes(1439)
    assert entry.data[const.CONF_VMATBASIC_FLOOR_LEVEL] == 0
    assert entry.data[const.CONF_VMATBASIC_FLOOR_MINUTES] == 1439
    second = await create_controller(
        coordinator, const.BED_TYPE_VMATBASIC, "auto", coordinator.client
    )
    coordinator._client.read_gatt_char.side_effect = None
    coordinator._client.read_gatt_char.return_value = bytes(3)
    coordinator._client.write_gatt_char.reset_mock()
    await second.floor_toggle()
    assert coordinator._client.write_gatt_char.call_args.args[1] == bytes.fromhex("00059f")
    await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize(
    "profile,key,value",
    [
        ("xtbox", const.CONF_VMATBASIC_FLOOR_LEVEL, 0),
        ("xtbox", const.CONF_VMATBASIC_FLOOR_MINUTES, 256),
        ("cbi", const.CONF_VMATBASIC_FLOOR_LEVEL, 256),
        ("cbi", const.CONF_VMATBASIC_FLOOR_MINUTES, 1440),
    ],
)
async def test_invalid_saved_parameters_do_not_finish_setup(hass, profile, key, value):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context, flow._manual_data = hass, {}, app_data(profile)
    result = await flow.async_step_vmatbasic({key: value})
    assert result["errors"] == {key: "vmatbasic_invalid"}


@pytest.mark.parametrize("profile", ["cbi", "xtbox"])
@pytest.mark.parametrize(
    "field", [const.CONF_VMATBASIC_FLOOR_LEVEL, const.CONF_VMATBASIC_FLOOR_MINUTES]
)
@pytest.mark.parametrize("value", [1.5, True, float("nan"), float("inf")])
async def test_rendered_profile_schema_rejects_nonwhole_values(hass, profile, field, value):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context, flow._manual_data = hass, {}, app_data(profile)
    result = await flow.async_step_vmatbasic()
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    with pytest.raises(vol.Invalid):
        schema({field: value})


@pytest.mark.parametrize("profiles", [("basic", "basic"), ("basic", "cbi"), ("xtbox", "basic")])
async def test_real_combine_flow_rejects_basic_profile_before_creation(hass, profiles):
    from tests.test_vmatbasic_public import close, target

    children = [
        await target(hass, profile, f"AA:BB:CC:DD:EE:0{index}")
        for index, profile in enumerate(profiles, 1)
    ]
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    entries = [child.entry for child in children]
    try:
        with patch.object(flow, "_pairable_single_entries", return_value=entries):
            result = await flow.async_step_pair_beds(
                {
                    CONF_PAIR_SELECTION: encode_pair_selection(
                        entries[0].entry_id, entries[1].entry_id
                    )
                }
            )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "vmatbasic_link_profile"}
        assert all(child.client.write_gatt_char.await_count == 0 for child in children)
    finally:
        for child in children:
            await close(child)


@pytest.mark.parametrize("profiles", [("cbi", "cbi"), ("cbi", "xtbox"), ("xtbox", "xtbox")])
async def test_real_combine_flow_preserves_each_admissible_profile(hass, profiles):
    from tests.test_vmatbasic_public import close, target

    children = [
        await target(hass, profile, f"AA:BB:CC:DD:EE:0{index}")
        for index, profile in enumerate(profiles, 1)
    ]
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    entries = [child.entry for child in children]
    try:
        with patch.object(flow, "_pairable_single_entries", return_value=entries):
            result = await flow.async_step_pair_beds(
                {
                    CONF_PAIR_SELECTION: encode_pair_selection(
                        entries[0].entry_id, entries[1].entry_id
                    ),
                    CONF_NAME: "Linked",
                }
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        descriptors = result["data"][const.CONF_PAIR_CHILDREN]
        assert [descriptor[const.CONF_VMATBASIC_PROFILE] for descriptor in descriptors] == list(
            profiles
        )
        assert len({descriptor[CONF_ADDRESS] for descriptor in descriptors}) == 2
        assert all(child.client.write_gatt_char.await_count == 0 for child in children)
    finally:
        for child in children:
            await close(child)
