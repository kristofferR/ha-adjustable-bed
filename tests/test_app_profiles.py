"""The declarative app-profile tables used by the setup and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _per_side_refusal,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_OKIN_CST,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_SVANE,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PAIRLINK_HOME_ID,
    CONF_PAIRLINK_HOST_SOURCE,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    CONF_PAIRLINK_ROLE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M1X12_PROFILE,
    DOMAIN,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_SINO,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    OKIN_CST_VARIANT_SANCTUARY,
    STAR_ELEVATE_VARIANT_M1X12,
    SVANE_VARIANT_JENSEN_LINON,
    VARIANT_AUTO,
    ZSERIES_VARIANT_Z280,
)
from custom_components.adjustable_bed.detection import (
    FAMILY_STEP_ROUTES,
    HIDDEN_APP_CHOICES,
    bed_type_choice,
    get_bed_type_options,
    resolve_bed_type_choice,
)
from tests.form_helpers import finish_new_bed, shown_markers, start_new_bed


def test_profiles_that_always_show_massage_hide_the_generic_choice() -> None:
    assert CONF_HAS_MASSAGE in hidden_generic_fields(BED_TYPE_KEESON, KEESON_VARIANT_INNOVA)
    assert CONF_HAS_MASSAGE not in hidden_generic_fields(BED_TYPE_KEESON, KEESON_VARIANT_SINO)
    # FSM Relax asks for massage in its own step instead of the generic form.
    assert CONF_HAS_MASSAGE in hidden_generic_fields(BED_TYPE_FSM_RELAX, None)
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_FSM_RELAX, None)


def test_a_variant_entry_replaces_its_bed_types_entry() -> None:
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_SVANE, VARIANT_AUTO)
    # LinOn owns none of Svane's fields; it asks only its own motor count.
    assert hidden_generic_fields(BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON) == {CONF_MOTOR_COUNT}
    assert hidden_generic_fields(BED_TYPE_LINAK, VARIANT_AUTO) == frozenset()


@pytest.mark.parametrize(
    ("requested", "changes", "expected"),
    [
        # Moving a pair to a per-side app.
        ((BED_TYPE_FSM_RELAX, None), {CONF_BED_TYPE: BED_TYPE_FSM_RELAX}, (CONF_BED_TYPE, "FSM Relax")),
        # Changing a side's own app variant.
        (
            (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA),
            {CONF_PROTOCOL_VARIANT: KEESON_VARIANT_INNOVA},
            (CONF_PROTOCOL_VARIANT, "INNOVA"),
        ),
        # Shared settings still save.
        ((BED_TYPE_KEESON, KEESON_VARIANT_SINO), {"idle_disconnect_seconds": 55}, None),
    ],
)
def test_shared_pair_edit_refusal(requested, changes, expected) -> None:
    sides = [(BED_TYPE_KEESON, KEESON_VARIANT_SINO), (BED_TYPE_KEESON, KEESON_VARIANT_SINO)]
    assert _per_side_refusal(requested, sides, changes) == expected


def test_a_sides_own_setting_is_refused() -> None:
    sides = [(BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT)] * 2
    refusal = _per_side_refusal(
        (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT), sides, {CONF_MOTOR_COUNT: 3}
    )
    assert refusal == (CONF_MOTOR_COUNT, "Heal Every Night")
    fsm = per_side_profile(BED_TYPE_FSM_RELAX, None)
    assert fsm is not None and CONF_PRODUCT_TYPE in fsm.keys


def test_reverie_protocol_models_and_pairlink_credentials_are_side_owned() -> None:
    for bed_type in (BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND):
        profile = per_side_profile(bed_type, None)
        assert profile is not None
        assert {
            CONF_PROTOCOL_VARIANT,
            CONF_MOTOR_COUNT,
            CONF_HAS_MASSAGE,
            CONF_DISABLE_ANGLE_SENSING,
        } <= profile.keys

    pairlink = per_side_profile(BED_TYPE_REVERIE_PAIRLINK, None)
    assert pairlink is not None
    assert {
        CONF_PROTOCOL_VARIANT,
        CONF_PAIRLINK_ROLE,
        CONF_PAIRLINK_HOST_SOURCE,
        CONF_PAIRLINK_HOME_ID,
        CONF_PAIRLINK_PASSWORD_TEXT,
        CONF_PAIRLINK_PASSWORD_HEX,
    } <= pairlink.keys


async def test_options_show_the_fields_a_chosen_variant_needs(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_HAS_MASSAGE: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    form = await flow.async_step_settings()
    assert CONF_HAS_MASSAGE not in shown_markers(form)
    assert CONF_HAS_MASSAGE in shown_markers(
        form, **{CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_SANCTUARY}
    )
    saved = await flow.async_step_settings(
        {CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_SANCTUARY, CONF_HAS_MASSAGE: True}
    )
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_PROTOCOL_VARIANT] == OKIN_CST_VARIANT_SANCTUARY
    assert entry.data[CONF_HAS_MASSAGE] is True


def test_apps_chosen_by_a_variant_are_listed_by_name() -> None:
    options = {option["value"]: option["label"] for option in get_bed_type_options()}
    innova = bed_type_choice(BED_TYPE_KEESON, KEESON_VARIANT_INNOVA)
    assert options[innova] == "INNOVA app (Keeson)"
    assert resolve_bed_type_choice(innova) == (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA)
    assert resolve_bed_type_choice(BED_TYPE_KEESON) == (BED_TYPE_KEESON, None)
    # Z-Series has no automatic page; the Customatic row names it and its
    # question offers each model.
    assert BED_TYPE_ZSERIES not in options
    assert bed_type_choice(BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280) in HIDDEN_APP_CHOICES
    assert "Z-Series" in options[BED_TYPE_CUSTOMATIC_CLARITY]


def test_m1x12_main_and_elevate_profiles_are_explicit_and_findable() -> None:
    options = {option["value"]: option["label"] for option in get_bed_type_options()}
    elevate_app = bed_type_choice(BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12)
    # The StarCode apps' row names the app; its question opens the app's step.
    assert "Adjustable Comfort M1X12" in options[BED_TYPE_STARCODE_ABM5_4]
    assert BED_TYPE_STARCODE_M1X12 in FAMILY_STEP_ROUTES
    assert options[elevate_app] == "Adjustable Comfort M1X12 ELEVATE"
    assert resolve_bed_type_choice(elevate_app) == (
        BED_TYPE_STAR_ELEVATE,
        STAR_ELEVATE_VARIANT_M1X12,
    )

    main_profile = per_side_profile(BED_TYPE_STARCODE_M1X12, None)
    elevate_profile = per_side_profile(BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12)
    assert main_profile is not None and CONF_STARCODE_M1X12_PROFILE in main_profile.keys
    assert main_profile is not None and CONF_STARCODE_LIFT_ENTRIES in main_profile.keys
    assert elevate_profile is not None and CONF_PROTOCOL_VARIANT in elevate_profile.keys
    assert _per_side_refusal(
        (BED_TYPE_STARCODE_M1X12, None),
        [(BED_TYPE_STARCODE_M1X12, None), (BED_TYPE_STARCODE_M1X12, None)],
        {CONF_STARCODE_M1X12_PROFILE: "kneading"},
    ) == (CONF_STARCODE_M1X12_PROFILE, "Adjustable Comfort M1X12")
    assert _per_side_refusal(
        (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12),
        [
            (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12),
            (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12),
        ],
        {CONF_PROTOCOL_VARIANT: STAR_ELEVATE_VARIANT_M1X12},
    ) == (CONF_PROTOCOL_VARIANT, "Adjustable Comfort M1X12 ELEVATE")


@pytest.mark.parametrize("variant", [KEESON_VARIANT_INNOVA, KEESON_VARIANT_AMERICANSTAR])
async def test_setup_resolves_an_app_entry_to_its_bed_type_and_variant(
    hass: HomeAssistant, variant: str,
) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await start_new_bed(flow, "typed", bed_type_choice(BED_TYPE_KEESON, variant), "AA:BB:CC:DD:EE:02")
    # These apps' screen sets the motor count before setup finishes.
    await finish_new_bed(flow, await flow.async_step_profile_questions({CONF_MOTOR_COUNT: "2"}))
    saved = flow._finish_with_verify.await_args.args[0]
    assert (saved[CONF_BED_TYPE], saved[CONF_PROTOCOL_VARIANT]) == (
        BED_TYPE_KEESON,
        variant,
    )


async def test_options_show_the_app_entry_and_let_the_variant_field_decide(
    hass: HomeAssistant,
) -> None:
    # Keeson apps change through the guided change; Okin CST's stay in Configure.
    variant = OKIN_CST_VARIANT_NECTAR_MOVE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:03",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: variant,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    choice = bed_type_choice(BED_TYPE_OKIN_CST, variant)

    form = await flow.async_step_settings()
    marker = next(m for m in form["data_schema"].schema if m.schema == CONF_BED_TYPE)
    assert form["data_schema"].schema[marker](marker.default()) == choice
    # The selector is unchanged, so the variant field decides.
    result = await flow.async_step_settings(
        {CONF_BED_TYPE: choice, CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_SANCTUARY}
    )
    if result["type"] == "form":
        result = await flow.async_step_settings({})
    assert result["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_OKIN_CST
    assert entry.data[CONF_PROTOCOL_VARIANT] == OKIN_CST_VARIANT_SANCTUARY


def test_americanstar_profile_owns_massage_and_per_side_layout() -> None:
    variant = KEESON_VARIANT_AMERICANSTAR
    choice = bed_type_choice(BED_TYPE_KEESON, variant)
    options = {option["value"]: option["label"] for option in get_bed_type_options()}
    assert options[choice] == "AMERICANSTAR app (Keeson)"
    assert resolve_bed_type_choice(choice) == (BED_TYPE_KEESON, variant)
    assert CONF_HAS_MASSAGE in hidden_generic_fields(BED_TYPE_KEESON, variant)
    # The app's screen question asks the motor count, so the generic form hides it.
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_KEESON, variant)
    sides = [(BED_TYPE_KEESON, variant)] * 2
    assert _per_side_refusal(sides[0], sides, {CONF_MOTOR_COUNT: 3}) == (
        CONF_MOTOR_COUNT, "AMERICANSTAR"
    )
