"""Validate the Fuzion Auth read before enabling encrypted notifications."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from .const import SLEEP_NUMBER_AUTH_CHAR_UUID

if TYPE_CHECKING:
    from bleak import BleakClient


class InvalidSleepNumberSession(BleakError):
    """Auth returned a missing, malformed or explicitly rejected session UUID."""


class SleepNumberConnectionLimitError(BleakError):
    """Auth refused another session without establishing a bond failure."""


def validate_sleep_number_session(value: bytes) -> bytes:
    """Reject malformed UUIDs and the two protocol failure sentinels."""
    if len(value) != 16:
        raise InvalidSleepNumberSession(
            f"Sleep Number Auth must contain a 16-byte session UUID (received {len(value)} bytes)"
        )
    identifier = int.from_bytes(value, "big")
    if identifier == 0:
        raise SleepNumberConnectionLimitError("Sleep Number connection limit reached (zero Auth UUID)")
    if identifier == 1:
        raise InvalidSleepNumberSession("Sleep Number authentication rejected (Auth UUID one)")
    return value


async def async_read_sleep_number_session(client: BleakClient) -> bytes:
    """Read a session UUID with the app's three attempts and 10-second timeout."""
    for attempt in range(3):
        try:
            async with asyncio.timeout(10):
                value = bytes(await client.read_gatt_char(SLEEP_NUMBER_AUTH_CHAR_UUID))
        except BleakError, TimeoutError:
            if attempt == 2:
                raise
            continue
        return validate_sleep_number_session(value)
    raise AssertionError("Unreachable authentication retry state")
