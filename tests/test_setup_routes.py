"""One authoritative app choice and per-family labelled routes in fresh setup (#676)."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _default_setup_route,
    _labelled_routes,
    _route_section,
    _setup_routes,
)
from custom_components.adjustable_bed.detection import (
    APP_VARIANT_CHOICES,
    bed_type_choice,
    bed_type_label,
    get_bed_type_options,
    resolve_bed_type_choice,
)
from custom_components.adjustable_bed.kaidi_protocol import (
    KAIDI_ADV_TYPE_BROADCAST,
    KaidiAdvertisement,
)
from tests.form_helpers import answer_app, complete, form_fields, select_options, suggested

ADDRESS = "11:22:33:44:55:66"


def _fields(result) -> set[str]:
    return {str(marker.schema) for marker in form_fields(result["data_schema"])}


async def _manual_entry(hass, app: str):
    """Reach the typed-address step, answering the app question with ``app``."""
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        return await answer_app(hass, result, app)


async def _typed(hass, app: str):
    """Answer the app question with ``app`` and type the address."""
    result = await _manual_entry(hass, app)
    assert result["step_id"] == "manual_entry"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )


def test_routes_are_the_familys_own_and_exclude_its_apps():
    keeson = _labelled_routes(const.BED_TYPE_KEESON)
    # The global list repeated values and omitted KSBT03CR.
    assert const.KEESON_VARIANT_KSBT_CR in keeson
    assert const.KEESON_VARIANT_INNOVA not in keeson
    assert list(keeson)[0] == const.VARIANT_AUTO
    assert len(keeson) == len(set(keeson))
    # The Keeson question asks for them itself, so the generic forms do not.
    assert _setup_routes(const.BED_TYPE_KEESON) == {}
    # A bed type with one route, or whose app step asks for its own, has none.
    # The Jensen / Svane question asks Svane's app profiles itself.
    assert _setup_routes(const.BED_TYPE_SVANE) == {}
    assert _setup_routes(const.BED_TYPE_DOUBLESLEEP) == {}
    # A bed type that accepts its automatic route lists it first.
    assert list(_setup_routes(const.BED_TYPE_SBI))[0] == const.VARIANT_AUTO
    assert const.OKIN_DOT_FURNIMOVE_VARIANTS.isdisjoint(_setup_routes(const.BED_TYPE_OKIN_DOT))


async def test_the_final_settings_have_no_global_variant_field(hass, enable_custom_integrations):
    # Sealy MotionFlex is a Solace name route, whose one route asks nothing more.
    result = await _typed(hass, const.BED_TYPE_SOLACE)
    assert result["step_id"] == "solace_family"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"choice": "name_route"}
    )
    assert result["step_id"] == "finish_settings"
    assert const.CONF_PROTOCOL_VARIANT not in _fields(result)
    assert "advanced" not in {marker.schema for marker in result["data_schema"].schema}


async def test_a_generic_route_offers_only_its_own_routes(hass, enable_custom_integrations):
    # CB24's routes are the final settings' collapsed Advanced section.
    result = await _typed(hass, const.BED_TYPE_OKIN_CB24)
    assert result["step_id"] == "finish_settings"
    section = result["data_schema"].schema[
        next(marker for marker in result["data_schema"].schema if marker == "advanced")
    ]
    assert section.options == {"collapsed": True}
    options = section.schema.schema[const.CONF_PROTOCOL_VARIANT].config["options"]
    assert [option["value"] for option in options] == list(_setup_routes(const.BED_TYPE_OKIN_CB24))
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await complete(
            hass,
            result,
            {"finish_settings": {CONF_NAME: "Bed", "advanced": {const.CONF_PROTOCOL_VARIANT: "cb27"}}},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == "cb27"


def test_a_choice_without_an_automatic_route_is_shown_open():
    # Every bed type that runs only on a chosen route asks it as its app's
    # question now, so a route list without Auto is drawn for one here.
    with patch(
        "custom_components.adjustable_bed.config_flow._setup_routes",
        return_value={"mc2": "MC2", "mc3": "MC3"},
    ):
        assert _route_section(const.BED_TYPE_COMFORT_ENHANCEMENTS, "").options == {
            "collapsed": False
        }
    assert _route_section(const.BED_TYPE_OKIN_CB24, "").options == {"collapsed": True}
    assert _route_section(const.BED_TYPE_SOLACE, "") is None
    assert _route_section(const.BED_TYPE_COMFORT_ENHANCEMENTS, "") is None


def test_okin_cst_asks_its_app_instead_of_a_route_list():
    """Its Auto is the MF900 profile, so the Okin question names each app's route."""
    assert _setup_routes(const.BED_TYPE_OKIN_CST) == {}
    labels = const.OKIN_CST_VARIANTS
    assert labels[const.OKIN_CST_VARIANT_RESIDENT] == "Resident Adjustable Bed app (Rize Resident)"


