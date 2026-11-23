"""Galaxy's exact case-sensitive scan and explicit advertisement suggestions."""

from ..goodvibe.discovery import KEYWORDS, name_product
from .catalog import PROFILE_CHOICES, SELECTORS

SCAN_CODES = tuple(
    code for _identity, code, admitted, _route in SELECTORS if admitted and _route != "desk"
)


def scan_matches(name: str | None) -> bool:
    return bool(name) and any(key in name for key in (*KEYWORDS, *SCAN_CODES))


def suggested_profile(name: str | None, *, russian: bool = False) -> str | None:
    try:
        code = name_product(name, russian=russian)
    except ValueError:
        return None
    return code if code in PROFILE_CHOICES else None
