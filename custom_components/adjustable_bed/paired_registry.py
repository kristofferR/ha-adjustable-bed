"""Pair conversion and unpair ownership transactions.

Connection probing and controller construction belong to integration setup.
This module validates registry plans, applies ownership changes in HA's required
order, and compensates failures before deleting the source config entry.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from types import MappingProxyType

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigEntryDisabler
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_SIDE,
    DOMAIN,
    PAIR_MODE_SINGLE_ADDRESS,
)
from .paired_devices import async_restore_full_device
from .pairing import (
    KEY_ABSORBED_ENTRY_ID,
    KEY_ORIGIN_SOURCE,
    KEY_ORIGIN_TITLE,
    KEY_ORIGIN_UNIQUE_ID,
    KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS,
    is_paired,
    iter_children,
    single_data_from_child,
    single_options_from_child,
)

_LOGGER = logging.getLogger(__name__)


def async_has_side_controller_entities(
    hass: HomeAssistant, entry: ConfigEntry, address: str,
) -> bool:
    """Find controls that require a capability controller before platform setup.

    During conversion they still belong to the original entry; after conversion
    they belong to the pair. Side unique IDs survive both ownership transfers.
    """
    owner_ids = {entry.entry_id}
    owner_ids.update(
        origin_id for child in iter_children(entry.data)
        if (origin_id := child.get(KEY_ABSORBED_ENTRY_ID))
    )
    registry = er.async_get(hass)
    return any(
        row.platform == DOMAIN
        and row.domain in {"climate", "light", "select"}
        and row.unique_id.startswith(f"{address}_")
        for owner_id in owner_ids
        for row in er.async_entries_for_config_entry(registry, owner_id)
    )


def _device_for_entry_and_identifier(
    registry: dr.DeviceRegistry,
    config_entry_id: str,
    identifier: tuple[str, str],
) -> dr.DeviceEntry | None:
    """Return one config entry's device carrying an exact identifier."""
    return registry.async_get_device_by_identifier(identifier, config_entry_id)


def _async_transfer_device_registry_entry(
    registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
    *,
    target_entry_id: str,
    identifier: tuple[str, str],
    via_device_id: str | None,
) -> None:
    """Move a device between config entries without changing its registry id.

    Home Assistant 2026.8 made devices single-owner. Registering the same
    identifier for the target entry now creates a separate placeholder instead
    of adding the target entry to the source device. Remove that placeholder
    before transferring the customized source device with the single-owner API.
    """
    target_device = _device_for_entry_and_identifier(registry, target_entry_id, identifier)
    if target_device is not None and target_device.id != device.id:
        registry.async_remove_device(target_device.id)
    registry.async_update_device(
        device.id,
        new_config_entry_id=target_entry_id,
        via_device_id=via_device_id,
    )


@dataclass(frozen=True)
class _DeviceMove:
    original: dr.DeviceEntry
    source: str
    target: str
    identifier: tuple[str, str]
    via_device_id: str | None


