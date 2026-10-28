"""Operation-owned Serta release and current paired hold projection regressions."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from custom_components.adjustable_bed.beds.cluster033 import AppController
from custom_components.adjustable_bed.beds.serta_mp_remote import (
    HEAD_TABLE,
    SertaMPRemoteController,
    pulse_frame,
)
from custom_components.adjustable_bed.button import _combined_motor_buttons_for
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services

from .test_cluster033_hold_admission import _connected_pair, _target

ZERO = bytes.fromhex("e5fe160000000006")
LOCAL = pulse_frame(HEAD_TABLE[1], 0x8000)


@pytest.fixture(autouse=True)
async def cleanup_targets(hass):
    yield
    for target in hass.data.get("cluster033_test_targets", []):
        await target.async_shutdown()


async def _serta(hass, monkeypatch):
    target, _controller, client = await _target(hass)
    target._client = client
    controller = SertaMPRemoteController(target)
    target._controller = controller
    monkeypatch.setattr(controller, "_wait", AsyncMock(return_value=False))
    await controller.start_notify()
    client.write_gatt_char.reset_mock()
    monkeypatch.setattr(target, "async_ensure_connected", AsyncMock(return_value=True))
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=target.entry.entry_id, **target.device_info
    )
    await async_register_services(hass)
    return target, controller, client, device


async def _call(hass, device, service, **fields):
    await hass.services.async_call(
        DOMAIN, service, {"device_id": [device.id], **fields}, blocking=True
    )


def _frames(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


async def _editing(hass, monkeypatch, target, controller, device, *, disconnect=False):
    started = asyncio.Event()

    async def wait(_ms, *, cleanup=False):
        assert not cleanup
        started.set()
        await target.cancel_command.wait()
        if disconnect:
            controller.on_disconnect()
        return True

    monkeypatch.setattr(controller, "_wait", wait)
    task = asyncio.create_task(
        _call(hass, device, "hold_control", control="head_target_up", duration=60)
    )
    await asyncio.wait_for(started.wait(), 2)
    return task


async def test_local_edit_stop_acknowledges_once_then_later_global_stops_send_zero(
    hass, monkeypatch
):
    target, controller, client, device = await _serta(hass, monkeypatch)
    editing = await _editing(hass, monkeypatch, target, controller, device)
    await _call(hass, device, "stop_all")
    await asyncio.wait_for(editing, 2)
    assert _frames(client) == [LOCAL]
    assert controller._local_release_stop is None
    await _call(hass, device, "stop_all")
    await _call(hass, device, "stop_all")
    assert _frames(client) == [LOCAL, ZERO, ZERO]


async def test_normal_local_completion_cannot_acknowledge_a_later_global_stop(hass, monkeypatch):
    _target, controller, client, device = await _serta(hass, monkeypatch)
    await _call(hass, device, "hold_control", control="head_target_up", duration=0.2)
    assert _frames(client) == [LOCAL]
    assert controller._local_release_stop is None
    await _call(hass, device, "stop_all")
    assert _frames(client) == [LOCAL, ZERO]
    await _call(hass, device, "hold_control", control="head_up", duration=0.1)
    assert _frames(client)[-2:] == [bytes.fromhex("e5fe160100000005"), ZERO]
    await _call(hass, device, "stop_all")
    assert _frames(client)[-1] == ZERO
    assert _frames(client).count(ZERO) == 3


async def test_newer_movement_replacement_cannot_turn_local_release_into_stop_ack(
    hass, monkeypatch
):
    target, controller, client, device = await _serta(hass, monkeypatch)
    editing = await _editing(hass, monkeypatch, target, controller, device)
    # A remote key replaces local editing through the same real scheduler.
    # Let just that next control complete finitely after it obtains admission.
    # The worker executes both commands, so changing the wait after replacement
    # starts would be racy. The remote key's single100ms wait can finish on the
    # second call while the existing local200ms wait retains its old coroutine.
    monkeypatch.setattr(controller, "_wait", AsyncMock(return_value=False))
    await _call(hass, device, "hold_control", control="head_up", duration=0.1)
    await asyncio.wait_for(editing, 2)
    assert controller._local_release_stop is None
    assert _frames(client) == [LOCAL, bytes.fromhex("e5fe160100000005"), ZERO]
    await _call(hass, device, "stop_all")
    assert _frames(client)[-1] == ZERO
    assert _frames(client).count(ZERO) == 2


async def test_failed_local_release_preserves_error_and_cannot_acknowledge_stop(hass, monkeypatch):
    target, controller, client, device = await _serta(hass, monkeypatch)
    editing = await _editing(hass, monkeypatch, target, controller, device)
    error = RuntimeError("local target transport failed")

    async def write(_char, command, **_kwargs):
        if command == LOCAL:
            raise error

    client.write_gatt_char.side_effect = write
    await _call(hass, device, "stop_all")
    with pytest.raises(RuntimeError) as caught:
        await asyncio.wait_for(editing, 2)
    assert caught.value is error
    assert controller._local_release_stop is None
    assert _frames(client) == [LOCAL, ZERO]


async def test_disconnected_skipped_release_cannot_acknowledge_reconnected_stop(hass, monkeypatch):
    target, controller, client, device = await _serta(hass, monkeypatch)
    editing = await _editing(hass, monkeypatch, target, controller, device, disconnect=True)
    await _call(hass, device, "stop_all")
    await asyncio.wait_for(editing, 2)
    assert _frames(client) == []
    assert controller._local_release_stop is None
    monkeypatch.setattr(controller, "_wait", AsyncMock(return_value=False))
    await controller.start_notify()
    client.write_gatt_char.reset_mock()
    await _call(hass, device, "stop_all")
    assert _frames(client) == [ZERO]


async def test_interrupted_release_during_overlapping_stops_cannot_acknowledge_either(
    hass, monkeypatch
):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    target, controller, client, device = await _serta(hass, monkeypatch)
    acknowledgements = []
    stop_all = controller.stop_all

    async def stop():
        context = current_command_context()
        acknowledgements.append(
            (controller._local_release_stop, context.admitted_stop_epoch if context else None)
        )
        await stop_all()

    monkeypatch.setattr(controller, "stop_all", stop)
    editing = await _editing(hass, monkeypatch, target, controller, device)
    writing, finish_write = asyncio.Event(), asyncio.Event()
    completed = []

    async def write(_char, command, **_kwargs):
        if command == LOCAL:
            writing.set()
            await finish_write.wait()
        completed.append(command)

    client.write_gatt_char.side_effect = write
    admitted_second = asyncio.Event()
    admit_stop = target._command_scheduler.admit_stop

    def admit(*args, **kwargs):
        task = admit_stop(*args, **kwargs)
        if target._command_scheduler.stop_epoch == 2:
            admitted_second.set()
        return task

    monkeypatch.setattr(target._command_scheduler, "admit_stop", admit)
    first = asyncio.create_task(_call(hass, device, "stop_all"))
    await asyncio.wait_for(writing.wait(), 2)
    second = asyncio.create_task(_call(hass, device, "stop_all"))
    await asyncio.wait_for(admitted_second.wait(), 2)
    finish_write.set()
    await asyncio.wait_for(asyncio.gather(editing, first, second), 2)
    assert _frames(client) == [LOCAL, ZERO, ZERO]
    assert completed == [ZERO, ZERO]
    assert acknowledgements == [(None, 1), (None, 2)]
    await _call(hass, device, "stop_all")
    assert _frames(client) == [LOCAL, ZERO, ZERO, ZERO]


async def test_later_admitted_stop_does_not_steal_successful_release_acknowledgement(
    hass, monkeypatch
):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandKind,
        current_command_context,
    )

    target, controller, client, device = await _serta(hass, monkeypatch)
    editing = await _editing(hass, monkeypatch, target, controller, device)
    stopping, finish_stop, second_admitted = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def auth():
        context = current_command_context()
        if context and context.kind is CommandKind.STOP and context.admitted_stop_epoch == 1:
            stopping.set()
            await finish_stop.wait()

    monkeypatch.setattr(target, "_async_refresh_controller_auth", auth)
    admit_stop = target._command_scheduler.admit_stop

    def admit(*args, **kwargs):
        task = admit_stop(*args, **kwargs)
        if target._command_scheduler.stop_epoch == 2:
            second_admitted.set()
        return task

    monkeypatch.setattr(target._command_scheduler, "admit_stop", admit)
    first = asyncio.create_task(_call(hass, device, "stop_all"))
    await asyncio.wait_for(stopping.wait(), 2)
    assert _frames(client) == [LOCAL]
    assert controller._local_release_stop is not None
    second = asyncio.create_task(_call(hass, device, "stop_all"))
    await asyncio.wait_for(second_admitted.wait(), 2)
    finish_stop.set()
    await asyncio.wait_for(asyncio.gather(editing, first, second), 2)
    assert _frames(client) == [LOCAL, ZERO]
    assert controller._local_release_stop is None


async def _published_buttons(hass, monkeypatch):
    pair, parent, children, triples = await _connected_pair(hass, monkeypatch)
    await async_setup_component(hass, "button", {})
    entities = _combined_motor_buttons_for(pair, list(pair.children.values()))
    for entity in entities:
        entity.entity_id = f"button.current_{entity._motor_key}_{entity._direction}"
    await hass.data["button"].async_add_entities(entities)
    return pair, parent, children, triples, entities


async def test_actual_auto_fallback_publishes_finite_both_and_registered_press_executes(
    hass, monkeypatch
):
    pair, _parent, _children, triples, entities = await _published_buttons(hass, monkeypatch)
    up = next(entity for entity in entities if entity.entity_id == "button.current_back_up")
    assert hass.states.get(up.entity_id).attributes["held_control"] == "head_up"
    assert pair._automatic_connection_mode
    left, left_ctrl, left_client = triples["left"]
    right, right_ctrl, right_client = triples["right"]
    left._connection_source = "hci0"
    right_client.is_connected = False

    async def exhausted(*, reset_timer=True):
        right._connection_attempt_details.append(
            {"error": "No connection slot available", "selected_source": "hci0"}
        )
        right._connection_attempt_count += 1
        return False

    route = []
    for side, (target, controller, client) in triples.items():

        async def disconnect(side=side, client=client):
            route.append(("disconnect", side))
            client.is_connected = False

        client.disconnect.side_effect = disconnect

        async def connect(side=side, target=target, controller=controller, client=client):
            assert all(
                not peer.is_connected for name, peer in pair.children.items() if name != side
            )
            route.append(("connect", side))
            target._client, target._controller = client, controller
            client.is_connected = True
            controller._wait = AsyncMock(return_value=False)
            await controller.start_notify()
            return True

        monkeypatch.setattr(target, "async_connect", connect)
    monkeypatch.setattr(right, "async_ensure_connected", exhausted)
    with pytest.raises(ConnectionError, match="Not connected"):
        await pair.async_execute_controller_command(lambda c: c.move_head_up(), side="right")
    monkeypatch.setattr(right, "async_ensure_connected", AsyncMock(return_value=True))
    assert pair.connection_mode == "sequential"
    assert "held_control" not in hass.states.get(up.entity_id).attributes
    assert all("held_control" not in entity.extra_state_attributes for entity in entities)
    # The same existing entity must retain finite execution through HA, not
    # just hide its hold label. Both physical protocols run in one-link order.
    for _child, controller, client in triples.values():
        monkeypatch.setattr(controller, "stop_all", AppController.stop_all.__get__(controller))
        client.write_gatt_char.reset_mock()
    route.clear()
    await hass.services.async_call("button", "press", {"entity_id": up.entity_id}, blocking=True)
    assert route == [
        ("connect", "left"),
        ("disconnect", "left"),
        ("connect", "right"),
        ("disconnect", "right"),
    ]
    for client in (left_client, right_client):
        assert bytes.fromhex("e5fe160100000005") in _frames(client)
        assert _frames(client)[-1] == ZERO
    assert not left.is_connected and not right.is_connected


@pytest.mark.parametrize(
    "change",
    [
        "up_control",
        "down_control",
        "start",
        "release",
        "missing_hold",
        "missing_motor",
        "unknown",
        "new_profile",
    ],
)
async def test_current_physical_specs_replace_construction_hold_offer(hass, monkeypatch, change):
    pair, _parent, _children, triples, entities = await _published_buttons(hass, monkeypatch)
    right, controller, _client = triples["right"]
    assert all("held_control" in entity.extra_state_attributes for entity in entities)
    original = AppController.motor_control_specs.fget
    assert original is not None
    specs = controller.motor_control_specs
    back = specs[0]
    if change in ("up_control", "down_control", "start", "release"):
        field = {"start": "start_delay_ms", "release": "release_delay_ms"}.get(change, change)
        altered = replace(
            back,
            hold=replace(
                back.hold, **{field: 7 if change in ("start", "release") else "different"}
            ),
        )
    elif change == "missing_hold":
        altered = replace(back, hold=None)
    else:
        altered = back
    monkeypatch.setattr(
        AppController,
        "motor_control_specs",
        property(
            lambda self: (
                ((altered,) + specs[1:] if change != "missing_motor" else specs[1:])
                if self is controller
                else original(self)
            )
        ),
    )
    if change == "unknown":
        right._controller = right._offline_controller = None
    elif change == "new_profile":
        from custom_components.adjustable_bed.cluster033_profiles import app_profile

        right._controller = AppController(right, app_profile("qplus_app", "MX"))
    pair._on_child_connection_change(pair.is_connected)
    for entity in entities:
        attrs = hass.states.get(entity.entity_id).attributes
        expected = not (
            change in ("unknown", "new_profile")
            or entity._motor_key == "back"
            and (
                change not in ("up_control", "down_control")
                or entity._direction == change.split("_")[0]
            )
        )
        assert ("held_control" in attrs) is expected
    right._controller = controller
    monkeypatch.setattr(AppController, "motor_control_specs", property(original))
    pair._on_child_connection_change(pair.is_connected)
    assert all(
        "held_control" in hass.states.get(entity.entity_id).attributes for entity in entities
    )


async def test_local_edit_body_error_propagates_after_target_release_and_later_stop(
    hass, monkeypatch
):
    _coordinator, controller, client, device = await _serta(hass, monkeypatch)
    error = RuntimeError("local edit operation failed")
    monkeypatch.setattr(controller, "_wait", AsyncMock(side_effect=error))
    with pytest.raises(RuntimeError) as caught:
        await _call(hass, device, "hold_control", control="head_target_up", duration=0.2)
    assert caught.value is error
    assert _frames(client) == [LOCAL]
    assert controller._local_release_stop is None
    await _call(hass, device, "stop_all")
    assert _frames(client) == [LOCAL, ZERO]