async def test_the_app_entry_decides_its_route(hass, enable_custom_integrations):
    choice = f"{const.BED_TYPE_KEESON}:{const.KEESON_VARIANT_INNOVA}"
    result = await _typed(hass, choice)
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await complete(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_KEESON
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_INNOVA


async def test_a_discovered_bed_keeps_its_route_in_a_collapsed_section(
    hass, mock_bluetooth_service_info, enable_custom_integrations
):
    """A detected generic route offers its other routes under Advanced, collapsed."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info
    )
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: suggested(result, const.CONF_BED_TYPE)}
    )
    assert result["step_id"] == "finish_settings"
    section = result["data_schema"].schema["advanced"]
    assert section.options == {"collapsed": True}
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await complete(
            hass,
            result,
            {
                "finish_settings": {
                    "advanced": {const.CONF_PROTOCOL_VARIANT: const.LINAK_VARIANT_PERFORMANCE}
                }
            },
        )
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_LINAK
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == const.LINAK_VARIANT_PERFORMANCE


async def test_a_discovered_alias_shows_a_friendly_row_and_keeps_its_id(
    hass, mock_bluetooth_service_info_okimat, enable_custom_integrations
):
    """A detected compatibility ID shows its friendly label only, and saves the ID."""
    info = mock_bluetooth_service_info_okimat
    info.name, info.service_uuids = "DewertOkin", [const.DEWERTOKIN_SERVICE_UUID]
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["step_id"] == "bluetooth_confirm"
    options = select_options(result, const.CONF_BED_TYPE)
    assert not set(options.values()) & set(const.LEGACY_BED_TYPE_MAPPING)
    assert suggested(result, const.CONF_BED_TYPE) == const.BED_TYPE_DEWERTOKIN
    assert options[const.BED_TYPE_DEWERTOKIN] == bed_type_label(const.BED_TYPE_DEWERTOKIN)
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await complete(hass, result)
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_DEWERTOKIN


async def test_a_discovered_okimat_asks_the_okin_question_with_another_app(
    hass, mock_bluetooth_service_info_okimat, enable_custom_integrations
):
    info = mock_bluetooth_service_info_okimat
    info.name, info.service_uuids = "Okimat Bed", [const.OKIMAT_SERVICE_UUID]
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["step_id"] == "okin_family"
    choices = list(select_options(result, "choice"))
    assert choices[-2:] == ["another", "keep"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "another"})
    assert result["step_id"] == "select_app"
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
    # An alias inside a family's journey names that family too.
    family = " · Okin" if alias == const.BED_TYPE_OKIMAT else ""
    shown = f"{bed_type_label(alias)}{family} (saved as {alias})"
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
        "Good Vibe Sleep",
        "eShine",
    ],
)
def test_every_listed_app_is_searchable_by_name(name):
    assert any(name.lower() in option["label"].lower() for option in get_bed_type_options())


_FLOYD = bed_type_choice(const.BED_TYPE_KAIDI, const.KAIDI_VARIANT_FLOYD)


@pytest.mark.parametrize(
    ("name", "choices"),
    [
        # Okin apps also carry the Rize brand; only Kaidi's app is "Rize Beds".
        ("Rize Beds", {const.BED_TYPE_KAIDI}),
        ("Floyd Home", {const.BED_TYPE_KAIDI, _FLOYD}),
        ("ISleep", {const.BED_TYPE_KAIDI, const.BED_TYPE_ISLEEP}),
        ("Kaidi", {const.BED_TYPE_KAIDI, _FLOYD, const.BED_TYPE_ISLEEP}),
        ("Bed Connect", {const.BED_TYPE_LINAK}),
        # POWER BOB ULTRA-O is the app of the Rize Bob product on Okin CST.
        ("Power Bob", {const.BED_TYPE_MOTOSLEEP, const.BED_TYPE_OKIN_CST}),
        *(
            (name, {const.BED_TYPE_OKIN_CST})
            # The full app names of their accepted reports.
            for name in (
                "MFirm 900 - O",
                "Jordan's Sanctuary - O",
                "Resident Adjustable Bed",
                "Rize Aviada - O",
                "POWER BOB ULTRA-O",
                "Rize Contemporary III - O",
                "Carefree",
                "Rize Clarity II - O",
                "Support 挺你 科技調整床",
            )
        ),
    ],
)
def test_an_app_name_finds_only_its_own_rows(name, choices):
    found = {
        option["value"]
        for option in get_bed_type_options()
        if name.lower() in option["label"].lower()
    }
    assert found == choices


@pytest.mark.parametrize("choice", sorted(bed_type_choice(*key) for key in APP_VARIANT_CHOICES))
async def test_the_final_settings_keep_every_app_entrys_route(hass, choice):
    """A profile that owns its variant must not drop the one its app entry chose."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._typed_address, flow._new_bed_origin = ADDRESS, "typed"
    flow._manual_data = flow._seed_new_bed(*resolve_bed_type_choice(choice))
    flow._final_settings_pending = True
    with patch.object(flow, "_async_finish_family_route", return_value={}) as finish:
        result = await flow.async_step_finish_settings({})
    assert result == {} and finish.called, result
    saved = flow._manual_data
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        resolve_bed_type_choice(choice)
    )


