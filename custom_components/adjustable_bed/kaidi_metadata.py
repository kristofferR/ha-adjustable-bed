"""Helpers for caching Kaidi mesh metadata in config entries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import CONF_KAIDI_ROOM_ID, CONF_KAIDI_TARGET_VADDR
from .kaidi_protocol import KaidiAdvertisement, extract_best_kaidi_advertisement


def resolve_kaidi_advertisement(
    hass: HomeAssistant,
    address: str,
    *,
    manufacturer_data: dict[int, bytes] | None = None,
) -> KaidiAdvertisement | None:
    """Resolve the richest Kaidi advertisement snapshot Home Assistant has seen."""
    normalized_address = address.upper()
    manufacturer_data_sets: list[dict[int, bytes] | None] = [manufacturer_data]
    seen_snapshots: set[tuple[tuple[int, bytes], ...]] = set()

    def _add_snapshot(snapshot: dict[int, bytes] | None) -> None:
        if not snapshot:
            return
        frozen = tuple(sorted((company_id, bytes(payload)) for company_id, payload in snapshot.items()))
        if frozen in seen_snapshots:
            return
        seen_snapshots.add(frozen)
        manufacturer_data_sets.append({company_id: bytes(payload) for company_id, payload in snapshot.items()})

    for connectable in (True, False):
        info = bluetooth.async_last_service_info(hass, normalized_address, connectable=connectable)
        if info is not None and info.address.upper() == normalized_address:
            _add_snapshot(info.manufacturer_data)

        for info in bluetooth.async_discovered_service_info(hass, connectable=connectable):
            if info.address.upper() != normalized_address:
                continue
            _add_snapshot(info.manufacturer_data)

    return extract_best_kaidi_advertisement(manufacturer_data_sets)


def add_kaidi_entry_metadata(
    entry_data: Mapping[str, Any],
    advertisement: KaidiAdvertisement | None,
) -> dict[str, Any]:
    """Return entry data with cached Kaidi room/VADDR state when available."""
    updated = dict(entry_data)

    if advertisement is None:
        return updated

    if advertisement.room_id is not None:
        updated[CONF_KAIDI_ROOM_ID] = advertisement.room_id
    if advertisement.vaddr is not None:
        updated[CONF_KAIDI_TARGET_VADDR] = advertisement.vaddr

    return updated
