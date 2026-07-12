"""Tests for unsupported-device helpers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.unsupported import (
    UnsupportedDeviceInfo,
    async_clear_unsupported_device_issues,
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
