"""Richmat 4.2.0's individual products and class-indexed controls (row173).

The compact catalog preserves product identity and both protocol branches.
Equal selector values do not merge products. No advertisement selects a product.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import TypedDict, cast


class Action(TypedDict):
    enum: str
    short: int
    base_short: int
    long: int
    operation: str
    maximum: int
    massage_max: int
    save: bool
    light: bool


class Version(TypedDict):
    motors: list[list[str | int | bool]]
    presets: list[list[str | bool]]


class Product(TypedDict):
    selectors: dict[str, object]
    manual: bool
    side: int
    swap: bool
    fan: bool
    light_board: bool
    therapy: dict[str, object]
    palette: list[str] | None
    versions: dict[str, Version]
    massage_sliders: dict[str, object]
    labels: dict[str, str]


class Catalog(TypedDict):
    actions: dict[str, Action]
    products: dict[str, Product]
    labels: dict[str, str]
    colors: dict[str, list[int]]
    enum_codes: dict[str, int]


_CATALOG = cast(
    Catalog, json.loads(gzip.decompress(Path(__file__).with_name("catalog.json.gz").read_bytes()))
)
ACTIONS = _CATALOG["actions"]
PRODUCTS = _CATALOG["products"]
LABELS = _CATALOG["labels"]
ENUM_CODES = _CATALOG["enum_codes"]
COLORS = _CATALOG["colors"]
PALETTE = tuple(
    tuple(COLORS[key])
    for key in ("ccbfd1", "ccdbf1", "ccb971", "ccdbc1", "ccdb91", "ccae31", "ccb9d1", "ccb9a1")
)
FOUR_COLORS = tuple(tuple(COLORS[key]) for key in ("ccb9d1", "ccb9a1", "ccb971", "ccae31"))
GROOVE_PALETTE = tuple(
    tuple(COLORS[key])
    for key in ("ccb9d1", "ccb9a1", "ccbfd1", "ccdbf1", "ccb971", "ccdbc1", "ccdb91", "ccae31")
)
PROFILE_CHOICES = {key: key for key, row in PRODUCTS.items() if row["manual"]}
RESTORED_CHOICES = {
    key: key + " (restored product)" for key, row in PRODUCTS.items() if not row["manual"]
}
ALL_CHOICES = {**PROFILE_CHOICES, **RESTORED_CHOICES}
SCAN_KEYWORDS = (
    "QRRM",
    "COOL",
    "MPE_",
    "209A05",
    "208A14",
    "200U",
    "FC200",
    "200I",
    "400I",
    "800I",
    "L&P-",
    "L&P ",
    "Luffabenz",
    *PROFILE_CHOICES,
)


def scan_matches(name: str | None) -> bool:
    return name is not None and any(keyword in name for keyword in SCAN_KEYWORDS)


def normalize_product(value: str) -> str:
    """The app's QR/manual normalization, deliberately not general whitespace trim."""
    return value.upper().replace("\n", "").replace(" ", "")


def descriptors(product: Product, selector: str) -> tuple[str, ...]:
    """Flatten actual nested groups without inventing controls from enum names."""
    result: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, list):
            for child in value:
                add(child)
        elif isinstance(value, str) and value.startswith("RMDeviceFunctionItemDetialsType@"):
            result.append(value.split("@", 1)[1])

    add(product["selectors"][selector])
    return tuple(result)
