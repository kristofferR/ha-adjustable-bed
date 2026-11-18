"""The app catalog is discovery vocabulary, never a physical capability table."""

import json
from pathlib import Path
from typing import Final

from ...profiles.luniosmart import KEYWORDS

ALIASES: Final = json.loads(Path(__file__).with_name("aliases.json").read_text())
SCAN_CODES: Final = tuple(row["code"] for row in ALIASES if row["eligible"])


def matches(name: str) -> bool:
    return any(keyword in name for keyword in (*KEYWORDS, *SCAN_CODES))
