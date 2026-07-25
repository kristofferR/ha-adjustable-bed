"""The Adjustable Bed integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_KAIDI,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_VIBRADORM,
    BEDTECH_MANUFACTURER_ID,
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
    CONF_OCTO_PIN,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    OCTO_VARIANT_STAR2,
    VARIANT_AUTO,
    connection_gated_by_bond,
    requires_pairing,
)
from .coordinator import AdjustableBedCoordinator
from .kaidi_metadata import add_kaidi_entry_metadata, resolve_kaidi_advertisement
from .services import (
    ATTR_CAPTURE_DURATION,
    ATTR_DIRECTION,
    ATTR_DURATION_MS,
    ATTR_INCLUDE_LOGS,
    ATTR_MOTOR,
    ATTR_POSITION,
    ATTR_PRESET,
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
    SERVICE_STOP_ALL,
    SERVICE_TIMED_MOVE,
    TIMED_MOVE_MOTOR_OPTIONS,
    async_register_services,
)
from .unsupported import (
    async_clear_unsupported_device_issues,
    clear_octo_pin_required_issue,
    create_pairing_required_issue,
)

# Re-exported for backwards compatibility: these moved to .services, but are
# imported from the package root by tests and by downstream automations.
__all__ = [
    "ATTR_CAPTURE_DURATION",
    "ATTR_DIRECTION",
    "ATTR_DURATION_MS",
    "ATTR_INCLUDE_LOGS",
    "ATTR_MOTOR",
    "ATTR_POSITION",
    "ATTR_PRESET",
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Adjustable Bed integration domain."""
    hass.data.setdefault(DOMAIN, {})

    # Clear obsolete "unsupported BLE device" Repairs issues from older versions
    # that nagged about every discovered non-bed device (feature removed).
    async_clear_unsupported_device_issues(hass)

    from .download import SupportBundleDownloadView

    hass.http.register_view(SupportBundleDownloadView)

    from .frontend import async_register_frontend

    await async_register_frontend(hass)

    await async_register_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to newer schema versions."""
    _LOGGER.debug(
        "Migrating config entry %s for %s from version %s",
        entry.entry_id,
        entry.title,
        entry.version,
    )

    if entry.version > 3:
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Adjustable Bed from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await async_register_services(hass)

    await _async_maybe_reclassify_bedtech_qrrm_entry(hass, entry)
    _maybe_cache_kaidi_metadata(hass, entry)
    _async_clear_stale_octo_pin_issue(hass, entry)

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

    def _bond_gated_unbonded() -> bool:
        """Return whether this entry still needs the bond-gated repair path.

        Evaluate this after each connection attempt rather than caching it at
        setup start: the coordinator can establish and persist the bond before
        a later setup step fails for an unrelated reason.
        """
        return connection_gated_by_bond(
            entry.data.get(CONF_BED_TYPE, ""), entry.data.get(CONF_PROTOCOL_VARIANT)
        ) and not entry.data.get(CONF_BLE_BOND_ESTABLISHED)

    # Helper to create pairing issue — only when there's actual evidence of a pairing
    # problem. Generic connection failures (timeout, device not found) should NOT
    # trigger this, since the bed may just be temporarily unreachable after a restart.
    async def _maybe_create_pairing_issue() -> None:
        bed_type = entry.data.get(CONF_BED_TYPE)
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        if not (bed_type and requires_pairing(bed_type, protocol_variant)):
            return

        address = entry.data.get(CONF_ADDRESS, "")

        # Check if the device is already paired/bonded at the OS level (BlueZ).
        # If it is, the connection failure is transient — not a pairing problem.
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
                        "Bed %s is already paired/bonded at OS level — "
                        "connection failure is transient, skipping pairing repair",
                        address,
                    )
                    return

        # Adapter explicitly doesn't support pairing (e.g. old ESPHome proxy)
        if coordinator.pairing_supported is False:
            await create_pairing_required_issue(
                hass,
                address or "Unknown",
                entry.data.get("name", entry.title),
                entry.entry_id,
            )
            return

        # LP Comfort Connect / Leggett & Platt Gen2 shows a distinct unbonded
        # failure signature in issue #385: reconnects time out outside the
        # pairing window while advertisements continue. Guide the user through
        # the repair flow (power-cycle into pairing mode, then pair) instead of
        # leaving the entry on retries that cannot establish the required bond.
        if _bond_gated_unbonded():
            await create_pairing_required_issue(
                hass,
                address or "Unknown",
                entry.data.get("name", entry.title),
                entry.entry_id,
            )
            return

        # Connection failed before pairing was even attempted (device not found,
        # timeout, etc.). Don't create repair — HA will retry automatically and
        # pairing will be attempted on the next successful connection.
        _LOGGER.debug(
            "Bed %s requires pairing but connection failed before pairing could be "
            "attempted — not creating pairing repair (will retry automatically)",
            address,
        )

    def _connection_failure_hint() -> str:
        """Return pairing guidance only while the entry remains unbonded."""
        if _bond_gated_unbonded():
            return (
                " This bed requires a Bluetooth bond. Open Settings → Repairs and "
                "follow the pairing steps (power-cycle the bed to enter its ~2 minute "
                "pairing mode)."
            )
        return " The integration will retry automatically."

    # Connect to the bed with a timeout to avoid blocking startup forever
    _LOGGER.debug("Attempting initial connection to bed (timeout: %.0fs)...", SETUP_TIMEOUT)
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
        await _maybe_create_pairing_issue()
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason=f"initial connection timed out after {SETUP_TIMEOUT:.0f}s",
            )
        raise ConfigEntryNotReady(
            f"Connection to bed at {entry.data.get(CONF_ADDRESS)} timed out after "
            f"{SETUP_TIMEOUT:.0f}s.{_connection_failure_hint()}"
        ) from None

    if not connected:
        await _maybe_create_pairing_issue()
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_DIAGNOSTIC:
            return await _async_setup_offline_diagnostic_entry(
                hass,
                entry,
                coordinator,
                reason="device was not reachable during initial setup",
            )
        if _bond_gated_unbonded():
            raise ConfigEntryNotReady(
                f"Failed to connect to bed at {entry.data.get(CONF_ADDRESS)}."
                f"{_connection_failure_hint()}"
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


async def _async_maybe_reclassify_bedtech_qrrm_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Correct a persisted Richmat QRRM entry from advertisement evidence.

    QRRM is used by both BedTech white-light controllers and Richmat/Casper RGB
    controllers, and both use the shared FEE9 service. A present manufacturer
    ID 0x4C57 is positive BedTech evidence, but its absence is inconclusive:
    ESPHome proxy snapshots can omit manufacturer data for the same device.
    Connected Device Information provides a second, model-specific correction
    path in the coordinator (issue #410).
    """
    bed_type = entry.data.get(CONF_BED_TYPE)
    if bed_type != BED_TYPE_RICHMAT:
        return

    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return

    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        _LOGGER.debug(
            "Skipping BedTech/Richmat QRRM reclassification for %s (%s): no "
            "advertisement seen yet for %s",
            entry.title,
            entry.entry_id,
            address,
        )
        return

    service_uuids = {
        uuid.lower() for uuid in (getattr(service_info, "service_uuids", None) or [])
    }
    if BEDTECH_SERVICE_UUID.lower() not in service_uuids:
        return

    device_name = getattr(service_info, "name", None)
    manufacturer_data = getattr(service_info, "manufacturer_data", None) or {}
    has_bedtech_manufacturer = BEDTECH_MANUFACTURER_ID in manufacturer_data

    if not isinstance(device_name, str) or not device_name.lower().startswith("qrrm"):
        return
    if not has_bedtech_manufacturer:
        _LOGGER.info(
            "QRRM entry %s (%s) has no protocol-specific advertisement evidence: "
            "manufacturer ID 0x%04X is absent (manufacturer IDs seen: %s); "
            "connected Device Information will be checked",
            entry.title,
            entry.entry_id,
            BEDTECH_MANUFACTURER_ID,
            sorted(manufacturer_data) or "none",
        )
        return

    new_data = {
        **entry.data,
        CONF_BED_TYPE: BED_TYPE_BEDTECH,
        CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
    }
    new_data.pop(CONF_RICHMAT_REMOTE, None)

    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.warning(
        "Corrected config entry %s (%s) from Richmat to BedTech because BLE name %r "
        "uses the shared FEE9 service and advertises BedTech manufacturer ID 0x%04X",
        entry.title,
        entry.entry_id,
        device_name,
        BEDTECH_MANUFACTURER_ID,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Adjustable Bed integration for %s", entry.title)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: AdjustableBedCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Disconnecting from bed...")
        await coordinator.async_shutdown()
        _LOGGER.info("Successfully unloaded Adjustable Bed integration for %s", entry.title)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up Repairs issues that would otherwise outlive the entry."""
    address = entry.data.get(CONF_ADDRESS)
    if address:
        clear_octo_pin_required_issue(hass, address)


def _async_clear_stale_octo_pin_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the Octo PIN repair when the configuration already resolves it.

    Runs on every setup, so saving a PIN (which reloads the entry) clears the
    issue even when the bed is unreachable and the connect path never runs.
    """
    address = entry.data.get(CONF_ADDRESS)
    if not address:
        return
    # Star2 has no PIN mechanism at all, and OctoStar2Controller has no
    # pin_locked_without_pin, so the connect path could never clear a stale
    # issue left behind by a variant switch.
    is_standard_octo = entry.data.get(CONF_BED_TYPE) == BED_TYPE_OCTO and entry.data.get(
        CONF_PROTOCOL_VARIANT
    ) != OCTO_VARIANT_STAR2
    if not is_standard_octo or entry.data.get(CONF_OCTO_PIN):
        clear_octo_pin_required_issue(hass, address)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.consume_internal_entry_update(entry):
        # The coordinator recorded its own BLE bond marker. Reloading for that
        # would disconnect the bed, which is fatal for a bed that only grants
        # one connection per pairing window (issue #385).
        _LOGGER.debug(
            "Skipping reload for %s: internal bond-marker update", entry.entry_id
        )
        return
    await hass.config_entries.async_reload(entry.entry_id)
