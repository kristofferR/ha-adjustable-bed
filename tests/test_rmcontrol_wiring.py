"""Focused tests for the explicit RMControl opt-in and HA action boundary."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import Entity
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.entity_specs import ProductButtonSpec
from custom_components.adjustable_bed.beds.rmcontrol.protocol import Notification
from custom_components.adjustable_bed.beds.rmcontrol.services import (
    ANTI_SNORE_SCHEMA,
    handle_rmcontrol_anti_snore,
)
from custom_components.adjustable_bed.button import AdjustableBedProductButton
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
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
from custom_components.adjustable_bed.entity_sweep import EntityLedger, PlatformEntities
from custom_components.adjustable_bed.setup_questions import setup_profile


def _runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.has_massage = False
    runtime.controller_side = None
    runtime.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    return runtime


def _sink(
    hass: HomeAssistant, entry: MockConfigEntry, runtime: MagicMock, domain: str
) -> tuple[PlatformEntities, MagicMock]:
    """A platform callback recording into a ledger that may sweep the entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    ledger = EntityLedger(hass, entry, runtime)
    ledger.platforms_forwarded((domain,))
    ledger.platform_finished(domain)
    add = MagicMock()
    return PlatformEntities(ledger, domain, add), add


def _sweep(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    runtime: MagicMock,
    built: dict[str, list[Entity]],
) -> None:
    """Sweep the entry as if each platform had just built ``built``."""
    ledger = EntityLedger(hass, entry, runtime)
    ledger.platforms_forwarded(built)
    for domain, entities in built.items():
        PlatformEntities(ledger, domain, MagicMock())(entities)
        ledger.platform_finished(domain)
    ledger.async_sweep()


def _richmat_question(key: str):
    profile = setup_profile(BED_TYPE_RICHMAT)
    assert profile is not None
    return next(question for question in profile.questions if question.key == key)


