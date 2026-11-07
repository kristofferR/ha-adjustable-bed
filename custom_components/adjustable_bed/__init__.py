"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any, Final

from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    SOURCE_BLUETOOTH,
    ConfigEntry,
)
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .beta_feedback import async_setup_beta_feedback
from .combine_suggestion import async_load_dismissal
from .const import (
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_VIBRADORM,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROFILE_MIGRATION,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    CONF_SIDE,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    KEESON_VARIANT_SINO,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    RUNTIME_BOND_KEYS,
    connection_gated_by_bond,
    requires_pairing,
    supports_runtime_authentication_recovery,
)
from .coordinator import AdjustableBedCoordinator, ChildEntryView
from .coordinator_connection import PairingOnlyConnectionActiveError
from .entity_runtime import EntityRuntime
from .entry_hooks import ENTRY_PREPARE_STEPS, entry_hooks
from .furnimove_repair import async_refresh_furnimove_layout_issues
from .linak_services import SERVICE_LINAK_MOVE_SIMULTANEOUS, SERVICE_LINAK_SET_ALARM
from .paired_coordinator import PairedBedCoordinator, SingleAddressPairedCoordinator
from .paired_devices import async_register_children
from .paired_registry import (
    _async_rehome_absorbed_singles,
    async_has_side_controller_entities,
)
from .paired_registry import (
    async_unpair_entry as async_unpair_entry,
)
from .pairing import (
    KEY_ABSORBED_ENTRY_ID,
    KEY_ORIGIN_DATA,
    KEY_ORIGIN_OPTIONS,
    effective_child_data,
    get_child,
    inheritable_child_fields,
    is_paired,
    iter_children,
    pair_member_addresses,
    side_owned_profile_fields,
    with_updated_child,
)
from .pairlink_local_setup import (
    PAIRLINK_LOCAL_PROFILE_LEASES_KEY,
    PairlinkLocalLeaseTransfer,
    async_restore_pairlink_local_transfers,
    async_start_paired_pairlink_local_child,
    preflight_paired_pairlink_local_roles,
    release_pairlink_local_profile_lease,
    release_pairlink_local_reservations,
)
from .position_estimate import (
    async_remove_position_estimates,
    async_setup_position_estimates,
    async_unload_position_estimates,
)
from .profile_id import migrate_v5_data, with_profile_ids
from .profile_recommendations import async_watch_profile_recommendations
from .profile_review import (
    async_refresh_profile_review_issue,
    profile_review_mark,
    v5_profile_review_mark,
)
from .remacro_discovery import (
    async_refresh_remacro_issues,
    async_watch_remacro_fallback,
    cache_paired_remacro_models,
)
from .repairs import (
    async_refresh_combine_beds_issue,
    async_setup_combine_beds_issue,
    async_track_combine_beds_issue,
)
from .services import (
    ATTR_ACTION,
    ATTR_ACTIONS,
    ATTR_CAPTURE_DURATION,
    ATTR_DIRECTION,
    ATTR_DURATION_MS,
    ATTR_FIRST_DIRECTION,
    ATTR_FIRST_MOTOR,
    ATTR_INCLUDE_LOGS,
    ATTR_LIFETIME,
    ATTR_MOTOR,
    ATTR_NAME,
    ATTR_PAUSE,
    ATTR_POSITION,
    ATTR_POSITIONS,
    ATTR_PRESET,
    ATTR_RECURRENCE_COUNT,
    ATTR_RECURRENCE_MINUTES,
    ATTR_SECOND_DIRECTION,
    ATTR_SECOND_MOTOR,
    ATTR_SECONDS,
    ATTR_SIDE,
    ATTR_TARGET_ADDRESS,
    DEFAULT_CAPTURE_DURATION,
    MAX_CAPTURE_DURATION,
    MAX_TIMED_MOVE_DURATION_MS,
    MIN_CAPTURE_DURATION,
    MIN_TIMED_MOVE_DURATION_MS,
    SERVICE_GENERATE_SUPPORT_BUNDLE,
    SERVICE_GOTO_PRESET,
    SERVICE_LINAK_RENAME,
    SERVICE_SAVE_PRESET,
    SERVICE_SET_POSITION,
    SERVICE_SET_POSITIONS,
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    TIMED_MOVE_MOTOR_OPTIONS,
    async_register_services,
)
from .solace_services import SERVICE_SOLACE_AUDIO, SERVICE_SOLACE_SET_ALARM
from .unsupported import (
    async_clear_unsupported_device_issues,
    create_pairing_required_issue,
)

