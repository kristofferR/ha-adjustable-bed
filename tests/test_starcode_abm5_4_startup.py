"""Required native startup is awaited, retryable and original-session owned."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_starcode_abm5_4 import make_controller

MODULE = "custom_components.adjustable_bed.beds.starcode_abm5_4"


@pytest.mark.parametrize("transport", ["BOX1220", "BOX25", "BOX25_STAR"])
async def test_terminal_subscription_failure_clears_startup_and_next_call_retries(transport):
    controller = make_controller(device=transport)
    client = controller.client
    client.start_notify.side_effect = [OSError("first"), OSError("terminal"), None]
    with patch(MODULE + ".asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(OSError, match="terminal"):
            await controller.start_notify()
        assert not controller._ready and controller._notify_client is None
        assert controller._notify_characteristic is None and not controller._tasks
        assert sum(call.args == (2,) for call in sleep.await_args_list) == 1
        client.stop_notify.assert_awaited_once()
        await controller.start_notify()
        assert controller._ready and client.start_notify.await_count == 3
        await controller.stop_notify()
    assert not controller._tasks


async def test_partial_backend_subscription_is_removed_after_terminal_failure():
    controller = make_controller(device="BOX1220")
    subscribed = False

    async def subscribe(_role, _callback):
        nonlocal subscribed
        subscribed = True
        raise OSError("partial subscription")

    async def unsubscribe(_role):
        nonlocal subscribed
        subscribed = False

    controller.client.start_notify.side_effect = subscribe
    controller.client.stop_notify.side_effect = unsubscribe
    with (
        patch(MODULE + ".asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(OSError, match="partial subscription"),
    ):
        await controller.start_notify()
    assert not subscribed and not controller._ready and not controller._tasks
    controller.client.stop_notify.assert_awaited_once()


async def test_repeated_cancelled_startup_is_retryable_without_delayed_task_leaks():
    controller = make_controller(device="BOX1220")
    entered = asyncio.Event()

    async def subscribe(_role, _callback):
        entered.set()
        await asyncio.Event().wait()

    controller.client.start_notify.side_effect = subscribe
    for _attempt in range(2):
        entered.clear()
        task = asyncio.create_task(controller.start_notify())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not controller._tasks and not controller._ready
        assert controller._notify_client is None
    controller.client.start_notify.side_effect = None
    await controller.start_notify()
    assert controller._ready
    await controller.stop_notify()


async def test_terminal_wake_failure_propagates_without_a_subscription_and_retries():
    controller = make_controller(device="BOX25")
    client = controller.client
    client.write_gatt_char.side_effect = [OSError("first"), OSError("terminal"), None]
    with pytest.raises(OSError, match="terminal"):
        await controller.start_notify()
    assert not controller._ready and not controller._tasks
    client.start_notify.assert_not_awaited()
    assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
        "5a0b00a5",
        "5a0b00a5",
    ]
    await controller.start_notify()
    assert controller._ready
    await controller.stop_notify()


@pytest.mark.parametrize("transition", ["cancel", "stop", "address", "client"])
async def test_pending_startup_never_publishes_readiness_after_cancel_or_owner_change(transition):
    controller = make_controller(device="BOX1220")
    client = controller.client
    entered = asyncio.Event()
    complete = asyncio.Event()

    async def subscribe(_role, _callback):
        entered.set()
        await complete.wait()

    client.start_notify.side_effect = subscribe
    task = asyncio.create_task(controller.start_notify())
    await entered.wait()
    assert not task.done() and not controller._ready
    if transition == "cancel":
        task.cancel()
    elif transition == "stop":
        await controller.stop_notify()
    elif transition == "address":
        controller._coordinator.address = "AA:BB:CC:DD:EE:00"
    else:
        controller._coordinator.client = make_controller(device="BOX1220").client
    complete.set()
    expected = asyncio.CancelledError if transition in ("cancel", "stop") else ConnectionError
    with pytest.raises(expected):
        await task
    assert not controller._ready and controller._notify_client is None
    assert controller._notify_characteristic is None and not controller._tasks
    client.stop_notify.assert_awaited_once()


async def test_concurrent_startups_share_only_the_successful_required_subscription():
    controller = make_controller(device="BOX1220")
    client = controller.client
    entered = asyncio.Event()
    complete = asyncio.Event()

    async def subscribe(_role, _callback):
        entered.set()
        await complete.wait()

    client.start_notify.side_effect = subscribe
    first = asyncio.create_task(controller.start_notify())
    await entered.wait()
    second = asyncio.create_task(controller.start_notify())
    assert not controller._ready
    complete.set()
    await asyncio.gather(first, second)
    assert controller._ready
    client.start_notify.assert_awaited_once()
    await controller.stop_notify()
    assert not controller._tasks
