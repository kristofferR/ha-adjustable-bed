"""Correct a stored Richmat QRRM entry that advertises BedTech evidence."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_RICHMAT,
    BEDTECH_MANUFACTURER_ID,
    BEDTECH_SERVICE_UUID,
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    VARIANT_AUTO,
)

_LOGGER = logging.getLogger(__name__)


async def async_reclassify_bedtech_qrrm_entry(
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

    service_uuids = {uuid.lower() for uuid in (getattr(service_info, "service_uuids", None) or [])}
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
