"""Per-address serialization of BLE connection attempts.

Several code paths in this integration can try to connect to the same bed at
once: the coordinator's retry loop, the config flow's capability probe and
pairing step, the pairing repair flow, and the support-bundle diagnostic. BlueZ
allows only one outstanding ``Device1.Connect()`` per device, so an overlapping
attempt fails immediately with ``org.bluez.Error.InProgress`` — and bleak's
cleanup for the loser then calls ``Disconnect()``, which can abort the
connection the winner was still establishing. Two retry loops racing this way
can keep a bed permanently unreachable.

Issue #385 caught exactly that in the field: two diagnostic attempts failed in
0.259s each with ``[org.bluez.Error.InProgress]`` while the coordinator had a
connect in flight.

Holding this lock across a whole connect attempt makes a competing caller wait
instead of poisoning the in-flight attempt. Waiting is always preferable: a
delayed connection still works, an aborted one does not.
"""

from __future__ import annotations

import asyncio
from typing import Final

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOCKS_KEY: Final = f"{DOMAIN}_connect_locks"


def async_get_connect_lock(hass: HomeAssistant, address: str) -> asyncio.Lock:
    """Return the shared connect lock for ``address``.

    Locks are stored on ``hass.data`` rather than at module scope so they do not
    leak between Home Assistant instances (or between tests).
    """
    locks: dict[str, asyncio.Lock] = hass.data.setdefault(_LOCKS_KEY, {})
    return locks.setdefault(address.upper(), asyncio.Lock())
