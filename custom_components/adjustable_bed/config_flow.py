"""Config flow for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
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
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .const import (
    ADAPTER_AUTO,
    ALL_PROTOCOL_VARIANTS,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_OCTO_PIN,
    CONF_POSITION_MODE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
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
    POSITION_MODE_ACCURACY,
    POSITION_MODE_SPEED,
    BEDS_WITH_ANGLE_SENSING,
    DOMAIN,
    KEESON_BASE_SERVICE_UUID,
    KEESON_VARIANTS,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_VARIANTS,
    LINAK_CONTROL_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OCTO_VARIANTS,
    OKIMAT_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_VARIANTS,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SOLACE_SERVICE_UUID,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

# Device name patterns that should NOT be detected as beds
# These use generic BUIDs that beds also use, but are clearly not beds
EXCLUDED_DEVICE_PATTERNS: tuple[str, ...] = (
    "scooter",
    "ninebot",
    "segway",
    "ebike",
    "e-bike",
    "escooter",
    "e-scooter",
    "skateboard",
    "hoverboard",
)


def is_valid_mac_address(address: str) -> bool:
    """Validate a MAC address format."""
    return bool(MAC_ADDRESS_PATTERN.match(address))


def get_variants_for_bed_type(bed_type: str) -> dict[str, str] | None:
    """Get available protocol variants for a bed type, or None if no variants."""
    if bed_type == BED_TYPE_KEESON:
        return KEESON_VARIANTS
    if bed_type == BED_TYPE_LEGGETT_PLATT:
        return LEGGETT_VARIANTS
    if bed_type == BED_TYPE_RICHMAT:
        return RICHMAT_VARIANTS
    if bed_type == BED_TYPE_OCTO:
        return OCTO_VARIANTS
    return None


def bed_type_has_variants(bed_type: str) -> bool:
    """Check if a bed type has multiple protocol variants."""
    return bed_type in (BED_TYPE_KEESON, BED_TYPE_LEGGETT_PLATT, BED_TYPE_OCTO, BED_TYPE_RICHMAT)


def get_available_adapters(hass) -> dict[str, str]:
    """Get available Bluetooth adapters/proxies."""
    adapters: dict[str, str] = {ADAPTER_AUTO: "Automatic (let Home Assistant choose)"}

    try:
        # Build a map of source -> friendly name from registered scanners
        scanner_names: dict[str, str] = {}

        # Use the official API to get all active scanners with their names
        try:
            from homeassistant.components.bluetooth import async_current_scanners
            for scanner in async_current_scanners(hass):
                source = getattr(scanner, 'source', None)
                name = getattr(scanner, 'name', None)
                if source and name:
                    scanner_names[source] = name
        except ImportError:
            _LOGGER.debug("async_current_scanners not available")
        except Exception as err:
            _LOGGER.debug("Could not get scanner names: %s", err)

        # Collect unique sources from all discovered devices
        seen_sources: set[str] = set()
        for service_info in async_discovered_service_info(hass, connectable=True):
            source = getattr(service_info, 'source', None)
            if source and source not in seen_sources:
                seen_sources.add(source)

                # Try to get a friendly name from the scanner
                friendly_name = scanner_names.get(source)

                if friendly_name and friendly_name != source:
                    # Use the scanner's friendly name with source in parentheses
                    adapters[source] = f"{friendly_name} ({source})"
                elif ':' in source:
                    # Looks like a MAC address - probably an ESPHome proxy without name
                    adapters[source] = f"Bluetooth Proxy ({source})"
                else:
                    # Might be a local adapter name like "hci0"
                    adapters[source] = f"Local Adapter ({source})"

    except Exception as err:
        _LOGGER.debug("Error getting Bluetooth adapters: %s", err)

    _LOGGER.debug("Available Bluetooth adapters: %s", adapters)
    return adapters


def detect_bed_type(service_info: BluetoothServiceInfoBleak) -> str | None:
    """Detect bed type from service info."""
    service_uuids = [str(uuid).lower() for uuid in service_info.service_uuids]
    device_name = (service_info.name or "").lower()

    _LOGGER.debug(
        "Detecting bed type for device %s (name: %s)",
        service_info.address,
        service_info.name,
    )
    _LOGGER.debug("  Service UUIDs: %s", service_uuids)
    _LOGGER.debug("  Manufacturer data: %s", service_info.manufacturer_data)

    # Exclude devices that are clearly not beds based on name
    # These often use the same generic BLE UUIDs as beds
    for pattern in EXCLUDED_DEVICE_PATTERNS:
        if pattern in device_name:
            _LOGGER.debug(
                "Device %s excluded: name '%s' matches excluded pattern '%s'",
                service_info.address,
                service_info.name,
                pattern,
            )
            return None

    # Check for Linak - most specific first
    if LINAK_CONTROL_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Linak bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_LINAK

    # Check for Leggett & Platt Gen2 (must check before generic UUIDs)
    if LEGGETT_GEN2_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Leggett & Platt Gen2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_LEGGETT_PLATT

    # Check for Reverie
    if REVERIE_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Reverie bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_REVERIE

    # Check for Okimat/Leggett Okin (same UUID, requires pairing)
    if OKIMAT_SERVICE_UUID.lower() in service_uuids:
        # Could be Okimat or Leggett Okin - default to Okimat
        _LOGGER.info(
            "Detected Okimat/Okin bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OKIMAT

    # Check for Richmat WiLinke variants
    for wilinke_uuid in RICHMAT_WILINKE_SERVICE_UUIDS:
        if wilinke_uuid.lower() in service_uuids:
            _LOGGER.info(
                "Detected Richmat WiLinke bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_RICHMAT

    # Check for MotoSleep - name-based detection (HHC prefix)
    if device_name.startswith("hhc"):
        _LOGGER.info(
            "Detected MotoSleep bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MOTOSLEEP

    # Check for Ergomotion - name-based detection (before Keeson since same UUID)
    if "ergomotion" in device_name or "ergo" in device_name:
        _LOGGER.info(
            "Detected Ergomotion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_ERGOMOTION

    # Check for Jiecang - name-based detection (Glide beds, Dream Motion app)
    if any(x in device_name for x in ["jiecang", "jc-", "dream motion", "glide"]):
        _LOGGER.info(
            "Detected Jiecang bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_JIECANG

    # Check for DewertOkin - name-based detection (A H Beard, HankookGallery)
    if any(x in device_name for x in ["dewertokin", "dewert", "a h beard", "hankook"]):
        _LOGGER.info(
            "Detected DewertOkin bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_DEWERTOKIN

    # Check for Serta Motion Perfect - name-based detection
    if any(x in device_name for x in ["serta", "motion perfect"]):
        _LOGGER.info(
            "Detected Serta bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_SERTA

    # Check for Octo Star2 variant - service UUID detection (before name-based Octo check)
    if OCTO_STAR2_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Octo Star2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OCTO

    # Check for Octo - name-based detection (before Solace since same UUID)
    if "octo" in device_name:
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OCTO

    # Check for Keeson BaseI4/I5 (must check before generic UUIDs)
    if KEESON_BASE_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Keeson Base bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_KEESON

    # Check for Solace/MotoSleep (same UUID, different protocols)
    # Solace uses 11-byte commands, MotoSleep uses 2-byte ASCII
    if SOLACE_SERVICE_UUID.lower() in service_uuids:
        # If name doesn't start with HHC, assume Solace
        _LOGGER.info(
            "Detected Solace bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_SOLACE

    # Check for Mattress Firm 900 (iFlex) - name-based detection
    # Must check before Richmat Nordic since they share the same UUID
    if "iflex" in device_name:
        _LOGGER.info(
            "Detected Mattress Firm 900 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MATTRESSFIRM

    # Check for Richmat Nordic / Keeson KSBT (same UUID)
    # These share the Nordic UART service UUID
    if RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids:
        # Default to Richmat, user can change in config
        _LOGGER.info(
            "Detected Richmat/Keeson bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_RICHMAT

    _LOGGER.debug("Device %s does not match any known bed types", service_info.address)
    return None


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
        self._manual_data: dict[str, Any] | None = None
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
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None

        bed_type = detect_bed_type(self._discovery_info)

        if user_input is not None:
            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
            protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)
            try:
                motor_pulse_count = int(user_input.get(CONF_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_COUNT))
                motor_pulse_delay_ms = int(user_input.get(CONF_MOTOR_PULSE_DELAY_MS, DEFAULT_MOTOR_PULSE_DELAY_MS))
            except ValueError:
                _LOGGER.warning("Invalid number input for motor pulse settings")
                motor_pulse_count = DEFAULT_MOTOR_PULSE_COUNT
                motor_pulse_delay_ms = DEFAULT_MOTOR_PULSE_DELAY_MS
            _LOGGER.info(
                "User confirmed bed setup: name=%s, type=%s, variant=%s, address=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s, pulse_count=%s, pulse_delay=%s",
                user_input.get(CONF_NAME, self._discovery_info.name or "Adjustable Bed"),
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
            entry_data = {
                CONF_ADDRESS: self._discovery_info.address.upper(),
                CONF_BED_TYPE: bed_type,
                CONF_PROTOCOL_VARIANT: protocol_variant,
                CONF_NAME: user_input.get(CONF_NAME, self._discovery_info.name),
                CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                CONF_DISABLE_ANGLE_SENSING: user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                CONF_PREFERRED_ADAPTER: preferred_adapter,
                CONF_MOTOR_PULSE_COUNT: motor_pulse_count,
                CONF_MOTOR_PULSE_DELAY_MS: motor_pulse_delay_ms,
                CONF_DISCONNECT_AFTER_COMMAND: user_input.get(CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND),
                CONF_IDLE_DISCONNECT_SECONDS: user_input.get(CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS),
            }
            # Add Octo PIN if configured
            if bed_type == BED_TYPE_OCTO:
                entry_data[CONF_OCTO_PIN] = user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, self._discovery_info.name or "Adjustable Bed"),
                data=entry_data,
            )

        _LOGGER.debug("Showing bluetooth confirmation form for %s", self._discovery_info.address)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        # Default angle sensing to enabled for beds that support it
        default_disable_angle = bed_type not in BEDS_WITH_ANGLE_SENSING

        # Build schema with optional variant selection
        schema_dict = {
            vol.Optional(
                CONF_NAME, default=self._discovery_info.name or "Adjustable Bed"
            ): str,
            vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In(
                [2, 3, 4]
            ),
            vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
            vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=default_disable_angle): bool,
            vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
            vol.Optional(CONF_MOTOR_PULSE_COUNT, default=str(DEFAULT_MOTOR_PULSE_COUNT)): TextSelector(
                TextSelectorConfig()
            ),
            vol.Optional(CONF_MOTOR_PULSE_DELAY_MS, default=str(DEFAULT_MOTOR_PULSE_DELAY_MS)): TextSelector(
                TextSelectorConfig()
            ),
            vol.Optional(CONF_DISCONNECT_AFTER_COMMAND, default=DEFAULT_DISCONNECT_AFTER_COMMAND): bool,
            vol.Optional(CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS): vol.All(
                vol.Coerce(int), vol.Range(min=10, max=300)
            ),
        }

        # Add variant selection if the bed type has variants
        variants = get_variants_for_bed_type(bed_type)
        if variants:
            schema_dict[vol.Optional(CONF_PROTOCOL_VARIANT, default=VARIANT_AUTO)] = vol.In(variants)

        # Add PIN field for Octo beds
        if bed_type == BED_TYPE_OCTO:
            schema_dict[vol.Optional(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN)] = vol.All(
                str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits")
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device or manual entry."""
        _LOGGER.debug("async_step_user called with input: %s", user_input)

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "manual":
                _LOGGER.debug("User selected manual entry")
                return await self.async_step_manual()

            _LOGGER.info("User selected device: %s", address)
            # Normalize address to uppercase to match Bluetooth discovery
            await self.async_set_unique_id(address.upper())
            self._abort_if_unique_id_configured()

            self._discovery_info = self._discovered_devices[address]
            return await self.async_step_bluetooth_confirm()

        # Discover devices
        _LOGGER.debug("Scanning for BLE devices...")
        
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
        
        current_addresses = self._async_current_ids()
        for discovery_info in all_discovered:
            if discovery_info.address in current_addresses:
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

        if not self._discovered_devices:
            _LOGGER.info("No beds discovered, showing manual entry form")
            return await self.async_step_manual()

        devices = {
            address: f"{info.name or 'Unknown'} ({address})"
            for address, info in self._discovered_devices.items()
        }
        devices["manual"] = "Enter address manually"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(devices)}
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().replace("-", ":")
            bed_type = user_input[CONF_BED_TYPE]

            # Validate MAC address format
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            elif not errors:
                preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                protocol_variant = user_input.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT)
                try:
                    motor_pulse_count = int(user_input.get(CONF_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_COUNT))
                    motor_pulse_delay_ms = int(user_input.get(CONF_MOTOR_PULSE_DELAY_MS, DEFAULT_MOTOR_PULSE_DELAY_MS))
                except ValueError:
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

                    await self.async_set_unique_id(address)
                    self._abort_if_unique_id_configured()

                    entry_data = {
                        CONF_ADDRESS: address,
                        CONF_BED_TYPE: bed_type,
                        CONF_PROTOCOL_VARIANT: protocol_variant,
                        CONF_NAME: user_input.get(CONF_NAME, "Adjustable Bed"),
                        CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                        CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                        CONF_DISABLE_ANGLE_SENSING: user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                        CONF_PREFERRED_ADAPTER: preferred_adapter,
                        CONF_MOTOR_PULSE_COUNT: motor_pulse_count,
                        CONF_MOTOR_PULSE_DELAY_MS: motor_pulse_delay_ms,
                        CONF_DISCONNECT_AFTER_COMMAND: user_input.get(CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND),
                        CONF_IDLE_DISCONNECT_SECONDS: user_input.get(CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS),
                    }
                    # For Octo beds, collect PIN in a separate step
                    if bed_type == BED_TYPE_OCTO:
                        self._manual_data = entry_data
                        return await self.async_step_manual_octo()
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME, "Adjustable Bed"),
                        data=entry_data,
                    )

        _LOGGER.debug("Showing manual entry form")

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_BED_TYPE): vol.In(SUPPORTED_BED_TYPES),
                    vol.Optional(CONF_PROTOCOL_VARIANT, default=VARIANT_AUTO): vol.In(
                        ALL_PROTOCOL_VARIANTS
                    ),
                    vol.Optional(CONF_NAME, default="Adjustable Bed"): str,
                    vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In(
                        [2, 3, 4]
                    ),
                    vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                    vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=DEFAULT_DISABLE_ANGLE_SENSING): bool,
                    vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
                    vol.Optional(CONF_MOTOR_PULSE_COUNT, default=str(DEFAULT_MOTOR_PULSE_COUNT)): TextSelector(
                        TextSelectorConfig()
                    ),
                    vol.Optional(CONF_MOTOR_PULSE_DELAY_MS, default=str(DEFAULT_MOTOR_PULSE_DELAY_MS)): TextSelector(
                        TextSelectorConfig()
                    ),
                    vol.Optional(CONF_DISCONNECT_AFTER_COMMAND, default=DEFAULT_DISCONNECT_AFTER_COMMAND): bool,
                    vol.Optional(CONF_IDLE_DISCONNECT_SECONDS, default=DEFAULT_IDLE_DISCONNECT_SECONDS): vol.In(
                        range(10, 301)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_manual_octo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Octo-specific configuration (PIN)."""
        assert self._manual_data is not None

        if user_input is not None:
            self._manual_data[CONF_OCTO_PIN] = user_input.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN)
            return self.async_create_entry(
                title=self._manual_data.get(CONF_NAME, "Adjustable Bed"),
                data=self._manual_data,
            )

        return self.async_show_form(
            step_id="manual_octo",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OCTO_PIN, default=DEFAULT_OCTO_PIN): vol.All(
                        str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits")
                    ),
                }
            ),
        )


class AdjustableBedOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle Adjustable Bed options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        # Get current values from config entry
        current_data = self.config_entry.data
        bed_type = current_data.get(CONF_BED_TYPE)

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

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
                default=current_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
            ): vol.In(adapters),
            vol.Optional(
                CONF_MOTOR_PULSE_COUNT,
                default=str(current_data.get(CONF_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_COUNT)),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_MOTOR_PULSE_DELAY_MS,
                default=str(current_data.get(CONF_MOTOR_PULSE_DELAY_MS, DEFAULT_MOTOR_PULSE_DELAY_MS)),
            ): TextSelector(TextSelectorConfig()),
            vol.Optional(
                CONF_DISCONNECT_AFTER_COMMAND,
                default=current_data.get(CONF_DISCONNECT_AFTER_COMMAND, DEFAULT_DISCONNECT_AFTER_COMMAND),
            ): bool,
            vol.Optional(
                CONF_IDLE_DISCONNECT_SECONDS,
                default=current_data.get(CONF_IDLE_DISCONNECT_SECONDS, DEFAULT_IDLE_DISCONNECT_SECONDS),
            ): vol.In(range(10, 301)),
            vol.Optional(
                CONF_DISABLE_ANGLE_SENSING,
                default=current_data.get(
                    CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
                ),
            ): bool,
            vol.Optional(
                CONF_POSITION_MODE,
                default=current_data.get(CONF_POSITION_MODE, DEFAULT_POSITION_MODE),
            ): vol.In({
                POSITION_MODE_SPEED: "Speed (recommended)",
                POSITION_MODE_ACCURACY: "Accuracy",
            }),
        }

        # Add variant selection if the bed type has variants
        variants = get_variants_for_bed_type(bed_type)
        if variants:
            schema_dict[vol.Optional(
                CONF_PROTOCOL_VARIANT,
                default=current_data.get(CONF_PROTOCOL_VARIANT, DEFAULT_PROTOCOL_VARIANT),
            )] = vol.In(variants)

        # Add PIN field for Octo beds
        if bed_type == BED_TYPE_OCTO:
            schema_dict[vol.Optional(
                CONF_OCTO_PIN,
                default=current_data.get(CONF_OCTO_PIN, DEFAULT_OCTO_PIN),
            )] = vol.All(str, vol.Match(r"^(\d{4})?$", msg="PIN must be exactly 4 digits"))

        if user_input is not None:
            # Convert text values to integers
            try:
                if CONF_MOTOR_PULSE_COUNT in user_input:
                    user_input[CONF_MOTOR_PULSE_COUNT] = int(user_input[CONF_MOTOR_PULSE_COUNT])
                if CONF_MOTOR_PULSE_DELAY_MS in user_input:
                    user_input[CONF_MOTOR_PULSE_DELAY_MS] = int(user_input[CONF_MOTOR_PULSE_DELAY_MS])
            except ValueError:
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
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )

