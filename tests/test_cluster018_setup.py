"""Explicit app/model selection and narrow advertisement hints."""

import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import voluptuous as vol

from custom_components.adjustable_bed.cluster018_models import MODEL_CHOICES
from custom_components.adjustable_bed.cluster018_profiles import (
    APP_NAMES,
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.config_flow import (
    _add_cluster018_schema_fields,
    _normalize_cluster018_data,
)
from custom_components.adjustable_bed.detection import get_bed_type_options


def test_all_five_app_choices_are_findable_and_model_inventories_are_distinct():
    choices = get_bed_type_options()
    for app, name in APP_NAMES.items():
        assert any(o['value'] == 'richmat_classic_apps:' + app and name in o['label'] for o in choices)
    assert {app: len(models) for app, models in MODEL_CHOICES.items()} == {
        'avocadoecobase': 704, 'coastersleep': 715, 'fortywinks': 725, 'milemont': 700, 'superior': 725,
    }
    for app, models in MODEL_CHOICES.items():
        assert set(models) == set(load_catalog(app)['models'])


def test_runtime_catalog_matches_every_frozen_member_layout_contract():
    """Expected digests come from accepted CP/MS records, before runtime import."""
    path = Path(__file__).parent / "fixtures/cluster018/catalog_contracts.json.gz"
    with gzip.open(path, "rt") as source:
        expected = json.load(source)
    assert len(expected["models"]) == 3569
    for row in expected["models"]:
        catalog = load_catalog(row["app"])
        assert catalog["fields"] == expected["fields"]
        encoded = json.dumps(catalog["models"][row["layout"]], separators=(",", ":"), sort_keys=True).encode()
        assert hashlib.sha256(encoded).hexdigest() == row["sha256"], row


def test_explicit_layout_is_required_and_aliases_are_package_local():
    with pytest.raises(ValueError):
        _normalize_cluster018_data({'protocol_variant': 'avocadoecobase'})
    assert resolve_layout('avocadoecobase', ' B6RU ') == 'B6RM'
    assert resolve_layout('avocadoecobase', 'OTRM', russian=True) == 'O0RM'
    assert resolve_layout('avocadoecobase', 'MPE_HJ002-bed', from_name=True) == 'TWRM'
    with pytest.raises(ValueError):
        resolve_layout('avocadoecobase', 'MPE_HJ002-bed')


def test_every_member_alias_preserves_name_manual_and_scan_boundaries():
    from custom_components.adjustable_bed.cluster018_discovery import matching_apps

    cases = json.loads((Path(__file__).parent / "fixtures/cluster018/alias_cases.json").read_text())
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
    exclusive = next(iter(set(MODEL_CHOICES['fortywinks']) - set(MODEL_CHOICES['milemont'])))
    with pytest.raises(ValueError):
        _normalize_cluster018_data({'protocol_variant': 'milemont', 'product_type': exclusive})
    data = {'protocol_variant': 'avocadoecobase', 'product_type': '6BRM'}
    schema = {}
    _add_cluster018_schema_fields(schema, data)
    assert vol.Schema(schema)(data)['product_type'] == '6BRM'


@pytest.mark.parametrize("app", ("fortywinks", "superior"))
@pytest.mark.parametrize("layout", ("CORN", "CPRN"))
def test_zrs6_picker_choices_select_actual_member_local_layouts(app, layout):
    data = {"protocol_variant": app, "product_type": "ZRS6:" + layout}
    schema = {}
    _add_cluster018_schema_fields(schema, data)
    selected = vol.Schema(schema)(data)
    _normalize_cluster018_data(selected)
    assert selected["product_type"] == layout
    assert layout in load_catalog(app)["models"]
    with pytest.raises(ValueError):
        _normalize_cluster018_data({"protocol_variant": app, "product_type": "ZRS6"})


@pytest.mark.parametrize("app", ("avocadoecobase", "coastersleep", "milemont"))
def test_zrs6_picker_is_not_added_to_other_member_apps(app):
    with pytest.raises(ValueError):
        _normalize_cluster018_data({"protocol_variant": app, "product_type": "ZRS6:CORN"})


def test_manual_aliases_are_selectable_but_diagnostic_layouts_are_rejected():
    data = {"protocol_variant": "avocadoecobase", "product_type": "B6RU"}
    schema = {}
    _add_cluster018_schema_fields(schema, data)
    _normalize_cluster018_data(vol.Schema(schema)(data))
    _normalize_cluster018_data(data)
    assert data["product_type"] == "B6RM"
    for layout in ("TEST", "RMCS"):
        with pytest.raises(ValueError):
            _normalize_cluster018_data({"protocol_variant": "avocadoecobase", "product_type": layout})


def test_name_admission_is_only_an_app_hint_and_excludes_diagnostic_names():
    from custom_components.adjustable_bed.cluster018_discovery import matching_apps
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    assert matching_apps('6BRM-123') == tuple(APP_NAMES)
    assert matching_apps(' B6RU') == ()
    assert matching_apps(None) == ()
    raw = SimpleNamespace(name='6BRM-123',service_uuids=[],manufacturer_data={},address='AA:BB:CC:DD:EE:FF')
    found = detect_bed_type_detailed(raw)
    assert found.bed_type == 'richmat'
    assert 'richmat_classic_apps' in found.ambiguous_types
    raw.name = 'Test Device'
    assert detect_bed_type_detailed(raw).bed_type is None
