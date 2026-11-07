"""Retire registry rows that a config entry's platforms no longer create.

Each platform records the unique IDs it builds. Once every platform has set
up and every bed or side knows its capabilities, rows for anything else are
removed, except those a controller says may still appear once the bed reports
them. A rebuilt builder replaces its own record, so a capability withdrawn
after discovery retires its entity the same way. While any capability is
unknown (an offline side, unfinished discovery) every row is kept.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.hass_dict import HassKey

from .const import CONF_SIDE, DOMAIN
from .entity_runtime import controller_side_scope
from .paired_coordinator import PairedBedCoordinator, entity_runtimes
from .pairing import iter_children

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# (entity domain, unique ID): the light and a legacy switch can share a unique ID.
type EntityIdentity = tuple[str, str]

_LEDGERS: HassKey[dict[str, EntityLedger]] = HassKey(f"{DOMAIN}_entity_ledgers")


def _retained_identities(
    entry: ConfigEntry, coordinator: AdjustableBedCoordinator | PairedBedCoordinator
) -> frozenset[EntityIdentity] | None:
    """Return identities kept although unbuilt, or None while any capability is unknown."""
    if isinstance(coordinator, PairedBedCoordinator):
        configured = {side for child in iter_children(entry.data) if (side := child.get(CONF_SIDE))}
        # A side kept by its original entry, or dropped at setup, is not built here.
        if not configured <= coordinator.children.keys():
            return None
    retained: set[EntityIdentity] = set()
    for runtime in entity_runtimes(coordinator):
        with controller_side_scope(runtime):
            controller = runtime.capability_controller
            if controller is None or not controller.controller_entity_discovery_complete:
                return None
            retained.update(
                (domain, runtime.entity_unique_id(key))
                for domain, key in controller.retained_entity_keys
            )
    return frozenset(retained)


class EntityLedger:
    """The identities one setup of a config entry's platforms has created."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self.coordinator = coordinator
        self._records: dict[object, frozenset[EntityIdentity]] = {}
        self._finished: set[str] = set()
        self._platforms: frozenset[str] | None = None
        self._swept: frozenset[EntityIdentity] | None = None
        self._sweep_scheduled = False
        self.active = True

    def record(self, key: object, identities: Iterable[EntityIdentity]) -> None:
        """Replace one builder's identities."""
        self._records[key] = frozenset(identities)

    def extend(self, key: object, identities: Iterable[EntityIdentity]) -> None:
        """Add identities to a record that only grows."""
        self._records[key] = self._records.get(key, frozenset()).union(identities)

    def platform_finished(self, domain: str) -> None:
        self._finished.add(domain)

    def platforms_forwarded(self, platforms: Iterable[str]) -> None:
        self._platforms = frozenset(platforms)

    @callback
    def async_schedule_sweep(self) -> None:
        """Sweep once every builder answering the same report has refreshed."""
        if self._sweep_scheduled:
            return
        self._sweep_scheduled = True

        @callback
        def run() -> None:
            self._sweep_scheduled = False
            if self.active:
                self.async_sweep()

        self.hass.loop.call_soon(run)

    @callback
    def async_sweep(self) -> None:
        """Remove rows nothing created, once the record is authoritative."""
        platforms = self._platforms
        # A platform that raised created nothing, which proves nothing.
        if platforms is None or not platforms <= self._finished:
            return
        retained = _retained_identities(self._entry, self.coordinator)
        if retained is None:
            return
        created = retained.union(*self._records.values())
        if created == self._swept:
            return
        self._swept = created
        registry = er.async_get(self.hass)
        removed: list[str] = []
        for row in list(er.async_entries_for_config_entry(registry, self._entry.entry_id)):
            if (
                row.platform == DOMAIN
                and row.domain in platforms
                and (row.domain, row.unique_id) not in created
            ):
                registry.async_remove(row.entity_id)
                removed.append(row.entity_id)
        if removed:
            _LOGGER.info(
                "Removed entities %s no longer provided by %s", ", ".join(removed), self._entry.title
            )


def _entity_ledger(hass: HomeAssistant, entry: ConfigEntry) -> EntityLedger:
    """Return the ledger of the entry's current setup, starting one if needed."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    ledgers = hass.data.setdefault(_LEDGERS, {})
    ledger = ledgers.get(entry.entry_id)
    # Each setup attempt has its own coordinator, so a retried setup starts afresh.
    if ledger is None or ledger.coordinator is not coordinator:
        ledger = ledgers[entry.entry_id] = EntityLedger(hass, entry, coordinator)

        @callback
        def drop() -> None:
            ledger.active = False
            if ledgers.get(entry.entry_id) is ledger:
                del ledgers[entry.entry_id]

        entry.async_on_unload(drop)
    return ledger


class PlatformEntities:
    """A platform's add-entities callback that records what the platform creates."""

    def __init__(self, ledger: EntityLedger, domain: str, add: AddEntitiesCallback) -> None:
        self._ledger = ledger
        self._domain = domain
        self._add = add

    def _identities(self, unique_ids: Iterable[str | None]) -> list[EntityIdentity]:
        return [(self._domain, unique_id) for unique_id in unique_ids if unique_id is not None]

    def __call__(self, new_entities: Iterable[Entity], update_before_add: bool = False) -> None:
        """Add entities that stay for the rest of this setup."""
        entities = list(new_entities)
        self._ledger.extend(self, self._identities(entity.unique_id for entity in entities))
        if update_before_add:
            self._add(entities, update_before_add)
        else:
            self._add(entities)

    def publish(self, key: object, unique_ids: Iterable[str | None]) -> None:
        """Replace what one rebuilt builder provides, then schedule a sweep."""
        self._ledger.record(key, self._identities(unique_ids))
        self._ledger.async_schedule_sweep()

    def has_row(self, unique_id: str) -> bool:
        """Whether this platform's registry row for the unique ID still exists."""
        registry = er.async_get(self._ledger.hass)
        return registry.async_get_entity_id(self._domain, DOMAIN, unique_id) is not None

    def add_published(self, entities: list[Entity]) -> None:
        """Add entities whose identities a ``publish`` call already recorded."""
        if entities:
            self._add(entities)


type PlatformSetup = Callable[[HomeAssistant, ConfigEntry, PlatformEntities], Awaitable[None]]
type EntryPlatformSetup = Callable[[HomeAssistant, ConfigEntry, AddEntitiesCallback], Awaitable[None]]


def records_entities(domain: Platform) -> Callable[[PlatformSetup], EntryPlatformSetup]:
    """Make a platform's ``async_setup_entry`` record the entities it creates."""

    def decorate(setup: PlatformSetup) -> EntryPlatformSetup:
        @wraps(setup)
        async def async_setup_entry(
            hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
        ) -> None:
            ledger = _entity_ledger(hass, entry)
            await setup(hass, entry, PlatformEntities(ledger, domain, async_add_entities))
            ledger.platform_finished(domain)

        return async_setup_entry

    return decorate


@callback
def async_sweep_after_setup(
    hass: HomeAssistant, entry: ConfigEntry, platforms: Iterable[Platform]
) -> None:
    """Retire stale rows once every forwarded platform has set up."""
    ledger = _entity_ledger(hass, entry)
    ledger.platforms_forwarded(platforms)
    ledger.async_sweep()
