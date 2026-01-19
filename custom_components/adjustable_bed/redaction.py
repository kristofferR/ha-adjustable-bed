"""Shared redaction utilities for the Adjustable Bed integration."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import CONF_OCTO_PIN

# Keys to fully redact
KEYS_TO_REDACT = {CONF_NAME, CONF_OCTO_PIN, "title"}

# Keys containing MAC addresses (partial redaction - keep OUI)
MAC_ADDRESS_KEYS = {CONF_ADDRESS, "address"}

# Regex pattern for MAC addresses (colon or hyphen separated)
MAC_ADDRESS_PATTERN = re.compile(r"([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}")


def _redact_mac_address(mac: str | None | Any) -> str | Any:
    """Redact the last 3 bytes of a MAC address, keeping the OUI (manufacturer ID).

    Example: AA:BB:CC:DD:EE:FF -> AA:BB:CC:**:**:**

    This function is designed to handle any input type defensively. Non-string
    inputs (including None, integers, etc.) are returned unchanged.

    Args:
        mac: The MAC address to redact. Accepts str, None, or any other type.

    Returns:
        The partially redacted MAC address, or "**REDACTED**" for invalid formats,
        or the original value if not a string or empty.
    """
    if not mac or not isinstance(mac, str):
        return mac

    # Handle both : and - separators
    sep = ":" if ":" in mac else "-"
    parts = mac.upper().replace("-", ":").split(":")

    if len(parts) != 6:
        return "**REDACTED**"

    # Keep first 3 bytes (OUI), redact last 3
    return f"{parts[0]}{sep}{parts[1]}{sep}{parts[2]}{sep}**{sep}**{sep}**"


def redact_string(text: str) -> str:
    """Redact MAC addresses found within a string."""

    def replace_mac(match: re.Match[str]) -> str:
        return _redact_mac_address(match.group(0))

    return MAC_ADDRESS_PATTERN.sub(replace_mac, text)


def redact_data(data: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive data from a dictionary.

    - Fully redacts name, title, PIN fields
    - Partially redacts MAC addresses (keeps OUI for debugging)

    Args:
        data: The data structure to redact.
        depth: Current recursion depth (for infinite loop prevention).

    Returns:
        A copy of the data with sensitive values redacted.
    """
    if depth > 20:  # Prevent infinite recursion
        return data

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower() if isinstance(key, str) else key
            if key in KEYS_TO_REDACT or key_lower in KEYS_TO_REDACT:
                result[key] = "**REDACTED**"
            elif key in MAC_ADDRESS_KEYS or key_lower in MAC_ADDRESS_KEYS:
                result[key] = _redact_mac_address(value) if isinstance(value, str) else value
            else:
                result[key] = redact_data(value, depth + 1)
        return result
    elif isinstance(data, list):
        return [redact_data(item, depth + 1) for item in data]
    elif isinstance(data, str):
        return redact_string(data)
    else:
        return data
