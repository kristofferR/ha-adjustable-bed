"""Personal Comfort sequences exercise the real paired group admission."""

import asyncio
from contextvars import Context
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.personal_comfort.services import register_services
from custom_components.adjustable_bed.command_scheduler import (
    CommandIntent,
    current_command_context,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_paired_coordinator import RecordingChild, _make
from tests.test_personal_comfort import make, writes
from tests.test_wire_snapshot import _load_tool


@pytest.fixture
async def clock():
    tool = _load_tool()
    virtual = tool.FakeClock()
    with tool.virtual_time(virtual):
        yield virtual


class Child(RecordingChild):
    # Like a spec=AdjustableBedCoordinator mock, this scheduler-backed double
    # advertises the receiver interface required by linked readiness.
    @property
    def __class__(self):
        return AdjustableBedCoordinator

    @__class__.setter
    def __class__(self, value: type[object]) -> None:
        raise TypeError("This receiver double keeps its scheduler implementation")

    async def async_validate_linked_command_readiness(self):
        await self.controller.async_validate_linked_readiness()

    async def async_prepare_command_operation(
        self,
        operation,
        *,
        resource=None,
        resources=None,
        cancel_running=True,
        group_id,
        expected_stop_epoch=None,
    ):
        # The real coordinator preempts its legacy event before reservation.
        if cancel_running:
            self._cancel.set()
        return await super().async_prepare_command_operation(
            operation,
            resource=resource,
            resources=resources,
            cancel_running=cancel_running,
            group_id=group_id,
            expected_stop_epoch=expected_stop_epoch,
        )

    @property
    def cancel_command(self):
        context = current_command_context()
        return context.cancel_event if context is not None else self._cancel

    async def async_execute_controller_command(
        self,
        command_fn,
        cancel_running=True,
        skip_disconnect=False,
        resource=None,
        resources=None,
        **_kwargs,
    ):
        await command_fn(self.controller)

    def record_command_trace(self, **_kwargs):
        pass

    def handle_controller_state_update(self, *_args):
        pass

    def handle_controller_state_updates(self, *_args):
        pass


def pair(left_route="malouf", right_route="reverie_v2", right_model="pf4"):
    log = []
    controllers, children = [], {}
    for side, route, model in (("left", left_route, "pf4"), ("right", right_route, right_model)):
        controller, c = make(route, model)
        child = Child(side, log)
        child._cancel = asyncio.Event()
        child.client = c.client
        child.controller = child.capability_controller = controller
        child._protocol_variant = route
        child.bed_type = "personal_comfort"
        child.entry = SimpleNamespace(
            data={"bed_type": "personal_comfort", "protocol_variant": route}
        )
        controller._coordinator = child
        children[side] = child
        controllers.append(controller)
    parent = _make(children, connection_mode="concurrent")
    return parent, controllers


async def call(hass, parent, operation, side="both"):
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(parent, side)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "personal_comfort_sequence",
            {"device_id": ["bed"], "operation": operation, "side": side},
            blocking=True,
        )


async def close(parent):
    await asyncio.gather(*(child.scheduler.async_shutdown() for child in parent.children.values()))


async def test_full_body_both_heads_before_feet(hass, clock):
    parent, controllers = pair()
    events = []
    for index, controller in enumerate(controllers):

        async def record(_char, packet, *, response, index=index):
            assert response
            events.append((index, bytes(packet).hex()))

        controller.client.write_gatt_char.side_effect = record
    try:
        await call(hass, parent, "full_body_massage")
        assert set(events[:2]) == {(0, "6e01004cbb"), (1, "32")}
        assert set(events[2:]) == {(0, "6e01004ebd"), (1, "32")}
        assert all(child.prepared_scopes for child in parent.children.values())
    finally:
        await close(parent)


async def test_every_model_admitted_before_first_write(hass, clock):
    parent, controllers = pair(right_model="pf2")
    try:
        with pytest.raises(ServiceValidationError):
            await call(hass, parent, "full_body_massage")
        assert all(not writes(controller._coordinator) for controller in controllers)
    finally:
        await close(parent)


async def test_peer_foot_uses_receiver_profile_and_releases(hass, clock):
    parent, controllers = pair()
    try:
        await call(hass, parent, "flat_with_peer_foot", "left")
        assert [v[1] for v in writes(controllers[0]._coordinator)] == ["6e010031a0"]
        assert writes(controllers[1]._coordinator) == [
            ("db801022-f324-29c3-38d1-85c0c2e86885", "02", True),
            ("db801022-f324-29c3-38d1-85c0c2e86885", "00", True),
        ]
    finally:
        await close(parent)


