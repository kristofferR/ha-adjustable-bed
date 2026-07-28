"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, cast

from homeassistant.components import bluetooth
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .combine_suggestion import async_load_dismissal
from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_KAIDI,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_VIBRADORM,
    BEDTECH_MANUFACTURER_ID,
    BEDTECH_SERVICE_UUID,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_ADV_TYPE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    CONF_KAIDI_VARIANT_SOURCE,
    CONF_MOTOR_COUNT,
    CONF_OCTO_PIN,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PAIR_SCHEMA_VERSION,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_SIDE,
    DOMAIN,
    OCTO_VARIANT_STAR2,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    VARIANT_AUTO,
    connection_gated_by_bond,
    requires_pairing,
)
from .coordinator import AdjustableBedCoordinator, ChildEntryView
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .paired_coordinator import PairedBedCoordinator, SingleAddressPairedCoordinator
from .pairing import (
    KEY_ABSORBED_ENTRY_ID,
    KEY_ORIGIN_SOURCE,
    KEY_ORIGIN_TITLE,
    KEY_ORIGIN_UNIQUE_ID,
    KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS,
    get_child,
    is_paired,
    iter_children,
    single_data_from_child,
    single_options_from_child,
    with_updated_child,
)
from .repairs import (
    async_refresh_combine_beds_issue,
    async_setup_combine_beds_issue,
    async_track_combine_beds_issue,
)
from .services import (
    ATTR_CAPTURE_DURATION,
    ATTR_DIRECTION,
    ATTR_DURATION_MS,
    ATTR_INCLUDE_LOGS,
    ATTR_MOTOR,
    ATTR_POSITION,
    ATTR_PRESET,
    ATTR_SIDE,
    ATTR_TARGET_ADDRESS,
    DEFAULT_CAPTURE_DURATION,
    MAX_CAPTURE_DURATION,
    MAX_TIMED_MOVE_DURATION_MS,
    MIN_CAPTURE_DURATION,
    MIN_TIMED_MOVE_DURATION_MS,
    SERVICE_GENERATE_SUPPORT_BUNDLE,
    SERVICE_GOTO_PRESET,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_POSITION,
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    TIMED_MOVE_MOTOR_OPTIONS,
    async_register_services,
)
from .unsupported import (
    async_clear_unsupported_device_issues,
    clear_octo_pin_required_issue,
    create_pairing_required_issue,
)

