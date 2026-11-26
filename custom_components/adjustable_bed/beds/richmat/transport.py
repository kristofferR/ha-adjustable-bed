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
    client: BleakClient, transports: Iterable[TransportKey], *, unique_service: bool = False
) -> AppLink:
    """First writer, first notify, last matched query selector, all independent.

    Each caller supplies only routes its own literals and accepted source prove.
    A matching service without either role still updates the query selector.
    """
    routes = {TRANSPORTS[key].service_uuid.lower(): TRANSPORTS[key] for key in transports}
    tx = rx = None
    single = False
    matched = False
    for service in client.services:
        route = routes.get(service.uuid.lower())
        if route is None:
            continue
        if matched and unique_service:
            raise ValueError("More than one supported app service is present")
        matched = True
        single = route.single
        for characteristic in service.characteristics:
            if (
                tx is None
                and characteristic.uuid.lower() == route.write_uuid.lower()
                and "write" in characteristic.properties
            ):
                tx = characteristic
            if rx is None and "notify" in characteristic.properties:
                rx = characteristic
    if tx is None:
        raise ValueError("No supported writable app route")
    return AppLink(client, tx, rx, single)
