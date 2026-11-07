"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.field_visibility import (
    ConditionOperator,
    ConditionValue,
    FieldCondition,
)
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.translation import async_get_translations
from homeassistant.loader import IntegrationNotFound, async_get_integration
from homeassistant.setup import async_setup_component

from .actuator_groups import ACTUATOR_GROUPS
from .adapter import (
    discover_services,
    find_service_info_by_address,
    get_discovered_service_info,
    read_ble_device_info,
)
from .address_lock import async_get_connect_lock
from .app_profiles import (
    foreign_settings,
    hidden_generic_fields,
    is_per_side_variant,
    per_side_profile,
)
from .beds.remacro_protocol import add_remacro_model, app_for_variant
from .bluetooth_bond import (
    BondRemovalResult,
    BondSelectionStatus,
    LocalBondInventory,
    LocalBondRecord,
    async_read_local_bonds,
    async_remove_local_bond,
    select_local_bond,
)
from .bluetooth_freshness import (
    ADVERTISEMENT_WAIT_SECONDS,
    FreshnessStatus,
    async_gate_connection,
    async_wait_for_advertisement,
)
from .bluetooth_transport import (
    ConnectionPath,
    PathPrediction,
    TransportClass,
    async_describe_actual,
    async_describe_prediction,
    async_path_for_source,
    async_predict_path,
    client_source,
)
from .bond_verification import (
    CONF_BLE_BOND_CONTEXT,
    BondEvidence,
    BondOwner,
    BondVerificationStatus,
    async_verify_authenticated_access,
    async_verify_native_bond,
    bond_owner_from_entry,
    build_bond_context,
)
from .cluster018_profiles import APP_NAMES as CLUSTER018_APP_NAMES
from .const import (
    ADAPTER_AUTO,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_BEDSENSE,
    BED_TYPE_CLUSTER018,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ERGOMOTION_APP,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_ISLEEP,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    BEDS_WITH_PERCENTAGE_POSITIONS,
    BEDS_WITH_POSITION_FEEDBACK,
    CLUSTER033_BED_TYPES,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_BLE_DEVICE_NAME,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JIECANG_APP_PROFILE,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_LEGGETT_APP_PROFILE,
    CONF_LEGS_MAX_ANGLE,
    CONF_LIMOSS_REMOTE_THEME,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_READ_UUID,
    CONF_LP_LEGACY_WRITE_UUID,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PRIMARY,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_OCTO_PIN,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PAIRLINK_HOME_ID,
    CONF_PAIRLINK_HOST_SOURCE,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    CONF_PAIRLINK_ROLE,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_REVERSE_MOTORS,
    CONF_RICHMAT_REMOTE,
    CONF_RMCONTROL_PRODUCT,
    CONF_RMCONTROL_SIDE,
    CONF_SLEEPYS_ELITE_SELECTOR,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M1X12_PROFILE,
    CONF_STARCODE_M5X5_PROFILE,
    CONF_STARCODE_TRANSPORT_SELECTOR,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_DEFAULT,
    CONF_VIBRADORM_FLOOR_LIGHT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_RGB,
    CONF_VIBRADORM_VMAT_REMOTE,
    CONF_VMATBASIC_FLOOR_LEVEL,
    CONF_VMATBASIC_FLOOR_MINUTES,
    CONF_VMATBASIC_PROFILE,
    CONNECTION_PROFILE_BALANCED,
    CONNECTION_PROFILE_RELIABLE,
    CONNECTION_PROFILES,
    DEFAULT_BACK_MAX_ANGLE,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_LEGS_MAX_ANGLE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DOMAIN,
    IDLE_DISCONNECT_KEEP_CONNECTED,
    JIECANG_APP_PROFILES,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_PURPLE,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANT_SIMON_LI,
    KEESON_VARIANT_SLEEP_HARMONY,
    LEGGETT_APP_DEFAULT_PROFILE,
    LEGGETT_APP_MOTOR_COUNTS,
    LEGGETT_APP_PROFILES,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    NAME_RULE_VARIANTS_BY_BED_TYPE,
    OCTO_VARIANT_STAR2,
    OKIN_BEDDING_APP_BED_TYPES,
    OKIN_CST_THREE_MOTOR_VARIANTS,
    OKIN_CST_VARIANTS,
    OKIN_DOT_FURNIMOVE_VARIANTS,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    PAIRLINK_ROLE_CENTRAL,
    PAIRLINK_ROLE_PERIPHERAL,
    POSITION_MODE_ACCURACY,
    POSITION_MODE_SPEED,
    PRODUCT_TYPES,
    REMACRO_VARIANT_JEROMES,
    REMACRO_VARIANT_THE_BRICK,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_MH_APPS,
    RICHMAT_MH_BED_TYPES,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_REMOTES,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    RUNTIME_BOND_KEYS,
    SIDE_LEFT,
    SIDE_RIGHT,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
    SOLACE_VARIANT_WOOSA,
    STARCODE_APP_CONNECTION_TIMEOUT_SECONDS,
    SVANE_VARIANT_JENSEN_LINON,
    SVANE_VARIANT_JMC,
    SVANE_VARIANTS,
    VARIANT_AUTO,
    VARIANT_REQUIRED_BED_TYPES,
    VIBRADORM_APP_CONFIG_KEYS,
    VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS,
    VIBRADORM_APP_PROFILES,
    VIBRADORM_RESTORED_CONTROLS,
    VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS,
    VIBRADORM_WERKMEISTER_CONTROLS,
    VMATBASIC_CONFIG_KEYS,
    VMATBASIC_PROFILES,
    ZSERIES_PULSE_COUNT_RANGE,
    ZSERIES_VARIANT_Z230,
    ZSERIES_VARIANT_Z280,
    DetectionResult,
    bed_type_has_position_feedback,
    disconnect_after_command_default_enabled,
    get_motor_pulse_defaults,
    get_richmat_features,
    get_richmat_motor_count,
    grants_one_connection_per_pairing_window,
    passive_position_reconciliation_default_enabled,
    requires_pairing,
    requires_pairing_after_service_discovery,
    resolve_explicit_bed_type,
    supports_passive_position_reconciliation,
)
from .detection import (
    APP_VARIANT_CHOICES,
    FAMILY_ROW_SEPARATOR,
    FAMILY_ROWS,
    FAMILY_STEP_ROUTES,
    HIDDEN_APP_CHOICES,
    PRODUCT_QUESTION_BED_TYPES,
    PROTOCOL_ROUTES,
    bed_type_choice,
    bed_type_label,
    detect_bed_type,
    detect_bed_type_detailed,
    detect_richmat_remote_from_name,
    family_row_label,
    get_bed_type_options,
    is_jensen_linon_name,
    is_mac_like_name,
    resolve_bed_type_choice,
)
from .discovery_log import async_get_discovery_log
from .discovery_settings import (
    async_is_discovery_disabled,
    async_set_discovery_disabled,
)
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .octo_auth import OctoPinStatus, async_verify_octo_pin
from .pairing import (
    KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS,
    build_pair_entry_data,
    build_single_address_pair_entry_data,
    effective_child_data,
    get_child,
    inheritable_child_fields,
    is_paired,
    iter_children,
    pair_member_addresses,
    supports_single_address_pairing,
    with_updated_child,
)
from .pairing_candidates import (
    CONF_PAIR_SELECTION,
    active_pairing_candidates,
    build_pair_selection_schema,
    selected_pair_ids,
)
from .position_estimate_flow import EstimatedPositionsFlowMixin
from .profile_id import with_profile_ids
from .profile_migration import (
    CUSTOMATIC_FAMILY,
    JENSEN_FAMILY,
    JIECANG_FAMILY,
    JORDANS_FAMILY,
    KEESON_FAMILY,
    LEGGETT_FAMILY,
    LIMOSS_FAMILY,
    LOGICDATA_FAMILY,
    MALOUF_FAMILY,
    MANAGED_FAMILIES,
    OKIN_FAMILY,
    SLEEPYS_FAMILY,
    SOLACE_FAMILY,
    VIBRADORM_FAMILY,
    ManagedFamily,
    MigrationSnapshot,
    async_control_changes,
    reconfigure_family,
)
from .remacro_discovery import remacro_entry_problem, remacro_manufacturer_data
from .setup_operation import (
    BluetoothOperationMixin,
    ConnectionLifetimePolicy,
    OperationOutcome,
    OperationResult,
    SetupAction,
)
from .setup_questions import (
    GENERIC_FIELDS,
    FlowContext,
    Question,
    SetupProfile,
    setup_profile,
    setup_profile_for,
)
from .unsupported import (
    PROXY_PAIRING_RECOVERY_URL,
    build_misidentified_issue_url,
    capture_device_info,
)
from .validators import (
    get_available_adapters,
    get_variants_for_bed_type,
    is_valid_mac_address,
    is_valid_octo_pin,
    is_valid_variant_for_bed_type,
    normalize_octo_pin,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.device import BLEDevice

    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

CONFIGURED_RETRY_PREFIX = "configured_retry::"

# Minimum confidence for a detected bed type to be suggested in the app question.
# Below it, or when detection is ambiguous (shared-UUID guesses such as OKIN
# receivers), nothing is suggested and the user chooses.
_AUTO_DETECT_MIN_CONFIDENCE = 0.7
# Explicit app candidates offered beside a confident match are hints, not ambiguity.
_EXPLICIT_APP_HINTS = frozenset(
    {BED_TYPE_CLUSTER018, BED_TYPE_MOTOMOTION, BED_TYPE_GOODVIBE, BED_TYPE_HJBED, BED_TYPE_ESHINE_OKIN, BED_TYPE_ISLEEP, BED_TYPE_STARCODE_ABM5_4, BED_TYPE_MOTION_BED, BED_TYPE_VMATBASIC, BED_TYPE_FURNIMOVE,
     BED_TYPE_GMMOTOR, "gmmotor_sleep_mm", "gmmotor_sleep_sxb"}
)


def _is_valid_rmcontrol_variant(product: object, variant: str) -> bool:
    """Validate the opt-in against the transports supported by its controller."""
    return not product or variant in (VARIANT_AUTO, RICHMAT_VARIANT_NORDIC, RICHMAT_VARIANT_WILINKE)


def _classify_connection_failure(err: BaseException) -> OperationOutcome:
    """Map a BLE failure to the outcome that produces the right advice.

    Beds allow one connection at a time and proxies have a fixed number of
    slots, so "someone else is using it" and "there was no room" are ordinary,
    recoverable situations with specific remedies. Telling a user their pairing
    failed when the bed's own remote is simply connected sends them to
    power-cycle hardware for no reason.
    """
    if isinstance(err, TimeoutError):
        return OperationOutcome.TIMEOUT
    message = str(err).lower()
    if "no backend with an available connection slot" in message or (
        "slot" in message and "available" in message
    ):
        return OperationOutcome.NO_CONNECTION_SLOTS
    if "in use" in message or "already connected" in message or "busy" in message:
        return OperationOutcome.CONNECTION_IN_USE
    if "timed out" in message or "timeout" in message:
        return OperationOutcome.TIMEOUT
    return OperationOutcome.CONNECTION_FAILED


async def _async_translation(hass: HomeAssistant, category: str, key: str, default: str) -> str:
    """Return a translated string from a flow catalogue, or an English default.

    ``category`` is ``config`` or ``options``: Home Assistant keeps them as
    separate namespaces, and the options flow cannot read config keys.
    """
    try:
        translations = await async_get_translations(hass, hass.config.language, category, {DOMAIN})
    except Exception:  # noqa: BLE001 - a missing translation must not block a flow
        return default
    return translations.get(f"component.{DOMAIN}.{category}.{key}", default)


# English fallbacks for the pairing form's bond-state line. The shipped text
# lives in strings.json; these only apply if a translation is missing.
_BOND_STATE_FALLBACKS: Final[dict[str, str]] = {
    "bond_state_proxy": (
        "ℹ️ This bed will pair through a Bluetooth proxy, which keeps the bond "
        "itself. Home Assistant cannot read or remove a bond stored on a proxy, "
        "so it cannot tell you whether one already exists."
    ),
    "bond_state_unreadable": (
        "ℹ️ Home Assistant could not read the Bluetooth bonds on this host, so it "
        "cannot tell whether this bed is already paired."
    ),
    "bond_state_existing": (
        "✅ This Home Assistant host already has a Bluetooth bond for this bed. "
        "The actions below reflect whether the selected adapter can use it and "
        "whether it can be replaced safely."
    ),
    "bond_state_multiple": (
        "⚠️ More than one Bluetooth adapter on this host is bonded to this bed. "
        "Pairing again will use whichever adapter Home Assistant connects through."
    ),
    "bond_state_mismatched": (
        "ℹ️ This Home Assistant host has a Bluetooth bond for this bed, but on a "
        "different adapter from the one this connection will use. Bonds belong "
        "to one adapter, so that one cannot be used here. Pair again to create a "
        "bond on this adapter, or select the bonded adapter instead."
    ),
    "bond_state_route_uncertain": (
        "ℹ️ This Home Assistant host has a Bluetooth bond for this bed, but more "
        "than one adapter or proxy could take the connection, and Home Assistant "
        "chooses which when it connects. Setting up with the existing bond would "
        "assume a route it cannot guarantee, so pair again instead and let the "
        "connection record which transport really owns the bond."
    ),
    "bond_state_none": ("ℹ️ This Home Assistant host has no Bluetooth bond for this bed yet."),
}


# English fallbacks for the pairing result. The shipped text lives in
# strings.json; these only apply when a translation is missing.
_PAIRING_OUTCOME_FALLBACKS: Final[dict[str, str]] = {
    "native_verified_local": "A stored bond was confirmed on this Home Assistant adapter ({transport}).",
    "native_absent": (
        "❌ No stored bond was found for this bed on this Home Assistant adapter "
        "({transport}). Put the bed back into Bluetooth pairing mode and select "
        "**Try again**."
    ),
    "no_run": "❌ Pairing did not run. Select **Try again**.",
    "verified_local": (
        "✅ Paired, and the bond was confirmed. It is stored on this Home "
        "Assistant host ({transport})."
    ),
    "verified_proxy": (
        "✅ Paired, and the bond was confirmed. It is stored on the Bluetooth "
        "proxy {transport}, not on Home Assistant, so moving this bed to a "
        "different proxy will mean pairing again."
    ),
    "verified_unknown": (
        "✅ Paired, and the bond was confirmed. Home Assistant could not tell "
        "which adapter or proxy carried it, so it does not know where the bond "
        "is stored."
    ),
    "existing_verified_local": (
        "✅ The existing bond works. It is stored on this Home Assistant host "
        "({transport}), and setup will use it as it is."
    ),
    "existing_verified_proxy": (
        "✅ The existing bond works. It is stored on the Bluetooth proxy "
        "{transport}, so moving this bed to a different proxy will mean pairing "
        "again."
    ),
    "existing_verified_unknown": (
        "✅ The existing bond works, but Home Assistant could not tell which "
        "adapter or proxy carried the check, so it does not know where the bond "
        "is stored."
    ),
    "unproven": (
        "⚠️ Pairing completed, but this bed gives Home Assistant no way to "
        "confirm the bond. Setup will finish and record that pairing happened, "
        "so the first connection does not try to pair on top of it. If the bond "
        "did not really form, Home Assistant will raise a repair asking you to "
        "pair again."
    ),
    "not_advertising": (
        "❌ The bed is not advertising, so no connection was attempted. Put it "
        "into pairing mode or move it closer to an adapter or proxy, then select "
        "**Try again**."
    ),
    "route_mismatch": (
        "❌ Home Assistant connected through a different Bluetooth path. No new "
        "pairing was attempted. Check that the selected adapter or proxy can "
        "reach the bed, then select **Try again**."
    ),
    "auth_failed": (
        "❌ The bed connected, but the link is still unauthenticated, so the bond "
        "did not form. Put the bed back into pairing mode and select **Try "
        "again**."
    ),
    "auth_failed_proxy": (
        "❌ The bed connected through Bluetooth proxy **{transport}**, but "
        "authentication failed. Close the bed's phone app, put the bed back into "
        "Bluetooth pairing mode, and select **Try again** using the same proxy.\n\n"
        "If the same authentication error returns, saved pairing keys on the "
        "proxy may be stale. Follow the [step-by-step recovery guide]({recovery_url}). "
        "A normal wireless firmware update does not erase these keys. A full "
        "flash erase is a last resort: it removes the proxy's settings and ALL "
        "Bluetooth pairings, so save its configuration first."
    ),
    "inconclusive": (
        "⚠️ Home Assistant could not confirm the existing bond either way: the "
        "check timed out or the bed does not answer it. The bond may well be "
        "fine. You can try again, or pair from scratch if the bed does not "
        "respond afterwards."
    ),
    "unsupported": (
        "❌ This Bluetooth adapter or proxy cannot pair. ESPHome proxies need "
        "ESPHome 2024.3.0 or newer; otherwise pair through a Bluetooth adapter "
        "on the Home Assistant host."
    ),
    "removal_unconfirmed": (
        "⚠️ Home Assistant could not confirm what happened to the existing "
        "bond, so pairing was not attempted and the bond may still be in "
        "place. Check the host's Bluetooth settings, then select **Try "
        "again**."
    ),
    "removal_failed": (
        "❌ The existing bond could not be removed, so pairing was not attempted "
        "and the old bond is still in place. Try again, and use Remove the "
        "Bluetooth bond from the device's options if it persists."
    ),
    "in_use": (
        "❌ The bed's Bluetooth connection is already in use. Beds allow only one "
        "connection at a time, so close the manufacturer's app and put the "
        "physical remote down, then select **Try again**."
    ),
    "no_slots": (
        "❌ Every Bluetooth adapter and proxy that can reach this bed is out of "
        "free connections. Free one up, or add another proxy, then select **Try "
        "again**."
    ),
    "timed_out": (
        "❌ The bed stopped responding partway through. Put it back into pairing "
        "mode and select **Try again**."
    ),
    "cancelled": "❌ Pairing was cancelled.",
    "connection_failed": (
        "❌ Could not pair. Another app or the bed's own remote may be holding "
        "the bed's connection, or it may be out of range. Select **Try again**."
    ),
}


def _log_detached_replacement(task: asyncio.Task[OperationResult]) -> None:
    """Consume a bond replacement that outlived the flow that started it."""
    if task.cancelled():
        return
    if (err := task.exception()) is not None:
        _LOGGER.warning("Bond replacement failed after the flow closed: %s", err)
        return
    _LOGGER.info("Bond replacement finished after the flow closed: %s", task.result().outcome)


def _every_route_holds_bond(
    prediction: PathPrediction,
    inventory: LocalBondInventory,
    record: LocalBondRecord,
) -> bool:
    """Return True when every route that may ever connect holds ``record``.

    ``prediction.chosen`` is advisory by design: Home Assistant re-ranks every
    connectable scanner inside ``connect()``, so a route is only certain when
    there is nothing else it could pick. Certifying a bond persists a marker
    that suppresses ``pair=True`` without ever connecting, so betting on the
    prediction costs an ordinary bed a failed authentication and a retry, and a
    bed that grants one connection per pairing window its whole window.

    Every enumerated route counts, including one that cannot take a connection
    at this instant. ``can_connect`` is free-slot state and nothing more: a
    proxy that is out of slots now can have one free before the entry's first
    connection, and certifying against that snapshot is the same bet on a
    changing value. ``connectable`` is no better a filter, since the path
    enumeration itself falls back to the non-connectable view for proxies that
    misclassify a bed they can in fact reach.
    """
    if not prediction.paths:
        return False
    for path in prediction.paths:
        if path.transport is not TransportClass.LOCAL:
            return False
        selection = select_local_bond(
            inventory, owner_source=path.source, owner_adapter=path.adapter
        )
        if not selection.is_exact or selection.record != record:
            return False
    return True


def _matching_local_bond_route(
    prediction: PathPrediction,
    inventory: LocalBondInventory,
    record: LocalBondRecord,
) -> ConnectionPath | None:
    """Return one visible local route that owns ``record``.

    This is not a prediction that the route will win. It only supplies the
    source on which an existing bond can be checked. The verification path pins
    discovery to that source and still rejects the result if Home Assistant's
    eventual connection is re-routed elsewhere.
    """
    for path in prediction.paths:
        if path.transport is not TransportClass.LOCAL:
            continue
        selection = select_local_bond(
            inventory,
            owner_source=path.source,
            owner_adapter=path.adapter,
        )
        if selection.is_exact and selection.record == record:
            return path
    return None


class NotAdvertisingError(Exception):
    """Raised when a bed is not advertising, so no connection was attempted.

    Distinct from a pairing failure on purpose: the two need different advice,
    and conflating them is what sends users to re-seat a bond that was never the
    problem (issues #458 and #461).
    """

    def __init__(self, status: FreshnessStatus) -> None:
        """Record which kind of missing evidence stopped the attempt."""
        super().__init__(str(status))
        self.status = status


class BondRouteMismatchError(Exception):
    """Raised when existing-bond verification connects through another adapter."""


def _per_side_refusal(
    requested: tuple[str, str],
    sides: list[tuple[str | None, str | None]],
    changes: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Return the field and app label a shared two-address pair edit may not change.

    A per-side app profile belongs to one physical bed, so the shared form may
    not move either side to, from or between such profiles, change a side's
    own variant, or overwrite a side's own app settings.
    """
    profiles = [requested, *sides]
    if any(bed_type != requested[0] for bed_type, _ in sides):
        for bed_type, variant in profiles:
            if profile := per_side_profile(bed_type, variant):
                return CONF_BED_TYPE, profile.label
    if CONF_PROTOCOL_VARIANT in changes:
        for bed_type, variant in profiles:
            if is_per_side_variant(bed_type, variant) and (
                profile := per_side_profile(bed_type, variant)
            ):
                return CONF_PROTOCOL_VARIANT, profile.label
    for bed_type, variant in profiles:
        profile = per_side_profile(bed_type, variant)
        if profile is not None and (changed := profile.keys.intersection(changes)):
            return min(changed), profile.label
    return None


def _apply_bed_type_choice(user_input: dict[str, Any], shown_choice: str | None) -> None:
    """Resolve an app entry of the bed-type selector into bed type and variant.

    The app's variant applies only when the user picked that entry; an
    unchanged selector leaves the variant field in charge.
    """
    choice = user_input.get(CONF_BED_TYPE)
    if not isinstance(choice, str):
        return
    bed_type, variant = resolve_bed_type_choice(choice)
    if variant is None:
        return
    user_input[CONF_BED_TYPE] = bed_type
    if choice != shown_choice:
        user_input[CONF_PROTOCOL_VARIANT] = variant


def _setup_routes(bed_type: str | None) -> dict[str, str]:
    """Return the labelled routes a generic setup may choose for a bed type.

    App variants are their own bed-type entries, and a bed type whose app
    step asks for its own variant is left to that step.
    """
    if bed_type is None or bed_type in _APP_SETUP_STEPS:
        return {}
    return _labelled_routes(bed_type)


def _labelled_routes(bed_type: str) -> dict[str, str]:
    """Return a bed type's labelled routes, with the automatic one first."""
    variants = get_variants_for_bed_type(bed_type) or {}
    excluded = _SETUP_ROUTE_EXCLUSIONS.get(bed_type, frozenset())
    routes = {
        variant: label
        for variant, label in variants.items()
        if (bed_type, variant) not in APP_VARIANT_CHOICES and variant not in excluded
    }
    if routes and VARIANT_AUTO not in routes and is_valid_variant_for_bed_type(bed_type, VARIANT_AUTO):
        # The bed type accepts its automatic route without labelling it.
        routes = {VARIANT_AUTO: "Auto-detect (recommended)", **routes}
    return routes


# FurniMove's DOT handsets belong to the FurniMove app profile, not a fresh DOT setup.
_SETUP_ROUTE_EXCLUSIONS: Final[dict[str, frozenset[str]]] = {
    BED_TYPE_OKIN_DOT: frozenset(OKIN_DOT_FURNIMOVE_VARIANTS),
}


def _route_section(bed_type: str | None, default: str) -> section | None:
    """Return a collapsed Advanced section with a bed type's labelled routes."""
    routes = _setup_routes(bed_type)
    if len(routes) < 2:
        return None
    if default not in routes:
        default = VARIANT_AUTO if VARIANT_AUTO in routes else next(iter(routes))
    field = SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=key, label=label) for key, label in routes.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    return section(
        vol.Schema({vol.Required(CONF_PROTOCOL_VARIANT, default=default): field}),
        {"collapsed": VARIANT_AUTO in routes},
    )


def _variant_errors_to_base(errors: dict[str, str]) -> dict[str, str]:
    """Show a route error on a form that has no route field."""
    if (error := errors.pop(CONF_PROTOCOL_VARIANT, None)) is not None:
        errors.setdefault("base", error)
    return errors


_VIBRADORM_FAMILY_TYPES: Final = VIBRADORM_FAMILY.bed_types


def _bed_type_selector(
    default: str | None, *, show_saved_id: bool = False
) -> _SearchableSelect:
    """Return the bed-type selector, keeping a default the list does not offer."""
    options = [_with_family(option) for option in get_bed_type_options()]
    if show_saved_id:
        # The StarCode and Richmat apps and the Reverie and Sleep Number
        # receivers have no guided change, and another bed type reaches the
        # Jensen JMC400 route only here, so Configure lists each by its own
        # label; setup asks behind the family row. Configure lists the
        # protocol-named routes the same way.
        unguided = {
            *(bed_type for bed_type, _variant, _step in _STARCODE_APPS.values()),
            *(bed_type for bed_type, _service in _REVERIE_ROUTES.values()),
            *(bed_type for bed_type, _service in _SLEEP_NUMBER_ROUTES.values()),
            *RICHMAT_MH_BED_TYPES,
            BED_TYPE_JENSEN,
            # Protocol-named routes are off the setup list but stay selectable.
            *PROTOCOL_ROUTES,
        }
        # The classic Richmat apps are app rows, each with the app's own label.
        unguided_apps = {
            bed_type_choice(BED_TYPE_CLUSTER018, app): APP_VARIANT_CHOICES[BED_TYPE_CLUSTER018, app]
            for app in CLUSTER018_APP_NAMES
        }
        options = sorted(
            [
                *(
                    option
                    for option in options
                    if option["value"] not in unguided and option["value"] not in unguided_apps
                ),
                *(
                    _with_family(SelectOptionDict(value=bed_type, label=bed_type_label(bed_type)))
                    for bed_type in unguided
                ),
                *(
                    _with_family(SelectOptionDict(value=value, label=label))
                    for value, label in unguided_apps.items()
                ),
            ],
            key=lambda option: option["label"].lower(),
        )
    family_row = (
        BED_TYPE_VIBRADORM
        if default in (BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC)
        else BED_TYPE_JIECANG_APP
        if default in (BED_TYPE_JIECANG, BED_TYPE_COMFORT_MOTION) and not show_saved_id
        else BED_TYPE_FURNIMOVE
        if default in OKIN_FAMILY.bed_types - {BED_TYPE_FURNIMOVE} and not show_saved_id
        else BED_TYPE_LEGGETT_OKIN
        if default in LEGGETT_FAMILY.bed_types - {BED_TYPE_LEGGETT_OKIN} and not show_saved_id
        else BED_TYPE_SLEEPYS_ELITE_APP
        if default in SLEEPYS_FAMILY.bed_types - {BED_TYPE_SLEEPYS_ELITE_APP}
        and not show_saved_id
        else BED_TYPE_MALOUF_APP
        if default in MALOUF_FAMILY.bed_types - {BED_TYPE_MALOUF_APP} and not show_saved_id
        else BED_TYPE_LOGICDATA_APP
        if default in (BED_TYPE_LOGICDATA, BED_TYPE_LOGICDATA_AIR_PUMP) and not show_saved_id
        else BED_TYPE_SVANE
        if default == BED_TYPE_JENSEN and not show_saved_id
        else _APP_FAMILY_ROWS.get(default or "")
        if not show_saved_id
        else None
    )
    if family_row is not None and default is not None:
        # The family row keeps the route it was drawn for; its step offers Keep.
        for option in options:
            if option["value"] == family_row:
                option["value"] = default
    if (
        default is not None
        and default not in {option["value"] for option in options}
    ):
        # Legacy aliases (e.g. dewertokin) and app types without an automatic
        # variant are not listed, but stay selectable for an existing choice.
        bed_type, variant = resolve_bed_type_choice(default)
        # A hidden app row keeps its own label, never its bed type's.
        label = _with_family(
            SelectOptionDict(
                value=default,
                label=(
                    APP_VARIANT_CHOICES[bed_type, variant]
                    if variant is not None
                    else bed_type_label(bed_type)
                ),
            )
        )["label"]
        if show_saved_id and label != bed_type:
            # Configure names the saved ID beside its friendly label.
            label = f"{label} (saved as {bed_type})"
        options.insert(0, SelectOptionDict(value=default, label=label))
    # Configure still accepts a family's route by its ID, as a suggested profile
    # submits it; the picker itself shows only the family row.
    return _SearchableSelect(
        options, accepted=FAMILY_STEP_ROUTES | HIDDEN_APP_CHOICES if show_saved_id else ()
    )


class _SearchableSelect(SelectSelector):
    """A long select users can search by label, showing labels only.

    Home Assistant 2026.11 filters a select only when it allows a custom value,
    and that picker shows the submitted value as its text. Each option's value
    is therefore its label; validation maps it back to the choice, and also
    accepts the choice itself. A custom value is never accepted.
    """

    def __init__(self, options: list[SelectOptionDict], *, accepted: Iterable[str] = ()) -> None:
        self._choices = {option["label"]: option["value"] for option in options}
        self._labels = {option["value"]: option["label"] for option in options}
        # Choices accepted by value without a row of their own.
        self._accepted = tuple(accepted)
        super().__init__(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=option["label"], label=option["label"])
                    for option in options
                ],
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

    def rows(self) -> Mapping[str, str]:
        """Return each row's submitted value (its label) and the choice it selects."""
        return dict(self._choices)

    def shown(self, choice: object) -> object:
        """Return the value the picker shows for a choice."""
        return self._labels.get(choice, choice) if isinstance(choice, str) else choice

    def __call__(self, data: Any) -> Any:
        # Home Assistant's selector typing does not declare __call__.
        listed: Any = SelectSelector(
            SelectSelectorConfig(options=[*self._choices, *self._labels, *self._accepted])
        )
        value = listed(cast(Any, super()).__call__(data))
        return self._choices.get(value, value)


_APP_NOT_LISTED: Final = "not_listed"
_FAMILY_NOT_SURE: Final = "not_sure"
# A discovered bed's app question searches every app with this answer.
_ANOTHER_APP: Final = "another"
# Longer lists of a bed type's rows become a searchable picker.
_LIST_ROWS: Final = 12


def _bed_type_rows(route: str) -> dict[str, str]:
    """Return a route's bed-type list rows, label to choice: its own and its apps'.

    A bed type that runs only as one of its apps offers just the apps.
    """
    bed_type, _variant = resolve_bed_type_choice(route)
    rows = {
        label: choice
        for label, choice in _bed_type_selector(route).rows().items()
        if resolve_bed_type_choice(choice)[0] == bed_type
    }
    if bed_type in VARIANT_REQUIRED_BED_TYPES and any(choice != bed_type for choice in rows.values()):
        rows = {label: choice for label, choice in rows.items() if choice != bed_type}
    return rows


def _default_setup_route(bed_type: str) -> str:
    """Return the route a new bed starts on when its row names none.

    A row that asks its app's product starts on none, so nothing is guessed.
    """
    if bed_type in VARIANT_REQUIRED_BED_TYPES and bed_type not in PRODUCT_QUESTION_BED_TYPES:
        apps = [variant for app_bed_type, variant in APP_VARIANT_CHOICES if app_bed_type == bed_type]
        if apps:
            return apps[0]
    routes = _setup_routes(bed_type)
    return VARIANT_AUTO if VARIANT_AUTO in routes or not routes else next(iter(routes))


def _offer_another_app(schema: vol.Schema) -> vol.Schema:
    """Add "Another app or remote" to a family question's answers, before Keep.

    The answer field is ``choice``, or ``app`` for Vibradorm's question.
    """
    fields = dict(schema.schema)
    for marker, selector in fields.items():
        if marker not in ("choice", "app") or not isinstance(selector, SelectSelector):
            continue
        options = list(selector.config["options"])
        values = [option if isinstance(option, str) else option["value"] for option in options]
        if _ANOTHER_APP not in values:
            another: str | SelectOptionDict = (
                _ANOTHER_APP
                if all(isinstance(option, str) for option in options)
                else SelectOptionDict(
                    value=_ANOTHER_APP, label="Another app or remote: search every app"
                )
            )
            options.insert(values.index("keep") if "keep" in values else len(options), another)
            fields[marker] = SelectSelector(
                SelectSelectorConfig(**{**selector.config, "options": options})
            )
        return vol.Schema(fields)
    return schema


def _family_rows(detected: str | None = None) -> list[tuple[str, str]]:
    """Return the brand list's rows, as (choice, label), from the bed-type list.

    Each brand group gives the rows that open a family question, as the list
    shows its routes; a group with one bed type gives that row, and a group
    with no family question gives its own rows. Its protocol-named routes,
    which the app question does not list, are rows too. A ``detected`` route
    keeps its place under its family's row, as in the app question.
    """
    listed = {choice: label for label, choice in _bed_type_selector(detected).rows().items()}
    by_label = {label: choice for choice, label in listed.items()}

    def row_for(choice: str) -> str | None:
        if choice in listed:
            return choice
        # A family route is reached through its family's row.
        return by_label.get(str(_bed_type_selector(choice).shown(choice)))

    rows: dict[str, str] = {}
    for routes in ACTUATOR_GROUPS.values():
        choices = [row_for(bed_type_choice(bed_type, variant)) for bed_type, variant in routes]
        families = [
            choice
            for choice in choices
            if choice is not None
            and choice in _APP_SETUP_STEPS
            and _APP_SETUP_STEPS[choice] in _FAMILY_STEPS
        ]
        for choice in families or choices:
            if choice is not None:
                rows.setdefault(choice, _brand_first(choice, listed[choice]))
        # The protocol-named routes are off the app question; the brand list keeps them.
        for bed_type, _variant in routes:
            if bed_type in PROTOCOL_ROUTES:
                rows.setdefault(bed_type, bed_type_label(bed_type))
    return sorted(rows.items(), key=lambda row: row[1].lower())


def _brand_first(choice: str, label: str) -> str:
    """Name a family row by its brand first, "<family>: <apps>", for the brand list.

    A detected route takes its family row's value, so the row is found by label.
    """
    row = next(
        (row for row, _names in FAMILY_ROWS.items() if row == choice or family_row_label(row) == label),
        None,
    )
    if row is None:
        return label
    family, apps = FAMILY_ROWS[row]
    return f"{family}: {apps}"


def _family_name(info: BluetoothServiceInfoBleak) -> str:
    """Name a discovered bed's family as its row in the bed-type list names it.

    A family row reads "<Family>: <its apps>" and another row "<Name> (<apps or
    models>)", so the part before the colon or parenthesis names the family.
    """
    bed_type = detect_bed_type(info) or BED_TYPE_DIAGNOSTIC
    if (family := _row_family(bed_type)) is not None:
        return family
    return bed_type_label(bed_type).split(" (", 1)[0]


def _bed_type_field(
    marker: type[vol.Required] | type[vol.Optional],
    default: str | None,
    **selector_options: Any,
) -> tuple[vol.Marker, _SearchableSelect]:
    """Return the bed-type marker and selector, defaulting to the shown label."""
    selector = _bed_type_selector(default, **selector_options)
    if default is None:
        return marker(CONF_BED_TYPE), selector
    return marker(CONF_BED_TYPE, default=selector.shown(default)), selector


def _rows_where(
    rows: Mapping[str, tuple[str | None, str]],
    test: Callable[[str | None, str], bool],
    operator: Literal["in", "not_in"] = "in",
    field: str = CONF_BED_TYPE,
) -> FieldCondition | None:
    """Return a condition on ``field`` for the rows that pass ``test``."""
    matching: list[ConditionValue] = [
        label for label, (bed_type, variant) in rows.items() if test(bed_type, variant)
    ]
    if not matching:
        return None
    return FieldCondition(field=field, operator=ConditionOperator(operator), value=matching)


def _shown_for(fields: Mapping[vol.Marker, Any], visible: FieldCondition) -> dict[vol.Marker, Any]:
    """Return the fields as native conditional fields shown only when ``visible`` holds.

    A field that already has a condition is shown only when both hold.
    """
    from homeassistant import data_entry_flow

    shown: dict[vol.Marker, Any] = {}
    for marker, validator in fields.items():
        condition: FieldCondition | list[FieldCondition] = visible
        if (existing := getattr(marker, "visible", None)) is not None:
            condition = [*(existing if isinstance(existing, list) else [existing]), visible]
        if not isinstance(marker, vol.Required | vol.Optional):
            raise TypeError(f"{marker.schema} is not a form field")
        marker_type = (
            data_entry_flow.Required
            if isinstance(marker, vol.Required)
            else data_entry_flow.Optional
        )
        shown[
            marker_type(
                marker.schema,
                default=marker.default,
                description=marker.description,
                visible=condition,
            )
        ] = validator
    return shown


def _condition_owned_generic_fields(
    schema: dict[vol.Marker, Any],
    rows: Mapping[str, tuple[str | None, str]],
    field: str = CONF_BED_TYPE,
    keep: Collection[str] = frozenset(),
) -> None:
    """Hide each generic field for the rows of ``field`` whose profile sets it itself.

    One form serves every row, so nothing redraws when another row is chosen.
    """
    for marker in tuple(schema):
        key = marker.schema
        if key not in GENERIC_FIELDS or key == field or key in keep:
            continue

        def owns(bed_type: str | None, variant: str, key: str = key) -> bool:
            return key in hidden_generic_fields(bed_type, variant)

        if all(owns(*profile) for profile in rows.values()):
            # Every row sets it, so no choice on this form can show it.
            del schema[marker]
            continue
        owners = _rows_where(rows, owns, "not_in", field)
        if owners is not None:
            schema.update(_shown_for({marker: schema.pop(marker)}, owners))


def _hide_owned_generic_fields(
    schema: dict[vol.Marker, Any],
    bed_type: str | None,
    variant: str | None,
    keep: Collection[str] = frozenset(),
) -> None:
    """Drop the generic fields the selected app profile sets itself, except ``keep``."""
    hidden = hidden_generic_fields(bed_type, variant) - set(keep)
    for marker in tuple(schema):
        if marker.schema in hidden:
            del schema[marker]


def _limoss_remote_features_left(
    previous: Mapping[str, Any], staged: Mapping[str, Any]
) -> tuple[bool, bool] | None:
    """Return the light and massage to keep when leaving enabled Limoss Remote features.

    None when nothing is turned off: only an enabled Limoss Remote feature has
    OFF commands to send.
    """
    if previous.get(CONF_BED_TYPE) != BED_TYPE_LIMOSS_REMOTE:
        return None
    remote = staged.get(CONF_BED_TYPE) == BED_TYPE_LIMOSS_REMOTE
    light = remote and bool(staged.get(CONF_HAS_LIGHT, False))
    massage = remote and bool(staged.get(CONF_HAS_MASSAGE, False))
    if (previous.get(CONF_HAS_LIGHT, False) and not light) or (
        previous.get(CONF_HAS_MASSAGE, False) and not massage
    ):
        return light, massage
    return None


async def _async_turn_off_limoss_remote_features(
    runtime: object, light: bool, massage: bool, *, side: str | None = None
) -> bool:
    """Send the Limoss Remote OFF commands through the live runtime; True once done.

    ``side`` names one receiver of a separate-address pair. Its commands run
    through the pair, so they take the pair's command lanes like its entities.
    A cancelled, replaced or failed command returns False, so the caller keeps
    the saved setup.
    """
    from .beds.limoss_remote import apply_limoss_remote_features
    from .coordinator import AdjustableBedCoordinator
    from .paired_coordinator import PairedBedCoordinator

    pair = runtime if side is not None and isinstance(runtime, PairedBedCoordinator) else None
    receiver = pair.child_for_side(side) if pair is not None and side is not None else runtime
    if (side is not None and pair is None) or not isinstance(receiver, AdjustableBedCoordinator):
        return False
    completed = False

    async def disable_features(controller: BedController) -> None:
        nonlocal completed
        await apply_limoss_remote_features(controller, light, massage, persist=False)
        if receiver.cancel_command.is_set():
            raise asyncio.CancelledError
        completed = True

    try:
        if pair is not None and side is not None:
            await pair.async_execute_controller_command(
                disable_features, side=side, cancel_running=True
            )
        else:
            await receiver.async_execute_controller_command(disable_features, cancel_running=True)
        # Replaced scheduler tickets return normally without completing their
        # callback. They cannot commit a change.
        if not completed:
            raise RuntimeError("Limoss Remote OFF transaction was interrupted")
    except Exception:
        _LOGGER.warning("Unable to complete Limoss Remote feature OFF transaction", exc_info=True)
        return False
    return True


def _checked_family(migrating: ManagedFamily, staged: Mapping[str, Any]) -> ManagedFamily:
    """The family whose check a staged route needs.

    A LOGICDATA route reached from another family's change, as the Comfort Motion
    review suggests one, still needs its own link check.
    """
    if staged.get(CONF_BED_TYPE) in LOGICDATA_FAMILY.bed_types:
        return LOGICDATA_FAMILY
    return migrating


_APP_SETUP_STEPS: Final[dict[str, str]] = {
    # Declared questions only: the app is its variant, chosen from the bed-type list.
    BED_TYPE_CLUSTER018: "profile_questions",
    **dict.fromkeys(CLUSTER033_BED_TYPES | {"ergomotion_4"}, "profile_questions"),
    # One row each asks the app's exact product.
    **dict.fromkeys(PRODUCT_QUESTION_BED_TYPES, "profile_questions"),
    BED_TYPE_VIBRADORM: "vibradorm",
    # The LOGICDATA question asks the app, and for Sleep Smart the bed base or pump.
    **dict.fromkeys(
        (BED_TYPE_LOGICDATA, BED_TYPE_LOGICDATA_APP, BED_TYPE_LOGICDATA_AIR_PUMP),
        "logicdata_family",
    ),
    **dict.fromkeys(JIECANG_FAMILY.bed_types, "jiecang_family"),
    **dict.fromkeys(OKIN_FAMILY.bed_types, "okin_family"),
    # A new Okin CST bed answers the Okin question with its apps first; CST is
    # not a guided family, so an existing entry keeps Configure.
    BED_TYPE_OKIN_CST: "okin_family",
    **dict.fromkeys(KEESON_FAMILY.bed_types, "keeson_family"),
    **dict.fromkeys(SOLACE_FAMILY.bed_types, "solace_family"),
    **dict.fromkeys(LEGGETT_FAMILY.bed_types, "leggett_family"),
    # Declared questions only: the layout is BedSense's own question.
    BED_TYPE_BEDSENSE: "profile_questions",
    # The StarCode apps' row asks the app; each app keeps its own step.
    BED_TYPE_STARCODE_ABM5_4: "starcode_family",
    # Declared questions only: each app's own answers, on the generic step.
    **dict.fromkeys(
        (
            BED_TYPE_MOTION_BED,
            BED_TYPE_DOUBLESLEEP,
            BED_TYPE_SLEEPTRACKER,
            BED_TYPE_ISLEEP,
            BED_TYPE_GMMOTOR,
            BED_TYPE_MOTOMOTION,
            "hush_base",
        ),
        "profile_questions",
    ),
    **dict.fromkeys(LIMOSS_FAMILY.bed_types, "limoss_family"),
    **dict.fromkeys((BED_TYPE_STARCODE_M1X12, BED_TYPE_STARCODE_M5X5), "profile_questions"),
    BED_TYPE_VIBRADORM_APP: "vibradorm",
    BED_TYPE_VMATBASIC: "vibradorm",
    BED_TYPE_LEGGETT_LP_LEGACY: "profile_questions",
    **dict.fromkeys(CUSTOMATIC_FAMILY.bed_types, "customatic_family"),
    **dict.fromkeys(JORDANS_FAMILY.bed_types, "jordans_family"),
    BED_TYPE_REMACRO: "remacro_family",
    BED_TYPE_REVERIE: "reverie_family",
    BED_TYPE_REVERIE_NIGHTSTAND: "reverie_family",
    BED_TYPE_SLEEP_NUMBER: "sleep_number_family",
    BED_TYPE_SLEEP_NUMBER_MCR: "sleep_number_family",
    **dict.fromkeys(SLEEPYS_FAMILY.bed_types, "sleepys_family"),
    # The classic apps keep their own declared questions above.
    **dict.fromkeys({BED_TYPE_RICHMAT, *RICHMAT_MH_BED_TYPES}, "richmat_family"),
    **dict.fromkeys(JENSEN_FAMILY.bed_types, "jensen_family"),
    **dict.fromkeys(MALOUF_FAMILY.bed_types, "malouf_family"),
}


def _name_rule_setup_name(bed_type: str | None, name: str | None) -> dict[str, str]:
    """Keep the raw Bluetooth name an app name rule reads, never the display name."""
    if (
        bed_type not in NAME_RULE_VARIANTS_BY_BED_TYPE and bed_type not in (BED_TYPE_GMMOTOR, BED_TYPE_MOTOMOTION)
    ) or name is None or is_mac_like_name(name):
        return {}
    return {CONF_BLE_DEVICE_NAME: name}


def _motor_count_options(
    bed_type: str | None,
    protocol_variant: str = DEFAULT_PROTOCOL_VARIANT,
) -> list[int]:
    """Return motor counts supported by the selected protocol."""
    if bed_type == BED_TYPE_SVANE and protocol_variant != SVANE_VARIANT_JENSEN_LINON:
        return [2]
    if bed_type == BED_TYPE_STARCODE_M5X5:
        return [2]
    if bed_type == BED_TYPE_OKIN_RF_ECO_BT:
        return [1]
    if bed_type == BED_TYPE_FURNIMOVE:
        return [1, 2, 3, 4]
    if bed_type in {
        *OKIN_BEDDING_APP_BED_TYPES,
        BED_TYPE_SIMMONS,
        BED_TYPE_CUSTOMATIC_CLARITY,
        BED_TYPE_CUSTOMATIC_JEROMES,
        # The pump has no motors; keep the stored count fixed and unused.
        BED_TYPE_LOGICDATA_AIR_PUMP,
    }:
        return [2]
    if bed_type in {BED_TYPE_CUSTOMATIC_REMEDY, BED_TYPE_ADJUSTABLE_LUMBAR}:
        return [3]
    if bed_type in RICHMAT_MH_BED_TYPES:
        # The selected app model's catalog fixes the axes; the count is unused.
        return [2]
    if bed_type == BED_TYPE_OCTO and protocol_variant != OCTO_VARIANT_STAR2:
        return [1, 2, 3, 4]
    if bed_type == BED_TYPE_OKIN_CST:
        return [3] if protocol_variant in OKIN_CST_THREE_MOTOR_VARIANTS else [2]
    if bed_type == BED_TYPE_SOLACE and protocol_variant == SOLACE_VARIANT_WOOSA:
        return [2]
    return [2, 3, 4]


def _is_valid_motor_count(
    bed_type: str | None,
    protocol_variant: str,
    motor_count: int,
) -> bool:
    """Return whether a motor count is valid for the selected protocol."""
    return motor_count in _motor_count_options(bed_type, protocol_variant)


def _richmat_mh_variant_error(
    bed_type: str | None, protocol_variant: str | None, name: str | None
) -> str | None:
    """Return a form error when the Richmat MH app could not resolve the model."""
    if bed_type not in RICHMAT_MH_APPS:
        return None
    from .beds.richmat_mh import resolve_model

    name = None if is_mac_like_name(name) else name
    _model, problem = resolve_model(RICHMAT_MH_APPS[bed_type], protocol_variant, name)
    return f"richmat_mh_{problem}" if problem else None


def _invalid_pulse_count(bed_type: str | None, pulse_count: int) -> bool:
    """Reject counts whose Z-Series press would fall outside the 0.1-60 s hold window."""
    low, high = ZSERIES_PULSE_COUNT_RANGE
    return bed_type == BED_TYPE_ZSERIES and not low <= pulse_count <= high


def _normalize_fixed_motor_count(
    bed_type: str | None,
    protocol_variant: str,
    motor_count: int,
) -> int:
    """Replace a stale form value when the profile fixes the motor count."""
    options = _motor_count_options(bed_type, protocol_variant)
    return options[0] if len(options) == 1 else motor_count


def _default_motor_count(
    bed_type: str | None,
    device_name: str | None = None,
) -> int:
    """Return the default motor count, including the historical OCTO RTV fallback."""
    if (
        bed_type == BED_TYPE_OCTO
        and device_name is not None
        and device_name.strip().lower().startswith("rtv")
    ):
        return 1
    if bed_type in {BED_TYPE_OKIN_CST, BED_TYPE_CUSTOMATIC_REMEDY}:
        return 3
    return DEFAULT_MOTOR_COUNT


def _confident_auto_detect(result: DetectionResult) -> str | None:
    """Return the detected bed type only for a high-confidence, unambiguous match.

    An explicit app hint does not defeat a confident receiver or name route.
    Shared app transports stay below the threshold and require a choice.
    """
    if (
        result.bed_type is not None
        and result.confidence >= _AUTO_DETECT_MIN_CONFIDENCE
        and not any(
            candidate not in _EXPLICIT_APP_HINTS for candidate in (result.ambiguous_types or ())
        )
    ):
        return result.bed_type
    return None


CONNECTION_PROFILE_OPTIONS: dict[str, str] = {
    CONNECTION_PROFILE_BALANCED: "Balanced (recommended)",
    CONNECTION_PROFILE_RELIABLE: "Reliable (slower connect)",
}

MALOUF_BED_TYPES = frozenset({BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN})


def _is_leggett_app_type(bed_type: str | None, variant: str | None = None) -> bool:
    """Resolve only the explicit Okin route of the legacy umbrella type."""
    return resolve_explicit_bed_type(bed_type, variant) == BED_TYPE_LEGGETT_OKIN


def _add_leggett_app_schema_field(
    schema: dict[vol.Marker, Any], current_data: dict[str, Any] | None = None
) -> None:
    current_data = current_data or {}
    schema[
        vol.Optional(
            CONF_LEGGETT_APP_PROFILE,
            default=current_data.get(CONF_LEGGETT_APP_PROFILE, LEGGETT_APP_DEFAULT_PROFILE),
        )
    ] = vol.In(LEGGETT_APP_PROFILES)


def _starcode_initial_transport(data: Mapping[str, Any], observed_name: str | None) -> str | None:
    """Resolve D from an explicit choice or original BLE identity, never a label."""
    from .beds.starcode_abm5_4_profiles import constructor_selector

    selected = data.get(CONF_STARCODE_TRANSPORT_SELECTOR)
    if isinstance(selected, str) and selected and selected != "auto":
        return selected
    original = data.get(CONF_BLE_DEVICE_NAME)
    if not isinstance(original, str) or not original:
        original = observed_name
    return constructor_selector(original) if isinstance(original, str) and original else None


def _starcode_setup_transport_present(client: BleakClient, selector: str) -> bool:
    """Require both selected app roles under their exact service UUID."""
    from .beds.starcode_abm5_4_profiles import TRANSPORTS

    transport = TRANSPORTS[selector]
    for service in client.services:
        if service.uuid.lower() == transport.service:
            roles = {char.uuid.lower() for char in service.characteristics}
            if {transport.write, transport.notify}.issubset(roles):
                return True
    return False


def starcode_live_transport_valid(hass: HomeAssistant, entry_id: str, selector: str) -> bool | None:
    """Check an entry's connected receiver without connecting or disturbing its link."""
    from bleak.exc import BleakError

    from .coordinator import AdjustableBedCoordinator

    runtime = hass.data.get(DOMAIN, {}).get(entry_id)
    if not isinstance(runtime, AdjustableBedCoordinator):
        return None
    client = runtime.client
    if client is None or client.is_connected is not True:
        return None
    try:
        if client.services is None:
            return None
        return _starcode_setup_transport_present(client, selector)
    except BleakError:
        # A just-connected client may not have completed GATT discovery.
        return None


def _limoss_remote_errors(data: dict[str, Any]) -> dict[str, str]:
    from .beds.limoss_remote import validate_limoss_remote_profile

    if data.get(CONF_PRODUCT_TYPE) not in PRODUCT_TYPES:
        return {CONF_PRODUCT_TYPE: "limoss_remote_product_required"}
    reverse = tuple(data.get(key, False) for key in CONF_REVERSE_MOTORS)
    try:
        validate_limoss_remote_profile(
            data[CONF_PRODUCT_TYPE],
            data.get(CONF_HAS_LIGHT, False),
            data.get(CONF_HAS_MASSAGE, False),
            (reverse[0], reverse[1], reverse[2], reverse[3]),
            data.get(CONF_LIMOSS_REMOTE_THEME),
        )
    except TypeError, ValueError:
        return {"base": "limoss_remote_invalid"}
    return {}


def _vibradorm_app_data(
    previous: Mapping[str, Any], submitted: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize explicit fresh defaults and clear incompatible retained state."""
    data = dict(previous)
    updates = dict(submitted)
    if CONF_VIBRADORM_APP_PROFILE in submitted and submitted[
        CONF_VIBRADORM_APP_PROFILE
    ] != previous.get(CONF_VIBRADORM_APP_PROFILE):
        for key in (*VIBRADORM_APP_CONFIG_KEYS - {CONF_VIBRADORM_APP_PROFILE}, CONF_HAS_MASSAGE):
            data.pop(key, None)
            updates.pop(key, None)
        data.pop(CONF_VIBRADORM_APP_METADATA, None)
        updates.pop(CONF_VIBRADORM_APP_METADATA, None)
    data.update(updates)
    app = data.get(CONF_VIBRADORM_APP_PROFILE)
    restored = data.get(CONF_VIBRADORM_RESTORED, False) if app == "caresse" else False
    data[CONF_VIBRADORM_RESTORED] = restored
    if app == "vmat":
        from .profiles.vibradorm import VMAT_REMOTES

        remote = data.get(CONF_VIBRADORM_VMAT_REMOTE)
        selected = VMAT_REMOTES.get(remote) if isinstance(remote, str) else None
        if selected is not None:
            data[CONF_VIBRADORM_CONTROL_TYPE] = str(selected.control_type)
            for key, flag in (
                (CONF_VIBRADORM_FLOOR_LIGHT, selected.floor_light),
                (CONF_VIBRADORM_RGB, selected.rgb),
                (CONF_HAS_MASSAGE, selected.massage),
                (CONF_VIBRADORM_LIGHT_EXTENSION, selected.light_extension),
            ):
                data[key] = flag
            if data.get(CONF_VIBRADORM_VMAT_REMOTE) != previous.get(CONF_VIBRADORM_VMAT_REMOTE):
                data.pop(CONF_VIBRADORM_APP_METADATA, None)
                data[CONF_VIBRADORM_FLOOR_DEFAULT] = 6 if selected.light_extension else 8
            else:
                data.setdefault(CONF_VIBRADORM_FLOOR_DEFAULT, 6 if selected.light_extension else 8)
        return data
    data.pop(CONF_VIBRADORM_VMAT_REMOTE, None)
    if not restored:
        data[CONF_VIBRADORM_CONTROL_TYPE] = (
            data.get(CONF_VIBRADORM_CONTROL_TYPE, "5") if app == "werkmeister" else "2"
        )
        data[CONF_VIBRADORM_FLOOR_LIGHT] = app == "werkmeister"
        for key in (CONF_VIBRADORM_RGB, CONF_HAS_MASSAGE, CONF_VIBRADORM_LIGHT_EXTENSION):
            data[key] = False
        data[CONF_VIBRADORM_FLOOR_DEFAULT] = 6
    else:
        if (
            not previous.get(CONF_VIBRADORM_RESTORED, False)
            and CONF_VIBRADORM_FLOOR_DEFAULT not in submitted
        ):
            # The fresh profile's hidden default is not a retained preference,
            # but a level answered on the same form is.
            data.pop(CONF_VIBRADORM_FLOOR_DEFAULT, None)
        data.setdefault(CONF_VIBRADORM_CONTROL_TYPE, "2")
        for key in (
            CONF_VIBRADORM_FLOOR_LIGHT,
            CONF_VIBRADORM_RGB,
            CONF_HAS_MASSAGE,
            CONF_VIBRADORM_LIGHT_EXTENSION,
        ):
            data.setdefault(key, False)
        data.setdefault(
            CONF_VIBRADORM_FLOOR_DEFAULT, 6 if data[CONF_VIBRADORM_LIGHT_EXTENSION] else 8
        )
    return data


def _vibradorm_app_errors(data: Mapping[str, Any]) -> dict[str, str]:
    """Validate the controller's immutable profile before making any BLE request."""
    from .profiles.vibradorm import validate_vibradorm_app_profile

    if data.get(CONF_VIBRADORM_APP_PROFILE) not in VIBRADORM_APP_PROFILES:
        return {CONF_VIBRADORM_APP_PROFILE: "vibradorm_app_required"}
    stored_control = data.get(CONF_VIBRADORM_CONTROL_TYPE)
    if isinstance(stored_control, bool) or not isinstance(stored_control, (int, str)):
        return {CONF_VIBRADORM_CONTROL_TYPE: "vibradorm_app_invalid"}
    if data[CONF_VIBRADORM_APP_PROFILE] == "vmat":
        from .profiles.vibradorm import VMAT_REMOTES

        if data.get(CONF_VIBRADORM_VMAT_REMOTE) not in VMAT_REMOTES:
            return {CONF_VIBRADORM_VMAT_REMOTE: "vibradorm_app_invalid"}
    choices = (
        VIBRADORM_WERKMEISTER_CONTROLS
        if data[CONF_VIBRADORM_APP_PROFILE] == "werkmeister"
        else VIBRADORM_RESTORED_CONTROLS
    )
    if data[CONF_VIBRADORM_APP_PROFILE] != "vmat" and stored_control not in choices:
        return {CONF_VIBRADORM_CONTROL_TYPE: "vibradorm_app_invalid"}
    floor_default = data.get(CONF_VIBRADORM_FLOOR_DEFAULT)
    if (
        isinstance(floor_default, bool)
        or not isinstance(floor_default, int)
        or not 1 <= floor_default <= 8
    ):
        return {CONF_VIBRADORM_FLOOR_DEFAULT: "vibradorm_app_invalid"}
    try:
        validate_vibradorm_app_profile(
            data[CONF_VIBRADORM_APP_PROFILE],
            "other" if stored_control == "other" else int(stored_control),
            restored=data.get(CONF_VIBRADORM_RESTORED, False),
            floor_light=data.get(CONF_VIBRADORM_FLOOR_LIGHT),
            rgb=data.get(CONF_VIBRADORM_RGB, False),
            massage=data.get(CONF_HAS_MASSAGE, False),
            light_extension=data.get(CONF_VIBRADORM_LIGHT_EXTENSION, False),
            remote=data.get(CONF_VIBRADORM_VMAT_REMOTE),
        )
    except TypeError, ValueError:
        return {"base": "vibradorm_app_invalid"}
    return {}


def _vmatbasic_data(previous: Mapping[str, Any], submitted: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(previous)
    if CONF_VMATBASIC_PROFILE in submitted and submitted[CONF_VMATBASIC_PROFILE] != previous.get(
        CONF_VMATBASIC_PROFILE
    ):
        # The old product's settings go; the ones answered for the new one stay.
        for key in VMATBASIC_CONFIG_KEYS - {CONF_VMATBASIC_PROFILE}:
            data.pop(key, None)
    data.update(submitted)
    if data.get(CONF_VMATBASIC_PROFILE) == "basic":
        for key in VMATBASIC_CONFIG_KEYS - {CONF_VMATBASIC_PROFILE}:
            data.pop(key, None)
    data.update(
        {
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_COUNT: 34,
            CONF_MOTOR_PULSE_DELAY_MS: 30,
            CONF_MOTOR_PULSE_USER_SET: False,
        }
    )
    return data


def _vmatbasic_errors(data: Mapping[str, Any]) -> dict[str, str]:
    from .profiles.vmatbasic import integer

    profile = data.get(CONF_VMATBASIC_PROFILE)
    if not isinstance(profile, str) or profile not in VMATBASIC_PROFILES:
        return {CONF_VMATBASIC_PROFILE: "vmatbasic_required"}
    for key, minimum, maximum in (
        (
            CONF_VMATBASIC_FLOOR_LEVEL,
            1 if profile == "xtbox" else 0,
            6 if profile == "xtbox" else 255,
        ),
        (CONF_VMATBASIC_FLOOR_MINUTES, 0, 255 if profile == "xtbox" else 1439),
    ):
        if key in data:
            try:
                integer(data[key], minimum, maximum)
            except ValueError:
                return {key: "vmatbasic_invalid"}
    return {}


def _show_profile_fields(
    schema: dict[vol.Marker, Any],
    bed_type: str | None,
    variant: str | None,
    rows: Mapping[str, tuple[str | None, str]] | None = None,
    field: str = CONF_BED_TYPE,
    keep: Collection[str] = frozenset(),
) -> None:
    """Fit a generic form to the selected profile.

    Configure offers Svane's app profiles by name rather than every variant
    slug; setup asks them in the Jensen / Svane family step. A form with a
    bed-type or route choice (``field``) hides each generic field for the rows
    whose profile sets it itself; a form for one profile drops them. Fields in
    ``keep`` are the profile's own questions and stay as they are.
    """
    if bed_type == BED_TYPE_SVANE and (rows is None or field != CONF_BED_TYPE):
        if variant not in SVANE_VARIANTS:
            variant = VARIANT_AUTO
        for marker in tuple(schema):
            if marker.schema == CONF_PROTOCOL_VARIANT:
                del schema[marker]
        schema[vol.Optional(CONF_PROTOCOL_VARIANT, default=variant)] = vol.In(SVANE_VARIANTS)
    if rows is not None:
        if field != CONF_BED_TYPE and CONF_PROTOCOL_VARIANT in hidden_generic_fields(
            bed_type, variant
        ):
            # A route field cannot hide itself; the profile owns the route.
            _hide_owned_generic_fields(schema, bed_type, variant, keep)
        _condition_owned_generic_fields(schema, rows, field, keep)
    else:
        _hide_owned_generic_fields(schema, bed_type, variant, keep)


# The Okin family's own routes, by the answer that selects each.
_OKIN_ROUTES: Final[dict[str, str]] = {
    "furnimove": BED_TYPE_FURNIMOVE,
    "okin_uuid": BED_TYPE_OKIN_UUID,
    "okin_dot": BED_TYPE_OKIN_DOT,
    "okin_rf_eco_bt": BED_TYPE_OKIN_RF_ECO_BT,
}
# English labels; strings.json translates the same keys.
_OKIN_ROUTE_LABELS: Final[dict[str, str]] = {
    "furnimove": "FurniMove / OKIN Smart Remote app",
    "okin_uuid": "No app: Okimat or OKIN handset code (requires pairing)",
    "okin_dot": "No app: DOT remote (RF34 or RF6707)",
    "okin_rf_eco_bt": "No app: single-actuator staircase, RF ECO BT (requires pairing)",
}
_OKIN_KEEP_LABEL: Final = "I don't know: keep the detected controls"
# The Okin CST products, each the route of the app its accepted report names
# (cluster 011, Nectar Move).
_OKIN_CST_APPS: Final[dict[str, str]] = {
    f"{BED_TYPE_OKIN_CST}:{variant}": variant
    for variant in OKIN_CST_VARIANTS
    if variant != VARIANT_AUTO
}


def _route_and_motors_schema(
    data: Mapping[str, Any], routes: Mapping[str, str], motor_counts: list[int]
) -> vol.Schema:
    """Ask a labelled route and the motor count, defaulting to the staged ones."""
    variant = data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
    motor_count = data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    return vol.Schema(
        {
            vol.Required(
                CONF_PROTOCOL_VARIANT,
                default=variant if variant in routes else next(iter(routes)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=key, label=label) for key, label in routes.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_MOTOR_COUNT,
                default=motor_count if motor_count in motor_counts else motor_counts[0],
            ): vol.All(vol.Coerce(int), vol.In(motor_counts)),
        }
    )


# The Keeson question's answers that expand into one exact app or route each.
_KEESON_GROUPS: Final[dict[str, tuple[tuple[str, str | None], ...]]] = {
    "ergomotion_apps": (
        (BED_TYPE_ERGOMOTION_APP, None),
        (BED_TYPE_ERGOMOTION_4, None),
        (BED_TYPE_SERTA_MP_REMOTE, None),
    ),
    "ore_apps": (
        (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES),
        (BED_TYPE_KEESON, KEESON_VARIANT_AMERICANSTAR),
        (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES),
        (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA),
        (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA),
        (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES),
    ),
    "okin_seating_apps": (
        (BED_TYPE_KEESON, KEESON_VARIANT_ADJUSTABLE_LITE),
        (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI),
        (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT),
        (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING),
    ),
    "purple_base_json": (
        (BED_TYPE_KEESON, KEESON_VARIANT_PURPLE),
        (BED_TYPE_KEESON, KEESON_VARIANT_BASE),
        (BED_TYPE_KEESON, KEESON_VARIANT_JSON),
    ),
}
_KEESON_RESTONIC: Final = frozenset({KEESON_VARIANT_RESTONIC_A, KEESON_VARIANT_RESTONIC_B})


# The L&P question's answers: each app's own route and layout, by its report.
_LEGGETT_ROUTES: Final[dict[str, tuple[str, Mapping[str, str]]]] = {
    "prodigy_ce": (BED_TYPE_LEGGETT_OKIN, {CONF_LEGGETT_APP_PROFILE: "prodigy4"}),
    "prodigy2": (BED_TYPE_LEGGETT_OKIN, {CONF_LEGGETT_APP_PROFILE: "prodigy2"}),
    "prodigy2l": (BED_TYPE_LEGGETT_OKIN, {CONF_LEGGETT_APP_PROFILE: "prodigy2l"}),
    "useries": (BED_TYPE_LEGGETT_OKIN, {CONF_LEGGETT_APP_PROFILE: "useries"}),
    # LP Control drives an LP BED receiver with its Okin profile; the route
    # keeps its default layout, which no LP Control product is proven to change.
    "lp_control_okin": (
        BED_TYPE_LEGGETT_OKIN,
        {CONF_LEGGETT_APP_PROFILE: LEGGETT_APP_DEFAULT_PROFILE},
    ),
    "lp_control_gen2": (BED_TYPE_LEGGETT_GEN2, {}),
    "lp_app_mlrm": (BED_TYPE_LEGGETT_WILINKE, {}),
    "lp_app_qrrm": (BED_TYPE_RICHMAT, {CONF_RICHMAT_REMOTE: RICHMAT_REMOTE_LP_QRRM}),
    "lp_legacy": (BED_TYPE_LEGGETT_LP_LEGACY, {}),
}
# The legacy L&P app's own settings.
_LP_LEGACY_KEYS: Final = (
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_WRITE_UUID,
    CONF_LP_LEGACY_READ_UUID,
)
# The umbrella ID's variant for each route it can run.
_LEGGETT_ALIAS_VARIANTS: Final[dict[str, str]] = {
    BED_TYPE_LEGGETT_GEN2: LEGGETT_VARIANT_GEN2,
    BED_TYPE_LEGGETT_OKIN: LEGGETT_VARIANT_OKIN,
    BED_TYPE_LEGGETT_WILINKE: LEGGETT_VARIANT_MLRM,
}


# The Jensen / Svane question's answers: each app with the bed it runs, as the
# bed type and variant each selects.
_JENSEN_ROUTES: Final[dict[str, tuple[str, str | None]]] = {
    "jensen_jmc400": (BED_TYPE_JENSEN, None),
    "jensen_linon": (BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON),
    "svane_bed": (BED_TYPE_SVANE, VARIANT_AUTO),
    "svane_jmc400": (BED_TYPE_SVANE, SVANE_VARIANT_JMC),
}


def _jensen_suggestion(bed_type: str, variant: str, name: str | None) -> str:
    """Return the answer the apps' own name rules pick for this bed.

    The Svane Remote app picks its JMC400 profile for a name with ``JMC``, and
    the Jensen app its LinOn profile for "Adjustable Bed" or "Jensen Bed".
    Every setup route suggests the same answer; the user confirms it.
    """
    from .svane_state import svane_profile_for_selected_name

    for answer, route in _JENSEN_ROUTES.items():
        if route == (bed_type, variant) and variant != VARIANT_AUTO:
            return answer
    if bed_type == BED_TYPE_JENSEN:
        return "jensen_jmc400"
    if name != "Svane Bed" and is_jensen_linon_name(name):
        return "jensen_linon"
    if svane_profile_for_selected_name(name) == "jmc":
        return "svane_jmc400"
    return "svane_bed"


# The Malouf question's answers, with the app each stages: the apps first,
# then the receiver routes.
_MALOUF_ROUTES: Final[dict[str, tuple[str, str | None]]] = {
    "malouf": (BED_TYPE_MALOUF_APP, "malouf"),
    "lucid": (BED_TYPE_MALOUF_APP, "lucid"),
    "nordic_uart": (BED_TYPE_MALOUF_NEW_OKIN, None),
    "ffe5": (BED_TYPE_MALOUF_LEGACY_OKIN, None),
}


# The Sleepy's question's answers: the app first, then the receiver routes.
_SLEEPYS_ROUTES: Final[dict[str, str]] = {
    "app": BED_TYPE_SLEEPYS_ELITE_APP,
    "box25": BED_TYPE_SLEEPYS_BOX25,
    "box24": BED_TYPE_SLEEPYS_BOX24,
    "box15": BED_TYPE_SLEEPYS_BOX15,
}


# The LOGICDATA question's answers: each app's bed type and app profile. Sleep
# Smart's bed base and air mattress pump are separate devices.
_LOGICDATA_ROUTES: Final[dict[str, tuple[str, str | None]]] = {
    "silvermotion": (BED_TYPE_LOGICDATA, None),
    "phone": (BED_TYPE_LOGICDATA_APP, "phone"),
    "tablet": (BED_TYPE_LOGICDATA_APP, "tablet"),
    "sleep_smart": (BED_TYPE_LOGICDATA_APP, "sleep_smart"),
    "sleep_smart_pump": (BED_TYPE_LOGICDATA_AIR_PUMP, None),
}


# The app-family questions' answers: each app's bed type, variant and own step.
_AppAnswer = tuple[str, str | None, str | None]
_CUSTOMATIC_APPS: Final[dict[str, _AppAnswer]] = {
    "clarity": (BED_TYPE_CUSTOMATIC_CLARITY, None, None),
    "jeromes": (BED_TYPE_CUSTOMATIC_JEROMES, None, None),
    "remedy": (BED_TYPE_CUSTOMATIC_REMEDY, None, None),
    "zseries_z230": (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230, None),
    "zseries_z280": (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280, None),
}
_JORDANS_APPS: Final[dict[str, _AppAnswer]] = {
    "serenity": (BED_TYPE_SERENITY, None, None),
    "tranquil": (BED_TYPE_TRANQUIL, None, None),
}
_STARCODE_APPS: Final[dict[str, _AppAnswer]] = {
    "m5x4": (BED_TYPE_STARCODE_ABM5_4, None, "profile_questions"),
    "m5x5": (BED_TYPE_STARCODE_M5X5, None, "profile_questions"),
    "m1x12": (BED_TYPE_STARCODE_M1X12, None, "profile_questions"),
}
# The Reverie question's answers: each receiver route and the service it advertises.
_REVERIE_ROUTES: Final[dict[str, tuple[str, str]]] = {
    "protocol_110": (BED_TYPE_REVERIE_NIGHTSTAND, REVERIE_NIGHTSTAND_SERVICE_UUID),
    "protocol_108": (BED_TYPE_REVERIE, REVERIE_SERVICE_UUID),
}
# The Sleep Number question's answers: each transport and the service it advertises.
_SLEEP_NUMBER_ROUTES: Final[dict[str, tuple[str, str]]] = {
    "fuzion": (BED_TYPE_SLEEP_NUMBER, SLEEP_NUMBER_SERVICE_UUID),
    "mcr": (BED_TYPE_SLEEP_NUMBER_MCR, SLEEP_NUMBER_MCR_SERVICE_UUID),
}
# The Remacro question's answers: the variant that selects each store app.
_REMACRO_APPS: Final[dict[str, str]] = {
    # Auto is the Slumberland app, as in v4.0.2.
    "slumberland": VARIANT_AUTO,
    "the_brick": REMACRO_VARIANT_THE_BRICK,
    "jeromes": REMACRO_VARIANT_JEROMES,
}
# The Richmat question's answers: each app's bed type and variant. RMControl and
# the remote controls share the Richmat route; the RMControl product tells them apart.
_RICHMAT_APPS: Final[dict[str, tuple[str, str | None]]] = {
    "rmcontrol": (BED_TYPE_RICHMAT, None),
    **{app: (bed_type, None) for bed_type, app in RICHMAT_MH_APPS.items()},
    **{app: (BED_TYPE_CLUSTER018, app) for app in CLUSTER018_APP_NAMES},
    "remote": (BED_TYPE_RICHMAT, None),
}

# The Limoss question's answers: the two apps, then the generic controls the
# family row and detection choose.
_LIMOSS_APPS: Final[dict[str, _AppAnswer]] = {
    "limoss_remote": (BED_TYPE_LIMOSS_REMOTE, None, "profile_questions"),
    "fsm_relax": (BED_TYPE_FSM_RELAX, None, "profile_questions"),
    "generic": (BED_TYPE_LIMOSS, None, None),
}
# The family question each app answer belongs to.
_ANSWER_STEPS: Final[dict[tuple[str, str | None], str]] = {
    **{answer[:2]: "customatic_family" for answer in _CUSTOMATIC_APPS.values()},
    **{answer[:2]: "jordans_family" for answer in _JORDANS_APPS.values()},
    **{answer[:2]: "starcode_family" for answer in _STARCODE_APPS.values()},
    **{answer[:2]: "limoss_family" for answer in _LIMOSS_APPS.values()},
    **dict.fromkeys(_RICHMAT_APPS.values(), "richmat_family"),
}
# Each app family's picker row, by the routes behind it. The first answer is the row.
_APP_FAMILY_ROWS: Final[dict[str, str]] = {
    **{
        bed_type: next(iter(apps.values()))[0]
        for apps in (_CUSTOMATIC_APPS, _JORDANS_APPS, _STARCODE_APPS)
        for bed_type, variant, _step in list(apps.values())[1:]
        # A model answer is a hidden app row, which keeps its own label.
        if variant is None
    },
    BED_TYPE_REVERIE: BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_SLEEP_NUMBER_MCR: BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_LIMOSS_REMOTE: BED_TYPE_LIMOSS,
    BED_TYPE_FSM_RELAX: BED_TYPE_LIMOSS,
}


# The Keeson question's answers, in the order the form lists them.
_KEESON_CHOICES: Final = (
    "sleep_harmony",
    "restonic",
    "ergomotion_apps",
    "ore_apps",
    "okin_seating_apps",
    "purple_base_json",
    "coolbase",
    "other_route",
    "keep",
)


def _keeson_route_label(bed_type: str, variant: str | None) -> str:
    """Label one exact Keeson answer: its app row, or its bed type or route."""
    if variant is None:
        return bed_type_label(bed_type)
    if (bed_type, variant) in APP_VARIANT_CHOICES:
        return APP_VARIANT_CHOICES[bed_type, variant]
    return (get_variants_for_bed_type(bed_type) or {}).get(variant, variant)


def _apply_route_defaults(data: dict[str, Any], bed_type: str, variant: str | None) -> None:
    """Give a newly chosen route the defaults Configure gives a bed-type change."""
    data[CONF_BED_TYPE] = bed_type
    variants = get_variants_for_bed_type(bed_type)
    if variant is None and variants:
        variant = (
            VARIANT_AUTO
            if is_valid_variant_for_bed_type(bed_type, VARIANT_AUTO)
            else next(iter(variants))
        )
    if variant is None:
        data.pop(CONF_PROTOCOL_VARIANT, None)
    else:
        data[CONF_PROTOCOL_VARIANT] = variant
    route_variant = variant or VARIANT_AUTO
    motor_counts = _motor_count_options(bed_type, route_variant)
    if data.get(CONF_MOTOR_COUNT) not in motor_counts:
        data[CONF_MOTOR_COUNT] = motor_counts[0]
    pulse_count, pulse_delay = get_motor_pulse_defaults(bed_type, route_variant)
    data[CONF_MOTOR_PULSE_COUNT] = pulse_count
    data[CONF_MOTOR_PULSE_DELAY_MS] = pulse_delay
    data[CONF_MOTOR_PULSE_USER_SET] = False
    data[CONF_DISABLE_ANGLE_SENSING] = not bed_type_has_position_feedback(bed_type, route_variant)


_JIECANG_LEGACY_ROUTES: Final[dict[str, str]] = {
    "legacy_jiecang": BED_TYPE_JIECANG,
    "legacy_lierda": BED_TYPE_COMFORT_MOTION,
}


def _configure_questions(
    data: Mapping[str, Any], saved_bed_type: object = None
) -> SetupProfile | None:
    """Return the declared questions Configure asks.

    An entry already on a managed family changes its route only through the
    guided change, so Configure leaves the family's route questions out. An
    entry switching in from another bed type still answers them here.
    """
    from .setup_questions import setup_profile_for

    profile = setup_profile_for(data)
    if profile is None or not profile.questions:
        return None
    saved = data.get(CONF_BED_TYPE) if saved_bed_type is None else saved_bed_type
    family = next(
        (
            family
            for family in MANAGED_FAMILIES
            if data.get(CONF_BED_TYPE) in family.bed_types and saved in family.bed_types
        ),
        None,
    )
    route_keys = set(family.route_keys) if family is not None else set()
    return dataclasses.replace(
        profile,
        questions=tuple(q for q in profile.questions if q.key not in route_keys),
    )


def _question_field(
    question: Question, data: Mapping[str, Any], context: FlowContext, *, visible: bool = False
) -> tuple[vol.Marker, Any]:
    """Return one declared question's form marker and validator.

    With ``visible`` the question's condition renders as a native conditional
    field; otherwise the caller has already decided the question is asked.
    """
    from homeassistant import data_entry_flow

    from .setup_questions import OPTIONAL, REQUIRED

    default = question.default_for(data, context)
    marker_type = (
        data_entry_flow.Required if default is REQUIRED else data_entry_flow.Optional
    )
    options = question.options(data, context)
    picker = (
        _SearchableSelect(
            [SelectOptionDict(value=str(key), label=label) for key, label in options.items()]
        )
        if question.searchable and options
        else None
    )
    marker = marker_type(
        question.key,
        default=(
            vol.UNDEFINED
            if default in (REQUIRED, OPTIONAL)
            else picker.shown(default)
            if picker is not None
            else default
        ),
        visible=question.when if visible else None,
    )
    if picker is not None:
        return marker, picker
    if question.multiple:
        if options is None:
            return marker, TextSelector(TextSelectorConfig(multiple=True))
        return marker, SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=str(key), label=label) for key, label in options.items()
                ],
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    if question.validator is not None:
        return marker, question.validator
    if question.text:
        return marker, str
    if options is None:
        return marker, bool
    if all(isinstance(key, int) for key in options):
        # The frontend returns a select's value as text.
        return marker, vol.All(vol.Coerce(int), vol.In(dict(options)))
    return marker, vol.In(dict(options))


def _profile_question_schema(
    profile: SetupProfile,
    data: Mapping[str, Any],
    context: FlowContext,
    *,
    advanced_section: bool = True,
) -> dict[vol.Marker, Any]:
    """Render a profile's questions, its advanced ones in a collapsed section."""
    schema: dict[vol.Marker, Any] = {}
    advanced: dict[vol.Marker, Any] = {}
    shown = {question.key for question in profile.questions}
    for question in profile.questions:
        # A condition on an answer this form does not ask, such as a route
        # Configure leaves to the guided change, is settled by the saved setup.
        visible = question.condition_fields() <= shown
        if not visible and not question.asked(data):
            continue
        marker, validator = _question_field(question, data, context, visible=visible)
        (advanced if question.advanced and advanced_section else schema)[marker] = validator
    if advanced:
        schema[vol.Optional("advanced")] = section(vol.Schema(advanced), {"collapsed": True})
    return schema


def _profile_answers(
    profile: SetupProfile,
    user_input: Mapping[str, Any],
    data: Mapping[str, Any],
    context: FlowContext,
) -> dict[str, Any]:
    """Return the submitted answers, flattening the Advanced section.

    An untouched Advanced section submits nothing, so its questions keep their
    staged or declared default.
    """
    from .setup_questions import OPTIONAL, REQUIRED

    submitted = {**user_input, **(user_input.get("advanced") or {})}
    answers = {}
    for question in profile.questions:
        if not question.asked({**data, **submitted}):
            # A hidden question is neither required nor saved.
            continue
        if question.key in submitted:
            _marker, validator = _question_field(question, data, context)
            try:
                # The schema coerces a select's text; a direct call gets the same.
                answers[question.key] = validator(submitted[question.key])
            except vol.Invalid:
                answers[question.key] = submitted[question.key]
        elif user_input and (default := question.default_for(data, context)) not in (
            REQUIRED,
            OPTIONAL,
        ):
            answers[question.key] = default
    return answers


_PULSE_FIELDS: Final = (CONF_MOTOR_PULSE_COUNT, CONF_MOTOR_PULSE_DELAY_MS)
_ANGLE_LIMITS: Final[dict[str, float]] = {
    CONF_BACK_MAX_ANGLE: DEFAULT_BACK_MAX_ANGLE,
    CONF_LEGS_MAX_ANGLE: DEFAULT_LEGS_MAX_ANGLE,
}
_POSITION_MODES: Final = {
    POSITION_MODE_SPEED: "Speed (recommended)",
    POSITION_MODE_ACCURACY: "Accuracy",
}
_TEXT: Final = TextSelector(TextSelectorConfig())


def _settings_fields(
    hass: HomeAssistant,
    data: Mapping[str, Any],
    bed_type: str,
    variant: str,
    keys: Iterable[str],
    defaults: Mapping[str, Any] | None = None,
) -> dict[vol.Marker, Any]:
    """Return the generic settings fields ``keys`` for a route, in that order.

    Each shows its saved value, else the caller's default, else the route's own:
    its pulse timing, its disconnect-after-command default and so on.
    """
    adapters = get_available_adapters(hass)
    route_defaults: dict[str, Any] = {
        CONF_NAME: "Adjustable Bed",
        CONF_MOTOR_COUNT: DEFAULT_MOTOR_COUNT,
        CONF_HAS_MASSAGE: DEFAULT_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING: DEFAULT_DISABLE_ANGLE_SENSING,
        CONF_POSITION_MODE: DEFAULT_POSITION_MODE,
        CONF_PASSIVE_POSITION_RECONCILIATION: passive_position_reconciliation_default_enabled(
            bed_type
        ),
        CONF_PREFERRED_ADAPTER: ADAPTER_AUTO,
        CONF_CONNECTION_PROFILE: DEFAULT_CONNECTION_PROFILE,
        **dict(zip(_PULSE_FIELDS, get_motor_pulse_defaults(bed_type, variant), strict=True)),
        CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command_default_enabled(bed_type, variant),
        CONF_IDLE_DISCONNECT_SECONDS: DEFAULT_IDLE_DISCONNECT_SECONDS,
        **_ANGLE_LIMITS,
        **(defaults or {}),
    }
    validators: dict[str, Any] = {
        CONF_NAME: str,
        CONF_MOTOR_COUNT: vol.All(vol.Coerce(int), vol.In(_motor_count_options(bed_type, variant))),
        CONF_POSITION_MODE: vol.In(_POSITION_MODES),
        CONF_PREFERRED_ADAPTER: vol.In(adapters),
        CONF_CONNECTION_PROFILE: vol.In(CONNECTION_PROFILE_OPTIONS),
        CONF_IDLE_DISCONNECT_SECONDS: vol.All(
            vol.Coerce(int), vol.Range(min=IDLE_DISCONNECT_KEEP_CONNECTED, max=300)
        ),
        **dict.fromkeys((*_PULSE_FIELDS, *_ANGLE_LIMITS), _TEXT),
    }
    fields: dict[vol.Marker, Any] = {}
    for key in keys:
        default = data.get(key, route_defaults[key])
        if key == CONF_PREFERRED_ADAPTER and default not in adapters:
            # A stored adapter that has gone falls back to automatic.
            default = ADAPTER_AUTO
        elif key in _PULSE_FIELDS or key in _ANGLE_LIMITS:
            default = str(default)
        fields[vol.Optional(key, default=default)] = validators.get(key, bool)
    return fields


def _parse_settings(
    submitted: Mapping[str, Any], bed_type: str, pulse_defaults: tuple[int, int]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return the submitted pulse timing and angle limits as numbers, and errors by field.

    A blank field takes its default. Only the fields submitted are returned.
    """
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, default in zip(_PULSE_FIELDS, pulse_defaults, strict=True):
        if key not in submitted:
            continue
        try:
            values[key] = int(submitted[key] or default)
        except ValueError, TypeError:
            errors[key] = "invalid_number"
            continue
        if values[key] < 1:
            errors[key] = "invalid_number"
    if not errors and _invalid_pulse_count(
        bed_type, values.get(CONF_MOTOR_PULSE_COUNT, pulse_defaults[0])
    ):
        errors[CONF_MOTOR_PULSE_COUNT] = "invalid_pulse_count_range"
    for key, default in _ANGLE_LIMITS.items():
        if key not in submitted:
            continue
        try:
            values[key] = float(submitted[key] or default)
        except ValueError, TypeError:
            errors[key] = "invalid_angle"
            continue
        if not 0 < values[key] <= 180:
            errors[key] = "invalid_angle"
    return values, errors


def _final_settings_questions(bed_type: str, variant: str | None) -> SetupProfile | None:
    """Return the declared questions a route without an app step asks in its final settings."""
    if bed_type in _APP_SETUP_STEPS:
        return None
    profile = setup_profile(bed_type, variant)
    return profile if profile is not None and profile.questions else None


# Short, single-attempt timeout for the optional setup-time connection probe.
# Keep this small so a failing probe (e.g. the phone app holding the bed's single
# BLE connection) never makes setup feel slow. Generic device information is
# best-effort; standard Octo additionally requires verified PIN access.
_PROBE_TIMEOUT_SECONDS = 15.0

_OCTO_PIN_MESSAGES: Final[dict[OctoPinStatus, str]] = {
    OctoPinStatus.ACCEPTED: "The bed accepted the PIN. Submit to finish setup.",
    OctoPinStatus.NOT_REQUIRED: "This bed does not require a PIN. Submit to finish setup.",
    OctoPinStatus.REQUIRED: "The bed requires a PIN. Enter it below and submit to check again.",
    OctoPinStatus.REJECTED: "The bed rejected the PIN. Correct it below and submit to check again.",
    OctoPinStatus.INCONCLUSIVE: (
        "PIN verification could not be completed. This does not mean the PIN is wrong. "
        "Wake the bed, close other apps connected to it, and check that your Bluetooth "
        "adapter or proxy is available. Submit to retry; the entry has not been saved."
    ),
}

# How long the setup probe waits for the bed to advertise before reporting it as
# absent. Deliberately shorter than the pairing wait: someone who just put a bed
# into pairing mode is standing at the bed and expects to wait, while someone
# finishing a setup form is not, and the result step offers Retry either way.
_PROBE_ADVERTISEMENT_WAIT_SECONDS = 10.0


# A family step asks which app runs the bed; it collects no app settings itself.
_FAMILY_STEPS: Final = frozenset(
    {
        "jiecang_family",
        "okin_family",
        "keeson_family",
        "solace_family",
        "leggett_family",
        "sleepys_family",
        "customatic_family",
        "jordans_family",
        "malouf_family",
        "remacro_family",
        "jensen_family",
        "reverie_family",
        "richmat_family",
        "sleep_number_family",
        "limoss_family",
    }
)
# Steps that ask which app runs the bed: a discovered bed's first question.
_APP_QUESTION_STEPS: Final = _FAMILY_STEPS | {"vibradorm", "logicdata_family", "starcode_family"}
# Each family question's name, from its family row.
_FAMILY_NAMES: Final[dict[str, str]] = {
    _APP_SETUP_STEPS[bed_type]: family for bed_type, (family, _apps) in FAMILY_ROWS.items()
}


def _row_family(choice: str) -> str | None:
    """Return the family of a bed-type list row: the family its journey asks.

    An answer of a family's question belongs to it, such as a classic Richmat
    app or AdjustableM5X5, though its own bed type opens only its own step.
    """
    bed_type, variant = resolve_bed_type_choice(choice)
    step = _ANSWER_STEPS.get((bed_type, variant)) or _APP_SETUP_STEPS.get(bed_type)
    return _FAMILY_NAMES.get(step) if step is not None else None


def _with_family(option: SelectOptionDict) -> SelectOptionDict:
    """Label a family member's row "<app> · <family>"; a family row already is.

    Configure lists a family row's own route by its own label, as a member.
    """
    if option["label"] == family_row_label(option["value"]) or (
        family := _row_family(option["value"])
    ) is None:
        return option
    app = option["label"].removesuffix(f" ({family})")
    return SelectOptionDict(value=option["value"], label=f"{app}{FAMILY_ROW_SEPARATOR}{family}")
APP_SETTINGS_BED_TYPES: Final = (
    frozenset(
        bed_type for bed_type, step in _APP_SETUP_STEPS.items() if step not in _FAMILY_STEPS
    )
    # FSM Relax asks its own settings after the Limoss question, and the Malouf
    # family step stages the app, whose model is asked after it.
    | {BED_TYPE_FSM_RELAX, BED_TYPE_MALOUF_APP}
)


def _skips_setup_connection_probe(bed_type: str | None, variant: str | None) -> bool:
    """Return True when setup should avoid a redundant Gen2 connection cycle.

    LP Comfort Connect must establish its first bond during the short pairing
    window. After the explicit pairing attempt, skip the optional read-only probe
    and let ``async_setup_entry`` make the meaningful bonded connection directly.
    """
    if bed_type == BED_TYPE_LEGGETT_GEN2:
        return True
    if bed_type == BED_TYPE_LEGGETT_PLATT:
        return variant in (VARIANT_AUTO, LEGGETT_VARIANT_GEN2, None)
    return False


@dataclass
class CapabilityReport:
    """Result of setup-time connection and optional application PIN checks."""

    device_found: bool = False
    connected: bool = False
    source: str | None = None
    rssi: int | None = None
    via_proxy: bool = False
    service_count: int = 0
    writable_count: int = 0
    manufacturer: str | None = None
    model: str | None = None
    position_feedback: bool = False
    error: str | None = None
    octo_pin_status: OctoPinStatus | None = None
    starcode_transport_valid: bool | None = None
    starcode_transport_selector: str | None = None
    starcode_ble_device_name: str | None = None
    # Which path the probe expected to take, and which one it really took. They
    # can differ: Home Assistant re-ranks every scanner when it connects, so a
    # prediction is never a promise (issue #456).
    predicted_path: ConnectionPath | None = None
    actual_path: ConnectionPath | None = None
    # Set when the bed had not advertised recently enough to be worth calling
    # establish_connection on at all (issue #458).
    freshness: FreshnessStatus | None = None


class AdjustableBedConfigFlow(BluetoothOperationMixin, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adjustable Bed."""

    # v4 introduces the paired-bed schema (Dual Bed 4.0). The v3->v4 migration is
    # a strict no-op for non-paired entries; see async_migrate_entry. Minor
    # version 2 stores v4.0.2 aliases and per-app keys under one name. Minor
    # version 3 marks older entries for the one-time app profile review. v5
    # stores the profile id each entry runs (profile_id.py); setup derives it
    # for new entries. Minor version 2 drops the obsolete keys recorded in
    # docs/design/config-keys.md; minor version 3 turns Massage off on layouts
    # whose profile has no massage; minor version 5 stores each Octo setup's
    # motor layout as its override.
    VERSION = 5
    MINOR_VERSION = 5

    @staticmethod
    def _mark_ble_bond_established(entry_data: dict[str, Any]) -> dict[str, Any]:
        """Persist that the bed already has a BLE bond."""
        return {
            **entry_data,
            CONF_BLE_BOND_ESTABLISHED: True,
        }

    def _create_entry_for_existing_bond(self, record: LocalBondRecord) -> ConfigFlowResult:
        """Create an entry after the user confirms the adapter is already bonded."""
        assert self._manual_data is not None
        assert record.has_bond
        _LOGGER.info(
            "User confirmed an existing BLE bond for %s via adapter %s",
            self._manual_data.get(CONF_ADDRESS),
            self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
        )
        entry_data = self._mark_ble_bond_established(self._manual_data)
        entry_data[CONF_BLE_BOND_CONTEXT] = build_bond_context(
            BondEvidence(
                status=BondVerificationStatus.VERIFIED,
                owner=BondOwner(
                    transport=TransportClass.LOCAL,
                    source=record.adapter_address,
                    adapter=record.adapter_path.rsplit("/", 1)[-1] or None,
                ),
                operation="existing_bluez_bond",
                observed_at=datetime.now(UTC).isoformat(),
            )
        )
        return self.async_create_entry(
            title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            data=entry_data,
        )

    async def _async_app_setup_step(
        self,
        entry_data: dict[str, Any],
        *,
        pairing_step: Literal["bluetooth_pairing", "manual_pairing"],
    ) -> ConfigFlowResult | None:
        """Continue with the step that collects the selected app's own settings."""
        bed_type = entry_data.get(CONF_BED_TYPE)
        if not isinstance(bed_type, str) or (step := _APP_SETUP_STEPS.get(bed_type)) is None:
            return None
        self._manual_data = entry_data
        self._route_pairing_from_discovery = pairing_step == "bluetooth_pairing"
        return await getattr(self, f"async_step_{step}")()

    async def _async_keep_detected(
        self, step_id: str, resume: Callable[[], Awaitable[ConfigFlowResult]]
    ) -> ConfigFlowResult:
        """Say what Keep sets up on a new bed before setup continues."""
        self._keep_detected = (step_id, resume)
        return await self.async_step_keep_detected()

    async def async_step_keep_detected(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain the kept route's generic controls, its pairing, and the way to an app."""
        assert self._manual_data is not None
        from .profile_review import route_label

        data = self._manual_data

        async def text(key: str, default: str) -> str:
            return await _async_translation(
                self.hass, "config", f"step.keep_detected.data_description.{key}", default
            )

        pairing = ""
        if requires_pairing(data[CONF_BED_TYPE], data.get(CONF_PROTOCOL_VARIANT)):
            pairing = " " + await text("pairing", "It requires Bluetooth pairing.")
        # Only a route with a guided change can choose its app in Reconfigure.
        later = (
            await text(
                "later_reconfigure",
                "To choose your app later, open **Reconfigure** from this entry's "
                "three-dot menu. **Configure › Change app or layout** points there too.",
            )
            if reconfigure_family(data) is not None
            else await text(
                "later_configure",
                "To choose your app later, change **Bed type** in **Configure › Change settings**.",
            )
        )
        return self.async_show_menu(
            step_id="keep_detected",
            menu_options=["keep_back", "keep_continue"],
            description_placeholders={
                "name": data.get(CONF_NAME) or data[CONF_ADDRESS],
                "route": route_label(data),
                "pairing": pairing,
                "later": later,
            },
        )

    async def async_step_keep_back(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return to the app question Keep was chosen on."""
        assert self._keep_detected is not None
        step_id, _resume = self._keep_detected
        self._keep_detected = None
        return await getattr(self, f"async_step_{step_id}")()

    async def async_step_keep_continue(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Continue setup with the kept route."""
        assert self._keep_detected is not None
        _step_id, resume = self._keep_detected
        self._keep_detected = None
        return await resume()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Stage a guided app or layout change without changing the working entry."""
        entry = self._get_reconfigure_entry()
        family = reconfigure_family(entry.data)
        if family is None:
            return self.async_abort(reason="reconfigure_not_supported")
        if self._migration is None:
            self._migration = MigrationSnapshot.of(entry)
            self._migration_family = family
            self._manual_data = self._migration.staged(entry.title)
        if is_paired(entry.data):
            return await self.async_step_migration_split(user_input)
        return await getattr(self, f"async_step_{family.key}")(user_input)

    async def async_step_migration_split(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Split only after explicit consent, using the existing registry transaction."""
        entry = self._get_reconfigure_entry()
        if user_input is not None and user_input.get("confirm"):
            if not self._migration_unchanged():
                return self.async_abort(reason="migration_entry_changed")

            async def split() -> None:
                from . import async_unpair_entry

                try:
                    await async_unpair_entry(self.hass, entry)
                except Exception:
                    _LOGGER.exception("Could not split config entry %s", entry.entry_id)

            self.hass.async_create_task(split(), f"adjustable_bed_unpair_{entry.entry_id}")
            return self.async_abort(reason="migration_pair_split_started")
        return self.async_show_form(
            step_id="migration_split",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"name": entry.title},
        )

    async def async_step_migration_keep(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Leave the saved entry untouched and record the explicit Keep."""
        if not self._migration_unchanged():
            return self.async_abort(reason="migration_entry_changed")
        from .profile_recommendations import async_keep_reviewed_profile
        from .profile_review import async_keep_current_profile

        entry = self._get_reconfigure_entry()
        async_keep_current_profile(self.hass, entry)
        await async_keep_reviewed_profile(self.hass, entry, self.flow_id)
        return self.async_abort(reason="migration_kept")

    async def async_step_vibradorm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose by app or keep the historical setup, never infer a profile."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        # On a legacy entry the legacy setup is the saved route, so it keeps it.
        on_legacy = (
            self._migration is not None
            and self._migration.data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM
        )
        choices = {
            "vmat": "VMAT",
            "caresse": "Caresse Diamant",
            "werkmeister": "Werkmeister",
            "vmatbasic": "V-MAT Basic",
            "legacy": "Keep current setup" if on_legacy else "Legacy setup",
        }
        if self._migration is not None and not on_legacy:
            choices["keep"] = "Keep current setup"
        choice = (user_input or {}).get("app")
        if choice in choices:
            if choice == "keep" or (choice == "legacy" and on_legacy):
                return await self.async_step_migration_keep()
            self._migration_verified = False
            same_profile = (
                choice == "vmatbasic" and self._manual_data.get(CONF_BED_TYPE) == BED_TYPE_VMATBASIC
            ) or (
                self._manual_data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM_APP
                and self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == choice
            )
            if not same_profile:
                for key in (*VIBRADORM_APP_CONFIG_KEYS, *VMATBASIC_CONFIG_KEYS):
                    self._manual_data.pop(key, None)
                self._manual_data.pop(CONF_VIBRADORM_APP_METADATA, None)
            if choice == "legacy":
                # A form drawn for a detected app or V-MAT Basic, or an app
                # entry, set none of the legacy settings, so they are asked.
                self._select_family_route(BED_TYPE_VIBRADORM, None)
                return await self.async_step_profile_questions()
            if choice == "vmatbasic":
                self._manual_data[CONF_BED_TYPE] = BED_TYPE_VMATBASIC
            else:
                self._manual_data[CONF_BED_TYPE] = BED_TYPE_VIBRADORM_APP
                self._manual_data[CONF_VIBRADORM_APP_PROFILE] = choice
            return await self.async_step_profile_questions()
        return self.async_show_form(
            step_id="vibradorm",
            data_schema=vol.Schema(
                {
                    vol.Required("app"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=value, label=label)
                                for value, label in choices.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    def _migration_unchanged(self) -> bool:
        return self._migration is not None and self._migration.matches(
            self._get_reconfigure_entry()
        )

    @property
    def _migration_requires_check(self) -> bool:
        staged = self._pending_entry if self._pending_entry is not None else self._manual_data
        if self._migration_family is None:
            return False
        return _checked_family(self._migration_family, staged or {}).requires_check(staged or {})

    def _migration_endpoint_check(self, client: BleakClient, data: dict[str, Any]) -> None:
        """Run the staged route's family check on the candidate link."""
        self._migration_preview = {}
        if self._migration_family is None:
            return
        check = _checked_family(self._migration_family, data).endpoint_check
        if check is not None:
            # The confirm step lists the controls of what the check resolved.
            self._migration_preview = dict(check(self.hass, client, data))

    def _migration_probe_check(self) -> Callable[[BleakClient], None] | None:
        """Return the probe's strict migration check, or None outside a migration."""
        if self._migration is None or self._pending_entry is None:
            return None
        data = self._pending_entry
        return lambda client: self._migration_endpoint_check(client, data)

    @contextlib.asynccontextmanager
    async def _migration_transport_operation(self) -> AsyncIterator[None]:
        """Release the old runtime under its normal locks for one validation task."""
        if self._migration is None:
            yield
            return
        entry = self._get_reconfigure_entry()
        runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if runtime is not None:
            async with runtime.async_transport_operation("profile_migration"):
                yield
        else:
            assert self._manual_data is not None
            async with async_get_connect_lock(self.hass, self._manual_data[CONF_ADDRESS]):
                yield

    def _migration_selection_label(self, data: Mapping[str, Any]) -> str:
        """Name a route by its profile's title, which names the app and its selection."""
        from .profile_review import route_label

        profile = setup_profile_for(data)
        if profile is not None and profile.title is not None:
            return profile.title(data)
        return route_label(data)

    async def _async_show_migration_confirm(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Review the staged change: added, removed, reinterpreted and referenced controls."""
        assert self._pending_entry is not None
        entry = self._get_reconfigure_entry()
        changes = await async_control_changes(
            self.hass, entry, {**self._pending_entry, **self._migration_preview}
        )

        async def text(key: str, default: str) -> str:
            return await _async_translation(
                self.hass, "config", f"step.migration_confirm.data_description.{key}", default
            )

        none = await text("summary_none", "None")

        def bullets(items: tuple[str, ...]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else none

        if changes.known:
            renamed = await text("summary_reinterpreted", "{old} becomes {new}")
            summary = (
                await text(
                    "summary_known",
                    "**Added:**\n{added}\n\n**Removed:**\n{removed}\n\n"
                    "**Changes meaning:**\n{reinterpreted}\n\n"
                    "**Unchanged:** {unchanged} controls keep their entity IDs.",
                )
            ).format(
                added=bullets(changes.added),
                removed=bullets(changes.removed),
                reinterpreted=bullets(
                    tuple(renamed.format(old=old, new=new) for old, new in changes.reinterpreted)
                ),
                unchanged=changes.unchanged,
            )
        else:
            summary = await text(
                "summary_unknown",
                "The new controls are known only after the bed connects. "
                "Controls the new setup does not support are removed.",
            )
        if changes.references:
            references = await text(
                "summary_references",
                "**Automations and scripts that use removed controls:**\n{references}",
            )
            summary += "\n\n" + references.format(references=bullets(changes.references))
        assert self._migration is not None
        return self.async_show_form(
            step_id="migration_confirm",
            # Apply and Keep are two equal answers, and neither is preselected.
            data_schema=vol.Schema(
                {
                    vol.Required("action"): SelectSelector(
                        SelectSelectorConfig(
                            options=["apply", "keep"],
                            translation_key="migration_confirm_action",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                "name": entry.title,
                "current": self._migration_selection_label(
                    {**self._migration.data, **self._migration.options}
                ),
                "selection": self._migration_selection_label(self._pending_entry),
                "summary": summary,
            },
        )

    async def async_step_migration_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Commit the staged selection only against the unchanged snapshot."""
        if (user_input or {}).get("action") == "keep":
            return await self.async_step_migration_keep()
        if self._pending_entry is None or (
            self._migration_requires_check and not self._migration_verified
        ):
            return self.async_abort(reason="migration_verification_required")
        if not self._migration_unchanged():
            return self.async_abort(reason="migration_entry_changed")
        if user_input is None or user_input.get("action") != "apply":
            return await self._async_show_migration_confirm()
        assert self._migration is not None
        entry = self._get_reconfigure_entry()
        from .const import CONF_PROFILE_REVIEW_PENDING

        data = dict(self._pending_entry)
        data.pop(CONF_PROFILE_REVIEW_PENDING, None)
        options = dict(entry.options)
        for key in (
            *VIBRADORM_APP_CONFIG_KEYS,
            *VMATBASIC_CONFIG_KEYS,
            *hidden_generic_fields(data[CONF_BED_TYPE], data.get(CONF_PROTOCOL_VARIANT)),
            CONF_BED_TYPE,
            CONF_PROTOCOL_VARIANT,
        ):
            options.pop(key, None)
        # The staged copy carries the saved route's profile id; derive the new one.
        data = with_profile_ids(data, options)
        if {**data, **options} == {**self._migration.data, **self._migration.options}:
            # The answer resolves to the saved route: nothing to migrate.
            return self.async_abort(reason="migration_unchanged")
        kept = _limoss_remote_features_left(
            {**self._migration.data, **self._migration.options}, {**data, **options}
        )
        if kept is not None and not await _async_turn_off_limoss_remote_features(
            self.hass.data.get(DOMAIN, {}).get(entry.entry_id), *kept
        ):
            # Leaving enabled Limoss Remote features needs their OFF commands;
            # the saved setup stays until they succeed.
            return await self._async_show_migration_confirm(
                errors={"base": "limoss_remote_feature_update_failed"}
            )
        if kept is not None and not self._migration_unchanged():
            # Another save landed while the OFF commands ran; never overwrite it.
            return self.async_abort(reason="migration_entry_changed")
        self._record_selected_app_intent(data)
        self.hass.config_entries.async_update_entry(entry, data=data, options=options)
        # The applied screen names the new setup and the way back.
        result = self.async_abort(
            reason="migration_applied",
            description_placeholders={
                "name": entry.title,
                "selection": self._migration_selection_label({**data, **options}),
                "current": self._migration_selection_label(
                    {**self._migration.data, **self._migration.options}
                ),
            },
        )
        from .profile_recommendations import (
            async_complete_profile_review,
            async_confirm_profile_review,
        )
        from .profile_review import async_clear_profile_review_issue

        async_clear_profile_review_issue(self.hass, entry.entry_id)
        # A profile recommendation that opened this change is answered by it.
        await async_confirm_profile_review(self.hass, entry, self.flow_id, {**data, **options})
        async_complete_profile_review(self.hass, entry, self.flow_id)
        if entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY):
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return result

    async def async_step_logicdata_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which LOGICDATA app runs the bed, and for Sleep Smart the bed base or pump.

        The apps share Bluetooth services, so nothing about the bed chooses one.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        incoming, _variant = self._incoming("logicdata_family")
        guided = self._migration is not None
        # Keep saves the route detection or the saved setup chose; the family
        # row alone chose no app to keep.
        can_keep = guided or incoming != BED_TYPE_LOGICDATA_APP
        # The pump is its own physical device, never a route a bed entry changes to.
        answers = [
            answer
            for answer, (bed_type, _app) in _LOGICDATA_ROUTES.items()
            if not (guided and bed_type == BED_TYPE_LOGICDATA_AIR_PUMP)
        ]
        choice = (user_input or {}).get("choice")
        if choice == "keep" and can_keep:
            if guided:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected(
                "logicdata_family", self._async_continue_logicdata_route
            )
        if choice in answers:
            bed_type, app = _LOGICDATA_ROUTES[choice]
            if (bed_type, app) != (data[CONF_BED_TYPE], data.get(CONF_LOGICDATA_APP_PROFILE)):
                # Another app's command family, layout and transport mean nothing here.
                for key in LOGICDATA_FAMILY.route_keys:
                    data.pop(key, None)
            self._select_family_route(bed_type, None)
            if app is not None:
                data[CONF_LOGICDATA_APP_PROFILE] = app
            return await self._async_continue_logicdata_route()
        return self.async_show_form(
            step_id="logicdata_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*answers, *(["keep"] if can_keep else [])],
                            translation_key="logicdata_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def _async_continue_logicdata_route(self) -> ConfigFlowResult:
        """Ask an app's own command family and layout, then finish the route."""
        from .setup_questions import setup_profile_for

        assert self._manual_data is not None
        # The row's form was drawn for the apps, so SimplicityFrame asks its
        # motor count here too.
        if (profile := setup_profile_for(self._manual_data)) is not None and profile.questions:
            return await self.async_step_profile_questions()
        # The pump continues to its check.
        return await self._async_finish_family_route()

    async def async_step_jiecang_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or remote controls the bed; never infer it from the bed's name."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        from .profile_review import suggested_apps

        assert self._manual_data is not None
        incoming, _variant = self._incoming("jiecang_family")
        # Keep saves the route detection or the saved setup chose; the family
        # row alone chose no route to keep.
        can_keep = self._migration is not None or incoming in _JIECANG_LEGACY_ROUTES.values()
        choices = [*JIECANG_APP_PROFILES, *_JIECANG_LEGACY_ROUTES, *(["keep"] if can_keep else [])]
        # Another family's app the review suggests for this route, such as the
        # LOGICDATA app for a Comfort Motion bed, continues in that family's question.
        apps = [
            app
            for app in suggested_apps(self.hass, self._manual_data)
            if resolve_bed_type_choice(app)[0] not in JIECANG_FAMILY.bed_types
        ]
        choice = (user_input or {}).get("choice")
        if choice in apps:
            data = self._manual_data
            for key in JIECANG_FAMILY.route_keys:
                data.pop(key, None)
            bed_type, variant = resolve_bed_type_choice(choice)
            self._select_family_route(bed_type, variant)
            if (step := _APP_SETUP_STEPS.get(bed_type)) is not None:
                return await getattr(self, f"async_step_{step}")()
            return await self._async_finish_family_route()
        if choice in choices:
            data = self._manual_data
            if choice == "keep":
                if self._migration is not None:
                    return await self.async_step_migration_keep()
                return await self._async_keep_detected(
                    "jiecang_family", self._async_finish_family_route
                )
            same_app = (
                data.get(CONF_BED_TYPE) == BED_TYPE_JIECANG_APP
                and data.get(CONF_JIECANG_APP_PROFILE) == choice
            )
            if not same_app:
                for key in JIECANG_FAMILY.route_keys:
                    data.pop(key, None)
            self._migration_verified = False
            if choice in _JIECANG_LEGACY_ROUTES:
                data[CONF_BED_TYPE] = _JIECANG_LEGACY_ROUTES[choice]
                if incoming == BED_TYPE_JIECANG_APP:
                    # The apps set the layout and cadence themselves, so the
                    # saved motor count means nothing here: ask the route's own.
                    return await self.async_step_jiecang_legacy()
                return await self._async_finish_family_route()
            data[CONF_BED_TYPE] = BED_TYPE_JIECANG_APP
            data[CONF_JIECANG_APP_PROFILE] = choice
            return await self.async_step_profile_questions()
        return self.async_show_form(
            step_id="jiecang_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            # Each suggested app is translated as a choice of its own.
                            options=[
                                *(key for key in choices if key != "keep"),
                                *apps,
                                *(["keep"] if can_keep else []),
                            ],
                            translation_key="jiecang_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def async_step_jiecang_legacy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the motor count a legacy remote route needs, with its own cadence."""
        assert self._manual_data is not None
        data = self._manual_data
        bed_type = data[CONF_BED_TYPE]
        if user_input is not None:
            data[CONF_MOTOR_COUNT] = int(user_input[CONF_MOTOR_COUNT])
            self._journey_set.add(CONF_MOTOR_COUNT)
            pulse_count, pulse_delay = get_motor_pulse_defaults(bed_type, VARIANT_AUTO)
            data[CONF_MOTOR_PULSE_COUNT] = pulse_count
            data[CONF_MOTOR_PULSE_DELAY_MS] = pulse_delay
            data[CONF_MOTOR_PULSE_USER_SET] = False
            return await self._async_finish_family_route()
        return self.async_show_form(
            step_id="jiecang_legacy",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.All(
                        vol.Coerce(int), vol.In(_motor_count_options(bed_type))
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(bed_type)},
        )

    async def _async_finish_family_route(self) -> ConfigFlowResult:
        """Continue a route chosen in a family step: a new bed's settings, pairing, the check."""
        if self._final_settings_pending:
            return await self._async_new_bed_settings("route")
        assert self._manual_data is not None
        data = self._manual_data
        if self._migration is not None and grants_one_connection_per_pairing_window(
            data[CONF_BED_TYPE], data.get(CONF_PROTOCOL_VARIANT)
        ):
            # Pairing would spend the one connection the box grants per window,
            # so the entry's first connection bonds after the change, as at setup.
            return await self._async_create_selected_app_entry(
                title=data.get(CONF_NAME, "Adjustable Bed"), data=data
            )
        if requires_pairing(data[CONF_BED_TYPE], data.get(CONF_PROTOCOL_VARIANT)):
            return await (
                self.async_step_bluetooth_pairing()
                if self._route_pairing_from_discovery
                else self.async_step_manual_pairing()
            )
        return await self._finish_with_verify(data, data.get(CONF_NAME, "Adjustable Bed"))

    async def async_step_okin_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or remote controls an Okin receiver; its GATT cannot tell."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        from .furnimove_repair import CONF_STAIRCASE_LAYOUT_CONFIRMED
        from .profile_review import choice_label, related_app_choices

        assert self._manual_data is not None
        data = self._manual_data
        first = "okin_family" not in self._family_incoming
        incoming, incoming_variant = self._incoming("okin_family")
        if (
            first
            and self._migration is None
            and (
                (incoming, incoming_variant) in APP_VARIANT_CHOICES
                or incoming == BED_TYPE_OKIN_CST
                and incoming_variant in _OKIN_CST_APPS.values()
            )
        ):
            # An app row, such as Nectar Move, or an explicit CST product
            # already answered the question.
            return await self._async_finish_family_route()
        # The apps the app review suggests for this route stay one answer away.
        apps = related_app_choices(incoming, incoming_variant)
        # A detected or chosen Okin CST bed is offered its own apps first.
        cst_apps = _OKIN_CST_APPS if incoming == BED_TYPE_OKIN_CST else {}
        # A FurniMove row or gateway chose no handset, so there is nothing to keep.
        can_keep = self._migration is not None or incoming != BED_TYPE_FURNIMOVE
        choice = (user_input or {}).get("choice")
        if choice == "keep" and can_keep:
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected(
                "okin_family",
                self.async_step_profile_questions
                if incoming in (BED_TYPE_OKIN_UUID, BED_TYPE_OKIMAT, BED_TYPE_OKIN_DOT)
                else self._async_finish_family_route,
            )
        if choice in cst_apps:
            self._select_family_route(BED_TYPE_OKIN_CST, cst_apps[choice])
            return await self._async_finish_family_route()
        if choice in _OKIN_ROUTES or choice in apps:
            bed_type, variant = (
                (_OKIN_ROUTES[choice], None)
                if choice in _OKIN_ROUTES
                else resolve_bed_type_choice(choice)
            )
            if incoming == BED_TYPE_OKIMAT and bed_type == BED_TYPE_OKIN_UUID:
                # The same route under its saved ID; never rewrite the ID.
                bed_type = BED_TYPE_OKIMAT
            self._migration_verified = False
            if bed_type != data[CONF_BED_TYPE]:
                for key in (*OKIN_FAMILY.route_keys, CONF_STAIRCASE_LAYOUT_CONFIRMED):
                    data.pop(key, None)
                self._select_family_route(bed_type, variant)
            if bed_type == BED_TYPE_FURNIMOVE:
                return await self.async_step_profile_questions()
            if bed_type in (BED_TYPE_OKIN_UUID, BED_TYPE_OKIMAT, BED_TYPE_OKIN_DOT):
                return await self.async_step_profile_questions()
            if bed_type == BED_TYPE_OKIN_RF_ECO_BT:
                # Choosing the staircase is the explicit confirmation its repair asks for.
                data[CONF_STAIRCASE_LAYOUT_CONFIRMED] = True
                data[CONF_MOTOR_COUNT] = 1
                self._journey_set.add(CONF_MOTOR_COUNT)
            return await self._async_finish_family_route()
        routes = [
            SelectOptionDict(value=key, label=label) for key, label in _OKIN_ROUTE_LABELS.items()
        ]
        app_options = [
            *(
                SelectOptionDict(value=key, label=OKIN_CST_VARIANTS[variant])
                for key, variant in cst_apps.items()
            ),
            *(SelectOptionDict(value=app, label=choice_label(app)) for app in apps),
        ]
        options = [
            # The detected family's apps come first, then the other Okin answers.
            *([*app_options, *routes] if cst_apps else [*routes, *app_options]),
            *([SelectOptionDict(value="keep", label=_OKIN_KEEP_LABEL)] if can_keep else []),
        ]
        return self.async_show_form(
            step_id="okin_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            translation_key="okin_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def async_step_keeson_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or remote runs a Keeson bed; shared names cannot tell."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        first = "keeson_family" not in self._family_incoming
        incoming, variant = self._incoming("keeson_family")
        if first and self._migration is None and (incoming, variant) in APP_VARIANT_CHOICES:
            # An app row already answered the question.
            return await self._async_continue_keeson_route()
        choice = (user_input or {}).get("choice")
        if choice == "keep":
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected("keeson_family", self._async_finish_family_route)
        if choice in _KEESON_GROUPS:
            self._keeson_group = choice
            return await self.async_step_keeson_app()
        if choice == "restonic":
            return await self.async_step_keeson_restonic()
        if choice == "other_route":
            self._select_family_route(BED_TYPE_KEESON, data.get(CONF_PROTOCOL_VARIANT))
            return await self.async_step_keeson_route()
        if choice in ("sleep_harmony", "coolbase"):
            self._select_family_route(
                *(
                    (BED_TYPE_KEESON, KEESON_VARIANT_SLEEP_HARMONY)
                    if choice == "sleep_harmony"
                    else (BED_TYPE_COOLBASE, None)
                )
            )
            return await self._async_finish_family_route()
        return self.async_show_form(
            step_id="keeson_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=list(_KEESON_CHOICES),
                            translation_key="keeson_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    def _select_family_route(self, bed_type: str, variant: str | None) -> None:
        """Stage one family route, with Configure's defaults when it changes.

        An answer without a variant on the staged bed type keeps the staged
        route, so choosing it again keeps the settings the form collected.
        """
        assert self._manual_data is not None
        data = self._manual_data
        self._migration_verified = False
        self._migration_preview = {}
        if bed_type == data[CONF_BED_TYPE] and variant in (None, data.get(CONF_PROTOCOL_VARIANT)):
            return
        _apply_route_defaults(data, bed_type, variant)

    async def _async_continue_keeson_route(self) -> ConfigFlowResult:
        """Ask what the staged route still needs, then finish it."""
        assert self._manual_data is not None
        data = self._manual_data
        bed_type = data[CONF_BED_TYPE]
        variant = data.get(CONF_PROTOCOL_VARIANT)
        if bed_type in _APP_SETUP_STEPS and bed_type not in KEESON_FAMILY.bed_types:
            # Its own app step owns the layout.
            return await getattr(self, f"async_step_{_APP_SETUP_STEPS[bed_type]}")()
        if variant in _KEESON_RESTONIC:
            return await self.async_step_keeson_restonic()
        return await self._async_ask_keeson_route()

    async def _async_ask_keeson_route(self) -> ConfigFlowResult:
        """Ask the staged route's declared questions, such as an app screen's motor count."""
        from .setup_questions import setup_profile_for

        assert self._manual_data is not None
        if (profile := setup_profile_for(self._manual_data)) is not None and profile.questions:
            return await self.async_step_profile_questions()
        return await self._async_finish_family_route()

    async def async_step_keeson_app(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Expand a grouped answer into its exact app or route."""
        assert self._keeson_group is not None
        # Purple, Base and JSON are plain routes, not app rows, so key every
        # answer by its own bed type and variant.
        routes = {
            f"{bed_type}:{variant}" if variant else bed_type: (bed_type, variant)
            for bed_type, variant in _KEESON_GROUPS[self._keeson_group]
        }
        choice = (user_input or {}).get("choice")
        if choice in routes:
            self._select_family_route(*routes[choice])
            return await self._async_continue_keeson_route()
        return self.async_show_form(
            step_id="keeson_app",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=key, label=_keeson_route_label(*route))
                                for key, route in routes.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_keeson_restonic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the remote style chosen in the Restonic BT app's settings."""
        assert self._manual_data is not None
        style = (user_input or {}).get(CONF_PROTOCOL_VARIANT)
        if style in _KEESON_RESTONIC:
            self._select_family_route(BED_TYPE_KEESON, style)
            return await self._async_finish_family_route()
        current = self._manual_data.get(CONF_PROTOCOL_VARIANT)
        return self.async_show_form(
            step_id="keeson_restonic",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PROTOCOL_VARIANT,
                        default=current if current in _KEESON_RESTONIC else KEESON_VARIANT_RESTONIC_A,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=sorted(_KEESON_RESTONIC),
                            translation_key="keeson_restonic_style",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_keeson_route(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an older Keeson remote route and the motor count."""
        assert self._manual_data is not None
        data = self._manual_data
        routes = _labelled_routes(BED_TYPE_KEESON)
        motor_counts = _motor_count_options(BED_TYPE_KEESON)
        if user_input is not None and user_input.get(CONF_PROTOCOL_VARIANT) in routes:
            self._select_family_route(BED_TYPE_KEESON, user_input[CONF_PROTOCOL_VARIANT])
            data[CONF_MOTOR_COUNT] = int(user_input[CONF_MOTOR_COUNT])
            self._journey_set.add(CONF_MOTOR_COUNT)
            return await self._async_ask_keeson_route()
        return self.async_show_form(
            step_id="keeson_route",
            data_schema=_route_and_motors_schema(data, routes, motor_counts),
        )

    async def async_step_solace_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app runs a QMS-named bed; several apps share those names."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        first = "solace_family" not in self._family_incoming
        incoming, variant = self._incoming("solace_family")
        if first and self._migration is None and variant == SOLACE_VARIANT_WOOSA:
            # The Woosa Sleep row already answered the question.
            return await self.async_step_solace_woosa()
        choice = (user_input or {}).get("choice")
        if choice == "keep":
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected("solace_family", self._async_finish_family_route)
        if choice == "name_route":
            self._select_family_route(BED_TYPE_SOLACE, VARIANT_AUTO)
            return await self._async_finish_family_route()
        if choice == "woosa":
            return await self.async_step_solace_woosa()
        if choice == "motion_bed":
            self._select_family_route(BED_TYPE_MOTION_BED, None)
            return await self.async_step_profile_questions()
        if choice == "bedsense":
            self._select_family_route(BED_TYPE_BEDSENSE, None)
            return await self.async_step_profile_questions()
        return self.async_show_form(
            step_id="solace_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=["name_route", "woosa", "motion_bed", "bedsense", "keep"],
                            translation_key="solace_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def async_step_solace_woosa(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Say what Woosa Sleep controls differ before choosing it."""
        if user_input is not None:
            self._select_family_route(BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA)
            return await self._async_finish_family_route()
        return self.async_show_form(step_id="solace_woosa", data_schema=vol.Schema({}))

    async def async_step_leggett_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which L&P app or remote runs the bed; each app has its own layout."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        incoming, _variant = self._incoming("leggett_family")
        choice = (user_input or {}).get("choice")
        if choice == "keep":
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected("leggett_family", self._async_finish_family_route)
        if choice in _LEGGETT_ROUTES:
            bed_type, extra = _LEGGETT_ROUTES[choice]
            variant: str | None = None
            if incoming == BED_TYPE_LEGGETT_PLATT and bed_type in _LEGGETT_ALIAS_VARIANTS:
                # The same route under its saved ID; never rewrite the ID.
                bed_type, variant = BED_TYPE_LEGGETT_PLATT, _LEGGETT_ALIAS_VARIANTS[bed_type]
            if bed_type != data[CONF_BED_TYPE]:
                # The legacy app's and the QRRM remote's own settings mean
                # nothing on another route.
                for key in (*_LP_LEGACY_KEYS, CONF_RICHMAT_REMOTE):
                    data.pop(key, None)
            self._select_family_route(bed_type, variant)
            data.update(extra)
            if CONF_LEGGETT_APP_PROFILE in extra:
                # The app's own layout.
                data[CONF_MOTOR_COUNT] = LEGGETT_APP_MOTOR_COUNTS[extra[CONF_LEGGETT_APP_PROFILE]]
                self._journey_set.add(CONF_MOTOR_COUNT)
            elif CONF_LEGGETT_APP_PROFILE in data and not _is_leggett_app_type(
                bed_type, variant
            ):
                data.pop(CONF_LEGGETT_APP_PROFILE)
            if bed_type == BED_TYPE_LEGGETT_LP_LEGACY:
                return await self.async_step_profile_questions()
            return await self._async_finish_family_route()
        return self.async_show_form(
            step_id="leggett_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*_LEGGETT_ROUTES, "keep"],
                            translation_key="leggett_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def async_step_jensen_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app and bed a Jensen or Svane controller runs.

        The JMC400 name and the LinonPI services each occur with both apps, so
        they never decide the profile; the apps' own name rules only suggest it.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        incoming = self._incoming("jensen_family")
        choice = (user_input or {}).get("choice")
        if choice == "keep" and self._migration is not None:
            return await self.async_step_migration_keep()
        if isinstance(choice, str) and choice in _JENSEN_ROUTES:
            from .setup_questions import setup_profile_for

            self._select_family_route(*_JENSEN_ROUTES[choice])
            # The form before this step was drawn for Svane, so a route with
            # settings of its own asks them now.
            if (profile := setup_profile_for(data)) is not None and profile.questions:
                return await self.async_step_profile_questions()
            return await self._async_finish_family_route()
        # An unnamed advertisement reports the address as its name, which no
        # name rule reads; the next source then names the bed.
        advertised = (
            self._discovery_info
            if self._discovery_info is not None
            else bluetooth.async_last_service_info(
                self.hass, data[CONF_ADDRESS], connectable=False
            )
        )
        name = next(
            (
                candidate
                for candidate in (
                    advertised.name if advertised is not None else None,
                    data.get(CONF_BLE_DEVICE_NAME),
                )
                if isinstance(candidate, str) and candidate and not is_mac_like_name(candidate)
            ),
            None,
        )
        return self.async_show_form(
            step_id="jensen_family",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "choice", default=_jensen_suggestion(*incoming, name)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                *_JENSEN_ROUTES,
                                *(["keep"] if self._migration is not None else []),
                            ],
                            translation_key="jensen_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_sleepys_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or receiver runs a Sleepy's Elite bed; never infer it from the bed."""
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        from .profile_review import choice_label, suggested_apps

        assert self._manual_data is not None
        data = self._manual_data
        incoming, _variant = self._incoming("sleepys_family")
        # The apps the app review suggests for this route stay one answer away.
        apps = [
            app
            for app in suggested_apps(self.hass, data)
            if resolve_bed_type_choice(app)[0] not in SLEEPYS_FAMILY.bed_types
        ]
        # Keep saves the route detection or the saved setup chose; the family
        # row alone chose no control box to keep.
        can_keep = self._migration is not None or incoming != BED_TYPE_SLEEPYS_ELITE_APP
        choice = (user_input or {}).get("choice")
        if choice == "keep" and can_keep:
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected(
                "sleepys_family", self._async_continue_sleepys_route
            )
        if choice in _SLEEPYS_ROUTES or choice in apps:
            bed_type, variant = (
                (_SLEEPYS_ROUTES[choice], None)
                if choice in _SLEEPYS_ROUTES
                else resolve_bed_type_choice(choice)
            )
            if bed_type != data[CONF_BED_TYPE]:
                # A new route starts from its own defaults, never another
                # route's control box or dialect.
                data.pop(CONF_SLEEPYS_ELITE_SELECTOR, None)
            self._select_family_route(bed_type, variant)
            return await self._async_continue_sleepys_route()
        options = [
            *(SelectOptionDict(value=key, label=key) for key in _SLEEPYS_ROUTES),
            *(SelectOptionDict(value=app, label=choice_label(app)) for app in apps),
            *([SelectOptionDict(value="keep", label="keep")] if can_keep else []),
        ]
        return self.async_show_form(
            step_id="sleepys_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            translation_key="sleepys_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    async def _async_continue_sleepys_route(self) -> ConfigFlowResult:
        """Ask what the staged route still needs, then finish it."""
        from .setup_questions import setup_profile_for

        assert self._manual_data is not None
        data = self._manual_data
        step = _APP_SETUP_STEPS.get(data[CONF_BED_TYPE])
        if step is not None and step != "sleepys_family":
            # A suggested app's own step owns its settings.
            return await getattr(self, f"async_step_{step}")()
        profile = setup_profile_for(data)
        if profile is not None and profile.questions:
            return await self.async_step_profile_questions()
        return await self._async_finish_family_route()

    async def async_step_customatic_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which Customatic app runs the bed, and for Z-Series the model."""
        return await self._async_app_family("customatic_family", _CUSTOMATIC_APPS, user_input)

    async def async_step_jordans_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which Jordan's app runs the bed."""
        return await self._async_app_family("jordans_family", _JORDANS_APPS, user_input)

    async def async_step_starcode_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which StarCode app runs the bed, then that app's own settings."""
        return await self._async_app_family("starcode_family", _STARCODE_APPS, user_input)

    async def async_step_reverie_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the Reverie receiver from the service the bed advertises."""
        return await self._async_service_family("reverie_family", _REVERIE_ROUTES, user_input)

    async def async_step_sleep_number_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the Sleep Number transport from the service the bed advertises."""
        return await self._async_service_family(
            "sleep_number_family", _SLEEP_NUMBER_ROUTES, user_input
        )

    async def _async_service_family(
        self,
        step_id: str,
        routes: Mapping[str, tuple[str, str]],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Confirm a family's route from the service the bed advertises.

        The receiver's service, not the app or name, decides the route. Only a
        bed whose advertisement shows none of the services, or several, is
        asked. The first route is the family's picker row.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        from .setup_questions import setup_profile_for

        assert self._manual_data is not None
        data = self._manual_data
        incoming, _variant = self._incoming(step_id)
        info = self._discovery_info or bluetooth.async_last_service_info(
            self.hass, data[CONF_ADDRESS], connectable=False
        )
        advertised = {uuid.lower() for uuid in (info.service_uuids if info else ())}
        confirmed = [key for key, (_bed_type, service) in routes.items() if service in advertised]
        choice = (user_input or {}).get("choice")
        if choice is None and len(confirmed) == 1:
            choice = confirmed[0]
        if choice == "keep" or (isinstance(choice, str) and choice in routes):
            if choice != "keep":
                self._select_family_route(routes[choice][0], None)
            profile = setup_profile_for(self._manual_data)
            resume = (
                self.async_step_profile_questions
                if profile is not None and profile.questions
                else self._async_finish_family_route
            )
            if choice == "keep" and self._migration is None:
                return await self._async_keep_detected(step_id, resume)
            return await resume()
        # A route detection or the saved setup chose stays one answer away.
        can_keep = incoming != next(iter(routes.values()))[0]
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*routes, *(["keep"] if can_keep else [])],
                            translation_key=f"{step_id}_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_richmat_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which Richmat app or remote runs the bed; shared names and services cannot tell.

        An app chosen elsewhere, such as from a brand's list, already answered.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        first = "richmat_family" not in self._family_incoming
        if first and self._incoming("richmat_family")[0] != BED_TYPE_RICHMAT:
            return await self._async_continue_richmat_route()
        choice = (user_input or {}).get("choice")
        if isinstance(choice, str) and choice in _RICHMAT_APPS:
            bed_type, variant = _RICHMAT_APPS[choice]
            self._select_family_route(bed_type, variant)
            if bed_type == BED_TYPE_RICHMAT:
                # RMControl still names its product; the remote controls have none.
                data[CONF_RMCONTROL_PRODUCT] = None if choice == "rmcontrol" else ""
            else:
                for key in (CONF_RMCONTROL_PRODUCT, CONF_RMCONTROL_SIDE, CONF_RICHMAT_REMOTE):
                    data.pop(key, None)
            return await self._async_continue_richmat_route()
        return self.async_show_form(
            step_id="richmat_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=list(_RICHMAT_APPS),
                            translation_key="richmat_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _async_continue_richmat_route(self) -> ConfigFlowResult:
        """Stage what the chosen Richmat route reads from the bed's name, then ask its questions."""
        assert self._manual_data is not None
        data = self._manual_data
        bed_type = data[CONF_BED_TYPE]
        info = self._discovery_info or bluetooth.async_last_service_info(
            self.hass, data[CONF_ADDRESS], connectable=False
        )
        name = info.name if info is not None else None
        if bed_type in RICHMAT_MH_APPS:
            # The app's name rule reads the raw advertised name.
            data.update(_name_rule_setup_name(bed_type, name))
        elif bed_type == BED_TYPE_RICHMAT and CONF_RICHMAT_REMOTE not in data:
            # A listed code the name carries is the default; an unlisted one is
            # kept as detected.
            code = detect_richmat_remote_from_name(name)
            data[CONF_RICHMAT_REMOTE] = (
                code.upper()
                if code and code.upper() in RICHMAT_REMOTES
                else code or RICHMAT_REMOTE_AUTO
            )
        return await self.async_step_profile_questions()

    async def async_step_remacro_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which store app runs a Remacro bed, offering the apps that list its model.

        The advertisement picks the model, never the app. A model no app lists,
        or none seen yet, runs the fallback controls on any app.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        from .beds.remacro_protocol import (
            MODELS,
            advertised_model_id,
            app_for_variant,
            apps_listing,
        )

        assert self._manual_data is not None
        data = self._manual_data
        manufacturer_data = remacro_manufacturer_data(
            self.hass,
            data[CONF_ADDRESS],
            self._discovery_info.manufacturer_data if self._discovery_info is not None else None,
        )
        model_id = advertised_model_id(manufacturer_data)
        listing = apps_listing(model_id)
        apps = [
            key
            for key, variant in _REMACRO_APPS.items()
            if not listing or app_for_variant(variant) in listing
        ]
        choice = (user_input or {}).get("choice")
        if isinstance(choice, str) and choice in apps:
            # The bed type stays; only the app changes, so the form's settings stay.
            data[CONF_PROTOCOL_VARIANT] = _REMACRO_APPS[choice]
            self._manual_data = self._maybe_add_advertisement_metadata(
                data, manufacturer_data=manufacturer_data
            )
            return await self._async_finish_family_route()
        model = (
            "none seen yet"
            if model_id is None
            else MODELS[model_id].name
            if model_id in MODELS
            else f"company ID {model_id}"
        )
        return self.async_show_form(
            step_id="remacro_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=apps,
                            translation_key="remacro_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"model": model},
        )

    async def async_step_limoss_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app runs a Limoss receiver, or keep its generic controls."""
        return await self._async_app_family(
            "limoss_family", _LIMOSS_APPS, user_input, row=BED_TYPE_LIMOSS
        )

    async def _async_app_family(
        self,
        step_id: str,
        apps: Mapping[str, _AppAnswer],
        user_input: dict[str, Any] | None,
        *,
        row: str | None = None,
    ) -> ConfigFlowResult:
        """Ask which app of a family runs the bed; the apps share names and services.

        Only the family row asks: an app chosen elsewhere, such as from a brand's
        list, already answered. A guided change asks again and offers Keep. The
        row is the first answer's route unless given.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        row = row or next(iter(apps.values()))[0]
        # Another family's guided change can hand over a suggested app.
        guided = self._migration_family is not None and self._migration_family.key == step_id
        first = step_id not in self._family_incoming
        # An app's own row, or a route arriving from another family,
        # already answered.
        if first and not guided and self._incoming(step_id)[0] != row:
            return await self._async_continue_app_family(apps)
        choice = (user_input or {}).get("choice")
        if choice == "keep" and guided:
            return await self.async_step_migration_keep()
        if isinstance(choice, str) and choice in apps:
            bed_type, variant, _step = apps[choice]
            changed = bed_type != data[CONF_BED_TYPE]
            self._select_family_route(bed_type, variant)
            if changed:
                # A new app starts without the old one's own settings, as in Configure.
                AdjustableBedOptionsFlow._remove_irrelevant_bed_settings(data, bed_type)  # noqa: SLF001
            return await self._async_continue_app_family(apps)
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*apps, *(["keep"] if guided else [])],
                            translation_key=f"{step_id}_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _async_continue_app_family(
        self, apps: Mapping[str, _AppAnswer]
    ) -> ConfigFlowResult:
        """Continue with the staged app's own step, or finish its route."""
        assert self._manual_data is not None
        data = self._manual_data
        step = next(
            (
                step
                for bed_type, _variant, step in apps.values()
                if bed_type == data[CONF_BED_TYPE]
            ),
            None,
        )
        if step is not None:
            return await getattr(self, f"async_step_{step}")()
        return await self._async_finish_family_route()

    async def async_step_profile_questions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the staged profile's declared questions, then finish its route."""
        from .setup_questions import setup_profile_for

        assert self._manual_data is not None
        data = self._manual_data
        profile = setup_profile_for(data)
        assert profile is not None and profile.questions
        if profile.seed is not None:
            self._manual_data = data = profile.seed(self.hass, data, self._discovery_info)
        context = FlowContext(self.hass, verifiable=self._verification_possible())
        answers = _profile_answers(profile, user_input or {}, data, context)
        candidate = profile.staged(data, answers)
        errors = profile.errors(candidate, context) if user_input is not None else {}
        if user_input is not None and not errors:
            # What normalizing dropped stays dropped.
            # An answer that picks the route settles what that route's profile owns.
            self._manual_data = {
                **candidate,
                **(setup_profile_for(candidate) or profile).settled(candidate),
            }
            if self._recheck_answers:
                # Answers that corrected a failed connection check are checked again.
                self._recheck_answers = False
                self._verify_form_shown = False
                self._pending_entry = self._manual_data
                self._async_start_probe_operation()
            return await self._async_finish_family_route()
        return self._show_profile_questions(profile, candidate, errors)

    def _show_profile_questions(
        self, profile: SetupProfile, data: Mapping[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="profile_questions",
            data_schema=vol.Schema(_profile_question_schema(profile, data, FlowContext(self.hass))),
            errors=errors,
            description_placeholders={
                "profile": profile.title(data) if profile.title else bed_type_label(data[CONF_BED_TYPE])
            },
        )

    async def async_step_malouf_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or receiver runs a Malouf or Lucid bed; never infer it from the bed.

        Shared services and retail names identify neither the app nor the hardware.
        """
        if (another := await self._async_another_app(user_input)) is not None:
            return another
        assert self._manual_data is not None
        data = self._manual_data
        incoming, _variant = self._incoming("malouf_family")
        # Keep saves the receiver detection or the saved setup chose; the family
        # row alone chose no app to keep.
        can_keep = self._migration is not None or incoming != BED_TYPE_MALOUF_APP
        choice = (user_input or {}).get("choice")
        if choice == "keep" and can_keep:
            if self._migration is not None:
                return await self.async_step_migration_keep()
            return await self._async_keep_detected(
                "malouf_family", self.async_step_profile_questions
            )
        if isinstance(choice, str) and choice in _MALOUF_ROUTES:
            bed_type, app = _MALOUF_ROUTES[choice]
            if (bed_type, app) != (data[CONF_BED_TYPE], data.get(CONF_MALOUF_APP_PROFILE)):
                # Another app or receiver starts from its own defaults, never
                # another app's model, role or transport.
                for key in (
                    CONF_MALOUF_APP_PROFILE,
                    CONF_MALOUF_APP_MODEL,
                    CONF_MALOUF_APP_TRANSPORT,
                    CONF_MALOUF_APP_PRIMARY,
                ):
                    data.pop(key, None)
            self._select_family_route(bed_type, None)
            if app is not None:
                data[CONF_MALOUF_APP_PROFILE] = app
            return await self.async_step_profile_questions()
        return self.async_show_form(
            step_id="malouf_family",
            data_schema=vol.Schema(
                {
                    vol.Required("choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=[*_MALOUF_ROUTES, *(["keep"] if can_keep else [])],
                            translation_key="malouf_family_choice",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"current": bed_type_label(incoming)},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return AdjustableBedOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._scan_error: str | None = None
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._all_ble_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._manual_data: dict[str, Any] | None = None
        # A family route that needs pairing pairs from discovery, not manual entry.
        self._route_pairing_from_discovery = False
        # The declared questions are open again to correct a failed connection check.
        self._recheck_answers = False
        # Guided change of an existing entry (profile_migration).
        self._migration: MigrationSnapshot | None = None
        self._migration_family: ManagedFamily | None = None
        self._migration_verified = False
        self._migration_endpoints_checked = False
        # The route each family question started from, by its step.
        self._family_incoming: dict[str, tuple[str, str]] = {}
        self._keeson_group: str | None = None
        # What the connection check resolved for the staged route, for the
        # confirm step's control list only.
        self._migration_preview: dict[str, Any] = {}
        # The bed-type row the app question or the brand list chose.
        self._selected_bed_type: str | None = None
        # The step that continues once the app is chosen, when the device came first.
        self._app_after_device: Literal["device", "manual_entry"] | None = None
        self._selected_protocol_variant: str | None = None
        # For disambiguation UI when BLE detection is ambiguous
        self._disambiguation_types: list[str] | None = None
        self._disambiguated_bed_type: str | None = None
        self._retrying_devices: dict[str, tuple[ConfigEntry, BluetoothServiceInfoBleak | None]] = {}
        # Carries the finalized entry across the optional verify_connection step
        self._pending_entry: dict[str, Any] | None = None
        self._pending_title: str | None = None
        # A new bed's journey: how the device was found, then its app's
        # questions, then its final settings (#676 direction A).
        self._new_bed_origin: Literal["discovered", "picked", "typed"] = "discovered"
        self._typed_address: str | None = None
        # A picked device keeps the adapter that found it as its default.
        self._device_adapter: str = ADAPTER_AUTO
        self._final_settings_pending = False
        self._final_settings_then: Literal["route", "verify"] = "route"
        # Generic fields a family or app step asked or set itself, outside a
        # declared question; the final settings leave them alone.
        self._journey_set: set[str] = set()
        # The family question a discovered bed opened, which offers every other app.
        self._another_app_step: str | None = None
        # The route a discovered bed's family settled without asking, to confirm.
        self._unasked_route: str | None = None
        # True once the verify_connection form has actually been rendered, so a
        # replayed submission from the previous form cannot be read as a
        # confirmation of a result the user never saw.
        self._verify_form_shown: bool = False
        self._octo_pin_form_shown: bool = False
        # The result step whose guided-change check failed; the failure form
        # hands its Try again or Keep back to it.
        self._migration_failed_from: Literal["verify_connection", "pairing_result"] | None = None
        # The family step a new bed's Keep came from, and how setup continues.
        self._keep_detected: tuple[str, Callable[[], Awaitable[ConfigFlowResult]]] | None = None
        # Set when the user chose to replace an existing host bond rather than
        # pair on top of it.
        self._pairing_remove_record: LocalBondRecord | None = None
        # Which pairing form to return to on Retry, and whether the pairing
        # result form has actually been rendered (see async_step_pairing_result).
        self._pairing_origin_step: str | None = None
        self._pairing_result_shown: bool = False
        # Which pairing operation the user asked for: a new bond, proving an
        # existing one, or replacing one.
        self._pairing_mode: str = "new"
        # The adapter that owns the bond being verified, so the check runs on the
        # route that can actually authenticate, and the record it belongs to.
        self._pairing_verify_source: str | None = None
        # An authentication failure on a proxy pins the next pairing attempt
        # to that source, even when the configured adapter is Automatic.
        self._pairing_retry_source: str | None = None
        self._pairing_verify_record: LocalBondRecord | None = None
        # True only when every route that could take the connection holds the
        # record being verified, which is what makes asserting it without
        # connecting sound (see _every_route_holds_bond).
        self._pairing_route_certain: bool = False
        # Octo capability snapshots captured per single-entry as the user connects
        # each side, so a one-link Octo pair can be captured SEQUENTIALLY across
        # resubmissions of the pair step (connect left, disconnect, connect right)
        # — the flow instance persists, so a side captured while live stays
        # available after it disconnects.
        self._captured_octo_snapshots: dict[str, dict[str, Any]] = {}
        _LOGGER.debug("AdjustableBedConfigFlow initialized")

    def _set_device_title_placeholders(self, name: str | None, address: str) -> None:
        """Identify the selected device in the flow title."""
        self.context["title_placeholders"] = {
            "name": name or "Unknown",
            "address": address.upper(),
        }

    def _prepare_disambiguation(self, detection_result: DetectionResult) -> bool:
        """Prepare the focused bed-type chooser for an ambiguous detection."""
        self._disambiguation_types = None
        self._disambiguated_bed_type = None

        bed_type = detection_result.bed_type
        if (
            bed_type is None
            or detection_result.confidence >= 0.7
            or (not detection_result.ambiguous_types and bed_type != BED_TYPE_MOTION_BED)
        ):
            return False

        seen: set[str] = set()
        disambiguation_types: list[str] = []
        for candidate in (bed_type, *(detection_result.ambiguous_types or ())):
            if candidate in _VIBRADORM_FAMILY_TYPES:
                candidate = BED_TYPE_VIBRADORM
            if candidate not in seen:
                seen.add(candidate)
                disambiguation_types.append(candidate)
        self._disambiguation_types = disambiguation_types
        return True

    async def _get_config_translation(self, key: str, default: str) -> str:
        """Return a config-flow translation with a safe English fallback."""
        return await _async_translation(self.hass, "config", key, default)

    async def _async_transport_note(
        self,
        address: str,
        preferred_adapter: str | None,
        bed_type: str | None = None,
        protocol_variant: str | None = None,
    ) -> str:
        """Describe the Bluetooth path setup will most likely take.

        Recomputed on every render of the form rather than captured once when
        the flow started: which adapters and proxies can see a bed changes from
        moment to moment, and showing a path that has since disappeared is worse
        than showing none.
        """
        try:
            prediction = async_predict_path(self.hass, address, preferred_adapter)
            return await async_describe_prediction(
                self.hass,
                prediction,
                pairing_required=bool(bed_type and requires_pairing(bed_type, protocol_variant)),
            )
        except Exception:  # noqa: BLE001 - never block setup on a preview
            _LOGGER.debug("Could not describe the connection path for %s", address, exc_info=True)
            return ""

    async def _get_pairing_instructions(
        self, bed_type: str | None, protocol_variant: str | None = None
    ) -> str:
        """Return pairing instructions tailored to the selected bed type."""
        if bed_type == BED_TYPE_SLEEP_NUMBER:
            return await self._get_config_translation(
                "step.bluetooth_pairing.data_description.pairing_instructions_sleep_number",
                "1. Put your bed in pairing mode (hold the side pairing button until the blue light blinks)\n"
                "2. Click 'Pair Now'",
            )
        if bed_type == BED_TYPE_LEGGETT_GEN2 or (
            bed_type == BED_TYPE_LEGGETT_PLATT and protocol_variant == LEGGETT_VARIANT_GEN2
        ):
            # LP Comfort Connect pairing steps, from the LP Control app's
            # pairing_mode_instructions_gen2 / settings_pair_another_phone_msg.
            return await self._get_config_translation(
                "step.bluetooth_pairing.data_description.pairing_instructions_leggett_gen2",
                "1. Unplug your bed's power cord and remove any batteries from the power supply.\n"
                "2. Plug the bed back in. Wait for a small chime and a pulsing blue light "
                "under the bed.\n"
                "3. While the light is pulsing, promptly click 'Pair Now'.",
            )
        if bed_type in {
            BED_TYPE_OKIMAT,
            BED_TYPE_OKIN_CST,
            BED_TYPE_OKIN_RF_ECO_BT,
            BED_TYPE_OKIN_UUID,
            BED_TYPE_LEGGETT_OKIN,
            BED_TYPE_LEGGETT_PLATT,
        }:
            return await self._get_config_translation(
                "step.bluetooth_pairing.data_description.pairing_instructions_okin",
                "1. Put the OKIN base into Bluetooth pairing mode by power-cycling the control box: "
                "unplug it for ~30 seconds, then plug it back in. The status light blinks blue, then turns "
                "green after ~20 seconds. (Some models instead use the under-bed lamp/light button - hold it "
                "until the light blinks blue.) There is no separate Bluetooth pairing button; any Pair/Learn "
                "button on the box only syncs the RF remote.\n"
                "2. While the light is active, click 'Pair Now'.",
            )
        return await self._get_config_translation(
            "step.bluetooth_pairing.data_description.pairing_instructions_generic",
            "1. Put your bed in pairing mode (hold lamp button until blue light blinks, or unplug for 30+ seconds)\n"
            "2. Click 'Pair Now'",
        )

    def _get_octo_split_setup_note(
        self,
        *,
        address: str,
        name: str | None,
        bed_type: str | None,
    ) -> str | None:
        """Return setup guidance for split Octo beds with one controller per side."""
        if bed_type != BED_TYPE_OCTO or not name:
            return None

        normalized_name = name.strip().lower()
        if not normalized_name:
            return None

        normalized_address = address.upper()
        candidates: list[BluetoothServiceInfoBleak] = []
        seen_addresses: set[str] = set()
        for device_map in (self._discovered_devices, self._all_ble_devices):
            for candidate in device_map.values():
                candidate_address = candidate.address.upper()
                if candidate_address in seen_addresses:
                    continue
                seen_addresses.add(candidate_address)
                candidates.append(candidate)

        if not candidates:
            candidates = get_discovered_service_info(
                self.hass,
                include_non_connectable=True,
            )

        matching_addresses: set[str] = set()
        for candidate in candidates:
            if candidate.address.upper() == normalized_address:
                continue
            if (candidate.name or "").strip().lower() != normalized_name:
                continue
            if detect_bed_type(candidate) != BED_TYPE_OCTO:
                continue
            matching_addresses.add(candidate.address.upper())

        if not matching_addresses:
            return None

        device_count = len(matching_addresses)
        device_word = "device" if device_count == 1 else "devices"
        verb = "is" if device_count == 1 else "are"
        return (
            f"{device_count} other Octo {device_word} named {name} {verb} visible. "
            "Split Octo beds often expose one BLE address per side, so add the other address "
            "as a second Adjustable Bed device if this one only moves one side. "
            "'Back + Legs Up' only affects the currently connected controller."
        )

    def _maybe_add_advertisement_metadata(
        self,
        entry_data: dict[str, Any],
        *,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> dict[str, Any]:
        """Cache advertisement selectors: Kaidi room/VADDR or the Remacro model."""
        if entry_data.get(CONF_BED_TYPE) == BED_TYPE_REMACRO:
            return add_remacro_model(
                entry_data,
                remacro_manufacturer_data(self.hass, entry_data[CONF_ADDRESS], manufacturer_data),
            )
        if entry_data.get(CONF_BED_TYPE) != BED_TYPE_KAIDI:
            return entry_data

        advertisement = resolve_kaidi_advertisement(
            self.hass,
            entry_data[CONF_ADDRESS],
            manufacturer_data=manufacturer_data,
        )
        return add_kaidi_entry_metadata(entry_data, advertisement)

    def _remacro_variant_error(
        self,
        bed_type: str | None,
        protocol_variant: str,
        address: str,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> str | None:
        """Return a form error when the chosen app does not list the bed's model."""
        if bed_type != BED_TYPE_REMACRO:
            return None
        problem, _ = remacro_entry_problem(
            {CONF_PROTOCOL_VARIANT: protocol_variant},
            remacro_manufacturer_data(self.hass, address, manufacturer_data),
        )
        return "remacro_model_not_in_app" if problem == "not_in_app" else None

    def _async_abort_diagnostic_browser(
        self,
        *,
        address: str,
        name: str | None,
        source: str | None,
        connectable: bool | None,
    ) -> ConfigFlowResult:
        """Finish the BLE browser flow without creating a config entry."""
        if connectable is True:
            connectable_text = "Yes"
        elif connectable is False:
            connectable_text = "No (scanner says non-connectable)"
        else:
            connectable_text = "Unknown"

        return self.async_abort(
            reason="diagnostic_browser_ready",
            description_placeholders={
                "name": name or "Unknown",
                "address": address,
                "source": source or "unknown",
                "connectable": connectable_text,
            },
        )

    def _configured_entries_by_address(self) -> dict[str, ConfigEntry]:
        """Return active entries keyed by normalized Bluetooth address.

        Paired entries (Dual Bed 4.0) have a synthetic ``pair_<id>`` unique_id, so
        they are additionally indexed by each member MAC. Otherwise re-discovery
        of an absorbed side would slip past the dedup and create a duplicate
        standalone entry. Single-bed entries have no members, so they are
        unaffected.

        Ignored discovery placeholders must remain selectable in a user-started
        flow. Home Assistant replaces the ignored entry when that flow creates
        the real entry; treating it as configured here made the bed disappear
        from both device pickers and led users to an unhelpful duplicate error.
        """
        configured: dict[str, ConfigEntry] = {}
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.source == SOURCE_IGNORE:
                continue
            candidate = entry.unique_id or entry.data.get(CONF_ADDRESS)
            if isinstance(candidate, str):
                configured[candidate.upper()] = entry
            for member in pair_member_addresses(entry.data):
                configured[member] = entry
        return configured

    def _octo_capability_snapshot(self, entry: ConfigEntry) -> dict | None:
        """Capability snapshot for a single Octo entry — its LIVE controller's, or
        the one cached earlier this flow, or None (not Octo / never connected).

        Octo discovers its capabilities post-connect, and a one-link Octo only ever
        has ONE side connected at a time, so we cache each side's snapshot the
        moment it is live and fall back to that cache when it later disconnects.
        That lets the user capture both sides SEQUENTIALLY (connect left, disconnect,
        connect right) across resubmissions of the pair step instead of needing both
        connected at once — which the single-connection profile is designed to avoid.
        """
        if entry.data.get(CONF_BED_TYPE) != BED_TYPE_OCTO:
            return None
        coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        snapshot_fn = getattr(getattr(coordinator, "controller", None), "capability_snapshot", None)
        live = snapshot_fn() if callable(snapshot_fn) else None
        if isinstance(live, dict):
            # Copy before caching/returning so later controller or builder mutation
            # can't change the cached sequential snapshot.
            snapshot = dict(live)
            self._captured_octo_snapshots[entry.entry_id] = snapshot
            return dict(snapshot)
        cached = self._captured_octo_snapshots.get(entry.entry_id)
        if isinstance(cached, dict):
            return dict(cached)
        # Older paired snapshots predate capability records. Keep their saved
        # fields available for offline setup, while OctoController treats them
        # as non-authoritative until current complete discovery arrives.
        capabilities = entry.data.get("capabilities")
        legacy = capabilities.get("octo") if isinstance(capabilities, Mapping) else None
        return dict(legacy) if isinstance(legacy, Mapping) else None

    def _offline_safe_bed_type(self, entry: ConfigEntry) -> str | None:
        """Resolve a concrete bed type for pairing compatibility.

        Legacy entries may store their concrete type under protocol_variant.
        Use the same resolver as offline controller creation and pair descriptors.
        """
        return resolve_explicit_bed_type(
            entry.data.get(CONF_BED_TYPE), entry.data.get(CONF_PROTOCOL_VARIANT)
        )

    def _resolved_pair_side_data(self, entry: ConfigEntry) -> dict[str, Any]:
        """Merged ``data`` + ``options`` for a pair child, with an explicit legacy
        variant resolved to its concrete bed type.

        Options (e.g. customized angle limits, which the coordinator reads before
        data) are merged in so they survive the original being absorbed. Resolve
        bed_type consistently with the compatibility check and offline controller
        creation, so an explicit legacy variant keeps its concrete type.
        """
        data = {**entry.data, **dict(entry.options)}
        data[CONF_BED_TYPE] = resolve_explicit_bed_type(
            data.get(CONF_BED_TYPE), data.get(CONF_PROTOCOL_VARIANT)
        )
        return data

    def _is_octo_star2(self, entry: ConfigEntry) -> bool:
        """Whether ``entry`` is an Octo Remote Star2 bed — a different protocol with
        FIXED capabilities and no PIN/snapshot, so it is statically offline-safe
        (unlike standard Octo, which needs a live capability snapshot)."""
        return (
            entry.data.get(CONF_BED_TYPE) == BED_TYPE_OCTO
            and entry.data.get(CONF_PROTOCOL_VARIANT) == OCTO_VARIANT_STAR2
        )

    def _is_octo_one_motor_lift(self, entry: ConfigEntry) -> bool:
        """Return whether an OCTO entry uses the standalone one-motor lift layout."""
        if entry.data.get(CONF_BED_TYPE) != BED_TYPE_OCTO:
            return False
        data = {**entry.data, **dict(entry.options)}
        override = data.get(CONF_OCTO_MOTOR_COUNT_OVERRIDE)
        if override not in (None, "auto"):
            return override == "1" or override == 1
        snapshot = self._octo_capability_snapshot(entry)
        discovered_count = snapshot.get("discovered_motor_count") if snapshot else None
        if type(discovered_count) is int and 1 <= discovered_count <= 4:
            return discovered_count == 1
        records = snapshot.get("capability_records") if snapshot else None
        motor_record = (
            records.get("1", records.get("000001")) if isinstance(records, dict) else None
        )
        characteristic = (
            motor_record.get("characteristic") if isinstance(motor_record, dict) else None
        )
        if isinstance(characteristic, list) and characteristic:
            return characteristic[0] == 1
        return False

    async def _pair_layout_snapshot(self, entry: ConfigEntry) -> dict[str, Any] | None:
        """Capture the side's generic motor layout from its capability controller.

        Prefer the loaded controller, otherwise mint the protocol's supported
        client-free capability controller. If neither is available, the layout is
        unknown and pairing is blocked rather than inferred from another protocol.
        The persisted snapshot keeps the decision auditable after absorption.
        """
        from .coordinator import AdjustableBedCoordinator
        from .octo_runtime import octo_controller

        coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        controller = getattr(coordinator, "capability_controller", None)
        if controller is None and not isinstance(coordinator, AdjustableBedCoordinator):
            coordinator = AdjustableBedCoordinator(self.hass, entry)
        if coordinator.capability_controller is None:
            await coordinator.async_prime_offline_controller()
        controller = coordinator.capability_controller
        if controller is None:
            return None
        specs = list(getattr(controller, "motor_control_specs", ()))
        configured_motor_count = entry.options.get(
            CONF_MOTOR_COUNT,
            entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
        )
        octo = octo_controller(controller)
        if octo is not None:
            configured_motor_count = octo.effective_motor_count
            if configured_motor_count is None:
                return None
        return {
            "motor_count": int(configured_motor_count),
            "motor_keys": sorted(spec.key for spec in specs),
            "discrete_motor_control": bool(
                getattr(controller, "has_discrete_motor_control", False)
            ),
            "supports_motor_control": bool(getattr(controller, "supports_motor_control", False)),
        }

    def _is_absorbed_pair_member(self, address: str) -> bool:
        """Whether ``address`` is already a side of an existing paired bed."""
        member = address.upper()
        return any(
            member in pair_member_addresses(entry.data)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    def _async_abort_retrying_entry(self, address: str) -> ConfigFlowResult:
        """Explain how to recover when the bed is already stuck retrying setup."""
        entry, info = self._retrying_devices[address]
        display_name = entry.title or (info.name if info is not None else None) or "Unknown"
        return self.async_abort(
            reason="configured_retrying",
            description_placeholders={
                "name": display_name,
                "address": address,
            },
        )

    def _retrying_display_name(
        self,
        entry: ConfigEntry,
        info: BluetoothServiceInfoBleak | None,
    ) -> str:
        """Return the most helpful name for a retrying config entry."""
        return entry.title or (info.name if info is not None else None) or "Unknown"

    async def _get_retrying_option_suffix(self) -> str:
        """Return the localized selector hint for retrying configured beds."""
        return await self._get_config_translation(
            "abort.configured_retrying_suffix",
            "[already configured, setup retry]",
        )

    def _format_retrying_option_label(
        self,
        address: str,
        entry: ConfigEntry,
        info: BluetoothServiceInfoBleak | None,
        *,
        suffix: str,
    ) -> str:
        """Format the selector label for a retrying configured bed."""
        return f"{self._retrying_display_name(entry, info)} ({address}) {suffix}"

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        # Respect the user's global opt-out: suppress automatic discovery cards
        # entirely (no flow, no Repairs issue, no discovery-log entry). Manual
        # "Add Integration" is unaffected and still lists nearby devices.
        if await async_is_discovery_disabled(self.hass):
            _LOGGER.debug(
                "Ignoring discovered device %s - automatic discovery is disabled",
                discovery_info.address,
            )
            return self.async_abort(reason="discovery_disabled")

        # First-time setup can fail before any entry exists. Load the domain
        # so the support action and its download route are already available.
        await async_setup_component(self.hass, DOMAIN, {})

        _LOGGER.info(
            "Bluetooth discovery triggered for device: %s (name: %s, RSSI: %s)",
            discovery_info.address,
            discovery_info.name,
            discovery_info.rssi,
        )
        _LOGGER.debug("Discovery info details:")
        _LOGGER.debug("  Address: %s", discovery_info.address)
        _LOGGER.debug("  Name: %s", discovery_info.name)
        _LOGGER.debug("  Service UUIDs: %s", discovery_info.service_uuids)
        _LOGGER.debug("  Manufacturer data: %s", discovery_info.manufacturer_data)
        _LOGGER.debug("  Service data: %s", discovery_info.service_data)

        # Normalize address to uppercase to prevent duplicates from case mismatches
        # between Bluetooth discovery (may be lowercase) and manual entry (normalized)
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        # Don't re-offer a side already absorbed into a paired bed: its MAC is a
        # pair member, not the paired entry's (synthetic) unique_id, so the abort
        # above won't catch it.
        if self._is_absorbed_pair_member(discovery_info.address):
            return self.async_abort(reason="already_configured")

        # Use detailed detection to get confidence and ambiguity info
        detection_result = detect_bed_type_detailed(discovery_info)
        bed_type = detection_result.bed_type

        if bed_type is None:
            # Devices that match our broad Bluetooth manifest matchers but aren't
            # recognised as a bed are silently ignored. We deliberately do NOT
            # raise a Repairs issue here: most matches are unrelated BLE devices
            # (the manifest matches generic manufacturer IDs / name prefixes), so
            # nagging the user about every passing speaker, sensor or phone would
            # be noise. Discovery simply aborts; users add unsupported beds via
            # the manual flow, which offers a support bundle.
            _LOGGER.debug(
                "Device %s is not a supported bed type, aborting",
                discovery_info.address,
            )
            return self.async_abort(reason="not_supported")

        _LOGGER.info(
            "Detected supported bed: %s at %s (name: %s) with confidence %.1f",
            bed_type,
            discovery_info.address,
            discovery_info.name,
            detection_result.confidence,
        )

        # Persist a compact record of this auto-detection so misidentified devices
        # can be diagnosed and reported later. Without this the signals behind a
        # false positive are lost once the discovery card is dismissed (HA only
        # persists the bare MAC for devices the user explicitly ignores).
        device_info = capture_device_info(discovery_info)
        try:
            await async_get_discovery_log(self.hass).async_record(
                address=device_info.address,
                name=device_info.name,
                service_uuids=device_info.service_uuids,
                manufacturer_data=device_info.manufacturer_data,
                bed_type=bed_type,
                confidence=detection_result.confidence,
                signals=detection_result.signals,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to record auto-detection for %s: %s",
                device_info.address,
                err,
            )

        self._discovery_info = discovery_info
        self._set_device_title_placeholders(discovery_info.name, discovery_info.address)

        # Check if disambiguation is needed (low confidence with alternatives)
        if self._prepare_disambiguation(detection_result):
            _LOGGER.debug(
                "Ambiguous detection for %s - showing disambiguation UI with options: %s",
                discovery_info.address,
                self._disambiguation_types,
            )
            return await self.async_step_bluetooth_disambiguate()

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_disambiguate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle disambiguation when BLE detection is ambiguous.

        Shows a focused list of 2-4 candidate bed types instead of the full
        dropdown with 20+ options, making it easier for users to select the
        correct type when the BLE service UUID matches multiple protocols.
        """
        assert self._discovery_info is not None
        assert self._disambiguation_types is not None

        if self._is_absorbed_pair_member(self._discovery_info.address):
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            selected = user_input.get("bed_type_choice")
            if selected == "show_all":
                # Every app, with this device's journey after it.
                _LOGGER.debug("User chose to search every app")
                return await self._async_search_every_app()
            self._disambiguated_bed_type = selected
            _LOGGER.debug("User disambiguated bed type to: %s", selected)
            return await self.async_step_bluetooth_confirm()

        # Build options for disambiguation - only the relevant 2-4 types
        options: list[SelectOptionDict] = []
        for bed_type in self._disambiguation_types:
            display_name = bed_type_label(bed_type)
            options.append(SelectOptionDict(value=bed_type, label=display_name))

        # Add "Show all bed types" fallback option with translated label
        show_all_label = await self._get_config_translation(
            "step.bluetooth_disambiguate.data.show_all_option",
            "Show all bed types...",
        )
        options.append(SelectOptionDict(value="show_all", label=show_all_label))

        return self.async_show_form(
            step_id="bluetooth_disambiguate",
            data_schema=vol.Schema(
                {
                    vol.Required("bed_type_choice"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "name": self._discovery_info.name or "Unknown",
                "address": self._discovery_info.address.upper(),
            },
        )

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app runs a discovered bed, from its detected family's apps (A3).

        A route whose family asks which app runs it asks that question, with
        another app one answer away. Otherwise this step lists the detected bed
        type's own rows, and it also confirms a route a family settled from the
        receiver without asking.
        """
        assert self._discovery_info is not None

        # The bed may have joined a pair while this discovery was awaiting input.
        if self._is_absorbed_pair_member(self._discovery_info.address):
            return self.async_abort(reason="already_configured")

        self._new_bed_origin = "discovered"
        staged = self._unasked_route
        detection = detect_bed_type_detailed(self._discovery_info)
        detected = self._disambiguated_bed_type or detection.bed_type
        if user_input is None and staged is None:
            if self._disambiguated_bed_type is None and self._prepare_disambiguation(detection):
                return await self.async_step_bluetooth_disambiguate()
            if detected is None:
                return await self._async_search_every_app()
            if (question := _APP_SETUP_STEPS.get(detected)) in _APP_QUESTION_STEPS:
                # The family's question is this bed's app question.
                self._another_app_step = question
                result = await self._async_start_new_bed(detected, None)
                if result.get("type") is not FlowResultType.FORM or result.get("step_id") == question:
                    return result
                # The family settled the route from the receiver without
                # asking, so confirm it before its own questions.
                assert self._manual_data is not None
                staged = self._unasked_route = bed_type_choice(
                    self._manual_data[CONF_BED_TYPE], self._manual_data.get(CONF_PROTOCOL_VARIANT)
                )
                self._another_app_step = None
                self._final_settings_pending = False
        route = staged or detected or BED_TYPE_DIAGNOSTIC
        another = await self._get_config_translation(
            "step.bluetooth_confirm.data.another", "Another app or remote: search every app"
        )
        options = [
            *(
                SelectOptionDict(value=choice, label=label)
                for label, choice in _bed_type_rows(route).items()
            ),
            SelectOptionDict(value=_ANOTHER_APP, label=another),
        ]
        picker: Any = (
            _SearchableSelect(options)
            if len(options) > _LIST_ROWS
            else SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST))
        )
        if user_input is not None:
            choice = picker(user_input[CONF_BED_TYPE])
            if choice == _ANOTHER_APP:
                return await self._async_search_every_app()
            self._unasked_route = None
            bed_type, variant = resolve_bed_type_choice(choice)
            return await self._async_start_new_bed(bed_type, variant)
        if route not in {option["value"] for option in options} or (
            resolve_bed_type_choice(route)[0] in VARIANT_REQUIRED_BED_TYPES and len(options) > 2
        ):
            # A bed type that runs only as one of its apps suggests none of them.
            route = None
        default = picker.shown(route) if isinstance(picker, _SearchableSelect) else route
        if detection.confidence < 0.7 and detection.ambiguous_types:
            # A paragraph of its own; translations carry no surrounding space.
            detection_note = "\n\n" + await self._get_config_translation(
                "step.bluetooth_confirm.data.uncertain",
                "Detection is not certain, so check that the app below is yours.",
            )
        else:
            detection_note = ""
        marker = (
            vol.Required(CONF_BED_TYPE, default=default)
            if default is not None
            else vol.Required(CONF_BED_TYPE)
        )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({marker: picker}),
            description_placeholders={
                "name": self._discovery_info.name or "Unknown",
                "address": self._discovery_info.address.upper(),
                "family": _family_name(self._discovery_info),
                "detection_note": detection_note,
            },
        )

    def _reset_family_state(self) -> None:
        """Forget the route each family question started from, for a new journey."""
        self._family_incoming.clear()
        self._keeson_group = None

    def _incoming(self, step_id: str) -> tuple[str, str]:
        """Return the route a family question started from, recorded on its first visit."""
        assert self._manual_data is not None
        return self._family_incoming.setdefault(
            step_id,
            (
                self._manual_data[CONF_BED_TYPE],
                self._manual_data.get(CONF_PROTOCOL_VARIANT) or VARIANT_AUTO,
            ),
        )

    async def _async_another_app(
        self, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult | None:
        """Search every app when a family question's answer asks for another one."""
        answer = (user_input or {}).get("choice", (user_input or {}).get("app"))
        if self._another_app_step is None or answer != _ANOTHER_APP:
            return None
        return await self._async_search_every_app()

    async def _async_search_every_app(self) -> ConfigFlowResult:
        """Ask the app question for this bed, when its family's list does not name its app."""
        self._another_app_step = None
        self._unasked_route = None
        self._final_settings_pending = False
        self._manual_data = None
        self._reset_family_state()
        self._selected_bed_type = None
        self._selected_protocol_variant = None
        self._app_after_device = "device"
        return await self.async_step_select_app()

    def _seed_new_bed(self, bed_type: str, variant: str | None) -> dict[str, Any]:
        """Return a new bed's entry before its app's questions: the device and its route."""
        info = self._discovery_info
        address = info.address.upper() if info is not None else self._typed_address
        assert address is not None
        data: dict[str, Any] = {
            CONF_ADDRESS: address,
            CONF_NAME: (info.name if info is not None else None) or "Adjustable Bed",
            CONF_BED_TYPE: bed_type,
            CONF_PROTOCOL_VARIANT: variant or _default_setup_route(bed_type),
            CONF_PREFERRED_ADAPTER: self._device_adapter,
        }
        if bed_type == BED_TYPE_SOLACE and info is not None and info.name:
            data[CONF_BLE_DEVICE_NAME] = info.name
        if info is not None:
            data.update(_name_rule_setup_name(bed_type, info.name))
        elif bed_type in RICHMAT_MH_APPS and (
            seen := bluetooth.async_last_service_info(self.hass, address, connectable=False)
        ):
            # The app's name rule reads the raw advertised name.
            data.update(_name_rule_setup_name(bed_type, seen.name))
        return data

    async def _async_start_new_bed(self, bed_type: str, variant: str | None) -> ConfigFlowResult:
        """Stage a new bed's route, ask its app's questions, then its final settings."""
        self._reset_family_state()
        self._journey_set = set()
        self._final_settings_pending = True
        data = self._seed_new_bed(bed_type, variant)
        pairing_step: Literal["bluetooth_pairing", "manual_pairing"] = (
            "bluetooth_pairing" if self._new_bed_origin == "discovered" else "manual_pairing"
        )
        if app_step := await self._async_app_setup_step(data, pairing_step=pairing_step):
            return app_step
        self._manual_data = data
        self._route_pairing_from_discovery = pairing_step == "bluetooth_pairing"
        return await self._async_finish_family_route()

    async def _async_new_bed_settings(self, then: Literal["route", "verify"]) -> ConfigFlowResult:
        """Ask a new bed's final settings once its app is settled, then continue with ``then``."""
        self._final_settings_then = then
        self._another_app_step = None
        return await self.async_step_finish_settings()

    @callback
    def async_show_form(
        self,
        *,
        step_id: str | None = None,
        data_schema: vol.Schema | None = None,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
        last_step: bool | None = None,
        preview: str | None = None,
    ) -> ConfigFlowResult:
        """Show a form; a discovered bed's family question also offers every other app."""
        if step_id is not None and step_id == self._another_app_step and data_schema is not None:
            data_schema = _offer_another_app(data_schema)
        return super().async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
            last_step=last_step,
            preview=preview,
        )

    async def async_step_finish_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask a new bed's own settings once its app and route are settled (A6).

        Fields the route's profile sets or asks itself are not shown, and timing
        is collapsed under Advanced connection and timing.
        """
        assert self._manual_data is not None
        data = self._manual_data
        bed_type: str = data[CONF_BED_TYPE]
        variant: str = data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
        info = self._discovery_info
        signals = detect_bed_type_detailed(info).signals if info is not None else None
        hidden = {*hidden_generic_fields(bed_type, variant), *self._journey_set}
        if len(_motor_count_options(bed_type, variant)) < 2:
            # The route fixes its motor count.
            hidden.add(CONF_MOTOR_COUNT)
        routes = (
            {}
            if (bed_type, variant) in APP_VARIANT_CHOICES or CONF_PROTOCOL_VARIANT in hidden
            else _setup_routes(bed_type)
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            submitted = {**user_input, **(user_input.get("timing") or {})}
            chosen = (user_input.get("advanced") or {}).get(CONF_PROTOCOL_VARIANT)
            drawn = variant
            if len(routes) >= 2 and chosen in routes:
                variant = chosen
            entry, errors = self._new_bed_entry(submitted, variant, hidden, signals, drawn)
            if not errors:
                self._final_settings_pending = False
                self._manual_data = entry
                if self._operation is not None:
                    # A probe an app step began shows the final name and adapter.
                    self._pending_entry = entry
                    self._async_start_probe_operation()
                if self._final_settings_then == "verify":
                    return await self._finish_with_verify(entry, entry[CONF_NAME])
                return await self._async_finish_family_route()
        return self.async_show_form(
            step_id="finish_settings",
            data_schema=vol.Schema(
                self._new_bed_settings_schema(bed_type, variant, hidden, routes, signals)
            ),
            errors=_variant_errors_to_base(errors),
            description_placeholders=await self._new_bed_settings_notes(user_input),
        )

    def _new_bed_settings_schema(
        self,
        bed_type: str,
        variant: str,
        hidden: Collection[str],
        routes: Mapping[str, str],
        signals: list[str] | None,
    ) -> dict[vol.Marker, Any]:
        """Return the final settings form for the staged route."""
        assert self._manual_data is not None
        data = self._manual_data
        defaults = {
            CONF_MOTOR_COUNT: self._new_bed_motor_count(bed_type),
            # Positions are read unless the user turns them off.
            CONF_DISABLE_ANGLE_SENSING: False,
            **dict(zip(_PULSE_FIELDS, get_motor_pulse_defaults(bed_type, variant, signals), strict=True)),
        }

        def fields(*keys: str) -> dict[vol.Marker, Any]:
            return _settings_fields(
                self.hass, data, bed_type, variant, [k for k in keys if k not in hidden], defaults
            )

        schema = fields(CONF_NAME, CONF_MOTOR_COUNT, CONF_HAS_MASSAGE)
        if any(bed_type_has_position_feedback(bed_type, route) for route in (variant, *routes)):
            schema.update(fields(CONF_DISABLE_ANGLE_SENSING))
        if (questions := _final_settings_questions(bed_type, variant)) is not None:
            schema.update(
                _profile_question_schema(
                    questions, data, FlowContext(self.hass), advanced_section=False
                )
            )
        schema.update(fields(CONF_PREFERRED_ADAPTER, CONF_DISCONNECT_AFTER_COMMAND))
        if len(routes) >= 2 and (advanced := _route_section(bed_type, variant)) is not None:
            schema[vol.Optional("advanced")] = advanced
        timing = fields(*_PULSE_FIELDS, CONF_IDLE_DISCONNECT_SECONDS)
        schema[vol.Optional("timing")] = section(vol.Schema(timing), {"collapsed": True})
        return schema

    def _detected_richmat_remote(self) -> str | None:
        """Return the Richmat remote code the advertisement or the name shows."""
        if self._discovery_info is None:
            return None
        return detect_bed_type_detailed(
            self._discovery_info
        ).detected_remote or detect_richmat_remote_from_name(self._discovery_info.name)

    def _new_bed_motor_count(self, bed_type: str) -> int:
        """Return a new bed's default motor count, from its remote where it shows one."""
        if bed_type == BED_TYPE_RICHMAT and (remote := self._detected_richmat_remote()):
            return get_richmat_motor_count(get_richmat_features(remote))
        name = self._discovery_info.name if self._discovery_info is not None else None
        return _default_motor_count(bed_type, name)

    def _new_bed_entry(
        self,
        submitted: Mapping[str, Any],
        variant: str,
        hidden: Collection[str],
        signals: list[str] | None,
        drawn_variant: str,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Return the new bed's entry from its staged route and final settings, and errors.

        The form was drawn for ``drawn_variant``; a timing value left as drawn
        follows a route chosen in its Advanced section instead.
        """
        assert self._manual_data is not None
        data = self._manual_data
        bed_type: str = data[CONF_BED_TYPE]
        # A client that ignores the form cannot answer what the route sets itself.
        submitted = {key: value for key, value in submitted.items() if key not in hidden}
        pulse_defaults = get_motor_pulse_defaults(bed_type, variant, signals)
        drawn = get_motor_pulse_defaults(bed_type, drawn_variant, signals)
        shown = {key: data.get(key, value) for key, value in zip(_PULSE_FIELDS, drawn, strict=True)}
        # Left as drawn: the staged value, or the chosen route's own default.
        answered = {
            key: submitted[key]
            for key in _PULSE_FIELDS
            if submitted.get(key) not in (None, "") and str(submitted[key]) != str(shown[key])
        }
        pulse, errors = _parse_settings(
            {**(shown if variant == drawn_variant else {}), **answered}, bed_type, pulse_defaults
        )
        pulse = {**dict(zip(_PULSE_FIELDS, pulse_defaults, strict=True)), **pulse}
        # A count the form did not show is the route's to set; the app or its
        # name may still settle it at runtime, as for an Octo RTV.
        shown_count = (
            self._new_bed_motor_count(bed_type) if CONF_MOTOR_COUNT not in hidden else DEFAULT_MOTOR_COUNT
        )
        motor_count = _normalize_fixed_motor_count(
            bed_type,
            variant,
            int(submitted.get(CONF_MOTOR_COUNT, data.get(CONF_MOTOR_COUNT, shown_count))),
        )
        if not _is_valid_motor_count(bed_type, variant, motor_count):
            errors[CONF_MOTOR_COUNT] = "invalid_motor_count_for_bed_type"
        if not is_valid_variant_for_bed_type(bed_type, variant):
            errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"
        info = self._discovery_info
        manufacturer_data = info.manufacturer_data if info is not None else None
        if variant_error := self._remacro_variant_error(
            bed_type, variant, data[CONF_ADDRESS], manufacturer_data
        ):
            errors[CONF_PROTOCOL_VARIANT] = variant_error
        entry: dict[str, Any] = {
            **data,
            CONF_NAME: submitted.get(CONF_NAME) or data.get(CONF_NAME, "Adjustable Bed"),
            CONF_MOTOR_COUNT: motor_count,
            CONF_HAS_MASSAGE: submitted.get(
                CONF_HAS_MASSAGE, data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE)
            ),
            CONF_DISABLE_ANGLE_SENSING: submitted.get(
                CONF_DISABLE_ANGLE_SENSING,
                data.get(
                    CONF_DISABLE_ANGLE_SENSING,
                    not bed_type_has_position_feedback(bed_type, variant),
                ),
            ),
            CONF_PREFERRED_ADAPTER: submitted.get(
                CONF_PREFERRED_ADAPTER, data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
            ),
            **pulse,
            # The user saw these, so a protocol migration must not treat them as
            # generated defaults, unless a route the app chose set them. Timing
            # the user changed is theirs.
            CONF_MOTOR_PULSE_USER_SET: bool(answered) or data.get(CONF_MOTOR_PULSE_USER_SET, True),
            CONF_DISCONNECT_AFTER_COMMAND: bool(
                submitted.get(
                    CONF_DISCONNECT_AFTER_COMMAND,
                    data.get(
                        CONF_DISCONNECT_AFTER_COMMAND,
                        disconnect_after_command_default_enabled(bed_type, variant),
                    ),
                )
            ),
            CONF_IDLE_DISCONNECT_SECONDS: submitted.get(
                CONF_IDLE_DISCONNECT_SECONDS,
                data.get(CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS),
            ),
        }
        if CONF_PROTOCOL_VARIANT in data or variant != data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO):
            entry[CONF_PROTOCOL_VARIANT] = variant
        if (questions := _final_settings_questions(bed_type, variant)) is not None:
            context = FlowContext(self.hass)
            entry = questions.staged(entry, _profile_answers(questions, submitted, entry, context))
            errors.update(questions.errors(entry, context))
            entry.update(questions.settled(entry))
        entry = self._maybe_add_advertisement_metadata(entry, manufacturer_data=manufacturer_data)
        _LOGGER.info(
            "New bed: address=%s, type=%s, variant=%s, motors=%s, adapter=%s",
            entry[CONF_ADDRESS],
            bed_type,
            entry.get(CONF_PROTOCOL_VARIANT),
            motor_count,
            entry[CONF_PREFERRED_ADAPTER],
        )
        return entry, errors

    async def _new_bed_settings_notes(
        self, user_input: Mapping[str, Any] | None
    ) -> dict[str, str]:
        """Return the final settings form's notes: the route, its transport and checks."""
        assert self._manual_data is not None
        data = self._manual_data
        bed_type: str = data[CONF_BED_TYPE]
        variant = data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
        address: str = data[CONF_ADDRESS]
        info = self._discovery_info
        notes = {
            "name": data.get(CONF_NAME, "Adjustable Bed"),
            "address": address,
            "profile": APP_VARIANT_CHOICES.get((bed_type, variant)) or bed_type_label(bed_type),
            "transport": await self._async_transport_note(
                address,
                (user_input or {}).get(
                    CONF_PREFERRED_ADAPTER, data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                ),
                bed_type,
                variant,
            ),
            "setup_note": "",
            "report_note": "",
        }
        octo_split_note = self._get_octo_split_setup_note(
            address=address, name=info.name if info is not None else None, bed_type=bed_type
        )
        if octo_split_note is not None:
            notes["setup_note"] = f"\n\n{octo_split_note}"
        if info is not None and self._new_bed_origin == "discovered":
            # A one-click "this isn't my bed" report, built from the live
            # (unredacted) advertisement because the user chooses to open it.
            detection = detect_bed_type_detailed(info)
            try:
                integration = await async_get_integration(self.hass, DOMAIN)
                version = str(integration.version) if integration.version else None
            except IntegrationNotFound:
                version = None
            url = build_misidentified_issue_url(
                capture_device_info(info),
                detection.bed_type,
                detection.confidence,
                detection.signals,
                integration_version=version,
                ha_version=HA_VERSION,
            )
            notes["report_note"] = (
                f"\n\nWrong device, or not a bed? [Report a misidentified device]({url})"
            )
        return notes

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the user step to pick discovered device or manual entry."""
        await async_setup_component(self.hass, DOMAIN, {})
        _LOGGER.debug("async_step_user called with input: %s", user_input)

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "scan":
                self._scan_error = None
                self.async_begin_operation(action=SetupAction.LOCATING)
                return await self.async_step_scan()
            if address.startswith(CONFIGURED_RETRY_PREFIX):
                return self._async_abort_retrying_entry(
                    address.removeprefix(CONFIGURED_RETRY_PREFIX)
                )
            if address == "manual":
                _LOGGER.debug("User chose to pick any Bluetooth device")
                # The device comes first here; the app question follows it.
                self._selected_bed_type = None
                self._selected_protocol_variant = None
                return await self.async_step_manual()
            if address == "select_by_app":
                _LOGGER.debug("User chose to set up by app or remote")
                self._selected_bed_type = None
                self._selected_protocol_variant = None
                self._app_after_device = None
                return await self.async_step_select_app()
            if address == "diagnostic":
                _LOGGER.debug("User selected diagnostic mode")
                return await self.async_step_diagnostic()
            if address == "pair_beds":
                _LOGGER.debug("User selected combine two beds")
                return await self.async_step_pair_beds()

            _LOGGER.info("User selected device: %s", address)
            # Normalize address to uppercase to match Bluetooth discovery
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()
            if self._is_absorbed_pair_member(address):
                return self.async_abort(reason="already_configured")

            self._discovery_info = self._discovered_devices[address]
            self._set_device_title_placeholders(
                self._discovery_info.name, self._discovery_info.address
            )
            return await self.async_step_bluetooth_confirm()

        # Discover devices
        _LOGGER.debug("Scanning for BLE devices...")
        self._discovered_devices.clear()  # Clear stale devices from previous scans

        # Log Bluetooth scanner status
        try:
            from homeassistant.components.bluetooth import async_scanner_count

            scanner_count = async_scanner_count(self.hass, connectable=True)
            _LOGGER.debug(
                "Bluetooth scanners available (connectable): %d",
                scanner_count,
            )
        except Exception as err:
            _LOGGER.debug("Could not get scanner count: %s", err)

        # Include non-connectable records as a fallback because some Bluetooth
        # proxies have been observed to misclassify connectable beds.
        all_discovered = get_discovered_service_info(
            self.hass,
            include_non_connectable=True,
        )
        _LOGGER.debug(
            "Total BLE devices visible: %d",
            len(all_discovered),
        )

        # Convert to upper-case for case-insensitive comparison
        configured_entries = self._configured_entries_by_address()
        self._retrying_devices.clear()
        for discovery_info in all_discovered:
            normalized_address = discovery_info.address.upper()
            configured_entry = configured_entries.get(normalized_address)
            if configured_entry is not None:
                if configured_entry.state == ConfigEntryState.SETUP_RETRY:
                    self._retrying_devices[normalized_address] = (configured_entry, discovery_info)
                else:
                    _LOGGER.debug(
                        "Skipping already configured device: %s",
                        discovery_info.address,
                    )
                continue
            if normalized_address in self._retrying_devices:
                _LOGGER.debug(
                    "Skipping duplicate retrying device snapshot: %s",
                    discovery_info.address,
                )
                continue
            bed_type = detect_bed_type(discovery_info)
            if bed_type is not None:
                _LOGGER.info(
                    "Found %s bed: %s (name: %s, RSSI: %s)",
                    bed_type,
                    discovery_info.address,
                    discovery_info.name,
                    discovery_info.rssi,
                )
                self._discovered_devices[discovery_info.address] = discovery_info

        _LOGGER.info(
            "BLE scan complete: found %d supported bed(s)",
            len(self._discovered_devices),
        )

        # Sort discovered beds: named devices first (alphabetically), then MAC-only/unnamed
        sorted_beds = sorted(
            self._discovered_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        sorted_retrying_devices = sorted(
            self._retrying_devices.items(),
            key=lambda item: (
                is_mac_like_name(self._retrying_display_name(item[1][0], item[1][1])),
                self._retrying_display_name(item[1][0], item[1][1]).lower(),
            ),
        )

        retrying_suffix = await self._get_retrying_option_suffix()

        # Discovered beds come first, named with their family; the fixed choices
        # are translated through the selector's translation key.
        options = [
            SelectOptionDict(
                value=address,
                label=f"{info.name or 'Unknown'} ({address}) · {_family_name(info)}",
            )
            for address, info in sorted_beds
        ]
        options += [
            SelectOptionDict(
                value=f"{CONFIGURED_RETRY_PREFIX}{address}",
                label=self._format_retrying_option_label(
                    address, entry, info, suffix=retrying_suffix
                ),
            )
            for address, (entry, info) in sorted_retrying_devices
        ]
        options += [
            SelectOptionDict(value=key, label=key)
            for key in ("select_by_app", "scan", "manual", "diagnostic")
        ]
        if len(self._pairable_single_entries()) >= 2:
            options.append(SelectOptionDict(value="pair_beds", label="pair_beds"))

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            translation_key="setup_start",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors={"base": self._scan_error} if self._scan_error else {},
        )

    async def async_step_select_app(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which app or remote controls the bed, from the bed-type list itself.

        A row picked here is the bed-type row the later form shows, so an app's
        row answers its family question and a family row still asks it.
        """
        not_listed = await self._get_config_translation(
            "step.select_app.data.not_listed", "My app isn't listed, or I don't know"
        )
        # A device picked first suggests its confidently detected route, and its
        # family row keeps that route, as the generic form's list does.
        detected = (
            _confident_auto_detect(detect_bed_type_detailed(self._discovery_info))
            if self._app_after_device == "device" and self._discovery_info is not None
            else None
        )
        rows = _bed_type_selector(detected).rows()
        picker = _SearchableSelect(
            [
                *(SelectOptionDict(value=choice, label=label) for label, choice in rows.items()),
                SelectOptionDict(value=_APP_NOT_LISTED, label=not_listed),
            ]
        )
        if user_input is not None:
            choice = picker(user_input[CONF_BED_TYPE])
            if choice == _APP_NOT_LISTED:
                return await self.async_step_select_family()
            bed_type, variant = resolve_bed_type_choice(choice)
            self._selected_bed_type = bed_type
            self._selected_protocol_variant = variant
            return await self._async_after_app_choice()
        marker = (
            vol.Required(CONF_BED_TYPE, default=picker.shown(detected))
            if detected is not None
            else vol.Required(CONF_BED_TYPE)
        )
        return self.async_show_form(
            step_id="select_app",
            data_schema=vol.Schema({marker: picker}),
        )

    async def _async_after_app_choice(self) -> ConfigFlowResult:
        """Continue with the device, or with the device already picked first."""
        step, self._app_after_device = self._app_after_device, None
        if step == "device":
            assert self._selected_bed_type is not None
            return await self._async_start_new_bed(
                self._selected_bed_type, self._selected_protocol_variant
            )
        if step == "manual_entry":
            return await self.async_step_manual_entry()
        return await self.async_step_manual()

    async def async_step_scan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Run an explicit discovery sweep behind the existing progress view."""

        async def scan() -> OperationResult:
            try:
                await bluetooth.async_request_active_scan(self.hass)
            except Exception:
                _LOGGER.debug("Active Bluetooth scan unavailable", exc_info=True)
                self._scan_error = "scan_failed"
                return OperationResult(outcome=OperationOutcome.CONNECTION_FAILED)
            return OperationResult(outcome=OperationOutcome.SUCCESS)

        return await self.async_run_operation_step(
            step_id="scan",
            worker=scan,
            next_step_id="scan_result",
        )

    async def async_step_scan_result(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Refresh selection without replaying the input that started the scan."""
        return await self.async_step_user()

    def _pairable_single_entries(self) -> list[ConfigEntry]:
        """Configured single-bed entries that could be combined into a pair.

        Excludes any standalone entry whose MAC is already a member of an
        existing pair (a stale/imported duplicate) — combining it again would
        create a second pair sharing the same child {address}_{key} unique IDs.
        """
        # Only fully-loaded beds are returned: a bed still in SETUP_RETRY or
        # failed initial setup has not registered its entities yet, so later
        # compatibility checks cannot safely inspect its capabilities.
        return active_pairing_candidates(self.hass)

    async def async_step_pair_beds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Combine two existing single-bed entries into one paired (Dual Bed) device.

        Conversion is ADDITIVE: one paired entry is created and the two originals
        are absorbed. Per-side entities keep their {address}_{key} unique_ids and
        their device keeps its (DOMAIN, MAC) identifier, so the pair's setup
        re-homes each original's registry rows in place (history/customizations
        preserved) and only then removes the original entry. The originals stay
        loaded and controllable until that handoff, so a failed pair setup never
        leaves the user without a bed.
        """
        entries = self._pairable_single_entries()
        if len(entries) < 2:
            return self.async_abort(reason="not_enough_beds")

        by_id = {entry.entry_id: entry for entry in entries}
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_ids = selected_pair_ids(user_input)
            left = by_id.get(selected_ids[0]) if selected_ids is not None else None
            right = by_id.get(selected_ids[1]) if selected_ids is not None else None
            left_layout = await self._pair_layout_snapshot(left) if left is not None else None
            right_layout = await self._pair_layout_snapshot(right) if right is not None else None
            if left is None or right is None:
                errors["base"] = "unknown"
            elif left.entry_id == right.entry_id:
                errors[CONF_PAIR_SELECTION] = "same_device"
            elif (left.data.get(CONF_ADDRESS) or "").upper() == (
                right.data.get(CONF_ADDRESS) or ""
            ).upper():
                # Two distinct entries for the same MAC would build children with
                # identical addresses and so collide on {address}_{key} unique IDs.
                errors[CONF_PAIR_SELECTION] = "same_address"
            elif self._offline_safe_bed_type(left) != self._offline_safe_bed_type(right):
                # Compare RESOLVED bed types: two legacy leggett_platt entries with
                # DIFFERENT explicit variants (gen2 vs mlrm) are different concrete
                # protocols, so they're an incompatible pair even though their raw
                # umbrella type matches — and would otherwise be stored as mismatched
                # concrete child types by _resolved_pair_side_data below.
                errors["base"] = "mismatched_bed_types"
            elif self._offline_safe_bed_type(left) == BED_TYPE_VMATBASIC and any(
                entry.data.get(CONF_VMATBASIC_PROFILE) not in {"cbi", "xtbox"}
                for entry in (left, right)
            ):
                errors["base"] = "vmatbasic_link_profile"
            elif self._offline_safe_bed_type(left) == BED_TYPE_OCTO and (
                self._is_octo_one_motor_lift(left) or self._is_octo_one_motor_lift(right)
            ):
                # One-motor Standard OCTO entries are standalone TV/bed lifts,
                # not bed sides. Reject even two matching lifts so the generic
                # layout-equality gate cannot turn them into a paired bed.
                errors["base"] = "octo_tv_lift_pairing_unsupported"
            elif self._offline_safe_bed_type(left) == BED_TYPE_OCTO and (
                (not self._is_octo_star2(left) and self._octo_capability_snapshot(left) is None)
                or (
                    not self._is_octo_star2(right) and self._octo_capability_snapshot(right) is None
                )
            ):
                # An OFFLINE Standard Octo side mints its light/RGBW/memory/synchro
                # entities from a capability snapshot captured here from the live bed
                # — so each STANDARD Octo bed must be connected at pairing for its
                # snapshot to exist. Star2 has fixed caps and needs no snapshot.
                errors["base"] = "octo_pairing_needs_connection"
            elif left_layout is None or right_layout is None:
                errors["base"] = "pairing_needs_capabilities"
            elif left_layout != right_layout:
                errors["base"] = "mismatched_motor_layouts"
            else:
                name = user_input.get(CONF_NAME) or f"{left.title} + {right.title}"
                # Merge each side's options (e.g. customized angle limits, which the
                # coordinator reads before data) into its descriptor so they aren't
                # lost when the original is absorbed. Each side's (entry_id,
                # unique_id) is recorded as provenance so the pair's setup can find
                # and re-home the original entry's registry rows in place.
                pair_data = build_pair_entry_data(
                    self._resolved_pair_side_data(left),
                    self._resolved_pair_side_data(right),
                    name=name,
                    left_octo_snapshot=self._octo_capability_snapshot(left),
                    right_octo_snapshot=self._octo_capability_snapshot(right),
                    left_layout_snapshot=left_layout,
                    right_layout_snapshot=right_layout,
                    left_origin=(left.entry_id, left.unique_id),
                    right_origin=(right.entry_id, right.unique_id),
                    left_origin_title=left.title,
                    right_origin_title=right.title,
                    left_origin_source=left.source,
                    right_origin_source=right.source,
                    left_origin_data=left.data,
                    right_origin_data=right.data,
                    left_origin_options=left.options,
                    right_origin_options=right.options,
                )
                await self.async_set_unique_id(pair_data[CONF_PAIR_ID])
                self._abort_if_unique_id_configured()
                # Do NOT remove the originals here. They stay loaded (so the user
                # keeps two working beds) until the pair entry's setup re-homes
                # their entity/device registry rows onto the pair and removes them
                # — a history-preserving handoff. Removing them now (the old path)
                # tore down their registry rows and let the paired platforms
                # recreate fresh ones, resetting per-side history/customizations.
                # The pair's unique_id (pair_<hash>) never collides with the
                # originals' MAC unique_ids, so create can proceed while they live.
                # See _async_rehome_absorbed_singles in __init__.py.
                _LOGGER.info(
                    "Combining %s + %s into paired bed %s (originals re-homed at setup)",
                    left.title,
                    right.title,
                    name,
                )
                return self.async_create_entry(title=name, data=pair_data)

        return self.async_show_form(
            step_id="pair_beds",
            data_schema=build_pair_selection_schema(entries),
            errors=errors,
        )

    async def async_step_select_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which brand is on the bed, when the app is not listed or not known.

        Each row is a bed-type list row: a family row names its apps and asks
        the family's question, and a brand without one names its own app or bed.
        """
        not_sure = await self._get_config_translation(
            "step.select_family.data.not_sure",
            "Not sure: run diagnostics or browse unsupported devices",
        )
        # A device picked first keeps its confidently detected route.
        detected = (
            _confident_auto_detect(detect_bed_type_detailed(self._discovery_info))
            if self._app_after_device == "device" and self._discovery_info is not None
            else None
        )
        picker = _SearchableSelect(
            [
                *(
                    SelectOptionDict(value=choice, label=label)
                    for choice, label in _family_rows(detected)
                ),
                SelectOptionDict(value=_FAMILY_NOT_SURE, label=not_sure),
            ]
        )
        if user_input is not None:
            choice = picker(user_input[CONF_BED_TYPE])
            if choice == _FAMILY_NOT_SURE:
                self._app_after_device = None
                return await self.async_step_diagnostic()
            bed_type, variant = resolve_bed_type_choice(choice)
            self._selected_bed_type = bed_type
            self._selected_protocol_variant = variant
            return await self._async_after_app_choice()
        return self.async_show_form(
            step_id="select_family",
            data_schema=vol.Schema({vol.Required(CONF_BED_TYPE): picker}),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle manual bed selection - show all BLE devices.

        Lists ALL visible BLE devices (not just recognized beds) so users can
        select from available devices or enter an address manually.
        """
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address.startswith(CONFIGURED_RETRY_PREFIX):
                return self._async_abort_retrying_entry(
                    address.removeprefix(CONFIGURED_RETRY_PREFIX)
                )
            if address == "manual_entry":
                _LOGGER.debug("User selected manual address entry")
                if self._selected_bed_type is None:
                    self._app_after_device = "manual_entry"
                    return await self.async_step_select_app()
                return await self.async_step_manual_entry()

            _LOGGER.info("User selected device for manual setup: %s", address)
            # Normalize address to uppercase to match Bluetooth discovery
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()
            if self._is_absorbed_pair_member(address):
                return self.async_abort(reason="already_configured")

            self._discovery_info = self._all_ble_devices[address]
            self._set_device_title_placeholders(
                self._discovery_info.name, self._discovery_info.address
            )
            self._new_bed_origin = "picked"
            source = getattr(self._discovery_info, "source", None) or ADAPTER_AUTO
            self._device_adapter = str(source)
            if self._selected_bed_type is None:
                # Pick any Bluetooth device: the app question follows the device.
                self._app_after_device = "device"
                return await self.async_step_select_app()
            return await self._async_start_new_bed(
                self._selected_bed_type, self._selected_protocol_variant
            )

        # Get ALL BLE devices (not just beds)
        _LOGGER.debug("Scanning for ALL BLE devices for manual selection...")

        all_discovered = get_discovered_service_info(
            self.hass,
            include_non_connectable=True,
        )
        _LOGGER.debug(
            "Total BLE devices visible for manual selection: %d",
            len(all_discovered),
        )

        configured_entries = self._configured_entries_by_address()
        self._all_ble_devices = {}
        self._retrying_devices.clear()
        for discovery_info in all_discovered:
            normalized_address = discovery_info.address.upper()
            configured_entry = configured_entries.get(normalized_address)
            if configured_entry is not None:
                if configured_entry.state == ConfigEntryState.SETUP_RETRY:
                    self._retrying_devices[normalized_address] = (configured_entry, discovery_info)
                continue

            self._all_ble_devices[discovery_info.address] = discovery_info

        _LOGGER.info(
            "Manual selection: found %d unconfigured BLE devices",
            len(self._all_ble_devices),
        )

        if not self._all_ble_devices and not self._retrying_devices:
            _LOGGER.info("No BLE devices found in either scanner view, showing manual entry form")
            if self._selected_bed_type is None:
                # Nothing to pick, so the address is typed after the app question.
                self._app_after_device = "manual_entry"
                return await self.async_step_select_app()
            return await self.async_step_manual_entry()

        # Sort devices: named devices first (alphabetically), then MAC-only/unnamed
        sorted_devices = sorted(
            self._all_ble_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        sorted_retrying_devices = sorted(
            self._retrying_devices.items(),
            key=lambda item: (
                is_mac_like_name(self._retrying_display_name(item[1][0], item[1][1])),
                self._retrying_display_name(item[1][0], item[1][1]).lower(),
            ),
        )
        retrying_suffix = await self._get_retrying_option_suffix()
        devices = {}
        for address, info in sorted_devices:
            label = f"{info.name or 'Unknown'} ({address})"
            if getattr(info, "connectable", True) is False:
                label += " [scanner says non-connectable]"
            devices[address] = label
        for address, (entry, info) in sorted_retrying_devices:
            devices[f"{CONFIGURED_RETRY_PREFIX}{address}"] = self._format_retrying_option_label(
                address,
                entry,
                info,
                suffix=retrying_suffix,
            )
        devices["manual_entry"] = "Enter address manually"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )

    async def async_step_manual_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the address of a bed that is not in range, once its app is chosen."""
        if self._selected_bed_type is None:
            self._app_after_device = "manual_entry"
            return await self.async_step_select_app()
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                retrying_entry = self._configured_entries_by_address().get(address)
                if (
                    retrying_entry is not None
                    and retrying_entry.state == ConfigEntryState.SETUP_RETRY
                ):
                    self._retrying_devices[address] = (retrying_entry, None)
                    return self._async_abort_retrying_entry(address)
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                if self._is_absorbed_pair_member(address):
                    return self.async_abort(reason="already_configured")
                self._set_device_title_placeholders(None, address)
                self._discovery_info = None
                self._typed_address = address
                self._new_bed_origin = "typed"
                self._device_adapter = ADAPTER_AUTO
                return await self._async_start_new_bed(
                    self._selected_bed_type, self._selected_protocol_variant
                )
        return self.async_show_form(
            step_id="manual_entry",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )

    async def _async_pairing_step(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        *,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Offer the pairing actions that actually apply to this bed's state.

        The old form offered "Pair Now" and "Skip (already paired)". Skip was
        ambiguous in both directions: it asserted a bond nothing had checked
        for, and it gave no way to replace one that had gone stale. The choices
        here are computed from what the host's BlueZ actually reports and from
        which transport would own the bond (issue #461).
        """
        assert self._manual_data is not None
        if (
            self._migration is not None
            and user_input is None
            and self._migration.is_unchanged_by(self._manual_data)
        ):
            # A label that resolves to the saved route never migrates anything.
            return self.async_abort(reason="migration_unchanged")
        address = self._manual_data.get(CONF_ADDRESS, "")
        bed_type = self._manual_data.get(CONF_BED_TYPE)
        variant = self._manual_data.get(CONF_PROTOCOL_VARIANT)

        errors = dict(errors or {})
        inventory = await async_read_local_bonds(address)
        prediction = async_predict_path(
            self.hass, address, self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        )
        existing = inventory.sole_bond
        # A proxy keeps its own bond store that the host cannot read. A proxy
        # winning the prediction does not, however, erase a visible host route
        # whose exact bond can be checked by connecting through that source.
        chosen_over_proxy = (
            prediction.chosen is not None and prediction.chosen.transport is TransportClass.PROXY
        )
        # "Not a proxy" is not the same as "provably the host". An unknown or
        # absent path cannot show that the bond BlueZ is holding is the one this
        # bed will actually use, so it is not offered as usable.
        proven_local = (
            prediction.chosen is not None and prediction.chosen.transport is TransportClass.LOCAL
        )
        # A bond belongs to one adapter, so the only usable one is the bond the
        # chosen route itself holds. On a multi-adapter host, hci0's bond says
        # nothing about a connection going out over hci1.
        existing_selection = (
            select_local_bond(
                inventory,
                owner_source=prediction.chosen.source,
                owner_adapter=prediction.chosen.adapter,
            )
            if proven_local and prediction.chosen is not None
            else None
        )
        chosen_uses_existing = (
            existing is not None
            and not chosen_over_proxy
            and existing_selection is not None
            and existing_selection.is_exact
            and existing_selection.record == existing
        )
        matching_local_route = (
            _matching_local_bond_route(prediction, inventory, existing)
            if existing is not None
            else None
        )
        # Replacement is the destructive action, and it is only meaningful when
        # a pairing attempt follows it. A bed that grants one connection per
        # pairing window defers bonding to its first connection, so replacing
        # here would remove a bond and pair nothing.
        defers_pairing = grants_one_connection_per_pairing_window(bed_type or "", variant)
        can_replace_existing = chosen_uses_existing and not defers_pairing
        # Certifying means persisting the bond marker without connecting, so it
        # rests entirely on the predicted route, and a prediction is advisory by
        # design. It is only honest when no other route could win and turn the
        # assertion false.
        can_certify_existing = existing is not None and _every_route_holds_bond(
            prediction, inventory, existing
        )
        # Verifying does not need that guarantee: it connects and records the
        # route it actually took, so a wrong prediction shows up as a failed
        # check rather than a false marker. A bed granting one connection per
        # pairing window cannot verify at all, though - spending the window is
        # the one thing this action exists to avoid - so for it the action would
        # be exactly the assertion above, and it is offered only when certain.
        can_offer_existing = existing is not None and (
            (not defers_pairing and matching_local_route is not None) or can_certify_existing
        )

        if user_input is not None:
            action = user_input.get("action")
            # Recorded for every action, so Retry returns to the form the user
            # actually came from rather than the discovery one.
            self._pairing_origin_step = step_id
            if action == "use_existing_bond" and can_offer_existing:
                # BlueZ saying "paired" is not the same as the bed accepting an
                # authenticated write, and a stale record looks identical to a
                # good one. Prove it over the air before claiming it is usable
                # (issue #461).
                self._pairing_mode = "verify_existing"
                # Only a bed that cannot be verified falls back to asserting the
                # record, and it may do so only over a certain route.
                self._pairing_route_certain = can_certify_existing
                self._pairing_remove_record = None
                # Verify on the adapter that holds the bond, not on whichever
                # one happens to have the strongest signal. BlueZ does not
                # always publish an adapter address; the route was matched to
                # this record above, so its source names the same adapter.
                self._pairing_verify_source = (existing.adapter_address if existing else None) or (
                    matching_local_route.source if matching_local_route is not None else None
                )
                self._pairing_verify_record = existing
                return await self._async_start_pairing_operation(address, prediction)
            if action == "remove_bond_and_pair" and can_replace_existing and existing is not None:
                # Destroying a bond gets its own confirmation naming the exact
                # record, rather than happening as a side effect of picking an
                # option from a list.
                self._pairing_remove_record = existing
                return await self.async_step_pairing_replace_confirm()
            if action in ("pair_now", "retry"):
                self._pairing_mode = "new"
                self._pairing_remove_record = None
                self._pairing_verify_source = None
                self._pairing_verify_record = None
                self._pairing_route_certain = False
                return await self._async_start_pairing_operation(address, prediction)

        options = ["pair_now"]
        if can_offer_existing:
            options.append("use_existing_bond")
        if can_replace_existing:
            options.append("remove_bond_and_pair")
        default_action = "use_existing_bond" if can_offer_existing else "pair_now"

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required("action", default=default_action): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                            translation_key="pairing_action",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "name": self._manual_data.get(CONF_NAME, "Unknown"),
                "pairing_instructions": await self._get_pairing_instructions(bed_type, variant),
                "transport": await self._async_transport_note(
                    address,
                    self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
                    bed_type,
                    variant,
                ),
                "bond_state": await self._async_bond_state_note(
                    inventory,
                    chosen_over_proxy and matching_local_route is None,
                    matching_local_route is not None,
                    route_uncertain=(matching_local_route is not None and not can_offer_existing),
                ),
            },
        )

    async def _async_bond_state_note(
        self,
        inventory: LocalBondInventory,
        over_proxy: bool,
        can_use_existing: bool,
        *,
        route_uncertain: bool = False,
    ) -> str:
        """Say what is already known about this bed's bond, if anything.

        Looked up rather than written inline: this is the central status on an
        otherwise translated form, and building it in Python left Norwegian
        users reading English exactly where it mattered most.
        """
        if over_proxy:
            key = "bond_state_proxy"
        elif not inventory.readable:
            key = "bond_state_unreadable"
        elif len(inventory.bonded_records) > 1:
            key = "bond_state_multiple"
        elif route_uncertain:
            # The bond is identified and sits on a route that could be used; it
            # just is not the only route, so it cannot be asserted up front.
            # Checked before the plain "there is a bond" note, because both are
            # true here and only this one says why the action is missing.
            key = "bond_state_route_uncertain"
        elif can_use_existing:
            key = "bond_state_existing"
        elif inventory.bonded_records:
            # A bond exists, just not one this route can use. Saying "no bond"
            # would be false, and it invites pairing again alongside a bond that
            # is sitting right there.
            key = "bond_state_mismatched"
        else:
            key = "bond_state_none"
        return await self._get_config_translation(
            f"step.bluetooth_pairing.data_description.{key}", _BOND_STATE_FALLBACKS[key]
        )

    async def async_step_bluetooth_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth pairing for beds that require it."""
        return await self._async_pairing_step("bluetooth_pairing", user_input)

    async def async_step_manual_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth pairing for manually selected beds that require it."""
        return await self._async_pairing_step("manual_pairing", user_input)

    async def _async_start_pairing_operation(
        self, address: str, prediction: PathPrediction
    ) -> ConfigFlowResult:
        """Begin a pairing operation, unless this bed must not spend a link."""
        assert self._manual_data is not None
        if self._pairing_mode == "verify_existing" and self._pairing_verify_record is not None:
            # A bed that grants one connection per pairing window must not spend
            # it proving a bond BlueZ already reports. Deferring without the
            # markers would be worse than not offering the action at all: the
            # coordinator would ask to pair on the one connection it gets, which
            # is exactly what picking "use the existing bond" was avoiding.
            #
            # That reasoning only holds while the route is certain. Asserting a
            # bond that the transport actually chosen does not hold suppresses
            # pair=True on a link that is not authenticated, and this is the one
            # bed that cannot spend another connection recovering from it. When
            # the route is in doubt, fall through and let the coordinator pair
            # on its first connection instead: requesting a bond that already
            # exists costs nothing, and skipping one that does not costs the bed.
            if grants_one_connection_per_pairing_window(
                self._manual_data.get(CONF_BED_TYPE) or "",
                self._manual_data.get(CONF_PROTOCOL_VARIANT),
            ):
                if self._pairing_route_certain:
                    return self._create_entry_for_existing_bond(self._pairing_verify_record)
                _LOGGER.info(
                    "Not certifying the existing bond for %s: more than one route could "
                    "take the connection, so the first coordinator connection will pair",
                    self._manual_data.get(CONF_ADDRESS),
                )
        deferred = self._async_deferred_pairing_entry()
        if deferred is not None:
            return deferred
        name = self._manual_data.get(CONF_NAME) or address
        self._pairing_result_shown = False
        self.async_begin_operation(
            name=name,
            address=address,
            prediction=prediction,
            action=SetupAction.LOCATING,
            policy=ConnectionLifetimePolicy.ORDINARY,
            placeholders={"name": name, "address": address},
        )
        return await self.async_step_pairing_progress()

    async def async_step_pairing_replace_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm replacing an existing bond before anything is destroyed.

        #461 requires the replace action to route through confirmation. Naming
        the exact adapter matters: on a host with more than one, "remove the
        bond" is ambiguous until it says which.
        """
        assert self._manual_data is not None
        record = self._pairing_remove_record
        if record is None:
            return await self._async_pairing_step(
                self._pairing_origin_step or "bluetooth_pairing", None
            )

        if user_input is not None:
            address = self._manual_data.get(CONF_ADDRESS, "")
            current = await async_read_local_bonds(address)
            current_record = current.sole_bond
            if current_record is None or not current_record.is_same_bond_as(record):
                # The confirmation named one exact BlueZ record. If it changed
                # while the dialog was open, never apply that stale approval to
                # whatever now occupies the same deterministic object path.
                # Identity, not equality: a bed that merely reconnects flips
                # ``connected``/``trusted`` and is still the approved bond.
                self._pairing_remove_record = None
                return await self._async_pairing_step(
                    self._pairing_origin_step or "bluetooth_pairing", None
                )
            self._pairing_mode = "replace_local"
            # A previous proxy retry must not route the replacement away from
            # the host bond the user just approved removing.
            self._pairing_retry_source = None
            self._pairing_origin_step = self._pairing_origin_step or "bluetooth_pairing"
            return await self._async_start_pairing_operation(
                address,
                async_predict_path(
                    self.hass,
                    address,
                    self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
                ),
            )

        return self.async_show_form(
            step_id="pairing_replace_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._manual_data.get(CONF_NAME, "Unknown"),
                "transport": record.adapter_address or record.adapter_path,
            },
        )

    def _async_deferred_pairing_entry(self) -> ConfigFlowResult | None:
        """Create the entry now for beds that must not spend a connection.

        LP Comfort Connect grants roughly one usable BLE connection per power
        cycle. Pairing here would open, bond and then close the connection the
        box will not grant again, leaving ``async_setup_entry`` with nothing to
        connect to (issue #385). Let the coordinator's first connection do
        connect -> discover -> bond -> stay connected instead.

        Checked before any operation starts, so ``KEEP_FIRST_LINK`` is enforced
        ahead of anything that could open a link rather than inside it.
        """
        assert self._manual_data is not None
        if not grants_one_connection_per_pairing_window(
            self._manual_data.get(CONF_BED_TYPE) or "",
            self._manual_data.get(CONF_PROTOCOL_VARIANT),
        ):
            return None
        _LOGGER.info(
            "Deferring the BLE bond for %s to the first coordinator connection: "
            "this bed grants one connection per pairing window",
            self._manual_data.get(CONF_ADDRESS),
        )
        return self.async_create_entry(
            title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            data=self._manual_data,
        )

    async def _async_pairing_worker(self) -> OperationResult:
        if self._migration is None:
            return await self._async_pairing_worker_reserved()
        assert self._manual_data is not None
        self._migration_endpoints_checked = False
        async with self._migration_transport_operation():
            result = await self._async_pairing_worker_reserved()
        self._migration_verified = (
            result.succeeded
            and self._migration_endpoints_checked
            and async_get_connect_lock(
                self.hass, self._manual_data[CONF_ADDRESS]
            ).retained_setup_client
            is None
        )
        if result.succeeded and not self._migration_verified:
            return OperationResult(outcome=OperationOutcome.CONNECTION_FAILED)
        return result

    async def _async_pairing_worker_reserved(self) -> OperationResult:
        """Run the pairing operation the user chose, and verify the result.

        Three modes share this worker because they share almost everything: the
        freshness gate, the connect, the strict verification and the cleanup.
        They differ only in whether a bond is removed first and whether one is
        requested at all.

        Returns a typed outcome rather than a bare bool so the result step can
        give advice that fits what actually happened. A bed that never answered
        a scan and a bed whose link stayed unauthenticated need different advice,
        and #461 forbids presenting the first as a pairing failure.
        """
        assert self._manual_data is not None
        address = self._manual_data.get(CONF_ADDRESS)
        mode = self._pairing_mode

        if mode == "replace_local" and self._pairing_remove_record is not None:
            # Prove the bed is reachable *before* destroying its bond. Removing
            # first would leave a sleeping bed with no bond and no way to make a
            # new one until someone walks over to it.
            self.async_report_action(SetupAction.LOCATING)
            preferred_adapter = self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
            source = (
                preferred_adapter
                if preferred_adapter and preferred_adapter != ADAPTER_AUTO
                else None
            )
            evidence, _device = await async_wait_for_advertisement(
                self.hass,
                address or "",
                source=source,
                wait_timeout=ADVERTISEMENT_WAIT_SECONDS,
                on_progress=self.async_report_progress,
            )
            if not evidence.is_fresh or _device is None:
                # A current advertisement does not guarantee a usable BLEDevice:
                # resolution can fail during scanner churn. Removing the bond on
                # that basis would leave the bed unbonded and unreachable.
                _LOGGER.info(
                    "Not replacing the bond for %s: the bed is not reachable (%s)",
                    address,
                    evidence.status,
                )
                return OperationResult(
                    outcome=OperationOutcome.NOT_ADVERTISING,
                    detail=(
                        str(evidence.status) if not evidence.is_fresh else "device_not_resolved"
                    ),
                )

            # From here the bed's bond is about to stop existing, so removal and
            # its replacement become one unit that a cancelled flow cannot cut in
            # half. Closing the progress dialog between RemoveDevice and the new
            # bond would otherwise leave the bed unpaired and unusable until
            # someone ran setup again.
            record = self._pairing_remove_record
            self._pairing_remove_record = None
            task = self.hass.async_create_task(
                self._async_replace_bond(address, record, _device),
                "adjustable_bed_bond_replacement",
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # The shielded task keeps running to completion; make sure its
                # outcome is consumed so it cannot surface later as a
                # never-retrieved exception.
                task.add_done_callback(_log_detached_replacement)
                raise

        return await self._async_pair_and_classify(address, mode)

    async def _async_replace_bond(
        self,
        address: str | None,
        record: LocalBondRecord,
        device: BLEDevice | None = None,
    ) -> OperationResult:
        """Remove one host bond and immediately pair a replacement.

        Run as a shielded unit (see ``_async_pairing_worker``): between the
        removal and the new bond the bed has no bond at all, and that window must
        not be left open by a flow the user walked away from.

        ``device`` is the one the reachability gate already resolved. Resolving
        again after the removal would let a moment of scanner churn return None
        and abort the transaction with the old bond gone and no replacement.
        """
        if not address:
            return OperationResult(
                outcome=OperationOutcome.CONNECTION_FAILED,
                detail="missing_address",
            )
        async with async_get_connect_lock(self.hass, address):
            current = await async_read_local_bonds(address)
            # Three different things can make this re-read disagree with the
            # confirmation, and only one of them is "the bond is still there".
            if not current.readable:
                # A failed or timed-out read proves nothing either way. Nothing
                # was removed, so say the state could not be confirmed rather
                # than assert the old bond survived.
                _LOGGER.warning(
                    "Not replacing the bond for %s: the host's bonds could not be read (%s)",
                    address,
                    current.status,
                )
                return OperationResult(
                    outcome=OperationOutcome.UNPAIR_UNCONFIRMED,
                    detail="bond_unreadable_before_removal",
                )
            current_record = current.sole_bond
            # Identity, not equality: ``connected``/``trusted`` change on their
            # own between the confirmation and this worker, and a bed that just
            # reconnected is still the bond the user approved removing.
            if current_record is None or not current_record.is_same_bond_as(record):
                if current.bonded_records:
                    _LOGGER.warning(
                        "Not replacing the bond for %s: the confirmed BlueZ record changed",
                        address,
                    )
                    return OperationResult(
                        outcome=OperationOutcome.UNPAIR_FAILED,
                        detail="bond_changed_before_removal",
                    )
                # Readable and empty: something else already removed the bond,
                # so the destructive half of this transaction has nothing left to
                # do. Refusing here would deny the pairing the user asked for
                # over a record that is already gone.
                _LOGGER.info(
                    "The bond for %s was already gone; pairing without removing anything",
                    address,
                )
                return await self._async_pair_and_classify(address, "replace_local", device)
            self.async_report_action(SetupAction.UNPAIRING)
            removal = await async_remove_local_bond(record)
            if not removal.succeeded:
                _LOGGER.warning(
                    "Not pairing %s: the existing bond could not be removed (%s)",
                    address,
                    removal.error,
                )
                return OperationResult(
                    outcome=(
                        OperationOutcome.UNPAIR_UNCONFIRMED
                        if removal.is_unconfirmed
                        else OperationOutcome.UNPAIR_FAILED
                    ),
                    detail=removal.error or str(removal.status),
                )
            # _attempt_pairing() re-enters this task-owned address lock, keeping
            # every other connector out from before removal through disconnect.
            return await self._async_pair_and_classify(address, "replace_local", device)

    async def _async_pair_and_classify(
        self, address: str | None, mode: str, device: BLEDevice | None = None
    ) -> OperationResult:
        """Connect, bond if asked, verify, and turn all of it into one outcome."""
        try:
            evidence = await self._attempt_pairing(
                address,
                request_bond=mode != "verify_existing",
                track_for_flow_cleanup=mode != "replace_local",
                device=device,
            )
        except BondRouteMismatchError as err:
            _LOGGER.info("Pairing route mismatch for %s: %s", address, err)
            return OperationResult(
                outcome=(
                    OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE
                    if mode == "verify_existing"
                    else OperationOutcome.ROUTE_MISMATCH
                ),
                detail=str(err),
            )
        except NotAdvertisingError as err:
            _LOGGER.info("Not pairing %s: %s", address, err.status)
            return OperationResult(outcome=OperationOutcome.NOT_ADVERTISING, detail=str(err.status))
        except (NotImplementedError, TypeError) as err:
            # NotImplementedError: ESPHome < 2024.3.0 doesn't support pairing
            # TypeError: older bleak-retry-connector doesn't have pair kwarg
            _LOGGER.warning("Pairing not supported: %s", err)
            return OperationResult(
                outcome=OperationOutcome.PAIRING_NOT_SUPPORTED,
                detail=str(err) or err.__class__.__name__,
            )
        except Exception as err:  # noqa: BLE001 - classified below
            _LOGGER.warning("Pairing failed for %s: %s", address, err)
            return OperationResult(
                outcome=_classify_connection_failure(err),
                detail=str(err) or err.__class__.__name__,
            )

        if (
            evidence.status is BondVerificationStatus.AUTH_FAILED
            or evidence.proves_native_bond_absent
        ):
            # Authentication failure or exact host absence contradicts a
            # successful bond, even when the pairing RPC returned normally.
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_FAILED,
                detail=evidence.error,
                payload=evidence,
            )
        if mode == "verify_existing" and not evidence.proves_bond:
            # The whole point of this mode is proof, so this is not a success.
            # But an inconclusive read proves nothing either way, and telling the
            # user their link is unauthenticated would push them into replacing a
            # bond that may be working perfectly.
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE,
                detail=str(evidence.status),
                payload=evidence,
            )
        return OperationResult(outcome=OperationOutcome.SUCCESS, payload=evidence)

    async def async_step_pairing_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair behind a live progress view instead of freezing the form.

        Pairing is the slowest thing setup does - it waits for the bed to
        advertise, connects, bonds and then verifies - so it is exactly the
        operation #457 means when it says no attempt may leave the previous form
        apparently frozen.
        """
        assert self._manual_data is not None
        return await self.async_run_operation_step(
            # A guided change shows its own checklist: nothing is saved yet.
            step_id="migration_pairing" if self._migration is not None else "pairing_progress",
            worker=self._async_pairing_worker,
            next_step_id="pairing_result",
            description_placeholders=self._migration_check_placeholders(self._manual_data),
        )

    async def async_step_migration_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair and check a guided change's staged route behind its checklist."""
        return await self.async_step_pairing_progress(user_input)

    async def async_step_pairing_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Acknowledge what pairing achieved, and let the user act on it.

        Like ``verify_connection``, this accepts input only once it has rendered
        its own form: the flow manager replays the caller's original input
        through its progress-done loop, and that must never be read as
        confirmation of a result the user has not seen.
        """
        assert self._manual_data is not None
        result = self.operation.result
        if (
            self._migration is not None
            and self._pairing_result_shown
            and (user_input or {}).get("action") == "keep"
        ):
            return await self.async_step_migration_keep()
        evidence = result.payload if result is not None else None
        succeeded = result is not None and result.succeeded
        native_bond_required = self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
        native_bond_verified = isinstance(evidence, BondEvidence) and evidence.proves_bond
        if native_bond_required:
            succeeded = succeeded and native_bond_verified
            if user_input is not None and user_input.get("action") != "retry" and not succeeded:
                user_input = None
        if self._migration is not None:
            succeeded = succeeded and self._migration_verified
            if user_input is not None and user_input.get("action") != "retry" and not succeeded:
                user_input = None

        if user_input is not None and self._pairing_result_shown:
            if user_input.get("action") == "retry":
                if (
                    isinstance(evidence, BondEvidence)
                    and evidence.status is BondVerificationStatus.AUTH_FAILED
                    and evidence.owner.transport is TransportClass.PROXY
                ):
                    self._pairing_retry_source = evidence.owner.source
                self._pairing_result_shown = False
                return await self._async_pairing_step(
                    self._pairing_origin_step or "bluetooth_pairing", None
                )
            entry_data = dict(self._manual_data)
            if isinstance(evidence, BondEvidence) and evidence.proves_bond:
                # A positively verified bond writes the marker *and* records
                # which transport owns it, so a later bond removal knows where
                # to look.
                entry_data = self._mark_ble_bond_established(entry_data)
                entry_data[CONF_BLE_BOND_CONTEXT] = build_bond_context(evidence)
                entry_data.pop(CONF_BLE_BOND_ATTEMPTED_SOURCE, None)
            elif succeeded and self._pairing_mode != "verify_existing":
                # A bond was asked for and nothing contradicted it, but this
                # protocol has no authentication-gated read to prove it with.
                # Record that pairing happened, without provenance: the marker
                # keeps the coordinator from immediately re-pairing a bed that
                # just paired, which over a proxy can return auth error 82 and
                # wedge the connection, while the missing context means this
                # cannot later authorize removing a host bond.
                #
                # The marker is scoped to the route that made the attempt. It is
                # only credible there: automatic routing can put the first real
                # connection on another adapter or proxy that was never bonded,
                # and an unscoped marker would suppress pair=True on that link
                # and turn a good setup into an authentication failure. Without
                # a known route there is nothing to scope it to, so nothing is
                # recorded and the bed simply pairs again on first connect.
                attempted_source = (
                    evidence.owner.source if isinstance(evidence, BondEvidence) else None
                )
                if attempted_source:
                    entry_data = self._mark_ble_bond_established(entry_data)
                    entry_data[CONF_BLE_BOND_ATTEMPTED_SOURCE] = attempted_source
                entry_data.pop(CONF_BLE_BOND_CONTEXT, None)
            return await self._async_create_selected_app_entry(
                title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                data=entry_data,
            )

        self._pairing_result_shown = True
        if self._migration is not None and not succeeded:
            return await self._async_show_migration_failure(
                "pairing_result",
                await self._async_pairing_outcome_note(result, evidence),
                {"base": "vmat_bond_required"}
                if native_bond_required and not native_bond_verified
                else None,
            )
        schema: dict[vol.Marker, Any] = {}
        if not succeeded:
            schema[vol.Required("action", default="retry")] = SelectSelector(
                SelectSelectorConfig(
                    options=["retry"] if native_bond_required else ["retry", "finish"],
                    mode=SelectSelectorMode.LIST,
                    translation_key="pairing_result_action",
                )
            )
        return self.async_show_form(
            step_id="pairing_result",
            data_schema=vol.Schema(schema),
            errors={"base": "vmat_bond_required"}
            if native_bond_required and not native_bond_verified
            else {},
            description_placeholders={
                "name": self._manual_data.get(CONF_NAME, "Unknown"),
                "outcome": await self._async_pairing_outcome_note(result, evidence),
            },
        )

    async def _async_pairing_outcome_note(
        self, result: OperationResult | None, evidence: Any
    ) -> str:
        """Describe what the operation achieved, in the user's language."""
        if result is None:
            return await self._pairing_text("no_run")

        if (
            result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
            and isinstance(evidence, BondEvidence)
            and evidence.proves_native_bond_absent
        ):
            where = evidence.owner.source or evidence.owner.adapter or "unknown"
            return (await self._pairing_text("native_absent")).format(transport=where)

        if (
            result.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
            and isinstance(evidence, BondEvidence)
            and evidence.status is BondVerificationStatus.AUTH_FAILED
            and evidence.owner.transport is TransportClass.PROXY
        ):
            path = async_path_for_source(self.hass, evidence.owner.source)
            transport = evidence.owner.source or "ESPHome proxy"
            if path is not None and path.display_name != transport:
                transport = f"{path.display_name} ({transport})"
            return (await self._pairing_text("auth_failed_proxy")).format(
                transport=transport,
                recovery_url=PROXY_PAIRING_RECOVERY_URL,
            )

        if result.succeeded and isinstance(evidence, BondEvidence):
            if not evidence.proves_bond:
                # Nothing contradicted the pairing, but nothing proved it either.
                return await self._pairing_text("unproven")
            owner = evidence.owner
            where = owner.source or str(owner.transport)
            if evidence.status is BondVerificationStatus.NATIVE_OS_STATE:
                return (await self._pairing_text("native_verified_local")).format(transport=where)
            if owner.transport is TransportClass.PROXY:
                key = "verified_proxy"
            elif owner.transport is TransportClass.LOCAL:
                key = "verified_local"
            else:
                # A verified read whose route could not be identified. Saying
                # "stored on this host" would contradict the evidence and
                # mislead about where a later bond removal has to happen.
                key = "verified_unknown"
            if self._pairing_mode == "verify_existing":
                key = f"existing_{key}"
            return (await self._pairing_text(key)).format(transport=where)

        keys = {
            OperationOutcome.NOT_ADVERTISING: "not_advertising",
            OperationOutcome.ROUTE_MISMATCH: "route_mismatch",
            OperationOutcome.BOND_VERIFICATION_FAILED: "auth_failed",
            OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE: "inconclusive",
            OperationOutcome.PAIRING_NOT_SUPPORTED: "unsupported",
            OperationOutcome.UNPAIR_FAILED: "removal_failed",
            OperationOutcome.UNPAIR_UNCONFIRMED: "removal_unconfirmed",
            OperationOutcome.CONNECTION_IN_USE: "in_use",
            OperationOutcome.NO_CONNECTION_SLOTS: "no_slots",
            OperationOutcome.TIMEOUT: "timed_out",
            OperationOutcome.CANCELLED: "cancelled",
        }
        return await self._pairing_text(keys.get(result.outcome, "connection_failed"))

    async def _pairing_text(self, key: str) -> str:
        """Return one pairing-result message, translated."""
        return await _async_translation(
            self.hass,
            "config",
            f"step.pairing_result.data_description.outcome_{key}",
            _PAIRING_OUTCOME_FALLBACKS[key],
        )

    async def _attempt_pairing(
        self,
        address: str | None,
        *,
        request_bond: bool = True,
        track_for_flow_cleanup: bool = True,
        device: BLEDevice | None = None,
    ) -> BondEvidence:
        """Pair using the protocol's required connection ordering, and verify it.

        Returns the evidence gathered, which is what the caller must judge: a
        connection is not a bond, and ``client.pair()`` returning is not a bond
        either. Only an authentication-gated operation that succeeded proves one
        (issue #461).

        Shielded bond replacement owns its client within the detached task, so
        flow cleanup must not disconnect it while the replacement is still
        running. Ordinary attempts are tracked so cancelling their flow closes
        the connection promptly.

        The bed must have advertised recently before anything is attempted.
        Without that check a bed that is asleep or unplugged still looks present
        in Home Assistant's history, and the attempt burns its whole connection
        timeout producing a failure that reads like a pairing problem (#458).

        Raises:
            NotImplementedError: the Bluetooth backend does not support pairing.
            NotAdvertisingError: the bed is not currently advertising.
        """
        from .support_proxy_logs import capture_proxy_logs

        if not address:
            raise ValueError("No address provided for pairing")

        preferred_adapter = ADAPTER_AUTO
        if self._manual_data:
            preferred_adapter = self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        if request_bond and self._pairing_retry_source:
            preferred_adapter = self._pairing_retry_source

        async with capture_proxy_logs(self.hass, address, preferred_adapter, retain=True):
            evidence = await self._attempt_pairing_with_capture(
                address,
                request_bond=request_bond,
                track_for_flow_cleanup=track_for_flow_cleanup,
                device=device,
                preferred_adapter=preferred_adapter,
            )
            cleared_source = evidence.owner.source if evidence.gatt_cache_cleared else None
            if cleared_source:
                # The failure may only have been the proxy's stale handles, which
                # the verifier has just dropped (issue #660). Verify the existing
                # bond on rediscovered handles first: re-pairing a bonded ESPHome
                # device can fail with error 82 or wedge the proxy. Both retries
                # are pinned to that proxy, as the manual proxy retry is, so a
                # reroute cannot judge or pair a different one.
                _LOGGER.info("Verifying %s once with rediscovered GATT services", address)
                saved_sources = (self._pairing_verify_source, self._pairing_retry_source)
                self._pairing_verify_source = cleared_source
                try:
                    try:
                        evidence = await self._attempt_pairing_with_capture(
                            address,
                            request_bond=False,
                            track_for_flow_cleanup=track_for_flow_cleanup,
                            device=None,
                            preferred_adapter=cleared_source,
                        )
                    except BondRouteMismatchError as err:
                        # HA reranks routes on connect, so one reroute away from
                        # the cleared proxy earns a second, final verification.
                        _LOGGER.info("Stale-cache verification for %s rerouted: %s", address, err)
                        evidence = await self._attempt_pairing_with_capture(
                            address,
                            request_bond=False,
                            track_for_flow_cleanup=track_for_flow_cleanup,
                            device=None,
                            preferred_adapter=cleared_source,
                        )
                    # Only a definite failure justifies pairing over a bond that
                    # may still be intact; an inconclusive read proves nothing.
                    if request_bond and evidence.status is BondVerificationStatus.AUTH_FAILED:
                        self._pairing_retry_source = cleared_source
                        evidence = await self._attempt_pairing_with_capture(
                            address,
                            request_bond=True,
                            track_for_flow_cleanup=track_for_flow_cleanup,
                            device=None,
                            preferred_adapter=cleared_source,
                        )
                finally:
                    self._pairing_verify_source, self._pairing_retry_source = saved_sources
            return evidence

    async def _attempt_pairing_with_capture(
        self,
        address: str,
        *,
        request_bond: bool,
        track_for_flow_cleanup: bool,
        device: BLEDevice | None,
        preferred_adapter: str,
    ) -> BondEvidence:
        """Run freshness, connection and Auth checks under one retained trace."""
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        _LOGGER.info(
            "Attempting to pair with %s (preferred adapter: %s)...",
            address,
            preferred_adapter,
        )

        prediction = async_predict_path(self.hass, address, preferred_adapter)
        pinned = bool(preferred_adapter and preferred_adapter != ADAPTER_AUTO)
        # Pairing writes a bond, and a bond belongs to whichever transport made
        # it, so a pinned adapter is honoured by pinning the source below rather
        # than by silently pairing over a stronger one. Whether that source can
        # reach the bed is decided by the freshness lookup, not by the
        # prediction: async_predict_path only enumerates connectable scanners,
        # and some ESPHome proxies file a perfectly connectable bed under
        # non-connectable, so refusing here would block pairing over exactly the
        # proxy that Automatic mode uses happily.
        source = preferred_adapter if pinned else None
        if request_bond and self._pairing_retry_source:
            source = self._pairing_retry_source
        if not request_bond and self._pairing_verify_source:
            # Verifying an existing bond has to happen on the adapter that holds
            # it. A stronger but unbonded adapter would answer with an
            # authentication failure and steer the user into replacing a bond
            # that works.
            source = self._pairing_verify_source
        if device is None:
            # Someone who just put a bed into pairing mode is standing at the bed
            # and expects to wait, so this wait is longer than the setup probe's.
            evidence, device = await async_wait_for_advertisement(
                self.hass,
                address,
                source=source,
                wait_timeout=ADVERTISEMENT_WAIT_SECONDS,
                on_progress=self.async_report_progress,
            )
            if not evidence.is_fresh or device is None:
                raise NotAdvertisingError(evidence.status)

        bed_type = self._manual_data.get(CONF_BED_TYPE) if self._manual_data else None
        protocol_variant = (
            self._manual_data.get(CONF_PROTOCOL_VARIANT) if self._manual_data else None
        )
        pair_after_service_discovery = bool(
            request_bond
            and (
                self._pairing_retry_source
                or (
                    bed_type
                    and requires_pairing_after_service_discovery(bed_type, protocol_variant)
                )
            )
        )

        # LP Control and Sleep Number discover GATT, then ask Android to
        # create the bond. BlueZ's pair=True path calls Device1.Pair instead of
        # making the app's ordinary unbonded GATT connection first.
        # Hold the address lock for the whole client lifetime, not just the
        # connect: the disconnect below must not land in the middle of another
        # caller's connect attempt, where bleak's cleanup can abort it. Keeping
        # it all in this one task is also required, because the lock is
        # reentrant per task rather than per caller.
        vmat_profile = (
            bed_type == BED_TYPE_VIBRADORM_APP
            and self._manual_data is not None
            and self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
        )
        connect_lock = async_get_connect_lock(self.hass, address)
        if connect_lock.retained_setup_client is not None:
            with contextlib.suppress(Exception):
                await connect_lock.async_release_setup_client()
        async with connect_lock, contextlib.AsyncExitStack() as budget:
            onboarding_deadline: float | None = None
            if bed_type == BED_TYPE_VIBRADORM_APP and request_bond:
                onboarding_deadline = asyncio.get_running_loop().time() + (
                    VIBRADORM_VMAT_ONBOARDING_TIMEOUT_SECONDS
                    if self._manual_data is not None
                    and self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
                    else VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS
                )
                await budget.enter_async_context(asyncio.timeout_at(onboarding_deadline))
            self.async_report_action(SetupAction.CONNECTING)
            connect_kwargs: dict[str, Any] = {
                "use_services_cache": not (
                    pair_after_service_discovery or bed_type == BED_TYPE_FURNIMOVE
                ),
            }
            if request_bond and not pair_after_service_discovery:
                # Passed only when a bond is wanted. Older bleak-retry-connector
                # versions have no pair keyword at all, and sending pair=False
                # there raises the TypeError this reports as "pairing not
                # supported" - for a mode that never needed pairing support.
                connect_kwargs["pair"] = True
            client = await establish_connection(
                BleakClient,
                device,
                address,
                max_attempts=1,
                timeout=(
                    STARCODE_APP_CONNECTION_TIMEOUT_SECONDS
                    if bed_type == BED_TYPE_STARCODE_ABM5_4
                    else 5.0
                    if request_bond
                    and self._manual_data is not None
                    and self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
                    else CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE].connection_timeout
                ),
                **connect_kwargs,
            )
            if track_for_flow_cleanup:
                self.async_track_client(client)
            vmat_setup_started = False
            try:
                # The routed transport is only knowable now, and it decides who
                # owns any bond this attempt creates.
                # Ownership has to come from the route actually taken. A
                # prediction is explicitly not a guarantee, and recording one as
                # the bond owner could persist "local" for a bond stored on a
                # proxy, later authorizing removal of an unrelated host bond.
                actual_source = client_source(client)
                path = async_path_for_source(self.hass, actual_source) if actual_source else None
                self.async_report_path(path or prediction.chosen)
                if (
                    not request_bond
                    and self._pairing_verify_source
                    and (
                        actual_source is None
                        or actual_source.upper() != self._pairing_verify_source.upper()
                    )
                ):
                    raise BondRouteMismatchError(
                        "connected through "
                        f"{actual_source or 'an unknown adapter'}, expected "
                        f"{self._pairing_verify_source}"
                    )
                if (
                    request_bond
                    and self._pairing_retry_source
                    and actual_source != self._pairing_retry_source
                ):
                    raise BondRouteMismatchError(
                        "connected through "
                        f"{actual_source or 'an unknown adapter'}, expected "
                        f"{self._pairing_retry_source}"
                    )

                native_existing: BondEvidence | None = None
                if self._migration is not None:
                    assert self._manual_data is not None
                    self._migration_endpoint_check(client, self._manual_data)
                    self._migration_endpoints_checked = True
                if vmat_profile:
                    from .profiles.vibradorm import VMAT_REMOTES
                    from .vibradorm_vmat_setup import validate_vmat_roles

                    assert self._manual_data is not None
                    remote = VMAT_REMOTES[self._manual_data[CONF_VIBRADORM_VMAT_REMOTE]]
                    validate_vmat_roles(client, basic=remote.control_type == 2)
                if bed_type == BED_TYPE_VIBRADORM_APP:
                    native_existing = await async_verify_native_bond(
                        address, path=path, operation="vibradorm_existing_native_bond"
                    )
                pair_error: Exception | None = None
                if pair_after_service_discovery and not (
                    native_existing is not None and native_existing.proves_bond
                ):
                    if bed_type == BED_TYPE_VIBRADORM_APP:
                        from .beds.vibradorm_app import (
                            VibradormAppMetadataProgress,
                            async_prepare_vibradorm_app_pairing,
                        )

                        assert self._manual_data is not None
                        assert onboarding_deadline is not None
                        stored_control = self._manual_data[CONF_VIBRADORM_CONTROL_TYPE]

                        def retain_metadata(delta: VibradormAppMetadataProgress) -> None:
                            assert self._manual_data is not None
                            cached = self._manual_data.get(CONF_VIBRADORM_APP_METADATA)
                            retained: dict[str, str | None] = {}
                            if isinstance(cached, dict):
                                retained = {
                                    key: value
                                    for key, value in cached.items()
                                    if key
                                    in (
                                        "model",
                                        "firmware",
                                        "software",
                                        "main_firmware_article",
                                        "xmc_status",
                                        "opmode",
                                        "device_name",
                                        "revision_id",
                                        "revision_string",
                                        "variant",
                                    )
                                    and (
                                        isinstance(value, str)
                                        or key == "main_firmware_article"
                                        and value is None
                                    )
                                }
                            retained.update(
                                (field, value)
                                for field, value in delta.items()
                                if isinstance(value, str)
                            )
                            self._manual_data[CONF_VIBRADORM_APP_METADATA] = retained

                        vmat_setup_started = self._manual_data[CONF_VIBRADORM_APP_PROFILE] == "vmat"
                        metadata = await async_prepare_vibradorm_app_pairing(
                            client,
                            self._manual_data[CONF_VIBRADORM_APP_PROFILE],
                            "other" if stored_control == "other" else int(stored_control),
                            deadline=onboarding_deadline,
                            metadata_progress=retain_metadata,
                            remote=self._manual_data.get(CONF_VIBRADORM_VMAT_REMOTE),
                        )
                        completed: VibradormAppMetadataProgress = {
                            "model": metadata.model,
                            "firmware": metadata.firmware,
                            "software": metadata.software,
                        }
                        if metadata.main_firmware_article is not None:
                            completed["main_firmware_article"] = metadata.main_firmware_article
                        retain_metadata(completed)
                    _LOGGER.info(
                        "Connected to %s and discovered services; creating the BLE bond now",
                        address,
                    )
                    self.async_report_action(SetupAction.PAIRING)
                    try:
                        await client.pair()
                    except NotImplementedError, TypeError:
                        # The backend cannot pair at all; an unauthenticated
                        # read would misreport this as stale proxy keys.
                        raise
                    except Exception as err:  # noqa: BLE001 - verify before judging the RPC
                        pair_error = err
                        _LOGGER.warning(
                            "Pairing %s raised (%s); verifying whether a bond was made",
                            address,
                            err,
                        )
                    else:
                        _LOGGER.info(
                            "BLE backend pairing completed for %s via %s; verifying Auth next",
                            address,
                            actual_source,
                        )

                self.async_report_action(SetupAction.VERIFYING_BOND)
                if bed_type == BED_TYPE_VIBRADORM_APP:
                    evidence = await async_verify_native_bond(
                        address,
                        path=path,
                        operation="setup_native_pairing"
                        if request_bond
                        else "verify_existing_native_bond",
                    )
                else:
                    evidence = await async_verify_authenticated_access(
                        client,
                        bed_type=bed_type,
                        protocol_variant=protocol_variant,
                        path=path,
                        operation=("setup_pairing" if request_bond else "verify_existing_bond"),
                    )
                if (
                    pair_after_service_discovery
                    and pair_error is not None
                    and not evidence.proves_native_bond_absent
                    and evidence.status
                    not in (
                        BondVerificationStatus.VERIFIED,
                        BondVerificationStatus.NATIVE_OS_STATE,
                        BondVerificationStatus.AUTH_FAILED,
                    )
                ):
                    raise pair_error
                _LOGGER.info(
                    "Bond verification result for %s via %s: status=%s reason=%s; disconnecting setup probe",
                    address,
                    actual_source,
                    evidence.status,
                    evidence.error or "none",
                )
                return evidence
            finally:
                self.async_report_action(SetupAction.DISCONNECTING)
                try:
                    if (
                        bed_type == BED_TYPE_VIBRADORM_APP
                        and vmat_setup_started
                        and self._manual_data is not None
                        and self._manual_data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
                        and client.is_connected
                    ):
                        from .vibradorm_vmat_setup import async_close_vmat_setup

                        try:
                            await async_close_vmat_setup(client)
                        except Exception:  # noqa: BLE001 - always disconnect the setup-owned client
                            _LOGGER.debug("VMAT setup close failed", exc_info=True)
                finally:
                    pending_failure = sys.exception()
                    try:
                        await client.disconnect()
                    except Exception:  # noqa: BLE001 - cleanup must not mask the result
                        if (
                            (vmat_profile or self._migration is not None)
                            and client.is_connected
                            and pending_failure is None
                        ):
                            raise
                        _LOGGER.debug("Disconnect after pairing %s failed", address, exc_info=True)
                    else:
                        if (
                            vmat_profile or self._migration is not None
                        ) and client.is_connected:
                            if pending_failure is None:
                                raise ConnectionError("The setup connection did not disconnect")
                        elif track_for_flow_cleanup:
                            # Only clear the client registered by this attempt.
                            self.async_track_client(None)
                    finally:
                        if (
                            vmat_profile or self._migration is not None
                        ) and client.is_connected:
                            # Replacement owns its task until terminal cleanup; only
                            # then transfer a surviving native link to flow/HA ownership.
                            self.async_retain_failed_setup_client(client, address)
                        elif (
                            vmat_profile or self._migration is not None
                        ) and track_for_flow_cleanup:
                            self.async_track_client(None)

    def _verification_possible(self) -> bool:
        """Return True only when a connectable scanner exists to probe through.

        With no connectable scanner the probe is guaranteed to fail with
        "device not found", so showing the verify step would only display an
        unhelpful error - skip straight to creating the entry instead.
        """
        try:
            from homeassistant.components.bluetooth import async_scanner_count

            return async_scanner_count(self.hass, connectable=True) > 0
        except Exception:  # noqa: BLE001 - absence of scanners must not break setup
            return False

    async def _async_create_selected_app_entry(
        self, *, title: str, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Retain first-selection intent only in this running Home Assistant session."""
        if self._migration is not None:
            if self._migration_requires_check and not self._migration_verified:
                return self.async_abort(reason="migration_verification_required")
            self._pending_entry = dict(data)
            return await self._async_show_migration_confirm()
        self._record_selected_app_intent(data)
        if data.get(CONF_BED_TYPE) == BED_TYPE_SVANE:
            variant = data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
            if variant not in SVANE_VARIANTS:
                raise ValueError("Unknown Svane Remote profile")
            if variant != SVANE_VARIANT_JENSEN_LINON:
                data.update(
                    {
                        CONF_MOTOR_COUNT: 2,
                        CONF_HAS_MASSAGE: False,
                        CONF_DISABLE_ANGLE_SENSING: True,
                        CONF_MOTOR_PULSE_USER_SET: False,
                    }
                )
        return self.async_create_entry(title=title, data=data)

    def _record_selected_app_intent(self, data: dict[str, Any]) -> None:
        """Apply process-local app intent only once the saved selection is accepted."""
        if data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM_APP:
            from .vibradorm_app_state import (
                clear_vibradorm_app_session_intent,
                mark_vibradorm_app_selection,
            )

            if (
                data.get(CONF_VIBRADORM_RESTORED, False)
                or data.get(CONF_VIBRADORM_APP_PROFILE) == "vmat"
            ):
                clear_vibradorm_app_session_intent(self.hass, data[CONF_ADDRESS])
            else:
                control = data[CONF_VIBRADORM_CONTROL_TYPE]
                mark_vibradorm_app_selection(
                    self.hass,
                    data[CONF_ADDRESS],
                    app_profile=data[CONF_VIBRADORM_APP_PROFILE],
                    control_type="other" if control == "other" else int(control),
                    remembered_floor_default=data.get(CONF_VIBRADORM_FLOOR_DEFAULT, 6),
                )

    async def _finish_with_verify(self, entry_data: dict[str, Any], title: str) -> ConfigFlowResult:
        """Stash the finalized entry and route through the verify_connection step.

        Skips the verify step (creating the entry directly) when no connectable
        scanner is available to probe through, or for one-connection pairing-window
        beds whose single connection must be left for setup (issue #385). Standard
        Octo must verify PIN requirements even when no scanner is available yet.
        """
        if entry_data.get(CONF_BED_TYPE) == BED_TYPE_SVANE:
            variant = entry_data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
            if variant not in SVANE_VARIANTS:
                raise ValueError("Unknown Svane Remote profile")
            if variant != SVANE_VARIANT_JENSEN_LINON:
                entry_data.update(
                    {
                        CONF_MOTOR_COUNT: 2,
                        CONF_HAS_MASSAGE: False,
                        CONF_DISABLE_ANGLE_SENSING: True,
                        CONF_MOTOR_PULSE_USER_SET: False,
                    }
                )
        if entry_data.get(CONF_BED_TYPE) == BED_TYPE_OKIN_RF_ECO_BT:
            from .furnimove_repair import CONF_STAIRCASE_LAYOUT_CONFIRMED

            entry_data[CONF_STAIRCASE_LAYOUT_CONFIRMED] = True
            entry_data[CONF_MOTOR_COUNT] = 1
        if entry_data.get(CONF_BED_TYPE) == BED_TYPE_FURNIMOVE:
            from .furnimove_profiles import FURNIMOVE_PROFILES

            if entry_data.get(CONF_FURNIMOVE_REMOTE) not in FURNIMOVE_PROFILES:
                self._manual_data = entry_data
                self._manual_data[CONF_NAME] = title
                return await self.async_step_profile_questions()
        if self._final_settings_pending:
            # An app step that finishes by itself still asks the bed's settings first.
            self._manual_data = entry_data
            return await self._async_new_bed_settings("verify")
        needs_pin_check = (
            entry_data.get(CONF_BED_TYPE) == BED_TYPE_OCTO
            and entry_data.get(CONF_PROTOCOL_VARIANT) != OCTO_VARIANT_STAR2
        )
        if self._migration is not None and self._migration.is_unchanged_by(entry_data):
            return self.async_abort(reason="migration_unchanged")
        if self._migration is not None and not self._migration_requires_check:
            return await self._async_create_selected_app_entry(title=title, data=entry_data)
        if (
            self._migration is None
            and not needs_pin_check
            and not self._verification_possible()
        ) or _skips_setup_connection_probe(
            entry_data.get(CONF_BED_TYPE), entry_data.get(CONF_PROTOCOL_VARIANT)
        ):
            return await self._async_create_selected_app_entry(title=title, data=entry_data)
        self._pending_entry = entry_data
        self._pending_title = title
        self._octo_pin_form_shown = False
        return await self.async_step_setup_progress()

    def _async_start_probe_operation(self) -> None:
        """Prepare the shared operation state for a capability probe."""
        assert self._pending_entry is not None
        address = self._pending_entry[CONF_ADDRESS]
        preferred = self._pending_entry.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        self.async_begin_operation(
            name=self._pending_entry.get(CONF_NAME) or address,
            address=address,
            prediction=async_predict_path(self.hass, address, preferred),
            action=SetupAction.LOCATING,
            policy=ConnectionLifetimePolicy.ORDINARY,
            placeholders={
                "name": self._pending_entry.get(CONF_NAME) or address,
                "address": address,
            },
        )

    async def _async_probe_worker(self) -> OperationResult:
        async with self._migration_transport_operation():
            result = await self._async_probe_worker_reserved()
        if self._migration is not None:
            self._migration_verified = result.succeeded
        return result

    async def _async_probe_worker_reserved(self) -> OperationResult:
        """Run the capability probe as a tracked background operation.

        Everything the client touches happens in this one task: the per-address
        connect lock is reentrant per ``asyncio.Task``, so splitting the connect
        and the disconnect across tasks would deadlock rather than re-enter.
        """
        assert self._pending_entry is not None
        starcode_transport = (
            _starcode_initial_transport(
                self._pending_entry,
                self._discovery_info.name if self._discovery_info is not None else None,
            )
            if self._pending_entry.get(CONF_BED_TYPE) == BED_TYPE_STARCODE_ABM5_4
            else None
        )
        report = await self._probe_capabilities(
            self._pending_entry[CONF_ADDRESS],
            self._pending_entry.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
            self._pending_entry.get(CONF_BED_TYPE),
            self._pending_entry.get(CONF_PROTOCOL_VARIANT),
            reporter=self.async_report_action,
            wait_progress=self.async_report_progress,
            path_reporter=self.async_report_path,
            client_tracker=self.async_track_client,
            octo_pin=self._pending_entry.get(CONF_OCTO_PIN, ""),
            starcode_transport_selector=starcode_transport,
            migration_check=self._migration_probe_check(),
        )
        if report.starcode_transport_selector is not None:
            self._pending_entry[CONF_STARCODE_TRANSPORT_SELECTOR] = (
                report.starcode_transport_selector
            )
        if report.starcode_ble_device_name:
            self._pending_entry.setdefault(CONF_BLE_DEVICE_NAME, report.starcode_ble_device_name)
        if report.freshness is FreshnessStatus.DEVICE_UNRESOLVED:
            outcome = OperationOutcome.DEVICE_UNRESOLVED
        elif report.freshness is not None and report.freshness is not FreshnessStatus.FRESH:
            outcome = OperationOutcome.NOT_ADVERTISING
        elif not report.connected or report.starcode_transport_valid is False:
            outcome = OperationOutcome.CONNECTION_FAILED
        elif report.octo_pin_status is OctoPinStatus.INCONCLUSIVE:
            outcome = OperationOutcome.PIN_VERIFICATION_INCONCLUSIVE
        elif report.octo_pin_status in (OctoPinStatus.REQUIRED, OctoPinStatus.REJECTED):
            outcome = OperationOutcome.AUTHENTICATION_FAILED
        else:
            outcome = OperationOutcome.SUCCESS
        return OperationResult(
            outcome=outcome,
            detail=report.error,
            path=report.actual_path or report.predicted_path,
            payload=report,
        )

    async def async_step_setup_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run connection and PIN checks behind a live progress view.

        Without this the form the user just submitted sits there frozen for as
        long as the BLE stack takes, which is indistinguishable from a hang
        (issue #457).
        """
        assert self._pending_entry is not None
        if self._operation is None:
            self._async_start_probe_operation()
        return await self.async_run_operation_step(
            # A guided change shows its own checklist: nothing is saved yet.
            step_id="migration_check" if self._migration is not None else "setup_progress",
            worker=self._async_probe_worker,
            next_step_id=(
                "verify_octo_pin"
                if self._pending_entry.get(CONF_BED_TYPE) == BED_TYPE_OCTO
                and self._pending_entry.get(CONF_PROTOCOL_VARIANT) != OCTO_VARIANT_STAR2
                else "verify_connection"
            ),
            description_placeholders=self._migration_check_placeholders(self._pending_entry),
        )

    async def async_step_migration_check(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Check a guided change's staged route behind its checklist."""
        return await self.async_step_setup_progress(user_input)

    def _migration_check_placeholders(self, staged: Mapping[str, Any]) -> dict[str, str]:
        """Name the staged route on a guided change's check screens."""
        if self._migration is None:
            return {}
        return {"selection": self._migration_selection_label(staged)}

    async def _async_show_migration_failure(
        self,
        origin: Literal["verify_connection", "pairing_result"],
        detail: str,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Say that a failed guided-change check saved nothing, then offer Try again or Keep."""
        staged = self._pending_entry if origin == "verify_connection" else self._manual_data
        assert staged is not None
        self._migration_failed_from = origin
        return self.async_show_form(
            step_id="migration_check_failed",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="retry"): SelectSelector(
                        SelectSelectorConfig(
                            options=["retry", "keep"],
                            translation_key="migration_check_action",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors or {},
            description_placeholders={
                "name": staged.get(CONF_NAME) or staged[CONF_ADDRESS],
                "detail": detail,
            },
        )

    async def async_step_migration_check_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Hand Try again or Keep back to the result step whose check failed."""
        if self._migration_failed_from == "pairing_result":
            return await self.async_step_pairing_result(user_input)
        return await self.async_step_verify_connection(user_input)

    async def _migration_probe_failure(self, report: CapabilityReport | None) -> str:
        """Explain why a guided change's connection check did not pass."""
        assert self._pending_entry is not None
        if report is not None and report.freshness is FreshnessStatus.DEVICE_UNRESOLVED:
            key, default = (
                "unresolved",
                "**{name}** is advertising, but Home Assistant couldn't open a connection "
                "to it just now. This is usually momentary.",
            )
        elif report is not None and report.freshness not in (None, FreshnessStatus.FRESH):
            key, default = (
                "not_advertising",
                "**{name}** hasn't advertised recently, so no connection was attempted. "
                "Wake it with its remote, or move it closer to an adapter or proxy.",
            )
        else:
            key, default = (
                "failed",
                "The check couldn't confirm that **{name}** works with **{selection}**: "
                "the connection failed, or the receiver doesn't offer what "
                "{selection} needs.",
            )
        text = await _async_translation(
            self.hass,
            "config",
            f"step.migration_check_failed.data_description.reason_{key}",
            default,
        )
        return text.format(
            name=self._pending_entry.get(CONF_NAME) or self._pending_entry[CONF_ADDRESS],
            selection=self._migration_selection_label(self._pending_entry),
        )

    async def _probe_capabilities(
        self,
        address: str,
        preferred_adapter: str | None,
        bed_type: str | None,
        protocol_variant: str | None = None,
        *,
        reporter: Callable[[SetupAction], None] | None = None,
        wait_progress: Callable[[float], None] | None = None,
        path_reporter: Callable[[ConnectionPath | None], None] | None = None,
        client_tracker: Callable[[BleakClient | None], None] | None = None,
        octo_pin: str = "",
        starcode_transport_selector: str | None = None,
        migration_check: Callable[[BleakClient], None] | None = None,
    ) -> CapabilityReport:
        """Connect once and report device information and Octo PIN acceptance.

        This never moves the bed. It selects an adapter,
        establishes a connection, discovers GATT services, and reads the standard
        Device Information service, then checks application PIN access for Octo.
        It always disconnects in ``finally`` so the
        coordinator can take the bed's single BLE connection afterwards, and it
        never raises: any failure is captured in ``report.error`` so setup stays
        non-blocking.

        Before connecting it checks that the bed has actually advertised
        recently. Without that check a bed that is asleep or unplugged still
        looks present in Home Assistant's history, and the probe burns its whole
        timeout producing a failure that reads like a pairing problem (#458).

        ``reporter`` receives the current phase so a progress view can name what
        is happening. ``wait_progress`` drives the numeric bar, and is passed
        only to the advertisement wait: that is the one step whose duration is
        known in advance, so it is the only one where a percentage is honest.
        ``path_reporter`` is called the moment the routed transport is known, so
        the progress view can name it while the probe is still running.
        ``client_tracker`` is handed the live client so a cancelled flow can
        still close it: the disconnect below is an ordinary await and can be
        interrupted, and a link left open holds the bed's only connection.
        """
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        def _report(action: SetupAction) -> None:
            if reporter is not None:
                reporter(action)

        has_position_feedback = bed_type_has_position_feedback(bed_type, protocol_variant)
        report = CapabilityReport(position_feedback=has_position_feedback)
        if bed_type == BED_TYPE_STARCODE_ABM5_4:
            report.starcode_transport_selector = starcode_transport_selector

        prediction = async_predict_path(self.hass, address, preferred_adapter)
        report.predicted_path = prediction.chosen

        _report(SetupAction.LOCATING)
        source = (
            preferred_adapter
            if preferred_adapter
            and preferred_adapter != ADAPTER_AUTO
            and prediction.preferred_available
            else None
        )
        if wait_progress is not None:
            # Give a bed that is merely between advertising intervals, or that
            # the user is walking over to wake, a chance before refusing.
            evidence, device = await async_wait_for_advertisement(
                self.hass,
                address,
                source=source,
                wait_timeout=_PROBE_ADVERTISEMENT_WAIT_SECONDS,
                on_progress=wait_progress,
            )
        else:
            evidence, device = async_gate_connection(self.hass, address, source=source)
        if bed_type == BED_TYPE_STARCODE_ABM5_4:
            from .beds.starcode_abm5_4_profiles import constructor_selector

            if device is not None and isinstance(device.name, str) and device.name:
                report.starcode_ble_device_name = device.name
                if report.starcode_transport_selector is None:
                    report.starcode_transport_selector = constructor_selector(device.name)
        report.freshness = evidence.status
        report.rssi = evidence.rssi
        if not evidence.is_fresh or device is None:
            # The gate reports an unresolvable device as its own status, so the
            # error key distinguishes "the bed is silent" from "we briefly lost
            # the handle to a bed that is advertising fine".
            report.error = evidence.error_key
            _LOGGER.debug("Skipping the capability probe for %s: %s", address, evidence.status)
            return report

        report.device_found = True
        report.source = evidence.source or (prediction.chosen.source if prediction.chosen else None)
        report.via_proxy = bool(
            evidence.path is not None and evidence.path.transport is TransportClass.PROXY
        )

        client: BleakClient | None = None
        # Hold the address lock until the probe has fully released the client,
        # so its disconnect cannot abort a connect attempt started elsewhere.
        # Everything for this client's lifetime stays in this one task: the
        # address lock is reentrant per task, so a helper task would block
        # rather than re-enter.
        try:
            async with async_get_connect_lock(self.hass, address):
                try:
                    _report(SetupAction.CONNECTING)
                    client = await establish_connection(
                        BleakClient,
                        device,
                        address,
                        max_attempts=1,
                        timeout=(
                            STARCODE_APP_CONNECTION_TIMEOUT_SECONDS
                            if bed_type == BED_TYPE_STARCODE_ABM5_4
                            else _PROBE_TIMEOUT_SECONDS
                        ),
                        use_services_cache=bed_type != BED_TYPE_FURNIMOVE,
                    )
                    if client_tracker is not None:
                        # Registered before anything else can fail or be
                        # cancelled, so the operation's cleanup owns this link
                        # from the moment it exists.
                        client_tracker(client)
                    report.connected = bool(client.is_connected)
                    # Record the real path straight after the connect, before
                    # anything else can fail: it is the only moment the routed
                    # source is known for *this* attempt.
                    actual_source = client_source(client)
                    if actual_source:
                        report.source = actual_source
                        report.actual_path = async_path_for_source(
                            self.hass,
                            actual_source,
                            # Only carry the measured signal over when the same
                            # scanner measured it.
                            rssi=(evidence.rssi if actual_source == evidence.source else None),
                        )
                        if report.actual_path is not None:
                            report.via_proxy = report.actual_path.transport is TransportClass.PROXY
                        if path_reporter is not None:
                            path_reporter(report.actual_path)
                    _report(SetupAction.DISCOVERING_SERVICES)
                    await discover_services(client, address)
                    if migration_check is not None:
                        migration_check(client)
                    services = list(client.services) if client.services else []
                    report.service_count = len(services)
                    writable = 0
                    for service in services:
                        for char in service.characteristics:
                            if (
                                "write" in char.properties
                                or "write-without-response" in char.properties
                            ):
                                writable += 1
                    report.writable_count = writable
                    if bed_type == BED_TYPE_STARCODE_ABM5_4:
                        selected_transport = report.starcode_transport_selector
                        if selected_transport is not None:
                            report.starcode_transport_valid = _starcode_setup_transport_present(
                                client, selected_transport
                            )
                            if not report.starcode_transport_valid:
                                report.error = f"Selected app transport {selected_transport} is missing required GATT roles"
                    _report(SetupAction.READING_CAPABILITIES)
                    report.manufacturer, report.model = await read_ble_device_info(client, address)
                    if bed_type == BED_TYPE_OCTO:
                        _report(SetupAction.VERIFYING_PIN)
                        report.octo_pin_status = await async_verify_octo_pin(
                            client, octo_pin, protocol_variant
                        )
                finally:
                    if client is not None:
                        _report(SetupAction.DISCONNECTING)
                        try:
                            await client.disconnect()
                        except Exception:  # noqa: BLE001 - generic probes are best-effort
                            if migration_check is not None and client.is_connected:
                                raise
                        else:
                            # Only cleared once the link is really closed, so a
                            # cancellation during the disconnect still leaves
                            # the cleanup something to retry.
                            if migration_check is not None and client.is_connected:
                                self.async_retain_failed_setup_client(client, address)
                                raise ConnectionError(
                                    "The validation connection could not be released"
                                )
                            if client_tracker is not None:
                                client_tracker(None)
                        finally:
                            if migration_check is not None and client.is_connected:
                                self.async_retain_failed_setup_client(client, address)
        except Exception as err:  # noqa: BLE001 - probe is best-effort
            if migration_check is not None:
                report.connected = False
            report.error = str(err) or err.__class__.__name__
            _LOGGER.debug("Capability probe for %s failed: %s", address, err)

        return report

    async def _format_capabilities(self, report: CapabilityReport) -> str:
        """Build the ✅/❌/⚠️/ℹ️ markdown checklist shown in verify_connection."""
        lines: list[str] = []

        if report.freshness is FreshnessStatus.DEVICE_UNRESOLVED:
            # The bed answered a scan, so "wake it up" would be wrong advice.
            # Home Assistant simply had no connectable handle for it at that
            # instant, which is what Check again is for.
            lines.append(
                "⚠️ This bed is advertising, but Home Assistant could not open a connection "
                "to it just now, so no connection was attempted."
            )
            lines.append(
                "This is usually momentary. Select **Check again**, or finish setup and let "
                "the integration keep trying."
            )
            return "\n".join(lines)

        if report.freshness is not None and report.freshness is not FreshnessStatus.FRESH:
            # Distinguished from a failed connection on purpose: the bed never
            # answered a scan, so telling the user to check the bond or the
            # adapter would send them after the wrong thing (#458).
            lines.append(
                "❌ This bed is not currently advertising, so no connection was attempted."
            )
            lines.append(
                "Wake it (press a button on the remote), put it in pairing mode, or move it "
                "closer to an adapter or proxy, then select **Check again**."
            )
            return "\n".join(lines)

        if not report.device_found:
            lines.append("❌ Device not found - it may be out of range or not advertising.")
            lines.append("You can still finish setup; the integration will keep trying to connect.")
            return "\n".join(lines)

        lines.append("✅ Device found via Bluetooth")

        if not report.connected:
            lines.append(
                "❌ Could not connect - another app or the bed remote may be holding the "
                "bed's connection (beds allow only one at a time), or it is out of range. "
                "You can still finish setup and try again later."
            )
            return "\n".join(lines)

        if report.actual_path is not None:
            lines.append(
                "✅ "
                + await async_describe_actual(self.hass, report.actual_path, report.predicted_path)
            )
        else:
            connected_parts = ["✅ Connected"]
            if report.source:
                connected_parts.append(f"via {report.source}")
            if report.via_proxy:
                connected_parts.append("(Bluetooth proxy)")
            if report.rssi is not None:
                connected_parts.append(f"(RSSI {report.rssi} dBm)")
            lines.append(" ".join(connected_parts))

        if report.service_count:
            services_word = "service" if report.service_count == 1 else "services"
            writable_word = (
                "writable characteristic"
                if report.writable_count == 1
                else "writable characteristics"
            )
            # The integration controls beds by writing commands to a
            # characteristic, so zero writable characteristics means this setup
            # cannot send commands - flag it instead of giving a false pass
            # (often a sign the probe reached the wrong device).
            marker = "✅" if report.writable_count else "⚠️"
            lines.append(
                f"{marker} GATT services discovered ({report.service_count} {services_word}, "
                f"{report.writable_count} {writable_word})"
            )
            if not report.writable_count:
                lines.append(
                    "⚠️ No writable characteristic found - this device may not be "
                    "controllable, or the probe reached the wrong device."
                )
        else:
            lines.append("⚠️ Connected, but no GATT services were discovered.")

        if report.starcode_transport_valid is False:
            lines.append(
                "❌ The selected app Bluetooth transport is missing its required GATT service or characteristics."
            )
        elif report.starcode_transport_valid is True:
            lines.append("✅ Selected app Bluetooth transport is available")

        if report.manufacturer or report.model:
            info = " · ".join(
                part
                for part in (
                    f"Manufacturer: {report.manufacturer}" if report.manufacturer else None,
                    f"Model: {report.model}" if report.model else None,
                )
                if part
            )
            lines.append(f"ℹ️ {info}")

        if report.position_feedback:
            lines.append("✅ Position feedback supported by this bed type")
        else:
            lines.append("⚠️ Position feedback: not available on this bed type")

        return "\n".join(lines)

    async def async_step_verify_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the capability checklist produced by the setup_progress step.

        This is a result step: the probe itself ran as a background task behind
        a progress view, so this only renders what it found. Submit always
        finishes setup unless a live probe disproved the selected app transport.
        Connection unavailability remains informational. When the bed was not
        advertising the form also offers Retry,
        which re-runs the check in place, so the user can go wake the bed
        without losing everything they already filled in (#458).

        It creates an entry only from input submitted against *this* form.
        ``FlowManager.async_configure`` re-passes the caller's original
        ``user_input`` on every iteration of its progress-done loop, so a
        duplicated submission of the previous form arriving just as the probe
        finishes would otherwise be replayed here and read as confirmation -
        creating an entry the user never saw a result for.
        """
        assert self._pending_entry is not None

        result = self.operation.result
        probe = result.payload if result is not None else None
        report = probe if isinstance(probe, CapabilityReport) else None
        if report is None:
            # The operation state is gone (a direct call, or a flow restored
            # without it). Say so rather than running a blocking probe here:
            # this is the step that exists so that nothing blocks.
            report = CapabilityReport(freshness=FreshnessStatus.MISSING)

        if self._migration is not None:
            if self._migration_verified:
                # A passed check goes straight to the review: nothing is saved yet.
                return await self._async_create_selected_app_entry(
                    title=self._pending_title
                    or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                    data=self._pending_entry,
                )
            if (
                user_input is not None
                and self._verify_form_shown
                and user_input.get("action") == "keep"
            ):
                return await self.async_step_migration_keep()
            if (
                user_input is not None
                and self._verify_form_shown
                and user_input.get("action") == "retry"
            ):
                self._verify_form_shown = False
                self._async_start_probe_operation()
                return await self.async_step_setup_progress()
            self._verify_form_shown = True
            return await self._async_show_migration_failure(
                "verify_connection",
                await self._migration_probe_failure(
                    probe if isinstance(probe, CapabilityReport) else None
                ),
            )

        if user_input is not None and self._verify_form_shown:
            if user_input.get("action") == "retry":
                self._verify_form_shown = False
                self._async_start_probe_operation()
                return await self.async_step_setup_progress()
            if report.starcode_transport_valid is False or (
                self._pending_entry.get(CONF_BED_TYPE) == BED_TYPE_STARCODE_ABM5_4
                and not self._pending_entry.get(CONF_STARCODE_TRANSPORT_SELECTOR)
            ):
                self._verify_form_shown = False
                self._manual_data = dict(self._pending_entry)
                self._recheck_answers = True
                profile = setup_profile_for(self._manual_data)
                assert profile is not None
                return self._show_profile_questions(
                    profile,
                    self._manual_data,
                    {CONF_STARCODE_TRANSPORT_SELECTOR: "starcode_app_invalid"},
                )
            return await self._async_create_selected_app_entry(
                title=self._pending_title or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                data=self._pending_entry,
            )

        schema: dict[vol.Marker, Any] = {}
        if report.freshness is not None and report.freshness is not FreshnessStatus.FRESH:
            # "Finish" stays the default so Submit keeps meaning what it always
            # meant here: setup is never blocked by a failed check. Retry is one
            # click away for the common case of "let me go wake the bed first".
            schema[vol.Required("action", default="finish")] = SelectSelector(
                SelectSelectorConfig(
                    options=["finish", "retry"],
                    mode=SelectSelectorMode.LIST,
                    translation_key="verify_action",
                )
            )

        self._verify_form_shown = True
        return self.async_show_form(
            step_id="verify_connection",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": self._pending_entry.get(CONF_NAME) or self._pending_entry[CONF_ADDRESS],
                "capabilities": await self._format_capabilities(report),
            },
        )

    async def async_step_verify_octo_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish only after PIN acceptance, or let the user correct and retry."""
        assert self._pending_entry is not None
        result = self.operation.result
        report = result.payload if result is not None else None
        status = (
            report.octo_pin_status
            if isinstance(report, CapabilityReport) and report.octo_pin_status is not None
            else OctoPinStatus.INCONCLUSIVE
        )
        errors: dict[str, str] = {}
        if user_input is not None and self._octo_pin_form_shown:
            if status.allows_setup:
                return self.async_create_entry(
                    title=self._pending_title
                    or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                    data=self._pending_entry,
                )
            pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, ""))
            if not is_valid_octo_pin(pin):
                errors[CONF_OCTO_PIN] = "invalid_pin"
            else:
                self._pending_entry[CONF_OCTO_PIN] = pin
                self._octo_pin_form_shown = False
                self._async_start_probe_operation()
                return await self.async_step_setup_progress()

        schema: dict[vol.Marker, Any] = {}
        if not status.allows_setup:
            errors.setdefault("base", f"octo_pin_{status.value}")
            schema[
                vol.Optional(CONF_OCTO_PIN, default=self._pending_entry.get(CONF_OCTO_PIN, ""))
            ] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
        self._octo_pin_form_shown = True
        return self.async_show_form(
            step_id="verify_octo_pin",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "name": self._pending_title or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                "result": await _async_translation(
                    self.hass,
                    "config",
                    f"step.verify_octo_pin.data_description.outcome_{status.value}",
                    _OCTO_PIN_MESSAGES[status],
                ),
            },
        )

    async def async_step_diagnostic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle unsupported BLE device browsing."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "manual":
                _LOGGER.debug("User selected manual entry for BLE browser")
                return await self.async_step_diagnostic_manual()

            _LOGGER.info("User selected device from BLE browser: %s", address)
            discovery_info = self._all_ble_devices[address]
            return self._async_abort_diagnostic_browser(
                address=discovery_info.address.upper(),
                name=discovery_info.name,
                source=getattr(discovery_info, "source", None),
                connectable=getattr(discovery_info, "connectable", None),
            )

        _LOGGER.debug("Scanning for all BLE devices for browser mode...")

        all_discovered = get_discovered_service_info(
            self.hass,
            include_non_connectable=True,
        )
        _LOGGER.debug(
            "Total BLE devices visible for browser mode: %d",
            len(all_discovered),
        )

        # Filter out already configured devices
        current_addresses = {addr.upper() for addr in self._async_current_ids() if addr is not None}

        self._all_ble_devices = {}
        for discovery_info in all_discovered:
            if discovery_info.address.upper() not in current_addresses:
                self._all_ble_devices[discovery_info.address] = discovery_info

        _LOGGER.info(
            "BLE browser: found %d unconfigured BLE devices",
            len(self._all_ble_devices),
        )

        if not self._all_ble_devices:
            _LOGGER.info("No BLE devices found in either scanner view, showing manual entry form")
            return await self.async_step_diagnostic_manual()

        # Sort devices: named devices first (alphabetically), then MAC-only/unnamed
        sorted_devices = sorted(
            self._all_ble_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        devices = {}
        for address, info in sorted_devices:
            label = f"{info.name or 'Unknown'} ({address})"
            if getattr(info, "connectable", True) is False:
                label += " [scanner says non-connectable]"
            devices[address] = label
        devices["manual"] = "Enter address manually"

        return self.async_show_form(
            step_id="diagnostic",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )

    async def async_step_diagnostic_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual MAC address entry for BLE browser mode."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().replace("-", ":")

            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                service_info, connectable = find_service_info_by_address(
                    self.hass,
                    address,
                    allow_non_connectable=True,
                )
                return self._async_abort_diagnostic_browser(
                    address=address,
                    name=user_input.get(CONF_NAME) or getattr(service_info, "name", None),
                    source=getattr(service_info, "source", None),
                    connectable=connectable if service_info is not None else None,
                )

        return self.async_show_form(
            step_id="diagnostic_manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Unknown BLE Device"): str,
                }
            ),
            errors=errors,
        )


def _shown_option_values(schema_dict: dict[Any, Any]) -> dict[str, Any]:
    """Return the default value each field in the options form showed, validated
    the SAME way ``user_input`` was.

    HA validates submitted input against this schema before handing it back, so
    a raw default of ``"10"`` would mis-compare against the coerced ``10``.
    Validating an empty input through the same schema coerces the defaults
    identically, so the paired-options save can tell which fields the user really
    changed (and not clobber per-side values with mistyped "changes").
    """
    try:
        shown = cast("dict[str, Any]", vol.Schema(schema_dict)({}))
        # Match the options handler's conversion from the string-valued select,
        # and its resolution of an app entry to the plain bed type.
        if CONF_MOTOR_COUNT in shown:
            shown[CONF_MOTOR_COUNT] = int(shown[CONF_MOTOR_COUNT])
        if isinstance(shown.get(CONF_BED_TYPE), str):
            shown[CONF_BED_TYPE] = resolve_bed_type_choice(shown[CONF_BED_TYPE])[0]
        return shown
    except vol.Invalid:
        return {}


def _pairlink_settings_schema(
    hass: HomeAssistant,
    current_data: Mapping[str, Any],
) -> dict[vol.Marker, Any]:
    """Build private, per-target Pairlink role and credential fields."""
    local_sources: list[SelectOptionDict] = []
    try:
        from .beds.reverie_pairlink_profile import pairlink_host_adapter_inventory

        local_sources = [
            {"value": item.source, "label": f"{item.source} ({item.adapter})"}
            for item in pairlink_host_adapter_inventory(hass)
            if item.transport == "local" and item.active
        ]
    except Exception:  # noqa: BLE001 - setup revalidates current inventory
        local_sources = []

    current_source = current_data.get(CONF_PAIRLINK_HOST_SOURCE)
    if isinstance(current_source, str) and current_source and all(
        option["value"] != current_source for option in local_sources
    ):
        local_sources.append(
            {"value": current_source, "label": f"{current_source} (not currently active)"}
        )
    source_selector: Any = (
        SelectSelector(
            SelectSelectorConfig(options=local_sources, mode=SelectSelectorMode.DROPDOWN)
        )
        if local_sources
        else TextSelector(TextSelectorConfig())
    )
    return {
        vol.Optional(
            CONF_PAIRLINK_ROLE,
            default=current_data.get(CONF_PAIRLINK_ROLE, PAIRLINK_ROLE_CENTRAL),
        ): vol.In(
            {
                PAIRLINK_ROLE_CENTRAL: "Selected-bed central connection",
                PAIRLINK_ROLE_PERIPHERAL: "Join from this host adapter",
            }
        ),
        vol.Optional(
            CONF_PAIRLINK_HOST_SOURCE,
            default=current_source or "",
        ): source_selector,
        vol.Optional(
            CONF_PAIRLINK_HOME_ID,
            default=(
                ""
                if current_data.get(CONF_PAIRLINK_HOME_ID) is None
                else str(current_data[CONF_PAIRLINK_HOME_ID])
            ),
        ): TextSelector(TextSelectorConfig()),
        vol.Optional(
            CONF_PAIRLINK_PASSWORD_TEXT,
            default=current_data.get(CONF_PAIRLINK_PASSWORD_TEXT, "1122"),
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Optional(
            CONF_PAIRLINK_PASSWORD_HEX,
            default=current_data.get(CONF_PAIRLINK_PASSWORD_HEX, ""),
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }


def _validate_pairlink_option_values(
    hass: HomeAssistant,
    current_data: Mapping[str, Any],
    values: dict[str, Any],
) -> dict[str, str]:
    """Validate only explicit Pairlink inputs and current selected-source evidence."""
    from .beds.reverie_pairlink_profile import (
        pairlink_host_adapter_inventory,
    )
    from .beds.reverie_pairlink_runtime import encode_pairlink_password, normalize_home_id

    errors: dict[str, str] = {}
    role = values.get(
        CONF_PAIRLINK_ROLE,
        current_data.get(CONF_PAIRLINK_ROLE, PAIRLINK_ROLE_CENTRAL),
    )
    if role not in (PAIRLINK_ROLE_CENTRAL, PAIRLINK_ROLE_PERIPHERAL):
        errors[CONF_PAIRLINK_ROLE] = "invalid_pairlink_role"
    else:
        values[CONF_PAIRLINK_ROLE] = role

    if role == PAIRLINK_ROLE_PERIPHERAL:
        source = values.get(CONF_PAIRLINK_HOST_SOURCE, current_data.get(CONF_PAIRLINK_HOST_SOURCE))
        inventory = pairlink_host_adapter_inventory(hass)
        matches = [
            item
            for item in inventory
            if item.source == source and item.transport == "local" and item.active
        ]
        if not isinstance(source, str) or not source or len(matches) != 1:
            errors[CONF_PAIRLINK_HOST_SOURCE] = "pairlink_local_source_unavailable"
        else:
            values[CONF_PAIRLINK_HOST_SOURCE] = source

    raw_home_id = values.get(CONF_PAIRLINK_HOME_ID, current_data.get(CONF_PAIRLINK_HOME_ID))
    home_id: int | None = None
    if raw_home_id not in (None, ""):
        try:
            parsed_home_id = (
                int(raw_home_id.strip(), 10) if isinstance(raw_home_id, str) else raw_home_id
            )
            if isinstance(parsed_home_id, bool) or not isinstance(parsed_home_id, int):
                raise TypeError("Pairlink HomeID must be an integer")
            home_id = parsed_home_id
            normalize_home_id(home_id)
        except (TypeError, ValueError):
            errors[CONF_PAIRLINK_HOME_ID] = "invalid_pairlink_home_id"
        else:
            values[CONF_PAIRLINK_HOME_ID] = home_id
    else:
        values[CONF_PAIRLINK_HOME_ID] = None

    # A blank value preserves caller-context provenance: runtime prefers the
    # current advertisement and uses the source-known 5566 default only when
    # that caller supplies no HomeID.

    password_text = values.get(
        CONF_PAIRLINK_PASSWORD_TEXT,
        current_data.get(CONF_PAIRLINK_PASSWORD_TEXT, "1122"),
    )
    password_hex = values.get(
        CONF_PAIRLINK_PASSWORD_HEX,
        current_data.get(CONF_PAIRLINK_PASSWORD_HEX),
    )
    if password_hex == "":
        password_hex = None
    try:
        encode_pairlink_password(
            password_text=password_text,
            password_hex=password_hex,
        )
    except (TypeError, ValueError):
        errors[CONF_PAIRLINK_PASSWORD_HEX if password_hex is not None else CONF_PAIRLINK_PASSWORD_TEXT] = (
            "invalid_pairlink_password"
        )
    else:
        values[CONF_PAIRLINK_PASSWORD_TEXT] = password_text
        values[CONF_PAIRLINK_PASSWORD_HEX] = password_hex
    return errors


class AdjustableBedOptionsFlow(
    EstimatedPositionsFlowMixin, BluetoothOperationMixin, OptionsFlowWithConfigEntry
):
    """Handle Adjustable Bed options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        super().__init__(config_entry)
        self._pending_data: dict[str, Any] = {}
        self._pending_changed_data: dict[str, Any] = {}
        # The exact BlueZ record the user confirmed removing, captured at the
        # confirmation step so the removal cannot drift onto a different one.
        self._bond_removal_record: LocalBondRecord | None = None
        # True once the bond-removal result form has been drawn, and once its
        # state update has been applied. Both guard against Home Assistant
        # replaying the confirmation's input into the result step.
        self._bond_removal_result_shown: bool = False
        self._bond_removal_state_applied: bool = False
        # A separate-address pair has one bond per child. The side selection is
        # held for the whole confirmation/removal transaction so every lookup,
        # lock and persistence write targets the same address.
        self._bond_removal_side: str | None = None
        # Casper/Hush side support depends on the GATT service the bed exposes,
        # which is only known while connected. ``None`` means not checked yet.
        self._side_transport_supported: bool | None = None
        self._side_transport_probe_failed: bool = False

    def _remember_pending_changes(
        self,
        schema_dict: dict[Any, Any],
        user_input: dict[str, Any],
    ) -> None:
        """Preserve user edits that triggered a dependent-field rebuild."""
        shown = _shown_option_values(schema_dict)
        self._pending_changed_data.update(
            {
                key: value
                for key, value in user_input.items()
                if key != CONF_DISABLE_DISCOVERY and key in shown and shown[key] != value
            }
        )

    @staticmethod
    def _variant_for_bed_type(bed_type: str, data: dict[str, Any]) -> str:
        """Return a valid variant while rebuilding the form for a new bed type."""
        variants = get_variants_for_bed_type(bed_type)
        if not variants:
            return DEFAULT_PROTOCOL_VARIANT

        requested_variant = data.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)
        if isinstance(requested_variant, str) and requested_variant in variants:
            return requested_variant
        if VARIANT_AUTO in variants:
            return VARIANT_AUTO
        return next(iter(variants))

    @classmethod
    def _variant_for_bed_type_change(
        cls,
        previous_bed_type: str,
        requested_bed_type: str,
        data: dict[str, Any],
    ) -> str:
        """Reset variants unless both bed types explicitly share one variant table."""
        previous_variants = get_variants_for_bed_type(previous_bed_type)
        requested_variants = get_variants_for_bed_type(requested_bed_type)
        if previous_variants is requested_variants and requested_variants is not None:
            return cls._variant_for_bed_type(requested_bed_type, data)
        if requested_variants and VARIANT_AUTO not in requested_variants:
            return next(iter(requested_variants))
        return VARIANT_AUTO

    @staticmethod
    def _remove_irrelevant_bed_settings(data: dict[str, Any], bed_type: str) -> None:
        """Drop settings that belong only to the previously selected protocol.

        Every setting another bed type's profiles own goes (``app_profiles``);
        the rest follow the route's capabilities.
        """
        for key in foreign_settings(bed_type):
            data.pop(key, None)
        if bed_type == BED_TYPE_REVERIE_PAIRLINK:
            for key in (CONF_PAIRLINK_HOST_SOURCE, CONF_PAIRLINK_HOME_ID, CONF_PAIRLINK_PASSWORD_HEX):
                if data.get(key) in (None, ""):
                    data.pop(key, None)
        if not get_variants_for_bed_type(bed_type):
            data.pop(CONF_PROTOCOL_VARIANT, None)
        if not _is_leggett_app_type(bed_type, data.get(CONF_PROTOCOL_VARIANT)):
            data.pop(CONF_LEGGETT_APP_PROFILE, None)
        if not supports_passive_position_reconciliation(bed_type):
            data.pop(CONF_PASSIVE_POSITION_RECONCILIATION, None)
        if (
            bed_type in BEDS_WITH_PERCENTAGE_POSITIONS
            or bed_type not in BEDS_WITH_POSITION_FEEDBACK
        ):
            data.pop(CONF_BACK_MAX_ANGLE, None)
            data.pop(CONF_LEGS_MAX_ANGLE, None)

    def _apply_bed_type_change_cleanup(
        self,
        new_data: dict[str, Any],
        bed_type: str,
        requested_variant: str,
    ) -> None:
        """Drop settings the newly saved protocol must not inherit (in place).

        A paired bed keeps its own copy of these settings per side, so the child
        descriptors are cleaned against their own bed type too - otherwise a
        protocol-specific leftover would survive on a side and win over the
        parent value.
        """
        # This preference is integration-wide. Remove any legacy per-entry
        # copy while saving unrelated options so it cannot become a second
        # source of truth.
        new_data.pop(CONF_DISABLE_DISCOVERY, None)
        previous_bed_type = self.config_entry.data.get(CONF_BED_TYPE)
        if not isinstance(previous_bed_type, str):
            previous_bed_type = BED_TYPE_DIAGNOSTIC
        previous_variant = self.config_entry.data.get(
            CONF_PROTOCOL_VARIANT,
            DEFAULT_PROTOCOL_VARIANT,
        )
        # These markers describe the old protocol's authentication requirements
        # and must not steer pairing for the new one. That includes the recorded
        # owner: leaving stale proxy provenance behind would keep blocking the
        # bond removal after the new protocol has established a perfectly
        # ordinary local bond.
        drop_bond_marker = requires_pairing(
            previous_bed_type, previous_variant
        ) != requires_pairing(
            bed_type,
            requested_variant,
        )
        if drop_bond_marker:
            new_data.pop(CONF_BLE_BOND_ESTABLISHED, None)
            new_data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
            new_data.pop(CONF_BLE_BOND_CONTEXT, None)
        self._remove_irrelevant_bed_settings(new_data, bed_type)

        children = iter_children(new_data)
        if not children:
            return
        cleaned: list[dict[str, Any]] = []
        for child in children:
            child_data = dict(child)
            if drop_bond_marker:
                child_data.pop(CONF_BLE_BOND_ESTABLISHED, None)
                child_data.pop(CONF_BLE_BOND_MARKER_UNRELIABLE, None)
                child_data.pop(CONF_BLE_BOND_CONTEXT, None)
            child_bed_type = child_data.get(CONF_BED_TYPE)
            self._remove_irrelevant_bed_settings(
                child_data,
                child_bed_type if isinstance(child_bed_type, str) else bed_type,
            )
            cleaned.append(child_data)
        new_data[CONF_PAIR_CHILDREN] = cleaned

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer the settings form alongside the pairing and Bluetooth actions.

        Always a menu rather than going straight to the form, because removing a
        Bluetooth bond has to live somewhere a user can find it, and it must be
        clearly separate from deleting the config entry (issue #455). The
        paired-bed actions share the same menu; which one is offered depends on
        how this entry is paired.
        """
        menu_options = ["settings"]
        data = self.config_entry.data
        if reconfigure_family(data) is not None:
            menu_options.append("change_app")
        if is_paired(data):
            if data.get(CONF_PAIR_MODE) == PAIR_MODE_SEPARATE_ADDRESS:
                menu_options.extend(["left_settings", "right_settings"])
            menu_options.append(
                "revert_sides" if data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS else "unpair"
            )
        elif supports_single_address_pairing(
            data.get(CONF_BED_TYPE),
            data.get(CONF_PROTOCOL_VARIANT),
            resolved_variant=data.get(CONF_KAIDI_RESOLVED_VARIANT),
            product_type=data.get(CONF_PRODUCT_TYPE),
            ble_device_name=data.get(CONF_BLE_DEVICE_NAME),
        ):
            menu_options.append("pair_sides")
        menu_options.extend(self.estimate_menu_options())
        if data.get(CONF_ADDRESS) or (
            data.get(CONF_PAIR_MODE) == PAIR_MODE_SEPARATE_ADDRESS and bool(iter_children(data))
        ):
            menu_options.append("remove_bond")
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_change_app(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point to the guided reconfigure wizard, keeping Configure read-only here.

        Home Assistant cannot hand an options flow over to a config flow, so the
        guided change runs from the entry's Reconfigure action and from Repairs.
        """
        if user_input is not None:
            return self.async_abort(reason="migration_reconfigure_required")
        from .profile_review import route_label

        return self.async_show_form(
            step_id="change_app",
            description_placeholders={"current": route_label(self.config_entry.data)},
        )

    def _async_flow_manager(self) -> Any:
        """Options flows are driven by their own manager, not the config one."""
        return self.hass.config_entries.options

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        return await self._async_options_form(user_input, step_id="settings")

    async def async_step_left_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_receiver_settings(SIDE_LEFT, user_input)

    async def async_step_right_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_receiver_settings(SIDE_RIGHT, user_input)

    async def _async_receiver_settings(
        self, side: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Edit one physical receiver without changing its partner or profile."""
        data = self.config_entry.data
        child = get_child(data, side)
        if data.get(CONF_PAIR_MODE) != PAIR_MODE_SEPARATE_ADDRESS or child is None:
            return self.async_abort(reason="pair_side_not_found")
        current = effective_child_data(data, side, self.config_entry.options)
        bed_type = current.get(CONF_BED_TYPE, BED_TYPE_DIAGNOSTIC)
        variant = current.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)
        pulse_defaults = get_motor_pulse_defaults(bed_type, variant)
        adapters = get_available_adapters(self.hass)
        schema = _settings_fields(
            self.hass,
            current,
            bed_type,
            variant,
            (
                CONF_PREFERRED_ADAPTER,
                CONF_CONNECTION_PROFILE,
                *_PULSE_FIELDS,
                CONF_DISCONNECT_AFTER_COMMAND,
                CONF_IDLE_DISCONNECT_SECONDS,
            ),
        )
        if bed_type == BED_TYPE_REVERIE_PAIRLINK:
            schema.update(_pairlink_settings_schema(self.hass, current))
        _hide_owned_generic_fields(schema, bed_type, variant)
        # This receiver's own profile questions; the pair's shared form cannot
        # ask them, because each side may run another profile.
        questions = _configure_questions(current)
        context = FlowContext(self.hass, self.config_entry.entry_id)
        if questions is not None:
            schema.update(
                _profile_question_schema(questions, current, context, advanced_section=False)
            )
        errors: dict[str, str] = {}
        if user_input is not None:
            changes = dict(user_input)
            # Settings this receiver's answers no longer allow leave it.
            stale: frozenset[str] = frozenset()
            if bed_type == BED_TYPE_REVERIE_PAIRLINK:
                errors.update(
                    _validate_pairlink_option_values(
                        self.hass,
                        current,
                        changes,
                    )
                )
            parsed, pulse_errors = _parse_settings(changes, bed_type, pulse_defaults)
            changes.update(parsed)
            errors.update(pulse_errors)
            if not errors:
                shown = _shown_option_values(schema)
                for field in (CONF_MOTOR_PULSE_COUNT, CONF_MOTOR_PULSE_DELAY_MS):
                    if field in shown:
                        shown[field] = int(shown[field])
                changes = {key: value for key, value in changes.items() if shown.get(key) != value}
                if (
                    CONF_PREFERRED_ADAPTER in user_input
                    and current.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO) not in adapters
                ):
                    # A gone adapter showed as automatic; save that, not the stale one.
                    changes[CONF_PREFERRED_ADAPTER] = user_input[CONF_PREFERRED_ADAPTER]
                if changes.keys() & {CONF_MOTOR_PULSE_COUNT, CONF_MOTOR_PULSE_DELAY_MS}:
                    changes[CONF_MOTOR_PULSE_USER_SET] = True
                if questions is not None:
                    asked = {question.key for question in questions.questions}
                    changes = {key: value for key, value in changes.items() if key not in asked}
                    before = {**current, **changes}
                    app_data = questions.staged(
                        before, _profile_answers(questions, user_input, current, context)
                    )
                    errors.update(questions.errors(app_data, context))
                    # A profile derives its settled values only from answers its
                    # checks accepted, as setup and single-entry Configure do.
                    if not errors:
                        # The answers, what normalizing corrected and the profile's
                        # own settled values belong to this receiver only.
                        changes.update(
                            {
                                key: value
                                for key, value in app_data.items()
                                if before.get(key) != value
                            }
                        )
                        changes.update(questions.settled(app_data))
                        stale = frozenset(current) - frozenset(app_data)
            if not errors:
                staged = {
                    key: value
                    for key, value in {**current, **changes}.items()
                    if key not in stale
                }
                kept = _limoss_remote_features_left(current, staged)
                if kept is not None:
                    # Light or massage turned off on this receiver: its OFF
                    # commands run first, and a failure keeps the saved setup.
                    if await _async_turn_off_limoss_remote_features(
                        self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id),
                        *kept,
                        side=side,
                    ):
                        # Keep anything saved while the commands ran.
                        data = self.config_entry.data
                    else:
                        errors["base"] = "limoss_remote_feature_update_failed"
            if not errors:
                # Move shared overrides into both receivers before changing
                # one side, keeping unrelated entry-level options intact.
                options = inheritable_child_fields(self.config_entry.options)
                for receiver_side in PAIR_SIDES:
                    if options and get_child(data, receiver_side) is not None:
                        data = with_updated_child(data, receiver_side, options)
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=with_updated_child(data, side, changes, remove=stale),
                )
                return self.async_create_entry(
                    title="",
                    data={
                        key: value
                        for key, value in self.config_entry.options.items()
                        if key not in options
                    },
                )
        return self.async_show_form(
            step_id=f"{side}_settings",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"name": child.get(CONF_NAME, side.title())},
        )

    async def async_step_unpair(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm splitting a paired bed back into two entries."""
        return await self._async_unpair_form(user_input, step_id="unpair")

    async def async_step_revert_sides(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reverting a single-address paired surface."""
        return await self._async_unpair_form(user_input, step_id="revert_sides")

    async def _async_unpair_form(
        self, user_input: dict[str, Any] | None, *, step_id: str
    ) -> ConfigFlowResult:
        """Run the deferred reversible unpair transaction."""
        if user_input is not None and user_input.get("confirm"):
            entry_id = self.config_entry.entry_id

            async def finish_unpair() -> None:
                from . import async_unpair_entry

                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry is None:
                    return
                try:
                    await async_unpair_entry(self.hass, entry)
                except Exception:  # noqa: BLE001 - task must report transaction failure
                    _LOGGER.exception("Could not unpair config entry %s", entry_id)

            # The options flow belongs to the entry being removed. Schedule the
            # transaction after returning the flow result so HA never tears down
            # an entry while its own options flow is still executing.
            self.hass.async_create_task(finish_unpair(), f"adjustable_bed_unpair_{entry_id}")
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

    async def async_step_pair_sides(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enable the reversible left/right/both surface on one BLE address."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        controller = getattr(runtime, "capability_controller", None)
        needs_casper_transport_proof = self.config_entry.data.get(CONF_BED_TYPE) in {"casper_base", "hush_base"}
        casper_not_connected = False
        if needs_casper_transport_proof and self._side_transport_supported is None:
            if runtime is not None and runtime.is_connected and controller is not None:
                self._side_transport_supported = bool(
                    getattr(controller, "supports_single_address_pairing", False)
                )
            elif runtime is None or (self._side_transport_probe_failed and user_input is None):
                casper_not_connected = True
            else:
                # These beds usually hand their connection back a second after
                # each command, so connect on demand instead of asking the user
                # to catch a live connection.
                self._side_transport_probe_failed = False
                self.async_begin_operation(
                    name=self.config_entry.title,
                    action=SetupAction.CONNECTING,
                    placeholders={"name": self.config_entry.title},
                )
                return await self.async_step_pair_sides_probe()
        motomotion_unsupported = self.config_entry.data.get(CONF_BED_TYPE) == BED_TYPE_MOTOMOTION and not supports_single_address_pairing(BED_TYPE_MOTOMOTION, ble_device_name=self.config_entry.data.get(CONF_BLE_DEVICE_NAME))
        if (
            motomotion_unsupported
            or casper_not_connected
            or self._side_transport_supported is False
            or (
                not needs_casper_transport_proof
                and controller is not None
                and not getattr(controller, "supports_single_address_pairing", True)
            )
        ):
            return self.async_show_form(
                step_id="pair_sides",
                data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
                errors={
                    "base": (
                        "casper_pairing_needs_connection"
                        if casper_not_connected
                        else "single_address_pairing_unsupported"
                    )
                },
            )

        if user_input is not None and user_input.get("confirm"):
            entry_id = self.config_entry.entry_id

            async def finish_pair_sides() -> None:
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry is None or is_paired(entry.data):
                    return
                original_data = dict(entry.data)
                original_options = dict(entry.options)
                registry = er.async_get(self.hass)
                origin_unique_ids = [
                    row.unique_id
                    for row in er.async_entries_for_config_entry(registry, entry.entry_id)
                ]
                paired_data = build_single_address_pair_entry_data(
                    original_data,
                    name=entry.title,
                    origin_entry_id=entry.entry_id,
                    origin_unique_id=entry.unique_id,
                    origin_title=entry.title,
                    origin_source=entry.source,
                    origin_options=original_options,
                )
                paired_data[KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS] = origin_unique_ids
                try:
                    if not await self.hass.config_entries.async_unload(entry.entry_id):
                        raise RuntimeError("could not unload entry")
                    self.hass.config_entries.async_update_entry(entry, data=paired_data)
                    if not await self.hass.config_entries.async_setup(entry.entry_id):
                        raise RuntimeError("paired entry setup failed")
                except Exception:  # noqa: BLE001 - restore the working standalone entry
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=original_data,
                        options=original_options,
                    )
                    with contextlib.suppress(Exception):
                        await self.hass.config_entries.async_setup(entry.entry_id)
                    _LOGGER.exception("Could not enable paired sides for config entry %s", entry_id)

            self.hass.async_create_task(
                finish_pair_sides(), f"adjustable_bed_pair_sides_{entry_id}"
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="pair_sides",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

    async def async_step_pair_sides_probe(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect to a Casper/Hush bed to learn whether it has a side byte."""
        return await self.async_run_operation_step(
            step_id="pair_sides_probe",
            worker=self._async_side_transport_worker,
            next_step_id="pair_sides",
        )

    async def _async_side_transport_worker(self) -> OperationResult:
        """Read side support from the live controller during one command."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        supported: bool | None = None

        async def probe(controller: BedController) -> None:
            nonlocal supported
            supported = bool(getattr(controller, "supports_single_address_pairing", False))

        try:
            if runtime is not None:
                await runtime.async_execute_controller_command(
                    probe,
                    cancel_running=False,
                    resource="configuration",
                    read_positions_after_operation=False,
                )
        except Exception as err:  # noqa: BLE001 - report, the user can retry
            _LOGGER.debug("Side support check for %s failed: %s", self.config_entry.title, err)
        if supported is None:
            # A command preempted during preparation returns without running.
            self._side_transport_probe_failed = True
            return OperationResult(outcome=OperationOutcome.CONNECTION_FAILED)
        self._side_transport_supported = supported
        return OperationResult(outcome=OperationOutcome.SUCCESS)

    async def _async_options_form(
        self,
        user_input: dict[str, Any] | None,
        *,
        step_id: str,
    ) -> ConfigFlowResult:
        """Show and save the normal options form."""
        # Get current values from config entry
        current_data: dict[str, Any] = dict(self.config_entry.data)
        separate_address_pair = (
            is_paired(current_data) and current_data.get(CONF_PAIR_MODE) != PAIR_MODE_SINGLE_ADDRESS
        )
        if separate_address_pair:
            # Per-side settings (motor count, massage, adapter, angle limits)
            # live in the child descriptors, not parent data. Show the first
            # side's real values so the form isn't generic defaults; on save,
            # only the keys the user actually changed propagate (see below), so
            # untouched values can't clobber the other side's per-side settings.
            first_child = next(iter(iter_children(current_data)), None)
            if first_child is not None:
                current_data = {**current_data, **first_child}
        # Pending values preserve edits while the form is rebuilt to show the
        # fields that belong to a newly selected bed type. They are applied last
        # so a pending edit wins over the stored (or per-side) value it replaces.
        if CONF_VMATBASIC_PROFILE in self._pending_data and self._pending_data[
            CONF_VMATBASIC_PROFILE
        ] != current_data.get(CONF_VMATBASIC_PROFILE):
            for key in VMATBASIC_CONFIG_KEYS - {CONF_VMATBASIC_PROFILE}:
                current_data.pop(key, None)
        current_data = {**current_data, **self._pending_data}
        bed_type: str = current_data.get(CONF_BED_TYPE) or BED_TYPE_DIAGNOSTIC

        variants = get_variants_for_bed_type(bed_type)
        form_variant = self._variant_for_bed_type(bed_type, current_data)
        shown_choice = bed_type_choice(bed_type, form_variant)
        if user_input is not None:
            _apply_bed_type_choice(user_input, shown_choice)
        has_position_feedback = bed_type_has_position_feedback(bed_type, form_variant)
        motor_count_options = _motor_count_options(bed_type, form_variant)
        try:
            form_motor_count = int(current_data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT))
        except TypeError, ValueError:
            form_motor_count = DEFAULT_MOTOR_COUNT
        if form_motor_count not in motor_count_options:
            form_motor_count = _default_motor_count(
                bed_type,
                current_data.get(CONF_NAME),
            )
            if form_motor_count not in motor_count_options:
                form_motor_count = motor_count_options[0]

        adapters = get_available_adapters(self.hass)

        # Global discovery toggle (shared across all beds, not stored per-entry)
        discovery_disabled = self._pending_data.get(
            CONF_DISABLE_DISCOVERY,
            await async_is_discovery_disabled(self.hass),
        )

        context = FlowContext(self.hass, self.config_entry.entry_id)

        def fields(*keys: str) -> dict[vol.Marker, Any]:
            return _settings_fields(
                self.hass,
                {**current_data, CONF_MOTOR_COUNT: form_motor_count},
                bed_type,
                form_variant,
                keys,
            )

        schema_dict: dict[vol.Marker, Any] = {
            **dict([_bed_type_field(vol.Optional, shown_choice, show_saved_id=True)]),
            **fields(
                CONF_HAS_MASSAGE,
                CONF_PREFERRED_ADAPTER,
                CONF_CONNECTION_PROFILE,
                *_PULSE_FIELDS,
                CONF_DISCONNECT_AFTER_COMMAND,
                CONF_IDLE_DISCONNECT_SECONDS,
            ),
            vol.Optional(CONF_DISABLE_DISCOVERY, default=discovery_disabled): bool,
            **fields(CONF_MOTOR_COUNT),
        }
        if has_position_feedback:
            schema_dict.update(fields(CONF_DISABLE_ANGLE_SENSING, CONF_POSITION_MODE))
        if supports_passive_position_reconciliation(bed_type):
            schema_dict.update(fields(CONF_PASSIVE_POSITION_RECONCILIATION))

        # Add variant selection if the bed type has variants. Handsets that moved
        # to the FurniMove app profile stay selectable only for an entry using one.
        if variants:
            if bed_type == BED_TYPE_OKIN_DOT:
                variants = {
                    key: label
                    for key, label in variants.items()
                    if key not in OKIN_DOT_FURNIMOVE_VARIANTS or key == form_variant
                }
            schema_dict[
                vol.Optional(
                    CONF_PROTOCOL_VARIANT,
                    default=form_variant,
                )
            ] = vol.In(variants)

        if bed_type == BED_TYPE_REVERIE_PAIRLINK and not separate_address_pair:
            schema_dict.update(_pairlink_settings_schema(self.hass, current_data))

        # Each route's own fields are on the form, shown only for that route.
        route_rows = {
            variant: (bed_type, variant)
            for variant in (SVANE_VARIANTS if bed_type == BED_TYPE_SVANE else variants or {})
        }
        # An app's own fields may ask a generic field its route sets, so the
        # generic ones it owns wait until those fields are in.
        held = {
            marker: schema_dict.pop(marker)
            for marker in tuple(schema_dict)
            if marker.schema in hidden_generic_fields(bed_type, form_variant)
        }
        # A two-address pair's shared form never shows one side's app settings.
        leggett_routes = _rows_where(
            route_rows, _is_leggett_app_type, field=CONF_PROTOCOL_VARIANT
        )
        if not separate_address_pair:
            if leggett_routes is not None:
                leggett: dict[vol.Marker, Any] = {}
                _add_leggett_app_schema_field(leggett, current_data)
                schema_dict.update(_shown_for(leggett, leggett_routes))
            elif _is_leggett_app_type(bed_type, form_variant):
                _add_leggett_app_schema_field(schema_dict, current_data)
            elif (
                questions := _configure_questions(
                    {**current_data, CONF_BED_TYPE: bed_type},
                    self.config_entry.data.get(CONF_BED_TYPE),
                )
            ) is not None:
                schema_dict.update(
                    _profile_question_schema(
                        questions, current_data, context, advanced_section=False
                    )
                )

        asked = {marker.schema for marker in schema_dict} & {marker.schema for marker in held}
        schema_dict.update(
            {marker: validator for marker, validator in held.items() if marker.schema not in asked}
        )
        _show_profile_fields(
            schema_dict,
            bed_type,
            form_variant,
            route_rows or None,
            CONF_PROTOCOL_VARIANT,
            keep=asked,
        )

        # Angle limits apply to beds that report angles, not percentages.
        if bed_type not in BEDS_WITH_PERCENTAGE_POSITIONS and has_position_feedback:
            schema_dict.update(fields(*_ANGLE_LIMITS))

        if user_input is not None:
            # HA's select control uses string values; keep persisted counts numeric.
            # A managed family changes app or layout only through the guided change.
            original_type = self.config_entry.data.get(CONF_BED_TYPE)
            selected_type = user_input.get(CONF_BED_TYPE, original_type)
            family = next(
                (family for family in MANAGED_FAMILIES if original_type in family.bed_types),
                None,
            )
            original_profile = {**self.config_entry.data, **self.config_entry.options}
            if original_type == BED_TYPE_VIBRADORM_APP:
                original_profile = _vibradorm_app_data(original_profile, {})
            elif original_type == BED_TYPE_VMATBASIC:
                original_profile = _vmatbasic_data(original_profile, {})
            # The form shows an unsaved variant as the route the entry runs.
            if isinstance(original_type, str):
                original_profile.setdefault(
                    CONF_PROTOCOL_VARIANT,
                    self._variant_for_bed_type(original_type, original_profile),
                )
            if _is_leggett_app_type(original_type, original_profile.get(CONF_PROTOCOL_VARIANT)):
                # An entry saved before app profiles runs the default one.
                original_profile.setdefault(CONF_LEGGETT_APP_PROFILE, LEGGETT_APP_DEFAULT_PROFILE)
            if (
                not separate_address_pair
                and family is not None
                and selected_type in family.bed_types
                and (
                    selected_type != original_type
                    or any(
                        key in user_input and user_input[key] != original_profile.get(key)
                        for key in family.route_keys
                    )
                )
            ):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "migration_reconfigure_required"},
                )
            if CONF_MOTOR_COUNT in user_input:
                user_input = {**user_input, CONF_MOTOR_COUNT: int(user_input[CONF_MOTOR_COUNT])}
            requested_bed_type = user_input.get(CONF_BED_TYPE, bed_type)
            requested_route = user_input.get(CONF_PROTOCOL_VARIANT, form_variant)
            if separate_address_pair:
                # Check every stored side, not only the representative one: a
                # rebuilt form must not hide another side's own app profile.
                # A field this form does not show can only be a side's own setting.
                shown_values = _shown_option_values(schema_dict)
                changes = {
                    **self._pending_changed_data,
                    **{
                        key: value
                        for key, value in user_input.items()
                        if key not in shown_values or value != shown_values[key]
                    },
                }
                if refusal := _per_side_refusal(
                    (requested_bed_type, requested_route),
                    [
                        (child.get(CONF_BED_TYPE), child.get(CONF_PROTOCOL_VARIANT))
                        for child in iter_children(self.config_entry.data)
                    ],
                    changes,
                ):
                    field, profile = refusal
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors={
                            field if vol.Optional(field) in schema_dict else "base": (
                                "app_profile_unpair_first"
                            )
                        },
                        description_placeholders={"profile": profile},
                    )
            if requested_bed_type != bed_type:
                # Re-render once using the selected protocol so its variant,
                # authentication, layout, remote, and position fields are
                # visible before anything is persisted.
                self._remember_pending_changes(schema_dict, user_input)
                self._pending_data = {
                    **self._pending_data,
                    **user_input,
                    CONF_BED_TYPE: requested_bed_type,
                }
                requested_variant = self._variant_for_bed_type_change(
                    bed_type,
                    requested_bed_type,
                    self._pending_data,
                )
                chosen_variant = user_input.get(CONF_PROTOCOL_VARIANT)
                if (
                    isinstance(chosen_variant, str)
                    and (requested_bed_type, chosen_variant) in APP_VARIANT_CHOICES
                ):
                    # The user picked that app's own entry; its variant is the route.
                    requested_variant = chosen_variant
                if get_variants_for_bed_type(requested_bed_type):
                    self._pending_data[CONF_PROTOCOL_VARIANT] = requested_variant
                    self._pending_changed_data[CONF_PROTOCOL_VARIANT] = requested_variant
                else:
                    self._pending_data.pop(CONF_PROTOCOL_VARIANT, None)
                requested_motor_options = _motor_count_options(
                    requested_bed_type,
                    requested_variant,
                )
                requested_motor_count = self._pending_data.get(
                    CONF_MOTOR_COUNT,
                    DEFAULT_MOTOR_COUNT,
                )
                if requested_motor_count not in requested_motor_options:
                    requested_motor_count = _default_motor_count(
                        requested_bed_type,
                        current_data.get(CONF_NAME),
                    )
                    if requested_motor_count not in requested_motor_options:
                        requested_motor_count = requested_motor_options[0]
                self._pending_data[CONF_MOTOR_COUNT] = requested_motor_count
                self._pending_changed_data[CONF_MOTOR_COUNT] = requested_motor_count
                pulse_count, pulse_delay = get_motor_pulse_defaults(
                    requested_bed_type,
                    requested_variant,
                )
                self._pending_data[CONF_MOTOR_PULSE_COUNT] = pulse_count
                self._pending_data[CONF_MOTOR_PULSE_DELAY_MS] = pulse_delay
                disable_angle_sensing = not bed_type_has_position_feedback(
                    requested_bed_type,
                    requested_variant,
                )
                self._pending_data[CONF_DISABLE_ANGLE_SENSING] = disable_angle_sensing
                self._pending_changed_data.update(
                    {
                        CONF_MOTOR_PULSE_COUNT: pulse_count,
                        CONF_MOTOR_PULSE_DELAY_MS: pulse_delay,
                        CONF_DISABLE_ANGLE_SENSING: disable_angle_sensing,
                    }
                )
                return await self._async_options_form(None, step_id=step_id)

            bed_type = requested_bed_type
            stale_profile_keys: frozenset[str] = frozenset()
            # What the declared profile sets itself, such as the generic fields it
            # owns. A paired save keeps only shown fields that changed, so these
            # are applied separately.
            profile_settled: dict[str, Any] = {}
            if bed_type == BED_TYPE_REVERIE_PAIRLINK and not separate_address_pair:
                pairlink_errors = _validate_pairlink_option_values(
                    self.hass,
                    current_data,
                    user_input,
                )
                if pairlink_errors:
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors=pairlink_errors,
                    )
            # The discovery toggle is global, not per-entry: pull it out of
            # user_input now so it is never written into entry data, but only
            # persist it on the success path below - otherwise a later
            # validation failure would partially apply the rejected form.
            pending_discovery = self._pending_data.get(CONF_DISABLE_DISCOVERY)
            discovery_disabled_input = (
                bool(pending_discovery) if isinstance(pending_discovery, bool) else None
            )
            if CONF_DISABLE_DISCOVERY in user_input:
                discovery_disabled_input = bool(user_input.pop(CONF_DISABLE_DISCOVERY))
            requested_variant = self._variant_for_bed_type(
                bed_type,
                {**current_data, **user_input},
            )
            # The form showed these for the drawn route; the selected one sets them.
            owned = hidden_generic_fields(bed_type, requested_variant)
            for key in owned - hidden_generic_fields(bed_type, form_variant) - {
                CONF_PROTOCOL_VARIANT
            }:
                user_input.pop(key, None)
            # Shared edits must be compatible with every separate-address side,
            # including a product that is absent from the representative side.
            shown = _shown_option_values(schema_dict)
            paired_changes = {
                **self._pending_changed_data,
                **{
                    key: value
                    for key, value in user_input.items()
                    if key in shown and shown[key] != value
                },
            }
            incompatible_child = any(
                child.get(CONF_BED_TYPE) == BED_TYPE_RICHMAT
                and not _is_valid_rmcontrol_variant(
                    child.get(CONF_RMCONTROL_PRODUCT),
                    self._variant_for_bed_type(BED_TYPE_RICHMAT, child),
                )
                for original_child in iter_children(self.config_entry.data)
                for child in [{**original_child, **paired_changes}]
            )
            if incompatible_child or (
                bed_type == BED_TYPE_RICHMAT
                and not _is_valid_rmcontrol_variant(
                    user_input.get(
                        CONF_RMCONTROL_PRODUCT, current_data.get(CONF_RMCONTROL_PRODUCT)
                    ),
                    requested_variant,
                )
            ):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={CONF_PROTOCOL_VARIANT: "invalid_variant_for_bed_type"},
                )
            # Switching a bed to an app that does not list its model would only
            # trade its controls for the fallback ones. Keeping the current app
            # is allowed, so a bed on the fallback controls can still save other
            # options. Pairs refuse any app change above.
            remacro_error: str | None = None
            remacro_address = current_data.get(CONF_ADDRESS)
            if (
                bed_type == BED_TYPE_REMACRO
                and not separate_address_pair
                and isinstance(remacro_address, str)
                and app_for_variant(requested_variant)
                != app_for_variant(self.config_entry.data.get(CONF_PROTOCOL_VARIANT))
            ):
                problem, _ = remacro_entry_problem(
                    {**current_data, CONF_PROTOCOL_VARIANT: requested_variant},
                    remacro_manufacturer_data(self.hass, remacro_address),
                )
                if problem == "not_in_app":
                    remacro_error = "remacro_model_not_in_app"
            if remacro_error is None and bed_type in RICHMAT_MH_APPS:
                # Each Richmat MH bed resolves its model from its stored raw name.
                for target in [*iter_children(current_data)] or [current_data]:
                    stored_name = target.get(CONF_BLE_DEVICE_NAME)
                    remacro_error = _richmat_mh_variant_error(
                        bed_type,
                        requested_variant,
                        stored_name if isinstance(stored_name, str) else None,
                    )
                    if remacro_error is not None:
                        break
            if remacro_error is not None:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={CONF_PROTOCOL_VARIANT: remacro_error},
                )
            if variants:
                user_input[CONF_PROTOCOL_VARIANT] = requested_variant
            else:
                user_input.pop(CONF_PROTOCOL_VARIANT, None)
            requested_motor_options = _motor_count_options(
                bed_type,
                requested_variant,
            )
            requested_motor_count = user_input.get(
                CONF_MOTOR_COUNT,
                form_motor_count,
            )
            if requested_motor_count not in requested_motor_options:
                if requested_variant != form_variant:
                    # A variant change can alter the fixed actuator count.
                    # Rebuild with its count instead of rejecting the value
                    # rendered for the previous variant.
                    self._pending_data = {**self._pending_data, **user_input}
                    if discovery_disabled_input is not None:
                        self._pending_data[CONF_DISABLE_DISCOVERY] = discovery_disabled_input
                    self._remember_pending_changes(schema_dict, user_input)
                    self._pending_data[CONF_MOTOR_COUNT] = requested_motor_options[0]
                    self._pending_changed_data[CONF_MOTOR_COUNT] = requested_motor_options[0]
                    return await self._async_options_form(None, step_id=step_id)
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={CONF_MOTOR_COUNT: "invalid_motor_count_for_bed_type"},
                )
            # A profile can hide this field; still persist its normalized default.
            user_input[CONF_MOTOR_COUNT] = requested_motor_count
            if has_position_feedback != bed_type_has_position_feedback(
                bed_type,
                requested_variant,
            ):
                # Rebuild once more when the chosen variant changes position
                # capability, so the user sees the new sensing default and can
                # still explicitly override it on the following submission.
                self._remember_pending_changes(schema_dict, user_input)
                self._pending_data = {**self._pending_data, **user_input}
                if discovery_disabled_input is not None:
                    self._pending_data[CONF_DISABLE_DISCOVERY] = discovery_disabled_input
                disable_angle_sensing = not bed_type_has_position_feedback(
                    bed_type,
                    requested_variant,
                )
                self._pending_data[CONF_DISABLE_ANGLE_SENSING] = disable_angle_sensing
                self._pending_changed_data[CONF_DISABLE_ANGLE_SENSING] = disable_angle_sensing
                return await self._async_options_form(None, step_id=step_id)
            if _is_leggett_app_type(bed_type, requested_variant) and not separate_address_pair:
                profile = user_input.get(
                    CONF_LEGGETT_APP_PROFILE, current_data.get(CONF_LEGGETT_APP_PROFILE)
                )
                if profile is not None:
                    if profile not in LEGGETT_APP_PROFILES:
                        return self.async_show_form(
                            step_id=step_id,
                            data_schema=vol.Schema(schema_dict),
                            errors={CONF_LEGGETT_APP_PROFILE: "leggett_app_invalid_profile"},
                        )
                    user_input[CONF_MOTOR_COUNT] = LEGGETT_APP_MOTOR_COUNTS[profile]
            if not separate_address_pair and (
                declared := _configure_questions(
                    {**current_data, CONF_BED_TYPE: bed_type},
                    self.config_entry.data.get(CONF_BED_TYPE),
                )
            ) is not None:
                answers = _profile_answers(declared, user_input, current_data, context)
                # The answers apply to the saved setup, as setup applies them to
                # the staged one, so a profile can tell what they change.
                before = {
                    **current_data,
                    **{key: value for key, value in user_input.items() if key not in answers},
                }
                app_data = declared.staged(before, answers)
                if app_errors := declared.errors(app_data, context):
                    return self.async_show_form(
                        step_id=step_id, data_schema=vol.Schema(schema_dict), errors=app_errors
                    )
                # The answers, and whatever normalizing corrected, are saved.
                for key in answers.keys() - app_data.keys():
                    user_input.pop(key, None)
                user_input.update(
                    {
                        key: value
                        for key, value in app_data.items()
                        if key in answers or before.get(key) != value
                    }
                )
                # An answer that picks the route, such as MC3, settles what that
                # route's own profile owns.
                profile_settled = (setup_profile_for(app_data) or declared).settled(app_data)
                user_input.update(profile_settled)
                # What normalizing dropped, such as retained settings an answer no
                # longer allows or an Auto choice stored as no value, leaves the
                # saved entry too, even when the form submitted it.
                stale_profile_keys = (frozenset(before) | answers.keys()) - frozenset(app_data)
            elif not separate_address_pair and (
                owner := setup_profile_for({**current_data, **user_input, CONF_BED_TYPE: bed_type})
            ) is not None:
                # A profile without questions still fixes the generic fields it
                # owns, such as MC3's missing massage, even when an entry
                # switches in from a bed type that had them on.
                user_input.update(owner.fixed_values())
            if bed_type == BED_TYPE_SVANE:
                svane_variant = user_input.get(
                    CONF_PROTOCOL_VARIANT, current_data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO)
                )
                if svane_variant not in SVANE_VARIANTS:
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors={"base": "invalid_variant"},
                    )
                if svane_variant != SVANE_VARIANT_JENSEN_LINON:
                    user_input.update(
                        {
                            CONF_MOTOR_COUNT: 2,
                            CONF_HAS_MASSAGE: False,
                            CONF_DISABLE_ANGLE_SENSING: True,
                            CONF_MOTOR_PULSE_USER_SET: False,
                        }
                    )
            if self.config_entry.data.get(
                CONF_PAIR_MODE
            ) == PAIR_MODE_SINGLE_ADDRESS and not supports_single_address_pairing(
                bed_type,
                user_input.get(
                    CONF_PROTOCOL_VARIANT,
                    current_data.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT),
                ),
                resolved_variant=current_data.get(CONF_KAIDI_RESOLVED_VARIANT),
                product_type=user_input.get(CONF_PRODUCT_TYPE, current_data.get(CONF_PRODUCT_TYPE)),
                ble_device_name=user_input.get(CONF_BLE_DEVICE_NAME, current_data.get(CONF_BLE_DEVICE_NAME)),
            ):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "single_address_pairing_unsupported"},
                )
            parsed, setting_errors = _parse_settings(
                user_input, bed_type, get_motor_pulse_defaults(bed_type, requested_variant)
            )
            if setting_errors:
                return self.async_show_form(
                    step_id=step_id, data_schema=vol.Schema(schema_dict), errors=setting_errors
                )
            user_input.update(parsed)

            async def commit_global_settings() -> ConfigFlowResult | None:
                """Apply global and hardware changes before confirming the review."""
                if not separate_address_pair and BED_TYPE_LIMOSS_REMOTE in (
                    bed_type,
                    self.config_entry.data.get(CONF_BED_TYPE),
                ):
                    from .coordinator import AdjustableBedCoordinator

                    runtime = self._bond_target_coordinator()
                    previous = (
                        runtime.entry.data
                        if isinstance(runtime, AdjustableBedCoordinator)
                        else self.config_entry.data
                    )
                    kept = _limoss_remote_features_left(
                        previous, {**user_input, CONF_BED_TYPE: bed_type}
                    )
                    if kept is not None and not await _async_turn_off_limoss_remote_features(
                        runtime, *kept
                    ):
                        return self.async_show_form(
                            step_id=step_id,
                            data_schema=vol.Schema(schema_dict),
                            errors={"base": "limoss_remote_feature_update_failed"},
                        )
                if discovery_disabled_input is not None:
                    await async_set_discovery_disabled(self.hass, discovery_disabled_input)
                return None

            # Update the config entry with new options
            # Record that the stored cadence is the user's choice rather than a
            # value the flow generated, so protocol migrations leave it alone.
            # Only displayed pulse fields count; app profiles can inject their
            # fixed cadence into user_input without offering a user override.
            pulse_user_set = any(
                field in user_input and vol.Optional(field) in schema_dict
                for field in (CONF_MOTOR_PULSE_COUNT, CONF_MOTOR_PULSE_DELAY_MS)
            )
            from .profile_recommendations import (
                async_complete_profile_review,
                async_confirm_profile_review,
            )

            if is_paired(self.config_entry.data):
                # For a paired bed, ONLY the keys the user actually changed go
                # anywhere. "Changed" is measured against the value the form
                # ACTUALLY SHOWED (the schema default, seeded from the
                # representative child / parent data, and validated/coerced the
                # same way user_input was). Writing the whole form (incl.
                # unchanged defaults) to parent data would also leak into the
                # children, since _build_paired_children treats parent data as
                # shared fields for any key a child descriptor doesn't store.
                shown = _shown_option_values(schema_dict)
                current_changed = {
                    key: value
                    for key, value in user_input.items()
                    if key in shown and shown[key] != value
                }
                changed = {
                    **self._pending_changed_data,
                    **current_changed,
                    **{
                        key: value
                        for key, value in profile_settled.items()
                        if self.config_entry.data.get(key) != value
                    },
                }
                new_data = {**self.config_entry.data, **changed}
                if pulse_user_set:
                    new_data[CONF_MOTOR_PULSE_USER_SET] = True
                if self.config_entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
                    self._apply_bed_type_change_cleanup(new_data, bed_type, requested_variant)
                    for key in stale_profile_keys:
                        new_data.pop(key, None)
                    if (commit_error := await commit_global_settings()) is not None:
                        return commit_error
                    self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                    await async_confirm_profile_review(
                        self.hass, self.config_entry, self.flow_id, new_data
                    )
                    async_complete_profile_review(self.hass, self.config_entry, self.flow_id)
                    return self.async_create_entry(title="", data={})
                submitted_adapter = user_input.get(CONF_PREFERRED_ADAPTER)
                for side in PAIR_SIDES:
                    child = get_child(new_data, side)
                    if child is None:
                        continue
                    child_changed = dict(changed)
                    # A child whose stored adapter has disappeared shows the
                    # 'auto' fallback; normalize it even though the submitted
                    # value looks unchanged vs that fallback, so a stale adapter
                    # doesn't linger.
                    stored_adapter = child.get(CONF_PREFERRED_ADAPTER)
                    if (
                        submitted_adapter is not None
                        and stored_adapter is not None
                        and stored_adapter not in adapters
                    ):
                        child_changed[CONF_PREFERRED_ADAPTER] = submitted_adapter
                    if child_changed:
                        new_data = with_updated_child(new_data, side, child_changed)
            else:
                new_data = {**self.config_entry.data, **self._pending_data, **user_input}
                if pulse_user_set:
                    new_data[CONF_MOTOR_PULSE_USER_SET] = True
            self._apply_bed_type_change_cleanup(new_data, bed_type, requested_variant)
            for key in stale_profile_keys:
                new_data.pop(key, None)
            if bed_type == BED_TYPE_VIBRADORM_APP and any(
                new_data.get(key) != self.config_entry.data.get(key)
                for key in (
                    CONF_VIBRADORM_APP_PROFILE,
                    CONF_VIBRADORM_CONTROL_TYPE,
                    CONF_VIBRADORM_VMAT_REMOTE,
                )
            ):
                new_data.pop(CONF_VIBRADORM_APP_METADATA, None)
            if (commit_error := await commit_global_settings()) is not None:
                return commit_error
            if not separate_address_pair and (
                bed_type == BED_TYPE_VIBRADORM_APP
                or self.config_entry.data.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM_APP
            ):
                selection_changed = any(
                    new_data.get(key) != self.config_entry.data.get(key)
                    for key in (
                        CONF_BED_TYPE,
                        CONF_VIBRADORM_APP_PROFILE,
                        CONF_VIBRADORM_CONTROL_TYPE,
                        CONF_VIBRADORM_VMAT_REMOTE,
                    )
                ) or (
                    new_data.get(CONF_VIBRADORM_RESTORED, False)
                    != self.config_entry.data.get(CONF_VIBRADORM_RESTORED, False)
                )
                if selection_changed:
                    from .vibradorm_app_state import (
                        clear_vibradorm_app_session_intent,
                        mark_vibradorm_app_selection,
                    )

                    address = new_data.get(CONF_ADDRESS)
                    if isinstance(address, str):
                        clear_vibradorm_app_session_intent(self.hass, address)
                        if (
                            bed_type == BED_TYPE_VIBRADORM_APP
                            and new_data.get(CONF_VIBRADORM_APP_PROFILE) != "vmat"
                            and not new_data.get(CONF_VIBRADORM_RESTORED, False)
                        ):
                            control = new_data[CONF_VIBRADORM_CONTROL_TYPE]
                            mark_vibradorm_app_selection(
                                self.hass,
                                address,
                                app_profile=new_data[CONF_VIBRADORM_APP_PROFILE],
                                control_type="other" if control == "other" else int(control),
                                remembered_floor_default=new_data[CONF_VIBRADORM_FLOOR_DEFAULT],
                            )
            if any(
                new_data.get(key) != self.config_entry.data.get(key)
                for key in (
                    CONF_STARCODE_M5X5_PROFILE,
                    CONF_STARCODE_M1X12_PROFILE,
                    CONF_PROTOCOL_VARIANT,
                    CONF_BLE_DEVICE_NAME,
                    CONF_STARCODE_LIFT_ENTRIES,
                )
            ):
                from .starcode_accessory_group import cancel_group_operations

                cancel_group_operations(self.hass, self.config_entry.entry_id)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            await async_confirm_profile_review(self.hass, self.config_entry, self.flow_id, new_data)
            async_complete_profile_review(self.hass, self.config_entry, self.flow_id)
            # A failed or retrying entry has no update listener yet, so a fix made
            # here (for example a Remacro app that lists the model) would not apply.
            if self.config_entry.state in (
                ConfigEntryState.SETUP_ERROR,
                ConfigEntryState.SETUP_RETRY,
            ):
                self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_dict),
        )

    # ------------------------------------------------------------------
    # Remove the Bluetooth bond (issue #455)
    #
    # Removing a bond is destructive and transport-specific, so it is gated on
    # three things: the bond must be shown to live on this host, the user must
    # confirm having seen which transport that is, and the removal must be
    # confirmed afterwards before anything is reported as done.
    # ------------------------------------------------------------------

    def _bond_target_data(self) -> dict[str, Any]:
        """Return the exact entry data backing the selected bond address."""
        side = self._bond_removal_side
        if side is None:
            data = dict(self.config_entry.data)
        else:
            data = effective_child_data(
                self.config_entry.data,
                side,
                self.config_entry.options,
            )
        address = data.get(CONF_ADDRESS)
        if isinstance(address, str):
            data[CONF_ADDRESS] = address.strip().upper()
        return data

    def _bond_target_coordinator(self) -> Any | None:
        """Return the coordinator whose locks and runtime state own the target."""
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        side = self._bond_removal_side
        if coordinator is None or side is None:
            return coordinator
        child_for_side = getattr(coordinator, "child_for_side", None)
        return child_for_side(side) if callable(child_for_side) else None

    async def async_step_remove_bond_side(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one unambiguous child address from a combined bed."""
        choices: dict[str, str] = {}
        address_sides: dict[str, list[str]] = {}
        for side in PAIR_SIDES:
            child = get_child(self.config_entry.data, side)
            if child is None:
                continue
            raw_address = child.get(CONF_ADDRESS)
            address = raw_address.strip().upper() if isinstance(raw_address, str) else ""
            if not address:
                return self._async_abort_bond_removal(
                    "ambiguous",
                    self.config_entry.title,
                    str(self.config_entry.data.get(CONF_ADDRESS, "")),
                    BondOwner(),
                )
            address_sides.setdefault(address, []).append(side)
            name = child.get(CONF_NAME) or side.title()
            choices[side] = f"{side.title()}: {name} ({address})"

        if not choices or any(len(sides) > 1 for sides in address_sides.values()):
            return self._async_abort_bond_removal(
                "ambiguous",
                self.config_entry.title,
                str(self.config_entry.data.get(CONF_ADDRESS, "")),
                BondOwner(),
            )

        if len(choices) == 1:
            self._bond_removal_side = next(iter(choices))
            return await self.async_step_remove_bond()

        if user_input is not None:
            submitted_side = user_input.get("side")
            if isinstance(submitted_side, str) and submitted_side in choices:
                self._bond_removal_side = submitted_side
                return await self.async_step_remove_bond()

        return self.async_show_form(
            step_id="remove_bond_side",
            data_schema=vol.Schema({vol.Required("side"): vol.In(choices)}),
        )

    async def _async_bond_situation(self) -> tuple[LocalBondInventory, BondOwner]:
        """Return the host's bond records and the owner we have on record."""
        data = self._bond_target_data()
        address = data.get(CONF_ADDRESS, "")
        inventory = await async_read_local_bonds(address)
        return inventory, bond_owner_from_entry(data)

    async def async_step_remove_bond(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain exactly what will be removed and ask for confirmation.

        The record is identified once, when the confirmation is rendered, and
        pinned. On submission the inventory is read again and the pinned record
        must still be there unchanged. Without that, the bond shown to the user
        and the bond actually removed are two separate lookups, and anything
        that changes BlueZ in between (another adapter pairing, a bond removed
        elsewhere) means removing something the user never saw.
        """
        if (
            self.config_entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SEPARATE_ADDRESS
            and self._bond_removal_side is None
        ):
            return await self.async_step_remove_bond_side(user_input)

        target_data = self._bond_target_data()
        inventory, owner = await self._async_bond_situation()
        name = target_data.get(CONF_NAME) or self.config_entry.title
        address = target_data.get(CONF_ADDRESS, "")

        # Proxy-owned bonds are refused before anything else: the host cannot
        # reach them, and a destructive button that quietly does nothing to the
        # bond the user has in mind is worse than no button.
        if owner.transport is TransportClass.PROXY:
            return self._async_abort_bond_removal("proxy_owned", name, address, owner)

        selection_source = owner.source
        selection_adapter = owner.adapter
        if not owner.is_host:
            # No recorded owner, which is every entry paired before provenance
            # existed. The host's own BlueZ still holds a record for this exact
            # address, so there is something concrete to remove, but if the bed
            # is currently routing through a proxy then the bond that matters to
            # the user lives there and this one is a leftover. Refuse rather
            # than act on a guess about which the user means.
            prediction = async_predict_path(
                self.hass,
                address,
                target_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
            )
            if (
                prediction.chosen is not None
                and prediction.chosen.transport is TransportClass.PROXY
            ):
                return self._async_abort_bond_removal("proxy_owned", name, address, owner)
            if (
                prediction.chosen is not None
                and prediction.chosen.transport is TransportClass.LOCAL
            ):
                # Legacy entries do not name the bond owner. A proven local
                # connection path supplies the same adapter identifiers newer
                # entries persist, so an explicitly selected adapter can still
                # disambiguate two host bonds.
                selection_source = prediction.chosen.source
                selection_adapter = prediction.chosen.adapter

        selection = select_local_bond(
            inventory,
            owner_source=selection_source,
            owner_adapter=selection_adapter,
        )
        if selection.status is BondSelectionStatus.UNREADABLE:
            return self._async_abort_bond_removal("bluez_unavailable", name, address, owner)
        if selection.status is BondSelectionStatus.NO_BOND:
            return self._async_abort_bond_removal("no_bond", name, address, owner)
        if selection.status is BondSelectionStatus.AMBIGUOUS:
            return self._async_abort_bond_removal("ambiguous", name, address, owner)
        if selection.status is BondSelectionStatus.UNKNOWN_OWNER:
            # Provenance names an adapter that no longer holds a bond for this
            # bed. Acting anyway would mean removing a record nothing pointed at.
            return self._async_abort_bond_removal("ambiguous", name, address, owner)

        record = selection.record
        assert record is not None

        if user_input is not None:
            pinned = self._bond_removal_record
            if pinned is None or not self._same_bond_record(pinned, record):
                # The host's bond state moved between showing the confirmation
                # and acting on it. Re-confirm rather than remove something else.
                self._bond_removal_record = None
                return self._async_abort_bond_removal("changed", name, address, owner)
            self.async_begin_operation(
                name=name,
                address=address,
                action=SetupAction.UNPAIRING,
                placeholders={"name": name, "address": address},
            )
            return await self.async_step_remove_bond_progress()

        # Pin what is being shown, so the submission can prove it is the same.
        self._bond_removal_record = record
        return self.async_show_form(
            step_id="remove_bond",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": name,
                "address": address,
                "transport": record.adapter_address or record.adapter_path,
                "provenance": (
                    ""
                    if owner.is_host
                    else (
                        "\n\n⚠️ Home Assistant has no record of which transport created "
                        "this bond, because it predates that being tracked. This is the "
                        "only Bluetooth bond this host holds for that address."
                    )
                ),
            },
        )

    def _async_abort_bond_removal(
        self, reason: str, name: str, address: str, owner: BondOwner
    ) -> ConfigFlowResult:
        """Abort the removal with an explanation of why it is not offered."""
        return self.async_abort(
            reason=f"remove_bond_{reason}",
            description_placeholders={
                "name": name,
                "address": address,
                "transport": owner.source or str(owner.transport),
            },
        )

    @staticmethod
    def _same_bond_record(pinned: LocalBondRecord, current: LocalBondRecord) -> bool:
        """Return True when two reads describe the same BlueZ device object."""
        return pinned.is_same_bond_as(current)

    async def _async_bond_removal_worker(self) -> OperationResult:
        """Stop using the bed, then remove the bond and confirm it is gone."""
        record = self._bond_removal_record
        assert record is not None

        coordinator = self._bond_target_coordinator()
        if coordinator is None:
            # No coordinator to quiesce, but the address still has to be held:
            # a config or repair flow could otherwise connect to this bed while
            # its bond is being removed.
            async with async_get_connect_lock(self.hass, record.address):
                return await self._async_remove_and_apply(record)

        # Hold the bed out of use for the whole transaction, through the
        # coordinator's own locking order. Releasing the locks before the
        # removal would let a command reconnect midway; composing public methods
        # from here would let the removal take the address lock while a command
        # already holds the command lock and is waiting for it.
        try:
            async with coordinator.async_transport_operation("unpair"):
                return await self._async_remove_and_apply(record)
        except Exception as err:  # noqa: BLE001 - report, do not remove blindly
            _LOGGER.warning("Could not remove the bond for %s: %s", self.config_entry.title, err)
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_FAILED,
                detail=str(err) or err.__class__.__name__,
            )

    async def _async_remove_and_apply(self, record: LocalBondRecord) -> OperationResult:
        """Finish a started removal and persist its result before cancellation."""
        removal_task = self.hass.async_create_task(async_remove_local_bond(record))
        try:
            removal = await asyncio.shield(removal_task)
        except asyncio.CancelledError:
            # Once RemoveDevice may have been sent, cancellation cannot safely
            # abandon the verification read. Keep the surrounding transport
            # lock held, record a confirmed removal, then honor cancellation.
            removal = await removal_task
            result = self._bond_removal_result(removal)
            self._apply_confirmed_bond_removal(result)
            raise
        result = self._bond_removal_result(removal)
        self._apply_confirmed_bond_removal(result)
        return result

    def _apply_confirmed_bond_removal(self, result: OperationResult) -> None:
        """Clear persisted bond state immediately after confirmed removal."""
        if not result.succeeded or self._bond_removal_state_applied:
            return
        self._bond_removal_state_applied = True
        side = self._bond_removal_side
        if side is not None:
            parent = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
            child_for_side = getattr(parent, "child_for_side", None)
            child = child_for_side(side) if callable(child_for_side) else None
            apply_removal = getattr(child, "apply_confirmed_bond_removal", None)
            if callable(apply_removal):
                apply_removal()
                return
            data = with_updated_child(
                self.config_entry.data,
                side,
                {},
                remove=RUNTIME_BOND_KEYS,
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=data,
            )
            return
        coordinator = self._bond_target_coordinator()
        if coordinator is not None:
            coordinator.apply_confirmed_bond_removal()
            return
        data = dict(self.config_entry.data)
        for key in RUNTIME_BOND_KEYS:
            data.pop(key, None)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    async def _async_bond_removal_outcome_note(self, succeeded: bool, detail: str | None) -> str:
        """Describe the removal in the user's language."""
        if succeeded:
            return await _async_translation(
                self.hass,
                "options",
                "step.remove_bond.data_description.outcome_removed",
                "✅ The Bluetooth bond was removed and the removal was confirmed.",
            )
        template = await _async_translation(
            self.hass,
            "options",
            "step.remove_bond.data_description.outcome_failed",
            "❌ The bond was not removed ({reason}).",
        )
        return template.format(reason=detail or "unknown reason")

    @staticmethod
    def _bond_removal_result(result: BondRemovalResult) -> OperationResult:
        """Turn a bond-removal outcome into an operation result."""
        if not result.succeeded:
            return OperationResult(
                outcome=OperationOutcome.UNPAIR_FAILED,
                detail=result.error or str(result.status),
                payload=result,
            )
        return OperationResult(outcome=OperationOutcome.SUCCESS, payload=result)

    async def async_step_remove_bond_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run the bond removal as a tracked background operation."""
        return await self.async_run_operation_step(
            step_id="remove_bond_progress",
            worker=self._async_bond_removal_worker,
            next_step_id="remove_bond_result",
        )

    async def async_step_remove_bond_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Report the outcome after the worker has applied confirmed removal."""
        result = self.operation.result
        succeeded = result is not None and result.succeeded

        if result is not None:
            self._apply_confirmed_bond_removal(result)

        if user_input is not None and self._bond_removal_result_shown:
            return self.async_create_entry(title="", data={})

        detail = result.detail if result is not None else None
        self._bond_removal_result_shown = True
        return self.async_show_form(
            step_id="remove_bond_result",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._bond_target_data().get(CONF_NAME) or self.config_entry.title,
                "outcome": await self._async_bond_removal_outcome_note(succeeded, detail),
            },
        )
