"""Explicit app identities for the RUF, W.Silver, AMERICANSTAR, Bailey and TX remotes."""

from __future__ import annotations

import gzip
import json
from functools import cache
from pathlib import Path
from typing import TypedDict, cast

APPS = {
    "ruf_betten": "ruf",
    "wsilver_products": "wsilver2",
    "richmat_americanstar": "americanstar",
    "bailey_bed_control": "bailey2",
    "richmat_tx": "tx",
}
DISPLAY_NAMES = {
    "ruf_betten": "RUF | Betten (Motor 2)",
    "wsilver_products": "W.Silver Products",
    "richmat_americanstar": "AMERICANSTAR (Richmat app)",
    "bailey_bed_control": "Bailey's Bed Control",
    "richmat_tx": "TX (Richmat app)",
}

type ControlRow = tuple[str, str, str, str, str, int, int]
type Field = str | int | bool | None | list[Field] | dict[str, Field]


class Profile(TypedDict):
    controls: list[ControlRow]
    fields: dict[str, Field]


@cache
def profiles(app: str) -> dict[str, Profile]:
    """Load only the explicitly selected app's compact, artifact-derived catalog."""
    if app not in APPS.values():
        raise ValueError(f"Unknown app: {app}")
    path = Path(__file__).with_name("row061_data") / f"{app}.json.gz"
    return cast(dict[str, Profile], json.loads(gzip.decompress(path.read_bytes())))


def fields(app: str, model: str) -> dict[str, Field]:
    return profiles(app)[model]["fields"]
