"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .beds.base import BedController

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_OKIN_CST,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_VIBRADORM,
    BEDS_WITH_POSITION_FEEDBACK,
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
    CONF_PAIR_CHILDREN,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PAIR_SCHEMA_VERSION,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_SIDE,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    KEESON_VARIANT_ERGOMOTION,
    OKIN_CST_POSITION_AXES,
    PAIR_SIDES,
    RICHMAT_REMOTE_AUTO,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    VARIANT_AUTO,
    requires_pairing,
)
from .coordinator import AdjustableBedCoordinator, ChildEntryView
from .detection import detect_richmat_remote_from_name
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .paired_coordinator import PairedBedCoordinator, PairedSideProxy
from .pairing import (
    KEY_ABSORBED_ENTRY_ID,
    get_child,
    is_paired,
    iter_children,
    pair_member_addresses,
    with_updated_child,
)
from .unsupported import create_pairing_required_issue

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Service constants
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"
ATTR_PRESET = "preset"
ATTR_MOTOR = "motor"
ATTR_POSITION = "position"
ATTR_SIDE = "side"
ATTR_TARGET_ADDRESS = "target_address"
ATTR_CAPTURE_DURATION = "capture_duration"
ATTR_INCLUDE_LOGS = "include_logs"
ATTR_DIRECTION = "direction"
ATTR_DURATION_MS = "duration_ms"
TIMED_MOVE_MOTOR_OPTIONS = (
    "back",
    "legs",
    "head",
    "feet",
    "tilt",
    "lumbar",
    "bed_height",
    "stair",
)

# Default capture duration for diagnostics (seconds)
DEFAULT_CAPTURE_DURATION = 120
MIN_CAPTURE_DURATION = 10
MAX_CAPTURE_DURATION = 300

# Timed move duration limits (milliseconds)
MIN_TIMED_MOVE_DURATION_MS = 100
MAX_TIMED_MOVE_DURATION_MS = 30000  # 30 seconds max

# Timeout for initial connection at startup
# Must be long enough to cover at least one full connection attempt (30s) with margin
SETUP_TIMEOUT = 45.0

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
# against the child coordinators. The remaining platforms (climate/light/select)
# are not forwarded for pairs yet; the combine flow blocks beds that expose them
# so their entities are never silently dropped.
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

    from .download import SupportBundleDownloadView

    hass.http.register_view(SupportBundleDownloadView)

    from .frontend import async_register_frontend

    await async_register_frontend(hass)

    await _async_register_services(hass)
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
    return {
        key: value for key, value in parent_data.items() if key not in _PAIR_ONLY_KEYS
    }


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
        view = ChildEntryView(
            entry, child_data, _make_child_persist_cb(hass, entry, side)
        )
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