async def test_peer_stop_prevents_delayed_feet_but_drains_own_release(clock):
    left, _ = make("malouf")
    right, c = make("reverie_v2")
    captured = left.capture()

    def validate():
        left.check_owner(captured)

    owner = replace(right.capture(), validate=validate)
    original = c.client.write_gatt_char
    tasks = []

    async def stop_peer():
        await asyncio.sleep(0.3)
        left._coordinator.stop_epoch += 1

    def write(*_args, **_kwargs):
        if not tasks:
            tasks.append(asyncio.create_task(stop_peer()))

    original.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await right.held_axis(owner, "feet", False, 30_000)
    assert [v[1] for v in writes(c)] == ["02", "00"]
    await asyncio.gather(*tasks)
    assert clock.now <= 0.4


async def test_session_change_blocks_delayed_full_body_foot(clock):
    controller, c = make("malouf")
    owner = controller.capture()
    c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: controller.on_disconnect()
    from custom_components.adjustable_bed.beds.personal_comfort.services import full_body

    with pytest.raises(ConnectionError):
        await full_body(controller, owner)
    assert [v[1] for v in writes(c)] == ["6e01004cbb"]


@pytest.mark.parametrize("right_route", ["reverie_v1", "reverie_v2"])
async def test_memory_all_target_admission_keeps_physical_receiver(hass, right_route):
    from homeassistant.core import ServiceCall

    from custom_components.adjustable_bed.services import handle_goto_preset

    parent, controllers = pair(right_route=right_route)
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, "both")], []),
        ):
            request = handle_goto_preset(
                ServiceCall(hass, DOMAIN, "goto_preset", {"preset": 2, "device_id": ["bed"]})
            )
            if right_route == "reverie_v1":
                with pytest.raises(ServiceValidationError):
                    await request
                assert all(not writes(controller._coordinator) for controller in controllers)
            else:
                await request
                assert [v[1] for v in writes(controllers[0]._coordinator)] == ["6e01002f9e"]
                assert [v[1] for v in writes(controllers[1]._coordinator)] == ["05"]
    finally:
        await close(parent)


async def test_stop_on_later_target_during_preflight_blocks_every_write(hass, clock, monkeypatch):
    from custom_components.adjustable_bed.beds.personal_comfort import services

    first, a = pair()
    second, b = pair()
    original = services._validation_controller
    changed = False

    async def validation(parent, child, preflighted):
        nonlocal changed
        result = await original(parent, child, preflighted)
        if parent is second and not changed:
            changed = True
            epoch = child.scheduler.request_stop()
            child.scheduler.finish_stop(epoch)
        return result

    monkeypatch.setattr(services, "_validation_controller", validation)
    register_services(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (second, "both")], []),
            ),
            pytest.raises(ServiceValidationError),
        ):
            await hass.services.async_call(
                DOMAIN,
                "personal_comfort_sequence",
                {"device_id": ["a", "b"], "operation": "full_body_massage"},
                blocking=True,
            )
        assert changed
        assert all(not writes(controller._coordinator) for controller in (*a, *b))
    finally:
        await close(first)
        await close(second)


async def test_peer_sequence_stop_is_expected_and_preserves_queued_command(hass, clock):
    parent, controllers = pair()
    peer = controllers[1]
    tasks = []

    async def stop_selected():
        await asyncio.sleep(0.3)
        await parent.async_stop_command(side="left")

    async def queued(_context):
        await peer.preset_zero_g()

    async def write(_char, packet, **_kwargs):
        if packet == b"\x02":
            tasks.append(asyncio.create_task(stop_selected(), context=Context()))
        elif packet == b"\x00":
            tasks.append(
                asyncio.create_task(
                    parent.children["right"].scheduler.execute(
                        CommandIntent(queued, cancel_running=False)
                    ),
                    context=Context(),
                )
            )
            await asyncio.sleep(0.1)

    peer.client.write_gatt_char.side_effect = write
    try:
        await call(hass, parent, "flat_with_peer_foot", "left")
        await asyncio.gather(*tasks)
        assert [v[1] for v in writes(peer._coordinator)] == ["02", "00", "01"]
        assert parent.children["left"].stop_epoch == 1
        assert parent.children["right"].stop_epoch == 0
        assert clock.now <= 0.5
    finally:
        await close(parent)