@dataclass
class _RegistryOwnership:
    """One prevalidated ownership plan, also used as its rollback journal.

    HA removes rows when their device moves to an incompatible owner. Restore
    entity owners before device owners, just as in the forward path. Snapshot
    before calling mutation APIs, which may raise after changing state.
    """

    entities: tuple[tuple[er.RegistryEntry, str], ...]
    devices: tuple[_DeviceMove, ...]
    placeholders: list[tuple[dr.DeviceEntry, str]] = field(default_factory=list, init=False)
    _attempted_entities: set[str] = field(default_factory=set, init=False)
    _attempted_devices: set[str] = field(default_factory=set, init=False)
    _attempted_placeholders: set[str] = field(default_factory=set, init=False)

    def apply(self, hass: HomeAssistant) -> None:
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        # All target entries must exist before HA allows a registry transfer.
        # Check the whole plan before its first mutation.
        for row, target in self.entities:
            current = ent_reg.async_get(row.entity_id)
            if current is None or current.config_entry_id != row.config_entry_id:
                raise HomeAssistantError(f"Entity ownership changed for {row.entity_id}")
            if hass.config_entries.async_get_entry(target) is None:
                raise HomeAssistantError(f"Target config entry {target} is missing")
            if row.device_id is not None and not any(
                move.original.id == row.device_id and move.target == target
                for move in self.devices
            ):
                device = dev_reg.async_get(row.device_id)
                if device is None or device.config_entry_id != target:
                    raise HomeAssistantError(f"No device ownership plan for {row.entity_id}")
        for move in self.devices:
            current = dev_reg.async_get(move.original.id)
            if current is None or current.config_entry_id != move.source:
                raise HomeAssistantError(f"Device ownership changed for {move.original.id}")
            if hass.config_entries.async_get_entry(move.target) is None:
                raise HomeAssistantError(f"Target config entry {move.target} is missing")
            placeholder = _device_for_entry_and_identifier(dev_reg, move.target, move.identifier)
            if placeholder is not None and placeholder.id != move.original.id:
                if er.async_entries_for_device(ent_reg, placeholder.id):
                    raise HomeAssistantError("Target placeholder already owns entity rows")
                self.placeholders.append((placeholder, move.target))
        for row, target in self.entities:
            self._attempted_entities.add(row.entity_id)
            ent_reg.async_update_entity(row.entity_id, config_entry_id=target)
        # Keep placeholder objects intact until commit. Removing one here can
        # discard its identity from HA's deleted-device index when the real
        # device takes over the same identifier, making exact rollback impossible.
        for placeholder, _owner in self.placeholders:
            self._attempted_placeholders.add(placeholder.id)
            dev_reg.async_update_device(
                placeholder.id,
                new_identifiers={(DOMAIN, f"paired_transfer_{placeholder.id}")},
                new_connections=set(),
            )
        for move in self.devices:
            self._attempted_devices.add(move.original.id)
            _async_transfer_device_registry_entry(
                dev_reg,
                move.original,
                target_entry_id=move.target,
                identifier=move.identifier,
                via_device_id=move.via_device_id,
            )

    def rollback(self, hass: HomeAssistant) -> bool:
        """Restore original owners idempotently; report every failed restoration."""
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        complete = True
        for row, _target in self.entities:
            if row.entity_id not in self._attempted_entities:
                continue
            try:
                current = ent_reg.async_get(row.entity_id)
                if current is None:
                    raise HomeAssistantError(f"Registry row {row.entity_id} disappeared")
                if current.config_entry_id != row.config_entry_id:
                    ent_reg.async_update_entity(row.entity_id, config_entry_id=row.config_entry_id)
            except Exception:
                complete = False
                _LOGGER.exception("Could not restore entity ownership for %s", row.entity_id)
        for move in self.devices:
            if move.original.id not in self._attempted_devices:
                continue
            try:
                current = dev_reg.async_get(move.original.id)
                if not isinstance(current, dr.DeviceEntry):
                    raise HomeAssistantError(f"Registry device {move.original.id} disappeared")
                if any(
                    row.device_id == move.original.id
                    and (restored := ent_reg.async_get(row.entity_id)) is not None
                    and restored.config_entry_id != row.config_entry_id
                    for row, _target in self.entities
                ):
                    raise HomeAssistantError("Device rollback would delete an unrestored entity")
                if (
                    current.config_entry_id == move.target
                    and current.config_entry_id != move.source
                ):
                    _async_transfer_device_registry_entry(
                        dev_reg,
                        current,
                        target_entry_id=move.source,
                        identifier=move.identifier,
                        via_device_id=move.original.via_device_id,
                    )
            except Exception:
                complete = False
                _LOGGER.exception("Could not restore device ownership for %s", move.original.id)
        for placeholder, owner in self.placeholders:
            if placeholder.id not in self._attempted_placeholders:
                continue
            try:
                current = dev_reg.async_get(placeholder.id)
                if not isinstance(current, dr.DeviceEntry):
                    raise HomeAssistantError("Placeholder disappeared before commit")
                if (
                    current.identifiers == placeholder.identifiers
                    and current.connections == placeholder.connections
                ):
                    continue
                if (
                    _device_for_entry_and_identifier(
                        dev_reg, owner, next(iter(placeholder.identifiers))
                    )
                    is not None
                ):
                    raise HomeAssistantError("Target device ownership has not been rolled back")
                dev_reg.async_update_device(
                    placeholder.id,
                    new_identifiers=set(placeholder.identifiers),
                    new_connections=set(placeholder.connections),
                )
            except Exception:
                complete = False
                _LOGGER.exception("Could not restore placeholder device %s", placeholder.id)
        return complete

    def finish(self, hass: HomeAssistant) -> None:
        """Retire empty placeholders only after the source entry was removed."""
        registry = dr.async_get(hass)
        for placeholder, _owner in self.placeholders:
            try:
                if registry.async_get(placeholder.id) is not None:
                    registry.async_remove_device(placeholder.id)
            except Exception:
                _LOGGER.exception("Could not retire committed placeholder %s", placeholder.id)


