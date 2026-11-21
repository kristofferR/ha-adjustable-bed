"""Shared redaction utilities for the Adjustable Bed integration."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from homeassistant.const import CONF_NAME

from .const import (
    BED_TYPE_SLEEP_NUMBER,
    CONF_BLE_DEVICE_NAME,
    CONF_FSM_RELAX_MEMORY_NAMES,
    CONF_JENSEN_PIN,
    CONF_OCTO_PIN,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    SLEEP_NUMBER_AUTH_CHAR_UUID,
)

REDACTED = "**REDACTED**"

# Credentials are secret in every file.
_CREDENTIAL_KEYS = {
    CONF_JENSEN_PIN,
    CONF_OCTO_PIN,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    "octo_pin_confirmation",
    "authcode",
    "authtoken",
    "token",
    "password",
}
# Text the user typed or renamed: often a person's name, never needed to debug.
_USER_TEXT_KEYS = {"title", CONF_BLE_DEVICE_NAME, CONF_FSM_RELAX_MEMORY_NAMES}
KEYS_TO_REDACT = {
    CONF_NAME,
    "serial",
    "serial_number",
    "configuration_url",
} | _USER_TEXT_KEYS | _CREDENTIAL_KEYS
# The support bundle keeps device names: they are what bed detection matches.
_BUNDLE_KEYS_TO_REDACT = _USER_TEXT_KEYS | _CREDENTIAL_KEYS

# A Bluetooth address with one consistent separator.
_HEX = "[0-9A-Fa-f]"
MAC_ADDRESS_PATTERN = re.compile(
    rf"(?<!{_HEX})({_HEX}{{2}})([:\-_])({_HEX}{{2}})\2({_HEX}{{2}})"
    rf"\2{_HEX}{{2}}\2{_HEX}{{2}}\2{_HEX}{{2}}(?!{_HEX})"
)

# Health and presence readings: the key stays, the value becomes its type.
# Matched on whole words of the key, so "motion_bed" or "anti_snore" never match.
_HEALTH_KEY = re.compile(
    r"_(?:heart|heartbeat|breath|breathing|respiration|respiratory|apnea|hrv|occupancy"
    r"|occupied|presence|inbed|onbed|outbed|awake|awakening|snoring|in_bed|on_bed|out_bed"
    r"|bed_exit|leave_bed|body_move|body_movement|body_revolve|snore_duration"
    r"|sleep_(?:report|data|stage|score|history|status|quality)|report_cache)_"
)


def _is_health_key(key: str) -> bool:
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower()
    return _HEALTH_KEY.search(f"_{re.sub('[^a-z0-9]+', '_', words)}_") is not None


def _redact_mac_address(mac: str | None | Any) -> str | Any:
    """Keep the manufacturer prefix (first three bytes) of a MAC address.

    Example: AA:BB:CC:DD:EE:FF -> AA:BB:CC:**:**:**

    Non-string or empty inputs are returned unchanged; a string that is not a
    six-byte address becomes "**REDACTED**".
    """
    if not mac or not isinstance(mac, str):
        return mac
    match = MAC_ADDRESS_PATTERN.fullmatch(mac.strip())
    if match is None:
        return REDACTED
    return _mask_match(match)


def _mask_match(match: re.Match[str]) -> str:
    sep = match.group(2)
    prefix = sep.join(match.group(index).upper() for index in (1, 3, 4))
    return f"{prefix}{sep}**{sep}**{sep}**"


def _device_half_pattern(addresses: Iterable[str]) -> re.Pattern[str] | None:
    """Match the device-specific half of known addresses in any other form.

    Names, advertisement data and frames can carry it without separators, in
    reverse byte order or as ASCII text.
    """
    forms: set[str] = set()
    for address in addresses:
        match = MAC_ADDRESS_PATTERN.fullmatch(address.strip()) if isinstance(address, str) else None
        if match is None:
            continue
        tail = match.group(0)[9:].replace(match.group(2), "").lower()
        octets = [tail[index : index + 2] for index in (0, 2, 4)]
        forms.add("[:\\-_]?".join(octets))
        forms.add("[:\\-_]?".join(reversed(octets)))
        forms.add(tail.encode().hex())
        forms.add(tail.upper().encode().hex())
    if not forms:
        return None
    return re.compile(f"(?i){'|'.join(sorted(forms))}")


def _redact_text(text: str, device_half: re.Pattern[str] | None) -> str:
    text = MAC_ADDRESS_PATTERN.sub(_mask_match, text)
    if device_half is not None:
        text = device_half.sub(lambda match: "*" * len(match.group(0)), text)
    return text


def redact_text(text: str, addresses: Iterable[str]) -> str:
    """Apply the address policy of ``redact_bundle`` to one string."""
    return _redact_text(text, _device_half_pattern(addresses))


def _redact(data: Any, keys: set[str], device_half: re.Pattern[str] | None, depth: int) -> Any:
    if depth > 20:  # Prevent infinite recursion
        return data
    if isinstance(data, dict):
        result: dict[Any, Any] = {}
        for key, value in data.items():
            key_lower = key.lower() if isinstance(key, str) else key
            out_key = _redact_text(key, device_half) if isinstance(key, str) else key
            if key in keys or key_lower in keys:
                result[out_key] = REDACTED
            elif isinstance(key, str) and _is_health_key(key):
                result[out_key] = f"<{type(value).__name__}>"
            else:
                result[out_key] = _redact(value, keys, device_half, depth + 1)
        return result
    if isinstance(data, list | tuple):
        return [_redact(item, keys, device_half, depth + 1) for item in data]
    if isinstance(data, str):
        return _redact_text(data, device_half)
    return data


def redact_data(data: Any, *, addresses: Iterable[str] = ()) -> Any:
    """Redact the diagnostics download.

    Removes names, typed text, serials and credentials, keeps only the
    manufacturer prefix of every Bluetooth address and hides health readings.
    ``addresses`` are scrubbed in every other form too (see ``redact_bundle``).
    """
    return _redact(data, KEYS_TO_REDACT, _device_half_pattern(addresses), 0)


def redact_bundle(data: Any, *, addresses: Iterable[str]) -> Any:
    """Redact a support bundle: the diagnostics policy, but device names stay.

    Every Bluetooth address keeps only its manufacturer prefix. The device half
    of each address in ``addresses`` is also starred wherever it appears without
    separators, in reverse byte order or as ASCII (names, advertisement data,
    frames, logs). Health and presence readings keep their key only.
    """
    return _redact(data, _BUNDLE_KEYS_TO_REDACT, _device_half_pattern(addresses), 0)


def _addresses_in(text: str) -> set[str]:
    return {
        match.group(0).upper().replace(match.group(2), ":")
        for match in MAC_ADDRESS_PATTERN.finditer(text)
    }


def mentions_only(text: str, addresses: set[str]) -> bool:
    """Whether every Bluetooth address in ``text`` is one of ``addresses``.

    ``addresses`` are upper case with colons.
    """
    return _addresses_in(text) <= addresses


def mentions_any(text: str, addresses: set[str]) -> bool:
    """Whether ``text`` names one of ``addresses`` (upper case with colons)."""
    return not _addresses_in(text).isdisjoint(addresses)


def redact_sleep_number_sessions(report: dict[str, Any]) -> None:
    """Keep Auth lengths and notification counts without publishing session IDs."""
    for service in report.get("gatt_services", []):
        for characteristic in service.get("characteristics", []):
            if str(characteristic.get("uuid", "")).lower() != SLEEP_NUMBER_AUTH_CHAR_UUID:
                continue
            read_result = characteristic.get("read_result")
            if isinstance(read_result, dict) and read_result.get("hex"):
                read_result["hex"] = "**REDACTED**"
                read_result["ascii_preview"] = None

    if (
        report.get("detection", {}).get("bed_type") != BED_TYPE_SLEEP_NUMBER
        and report.get("integration", {}).get("bed_type") != BED_TYPE_SLEEP_NUMBER
    ):
        return
    # Fuzion notification hints can carry the same session UUID. Their timing,
    # characteristic and lengths remain useful without the reusable identifier.
    for notification in report.get("notifications", []):
        if len(str(notification.get("data_hex", ""))) == 32:
            notification["data_hex"] = "**REDACTED**"
    for summary in report.get("notification_summary", {}).get("by_characteristic", {}).values():
        summary["top_repeated_payloads"] = []
        summary["ascii_previews"] = []


SLEEPTRACKER_SECRET_CHARACTERISTICS = frozenset(
    {
        "4bc4783d-64a3-45b0-9a4a-06cb7713e32b",
        "a5a25fb5-500f-436b-8d36-447bc5f30a29",
        "3d91d13b-2310-43d1-b991-9e915b047653",
    }
)


def redact_sleeptracker_sessions(report: dict[str, Any]) -> None:
    """Retain lengths/counts without publishing framed challenges or tokens."""
    for service in report.get("gatt_services", []):
        for characteristic in service.get("characteristics", []):
            if str(characteristic.get("uuid", "")).lower() in SLEEPTRACKER_SECRET_CHARACTERISTICS:
                result = characteristic.get("read_result")
                if isinstance(result, dict):
                    result["hex"] = "**REDACTED**"
                    result["ascii_preview"] = None
    for notification in report.get("notifications", []):
        if (
            str(notification.get("characteristic", "")).lower()
            in SLEEPTRACKER_SECRET_CHARACTERISTICS
        ):
            notification["data_hex"] = "**REDACTED**"
    for uuid, summary in (
        report.get("notification_summary", {}).get("by_characteristic", {}).items()
    ):
        if uuid.lower() in SLEEPTRACKER_SECRET_CHARACTERISTICS:
            summary["top_repeated_payloads"] = []
            summary["ascii_previews"] = []
