"""The declarative app-profile tables used by the setup and options flows."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedOptionsFlow,
    _per_side_refusal,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_FSM_RELAX,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_SINO,
    SVANE_VARIANT_JENSEN_LINON,
    VARIANT_AUTO,
)


def test_profiles_that_always_show_massage_hide_the_generic_choice() -> None:
    assert CONF_HAS_MASSAGE in hidden_generic_fields(BED_TYPE_KEESON, KEESON_VARIANT_INNOVA)
    assert CONF_HAS_MASSAGE not in hidden_generic_fields(BED_TYPE_KEESON, KEESON_VARIANT_SINO)
    # FSM Relax asks for massage in its own step instead of the generic form.
    assert CONF_HAS_MASSAGE in hidden_generic_fields(BED_TYPE_FSM_RELAX, None)
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_FSM_RELAX, None)


def test_a_variant_entry_replaces_its_bed_types_entry() -> None:
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_SVANE, VARIANT_AUTO)
    assert hidden_generic_fields(BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON) == frozenset()
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


async def test_options_redraw_when_a_variant_needs_hidden_fields(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: KEESON_VARIANT_INNOVA,
            CONF_HAS_MASSAGE: False,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    form = await flow.async_step_settings()
    assert CONF_HAS_MASSAGE not in {marker.schema for marker in form["data_schema"].schema}
    redrawn = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: KEESON_VARIANT_SINO})
    assert redrawn["type"] == "form"
    assert CONF_HAS_MASSAGE in {marker.schema for marker in redrawn["data_schema"].schema}
    saved = await flow.async_step_settings({CONF_HAS_MASSAGE: True})
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_PROTOCOL_VARIANT] == KEESON_VARIANT_SINO
    assert entry.data[CONF_HAS_MASSAGE] is True