@pytest.mark.parametrize(
    "bed_type",
    sorted(
        {bed_type for bed_type, _variant in APP_VARIANT_CHOICES}
        - const.VARIANT_REQUIRED_BED_TYPES
    ),
)
def test_a_generic_row_never_starts_on_an_app_entrys_route(bed_type):
    """A bed type's own row starts on its own route, never one of its apps'.

    A bed type that runs only as one of its apps has no row of its own.
    """
    assert (bed_type, _default_setup_route(bed_type)) not in APP_VARIANT_CHOICES


@pytest.mark.parametrize(
    ("choice", "bed_type", "variant"),
    [
        (const.BED_TYPE_KAIDI, const.BED_TYPE_KAIDI, const.VARIANT_AUTO),
        (f"{const.BED_TYPE_KAIDI}:{const.KAIDI_VARIANT_FLOYD}", const.BED_TYPE_KAIDI, const.KAIDI_VARIANT_FLOYD),
        (const.BED_TYPE_ISLEEP, const.BED_TYPE_ISLEEP, const.VARIANT_AUTO),
    ],
)
async def test_kaidi_brand_lists_each_app(
    hass, enable_custom_integrations, choice, bed_type, variant
):
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        for step_input in (
            {CONF_ADDRESS: "select_by_app"},
            # The brand list is the fallback of the app question. Kaidi has no
            # family question, so its apps are rows of the list themselves.
            {const.CONF_BED_TYPE: "not_listed"},
            {const.CONF_BED_TYPE: choice},
        ):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], step_input)
    assert result["step_id"] == "manual_entry"
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.resolve_kaidi_advertisement",
            return_value=None,
        ),
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
        # ISleep asks for its product and room, as shown.
        result = await complete(hass, result, {"finish_settings": {CONF_NAME: "Kaidi Bed"}})
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    data = result["data"]
    assert (data[const.CONF_BED_TYPE], data[const.CONF_PROTOCOL_VARIANT]) == (bed_type, variant)


