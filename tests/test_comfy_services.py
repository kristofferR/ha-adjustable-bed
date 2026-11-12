"""Registered row084 actions, real entity builders, setup and service preflight."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.kaidi.comfy import ComfyController
from custom_components.adjustable_bed.profiles.comfy import COMFY_ACTIONS
from tests.test_comfy import make_controller, no_real_timers  # noqa: F401
from tests.test_generic_services import select, target
from tests.test_isleep import packets


@pytest.fixture
async def comfy_resolve(hass):
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as patched:
        yield patched


def actual_target(app="komfyd"):
    c, raw, client = make_controller(app)
    co, _ = target(app, family=ComfyController)
    co.capability_controller = co.controller = c
    co.client, co.cancel_command = client, raw.cancel_command
    co.motor_pulse_count, co.motor_pulse_delay_ms = 1, 0
    co.entry = raw.entry
    c._coordinator = co

    async def execute(command, **_kwargs):
        await command(c)

    co.async_execute_controller_command = AsyncMock(side_effect=execute)
    return co, c, client


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("action", COMFY_ACTIONS)
async def test_registered_actions_dispatch_real_controller(hass, comfy_resolve, app, action):
    co, c, client = actual_target(app)
    select(comfy_resolve, (co, c))
    await hass.services.async_call(
        const.DOMAIN, "comfy_control", {"device_id": "bed", "action": action}, blocking=True
    )
    assert packets(client)[0][11] == c._opcode(action)
    assert co.async_execute_controller_command.await_args.kwargs["cancel_running"]
    c._stop_countdown()


async def test_all_targets_preflight_before_first_frame(hass, comfy_resolve):
    first, fc, client = actual_target()
    second, sc, other = actual_target("comfyds")
    sc._lock_status = "other"
    select(comfy_resolve, (first, fc), (second, sc))
    with pytest.raises(ServiceValidationError, match="locked"):
        await hass.services.async_call(
            const.DOMAIN,
            "comfy_control",
            {"device_id": "bed", "action": "h_increase"},
            blocking=True,
        )
    assert not packets(client) and not packets(other)
    first.async_execute_controller_command.assert_not_awaited()


async def test_raw_admin_and_unlisted_opcodes_are_rejected(hass, comfy_resolve):
    for action in ("69", "enroll", "reset", "massage_on"):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                const.DOMAIN, "comfy_control", {"device_id": "bed", "action": action}, blocking=True
            )


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
async def test_actual_platform_builders_expose_source_named_controls(hass, app):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.cover import _cover_entities_for
    from custom_components.adjustable_bed.select import _select_entities_for
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from tests.card_placements import _runtime

    c, _, _ = make_controller(app)
    runtime = _runtime()
    runtime.capability_controller = c
    runtime.controller = c
    runtime.bed_type = app
    runtime.entry.data = {**c._coordinator.entry.data, const.CONF_MOTOR_COUNT: 3}
    runtime.controller_side = None
    runtime.has_massage = False
    runtime.entry.entry_id = "comfy"
    with patch(
        "custom_components.adjustable_bed.button._async_migrate_massage_intensity_button_unique_ids"
    ):
        buttons = _button_entities_for(hass, runtime)
    assert {f"comfy_{a}" for a in COMFY_ACTIONS} <= {b.translation_key for b in buttons}
    assert {e.entity_description.translation_key for e in _cover_entities_for(hass, runtime)} == {
        "comfy_head",
        "comfy_foot",
        "comfy_waist",
    }
    assert {e.translation_key for e in _select_entities_for(hass, runtime)} >= {
        "comfy_selected_side",
        "comfy_timer_selection",
    }
    assert {e.translation_key for e in _sensor_entities_for(hass, runtime)} >= {
        "comfy_lock_status",
        "comfy_timer_remaining",
    }


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
async def test_manual_picker_profile_and_paired_owned_fields(hass, app):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.detection import get_bed_type_options
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    assert app in {o["value"] for o in get_bed_type_options()}
    profile = setup_profile_for({const.CONF_BED_TYPE: app})
    assert profile is not None
    assert {q.key for q in profile.questions} == {
        const.CONF_PRODUCT_TYPE,
        const.CONF_KAIDI_ROOM_ID,
        const.CONF_KAIDI_SOFA_ACU_NO,
    }
    assert profile.owns[const.CONF_MOTOR_COUNT] == 3
    assert profile.owns[const.CONF_HAS_MASSAGE] is False
    assert per_side_profile(app, None) is not None


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
async def test_real_manual_flow_saves_explicit_app_and_alias(hass, app):
    from homeassistant.const import CONF_NAME

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    result = await start_new_bed(flow, "typed", app, "AA:BB:CC:DD:EE:FF")
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions(
        {
            const.CONF_PRODUCT_TYPE: 131,
            const.CONF_KAIDI_ROOM_ID: -1,
            const.CONF_KAIDI_SOFA_ACU_NO: 0xF322,
        }
    )
    assert result["step_id"] == "finish_settings"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings({CONF_NAME: "Bed"})
    saved = finish.call_args.args[0]
    assert (
        saved[const.CONF_BED_TYPE],
        saved[const.CONF_PRODUCT_TYPE],
        saved[const.CONF_KAIDI_ROOM_ID],
    ) == (app, 131, -1)
    assert saved[const.CONF_MOTOR_COUNT] == 3 and saved[const.CONF_HAS_MASSAGE] is False


def test_shared_and_name_only_hints_never_guess_either_app():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    for name, payload in (
        ("KomfyD", {}),
        ("ComfyDS", {}),
        ("Mouselet", {0xFFFF: bytes.fromhex("c0ff0278563412ffeeddccbbaa0000821322a104030201")}),
    ):
        result = detect_bed_type_detailed(_make_service_info(name=name, manufacturer_data=payload))
        assert result.bed_type not in ("komfyd", "comfyds")
    assert {"komfyd", "comfyds"} <= set(result.ambiguous_types)


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("product", (None, "129", "130", "131"))
def test_pairing_admission_requires_the_dual_product(app, product):
    from custom_components.adjustable_bed.pairing import supports_single_address_pairing

    assert supports_single_address_pairing(app, product_type=product) == (product == "130")


async def test_unknown_hf_side_fails_all_target_preflight(hass, comfy_resolve):
    first, fc, client = actual_target()
    second, sc, other = actual_target("comfyds")
    sc._selected_side = None
    select(comfy_resolve, (first, fc), (second, sc))
    with pytest.raises(ServiceValidationError, match="Select a bed side"):
        await hass.services.async_call(
            const.DOMAIN,
            "comfy_control",
            {"device_id": "bed", "action": "h_increase"},
            blocking=True,
        )
    assert not packets(client) and not packets(other)
