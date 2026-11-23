"""Helpers for caching Kaidi mesh metadata in config entries."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from ...const import (
    BED_TYPE_KAIDI,
    CONF_BED_TYPE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
)
from ...profiles.kaidi import resolve_kaidi_variant_from_entry_data
from .protocol import KaidiAdvertisement, extract_best_kaidi_advertisement

_LOGGER = logging.getLogger(__name__)


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
        resolution = resolve_kaidi_variant_from_entry_data(updated)
    else:
        updated[CONF_KAIDI_ADV_TYPE] = advertisement.adv_type
        if advertisement.room_id is not None:
            updated[CONF_KAIDI_ROOM_ID] = advertisement.room_id
        if advertisement.vaddr is not None:
            updated[CONF_KAIDI_TARGET_VADDR] = advertisement.vaddr
        if advertisement.product_id is not None:
            updated[CONF_KAIDI_PRODUCT_ID] = advertisement.product_id
        if advertisement.sofa_acu_no is not None:
            updated[CONF_KAIDI_SOFA_ACU_NO] = advertisement.sofa_acu_no
        resolution = resolve_kaidi_variant_from_entry_data(updated)

    updated[CONF_KAIDI_VARIANT_SOURCE] = resolution.source
    if resolution.variant is not None:
        updated[CONF_KAIDI_RESOLVED_VARIANT] = resolution.variant
    else:
        updated.pop(CONF_KAIDI_RESOLVED_VARIANT, None)

    return updated


async def async_cache_kaidi_entry_metadata(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Cache Kaidi room/VADDR state from Bluetooth history for existing entries."""
    if entry.data.get(CONF_BED_TYPE) != BED_TYPE_KAIDI:
        return

    advertisement = resolve_kaidi_advertisement(
        hass,
        entry.data[CONF_ADDRESS],
    )
    if advertisement is None:
        return

    new_data = add_kaidi_entry_metadata(entry.data, advertisement)
    if new_data == dict(entry.data):
        return

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info(
        "Cached Kaidi metadata for %s (room_id=%s, target_vaddr=%s, product_id=%s, sofa_acu_no=%s, adv_type=%s, resolved_variant=%s, variant_source=%s)",
        entry.data[CONF_ADDRESS],
        new_data.get(CONF_KAIDI_ROOM_ID),
        new_data.get(CONF_KAIDI_TARGET_VADDR),
        new_data.get(CONF_KAIDI_PRODUCT_ID),
        new_data.get(CONF_KAIDI_SOFA_ACU_NO),
        new_data.get(CONF_KAIDI_ADV_TYPE),
        new_data.get(CONF_KAIDI_RESOLVED_VARIANT),
        new_data.get(CONF_KAIDI_VARIANT_SOURCE),
    )
