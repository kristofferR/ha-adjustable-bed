"""Tests for unsupported-device helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.unsupported import (
    UnsupportedDeviceInfo,
    async_clear_unsupported_device_issues,
    build_misidentified_issue_url,
)


async def test_clear_unsupported_device_issues(hass: HomeAssistant) -> None:
    """Cleanup removes obsolete unsupported-device issues, leaving others alone."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "unsupported_device_abxm2",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="unsupported_device",
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        "unsupported_device_d1_28_41_53_59_9d",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="unsupported_device",
    )
    # An unrelated issue that must survive the cleanup.
    ir.async_create_issue(
        hass,
        DOMAIN,
        "pairing_required_aa_bb_cc_dd_ee_ff",
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="pairing_required",
    )

    registry = ir.async_get(hass)
    assert len(registry.issues) == 3

    async_clear_unsupported_device_issues(hass)

    remaining = {issue_id for (domain, issue_id) in registry.issues if domain == DOMAIN}
    assert remaining == {"pairing_required_aa_bb_cc_dd_ee_ff"}


def test_misidentified_details_rounds_confidence() -> None:
    """Misidentified-device issue details should round confidence percentages."""
    device_info = UnsupportedDeviceInfo(
        address="AA:BB:CC:DD:EE:FF",
        name="Wrong Device",
        service_uuids=[],
        manufacturer_data={},
    )

    details = device_info.to_misidentified_details(
        detected_bed_type="richmat",
        confidence=0.956,
        signals=["name matched QRRM"],
        integration_version="3.1.0",
        ha_version="2026.7.1",
    )

    assert "confidence 96%" in details
    assert "| Confidence | 96% |" in details
    assert "| Integration version | `3.1.0` |" in details
    assert "| Home Assistant | `2026.7.1` |" in details


def test_misidentified_details_without_versions() -> None:
    """Version rows fall back to "unknown" when versions are not provided."""
    device_info = UnsupportedDeviceInfo(
        address="AA:BB:CC:DD:EE:FF",
        name=None,
        service_uuids=[],
        manufacturer_data={},
    )

    details = device_info.to_misidentified_details(
        detected_bed_type="richmat",
        confidence=0.8,
        signals=[],
    )

    assert "| Integration version | `unknown` |" in details
    assert "| Home Assistant | `unknown` |" in details


def test_misidentified_report_never_publishes_the_device_identity() -> None:
    """The public issue has a neutral title and only the address prefix (PRIV-7)."""
    device_info = UnsupportedDeviceInfo(
        address="AA:BB:CC:DD:EE:FF",
        name="Anna's phone",
        service_uuids=[],
        manufacturer_data={0x004C: bytes.fromhex("0102ffeedd")},
    )

    url = build_misidentified_issue_url(device_info, "richmat", 0.8, ["name"])
    query = parse_qs(urlparse(url).query)

    assert query["title"] == ["[Misidentified] Detected as richmat"]
    details = query["details"][0]
    assert "AA:BB:CC:**:**:**" in details
    assert "DD:EE:FF" not in details
