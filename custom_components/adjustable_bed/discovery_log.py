"""Persistent log of auto-detected BLE devices for diagnosing misidentification.

When the integration auto-detects a device as a supported bed during Bluetooth
discovery, a compact record (device name, advertised service UUIDs, manufacturer
data, the bed type guessed, confidence, and the detection signals) is appended
here. This gives users and maintainers the data needed to report and fix
false-positive detections.

Without this, those signals are lost once a discovery card is dismissed: Home
Assistant only persists the bare MAC for devices the user explicitly ignores,
which is not enough to tell *why* a device was misidentified.

See: https://github.com/kristofferR/ha-adjustable-bed/discussions/342
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_discovery_log"
# Most recent auto-detections to retain. Deduped by MAC, so this is a cap on
# distinct devices, not raw advertisements.
MAX_ENTRIES = 100
# Key under hass.data for the per-instance singleton. Kept separate from
# hass.data[DOMAIN] (which holds coordinators keyed by entry_id) to avoid
# colliding with config-entry storage.
_DATA_KEY = f"{DOMAIN}_discovery_log"


class DiscoveryLogEntry(TypedDict):
    """A single auto-detection record."""

    detected_at: str
    address: str
    name: str | None
    service_uuids: list[str]
    manufacturer_data: dict[str, str]
    bed_type: str | None
    confidence: float
    signals: list[str]


class DiscoveryLog:
    """Stores the most recent auto-detected devices (capped, deduped by MAC)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the backing store (loaded lazily on first use)."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._entries: list[DiscoveryLogEntry] | None = None
        # Serialises concurrent async_record() calls so an interleaved
        # load/mutate/save cannot drop an append.
        self._write_lock = asyncio.Lock()

    async def _async_ensure_loaded(self) -> list[DiscoveryLogEntry]:
        """Load entries from disk on first access, then keep them in memory."""
        if self._entries is None:
            data = await self._store.async_load()
            entries = data.get("entries", []) if isinstance(data, dict) else []
            self._entries = list(entries)
        return self._entries

    async def async_record(
        self,
        *,
        address: str,
        name: str | None,
        service_uuids: list[str],
        manufacturer_data: dict[int, bytes] | None,
        bed_type: str | None,
        confidence: float,
        signals: list[str],
    ) -> None:
        """Append a detection record, keeping only the latest MAX_ENTRIES.

        Records are deduped by MAC so that a single device re-advertising cannot
        flood the log and the most recent detection always wins.
        """
        normalized = address.upper()
        async with self._write_lock:
            entries = await self._async_ensure_loaded()
            entries = [entry for entry in entries if entry.get("address") != normalized]
            entries.append(
                DiscoveryLogEntry(
                    detected_at=dt_util.utcnow().isoformat(),
                    address=normalized,
                    name=name,
                    service_uuids=list(service_uuids),
                    manufacturer_data={
                        f"0x{company_id:04X}": bytes(value).hex()
                        for company_id, value in (manufacturer_data or {}).items()
                    },
                    bed_type=bed_type,
                    confidence=round(confidence, 3),
                    signals=list(signals),
                )
            )
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            self._entries = entries
            await self._store.async_save({"entries": entries})
        _LOGGER.debug(
            "Recorded auto-detection of %s as %s (confidence %.2f); log holds %d device(s)",
            normalized,
            bed_type,
            confidence,
            len(entries),
        )

    async def async_get(self, address: str) -> DiscoveryLogEntry | None:
        """Return the most recent record for an address, if any."""
        normalized = address.upper()
        for entry in await self._async_ensure_loaded():
            if entry.get("address") == normalized:
                return entry
        return None

    async def async_all(self) -> list[DiscoveryLogEntry]:
        """Return all records, most recent first."""
        return list(reversed(await self._async_ensure_loaded()))


@callback
def async_get_discovery_log(hass: HomeAssistant) -> DiscoveryLog:
    """Return the singleton discovery log for this Home Assistant instance."""
    log: DiscoveryLog | None = hass.data.get(_DATA_KEY)
    if log is None:
        log = DiscoveryLog(hass)
        hass.data[_DATA_KEY] = log
    return log
