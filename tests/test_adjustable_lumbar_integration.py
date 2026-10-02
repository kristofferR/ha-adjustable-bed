"""Adjustable bed (Lumbar) profile wiring: setup, entities, services and pairs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedOptionsFlow,
    _motor_count_options,
    _name_rule_setup_name,
)
from custom_components.adjustable_bed.const import (
    ADJUSTABLE_LUMBAR_VARIANTS,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_DIAGNOSTIC,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    SIDE_BOTH,
    VARIANT_AUTO,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from tests.conftest import make_controller_mock
from tests.test_adjustable_lumbar import make_controller
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_malouf_app_entities import configure_entity_runtime


@pytest.mark.parametrize(
    ("variant", "stored", "branch"),
    [
        (VARIANT_AUTO, "OKIN-1", "okin"),
        (VARIANT_AUTO, "Star25", "star"),
        (VARIANT_AUTO, None, None),
        ("adjustable_lumbar_okin", "Star25", "okin"),
        ("adjustable_lumbar_star", None, "star"),
    ],
)
async def test_offline_factory_never_reads_the_display_name(variant, stored, branch):
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[CONF_BLE_DEVICE_NAME] = stored
    controller = await create_controller(
        coordinator, BED_TYPE_ADJUSTABLE_LUMBAR, variant, None, device_name="OKIN display"
    )
    assert controller.protocol_diagnostics["adjustable_lumbar_branch"] == branch
    assert {spec.key for spec in controller.motor_control_specs} == {"head", "feet", "lumbar"}


def test_profile_constants_and_setup_options():
    assert BED_TYPE_ADJUSTABLE_LUMBAR in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert BED_TYPE_ADJUSTABLE_LUMBAR in BEDS_WITHOUT_ANGLE_FEEDBACK
    assert not bed_type_has_position_feedback(BED_TYPE_ADJUSTABLE_LUMBAR, VARIANT_AUTO)
    assert not requires_pairing(BED_TYPE_ADJUSTABLE_LUMBAR)
    assert get_motor_pulse_defaults(BED_TYPE_ADJUSTABLE_LUMBAR) == (10, 100)
    assert _motor_count_options(BED_TYPE_ADJUSTABLE_LUMBAR) == [3]
    assert get_variants_for_bed_type(BED_TYPE_ADJUSTABLE_LUMBAR) == ADJUSTABLE_LUMBAR_VARIANTS
    assert is_valid_variant_for_bed_type(BED_TYPE_ADJUSTABLE_LUMBAR, "adjustable_lumbar_star")
    assert not is_valid_variant_for_bed_type(BED_TYPE_ADJUSTABLE_LUMBAR, "simmons_okin")
    assert get_actuator_group_for_bed_type(BED_TYPE_ADJUSTABLE_LUMBAR) == (
        "okin",
        "Adjustable bed (Lumbar) app",
    )
    assert any(
        option["value"] == BED_TYPE_ADJUSTABLE_LUMBAR for option in get_bed_type_options()
    )
    assert _name_rule_setup_name(BED_TYPE_ADJUSTABLE_LUMBAR, "Star25") == {
        CONF_BLE_DEVICE_NAME: "Star25"
    }
    assert _name_rule_setup_name(BED_TYPE_ADJUSTABLE_LUMBAR, "AA:BB:CC:DD:EE:FF") == {}


@pytest.mark.parametrize("name", ["OKIN-112233", "Star252201", "SmartBed-1"])
@pytest.mark.parametrize(
    "service", ["6e400001-b5a3-f393-e0a9-e50e24dcca9e", "62741523-52f9-8864-b1ab-3b3a8d65950b"]
)
def test_shared_names_and_services_never_select_the_app(name, service):
    info = MagicMock()
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = [service]
    info.manufacturer_data = {}
    assert detect_bed_type(info) != BED_TYPE_ADJUSTABLE_LUMBAR


async def test_buttons_expose_the_app_surface(hass):
    runtime = configure_entity_runtime(hass, make_controller("OKIN-1"), BED_TYPE_ADJUSTABLE_LUMBAR)
    keys = {
        entity.unique_id.removeprefix("bed_").removesuffix("_left")
        for entity in _button_entities_for(hass, runtime)
    }
    assert {
        "preset_flat",
        "preset_zero_g",
        "preset_lounge",
        "preset_incline",
        "preset_anti_snore",
        "toggle_light",
        "massage_all_off",
        "massage_all_up",
        "massage_all_down",
        "adjustable_lumbar_save_zero_g",
        "adjustable_lumbar_wave_1",
        "adjustable_lumbar_massage_on",
        "adjustable_lumbar_check_massage",
    } <= keys
    assert not {"preset_tv", "preset_memory_1", "program_memory_1", "massage_all_toggle"} & keys


@pytest.mark.parametrize("retain", [True, False])
async def test_app_buttons_retire_with_the_profile(hass, retain):
    controller = (
        make_controller("OKIN-1")
        if retain
        else make_controller_mock(
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            controller_button_specs=(),
            position_number_specs=(),
        )
    )
    runtime = configure_entity_runtime(
        hass, controller, BED_TYPE_ADJUSTABLE_LUMBAR if retain else BED_TYPE_DIAGNOSTIC
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "button", DOMAIN, "bed_adjustable_lumbar_save_incline_left", config_entry=runtime.entry
    )
    _button_entities_for(hass, runtime)
    assert (registry.async_get(old.entity_id) is not None) is retain


def _service_target(profile=BED_TYPE_ADJUSTABLE_LUMBAR):
    controller = make_controller("OKIN-1")
    controller.hold_control = AsyncMock()
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Lumbar"
    coordinator.bed_type = profile
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.mark.parametrize(
    ("control", "error"),
    [("save_lounge", None), ("massage_stop", "combination"), ("tv", "combination")],
)
async def test_hold_service_preflights_before_writing(hass, control, error):
    await async_register_services(hass)
    coordinator, controller = _service_target()
    call = {"device_id": "bed", "control": control, "duration": 6}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(
                    DOMAIN, "adjustable_lumbar_hold_control", call, blocking=True
                )
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(
                DOMAIN, "adjustable_lumbar_hold_control", call, blocking=True
            )
            controller.hold_control.assert_awaited_once_with("save_lounge", 6000)


async def test_hold_service_refuses_a_mixed_selection_before_any_write(hass):
    await async_register_services(hass)
    lumbar, lumbar_controller = _service_target()
    other, _ = _service_target("okin_64bit")
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(lumbar, SIDE_BOTH), (other, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="Adjustable bed"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "adjustable_lumbar_hold_control",
            {"device_id": ["a", "b"], "control": "flat", "duration": 1},
            blocking=True,
        )
    lumbar.async_execute_controller_command.assert_not_awaited()
    lumbar_controller.hold_control.assert_not_awaited()


def test_service_metadata_lists_every_held_control():
    from pathlib import Path

    import yaml

    from custom_components.adjustable_bed.beds.adjustable_lumbar import HELD_CONTROLS

    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    services = yaml.safe_load((root / "services.yaml").read_text())
    field = services["adjustable_lumbar_hold_control"]["fields"]["control"]
    assert tuple(field["selector"]["select"]["options"]) == HELD_CONTROLS


def _side(address: str, variant: str) -> dict[str, object]:
    return {
        CONF_ADDRESS: address,
        CONF_NAME: address,
        CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR,
        CONF_PROTOCOL_VARIANT: variant,
        CONF_MOTOR_COUNT: 3,
        CONF_DISABLE_ANGLE_SENSING: True,
    }


async def test_two_address_pair_refuses_shared_variant_changes(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(
            _side("AA:BB:CC:DD:EE:11", VARIANT_AUTO),
            _side("AA:BB:CC:DD:EE:22", "adjustable_lumbar_star"),
            name="Pair",
        ),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    refused = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "adjustable_lumbar_okin"})
    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {CONF_PROTOCOL_VARIANT: "adjustable_lumbar_unpair_first"}
    saved = await flow.async_step_settings({CONF_IDLE_DISCONNECT_SECONDS: 60})
    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert effective_child_data(entry.data, "left")[CONF_PROTOCOL_VARIANT] == VARIANT_AUTO
    assert effective_child_data(entry.data, "right")[CONF_PROTOCOL_VARIANT] == (
        "adjustable_lumbar_star"
    )


@pytest.fixture
def star_client(mock_bleak_client: MagicMock) -> MagicMock:
    def char(uuid: str, handle: int, *props: str) -> MagicMock:
        return MagicMock(uuid=uuid, handle=handle, properties=list(props), descriptors=[])

    nus = MagicMock(uuid="6e400001-b5a3-f393-e0a9-e50e24dcca9e", handle=0)
    nus.characteristics = [
        char("6e400002-b5a3-f393-e0a9-e50e24dcca9e", 1, "write-without-response"),
        char("6e400003-b5a3-f393-e0a9-e50e24dcca9e", 2, "notify"),
    ]
    info = MagicMock(uuid="0000180a-0000-1000-8000-00805f9b34fb", handle=3)
    info.characteristics = [char("00002a29-0000-1000-8000-00805f9b34fb", 4, "read")]
    mock_bleak_client.services.__iter__ = lambda self: iter([nus, info])
    mock_bleak_client.services.__len__ = lambda self: 2
    mock_bleak_client.read_gatt_char = AsyncMock(return_value=bytearray(b"STAR"))
    return mock_bleak_client


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_connection_reads_the_manufacturer_once_and_persists_the_raw_name(
    hass, star_client: MagicMock, mock_async_ble_device_from_address: MagicMock
) -> None:
    mock_async_ble_device_from_address.return_value.name = "Star252201"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Bedroom",
            CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 3,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await coordinator.async_connect()
    assert coordinator.controller.table == "35_22_01"
    # The generic Device Information pass is skipped: one app read only.
    assert star_client.read_gatt_char.await_count == 1
    assert entry.data[CONF_BLE_DEVICE_NAME] == "Star252201"
    await coordinator.async_disconnect()


async def test_options_switch_fixes_the_axes_and_refresh(hass):
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_64BIT,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_OKIN_64BIT,
            CONF_MOTOR_COUNT: 2,
            CONF_MOTOR_PULSE_COUNT: 7,
            CONF_MOTOR_PULSE_DELAY_MS: 150,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form(
        {CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR}, step_id="settings"
    )
    markers = {marker.schema for marker in rebuilt["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers and CONF_MOTOR_PULSE_DELAY_MS not in markers
    saved = await flow._async_options_form(
        {CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR, CONF_PROTOCOL_VARIANT: "adjustable_lumbar_star"},
        step_id="settings",
    )
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_ADJUSTABLE_LUMBAR
    assert entry.data[CONF_MOTOR_COUNT] == 3
    assert entry.data[CONF_MOTOR_PULSE_DELAY_MS] == 100
