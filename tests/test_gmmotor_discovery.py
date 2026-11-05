"""GM Control's distinct scan admission, name alias and final product selection."""

from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.gmmotor_discovery import (
    resolve_selection,
    scan_name_matches,
    selector_from_name,
)


def test_app_discovery_offers_explicit_choice_and_preserves_existing_receiver():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    raw = SimpleNamespace(
        name="6BRM-123", service_uuids=[], manufacturer_data={}, address="AA:BB:CC:DD:EE:FF"
    )
    result = detect_bed_type_detailed(raw)
    assert result.bed_type == "richmat" and "gmmotor" in result.ambiguous_types
    raw.name = "prefix6BRM"
    result = detect_bed_type_detailed(raw)
    assert result.bed_type == "gmmotor" and result.confidence < 0.7
    raw.name = "RM-sensor"
    result = detect_bed_type_detailed(raw)
    assert result.bed_type == "casper_sleep_mm"
    assert "gmmotor_sleep_mm" in result.ambiguous_types
    assert "gmmotor_sleep_sxb" in result.ambiguous_types


@pytest.mark.parametrize(
    ("bed_type", "name"),
    [
        ("gmmotor", "6BRM-123"),
        ("gmmotor_sleep_mm", "RM-sensor"),
        ("gmmotor_sleep_sxb", "HJ-sensor"),
    ],
)
def test_confirmed_companion_app_is_not_replaced_by_a_shared_receiver_name(bed_type, name):
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile

    raw = SimpleNamespace(
        name=name, service_uuids=[], manufacturer_data={}, address="AA:BB:CC:DD:EE:FF"
    )
    assert recommend_profile({"bed_type": bed_type, "product_type": "6BRM"}, raw, {}) is None


def test_scan_filter_remains_case_sensitive_substring() -> None:
    assert scan_name_matches("prefix-MlRM-bed")
    assert not scan_name_matches("prefix-mlrm-bed")
    assert scan_name_matches("BED-unknown")
    assert scan_name_matches("X6BRM123")
    assert not scan_name_matches("unknown")


@pytest.mark.parametrize(
    ("name", "selector"),
    [
        ("B6RU123", "B6RM"),
        ("FC200", "A8RM"),
        ("208A05", "A8RM"),
        ("MPE_HJ001", "ZRA2"),
        ("MPE_HJ002", "TWRM"),
        ("MPE_HJ008", "BLRM"),
        ("MPE_other", "ZRA2"),
        ("L&P-bed", "ZRS3"),
        ("BRRM", "YGRM"),
        ("MlRM", "MLRM"),
    ],
)
def test_exact_name_aliases(name: str, selector: str) -> None:
    assert selector_from_name(name) == selector


def test_locale_branch_and_safe_range_failure() -> None:
    assert selector_from_name("OTRM") == "OTRM"
    assert selector_from_name("OTRM", russian=True) == "O0RM"
    assert selector_from_name("MPE_") == ""  # HA safe handling; artifact substring throws.
    assert selector_from_name("x") == ""
    assert selector_from_name("unknown") == "UNKN"
    assert resolve_selection("UNKN") == ""


def test_remote_and_barcode_choices_are_explicit() -> None:
    with pytest.raises(ValueError):
        resolve_selection("ZRS3")
    assert resolve_selection("ZRS3", "APRM") == "APRM"
    with pytest.raises(ValueError):
        resolve_selection("ZRS3", "6BRM")
    assert resolve_selection("MHRN", "HQRN") == "HQRN"
    assert resolve_selection("MHRN", "HNRN") == "HNRN"
    with pytest.raises(ValueError):
        resolve_selection("QRRM")
    assert resolve_selection("QRRM", "6BRM") == "6BRM"
    assert resolve_selection("QRRM", "6brm") == "6BRM"
    assert resolve_selection("QLRN") == ""  # Compiled but unsupported in this app.
