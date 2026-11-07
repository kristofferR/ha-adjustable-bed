"""Explicit app/model selection and narrow advertisement hints."""

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.catalog_json import load
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.richmat_classic_models import MODEL_CHOICES
from custom_components.adjustable_bed.richmat_classic_profiles import (
    APP_NAMES,
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.setup_questions import SetupProfile, setup_profile

PROFILE = setup_profile(BED_TYPE_RICHMAT_CLASSIC_APPS)
assert isinstance(PROFILE, SetupProfile)
LAYOUT, THIRD_SERVICE = PROFILE.questions


def _layouts(app: str) -> set[str]:
    return set(LAYOUT.options({"protocol_variant": app}) or {})


def _setup(data: dict) -> dict:
    """Stage the layout answer as setup and Configure do; raise on its error."""
    answers = {key: data[key] for key in ("product_type",) if key in data}
    staged = PROFILE.staged({k: v for k, v in data.items() if k not in answers}, answers)
    assert PROFILE.validate is not None
    if errors := PROFILE.validate(staged):
        raise ValueError(errors)
    return {**staged, **PROFILE.settled(staged)}


def test_all_five_app_choices_are_findable_and_model_inventories_are_distinct():
    # Each app is an answer of the one Richmat row, which names it.
    richmat_row = next(o for o in get_bed_type_options() if o['value'] == 'richmat')
    for app, name in APP_NAMES.items():
        assert name in richmat_row['label']
        assert not any(o['value'] == 'richmat_classic_apps:' + app for o in get_bed_type_options())
    assert {app: len(models) for app, models in MODEL_CHOICES.items()} == {
        'avocadoecobase': 704, 'coastersleep': 715, 'fortywinks': 725, 'milemont': 700, 'superior': 725,
    }
    for app, models in MODEL_CHOICES.items():
        assert set(models) == set(load_catalog(app).models)


def test_runtime_catalog_matches_every_frozen_member_layout_contract():
    """Expected digests come from accepted CP/MS records, before runtime import."""
    path = Path(__file__).parent / "fixtures/richmat_classic/catalog_contracts.json.gz"
    with gzip.open(path, "rt") as source:
        expected = json.load(source)
    assert len(expected["models"]) == 3569
    for row in expected["models"]:
        catalog = load("richmat_classic_data", row["app"]).entries()
        assert catalog["fields"].json() == expected["fields"]
        model = catalog["models"].entries()[row["layout"]].json()
        encoded = json.dumps(model, separators=(",", ":"), sort_keys=True).encode()
        assert hashlib.sha256(encoded).hexdigest() == row["sha256"], row


def test_the_app_is_its_variant_and_setup_asks_its_layout():
    assert BED_TYPE_RICHMAT_CLASSIC_APPS not in {o["value"] for o in get_bed_type_options()}
    assert LAYOUT.key == "product_type"
    assert (THIRD_SERVICE.key, THIRD_SERVICE.default, THIRD_SERVICE.advanced) == (
        CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False, True,
    )
    saved = _setup({"protocol_variant": "milemont", "product_type": "6BRM"})
    assert {key: saved[key] for key in (CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING)} == {
        CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: False, CONF_DISABLE_ANGLE_SENSING: True,
    }
    assert PROFILE.title is not None and PROFILE.title(saved) == "Milemont"


def test_explicit_layout_is_required_and_aliases_are_package_local():
    with pytest.raises(ValueError):
        _setup({'protocol_variant': 'avocadoecobase'})
    assert resolve_layout('avocadoecobase', ' B6RU ') == 'B6RM'
    assert resolve_layout('avocadoecobase', 'OTRM', russian=True) == 'O0RM'
    assert resolve_layout('avocadoecobase', 'MPE_HJ002-bed', from_name=True) == 'TWRM'
    with pytest.raises(ValueError):
        resolve_layout('avocadoecobase', 'MPE_HJ002-bed')


def test_every_member_alias_preserves_name_manual_and_scan_boundaries():
    from custom_components.adjustable_bed.richmat_classic_discovery import matching_apps

    cases = json.loads((Path(__file__).parent / "fixtures/richmat_classic/alias_cases.json").read_text())
    assert len(cases) == 122
    for case in cases:
        assert resolve_layout(case["app"], case["alias"], from_name=True) == case["target"], case
        assert (case["app"] in matching_apps(case["alias"])) == case["scan_admitted"], case
        if case["manual"]:
            assert resolve_layout(case["app"], " " + case["alias"].lower() + " ") == case["target"], case
        else:
            with pytest.raises(ValueError, match="four"):
                resolve_layout(case["app"], case["alias"])


def test_options_validate_member_specific_layout_before_mutation():
    exclusive = min(set(_layouts('fortywinks')) - set(_layouts('milemont')) - {"ZRS6:CORN", "ZRS6:CPRN"})
    assert exclusive in _layouts('fortywinks') and exclusive not in _layouts('milemont')
    with pytest.raises(ValueError):
        _setup({'protocol_variant': 'milemont', 'product_type': exclusive})
    assert _setup({'protocol_variant': 'avocadoecobase', 'product_type': '6BRM'})['product_type'] == '6BRM'


@pytest.mark.parametrize("app", ("fortywinks", "superior"))
@pytest.mark.parametrize("layout", ("CORN", "CPRN"))
def test_zrs6_picker_choices_select_actual_member_local_layouts(app, layout):
    assert "ZRS6:" + layout in _layouts(app) and "ZRS6" not in _layouts(app)
    selected = _setup({"protocol_variant": app, "product_type": "ZRS6:" + layout})
    assert selected["product_type"] == layout
    assert layout in load_catalog(app).models
    with pytest.raises(ValueError):
        _setup({"protocol_variant": app, "product_type": "ZRS6"})


@pytest.mark.parametrize("app", ("avocadoecobase", "coastersleep", "milemont"))
def test_zrs6_picker_is_not_added_to_other_member_apps(app):
    assert "ZRS6:CORN" not in _layouts(app)
    with pytest.raises(ValueError):
        _setup({"protocol_variant": app, "product_type": "ZRS6:CORN"})


def test_manual_aliases_are_selectable_but_diagnostic_layouts_are_rejected():
    assert "B6RU" in _layouts("avocadoecobase")
    assert _setup({"protocol_variant": "avocadoecobase", "product_type": " b6ru "})["product_type"] == "B6RM"
    for layout in ("TEST", "RMCS"):
        assert layout not in _layouts("avocadoecobase")
        with pytest.raises(ValueError):
            _setup({"protocol_variant": "avocadoecobase", "product_type": layout})


def test_name_admission_is_only_an_app_hint_and_excludes_diagnostic_names():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.richmat_classic_discovery import matching_apps
    assert matching_apps('6BRM-123') == tuple(APP_NAMES)
    assert matching_apps(' B6RU') == ()
    assert matching_apps(None) == ()
    raw = SimpleNamespace(name='6BRM-123',service_uuids=[],manufacturer_data={},address='AA:BB:CC:DD:EE:FF')
    found = detect_bed_type_detailed(raw)
    assert found.bed_type == 'richmat'
    assert 'richmat_classic_apps' in found.ambiguous_types
    raw.name = 'Test Device'
    assert detect_bed_type_detailed(raw).bed_type is None


@pytest.mark.parametrize("app", tuple(APP_NAMES))
def test_app_hint_preserves_explicit_member_selection(app):
    from custom_components.adjustable_bed.const import (
        BED_TYPE_RICHMAT_CLASSIC_APPS,
        CONF_BED_TYPE,
        CONF_PROTOCOL_VARIANT,
    )
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    advert = SimpleNamespace(
        address="AA:BB:CC:DD:EE:66",
        name="QRRM157738",
        service_uuids=["0000fee9-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={19543: bytes.fromhex("54307651")},
        service_data={},
    )
    assert BED_TYPE_RICHMAT_CLASSIC_APPS in (detect_bed_type_detailed(advert).ambiguous_types or ())
    assert recommend_profile(
        {CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS, CONF_PROTOCOL_VARIANT: app}, advert, {}
    ) is None


async def test_manual_setup_asks_the_chosen_apps_layout_on_the_generic_step(hass):
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISCONNECT_AFTER_COMMAND,
        CONF_PRODUCT_TYPE,
        CONF_PROTOCOL_VARIANT,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow._selected_bed_type, flow._selected_protocol_variant = BED_TYPE_RICHMAT_CLASSIC_APPS, "fortywinks"
    result = await flow.async_step_manual_entry({CONF_ADDRESS: "AA:BB:CC:DD:EE:18"})
    assert result["step_id"] == "profile_questions"
    assert result["description_placeholders"] == {"profile": "Forty Winks"}
    # Forty Winks ships every other app's layouts, so a diagnostic one is the refusal.
    invalid = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: "TEST"})
    assert invalid["errors"] == {CONF_PRODUCT_TYPE: "richmat_classic_layout"}
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: "ZRS6:CORN"})
        assert result["step_id"] == "finish_settings"
        result = await flow.async_step_finish_settings(
            {CONF_NAME: "Classic bed", CONF_DISCONNECT_AFTER_COMMAND: False}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert (data[CONF_BED_TYPE], data[CONF_PROTOCOL_VARIANT], data[CONF_PRODUCT_TYPE]) == (
        BED_TYPE_RICHMAT_CLASSIC_APPS, "fortywinks", "CORN",
    )
    assert (data[CONF_MOTOR_COUNT], data[CONF_HAS_MASSAGE], data[CONF_DISABLE_ANGLE_SENSING]) == (
        2, False, True,
    )
    assert data[CONF_RICHMAT_CLASSIC_THIRD_SERVICE] is False
    from custom_components.adjustable_bed.profile_id import resolve_profile_id

    assert resolve_profile_id(data) == f"{BED_TYPE_RICHMAT_CLASSIC_APPS}:fortywinks"


async def test_configure_rejects_another_apps_layout_and_saves_the_fallback(hass):
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_PRODUCT_TYPE,
        CONF_PROTOCOL_VARIANT,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:18",
            CONF_BED_TYPE: BED_TYPE_RICHMAT_CLASSIC_APPS,
            CONF_PROTOCOL_VARIANT: "milemont",
            CONF_PRODUCT_TYPE: "6BRM",
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    form = await flow.async_step_settings()
    shown = {str(key) for key in form["data_schema"].schema}
    assert {CONF_PRODUCT_TYPE, CONF_RICHMAT_CLASSIC_THIRD_SERVICE} <= shown
    assert not {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING} & shown
    exclusive = min(set(_layouts("fortywinks")) - set(_layouts("milemont")) - {"ZRS6:CORN", "ZRS6:CPRN"})
    result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "milemont", CONF_PRODUCT_TYPE: exclusive})
    assert result["errors"]
    result = await flow.async_step_settings(
        {CONF_PRODUCT_TYPE: "B6RU", CONF_RICHMAT_CLASSIC_THIRD_SERVICE: True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PRODUCT_TYPE] == "B6RM"
    assert entry.data[CONF_RICHMAT_CLASSIC_THIRD_SERVICE] is True