# Re-exported for backwards compatibility: these moved to .services, but are
# imported from the package root by tests and by downstream automations.
__all__ = [
    "ATTR_CAPTURE_DURATION",
    "ATTR_DIRECTION",
    "ATTR_DURATION_MS",
    "ATTR_INCLUDE_LOGS",
    "ATTR_MOTOR",
    "ATTR_POSITION",
    "ATTR_PRESET",
    "ATTR_SIDE",
    "ATTR_TARGET_ADDRESS",
    "DEFAULT_CAPTURE_DURATION",
    "MAX_CAPTURE_DURATION",
    "MAX_TIMED_MOVE_DURATION_MS",
    "MIN_CAPTURE_DURATION",
    "MIN_TIMED_MOVE_DURATION_MS",
    "SERVICE_GENERATE_SUPPORT_BUNDLE",
    "SERVICE_GOTO_PRESET",
    "SERVICE_SAVE_PRESET",
    "SERVICE_SET_POSITION",
    "SERVICE_STOP_ALL",
    "SERVICE_TIMED_MOVE",
    "TIMED_MOVE_MOTOR_OPTIONS",
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Timeout for initial connection at startup.
# Must cover a full connection retry cycle: up to 3 attempts of ~30s each plus
# backoff between them. Beds that are slow to wake (e.g. just repowered) often
# only connect on the second or third attempt; 45s cut the cycle short.
SETUP_TIMEOUT = 120.0
SETUP_CLEANUP_TIMEOUT = 5.0

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Platforms a paired bed (Dual Bed 4.0) sets up. Each builds per-side entities
# against logical child coordinators; single-address pairs keep every entity on
# the one physical MAC device while separate-address pairs use child devices.
PAIRED_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Adjustable Bed integration domain."""
    hass.data.setdefault(DOMAIN, {})

    # Clear obsolete "unsupported BLE device" Repairs issues from older versions
    # that nagged about every discovered non-bed device (feature removed).
    async_clear_unsupported_device_issues(hass)
    await async_load_dismissal(hass)
    async_setup_combine_beds_issue(hass)

    from .download import SupportBundleDownloadView

    hass.http.register_view(SupportBundleDownloadView)

    from .frontend import async_register_frontend

    await async_register_frontend(hass)

    await async_register_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to newer schema versions."""
    _LOGGER.debug(
        "Migrating config entry %s for %s from version %s",
        entry.entry_id,
        entry.title,
        entry.version,
    )

    if entry.version > 4:
        _LOGGER.error(
            "Cannot migrate config entry %s for %s from unsupported future version %s",
            entry.entry_id,
            entry.title,
            entry.version,
        )
        return False

    if entry.version <= 2:
        new_data = {**entry.data}

        # Legacy Vibradorm entries that predate disable_angle_sensing defaulted
        # position feedback to disabled, so entities stayed unavailable unless
        # users manually reconfigured options.
        if (
            new_data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM
            and CONF_DISABLE_ANGLE_SENSING not in new_data
        ):
            new_data[CONF_DISABLE_ANGLE_SENSING] = False
            _LOGGER.info(
                "Migrated %s (%s): enabled angle sensing only for legacy Vibradorm "
                "entries missing disable_angle_sensing (existing user setting left unchanged)",
                entry.title,
                entry.entry_id,
            )

        hass.config_entries.async_update_entry(entry, data=new_data, version=3)

    if entry.version < 4:
        # v3 -> v4: introduce the paired-bed schema (Dual Bed 4.0). STRICT no-op
        # for every existing (non-paired) entry — only the version is stamped, no
        # data is touched — so the migration that runs for *every* entry on
        # upgrade can never corrupt a single bed. Paired entries are created only
        # by the opt-in pairing flow (already at v4) and never reach this branch.
        hass.config_entries.async_update_entry(entry, version=4)

    _LOGGER.debug(
        "Migration complete for config entry %s (%s), now at version %s",
        entry.title,
        entry.entry_id,
        entry.version,
    )
    return True


def _maybe_cache_kaidi_metadata(hass: HomeAssistant, entry: ConfigEntry) -> None:
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


def _async_ensure_device_registry_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
) -> None:
    """Ensure the bed has a device-registry entry even before first connect.

    This keeps device-targeted diagnostics, especially support bundles,
    available when the initial connection fails and Home Assistant leaves the
    config entry in SETUP_RETRY.
    """
    device_registry = dr.async_get(hass)
    device_info = coordinator.device_info
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=device_info.get("identifiers"),
        name=device_info.get("name"),
        manufacturer=device_info.get("manufacturer"),
        model=device_info.get("model"),
    )


async def _async_finish_entry_setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    *,
    schedule_initial_position_read: bool,
) -> bool:
    """Store coordinator, forward platforms, and finish setup."""
    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if schedule_initial_position_read:
        entry.async_create_background_task(
            hass,
            coordinator.async_read_initial_positions(),
            name=f"adjustable_bed_initial_position_read_{entry.entry_id}",
        )

    _LOGGER.info("Adjustable Bed integration setup complete for %s", entry.title)
    return True


async def _async_setup_offline_diagnostic_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    reason: str,
) -> bool:
    """Load a diagnostic entry even when initial BLE connection fails."""
    from .beds.diagnostic import DiagnosticBedController

    _LOGGER.warning(
        "Loading diagnostic entry %s (%s) without an initial BLE connection so "
        "diagnostic actions remain available: %s",
        entry.title,
        entry.data.get(CONF_ADDRESS),
        reason,
    )
    coordinator._controller = DiagnosticBedController(coordinator)
    return await _async_finish_entry_setup(
        hass,
        entry,
        coordinator,
        schedule_initial_position_read=False,
    )


# Entry-data keys that must NOT be inherited by a child coordinator: the pair's
# own keys, plus per-side state like the BLE bond marker — inheriting a top-level
# bond marker would poison BOTH sides (one repaired side must not flip the other
# to "already bonded" and skip pairing).
_PAIR_ONLY_KEYS = frozenset(
    {
        CONF_PAIR_ID,
        CONF_PAIR_MODE,
        CONF_PAIR_CHILDREN,
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_SCHEMA_VERSION,
        CONF_PAIR_CONNECTION_MODE,
        CONF_BLE_BOND_ESTABLISHED,
    }
)


def _shared_child_fields(parent_data: Mapping[str, Any]) -> dict[str, Any]:
    """Parent-level config inherited by every child (each descriptor overrides)."""
    return {key: value for key, value in parent_data.items() if key not in _PAIR_ONLY_KEYS}


