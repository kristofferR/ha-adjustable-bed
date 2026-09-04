"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

import voluptuous as vol
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
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.helpers.translation import async_get_translations
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .actuator_groups import (
    ACTUATOR_GROUPS,
    SINGLE_TYPE_GROUPS,
)
from .adapter import (
    discover_services,
    find_service_info_by_address,
    get_discovered_service_info,
    read_ble_device_info,
)
from .address_lock import async_get_connect_lock
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
    bond_owner_from_entry,
    build_bond_context,
)
from .const import (
    ADAPTER_AUTO,
    ALL_PROTOCOL_VARIANTS,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_JENSEN,
    BED_TYPE_KAIDI,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SOLACE,
    BEDS_WITH_PERCENTAGE_POSITIONS,
    BEDS_WITH_POSITION_FEEDBACK,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_BLE_BOND_MARKER_UNRELIABLE,
    CONF_BLE_DEVICE_NAME,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_KAIDI_RESOLVED_VARIANT,
    CONF_LEGS_MAX_ANGLE,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_OCTO_PIN,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PASSIVE_POSITION_RECONCILIATION,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONNECTION_PROFILE_BALANCED,
    CONNECTION_PROFILE_RELIABLE,
    CONNECTION_PROFILES,
    DEFAULT_BACK_MAX_ANGLE,
    DEFAULT_CONNECTION_PROFILE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
    DEFAULT_LEGS_MAX_ANGLE,
    DEFAULT_MOTOR_COUNT,
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    DEFAULT_OCTO_PIN,
    DEFAULT_POSITION_MODE,
    DEFAULT_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_VARIANT_GEN2,
    MALOUF_LAYOUT_AUTO,
    MALOUF_LAYOUTS,
    MALOUF_MEMORY_SLOT_OPTIONS,
    MALOUF_MEMORY_SLOTS_AUTO,
    OCTO_VARIANT_STAR2,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    OKIN_CST_THREE_MOTOR_VARIANTS,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    POSITION_MODE_ACCURACY,
    POSITION_MODE_SPEED,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTES,
    RUNTIME_BOND_KEYS,
    VARIANT_AUTO,
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
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type,
    detect_bed_type_detailed,
    detect_richmat_remote_from_name,
    get_bed_type_options,
    is_mac_like_name,
)
from .discovery_log import async_get_discovery_log
from .discovery_settings import (
    async_is_discovery_disabled,
    async_set_discovery_disabled,
)
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .pairing import (
    KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS,
    build_pair_entry_data,
    build_single_address_pair_entry_data,
    effective_child_data,
    get_child,
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
from .setup_operation import (
    BluetoothOperationMixin,
    ConnectionLifetimePolicy,
    OperationOutcome,
    OperationResult,
    SetupAction,
)
from .unsupported import (
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

_LOGGER = logging.getLogger(__name__)

CONFIGURED_RETRY_PREFIX = "configured_retry::"

# Sentinel value for the "Auto-detect" entry in the full manual bed-type list.
# When chosen, the flow re-runs detection on the selected device instead of
# forcing the user to guess a protocol (and instead of silently defaulting to
# the first alphabetical entry). Must not collide with any real bed type.
BED_TYPE_AUTO_DETECT = "auto_detect"

# Minimum confidence for the manual "Auto-detect" flow to commit to a concrete
# bed type. Below this — or when the detection is ambiguous (shared-UUID guesses
# such as OKIN receivers) — we keep "Auto-detect" selected and ask the user to
# choose, rather than silently configuring a guessed protocol.
_AUTO_DETECT_MIN_CONFIDENCE = 0.7


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
    "auth_failed": (
        "❌ The bed connected, but the link is still unauthenticated, so the bond "
        "did not form. Put the bed back into pairing mode and select **Try "
        "again**."
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


def _motor_count_options(
    bed_type: str | None,
    protocol_variant: str = DEFAULT_PROTOCOL_VARIANT,
) -> list[int]:
    """Return motor counts supported by the selected protocol."""
    if bed_type == BED_TYPE_OCTO and protocol_variant != OCTO_VARIANT_STAR2:
        return [1, 2, 3, 4]
    if bed_type == BED_TYPE_OKIN_CST:
        return [3] if protocol_variant in OKIN_CST_THREE_MOTOR_VARIANTS else [2]
    return [2, 3, 4]


def _motor_count_options_for_all_variants(bed_type: str | None) -> list[int]:
    """Return the union of motor counts selectable across protocol variants."""
    variants = get_variants_for_bed_type(bed_type)
    if variants is None:
        return _motor_count_options(bed_type)
    return sorted(
        {
            motor_count
            for variant in variants
            for motor_count in _motor_count_options(bed_type, variant)
        }
    )


def _is_valid_motor_count(
    bed_type: str | None,
    protocol_variant: str,
    motor_count: int,
) -> bool:
    """Return whether a motor count is valid for the selected protocol."""
    return motor_count in _motor_count_options(bed_type, protocol_variant)


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
    """Return the motor-count default, recognizing OCTO RTV one-motor lifts."""
    if (
        bed_type == BED_TYPE_OCTO
        and device_name is not None
        and device_name.strip().lower().startswith("rtv")
    ):
        return 1
    if bed_type == BED_TYPE_OKIN_CST:
        return 3
    return DEFAULT_MOTOR_COUNT


def _confident_auto_detect(result: DetectionResult) -> str | None:
    """Return the detected bed type only for a high-confidence, unambiguous match.

    Used by the manual Auto-detect path so a low-confidence or ambiguous
    detection does not become a silent default/auto-resolution.
    """
    if (
        result.bed_type is not None
        and result.confidence >= _AUTO_DETECT_MIN_CONFIDENCE
        and not result.ambiguous_types
    ):
        return result.bed_type
    return None


CONNECTION_PROFILE_OPTIONS: dict[str, str] = {
    CONNECTION_PROFILE_BALANCED: "Balanced (recommended)",
    CONNECTION_PROFILE_RELIABLE: "Reliable (slower connect)",
}

MALOUF_BED_TYPES = frozenset({BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN})


def _add_malouf_schema_fields(schema: dict[vol.Marker, Any]) -> None:
    """Add physical-layout fields, kept deliberately separate from protocol."""
    schema[vol.Optional(CONF_MALOUF_LAYOUT, default=MALOUF_LAYOUT_AUTO)] = vol.In(MALOUF_LAYOUTS)
    schema[vol.Optional(CONF_MALOUF_MEMORY_SLOTS, default=MALOUF_MEMORY_SLOTS_AUTO)] = vol.All(
        vol.Coerce(int), vol.In(MALOUF_MEMORY_SLOT_OPTIONS)
    )


def _add_cb24_side_schema_field(schema: dict[vol.Marker, Any]) -> None:
    """Expose the legacy CB24 native A/B selector when the type is known."""
    schema[
        vol.Optional(CONF_CB24_BED_SELECTION, default=CB24_BED_SELECTION_DEFAULT)
    ] = vol.In(
        {
            CB24_BED_SELECTION_DEFAULT: "Both sides",
            CB24_BED_SELECTION_A: "Side A / Left",
            CB24_BED_SELECTION_B: "Side B / Right",
        }
    )


def _add_malouf_entry_data(
    entry_data: dict[str, Any], user_input: dict[str, Any], bed_type: str | None
) -> None:
    """Persist Malouf physical capabilities without deriving them from a model name."""
    if bed_type not in MALOUF_BED_TYPES:
        return
    entry_data[CONF_MALOUF_LAYOUT] = user_input.get(CONF_MALOUF_LAYOUT, MALOUF_LAYOUT_AUTO)
    entry_data[CONF_MALOUF_MEMORY_SLOTS] = int(
        user_input.get(CONF_MALOUF_MEMORY_SLOTS, MALOUF_MEMORY_SLOTS_AUTO)
    )


def _add_cb24_entry_data(
    entry_data: dict[str, Any], user_input: dict[str, Any], bed_type: str | None
) -> None:
    """Persist the native CB24 A/B selector when it was collected."""
    if bed_type == BED_TYPE_OKIN_CB24:
        entry_data[CONF_CB24_BED_SELECTION] = int(
            user_input.get(CONF_CB24_BED_SELECTION, CB24_BED_SELECTION_DEFAULT)
        )


# Short, single-attempt timeout for the optional setup-time connection probe.
# Keep this small so a failing probe (e.g. the phone app holding the bed's single
# BLE connection) never makes setup feel slow. The probe is best-effort and never
# blocks entry creation.
_PROBE_TIMEOUT_SECONDS = 15.0

# How long the setup probe waits for the bed to advertise before reporting it as
# absent. Deliberately shorter than the pairing wait: someone who just put a bed
# into pairing mode is standing at the bed and expects to wait, while someone
# finishing a setup form is not, and the result step offers Retry either way.
_PROBE_ADVERTISEMENT_WAIT_SECONDS = 10.0


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
    """Result of the read-only setup-time connection probe."""

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
    # a strict no-op for non-paired entries; see async_migrate_entry.
    VERSION = 4

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

    def _disconnect_after_command_choice(
        self,
        user_input: dict[str, Any],
        bed_type: str | None,
        protocol_variant: str | None,
        rendered_default: bool,
    ) -> bool | None:
        """Return the "disconnect after each command" value to persist.

        A submitted value that matches the rendered default is ambiguous when
        the user also changed to a protocol with the opposite default. Return
        None in that case so a second, bed-specific form can obtain an explicit
        choice. This preserves both an untouched default and an explicit choice
        that happens to equal the old default.
        """
        selected_default = disconnect_after_command_default_enabled(
            bed_type, protocol_variant
        )
        submitted = user_input.get(CONF_DISCONNECT_AFTER_COMMAND)
        if self._disconnect_choice_confirmed:
            return bool(submitted)
        if submitted is None:
            return selected_default
        if bool(submitted) == rendered_default and selected_default != rendered_default:
            return None
        return bool(submitted)

    def _disconnect_after_command_schema(self) -> vol.Schema:
        """Build the explicit disconnect-choice confirmation schema."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_DISCONNECT_AFTER_COMMAND,
                    default=self._pending_disconnect_default,
                ): bool,
            }
        )

    def _request_disconnect_after_command_choice(
        self,
        user_input: dict[str, Any],
        *,
        resume_step: str,
        bed_type: str | None,
        protocol_variant: str | None,
    ) -> ConfigFlowResult:
        """Ask again after the selected protocol's default is known."""
        self._pending_disconnect_input = dict(user_input)
        self._pending_disconnect_resume_step = resume_step
        self._pending_disconnect_default = disconnect_after_command_default_enabled(
            bed_type, protocol_variant
        )
        return self.async_show_form(
            step_id="disconnect_after_command",
            data_schema=self._disconnect_after_command_schema(),
        )

    async def async_step_disconnect_after_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an explicit connection-lifetime choice for the selected bed."""
        assert self._pending_disconnect_input is not None
        assert self._pending_disconnect_resume_step is not None

        if user_input is None:
            return self.async_show_form(
                step_id="disconnect_after_command",
                data_schema=self._disconnect_after_command_schema(),
            )

        resume_input = self._pending_disconnect_input
        resume_step = self._pending_disconnect_resume_step
        resume_input[CONF_DISCONNECT_AFTER_COMMAND] = user_input[
            CONF_DISCONNECT_AFTER_COMMAND
        ]
        self._pending_disconnect_input = None
        self._pending_disconnect_resume_step = None
        self._disconnect_choice_confirmed = True
        try:
            if resume_step == "bluetooth_confirm":
                return await self.async_step_bluetooth_confirm(resume_input)
            if resume_step == "manual_config":
                return await self.async_step_manual_config(resume_input)
            if resume_step == "manual_entry":
                return await self.async_step_manual_entry(resume_input)
            raise RuntimeError(f"Unknown disconnect choice resume step: {resume_step}")
        finally:
            self._disconnect_choice_confirmed = False

    @staticmethod
    def _needs_malouf_step(bed_type: str | None, user_input: dict[str, Any]) -> bool:
        """Return True when the Malouf layout/memory fields still need collecting.

        The layout and memory-slot fields are only shown inline when the form was
        built already knowing the bed is Malouf (pre-selected brand or a confident
        detection). When the user instead picks a Malouf protocol from the bed-type
        dropdown, the inline fields were never rendered, so ``user_input`` lacks
        them and we must collect them in a dedicated follow-up step. Otherwise the
        entry silently persists the default layout, dropping Hi-Lo / four-motor
        controls until the user discovers the options flow.
        """
        return bed_type in MALOUF_BED_TYPES and CONF_MALOUF_LAYOUT not in user_input

    async def _async_malouf_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Collect Malouf layout/memory fields, then finish setup."""
        assert self._manual_data is not None

        if user_input is not None:
            _add_malouf_entry_data(
                self._manual_data, user_input, self._manual_data.get(CONF_BED_TYPE)
            )
            return await self._finish_with_verify(
                self._manual_data,
                self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            )

        schema_dict: dict[vol.Marker, Any] = {}
        _add_malouf_schema_fields(schema_dict)
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_dict),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return AdjustableBedOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._all_ble_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._manual_data: dict[str, Any] | None = None
        # For two-tier actuator selection
        self._selected_actuator: str | None = None
        self._selected_bed_type: str | None = None
        self._selected_protocol_variant: str | None = None
        # For disambiguation UI when BLE detection is ambiguous
        self._disambiguation_types: list[str] | None = None
        self._disambiguated_bed_type: str | None = None
        self._show_full_bed_type_list: bool = False
        self._retrying_devices: dict[str, tuple[ConfigEntry, BluetoothServiceInfoBleak | None]] = {}
        # Carries the finalized entry across the optional verify_connection step
        self._pending_entry: dict[str, Any] | None = None
        self._pending_title: str | None = None
        # When a bed-type change makes the first form's checkbox ambiguous,
        # retain its validated submission while a bed-specific follow-up asks
        # for an explicit connection-lifetime choice.
        self._pending_disconnect_input: dict[str, Any] | None = None
        self._pending_disconnect_resume_step: str | None = None
        self._pending_disconnect_default: bool = DEFAULT_DISCONNECT_AFTER_COMMAND
        self._disconnect_choice_confirmed: bool = False
        # True once the verify_connection form has actually been rendered, so a
        # replayed submission from the previous form cannot be read as a
        # confirmation of a result the user never saw.
        self._verify_form_shown: bool = False
        # Set when the user chose to replace an existing host bond rather than
        # pair on top of it.
        self._pairing_remove_record: LocalBondRecord | None = None
        # The evidence behind a verified bond, kept for logging and diagnostics.
        self._pairing_success_evidence: BondEvidence | None = None
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
        self._show_full_bed_type_list = False

        bed_type = detection_result.bed_type
        if (
            bed_type is None
            or detection_result.confidence >= 0.7
            or not detection_result.ambiguous_types
        ):
            return False

        seen: set[str] = set()
        disambiguation_types: list[str] = []
        for candidate in (bed_type, *detection_result.ambiguous_types):
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

    def _maybe_add_kaidi_metadata(
        self,
        entry_data: dict[str, Any],
        *,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> dict[str, Any]:
        """Cache Kaidi room/VADDR state when this entry targets a Kaidi bed."""
        if entry_data.get(CONF_BED_TYPE) != BED_TYPE_KAIDI:
            return entry_data

        advertisement = resolve_kaidi_advertisement(
            self.hass,
            entry_data[CONF_ADDRESS],
            manufacturer_data=manufacturer_data,
        )
        return add_kaidi_entry_metadata(entry_data, advertisement)

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
        return dict(cached) if isinstance(cached, dict) else None

    def _offline_safe_bed_type(self, entry: ConfigEntry) -> str | None:
        """Resolve ``entry``'s bed type for the offline-capability-safe check.

        A legacy ``leggett_platt`` entry stores its real protocol under
        ``protocol_variant``; an EXPLICIT variant resolves to a concrete type
        that the offline-safe set already lists (``leggett_gen2`` /
        ``leggett_wilinke``), even though the umbrella ``leggett_platt`` is not.
        Funnel through the shared ``resolve_explicit_bed_type`` so the gate,
        offline minting, and the pair descriptors all agree (``okin`` ->
        leggett_okin, still unsafe; ``auto``/unset stays the umbrella type).
        """
        return resolve_explicit_bed_type(
            entry.data.get(CONF_BED_TYPE), entry.data.get(CONF_PROTOCOL_VARIANT)
        )

    def _resolved_pair_side_data(self, entry: ConfigEntry) -> dict[str, Any]:
        """Merged ``data`` + ``options`` for a pair child, with an explicit legacy
        variant resolved to its concrete bed type.

        Options (e.g. customized angle limits, which the coordinator reads before
        data) are merged in so they survive the original being absorbed. The
        bed_type is normalised through the SAME resolver the offline-safe gate
        used, so the descriptor that gets stored is the one the gate approved —
        otherwise the pair would carry the umbrella ``leggett_platt`` and
        ``async_prime_offline_controller`` would refuse to mint the side the gate
        just promised was offline-safe.
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
        motor_count = entry.options.get(
            CONF_MOTOR_COUNT,
            entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
        )
        return motor_count == 1

    async def _pair_layout_snapshot(self, entry: ConfigEntry) -> dict[str, Any] | None:
        """Capture the side's generic motor layout from its capability controller.

        Prefer the loaded controller, otherwise mint the protocol's supported
        client-free capability controller. If neither is available, the layout is
        unknown and pairing is blocked rather than inferred from another protocol.
        The persisted snapshot keeps the decision auditable after absorption.
        """
        from .coordinator import AdjustableBedCoordinator

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
        return {
            "motor_count": int(configured_motor_count),
            "motor_keys": sorted(spec.key for spec in specs),
            "discrete_motor_control": bool(
                getattr(controller, "has_discrete_motor_control", False)
            ),
            "supports_motor_control": bool(getattr(controller, "supports_motor_control", False)),
        }

    def _has_unsafe_offline_platforms(self, entry: ConfigEntry) -> bool:
        """Whether ``entry`` exposes climate/light/select a half-available pair
        couldn't recreate.

        These platforms are now forwarded per-side, but their per-side entities
        are built from a side's ``capability_controller`` — which only an
        offline-capability-safe bed type has when a side is offline at setup. For
        any other type, a half-available pair (or a conversion where a side drops
        before connecting) would lose those entities, so keep blocking those.

        Octo is offline-capable ONLY via a captured snapshot, so it is unsafe iff
        it has no snapshot (i.e. wasn't connected at pairing).
        """
        bed_type = self._offline_safe_bed_type(entry)
        if bed_type in OFFLINE_CAPABILITY_SAFE_BED_TYPES:
            return False
        if bed_type == BED_TYPE_OCTO:
            # Star2 has fixed caps -> statically offline-safe; standard Octo needs a
            # live capability snapshot.
            if self._is_octo_star2(entry):
                return False
            return self._octo_capability_snapshot(entry) is None
        registry = er.async_get(self.hass)
        platforms = {"climate", "light", "select"}
        return any(
            entity.domain in platforms
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        )

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

        if user_input is not None:
            selected = user_input.get("bed_type_choice")
            if selected == "show_all":
                # User wants the full dropdown - set flag and go to confirm step
                self._show_full_bed_type_list = True
                self._disambiguated_bed_type = None
                _LOGGER.debug("User selected 'show all bed types' option")
            else:
                # User selected a specific type from disambiguation
                self._disambiguated_bed_type = selected
                self._show_full_bed_type_list = False
                _LOGGER.debug("User disambiguated bed type to: %s", selected)

            return await self.async_step_bluetooth_confirm()

        # Build options for disambiguation - only the relevant 2-4 types
        options: list[SelectOptionDict] = []
        for bed_type in self._disambiguation_types:
            display_name = BED_TYPE_DISPLAY_NAMES.get(bed_type, bed_type)
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
        """Confirm discovery."""
        assert self._discovery_info is not None

        # Use detailed detection to get confidence and ambiguity info
        detection_result = detect_bed_type_detailed(self._discovery_info)
        detected_bed_type = detection_result.bed_type

        # Use disambiguated type if user selected one, otherwise use detected type
        bed_type = self._disambiguated_bed_type or detected_bed_type
        errors: dict[str, str] = {}

        if (
            user_input is None
            and self._disambiguated_bed_type is None
            and not self._show_full_bed_type_list
            and self._prepare_disambiguation(detection_result)
        ):
            _LOGGER.debug(
                "Ambiguous detection for %s - showing disambiguation UI with options: %s",
                self._discovery_info.address,
                self._disambiguation_types,
            )
            return await self.async_step_bluetooth_disambiguate()

        # Resolve the disconnect default from the bed type the form actually
        # displays. An ambiguous "show all" result defaults to Auto-detect, not
        # the low-confidence candidate returned by detection.
        bed_type_default = bed_type
        if self._show_full_bed_type_list:
            bed_type_default = (
                self._disambiguated_bed_type
                or _confident_auto_detect(detection_result)
                or BED_TYPE_AUTO_DETECT
            )
        defaults_bed_type = (
            None if bed_type_default == BED_TYPE_AUTO_DETECT else bed_type_default
        )
        default_disconnect_after_command = disconnect_after_command_default_enabled(
            defaults_bed_type, VARIANT_AUTO
        )

        if user_input is not None:
            # Get user-selected bed type (may differ from auto-detected)
            selected_bed_type = user_input.get(CONF_BED_TYPE, bed_type)
            # "Auto-detect" in the full manual list: resolve to an explicitly
            # disambiguated choice or a high-confidence, unambiguous detection;
            # otherwise re-show the form with a clear error instead of committing
            # to a low-confidence/ambiguous guess.
            if selected_bed_type == BED_TYPE_AUTO_DETECT:
                resolved = self._disambiguated_bed_type or _confident_auto_detect(detection_result)
                if resolved:
                    _LOGGER.info(
                        "Auto-detect resolved bed type to %s for %s",
                        resolved,
                        self._discovery_info.address,
                    )
                    selected_bed_type = resolved
                else:
                    errors["base"] = "auto_detect_failed"
                    selected_bed_type = None
            octo_pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN))
            if (
                selected_bed_type == BED_TYPE_OCTO
                and bed_type == BED_TYPE_OCTO
                and not is_valid_octo_pin(octo_pin)
            ):
                errors[CONF_OCTO_PIN] = "invalid_pin"
            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
            protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)

            motor_count = _normalize_fixed_motor_count(
                selected_bed_type,
                protocol_variant,
                user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
            )
            user_input[CONF_MOTOR_COUNT] = motor_count
            if selected_bed_type and not _is_valid_motor_count(
                selected_bed_type, protocol_variant, motor_count
            ):
                errors[CONF_MOTOR_COUNT] = "invalid_motor_count_for_bed_type"

            # Validate protocol variant is valid for selected bed type
            if selected_bed_type and not is_valid_variant_for_bed_type(
                selected_bed_type, protocol_variant
            ):
                errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = get_motor_pulse_defaults(
                selected_bed_type,
                protocol_variant,
                detection_result.signals,
            )
            # Validate motor pulse count
            pulse_count_input = user_input.get(CONF_MOTOR_PULSE_COUNT)
            if pulse_count_input is not None and pulse_count_input != "":
                try:
                    motor_pulse_count = int(pulse_count_input)
                except ValueError, TypeError:
                    errors[CONF_MOTOR_PULSE_COUNT] = "invalid_number"
                    motor_pulse_count = pulse_defaults[0]
            else:
                motor_pulse_count = pulse_defaults[0]
            # Validate motor pulse delay
            pulse_delay_input = user_input.get(CONF_MOTOR_PULSE_DELAY_MS)
            if pulse_delay_input is not None and pulse_delay_input != "":
                try:
                    motor_pulse_delay_ms = int(pulse_delay_input)
                except ValueError, TypeError:
                    errors[CONF_MOTOR_PULSE_DELAY_MS] = "invalid_number"
                    motor_pulse_delay_ms = pulse_defaults[1]
            else:
                motor_pulse_delay_ms = pulse_defaults[1]
            if not errors:
                disconnect_after_command = self._disconnect_after_command_choice(
                    user_input,
                    selected_bed_type,
                    protocol_variant,
                    default_disconnect_after_command,
                )
                if disconnect_after_command is None:
                    return self._request_disconnect_after_command_choice(
                        user_input,
                        resume_step="bluetooth_confirm",
                        bed_type=selected_bed_type,
                        protocol_variant=protocol_variant,
                    )
                _LOGGER.info(
                    "User confirmed bed setup: name=%s, type=%s (detected: %s), variant=%s, address=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s, pulse_count=%s, pulse_delay=%s",
                    user_input.get(
                        CONF_NAME, self._discovery_info.name or "Adjustable Bed"
                    ),
                    selected_bed_type,
                    detected_bed_type,
                    protocol_variant,
                    self._discovery_info.address,
                    user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    user_input.get(
                        CONF_DISABLE_ANGLE_SENSING,
                        DEFAULT_DISABLE_ANGLE_SENSING,
                    ),
                    preferred_adapter,
                    motor_pulse_count,
                    motor_pulse_delay_ms,
                )
                entry_data = {
                    CONF_ADDRESS: self._discovery_info.address.upper(),
                    CONF_BED_TYPE: selected_bed_type,
                    CONF_PROTOCOL_VARIANT: protocol_variant,
                    CONF_NAME: user_input.get(CONF_NAME, self._discovery_info.name),
                    CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    CONF_DISABLE_ANGLE_SENSING: user_input.get(
                        CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
                    ),
                    CONF_PREFERRED_ADAPTER: preferred_adapter,
                    CONF_MOTOR_PULSE_COUNT: motor_pulse_count,
                    CONF_MOTOR_PULSE_DELAY_MS: motor_pulse_delay_ms,
                    # The user saw and submitted these, so a protocol
                    # migration must not treat them as generated defaults.
                    CONF_MOTOR_PULSE_USER_SET: True,
                    CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command,
                    CONF_IDLE_DISCONNECT_SECONDS: user_input.get(
                        CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
                    ),
                }
                if selected_bed_type == BED_TYPE_SOLACE and self._discovery_info.name:
                    entry_data[CONF_BLE_DEVICE_NAME] = self._discovery_info.name
                _add_malouf_entry_data(entry_data, user_input, selected_bed_type)
                _add_cb24_entry_data(entry_data, user_input, selected_bed_type)
                # Malouf layout/memory fields weren't shown inline (user overrode the
                # detected type to Malouf), so collect them in a follow-up step.
                if self._needs_malouf_step(selected_bed_type, user_input):
                    self._manual_data = entry_data
                    return await self.async_step_bluetooth_malouf()
                # Handle bed-type-specific configuration when user overrides detected type
                # If user selected Octo but detection wasn't Octo, collect PIN in follow-up step
                if selected_bed_type == BED_TYPE_OCTO and detected_bed_type != BED_TYPE_OCTO:
                    self._manual_data = entry_data
                    return await self.async_step_bluetooth_octo()
                # If user selected Richmat but detection wasn't Richmat, collect remote in follow-up step
                if selected_bed_type == BED_TYPE_RICHMAT and detected_bed_type != BED_TYPE_RICHMAT:
                    self._manual_data = entry_data
                    return await self.async_step_bluetooth_richmat()
                # Add Octo PIN if configured (when detected as Octo, field was shown inline)
                if selected_bed_type == BED_TYPE_OCTO:
                    entry_data[CONF_OCTO_PIN] = octo_pin
                # Add Jensen PIN if configured (when detected as Jensen, field was shown inline)
                if selected_bed_type == BED_TYPE_JENSEN:
                    entry_data[CONF_JENSEN_PIN] = user_input.get(CONF_JENSEN_PIN, "")
                # Add Richmat remote code if configured (when detected as Richmat, field was shown inline)
                if selected_bed_type == BED_TYPE_RICHMAT:
                    user_selected_remote = user_input.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO)
                    # If user selected "auto", try to use auto-detected code instead
                    if user_selected_remote == RICHMAT_REMOTE_AUTO:
                        detected_code = detect_richmat_remote_from_name(self._discovery_info.name)
                        if detected_code:
                            _LOGGER.info(
                                "Using auto-detected remote code '%s' for Richmat bed",
                                detected_code,
                            )
                            entry_data[CONF_RICHMAT_REMOTE] = detected_code
                        else:
                            entry_data[CONF_RICHMAT_REMOTE] = RICHMAT_REMOTE_AUTO
                    else:
                        entry_data[CONF_RICHMAT_REMOTE] = user_selected_remote
                entry_data = self._maybe_add_kaidi_metadata(
                    entry_data,
                    manufacturer_data=self._discovery_info.manufacturer_data,
                )
                # If bed requires pairing, show pairing instructions
                if selected_bed_type and requires_pairing(selected_bed_type, protocol_variant):
                    self._manual_data = entry_data
                    return await self.async_step_bluetooth_pairing()
                return await self._finish_with_verify(
                    entry_data,
                    user_input.get(CONF_NAME, self._discovery_info.name or "Adjustable Bed"),
                )

        _LOGGER.debug("Showing bluetooth confirmation form for %s", self._discovery_info.address)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Default angle sensing to enabled for beds that support position feedback.
        # The variant selector below always defaults to VARIANT_AUTO here (detection
        # does not resolve a variant), so the Keeson/ergomotion case cannot apply yet
        # and this matches plain BEDS_WITH_POSITION_FEEDBACK membership. Going through
        # the shared predicate keeps this in step with the paths that do know a variant.
        default_disable_angle = not bed_type_has_position_feedback(bed_type, VARIANT_AUTO)
        # Get bed-type-specific motor pulse defaults
        pulse_defaults = get_motor_pulse_defaults(
            bed_type,
            VARIANT_AUTO,
            detection_result.signals,
        )
        default_pulse_count, default_pulse_delay = pulse_defaults

        # Auto-detect motor count for Richmat beds based on remote code features
        default_motor_count = _default_motor_count(bed_type, self._discovery_info.name)
        detected_remote = detection_result.detected_remote
        if bed_type == BED_TYPE_RICHMAT:
            # Use detected_remote from detection result, or try to extract from name
            if not detected_remote:
                detected_remote = detect_richmat_remote_from_name(self._discovery_info.name)
            if detected_remote:
                features = get_richmat_features(detected_remote)
                default_motor_count = get_richmat_motor_count(features)

        # Build schema with optional variant selection
        # Use searchable dropdown when user asked for all bed types, otherwise simple dropdown
        bed_type_selector: Any
        if self._show_full_bed_type_list:
            # Prepend an "Auto-detect" option and default to it when detection
            # didn't identify the device, so the user isn't silently dropped onto
            # the first alphabetical protocol and forced to guess.
            auto_label = await self._get_config_translation(
                "step.bluetooth_confirm.data.auto_detect_option",
                "Auto-detect (recommended)",
            )
            bed_type_selector = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=BED_TYPE_AUTO_DETECT, label=auto_label),
                        *get_bed_type_options(),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Same display-name dropdown as the full list, so users see
            # "Diagnostic (unknown bed)" etc. instead of raw type slugs
            # (issue #385). Detection may return a legacy alias (e.g.
            # dewertokin) that the display list omits; prepend it so the
            # detected default stays selectable.
            options = get_bed_type_options()
            if isinstance(bed_type_default, str) and bed_type_default not in {
                option["value"] for option in options
            }:
                options.insert(
                    0,
                    SelectOptionDict(
                        value=bed_type_default,
                        label=BED_TYPE_DISPLAY_NAMES.get(bed_type_default, bed_type_default),
                    ),
                )
            bed_type_selector = SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict: dict[vol.Marker, Any] = {
            vol.Optional(CONF_BED_TYPE, default=bed_type_default): bed_type_selector,
            vol.Optional(CONF_NAME, default=self._discovery_info.name or "Adjustable Bed"): str,
            vol.Optional(CONF_MOTOR_COUNT, default=default_motor_count): vol.All(
                vol.Coerce(int), vol.In([1, 2, 3, 4])
            ),
            vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
            vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle): bool,
            vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
            vol.Optional(CONF_MOTOR_PULSE_COUNT, default=str(default_pulse_count)): TextSelector(
                TextSelectorConfig()
            ),
            vol.Optional(CONF_MOTOR_PULSE_DELAY_MS, default=str(default_pulse_delay)): TextSelector(
                TextSelectorConfig()
            ),
            vol.Optional(
                CONF_DISCONNECT_AFTER_COMMAND, default=default_disconnect_after_command
            ): bool,
            vol.Optional(
                CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
        }

        # Always show variant selection - user may change bed type to one with variants
        # If user changes bed type, they can select the appropriate variant
        # Validation on submission ensures only valid variants are accepted
        schema_dict[vol.Optional(CONF_PROTOCOL_VARIANT, default=VARIANT_AUTO)] = vol.In(
            ALL_PROTOCOL_VARIANTS
        )

        if bed_type in MALOUF_BED_TYPES:
            _add_malouf_schema_fields(schema_dict)
        if bed_type == BED_TYPE_OKIN_CB24:
            _add_cb24_side_schema_field(schema_dict)

        # Add PIN field for Octo beds
        if bed_type == BED_TYPE_OCTO:
            schema_dict[vol.Optional(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN)] = TextSelector(
                TextSelectorConfig()
            )

        # Add PIN field for Jensen beds (default PIN "3060" is used if empty)
        if bed_type == BED_TYPE_JENSEN:
            schema_dict[vol.Optional(CONF_JENSEN_PIN, default="")] = TextSelector(
                TextSelectorConfig()
            )

        # Add remote selection for Richmat beds with auto-detected default
        # Uses detected_remote from detection result or from earlier name-based detection
        if bed_type == BED_TYPE_RICHMAT:
            if detected_remote:
                _LOGGER.info(
                    "Auto-detected Richmat remote code '%s' from device name '%s'",
                    detected_remote,
                    self._discovery_info.name,
                )
            # Only use detected code as default if it's in the dropdown options
            # Otherwise, "auto" will be used and the detected code stored when saving
            default_remote = (
                detected_remote.upper()
                if detected_remote and detected_remote.upper() in RICHMAT_REMOTES
                else RICHMAT_REMOTE_AUTO
            )
            # Create modified remotes dict with auto-detected info in the label
            remotes_options = dict(RICHMAT_REMOTES)
            if detected_remote and detected_remote.upper() not in RICHMAT_REMOTES:
                # Modify "Auto" label to show detected code
                remotes_options[RICHMAT_REMOTE_AUTO] = f"Auto (detected: {detected_remote.upper()})"
            schema_dict[vol.Optional(CONF_RICHMAT_REMOTE, default=default_remote)] = vol.In(
                remotes_options
            )

        # Build description placeholders with optional ambiguity warning
        description_placeholders = {
            "name": self._discovery_info.name or "Unknown",
            "address": self._discovery_info.address.upper(),
            "transport": await self._async_transport_note(
                self._discovery_info.address,
                # On a redisplay after a validation error the user's adapter and
                # protocol choices are known. Previewing the defaults instead
                # can warn about a proxy for someone who picked a local adapter,
                # or drop the pairing warning for the type they actually chose.
                (user_input or {}).get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
                (user_input or {}).get(CONF_BED_TYPE) or bed_type,
                (user_input or {}).get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO),
            ),
        }

        # Add detection confidence info for ambiguous cases
        # Skip the warning if user already went through disambiguation step
        if self._disambiguated_bed_type:
            # User already chose from disambiguation - show their selection
            display_name = BED_TYPE_DISPLAY_NAMES.get(
                self._disambiguated_bed_type, self._disambiguated_bed_type
            )
            description_placeholders["detection_note"] = f"Selected: {display_name}"
        elif self._show_full_bed_type_list:
            # User asked to see all bed types
            description_placeholders["detection_note"] = "Select your bed type from the list."
        elif detection_result.confidence < 0.7 and detection_result.ambiguous_types:
            # Map internal bed type constants to human-readable display names
            display_names = [
                BED_TYPE_DISPLAY_NAMES.get(t, t) for t in detection_result.ambiguous_types
            ]
            ambiguous_list = ", ".join(display_names)
            description_placeholders["detection_note"] = (
                f"Detection confidence: {int(detection_result.confidence * 100)}%. "
                f"Could also be: {ambiguous_list}. "
                "Verify the bed type below matches your device."
            )
        else:
            # For high-confidence detections, show a reassuring message
            description_placeholders["detection_note"] = "Detected automatically."

        octo_split_note = self._get_octo_split_setup_note(
            address=self._discovery_info.address,
            name=self._discovery_info.name,
            bed_type=bed_type,
        )
        if octo_split_note is not None:
            description_placeholders["detection_note"] = (
                f"{description_placeholders['detection_note']}\n{octo_split_note}"
            )

        # Offer a one-click "this isn't my bed" report so false-positive
        # detections can be fixed. Built from the live (un-redacted) discovery
        # data because the user explicitly chooses whether to open the link.
        report_device_info = capture_device_info(self._discovery_info)
        try:
            integration = await async_get_integration(self.hass, DOMAIN)
            integration_version = str(integration.version) if integration.version else None
        except IntegrationNotFound:
            integration_version = None
        report_url = build_misidentified_issue_url(
            report_device_info,
            detected_bed_type,
            detection_result.confidence,
            detection_result.signals,
            integration_version=integration_version,
            ha_version=HA_VERSION,
        )
        description_placeholders["report_note"] = (
            f"Wrong device, or not a bed? [Report a misidentified device]({report_url})"
        )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the user step to pick discovered device or manual entry."""
        _LOGGER.debug("async_step_user called with input: %s", user_input)

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address.startswith(CONFIGURED_RETRY_PREFIX):
                return self._async_abort_retrying_entry(
                    address.removeprefix(CONFIGURED_RETRY_PREFIX)
                )
            if address == "manual":
                _LOGGER.debug("User selected manual entry (full list)")
                # Reset two-tier selection state - show all BLE devices with full bed type dropdown
                self._selected_actuator = None
                self._selected_bed_type = None
                self._selected_protocol_variant = None
                return await self.async_step_manual()
            if address == "select_by_brand":
                _LOGGER.debug("User selected two-tier brand selection")
                return await self.async_step_select_actuator()
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

        # Build device list - discovered beds first when available, then manual options
        devices: dict[str, str] = {}
        if sorted_beds:
            devices.update(
                {address: f"{info.name or 'Unknown'} ({address})" for address, info in sorted_beds}
            )
            devices.update(
                {
                    f"{CONFIGURED_RETRY_PREFIX}{address}": self._format_retrying_option_label(
                        address,
                        entry,
                        info,
                        suffix=retrying_suffix,
                    )
                    for address, (entry, info) in sorted_retrying_devices
                }
            )
            devices["select_by_brand"] = "Select by actuator brand"
        else:
            devices.update(
                {
                    f"{CONFIGURED_RETRY_PREFIX}{address}": self._format_retrying_option_label(
                        address,
                        entry,
                        info,
                        suffix=retrying_suffix,
                    )
                    for address, (entry, info) in sorted_retrying_devices
                }
            )
            devices["select_by_brand"] = "Select by actuator brand (recommended)"
        devices["manual"] = "Show all BLE devices"
        devices["diagnostic"] = "Browse unsupported BLE devices"
        if len(self._pairable_single_entries()) >= 2:
            devices["pair_beds"] = "Combine two beds into one (Dual Bed)"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )

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
                # Standard Octo is paired via the sequential active-connection
                # profile, and its OFFLINE side mints its light/RGBW/memory/synchro
                # entities from a capability snapshot captured here from the live bed
                # — so each STANDARD Octo bed must be connected at pairing for its
                # snapshot to exist. Star2 has fixed caps and needs no snapshot.
                errors["base"] = "octo_pairing_needs_connection"
            elif self._has_unsafe_offline_platforms(left) or self._has_unsafe_offline_platforms(
                right
            ):
                # climate/light/select are forwarded per-side now, but a
                # non-offline-capability-safe bed can't rebuild them when a side
                # is offline, so a half-available pair would lose them.
                errors["base"] = "pairing_unsupported_entities"
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

    async def async_step_select_actuator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select actuator brand from label (first tier of two-tier selection)."""
        if user_input is not None:
            selected = user_input["actuator_brand"]
            group = ACTUATOR_GROUPS[selected]

            if group["variants"] is not None:
                # Has variants - go to variant selection
                self._selected_actuator = selected
                return await self.async_step_select_variant()
            else:
                # Single protocol - go directly to device selection
                self._selected_bed_type = SINGLE_TYPE_GROUPS[selected]
                self._selected_protocol_variant = None
                return await self.async_step_manual()

        # Build options for actuator brand selection
        options: list[SelectOptionDict] = [
            SelectOptionDict(
                value=key,
                label=f"{group['display']} - {group['description']}",
            )
            for key, group in ACTUATOR_GROUPS.items()
        ]

        return self.async_show_form(
            step_id="select_actuator",
            data_schema=vol.Schema(
                {
                    vol.Required("actuator_brand"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_select_variant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select variant within actuator brand (second tier of two-tier selection)."""
        assert self._selected_actuator is not None
        group = ACTUATOR_GROUPS[self._selected_actuator]
        variants = group["variants"]
        assert variants is not None

        if user_input is not None:
            selected_idx = int(user_input["variant"])
            variant = variants[selected_idx]
            self._selected_bed_type = variant["type"]
            self._selected_protocol_variant = variant.get("variant")
            return await self.async_step_manual()

        # Build options for variant selection
        options: list[SelectOptionDict] = [
            SelectOptionDict(
                value=str(i),
                label=f"{v['label']} - {v['description']}",
            )
            for i, v in enumerate(variants)
        ]

        return self.async_show_form(
            step_id="select_variant",
            data_schema=vol.Schema(
                {
                    vol.Required("variant"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={
                "actuator": group["display"],
            },
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
            return await self.async_step_manual_config()

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

    async def async_step_manual_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual bed configuration after device selection."""
        errors: dict[str, str] = {}

        # Get the address from discovery_info or manual_address
        if self._discovery_info is not None:
            address = self._discovery_info.address.upper()
            device_name = self._discovery_info.name or "Unknown"
            discovery_source = getattr(self._discovery_info, "source", None) or ADAPTER_AUTO
            detection_result = detect_bed_type_detailed(self._discovery_info)
        else:
            # This shouldn't happen, but handle gracefully
            return await self.async_step_manual_entry()

        preselected_bed_type = self._selected_bed_type
        preselected_protocol_variant = self._selected_protocol_variant or VARIANT_AUTO
        detected_bed_type = detect_bed_type(self._discovery_info)
        detection_result = detect_bed_type_detailed(self._discovery_info)
        confident_bed_type = _confident_auto_detect(detection_result)
        defaults_bed_type = preselected_bed_type or confident_bed_type
        default_disconnect_after_command = disconnect_after_command_default_enabled(
            defaults_bed_type, preselected_protocol_variant
        )

        if user_input is not None:
            bed_type = user_input[CONF_BED_TYPE]

            # "Auto-detect" resolves only to a high-confidence, unambiguous match;
            # otherwise it re-shows the form with a clear error instead of silently
            # configuring a guessed protocol (issue #385).
            if bed_type == BED_TYPE_AUTO_DETECT:
                resolved = confident_bed_type
                if resolved:
                    _LOGGER.info("Auto-detect resolved bed type to %s for %s", resolved, address)
                    bed_type = resolved
                else:
                    errors["base"] = "auto_detect_failed"

            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, str(discovery_source))
            protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)

            motor_count = _normalize_fixed_motor_count(
                bed_type,
                protocol_variant,
                user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
            )
            user_input[CONF_MOTOR_COUNT] = motor_count
            if bed_type != BED_TYPE_AUTO_DETECT and not _is_valid_motor_count(
                bed_type, protocol_variant, motor_count
            ):
                errors[CONF_MOTOR_COUNT] = "invalid_motor_count_for_bed_type"

            # Validate protocol variant is valid for bed type
            if bed_type != BED_TYPE_AUTO_DETECT and not is_valid_variant_for_bed_type(
                bed_type, protocol_variant
            ):
                errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = get_motor_pulse_defaults(
                bed_type,
                protocol_variant,
                detection_result.signals,
            )
            motor_pulse_count = pulse_defaults[0]
            motor_pulse_delay_ms = pulse_defaults[1]
            try:
                motor_pulse_count = int(user_input.get(CONF_MOTOR_PULSE_COUNT) or pulse_defaults[0])
                motor_pulse_delay_ms = int(
                    user_input.get(CONF_MOTOR_PULSE_DELAY_MS) or pulse_defaults[1]
                )
            except ValueError, TypeError:
                errors["base"] = "invalid_number"

            if not errors:
                disconnect_after_command = self._disconnect_after_command_choice(
                    user_input,
                    bed_type,
                    protocol_variant,
                    default_disconnect_after_command,
                )
                if disconnect_after_command is None:
                    return self._request_disconnect_after_command_choice(
                        user_input,
                        resume_step="manual_config",
                        bed_type=bed_type,
                        protocol_variant=protocol_variant,
                    )
                _LOGGER.info(
                    "Manual bed configuration: address=%s, type=%s, variant=%s, name=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s, pulse_count=%s, pulse_delay=%s",
                    address,
                    bed_type,
                    protocol_variant,
                    user_input.get(CONF_NAME, "Adjustable Bed"),
                    user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                    preferred_adapter,
                    motor_pulse_count,
                    motor_pulse_delay_ms,
                )

                entry_data = {
                    CONF_ADDRESS: address,
                    CONF_BED_TYPE: bed_type,
                    CONF_PROTOCOL_VARIANT: protocol_variant,
                    CONF_NAME: user_input.get(CONF_NAME, "Adjustable Bed"),
                    CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    CONF_DISABLE_ANGLE_SENSING: user_input.get(
                        CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
                    ),
                    CONF_PREFERRED_ADAPTER: preferred_adapter,
                    CONF_MOTOR_PULSE_COUNT: motor_pulse_count,
                    CONF_MOTOR_PULSE_DELAY_MS: motor_pulse_delay_ms,
                    # The user saw and submitted these, so a protocol
                    # migration must not treat them as generated defaults.
                    CONF_MOTOR_PULSE_USER_SET: True,
                    CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command,
                    CONF_IDLE_DISCONNECT_SECONDS: user_input.get(
                        CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
                    ),
                }
                _add_malouf_entry_data(entry_data, user_input, bed_type)
                _add_cb24_entry_data(entry_data, user_input, bed_type)
                # Malouf layout/memory fields weren't shown inline (bed type was
                # chosen from the dropdown), so collect them in a follow-up step.
                if self._needs_malouf_step(bed_type, user_input):
                    self._manual_data = entry_data
                    return await self.async_step_manual_malouf()
                # For Octo beds, collect PIN in a separate step
                if bed_type == BED_TYPE_OCTO:
                    self._manual_data = entry_data
                    return await self.async_step_manual_octo()
                # For Richmat beds, collect remote code in a separate step
                if bed_type == BED_TYPE_RICHMAT:
                    self._manual_data = entry_data
                    return await self.async_step_manual_richmat()
                # If bed requires pairing, show pairing instructions
                if requires_pairing(bed_type, protocol_variant):
                    self._manual_data = entry_data
                    return await self.async_step_manual_pairing()
                entry_data = self._maybe_add_kaidi_metadata(
                    entry_data,
                    manufacturer_data=self._discovery_info.manufacturer_data,
                )
                return await self._finish_with_verify(
                    entry_data,
                    user_input.get(CONF_NAME, "Adjustable Bed"),
                )

        _LOGGER.debug("Showing manual config form for device: %s (%s)", device_name, address)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Ensure discovery_source is valid - it may refer to a proxy that disappeared
        if discovery_source not in adapters:
            discovery_source = ADAPTER_AUTO

        # Build base schema with bed type selector (alphabetically sorted)
        if preselected_bed_type:
            # Bed type was pre-selected from two-tier actuator selection.
            # Use it as the default value in the SelectSelector, but the field
            # remains editable so users can override if needed.
            schema_dict: dict[vol.Marker, Any] = {
                vol.Required(CONF_BED_TYPE, default=preselected_bed_type): SelectSelector(
                    SelectSelectorConfig(
                        options=get_bed_type_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROTOCOL_VARIANT, default=preselected_protocol_variant): vol.In(
                    ALL_PROTOCOL_VARIANTS
                ),
            }
        else:
            # No pre-selected brand: offer "Auto-detect" first and default to it
            # (or to the detected type) so the user isn't dropped onto the first
            # alphabetical protocol and forced to guess (issue #385).
            auto_label = await self._get_config_translation(
                "step.bluetooth_confirm.data.auto_detect_option",
                "Auto-detect (recommended)",
            )
            schema_dict = {
                vol.Required(
                    CONF_BED_TYPE, default=confident_bed_type or BED_TYPE_AUTO_DETECT
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=BED_TYPE_AUTO_DETECT, label=auto_label),
                            *get_bed_type_options(),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROTOCOL_VARIANT, default=VARIANT_AUTO): vol.In(
                    ALL_PROTOCOL_VARIANTS
                ),
            }

        # Determine smart defaults based on the bed type the form will default to:
        # a pre-selected brand, or the high-confidence detection that the
        # Auto-detect default resolves to. Otherwise a one-click "accept the
        # default" would persist generic timing/angle options for a known bed.
        if defaults_bed_type:
            # Keeson with Ergomotion variant supports position feedback
            has_position_feedback = bed_type_has_position_feedback(
                defaults_bed_type, preselected_protocol_variant
            )
            default_disable_angle = not has_position_feedback
            # Use bed-specific motor pulse defaults if available
            pulse_defaults = get_motor_pulse_defaults(
                defaults_bed_type,
                preselected_protocol_variant,
                detection_result.signals,
            )
            default_pulse_count, default_pulse_delay = pulse_defaults
        else:
            default_disable_angle = DEFAULT_DISABLE_ANGLE_SENSING
            default_pulse_count = DEFAULT_MOTOR_PULSE_COUNT
            default_pulse_delay = DEFAULT_MOTOR_PULSE_DELAY_MS

        octo_split_note = self._get_octo_split_setup_note(
            address=address,
            name=None if device_name == "Unknown" else device_name,
            bed_type=preselected_bed_type or detected_bed_type,
        )

        # Add remaining fields
        schema_dict.update(
            {
                vol.Optional(
                    CONF_NAME, default=device_name if device_name != "Unknown" else "Adjustable Bed"
                ): str,
                vol.Optional(
                    CONF_MOTOR_COUNT,
                    default=_default_motor_count(defaults_bed_type, device_name),
                ): vol.All(vol.Coerce(int), vol.In([1, 2, 3, 4])),
                vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle): bool,
                vol.Optional(CONF_PREFERRED_ADAPTER, default=discovery_source): vol.In(adapters),
                vol.Optional(
                    CONF_MOTOR_PULSE_COUNT, default=str(default_pulse_count)
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_MOTOR_PULSE_DELAY_MS, default=str(default_pulse_delay)
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_DISCONNECT_AFTER_COMMAND, default=default_disconnect_after_command
                ): bool,
                vol.Optional(
                    CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )
        if defaults_bed_type in MALOUF_BED_TYPES:
            _add_malouf_schema_fields(schema_dict)
        if defaults_bed_type == BED_TYPE_OKIN_CB24:
            _add_cb24_side_schema_field(schema_dict)

        return self.async_show_form(
            step_id="manual_config",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "name": device_name,
                "address": address,
                "setup_note": f"\n{octo_split_note}" if octo_split_note else "",
                "transport": await self._async_transport_note(
                    address,
                    (user_input or {}).get(CONF_PREFERRED_ADAPTER, discovery_source),
                    (user_input or {}).get(CONF_BED_TYPE) or defaults_bed_type,
                    (user_input or {}).get(CONF_PROTOCOL_VARIANT, preselected_protocol_variant),
                ),
            },
        )

    async def async_step_manual_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual address entry when user types in the MAC address."""
        errors: dict[str, str] = {}
        preselected_bed_type = self._selected_bed_type
        preselected_protocol_variant = self._selected_protocol_variant or VARIANT_AUTO
        default_disconnect_after_command = disconnect_after_command_default_enabled(
            preselected_bed_type, preselected_protocol_variant
        )

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().replace("-", ":")
            bed_type = user_input[CONF_BED_TYPE]

            # Validate MAC address format
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)

                motor_count = _normalize_fixed_motor_count(
                    bed_type,
                    protocol_variant,
                    user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                )
                user_input[CONF_MOTOR_COUNT] = motor_count
                if not _is_valid_motor_count(bed_type, protocol_variant, motor_count):
                    errors[CONF_MOTOR_COUNT] = "invalid_motor_count_for_bed_type"

                # Validate protocol variant is valid for bed type
                if not is_valid_variant_for_bed_type(bed_type, protocol_variant):
                    errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

                # Get bed-specific defaults for motor pulse settings
                pulse_defaults = get_motor_pulse_defaults(
                    bed_type,
                    protocol_variant,
                )
                motor_pulse_count = pulse_defaults[0]
                motor_pulse_delay_ms = pulse_defaults[1]
                try:
                    motor_pulse_count = int(
                        user_input.get(CONF_MOTOR_PULSE_COUNT) or pulse_defaults[0]
                    )
                    motor_pulse_delay_ms = int(
                        user_input.get(CONF_MOTOR_PULSE_DELAY_MS) or pulse_defaults[1]
                    )
                except ValueError, TypeError:
                    errors["base"] = "invalid_number"

                if not errors:
                    disconnect_after_command = self._disconnect_after_command_choice(
                        user_input,
                        bed_type,
                        protocol_variant,
                        default_disconnect_after_command,
                    )
                    if disconnect_after_command is None:
                        return self._request_disconnect_after_command_choice(
                            user_input,
                            resume_step="manual_entry",
                            bed_type=bed_type,
                            protocol_variant=protocol_variant,
                        )
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
                    self._set_device_title_placeholders(user_input.get(CONF_NAME), address)

                    _LOGGER.info(
                        "Manual bed configuration: address=%s, type=%s, variant=%s, name=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s, pulse_count=%s, pulse_delay=%s",
                        address,
                        bed_type,
                        protocol_variant,
                        user_input.get(CONF_NAME, "Adjustable Bed"),
                        user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                        user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                        user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                        preferred_adapter,
                        motor_pulse_count,
                        motor_pulse_delay_ms,
                    )

                    entry_data = {
                        CONF_ADDRESS: address,
                        CONF_BED_TYPE: bed_type,
                        CONF_PROTOCOL_VARIANT: protocol_variant,
                        CONF_NAME: user_input.get(CONF_NAME, "Adjustable Bed"),
                        CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                        CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                        CONF_DISABLE_ANGLE_SENSING: user_input.get(
                            CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
                        ),
                        CONF_PREFERRED_ADAPTER: preferred_adapter,
                        CONF_MOTOR_PULSE_COUNT: motor_pulse_count,
                        CONF_MOTOR_PULSE_DELAY_MS: motor_pulse_delay_ms,
                        # The user saw and submitted these, so a protocol
                        # migration must not treat them as generated defaults.
                        CONF_MOTOR_PULSE_USER_SET: True,
                        CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command,
                        CONF_IDLE_DISCONNECT_SECONDS: user_input.get(
                            CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
                        ),
                    }
                    _add_malouf_entry_data(entry_data, user_input, bed_type)
                    _add_cb24_entry_data(entry_data, user_input, bed_type)
                    # Malouf layout/memory fields weren't shown inline (bed type was
                    # chosen from the dropdown), so collect them in a follow-up step.
                    if self._needs_malouf_step(bed_type, user_input):
                        self._manual_data = entry_data
                        return await self.async_step_manual_malouf()
                    # For Octo beds, collect PIN in a separate step
                    if bed_type == BED_TYPE_OCTO:
                        self._manual_data = entry_data
                        return await self.async_step_manual_octo()
                    # For Richmat beds, collect remote code in a separate step
                    if bed_type == BED_TYPE_RICHMAT:
                        self._manual_data = entry_data
                        return await self.async_step_manual_richmat()
                    # If bed requires pairing, show pairing instructions
                    if requires_pairing(bed_type, protocol_variant):
                        self._manual_data = entry_data
                        return await self.async_step_manual_pairing()
                    entry_data = self._maybe_add_kaidi_metadata(entry_data)
                    return await self._finish_with_verify(
                        entry_data,
                        user_input.get(CONF_NAME, "Adjustable Bed"),
                    )

        _LOGGER.debug("Showing manual entry form")

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Check if bed type was pre-selected from two-tier actuator selection
        # Build base schema with bed type selector (alphabetically sorted)
        if preselected_bed_type:
            schema_dict: dict[vol.Marker, Any] = {
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_BED_TYPE, default=preselected_bed_type): SelectSelector(
                    SelectSelectorConfig(
                        options=get_bed_type_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROTOCOL_VARIANT, default=preselected_protocol_variant): vol.In(
                    ALL_PROTOCOL_VARIANTS
                ),
            }
        else:
            schema_dict = {
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_BED_TYPE): SelectSelector(
                    SelectSelectorConfig(
                        options=get_bed_type_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROTOCOL_VARIANT, default=VARIANT_AUTO): vol.In(
                    ALL_PROTOCOL_VARIANTS
                ),
            }

        # Determine smart defaults based on preselected bed type and variant
        if preselected_bed_type:
            # Keeson with Ergomotion variant supports position feedback
            has_position_feedback = bed_type_has_position_feedback(
                preselected_bed_type, preselected_protocol_variant
            )
            default_disable_angle = not has_position_feedback
            # Use bed-specific motor pulse defaults if available
            pulse_defaults = get_motor_pulse_defaults(
                preselected_bed_type,
                preselected_protocol_variant,
            )
            default_pulse_count, default_pulse_delay = pulse_defaults
        else:
            default_disable_angle = DEFAULT_DISABLE_ANGLE_SENSING
            default_pulse_count = DEFAULT_MOTOR_PULSE_COUNT
            default_pulse_delay = DEFAULT_MOTOR_PULSE_DELAY_MS

        # Add remaining fields
        schema_dict.update(
            {
                vol.Optional(CONF_NAME, default="Adjustable Bed"): str,
                vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.All(
                    vol.Coerce(int), vol.In([1, 2, 3, 4])
                ),
                vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle): bool,
                vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
                vol.Optional(
                    CONF_MOTOR_PULSE_COUNT, default=str(default_pulse_count)
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_MOTOR_PULSE_DELAY_MS, default=str(default_pulse_delay)
                ): TextSelector(TextSelectorConfig()),
                vol.Optional(
                    CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )
        schema_dict[
            vol.Optional(
                CONF_DISCONNECT_AFTER_COMMAND, default=default_disconnect_after_command
            )
        ] = bool
        if preselected_bed_type in MALOUF_BED_TYPES:
            _add_malouf_schema_fields(schema_dict)
        if preselected_bed_type == BED_TYPE_OKIN_CB24:
            _add_cb24_side_schema_field(schema_dict)

        typed_address = (user_input or {}).get(CONF_ADDRESS, "")
        return self.async_show_form(
            step_id="manual_entry",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "transport": (
                    await self._async_transport_note(
                        typed_address.upper().replace("-", ":"),
                        (user_input or {}).get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
                        (user_input or {}).get(CONF_BED_TYPE),
                        (user_input or {}).get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO),
                    )
                    if is_valid_mac_address(typed_address.upper().replace("-", ":"))
                    else ""
                ),
            },
        )

    async def async_step_manual_octo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Octo-specific configuration (PIN)."""
        assert self._manual_data is not None

        errors: dict[str, str] = {}

        if user_input is not None:
            octo_pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN))
            if not is_valid_octo_pin(octo_pin):
                errors[CONF_OCTO_PIN] = "invalid_pin"
            else:
                self._manual_data[CONF_OCTO_PIN] = octo_pin
                return self.async_create_entry(
                    title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                    data=self._manual_data,
                )

        return self.async_show_form(
            step_id="manual_octo",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN): TextSelector(
                        TextSelectorConfig()
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_manual_richmat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Richmat-specific configuration (remote code)."""
        assert self._manual_data is not None

        if user_input is not None:
            self._manual_data[CONF_RICHMAT_REMOTE] = user_input.get(
                CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO
            )
            return await self._finish_with_verify(
                self._manual_data,
                self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            )

        return self.async_show_form(
            step_id="manual_richmat",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_RICHMAT_REMOTE, default=RICHMAT_REMOTE_AUTO): vol.In(
                        RICHMAT_REMOTES
                    ),
                }
            ),
        )

    async def async_step_manual_malouf(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect Malouf layout/memory fields for the manual-entry paths."""
        return await self._async_malouf_step("manual_malouf", user_input)

    async def async_step_bluetooth_octo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Octo-specific configuration (PIN) after Bluetooth discovery type override."""
        assert self._manual_data is not None

        errors: dict[str, str] = {}

        if user_input is not None:
            octo_pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN))
            if not is_valid_octo_pin(octo_pin):
                errors[CONF_OCTO_PIN] = "invalid_pin"
            else:
                self._manual_data[CONF_OCTO_PIN] = octo_pin
                return self.async_create_entry(
                    title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                    data=self._manual_data,
                )

        return self.async_show_form(
            step_id="bluetooth_octo",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN): TextSelector(
                        TextSelectorConfig()
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_bluetooth_richmat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Richmat-specific configuration (remote code) after Bluetooth discovery type override."""
        assert self._manual_data is not None

        if user_input is not None:
            self._manual_data[CONF_RICHMAT_REMOTE] = user_input.get(
                CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO
            )
            return await self._finish_with_verify(
                self._manual_data,
                self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            )

        return self.async_show_form(
            step_id="bluetooth_richmat",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_RICHMAT_REMOTE, default=RICHMAT_REMOTE_AUTO): vol.In(
                        RICHMAT_REMOTES
                    ),
                }
            ),
        )

    async def async_step_bluetooth_malouf(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect Malouf layout/memory fields after a Bluetooth-discovery override."""
        return await self._async_malouf_step("bluetooth_malouf", user_input)

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
        can_certify_existing = (
            existing is not None
            and _every_route_holds_bond(prediction, inventory, existing)
        )
        # Verifying does not need that guarantee: it connects and records the
        # route it actually took, so a wrong prediction shows up as a failed
        # check rather than a false marker. A bed granting one connection per
        # pairing window cannot verify at all, though - spending the window is
        # the one thing this action exists to avoid - so for it the action would
        # be exactly the assertion above, and it is offered only when certain.
        can_offer_existing = existing is not None and (
            (not defers_pairing and matching_local_route is not None)
            or can_certify_existing
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
                self._pairing_verify_source = (
                    (existing.adapter_address if existing else None)
                    or (
                        matching_local_route.source
                        if matching_local_route is not None
                        else None
                    )
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
                    route_uncertain=(
                        matching_local_route is not None and not can_offer_existing
                    ),
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
            preferred_adapter = self._manual_data.get(
                CONF_PREFERRED_ADAPTER, ADAPTER_AUTO
            )
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
            _LOGGER.info("Could not verify the existing bond for %s: %s", address, err)
            return OperationResult(
                outcome=OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE,
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

        if evidence.status is BondVerificationStatus.AUTH_FAILED:
            # The link came up but is still unauthenticated, which is the one
            # outcome that says the bond really did not form.
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
        return await self.async_run_operation_step(
            step_id="pairing_progress",
            worker=self._async_pairing_worker,
            next_step_id="pairing_result",
        )

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
        evidence = result.payload if result is not None else None
        succeeded = result is not None and result.succeeded

        if user_input is not None and self._pairing_result_shown:
            if user_input.get("action") == "retry":
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
                self._pairing_success_evidence = evidence
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
            return self.async_create_entry(
                title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                data=entry_data,
            )

        schema: dict[vol.Marker, Any] = {}
        if not succeeded:
            schema[vol.Required("action", default="retry")] = SelectSelector(
                SelectSelectorConfig(
                    options=["retry", "finish"],
                    mode=SelectSelectorMode.LIST,
                    translation_key="pairing_result_action",
                )
            )

        self._pairing_result_shown = True
        return self.async_show_form(
            step_id="pairing_result",
            data_schema=vol.Schema(schema),
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

        if result.succeeded and isinstance(evidence, BondEvidence):
            if not evidence.proves_bond:
                # Nothing contradicted the pairing, but nothing proved it either.
                return await self._pairing_text("unproven")
            owner = evidence.owner
            where = owner.source or str(owner.transport)
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
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        if not address:
            raise ValueError("No address provided for pairing")

        preferred_adapter = ADAPTER_AUTO
        if self._manual_data:
            preferred_adapter = self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

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
            and bed_type
            and requires_pairing_after_service_discovery(bed_type, protocol_variant)
        )

        # LP Control first connects and discovers GATT, then asks Android to
        # create the bond. BlueZ's pair=True path calls Device1.Pair instead of
        # making the app's ordinary unbonded GATT connection first.
        # Hold the address lock for the whole client lifetime, not just the
        # connect: the disconnect below must not land in the middle of another
        # caller's connect attempt, where bleak's cleanup can abort it. Keeping
        # it all in this one task is also required, because the lock is
        # reentrant per task rather than per caller.
        async with async_get_connect_lock(self.hass, address):
            self.async_report_action(SetupAction.CONNECTING)
            connect_kwargs: dict[str, Any] = {
                "use_services_cache": not pair_after_service_discovery,
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
                timeout=CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE].connection_timeout,
                **connect_kwargs,
            )
            if track_for_flow_cleanup:
                self.async_track_client(client)
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

                if pair_after_service_discovery:
                    _LOGGER.info(
                        "Connected to %s and discovered services; creating the BLE bond now",
                        address,
                    )
                    self.async_report_action(SetupAction.PAIRING)
                    await client.pair()

                self.async_report_action(SetupAction.VERIFYING_BOND)
                return await async_verify_authenticated_access(
                    client,
                    bed_type=bed_type,
                    protocol_variant=protocol_variant,
                    path=path,
                    operation=("setup_pairing" if request_bond else "verify_existing_bond"),
                )
            finally:
                self.async_report_action(SetupAction.DISCONNECTING)
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001 - cleanup must not mask the result
                    _LOGGER.debug("Disconnect after pairing %s failed", address, exc_info=True)
                else:
                    # Only clear what this attempt registered: the shielded
                    # replacement never tracks its client, so untracking here
                    # would drop a client it does not own.
                    if track_for_flow_cleanup:
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

    async def _finish_with_verify(self, entry_data: dict[str, Any], title: str) -> ConfigFlowResult:
        """Stash the finalized entry and route through the verify_connection step.

        Skips the verify step (creating the entry directly) when no connectable
        scanner is available to probe through, or for one-connection pairing-window
        beds whose single connection must be left for setup (issue #385).
        """
        if not self._verification_possible() or _skips_setup_connection_probe(
            entry_data.get(CONF_BED_TYPE), entry_data.get(CONF_PROTOCOL_VARIANT)
        ):
            return self.async_create_entry(title=title, data=entry_data)
        self._pending_entry = entry_data
        self._pending_title = title
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
        """Run the capability probe as a tracked background operation.

        Everything the client touches happens in this one task: the per-address
        connect lock is reentrant per ``asyncio.Task``, so splitting the connect
        and the disconnect across tasks would deadlock rather than re-enter.
        """
        assert self._pending_entry is not None
        report = await self._probe_capabilities(
            self._pending_entry[CONF_ADDRESS],
            self._pending_entry.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
            self._pending_entry.get(CONF_BED_TYPE),
            self._pending_entry.get(CONF_PROTOCOL_VARIANT),
            reporter=self.async_report_action,
            wait_progress=self.async_report_progress,
            path_reporter=self.async_report_path,
            client_tracker=self.async_track_client,
        )
        if report.freshness is FreshnessStatus.DEVICE_UNRESOLVED:
            outcome = OperationOutcome.DEVICE_UNRESOLVED
        elif report.freshness is not None and report.freshness is not FreshnessStatus.FRESH:
            outcome = OperationOutcome.NOT_ADVERTISING
        elif not report.connected:
            outcome = OperationOutcome.CONNECTION_FAILED
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
        """Run the read-only capability probe behind a live progress view.

        Without this the form the user just submitted sits there frozen for as
        long as the BLE stack takes, which is indistinguishable from a hang
        (issue #457).
        """
        assert self._pending_entry is not None
        if self._operation is None:
            self._async_start_probe_operation()
        return await self.async_run_operation_step(
            step_id="setup_progress",
            worker=self._async_probe_worker,
            next_step_id="verify_connection",
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
    ) -> CapabilityReport:
        """Connect once (read-only) and report what was detected.

        This never sends a movement/control command - it only selects an adapter,
        establishes a connection, discovers GATT services, and reads the standard
        Device Information service. It always disconnects in ``finally`` so the
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
                        timeout=_PROBE_TIMEOUT_SECONDS,
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
                    _report(SetupAction.READING_CAPABILITIES)
                    report.manufacturer, report.model = await read_ble_device_info(client, address)
                finally:
                    if client is not None:
                        _report(SetupAction.DISCONNECTING)
                        try:
                            await client.disconnect()
                        except Exception:  # noqa: BLE001 - cleanup must not raise
                            pass
                        else:
                            # Only cleared once the link is really closed, so a
                            # cancellation during the disconnect still leaves
                            # the cleanup something to retry.
                            if client_tracker is not None:
                                client_tracker(None)
        except Exception as err:  # noqa: BLE001 - probe is best-effort
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
        finishes setup - a failed probe is informational and never blocks entry
        creation. When the bed was not advertising the form also offers Retry,
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

        if user_input is not None and self._verify_form_shown:
            if user_input.get("action") == "retry":
                self._verify_form_shown = False
                self._async_start_probe_operation()
                return await self.async_step_setup_progress()
            return self.async_create_entry(
                title=self._pending_title or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                data=self._pending_entry,
            )

        result = self.operation.result
        report = result.payload if result is not None else None
        if not isinstance(report, CapabilityReport):
            # The operation state is gone (a direct call, or a flow restored
            # without it). Say so rather than running a blocking probe here:
            # this is the step that exists so that nothing blocks.
            report = CapabilityReport(freshness=FreshnessStatus.MISSING)

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

    async def async_step_diagnostic_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backward-compatible handler for old flow links."""
        assert self._discovery_info is not None
        return self._async_abort_diagnostic_browser(
            address=self._discovery_info.address.upper(),
            name=self._discovery_info.name,
            source=getattr(self._discovery_info, "source", None),
            connectable=getattr(self._discovery_info, "connectable", None),
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
        return cast("dict[str, Any]", vol.Schema(schema_dict)({}))
    except vol.Invalid:
        return {}


class AdjustableBedOptionsFlow(BluetoothOperationMixin, OptionsFlowWithConfigEntry):
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
        """Drop settings that belong only to the previously selected protocol."""
        if not get_variants_for_bed_type(bed_type):
            data.pop(CONF_PROTOCOL_VARIANT, None)
        if bed_type != BED_TYPE_OCTO:
            data.pop(CONF_OCTO_PIN, None)
        if bed_type != BED_TYPE_JENSEN:
            data.pop(CONF_JENSEN_PIN, None)
        if bed_type != BED_TYPE_RICHMAT:
            data.pop(CONF_RICHMAT_REMOTE, None)
        if bed_type not in MALOUF_BED_TYPES:
            data.pop(CONF_MALOUF_LAYOUT, None)
            data.pop(CONF_MALOUF_MEMORY_SLOTS, None)
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
        drop_bond_marker = requires_pairing(previous_bed_type, previous_variant) != requires_pairing(
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
        if is_paired(data):
            menu_options.append(
                "revert_sides"
                if data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS
                else "unpair"
            )
        elif supports_single_address_pairing(
            data.get(CONF_BED_TYPE),
            data.get(CONF_PROTOCOL_VARIANT),
            resolved_variant=data.get(CONF_KAIDI_RESOLVED_VARIANT),
        ):
            menu_options.append("pair_sides")
        if data.get(CONF_ADDRESS) or (
            data.get(CONF_PAIR_MODE) == PAIR_MODE_SEPARATE_ADDRESS
            and bool(iter_children(data))
        ):
            menu_options.append("remove_bond")
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    def _async_flow_manager(self) -> Any:
        """Options flows are driven by their own manager, not the config one."""
        return self.hass.config_entries.options

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        return await self._async_options_form(user_input, step_id="settings")

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
        if controller is not None and not getattr(
            controller, "supports_single_address_pairing", True
        ):
            return self.async_show_form(
                step_id="pair_sides",
                data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
                errors={"base": "single_address_pairing_unsupported"},
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
                    for row in er.async_entries_for_config_entry(
                        registry, entry.entry_id
                    )
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
                paired_data[KEY_SINGLE_ADDRESS_ORIGIN_ENTITY_UNIQUE_IDS] = (
                    origin_unique_ids
                )
                try:
                    if not await self.hass.config_entries.async_unload(entry.entry_id):
                        raise RuntimeError("could not unload entry")
                    self.hass.config_entries.async_update_entry(
                        entry, data=paired_data
                    )
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
                    _LOGGER.exception(
                        "Could not enable paired sides for config entry %s", entry_id
                    )

            self.hass.async_create_task(
                finish_pair_sides(), f"adjustable_bed_pair_sides_{entry_id}"
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="pair_sides",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

    async def _async_options_form(
        self,
        user_input: dict[str, Any] | None,
        *,
        step_id: str,
    ) -> ConfigFlowResult:
        """Show and save the normal options form."""
        # Get current values from config entry
        current_data: dict[str, Any] = dict(self.config_entry.data)
        if is_paired(current_data) and current_data.get(CONF_PAIR_MODE) != (
            PAIR_MODE_SINGLE_ADDRESS
        ):
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
        current_data = {**current_data, **self._pending_data}
        bed_type = current_data.get(CONF_BED_TYPE)
        if bed_type is None:
            bed_type = BED_TYPE_DIAGNOSTIC

        bed_type_options = get_bed_type_options()
        if bed_type not in {option["value"] for option in bed_type_options}:
            bed_type_options.insert(
                0,
                SelectOptionDict(
                    value=bed_type,
                    label=BED_TYPE_DISPLAY_NAMES.get(bed_type, bed_type),
                ),
            )
        variants = get_variants_for_bed_type(bed_type)
        form_variant = self._variant_for_bed_type(bed_type, current_data)
        has_position_feedback = bed_type_has_position_feedback(bed_type, form_variant)
        form_pulse_defaults = get_motor_pulse_defaults(bed_type, form_variant)
        motor_count_options = _motor_count_options_for_all_variants(bed_type)
        try:
            form_motor_count = int(current_data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT))
        except (TypeError, ValueError):
            form_motor_count = DEFAULT_MOTOR_COUNT
        if form_motor_count not in motor_count_options:
            form_motor_count = _default_motor_count(
                bed_type,
                current_data.get(CONF_NAME),
            )
            if form_motor_count not in motor_count_options:
                form_motor_count = motor_count_options[0]

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Get current adapter, falling back to auto if stored adapter no longer exists
        current_adapter = current_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        if current_adapter not in adapters:
            current_adapter = ADAPTER_AUTO

        # Global discovery toggle (shared across all beds, not stored per-entry)
        discovery_disabled = self._pending_data.get(
            CONF_DISABLE_DISCOVERY,
            await async_is_discovery_disabled(self.hass),
        )

        # Build schema
        schema_dict = {
            vol.Optional(CONF_BED_TYPE, default=bed_type): SelectSelector(
                SelectSelectorConfig(
                    options=bed_type_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_MOTOR_COUNT,
                default=form_motor_count,
            ): vol.All(
                vol.Coerce(int),
                vol.In(motor_count_options),
            ),
            vol.Optional(
                CONF_HAS_MASSAGE,
                default=current_data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
            ): bool,
            vol.Optional(
                CONF_PREFERRED_ADAPTER,
                default=current_adapter,
            ): vol.In(adapters),
            vol.Optional(
                CONF_CONNECTION_PROFILE,
                default=current_data.get(CONF_CONNECTION_PROFILE, DEFAULT_CONNECTION_PROFILE),
            ): vol.In(CONNECTION_PROFILE_OPTIONS),
            vol.Optional(
                CONF_MOTOR_PULSE_COUNT,
                default=str(current_data.get(CONF_MOTOR_PULSE_COUNT, form_pulse_defaults[0])),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_MOTOR_PULSE_DELAY_MS,
                default=str(current_data.get(CONF_MOTOR_PULSE_DELAY_MS, form_pulse_defaults[1])),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_DISCONNECT_AFTER_COMMAND,
                default=current_data.get(
                    CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
                ),
            ): bool,
            vol.Optional(
                CONF_IDLE_DISCONNECT_SECONDS,
                default=current_data.get(
                    CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            vol.Optional(
                CONF_DISABLE_DISCOVERY,
                default=discovery_disabled,
            ): bool,
        }

        if has_position_feedback:
            schema_dict[
                vol.Optional(
                    CONF_DISABLE_ANGLE_SENSING,
                    default=current_data.get(
                        CONF_DISABLE_ANGLE_SENSING,
                        DEFAULT_DISABLE_ANGLE_SENSING,
                    ),
                )
            ] = bool
            schema_dict[
                vol.Optional(
                    CONF_POSITION_MODE,
                    default=current_data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE),
                )
            ] = vol.In(
                {
                    POSITION_MODE_SPEED: "Speed (recommended)",
                    POSITION_MODE_ACCURACY: "Accuracy",
                }
            )

        if supports_passive_position_reconciliation(bed_type):
            schema_dict[
                vol.Optional(
                    CONF_PASSIVE_POSITION_RECONCILIATION,
                    default=current_data.get(
                        CONF_PASSIVE_POSITION_RECONCILIATION,
                        passive_position_reconciliation_default_enabled(bed_type),
                    ),
                )
            ] = bool

        # Add variant selection if the bed type has variants
        if variants:
            schema_dict[
                vol.Optional(
                    CONF_PROTOCOL_VARIANT,
                    default=form_variant,
                )
            ] = vol.In(variants)

        # Add PIN field for Octo beds
        if bed_type == BED_TYPE_OCTO:
            schema_dict[
                vol.Optional(
                    CONF_OCTO_PIN,
                    default=current_data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN),
                )
            ] = TextSelector(TextSelectorConfig())

        # Add PIN field for Jensen beds
        if bed_type == BED_TYPE_JENSEN:
            schema_dict[
                vol.Optional(
                    CONF_JENSEN_PIN,
                    default=current_data.get(CONF_JENSEN_PIN, ""),
                )
            ] = TextSelector(TextSelectorConfig())

        # Add remote selection for Richmat beds
        if bed_type == BED_TYPE_RICHMAT:
            current_remote = current_data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO)
            remote_options = dict(RICHMAT_REMOTES)
            if current_remote not in remote_options:
                remote_options[current_remote] = f"{current_remote.upper()} (current detected code)"
            schema_dict[
                vol.Optional(
                    CONF_RICHMAT_REMOTE,
                    default=current_remote,
                )
            ] = vol.In(remote_options)

        if bed_type in MALOUF_BED_TYPES:
            schema_dict[
                vol.Optional(
                    CONF_MALOUF_LAYOUT,
                    default=current_data.get(CONF_MALOUF_LAYOUT, MALOUF_LAYOUT_AUTO),
                )
            ] = vol.In(MALOUF_LAYOUTS)
            schema_dict[
                vol.Optional(
                    CONF_MALOUF_MEMORY_SLOTS,
                    default=current_data.get(CONF_MALOUF_MEMORY_SLOTS, MALOUF_MEMORY_SLOTS_AUTO),
                )
            ] = vol.All(vol.Coerce(int), vol.In(MALOUF_MEMORY_SLOT_OPTIONS))

        if bed_type == BED_TYPE_OKIN_CB24:
            schema_dict[
                vol.Optional(
                    CONF_CB24_BED_SELECTION,
                    default=current_data.get(
                        CONF_CB24_BED_SELECTION, CB24_BED_SELECTION_DEFAULT
                    ),
                )
            ] = vol.In(
                {
                    CB24_BED_SELECTION_DEFAULT: "Both sides",
                    CB24_BED_SELECTION_A: "Side A / Left",
                    CB24_BED_SELECTION_B: "Side B / Right",
                }
            )

        # Add angle limit fields for beds that use angle-based positions
        # (not percentage-based beds like Keeson/Ergomotion/Serta/Jensen)
        # Only show for beds that actually support position feedback
        if (
            bed_type
            and bed_type not in BEDS_WITH_PERCENTAGE_POSITIONS
            and has_position_feedback
        ):
            schema_dict[
                vol.Optional(
                    CONF_BACK_MAX_ANGLE,
                    default=str(current_data.get(CONF_BACK_MAX_ANGLE, DEFAULT_BACK_MAX_ANGLE)),
                )
            ] = TextSelector(TextSelectorConfig())
            schema_dict[
                vol.Optional(
                    CONF_LEGS_MAX_ANGLE,
                    default=str(current_data.get(CONF_LEGS_MAX_ANGLE, DEFAULT_LEGS_MAX_ANGLE)),
                )
            ] = TextSelector(TextSelectorConfig())

        if user_input is not None:
            requested_bed_type = user_input.get(CONF_BED_TYPE, bed_type)
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
            if bed_type == BED_TYPE_OCTO and CONF_OCTO_PIN in user_input:
                octo_pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN))
                if not is_valid_octo_pin(octo_pin):
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_OCTO_PIN: "invalid_pin"},
                    )
                user_input[CONF_OCTO_PIN] = octo_pin
            if (
                self.config_entry.data.get(CONF_PAIR_MODE)
                == PAIR_MODE_SINGLE_ADDRESS
                and not supports_single_address_pairing(
                    bed_type,
                    user_input.get(
                        CONF_PROTOCOL_VARIANT,
                        current_data.get(
                            CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT
                        ),
                    ),
                    resolved_variant=current_data.get(
                        CONF_KAIDI_RESOLVED_VARIANT
                    ),
                )
            ):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "single_address_pairing_unsupported"},
                )
            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = get_motor_pulse_defaults(
                bed_type,
                requested_variant,
            )
            # Convert text values to integers
            try:
                if CONF_MOTOR_PULSE_COUNT in user_input:
                    user_input[CONF_MOTOR_PULSE_COUNT] = int(
                        user_input[CONF_MOTOR_PULSE_COUNT] or pulse_defaults[0]
                    )
                if CONF_MOTOR_PULSE_DELAY_MS in user_input:
                    user_input[CONF_MOTOR_PULSE_DELAY_MS] = int(
                        user_input[CONF_MOTOR_PULSE_DELAY_MS] or pulse_defaults[1]
                    )
            except ValueError, TypeError:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "invalid_number"},
                )
            # Convert angle limit values to floats with field-specific error handling
            if CONF_BACK_MAX_ANGLE in user_input:
                try:
                    value = float(user_input[CONF_BACK_MAX_ANGLE] or DEFAULT_BACK_MAX_ANGLE)
                    if value <= 0 or value > 180:
                        return self.async_show_form(
                            step_id=step_id,
                            data_schema=vol.Schema(schema_dict),
                            errors={CONF_BACK_MAX_ANGLE: "invalid_angle"},
                        )
                    user_input[CONF_BACK_MAX_ANGLE] = value
                except ValueError, TypeError:
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_BACK_MAX_ANGLE: "invalid_angle"},
                    )
            if CONF_LEGS_MAX_ANGLE in user_input:
                try:
                    value = float(user_input[CONF_LEGS_MAX_ANGLE] or DEFAULT_LEGS_MAX_ANGLE)
                    if value <= 0 or value > 180:
                        return self.async_show_form(
                            step_id=step_id,
                            data_schema=vol.Schema(schema_dict),
                            errors={CONF_LEGS_MAX_ANGLE: "invalid_angle"},
                        )
                    user_input[CONF_LEGS_MAX_ANGLE] = value
                except ValueError, TypeError:
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_LEGS_MAX_ANGLE: "invalid_angle"},
                    )
            # All validations passed - now it is safe to commit global state.
            if discovery_disabled_input is not None:
                await async_set_discovery_disabled(self.hass, discovery_disabled_input)
            # Update the config entry with new options
            # Record that the stored cadence is the user's choice rather than a
            # value the flow generated, so protocol migrations leave it alone.
            # The pulse fields are always present in this form, so saving it at
            # all means the user saw and accepted the values.
            pulse_user_set = (
                CONF_MOTOR_PULSE_COUNT in user_input or CONF_MOTOR_PULSE_DELAY_MS in user_input
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
                changed = {**self._pending_changed_data, **current_changed}
                new_data = {**self.config_entry.data, **changed}
                if pulse_user_set:
                    new_data[CONF_MOTOR_PULSE_USER_SET] = True
                if (
                    self.config_entry.data.get(CONF_PAIR_MODE)
                    == PAIR_MODE_SINGLE_ADDRESS
                ):
                    self._apply_bed_type_change_cleanup(new_data, bed_type, requested_variant)
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )
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
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
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
            self.config_entry.data.get(CONF_PAIR_MODE)
            == PAIR_MODE_SEPARATE_ADDRESS
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
            _LOGGER.warning(
                "Could not remove the bond for %s: %s", self.config_entry.title, err
            )
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
                "name": self._bond_target_data().get(CONF_NAME)
                or self.config_entry.title,
                "outcome": await self._async_bond_removal_outcome_note(succeeded, detail),
            },
        )
