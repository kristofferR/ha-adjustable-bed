"""Bed-family steps of standalone config-entry setup.

``async_setup_entry`` stays bed-agnostic: it runs every prepare step, then
looks up the hooks registered for the entry's bed type. Each step and hook is
declared in its family's module.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .beds.furnimove.repair import async_load_offline_furnimove_entry
from .beds.kaidi.metadata import async_cache_kaidi_entry_metadata
from .beds.octo.runtime import async_refresh_octo_pin_issue
from .beds.remacro.discovery import async_prepare_remacro_entry
from .beds.reverie.pairlink_local_setup import async_setup_pairlink_local_entry
from .beds.richmat.qrrm_reclassification import async_reclassify_bedtech_qrrm_entry
from .const import BED_TYPE_DIAGNOSTIC, BED_TYPE_FURNIMOVE, BED_TYPE_REVERIE_PAIRLINK
from .import_executor import async_import_modules

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

type PrepareEntry = Callable[[HomeAssistant, ConfigEntry], Awaitable[None]]
type LoadOffline = Callable[
    [HomeAssistant, ConfigEntry, AdjustableBedCoordinator, str], Awaitable[bool]
]
type SetupLocal = Callable[
    [HomeAssistant, ConfigEntry, AdjustableBedCoordinator, Callable[[], Awaitable[None]]],
    Awaitable[bool],
]


async def _async_load_offline_diagnostic_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    reason: str,
) -> bool:
    """Load a diagnostic entry even when initial BLE connection fails."""
    await async_import_modules(hass, "beds.diagnostic")
    from .beds.diagnostic import DiagnosticBedController

    _LOGGER.warning(
        "Loading diagnostic entry %s (%s) without an initial BLE connection so "
        "diagnostic actions remain available: %s",
        entry.title,
        entry.data.get(CONF_ADDRESS),
        reason,
    )
    coordinator._controller = DiagnosticBedController(coordinator)
    return True


@dataclass(frozen=True, slots=True)
class EntryHooks:
    """Setup steps one bed type adds to a standalone entry."""

    # Prepares a load without the first connection; False keeps the setup retry.
    load_offline: LoadOffline | None = None
    # Replaces the central connection; False when the entry does not select it.
    setup_local: SetupLocal | None = None


# Run on every standalone entry, in order, before its coordinator exists. Each
# step also clears what it raised for an entry that no longer matches it. The
# QRRM step can change the bed type the later steps see.
ENTRY_PREPARE_STEPS: Final[tuple[PrepareEntry, ...]] = (
    async_reclassify_bedtech_qrrm_entry,
    async_cache_kaidi_entry_metadata,
    async_prepare_remacro_entry,
    async_refresh_octo_pin_issue,
)

_ENTRY_HOOKS: Final[Mapping[str, EntryHooks]] = {
    BED_TYPE_DIAGNOSTIC: EntryHooks(load_offline=_async_load_offline_diagnostic_entry),
    BED_TYPE_FURNIMOVE: EntryHooks(load_offline=async_load_offline_furnimove_entry),
    BED_TYPE_REVERIE_PAIRLINK: EntryHooks(setup_local=async_setup_pairlink_local_entry),
}
_NO_HOOKS: Final = EntryHooks()


def entry_hooks(bed_type: str) -> EntryHooks:
    """Return the hooks registered for a bed type."""
    return _ENTRY_HOOKS.get(bed_type, _NO_HOOKS)