@pytest.mark.parametrize(
    ("choice", "product_id", "resolved"),
    [
        (const.BED_TYPE_KAIDI, 136, const.KAIDI_VARIANT_SEAT_1),
        (_FLOYD, 139, const.KAIDI_VARIANT_FLOYD),
    ],
)
async def test_kaidi_app_rows_keep_the_advertised_mesh_metadata(
    hass, enable_custom_integrations, choice, product_id, resolved
):
    """Picking a Kaidi app by its label still caches the room, target and product."""
    result = await _typed(hass, choice)
    advertisement = KaidiAdvertisement(
        adv_type=KAIDI_ADV_TYPE_BROADCAST,
        room_id=0x12345678,
        vaddr=0x01020304,
        product_id=product_id,
        sofa_acu_no=0x2004,
    )
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.resolve_kaidi_advertisement",
            return_value=advertisement,
        ),
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
    ):
        result = await complete(
            hass,
            result,
            {"finish_settings": {"advanced": {const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO}}},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    data = result["data"]
    assert (data[const.CONF_BED_TYPE], data[const.CONF_PROTOCOL_VARIANT]) == (
        resolve_bed_type_choice(choice)[0],
        resolve_bed_type_choice(choice)[1] or const.VARIANT_AUTO,
    )
    assert data[const.CONF_KAIDI_ROOM_ID] == 0x12345678
    assert data[const.CONF_KAIDI_TARGET_VADDR] == 0x01020304
    assert data[const.CONF_KAIDI_PRODUCT_ID] == product_id
    assert data[const.CONF_KAIDI_RESOLVED_VARIANT] == resolved


@pytest.mark.parametrize(
    "bed_type",
    [const.BED_TYPE_JIECANG_APP, const.BED_TYPE_MALOUF_APP, const.BED_TYPE_LOGICDATA_APP],
)
def test_app_owned_layout_and_cadence_are_not_asked(bed_type):
    hidden = hidden_generic_fields(bed_type, None)
    assert {const.CONF_MOTOR_COUNT, const.CONF_MOTOR_PULSE_DELAY_MS} <= hidden
    # The pulse count still bounds each held movement.
    assert const.CONF_MOTOR_PULSE_COUNT not in hidden


async def test_an_app_model_is_asked_when_its_name_rule_cannot_run(
    hass, enable_custom_integrations
):
    """A manual entry knows no Bluetooth name, so the app's Auto rule is refused."""
    result = await _typed(hass, const.BED_TYPE_RICHMAT)
    assert result["step_id"] == "richmat_family"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"choice": "harmony"}
    )
    assert result["step_id"] == "profile_questions"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "auto"}
    )
    assert result["errors"] == {const.CONF_PROTOCOL_VARIANT: "richmat_mh_no_name"}
    model = next(
        route for route in const.RICHMAT_MH_VARIANTS_BY_APP["harmony"] if route != "auto"
    )
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: model}
        )
        assert not result.get("errors"), result.get("errors")
        result = await complete(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_RICHMAT_HARMONY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == model


def test_every_picker_label_maps_back_to_one_choice():
    """The searchable picker uses labels as values, so labels must be unique."""
    labels = [option["label"] for option in get_bed_type_options()]
    assert len(labels) == len(set(labels))


@pytest.mark.parametrize("bed_type", [const.BED_TYPE_ESHINE_OKIN])
def test_product_apps_choose_their_route_from_the_app_entry(bed_type):
    """Each product is its own app entry: no global variant and no route step."""
    assert _setup_routes(bed_type) == {}
    rows = [
        option
        for option in get_bed_type_options()
        if resolve_bed_type_choice(option["value"])[0] == bed_type
    ]
    assert rows
    assert all(bed_type_label(bed_type) != option["label"] for option in rows)
