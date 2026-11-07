"""Explicit cluster-018 service selection on the current physical session."""

from __future__ import annotations

from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...codec import richmat as codec
from ...profiles.richmat import CLASSIC_TRANSPORTS
from .protocol import Wire

# The five apps share one fixed service order: W1, W2, Nordic UART, then W4.
# Nordic UART takes the bare resource bytes (RAW); the others are framed.
ROUTES: tuple[tuple[str, str, str, Wire], ...] = tuple(
    (
        transport.service_uuid,
        transport.write_uuid,
        transport.notify_uuid,
        "RAW" if transport.single else "FRAMED",
    )
    for transport in (codec.TRANSPORTS[key] for key in CLASSIC_TRANSPORTS)
)


@dataclass(frozen=True, slots=True)
class Transport:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    wire: Wire

    @property
    def has_notifications(self) -> bool:
        return bool(set(self.notify.properties) & {"notify", "indicate"})

    @property
    def response(self) -> bool:
        # Bleak requires an explicit ATT choice. The app did not set writeType.
        return "write" in self.write.properties


def select(client: BleakClient, *, third_service: bool = False) -> Transport:
    for service_uuid, write_uuid, notify_uuid, wire in ROUTES:
        service = client.services.get_service(service_uuid)
        if service is None:
            continue
        write = service.get_characteristic(write_uuid)
        notify = service.get_characteristic(notify_uuid)
        if write is None or notify is None:
            raise ValueError("The first matching app service has incomplete characteristics")
        if not set(write.properties) & {"write", "write-without-response"}:
            raise ValueError("The app's command characteristic is not writable")
        return Transport(client, write, notify, wire)
    services = list(client.services)
    if third_service and len(services) > 2:
        writes = [c for c in services[2].characteristics if set(c.properties) & {"write", "write-without-response"}]
        reads = [c for c in services[2].characteristics if set(c.properties) & {"read", "notify", "indicate"}]
        if writes and reads:
            return Transport(client, writes[-1], reads[-1], "RAW")
    raise ValueError("No complete app transport; third-service fallback requires explicit selection")