def _make_child_persist_cb(
    hass: HomeAssistant, entry: ConfigEntry, side: str
) -> Callable[[dict[str, Any]], None]:
    """Route a child's runtime config change back to its parent descriptor.

    Only keys that differ from the CURRENTLY persisted descriptor are written
    (so it stays minimal). Comparing against the live descriptor — not a static
    build-time baseline — means a value reverted to its original is still
    written, instead of leaving a stale override behind.
    """

    def persist(new_child_data: dict[str, Any]) -> None:
        current = get_child(entry.data, side) or {}
        # Parent options now flow into the child view's `.data`; never write
        # those option-managed keys back into the per-side descriptor (they'd
        # become a stale per-side override that shadows future option edits).
        option_keys = set(entry.options)
        delta = {
            key: value
            for key, value in new_child_data.items()
            if current.get(key) != value and key not in option_keys
        }
        if not delta:
            return
        hass.config_entries.async_update_entry(
            entry, data=with_updated_child(entry.data, side, delta)
        )

    return persist


def _build_paired_children(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, AdjustableBedCoordinator]:
    """Build one child coordinator per side from the paired entry's descriptors."""
    shared = _shared_child_fields(entry.data)
    children: dict[str, AdjustableBedCoordinator] = {}
    for side in PAIR_SIDES:
        descriptor = get_child(entry.data, side)
        if descriptor is None:
            continue
        child_data: dict[str, Any] = {**shared, **descriptor}
        view = ChildEntryView(entry, child_data, _make_child_persist_cb(hass, entry, side))
        # The view duck-types a ConfigEntry for the coordinator's purposes.
        children[side] = AdjustableBedCoordinator(hass, cast("ConfigEntry", view))
    return children


def _async_ensure_paired_device_registry(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PairedBedCoordinator
) -> None:
    """Eagerly create the synthetic parent device and its child sub-devices.

    Created before the first connect so the device (and its diagnostics) survive
    a half-available pair or a SETUP_RETRY.
    """
    registry = dr.async_get(hass)
    parent_info = coordinator.device_info
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=parent_info.get("identifiers"),
        name=parent_info.get("name"),
        manufacturer=parent_info.get("manufacturer"),
        model=parent_info.get("model"),
    )
    parent_identifier = (DOMAIN, coordinator.pair_id)
    for child in coordinator.children.values():
        child_info = child.device_info
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=child_info.get("identifiers"),
            name=child_info.get("name"),
            manufacturer=child_info.get("manufacturer"),
            model=child_info.get("model"),
            via_device=parent_identifier,
        )


