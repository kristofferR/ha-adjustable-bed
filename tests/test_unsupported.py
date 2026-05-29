"""Tests for unsupported-device helpers."""

from __future__ import annotations

from custom_components.adjustable_bed.unsupported import UnsupportedDeviceInfo


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
    )

    assert "confidence 96%" in details
    assert "| Confidence | 96% |" in details
