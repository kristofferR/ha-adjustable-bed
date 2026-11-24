"""Validate the same Dorsal receiver in setup and on the command link."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components import bluetooth

from ...discovery_hints.dorsal import DORSAL_TRANSPORTS, ROOMI_SCAN
from ...errors import failed, invalid
from ..richmat.transport import AppLink, select_app_link

if TYPE_CHECKING:
    from bleak import BleakClient
    from homeassistant.core import HomeAssistant


def validate_name(
    hass: HomeAssistant, address: str, route: str | None, device_name: str | None
) -> None:
    """Corroborate Roomi using either advertisement history for this address."""
    if route != "roomi" or device_name and ROOMI_SCAN in device_name:
        return
    for connectable in (True, False):
        advert = bluetooth.async_last_service_info(hass, address, connectable=connectable)
        if advert is not None and advert.name and ROOMI_SCAN in advert.name:
            return
    raise invalid("dorsal_roomi_receiver")


def select_link(client: BleakClient) -> AppLink:
    try:
        return select_app_link(client, DORSAL_TRANSPORTS)
    except ValueError as error:
        raise failed("dorsal_receiver_unavailable") from error
