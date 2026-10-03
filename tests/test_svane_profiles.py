"""Explicit Svane configuration, native exposure and physical preference guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jensen_linon import JensenLinonController
from custom_components.adjustable_bed.beds.svane import HEAD, POSITION, SvaneController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SVANE_VARIANT_JENSEN_LINON,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
    VARIANT_AUTO,
    bed_type_has_position_feedback,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.detection import detect_bed_type
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.svane_state import get_svane_session
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.app_state_helpers import stored_app_state
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_svane import make_controller, written


@pytest.mark.parametrize(
    "variant,expected",
    [
        (VARIANT_AUTO, "multi"),
        (None, "multi"),
        (SVANE_VARIANT_MULTI, "multi"),
        (SVANE_VARIANT_JMC, "jmc"),
        (SVANE_VARIANT_JENSEN_LINON, "linon"),
    ],
)
async def test_stored_profile_factory_preserves_old_routes_and_explicit_jmc(
    hass, variant, expected
):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_SVANE}
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator, BED_TYPE_SVANE, variant, None, device_name="JMC400"
    )
    if expected == "linon":
        assert isinstance(controller, JensenLinonController)
    else:
        assert isinstance(controller, SvaneController) and controller.profile == expected
        assert not controller.position_number_specs
        assert {s.key for s in controller.motor_control_specs} == {"back", "legs"}
        assert not bed_type_has_position_feedback(BED_TYPE_SVANE, variant)
    assert not requires_pairing(BED_TYPE_SVANE, variant)


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_all_setup_forms_explicit_profile_without_unproven_layout_or_timing(hass, step):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = flow._disambiguated_bed_type = BED_TYPE_SVANE
    info = MagicMock()
    info.name = "Svane Bed"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = [HEAD]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    form = await getattr(flow, "async_step_" + step)()
    fields = {m.schema for m in form["data_schema"].schema}
    assert CONF_PROTOCOL_VARIANT in fields
    assert not fields.intersection(
        {
            CONF_MOTOR_COUNT,
            CONF_HAS_MASSAGE,
            CONF_MOTOR_PULSE_COUNT,
            CONF_MOTOR_PULSE_DELAY_MS,
            CONF_DISABLE_ANGLE_SENSING,
        }
    )


async def test_preverification_normalizes_legacy_options_before_probe(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._verification_possible = MagicMock(return_value=True)
    flow.async_step_setup_progress = AsyncMock(return_value={"type": "form"})
    entry = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC,
        CONF_MOTOR_COUNT: 4,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: False,
    }
    await flow._finish_with_verify(entry, "Bed")
    assert flow._pending_entry[CONF_MOTOR_COUNT] == 2
    assert flow._pending_entry[CONF_HAS_MASSAGE] is False
    assert flow._pending_entry[CONF_DISABLE_ANGLE_SENSING] is True


async def test_options_explicit_jmc_persists_and_clears_changed_app_session(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Svane",
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    session = get_svane_session(hass, entry.data[CONF_ADDRESS], "multi")
    session.light_on = True
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow._async_options_form(
        {CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC}, step_id="settings"
    )
    if result["type"] == "form":
        result = await flow._async_options_form(
            {CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC}, step_id="settings"
        )
    assert result["type"] == "create_entry"
    assert entry.data[CONF_PROTOCOL_VARIANT] == SVANE_VARIANT_JMC
    assert not get_svane_session(hass, entry.data[CONF_ADDRESS], "multi").light_on


@pytest.mark.parametrize(
    ("name", "is_svane"),
    [
        ("svane bed", True),
        ("Svane Bed extra", True),
        ("SVANE BED", True),
        ("JMC400", False),
        ("jmc400", False),
    ],
)
def test_established_name_match_is_kept_and_jmc_stays_jensen(name, is_svane):
    """Renamed Svane beds keep detecting as before; JMC400 remains Jensen."""
    info = MagicMock()
    info.name = name
    info.service_uuids = []
    info.manufacturer_data = {}
    info.address = "AA:BB:CC:DD:EE:FF"
    assert (detect_bed_type(info) == BED_TYPE_SVANE) is is_svane


async def test_native_entities_expose_literals_raw_records_and_unknown_assumed_lamp(hass):
    controller = make_controller()
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_SVANE)
    runtime.bed_type = BED_TYPE_SVANE

    async def dispatch(command, **kwargs):
        await command(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    buttons = _button_entities_for(hass, runtime)
    # The app's Svane position keeps the preset_zero_g ID existing entries use.
    literal = next(b for b in buttons if "preset_zero_g" in b.unique_id)
    assert not any("svane_position" in b.unique_id or "flat" in b.unique_id for b in buttons)
    await literal.async_press()
    assert written(controller)[0][2] == "0300"
    covers = _cover_entities_for(hass, runtime)
    assert {c.unique_id for c in covers} == {"bed_back_left", "bed_legs_left"}
    numbers = _number_entities_for(hass, runtime)
    # The established 0-100 light slider stays; levels snap to the app's steps.
    intensity = next(
        n for n in numbers if n.entity_description.key == "light_level"
    )
    assert (intensity.native_min_value, intensity.native_max_value) == (0, 100)
    assert not any("position" in n.unique_id for n in numbers)
    assert _light_entities_for(hass, runtime) == []
    lamp = next(
        s
        for s in _switch_entities_for(hass, runtime)
        if s.entity_description.key == "under_bed_lights"
    )
    assert lamp.is_on is None and lamp.assumed_state
    with patch.object(lamp, "async_write_ha_state", MagicMock()):
        await lamp.async_turn_on()
        assert lamp.is_on is True
    assert controller.session.light_on


async def test_real_parser_coordinator_and_diagnostic_freshness_no_angle_inference(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller()
    coordinator._controller = controller
    coordinator._client = controller.client
    controller._coordinator = coordinator
    sensors = {
        s._spec.key: s
        for s in _sensor_entities_for(hass, coordinator)
        if hasattr(s, "_spec") and s._spec.key.startswith("svane_")
    }
    assert sensors["svane_head_raw"].native_value is None
    assert controller.accept_response(HEAD, POSITION, b"\x81\x38\xff")
    assert sensors["svane_head_raw"].native_value == "8138ff"
    assert sensors["svane_head_raw"].extra_state_attributes["svane_head_raw_observed_at"]
    assert sensors["svane_head_raw"].extra_state_attributes["svane_head_raw_service"] == HEAD
    assert (
        sensors["svane_head_raw"].extra_state_attributes["svane_head_raw_target_address"]
        == entry.data[CONF_ADDRESS]
    )
    assert sensors["svane_feet_raw"].native_value is None
    assert not coordinator.position_data
    assert not controller.position_number_specs


async def test_preferences_are_app_state_without_entry_or_bond_writes(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_SVANE}
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, BED_TYPE_SVANE, None, None)
    assert isinstance(controller, SvaneController)
    coordinator._controller = controller
    await coordinator._async_restore_app_state(controller)
    before = dict(entry.data)
    preferences = {"intensity": 95, "slots": ["00112233", "44556677"]}
    with patch.object(coordinator, "_begin_internal_entry_update") as guard:
        controller.session.restore(preferences)
        coordinator.save_app_state(controller)
        coordinator.save_app_state(controller)
    guard.assert_not_called()
    assert entry.data == before
    assert await stored_app_state(coordinator, "multi") == preferences


async def test_paired_persistence_and_parent_to_standalone_migration_remain_target_local(hass):
    from custom_components.adjustable_bed import _build_paired_children
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_CHILDREN,
        CONF_PAIR_ID,
        CONF_SIDE,
        SIDE_LEFT,
        SIDE_RIGHT,
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.pairing import get_child

    first = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_SIDE: SIDE_LEFT,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_MULTI,
    }
    second = {
        **first,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        CONF_SIDE: SIDE_RIGHT,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PAIR_ID: "svane-pair",
            CONF_PAIR_CHILDREN: [first, second],
            CONF_NAME: "Paired Svane",
        },
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    parent = PairedBedCoordinator(hass, entry, children)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = parent
    left, right = children[SIDE_LEFT], children[SIDE_RIGHT]
    left_controller = await create_controller(left, BED_TYPE_SVANE, SVANE_VARIANT_MULTI, None)
    assert isinstance(left_controller, SvaneController)
    left._controller = left_controller
    await left._async_restore_app_state(left_controller)
    session = left_controller.session
    session.light_on = True
    session.light_step = -5
    session.multi_slots[1] = (b"head", b"feet")
    with patch.object(hass.config_entries, "async_update_entry") as update:
        left.save_app_state(left_controller)
    # Preferences belong to the physical address, never to either descriptor.
    update.assert_not_called()
    assert get_child(entry.data, SIDE_LEFT) == first
    assert get_child(entry.data, SIDE_RIGHT) == second
    assert (await stored_app_state(left, "multi"))["multi_slots"] == {"1": ["68656164", "66656574"]}
    assert await stored_app_state(right, "jmc") == {}
    standalone = MockConfigEntry(domain=DOMAIN, data=dict(left.entry.data))
    rebuilt = AdjustableBedCoordinator(hass, standalone)
    controller = await create_controller(rebuilt, BED_TYPE_SVANE, SVANE_VARIANT_MULTI, None)
    assert isinstance(controller, SvaneController)
    assert controller.session is session
    await rebuilt._async_restore_app_state(controller)
    assert (
        session.multi_slots[1] == (b"head", b"feet")
        and session.light_on
        and session.light_step == -5
    )
    assert get_svane_session(hass, second[CONF_ADDRESS], "jmc") is not session
    await parent.async_shutdown()


@pytest.mark.parametrize("step", ["manual_entry", "manual_config", "bluetooth_confirm"])
async def test_changed_bed_type_rebuilds_hidden_generic_choices_before_entry(hass, step):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = flow._disambiguated_bed_type = BED_TYPE_SVANE
    info = MagicMock()
    info.name = "Svane Bed"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = [HEAD]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    await getattr(flow, "async_step_" + step)()
    result = await getattr(flow, "async_step_" + step)(
        {CONF_BED_TYPE: "okin_cst", CONF_ADDRESS: info.address, CONF_NAME: "Preserved input"}
    )
    assert result["type"] == "form"
    assert CONF_MOTOR_COUNT in {m.schema for m in result["data_schema"].schema}
    name_marker = next(m for m in result["data_schema"].schema if m.schema == CONF_NAME)
    assert name_marker.description["suggested_value"] == "Preserved input"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("JMC400", SVANE_VARIANT_JMC),
        ("OtherJMCtarget", SVANE_VARIANT_JMC),
        ("jmc400", VARIANT_AUTO),
        ("Svane Bed", VARIANT_AUTO),
    ],
)
async def test_new_explicit_svane_selection_uses_case_sensitive_app_name_rule(hass, name, expected):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    info = MagicMock()
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = []
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._disambiguated_bed_type = BED_TYPE_SVANE
    finish = AsyncMock()
    flow._finish_with_verify = finish
    await flow.async_step_bluetooth_confirm(
        {
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            "disconnect_after_command": False,
        }
    )
    assert finish.await_args.args[0][CONF_PROTOCOL_VARIANT] == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Svane Bed", True),
        ("JMC400", True),
        ("svane bed", False),
        ("JMC400 extra", False),
        (None, False),
    ],
)
def test_source_exact_scan_allowlist_independent_of_known_address_selection(name, expected):
    from custom_components.adjustable_bed.svane_state import is_svane_discovery_name

    assert is_svane_discovery_name(name) is expected


@pytest.mark.parametrize("stale", [False, True])
async def test_current_disconnect_hook_runs_once_before_connecting_return(hass, stale):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_SVANE}
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller()
    coordinator._controller = controller
    coordinator._client = controller.client
    coordinator._connecting = True
    hook = MagicMock()
    with patch.object(controller, "on_disconnect", hook):
        coordinator._on_disconnect(MagicMock() if stale else controller.client)
    assert hook.call_count == (0 if stale else 1)
    assert coordinator.controller is controller
    assert coordinator.client is controller.client
