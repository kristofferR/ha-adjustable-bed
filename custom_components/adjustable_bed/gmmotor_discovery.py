"""GM Control's scan/name/remote-selection rules, applied only after app choice."""

from __future__ import annotations


def scan_name_matches(name: str) -> bool:
    """Source case-sensitive substring filter; service UUID alone is insufficient."""
    from .gmmotor_catalog import SCAN_KEYWORDS

    return any(keyword in name for keyword in SCAN_KEYWORDS)


def selector_from_name(name: str, *, russian: bool = False) -> str:
    """Resolve the source aliases, with safe handling of short malformed names.

    The app's range access can fail on a short name. HA returns its empty base
    selector instead, requiring the user to choose an admitted product.
    """
    from .gmmotor_catalog import NAME_ALIASES

    if len(name) < 4:
        return ""
    prefix = name[:4].upper()
    if prefix == "MPE_":
        if len(name) < 9:
            return ""
        selected = NAME_ALIASES.get((name[:9].upper(), russian), "ZRA2")
    else:
        selected = NAME_ALIASES.get((prefix, russian), prefix)
    return selected


def resolve_selection(selector: str, choice: str | None = None) -> str:
    """Keep remote pickers explicit; never choose the first physical variant."""
    from .gmmotor_catalog import REMOTE_TARGETS, ROUTES

    if selector not in ROUTES:
        return ""  # The source's unknown/unsupported selector fallback.
    if selector in REMOTE_TARGETS:
        if choice not in REMOTE_TARGETS[selector]:
            raise ValueError("Choose the exact GM Control remote/product from this selector")
        assert choice is not None
        return choice
    if selector == "QRRM":
        choice = choice.upper() if choice is not None else None
        if choice is None or choice not in ROUTES or not choice:
            raise ValueError("Choose an admitted GM Control barcode product")
        return resolve_selection(choice)
    return selector