def test_profile_opt_in_and_exact_selection() -> None:
    product = _richmat_question(CONF_RMCONTROL_PRODUCT)
    side = _richmat_question(CONF_RMCONTROL_SIDE)
    products = product.options({})
    assert products is not None
    assert "" in products and "A3RM" in products and "unknown-app-product" not in products
    # The legacy remote controls stay the default; the RMControl answer names a product.
    assert product.default_for({}) == ""
    assert side.default_for({}) == "left"
    assert set(side.options({}) or {}) == {"left", "right", "both"}


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
    coordinator.async_execute_controller_command = AsyncMock()
    action = AsyncMock()
    button = AdjustableBedProductButton(
        coordinator, ProductButtonSpec(key="heating_low", name="Heating low", press_fn=action)
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


_RMCONTROL_GATES = (
    "supports_rmcontrol_single_alarm",
    "supports_rmcontrol_repeat_alarm",
    "supports_rmcontrol_alarm_time_sync",
    "supports_rmcontrol_anti_snore",
)


def _rmcontrol_with(gate: str) -> MagicMock:
    """A product controller offering exactly one RMControl gate."""
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController

    controller = MagicMock(spec=RmcontrolController)
    for name in _RMCONTROL_GATES:
        setattr(controller, name, name == gate)
    return controller


def _alarm_product(product: str):
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController

    controller = RmcontrolController(MagicMock(), product)
    controller._reported_capabilities.add("alarm")
    controller.rmcontrol_repeat_alarm = AsyncMock()
    controller.rmcontrol_delete_alarm = AsyncMock()
    controller.rmcontrol_single_alarm = AsyncMock()
    return controller


async def test_repeating_alarm_uses_the_slot_days_and_catalog_action(hass: HomeAssistant) -> None:
    from tests.alarm_helpers import call_set_alarm

    controller = _alarm_product("MXRN")
    capability = controller.alarm_capability
    assert capability is not None and capability.slots == 7 and "tv" in capability.wake_actions
    await call_set_alarm(
        hass,
        controller,
        {
            "enabled": True,
            "time": "07:35:00",
            "slot": 2,
            "weekdays": ["monday", "sunday"],
            "wake_action": "tv",
        },
    )
    controller.rmcontrol_repeat_alarm.assert_awaited_once_with(2, 7, 35, (0, 6), "TVPosition")
    await call_set_alarm(hass, controller, {"enabled": False, "slot": 2})
    controller.rmcontrol_delete_alarm.assert_awaited_once_with(2)
    with pytest.raises(ServiceValidationError, match="at least one day"):
        await call_set_alarm(
            hass, controller, {"enabled": True, "time": "07:35:00", "wake_action": "tv"}
        )


async def test_single_alarm_counts_down_to_the_time(hass: HomeAssistant) -> None:
    from datetime import datetime

    from tests.alarm_helpers import call_set_alarm

    controller = _alarm_product("A4RN")
    assert controller.supports_rmcontrol_single_alarm
    now = datetime(2026, 11, 18, 7, 0)
    with (
        patch("custom_components.adjustable_bed.services.dt_util.now", return_value=now),
        patch(
            "custom_components.adjustable_bed.beds.rmcontrol.controller.dt_util.now",
            return_value=now,
        ),
    ):
        await call_set_alarm(
            hass, controller, {"enabled": True, "time": "07:05:00", "wake_action": "tv"}
        )
    controller.rmcontrol_single_alarm.assert_awaited_once_with(5, "TVPosition")
    controller.rmcontrol_single_alarm.reset_mock()
    await call_set_alarm(hass, controller, {"enabled": False})
    controller.rmcontrol_single_alarm.assert_awaited_once_with(0, None)


async def test_snore_configuration_is_not_enable_switch(hass: HomeAssistant) -> None:
    controller = _rmcontrol_with("supports_rmcontrol_anti_snore")
    controller.rmcontrol_anti_snore_config = AsyncMock()
    controller.rmcontrol_anti_snore_switch = AsyncMock()

    async def execute(call, supported, command):
        assert supported(controller)
        await command(controller)

    data = ANTI_SNORE_SCHEMA(
        {
            "device_id": "bed",
            "operation": "configure",
            "mode": "count",
            "value": 3,
        }
    )
    with patch("custom_components.adjustable_bed.beds.rmcontrol.services._execute", side_effect=execute):
        await handle_rmcontrol_anti_snore(ServiceCall(hass, DOMAIN, "rmcontrol_anti_snore", data))
    controller.rmcontrol_anti_snore_config.assert_awaited_once_with("count", 3)
    controller.rmcontrol_anti_snore_switch.assert_not_awaited()


def test_service_schemas_reject_invalid_wire_ranges() -> None:
    with pytest.raises(vol.Invalid):
        ANTI_SNORE_SCHEMA({"device_id": "bed", "operation": "configure", "mode": "enabled"})


def test_late_capability_adds_entities_once_and_unregisters(hass) -> None:
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.capability_controller.has_dynamic_controller_entities = True
    entry = MagicMock()
    sink = MagicMock()
    initial = MagicMock(spec=Entity)
    initial.unique_id = "existing"
    late = MagicMock(spec=Entity)
    late.unique_id = "late_rgb"
    current = [initial]
    async_setup_dynamic_entities(entry, coordinator, sink, lambda: tuple(current))
    callback = coordinator.register_controller_state_callback.call_args.args[0]
    current.append(late)
    callback({})
    callback({})
    added = [call.args[0] for call in sink.add_published.call_args_list if call.args[0]]
    assert added == [[initial], [late]]
    entry.async_on_unload.assert_called_once_with(
        coordinator.register_controller_state_callback.return_value
    )


def test_static_controller_does_not_gain_a_discovery_listener(hass) -> None:
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.capability_controller.has_dynamic_controller_entities = False
    async_setup_dynamic_entities(MagicMock(), coordinator, MagicMock(), lambda: ())
    coordinator.register_controller_state_callback.assert_not_called()


async def test_factory_uses_opt_in_product_and_preserves_legacy_without_it(hass) -> None:
    from custom_components.adjustable_bed.beds.richmat.controller import RichmatController
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController

    coordinator = MagicMock(hass=hass)
    coordinator.name = "Test bed"
    coordinator.entry.title = "Test bed"
    client = MagicMock()
    client.is_connected = True
    with patch(
        "custom_components.adjustable_bed.beds.rmcontrol.controller.detect_rmcontrol_transport",
        new_callable=AsyncMock,
        return_value=(False, "6e400002-b5a3-f393-e0a9-e50e24dcca9e", False),
    ):
        coordinator.entry.data = {CONF_RMCONTROL_PRODUCT: "A3RM", CONF_RMCONTROL_SIDE: "right"}
        selected = await create_controller(coordinator, BED_TYPE_RICHMAT, "nordic", client)
    assert isinstance(selected, RmcontrolController)
    assert selected.rmcontrol_product == "A3RM"
    assert selected.protocol_diagnostics["side"] == "right"
    coordinator.entry.data = {}
    legacy = await create_controller(coordinator, BED_TYPE_RICHMAT, "nordic", client)
    assert type(legacy) is RichmatController


async def test_factory_rejects_profile_with_unrelated_frame_variant(hass) -> None:
    with pytest.raises(ValueError, match="Nordic or WiLinke"):
        coordinator = MagicMock(hass=hass)
        coordinator.name = coordinator.entry.title = "Test bed"
        coordinator.entry.data = {CONF_RMCONTROL_PRODUCT: "A3RM"}
        await create_controller(coordinator, BED_TYPE_RICHMAT, "prefix55", MagicMock())


@pytest.mark.parametrize("code", ["FWRM", "WFRM"])
def test_desk_products_are_not_selectable(code: str) -> None:
    assert code not in (_richmat_question(CONF_RMCONTROL_PRODUCT).options({}) or {})


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa"])
@pytest.mark.parametrize("existing_product", ["", "A0RM"])
async def test_options_reject_incompatible_product_transport_before_save(
    hass: HomeAssistant, variant: str, existing_product: str
) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

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
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController
    from custom_components.adjustable_bed.beds.rmcontrol.protocol import Notification
    from custom_components.adjustable_bed.select import _select_entities_for

    coordinator = _runtime()
    ctrl = RmcontrolController(coordinator, "A0RM")
    coordinator.capability_controller = ctrl
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "select", DOMAIN, "bed_light_timer", config_entry=entry,
    )
    ctrl._accept_notification(Notification("capability", {"light": True}))
    sink, add = _sink(hass, entry, coordinator, "select")
    async_setup_dynamic_entities(
        entry, coordinator, sink, lambda: _select_entities_for(hass, coordinator)
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


@pytest.mark.parametrize("product,keep_light,keep_timer", [
    ("6ERM", True, True), ("FCRN", False, False), ("A0RM", False, True),
])
async def test_light_registry_retains_only_possible_profile_capabilities(
    hass: HomeAssistant, product: str, keep_light: bool, keep_timer: bool
) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.select import _select_entities_for

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = _runtime()
    coordinator.entry = entry
    coordinator.capability_controller = RmcontrolController(coordinator, product)
    registry = er.async_get(hass)
    light = registry.async_get_or_create(
        "light", DOMAIN, "bed_under_bed_lights", config_entry=entry,
    )
    timer = registry.async_get_or_create(
        "select", DOMAIN, "bed_light_timer", config_entry=entry,
    )
    _sweep(
        hass,
        entry,
        coordinator,
        {
            "light": _light_entities_for(hass, coordinator),
            "select": _select_entities_for(hass, coordinator),
        },
    )
    assert (registry.async_get(light.entity_id) is not None) == keep_light
    assert (registry.async_get(timer.entity_id) is not None) == keep_timer


@pytest.mark.parametrize("explicit_on", [True, False])
@pytest.mark.parametrize("toggle", [True, False])
@pytest.mark.parametrize("is_on", [True, False])
async def test_light_without_reported_color_uses_power_only(
    explicit_on: bool, toggle: bool, is_on: bool
) -> None:
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

    coordinator = MagicMock()
    ctrl = MagicMock(spec=BedController)
    ctrl.default_light_rgb_color = None
    ctrl.supported_color_mode = "rgb"
    ctrl.supports_explicit_light_on_control = explicit_on
    ctrl.supports_light_toggle_control = toggle
    ctrl.lights_on = AsyncMock()
    ctrl.lights_toggle = AsyncMock()
    ctrl.set_light_color = AsyncMock()
    ctrl.light_auto_off_seconds = None
    coordinator.controller = ctrl
    coordinator.capability_controller = ctrl

    async def execute(command, **kwargs):
        await command(ctrl)

    coordinator.async_execute_controller_command = execute
    light = AdjustableBedLight(coordinator, LIGHT_DESCRIPTION)
    light._attr_is_on = is_on
    light.async_write_ha_state = MagicMock()
    if explicit_on:
        await light.async_turn_on()
        ctrl.lights_on.assert_awaited_once()
        assert light.is_on
        assert light.rgb_color is None
        ctrl.lights_toggle.assert_not_awaited()
    elif toggle:
        await light.async_turn_on()
        ctrl.lights_on.assert_not_awaited()
        if is_on:
            ctrl.lights_toggle.assert_not_awaited()
        else:
            ctrl.lights_toggle.assert_awaited_once()
        assert light.is_on
        assert light.rgb_color is None
    else:
        with pytest.raises(ValueError, match="No RGB color"):
            await light.async_turn_on()
        ctrl.lights_on.assert_not_awaited()
        ctrl.lights_toggle.assert_not_awaited()
    ctrl.set_light_color.assert_not_awaited()


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa", "auto", "nordic", "wilinke"])
def test_initial_product_answer_validates_transport(variant: str) -> None:
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT

    profile = setup_profile(BED_TYPE_RICHMAT)
    assert profile is not None and profile.validate is not None
    errors = profile.validate(
        {
            CONF_BED_TYPE: BED_TYPE_RICHMAT,
            CONF_RMCONTROL_PRODUCT: "A0RM",
            CONF_PROTOCOL_VARIANT: variant,
        }
    )
    assert errors == (
        {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"} if variant.startswith("prefix") else {}
    )


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa"])
async def test_bluetooth_confirmation_rejects_incompatible_product(
    hass: HomeAssistant, mock_bluetooth_service_info, variant: str
) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._finish_with_verify = AsyncMock()
    flow._disambiguated_bed_type = BED_TYPE_RICHMAT
    result = await flow.async_step_bluetooth_confirm()
    assert result["step_id"] == "richmat_family"
    result = await flow.async_step_richmat_family({"choice": "rmcontrol"})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions(
        {CONF_RMCONTROL_PRODUCT: "A0RM", "advanced": {CONF_PROTOCOL_VARIANT: variant}}
    )
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"}
    flow._finish_with_verify.assert_not_awaited()


@pytest.mark.parametrize("domain", ["sensor", "binary_sensor"])
async def test_rmcontrol_restart_retains_event_driven_registry_rows(hass, domain) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    key = "rmcontrol_music_playing" if domain == "binary_sensor" else "rmcontrol_music_volume"
    row = registry.async_get_or_create(domain, DOMAIN, "bed_" + key, config_entry=entry)
    coordinator = _runtime()
    coordinator.capability_controller = RmcontrolController(coordinator, "A0RM")
    coordinator.capability_controller._accept_notification(
        Notification("capability", {"light": True})
    )
    _sweep(hass, entry, coordinator, {domain: []})
    assert registry.async_get(row.entity_id) is not None


@pytest.mark.parametrize("operation", ["single", "repeat"])
@pytest.mark.parametrize("paired", [False, True])
async def test_alarm_validates_every_product_before_writing(hass, operation, paired) -> None:
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first = MagicMock()
    second = MagicMock()
    first_product, second_product = ("A4RN", "CMRM") if operation == "single" else ("MXRN", "N4RN")
    first.capability_controller = RmcontrolController(first, first_product)
    second.capability_controller = RmcontrolController(second, second_product)
    for target in (first, second):
        target.capability_controller._reported_capabilities.add("alarm")
        assert getattr(target.capability_controller, "supports_rmcontrol_" + operation + "_alarm")
    data = {
        "device_id": ["bed"], "enabled": True, "time": "07:00", "wake_action": "tv",
        **({} if operation == "single" else {"slot": 1, "weekdays": ["monday"]}),
    }
    targets = [(first, "both")] if paired else [(first, "both"), (second, "both")]
    first.capability_controller.validate_rmcontrol_alarm_action("TVPosition")

    def physical(coordinator, side):
        return [first, second] if paired else [coordinator]

    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=(targets, [])),
        patch("custom_components.adjustable_bed.services._command_targets", side_effect=physical),
        patch("custom_components.adjustable_bed.services._execute_sided",
              new_callable=AsyncMock) as execute,
        pytest.raises(ServiceValidationError, match="cannot wake with 'tv'"),
    ):
        await hass.services.async_call(DOMAIN, "set_alarm", data, blocking=True)
    execute.assert_not_awaited()


