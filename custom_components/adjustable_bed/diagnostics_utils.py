"""Shared utilities for diagnostics and support reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator


def get_gatt_summary(coordinator: AdjustableBedCoordinator) -> dict[str, Any]:
    """Get GATT service/characteristic summary for diagnostics."""
    client = coordinator.client
    if not client or not client.services:
        return {"available": False}

    service_count = len(list(client.services))
    char_count = 0
    notifiable_chars: list[str] = []
    writable_chars: list[str] = []

    for service in client.services:
        for char in service.characteristics:
            char_count += 1
            if "notify" in char.properties or "indicate" in char.properties:
                notifiable_chars.append(char.uuid)
            if "write" in char.properties or "write-without-response" in char.properties:
                writable_chars.append(char.uuid)

    return {
        "available": True,
        "service_count": service_count,
        "characteristic_count": char_count,
        "notifiable_characteristics": notifiable_chars,
        "writable_characteristics": writable_chars,
    }
