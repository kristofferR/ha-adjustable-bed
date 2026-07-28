"""Remembers that the user said their beds are separate, not two sides of one.

The Dual Bed suggestion is a fixable Repairs issue, and Home Assistant offers no
Ignore action for those: a fixable issue opens its fix flow, so the only way out
of the dialog is to close it, which leaves the issue sitting in Repairs. For
someone who genuinely owns two beds that is a permanent, unanswerable warning.

Each dismissal is recorded against the set of addresses that was suggested,
not as a global "never ask" flag. Those beds and any remaining subset stay
separate, while adding another bed is a different question and gets asked again.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, override

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 2
STORAGE_KEY = f"{DOMAIN}_combine_suggestion"
_DATA_KEY = f"{DOMAIN}_combine_suggestion"

KEY_DISMISSED = "dismissed_address_sets"
LEGACY_KEY_DISMISSED = "dismissed_addresses"


def normalize_addresses(addresses: Iterable[str]) -> frozenset[str]:
    """Return a comparable address set, case and order independent."""
    return frozenset(address.upper() for address in addresses if isinstance(address, str))


def _normalize_address_sets(address_sets: object) -> frozenset[frozenset[str]]:
    """Return valid normalized address sets from persisted JSON data."""
    if not isinstance(address_sets, list):
        return frozenset()

    normalized_sets: list[frozenset[str]] = []
    for addresses in address_sets:
        if not isinstance(addresses, list):
            continue
        normalized = normalize_addresses(addresses)
        if normalized:
            normalized_sets.append(normalized)
    return frozenset(normalized_sets)


def _serialize_address_sets(
    address_sets: Iterable[frozenset[str]],
) -> list[list[str]]:
    """Return stable JSON data for a collection of address sets."""
    return sorted(sorted(addresses) for addresses in address_sets)


class CombineSuggestionStore(Store[dict[str, Any]]):
    """Store with migration from the original single-dismissal format."""

    @override
    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate a v1 address list into the v2 dismissal history."""
        if old_major_version != 1:
            raise ValueError(f"Unsupported combine suggestion storage version {old_major_version}")

        dismissed = normalize_addresses(old_data.get(LEGACY_KEY_DISMISSED) or ())
        return {KEY_DISMISSED: [sorted(dismissed)] if dismissed else []}


class CombineSuggestionState:
    """The bed sets the user has already declared separate."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the backing store; call ``async_load`` before reading."""
        self._store = CombineSuggestionStore(hass, STORAGE_VERSION, STORAGE_KEY)
        self._dismissed: frozenset[frozenset[str]] = frozenset()
        self._loaded = False

    @property
    def dismissed(self) -> frozenset[frozenset[str]]:
        """Return the dismissed address sets.

        Cached deliberately. The Repairs refresh runs from synchronous entry
        lifecycle callbacks, which cannot await a store read.
        """
        return self._dismissed

    async def async_load(self) -> None:
        """Read the persisted dismissal once, at integration setup."""
        if self._loaded:
            return
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            self._dismissed = _normalize_address_sets(loaded.get(KEY_DISMISSED))
        self._loaded = True

    async def async_dismiss(self, addresses: Iterable[str]) -> None:
        """Record that this exact set of beds is not one physical bed."""
        dismissed = normalize_addresses(addresses)
        if not dismissed or dismissed in self._dismissed:
            return
        self._dismissed = self._dismissed | {dismissed}
        await self._store.async_save(
            {KEY_DISMISSED: _serialize_address_sets(self._dismissed)}
        )
        _LOGGER.debug("Combine suggestion dismissed for %s", sorted(dismissed))


def _async_get_state(hass: HomeAssistant) -> CombineSuggestionState:
    """Return the singleton dismissal state for this Home Assistant instance."""
    state: CombineSuggestionState | None = hass.data.get(_DATA_KEY)
    if state is None:
        state = CombineSuggestionState(hass)
        hass.data[_DATA_KEY] = state
    return state


async def async_load_dismissal(hass: HomeAssistant) -> None:
    """Load the persisted dismissal so the sync refresh can consult it."""
    await _async_get_state(hass).async_load()


def async_is_dismissed(hass: HomeAssistant, addresses: Iterable[str]) -> bool:
    """Return True when the user already called all these beds separate."""
    candidates = normalize_addresses(addresses)
    return bool(candidates) and any(
        candidates <= dismissed for dismissed in _async_get_state(hass).dismissed
    )


async def async_dismiss(hass: HomeAssistant, addresses: Iterable[str]) -> None:
    """Persist that this set of beds is separate and should not be suggested."""
    await _async_get_state(hass).async_dismiss(addresses)