async def _async_release_absorbed_singles(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Disconnect (but do NOT remove) the original singles a single-connection pair
    is about to absorb, freeing their one-link BLE before the pair connects.

    Octo holds a single BLE link per bed and keeps it alive via the PIN keepalive,
    so a still-loaded original NEVER idle-disconnects on its own — and the paired
    child connects to the SAME MAC, so without this it could never open the link and
    the pair would hang in setup retry. Concurrent pairs (Linak) don't need this:
    their originals idle-disconnect and the post-absorb retry self-heals.

    The originals stay LOADED config entries (re-homed + removed only after a
    successful connect), so a failed pair setup still leaves the user two working
    singles that reconnect on demand. Best-effort: a failed release just means the
    pair's connect retries.
    """
    for child in iter_children(entry.data):
        absorbed_id = child.get(KEY_ABSORBED_ENTRY_ID)
        if not absorbed_id:
            continue
        original = hass.config_entries.async_get_entry(absorbed_id)
        if original is None or is_paired(original.data):
            continue
        original_coordinator = hass.data.get(DOMAIN, {}).get(absorbed_id)
        if not isinstance(original_coordinator, AdjustableBedCoordinator):
            continue
        try:
            await original_coordinator.async_disconnect("absorbed_by_pair")
            _LOGGER.debug(
                "Released absorbed single %s's BLE link before paired connect",
                absorbed_id,
            )
        except Exception:  # noqa: BLE001 - best-effort; the pair connect retries
            _LOGGER.debug("Could not pre-release absorbed single %s", absorbed_id)


async def _async_rehome_absorbed_singles(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    """Re-home absorbed single entries' registry rows onto the pair, then remove them.

    Conversion is ADDITIVE. Instead of deleting each original single entry's
    registry rows and letting the paired platforms recreate them (which would
    reset per-side history and customizations), this moves the existing rows onto
    the pair entry IN PLACE:

    * Each child device already shares the single's ``(DOMAIN, MAC)`` identifier,
      so ``_async_ensure_paired_device_registry`` (run earlier in setup) merged the
      pair's config-entry id into the existing device and nested it under the
      synthetic parent. Removing the original then only drops the original's
      config-entry id, leaving the SAME device object (id, name_by_user, area)
      alive.
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
        rehomed_entity_ids: list[str] = []
        try:
            # Re-point the original's entity rows onto the pair first. After this
            # they are indexed under the pair, not the original, so removing the
            # original config entry below clears none of them.
            for reg_entry in er.async_entries_for_config_entry(ent_reg, absorbed_id):
                ent_reg.async_update_entity(reg_entry.entity_id, config_entry_id=entry.entry_id)
                rehomed_entity_ids.append(reg_entry.entity_id)
            # Now safe to drop the original entry: its entities are re-homed and
            # its device still carries the pair's config entry, so HA deletes
            # neither. async_remove() removes the entry even on an unclean platform
            # unload (it returns {"require_restart": True} rather than raising); the
            # rows are already re-homed so the conversion is structurally complete,
            # but surface that case — the original's old entities may linger until a
            # restart (there is nothing to roll back, the entry is already gone).
            removal = await hass.config_entries.async_remove(absorbed_id)
            if removal.get("require_restart"):
                _LOGGER.warning(
                    "Absorbed bed %s did not unload cleanly (require_restart); its "
                    "old entities may linger until Home Assistant restarts",
                    absorbed_id,
                )
        except Exception:  # noqa: BLE001 - re-home must not abort paired setup
            # Roll the rows back onto the still-loaded single. Otherwise it would
            # own none of its rows while its live entities still hold the
            # {MAC}_{key} unique_ids, and the paired platforms would adopt the same
            # rows — duplicate/missing controls. Restoring config_entry_id keeps
            # the side a consistent single, retried cleanly on the next reload.
            for entity_id in rehomed_entity_ids:
                try:
                    ent_reg.async_update_entity(entity_id, config_entry_id=absorbed_id)
                except Exception:  # noqa: BLE001 - best-effort rollback
                    _LOGGER.debug(
                        "Rollback of re-homed row %s to %s failed",
                        entity_id,
                        absorbed_id,
                    )
            _LOGGER.exception(
                "Failed to re-home absorbed bed %s onto paired entry %s; rolled "
                "back, will retry on the next reload",
                absorbed_id,
                entry.entry_id,
            )
            continue
        side = child.get(CONF_SIDE)
        if side:
            absorbed_sides.add(side)
        _LOGGER.info(
            "Re-homed %d entit%s from absorbed bed %s (%s) onto paired entry %s",
            len(rehomed_entity_ids),
            "y" if len(rehomed_entity_ids) == 1 else "ies",
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
        preserved = set(
            entry.data.get(KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS, [])
        )
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
            for row in list(
                er.async_entries_for_config_entry(registry, entry.entry_id)
            ):
                if row.unique_id not in preserved and row.unique_id.endswith(
                    ("_left", "_right", "_both")
                ):
                    registry.async_remove(row.entity_id)
        except Exception:
            _LOGGER.exception(
                "Failed to revert single-address paired bed %s", entry.title
            )
            with contextlib.suppress(Exception):
                await hass.config_entries.async_unload(entry.entry_id)
            hass.config_entries.async_update_entry(
                entry,
                data=paired_data,
                options=paired_options,
                title=paired_title,
                unique_id=paired_unique_id,
            )
            with contextlib.suppress(Exception):
                await hass.config_entries.async_setup(entry.entry_id)
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

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    parent = dev_reg.async_get_device(identifiers={(DOMAIN, entry.data[CONF_PAIR_ID])})
    child_devices: dict[str, dr.DeviceEntry] = {}
    for single, address in singles:
        device = dev_reg.async_get_device(identifiers={(DOMAIN, address)})
        if device is not None:
            child_devices[single.entry_id] = device

    pair_rows = list(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    row_owners: dict[str, str] = {}
    for row in pair_rows:
        for single, address in singles:
            device = child_devices.get(single.entry_id)
            if row.device_id == getattr(device, "id", None) or row.unique_id.upper().startswith(
                address.upper()
            ):
                row_owners[row.entity_id] = single.entry_id
                break

    unloaded = await hass.config_entries.async_unload(entry.entry_id)
    if not unloaded:
        raise HomeAssistantError("Could not unload the paired bed before unpairing")

    try:
        for single, _address in singles:
            device = child_devices.get(single.entry_id)
            await hass.config_entries.async_add(single)
            if device is not None:
                dev_reg.async_update_device(device.id, via_device_id=None)

        # Entity-registry validation only permits ownership by config entries
        # already known to HA. Add both singles first, then explicitly re-home
        # every per-side row (platform setup normally adopts them by unique_id;
        # this makes the ownership transition deterministic).
        for entity_id, owner_entry_id in row_owners.items():
            ent_reg.async_update_entity(entity_id, config_entry_id=owner_entry_id)

        removal = await hass.config_entries.async_remove(entry.entry_id)
        if removal.get("require_restart"):
            _LOGGER.warning(
                "Paired bed %s required a restart while completing unpair",
                entry.entry_id,
            )
    except Exception:
        for entity_id in row_owners:
            if ent_reg.async_get(entity_id) is not None:
                ent_reg.async_update_entity(entity_id, config_entry_id=entry.entry_id)
        for single, _address in reversed(singles):
            if hass.config_entries.async_get_entry(single.entry_id) is not None:
                with contextlib.suppress(Exception):
                    await hass.config_entries.async_remove(single.entry_id)
        for single, _address in singles:
            device = child_devices.get(single.entry_id)
            if device is not None:
                dev_reg.async_update_device(
                    device.id,
                    add_config_entry_id=entry.entry_id,
                    remove_config_entry_id=single.entry_id,
                    via_device_id=parent.id if parent is not None else None,
                )
        if hass.config_entries.async_get_entry(entry.entry_id) is not None:
            with contextlib.suppress(Exception):
                await hass.config_entries.async_setup(entry.entry_id)
        _LOGGER.exception("Failed to unpair %s; restored paired registry ownership", entry.title)
        raise

    _LOGGER.info(
        "Unpaired %s into standalone entries %s",
        entry.title,
        ", ".join(single.entry_id for single, _ in singles),
    )
    return [single for single, _ in singles]


async def _async_setup_paired_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a paired (Dual Bed 4.0) entry as one logical device."""
    _LOGGER.info(
        "Setting up paired bed %s (pair_id=%s, mode=%s, sides=%s)",
        entry.title,
        entry.data.get(CONF_PAIR_ID),
        entry.data.get(CONF_PAIR_MODE),
        [child.get(CONF_SIDE) for child in entry.data.get(CONF_PAIR_CHILDREN, [])],
    )

    if entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
        return await _async_setup_single_address_paired_entry(hass, entry)

    children = _build_paired_children(hass, entry)
    if not children:
        raise ConfigEntryNotReady("Paired bed has no child sides configured")

    coordinator = PairedBedCoordinator(hass, entry, children)
    _async_ensure_paired_device_registry(hass, entry, coordinator)

    async def _pairing_repairs_for_unconnected() -> None:
        # Surface a per-side pairing repair for any side that needs OS-level BLE
        # pairing and didn't connect — like a single bed does. Run this BEFORE any
        # abort (timeout / no-side-connected) so a paired bonding bed (OKIN/Leggett)
        # whose sides all fail to pair still prompts the user instead of silently
        # retrying forever.
        for child in coordinator.children.values():
            if not child.is_connected:
                await _maybe_create_pairing_issue_for(hass, child)

    # Single-connection beds (Octo) hold one BLE link per bed and keep it alive via
    # the PIN keepalive, so a still-loaded original would block the paired child
    # (same MAC) from ever connecting — release the originals' links first. They
    # stay loaded config entries, re-homed/removed only after a successful connect,
    # so a failed setup still leaves two working singles.
    if coordinator.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
        await _async_release_absorbed_singles(hass, entry)

    try:
        async with asyncio.timeout(SETUP_TIMEOUT):
            connected = await coordinator.async_connect()
    except TimeoutError:
        # The coordinator isn't in hass.data yet, so the unload path won't run —
        # shut it down here or a side that already connected keeps its BLE link
        # alive across SETUP_RETRY.
        await _pairing_repairs_for_unconnected()
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(
            f"Paired bed {entry.title} timed out connecting after {SETUP_TIMEOUT:.0f}s"
        ) from None

    # Half-available is fine, but surface pairing repairs for any unconnected side
    # first — including the all-offline case, which aborts below.
    await _pairing_repairs_for_unconnected()
    if not connected:
        # If NO side connected there is nothing to control yet — retry like a
        # single bed.
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(f"No side of paired bed {entry.title} could be connected")

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # At least one child connected, so the pair can provide controls. ONLY NOW
    # absorb the original single entries — re-home their entity/device registry
    # rows onto the pair, then remove them. Deferring this until after a successful
    # connect keeps the originals (and their live controls) intact on the timeout /
    # no-side-connected paths above: if the pair can't load, the user keeps two
    # working beds, and the still-loaded originals idle-disconnect on their own so a
    # later retry's children can take the single-link BLE. Must run before
    # forwarding platforms so the originals' live entities are torn down first,
    # freeing the shared {address}_{key} unique_ids the paired platforms reuse.
    # No-op on reload (originals already gone).
    absorbed_sides = await _async_rehome_absorbed_singles(hass, entry)
    # A just-absorbed concurrent side may have failed its initial connect ONLY
    # because its original single was still holding the (single-link) BLE — which
    # the absorb above has now freed. Retry such a side once so a non-offline-
    # mintable side (an auto-detected Richmat/L&P/Keeson variant) gets its live
    # controller and exposes entities, instead of staying empty until a reload.
    # Skip in sequential mode (Octo), which deliberately releases each side's link
    # and mints offline sides from the pairing-time capability snapshot.
    if absorbed_sides and coordinator.connection_mode != PAIR_CONNECTION_MODE_SEQUENTIAL:
        for side in absorbed_sides:
            child = coordinator.children.get(side)
            if child is None or child.is_connected:
                continue
            try:
                # Bound the retry like the initial connect above: async_connect can
                # hang, and an unbounded retry would block offline-prime / platform
                # forwarding indefinitely. A timeout just falls back to offline-prime.
                async with asyncio.timeout(SETUP_TIMEOUT):
                    await child.async_connect()
            except Exception:  # noqa: BLE001 - a failed retry just falls back to offline-prime
                _LOGGER.debug("Post-absorb reconnect of %s side failed; priming offline", side)
    # Prime a client-free capability controller for any side that did NOT connect,
    # so its per-side entities are still created up-front (with byte-identical
    # unique_ids); the live controller takes over on reconnect with no reload.
    # Connected sides already have a live controller and are skipped. Bed types
    # whose controller needs a live connection (auto-detected variants) stay as
    # before until they connect.
    for child in coordinator.children.values():
        await child.async_prime_offline_controller()
    await hass.config_entries.async_forward_entry_setups(entry, PAIRED_PLATFORMS)

    # Seed each connected child's positions, like the single-bed path does, so
    # per-side covers don't sit at "unknown" until the first movement.
    for child in coordinator.children.values():
        if child.is_connected:
            entry.async_create_background_task(
                hass,
                child.async_read_initial_positions(),
                name=f"adjustable_bed_paired_initial_read_{child.address}",
            )

    _LOGGER.info("Paired bed setup complete for %s", entry.title)
    return True


async def _async_setup_single_address_paired_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up a left/right/both surface over one physical coordinator."""
    inner = AdjustableBedCoordinator(hass, entry)
    coordinator = SingleAddressPairedCoordinator(hass, entry, inner)
    info = coordinator.device_info
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=info.get("identifiers"),
        name=info.get("name"),
        manufacturer=info.get("manufacturer"),
        model=info.get("model"),
    )
    try:
        async with asyncio.timeout(SETUP_TIMEOUT):
            connected = await coordinator.async_connect()
    except TimeoutError:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(
            f"Single-address paired bed {entry.title} timed out connecting"
        ) from None
    if not connected:
        await _maybe_create_pairing_issue_for(hass, inner)
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(f"Bed {entry.title} could not be connected")

    controller = inner.controller
    if controller is not None and not getattr(
        controller, "supports_single_address_pairing", True
    ):
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(
            "This CBNew protocol has no side selector and cannot expose paired sides"
        )

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PAIRED_PLATFORMS)
    for side, child in coordinator.children.items():
        entry.async_create_background_task(
            hass,
            child.async_read_initial_positions(),
            name=f"adjustable_bed_single_address_initial_read_{side}",
        )
    _LOGGER.info("Single-address paired bed setup complete for %s", entry.title)
    return True


def _bond_gated_unbonded(coordinator: AdjustableBedCoordinator) -> bool:
    """Return whether this coordinator still needs the bond-gated repair path."""
    entry_data = coordinator.entry.data
    return connection_gated_by_bond(
        entry_data.get(CONF_BED_TYPE, ""), entry_data.get(CONF_PROTOCOL_VARIANT)
    ) and not entry_data.get(CONF_BLE_BOND_ESTABLISHED)


def _connection_failure_hint(coordinator: AdjustableBedCoordinator) -> str:
    """Return pairing guidance only while the coordinator remains unbonded."""
    if _bond_gated_unbonded(coordinator):
        return (
            " This bed requires a Bluetooth bond. Open Settings → Repairs and "
            "follow the pairing steps (power-cycle the bed to enter its ~2 minute "
            "pairing mode)."
        )
    return " The integration will retry automatically."


async def _maybe_create_pairing_issue_for(
    hass: HomeAssistant, coordinator: AdjustableBedCoordinator
) -> None:
    """Surface a pairing-required repair issue for one bed (a single bed or one
    side of a pair) when it needs OS-level BLE pairing and the failure looks like
    a pairing problem — not a transient one.

    No-op for beds that don't require pairing, or that are already bonded at the
    OS level (BlueZ), or where the connection simply failed before pairing could
    be attempted (HA retries and pairing happens on the next connect).
    """
    entry_data = coordinator.entry.data
    bed_type = entry_data.get(CONF_BED_TYPE)
    protocol_variant = entry_data.get(CONF_PROTOCOL_VARIANT)
    if not (bed_type and requires_pairing(bed_type, protocol_variant)):
        return

    address = entry_data.get(CONF_ADDRESS, "")
    if address:
        ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
        if ble_device is not None and isinstance(getattr(ble_device, "details", None), dict):
            props = ble_device.details.get("props", {})
            if props.get("Paired") or props.get("Bonded"):
                _LOGGER.debug(
                    "Bed %s is already paired/bonded at OS level — skipping "
                    "pairing repair (connection failure is transient)",
                    address,
                )
                return

    if coordinator.pairing_supported is False:
        await create_pairing_required_issue(
            hass,
            address or "Unknown",
            entry_data.get("name", coordinator.entry.title),
            coordinator.entry.entry_id,
        )
        return

    # LP Comfort Connect / Leggett & Platt Gen2 shows a distinct unbonded
    # failure signature: reconnects time out outside the pairing window while
    # advertisements continue. Surface the repair flow instead of retrying a
    # connection that cannot succeed until the required bond is established.
    if _bond_gated_unbonded(coordinator):
        await create_pairing_required_issue(
            hass,
            address or "Unknown",
            entry_data.get("name", coordinator.entry.title),
            coordinator.entry.entry_id,
        )
        return

    _LOGGER.debug(
        "Bed %s requires pairing but connection failed before pairing could be "
        "attempted — not creating pairing repair (will retry automatically)",
        address,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adjustable Bed from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    async_track_combine_beds_issue(hass, entry)
    await async_register_services(hass)

    # Paired beds (Dual Bed 4.0) route to a dedicated setup path; single-bed
    # entries (no pair_id) fall through to the unchanged logic below.
    if is_paired(entry.data):
        return await _async_setup_paired_entry(hass, entry)

    await _async_maybe_reclassify_bedtech_qrrm_entry(hass, entry)
    _maybe_cache_kaidi_metadata(hass, entry)
    _async_clear_stale_octo_pin_issue(hass, entry)

    _LOGGER.info(
        "Setting up Adjustable Bed integration for %s (address: %s, type: %s, motors: %s, massage: %s)",
        entry.title,
        entry.data.get(CONF_ADDRESS),
        entry.data.get(CONF_BED_TYPE),
        entry.data.get(CONF_MOTOR_COUNT),
        entry.data.get(CONF_HAS_MASSAGE),
    )

    coordinator = AdjustableBedCoordinator(hass, entry)
    _async_ensure_device_registry_entry(hass, entry, coordinator)

    # Connect to the bed with a timeout to avoid blocking startup forever
    _LOGGER.debug("Attempting initial connection to bed (timeout: %.0fs)...", SETUP_TIMEOUT)
    try:
        async with asyncio.timeout(SETUP_TIMEOUT):
            connected = await coordinator.async_connect()
    except TimeoutError:
        try:
            async with asyncio.timeout(SETUP_CLEANUP_TIMEOUT):
                await coordinator.async_disconnect(reason="setup timeout cleanup")
        except TimeoutError:
            _LOGGER.warning(
                "Timed out while disconnecting %s after setup timeout",
                entry.title,
            )
        except Exception as err:  # Best-effort cleanup must not block setup retry
            _LOGGER.warning(
                "Failed to disconnect %s after setup timeout: %s",
                entry.title,
                err,
            )
        await _maybe_create_pairing_issue_for(hass, coordinator)
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason=f"initial connection timed out after {SETUP_TIMEOUT:.0f}s",
            )
        raise ConfigEntryNotReady(
            f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after "
            f"{SETUP_TIMEOUT:.0f}s.{_connection_failure_hint(coordinator)}"
        ) from None

    if not connected:
        await _maybe_create_pairing_issue_for(hass, coordinator)
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason="device was not reachable during initial setup",
            )
        if _bond_gated_unbonded(coordinator):
            raise ConfigEntryNotReady(
                f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}."
                f"{_connection_failure_hint(coordinator)}"
            )
        raise ConfigEntryNotReady(
            f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}. "
            "Check that the bed is powered on and in range of your Bluetooth adapter/proxy."
        )

    # Register the reload listener only after the first successful connect.
    # Setup-time connection logic may persist inferred bond state onto the entry,
    # and we do not want that one-time migration to trigger an immediate reload.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("Successfully connected to bed at %s", entry.data.get(CONF_ADDRESS))
    return await _async_finish_entry_setup(
        hass,
        entry,
        coordinator,
        schedule_initial_position_read=True,
    )


