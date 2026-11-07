"""GM Control's distinct P1 and P2 GATT admission and selection rules."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTService
    from homeassistant.core import HomeAssistant

_WRITE_LOCK_KEY = "adjustable_bed_gmmotor_native_write_lock"


def native_write_lock(hass: HomeAssistant) -> asyncio.Lock:
    """Both app protocols share the SDK's global native-write mutex."""
    lock = hass.data.get(_WRITE_LOCK_KEY)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        hass.data[_WRITE_LOCK_KEY] = lock
    return lock


# Discovery iteration order matters; these are exact artifact-local constants.
P1_SERVICES = {
    "0000fee9-0000-1000-8000-00805f9b34fb": "d44bc439-abfd-45a2-b575-925416129600",
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "0000e0ff-3c17-d293-8e48-14fe2e4da212": "00000002-3c17-d293-8e48-14fe2e4da212",
    "0000fff0-0000-1000-8000-00805f9b34fb": "0000fff2-0000-1000-8000-00805f9b34fb",
    "0000ffe0-0000-1000-8000-00805f9b34fb": "0000ffe2-0000-1000-8000-00805f9b34fb",
    "0000fee9-0000-1000-8000-00805f9b34bb": "d44bc439-abfd-45a2-b575-925416129622",
}
NORDIC = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
SLEEP_SERVICE = "2320567c-05cf-6eb4-c341-772851827e1b"
E0FF = "0000e0ff-3c17-d293-8e48-14fe2e4da212"
SLEEP_WRITE = "00000002-3c17-d293-8e48-14fe2e4da212"
SLEEP_NOTIFY = "00000003-3c17-d293-8e48-14fe2e4da212"


@dataclass(frozen=True, slots=True)
class Transport:
    """Exact discovered characteristic objects preserve duplicate-UUID ordering."""

    write: BleakGATTCharacteristic
    notifications: tuple[BleakGATTCharacteristic, ...]
    response: bool
    single: bool = False


def select_p1(services: Iterable[BleakGATTService]) -> Transport:
    """Last accepted service mode, first exact WRITE and first global NOTIFY."""
    discovered = tuple(services)
    selected = next(
        (s.uuid.lower() for s in reversed(discovered) if s.uuid.lower() in P1_SERVICES), None
    )
    if selected is None:
        raise ValueError("GM Control has no accepted P1 service")
    characteristics = [c for s in discovered for c in s.characteristics]
    write = next(
        (
            c
            for c in characteristics
            if c.uuid.lower() == P1_SERVICES[selected] and "write" in c.properties
        ),
        None,
    )
    notify = next((c for c in characteristics if "notify" in c.properties), None)
    if write is None or notify is None:
        raise ValueError("GM Control lacks its selected WRITE or global NOTIFY role")
    return Transport(
        write, (notify,), "write-without-response" not in write.properties, selected == NORDIC
    )


def select_sleep(services: Iterable[BleakGATTService], *, sxb: bool) -> Transport:
    """P2 carries candidates across services, and WRITE wins dual-property chars."""
    write = None
    notify = None
    subscriptions: list[BleakGATTCharacteristic] = []
    for service in services:
        if service.uuid.lower() not in (SLEEP_SERVICE, E0FF):
            continue
        for characteristic in service.characteristics:
            props, uuid = characteristic.properties, characteristic.uuid.lower()
            if (sxb and uuid == SLEEP_WRITE and "write" in props) or (
                not sxb and "write-without-response" in props
            ):
                write = characteristic
            elif "notify" in props and (not sxb or uuid == SLEEP_NOTIFY):
                notify = characteristic
                subscriptions.append(characteristic)
        if write is not None and notify is not None:
            return Transport(write, tuple(subscriptions), sxb)
    raise ValueError("GM Control sleep module lacks its selected write/notify pair")
