"""Explicit Serenity selection persists independently of shared OKIN discovery."""

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.actuator_groups import actuator_group_for
from custom_components.adjustable_bed.config_flow import (
    _default_motor_count,
    _is_valid_motor_count,
    _motor_count_options,
    _normalize_fixed_motor_count,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    BED_TYPE_SERENITY,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import _create_from_registry
from custom_components.adjustable_bed.detection import (
    bed_type_label,
    detect_bed_type,
    get_bed_type_options,
)
from tests.form_helpers import NEW_BED_ROUTES, finish_new_bed, form_fields, start_new_bed
from tests.test_controller_contract import _FactoryCoordinator


async def test_explicit_profile_builds_fixed_controls_without_live_advertisement():
    coordinator = _FactoryCoordinator()
    coordinator.protocol_variant = "support"
    coordinator.motor_count = 4
    controller = await _create_from_registry(coordinator, BED_TYPE_SERENITY)
    assert controller is not None
    assert controller.protocol_diagnostics["cst_profile"] == "serenity"
    assert {spec.key for spec in controller.motor_control_specs} == {"head", "feet"}
    assert controller.memory_slot_count == 2
    assert controller.requires_notification_channel
    assert actuator_group_for(BED_TYPE_SERENITY) == "okin"
    assert (
        next(option for option in get_bed_type_options() if option["value"] == BED_TYPE_SERENITY)[
            "label"
        ]
        == "Serenity and Tranquil apps · Jordan's"
    )
    # A saved entry keeps its own app's label.
    assert bed_type_label(BED_TYPE_SERENITY) == "Jordan's Serenity app"


@pytest.mark.parametrize("old_count", [1, 2, 3, 4])
def test_fixed_named_axis_layout_normalizes_old_generic_motor_setting(old_count):
    assert _motor_count_options(BED_TYPE_SERENITY) == [2]
    assert _default_motor_count(BED_TYPE_SERENITY) == 2
    assert _normalize_fixed_motor_count(BED_TYPE_SERENITY, "auto", old_count) == 2
    assert _is_valid_motor_count(BED_TYPE_SERENITY, "auto", old_count) is (old_count == 2)
    assert not requires_pairing(BED_TYPE_SERENITY)
    assert not bed_type_has_position_feedback(BED_TYPE_SERENITY, "auto")
    assert get_motor_pulse_defaults(BED_TYPE_SERENITY) == (10, 100)


@pytest.mark.parametrize("name", ["OKIN", "OKIN-003444", "okin example", "UnNamed"])
def test_shared_name_and_service_do_not_select_the_serenity_app(name):
    info = MagicMock(name=name)
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    assert detect_bed_type(info) != BED_TYPE_SERENITY


def _okin_flow(hass):
    """A setup for a shared OKIN receiver, which names no app."""
    from unittest.mock import AsyncMock

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    return flow


async def _final_settings(hass, route: str, choice: str):
    """The flow and final settings of a new bed set up as ``choice``."""
    flow = _okin_flow(hass)
    result = await start_new_bed(flow, route, choice)
    if result["step_id"] == "jordans_family":
        # The Jordan's row asks which app.
        result = await flow.async_step_jordans_family({"choice": "serenity"})
    assert result["step_id"] == "finish_settings"
    return flow, result


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_setup_hides_unproven_motor_count_and_fixed_refresh_delay(hass, route):
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    _flow, form = await _final_settings(hass, route, BED_TYPE_SERENITY)
    fields = {marker.schema for marker in form_fields(form["data_schema"])}
    assert CONF_MOTOR_COUNT not in fields
    assert CONF_MOTOR_PULSE_DELAY_MS not in fields


async def test_options_switch_from_generic_profile_preserves_explicit_serenity_defaults(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_CST,
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_MOTOR_COUNT: 4,
            CONF_PROTOCOL_VARIANT: "support",
            CONF_MOTOR_PULSE_COUNT: 7,
            CONF_MOTOR_PULSE_DELAY_MS: 150,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_SERENITY}, step_id="settings")
    assert rebuilt["type"] == "form"
    markers = {marker.schema for marker in rebuilt["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers
    assert CONF_MOTOR_PULSE_DELAY_MS not in markers
    assert CONF_PROTOCOL_VARIANT not in markers
    saved = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_SERENITY}, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_SERENITY
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert entry.data[CONF_MOTOR_PULSE_COUNT] == 10
    assert entry.data[CONF_MOTOR_PULSE_DELAY_MS] == 100
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True
    controller = await _create_from_registry(_FactoryCoordinator(), entry.data[CONF_BED_TYPE])
    assert controller.protocol_diagnostics["cst_profile"] == "serenity"
    assert controller.memory_slot_count == 2


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_the_final_settings_ignore_fields_the_app_sets_itself(hass, route):
    """A client that ignores the form cannot change what the app sets."""
    from unittest.mock import AsyncMock

    from homeassistant.const import CONF_NAME

    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    flow, form = await _final_settings(hass, route, BED_TYPE_SERENITY)
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await finish_new_bed(
        flow,
        form,
        {CONF_NAME: "Edited bed", CONF_MOTOR_COUNT: 4, "timing": {CONF_MOTOR_PULSE_DELAY_MS: "300"}},
    )
    saved = flow._finish_with_verify.await_args.args[0]
    assert (saved[CONF_MOTOR_COUNT], saved[CONF_MOTOR_PULSE_DELAY_MS]) == (2, 100)


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_the_final_settings_show_each_routes_own_fields(hass, route):
    from custom_components.adjustable_bed.const import (
        BED_TYPE_LINAK,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    )

    _flow, form = await _final_settings(hass, route, BED_TYPE_OCTO)
    octo = {marker.schema for marker in form_fields(form["data_schema"])}
    assert CONF_MOTOR_COUNT not in octo
    assert CONF_OCTO_MOTOR_COUNT_OVERRIDE in octo
    assert CONF_MOTOR_PULSE_DELAY_MS in octo
    _flow, form = await _final_settings(hass, route, BED_TYPE_LINAK)
    linak = {marker.schema for marker in form_fields(form["data_schema"])}
    assert {CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS} <= linak
    assert CONF_OCTO_MOTOR_COUNT_OVERRIDE not in linak

