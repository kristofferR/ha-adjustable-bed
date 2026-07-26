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

The lock is **reentrant per asyncio task**, which a plain ``asyncio.Lock`` is
not. These paths legitimately nest: the support-bundle capture holds the
address for its whole capture and then asks the coordinator to reconnect a
dropped link (``async_ensure_connected`` → ``_async_connect_locked``), which
acquires the same address. With a plain lock that awaits itself and the capture
hangs forever. Reentrancy is the right semantic here because the nested call is
part of the same logical operation on the same device, in the same task, so
letting it through cannot interleave it with a competing caller.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Final

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOCKS_KEY: Final = f"{DOMAIN}_connect_locks"


class ReentrantAddressLock:
    """An asyncio lock that the owning task may re-acquire.

    Only the task that already holds the lock is let through; any other task
    waits as it would on a plain ``asyncio.Lock``.
    """

    def __init__(self) -> None:
        """Initialize an unowned lock."""
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task[object] | None = None
        self._depth = 0

    def locked(self) -> bool:
        """Return True while any task holds the lock."""
        return self._lock.locked()

    async def acquire(self) -> None:
        """Acquire the lock, or re-enter it when this task already owns it."""
        task = asyncio.current_task()
        if self._owner is not None and self._owner is task:
            self._depth += 1
            return
        await self._lock.acquire()
        self._owner = task
        self._depth = 1

    def release(self) -> None:
        """Release one level of ownership."""
        if self._depth == 0:
            raise RuntimeError("Lock is not acquired")
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()

    async def __aenter__(self) -> ReentrantAddressLock:
        """Acquire the lock for an ``async with`` block."""
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the lock at the end of an ``async with`` block."""
        self.release()


def async_get_connect_lock(hass: HomeAssistant, address: str) -> ReentrantAddressLock:
    """Return the shared connect lock for ``address``.

    Locks are stored on ``hass.data`` rather than at module scope so they do not
    leak between Home Assistant instances (or between tests).
    """
    locks: dict[str, ReentrantAddressLock] = hass.data.setdefault(_LOCKS_KEY, {})
    return locks.setdefault(address.upper(), ReentrantAddressLock())