@pytest.mark.parametrize("variant", ["prefix55", "prefixaa", "wilinke"])
async def test_each_receiver_checks_its_own_product_transport(
    hass: HomeAssistant, enable_custom_integrations, variant: str
) -> None:
    """A receiver's dialect is its own answer, checked against its own product."""
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
    from tests.test_paired_receiver_questions import child, pair_entry, receiver_form

    richmat = {CONF_BED_TYPE: BED_TYPE_RICHMAT, CONF_PROTOCOL_VARIANT: "auto"}
    entry = pair_entry(
        hass,
        {**richmat, CONF_RMCONTROL_PRODUCT: ""},
        {**richmat, CONF_RMCONTROL_PRODUCT: "A0RM"},
    )
    right = await receiver_form(hass, entry, "right")
    result = await hass.config_entries.options.async_configure(
        right["flow_id"], {**right["data_schema"]({}), CONF_PROTOCOL_VARIANT: variant}
    )
    if variant.startswith("prefix"):
        assert result["errors"] == {CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"}
        assert child(entry, "right")[CONF_PROTOCOL_VARIANT] == "auto"
        hass.config_entries.options.async_abort(right["flow_id"])
    else:
        assert result["type"] == "create_entry"
        assert child(entry, "right")[CONF_PROTOCOL_VARIANT] == variant
    # The other receiver keeps its own route.
    assert child(entry, "left")[CONF_PROTOCOL_VARIANT] == "auto"


@pytest.mark.parametrize("pair_mode", [None, "single_address", "separate_address"])
async def test_product_options_are_not_shared_between_physical_controllers(
    hass: HomeAssistant, pair_mode: str | None
) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_MOTOR_COUNT,
        CONF_PAIR_CHILDREN,
        CONF_PAIR_ID,
        CONF_PAIR_MODE,
        CONF_PROTOCOL_VARIANT,
        CONF_SIDE,
    )

    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_MOTOR_COUNT: 2,
        CONF_PROTOCOL_VARIANT: "auto",
        CONF_RMCONTROL_PRODUCT: "A0RM",
        CONF_RMCONTROL_SIDE: "left",
    }
    if pair_mode is not None:
        data.update({CONF_PAIR_ID: "rmcontrol_pair", CONF_PAIR_MODE: pair_mode})
    if pair_mode == "separate_address":
        data[CONF_PAIR_CHILDREN] = [
            {**data, CONF_SIDE: "left"},
            {
                **data,
                CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
                CONF_SIDE: "right",
                CONF_RMCONTROL_PRODUCT: "A3RM",
                CONF_RMCONTROL_SIDE: "right",
            },
        ]
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    form = await flow.async_step_settings(None)
    fields = {marker.schema for marker in form["data_schema"].schema}
    shared = pair_mode == "separate_address"
    assert (CONF_RMCONTROL_PRODUCT in fields) is not shared
    assert (CONF_RMCONTROL_SIDE in fields) is not shared
    if not shared:
        return
    # Each receiver's product, side and dialect are its own step's answers.
    assert CONF_PROTOCOL_VARIANT not in fields
    schema = form["data_schema"]
    assert isinstance(schema, vol.Schema)
    submission = schema({})
    assert isinstance(submission, dict)
    result = await flow.async_step_settings(submission)
    assert result["type"] == "create_entry"
    children = entry.data[CONF_PAIR_CHILDREN]
    assert [child[CONF_RMCONTROL_PRODUCT] for child in children] == ["A0RM", "A3RM"]
    assert [child[CONF_RMCONTROL_SIDE] for child in children] == ["left", "right"]
    assert all(child[CONF_PROTOCOL_VARIANT] == "auto" for child in children)


