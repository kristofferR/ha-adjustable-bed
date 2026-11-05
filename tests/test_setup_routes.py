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
    _apply_setup_bed_type_choice,
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
from tests.form_helpers import shown_markers

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


async def test_fresh_forms_have_no_global_variant_field(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    assert result["step_id"] == "manual_entry"
    assert const.CONF_PROTOCOL_VARIANT not in shown_markers(result)
    assert "advanced" not in shown_markers(result)
    # The Jensen / Svane question asks Svane's app profiles after the form.
    assert const.CONF_PROTOCOL_VARIANT not in shown_markers(
        result, **{const.CONF_BED_TYPE: const.BED_TYPE_SVANE}
    )


async def test_generic_choice_asks_only_its_own_routes(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_OKIN_CB24, CONF_NAME: "Bed"},
    )
    assert result["step_id"] == "route"
    section = result["data_schema"].schema["advanced"]
    assert section.options == {"collapsed": True}
    options = section.schema.schema[const.CONF_PROTOCOL_VARIANT].config["options"]
    assert [option["value"] for option in options] == list(_setup_routes(const.BED_TYPE_OKIN_CB24))
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: "cb27"}}
        )
        if result.get("step_id") == "disconnect_after_command":
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == "cb27"


def test_a_choice_without_an_automatic_route_is_shown_open():
    assert _route_section(const.BED_TYPE_COMFORT_ENHANCEMENTS, "").options == {"collapsed": False}
    assert _route_section(const.BED_TYPE_OKIN_CB24, "").options == {"collapsed": True}
    assert _route_section(const.BED_TYPE_SOLACE, "") is None


def test_okin_cst_asks_its_app_instead_of_a_route_list():
    """Its Auto is the MF900 profile, so the Okin question names each app's route."""
    assert _setup_routes(const.BED_TYPE_OKIN_CST) == {}
    labels = const.OKIN_CST_VARIANTS
    assert labels[const.OKIN_CST_VARIANT_RESIDENT] == "Resident Adjustable Bed app (Rize Resident)"


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
    assert form["data_schema"] is not None
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
    ("name", "service_uuid", "alias"),
    [
        ("Okimat Bed", const.OKIMAT_SERVICE_UUID, const.BED_TYPE_OKIMAT),
        ("DewertOkin", const.DEWERTOKIN_SERVICE_UUID, const.BED_TYPE_DEWERTOKIN),
    ],
)
async def test_a_discovered_alias_shows_a_friendly_row_and_keeps_its_id(
    hass, mock_bluetooth_service_info_okimat, enable_custom_integrations, name, service_uuid, alias
):
    """Discovery shows a detected compatibility ID by its friendly label only."""
    info = mock_bluetooth_service_info_okimat
    info.name, info.service_uuids = name, [service_uuid]
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert result["step_id"] == "bluetooth_confirm"
    schema = result["data_schema"].schema
    selector = schema[const.CONF_BED_TYPE]
    labels = {option["label"] for option in selector.config["options"]}
    assert not labels & set(const.LEGACY_BED_TYPE_MAPPING)
    shown = next(marker for marker in schema if marker == const.CONF_BED_TYPE).default()
    # Okimat opens the Okin family row; another alias shows its own label.
    family_row = next(
        option["label"]
        for option in get_bed_type_options()
        if option["value"] == const.BED_TYPE_FURNIMOVE
    )
    assert shown == (family_row if alias == const.BED_TYPE_OKIMAT else bed_type_label(alias))
    # The friendly row maps back to the detected ID, which is never rewritten.
    assert selector(shown) == alias
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
async def test_fitting_the_form_keeps_every_app_entrys_route(hass, choice):
    """A profile that owns its variant must not drop the one its app entry chose."""
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_USER}
    submitted = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: choice}
    _apply_setup_bed_type_choice(submitted, None, const.VARIANT_AUTO)
    flow._drop_owned_answers(submitted, None, const.VARIANT_AUTO)
    assert (submitted[const.CONF_BED_TYPE], submitted[const.CONF_PROTOCOL_VARIANT]) == (
        resolve_bed_type_choice(choice)
    )