async def _async_rehome_absorbed_singles(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
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
    """
    ent_reg = er.async_get(hass)
    for child in iter_children(entry.data):
        absorbed_id = child.get(KEY_ABSORBED_ENTRY_ID)
        if not absorbed_id:
            continue
        original = hass.config_entries.async_get_entry(absorbed_id)
        if original is None or is_paired(original.data):
            # Already absorbed (e.g. a reload) or no longer a plain single —
            # nothing to move.
            continue
        # Re-point the original's entity rows onto the pair first. After this they
        # are indexed under the pair, not the original, so removing the original
        # config entry below clears none of them.
        rehomed = 0
        for reg_entry in er.async_entries_for_config_entry(ent_reg, absorbed_id):
            ent_reg.async_update_entity(
                reg_entry.entity_id, config_entry_id=entry.entry_id
            )
            rehomed += 1
        # Now safe to drop the original entry: its entities are re-homed and its
        # device still carries the pair's config entry, so HA deletes neither.
        await hass.config_entries.async_remove(absorbed_id)
        _LOGGER.info(
            "Re-homed %d entit%s from absorbed bed %s (%s) onto paired entry %s",
            rehomed,
            "y" if rehomed == 1 else "ies",
            original.title,
            absorbed_id,
            entry.entry_id,
        )


async def _async_setup_paired_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a paired (Dual Bed 4.0) entry as one logical device."""
    _LOGGER.info(
        "Setting up paired bed %s (pair_id=%s, mode=%s, sides=%s)",
        entry.title,
        entry.data.get(CONF_PAIR_ID),
        entry.data.get(CONF_PAIR_MODE),
        [child.get(CONF_SIDE) for child in entry.data.get(CONF_PAIR_CHILDREN, [])],
    )

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
        raise ConfigEntryNotReady(
            f"No side of paired bed {entry.title} could be connected"
        )

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
    await _async_rehome_absorbed_singles(hass, entry)
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
        ble_device = bluetooth.async_ble_device_from_address(
            hass, address, connectable=True
        )
        if ble_device is not None and isinstance(
            getattr(ble_device, "details", None), dict
        ):
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

    _LOGGER.debug(
        "Bed %s requires pairing but connection failed before pairing could be "
        "attempted — not creating pairing repair (will retry automatically)",
        address,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adjustable Bed from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_services(hass)

    # Paired beds (Dual Bed 4.0) route to a dedicated setup path; single-bed
    # entries (no pair_id) fall through to the unchanged logic below.
    if is_paired(entry.data):
        return await _async_setup_paired_entry(hass, entry)

    await _async_maybe_reclassify_legacy_bedtech_entry(hass, entry)
    _maybe_cache_kaidi_metadata(hass, entry)

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
        await _maybe_create_pairing_issue_for(hass, coordinator)
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason=f"initial connection timed out after {SETUP_TIMEOUT:.0f}s",
            )
        raise ConfigEntryNotReady(
            f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after {SETUP_TIMEOUT:.0f}s. "
            "The integration will retry automatically."
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


async def _async_maybe_reclassify_legacy_bedtech_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Correct legacy BedTech entries that were created for Richmat QRRM beds.

    BedTech and Richmat WiLinke share the FEE9 service, and older versions of
    the integration could persist QRRM devices as `bedtech`. That leaves the
    entry sending BedTech preset/light bytes to a Richmat controller, which is
    why issue #243 reported lounge and light commands either doing nothing or
    triggering the wrong behavior.
    """
    if entry.data.get(CONF_BED_TYPE) != BED_TYPE_BEDTECH:
        return

    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return

    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        return

    service_uuids = {
        uuid.lower() for uuid in (getattr(service_info, "service_uuids", None) or [])
    }
    if BEDTECH_SERVICE_UUID.lower() not in service_uuids:
        return

    device_name = getattr(service_info, "name", None)
    detected_remote = detect_richmat_remote_from_name(device_name)
    if not detected_remote:
        return

    new_data = {
        **entry.data,
        CONF_BED_TYPE: BED_TYPE_RICHMAT,
        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
    }
    if entry.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO) == RICHMAT_REMOTE_AUTO:
        new_data[CONF_RICHMAT_REMOTE] = detected_remote

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.warning(
        "Corrected config entry %s (%s) from BedTech to Richmat because BLE name %r "
        "matches Richmat remote %r on the shared FEE9 service",
        entry.title,
        entry.entry_id,
        device_name,
        detected_remote,
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register Adjustable Bed services."""
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

    def _resolve_sided_target(
        hass: HomeAssistant, device_id: str
    ) -> tuple[AdjustableBedCoordinator | PairedBedCoordinator, str | None] | None:
        """Resolve (coordinator, inferred_side) for a sided service target.

        ``inferred_side`` is the left/right of a targeted paired child sub-device
        (matched by its MAC identifier), or ``None`` for a single bed or the
        paired parent device. Lets a caller targeting one side's device act on
        just that side without passing ``side`` explicitly.
        """
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if not device:
            return None
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator | None = None
        for entry_id in device.config_entries:
            if entry_id in hass.data.get(DOMAIN, {}):
                coordinator = hass.data[DOMAIN][entry_id]
                break
        if coordinator is None:
            return None
        inferred_side: str | None = None
        if isinstance(coordinator, PairedBedCoordinator):
            macs = {
                ident[1].upper() for ident in device.identifiers if ident[0] == DOMAIN
            }
            for side, child in coordinator.children.items():
                if child.address.upper() in macs:
                    inferred_side = side
                    break
        return coordinator, inferred_side

    def _resolve_sided_targets(
        hass: HomeAssistant,
        device_ids: list[str],
        explicit_side: str | None,
    ) -> tuple[
        list[tuple[AdjustableBedCoordinator | PairedBedCoordinator, str]],
        list[str],
    ]:
        """Group sided-service targets by coordinator, merging inferred sides.

        Targeting both of a pair's child devices (or the parent) in one call
        collapses to a single ``both`` fan-out — preserving the both-failure
        contract — instead of two separate side commands. Each coordinator
        appears once in first-seen order. Returns (targets, missing_device_ids).
        """
        ordered: list[int] = []
        by_key: dict[
            int,
            tuple[AdjustableBedCoordinator | PairedBedCoordinator, set[str | None]],
        ] = {}
        missing: list[str] = []
        for device_id in device_ids:
            resolved = _resolve_sided_target(hass, device_id)
            if resolved is None:
                missing.append(device_id)
                continue
            coordinator, inferred_side = resolved
            key = id(coordinator)
            if key not in by_key:
                by_key[key] = (coordinator, set())
                ordered.append(key)
            by_key[key][1].add(inferred_side)

        targets: list[tuple[AdjustableBedCoordinator | PairedBedCoordinator, str]] = []
        for key in ordered:
            coordinator, sides = by_key[key]
            if explicit_side is not None:
                side = explicit_side
            elif sides == {SIDE_LEFT}:
                side = SIDE_LEFT
            elif sides == {SIDE_RIGHT}:
                side = SIDE_RIGHT
            else:
                # parent device (None), both children, or a mix → whole bed.
                side = SIDE_BOTH
            targets.append((coordinator, side))
        return targets, missing

    def _get_support_bundle_target_from_device(
        hass: HomeAssistant, device_id: str
    ) -> tuple[str, AdjustableBedCoordinator | None, ConfigEntry] | None:
        """Resolve support-bundle target details from a device registry ID."""
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if not device:
            return None

        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN:
                continue

            address = entry.data.get(CONF_ADDRESS)
            if not isinstance(address, str) and is_paired(entry.data):
                # Paired entries keep addresses only in pair_children. Resolve to
                # the targeted child sub-device's MAC (else the first member) so
                # the bundle can still capture BLE/GATT for that side by address.
                members = pair_member_addresses(entry.data)
                device_macs = {
                    ident[1].upper()
                    for ident in device.identifiers
                    if ident[0] == DOMAIN
                }
                address = next((m for m in members if m in device_macs), None)
                if address is None and members:
                    # The synthetic parent device (pair_id identifier) covers both
                    # sides; a bundle is per-address, so make the user pick one
                    # side's device instead of silently capturing only the first.
                    raise ServiceValidationError(
                        f"{entry.title} is a paired bed; target one side's device "
                        "for the support bundle.",
                        translation_domain=DOMAIN,
                        translation_key="bundle_needs_side_for_paired",
                        translation_placeholders={"device_name": entry.title},
                    )
            if not isinstance(address, str):
                continue

            coordinator: AdjustableBedCoordinator | None = None
            stored = hass.data.get(DOMAIN, {}).get(entry_id)
            if isinstance(stored, PairedBedCoordinator):
                # Reuse the matching live child coordinator so the bundle pauses
                # and reuses its connection instead of opening a second BLE link
                # (single-connection beds can't take two).
                for child in stored.children.values():
                    if child.address.upper() == address.upper():
                        coordinator = child
                        break
            else:
                coordinator = cast("AdjustableBedCoordinator | None", stored)
            return address, coordinator, entry

        return None

    async def _get_controller_for_service(
        coordinator: AdjustableBedCoordinator,
    ) -> BedController:
        """Return an active controller for service validation/execution.

        Service calls may arrive while the coordinator is idle-disconnected and
        controller is None. Reconnect first so capability checks don't fail with
        a false "not supported" error.
        """
        controller = coordinator.controller
        if controller is not None:
            return controller

        _LOGGER.debug(
            "No active controller for %s during service call; attempting reconnect",
            coordinator.name,
        )
        connected = await coordinator.async_ensure_connected(reset_timer=False)
        controller = coordinator.controller
        if not connected or controller is None:
            raise ServiceValidationError(
                f"Device '{coordinator.name}' is currently unavailable (unable to connect)",
            )
        return controller

    def _command_targets(
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator, side: str
    ) -> list[AdjustableBedCoordinator]:
        """Return the per-side coordinators a sided command must validate.

        For a paired bed this is the child coordinator(s) for ``side``; the
        caller validates each (pre-flight all sides before commanding any) and
        then executes via the paired coordinator's fan-out. For a single bed,
        ``left``/``right`` is rejected and ``both`` maps to the one controller.
        """
        if isinstance(coordinator, PairedBedCoordinator):
            if side == SIDE_BOTH:
                return list(coordinator.children.values())
            child = coordinator.child_for_side(side)
            if child is None:
                raise ServiceValidationError(
                    f"This bed has no {side} side",
                    translation_domain=DOMAIN,
                    translation_key="side_not_available",
                    translation_placeholders={"side": side},
                )
            return [child]

        if side != SIDE_BOTH:
            raise ServiceValidationError(
                "This is a single bed; the Left/Right/Both option only applies to "
                "paired beds.",
                translation_domain=DOMAIN,
                translation_key="side_not_supported",
            )
        return [coordinator]

    async def _execute_sided(
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
        side: str,
        command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool = True,
    ) -> None:
        """Run a command on the targeted side(s).

        A paired bed fans out (with the both-failure stop-the-other contract); a
        single bed runs exactly as before.
        """
        if isinstance(coordinator, PairedBedCoordinator):
            await coordinator.async_execute_controller_command(
                command_fn, side=side, cancel_running=cancel_running
            )
        else:
            await coordinator.async_execute_controller_command(
                command_fn, cancel_running=cancel_running
            )

    async def _release_preflighted(
        preflighted: list[
            tuple[
                AdjustableBedCoordinator | PairedBedCoordinator,
                AdjustableBedCoordinator,
            ]
        ],
    ) -> None:
        """Give every bed/side connected during a failed pre-flight a normal idle
        disconnect, so a validation abort doesn't leave a BLE link open with no
        idle timer (the command finalizer that would reset it never ran). Applies
        to single beds too, not just paired sides — both reconnect with
        reset_timer=False during validation."""
        for _coordinator, target in preflighted:
            if target.is_connected:
                with contextlib.suppress(Exception):
                    await target.async_ensure_connected(reset_timer=True)

    def _single_bed_for_service(
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
        inferred_side: str | None,
        service: str,
    ) -> AdjustableBedCoordinator:
        """Resolve a per-motor service target to one coordinator.

        These services drive a single bed's motors directly (controller/motor
        specs), so for a paired bed a call that targets one side's child device
        routes to that child; targeting the paired parent (no side) is rejected
        with guidance to pick a side. Avoids a raw AttributeError on
        PairedBedCoordinator and keeps the services usable after pairing.
        """
        if isinstance(coordinator, PairedBedCoordinator):
            if inferred_side is not None:
                child = coordinator.child_for_side(inferred_side)
                if child is not None:
                    # Wrap so the per-motor service routes writes through the
                    # parent (pair lock) yet reads the child's entry/controller.
                    return cast(
                        "AdjustableBedCoordinator",
                        PairedSideProxy(coordinator, child, inferred_side),
                    )
            raise ServiceValidationError(
                f"{coordinator.name} is a paired bed; target one side's device "
                f"for {service}.",
                translation_domain=DOMAIN,
                translation_key="service_needs_side_for_paired",
                translation_placeholders={
                    "device_name": coordinator.name,
                    "service": service,
                },
            )
        return coordinator

    async def handle_goto_preset(call: ServiceCall) -> None:
        """Handle goto_preset service call."""
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        explicit_side = call.data.get(ATTR_SIDE)

        _LOGGER.info(
            "Service goto_preset called: preset=%d (side=%s)", preset, explicit_side
        )

        targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
        if missing:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {missing[0]}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": missing[0]},
            )
        # Phase 1: validate the preset on EVERY targeted side before moving any
        # bed, so a multi-target call never half-executes.
        preflighted: list[
            tuple[
                AdjustableBedCoordinator | PairedBedCoordinator,
                AdjustableBedCoordinator,
            ]
        ] = []
        try:
            for coordinator, side in targets:
                for target in _command_targets(coordinator, side):
                    controller = await _get_controller_for_service(target)
                    preflighted.append((coordinator, target))
                    if not getattr(controller, "supports_memory_presets", False):
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not support memory presets",
                            translation_domain=DOMAIN,
                            translation_key="memory_presets_not_supported",
                            translation_placeholders={"device_name": target.name},
                        )
                    slot_count = getattr(controller, "memory_slot_count", 4)
                    if preset > slot_count:
                        raise ServiceValidationError(
                            f"Device '{target.name}' only supports memory presets 1-{slot_count}. "
                            f"Preset {preset} is not available for this bed type.",
                            translation_domain=DOMAIN,
                            translation_key="invalid_preset_number",
                            translation_placeholders={
                                "device_name": target.name,
                                "max_preset": str(slot_count),
                                "requested_preset": str(preset),
                            },
                        )
        except ServiceValidationError:
            await _release_preflighted(preflighted)
            raise

        # Phase 2: every target validated — now move them. If one bed's command
        # fails, release the still-connected preflighted beds that never ran (and
        # so never reset their idle timer) before propagating.
        try:
            for coordinator, side in targets:
                await _execute_sided(
                    coordinator,
                    side,
                    lambda ctrl, p=preset: ctrl.preset_memory(p),  # type: ignore[misc]
                )
        except Exception:
            await _release_preflighted(preflighted)
            raise

    async def handle_save_preset(call: ServiceCall) -> None:
        """Handle save_preset service call."""
        preset = call.data[ATTR_PRESET]
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        explicit_side = call.data.get(ATTR_SIDE)

        _LOGGER.info(
            "Service save_preset called: preset=%d (side=%s)", preset, explicit_side
        )

        targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
        if missing:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID {missing[0]}",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": missing[0]},
            )
        # Phase 1: validate that every targeted side can program this slot before
        # programming any, so a multi-target call never half-executes.
        preflighted: list[
            tuple[
                AdjustableBedCoordinator | PairedBedCoordinator,
                AdjustableBedCoordinator,
            ]
        ] = []
        try:
            for coordinator, side in targets:
                for target in _command_targets(coordinator, side):
                    controller = await _get_controller_for_service(target)
                    preflighted.append((coordinator, target))
                    if not getattr(controller, "supports_memory_programming", False):
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not support programming memory presets",
                            translation_domain=DOMAIN,
                            translation_key="memory_programming_not_supported",
                            translation_placeholders={"device_name": target.name},
                        )
                    slot_count = getattr(controller, "memory_slot_count", 4)
                    if preset > slot_count:
                        raise ServiceValidationError(
                            f"Device '{target.name}' only supports memory presets 1-{slot_count}. "
                            f"Preset {preset} is not available for this bed type.",
                            translation_domain=DOMAIN,
                            translation_key="invalid_preset_number",
                            translation_placeholders={
                                "device_name": target.name,
                                "max_preset": str(slot_count),
                                "requested_preset": str(preset),
                            },
                        )
        except ServiceValidationError:
            await _release_preflighted(preflighted)
            raise

        # Phase 2: every target validated — now program them. Release any
        # still-connected preflighted bed that never ran if one fails.
        try:
            for coordinator, side in targets:
                await _execute_sided(
                    coordinator,
                    side,
                    lambda ctrl, p=preset: ctrl.program_memory(p),  # type: ignore[misc]
                    cancel_running=False,
                )
        except Exception:
            await _release_preflighted(preflighted)
            raise

    async def handle_stop_all(call: ServiceCall) -> None:
        """Handle stop_all service call."""
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        explicit_side = call.data.get(ATTR_SIDE)

        _LOGGER.info("Service stop_all called (side=%s)", explicit_side)

        targets, missing_device_ids = _resolve_sided_targets(
            hass, device_ids, explicit_side
        )

        async def _stop_one(
            coordinator: AdjustableBedCoordinator | PairedBedCoordinator, side: str
        ) -> None:
            # Validate that side applies (rejects left/right on a single bed).
            _command_targets(coordinator, side)
            if isinstance(coordinator, PairedBedCoordinator):
                await coordinator.async_stop_command(side=side)
            else:
                await coordinator.async_stop_command()

        # STOP is a safety action: attempt every target before surfacing an
        # error, so one bed's failure never leaves another still moving.
        results = await asyncio.gather(
            *(_stop_one(coordinator, side) for coordinator, side in targets),
            return_exceptions=True,
        )
        stop_errors = [r for r in results if isinstance(r, BaseException)]

        if missing_device_ids:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device(s) with ID(s): {', '.join(missing_device_ids)}",
                translation_domain=DOMAIN,
                translation_key="devices_not_found",
                translation_placeholders={"device_ids": ", ".join(missing_device_ids)},
            )

        if stop_errors:
            # Every target was attempted; surface the first failure.
            raise stop_errors[0]

    # Optional left/right/both target (paired beds). No default: when omitted, a
    # call that targets one side's child device acts on just that side, otherwise
    # it falls back to 'both' — so single-bed automations are unchanged.
    side_field = {
        vol.Optional(ATTR_SIDE): vol.In([SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH])
    }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
                **side_field,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        handle_save_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
                **side_field,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL,
        handle_stop_all,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                **side_field,
            }
        ),
    )

    @contextlib.asynccontextmanager
    async def _release_idle_on_validation_failure(
        coordinator: AdjustableBedCoordinator,
    ) -> AsyncIterator[None]:
        """Release a bed reconnected for a per-motor service if validation fails.

        _get_controller_for_service reconnects with reset_timer=False; without
        this an invalid set_position/timed_move would leave the BLE link open
        with no idle timer (the preset preflight path already guards this way)."""
        try:
            yield
        except ServiceValidationError:
            if coordinator.is_connected:
                with contextlib.suppress(Exception):
                    await coordinator.async_ensure_connected(reset_timer=True)
            raise

    async def handle_set_position(call: ServiceCall) -> None:
        """Handle set_position service call."""
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        motor = call.data[ATTR_MOTOR]
        position = call.data[ATTR_POSITION]

        _LOGGER.info(
            "Service set_position called: motor=%s, position=%.1f%%",
            motor,
            position,
        )

        for device_id in device_ids:
            resolved = _resolve_sided_target(hass, device_id)
            if resolved is None:
                raise ServiceValidationError(
                    f"Could not find Adjustable Bed device with ID {device_id}",
                    translation_domain=DOMAIN,
                    translation_key="device_not_found",
                    translation_placeholders={"device_id": device_id},
                )
            coordinator = _single_bed_for_service(
                resolved[0], resolved[1], "set_position"
            )
            async with _release_idle_on_validation_failure(coordinator):
                controller = await _get_controller_for_service(coordinator)

                # Bed type / motor count come from the coordinator's own entry (the
                # child's ChildEntryView for a paired-side target — children aren't in
                # hass.data, so don't scan it).
                entry = coordinator.entry
                bed_type = entry.data.get(CONF_BED_TYPE)
                motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
                protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
                supports_direct_position_control = bool(
                    getattr(controller, "supports_direct_position_control", False)
                )

                # Validate bed supports position feedback
                # Special case: BED_TYPE_KEESON only supports position feedback with ergomotion variant
                has_position_feedback = bed_type in BEDS_WITH_POSITION_FEEDBACK or (
                    bed_type == BED_TYPE_KEESON
                    and protocol_variant == KEESON_VARIANT_ERGOMOTION
                )
                if not has_position_feedback and not supports_direct_position_control:
                    raise ServiceValidationError(
                        f"Device '{coordinator.name}' (type: {bed_type}) does not support position feedback",
                        translation_domain=DOMAIN,
                        translation_key="position_feedback_not_supported",
                        translation_placeholders={
                            "device_name": coordinator.name,
                            "bed_type": bed_type or "unknown",
                        },
                    )

                # Validate angle sensing is enabled
                if coordinator.disable_angle_sensing:
                    raise ServiceValidationError(
                        f"Angle sensing is disabled for device '{coordinator.name}'",
                        translation_domain=DOMAIN,
                        translation_key="angle_sensing_disabled",
                        translation_placeholders={"device_name": coordinator.name},
                    )

                # Define motor configurations.
                # For Keeson/Ergomotion: only head and feet are valid, they map to back/legs keys.
                # For BOX25: only head and feet are valid, using direct percentage positions.
                # For CST: only back and legs publish position feedback.
                # For Kaidi: direct position writes expose back/legs percentage targets.
                # For standard beds: based on motor_count (2=back/legs, 3=+head, 4=+feet).
                uses_percentage_positions = bed_type in (
                    BED_TYPE_KEESON,
                    BED_TYPE_ERGOMOTION,
                    BED_TYPE_SLEEPYS_BOX25,
                ) or (bed_type == BED_TYPE_KAIDI and supports_direct_position_control)

                if bed_type == BED_TYPE_KAIDI and supports_direct_position_control:
                    valid_motors = {"back", "legs"}
                    motor_configs = {
                        "back": {
                            "position_key": "back",
                            "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                            "max_value": 100.0,
                        },
                        "legs": {
                            "position_key": "legs",
                            "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                            "max_value": 100.0,
                        },
                    }
                elif bed_type in (BED_TYPE_KEESON, BED_TYPE_ERGOMOTION):
                    # Keeson/Ergomotion only have head and feet motors
                    valid_motors = {"head", "feet"}
                    motor_configs = {
                        "head": {
                            "position_key": "back",  # Maps to "back" in position_data
                            "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                            "max_value": 100.0,  # Percentage
                        },
                        "feet": {
                            "position_key": "legs",  # Maps to "legs" in position_data
                            "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                            "max_value": 100.0,  # Percentage
                        },
                    }
                elif bed_type == BED_TYPE_SLEEPYS_BOX25:
                    valid_motors = {"head", "feet"}
                    motor_configs = {
                        "head": {
                            "position_key": "head",
                            "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                            "max_value": 100.0,
                        },
                        "feet": {
                            "position_key": "feet",
                            "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                            "max_value": 100.0,
                        },
                    }
                elif bed_type == BED_TYPE_OKIN_CST:
                    valid_motors = set(OKIN_CST_POSITION_AXES)
                    motor_configs = {
                        "back": {
                            "position_key": "back",
                            "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                            "max_value": coordinator.get_max_angle("back"),  # Degrees
                        },
                        "legs": {
                            "position_key": "legs",
                            "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                            "max_value": coordinator.get_max_angle("legs"),  # Degrees
                        },
                    }
                else:
                    # Standard beds: motor availability depends on motor_count
                    motor_configs = {
                        "back": {
                            "position_key": "back",
                            "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                            "max_value": coordinator.get_max_angle("back"),  # Degrees
                            "min_motors": 2,
                        },
                        "legs": {
                            "position_key": "legs",
                            "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                            "max_value": coordinator.get_max_angle("legs"),  # Degrees
                            "min_motors": 2,
                        },
                        "head": {
                            "position_key": "head",
                            "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                            "max_value": coordinator.get_max_angle("head"),  # Degrees
                            "min_motors": 3,
                        },
                        "feet": {
                            "position_key": "feet",
                            "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                            "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                            "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                            "max_value": coordinator.get_max_angle("feet"),  # Degrees
                            "min_motors": 4,
                        },
                    }
                    # Filter to valid motors based on motor_count
                    valid_motors = {
                        m for m, cfg in motor_configs.items() if motor_count >= cfg.get("min_motors", 2)
                    }

                # Validate motor is valid for this bed
                if motor not in valid_motors:
                    raise ServiceValidationError(
                        f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                        f"Valid motors: {', '.join(sorted(valid_motors))}",
                        translation_domain=DOMAIN,
                        translation_key="invalid_motor_for_bed_type",
                        translation_placeholders={
                            "motor": motor,
                            "device_name": coordinator.name,
                            "valid_motors": ", ".join(sorted(valid_motors)),
                        },
                    )

                config = motor_configs[motor]
                max_value = config["max_value"]

                # Validate position is in range
                if position < 0 or position > max_value:
                    unit = "%" if uses_percentage_positions else "°"
                    raise ServiceValidationError(
                        f"Position {position} is out of range for motor '{motor}'. "
                        f"Valid range: 0-{max_value}{unit}",
                        translation_domain=DOMAIN,
                        translation_key="invalid_position_range",
                        translation_placeholders={
                            "position": str(position),
                            "motor": motor,
                            "max_value": str(max_value),
                            "unit": unit,
                        },
                    )

                # Call async_seek_position
                await coordinator.async_seek_position(
                    position_key=cast(str, config["position_key"]),
                    target_angle=position,
                    move_up_fn=config["move_up_fn"],  # type: ignore[arg-type]
                    move_down_fn=config["move_down_fn"],  # type: ignore[arg-type]
                    move_stop_fn=config["move_stop_fn"],  # type: ignore[arg-type]
                )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITION,
        handle_set_position,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_MOTOR): vol.In(["back", "legs", "head", "feet"]),
                # No max cap here - per-motor validation handles bed-specific limits
                vol.Required(ATTR_POSITION): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        ),
    )

    async def handle_timed_move(call: ServiceCall) -> None:
        """Handle timed_move service call."""
        device_ids = call.data.get(CONF_DEVICE_ID, [])
        motor = call.data[ATTR_MOTOR]
        direction = call.data[ATTR_DIRECTION]
        duration_ms = call.data[ATTR_DURATION_MS]

        _LOGGER.info(
            "Service timed_move called: motor=%s, direction=%s, duration_ms=%d",
            motor,
            direction,
            duration_ms,
        )

        for device_id in device_ids:
            resolved = _resolve_sided_target(hass, device_id)
            if resolved is None:
                raise ServiceValidationError(
                    f"Could not find Adjustable Bed device with ID {device_id}",
                    translation_domain=DOMAIN,
                    translation_key="device_not_found",
                    translation_placeholders={"device_id": device_id},
                )
            coordinator = _single_bed_for_service(
                resolved[0], resolved[1], "timed_move"
            )
            # Create a narrowed reference for use in closures (mypy doesn't narrow across closures)
            coordinator_: AdjustableBedCoordinator = coordinator
            async with _release_idle_on_validation_failure(coordinator):
                controller = await _get_controller_for_service(coordinator)
                motor_configs = {
                    spec.key: {
                        "move_up_fn": spec.open_fn,
                        "move_down_fn": spec.close_fn,
                        "move_stop_fn": spec.stop_fn,
                    }
                    for spec in controller.motor_control_specs
                    if spec.key in TIMED_MOVE_MOTOR_OPTIONS
                }
                valid_motors = set(motor_configs)

                # Validate motor is valid for this bed
                if motor not in valid_motors:
                    raise ServiceValidationError(
                        f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                        f"Valid motors: {', '.join(sorted(valid_motors))}",
                        translation_domain=DOMAIN,
                        translation_key="invalid_motor_for_bed_type",
                        translation_placeholders={
                            "motor": motor,
                            "device_name": coordinator.name,
                            "valid_motors": ", ".join(sorted(valid_motors)),
                        },
                    )

                config = motor_configs[motor]

                # Get the appropriate move function based on direction
                move_fn = config["move_up_fn"] if direction == "up" else config["move_down_fn"]
                stop_fn = config["move_stop_fn"]

                # Execute timed movement
                # Calculate repeat count: duration_ms / pulse_delay_ms
                # Example: 3500ms on Octo (350ms delay) = 10 repeats
                pulse_delay_ms = coordinator.motor_pulse_delay_ms
                if pulse_delay_ms <= 0:
                    _LOGGER.warning(
                        "Invalid motor_pulse_delay_ms (%d) for device %s, using default 100ms",
                        pulse_delay_ms,
                        coordinator.name,
                    )
                    pulse_delay_ms = 100  # DEFAULT_MOTOR_PULSE_DELAY_MS
                # Round up to honor requested duration as minimum
                calculated_repeat_count = max(1, (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms)

                _LOGGER.debug(
                    "Timed move: duration=%dms, pulse_delay=%dms, repeat_count=%d",
                    duration_ms,
                    pulse_delay_ms,
                    calculated_repeat_count,
                )

                # Store original pulse count to restore after
                original_pulse_count = coordinator.motor_pulse_count

                # Bind closure variables as defaults to avoid late-binding bugs
                async def timed_movement(
                    ctrl: BedController,
                    *,
                    _coordinator: AdjustableBedCoordinator = coordinator_,
                    _move_fn: Callable[..., Coroutine[Any, Any, None]] = move_fn,
                    _stop_fn: Callable[..., Coroutine[Any, Any, None]] = stop_fn,
                    _calculated_repeat_count: int = calculated_repeat_count,
                    _original_pulse_count: int = original_pulse_count,
                ) -> None:
                    """Execute movement for specified duration, always sending stop."""
                    try:
                        # Temporarily set pulse count to calculated value
                        # This is safe because we're inside the command lock
                        _coordinator._motor_pulse_count = _calculated_repeat_count

                        # Call the movement function (uses coordinator's pulse settings)
                        await _move_fn(ctrl)
                    finally:
                        # Restore original pulse count
                        _coordinator._motor_pulse_count = _original_pulse_count

                        # Always send stop command
                        await asyncio.shield(_stop_fn(ctrl))

                await coordinator.async_execute_controller_command(timed_movement)

    hass.services.async_register(
        DOMAIN,
        SERVICE_TIMED_MOVE,
        handle_timed_move,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_MOTOR): vol.In(TIMED_MOVE_MOTOR_OPTIONS),
                vol.Required(ATTR_DIRECTION): vol.In(["up", "down"]),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_TIMED_MOVE_DURATION_MS, max=MAX_TIMED_MOVE_DURATION_MS),
                ),
            }
        ),
    )

    async def handle_generate_support_bundle(call: ServiceCall) -> None:
        """Handle generate_support_bundle service call."""
        from homeassistant.components.persistent_notification import async_create

        from .download import register_download
        from .support_bundle import generate_support_bundle, save_support_bundle

        device_ids = call.data.get(CONF_DEVICE_ID, [])
        target_address = call.data.get(ATTR_TARGET_ADDRESS)
        capture_duration = call.data.get(ATTR_CAPTURE_DURATION, DEFAULT_CAPTURE_DURATION)
        include_logs = call.data.get(ATTR_INCLUDE_LOGS, True)

        address: str | None = None
        coordinator: AdjustableBedCoordinator | None = None
        entry: ConfigEntry | None = None
        selected_device_id: str | None = None

        if target_address:
            from .config_flow import is_valid_mac_address

            address = str(target_address).upper().replace("-", ":")
            if not is_valid_mac_address(address):
                raise ServiceValidationError(
                    f"Invalid MAC address format: {target_address}. "
                    "Please provide a valid MAC address in the format "
                    "XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX.",
                    translation_domain=DOMAIN,
                    translation_key="invalid_mac_address",
                )
            _LOGGER.info(
                "Generating support bundle for unconfigured device at %s",
                address,
            )
        elif device_ids:
            if len(device_ids) > 1:
                raise ServiceValidationError(
                    "Support bundle generation only supports one configured device at a time. "
                    "Select a single device or use target_address for an unconfigured bed.",
                    translation_domain=DOMAIN,
                    translation_key="multiple_device_targets_not_supported",
                )
            # str() narrows the untyped service-call value for the str-typed parameter
            selected_device_id = str(device_ids[0])
            target = _get_support_bundle_target_from_device(hass, selected_device_id)
            if target is not None:
                address, coordinator, entry = target
                device_name = coordinator.name if coordinator is not None else entry.title
                _LOGGER.info(
                    "Generating support bundle for configured device %s at %s",
                    device_name,
                    address,
                )
            else:
                raise ServiceValidationError(
                    f"Could not find Adjustable Bed device with ID: {selected_device_id}. "
                    "Please verify the device is configured and try again.",
                    translation_domain=DOMAIN,
                    translation_key="device_not_found",
                )
        else:
            raise ServiceValidationError(
                "No device_id or target_address was provided. "
                "Please specify either a configured device or a target MAC address.",
                translation_domain=DOMAIN,
                translation_key="missing_target",
            )

        assert address is not None
        try:
            report = await asyncio.wait_for(
                generate_support_bundle(
                    hass,
                    address=address,
                    capture_duration=capture_duration,
                    include_logs=include_logs,
                    coordinator=coordinator,
                    entry=entry,
                    device_id=selected_device_id,
                ),
                timeout=capture_duration + 120,
            )
            filepath = await hass.async_add_executor_job(
                save_support_bundle,
                hass,
                report,
                address,
            )

            download_url = register_download(hass, filepath)
            notification_count = len(report.get("notifications", []))
            async_create(
                hass,
                f"[**Download support bundle**]({download_url})\n\n"
                f"Captured {notification_count} notifications over "
                f"{capture_duration} seconds.\n\n"
                "Attach this JSON file when reporting unsupported or broken beds.\n\n"
                f"File path: `{filepath}`",
                title="Adjustable Bed Support Bundle Ready",
                notification_id=f"adjustable_bed_support_bundle_{address.replace(':', '_').lower()}",
            )
            _LOGGER.info("Support bundle saved to %s", filepath)
        except TimeoutError:
            _LOGGER.exception(
                "Support bundle generation timed out after %d seconds for %s",
                capture_duration + 120,
                address,
            )
            async_create(
                hass,
                f"Support bundle generation timed out after {capture_duration + 120} seconds "
                f"for {address}.\n\n"
                "The BLE diagnostics may be hanging. Check Bluetooth connectivity and try again.",
                title="Adjustable Bed Support Bundle Timeout",
                notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
            )
            raise
        except Exception as err:
            _LOGGER.exception("Failed to generate support bundle for %s", address)
            async_create(
                hass,
                f"Failed to generate support bundle for {address}:\n\n{err}",
                title="Adjustable Bed Support Bundle Error",
                notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
            )
            raise

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_SUPPORT_BUNDLE,
        handle_generate_support_bundle,
        schema=vol.Schema(
            {
                vol.Exclusive(CONF_DEVICE_ID, "target"): cv.ensure_list,
                vol.Exclusive(ATTR_TARGET_ADDRESS, "target"): cv.string,
                vol.Optional(ATTR_CAPTURE_DURATION, default=DEFAULT_CAPTURE_DURATION): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CAPTURE_DURATION, max=MAX_CAPTURE_DURATION),
                ),
                vol.Optional(ATTR_INCLUDE_LOGS, default=True): cv.boolean,
            }
        ),
    )

    _LOGGER.debug("Registered Adjustable Bed services")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Adjustable Bed integration for %s", entry.title)

    platforms = PAIRED_PLATFORMS if is_paired(entry.data) else PLATFORMS
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        coordinator: AdjustableBedCoordinator | PairedBedCoordinator = hass.data[
            DOMAIN
        ].pop(entry.entry_id)
        _LOGGER.debug("Disconnecting from bed...")
        await coordinator.async_shutdown()
        _LOGGER.info("Successfully unloaded Adjustable Bed integration for %s", entry.title)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(entry.entry_id)
