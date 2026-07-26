"""Tests for per-address BLE connect serialization (issue #385)."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.address_lock import async_get_connect_lock

from .conftest import TEST_ADDRESS


async def test_same_address_shares_one_lock(hass: HomeAssistant) -> None:
    """Every caller for an address must contend for the same lock."""
    assert async_get_connect_lock(hass, TEST_ADDRESS) is async_get_connect_lock(
        hass, TEST_ADDRESS
    )
    # BlueZ addresses reach us in mixed case from different code paths.
    assert async_get_connect_lock(hass, TEST_ADDRESS.lower()) is async_get_connect_lock(
        hass, TEST_ADDRESS.upper()
    )


async def test_different_addresses_do_not_block_each_other(
    hass: HomeAssistant,
) -> None:
    """Two beds must still be able to connect concurrently."""
    other = "11:22:33:44:55:66"
    async with async_get_connect_lock(hass, TEST_ADDRESS):
        assert not async_get_connect_lock(hass, other).locked()


async def test_second_attempt_waits_instead_of_racing(hass: HomeAssistant) -> None:
    """A competing attempt waits rather than poisoning the in-flight one.

    Overlapping BlueZ connects fail instantly with org.bluez.Error.InProgress,
    and the loser's cleanup can abort the winner's connection.
    """
    order: list[str] = []
    lock = async_get_connect_lock(hass, TEST_ADDRESS)

    async def attempt(name: str, hold: float) -> None:
        async with async_get_connect_lock(hass, TEST_ADDRESS):
            order.append(f"{name}:start")
            await asyncio.sleep(hold)
            order.append(f"{name}:done")

    first = asyncio.create_task(attempt("first", 0.05))
    await asyncio.sleep(0)  # let the first task take the lock
    assert lock.locked()
    second = asyncio.create_task(attempt("second", 0))
    await asyncio.gather(first, second)

    assert order == ["first:start", "first:done", "second:start", "second:done"]


async def test_lock_is_reentrant_for_the_owning_task(hass: HomeAssistant) -> None:
    """Nested acquisition by the same task must not deadlock.

    The support-bundle capture holds the address for its whole capture and then
    asks the coordinator to reconnect a dropped link, which acquires the same
    address. A plain asyncio.Lock would await itself forever (issue #385).
    """
    lock = async_get_connect_lock(hass, TEST_ADDRESS)

    async with lock:
        async with lock:
            assert lock.locked()
        # Still held by the outer acquisition.
        assert lock.locked()
    assert not lock.locked()


async def test_reentrancy_does_not_let_another_task_in(hass: HomeAssistant) -> None:
    """Only the owning task may re-enter; others still queue behind it."""
    order: list[str] = []

    async def other() -> None:
        async with async_get_connect_lock(hass, TEST_ADDRESS):
            order.append("other")

    async with async_get_connect_lock(hass, TEST_ADDRESS) as lock:
        task = asyncio.create_task(other())
        await asyncio.sleep(0)
        async with lock:  # re-entry by the owner succeeds immediately
            order.append("owner-nested")
        assert order == ["owner-nested"]  # the other task is still blocked
    await task
    assert order == ["owner-nested", "other"]


async def test_release_without_acquire_is_an_error(hass: HomeAssistant) -> None:
    """A stray release must not silently corrupt ownership tracking."""
    lock = async_get_connect_lock(hass, TEST_ADDRESS)
    with pytest.raises(RuntimeError):
        lock.release()
