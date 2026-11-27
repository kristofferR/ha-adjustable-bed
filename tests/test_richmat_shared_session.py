"""The shared Richmat session preserves Comfort's profile and side encoder hooks."""

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat import atlas_lift, fixed
from custom_components.adjustable_bed.profiles.comfort_bed import PROFILE
from tests.hold_lease_wire import virtual_clock
from tests.test_atlas_lift import client_on, frames, session_for
from tests.test_comfort_bed import bed, literal, service


def controller_on(client):
    coordinator = MagicMock(
        client=client,
        cancel_command=asyncio.Event(),
        motor_count=2,
        motor_pulse_count=2,
        motor_pulse_delay_ms=100,
    )
    return coordinator, bed.ComfortBedController(coordinator)


@pytest.mark.parametrize("route", PROFILE.transports)
@pytest.mark.parametrize("side", (0, 1))
async def test_native_directions_and_release_use_comfort_encoder_on_every_route(route, side):
    assert atlas_lift._Link is fixed._Link
    client = client_on(service(route, "write"))
    _, controller = controller_on(client)
    with virtual_clock():
        await controller.async_on_connect(session_for(controller, client))
        assert controller.profile is PROFILE
        controller._select_side("right" if side else "left")
        for spec, actions in zip(
            controller.motor_control_specs,
            (
                ("Head up", "Head down"),
                ("Foot up", "Foot down"),
                ("Head and foot up", "Head and foot down"),
            ),
            strict=True,
        ):
            client.write_gatt_char.reset_mock()
            await spec.open_fn(controller)
            await spec.close_fn(controller)
            assert frames(client) == [
                literal(action, route == "n1", 0 if route == "n1" else side)
                for name in actions
                for action in (name, name, "Movement STOP")
            ]
    controller.on_disconnect()


@pytest.mark.parametrize("kind", ("atlas", "topcare"))
async def test_default_notification_hook_forwards_raw_and_rejects_retired_links(kind):
    from custom_components.adjustable_bed.beds.richmat.topcare import TopcareController

    old = client_on(service("w1", "write"))
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    cls = atlas_lift.AtlasLiftController if kind == "atlas" else TopcareController
    controller = cls(coordinator)
    raw = MagicMock()
    controller.set_raw_notify_callback(raw)
    with virtual_clock():
        await controller.async_on_connect(session_for(controller, old))
        assert type(controller._current_link()) is fixed._Link
        sender, receive = old.start_notify.await_args.args
        receive(sender, bytearray(b"opaque"))
        raw.assert_called_once_with(sender.uuid, b"opaque")
        coordinator.handle_controller_state_updates.assert_not_called()
        await controller.stop_notify()
        receive(sender, bytearray(b"after cleanup"))
        controller.on_disconnect()
        new = client_on(service("n1", "write"))
        coordinator.client = new
        await controller.async_on_connect(session_for(controller, new))
        receive(sender, bytearray(b"old session"))
        raw.assert_called_once()
    controller.on_disconnect()


@pytest.mark.parametrize("route", PROFILE.transports)
async def test_actual_inflight_cancel_releases_original_side_on_every_route(route):
    client = client_on(service(route, "write"))
    _, controller = controller_on(client)
    with virtual_clock():
        await controller.async_on_connect(session_for(controller, client))
        controller._select_side("right")
        client.write_gatt_char.reset_mock()
        began, finish = asyncio.Event(), asyncio.Event()
        motion = literal("Head up", route == "n1", 0 if route == "n1" else 1)
        stop = literal("Movement STOP", route == "n1", 0 if route == "n1" else 1)

        async def write(_char, frame, **kwargs):
            if frame == motion:
                began.set()
                await finish.wait()

        client.write_gatt_char.side_effect = write
        task = asyncio.create_task(controller.move_back_up())
        await began.wait()
        task.cancel()
        controller._select_side("left")
        await asyncio.sleep(0)
        assert not task.done() and frames(client) == [motion]
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert frames(client) == [motion, stop]
    controller.on_disconnect()


@pytest.mark.parametrize("route", PROFILE.transports)
async def test_queued_command_never_crosses_replacement_on_every_route(route):
    old = client_on(service(route, "write"))
    coordinator, controller = controller_on(old)
    with virtual_clock():
        await controller.async_on_connect(session_for(controller, old))
        old.write_gatt_char.reset_mock()
        async with controller.ble_lock:
            task = asyncio.create_task(controller.preset_tv())
            await asyncio.sleep(0.15)
            controller.on_disconnect()
            new = client_on(service("w1" if route == "n1" else "n1", "write"))
            coordinator.client = new
        with pytest.raises(ConnectionError):
            await task
        old.write_gatt_char.assert_not_awaited()
        new.write_gatt_char.assert_not_awaited()
        await controller.async_on_connect(session_for(controller, new))
        assert controller._current_link().client is new
    controller.on_disconnect()
