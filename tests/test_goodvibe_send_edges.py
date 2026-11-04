"""Public Good Vibe send-boundary regressions from final independent review."""

import asyncio
import faulthandler
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import DOMAIN
from tests.test_goodvibe_ha import runtime


async def start_hold(hass, c):
    return asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": ["bed"],
                "control": "goodvibe_38910fea480caabe",
                "duration": 60,
            },
            blocking=True,
        )
    )


async def test_release_during_ordinary_short_wire_wait(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    wire = asyncio.Event()
    original_send = obj._send

    async def send(data, **kwargs):
        if data.hex() == "6e010046b5":
            wire.set()
        return await original_send(data, **kwargs)

    obj._send = send
    # Finish the ordinary one-second public button's timer immediately.
    # Keep actual admission, BLE lock, pointer release and cancellation logic.
    obj._delay = AsyncMock(return_value=True)
    c._client.write_gatt_char = AsyncMock()
    action = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.key == "goodvibe_38910fea480caabe")
    )
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await obj._ble_lock.acquire()
        task = asyncio.create_task(action.async_press())
        await asyncio.wait_for(wire.wait(), 1)
        gesture = obj._gesture
        released = asyncio.create_task(release.async_press())
        await asyncio.sleep(0)
        assert gesture.release_is_current
        obj._ble_lock.release()
        await asyncio.wait_for(asyncio.gather(task, released), 1)
    frames = [x.args[1].hex() for x in c._client.write_gatt_char.await_args_list]
    c._client.is_connected = False
    await c.async_shutdown()
    assert frames == ["6e010046b5"], frames


@pytest.mark.parametrize("mode", ["success", "connection_error", "dispose"])
async def test_early_release_pending_short_send_settles(hass, mode):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    delay_entered, wire_entered, allow_wire = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delay(_ms):
        delay_entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay

    async def write(*args, **kwargs):
        wire_entered.set()
        await allow_wire.wait()
        if mode == "connection_error":
            raise ConnectionError("backend write failed")

    c._client.write_gatt_char = AsyncMock(side_effect=write)
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = await start_hold(hass, c)
        await asyncio.wait_for(delay_entered.wait(), 1)
        released = asyncio.create_task(release.async_press())
        await asyncio.wait_for(wire_entered.wait(), 1)
        if mode == "dispose":
            obj.on_disconnect()
        allow_wire.set()
        results = await asyncio.wait_for(asyncio.gather(task, released, return_exceptions=True), 1)
    assert c._client.write_gatt_char.await_count == 1
    assert obj._gesture is None
    assert not any(
        t.get_coro().__qualname__.endswith("press.<locals>.send")
        for t in asyncio.all_tasks()
        if not t.done()
    )
    if mode == "connection_error":
        assert isinstance(results[0], Exception), results
    else:
        assert results == [None, None], results
    c._client.is_connected = False
    await c.async_shutdown()


async def test_backend_cancelled_short_send_must_not_spin(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered = asyncio.Event()

    async def delay(_ms):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay

    async def write(*_args, **_kwargs):
        # A cancelled child must be terminal. The watchdog only bounds the
        # reproducer, and does not participate in controller/scheduler logic.
        print("BACKEND_CANCELLED_ONE_SHORT_SEND", flush=True)
        faulthandler.dump_traceback_later(0.5, exit=True)
        raise asyncio.CancelledError

    c._client.write_gatt_char = AsyncMock(side_effect=write)
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = await start_hold(hass, c)
        await asyncio.wait_for(entered.wait(), 1)
        released = asyncio.create_task(release.async_press())
        try:
            await asyncio.wait_for(asyncio.gather(task, released, return_exceptions=True), 0.2)
        finally:
            faulthandler.cancel_dump_traceback_later()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_finite_public_hold_release_during_ordinary_short_wire_wait(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    wire = asyncio.Event()
    send = obj._send

    async def sending(data, **kwargs):
        if data.hex() == "6e010046b5":
            wire.set()
        return await send(data, **kwargs)

    obj._send = sending
    obj._delay = AsyncMock(return_value=True)
    c._client.write_gatt_char = AsyncMock()
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await obj._ble_lock.acquire()
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": ["bed"],
                    "control": "goodvibe_38910fea480caabe",
                    "duration": 1,
                },
                blocking=True,
            )
        )
        await asyncio.wait_for(wire.wait(), 1)
        released = asyncio.create_task(release.async_press())
        await asyncio.sleep(0)
        assert obj._gesture.release_is_current
        obj._ble_lock.release()
        await asyncio.wait_for(asyncio.gather(task, released), 1)
    frames = [x.args[1].hex() for x in c._client.write_gatt_char.await_args_list]
    c._client.is_connected = False
    await c.async_shutdown()
    assert frames == ["6e010046b5"], frames


async def test_shutdown_pending_short_send_cancels_and_drains_once(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered, wire_entered = asyncio.Event(), asyncio.Event()

    async def delay(_ms):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay

    async def write(*_args, **_kwargs):
        wire_entered.set()
        await asyncio.Event().wait()

    c._client.write_gatt_char = AsyncMock(side_effect=write)
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = await start_hold(hass, c)
        await asyncio.wait_for(entered.wait(), 1)
        released = asyncio.create_task(release.async_press())
        await asyncio.wait_for(wire_entered.wait(), 1)
        await asyncio.wait_for(c._command_scheduler.async_shutdown(), 1)
        await asyncio.wait_for(asyncio.gather(task, released, return_exceptions=True), 1)
    assert c._client.write_gatt_char.await_count == 1
    assert obj._gesture is None
    assert not any(
        t.get_coro().__qualname__.endswith("press.<locals>.send")
        for t in asyncio.all_tasks()
        if not t.done()
    )
    c._client.is_connected = False
    await c.async_shutdown()


async def test_ordinary_short_already_submitted_to_ble_is_not_resent_on_release(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered = asyncio.Event()

    async def write(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    obj._delay = AsyncMock(return_value=True)
    c._client.write_gatt_char = AsyncMock(side_effect=write)
    action = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.key == "goodvibe_38910fea480caabe")
    )
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(action.async_press())
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(release.async_press(), 1)
        await asyncio.wait_for(task, 1)
    assert [call.args[1] for call in c._client.write_gatt_char.await_args_list] == [
        bytes.fromhex("6e010046b5")
    ]
    assert obj._gesture is None
    c._client.is_connected = False
    await c.async_shutdown()
