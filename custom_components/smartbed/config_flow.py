"""Config flow for Smart Bed integration."""

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

from .const import (
    ADAPTER_AUTO,
    BED_TYPE_LINAK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DEFAULT_DISABLE_ANGLE_SENSING,
    DEFAULT_HAS_MASSAGE,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    LINAK_CONTROL_SERVICE_UUID,
    SUPPORTED_BED_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def is_valid_mac_address(address: str) -> bool:
    """Validate a MAC address format."""
    return bool(MAC_ADDRESS_PATTERN.match(address))


def get_available_adapters(hass) -> dict[str, str]:
    """Get available Bluetooth adapters/proxies."""
    adapters: dict[str, str] = {ADAPTER_AUTO: "Automatic (let Home Assistant choose)"}
    
    try:
        # Build a map of source -> friendly name
        scanner_names: dict[str, str] = {}
        
        # Try to get scanner names from Bluetooth manager
        try:
            from homeassistant.components.bluetooth import async_scanner_by_source
            # We'll populate names as we find sources
        except ImportError:
            pass
        
        # Try accessing the manager directly for scanner names
        try:
            from homeassistant.components.bluetooth import DOMAIN as BLUETOOTH_DOMAIN
            manager = hass.data.get(BLUETOOTH_DOMAIN)
            if manager:
                # Try different attributes that might contain scanner info
                for attr in ('_connectable_scanners', '_scanners', 'scanners'):
                    scanners = getattr(manager, attr, None)
                    if scanners:
                        for scanner in scanners:
                            source = getattr(scanner, 'source', None)
                            name = getattr(scanner, 'name', None)
                            if source and name and source not in scanner_names:
                                scanner_names[source] = name
        except Exception as err:
            _LOGGER.debug("Could not get scanner names from manager: %s", err)
        
        # Collect unique sources from all discovered devices
        seen_sources: set[str] = set()
        for service_info in async_discovered_service_info(hass, connectable=True):
            source = getattr(service_info, 'source', None)
            if source and source not in seen_sources:
                seen_sources.add(source)
                
                # Try to get a friendly name
                friendly_name = scanner_names.get(source)
                
                if friendly_name:
                    # Use the scanner's friendly name
                    adapters[source] = f"{friendly_name} ({source})"
                elif ':' in source:
                    # Looks like a MAC address - probably an ESPHome proxy
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

    _LOGGER.debug(
        "Detecting bed type for device %s (name: %s)",
        service_info.address,
        service_info.name,
    )
    _LOGGER.debug("  Service UUIDs: %s", service_uuids)
    _LOGGER.debug("  Manufacturer data: %s", service_info.manufacturer_data)

    # Check for Linak
    if LINAK_CONTROL_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Linak bed at %s (name: %s) - found service UUID %s",
            service_info.address,
            service_info.name,
            LINAK_CONTROL_SERVICE_UUID,
        )
        return BED_TYPE_LINAK

    _LOGGER.debug("Device %s does not match any known bed types", service_info.address)
    return None


class SmartBedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Bed."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SmartBedOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        _LOGGER.debug("SmartBedConfigFlow initialized")

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

        await self.async_set_unique_id(discovery_info.address)
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

        if user_input is not None:
            bed_type = detect_bed_type(self._discovery_info)
            preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
            _LOGGER.info(
                "User confirmed bed setup: name=%s, type=%s, address=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s",
                user_input.get(CONF_NAME, self._discovery_info.name or "Smart Bed"),
                bed_type,
                self._discovery_info.address,
                user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                preferred_adapter,
            )
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, self._discovery_info.name or "Smart Bed"),
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_BED_TYPE: bed_type,
                    CONF_NAME: user_input.get(CONF_NAME, self._discovery_info.name),
                    CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    CONF_DISABLE_ANGLE_SENSING: user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                    CONF_PREFERRED_ADAPTER: preferred_adapter,
                },
            )

        _LOGGER.debug("Showing bluetooth confirmation form for %s", self._discovery_info.address)
        
        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)
        
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=self._discovery_info.name or "Smart Bed"
                    ): str,
                    vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In(
                        [2, 3, 4]
                    ),
                    vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                    vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=DEFAULT_DISABLE_ANGLE_SENSING): bool,
                    vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
                }
            ),
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
            await self.async_set_unique_id(address)
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

            # Validate MAC address format
            if not is_valid_mac_address(address):
                errors["base"] = "invalid_mac_address"
            else:
                preferred_adapter = user_input.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO)
                _LOGGER.info(
                    "Manual bed configuration: address=%s, type=%s, name=%s, motors=%s, massage=%s, disable_angle_sensing=%s, adapter=%s",
                    address,
                    user_input[CONF_BED_TYPE],
                    user_input.get(CONF_NAME, "Smart Bed"),
                    user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                    preferred_adapter,
                )

                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, "Smart Bed"),
                    data={
                        CONF_ADDRESS: address,
                        CONF_BED_TYPE: user_input[CONF_BED_TYPE],
                        CONF_NAME: user_input.get(CONF_NAME, "Smart Bed"),
                        CONF_MOTOR_COUNT: user_input.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                        CONF_HAS_MASSAGE: user_input.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                        CONF_DISABLE_ANGLE_SENSING: user_input.get(CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING),
                        CONF_PREFERRED_ADAPTER: preferred_adapter,
                    },
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
                    vol.Optional(CONF_NAME, default="Smart Bed"): str,
                    vol.Optional(CONF_MOTOR_COUNT, default=DEFAULT_MOTOR_COUNT): vol.In(
                        [2, 3, 4]
                    ),
                    vol.Optional(CONF_HAS_MASSAGE, default=DEFAULT_HAS_MASSAGE): bool,
                    vol.Optional(CONF_DISABLE_ANGLE_SENSING, default=DEFAULT_DISABLE_ANGLE_SENSING): bool,
                    vol.Optional(CONF_PREFERRED_ADAPTER, default=ADAPTER_AUTO): vol.In(adapters),
                }
            ),
            errors=errors,
        )


class SmartBedOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle Smart Bed options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update the config entry with new options
            new_data = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            return self.async_create_entry(title="", data={})

        # Get current values from config entry
        current_data = self.config_entry.data

        # Get available Bluetooth adapters
        adapters = get_available_adapters(self.hass)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MOTOR_COUNT,
                        default=current_data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT),
                    ): vol.In([2, 3, 4]),
                    vol.Optional(
                        CONF_HAS_MASSAGE,
                        default=current_data.get(CONF_HAS_MASSAGE, DEFAULT_HAS_MASSAGE),
                    ): bool,
                    vol.Optional(
                        CONF_DISABLE_ANGLE_SENSING,
                        default=current_data.get(
                            CONF_DISABLE_ANGLE_SENSING, DEFAULT_DISABLE_ANGLE_SENSING
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_PREFERRED_ADAPTER,
                        default=current_data.get(CONF_PREFERRED_ADAPTER, ADAPTER_AUTO),
                    ): vol.In(adapters),
                }
            ),
        )

