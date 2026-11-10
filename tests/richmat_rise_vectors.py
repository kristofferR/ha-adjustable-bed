"""Frozen literal frames from the two accepted cluster-021 member reports."""

import gzip
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures/richmat_rise"

# Accepted direct timer domain: Luuna P2 D1RM/D9RM seekbar commands and
# Power Cool SPECIAL_COMMANDS.json massage timer sliders. These three values
# are parameterized there rather than repeated in the original 417/22 samples.
_TIMER_FRAMES = frozenset({"6e01000170", "6e01000473", "6e01008bfa"})


def records(app: str, domain: str) -> list[dict]:
    with gzip.open(FIXTURES / f"{app}_{domain}.json.gz", "rt") as source:
        return json.load(source)


def _frames(app: str) -> frozenset[str]:
    frames = set(_TIMER_FRAMES)
    for row in records(app, "commands"):
        values = row["bytes"].values() if isinstance(row["bytes"], dict) else (row["bytes"],)
        frames.update(value.lower() for value in values)
    for row in records(app, "vectors"):
        value = row["expected_bytes"].lower().replace(" ", "")
        if len(value) > 2 and not value.startswith("6e"):
            continue  # RMCS is tested by its separate unchecksummed builder.
        if len(value) > 10 and len(value) % 10 == 0:
            frames.update(value[i:i + 10] for i in range(0, len(value), 10))
        else:
            frames.add(value)
    return frozenset(frames)


FROZEN_FRAMES = {f"richmat_classic_{app}": _frames(app) for app in ("luunarise2", "powercool")}
