"""Focused tests for the explicit RMControl opt-in and HA action boundary."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import Entity

from custom_components.adjustable_bed.beds.base import BedController, ControllerButtonSpec
from custom_components.adjustable_bed.button import AdjustableBedProductButton
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedOptionsFlow,
    _rmcontrol_schema_fields,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_RICHMAT,
    CONF_RMCONTROL_PRODUCT,
    CONF_RMCONTROL_SIDE,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.entity_discovery import async_setup_dynamic_entities
from custom_components.adjustable_bed.rmcontrol_services import (
    ALARM_SCHEMA,
    ANTI_SNORE_SCHEMA,
    handle_rmcontrol_alarm,
    handle_rmcontrol_anti_snore,
)


def test_profile_opt_in_and_exact_selection() -> None:
    schema = vol.Schema(_rmcontrol_schema_fields())
    assert schema({}) == {CONF_RMCONTROL_PRODUCT: "", CONF_RMCONTROL_SIDE: "left"}
    assert schema({CONF_RMCONTROL_PRODUCT: "A3RM", CONF_RMCONTROL_SIDE: "right"}) == {
        CONF_RMCONTROL_PRODUCT: "A3RM",
        CONF_RMCONTROL_SIDE: "right",
    }
    with pytest.raises(vol.Invalid):
        schema({CONF_RMCONTROL_PRODUCT: "unknown-app-product"})
    with pytest.raises(vol.Invalid):
        schema({CONF_RMCONTROL_SIDE: "auto"})


def test_profile_removed_only_when_changing_protocol() -> None:
    data = {CONF_RMCONTROL_PRODUCT: "A3RM", CONF_RMCONTROL_SIDE: "right"}
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, BED_TYPE_RICHMAT)
    assert data[CONF_RMCONTROL_PRODUCT] == "A3RM"
    AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, BED_TYPE_LINAK)
    assert CONF_RMCONTROL_PRODUCT not in data
    assert CONF_RMCONTROL_SIDE not in data


async def test_extra_product_button_uses_current_controller_and_lock() -> None:
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    coordinator.entity_translation_key.side_effect = lambda key: key
    coordinator.async_execute_controller_command = AsyncMock()
    action = AsyncMock()
    button = AdjustableBedProductButton(
        coordinator, ControllerButtonSpec(key="heating_low", name="Heating low", press_fn=action)
    )
    await button.async_press()
    assert button.unique_id == "bed_product_action_heating_low"
    assert button.translation_key == "product_action"
    assert button.translation_placeholders == {"action": "Heating low"}
    assert not button.entity_registry_enabled_default
    coordinator.async_execute_controller_command.assert_awaited_once_with(
        action, cancel_running=True
    )
    action.assert_not_awaited()


@pytest.mark.parametrize("operation", ["single", "repeat", "delete"])
async def test_alarm_required_fields_fail_before_connect(
    hass: HomeAssistant, operation: str
) -> None:
    call = ServiceCall(
        hass, DOMAIN, "rmcontrol_alarm", {"device_id": ["bed"], "operation": operation}
    )
    with patch(
        "custom_components.adjustable_bed.rmcontrol_services._execute", new_callable=AsyncMock
    ) as execute:
        with pytest.raises(ServiceValidationError, match="requires"):
            await handle_rmcontrol_alarm(call)
        execute.assert_not_awaited()


async def test_repeat_alarm_names_are_converted_once(hass: HomeAssistant) -> None:
    controller = MagicMock(spec=BedController)
    controller.rmcontrol_repeat_alarm = AsyncMock()

    async def execute(call, capability, command):
        assert capability == "supports_rmcontrol_repeat_alarm"
        await command(controller)

    data = ALARM_SCHEMA(
        {
            "device_id": "bed",
            "operation": "repeat",
            "alarm_id": 2,
            "time": "07:35:00",
            "weekdays": ["monday", "sunday"],
            "action": "Memory1",
        }
    )
    with patch("custom_components.adjustable_bed.rmcontrol_services._execute", side_effect=execute):
        await handle_rmcontrol_alarm(ServiceCall(hass, DOMAIN, "rmcontrol_alarm", data))
    controller.rmcontrol_repeat_alarm.assert_awaited_once_with(2, 7, 35, (0, 6), "Memory1")


@pytest.mark.parametrize(
    ("operation", "fields", "capability"),
    [
        ("single", {"minutes": 5, "action": "Memory1"}, "single"),
        ("cancel_single", {}, "single"),
        (
            "repeat",
            {"alarm_id": 1, "time": "07:00", "weekdays": ["monday"], "action": "Memory1"},
            "repeat",
        ),
        ("delete", {"alarm_id": 1}, "repeat"),
        ("query", {}, "repeat"),
        ("sync", {}, "time_sync"),
    ],
)
async def test_alarm_operations_require_their_specific_capability(
    hass: HomeAssistant, operation: str, fields: dict[str, object], capability: str
) -> None:
    data = ALARM_SCHEMA({"device_id": "bed", "operation": operation, **fields})
    with patch(
        "custom_components.adjustable_bed.rmcontrol_services._execute", new_callable=AsyncMock
    ) as execute:
        await handle_rmcontrol_alarm(ServiceCall(hass, DOMAIN, "rmcontrol_alarm", data))
    expected = (
        "supports_rmcontrol_alarm_time_sync"
        if capability == "time_sync"
        else f"supports_rmcontrol_{capability}_alarm"
    )
    assert execute.await_args.args[1] == expected


async def test_snore_configuration_is_not_enable_switch(hass: HomeAssistant) -> None:
    controller = MagicMock(spec=BedController)
    controller.rmcontrol_anti_snore_config = AsyncMock()
    controller.rmcontrol_anti_snore_switch = AsyncMock()

    async def execute(call, capability, command):
        assert capability == "supports_rmcontrol_anti_snore"
        await command(controller)

    data = ANTI_SNORE_SCHEMA(
        {
            "device_id": "bed",
            "operation": "configure",
            "mode": "count",
            "value": 3,
        }
    )
    with patch("custom_components.adjustable_bed.rmcontrol_services._execute", side_effect=execute):
        await handle_rmcontrol_anti_snore(ServiceCall(hass, DOMAIN, "rmcontrol_anti_snore", data))
    controller.rmcontrol_anti_snore_config.assert_awaited_once_with("count", 3)
    controller.rmcontrol_anti_snore_switch.assert_not_awaited()


def test_service_schemas_reject_invalid_wire_ranges() -> None:
    with pytest.raises(vol.Invalid):
        ALARM_SCHEMA({"device_id": "bed", "operation": "delete", "alarm_id": 8})
    with pytest.raises(vol.Invalid):
        ANTI_SNORE_SCHEMA({"device_id": "bed", "operation": "configure", "mode": "enabled"})


def test_late_capability_adds_entities_once_and_unregisters() -> None:
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.capability_controller.has_dynamic_controller_entities = True
    entry = MagicMock()
    add = MagicMock()
    initial = MagicMock(spec=Entity)
    initial.unique_id = "existing"
    late = MagicMock(spec=Entity)
    late.unique_id = "late_rgb"
    current = [initial]
    async_setup_dynamic_entities(entry, coordinator, add, lambda: tuple(current))
    add.assert_called_once_with([initial])
    callback = coordinator.register_controller_state_callback.call_args.args[0]
    current.append(late)
    callback({})
    callback({})
    assert add.call_count == 2
    assert add.call_args.args == ([late],)
    entry.async_on_unload.assert_called_once_with(
        coordinator.register_controller_state_callback.return_value
    )


def test_static_controller_does_not_gain_a_discovery_listener() -> None:
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.capability_controller.has_dynamic_controller_entities = False
    async_setup_dynamic_entities(MagicMock(), coordinator, MagicMock(), lambda: ())
    coordinator.register_controller_state_callback.assert_not_called()


async def test_factory_uses_opt_in_product_and_preserves_legacy_without_it() -> None:
    from custom_components.adjustable_bed.beds.richmat import RichmatController
    from custom_components.adjustable_bed.beds.rmcontrol import RmcontrolController

    coordinator = MagicMock()
    coordinator.name = "Test bed"
    coordinator.entry.title = "Test bed"
    client = MagicMock()
    client.is_connected = True
    with patch(
        "custom_components.adjustable_bed.beds.rmcontrol.detect_rmcontrol_transport",
        new_callable=AsyncMock,
        return_value=(False, "6e400002-b5a3-f393-e0a9-e50e24dcca9e", False),
    ):
        selected = await create_controller(
            coordinator, BED_TYPE_RICHMAT, "nordic", client,
            rmcontrol_product="A3RM", rmcontrol_side="right",
        )
    assert isinstance(selected, RmcontrolController)
    assert selected.rmcontrol_product == "A3RM"
    assert selected.protocol_diagnostics["side"] == "right"
    legacy = await create_controller(coordinator, BED_TYPE_RICHMAT, "nordic", client)
    assert type(legacy) is RichmatController


async def test_factory_rejects_profile_with_unrelated_frame_variant() -> None:
    with pytest.raises(ValueError, match="Nordic or WiLinke"):
        await create_controller(
            MagicMock(), BED_TYPE_RICHMAT, "prefix55", MagicMock(), rmcontrol_product="A3RM"
        )


@pytest.mark.parametrize("code", ["FWRM", "WFRM"])
def test_desk_products_are_not_selectable(code: str) -> None:
    with pytest.raises(vol.Invalid):
        vol.Schema(_rmcontrol_schema_fields())({CONF_RMCONTROL_PRODUCT: code})


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa"])
@pytest.mark.parametrize("existing_product", ["", "A0RM"])
async def test_options_reject_incompatible_product_transport_before_save(
    hass: HomeAssistant, variant: str, existing_product: str
) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_MOTOR_COUNT,
        CONF_PROTOCOL_VARIANT,
    )

    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_MOTOR_COUNT: 2, CONF_PROTOCOL_VARIANT: "auto",
        CONF_RMCONTROL_PRODUCT: existing_product,
    })
    entry.add_to_hass(hass)
    original = dict(entry.data)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    submission = {CONF_PROTOCOL_VARIANT: variant}
    if not existing_product:
        submission[CONF_RMCONTROL_PRODUCT] = "A0RM"
    result = await flow.async_step_settings(submission)
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"}
    assert dict(entry.data) == original


async def test_dynamic_light_select_survives_reconnect_discovery(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.rmcontrol import RmcontrolController
    from custom_components.adjustable_bed.rmcontrol_protocol import Notification
    from custom_components.adjustable_bed.select import _select_entities_for

    coordinator = MagicMock()
    coordinator.has_massage = False
    coordinator.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    ctrl = RmcontrolController(coordinator, "A0RM")
    coordinator.capability_controller = ctrl
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "select", DOMAIN, "bed_light_timer", config_entry=entry,
    )
    ctrl._accept_notification(Notification("capability", {"light": True}))
    add = MagicMock()
    async_setup_dynamic_entities(
        entry, coordinator, add, lambda: _select_entities_for(hass, coordinator)
    )
    assert add.call_count == 1
    callback = coordinator.register_controller_state_callback.call_args.args[0]
    coordinator.capability_controller = RmcontrolController(coordinator, "A0RM")
    callback({})
    assert registry.async_get(row.entity_id) is not None
    coordinator.capability_controller._accept_notification(
        Notification("capability", {"light": True})
    )
    callback({})
    assert registry.async_get(row.entity_id) is not None
    assert add.call_count == 1


@pytest.mark.parametrize("explicit_on", [True, False])
async def test_light_without_reported_color_uses_power_only(explicit_on: bool) -> None:
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

    coordinator = MagicMock()
    ctrl = MagicMock(spec=BedController)
    ctrl.default_light_rgb_color = None
    ctrl.supported_color_mode = "rgb"
    ctrl.supports_explicit_light_on_control = explicit_on
    ctrl.lights_on = AsyncMock()
    ctrl.set_light_color = AsyncMock()
    coordinator.capability_controller = ctrl

    async def execute(command, **kwargs):
        await command(ctrl)

    coordinator.async_execute_controller_command = execute
    light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    if explicit_on:
        await light.async_turn_on()
        ctrl.lights_on.assert_awaited_once()
        assert light.is_on
        assert light.rgb_color is None
    else:
        with pytest.raises(ValueError, match="No RGB color"):
            await light.async_turn_on()
        ctrl.lights_on.assert_not_awaited()
    ctrl.set_light_color.assert_not_awaited()


@pytest.mark.parametrize("step", ["manual_richmat", "bluetooth_richmat"])
@pytest.mark.parametrize("variant", ["prefix55", "prefixaa", "auto", "nordic", "wilinke"])
async def test_initial_product_followup_validates_transport(
    hass: HomeAssistant, step: str, variant: str
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_PROTOCOL_VARIANT: variant}
    original = dict(flow._manual_data)
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await getattr(flow, "async_step_" + step)({CONF_RMCONTROL_PRODUCT: "A0RM"})
    if variant.startswith("prefix"):
        assert result["errors"] == {"base": "invalid_variant_for_bed_type"}
        assert flow._manual_data == original
        flow._finish_with_verify.assert_not_awaited()
    else:
        flow._finish_with_verify.assert_awaited_once()


@pytest.mark.parametrize("domain", ["sensor", "binary_sensor"])
async def test_retired_telemetry_cleanup_is_scoped_to_current_bed(
    hass: HomeAssistant, domain: str
) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.entity_discovery import (
        async_remove_retired_rmcontrol_telemetry,
    )

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    rows = {
        key: registry.async_get_or_create(domain, DOMAIN, key, config_entry=entry)
        for key in ("bed_rmcontrol_old", "bed_rmcontrol_current", "other_rmcontrol_old", "bed_other")
    }
    coordinator = MagicMock()
    coordinator.entity_unique_id.side_effect = lambda key: "bed_" + key
    ctrl = coordinator.capability_controller
    spec = MagicMock(key="rmcontrol_current")
    ctrl.controller_state_sensor_specs = (spec,)
    ctrl.controller_state_binary_sensor_specs = (spec,)
    async_remove_retired_rmcontrol_telemetry(hass, entry, coordinator, domain)
    assert registry.async_get(rows["bed_rmcontrol_old"].entity_id) is None
    for key in ("bed_rmcontrol_current", "other_rmcontrol_old", "bed_other"):
        assert registry.async_get(rows[key].entity_id) is not None
    ctrl.controller_state_sensor_specs = ()
    ctrl.controller_state_binary_sensor_specs = ()
    async_remove_retired_rmcontrol_telemetry(hass, entry, coordinator, domain)
    assert registry.async_get(rows["bed_rmcontrol_current"].entity_id) is None


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa"])
async def test_bluetooth_confirmation_rejects_incompatible_product(
    hass: HomeAssistant, mock_bluetooth_service_info, variant: str
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._finish_with_verify = AsyncMock()
    result = await flow.async_step_bluetooth_confirm({
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_PROTOCOL_VARIANT: variant,
        CONF_RMCONTROL_PRODUCT: "A0RM",
    })
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"}
    flow._finish_with_verify.assert_not_awaited()
