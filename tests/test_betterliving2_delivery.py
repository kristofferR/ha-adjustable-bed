"""Own command delivery excludes startup and fresh-event release frames."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
)
from custom_components.adjustable_bed.light import AdjustableBedAssumedLight
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_review import NOW, ready
from tests.test_betterliving2_runtime import bed, writes


async def startup(controller):
    await controller.async_on_connect(
        SimpleNamespace(
            async_start_notify=controller.start_notify,
            store_device_info=lambda *_: None,
        )
    )


async def test_startup_frames_do_not_deliver_a_cancelled_user_command(hass):
    child, controller, client, _ = await bed(hass, "p2")
    results = []

    async def operation(_controller):
        with delivered(results.append):
            await startup(controller)
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()
            await controller.lights_toggle()

    try:
        with ready(child), virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == 2  # Actual clock and query startup frames only.
        assert results == [Delivery.NONE]
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("action", ("sync_clock", "query_alarm", "query_massage"))
async def test_explicit_refresh_is_its_own_command_frame(hass, action):
    child, controller, client, _ = await bed(hass, "p2")
    results = []

    async def operation(_controller):
        with delivered(results.append):
            await getattr(controller, action)()

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == 1
        assert results == [Delivery.SENT]
    finally:
        await child.async_shutdown()


async def test_transmitted_toggle_updates_entity_after_cancellation(hass):
    child, controller, client, _ = await bed(hass, "p2")
    entity = AdjustableBedAssumedLight(child)
    entity.async_write_ha_state = MagicMock()

    async def sent(*_args, **_kwargs):
        context = current_command_context()
        assert context is not None
        context.cancel_event.set()

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            client.write_gatt_char.side_effect = sent
            await entity.async_toggle()
        assert len(writes(client)) == 1
        assert entity.is_on is True
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("when", ("before", "after"))
async def test_level_publication_uses_sent_frame_not_cancellation_alone(hass, when):
    child, controller, client, _ = await bed(hass)
    controller.forward_controller_state_updates(runtime.LEVELS["head"](2))

    async def sent(*_args, **_kwargs):
        context = current_command_context()
        assert context is not None
        context.cancel_event.set()

    async def operation(_controller):
        if when == "before":
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()
        await controller.set_level("head", 3)

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            client.write_gatt_char.side_effect = sent
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == (0 if when == "before" else 1)
        assert child.controller_state[runtime.LEVELS["head"]] == (2 if when == "before" else 3)
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("value", ("level", "alarm"))
async def test_earlier_clock_write_cannot_publish_an_unsent_value(hass, value):
    child, controller, client, _ = await bed(hass)
    controller.forward_controller_state_updates(runtime.LEVELS["head"](2))
    prior = controller._view = controller._saved = runtime.AlarmView(hour=6, minute=15)
    results = []

    async def operation(_controller):
        with delivered(results.append):
            await controller.sync_clock()
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()
            if value == "level":
                await controller.set_level("head", 3)
            else:
                plan = controller.prepare_alarm(
                    enabled=True, hour=7, minute=30, weekdays=frozenset({1}), action="memory_1"
                )
                await controller.set_alarm(plan)

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == 1
        assert results == [Delivery.PARTIAL]
        assert child.controller_state[runtime.LEVELS["head"]] == 2
        assert controller._view == controller._saved == prior
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("after_frames", (1, 2))
async def test_partial_massage_value_becomes_unknown_without_changing_unsent_zone(
    hass, after_frames
):
    child, controller, client, _ = await bed(hass)
    controller.forward_controller_state_updates(
        runtime.LEVELS["head"](2), runtime.LEVELS["feet"](2)
    )
    results = []

    async def sent(*_args, **_kwargs):
        context = current_command_context()
        assert context is not None
        if client.write_gatt_char.await_count == after_frames:
            context.cancel_event.set()

    async def operation(_controller):
        with delivered(results.append):
            await controller.massage_pair(1, 3)

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            client.write_gatt_char.side_effect = sent
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == after_frames
        assert results == [Delivery.PARTIAL]
        assert child.controller_state[runtime.LEVELS["head"]] == (None if after_frames == 1 else 1)
        assert child.controller_state[runtime.LEVELS["feet"]] == 2
    finally:
        await child.async_shutdown()


async def test_fresh_cleanup_frames_do_not_deliver_the_cancelled_command(hass):
    child, controller, client, _ = await bed(hass)
    results = []

    async def operation(_controller):
        context = current_command_context()
        assert context is not None
        context.cancel_event.set()
        with delivered(results.append):
            await controller._cleanup(controller._live(), 2, controller._serial, context)

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            await child.async_execute_controller_command(operation)
        assert len(writes(client)) == 2
        assert results == [Delivery.NONE]
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize(
    "wire,after_frames,notification",
    (
        ("p3", 1, None),
        ("p3", 3, None),
        pytest.param("p2", 1, "ed8003", id="notification_p2"),
        pytest.param("p3", 1, "a50c", id="notification_p3"),
    ),
)
async def test_partial_alarm_clears_shown_selection_and_retains_prior_preferences(
    hass, wire, after_frames, notification
):
    child, controller, client, _ = await bed(hass, wire)
    results = []
    contexts = []
    alarm_frames = []
    prior = controller._view = controller._saved = runtime.AlarmView(hour=6, minute=15)

    async def sent(*_args, **_kwargs):
        context = current_command_context()
        assert context is not None
        if client.write_gatt_char.await_count == after_frames:
            if notification is None:
                context.cancel_event.set()
            else:
                contexts.append(context)
                sender, callback = client.start_notify.call_args.args
                callback(sender, bytearray.fromhex(notification))

    async def operation(_controller):
        plan = controller.prepare_alarm(
            enabled=True, hour=7, minute=30, weekdays=frozenset({1}), action="memory_1"
        )
        alarm_frames.append(plan.frame)
        with delivered(results.append):
            await controller.set_alarm(plan)

    try:
        with ready(child), virtual_clock():
            await startup(controller)
            client.write_gatt_char.reset_mock()
            client.write_gatt_char.side_effect = sent
            await child.async_execute_controller_command(operation)
        if notification is None:
            assert len(writes(client)) == after_frames
        else:
            assert writes(client).count(alarm_frames[0]) == 1
            assert writes(client).count(runtime.app.command(wire.upper(), 0)) == 1
            assert len(contexts) == 1
            assert not contexts[0].cancel_event.is_set()
            assert contexts[0].frames_skipped == 1
        if after_frames == 1:
            assert results == [Delivery.PARTIAL]
            assert controller._view.hour is None and controller._view.minute is None
            assert controller._saved == prior
        else:
            assert results == [Delivery.SENT]
            assert controller._view.hour == controller._saved.hour == 7
            assert controller._view.minute == controller._saved.minute == 30
    finally:
        await child.async_shutdown()
