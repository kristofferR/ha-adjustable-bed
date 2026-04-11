"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.helpers.translation import async_get_translations

from .actuator_groups import (
    ACTUATOR_GROUPS,
    SINGLE_TYPE_GROUPS,
)
from .adapter import find_service_info_by_address, get_discovered_service_info
from .const import (
    ADAPTER_AUTO,
    ALL_PROTOCOL_VARIANTS,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_JENSEN,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEP_NUMBER,
    BEDS_WITH_PERCENTAGE_POSITIONS,
    BEDS_WITH_POSITION_FEEDBACK,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_CONNECTION_PROFILE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_LEGS_MAX_ANGLE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
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
    POSITION_MODE_ACCURACY,
    POSITION_MODE_SPEED,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTES,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
    get_richmat_features,
    get_richmat_motor_count,
    requires_pairing,
)
from .detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type,
    detect_bed_type_detailed,
    detect_richmat_remote_from_name,
    determine_unsupported_reason,
    get_bed_type_options,
    is_mac_like_name,
)
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .unsupported import (
    capture_device_info,
    create_unsupported_device_issue,
    log_unsupported_device,
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

CONNECTION_PROFILE_OPTIONS: dict[str, str] = {
    CONNECTION_PROFILE_BALANCED: "Balanced (recommended)",
    CONNECTION_PROFILE_RELIABLE: "Reliable (slower connect)",
}


class AdjustableBedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adjustable Bed."""

    VERSION = 3

    @staticmethod
    def _mark_ble_bond_established(entry_data: dict[str, Any]) -> dict[str, Any]:
        """Persist that the bed already has a BLE bond."""
        return {
            **entry_data,
            CONF_BLE_BOND_ESTABLISHED: True,
        }

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
        _LOGGER.debug("AdjustableBedConfigFlow initialized")

    async def _get_config_translation(self, key: str, default: str) -> str:
        """Return a config-flow translation with a safe English fallback."""
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "config", {DOMAIN}
        )
        return translations.get(f"component.{DOMAIN}.config.{key}", default)

    async def _get_pairing_instructions(self, bed_type: str | None) -> str:
        """Return pairing instructions tailored to the selected bed type."""
        if bed_type == BED_TYPE_SLEEP_NUMBER:
            return await self._get_config_translation(
                "step.bluetooth_pairing.data_description.pairing_instructions_sleep_number",
                "1. Put your bed in pairing mode (hold the side pairing button until the blue light blinks)\n"
                "2. Click 'Pair Now'",
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
        """Return configured entries keyed by normalized Bluetooth address."""
        configured: dict[str, ConfigEntry] = {}
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            candidate = entry.unique_id or entry.data.get(CONF_ADDRESS)
            if isinstance(candidate, str):
                configured[candidate.upper()] = entry
        return configured

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

        # Use detailed detection to get confidence and ambiguity info
        detection_result = detect_bed_type_detailed(discovery_info)
        bed_type = detection_result.bed_type

        if bed_type is None:
            # Check if device was excluded as a known non-bed device
            is_excluded = any(s.startswith("excluded:") for s in detection_result.signals)

            if not is_excluded:
                # Only create Repairs issue for genuinely unknown devices,
                # not for devices already identified as non-bed (speakers, etc.)
                device_info = capture_device_info(discovery_info)
                reason = determine_unsupported_reason(discovery_info)
                created = await create_unsupported_device_issue(self.hass, device_info, reason)
                if created:
                    log_unsupported_device(device_info, reason)

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

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}

        # Check if disambiguation is needed (low confidence with alternatives)
        if detection_result.confidence < 0.7 and detection_result.ambiguous_types:
            # Build list of all candidate types (detected + alternatives), deduplicated
            seen: set[str] = set()
            disambiguation_types: list[str] = []
            for t in [bed_type] + list(detection_result.ambiguous_types):
                if t not in seen:
                    seen.add(t)
                    disambiguation_types.append(t)
            self._disambiguation_types = disambiguation_types
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

        if user_input is not None:
            # Get user-selected bed type (may differ from auto-detected)
            selected_bed_type = user_input.get(CONF_BED_TYPE, bed_type)
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
                except (ValueError, TypeError):
                    errors[CONF_MOTOR_PULSE_COUNT] = "invalid_number"
                    motor_pulse_count = pulse_defaults[0]
            else:
                motor_pulse_count = pulse_defaults[0]
            # Validate motor pulse delay
            pulse_delay_input = user_input.get(CONF_MOTOR_PULSE_DELAY_MS)
            if pulse_delay_input is not None and pulse_delay_input != "":
                try:
                    motor_pulse_delay_ms = int(pulse_delay_input)
                except (ValueError, TypeError):
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
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, self._discovery_info.name or "Adjustable Bed"),
                    data=entry_data,
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
        if self._show_full_bed_type_list:
            bed_type_selector = SelectSelector(
                SelectSelectorConfig(
                    options=get_bed_type_options(),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            bed_type_selector = vol.In(SUPPORTED_BED_TYPES)

        schema_dict: dict[vol.Marker, Any] = {
            vol.Optional(CONF_BED_TYPE, default=bed_type): bed_type_selector,
            vol.Optional(CONF_NAME, default=self._discovery_info.name or "Adjustable Bed"): str,
            vol.Optional(CONF_MOTOR_COUNT, default=default_motor_count): vol.In([2, 3, 4]),
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

            _LOGGER.info("User selected device: %s", address)
            # Normalize address to uppercase to match Bluetooth discovery
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()

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

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
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

            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, str(discovery_source))
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
                motor_pulse_count = int(user_input.get(CONF_MOTOR_PULSE_COUNT) or pulse_defaults[0])
                motor_pulse_delay_ms = int(
                    user_input.get(CONF_MOTOR_PULSE_DELAY_MS) or pulse_defaults[1]
                )
            except (ValueError, TypeError):
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
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "Adjustable Bed"),
                    data=entry_data,
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
            schema_dict = {
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
                vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In([2, 3, 4]),
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
                ): vol.In(range(10, 301)),
            }
        )

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
                except (ValueError, TypeError):
                    errors["base"] = "invalid_number"

                if not errors:
                    retrying_entry = self._configured_entries_by_address().get(address)
                    if retrying_entry is not None and retrying_entry.state == ConfigEntryState.SETUP_RETRY:
                        self._retrying_devices[address] = (retrying_entry, None)
                        return self._async_abort_retrying_entry(address)

                    await self.async_set_unique_id(address)
                    self._abort_if_unique_id_configured()

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
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, "Adjustable Bed"),
                        data=entry_data,
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
                vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In([2, 3, 4]),
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
                ): vol.In(range(10, 301)),
            }
        )

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
            return self.async_create_entry(
                title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                data=self._manual_data,
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
            return self.async_create_entry(
                title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                data=self._manual_data,
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

    async def async_step_bluetooth_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth pairing for beds that require it."""
        assert self._manual_data is not None

        errors: dict[str, str] = {}
        description_placeholders = {
            "name": self._manual_data.get(CONF_NAME, "Unknown"),
            "pairing_instructions": await self._get_pairing_instructions(
                self._manual_data.get(CONF_BED_TYPE)
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
                # User wants to try without pairing (maybe already paired manually)
                return self.async_create_entry(
                    title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                    data=self._manual_data,
                )

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
                self._manual_data.get(CONF_BED_TYPE)
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
                # User wants to try without pairing (maybe already paired manually)
                return self.async_create_entry(
                    title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                    data=self._manual_data,
                )

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


class AdjustableBedOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle Adjustable Bed options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        # Get current values from config entry
        current_data = self.config_entry.data
        bed_type = current_data.get(CONF_BED_TYPE)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Get current adapter, falling back to auto if stored adapter no longer exists
        current_adapter = current_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
        if current_adapter not in adapters:
            current_adapter = ADAPTER_AUTO

        # Build schema
        schema_dict = {
            vol.Optional(
                CONF_MOTOR_COUNT,
                default=current_data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
            ): vol.In([2, 3, 4]),
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
            ): vol.In(range(10, 301)),
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
        }

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
            if bed_type == BED_TYPE_OCTO and CONF_OCTO_PIN in user_input:
                octo_pin = normalize_octo_pin(user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN))
                if not is_valid_octo_pin(octo_pin):
                    return self.async_show_form(
                        step_id="init",
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_OCTO_PIN: "invalid_pin"},
                    )
                user_input[CONF_OCTO_PIN] = octo_pin
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
            except (ValueError, TypeError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(schema_dict),
                    errors={"base": "invalid_number"},
                )
            # Convert angle limit values to floats with field-specific error handling
            if CONF_BACK_MAX_ANGLE in user_input:
                try:
                    value = float(user_input[CONF_BACK_MAX_ANGLE] or DEFAULT_BACK_MAX_ANGLE)
                    if value <= 0 or value > 180:
                        return self.async_show_form(
                            step_id="init",
                            data_schema=vol.Schema(schema_dict),
                            errors={CONF_BACK_MAX_ANGLE: "invalid_angle"},
                        )
                    user_input[CONF_BACK_MAX_ANGLE] = value
                except (ValueError, TypeError):
                    return self.async_show_form(
                        step_id="init",
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_BACK_MAX_ANGLE: "invalid_angle"},
                    )
            if CONF_LEGS_MAX_ANGLE in user_input:
                try:
                    value = float(user_input[CONF_LEGS_MAX_ANGLE] or DEFAULT_LEGS_MAX_ANGLE)
                    if value <= 0 or value > 180:
                        return self.async_show_form(
                            step_id="init",
                            data_schema=vol.Schema(schema_dict),
                            errors={CONF_LEGS_MAX_ANGLE: "invalid_angle"},
                        )
                    user_input[CONF_LEGS_MAX_ANGLE] = value
                except (ValueError, TypeError):
                    return self.async_show_form(
                        step_id="init",
                        data_schema=vol.Schema(schema_dict),
                        errors={CONF_LEGS_MAX_ANGLE: "invalid_angle"},
                    )
            # Update the config entry with new options
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
