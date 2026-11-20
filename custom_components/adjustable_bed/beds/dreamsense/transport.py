"""Dream Sense discovery preserves first endpoints and last recognized format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...errors import invalid

# This app's W1..W5 are not the classic app's transport order or RAW mapping.
ROUTES: Final = (
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", False),
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600", True),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622", True),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb", True),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb", True),
    ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "00000002-3c17-d293-8e48-14fe2e4da212", True),
)


@dataclass(frozen=True, slots=True)
class Session:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    single: bool
    generation: int
    product: str

    @property
    def response(self) -> bool:
        return "write-without-response" not in self.write.properties


def select(client: BleakClient, generation: int, product: str) -> Session:
    write = notify = None
    single = False
    for service in client.services:
        route = next((r for r in ROUTES if r[0] == service.uuid.lower()), None)
        if route is None:
            continue
        single = route[2]
        for char in service.characteristics:
            if write is None and char.uuid.lower() == route[1] and "write" in char.properties:
                write = char
            if notify is None and "notify" in char.properties:
                notify = char
    if write is None or notify is None:
        raise invalid("dreamsense_transport")
    return Session(client, write, notify, single, generation, product)
