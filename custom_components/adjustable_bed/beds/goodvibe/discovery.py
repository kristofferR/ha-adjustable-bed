"""Exact Good Vibe Sleep name filter and aliases, without transport-based model guesses."""

from __future__ import annotations

from .catalog import PRODUCTS

KEYWORDS = (
    "QRRM",
    "MlRM",
    "COOL",
    "Cool",
    "MPE_",
    "209A05",
    "208A14",
    "200U",
    "FC200",
    "200I",
    "200i",
    "400I",
    "400i",
    "800I",
    "800i",
    "L&P-",
    "L&P ",
    "BED-",
    "UaRM",
)
ALIASES = {
    "B6RU": "B6RM",
    "ZR90": "S9RM",
    "200I": "A8RM",
    "208A": "A8RM",
    "FC20": "A8RM",
    "400I": "A0RM",
    "200U": "A0RM",
    "800I": "A1RM",
    "L&P-": "ZRS3",
    "L&P ": "ZRS3",
    "BRRM": "YGRM",
}


def scan_matches(name: str | None) -> bool:
    return name is not None and (
        name.startswith(("RM-", "HJ-"))
        or any(
            key in name
            for key in (
                *KEYWORDS,
                *(
                    p.label
                    for p in PRODUCTS.values()
                    if "/" not in p.label and p.label != "None (fallback)"
                ),
            )
        )
    )


def name_product(name: str | None, *, russian: bool = False) -> str:
    if name is None:
        return ""
    if len(name) < 4 or name[:4].upper() == "MPE_" and len(name) < 9:
        raise ValueError("Advertisement name is too short for the shipped selector")
    prefix = name[:4].upper()
    if prefix in ALIASES:
        return ALIASES[prefix]
    if prefix == "MPE_":
        return {
            "MPE_HJ002": "TWRM",
            "MPE_HJ003": "WPRM",
            "MPE_HJ005": "WPRM",
            "MPE_HJ006": "BNRM",
            "MPE_HJ008": "BLRM",
        }.get(name[:9].upper(), "ZRA2")
    return "O0RM" if prefix == "OTRM" and russian else prefix


def suggested_profile(name: str | None, *, russian: bool = False) -> str | None:
    """Offer the shipped app's mapping as a hint; setup still requires an app choice."""
    if name is not None and name.startswith("RM-"):
        return "sleep_rm"
    if name is not None and name.startswith("HJ-"):
        return "sleep_hj"
    try:
        model = name_product(name, russian=russian)
    except ValueError:
        return None
    return next(
        (key for key, product in PRODUCTS.items() if "/" not in key and product.label == model),
        None,
    )
