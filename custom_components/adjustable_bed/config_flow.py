"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Any, cast

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
    select_adapter,
)
from .const import (
    ADAPTER_AUTO,
    ALL_PROTOCOL_VARIANTS,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_JENSEN,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
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
    BEDS_WITH_PERCENTAGE_POSITIONS,
    BEDS_WITH_POSITION_FEEDBACK,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISABLE_DISCOVERY,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_LEGS_MAX_ANGLE,
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
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
    KEESON_VARIANT_ERGOMOTION,
    LEGGETT_VARIANT_GEN2,
    MALOUF_LAYOUT_AUTO,
    MALOUF_LAYOUTS,
    MALOUF_MEMORY_SLOT_OPTIONS,
    MALOUF_MEMORY_SLOTS_AUTO,
    OCTO_VARIANT_STAR2,
    OFFLINE_CAPABILITY_SAFE_BED_TYPES,
    PAIR_MODE_SINGLE_ADDRESS,
    PAIR_SIDES,
    POSITION_MODE_ACCURACY,
    POSITION_MODE_SPEED,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTES,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
    DetectionResult,
    get_richmat_features,
    get_richmat_motor_count,
    passive_position_reconciliation_default_enabled,
    requires_pairing,
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
    get_child,
    is_paired,
    iter_children,
    pair_member_addresses,
    supports_single_address_pairing,
    with_updated_child,
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


class AdjustableBedConfigFlow(ConfigFlow, domain=DOMAIN):
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

    def _create_entry_for_existing_bond(self) -> ConfigFlowResult:
        """Create an entry after the user confirms the adapter is already bonded."""
        assert self._manual_data is not None
        _LOGGER.info(
            "User confirmed an existing BLE bond for %s via adapter %s",
            self._manual_data.get(CONF_ADDRESS),
            self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
        )
        return self.async_create_entry(
            title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
            data=self._mark_ble_bond_established(self._manual_data),
        )

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
        # Octo capability snapshots captured per single-entry as the user connects
        # each side, so a one-link Octo pair can be captured SEQUENTIALLY across
        # resubmissions of the pair step (connect left, disconnect, connect right)
        # — the flow instance persists, so a side captured while live stays
        # available after it disconnects.
        self._captured_octo_snapshots: dict[str, dict[str, Any]] = {}
        _LOGGER.debug("AdjustableBedConfigFlow initialized")

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
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "config", {DOMAIN}
        )
        return translations.get(f"component.{DOMAIN}.config.{key}", default)

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
                "2. Plug the bed back in. You'll hear a small chime and see a pulsing blue light "
                "under the bed - the bed stays in pairing mode for about 2 minutes.\n"
                "3. While the light is pulsing, click 'Pair Now'.",
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
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}

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
                "name": self._discovery_info.name or self._discovery_info.address,
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

            # Validate protocol variant is valid for selected bed type
            if selected_bed_type and not is_valid_variant_for_bed_type(
                selected_bed_type, protocol_variant
            ):
                errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
                str(selected_bed_type) if selected_bed_type else "",
                (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS),
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
            _LOGGER.info(
                "User confirmed bed setup: name=%s, type=%s (detected: %s), variant=%s, address=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s, pulse_count=%s, pulse_delay=%s",
                user_input.get(CONF_NAME, self._discovery_info.name or "Adjustable Bed"),
                selected_bed_type,
                detected_bed_type,
                protocol_variant,
                self._discovery_info.address,
                user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                preferred_adapter,
                motor_pulse_count,
                motor_pulse_delay_ms,
            )
            if not errors:
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
                    CONF_DISCONNECT_AFTER_COMMAND: user_input.get(
                        CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
                    ),
                    CONF_IDLE_DISCONNECT_SECONDS: user_input.get(
                        CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS
                    ),
                }
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

        # Default angle sensing to enabled for beds that support position feedback
        default_disable_angle = bed_type not in BEDS_WITH_POSITION_FEEDBACK

        # Get bed-type-specific motor pulse defaults
        pulse_defaults = (
            BED_MOTOR_PULSE_DEFAULTS.get(
                bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
            )
            if bed_type
            else (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
        )
        default_pulse_count, default_pulse_delay = pulse_defaults

        # Auto-detect motor count for Richmat beds based on remote code features
        default_motor_count = DEFAULT_MOTOR_COUNT
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
        bed_type_default: Any = bed_type
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
            # Default to an explicit disambiguation choice or a high-confidence,
            # unambiguous detection; otherwise keep "Auto-detect" selected so an
            # ambiguous/low-confidence guess isn't silently accepted.
            bed_type_default = (
                self._disambiguated_bed_type
                or _confident_auto_detect(detection_result)
                or BED_TYPE_AUTO_DETECT
            )
        else:
            bed_type_selector = vol.In(SUPPORTED_BED_TYPES)

        schema_dict: dict[vol.Marker, Any] = {
            vol.Optional(CONF_BED_TYPE, default=bed_type_default): bed_type_selector,
            vol.Optional(CONF_NAME, default=self._discovery_info.name or "Adjustable Bed"): str,
            vol.Optional(CONF_MOTOR_COUNT, default=default_motor_count): vol.All(
                vol.Coerce(int), vol.In([2, 3, 4])
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
                CONF_DISCONNECT_AFTER_COMMAND, default=DEFAULT_DISCONNECT_AFTER_COMMAND
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
            "name": self._discovery_info.name or self._discovery_info.address,
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
        return [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if not is_paired(entry.data)
            and entry.data.get(CONF_ADDRESS)
            and not self._is_absorbed_pair_member(entry.data[CONF_ADDRESS])
            # Only fully-loaded beds: a bed still in SETUP_RETRY / failed initial
            # setup hasn't registered its entities yet, so _has_unpairable_entities
            # can't see climate/light/select it would later expose (which a pair
            # doesn't forward and would drop).
            and entry.state == ConfigEntryState.LOADED
        ]

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
            left = by_id.get(user_input["left_entry"])
            right = by_id.get(user_input["right_entry"])
            left_layout = await self._pair_layout_snapshot(left) if left is not None else None
            right_layout = await self._pair_layout_snapshot(right) if right is not None else None
            if left is None or right is None:
                errors["base"] = "unknown"
            elif left.entry_id == right.entry_id:
                errors["right_entry"] = "same_device"
            elif (left.data.get(CONF_ADDRESS) or "").upper() == (
                right.data.get(CONF_ADDRESS) or ""
            ).upper():
                # Two distinct entries for the same MAC would build children with
                # identical addresses and so collide on {address}_{key} unique IDs.
                errors["right_entry"] = "same_address"
            elif self._offline_safe_bed_type(left) != self._offline_safe_bed_type(right):
                # Compare RESOLVED bed types: two legacy leggett_platt entries with
                # DIFFERENT explicit variants (gen2 vs mlrm) are different concrete
                # protocols, so they're an incompatible pair even though their raw
                # umbrella type matches — and would otherwise be stored as mismatched
                # concrete child types by _resolved_pair_side_data below.
                errors["base"] = "mismatched_bed_types"
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

        options = [
            SelectOptionDict(value=entry.entry_id, label=entry.title or entry.entry_id)
            for entry in entries
        ]
        side_selector = SelectSelector(
            SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
        )
        return self.async_show_form(
            step_id="pair_beds",
            data_schema=vol.Schema(
                {
                    vol.Required("left_entry"): side_selector,
                    vol.Required("right_entry"): side_selector,
                    vol.Optional(CONF_NAME): str,
                }
            ),
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
        else:
            # This shouldn't happen, but handle gracefully
            return await self.async_step_manual_entry()

        if user_input is not None:
            bed_type = user_input[CONF_BED_TYPE]

            # "Auto-detect" resolves only to a high-confidence, unambiguous match;
            # otherwise it re-shows the form with a clear error instead of silently
            # configuring a guessed protocol (issue #385).
            if bed_type == BED_TYPE_AUTO_DETECT:
                resolved = _confident_auto_detect(detect_bed_type_detailed(self._discovery_info))
                if resolved:
                    _LOGGER.info("Auto-detect resolved bed type to %s for %s", resolved, address)
                    bed_type = resolved
                else:
                    errors["base"] = "auto_detect_failed"

            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, str(discovery_source))
            protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)

            # Validate protocol variant is valid for bed type
            if bed_type != BED_TYPE_AUTO_DETECT and not is_valid_variant_for_bed_type(
                bed_type, protocol_variant
            ):
                errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
                bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
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
                    CONF_DISCONNECT_AFTER_COMMAND: user_input.get(
                        CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
                    ),
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

        # Check if bed type was pre-selected from two-tier actuator selection
        preselected_bed_type = self._selected_bed_type
        preselected_protocol_variant = self._selected_protocol_variant or VARIANT_AUTO
        detected_bed_type = detect_bed_type(self._discovery_info)
        # Only a high-confidence, unambiguous detection becomes the Auto-detect
        # default; ambiguous/low-confidence guesses keep "Auto-detect" selected.
        confident_bed_type = _confident_auto_detect(detect_bed_type_detailed(self._discovery_info))

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
        defaults_bed_type = preselected_bed_type or confident_bed_type
        if defaults_bed_type:
            # Keeson with Ergomotion variant supports position feedback
            has_position_feedback = defaults_bed_type in BEDS_WITH_POSITION_FEEDBACK or (
                defaults_bed_type == BED_TYPE_KEESON
                and preselected_protocol_variant == KEESON_VARIANT_ERGOMOTION
            )
            default_disable_angle = not has_position_feedback
            # Use bed-specific motor pulse defaults if available
            pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
                defaults_bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
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
                vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.All(
                    vol.Coerce(int), vol.In([2, 3, 4])
                ),
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
                    CONF_DISCONNECT_AFTER_COMMAND, default=DEFAULT_DISCONNECT_AFTER_COMMAND
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
            },
        )

    async def async_step_manual_entry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual address entry when user types in the MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().replace("-", ":")
            bed_type = user_input[CONF_BED_TYPE]

            # Validate MAC address format
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)

                # Validate protocol variant is valid for bed type
                if not is_valid_variant_for_bed_type(bed_type, protocol_variant):
                    errors[CONF_PROTOCOL_VARIANT] = "invalid_variant_for_bed_type"

                # Get bed-specific defaults for motor pulse settings
                pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
                    bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
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
                        CONF_DISCONNECT_AFTER_COMMAND: user_input.get(
                            CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND
                        ),
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
        preselected_bed_type = self._selected_bed_type
        preselected_protocol_variant = self._selected_protocol_variant or VARIANT_AUTO

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
            has_position_feedback = preselected_bed_type in BEDS_WITH_POSITION_FEEDBACK or (
                preselected_bed_type == BED_TYPE_KEESON
                and preselected_protocol_variant == KEESON_VARIANT_ERGOMOTION
            )
            default_disable_angle = not has_position_feedback
            # Use bed-specific motor pulse defaults if available
            pulse_defaults = BED_MOTOR_PULSE_DEFAULTS.get(
                preselected_bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
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
                    vol.Coerce(int), vol.In([2, 3, 4])
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
                    CONF_DISCONNECT_AFTER_COMMAND, default=DEFAULT_DISCONNECT_AFTER_COMMAND
                ): bool,
                vol.Optional(
                    CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )
        if preselected_bed_type in MALOUF_BED_TYPES:
            _add_malouf_schema_fields(schema_dict)
        if preselected_bed_type == BED_TYPE_OKIN_CB24:
            _add_cb24_side_schema_field(schema_dict)

        return self.async_show_form(
            step_id="manual_entry",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
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

    async def async_step_bluetooth_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth pairing for beds that require it."""
        assert self._manual_data is not None

        errors: dict[str, str] = {}
        description_placeholders = {
            "name": self._manual_data.get(CONF_NAME, "Unknown"),
            "pairing_instructions": await self._get_pairing_instructions(
                self._manual_data.get(CONF_BED_TYPE),
                self._manual_data.get(CONF_PROTOCOL_VARIANT),
            ),
        }

        if user_input is not None:
            action = user_input.get("action")

            if action == "pair_now":
                # Attempt pairing
                address = self._manual_data.get(CONF_ADDRESS)
                try:
                    paired = await self._attempt_pairing(address)
                    if paired:
                        return self.async_create_entry(
                            title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                            data=self._mark_ble_bond_established(self._manual_data),
                        )
                    else:
                        errors["base"] = "pairing_failed"
                except (NotImplementedError, TypeError) as err:
                    # NotImplementedError: ESPHome < 2024.3.0 doesn't support pairing
                    # TypeError: older bleak-retry-connector doesn't have pair kwarg
                    _LOGGER.warning("Pairing not supported: %s", err)
                    errors["base"] = "pairing_not_supported"
                except Exception as err:
                    _LOGGER.warning("Pairing failed for %s: %s", address, err)
                    errors["base"] = "pairing_failed"

            elif action == "skip_pairing":
                return self._create_entry_for_existing_bond()

        return self.async_show_form(
            step_id="bluetooth_pairing",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value="pair_now", label="Pair Now"),
                                SelectOptionDict(
                                    value="skip_pairing", label="Skip (already paired)"
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_manual_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth pairing for manually selected beds that require it."""
        assert self._manual_data is not None

        errors: dict[str, str] = {}
        description_placeholders = {
            "name": self._manual_data.get(CONF_NAME, "Unknown"),
            "pairing_instructions": await self._get_pairing_instructions(
                self._manual_data.get(CONF_BED_TYPE),
                self._manual_data.get(CONF_PROTOCOL_VARIANT),
            ),
        }

        if user_input is not None:
            action = user_input.get("action")

            if action == "pair_now":
                # Attempt pairing
                address = self._manual_data.get(CONF_ADDRESS)
                try:
                    paired = await self._attempt_pairing(address)
                    if paired:
                        return self.async_create_entry(
                            title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                            data=self._mark_ble_bond_established(self._manual_data),
                        )
                    else:
                        errors["base"] = "pairing_failed"
                except (NotImplementedError, TypeError) as err:
                    # NotImplementedError: ESPHome < 2024.3.0 doesn't support pairing
                    # TypeError: older bleak-retry-connector doesn't have pair kwarg
                    _LOGGER.warning("Pairing not supported: %s", err)
                    errors["base"] = "pairing_not_supported"
                except Exception as err:
                    _LOGGER.warning("Pairing failed for %s: %s", address, err)
                    errors["base"] = "pairing_failed"

            elif action == "skip_pairing":
                return self._create_entry_for_existing_bond()

        return self.async_show_form(
            step_id="manual_pairing",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value="pair_now", label="Pair Now"),
                                SelectOptionDict(
                                    value="skip_pairing", label="Skip (already paired)"
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def _attempt_pairing(self, address: str | None) -> bool:
        """Attempt to pair with the device using establish_connection with pair=True.

        Returns:
            True if pairing succeeded, False otherwise

        Raises:
            NotImplementedError: If the Bluetooth backend doesn't support pairing
            Exception: If pairing fails for other reasons
        """
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        if not address:
            raise ValueError("No address provided for pairing")

        # Get preferred adapter from config data
        preferred_adapter = ADAPTER_AUTO
        if self._manual_data:
            preferred_adapter = self._manual_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)

        _LOGGER.info(
            "Attempting to pair with %s (preferred adapter: %s)...",
            address,
            preferred_adapter,
        )

        # Find the device from discovered service info, respecting preferred adapter
        address_upper = address.upper()
        matching_service_info = None

        for service_info in get_discovered_service_info(
            self.hass,
            include_non_connectable=True,
        ):
            if service_info.address.upper() != address_upper:
                continue
            # Check adapter preference
            source = getattr(service_info, "source", None)
            if preferred_adapter == ADAPTER_AUTO:
                # Accept any adapter
                matching_service_info = service_info
                break
            elif source == preferred_adapter:
                # Exact match for preferred adapter
                matching_service_info = service_info
                break

        if not matching_service_info:
            if preferred_adapter != ADAPTER_AUTO:
                raise ValueError(
                    f"Device {address} not found via adapter '{preferred_adapter}'. "
                    "Try setting adapter to 'auto' or ensure the device is in range of the preferred adapter."
                )
            raise ValueError(f"Device {address} not found in Bluetooth scan")

        device = matching_service_info.device
        _LOGGER.debug(
            "Found device %s via adapter %s (connectable=%s)",
            address,
            getattr(matching_service_info, "source", "unknown"),
            getattr(matching_service_info, "connectable", None),
        )

        # Connect with pairing enabled - this handles both built-in HA Bluetooth
        # (pairing during connection) and ESPHome proxy (pairing after connection)
        client = await establish_connection(
            BleakClient,
            device,
            address,
            max_attempts=1,
            timeout=CONNECTION_PROFILES[DEFAULT_CONNECTION_PROFILE].connection_timeout,
            pair=True,
        )
        try:
            # Connection with pair=True succeeded - pairing is complete
            _LOGGER.info("Pairing successful for %s", address)
            return True
        finally:
            await client.disconnect()

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
        return await self.async_step_verify_connection()

    async def _probe_capabilities(
        self,
        address: str,
        preferred_adapter: str | None,
        bed_type: str | None,
        protocol_variant: str | None = None,
    ) -> CapabilityReport:
        """Connect once (read-only) and report what was detected.

        This never sends a movement/control command - it only selects an adapter,
        establishes a connection, discovers GATT services, and reads the standard
        Device Information service. It always disconnects in ``finally`` so the
        coordinator can take the bed's single BLE connection afterwards, and it
        never raises: any failure is captured in ``report.error`` so setup stays
        non-blocking.
        """
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection

        # Keeson exposes position feedback only on its Ergomotion variant, so
        # mirror the same special-case the confirm step uses for angle sensing.
        has_position_feedback = bool(bed_type) and (
            bed_type in BEDS_WITH_POSITION_FEEDBACK
            or (bed_type == BED_TYPE_KEESON and protocol_variant == KEESON_VARIANT_ERGOMOTION)
        )
        report = CapabilityReport(position_feedback=has_position_feedback)

        try:
            selection = await select_adapter(self.hass, address, preferred_adapter)
        except Exception as err:  # noqa: BLE001 - probe is best-effort
            report.error = str(err) or err.__class__.__name__
            return report

        device = selection.device
        if device is None:
            report.error = "device_not_found"
            return report

        report.device_found = True
        report.source = selection.source
        report.rssi = selection.rssi
        report.via_proxy = bool(selection.source and "esphome" in selection.source.lower())

        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClient,
                device,
                address,
                max_attempts=1,
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
            report.connected = bool(client.is_connected)
            await discover_services(client, address)
            services = list(client.services) if client.services else []
            report.service_count = len(services)
            writable = 0
            for service in services:
                for char in service.characteristics:
                    if "write" in char.properties or "write-without-response" in char.properties:
                        writable += 1
            report.writable_count = writable
            report.manufacturer, report.model = await read_ble_device_info(client, address)
        except Exception as err:  # noqa: BLE001 - probe is best-effort
            report.error = str(err) or err.__class__.__name__
            _LOGGER.debug("Capability probe for %s failed: %s", address, err)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001 - cleanup must not raise
                    pass

        return report

    @staticmethod
    def _format_capabilities(report: CapabilityReport) -> str:
        """Build the ✅/❌/⚠️/ℹ️ markdown checklist shown in verify_connection."""
        lines: list[str] = []

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

        connected_parts = ["✅ Connected"]
        if report.source:
            connected_parts.append(f"via {report.source}")
        if report.via_proxy:
            connected_parts.append("(ESPHome proxy)")
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
        """Probe the bed once (read-only) and show a capability checklist.

        Shown after the confirm/manual step for non-PIN/non-pairing beds. The
        Submit button always finishes setup - a failed probe is informational
        only and never blocks entry creation.
        """
        assert self._pending_entry is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._pending_title or self._pending_entry.get(CONF_NAME, "Adjustable Bed"),
                data=self._pending_entry,
            )

        report = await self._probe_capabilities(
            self._pending_entry[CONF_ADDRESS],
            self._pending_entry.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
            self._pending_entry.get(CONF_BED_TYPE),
            self._pending_entry.get(CONF_PROTOCOL_VARIANT),
        )

        return self.async_show_form(
            step_id="verify_connection",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._pending_entry.get(CONF_NAME) or self._pending_entry[CONF_ADDRESS],
                "capabilities": self._format_capabilities(report),
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


class AdjustableBedOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle Adjustable Bed options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if is_paired(self.config_entry.data) and user_input is None:
            action = (
                "revert_sides"
                if self.config_entry.data.get(CONF_PAIR_MODE)
                == PAIR_MODE_SINGLE_ADDRESS
                else "unpair"
            )
            return self.async_show_menu(
                step_id="init", menu_options=["settings", action]
            )
        if user_input is None and supports_single_address_pairing(
            self.config_entry.data.get(CONF_BED_TYPE),
            self.config_entry.data.get(CONF_PROTOCOL_VARIANT),
        ):
            return self.async_show_menu(
                step_id="init", menu_options=["settings", "pair_sides"]
            )
        return await self._async_options_form(user_input, step_id="init")

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage settings for a paired bed."""
        return await self._async_options_form(user_input, step_id="init")

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
        bed_type = current_data.get(CONF_BED_TYPE)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Get current adapter, falling back to auto if stored adapter no longer exists
        current_adapter = current_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        if current_adapter not in adapters:
            current_adapter = ADAPTER_AUTO

        # Global discovery toggle (shared across all beds, not stored per-entry)
        discovery_disabled = await async_is_discovery_disabled(self.hass)

        # Build schema
        schema_dict = {
            vol.Optional(
                CONF_MOTOR_COUNT,
                default=current_data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
            ): vol.All(vol.Coerce(int), vol.In([2, 3, 4])),
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
                default=str(current_data.get(CONF_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_COUNT)),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_MOTOR_PULSE_DELAY_MS,
                default=str(
                    current_data.get(CONF_MOTOR_PULSE_DELAY_MS, DEFAULT_MOTOR_PULSE_DELAY_MS)
                ),
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
                CONF_DISABLE_ANGLE_SENSING,
                default=current_data.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
            ): bool,
            vol.Optional(
                CONF_POSITION_MODE,
                default=current_data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE),
            ): vol.In(
                {
                    POSITION_MODE_SPEED: "Speed (recommended)",
                    POSITION_MODE_ACCURACY: "Accuracy",
                }
            ),
            vol.Optional(
                CONF_DISABLE_DISCOVERY,
                default=discovery_disabled,
            ): bool,
        }

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
        variants = get_variants_for_bed_type(bed_type)
        if variants:
            schema_dict[
                vol.Optional(
                    CONF_PROTOCOL_VARIANT,
                    default=current_data.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT),
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
            schema_dict[
                vol.Optional(
                    CONF_RICHMAT_REMOTE,
                    default=current_data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO),
                )
            ] = vol.In(RICHMAT_REMOTES)

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
            and bed_type in BEDS_WITH_POSITION_FEEDBACK
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
            # The discovery toggle is global, not per-entry: pull it out of
            # user_input now so it is never written into entry data, but only
            # persist it on the success path below - otherwise a later
            # validation failure would partially apply the rejected form.
            discovery_disabled_input: bool | None = None
            if CONF_DISABLE_DISCOVERY in user_input:
                discovery_disabled_input = bool(user_input.pop(CONF_DISABLE_DISCOVERY))
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
                )
            ):
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "single_address_pairing_unsupported"},
                )
            # Get bed-specific defaults for motor pulse settings
            pulse_defaults = (
                BED_MOTOR_PULSE_DEFAULTS.get(
                    bed_type, (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
                )
                if bed_type
                else (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
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
                changed = {
                    key: value
                    for key, value in user_input.items()
                    if key in shown and shown[key] != value
                }
                new_data = {**self.config_entry.data, **changed}
                if (
                    self.config_entry.data.get(CONF_PAIR_MODE)
                    == PAIR_MODE_SINGLE_ADDRESS
                ):
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
                new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_dict),
        )
