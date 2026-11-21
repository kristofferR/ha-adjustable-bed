"""Name the automations and scripts that still use an entity the bed lost.

When an entity folds into another one (timer buttons that became one timer
select) or goes away, the sweep removes its registry row and an automation
using it stops working without a word. Each enabled row the sweep removes is
remembered until Home Assistant has started and automations and scripts are
checked. One repair per bed lists each removed entity one of them still uses,
and goes away at the first start where none does. A remembered entity nothing
uses is forgotten. Rows the user deletes, and a deleted bed's rows, never pass
through here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .automation_references import entity_users
from .beta_feedback import breaking_changes_url
from .const import DOMAIN

ISSUE_PREFIX: Final = "removed_entities_"


class _Removed(TypedDict):
    entity_id: str
    # As Home Assistant showed it, with its device's name.
    name: str
    # Device actions name an entity by its registry ID.
    registry_id: str


# Entry ID -> the removed rows.
type _Records = dict[str, list[_Removed]]
_STORE: HassKey[tuple[Store[_Records], _Records]] = HassKey(f"{DOMAIN}_removed_entities")


async def async_setup_removed_entities(hass: HomeAssistant) -> None:
    """Load the remembered rows before any entry can remove one."""
    store: Store[_Records] = Store(hass, 1, f"{DOMAIN}.removed_entities")
    hass.data[_STORE] = (store, await store.async_load() or {})


@callback
def _async_save(hass: HomeAssistant) -> None:
    store, records = hass.data[_STORE]
    # Written ahead of the entity registry, which waits ten seconds.
    store.async_delay_save(lambda: records, 0)


@callback
def async_remove_entities(
    hass: HomeAssistant, entry: ConfigEntry, rows: Iterable[er.RegistryEntry]
) -> None:
    """Remove rows nothing builds any more, remembering the enabled ones."""
    registry = er.async_get(hass)
    removed: list[_Removed] = []
    for row in rows:
        # A disabled entity did nothing in an automation before either.
        if row.disabled_by is None:
            name = er.async_get_full_entity_name(hass, row) or row.entity_id
            removed.append({"entity_id": row.entity_id, "name": name, "registry_id": row.id})
        registry.async_remove(row.entity_id)
    if removed and (state := hass.data.get(_STORE)) is not None:
        state[1].setdefault(entry.entry_id, []).extend(removed)
        _async_save(hass)
        async_report_removed_entities(hass, entry)


@callback
def async_forget_removed_entities(hass: HomeAssistant, entry_id: str) -> None:
    """Forget a deleted bed's removed rows."""
    if (state := hass.data.get(_STORE)) is not None and state[1].pop(entry_id, None):
        _async_save(hass)


@callback
def async_report_removed_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise, update or withdraw the bed's repair once automations have loaded."""

    async def report(_hass: HomeAssistant) -> None:
        state = hass.data.get(_STORE)
        if state is None or hass.config_entries.async_get_entry(entry.entry_id) is None:
            return
        registry = er.async_get(hass)
        lines: list[str] = []
        kept: list[_Removed] = []
        records = state[1].pop(entry.entry_id, [])
        for record in records:
            # An entity built again under its old ID is not removed any more.
            if registry.async_is_registered(record["entity_id"]):
                continue
            if users := entity_users(hass, (record["entity_id"], record["registry_id"])):
                kept.append(record)
                lines.append(
                    f"- {record['name']} ({record['entity_id']}): {', '.join(sorted(users))}"
                )
        if kept:
            state[1][entry.entry_id] = kept
        if kept != records:
            _async_save(hass)
        issue_id = ISSUE_PREFIX + entry.entry_id
        if not lines:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            return
        version = (await async_get_integration(hass, DOMAIN)).version
        guide = breaking_changes_url(version) if version is not None else None
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            config_entry_id=entry.entry_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=f"{guide}#appendix-a-removed-and-replaced-entities-by-bed" if guide else None,
            translation_key="removed_entities",
            translation_placeholders={"bed": entry.title, "entities": "\n".join(sorted(lines))},
        )

    async_at_started(hass, report)