@pytest.mark.parametrize(
    "key",
    sorted(
        key
        for key in APP_VARIANT_CHOICES
        if key[0] in {option["value"] for option in get_bed_type_options()}
    ),
)
def test_a_generic_row_never_inherits_the_app_entry_it_replaces(key):
    """A form drawn for an app entry, then switched to its bed type's own row."""
    bed_type, app_variant = key
    submitted = {const.CONF_BED_TYPE: bed_type}
    _apply_setup_bed_type_choice(submitted, bed_type, app_variant)
    assert (bed_type, submitted[const.CONF_PROTOCOL_VARIANT]) not in APP_VARIANT_CHOICES


@pytest.mark.parametrize(
    ("index", "bed_type", "variant"),
    [
        (0, const.BED_TYPE_KAIDI, const.VARIANT_AUTO),
        (1, const.BED_TYPE_KAIDI, const.KAIDI_VARIANT_FLOYD),
        (2, const.BED_TYPE_ISLEEP, const.VARIANT_AUTO),
    ],
)
async def test_kaidi_brand_lists_each_app(
    hass, enable_custom_integrations, index, bed_type, variant
):
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        for step_input in (
            {CONF_ADDRESS: "select_by_brand"},
            {"actuator_brand": "kaidi"},
            {"variant": str(index)},
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
            result["flow_id"], {CONF_ADDRESS: ADDRESS, CONF_NAME: "Kaidi Bed"}
        )
        if result.get("step_id") == "route":
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO}}
            )
        if result.get("step_id") == "isleep":
            # The ISleep app step asks for its product and room, as shown.
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], result["data_schema"]({})
            )
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
    label = {option["value"]: option["label"] for option in get_bed_type_options()}[choice]
    result = await _manual_entry(hass)
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
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: label, CONF_NAME: "Kaidi Bed"},
        )
        if result.get("step_id") == "route":
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO}}
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


async def test_route_is_collected_before_route_dependent_validation(
    hass, enable_custom_integrations
):
    """An app model route can be chosen even when its automatic rule cannot run."""
    result = await _manual_entry(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_HARMONY},
    )
    # No Bluetooth name is known, so the automatic model rule would be refused.
    assert result["step_id"] == "route"
    model = next(
        route for route in _setup_routes(const.BED_TYPE_RICHMAT_HARMONY) if route != "auto"
    )
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: model}}
        )
        while result["type"] is FlowResultType.FORM and result["step_id"] != "manual_entry":
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert not result.get("errors"), result.get("errors")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == model


async def test_a_refused_route_is_asked_again(hass, enable_custom_integrations):
    result = await _manual_entry(hass)
    choice = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_HARMONY}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], choice)
    assert result["step_id"] == "route"
    # Auto needs a Bluetooth name this manual entry does not have.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"advanced": {const.CONF_PROTOCOL_VARIANT: "auto"}}
    )
    assert result["step_id"] == "manual_entry"
    assert result["errors"]["base"] == "richmat_mh_no_name"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], choice)
    assert result["step_id"] == "route"
    hass.config_entries.flow.async_abort(result["flow_id"])


def test_every_picker_label_maps_back_to_one_choice():
    """The searchable picker uses labels as values, so labels must be unique."""
    labels = [option["label"] for option in get_bed_type_options()]
    assert len(labels) == len(set(labels))


@pytest.mark.parametrize("bed_type", [const.BED_TYPE_GOODVIBE, const.BED_TYPE_ESHINE_OKIN])
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
    choice = rows[0]["value"]
    submitted = {const.CONF_BED_TYPE: choice}
    _apply_setup_bed_type_choice(submitted, None, const.VARIANT_AUTO)
    assert (submitted[const.CONF_BED_TYPE], submitted[const.CONF_PROTOCOL_VARIANT]) == (
        resolve_bed_type_choice(choice)
    )
