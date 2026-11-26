"""Sleeptime's read-only selection of the Nordic UART characteristic roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTServiceCollection


def gatt_roles(
    services: BleakGATTServiceCollection,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic] | None:
    """Resolve the exact write-without-response and notify or indicate pair."""
    service = services.get_service(NORDIC_UART_SERVICE_UUID)
    if service is None:
        return None
    write = service.get_characteristic(NORDIC_UART_WRITE_CHAR_UUID)
    notify = service.get_characteristic(NORDIC_UART_READ_CHAR_UUID)
    if (
        write is None
        or "write-without-response" not in write.properties
        or notify is None
        or not {"notify", "indicate"}.intersection(notify.properties)
    ):
        return None
    return write, notify
