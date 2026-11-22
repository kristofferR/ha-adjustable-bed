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
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

# Imported first: it stops on a Home Assistant too old for the imports below.
from . import minimum_home_assistant  # noqa: F401
from .bed_traits import bed_type_has_position_feedback, default_connection_mode
from .beds.furnimove.repair import async_refresh_furnimove_layout_issues
from .beds.remacro.discovery import (
    async_refresh_remacro_issues,
    async_watch_remacro_fallback,
    cache_paired_remacro_models,
)
from .beds.reverie.pairlink_local_setup import (
    PAIRLINK_LOCAL_PROFILE_LEASES_KEY,
    PairlinkLocalLeaseTransfer,
    async_preflight_paired_pairlink_local_roles,
    async_restore_pairlink_local_transfers,
    async_start_paired_pairlink_local_child,
    release_pairlink_local_profile_lease,
    release_pairlink_local_reservations,
)
from .beta_feedback import async_setup_beta_feedback, async_setup_upgrade_notice
from .combine_suggestion import async_load_dismissal
from .const import (
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OCTO,
    BED_TYPE_QPLUS_APP,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SMARTBED,
    BED_TYPE_VIBRADORM,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_MIGRATION,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    CONF_SIDE,
    CONNECTION_MODE_ALWAYS,
    CONNECTION_MODE_IDLE,
    CONNECTION_MODE_RELEASE,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    IDLE_DISCONNECT_KEEP_CONNECTED,
    KEESON_VARIANT_SINO,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    RETIRED_BED_TYPES,
    RUNTIME_BOND_KEYS,
    VARIANT_AUTO,
    connection_gated_by_bond,
    requires_pairing,
    supports_runtime_authentication_recovery,
)
from .coordinator import AdjustableBedCoordinator, ChildEntryView
from .coordinator_connection import PairingOnlyConnectionActiveError
from .download import SupportBundleDownloadView
from .entity_retypes import async_carry_over_retyped_entities
from .entity_runtime import EntityRuntime
from .entity_sweep import async_sweep_after_setup
from .entry_hooks import ENTRY_PREPARE_STEPS, entry_hooks
from .errors import not_ready, setup_stopped
from .frontend import async_register_frontend
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
from .position_estimate import (
    async_remove_position_estimates,
    async_setup_position_estimates,
    async_unload_position_estimates,
)
from .profile_id import entry_profile_id, migrate_v5_data, profile_route, with_profile_ids
from .profile_recommendations import async_watch_profile_recommendations
from .profile_review import (
    async_refresh_profile_review_issue,
    profile_review_mark,
    v5_profile_review_mark,
)
from .removed_actions import async_report_removed_calls
from .removed_entities import (
    async_forget_removed_entities,
    async_report_removed_entities,
    async_setup_removed_entities,
)
from .repairs import (
    async_refresh_combine_beds_issue,
    async_setup_combine_beds_issue,
    async_track_combine_beds_issue,
)
from .runtime_data import domain_registry, loaded_runtime
from .services import (
    ATTR_ACTION,
    ATTR_ACTIONS,
    ATTR_CAPTURE_DURATION,
    ATTR_DIRECTION,
    ATTR_DURATION_MS,
    ATTR_FIRST_DIRECTION,
    ATTR_FIRST_MOTOR,
    ATTR_INCLUDE_LOGS,
    ATTR_MOTOR,
    ATTR_NAME,
    ATTR_POSITION,
    ATTR_POSITIONS,
    ATTR_PRESET,
    ATTR_SECOND_DIRECTION,
    ATTR_SECOND_MOTOR,
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
    SERVICE_SET_POSITIONS,
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    TIMED_MOVE_MOTOR_OPTIONS,
    async_register_services,
)
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
    "ATTR_MOTOR",
    "ATTR_NAME",
    "ATTR_POSITION",
    "ATTR_POSITIONS",
    "ATTR_PRESET",
    "ATTR_SECOND_DIRECTION",
    "ATTR_SECOND_MOTOR",
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

# Standalone and paired beds (both single- and separate-address pairs) set up
# the same platforms; a pair builds per-side entities on native child devices.
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Adjustable Bed integration domain."""
    hass.data.setdefault(DOMAIN, {})

    # Clear obsolete "unsupported BLE device" Repairs issues from older versions
    # that nagged about every discovered non-bed device (feature removed).
    async_clear_unsupported_device_issues(hass)
    await async_load_dismissal(hass)
    async_setup_combine_beds_issue(hass)

    hass.http.register_view(SupportBundleDownloadView)
    await async_register_frontend(hass)

    await async_register_services(hass)
    await async_setup_beta_feedback(hass)
    await async_setup_upgrade_notice(hass)
    async_report_removed_calls(hass)
    await async_setup_removed_entities(hass)
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


# What 4.x ran with when an entry had not saved the setting. v5 falls back to
# each bed type's own default instead, so a 4.x entry saves 4.x's value first.
_V4_RUNTIME_DEFAULTS: Final[dict[str, bool]] = {
    "disconnect_after_command": False,
    CONF_DISABLE_ANGLE_SENSING: True,
}


def migrate_v4_runtime_defaults(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return 4.x entry data with the values 4.x ran with saved where it had none.

    4.x read both from the data of the bed that ran: a standalone entry, a
    one-address pair, or a two-address side over its pair's data (options that
    reached the side still win). A two-address pair's own data held neither,
    so only its sides are filled. An original entry a pair restores on unpair is
    filled on its own. Diagnostic entries from 1.4.6 to 2.5.3, for example,
    saved no handoff.
    """
    migrated = dict(data)
    children = migrated.get(CONF_PAIR_CHILDREN)
    separate = isinstance(children, list) and data.get(CONF_PAIR_MODE) != PAIR_MODE_SINGLE_ADDRESS
    if not separate:
        for key, value in _V4_RUNTIME_DEFAULTS.items():
            migrated.setdefault(key, value)
    if isinstance(children, list):
        migrated[CONF_PAIR_CHILDREN] = [
            _v4_side_defaults(child, data, fill=separate) if isinstance(child, Mapping) else child
            for child in children
        ]
    return migrated


