"""Tests for integration manifest discovery hints."""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from homeassistant.components.bluetooth.match import IntegrationMatcher


def test_manifest_discovers_motosleep_names_in_both_cases() -> None:
    """Name-only MotoSleep advertisements must reach normalized routing."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    local_names = {
        entry["local_name"] for entry in manifest["bluetooth"] if "local_name" in entry
    }
    assert {"HHC*", "hhc*", "MOTOB*", "motob*", "MOTOS*", "motos*"} <= local_names


def test_manifest_bluetooth_matchers_are_accepted_by_home_assistant() -> None:
    """Every discovery hint must be safe to load into the Bluetooth index."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    IntegrationMatcher(manifest["bluetooth"]).async_setup()


def test_manifest_discovers_supported_prefixed_qms2_name() -> None:
    """The detector-supported prefixed name must pass the discovery gate."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert any(
        fnmatchcase("My QMS2 Base", entry["local_name"])
        for entry in manifest["bluetooth"]
        if "local_name" in entry
    )


def test_manifest_discovers_okin_receiver_name_only_advertisements() -> None:
    """Name-only OKIN receiver advertisements must start the Bluetooth flow."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert {
        "OKIN*Receiver*",
        "OKIN*receiver*",
        "Okin*Receiver*",
        "Okin*receiver*",
        "okin*Receiver*",
        "okin*receiver*",
    }.issubset(
        {entry["local_name"] for entry in manifest["bluetooth"] if "local_name" in entry}
    )


def test_manifest_discovers_leggett_gen2_manufacturer_advertisements() -> None:
    """LP Comfort Connect (Gen2) advertises no service UUID, so discovery must
    match on manufacturer id 0x092D + "XP"/"CP" prefix (issue #385 review)."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    starts = {
        tuple(entry["manufacturer_data_start"])
        for entry in manifest["bluetooth"]
        if entry.get("manufacturer_id") == 0x092D and "manufacturer_data_start" in entry
    }
    assert (88, 80) in starts  # "XP"
    assert (67, 80) in starts  # "CP"


def test_manifest_discovers_adjustable_lite_name_only_advertisements() -> None:
    """Adjustable Lite scans by name alone, with no advertised service filter."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patterns = [entry["local_name"] for entry in manifest["bluetooth"] if "local_name" in entry]

    for name in ("KSBT01C000015046", "KSBT03C000015046"):
        assert any(fnmatchcase(name, pattern) for pattern in patterns)


def test_manifest_discovers_restonic_bt_name_only_advertisements() -> None:
    """Restonic BT accepts case-sensitive base-i4/base-i5 names with no service filter."""
    manifest_path = (
        Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patterns = [entry["local_name"] for entry in manifest["bluetooth"] if "local_name" in entry]

    for name in ("base-i4.00002574", "base-i4X0001", "base-i4", "base-i5.00000682"):
        assert any(fnmatchcase(name, pattern) for pattern in patterns)
    assert not any(fnmatchcase("BASE-I4.00002574", pattern) for pattern in patterns)


def test_pairlink_company_key_reaches_host_matcher_without_claiming_protocol() -> None:
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    manifest_path = Path(__file__).parents[1] / "custom_components/adjustable_bed/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    matcher = IntegrationMatcher([{"domain": DOMAIN, **entry} for entry in manifest["bluetooth"]])
    matcher.async_setup()
    raw = bytes.fromhex("B905C0000178563412900243AABBCCDDEEFF")
    company = int.from_bytes(raw[:2], "little")
    info = _make_service_info(
        name="Unknown", service_uuids=[], manufacturer_data={company: raw[2:]},
    )
    assert DOMAIN in matcher.match_domains(info)
    # A generic SDK manufacturer record does not establish a bed protocol.
    assert detect_bed_type_detailed(info).bed_type is None


def test_eshine_uart_advertisements_reach_discovery_without_product_inference() -> None:
    from custom_components.adjustable_bed.beds.eshine_okin_protocol import SERVICE_UUID
    from custom_components.adjustable_bed.const import BED_TYPE_ESHINE_OKIN, DOMAIN
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    manifest_path = Path(__file__).parents[1] / "custom_components/adjustable_bed/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    matcher = IntegrationMatcher([{"domain": DOMAIN, **entry} for entry in manifest["bluetooth"]])
    matcher.async_setup()
    for name in ("Smartbed", "prefix Smartbed suffix"):
        info = _make_service_info(name=name, service_uuids=[SERVICE_UUID])
        info.connectable = True
        assert DOMAIN in matcher.match_domains(info)
        detected = detect_bed_type_detailed(info)
        assert BED_TYPE_ESHINE_OKIN in [detected.bed_type, *(detected.ambiguous_types or ())]
        assert not any("eshine_e" in signal for signal in detected.signals)


@pytest.mark.parametrize(
    ("name", "services"),
    [
        ("SOFA000001SC00M", []),
        ("BT2010000", []),
        ("MOTO00000100000", []),
        ("xSOFA00001SC00M", ["0000ffe0-0000-1000-8000-00805f9b34fb"]),
        ("xBT201000", ["0000fff0-0000-1000-8000-00805f9b34fb"]),
        ("xMOTO0000100000", ["0000ffe0-0000-1000-8000-00805f9b34fb"]),
    ],
)
def test_motomotion_host_hints_preserve_explicit_app_choice(name, services) -> None:
    from custom_components.adjustable_bed.const import BED_TYPE_MOTOMOTION, DOMAIN
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    manifest = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/manifest.json").read_text()
    )
    matcher = IntegrationMatcher([{"domain": DOMAIN, **entry} for entry in manifest["bluetooth"]])
    matcher.async_setup()
    info = _make_service_info(name=name, service_uuids=services)
    info.connectable = True
    assert DOMAIN in matcher.match_domains(info)
    detected = detect_bed_type_detailed(info)
    assert BED_TYPE_MOTOMOTION in [detected.bed_type, *(detected.ambiguous_types or ())]
    assert "name:motomotion_app_candidate" in detected.signals
