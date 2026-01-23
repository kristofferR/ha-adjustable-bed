"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
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

from .actuator_groups import (
    ACTUATOR_GROUPS,
    SINGLE_TYPE_GROUPS,
)
from .const import (
    ADAPTER_AUTO,
    ALL_PROTOCOL_VARIANTS,
    BED_MOTOR_PULSE_DEFAULTS,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_JENSEN,
    BED_TYPE_KEESON,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BEDS_WITH_POSITION_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_JENSEN_PIN,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_IDLE_DISCONNECT_SECONDS,
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


class AdjustableBedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adjustable Bed."""

    VERSION = 1

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
        _LOGGER.debug("AdjustableBedConfigFlow initialized")

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

        bed_type = detect_bed_type(discovery_info)
        if bed_type is None:
            # Capture device info for troubleshooting
            device_info = capture_device_info(discovery_info)
            reason = determine_unsupported_reason(discovery_info)

            # Log detailed info and create Repairs issue
            log_unsupported_device(device_info, reason)
            await create_unsupported_device_issue(self.hass, device_info, reason)

            _LOGGER.debug(
                "Device %s is not a supported bed type, aborting",
                discovery_info.address,
            )
            return self.async_abort(reason="not_supported")

        _LOGGER.info(
            "Detected supported bed: %s at %s (name: %s)",
            bed_type,
            discovery_info.address,
            discovery_info.name,
        )

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None

        # Use detailed detection to get confidence and ambiguity info
        detection_result = detect_bed_type_detailed(self._discovery_info)
        bed_type = detection_result.bed_type
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
            if selected_bed_type and not is_valid_variant_for_bed_type(selected_bed_type, protocol_variant):
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
                bed_type,
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
                if selected_bed_type == BED_TYPE_OCTO and bed_type != BED_TYPE_OCTO:
                    self._manual_data = entry_data
                    return await self.async_step_bluetooth_octo()
                # If user selected Richmat but detection wasn't Richmat, collect remote in follow-up step
                if selected_bed_type == BED_TYPE_RICHMAT and bed_type != BED_TYPE_RICHMAT:
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
        schema_dict = {
            vol.Optional(CONF_BED_TYPE, default=bed_type): vol.In(SUPPORTED_BED_TYPES),
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
                remotes_options[RICHMAT_REMOTE_AUTO] = (
                    f"Auto (detected: {detected_remote.upper()})"
                )
            schema_dict[vol.Optional(CONF_RICHMAT_REMOTE, default=default_remote)] = vol.In(
                remotes_options
            )

        # Build description placeholders with optional ambiguity warning
        description_placeholders = {
            "name": self._discovery_info.name or self._discovery_info.address,
        }

        # Add detection confidence info for ambiguous cases
        if detection_result.confidence < 0.7 and detection_result.ambiguous_types:
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

        # Get all discovered devices
        all_discovered = list(async_discovered_service_info(self.hass))
        _LOGGER.debug(
            "Total BLE devices visible: %d",
            len(all_discovered),
        )

        # Convert to upper-case for case-insensitive comparison
        # (configured IDs are upper-case, but discovered addresses may be lower-case)
        current_addresses = {addr.upper() for addr in self._async_current_ids() if addr is not None}
        for discovery_info in all_discovered:
            if discovery_info.address.upper() in current_addresses:
                _LOGGER.debug(
                    "Skipping already configured device: %s",
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

        # Build device list - manual options first, then discovered beds, then diagnostic
        devices: dict[str, str] = {
            "select_by_brand": "Select by actuator brand (recommended)",
            "manual": "Show all BLE devices",
        }

        # Sort discovered beds: named devices first (alphabetically), then MAC-only/unnamed
        sorted_beds = sorted(
            self._discovered_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        devices.update(
            {address: f"{info.name or 'Unknown'} ({address})" for address, info in sorted_beds}
        )
        devices["diagnostic"] = "Diagnostic mode (unsupported device)"

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

        all_discovered = list(async_discovered_service_info(self.hass, connectable=True))
        _LOGGER.debug(
            "Total connectable BLE devices visible: %d",
            len(all_discovered),
        )

        # Filter out already configured devices
        current_addresses = {addr.upper() for addr in self._async_current_ids() if addr is not None}

        self._all_ble_devices = {}
        for discovery_info in all_discovered:
            if discovery_info.address.upper() not in current_addresses:
                self._all_ble_devices[discovery_info.address] = discovery_info

        _LOGGER.info(
            "Manual selection: found %d unconfigured BLE devices",
            len(self._all_ble_devices),
        )

        if not self._all_ble_devices:
            _LOGGER.info("No BLE devices found, showing manual entry form")
            return await self.async_step_manual_entry()

        # Sort devices: named devices first (alphabetically), then MAC-only/unnamed
        sorted_devices = sorted(
            self._all_ble_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        devices = {
            address: f"{info.name or 'Unknown'} ({address})" for address, info in sorted_devices
        }
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

        # Add remaining fields
        schema_dict.update(
            {
                vol.Optional(
                    CONF_NAME, default=device_name if device_name != "Unknown" else "Adjustable Bed"
                ): str,
                vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In([2, 3, 4]),
                vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                vol.Optional(
                    CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle
                ): bool,
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
                vol.Optional(
                    CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle
                ): bool,
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
                            data=self._manual_data,
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
                                SelectOptionDict(value="skip_pairing", label="Skip (already paired)"),
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
                            data=self._manual_data,
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
                                SelectOptionDict(value="skip_pairing", label="Skip (already paired)"),
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

        for service_info in async_discovered_service_info(self.hass, connectable=True):
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
            "Found device %s via adapter %s",
            address,
            getattr(matching_service_info, "source", "unknown"),
        )

        # Connect with pairing enabled - this handles both built-in HA Bluetooth
        # (pairing during connection) and ESPHome proxy (pairing after connection)
        client = await establish_connection(
            BleakClient,
            device,
            address,
            max_attempts=1,
            timeout=30.0,  # Match coordinator's CONNECTION_TIMEOUT
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
        """Handle diagnostic mode device selection.

        Lists ALL visible BLE devices (not just recognized beds) so users can
        add unsupported devices for diagnostic capture.
        """
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "manual":
                _LOGGER.debug("User selected manual entry for diagnostic mode")
                return await self.async_step_diagnostic_manual()

            _LOGGER.info("User selected device for diagnostic mode: %s", address)
            # Normalize address to uppercase to match Bluetooth discovery
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()

            self._discovery_info = self._all_ble_devices[address]
            return await self.async_step_diagnostic_confirm()

        # Get ALL BLE devices (not just beds)
        _LOGGER.debug("Scanning for ALL BLE devices for diagnostic mode...")

        all_discovered = list(async_discovered_service_info(self.hass, connectable=True))
        _LOGGER.debug(
            "Total connectable BLE devices visible: %d",
            len(all_discovered),
        )

        # Filter out already configured devices
        current_addresses = {addr.upper() for addr in self._async_current_ids() if addr is not None}

        self._all_ble_devices = {}
        for discovery_info in all_discovered:
            if discovery_info.address.upper() not in current_addresses:
                self._all_ble_devices[discovery_info.address] = discovery_info

        _LOGGER.info(
            "Diagnostic mode: found %d unconfigured BLE devices",
            len(self._all_ble_devices),
        )

        if not self._all_ble_devices:
            _LOGGER.info("No BLE devices found, showing manual entry form")
            return await self.async_step_diagnostic_manual()

        # Sort devices: named devices first (alphabetically), then MAC-only/unnamed
        sorted_devices = sorted(
            self._all_ble_devices.items(),
            key=lambda x: (is_mac_like_name(x[1].name), (x[1].name or "").lower()),
        )
        devices = {
            address: f"{info.name or 'Unknown'} ({address})" for address, info in sorted_devices
        }
        devices["manual"] = "Enter address manually"

        return self.async_show_form(
            step_id="diagnostic",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )

    async def async_step_diagnostic_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm diagnostic device setup."""
        assert self._discovery_info is not None

        # Get discovery source for default adapter selection
        discovery_source = getattr(self._discovery_info, "source", None) or ADAPTER_AUTO

        if user_input is not None:
            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, discovery_source)
            device_name = user_input.get(
                CONF_NAME, self._discovery_info.name or "Diagnostic Device"
            )
            _LOGGER.info(
                "Creating diagnostic device entry: name=%s, address=%s, adapter=%s",
                device_name,
                self._discovery_info.address,
                preferred_adapter,
            )

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_ADDRESS: self._discovery_info.address.upper(),
                    CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
                    CONF_NAME: device_name,
                    CONF_MOTOR_COUNT: 0,  # No motors for diagnostic
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                    CONF_PREFERRED_ADAPTER: preferred_adapter,
                },
            )

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        return self.async_show_form(
            step_id="diagnostic_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=self._discovery_info.name or "Diagnostic Device"
                    ): str,
                    vol.Optional(CONF_PREFERRED_ADAPTER, default=discovery_source): vol.In(
                        adapters
                    ),
                }
            ),
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address,
                "address": self._discovery_info.address,
            },
        )

    async def async_step_diagnostic_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual MAC address entry for diagnostic mode."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().replace("-", ":")

            # Validate MAC address format
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                device_name = user_input.get(CONF_NAME, "Diagnostic Device")
                _LOGGER.info(
                    "Creating diagnostic device entry (manual): name=%s, address=%s, adapter=%s",
                    device_name,
                    address,
                    preferred_adapter,
                )

                return self.async_create_entry(
                    title=device_name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_BED_TYPE: BED_TYPE_DIAGNOSTIC,
                        CONF_NAME: device_name,
                        CONF_MOTOR_COUNT: 0,  # No motors for diagnostic
                        CONF_HAS_MASSAGE: False,
                        CONF_DISABLE_ANGLE_SENSING: True,
                        CONF_PREFERRED_ADAPTER: preferred_adapter,
                    },
                )

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        return self.async_show_form(
            step_id="diagnostic_manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Diagnostic Device"): str,
                    vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
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
            # Update the config entry with new options
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            # Reload integration to apply changes immediately
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