# Re-exported for backwards compatibility: these moved to .services, but are
# imported from the package root by tests and by downstream automations.
__all__ = [
    "ATTR_CAPTURE_DURATION",
    "ATTR_DIRECTION",
    "ATTR_DURATION_MS",
    "ATTR_INCLUDE_LOGS",
    "ATTR_FIRST_DIRECTION",
    "ATTR_FIRST_MOTOR",
    "ATTR_ACTION",
    "ATTR_ACTIONS",
    "ATTR_LIFETIME",
    "ATTR_MOTOR",
    "ATTR_NAME",
    "ATTR_PAUSE",
    "ATTR_POSITION",
    "ATTR_POSITIONS",
    "ATTR_PRESET",
    "ATTR_RECURRENCE_COUNT",
    "ATTR_RECURRENCE_MINUTES",
    "ATTR_SECOND_DIRECTION",
    "ATTR_SECOND_MOTOR",
    "ATTR_SECONDS",
    "ATTR_SIDE",
    "ATTR_TARGET_ADDRESS",
    "DEFAULT_CAPTURE_DURATION",
    "MAX_CAPTURE_DURATION",
    "MAX_TIMED_MOVE_DURATION_MS",
    "MIN_CAPTURE_DURATION",
    "MIN_TIMED_MOVE_DURATION_MS",
    "SERVICE_GENERATE_SUPPORT_BUNDLE",
    "SERVICE_GOTO_PRESET",
    "SERVICE_LINAK_MOVE_SIMULTANEOUS",
    "SERVICE_LINAK_RENAME",
    "SERVICE_LINAK_SET_ALARM",
    "SERVICE_SOLACE_AUDIO",
    "SERVICE_SOLACE_SET_ALARM",
    "SERVICE_SAVE_PRESET",
    "SERVICE_SET_POSITION",
    "SERVICE_SET_POSITIONS",
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
# against native child devices for both single- and separate-address pairs.
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
    await async_setup_beta_feedback(hass)
    return True


# Keeson's deprecated "ore" variant was an alias for Sino.
_V4_2_VARIANT_ALIASES: Final = {"ore": KEESON_VARIANT_SINO}
# Per-app copies of generic settings, released in v4.0.2.
_V4_2_RENAMED_KEYS: Final[dict[str, str]] = {
    "logicdata_app_has_light": CONF_HAS_LIGHT,
    "jiecang_app_has_light": CONF_HAS_LIGHT,
}


def migrate_v4_2_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return entry data with v4.0.2 aliases replaced, including paired sides.

    A side descriptor and the original entry it restores on unpair are
    migrated too, so a later split never brings an alias back.
    """
    migrated = dict(data)
    variant = migrated.get(CONF_PROTOCOL_VARIANT)
    if isinstance(variant, str) and variant in _V4_2_VARIANT_ALIASES:
        migrated[CONF_PROTOCOL_VARIANT] = _V4_2_VARIANT_ALIASES[variant]
    for old_key, new_key in _V4_2_RENAMED_KEYS.items():
        if old_key in migrated:
            value = migrated.pop(old_key)
            migrated.setdefault(new_key, value)
    for key in (KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS):
        if isinstance(nested := migrated.get(key), Mapping):
            migrated[key] = migrate_v4_2_data(nested)
    if isinstance(children := migrated.get(CONF_PAIR_CHILDREN), list):
        migrated[CONF_PAIR_CHILDREN] = [
            migrate_v4_2_data(child) if isinstance(child, Mapping) else child
            for child in children
        ]
    return migrated


def _with_migration_record(
    data: dict[str, Any], *, from_version: int, from_minor_version: int, **fields: Any
) -> dict[str, Any]:
    """Add ``fields`` to the migration record, starting one if the entry has none."""
    record = data.get(CONF_PROFILE_MIGRATION)
    data[CONF_PROFILE_MIGRATION] = {
        **(
            record
            if isinstance(record, Mapping)
            else {"from_version": from_version, "from_minor_version": from_minor_version}
        ),
        **fields,
    }
    return data


# Keys no code reads on v5; docs/design/config-keys.md records the evidence.
# Schema 5.2 drops them wherever an entry stores configuration.
V5_2_OBSOLETE_KEYS: Final = frozenset(
    {
        # Integration-wide since it was added: its own Store is the only reader,
        # so a per-entry copy is never read.
        CONF_DISABLE_DISCOVERY,
        # Written on every pair since schema 4 and never read: the entry's
        # schema version is what versions pair data.
        "pair_schema_version",
    }
)


def _drop_obsolete_keys(
    data: Mapping[str, Any], location: str, dropped: dict[str, list[str]]
) -> dict[str, Any]:
    """Return ``data`` without obsolete keys, recording what each location lost.

    Paired sides and the original entries they restore on unpair are cleaned
    too, so a later split never brings an obsolete key back.
    """
    kept = {key: value for key, value in data.items() if key not in V5_2_OBSOLETE_KEYS}
    if removed := sorted(V5_2_OBSOLETE_KEYS.intersection(data)):
        dropped[location] = removed
    for key in (KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS):
        if isinstance(nested := kept.get(key), Mapping):
            kept[key] = _drop_obsolete_keys(nested, f"{location}.{key}", dropped)
    if isinstance(children := kept.get(CONF_PAIR_CHILDREN), list):
        kept[CONF_PAIR_CHILDREN] = [
            _drop_obsolete_keys(child, f"{location}.{child.get(CONF_SIDE, index)}", dropped)
            if isinstance(child, Mapping)
            else child
            for index, child in enumerate(children)
        ]
    return kept


def migrate_v5_2_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return entry data and options without the obsolete keys.

    The migration record lists each dropped key by where it was stored
    (``data``, ``options``, ``data.left``, ``data.left.origin_options`` and so
    on). An entry without a record yet gets one from the schema it came from.
    Nothing to drop leaves both unchanged.
    """
    dropped: dict[str, list[str]] = {}
    new_data = _drop_obsolete_keys(data, "data", dropped)
    new_options = _drop_obsolete_keys(options, "options", dropped)
    if dropped:
        _with_migration_record(
            new_data,
            from_version=from_version,
            from_minor_version=from_minor_version,
            dropped_keys=dropped,
        )
    return new_data, new_options


# Layouts whose massage buttons raise or do nothing (#787). Their profile settles
# massage off, as setup and Configure already save it for them.
_V5_3_MASSAGE_BED_TYPES: Final = frozenset(
    {BED_TYPE_FURNIMOVE, BED_TYPE_COMFORT_ENHANCEMENTS, BED_TYPE_SLEEPYS_ELITE_APP}
)


def _massage_left_on(view: Mapping[str, Any]) -> bool:
    """Return True for saved Massage on a layout whose profile settles it off."""
    from .setup_questions import profile_massage

    return (
        view.get(CONF_BED_TYPE) in _V5_3_MASSAGE_BED_TYPES
        and bool(view.get(CONF_HAS_MASSAGE))
        and profile_massage(view) is False
    )


def _without_shared_massage_option(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move a paired entry's Massage option into the sides it reached.

    These layouts own Massage per side from 5.3 on, so the option no longer
    reaches them. Before, it overrode every side whose profile did not own
    Massage: each such side keeps that value in its own descriptor, and the
    option goes. A pair without these layouts keeps its option.
    """
    new_options = dict(options)
    children = data.get(CONF_PAIR_CHILDREN)
    if (
        CONF_HAS_MASSAGE not in options
        or not isinstance(children, list)
        or not any(
            isinstance(child, Mapping) and child.get(CONF_BED_TYPE) in _V5_3_MASSAGE_BED_TYPES
            for child in children
        )
    ):
        return dict(data), new_options
    value = new_options.pop(CONF_HAS_MASSAGE)
    updated: list[Any] = []
    for child in children:
        if isinstance(child, Mapping) and (
            child.get(CONF_BED_TYPE) in _V5_3_MASSAGE_BED_TYPES
            or CONF_HAS_MASSAGE not in side_owned_profile_fields(child)
        ):
            child = {**child, CONF_HAS_MASSAGE: value}
        updated.append(child)
    return {**data, CONF_PAIR_CHILDREN: updated}, new_options


def migrate_v5_3_data(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return entry data and options with Massage off on the layouts without massage.

    A paired side is judged by the settings it runs with, and the original entry
    it restores on unpair is corrected too. A shared Massage option first moves
    into the sides of a pair with these layouts, which own Massage per side, so
    every side keeps the value it ran with. The migration record lists each
    corrected place under ``massage_off``, which is also returned.
    """
    new_options = dict(options)
    turned_off: list[str] = []
    if is_paired(data):
        data, new_options = _without_shared_massage_option(data, options)
    new_data = dict(data)
    if not is_paired(data):
        if _massage_left_on(data):
            new_data[CONF_HAS_MASSAGE] = False
            turned_off.append("data")
    elif isinstance(children := data.get(CONF_PAIR_CHILDREN), list):
        updated: list[Any] = []
        for child in children:
            side = child.get(CONF_SIDE) if isinstance(child, Mapping) else None
            if side not in PAIR_SIDES:
                updated.append(child)
                continue
            child = dict(child)
            if _massage_left_on(effective_child_data(data, side, new_options)):
                child[CONF_HAS_MASSAGE] = False
                turned_off.append(f"data.{side}")
            origin = child.get(KEY_ORIGIN_DATA)
            if isinstance(origin, Mapping) and _massage_left_on(origin):
                child[KEY_ORIGIN_DATA] = {**origin, CONF_HAS_MASSAGE: False}
                turned_off.append(f"data.{side}.{KEY_ORIGIN_DATA}")
            updated.append(child)
        new_data[CONF_PAIR_CHILDREN] = updated
    if turned_off:
        _with_migration_record(
            new_data,
            from_version=from_version,
            from_minor_version=from_minor_version,
            massage_off=turned_off,
        )
    return new_data, new_options, turned_off


def _octo_motor_override(view: Mapping[str, Any]) -> str | None:
    """Return the override an Octo setup saved before the selector ran with, or None.

    Before the selector existed, a stored count other than the default was the
    user's explicit layout; the default count followed the advertised one.
    """
    if view.get(CONF_BED_TYPE) != BED_TYPE_OCTO or CONF_OCTO_MOTOR_COUNT_OVERRIDE in view:
        return None
    count = view.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    return str(count) if type(count) is int and count in (1, 3, 4) else "auto"


def migrate_v5_5_data(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> dict[str, Any]:
    """Return entry data with every Octo setup's motor layout stored as its override.

    A paired side is judged by the settings it runs with, and the original entry
    it restores on unpair is written too. The migration record lists each place
    under ``octo_motor_count_override``.
    """
    new_data = dict(data)
    written: list[str] = []
    if not is_paired(data):
        if (override := _octo_motor_override(data)) is not None:
            new_data[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = override
            written.append("data")
    elif isinstance(children := data.get(CONF_PAIR_CHILDREN), list):
        updated: list[Any] = []
        for child in children:
            side = child.get(CONF_SIDE) if isinstance(child, Mapping) else None
            if side not in PAIR_SIDES:
                updated.append(child)
                continue
            child = dict(child)
            if (override := _octo_motor_override(effective_child_data(data, side, options))):
                child[CONF_OCTO_MOTOR_COUNT_OVERRIDE] = override
                written.append(f"data.{side}")
            origin = child.get(KEY_ORIGIN_DATA)
            if isinstance(origin, Mapping) and (override := _octo_motor_override(origin)):
                child[KEY_ORIGIN_DATA] = {**origin, CONF_OCTO_MOTOR_COUNT_OVERRIDE: override}
                written.append(f"data.{side}.{KEY_ORIGIN_DATA}")
            updated.append(child)
        new_data[CONF_PAIR_CHILDREN] = updated
    if written:
        _with_migration_record(
            new_data,
            from_version=from_version,
            from_minor_version=from_minor_version,
            octo_motor_count_override=written,
        )
    return new_data


def _massage_button_unique_ids(data: Mapping[str, Any], turned_off: list[str]) -> set[str]:
    """Return the unique ids of the massage buttons Massage on gave these runtimes."""
    from .button import BUTTON_DESCRIPTIONS

    keys = [description.key for description in BUTTON_DESCRIPTIONS if description.requires_massage]
    unique_ids: set[str] = set()
    for location in turned_off:
        if location == "data":
            unique_ids.update(f"{data[CONF_ADDRESS].upper()}_{key}" for key in keys)
            continue
        _data, side, *origin = location.split(".")
        child = get_child(data, side)
        address = child.get(CONF_ADDRESS) if child is not None else None
        if origin or address is None:
            # An original entry has no entities until an unpair restores it.
            continue
        # These layouts never pair on one address, so each side has its own.
        unique_ids.update(f"{address.upper()}_{key}" for key in keys)
        # A combined control needs both sides, so it goes with either one.
        unique_ids.update(f"{data[CONF_PAIR_ID]}_{key}_both" for key in keys)
    return unique_ids


def migrate_v5_4_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return entry data or options with the classic Richmat key's current name.

    4.4 stored the third-service fallback under the audit-tracker name. Paired
    sides and the original entries they restore on unpair are migrated too.
    """
    from .richmat_classic_profiles import KEY_PREFIX, LEGACY_KEY_PREFIX

    legacy_key = LEGACY_KEY_PREFIX + CONF_RICHMAT_CLASSIC_THIRD_SERVICE.removeprefix(KEY_PREFIX)
    migrated = dict(data)
    if legacy_key in migrated:
        migrated.setdefault(CONF_RICHMAT_CLASSIC_THIRD_SERVICE, migrated.pop(legacy_key))
    for key in (KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS):
        if isinstance(nested := migrated.get(key), Mapping):
            migrated[key] = migrate_v5_4_data(nested)
    if isinstance(children := migrated.get(CONF_PAIR_CHILDREN), list):
        migrated[CONF_PAIR_CHILDREN] = [
            migrate_v5_4_data(child) if isinstance(child, Mapping) else child
            for child in children
        ]
    return migrated


async def _async_migrate_v5_4_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give the classic Richmat entities and stored app state their current names."""
    from .app_state_store import app_state_slot, app_state_store
    from .richmat_classic_profiles import (
        KEY_PREFIX,
        LEGACY_APP_STATE_KEY_PREFIX,
        LEGACY_KEY_PREFIX,
    )

    registry = er.async_get(hass)
    # Unique ids are ``<address or pair id>_<key>[_<side>]``.
    legacy, current = f"_{LEGACY_KEY_PREFIX}", f"_{KEY_PREFIX}"

    @callback
    def rename(entity: er.RegistryEntry) -> dict[str, Any] | None:
        if legacy not in entity.unique_id:
            return None
        unique_id = entity.unique_id.replace(legacy, current, 1)
        if registry.async_get_entity_id(entity.domain, DOMAIN, unique_id) is not None:
            return None
        return {"new_unique_id": unique_id}

    await er.async_migrate_entries(hass, entry.entry_id, rename)
    old_slots = app_state_slot(BED_TYPE_RICHMAT_CLASSIC_APPS, None, LEGACY_APP_STATE_KEY_PREFIX)
    new_slots = old_slots.removesuffix(LEGACY_APP_STATE_KEY_PREFIX)
    for address in _entry_addresses(entry):
        try:
            await app_state_store(hass, address).async_rename_slots(old_slots, new_slots)
        except OSError:
            _LOGGER.warning("Could not rename stored app preferences for %s", address, exc_info=True)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate config entries to newer schema versions.

    Each step upgrades from one schema to the next, so an entry from any older
    version walks the chain. Home Assistant refuses an entry from a newer major
    version before calling this.
    """
    _LOGGER.debug(
        "Migrating config entry %s for %s from version %s",
        entry.entry_id,
        entry.title,
        entry.version,
    )

    original_version = (entry.version, entry.minor_version)
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

    if entry.version == 4 and entry.minor_version < 2:
        # v4.1 -> v4.2: store values that v4.0.2 kept under aliases or
        # per-app keys under the one name the integration now reads.
        hass.config_entries.async_update_entry(
            entry,
            data=migrate_v4_2_data(entry.data),
            options=migrate_v4_2_data(entry.options),
            minor_version=2,
        )

    if entry.version == 4 and entry.minor_version < 3:
        # v4.2 -> v4.3: entries from before the explicit app profiles are asked
        # once whether one fits; later entries chose from the full list.
        data = dict(entry.data)
        if (mark := profile_review_mark(data)) is not None:
            data[CONF_PROFILE_REVIEW_PENDING] = mark
        hass.config_entries.async_update_entry(entry, data=data, minor_version=3)

    if entry.version == 4:
        # v4 -> v5.1: store the profile id each entry and paired side runs, and a
        # record of where it came from. The saved bed type, variant and app keys
        # are not touched. Schema 5 entries cannot load on 4.x; restoring a Home
        # Assistant backup is the only way back.
        data = migrate_v5_data(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        # A route that gained an app in v5, such as Woosa Sleep on the Solace
        # name routes, is reviewed once more.
        if (mark := v5_profile_review_mark(data)) is not None:
            data[CONF_PROFILE_REVIEW_PENDING] = mark
        hass.config_entries.async_update_entry(entry, data=data, version=5, minor_version=1)

    if entry.version == 5 and entry.minor_version < 2:
        # v5.1 -> v5.2: drop the keys the CONF_* audit found obsolete and list
        # them in the migration record.
        data, options = migrate_v5_2_entry(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=2
        )

    if entry.version == 5 and entry.minor_version < 3:
        # v5.2 -> v5.3: Massage off on layouts whose profile has no massage
        # (#787), and their dead massage buttons leave the registry.
        data, options, turned_off = migrate_v5_3_data(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        # The buttons leave the registry now, not at the next successful setup,
        # so a bed that is out of reach keeps no orphans.
        registry = er.async_get(hass)
        for unique_id in _massage_button_unique_ids(data, turned_off):
            entity_id = registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=3
        )

    if entry.version == 5 and entry.minor_version < 4:
        # v5.3 -> v5.4: the classic Richmat apps' config key, entity unique ids
        # and stored app state leave the audit-tracker name 4.4 shipped them with.
        await _async_migrate_v5_4_ids(hass, entry)
        hass.config_entries.async_update_entry(
            entry,
            data=migrate_v5_4_data(entry.data),
            options=migrate_v5_4_data(entry.options),
            minor_version=4,
        )

    if entry.version == 5 and entry.minor_version < 5:
        # v5.4 -> v5.5: an Octo setup stores its motor layout as the override,
        # so nothing reads the count saved before the selector existed.
        data = migrate_v5_5_data(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        hass.config_entries.async_update_entry(entry, data=data, minor_version=5)

    _LOGGER.debug(
        "Migration complete for config entry %s (%s), now at version %s",
        entry.title,
        entry.entry_id,
        entry.version,
    )


def _async_sync_profile_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-derive the stored profile ids before any coordinator reads them.

    Configure, repairs, pairing and runtime corrections edit the saved bed type,
    variant or app key; every one of them reaches the coordinator through a
    setup, so deriving here keeps the stored ids current.
    """
    data = with_profile_ids(entry.data, entry.options)
    if data != dict(entry.data):
        hass.config_entries.async_update_entry(entry, data=data)


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
    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info
    )


async def _async_finish_entry_setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    *,
    schedule_initial_position_read: bool,
) -> None:
    """Store coordinator, forward platforms, and finish setup."""
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await async_setup_position_estimates(hass, entry.entry_id, [(coordinator.address, None)])

    _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if schedule_initial_position_read:
        # The successful connect also requests hydration. Route both paths
        # through the coordinator's session-aware deduplication so platform
        # forwarding cannot race a second full read onto the same BLE link.
        coordinator._schedule_position_hydration()

    _LOGGER.info("Adjustable Bed integration setup complete for %s", entry.title)


def _shared_child_fields(parent_data: Mapping[str, Any]) -> dict[str, Any]:
    """Parent-level config inherited by every child (each descriptor overrides)."""
    return inheritable_child_fields(parent_data)


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
        option_keys = set(inheritable_child_fields(entry.options))
        delta = {
            key: value
            for key, value in new_child_data.items()
            if current.get(key) != value and key not in option_keys
        }
        removed_runtime_keys = {
            key for key in RUNTIME_BOND_KEYS if key in current and key not in new_child_data
        }
        if not delta and not removed_runtime_keys:
            return
        hass.config_entries.async_update_entry(
            entry,
            data=with_updated_child(
                entry.data,
                side,
                delta,
                remove=removed_runtime_keys,
            ),
        )

    return persist


def _build_paired_children(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, AdjustableBedCoordinator]:
    """Build one child coordinator per side from the paired entry's descriptors."""
    children: dict[str, AdjustableBedCoordinator] = {}
    for side in PAIR_SIDES:
        descriptor = get_child(entry.data, side)
        if descriptor is None:
            continue
        child_data = effective_child_data(entry.data, side, entry.options)
        view = ChildEntryView(entry, child_data, _make_child_persist_cb(hass, entry, side))
        children[side] = AdjustableBedCoordinator(hass, view)
    return children


def _async_ensure_paired_device_registry(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PairedBedCoordinator
) -> None:
    """Eagerly create the paired parent before connecting.

    Created before the first connect so the device (and its diagnostics) survive
    a half-available pair or a SETUP_RETRY. Side children are registered after
    absorbed standalone devices have transferred ownership; other sides can be
    registered immediately for diagnostics during SETUP_RETRY.
    """
    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info
    )
    async_register_children(hass, coordinator)


async def _async_release_absorbed_singles(
    hass: HomeAssistant, entry: ConfigEntry,
    *, local_transfers: list[PairlinkLocalLeaseTransfer] | None = None,
) -> tuple[AdjustableBedCoordinator, ...]:
    """Release the original singles' links before their paired children connect.

    Each child takes over the SAME address as its original, so a still-connected
    original can block setup regardless of the pair's connection mode.

    The originals stay LOADED config entries (re-homed + removed only after a
    successful connect), so a failed pair setup still leaves the user two working
    singles that reconnect on demand. Refuse the takeover if an original cannot be
    released safely; absorbing it after a partial paired connect could otherwise
    strand that side.
    """
    transferring: list[AdjustableBedCoordinator] = []
    try:
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
                transfer = next(
                    (item for item in local_transfers or () if item.original is original_coordinator),
                    None,
                )
                if local_transfers and absorbed_id in {
                    item.original.entry.entry_id for item in local_transfers
                } and transfer is None:
                    raise ConfigEntryNotReady("Absorbed local runtime changed before transfer")
                if transfer is not None:
                    released = await original_coordinator.async_release_for_pairing_transfer(
                        expected_pairlink_runtime=transfer.runtime,
                    )
                else:
                    released = await original_coordinator.async_release_for_pairing_transfer()
                if released is not False:
                    transferring.append(original_coordinator)
                if released is False or original_coordinator.is_connected:
                    raise ConfigEntryNotReady(
                        f"Could not release {original.title} before paired setup"
                    )
                _LOGGER.debug(
                    "Released absorbed single %s's BLE link before paired connect",
                    absorbed_id,
                )
            except PairingOnlyConnectionActiveError as err:
                raise ConfigEntryNotReady(
                    f"Cannot transfer {original.title} while its pairing-only connection is active"
                ) from err
            except ConfigEntryNotReady:
                raise
            except Exception as err:  # noqa: BLE001 - retain both working originals
                raise ConfigEntryNotReady(
                    f"Could not release {original.title} before paired setup: {err}"
                ) from err
    except (Exception, asyncio.CancelledError):
        for coordinator in transferring:
            coordinator.finish_pairing_transfer()
        raise
    return tuple(transferring)


async def _async_setup_paired_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up a paired (Dual Bed 4.0) entry as one logical device."""
    # HA only clears pending flows matching the new entry's unique_id. A pair's
    # synthetic ID does not match its members' existing Bluetooth discovery cards.
    members = set(pair_member_addresses(entry.data))
    for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN):
        context = flow.get("context", {})
        address = context.get("unique_id")
        if (
            context.get("source") == SOURCE_BLUETOOTH
            and isinstance(address, str)
            and address.upper() in members
        ):
            hass.config_entries.flow.async_abort(flow["flow_id"])

    _LOGGER.info(
        "Setting up paired bed %s (pair_id=%s, mode=%s, sides=%s)",
        entry.title,
        entry.data.get(CONF_PAIR_ID),
        entry.data.get(CONF_PAIR_MODE),
        [child.get(CONF_SIDE) for child in entry.data.get(CONF_PAIR_CHILDREN, [])],
    )

    cache_paired_remacro_models(hass, entry)
    _async_sync_profile_ids(hass, entry)
    if entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
        await _async_setup_single_address_paired_entry(hass, entry)
        return

    children = _build_paired_children(hass, entry)
    if not children:
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="paired_entry_has_no_sides")

    # Observe the first connection too: sequential pairing may disconnect one
    # side before platform setup, taking its live controller with it.
    await async_watch_profile_recommendations(hass, entry, children.items())

    # Seed persisted capability snapshots before a live connection can cache an
    # incomplete discovery over them. Complete live discovery still refreshes
    # this fallback through cache_capability_controller().
    for child in children.values():
        await child.async_prime_offline_controller()

    # A local Pairlink server is selected per physical child. Validate and
    # reserve all selected adapters before creating the parent device or
    # releasing the existing single-entry owners.
    pairlink_inventory, pairlink_local_roles, pairlink_transfers = preflight_paired_pairlink_local_roles(
        hass, entry, children
    )

    try:
        coordinator = PairedBedCoordinator(hass, entry, children)
        _async_ensure_paired_device_registry(hass, entry, coordinator)
    except BaseException:
        release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
        await async_restore_pairlink_local_transfers(hass, None, pairlink_transfers, pairlink_inventory)
        raise

    async def _pairing_repairs_for_unconnected() -> None:
        # Surface a per-side pairing repair for any side that needs OS-level BLE
        # pairing and didn't connect — like a single bed does. Run this BEFORE any
        # abort (timeout / no-side-connected) so a paired bonding bed (OKIN/Leggett)
        # whose sides all fail to pair still prompts the user instead of silently
        # retrying forever.
        for child in children.values():
            if not child.is_connected:
                await _maybe_create_pairing_issue_for(hass, child)

    pair_shutdown_complete = False

    async def _shutdown_failed_pair() -> None:
        nonlocal pair_shutdown_complete
        if not pair_shutdown_complete:
            await coordinator.async_shutdown()
            pair_shutdown_complete = True

    transferring: tuple[AdjustableBedCoordinator, ...] = ()
    try:
        try:
            try:
                async with asyncio.timeout(SETUP_TIMEOUT):
                    # Release the old owners of these addresses before opening replacement
                    # links. Keep their entries until setup succeeds so they can reconnect
                    # on failure. The shared setup deadline also bounds stalled BLE teardown.
                    if pairlink_transfers:
                        transferring = await _async_release_absorbed_singles(
                            hass, entry, local_transfers=pairlink_transfers,
                        )
                    else:
                        transferring = await _async_release_absorbed_singles(hass, entry)
                    for _side, child, source, adapter, owner in pairlink_local_roles:
                        if hass.data[DOMAIN][PAIRLINK_LOCAL_PROFILE_LEASES_KEY].get(adapter) != owner:
                            raise ConfigEntryNotReady("Pairlink local reservation changed before startup")
                        await async_start_paired_pairlink_local_child(
                            hass,
                            child,
                            host_adapter_source=source,
                            adapter_inventory=pairlink_inventory,
                        )
                    if pairlink_local_roles:
                        connected = await coordinator._async_connect_children(
                            started_local_sides={side for side, *_rest in pairlink_local_roles},
                        )
                    else:
                        connected = await coordinator.async_connect()
            except ConfigEntryNotReady:
                await _shutdown_failed_pair()
                release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
                raise
            except TimeoutError:
                # The coordinator isn't in hass.data yet, so the unload path won't run —
                # shut it down here or a side that already connected keeps its BLE link
                # alive across SETUP_RETRY.
                await _pairing_repairs_for_unconnected()
                await _shutdown_failed_pair()
                release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
                raise ConfigEntryNotReady(
                    f"Paired bed {entry.title} timed out connecting after {SETUP_TIMEOUT:.0f}s"
                ) from None
            except (Exception, asyncio.CancelledError):
                await _shutdown_failed_pair()
                release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
                raise

            # Half-available is fine, but surface pairing repairs for any unconnected side
            # first — including the all-offline case, which aborts below.
            await _pairing_repairs_for_unconnected()
            if not connected:
                # If NO side connected there is nothing to control yet — retry like a
                # single bed.
                await _shutdown_failed_pair()
                release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
                raise ConfigEntryNotReady(
                    f"No side of paired bed {entry.title} could be connected"
                )

            # Some sides cannot recreate their extra controls without discovery. A
            # concurrent side can lose its first race with the standalone receiver's
            # just-released link, so retry it while the original entry and registry
            # ownership are still intact. This keeps capability validation before the
            # irreversible absorption step without making the later reconnect path
            # unreachable for controller-gated sides.
            try:
                for child in children.values():
                    if not async_has_side_controller_entities(hass, entry, child.address):
                        continue
                    await child.async_prime_offline_controller()
                    capability_controller = child.capability_controller
                    if (
                        coordinator.connection_mode != PAIR_CONNECTION_MODE_SEQUENTIAL
                        and not child.is_connected
                        and (
                            capability_controller is None
                            or not capability_controller.controller_entity_discovery_complete
                        )
                    ):
                        try:
                            async with asyncio.timeout(SETUP_TIMEOUT):
                                if await child.async_connect():
                                    child.cache_capability_controller()
                        except Exception:  # noqa: BLE001 - validation below reports the retry
                            _LOGGER.debug(
                                "Pre-absorb capability reconnect of %s failed",
                                child.address,
                                exc_info=True,
                            )
                        capability_controller = child.capability_controller
                    if (
                        capability_controller is None
                        or not capability_controller.controller_entity_discovery_complete
                    ):
                        raise ConfigEntryNotReady(
                            f"Paired bed {entry.title} needs {child.name} to connect "
                            "and finish discovering its controls before they can be restored"
                        )
            except (Exception, asyncio.CancelledError):
                await _shutdown_failed_pair()
                release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
                raise

            hass.data[DOMAIN][entry.entry_id] = coordinator
            # At least one child connected, so the pair can provide controls. ONLY NOW
            # absorb the original single entries — re-home their entity/device registry
            # rows onto the pair, then remove them. Deferring this until after a successful
            # connect keeps the originals (and their live controls) intact on the timeout /
            # no-side-connected paths above: if the pair can't load, the user keeps two
            # working beds that can reconnect on demand. Must run before
            # forwarding platforms so the originals' live entities are torn down first,
            # freeing the shared {address}_{key} unique_ids the paired platforms reuse.
            # No-op on reload (originals already gone).
            absorbed_sides = await _async_rehome_absorbed_singles(hass, entry)
        finally:
            try:
                await async_restore_pairlink_local_transfers(
                    hass, coordinator, pairlink_transfers, pairlink_inventory,
                )
            finally:
                for original_coordinator in transferring:
                    original_coordinator.finish_pairing_transfer()
        # A side whose original entry survived a registry rollback must remain solely
        # controlled by that original. Do not let paired platforms adopt the same
        # unique ids back onto the pair under Home Assistant's single-owner registry.
        retained_sides = {
            side
            for child in iter_children(entry.data)
            if (side := child.get(CONF_SIDE))
            and (absorbed_id := child.get(KEY_ABSORBED_ENTRY_ID))
            and hass.config_entries.async_get_entry(absorbed_id) is not None
        }
        for side in retained_sides:
            await coordinator.async_remove_child(side)
        if not coordinator.children:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            await _shutdown_failed_pair()
            release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
            raise ConfigEntryNotReady(
                f"Could not absorb either standalone side of paired bed {entry.title}"
            )
        # A just-absorbed concurrent side may have failed its initial connect ONLY
        # because its original single was still holding the (single-link) BLE — which
        # the absorb above has now freed. Retry such a side once so a non-offline-
        # mintable side (an auto-detected Richmat/L&P/Keeson variant) gets its live
        # controller and exposes entities, instead of staying empty until a reload.
        # Skip in explicit sequential mode, which deliberately releases each side's link
        # and mints offline sides from the pairing-time capability snapshot.
        if absorbed_sides and coordinator.connection_mode != PAIR_CONNECTION_MODE_SEQUENTIAL:
            for side in absorbed_sides:
                child = coordinator.children.get(side)
                if child is None or child.is_connected or _has_selected_disconnected_transport(child):
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
            assert isinstance(child, AdjustableBedCoordinator)
            await child.async_prime_offline_controller()
        try:
            async_register_children(hass, coordinator)
            entry.async_on_unload(entry.add_update_listener(_async_update_listener))
            # Each side keeps its own calibration and estimate.
            await async_setup_position_estimates(
                hass,
                entry.entry_id,
                [(child.address, side) for side, child in coordinator.children.items()],
            )
            await hass.config_entries.async_forward_entry_setups(entry, PAIRED_PLATFORMS)
        except (Exception, asyncio.CancelledError):
            hass.data[DOMAIN].pop(entry.entry_id, None)
            await _shutdown_failed_pair()
            release_pairlink_local_reservations(hass, pairlink_local_roles, pairlink_transfers)
            raise

        # Seed each connected child's positions, like the single-bed path does, so
        # per-side covers don't sit at "unknown" until the first movement.
        for child in coordinator.children.values():
            assert isinstance(child, AdjustableBedCoordinator)
            if child.is_connected:
                child._schedule_position_hydration()

        sides = coordinator.children.values()
        async_watch_remacro_fallback(
            hass, entry, (side for side in sides if isinstance(side, AdjustableBedCoordinator))
        )
        _LOGGER.info("Paired bed setup complete for %s", entry.title)
    except BaseException:
        # Source removal commits registry ownership even if setup is cancelled.
        # Stop the failed pair without reclaiming committed or restored singles.
        if hass.data[DOMAIN].get(entry.entry_id) is coordinator:
            hass.data[DOMAIN].pop(entry.entry_id)
        cleanup_task = hass.async_create_task(
            _shutdown_failed_pair(), "adjustable_bed.failed_pair_shutdown"
        )
        cancelled = False
        try:
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup_task.result()
        finally:
            for _side, _child, _source, adapter, owner in pairlink_local_roles:
                release_pairlink_local_profile_lease(hass, owner, adapter)
        if cancelled:
            raise asyncio.CancelledError from None
        raise


async def _async_setup_single_address_paired_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up a left/right/both surface over one physical coordinator."""
    inner = AdjustableBedCoordinator(hass, entry)
    coordinator = SingleAddressPairedCoordinator(hass, entry, inner)
    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info
    )
    async_register_children(hass, coordinator)
    await async_watch_profile_recommendations(hass, entry, ((None, inner),))
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
    if controller is not None and not getattr(controller, "supports_single_address_pairing", True):
        await coordinator.async_shutdown()
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="single_address_pair_unsupported"
        )

    hass.data[DOMAIN][entry.entry_id] = coordinator
    try:
        async_register_children(hass, coordinator)
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        await hass.config_entries.async_forward_entry_setups(entry, PAIRED_PLATFORMS)
    except (Exception, asyncio.CancelledError):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await coordinator.async_shutdown()
        raise
    if inner.bed_type != BED_TYPE_SLEEP_NUMBER:
        for side, child in coordinator.children.items():
            entry.async_create_background_task(
                hass,
                child.async_read_initial_positions(),
                name=f"adjustable_bed_single_address_initial_read_{side}",
            )
    _LOGGER.info("Single-address paired bed setup complete for %s", entry.title)


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
        # A failed connection proves nothing about a runtime auth repair: only
        # a successful connection resolves it, so keep it until then.
        if not (bed_type and supports_runtime_authentication_recovery(bed_type, protocol_variant)):
            await coordinator.async_clear_obsolete_pairing_state()
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up Adjustable Bed from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    async_track_combine_beds_issue(hass, entry)
    async_refresh_furnimove_layout_issues(hass, entry)
    async_refresh_profile_review_issue(hass, entry)
    await async_register_services(hass)

    # Paired beds (Dual Bed 4.0) route to a dedicated setup path; single-bed
    # entries (no pair_id) fall through to the unchanged logic below.
    if is_paired(entry.data):
        await _async_setup_paired_entry(hass, entry)
        return

    for prepare in ENTRY_PREPARE_STEPS:
        await prepare(hass, entry)
    _async_sync_profile_ids(hass, entry)

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
    await async_watch_profile_recommendations(hass, entry, ((None, coordinator),))

    hooks = entry_hooks(coordinator.bed_type)
    if hooks.setup_local is not None:

        async def finish_local_setup() -> None:
            entry.async_on_unload(entry.add_update_listener(_async_update_listener))
            async_watch_remacro_fallback(hass, entry, (coordinator,))
            await _async_finish_entry_setup(
                hass, entry, coordinator, schedule_initial_position_read=False
            )

        if await hooks.setup_local(hass, entry, coordinator, finish_local_setup):
            return

    # Connect to the bed with a timeout to avoid blocking startup forever
    _LOGGER.debug("Attempting initial connection to bed (timeout: %.0fs)...", SETUP_TIMEOUT)
    initial_connection_timed_out = False
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
        initial_connection_timed_out = True
        connected = False

    if not connected:
        await _maybe_create_pairing_issue_for(hass, coordinator)
        hooks = entry_hooks(coordinator.bed_type)
        if hooks.load_offline is not None and await hooks.load_offline(
            hass,
            entry,
            coordinator,
            f"initial connection timed out after {SETUP_TIMEOUT:.0f}s"
            if initial_connection_timed_out
            else "device was not reachable during initial setup",
        ):
            entry.async_on_unload(entry.add_update_listener(_async_update_listener))
            await _async_finish_entry_setup(
                hass, entry, coordinator, schedule_initial_position_read=False
            )
            return
        if initial_connection_timed_out:
            raise ConfigEntryNotReady(
                f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after "
                f"{SETUP_TIMEOUT:.0f}s.{_connection_failure_hint(coordinator)}"
            ) from None
        if _bond_gated_unbonded(coordinator):
            raise ConfigEntryNotReady(
                f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}."
                f"{_connection_failure_hint(coordinator)}"
            )
        last_attempt = (coordinator.connection_attempt_details or [{}])[-1]
        if last_attempt.get("connect_elapsed_seconds") is not None and last_attempt.get("error"):
            # The link came up, so range/power advice would mislead.
            raise ConfigEntryNotReady(
                f"Connected to bed at {entry.data.get(CONF_ADDRESS)}, but its startup "
                f"failed: {last_attempt['error']}.{_connection_failure_hint(coordinator)}"
            )
        raise ConfigEntryNotReady(
            f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}. "
            "Check that the bed is powered on and in range of your Bluetooth adapter/proxy."
        )

    # The connection proves an advertisement, which the review may still need.
    async_refresh_profile_review_issue(hass, entry)
    # Register the reload listener only after the first successful connect.
    # Setup-time connection logic may persist inferred bond state onto the entry,
    # and we do not want that one-time migration to trigger an immediate reload.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("Successfully connected to bed at %s", entry.data.get(CONF_ADDRESS))
    # Keep the proven layout available to the combine wizard after idle disconnect.
    coordinator.cache_capability_controller()
    async_watch_remacro_fallback(hass, entry, (coordinator,))
    await _async_finish_entry_setup(
        hass,
        entry,
        coordinator,
        schedule_initial_position_read=True,
    )


