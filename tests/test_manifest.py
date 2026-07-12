"""Tests for integration manifest discovery hints."""

from __future__ import annotations

import json
from pathlib import Path


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
