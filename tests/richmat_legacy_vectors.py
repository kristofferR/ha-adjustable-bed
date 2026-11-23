"""Accepted Richmat NU503/Silver app data, adapted to production codec and action phases."""

import gzip
import json
import re
from pathlib import Path

ACCEPTED = json.loads(
    gzip.decompress(
        (Path(__file__).parent / "fixtures/richmat_legacy/accepted.json.gz").read_bytes()
    )
)


def literal_frames(member):
    rows = ACCEPTED[member]["literal"]
    return {
        row["inputs"].get("text", row["inputs"].get("literal")): row["expected_bytes"]
        for row in rows
        if member == "silver" or row["inputs"]["mode"] == "literal"
    }


# Frame sets come from frozen expectations and accepted phase DATA, never the
# current production catalog. A changed catalog cannot bless its own new byte.
FROZEN_FRAMES: dict[str, frozenset[str]] = {}
for app, member in (("sleep_evolution", "nu503"), ("wsilver_legacy", "silver")):
    literal = literal_frames(member)
    gathered: dict[str, set[str]] = {}
    for row in ACCEPTED[member]["commands"]:
        code = "BE" if row["profile"] == "BE_massage" else row["profile"]
        values = re.findall(r'sendMessage\("(.)"\)', row["down"] + row["release"])
        for branch in row["branches"].values():
            values.extend(branch.get("strings", branch.get("sends", [])))
        gathered.setdefault(f"{app}:{code}", set()).update(literal[v] for v in values)
    FROZEN_FRAMES.update((key, frozenset(values)) for key, values in gathered.items())
