"""Shared payload formatting helpers for diagnostics and support bundles."""

from __future__ import annotations

from collections import Counter
from typing import Any

MAX_ASCII_PREVIEW_LENGTH = 64
MAX_REPEATED_PAYLOADS = 5


def payload_hex(data: bytes | bytearray | memoryview | None) -> str | None:
    """Return payload as hex string."""
    if data is None:
        return None
    return bytes(data).hex()


def payload_length(data: bytes | bytearray | memoryview | None) -> int | None:
    """Return payload length in bytes."""
    if data is None:
        return None
    return len(bytes(data))


def payload_ascii_preview(
    data: bytes | bytearray | memoryview | None,
    *,
    max_length: int = MAX_ASCII_PREVIEW_LENGTH,
) -> str | None:
    """Return a safe ASCII preview when the payload is printable."""
    if data is None:
        return None

    payload = bytes(data)
    if not payload:
        return ""

    if not all(32 <= byte <= 126 or byte in (9, 10, 13) for byte in payload):
        return None

    preview = payload.decode("ascii", errors="ignore")
    if len(preview) > max_length:
        return preview[:max_length] + "..."
    return preview


def format_payload(
    data: bytes | bytearray | memoryview | None,
    *,
    include_raw_hex_key: bool = False,
) -> dict[str, Any] | None:
    """Return a consistent payload representation."""
    if data is None:
        return None

    payload = bytes(data)
    formatted: dict[str, Any] = {
        "hex": payload.hex(),
        "length": len(payload),
        "ascii_preview": payload_ascii_preview(payload),
    }
    if include_raw_hex_key:
        formatted["data_hex"] = formatted["hex"]
    return formatted


def format_mapping_payloads(mapping: dict[Any, bytes] | None) -> dict[str, dict[str, Any]]:
    """Return a consistent payload mapping representation."""
    if not mapping:
        return {}
    return {
        str(key): format_payload(value) or {"hex": "", "length": 0, "ascii_preview": ""}
        for key, value in mapping.items()
    }


def summarize_repeated_payloads(
    payloads: list[bytes | bytearray | memoryview],
    *,
    limit: int = MAX_REPEATED_PAYLOADS,
) -> list[dict[str, Any]]:
    """Return the most common payloads with counts."""
    counter = Counter(bytes(payload).hex() for payload in payloads)
    repeated: list[dict[str, Any]] = []

    for payload_hex_value, count in counter.most_common(limit):
        payload = bytes.fromhex(payload_hex_value)
        repeated.append(
            {
                "count": count,
                "payload": format_payload(payload),
            }
        )

    return repeated