async def _async_rehome_absorbed_singles(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Re-home absorbed single entries' registry rows onto the pair, then remove them.

    Conversion is ADDITIVE. Instead of deleting each original single entry's
    registry rows and letting the paired platforms recreate them (which would
    reset per-side history and customizations), this moves the existing rows onto
    the pair entry IN PLACE:

    * Each child device keeps the single's ``(DOMAIN, MAC)`` identifier. The
      existing customized device is explicitly transferred to the pair entry and
      nested under its synthetic parent, preserving the SAME registry object (id,
      name_by_user, area). This also works with Home Assistant's single-owner
      device model, where registering the pair first creates a separate placeholder.
    * Each entity row is re-pointed ``config_entry_id`` -> pair BEFORE the original
      is removed, so clearing the original config entry no longer deletes it (HA
      deletes entity rows indexed by the removed config entry). The paired platform
      later adopts the row by unique_id (same ``entity_id``, history, name, area)
      instead of creating a new one.

    Provenance is each child descriptor's ``absorbed_entry_id`` (recorded by the
    pairing wizard). Idempotent: on a reload the originals are already gone, so each
    lookup misses and this is a no-op; pairs created by the old remove-then-create
    path carry no ``absorbed_entry_id`` and are skipped.

    Returns the set of child sides whose original single was actually absorbed
    here, so the caller can retry those sides' connect now that their (single-link)
    BLE has been freed.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    parent = _device_for_entry_and_identifier(
        dev_reg,
        entry.entry_id,
        (DOMAIN, entry.data[CONF_PAIR_ID]),
    )
    absorbed_sides: set[str] = set()
    for child in iter_children(entry.data):
        absorbed_id = child.get(KEY_ABSORBED_ENTRY_ID)
        if not absorbed_id:
            continue
        original = hass.config_entries.async_get_entry(absorbed_id)
        if original is None or is_paired(original.data):
            # Already absorbed (e.g. a reload) or no longer a plain single —
            # nothing to move.
            continue
        # Best-effort per side: this runs after the live coordinator is already in
        # hass.data, so a registry error must NOT propagate (it would fail setup
        # and leak the coordinator's open BLE links) nor abort the other side. On
        # failure the re-pointing is rolled back so the still-loaded single keeps
        # owning its rows; the side is then absorbed cleanly on the next reload.
        address = child.get(CONF_ADDRESS)
        identifier = (DOMAIN, address) if isinstance(address, str) else None
        original_device = (
            _device_for_entry_and_identifier(dev_reg, absorbed_id, identifier)
            if identifier is not None
            else None
        )
        ownership = _RegistryOwnership(
            entities=tuple(
                (row, entry.entry_id)
                for row in er.async_entries_for_config_entry(ent_reg, absorbed_id)
            ),
            devices=(
                (
                    _DeviceMove(
                        original_device,
                        absorbed_id,
                        entry.entry_id,
                        identifier,
                        parent.id if parent is not None else None,
                    ),
                )
                if original_device is not None and identifier is not None
                else ()
            ),
        )
        try:
            ownership.apply(hass)
            # Now safe to drop the original entry: its entities are re-homed and
            # its device is owned by the pair entry, so HA deletes neither.
            # async_remove() removes the entry even on an unclean platform
            # unload (it returns {"require_restart": True} rather than raising); the
            # rows are already re-homed so the conversion is structurally complete,
            # but surface that case — the original's old entities may linger until a
            # restart (there is nothing to roll back, the entry is already gone).
            removal = await hass.config_entries.async_remove(absorbed_id)
            ownership.finish(hass)
            if removal.get("require_restart"):
                _LOGGER.warning(
                    "Absorbed bed %s did not unload cleanly (require_restart); its "
                    "old entities may linger until Home Assistant restarts",
                    absorbed_id,
                )
        except (Exception, asyncio.CancelledError) as err:
            if hass.config_entries.async_get_entry(absorbed_id) is not None:
                restored = ownership.rollback(hass)
                _LOGGER.exception(
                    "Failed to re-home absorbed bed %s onto paired entry %s; "
                    "rollback %s, will retry on the next reload",
                    absorbed_id,
                    entry.entry_id,
                    "completed" if restored else "incomplete",
                )
            else:
                # Removing the source is the commit point. Never move rows to a
                # config entry that HA has already removed.
                ownership.finish(hass)
                _LOGGER.exception("Absorbed bed %s was removed before removal raised", absorbed_id)
                side = child.get(CONF_SIDE)
                if side:
                    absorbed_sides.add(side)
            if isinstance(err, asyncio.CancelledError):
                raise
            continue
        side = child.get(CONF_SIDE)
        if side:
            absorbed_sides.add(side)
        _LOGGER.info(
            "Re-homed %d entit%s from absorbed bed %s (%s) onto paired entry %s",
            len(ownership.entities),
            "y" if len(ownership.entities) == 1 else "ies",
            original.title,
            absorbed_id,
            entry.entry_id,
        )
    return absorbed_sides


