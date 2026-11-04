"""R041-I/J/R: production entity projections and registered hold admission seams."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH, SIDE_LEFT, SIDE_RIGHT
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services


def make_child(hass: HomeAssistant, suffix: int):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "address": f"AA:BB:CC:DD:EE:{suffix:02X}", "name": f"Bed {suffix}",
        "bed_type": "reverie_pairlink", "disable_angle_sensing": True,
    })
    child = AdjustableBedCoordinator(hass, entry)
    controller = ReveriePairlinkController(child, model="R510L")
    # Transport-facing effects only. Keep real controller metadata, validation,
    # service preparation, coordinator wire/cancel locks and device scheduler.
    controller.hold_control = AsyncMock()
    controller.prepare_for_movement = AsyncMock()
    controller.stop_all = AsyncMock()
    child._controller = controller
    child.async_ensure_connected = AsyncMock(return_value=True)
    child._async_refresh_controller_auth = AsyncMock()
    return child, controller


async def call(hass, service, device="bed", **fields):
    await hass.services.async_call(DOMAIN, service, {"device_id": device, **fields}, blocking=True)


@pytest.mark.parametrize("service", ["hold_control", "timed_move"])
@pytest.mark.parametrize("paired", [False, True])
async def test_registered_hold_rejects_stop_during_actual_connect_preflight(hass, service, paired):
    left, ctrl = make_child(hass, 1)
    right, other_ctrl = make_child(hass, 2)
    parent = PairedBedCoordinator(hass, SimpleNamespace(data={"pair_id": "pair"}),
        {SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode="concurrent")
    selected = parent if paired else left
    await async_register_services(hass)
    left._controller = None
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def connect(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await finish.wait()
        left._controller = ctrl
        return True

    left.async_ensure_connected = connect
    fields = ({"control": "back_up", "duration": 1} if service == "hold_control" else
        {"motor": "back", "direction": "up", "duration_ms": 1000})
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(selected, SIDE_BOTH)], [])):
        task = asyncio.create_task(call(hass, service, **fields))
        try:
            async with asyncio.timeout(2):
                await entered.wait()
                await call(hass, "stop_all")
                finish.set()
                await task
            ctrl.hold_control.assert_not_awaited()
            other_ctrl.hold_control.assert_not_awaited()
            ctrl.stop_all.assert_awaited_once()
            assert left._command_scheduler.stop_epoch == 1
        finally:
            finish.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await left._command_scheduler.async_shutdown()
            await right._command_scheduler.async_shutdown()


@pytest.mark.parametrize("service", ["hold_control", "timed_move"])
@pytest.mark.parametrize("stop_target", ["physical", "pair"])
async def test_old_both_event_cannot_cancel_new_work_after_side_lane_wait(hass, service, stop_target):
    left, ctrl = make_child(hass, 1)
    right, other_ctrl = make_child(hass, 2)
    parent = PairedBedCoordinator(hass, SimpleNamespace(data={"pair_id": "pair"}),
        {SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode="concurrent")
    await async_register_services(hass)
    entered = asyncio.Event()
    original_lanes = parent._lanes.locked_target_sides

    @asynccontextmanager
    async def observed_lanes(targets):
        entered.set()
        async with original_lanes(targets):
            yield

    parent._lanes.locked_target_sides = observed_lanes
    fields = ({"control": "back_up", "duration": 1} if service == "hold_control" else
        {"motor": "back", "direction": "up", "duration_ms": 1000})
    active, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def newer(_controller):
        active.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    def resolve(_hass, ids, side=None):
        if ids == ["physical"]:
            return [(left, SIDE_BOTH)], []
        return [(parent, side or SIDE_BOTH)], []

    await parent._lanes.side_locks[SIDE_LEFT].acquire()
    task = newer_task = None
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets", side_effect=resolve):
            task = asyncio.create_task(call(hass, service, device="pair", **fields))
            async with asyncio.timeout(2):
                await entered.wait()
                await call(hass, "stop_all", device=stop_target,
                    **({"side": SIDE_LEFT} if stop_target == "pair" else {}))
                newer_task = asyncio.create_task(left.async_execute_controller_command(
                    newer, resource="motor:back"))
                await active.wait()
                count = left._cancel_counter
                parent._lanes.side_locks[SIDE_LEFT].release()
                await task
                assert not cancelled.is_set(), "stale Both admission cancelled newer physical movement"
                assert left._cancel_counter == count, "stale event mutated legacy cancellation ownership"
                ctrl.hold_control.assert_not_awaited()
                other_ctrl.hold_control.assert_not_awaited()
                release.set()
                await newer_task
    finally:
        if parent._lanes.side_locks[SIDE_LEFT].locked():
            parent._lanes.side_locks[SIDE_LEFT].release()
        release.set()
        for pending in (task, newer_task):
            if pending is not None and not pending.done():
                pending.cancel()
        await asyncio.gather(*(p for p in (task, newer_task) if p is not None), return_exceptions=True)
        await left._command_scheduler.async_shutdown()
        await right._command_scheduler.async_shutdown()


@pytest.mark.parametrize("service", ["hold_control", "timed_move"])
async def test_current_registered_both_event_reaches_each_real_controller(hass, service):
    left, ctrl = make_child(hass, 1)
    right, other_ctrl = make_child(hass, 2)
    parent = PairedBedCoordinator(hass, SimpleNamespace(data={"pair_id": "pair"}),
        {SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode="concurrent")
    await async_register_services(hass)
    fields = ({"control": "back_up", "duration": 1} if service == "hold_control" else
        {"motor": "back", "direction": "up", "duration_ms": 1000})
    try:
        with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, SIDE_BOTH)], [])):
            await call(hass, service, **fields)
        ctrl.hold_control.assert_awaited_once_with("back_up", 1000)
        other_ctrl.hold_control.assert_awaited_once_with("back_up", 1000)
    finally:
        await left._command_scheduler.async_shutdown()
        await right._command_scheduler.async_shutdown()


async def test_real_entity_projection_matches_card_fixture(hass):
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.button import PairedBedCombinedMotorButton
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.paired_coordinator import PairedSideProxy

    left, ctrl = make_child(hass, 1)
    right, other_ctrl = make_child(hass, 2)
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "pair"})
    entry.add_to_hass(hass)
    parent = PairedBedCoordinator(hass, entry,
        {SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode="concurrent")
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **parent.device_info)
    spec = next(spec for spec in ctrl.motor_control_specs if spec.key == "back")
    cover = AdjustableBedCover(left, _build_cover_description(spec))
    combined = PairedBedCombinedMotorButton(parent, spec, "up")
    data = {
        "standalone_cover": cover.extra_state_attributes,
        "paired_left_cover": AdjustableBedCover(
            PairedSideProxy(parent, left, SIDE_LEFT), _build_cover_description(spec)
        ).extra_state_attributes,
        "compatible_both_button": combined.extra_state_attributes,
    }

    class DifferentTiming(ReveriePairlinkController):
        @property
        def motor_control_specs(self):
            # Synthetic mismatch exercises contract intersection, not bed timing.
            return tuple(replace(spec, hold=replace(spec.hold, release_delay_ms=1))
                if spec.hold else spec for spec in super().motor_control_specs)

    right._controller = DifferentTiming(right, model="R510L")
    data["incompatible_both_button"] = combined.extra_state_attributes
    right._controller = other_ctrl
    parent._connection_mode = "sequential"
    data["sequential_both_button"] = combined.extra_state_attributes
    fixture = Path(__file__).parents[1] / "custom_components/adjustable_bed/frontend/src/fixtures/reverie041-holds.json"
    assert json.loads(fixture.read_text()) == data


async def test_standalone_controller_action_preserves_flat_hold_contract(hass):
    from custom_components.adjustable_bed.beds.base import ControllerButtonSpec, ControllerHoldSpec
    from custom_components.adjustable_bed.button import ControllerActionButton

    child, controller = make_child(hass, 3)
    spec = ControllerButtonSpec(key="back_up", name="Back up",
        press_fn=lambda ctrl: ctrl.move_back_up(),
        hold=ControllerHoldSpec("back_up"))
    button = ControllerActionButton(child, spec)
    assert button.extra_state_attributes == {
        "held_control": "back_up", "hold_start_delay_ms": 0, "hold_release_delay_ms": 0,
    }


async def test_sequential_both_button_uses_finite_current_hold_on_each_receiver(hass):
    from custom_components.adjustable_bed.button import PairedBedCombinedMotorButton

    left, ctrl = make_child(hass, 1)
    right, other_ctrl = make_child(hass, 2)
    parent = PairedBedCoordinator(hass, SimpleNamespace(data={"pair_id": "pair"}),
        {SIDE_LEFT: left, SIDE_RIGHT: right}, connection_mode="sequential")
    events = []
    for side, child, controller in ((SIDE_LEFT, left, ctrl), (SIDE_RIGHT, right, other_ctrl)):
        async def connect(_side=side):
            events.append((_side, "connect"))
            return True
        async def disconnect(_reason, _side=side):
            events.append((_side, "disconnect"))
            return True
        async def finite(control, duration_ms, _side=side):
            events.append((_side, control, duration_ms))
        child.async_connect = connect
        child.async_disconnect = disconnect
        controller.hold_control.side_effect = finite
        controller.async_send_payload = AsyncMock()
    spec = next(spec for spec in ctrl.motor_control_specs if spec.key == "back")
    button = PairedBedCombinedMotorButton(parent, spec, "up")
    assert "paired_hold_motor" not in button.extra_state_attributes
    try:
        await button.async_press()
        assert events == [
            (SIDE_LEFT, "connect"), (SIDE_LEFT, "back_up", 1000), (SIDE_LEFT, "disconnect"),
            (SIDE_RIGHT, "connect"), (SIDE_RIGHT, "back_up", 1000), (SIDE_RIGHT, "disconnect"),
        ]
        ctrl.async_send_payload.assert_not_awaited()
        other_ctrl.async_send_payload.assert_not_awaited()
    finally:
        await left._command_scheduler.async_shutdown()
        await right._command_scheduler.async_shutdown()
