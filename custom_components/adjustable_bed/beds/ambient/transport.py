"""Resolve the Ambient receiver's write and notification roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ...profiles import ambient as app

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTServiceCollection


def resolve_gatt(
    services: BleakGATTServiceCollection,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
    """Match the app's UUID selectors and require unambiguous actual roles."""
    matches = [service for service in services if app.SERVICE[:8] in service.uuid.lower()]
    if len(matches) != 1:
        raise BleakError("M3 Ambient requires one 6e40fffe service")
    chars = matches[0].characteristics
    writes = [char for char in chars if app.WRITE[:8] in char.uuid.lower()]
    notifies = [char for char in chars if app.NOTIFY[:8] in char.uuid.lower()]
    if len(writes) != 1 or "write" not in writes[0].properties:
        raise BleakError("M3 Ambient requires a 6e40aa02 write-with-response role")
    if len(notifies) != 1 or "notify" not in notifies[0].properties:
        raise BleakError("M3 Ambient requires a 6e40aa03 notification role")
    return writes[0], notifies[0]
