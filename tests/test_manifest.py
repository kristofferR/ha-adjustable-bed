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