def _v4_side_defaults(
    child: Mapping[str, Any], pair: Mapping[str, Any], *, fill: bool
) -> dict[str, Any]:
    side = dict(child)
    if fill:
        for key, value in _V4_RUNTIME_DEFAULTS.items():
            if key not in pair:
                side.setdefault(key, value)
    if isinstance(origin := side.get(KEY_ORIGIN_DATA), Mapping):
        side[KEY_ORIGIN_DATA] = migrate_v4_runtime_defaults(origin)
    return side


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


# Keys no code reads on v5.
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


# Settings 5.6 removed (#v5 settings simplification). Their behaviour is now
# one value for every bed, or the per-bed default.
V5_6_REMOVED_KEYS: Final = frozenset(
    {"position_mode", "connection_profile", "pair_connection_mode"}
)
_LEGACY_DISCONNECT_AFTER_COMMAND: Final = "disconnect_after_command"


_V5_6_INHERITED_KEYS: Final = (
    _LEGACY_DISCONNECT_AFTER_COMMAND,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_DISABLE_ANGLE_SENSING,
)


def _v5_6_settings(
    settings: Mapping[str, Any],
    route: Mapping[str, Any],
    location: str,
    changed: dict[str, list[str]],
    *,
    paired: bool = False,
    underneath: Mapping[str, Any] | None = None,
    side_overrides: Mapping[str, Any] | None = None,
    side_route: Mapping[str, Any] | None = None,
    explicit_mode: bool = False,
) -> dict[str, Any]:
    """Return one stored settings mapping in the 5.6 shape.

    ``route`` holds the bed type and variant the mapping runs with, so a saved
    "Disable angle sensing" equal to that route's default is dropped. Paired
    sides first take the shared values they inherited, then each side and each
    original entry is rewritten against its own route. A pair's parent and
    sides (``paired``) keep their angle-sensing values as they are, since a
    side without one would inherit the parent's. Options pass the legacy data
    they layer over as ``underneath``, so their mode reads both as one.
    """
    new = {key: value for key, value in settings.items() if key not in V5_6_REMOVED_KEYS}
    notes = sorted(V5_6_REMOVED_KEYS.intersection(settings))
    if isinstance(children := new.get(CONF_PAIR_CHILDREN), list):
        shared = {key: new[key] for key in _V5_6_INHERITED_KEYS if key in new}
        new[CONF_PAIR_CHILDREN] = [
            _v5_6_settings(
                # In the order a side reads them: parent, side, then the options
                # the side does not own itself.
                {**shared, **child, **_not_owned(child, side_overrides)},
                {**route, **_route_of(child), **_not_owned(child, side_route)},
                f"{location}.{child.get(CONF_SIDE, index)}",
                changed,
                paired=True,
                explicit_mode=True,
            )
            if isinstance(child, Mapping)
            else child
            for index, child in enumerate(children)
        ]
    below = underneath or {}
    own_after = new.pop(_LEGACY_DISCONNECT_AFTER_COMMAND, None)
    own_seconds = new.get(CONF_IDLE_DISCONNECT_SECONDS)
    layered = underneath is not None and (own_after is not None or own_seconds is not None)
    # Options over data read as one: what this layer leaves out, the one below sets.
    after = own_after if own_after is not None else below.get(_LEGACY_DISCONNECT_AFTER_COMMAND)
    seconds = own_seconds if own_seconds is not None else below.get(CONF_IDLE_DISCONNECT_SECONDS)
    if not layered:
        after, seconds = own_after, own_seconds
    explicit_mode = explicit_mode or layered
    view = {**_route_of(new), **route}
    default_mode = default_connection_mode(view.get(CONF_BED_TYPE), view.get(CONF_PROTOCOL_VARIANT))
    if own_seconds == IDLE_DISCONNECT_KEEP_CONNECTED:
        new.pop(CONF_IDLE_DISCONNECT_SECONDS)
    mode: str | None = None
    if seconds == IDLE_DISCONNECT_KEEP_CONNECTED:
        # Issue #700's "0 keeps the bed connected" applied only while the
        # handoff was off: saved, inherited, or the bed type's default.
        handoff = after if after is not None else default_mode == CONNECTION_MODE_RELEASE
        if after is True or (handoff and explicit_mode):
            # A side or an option saves its handoff, so it never takes Always
            # from the layer below.
            mode = CONNECTION_MODE_RELEASE
        elif not handoff:
            mode = CONNECTION_MODE_ALWAYS
        else:
            notes.append(f"{CONF_IDLE_DISCONNECT_SECONDS}=0 (handoff on)")
    elif after is True:
        mode = CONNECTION_MODE_RELEASE
    elif after is False:
        mode = CONNECTION_MODE_IDLE
    elif explicit_mode and seconds is not None:
        # Without a saved mode this would take the layer below's new mode,
        # which its own settings never followed: save the mode it ran with.
        mode = default_mode
    if mode is not None:
        new[CONF_CONNECTION_MODE] = mode
        notes.append(f"{CONF_CONNECTION_MODE}={mode}")
    elif own_after is not None:
        notes.append(_LEGACY_DISCONNECT_AFTER_COMMAND)
    feedback = bed_type_has_position_feedback(
        view.get(CONF_BED_TYPE), view.get(CONF_PROTOCOL_VARIANT)
    )
    paired = paired or isinstance(children, list)
    disabled = new.get(CONF_DISABLE_ANGLE_SENSING)
    below_disabled = below.get(CONF_DISABLE_ANGLE_SENSING)
    if (
        isinstance(disabled, bool)
        and not paired
        and disabled is not feedback
        # Dropping it must not uncover an opposite value in the layer below.
        and below_disabled in (None, disabled)
    ):
        # Equal to the route's own default: the route decides it now.
        del new[CONF_DISABLE_ANGLE_SENSING]
        notes.append(CONF_DISABLE_ANGLE_SENSING)
    raw_origin = settings.get(KEY_ORIGIN_DATA)
    for key in (KEY_ORIGIN_DATA, KEY_ORIGIN_OPTIONS):
        if isinstance(nested := new.get(key), Mapping):
            origin = raw_origin if isinstance(raw_origin, Mapping) else nested
            new[key] = _v5_6_settings(
                nested,
                {**_route_of(origin), **_route_of(nested)},
                f"{location}.{key}",
                changed,
                underneath=origin if key == KEY_ORIGIN_OPTIONS else None,
            )
    if notes:
        changed.setdefault(location, []).extend(notes)
    return new


