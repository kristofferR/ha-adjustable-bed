"""Shared redaction utilities for the Adjustable Bed integration."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from homeassistant.const import CONF_NAME

from .beds.reverie.pairlink_protocol import (
    PAIRLINK_LOW_POWER_NOTIFY_UUID,
    PAIRLINK_LOW_POWER_SERVICE_UUID,
    PAIRLINK_LOW_POWER_WRITE_UUID,
    PAIRLINK_NOTIFY_UUID,
    PAIRLINK_WRITE_UUID,
)
from .const import (
    BED_TYPE_REVERIE_PAIRLINK,
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
    "active_sleep_auth_id",
    "ergobq_stamp",
    "ergobq_serial",
    "octo_pin_confirmation",
    "authcode",
    "authtoken",
    "token",
    "password",
}
# Text the user typed or renamed: often a person's name, never needed to debug.
_USER_TEXT_KEYS = {"title", "origin_title", CONF_BLE_DEVICE_NAME, CONF_FSM_RELAX_MEMORY_NAMES}
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


def _mask_match(match: re.Match[str]) -> str:
    sep = match.group(2)
    prefix = sep.join(match.group(index).upper() for index in (1, 3, 4))
    return f"{prefix}{sep}**{sep}**{sep}**"


def redact_text(text: str) -> str:
    """Keep only the manufacturer prefix of every Bluetooth address in ``text``."""
    return MAC_ADDRESS_PATTERN.sub(_mask_match, text)


def _redact(data: Any, keys: set[str], depth: int) -> Any:
    if depth > 20:  # Prevent infinite recursion
        return data
    if isinstance(data, dict):
        result: dict[Any, Any] = {}
        for key, value in data.items():
            key_lower = key.lower() if isinstance(key, str) else key
            out_key = redact_text(key) if isinstance(key, str) else key
            if key in keys or key_lower in keys:
                result[out_key] = REDACTED
            elif isinstance(key, str) and _is_health_key(key):
                result[out_key] = f"<{type(value).__name__}>"
            else:
                result[out_key] = _redact(value, keys, depth + 1)
        return result
    if isinstance(data, list | tuple):
        return [_redact(item, keys, depth + 1) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


def redact_data(data: Any) -> Any:
    """Redact the diagnostics download.

    Removes names, typed text, serials and credentials, keeps only the
    manufacturer prefix of every Bluetooth address and hides health readings.
    """
    return _redact(data, KEYS_TO_REDACT, 0)


def redact_bundle(data: Any) -> Any:
    """Redact a support bundle: the diagnostics policy, but device names stay."""
    return _redact(data, _BUNDLE_KEYS_TO_REDACT, 0)


def names_pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    """Match typed names as whole words, the longest first so none is left half shown."""
    words = sorted(
        {name.strip() for name in names if isinstance(name, str) and len(name.strip()) >= 3},
        key=len,
        reverse=True,
    )
    if not words:
        return None
    return re.compile(
        "(?i)" + "|".join(rf"(?<!\w){re.escape(word)}(?!\w)" for word in words)
    )


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


# Pairlink keys its frames with the home ID, which the bed advertises, and a
# four-byte password: one captured frame lets anyone recover the password
# offline. The low-power characteristics use generic UUIDs, so they are
# redacted only for a Pairlink bed.
_PAIRLINK_CHARACTERISTICS = frozenset({PAIRLINK_WRITE_UUID, PAIRLINK_NOTIFY_UUID})
_PAIRLINK_LOW_POWER_CHARACTERISTICS = frozenset(
    {PAIRLINK_LOW_POWER_WRITE_UUID, PAIRLINK_LOW_POWER_NOTIFY_UUID}
)

# A JSON credential, such as a bed's Wi-Fi provisioning message.
CREDENTIAL_PAYLOAD = re.compile(rb'(?i)"(?:ssid|pswd|password|passwd|pwd)"\s*:')


def redact_pairlink_frames(report: dict[str, Any]) -> None:
    """Keep Pairlink frame lengths and counts, never their bytes."""
    secret = set(_PAIRLINK_CHARACTERISTICS)
    # A capture by address alone knows no bed type: the complete low-power
    # profile, which no other supported bed uses, is enough.
    low_power_profile = any(
        str(service.get("uuid", "")).lower() == PAIRLINK_LOW_POWER_SERVICE_UUID
        and {str(char.get("uuid", "")).lower() for char in service.get("characteristics", [])}
        >= _PAIRLINK_LOW_POWER_CHARACTERISTICS
        for service in report.get("gatt_services", [])
    )
    if low_power_profile or BED_TYPE_REVERIE_PAIRLINK in (
        report.get("detection", {}).get("bed_type"),
        report.get("integration", {}).get("bed_type"),
    ):
        secret |= _PAIRLINK_LOW_POWER_CHARACTERISTICS
    for service in report.get("gatt_services", []):
        for characteristic in service.get("characteristics", []):
            result = characteristic.get("read_result")
            if str(characteristic.get("uuid", "")).lower() in secret and isinstance(result, dict):
                result["hex"] = REDACTED
                result["ascii_preview"] = None
    for notification in report.get("notifications", []):
        if str(notification.get("characteristic", "")).lower() in secret:
            notification["data_hex"] = REDACTED
    for uuid, summary in report.get("notification_summary", {}).get("by_characteristic", {}).items():
        if uuid.lower() in secret:
            summary["top_repeated_payloads"] = []
            summary["ascii_previews"] = []