async def async_unpair_entry(hass: HomeAssistant, entry: ConfigEntry) -> list[ConfigEntry]:
    """Split a paired entry into standalone children without recreating entities.

    The pair is unloaded first, each per-side entity row is re-pointed to the
    future standalone entry, and each existing child device is detached from the
    synthetic parent. The original config-entry ids and unique ids are reused
    when provenance is available. Combined parent entities remain owned by the
    pair and are deleted when the pair entry is removed.

    If any standalone entry cannot be added, registry ownership is restored to
    the pair, partially-added singles are removed, and the pair is reloaded.
    """
    if not is_paired(entry.data):
        raise HomeAssistantError("Cannot unpair a standalone bed")

    if entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
        children = iter_children(entry.data)
        if not children:
            raise HomeAssistantError("Single-address pair has no provenance")
        origin_data = single_data_from_child(children[0])
        origin_options = single_options_from_child(children[0])
        origin_title = children[0].get(KEY_ORIGIN_TITLE) or entry.title
        origin_unique_id = children[0].get(KEY_ORIGIN_UNIQUE_ID) or entry.unique_id
        paired_data = dict(entry.data)
        paired_options = dict(entry.options)
        paired_title = entry.title
        paired_unique_id = entry.unique_id
        preserved = set(entry.data.get(KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS, []))
        unloaded = await hass.config_entries.async_unload(entry.entry_id)
        if not unloaded:
            raise HomeAssistantError("Could not unload the bed before reverting sides")
        try:
            hass.config_entries.async_update_entry(
                entry,
                data=origin_data,
                options=origin_options,
                title=origin_title,
                unique_id=origin_unique_id,
            )
            if not await hass.config_entries.async_setup(entry.entry_id):
                raise RuntimeError("standalone entry setup failed")
            registry = er.async_get(hass)
            for row in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
                if row.unique_id not in preserved and row.unique_id.endswith(
                    ("_left", "_right", "_both")
                ):
                    registry.async_remove(row.entity_id)
            devices = dr.async_get(hass)
            for child_device in dr.async_child_entries_for_config_entry(devices, entry.entry_id):
                # Original rows have been adopted by the standalone platforms.
                # Preserve disabled originals too, which may not have loaded.
                parent_id = child_device.parent_device_id
                for row in er.async_entries_for_device(registry, child_device.id, include_disabled_entities=True):
                    if row.unique_id in preserved:
                        registry.async_update_entity(row.entity_id, device_id=parent_id)
                devices.async_remove_device(child_device.id)

        except (Exception, asyncio.CancelledError):
            _LOGGER.exception("Failed to revert single-address paired bed %s", entry.title)
            try:
                await hass.config_entries.async_unload(entry.entry_id)
            except Exception:
                _LOGGER.exception(
                    "Could not unload reverted entry %s during rollback", entry.entry_id
                )
            try:
                hass.config_entries.async_update_entry(
                    entry,
                    data=paired_data,
                    options=paired_options,
                    title=paired_title,
                    unique_id=paired_unique_id,
                )
                if not await hass.config_entries.async_setup(entry.entry_id):
                    _LOGGER.error("Paired entry %s did not reload after rollback", entry.entry_id)
            except Exception:
                _LOGGER.exception("Could not restore paired configuration for %s", entry.entry_id)
            raise
        return [entry]

    children = iter_children(entry.data)
    if len(children) != 2:
        raise HomeAssistantError("Paired bed must contain exactly two sides")

    existing_entries = hass.config_entries.async_entries(DOMAIN)
    occupied_entry_ids = {
        candidate.entry_id for candidate in existing_entries if candidate is not entry
    }
    occupied_unique_ids = {
        candidate.unique_id
        for candidate in existing_entries
        if candidate is not entry and candidate.unique_id is not None
    }
    singles: list[tuple[ConfigEntry, str]] = []
    for child in children:
        address = child.get(CONF_ADDRESS)
        if not isinstance(address, str) or not address:
            raise HomeAssistantError("Paired child is missing its Bluetooth address")
        unique_id = child.get(KEY_ORIGIN_UNIQUE_ID) or address
        if unique_id in occupied_unique_ids:
            raise HomeAssistantError(
                f"Cannot unpair because standalone id {unique_id} already exists"
            )
        origin_entry_id = child.get(KEY_ABSORBED_ENTRY_ID)
        if origin_entry_id in occupied_entry_ids:
            raise HomeAssistantError(
                f"Cannot restore original config entry {origin_entry_id}: id is in use"
            )
        title = child.get(KEY_ORIGIN_TITLE) or child.get("name") or address
        source = child.get(KEY_ORIGIN_SOURCE) or SOURCE_IMPORT
        single = ConfigEntry(
            data=single_data_from_child(child),
            # Register both target entry ids before moving registry rows, but do
            # not let async_add() set up their platforms until the transfer is
            # complete. This avoids temporary duplicate entities/devices under
            # Home Assistant's single-owner registries.
            disabled_by=ConfigEntryDisabler.USER,
            discovery_keys=MappingProxyType({}),
            domain=DOMAIN,
            entry_id=origin_entry_id,
            minor_version=1,
            options=single_options_from_child(child),
            source=source,
            subentries_data=(),
            title=title,
            unique_id=unique_id,
            version=entry.version,
        )
        singles.append((single, address))
        occupied_entry_ids.add(single.entry_id)
        occupied_unique_ids.add(unique_id)

    unloaded = await hass.config_entries.async_unload(entry.entry_id)
    if not unloaded:
        raise HomeAssistantError("Could not unload the paired bed before unpairing")
    # Child devices cannot change config-entry ownership. Restore their full
    # records first, then use the same ownership transaction as standalone beds.
    try:
        for child in children:
            device = dr.async_get(hass).async_get_child_device_by_identifier(
                (DOMAIN, child.get(CONF_ADDRESS, "")), entry.entry_id,
            )
            if device is not None:
                await async_restore_full_device(hass, entry, device, child.get(CONF_SIDE, ""))
    except (Exception, asyncio.CancelledError):
        await hass.config_entries.async_setup(entry.entry_id)
        raise

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    child_devices: dict[str, dr.DeviceEntry] = {}
    for single, address in singles:
        device = _device_for_entry_and_identifier(
            dev_reg,
            entry.entry_id,
            (DOMAIN, address),
        )
        if device is not None:
            child_devices[single.entry_id] = device

    pair_rows = list(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    row_owners: dict[str, str] = {}
    for row in pair_rows:
        for single, address in singles:
            device = child_devices.get(single.entry_id)
            if (
                device is not None and row.device_id == device.id
            ) or row.unique_id.upper().startswith(address.upper()):
                row_owners[row.entity_id] = single.entry_id
                break

    ownership = _RegistryOwnership(
        entities=tuple(
            (row, row_owners[row.entity_id]) for row in pair_rows if row.entity_id in row_owners
        ),
        devices=tuple(
            _DeviceMove(
                child_devices[single.entry_id],
                entry.entry_id,
                single.entry_id,
                (DOMAIN, address),
                None,
            )
            for single, address in singles
            if single.entry_id in child_devices
        ),
    )

    try:
        # async_add() normally sets an entry up immediately. These entries are
        # temporarily disabled, so both ids become valid registry owners without
        # racing platform setup against the row transfers below.
        for single, _address in singles:
            await hass.config_entries.async_add(single)

        ownership.apply(hass)

        # Load the restored entries only after their existing device and entity
        # rows belong to them. The setup paths now adopt those rows in place.
        for single, _address in singles:
            if not await hass.config_entries.async_set_disabled_by(single.entry_id, None):
                _LOGGER.info(
                    "Restored bed %s did not load immediately; Home Assistant will retry setup",
                    single.title,
                )

        removal = await hass.config_entries.async_remove(entry.entry_id)
        ownership.finish(hass)
        if removal.get("require_restart"):
            _LOGGER.warning(
                "Paired bed %s required a restart while completing unpair",
                entry.entry_id,
            )
    except (Exception, asyncio.CancelledError):
        # Preserve the triggering exception even if a compensating action fails.
        # Never remove a target that still owns user data after failed rollback.
        if hass.config_entries.async_get_entry(entry.entry_id) is None:
            ownership.finish(hass)
            _LOGGER.exception("Pair %s was removed before unpair removal raised", entry.entry_id)
            raise
        restored = ownership.rollback(hass)
        for single, _address in reversed(singles):
            if hass.config_entries.async_get_entry(single.entry_id) is None:
                continue
            if er.async_entries_for_config_entry(
                ent_reg, single.entry_id
            ) or dr.async_entries_for_config_entry(dev_reg, single.entry_id) or dr.async_child_entries_for_config_entry(dev_reg, single.entry_id):
                restored = False
                _LOGGER.error(
                    "Keeping restored entry %s because rollback left registry ownership there",
                    single.entry_id,
                )
                continue
            try:
                await hass.config_entries.async_remove(single.entry_id)
            except Exception:
                restored = False
                _LOGGER.exception("Could not remove partially restored entry %s", single.entry_id)
        try:
            if not await hass.config_entries.async_setup(entry.entry_id):
                restored = False
                _LOGGER.error("Paired entry %s did not reload after rollback", entry.entry_id)
        except Exception:
            restored = False
            _LOGGER.exception("Could not reload paired entry %s after rollback", entry.entry_id)
        _LOGGER.exception(
            "Failed to unpair %s; registry rollback %s",
            entry.title,
            "completed" if restored else "incomplete",
        )
        raise

    _LOGGER.info(
        "Unpaired %s into standalone entries %s",
        entry.title,
        ", ".join(single.entry_id for single, _ in singles),
    )
    return [single for single, _ in singles]