def _has_selected_disconnected_transport(child: EntityRuntime) -> bool:
    """Recognize a selected local role without inferring physical readiness."""
    controller = child.controller or child.capability_controller
    return bool(
        controller is not None
        and controller.requires_disconnected_transport
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unload a config entry."""
    _LOGGER.info("Unloading Adjustable Bed integration for %s", entry.title)

    platforms = PAIRED_PLATFORMS if is_paired(entry.data) else PLATFORMS
    await hass.config_entries.async_unload_platforms_or_raise(entry, platforms)
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator = hass.data[DOMAIN].pop(
        entry.entry_id
    )
    _LOGGER.debug("Disconnecting from bed...")
    await coordinator.async_shutdown()
    # After shutdown settled any movement, so its travel is persisted.
    await async_unload_position_estimates(hass, entry.entry_id)
    _LOGGER.info("Successfully unloaded Adjustable Bed integration for %s", entry.title)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up state that would otherwise outlive the entry.

    Home Assistant removes the entry's Repairs issues itself: each one is linked
    to the entry that raised it.
    """
    await async_remove_position_estimates(hass, entry.entry_id)
    # Unpair and combine restore other entries for the same beds first, so only
    # addresses nobody else owns lose their app state.
    owned = {
        owned_address
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
        for owned_address in _entry_addresses(other)
    }
    addresses = set(_entry_addresses(entry))
    unowned = addresses - owned
    # A combine that never absorbed its beds still raised their Remacro warnings
    # as its own. Give each back to the entry that still runs the bed before
    # Home Assistant removes the issues linked to this one.
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and addresses.intersection(_entry_addresses(other)):
            async_refresh_remacro_issues(hass, other)
    from .app_state_store import async_remove_app_states

    # Re-adding a bed must not restore the removed entry's app state or session.
    try:
        await async_remove_app_states(hass, unowned)
    except OSError:
        _LOGGER.warning("Could not delete stored app preferences for %s", sorted(unowned), exc_info=True)
    hass.loop.call_soon(async_refresh_combine_beds_issue, hass)


def _entry_addresses(entry: ConfigEntry) -> list[str]:
    """Return every physical bed address a standalone or paired entry owns."""
    addresses = list(pair_member_addresses(entry.data)) if is_paired(entry.data) else []
    address = entry.data.get(CONF_ADDRESS)
    if isinstance(address, str):
        addresses.append(address.upper())
    return addresses


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.consume_internal_entry_update(entry):
        # The coordinator recorded its own BLE bond marker. Reloading for that
        # would disconnect the bed, which is fatal for a bed that only grants
        # one connection per pairing window (issue #385).
        _LOGGER.debug("Skipping reload for %s: internal bond-marker update", entry.entry_id)
        return
    await hass.config_entries.async_reload(entry.entry_id)