def test_countdown_counts_from_the_write_time() -> None:
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest

    alarm = AlarmRequest(
        enabled=True, hour=7, minute=5, reference_time=datetime(2026, 11, 18, 7, 0, 30)
    )
    assert alarm.minutes_until() == 5
    # Admission took a minute: the bed still fires at 07:05.
    assert alarm.minutes_until(datetime(2026, 11, 18, 7, 1, 10)) == 4


def test_countdown_uses_real_time_across_a_clock_change() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from custom_components.adjustable_bed.alarm import AlarmRequest

    oslo = ZoneInfo("Europe/Oslo")
    # Clocks spring forward from 02:00 to 03:00 on 2026-03-29.
    alarm = AlarmRequest(
        enabled=True, hour=3, minute=30, reference_time=datetime(2026, 3, 29, 1, 30, tzinfo=oslo)
    )
    assert alarm.minutes_until() == 60


def test_countdown_picks_the_repeated_hour_after_a_clock_change() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from custom_components.adjustable_bed.alarm import AlarmRequest

    oslo = ZoneInfo("Europe/Oslo")
    # Clocks fall back from 03:00 to 02:00 on 2026-10-25; 02:30 happens twice.
    alarm = AlarmRequest(
        enabled=True,
        hour=2,
        minute=30,
        reference_time=datetime(2026, 10, 25, 2, 45, tzinfo=oslo),
    )
    assert alarm.minutes_until() == 45
