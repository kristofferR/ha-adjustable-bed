"""Explicit SIMMONS profile: factory routing, setup options and shared discovery."""

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
from custom_components.adjustable_bed.config_flow import _motor_count_options
from custom_components.adjustable_bed.const import (
    BED_TYPE_SIMMONS,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BLE_DEVICE_NAME,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    SIMMONS_VARIANTS,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from tests.test_controller_contract import _FactoryCoordinator


@pytest.mark.parametrize(
    ("variant", "name", "protocol", "inclined"),
    [
        ("auto", "OKIN-112233", "okin", False),
        ("auto", "SmartBed-112233", "smartbed", False),
        ("simmons_okin", "SmartBed-112233", "okin", False),
        ("simmons_inclined_smartbed", "OKIN-112233", "smartbed", True),
        ("simmons_inclined", None, "smartbed", True),
    ],
)
async def test_factory_resolves_protocol_and_layout_offline(variant, name, protocol, inclined):
    coordinator = _FactoryCoordinator()
    # Offline, the factory is handed the display name; only the stored raw
    # Bluetooth name may feed the app's name rule.
    coordinator.entry.data[CONF_BLE_DEVICE_NAME] = name
    controller = await create_controller(
        coordinator, BED_TYPE_SIMMONS, variant, None, device_name="OKIN display name"
    )
    assert controller.protocol_diagnostics["simmons_protocol"] == protocol
    assert controller.protocol_diagnostics["simmons_layout"] == ("inclined" if inclined else "regular")
    assert {spec.key for spec in controller.motor_control_specs} == {"back", "legs"}
    assert {spec.key for spec in controller.controller_state_sensor_specs} == {
        "simmons_alarm_1",
        "simmons_alarm_2",
    }


def test_profile_constants_and_setup_options():
    assert BED_TYPE_SIMMONS in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert BED_TYPE_SIMMONS in BEDS_WITHOUT_ANGLE_FEEDBACK
    assert not bed_type_has_position_feedback(BED_TYPE_SIMMONS, "auto")
    assert not requires_pairing(BED_TYPE_SIMMONS)
    assert get_motor_pulse_defaults(BED_TYPE_SIMMONS) == (4, 300)
    assert _motor_count_options(BED_TYPE_SIMMONS) == [2]
    assert get_variants_for_bed_type(BED_TYPE_SIMMONS) == SIMMONS_VARIANTS
    assert is_valid_variant_for_bed_type(BED_TYPE_SIMMONS, "simmons_inclined_okin")
    assert not is_valid_variant_for_bed_type(BED_TYPE_SIMMONS, "woosa")
    assert get_actuator_group_for_bed_type(BED_TYPE_SIMMONS) == ("okin", "SIMMONS app")
    assert any(
        option["value"] == BED_TYPE_SIMMONS and option["label"] == "SIMMONS app"
        for option in get_bed_type_options()
    )


@pytest.mark.parametrize("name", ["OKIN-112233", "SmartBed-112233", "Simmons"])
@pytest.mark.parametrize(
    "service",
    ["6e400001-b5a3-f393-e0a9-e50e24dcca9e", "0000ffe5-0000-1000-8000-00805f9b34fb"],
)
def test_shared_names_and_services_never_select_the_app(name, service):
    info = MagicMock()
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = [service]
    info.manufacturer_data = {}
    assert detect_bed_type(info) != BED_TYPE_SIMMONS


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_setup_hides_motor_count_and_the_fixed_refresh_delay(hass, step):
    from unittest.mock import AsyncMock

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = BED_TYPE_SIMMONS
    flow._disambiguated_bed_type = BED_TYPE_SIMMONS
    info = MagicMock()
    info.name = "OKIN-112233"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["0000ffe5-0000-1000-8000-00805f9b34fb"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    form = await getattr(flow, f"async_step_{step}")()
    assert form["type"] == "form"
    markers = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers
    assert CONF_MOTOR_PULSE_DELAY_MS not in markers


async def test_options_switch_to_simmons_keeps_the_layout_choice(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_FFE,
        CONF_BED_TYPE,
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
            CONF_BED_TYPE: BED_TYPE_OKIN_FFE,
            CONF_MOTOR_COUNT: 4,
            CONF_MOTOR_PULSE_COUNT: 7,
            CONF_MOTOR_PULSE_DELAY_MS: 150,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_SIMMONS}, step_id="settings")
    assert rebuilt["type"] == "form"
    markers = {marker.schema: marker for marker in rebuilt["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers and CONF_MOTOR_PULSE_DELAY_MS not in markers
    assert CONF_PROTOCOL_VARIANT in markers
    saved = await flow._async_options_form(
        {CONF_BED_TYPE: BED_TYPE_SIMMONS, CONF_PROTOCOL_VARIANT: "simmons_inclined"},
        step_id="settings",
    )
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_SIMMONS
    assert entry.data[CONF_PROTOCOL_VARIANT] == "simmons_inclined"
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert (entry.data[CONF_MOTOR_PULSE_COUNT], entry.data[CONF_MOTOR_PULSE_DELAY_MS]) == (4, 300)
