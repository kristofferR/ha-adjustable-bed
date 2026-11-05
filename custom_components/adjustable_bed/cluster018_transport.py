"""Explicit cluster-018 service selection on the current physical session."""

from __future__ import annotations

from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from .cluster018_protocol import Wire

ROUTES = (
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600", "d44bc439-abfd-45a2-b575-925416129601", "FRAMED"),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622", "d44bc439-abfd-45a2-b575-925416129611", "FRAMED"),
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "6e400003-b5a3-f393-e0a9-e50e24dcca9e", "RAW"),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb", "0000fff1-0000-1000-8000-00805f9b34fb", "FRAMED"),
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
        return Transport(client, write, notify, "RAW" if wire == "RAW" else "FRAMED")
    services = list(client.services)
    if third_service and len(services) > 2:
        writes = [c for c in services[2].characteristics if set(c.properties) & {"write", "write-without-response"}]
        reads = [c for c in services[2].characteristics if set(c.properties) & {"read", "notify", "indicate"}]
        if writes and reads:
            return Transport(client, writes[-1], reads[-1], "RAW")
    raise ValueError("No complete app transport; third-service fallback requires explicit selection")
