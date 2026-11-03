"""Bed guides in docs/beds keep the reference layout described in docs/BED_GUIDE_FORMAT.md.

Guides drifted into audit prose once nothing checked them. This only checks the skeleton a reader
scans first; the body below it is free to vary per protocol.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BEDS = Path(__file__).resolve().parents[1] / "docs" / "beds"

# Discovery ledgers (*-disposition.md) and the Sleep Number action reference are other doc types.
_NOT_GUIDES = {"sleep-number-services.md"}

GUIDES = sorted(
    p
    for p in BEDS.glob("*.md")
    if not p.name.endswith("-disposition.md") and p.name not in _NOT_GUIDES
)

_REQUIRED = {
    "status line": re.compile(r"^\*\*Status:\*\* (✅|❓|⚠️)", re.M),
    "credit line": re.compile(r"^\*\*Credit:\*\* ", re.M),
    "Known Models section": re.compile(r"^## Known (Models|Brands|Controllers)\b", re.M),
    "Apps table": re.compile(r"^## Apps\s*$(?:(?!^## ).)*?^\| ", re.M | re.S),
    "Features table": re.compile(r"^## Features\s*$(?:(?!^## ).)*?^\| Feature \|", re.M | re.S),
}


@pytest.mark.parametrize("guide", GUIDES, ids=lambda p: p.name)
def test_bed_guide_keeps_reference_layout(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    missing = [name for name, pattern in _REQUIRED.items() if not pattern.search(text)]
    assert not missing, f"{guide.name} lacks {', '.join(missing)}; see docs/BED_GUIDE_FORMAT.md"
