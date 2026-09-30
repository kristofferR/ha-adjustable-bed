"""Explicit Serenity selection persists independently of shared OKIN discovery."""

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
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
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
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
    assert get_actuator_group_for_bed_type(BED_TYPE_SERENITY) == ("okin", "Jordan's Serenity app")
    assert (
        next(option for option in get_bed_type_options() if option["value"] == BED_TYPE_SERENITY)[
            "label"
        ]
        == "Jordan's Serenity app"
    )


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


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_setup_hides_unproven_motor_count_and_fixed_refresh_delay(hass, step):
    from unittest.mock import AsyncMock

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = BED_TYPE_SERENITY
    flow._disambiguated_bed_type = BED_TYPE_SERENITY
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    form = await getattr(flow, f"async_step_{step}")()
    assert form["type"] == "form"
    markers = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers
    assert CONF_MOTOR_PULSE_DELAY_MS not in markers


async def test_options_switch_from_generic_profile_preserves_explicit_serenity_defaults(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

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


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
@pytest.mark.parametrize(
    "shown,requested", [(BED_TYPE_SERENITY, BED_TYPE_OCTO), (BED_TYPE_OCTO, BED_TYPE_SERENITY)]
)
async def test_changing_setup_profile_restores_choices_and_keeps_entered_values(
    hass, step, shown, requested
):
    from unittest.mock import AsyncMock

    from homeassistant.const import CONF_ADDRESS, CONF_NAME

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = shown
    flow._disambiguated_bed_type = shown
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    submitted = {
        CONF_BED_TYPE: requested,
        CONF_NAME: "Edited bed",
        CONF_ADDRESS: "11:22:33:44:55:66",
    }
    form = await getattr(flow, f"async_step_{step}")(submitted)
    assert form["type"] == "form"
    assert form["step_id"] == step
    markers = {marker.schema: marker for marker in form["data_schema"].schema}
    assert (CONF_MOTOR_COUNT in markers) is (requested != BED_TYPE_SERENITY)
    assert (CONF_MOTOR_PULSE_DELAY_MS in markers) is (requested != BED_TYPE_SERENITY)
    assert markers[CONF_BED_TYPE].description["suggested_value"] == requested
    assert markers[CONF_NAME].description["suggested_value"] == "Edited bed"
    if step == "manual_entry":
        assert markers[CONF_ADDRESS].description["suggested_value"] == "11:22:33:44:55:66"
    assert flow._manual_data is None
    assert flow._pending_entry is None
