"""One authoritative app choice and per-family labelled routes in fresh setup (#676)."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _route_section,
    _setup_routes,
)
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options

ADDRESS = "11:22:33:44:55:66"


def _fields(result) -> set[str]:
    return {str(marker.schema) for marker in result["data_schema"].schema}


async def _manual_entry(hass):
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )


def test_routes_are_the_familys_own_and_exclude_its_apps():
    keeson = _setup_routes(const.BED_TYPE_KEESON)
    # The global list repeated values and omitted KSBT03CR.
    assert const.KEESON_VARIANT_KSBT_CR in keeson
    assert const.KEESON_VARIANT_INNOVA not in keeson
    assert list(keeson)[0] == const.VARIANT_AUTO
    assert len(keeson) == len(set(keeson))
    # A bed type with one route, or whose app step asks for its own, has none.
    assert len(_setup_routes(const.BED_TYPE_SOLACE)) == 1
    assert _setup_routes(const.BED_TYPE_DOUBLESLEEP) == {}
    # A bed type that accepts its automatic route lists it first.
    assert list(_setup_routes(const.BED_TYPE_SBI))[0] == const.VARIANT_AUTO
    assert const.OKIN_DOT_FURNIMOVE_VARIANTS.isdisjoint(_setup_routes(const.BED_TYPE_OKIN_DOT))


async def test_fresh_forms_have_no_global_variant_field(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    assert result["step_id"] == "manual_entry"
    assert const.CONF_PROTOCOL_VARIANT not in _fields(result)
    assert "advanced" not in _fields(result)


async def test_generic_choice_asks_only_its_own_routes(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_KEESON, CONF_NAME: "Bed"},
    )
    assert result["step_id"] == "route"
    section = result["data_schema"].schema["advanced"]
    assert section.options == {"collapsed": True}
    options = section.schema.schema[const.CONF_PROTOCOL_VARIANT].config["options"]
    assert [option["value"] for option in options] == list(_setup_routes(const.BED_TYPE_KEESON))
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: "ksbt_cr"}}
        )
        if result.get("step_id") == "disconnect_after_command":
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == "ksbt_cr"


def test_a_choice_without_an_automatic_route_is_shown_open():
    assert _route_section(const.BED_TYPE_COMFORT_ENHANCEMENTS, "").options == {"collapsed": False}
    assert _route_section(const.BED_TYPE_KEESON, "").options == {"collapsed": True}
    assert _route_section(const.BED_TYPE_SOLACE, "") is None


async def test_the_app_entry_decides_its_route(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    choice = f"{const.BED_TYPE_KEESON}:{const.KEESON_VARIANT_INNOVA}"
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: choice}
        )
        while result["type"] is FlowResultType.FORM and result["step_id"] != "route":
            assert result["step_id"] != "manual_entry", result.get("errors")
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_KEESON
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_INNOVA


async def test_an_unchanged_preselected_app_entry_still_sets_its_route(hass):
    """The app row is authoritative even when the user leaves it as shown."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_USER}
    flow._selected_bed_type = const.BED_TYPE_KEESON
    flow._selected_protocol_variant = const.KEESON_VARIANT_RESTONIC_B
    form = await flow.async_step_manual_entry()
    defaults = form["data_schema"]({CONF_ADDRESS: ADDRESS})
    assert defaults[const.CONF_BED_TYPE] == "keeson:restonic_b"
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await flow.async_step_manual_entry(defaults)
    assert result.get("step_id") != "route"
    data = result.get("data") or flow._manual_data or flow._pending_entry
    assert data is not None
    assert data[const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_RESTONIC_B


async def test_discovered_bed_keeps_its_route_in_a_collapsed_section(
    hass, mock_bluetooth_service_info, enable_custom_integrations
):
    """A detected generic route needs no extra step; another bed type gets its own."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"
    section = result["data_schema"].schema["advanced"]
    assert section.options == {"collapsed": True}
    # Choosing another generic bed type ignores the section drawn for Linak.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
            "advanced": {const.CONF_PROTOCOL_VARIANT: const.LINAK_VARIANT_PERFORMANCE},
        },
    )
    assert result["step_id"] == "route"
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize(
    ("alias", "target"),
    [
        (const.BED_TYPE_OKIMAT, const.BED_TYPE_OKIN_UUID),
        (const.BED_TYPE_DEWERTOKIN, const.BED_TYPE_OKIN_HANDLE),
        (const.BED_TYPE_NECTAR, const.BED_TYPE_OKIN_7BYTE),
        (const.BED_TYPE_MATTRESSFIRM, const.BED_TYPE_OKIN_NORDIC),
    ],
)
async def test_aliases_show_friendly_labels_and_keep_their_saved_id(hass, alias, target):
    from custom_components.adjustable_bed.const import LEGACY_BED_TYPE_MAPPING

    assert LEGACY_BED_TYPE_MAPPING[alias] == target
    label = bed_type_label(alias)
    # Friendly, and distinct from the route it runs so it maps back exactly.
    assert alias not in label and label != bed_type_label(target)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: alias},
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass
    result = await flow.async_step_settings()
    selector = result["data_schema"].schema[const.CONF_BED_TYPE]
    shown = f"{bed_type_label(alias)} (saved as {alias})"
    assert shown in {option["label"] for option in selector.config["options"]}
    # The shown label maps back to the saved ID, never to the route it runs.
    assert selector(shown) == alias
    assert entry.data[const.CONF_BED_TYPE] == alias


def test_leggett_umbrella_route_has_a_friendly_label():
    assert bed_type_label(const.BED_TYPE_LEGGETT_PLATT) != const.BED_TYPE_LEGGETT_PLATT


@pytest.mark.parametrize(
    "name",
    [
        "RMControl",
        "Sleep Harmony",
        "Power Bob",
        "LP Control",
        "Bed Control",
        "Performance Series",
        "HomeKobo",
        "Sweet Night",
        "Sealy MotionFlex",
        "Linx",
        "Juna Sleep",
        "Woosa Sleep",
    ],
)
def test_every_listed_app_is_searchable_by_name(name):
    assert any(name.lower() in option["label"].lower() for option in get_bed_type_options())


@pytest.mark.parametrize(
    "bed_type",
    [const.BED_TYPE_JIECANG_APP, const.BED_TYPE_MALOUF_APP, const.BED_TYPE_LOGICDATA_APP],
)
def test_app_owned_layout_and_cadence_are_not_asked(bed_type):
    hidden = hidden_generic_fields(bed_type, None)
    assert {const.CONF_MOTOR_COUNT, const.CONF_MOTOR_PULSE_DELAY_MS} <= hidden
    # The pulse count still bounds each held movement.
    assert const.CONF_MOTOR_PULSE_COUNT not in hidden
