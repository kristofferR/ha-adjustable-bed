"""Frozen BedTech 7.1.3 (14) vectors and all 585 model/action/side routes.

Accepted unit095 report manifest d196849c2c9463ac6bbd929eea3070d0e8f234aa511362284508a9c9cdc945fd.
Static artifact evidence only; no claim of hardware validation.
"""

import json
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures"
VECTORS = json.loads((_FIXTURES / "bedtech_vectors.json").read_text())
ROUTES = json.loads((_FIXTURES / "bedtech_routing.json").read_text())
_BY_COMMAND = {row["command"]: row["hex"].lower() for row in VECTORS}
FROZEN_FRAMES = {
    f"bedtech_{model.lower()}": frozenset(
        _BY_COMMAND[command]
        for row in ROUTES
        if row["model"] == model
        for command in row["commands"]
        if command
    )
    for model in sorted({row["model"] for row in ROUTES})
}
ALL_FRAMES = frozenset(row["hex"].lower() for row in VECTORS if row["hex"] != "NO_WRITE")
