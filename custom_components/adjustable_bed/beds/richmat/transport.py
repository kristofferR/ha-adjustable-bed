"""Property-selected GATT roles used by independently proven Richmat app profiles."""

from collections.abc import Iterable
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...codec.richmat import TRANSPORTS, TransportKey


@dataclass(frozen=True, slots=True)
class AppLink:
    client: BleakClient
    tx: BleakGATTCharacteristic
    rx: BleakGATTCharacteristic | None
    query_single: bool


def select_app_link(
    client: BleakClient, transports: Iterable[TransportKey], *, same_service: bool = False
) -> AppLink:
    """Select app-specific GATT roles from exact writable endpoints.

    By default the first writer, first notify and last matched query selector
    are independent. With same_service, the writer's service supplies all three.
    """
    routes = {TRANSPORTS[key].service_uuid.lower(): TRANSPORTS[key] for key in transports}
    tx = rx = None
    single = False
    for service in client.services:
        route = routes.get(service.uuid.lower())
        if route is None:
            continue
        single = route.single
        service_rx = None
        for characteristic in service.characteristics:
            if (
                tx is None
                and characteristic.uuid.lower() == route.write_uuid.lower()
                and "write" in characteristic.properties
            ):
                tx = characteristic
            if service_rx is None and "notify" in characteristic.properties:
                service_rx = characteristic
        if same_service and tx is not None:
            return AppLink(client, tx, service_rx, single)
        if rx is None:
            rx = service_rx
    if tx is None:
        raise ValueError("No supported writable app route")
    return AppLink(client, tx, rx, single)