def _not_owned(child: Mapping[str, Any], options: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the pair options a side reads: those its own profile does not own."""
    owned = side_owned_profile_fields(child)
    return {key: value for key, value in (options or {}).items() if key not in owned}


def _route_of(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bed type and variant a settings mapping stores."""
    return {
        key: settings[key] for key in (CONF_BED_TYPE, CONF_PROTOCOL_VARIANT) if key in settings
    }


def migrate_v5_6_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return entry data and options with the 5.6 settings shape.

    Removed settings are dropped; "Disconnect after each command" and the idle
    timeout's 0 become the connection mode; a saved angle-sensing choice equal
    to its route's default is dropped, since the route now decides it. The
    migration record lists each change by where it was stored.
    """
    paired = isinstance(data.get(CONF_PAIR_CHILDREN), list)
    side_overrides: dict[str, Any] = {}
    if (
        paired
        and data.get(CONF_PAIR_MODE) != PAIR_MODE_SINGLE_ADDRESS
        and (
            _LEGACY_DISCONNECT_AFTER_COMMAND in options
            or CONF_IDLE_DISCONNECT_SECONDS in options
        )
    ):
        # A two-address pair's connection options win over each side's own
        # settings, so each side's mode is derived with them and the options
        # lose them. A one-address pair's physical bed reads the parent.
        side_overrides = {
            key: options[key]
            for key in (_LEGACY_DISCONNECT_AFTER_COMMAND, CONF_IDLE_DISCONNECT_SECONDS)
            if key in options
        }
        options = {key: value for key, value in options.items() if key not in side_overrides}
    changed: dict[str, list[str]] = {}
    if side_overrides:
        changed["options"] = [f"{key} (moved to each side)" for key in sorted(side_overrides)]
    route = _route_of(data)
    new_data = _v5_6_settings(
        data,
        route,
        "data",
        changed,
        side_overrides=side_overrides,
        # A side reads the pair's route options over its own.
        side_route=_route_of(options) if paired else None,
    )
    new_options = _v5_6_settings(
        options,
        {**route, **_route_of(options)},
        "options",
        changed,
        # A pair's options reach its sides, which keep their angle choices.
        paired=paired,
        underneath=data,
    )
    if changed:
        _with_migration_record(
            new_data,
            from_version=from_version,
            from_minor_version=from_minor_version,
            settings_5_6=changed,
        )
    return new_data, new_options


# The bed type SmartBed app beds were saved under before schema 5.7.
_OKIN_CB24: Final = "okin_cb24"
# That route sent the CB24 frames whichever legacy receiver was chosen, so each
# maps to the SmartBed receiver that still sends them.
_OKIN_CB24_VARIANTS: Final = {"cb_old": "cb24", "dacheng": "cb24", "cb_new": "cb27new"}


def _smartbed_variant(view: Mapping[str, Any], *, single_address: bool = False) -> str:
    """Return the SmartBed receiver that sends what this okin_cb24 route sent."""
    variant = view.get(CONF_PROTOCOL_VARIANT) or VARIANT_AUTO
    variant = _OKIN_CB24_VARIANTS.get(variant, variant)
    sided = single_address or view.get(CONF_CB24_BED_SELECTION) in (
        CB24_BED_SELECTION_A,
        CB24_BED_SELECTION_B,
    )
    # Every legacy variant sent its side; among the app's receivers only CB24AB does.
    return "cb24_ab" if sided and variant != "cb27new" else variant


def _as_smartbed(settings: Mapping[str, Any], variant: str | None = None) -> dict[str, Any]:
    """Return one stored mapping of an okin_cb24 route as the SmartBed route stores it.

    ``variant`` is the receiver to store. Without one, a stored legacy name is
    only translated.
    """
    new = dict(settings)
    if new.get(CONF_BED_TYPE) == _OKIN_CB24:
        new[CONF_BED_TYPE] = BED_TYPE_SMARTBED
    stored = new.get(CONF_PROTOCOL_VARIANT)
    if variant is not None:
        new[CONF_PROTOCOL_VARIANT] = variant
    elif isinstance(stored, str):
        new[CONF_PROTOCOL_VARIANT] = _OKIN_CB24_VARIANTS.get(stored, stored)
    if new.get(CONF_PROTOCOL_VARIANT) != "cb24_ab" and CONF_CB24_BED_SELECTION in new:
        new[CONF_CB24_BED_SELECTION] = CB24_BED_SELECTION_DEFAULT
    # The route drove head and feet whatever count was saved, and the app's
    # profile decides the rest.
    for key, value in (
        (CONF_MOTOR_COUNT, 2),
        (CONF_HAS_MASSAGE, False),
        (CONF_DISABLE_ANGLE_SENSING, True),
        (CONF_MOTOR_PULSE_USER_SET, False),
    ):
        if key in new:
            new[key] = value
    return new


def migrate_v5_7_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return entry data and options with every okin_cb24 route saved as SmartBed.

    The receiver is the one that sends the frames the bed got before: a bed with
    a side becomes CB24AB, the only receiver of the app that sends one. A bed
    reads its own data, so that decides its receiver. A paired side also read
    the pair's options; it now stores what it ran with, since SmartBed's
    settings belong to each side. The original entries a pair restores on
    unpair are written too, and an open or kept app review follows the renamed
    route. The migration record lists each place under ``smartbed``. Any other
    entry is returned unchanged.
    """
    from .pairing import side_owned_profile_fields
    from .profile_review import carry_profile_review_to_renamed_route

    moved: list[str] = []
    single = data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS

    def bed(own: Mapping[str, Any], location: str, *, one_address: bool = False) -> dict[str, Any]:
        """Return a bed's own data: a standalone entry, a pair's parent or an original."""
        if own.get(CONF_BED_TYPE) != _OKIN_CB24:
            return dict(own)
        variant = _smartbed_variant(own, single_address=one_address)
        moved.append(location)
        stores = variant != VARIANT_AUTO or CONF_PROTOCOL_VARIANT in own
        return _as_smartbed(own, variant if stores else None)

    new_data = bed(data, "data", one_address=single)
    if isinstance(children := data.get(CONF_PAIR_CHILDREN), list):
        updated: list[Any] = []
        for child in children:
            side = child.get(CONF_SIDE) if isinstance(child, Mapping) else None
            if side not in PAIR_SIDES:
                updated.append(child)
                continue
            child = dict(child)
            view = effective_child_data(data, side, options)
            if view.get(CONF_BED_TYPE) == _OKIN_CB24:
                variant = _smartbed_variant(view, single_address=single)
                owned = side_owned_profile_fields(
                    {CONF_BED_TYPE: BED_TYPE_SMARTBED, CONF_PROTOCOL_VARIANT: variant}
                )
                ran_with = {key: view[key] for key in owned if key in view}
                child = _as_smartbed({**child, **ran_with, CONF_BED_TYPE: _OKIN_CB24}, variant)
                moved.append(f"data.{side}")
            origin = child.get(KEY_ORIGIN_DATA)
            if isinstance(origin, Mapping) and origin.get(CONF_BED_TYPE) == _OKIN_CB24:
                restored = bed(origin, f"data.{side}.{KEY_ORIGIN_DATA}")
                carry_profile_review_to_renamed_route(origin, restored)
                child[KEY_ORIGIN_DATA] = restored
                if isinstance(origin_options := child.get(KEY_ORIGIN_OPTIONS), Mapping):
                    child[KEY_ORIGIN_OPTIONS] = _as_smartbed(origin_options)
            updated.append(child)
        new_data[CONF_PAIR_CHILDREN] = updated
    if not moved:
        return new_data, dict(options)
    carry_profile_review_to_renamed_route(data, new_data)
    _with_migration_record(
        new_data,
        from_version=from_version,
        from_minor_version=from_minor_version,
        smartbed=moved,
    )
    return new_data, _as_smartbed(options)


# What each control of the okin_cb24 route is on the SmartBed route. Unique ids
# are ``<address or pair id>_<key>[_<side>]``; a pair's own movement buttons end
# in ``_both``.
_V5_7_ENTITY_KEYS: Final = {
    "cover": {"back": "head", "legs": "feet"},
    "button": {
        "massage_mode_step": "smartbed_wave_up",
        "back_up_both": "head_up_both",
        "back_down_both": "head_down_both",
        "legs_up_both": "feet_up_both",
        "legs_down_both": "feet_down_both",
    },
}


@callback
def _async_migrate_v5_7_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Keep the entity IDs of the controls the SmartBed route names differently.

    A saved motor count of three or four added Head and Feet covers that sent
    the Back and Legs commands. Back and Legs keep their entity IDs; the
    duplicates go.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        for old, new in _V5_7_ENTITY_KEYS.get(entity.domain, {}).items():
            for suffix in ("", *(f"_{side}" for side in PAIR_SIDES)):
                if not entity.unique_id.endswith(f"_{old}{suffix}"):
                    continue
                unique_id = f"{entity.unique_id.removesuffix(f'{old}{suffix}')}{new}{suffix}"
                duplicate = registry.async_get_entity_id(entity.domain, DOMAIN, unique_id)
                if duplicate is not None:
                    registry.async_remove(duplicate)
                registry.async_update_entity(entity.entity_id, new_unique_id=unique_id)


def migrate_v5_8_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return entry data and options with each retired bed type saved as its route.

    4.x saved Okimat, DewertOkin, Nectar and Mattress Firm beds under the brand;
    each ran the Okin receiver route it is now saved as, so nothing else
    changes. Paired sides and the original entries they restore on unpair are
    written too, and an open or kept app review follows the renamed route. The
    migration record lists each place under ``renamed_bed_types``.
    """
    from .profile_review import carry_profile_review_to_renamed_route

    renamed: dict[str, str] = {}

    def current(settings: Mapping[str, Any], location: str) -> dict[str, Any]:
        new = dict(settings)
        if (retired := new.get(CONF_BED_TYPE)) in RETIRED_BED_TYPES:
            new[CONF_BED_TYPE] = RETIRED_BED_TYPES[retired]
            renamed[location] = retired
        return new

    new_data = current(data, "data")
    new_options = current(options, "options")
    if isinstance(children := data.get(CONF_PAIR_CHILDREN), list):
        updated: list[Any] = []
        for child in children:
            side = child.get(CONF_SIDE) if isinstance(child, Mapping) else None
            if side not in PAIR_SIDES:
                updated.append(child)
                continue
            child = current(child, f"data.{side}")
            if isinstance(origin := child.get(KEY_ORIGIN_DATA), Mapping):
                restored = current(origin, f"data.{side}.{KEY_ORIGIN_DATA}")
                carry_profile_review_to_renamed_route(origin, restored)
                child[KEY_ORIGIN_DATA] = restored
            if isinstance(origin_options := child.get(KEY_ORIGIN_OPTIONS), Mapping):
                child[KEY_ORIGIN_OPTIONS] = current(
                    origin_options, f"data.{side}.{KEY_ORIGIN_OPTIONS}"
                )
            updated.append(child)
        new_data[CONF_PAIR_CHILDREN] = updated
    if renamed:
        carry_profile_review_to_renamed_route(data, new_data)
        _with_migration_record(
            new_data,
            from_version=from_version,
            from_minor_version=from_minor_version,
            renamed_bed_types=renamed,
        )
    return new_data, new_options


# The bed type Q-Plus app beds were saved under before schema 5.9.
_SBI: Final = "sbi"
# The app layout whose keys that route sent: all four motors, the light, the
# massage modes and TV on the key the route called TV.
_SBI_LAYOUT: Final = "H"


def _as_qplus(own: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bed's own sbi settings as the Q-Plus app route stores them.

    The bed selection stays as stored: Both, A or B mean the same on both
    routes, and unset or automatic builds Both on either. The choice to read
    positions stays too; the app route reads them as the sbi route did.
    """
    new = {**own, CONF_BED_TYPE: BED_TYPE_QPLUS_APP, CONF_PRODUCT_TYPE: _SBI_LAYOUT}
    # The app's layout decides the controls.
    for key, value in (
        (CONF_MOTOR_COUNT, 2),
        (CONF_HAS_MASSAGE, False),
        (CONF_MOTOR_PULSE_USER_SET, False),
    ):
        if key in new:
            new[key] = value
    return new


def _sbi_renamed(shared: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shared layer with only its sbi bed type renamed.

    A pair's options, a two-address pair's own data and an original's options
    hold values a bed of another type may still read, so they stay as they are.
    """
    if shared.get(CONF_BED_TYPE) != _SBI:
        return dict(shared)
    return {**shared, CONF_BED_TYPE: BED_TYPE_QPLUS_APP}


def migrate_v5_9_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    from_version: int,
    from_minor_version: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return entry data and options with every sbi route saved as the Q-Plus app.

    A bed keeps its stored bed selection and its choice to read positions, and
    takes the app's H layout, the one with the keys the sbi route sent. A
    two-address side also read the pair's options; it now stores the selection
    it ran with, since the app's selection belongs to each side. The original
    entries a pair restores on unpair are written too, and an open or kept app
    review follows the renamed route. The migration record lists each place
    under ``qplus_app``.

    The app route reads positions from this schema on. A Q-Plus app bed without
    a saved choice ran with them unread, and keeps that until the user turns
    reading on; the record lists those under ``qplus_app_positions_unread``.
    An entry from before schema 5.6 has its choice settled by that step, which
    already reads the route's new default. Any other entry is returned
    unchanged.
    """
    from .profile_review import carry_profile_review_to_renamed_route

    moved: list[str] = []
    unread: list[str] = []
    single = data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS
    children = data.get(CONF_PAIR_CHILDREN)

    settled_before = (from_version, from_minor_version) >= (5, 6)

    def keeps_unread(view: Mapping[str, Any]) -> bool:
        return (
            settled_before
            and view.get(CONF_BED_TYPE) == BED_TYPE_QPLUS_APP
            and CONF_DISABLE_ANGLE_SENSING not in view
        )

    def bed(own: Mapping[str, Any], location: str) -> dict[str, Any]:
        """Return a bed's own data: a standalone entry, a one-address pair or an original."""
        if own.get(CONF_BED_TYPE) == _SBI:
            moved.append(location)
            return _as_qplus(own)
        if keeps_unread(own):
            unread.append(location)
            return {**own, CONF_DISABLE_ANGLE_SENSING: True}
        return dict(own)

    if isinstance(children, list) and not single:
        new_data = _sbi_renamed(data)
        if new_data != dict(data):
            moved.append("data")
    else:
        new_data = bed(data, "data")
    if isinstance(children, list):
        updated: list[Any] = []
        for child in children:
            side = child.get(CONF_SIDE) if isinstance(child, Mapping) else None
            if side not in PAIR_SIDES:
                updated.append(child)
                continue
            child = dict(child)
            view = effective_child_data(data, side, options)
            if view.get(CONF_BED_TYPE) == _SBI:
                if not single and CONF_PROTOCOL_VARIANT in view:
                    child[CONF_PROTOCOL_VARIANT] = view[CONF_PROTOCOL_VARIANT]
                child = _as_qplus(child)
                moved.append(f"data.{side}")
            elif keeps_unread(view):
                child[CONF_DISABLE_ANGLE_SENSING] = True
                unread.append(f"data.{side}")
            if isinstance(origin := child.get(KEY_ORIGIN_DATA), Mapping):
                restored = bed(origin, f"data.{side}.{KEY_ORIGIN_DATA}")
                carry_profile_review_to_renamed_route(origin, restored)
                child[KEY_ORIGIN_DATA] = restored
                if isinstance(origin_options := child.get(KEY_ORIGIN_OPTIONS), Mapping):
                    child[KEY_ORIGIN_OPTIONS] = _sbi_renamed(origin_options)
            updated.append(child)
        new_data[CONF_PAIR_CHILDREN] = updated
    if not moved and not unread:
        return new_data, dict(options)
    fields: dict[str, Any] = {}
    if moved:
        carry_profile_review_to_renamed_route(data, new_data)
        fields["qplus_app"] = moved
    if unread:
        fields["qplus_app_positions_unread"] = unread
    _with_migration_record(
        new_data, from_version=from_version, from_minor_version=from_minor_version, **fields
    )
    return new_data, _sbi_renamed(options)


# The sbi route's buttons the Q-Plus app's H layout has under another key, with
# the same command and the same meaning. Unique ids are
# ``<address>_<key>[_<side>]``.
_V5_9_BUTTON_KEYS: Final = {
    "preset_zero_g": "zero_g",
    "preset_tv": "tv",
    "toggle_light": "light",
    "massage_head_up": "massage_head",
    "massage_foot_up": "massage_foot",
}


@callback
def _async_migrate_v5_9_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Keep the entity IDs of the sbi buttons the Q-Plus app names differently.

    Only the beds this step moves are touched: another bed type on the other
    side of a pair keeps its rows. Every other sbi control has no app control
    with the same command and meaning, and goes when the bed next loads.
    """
    data = entry.data
    beds = [data] if data.get(CONF_BED_TYPE) == _SBI else []
    beds += [
        view
        for side in PAIR_SIDES
        if get_child(data, side) is not None
        and (view := effective_child_data(data, side, entry.options)).get(CONF_BED_TYPE) == _SBI
    ]
    addresses = {
        address.upper() for bed in beds if isinstance(address := bed.get(CONF_ADDRESS), str)
    }
    keys = {
        f"{old}{suffix}": f"{new}{suffix}"
        for old, new in _V5_9_BUTTON_KEYS.items()
        for suffix in ("", *(f"_{side}" for side in PAIR_SIDES))
    }
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        address, _, key = entity.unique_id.partition("_")
        if entity.domain != "button" or address not in addresses or key not in keys:
            continue
        unique_id = f"{address}_{keys[key]}"
        duplicate = registry.async_get_entity_id("button", DOMAIN, unique_id)
        if duplicate is not None:
            registry.async_remove(duplicate)
        registry.async_update_entity(entity.entity_id, new_unique_id=unique_id)


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
    from .beds.richmat_classic.profiles import KEY_PREFIX, LEGACY_KEY_PREFIX

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
    from .beds.richmat_classic.profiles import (
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
        # are not touched; a connection or position setting 4.x ran with by
        # default is saved. Schema 5 entries cannot load on 4.x; restoring a Home
        # Assistant backup is the only way back.
        data = migrate_v5_data(
            migrate_v4_runtime_defaults(entry.data),
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

    if entry.version == 5 and entry.minor_version < 6:
        # v5.5 -> v5.6: the settings simplification. Position update mode,
        # connection profile and the stored pair connection mode go; the
        # disconnect settings become one connection mode.
        data, options = migrate_v5_6_entry(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=6
        )

    if entry.version == 5 and entry.minor_version < 7:
        # v5.6 -> v5.7: a bed on the okin_cb24 route becomes a SmartBed app bed,
        # the one bed type for that app, on the receiver that sends what it got
        # before. Controls the app names differently keep their entity IDs.
        data, options = migrate_v5_7_entry(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        if renamed := data != dict(entry.data):
            _async_migrate_v5_7_entities(hass, entry)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=7
        )
        if renamed:
            # The id each route runs under is derived from the renamed fields.
            _async_sync_profile_ids(hass, entry)

    if entry.version == 5 and entry.minor_version < 8:
        # v5.7 -> v5.8: an Okimat, DewertOkin, Nectar or Mattress Firm bed that
        # 4.x saved under its brand is saved as the Okin receiver route it runs.
        data, options = migrate_v5_8_entry(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        renamed = data != dict(entry.data)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=8
        )
        if renamed:
            _async_sync_profile_ids(hass, entry)

    if entry.version == 5 and entry.minor_version < 9:
        # v5.8 -> v5.9: a bed on the sbi route becomes a Q-Plus app bed, the one
        # bed type for that app, with the bed selection it sent before. Buttons
        # the app has under another key keep their entity IDs.
        data, options = migrate_v5_9_entry(
            entry.data,
            entry.options,
            from_version=original_version[0],
            from_minor_version=original_version[1],
        )
        if renamed := data != dict(entry.data):
            _async_migrate_v5_9_entities(hass, entry)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, minor_version=9
        )
        if renamed:
            _async_sync_profile_ids(hass, entry)

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
    async_carry_over_retyped_entities(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_sweep_after_setup(hass, entry, PLATFORMS)

    if schedule_initial_position_read:
        # The successful connect also requests hydration. Route both paths
        # through the coordinator's session-aware deduplication so platform
        # forwarding cannot race a second full read onto the same BLE link.
        coordinator._schedule_position_hydration()

    _LOGGER.info("Adjustable Bed integration setup complete for %s", entry.title)


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
    views: dict[str, ChildEntryView] = {}
    for side in PAIR_SIDES:
        descriptor = get_child(entry.data, side)
        if descriptor is None:
            continue
        child_data = effective_child_data(entry.data, side, entry.options)
        validate = entry_hooks(profile_route(entry_profile_id(child_data)).bed_type).validate
        if validate is not None:
            validate(child_data)
        views[side] = ChildEntryView(entry, child_data, _make_child_persist_cb(hass, entry, side))
    return {side: AdjustableBedCoordinator(hass, view) for side, view in views.items()}


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
            original_coordinator = loaded_runtime(hass, absorbed_id)
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
                    raise not_ready("setup_retry")
                if transfer is not None:
                    released = await original_coordinator.async_release_for_pairing_transfer(
                        expected_pairlink_runtime=transfer.runtime,
                    )
                else:
                    released = await original_coordinator.async_release_for_pairing_transfer()
                if released is not False:
                    transferring.append(original_coordinator)
                if released is False or original_coordinator.is_connected:
                    raise not_ready("pair_side_busy", name=original.title)
                _LOGGER.debug(
                    "Released absorbed single %s's BLE link before paired connect",
                    absorbed_id,
                )
            except PairingOnlyConnectionActiveError as err:
                raise not_ready("pair_side_busy", name=original.title) from err
            except ConfigEntryNotReady:
                raise
            except Exception as err:
                raise not_ready("pair_side_busy", name=original.title) from err
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

    for side in PAIR_SIDES:
        if get_child(entry.data, side) is not None:
            await AdjustableBedCoordinator.async_import_tables(
                hass, effective_child_data(entry.data, side, entry.options)
            )
    children = _build_paired_children(hass, entry)
    if not children:
        raise setup_stopped("paired_entry_has_no_sides")

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
    (
        pairlink_inventory,
        pairlink_local_roles,
        pairlink_transfers,
    ) = await async_preflight_paired_pairlink_local_roles(hass, entry, children)

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
                        leases = domain_registry(hass, PAIRLINK_LOCAL_PROFILE_LEASES_KEY, dict)
                        if leases.get(adapter) != owner:
                            raise not_ready("setup_retry")
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
                if any(child.refused_outside_pairing_window for child in children.values()):
                    raise not_ready("setup_pairing_window_closed", name=entry.title) from None
                raise not_ready("setup_timed_out", name=entry.title, seconds=f"{SETUP_TIMEOUT:.0f}", hint="") from None
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
                if any(child.refused_outside_pairing_window for child in children.values()):
                    raise not_ready("setup_pairing_window_closed", name=entry.title)
                raise not_ready("pair_sides_unavailable", name=entry.title)

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
                        except Exception:
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
                        raise not_ready("pair_side_discovering", name=entry.title, side=child.name)
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
            raise not_ready("pair_transfer_failed", name=entry.title)
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
                except Exception:
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
            async_carry_over_retyped_entities(hass, entry, coordinator)
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            async_sweep_after_setup(hass, entry, PLATFORMS)
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
        if loaded_runtime(hass, entry.entry_id) is coordinator:
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
    inner = await AdjustableBedCoordinator.async_create(hass, entry)
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
        raise not_ready("setup_timed_out", name=entry.title, seconds=f"{SETUP_TIMEOUT:.0f}", hint="") from None
    if not connected:
        await _maybe_create_pairing_issue_for(hass, inner)
        await coordinator.async_shutdown()
        raise not_ready("setup_connect_failed", name=entry.title, hint="")

    controller = inner.controller
    if controller is not None and not controller.supports_single_address_pairing:
        await coordinator.async_shutdown()
        raise setup_stopped("single_address_pair_unsupported")

    hass.data[DOMAIN][entry.entry_id] = coordinator
    try:
        async_register_children(hass, coordinator)
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        async_carry_over_retyped_entities(hass, entry, coordinator)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        async_sweep_after_setup(hass, entry, PLATFORMS)
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
    async_report_removed_entities(hass, entry)
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

    coordinator = await AdjustableBedCoordinator.async_create(hass, entry)
    try:
        await _async_setup_standalone_entry(hass, entry, coordinator)
    except BaseException:
        # A failed setup must not leave a reconnect timer or bond task behind:
        # Home Assistant's retry builds a new coordinator for the same bed,
        # which accepts one connection.
        if loaded_runtime(hass, entry.entry_id) is coordinator:
            hass.data[DOMAIN].pop(entry.entry_id)

        async def _bounded_shutdown() -> None:
            # A stalled disconnect must not block the setup retry.
            async with asyncio.timeout(SETUP_CLEANUP_TIMEOUT):
                await coordinator.async_shutdown()

        shutdown = hass.async_create_task(
            _bounded_shutdown(), "adjustable_bed.failed_setup_shutdown"
        )
        cancelled = False
        while not shutdown.done():
            try:
                # Unlike awaiting the task, this neither cancels it nor raises its error.
                await asyncio.wait((shutdown,))
            except asyncio.CancelledError:
                cancelled = True
        if not shutdown.cancelled() and (err := shutdown.exception()) is not None:
            _LOGGER.warning(
                "Failed to stop %s after its setup failed: %r", entry.title, err
            )
        if cancelled:
            raise asyncio.CancelledError from None
        raise


async def _async_setup_standalone_entry(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: AdjustableBedCoordinator
) -> None:
    """Connect a standalone bed and forward its platforms."""
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
        if coordinator.refused_outside_pairing_window:
            raise not_ready("setup_pairing_window_closed", name=entry.title) from None
        if initial_connection_timed_out:
            raise not_ready("setup_timed_out", name=entry.title, seconds=f"{SETUP_TIMEOUT:.0f}", hint=_connection_failure_hint(coordinator)) from None
        if _bond_gated_unbonded(coordinator):
            raise not_ready("setup_connect_failed", name=entry.title, hint=_connection_failure_hint(coordinator))
        last_attempt = (coordinator.connection_attempt_details or [{}])[-1]
        if last_attempt.get("connect_elapsed_seconds") is not None and last_attempt.get("error"):
            # The link came up, so range/power advice would mislead.
            raise not_ready("setup_startup_failed", name=entry.title, error=last_attempt['error'], hint=_connection_failure_hint(coordinator))
        raise not_ready("setup_connect_failed", name=entry.title, hint="")

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

    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
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
    async_forget_removed_entities(hass, entry.entry_id)
    # Unpair and combine restore other entries for the same beds first, so only
    # addresses nobody else owns lose their app state and estimates.
    owned = {
        owned_address
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
        for owned_address in _entry_addresses(other)
    }
    addresses = set(_entry_addresses(entry))
    unowned = addresses - owned
    await async_remove_position_estimates(hass, entry.entry_id, entry.data, unowned)
    # A combine that never absorbed its beds still raised their Remacro warnings
    # as its own. Give each back to the entry that still runs the bed before
    # Home Assistant removes the issues linked to this one.
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and addresses.intersection(_entry_addresses(other)):
            async_refresh_remacro_issues(hass, other)
    from homeassistant.helpers.storage import Store

    from .app_state_store import async_remove_app_states, pairlink_sdk_store_key

    # Re-adding a bed must not restore the removed entry's app state or session.
    try:
        await async_remove_app_states(hass, unowned)
        # Pairlink keys its metadata by entry, so no other entry ever reads it.
        for address in (None, *addresses):
            await Store(hass, 1, pairlink_sdk_store_key(entry.entry_id, address)).async_remove()
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
    coordinator = loaded_runtime(hass, entry.entry_id)
    if coordinator is not None and coordinator.consume_internal_entry_update(entry):
        # The coordinator recorded its own BLE bond marker. Reloading for that
        # would disconnect the bed, which is fatal for a bed that only grants
        # one connection per pairing window (issue #385).
        _LOGGER.debug("Skipping reload for %s: internal bond-marker update", entry.entry_id)
        return
    await hass.config_entries.async_reload(entry.entry_id)
