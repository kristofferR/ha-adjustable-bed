"""Registered services prove the card's physical cleanup ownership assumptions."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.setup import async_setup_component

from custom_components.adjustable_bed.beds.cluster033 import AppController
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.paired_coordinator import PairedSideProxy

from .test_cluster033_hold_admission import _connected_pair


@pytest.fixture(autouse=True)
async def cleanup_targets(hass):
    yield
    for target in hass.data.get("cluster033_test_targets", []):
        await target.async_shutdown()


async def _cover_pair(hass, monkeypatch):
    pair, parent, children, triples = await _connected_pair(hass, monkeypatch)
    await async_setup_component(hass, "cover", {})
    covers = {}
    starts = {side: asyncio.Event() for side in triples}
    for side, (target, controller, _client) in triples.items():
        # The shared temporal fixture mocks this method. Restore the real app
        # release: these assertions need actual zero/query packets and cleanup.
        monkeypatch.setattr(controller, "stop_all", AppController.stop_all.__get__(controller))

        async def wait(_ms, *, cleanup=False, target=target, side=side):
            if cleanup:
                return False
            starts[side].set()
            await target.cancel_command.wait()
            return True

        monkeypatch.setattr(controller, "_wait", wait)
        runtime = PairedSideProxy(pair, target, side)
        cover = AdjustableBedCover(
            runtime, _build_cover_description(controller.motor_control_specs[0])
        )
        cover.entity_id = f"cover.card_{side}"
        covers[side] = cover
    await hass.data["cover"].async_add_entities(list(covers.values()))
    return pair, parent, children, triples, starts, covers


async def test_registered_opposite_stop_preserves_right_hold_until_own_cover_release(
    hass, monkeypatch
):
    _pair, _parent, children, triples, starts, covers = await _cover_pair(hass, monkeypatch)
    right, _controller, client = triples["right"]
    held = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [children["right"].id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    try:
        await asyncio.wait_for(starts["right"].wait(), 2)
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [children["left"].id]}, blocking=True
        )
        assert not held.done()
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            bytes.fromhex("e5fe160100000005")
        ]
        # The actual HA registered cover service runs its current stop_fn and
        # paired resource path; no direct controller or stop mock substitutes.
        await hass.services.async_call(
            "cover", "stop_cover", {"entity_id": covers["right"].entity_id}, blocking=True
        )
        await asyncio.wait_for(held, 2)
        frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert frames[0] == bytes.fromhex("e5fe160100000005")
        assert frames[1:] and all(
            frame == bytes.fromhex("e5fe160000000006") for frame in frames[1:]
        )
        assert not right._command_scheduler.has_pending
    finally:
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)


async def test_registered_partial_both_stop_requires_remaining_side_cleanup(hass, monkeypatch):
    _pair, parent, children, triples, starts, _covers = await _cover_pair(hass, monkeypatch)
    held = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [parent.id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in starts.values())), 2)
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [children["left"].id]}, blocking=True
        )
        right, _controller, client = triples["right"]
        assert not held.done()
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            bytes.fromhex("e5fe160100000005")
        ]
        # Keeping Both's card release owner is required: Left STOP alone does
        # not end the other child's bounded service, even with shared admission.
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [parent.id]}, blocking=True
        )
        await asyncio.wait_for(held, 2)
        assert any(
            call.args[1] == bytes.fromhex("e5fe160000000006")
            for call in client.write_gatt_char.await_args_list
        )
        assert all(
            not child._command_scheduler.has_pending for child, _ctrl, _client in triples.values()
        )
    finally:
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)


@pytest.mark.parametrize("kind", ["mx", "serta"])
async def test_registered_source_specific_release_policy_probe(hass, monkeypatch, kind):
    """Capture actual registered cancellation packets without protocol timers."""
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.beds.serta_mp_remote import (
        HEAD_TABLE,
        SertaMPRemoteController,
        pulse_frame,
    )
    from custom_components.adjustable_bed.services import async_register_services

    from .test_cluster033_hold_admission import _target

    target, controller, client = await _target(hass, mx=kind == "mx")
    target._client, target._controller = client, controller
    if kind == "serta":
        controller = SertaMPRemoteController(target)
        target._controller = controller
        controller._wait = AsyncMock(return_value=False)
        await controller.start_notify()
        client.write_gatt_char.reset_mock()
    monkeypatch.setattr(target, "async_ensure_connected", AsyncMock(return_value=True))
    started = asyncio.Event()
    cleanup_delays = []

    async def wait(ms, *, cleanup=False):
        if cleanup:
            cleanup_delays.append(ms)
            return False
        started.set()
        await target.cancel_command.wait()
        return True

    monkeypatch.setattr(controller, "_wait", wait)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=target.entry.entry_id, **target.device_info
    )
    await async_register_services(hass)
    held = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": [device.id],
                "control": "mx_memory1" if kind == "mx" else "head_target_up",
                "duration": 60,
            },
            blocking=True,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 2)
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [device.id]}, blocking=True
        )
        await asyncio.wait_for(held, 2)
        frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
        if kind == "mx":
            assert frames[0] == bytes.fromhex("040200010000")
            assert frames[1:] and all(frame == b"\x00\xb0" for frame in frames[1:])
            assert cleanup_delays == [300] * 6  # command-finally and explicit Stop each query only
        else:
            assert frames == [pulse_frame(HEAD_TABLE[1], 0x8000)]
    finally:
        held.cancel()
        await asyncio.gather(held, return_exceptions=True)


def test_existing_combined_entity_drops_hold_offer_after_live_sequential_transition():
    """Pin the current-mode projection seam, independently of card inference."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.button import _combined_motor_buttons_for
    from custom_components.adjustable_bed.cluster033_profiles import app_profile

    from .test_cluster033 import coordinator

    ctrl = AppController(coordinator(), app_profile("tempur_curve"))
    parent = MagicMock(pair_id="pair", device_info={}, children={}, connection_mode="concurrent")
    entities = _combined_motor_buttons_for(
        parent, [SimpleNamespace(capability_controller=ctrl)] * 2
    )
    assert all("held_control" in entity.extra_state_attributes for entity in entities)
    parent.connection_mode = "sequential"
    assert all("held_control" not in entity.extra_state_attributes for entity in entities)