async def _async_maybe_reclassify_bedtech_qrrm_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Correct a persisted Richmat QRRM entry from advertisement evidence.

    QRRM is used by both BedTech white-light controllers and Richmat/Casper RGB
    controllers, and both use the shared FEE9 service. A present manufacturer
    ID 0x4C57 is positive BedTech evidence, but its absence is inconclusive:
    ESPHome proxy snapshots can omit manufacturer data for the same device.
    Connected Device Information provides a second, model-specific correction
    path in the coordinator (issue #410).
    """
    bed_type = entry.data.get(CONF_BED_TYPE)
    if bed_type != BED_TYPE_RICHMAT:
        return

    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return

    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        _LOGGER.debug(
            "Skipping BedTech/Richmat QRRM reclassification for %s (%s): no "
            "advertisement seen yet for %s",
            entry.title,
            entry.entry_id,
            address,
        )
        return

    service_uuids = {uuid.lower() for uuid in (getattr(service_info, "service_uuids", None) or [])}
    if BEDTECH_SERVICE_UUID.lower() not in service_uuids:
        return

    device_name = getattr(service_info, "name", None)
    manufacturer_data = getattr(service_info, "manufacturer_data", None) or {}
    has_bedtech_manufacturer = BEDTECH_MANUFACTURER_ID in manufacturer_data

    if not isinstance(device_name, str) or not device_name.lower().startswith("qrrm"):
        return
    if not has_bedtech_manufacturer:
        _LOGGER.info(
            "QRRM entry %s (%s) has no protocol-specific advertisement evidence: "
            "manufacturer ID 0x%04X is absent (manufacturer IDs seen: %s); "
            "connected Device Information will be checked",
            entry.title,
            entry.entry_id,
            BEDTECH_MANUFACTURER_ID,
            sorted(manufacturer_data) or "none",
        )
        return

    new_data = {
        **entry.data,
        CONF_BED_TYPE: BED_TYPE_BEDTECH,
        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
    }
    new_data.pop(CONF_RICHMAT_REMOTE, None)

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.warning(
        "Corrected config entry %s (%s) from Richmat to BedTech because BLE name %r "
        "uses the shared FEE9 service and advertises BedTech manufacturer ID 0x%04X",
        entry.title,
        entry.entry_id,
        device_name,
        BEDTECH_MANUFACTURER_ID,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Adjustable Bed integration for %s", entry.title)

    platforms = PAIRED_PLATFORMS if is_paired(entry.data) else PLATFORMS
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        _LOGGER.debug("Disconnecting from bed...")
        await coordinator.async_shutdown()
        _LOGGER.info("Successfully unloaded Adjustable Bed integration for %s", entry.title)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up Repairs issues that would otherwise outlive the entry."""
    address = entry.data.get(CONF_ADDRESS)
    if address:
        clear_octo_pin_required_issue(hass, address)
    hass.loop.call_soon(async_refresh_combine_beds_issue, hass)


def _async_clear_stale_octo_pin_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the Octo PIN repair when the configuration already resolves it.

    Runs on every setup, so saving a PIN (which reloads the entry) clears the
    issue even when the bed is unreachable and the connect path never runs.
    """
    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return
    # Star2 has no PIN mechanism at all, and OctoStar2Controller has no
    # pin_locked_without_pin, so the connect path could never clear a stale
    # issue left behind by a variant switch.
    is_standard_octo = entry.data.get(CONF_BED_TYPE) == BED_TYPE_OCTO and entry.data.get(
        CONF_PROTOCOL_VARIANT
    ) != OCTO_VARIANT_STAR2
    if not is_standard_octo or entry.data.get(CONF_OCTO_PIN):
        clear_octo_pin_required_issue(hass, address)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.consume_internal_entry_update(entry):
        # The coordinator recorded its own BLE bond marker. Reloading for that
        # would disconnect the bed, which is fatal for a bed that only grants
        # one connection per pairing window (issue #385).
        _LOGGER.debug(
            "Skipping reload for %s: internal bond-marker update", entry.entry_id
        )
        return
    await hass.config_entries.async_reload(entry.entry_id)
