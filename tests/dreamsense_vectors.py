"""Accepted Dream Sense literals, distinct from the production catalog."""

import json
from pathlib import Path

from custom_components.adjustable_bed.profiles.dreamsense import PROFILES

ROOT = Path(__file__).parent / "fixtures/dreamsense"
VECTORS = json.loads((ROOT / "vectors.json").read_text())
CATALOG = json.loads((ROOT / "catalog.json").read_text())
GATT = json.loads((ROOT / "gatt-layouts.json").read_text())
FRAMES = (
    frozenset(
        value.replace(" ", "")
        for row in VECTORS
        if not row["id"].startswith("excluded-")
        for literal in row["expected_bytes"].split("|")
        for value in (
            [literal[:14], literal[15:]] if len(literal.strip().split()) == 10 else [literal]
        )
    )
    | frozenset(row[5] for row in CATALOG)
    | frozenset(row[6] for row in CATALOG)
)
# Authoritative startup, unconditional raw probes and scoped correction literals.
FRAMES |= frozenset({"00", "01", "75", "d6", "6e010075e4", "6e0100d645"})
FROZEN_FRAMES = {p.key: FRAMES for p in PROFILES.values()}
