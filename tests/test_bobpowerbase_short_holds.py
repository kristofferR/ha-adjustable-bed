"""Bob finite holds exclude source startup, while absolute safety fences still win."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.beds.goodvibe import controller as bed
from custom_components.adjustable_bed.beds.goodvibe.controller import GoodVibeController
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
    HoldLease,
    current_command_context,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.profiles.bobpowerbase import CATALOG
from tests.hold_lease_wire import virtual_clock
from tests.test_bobpowerbase_services import domain_bootstrap as domain_bootstrap
from tests.test_bobpowerbase_services import register, runtime

MOVE = codec.function(CATALOG.actions["head_up"].short)
STOP = codec.function(0x6E)


@pytest.fixture
async def physical(hass):
    coordinator = runtime(hass)
    device = register(hass, coordinator)
    await services.async_register_services(hass)
    with (
        patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock()),
    ):
        try:
            yield coordinator, device
        finally:
            await coordinator.async_shutdown()
            await coordinator.entry._async_process_on_unload(hass)


@pytest.fixture
async def clock(physical, monkeypatch):
    del physical
    # Reuse only the existing virtual timer, never a wire scenario/capture.
    with virtual_clock() as clock:
        monkeypatch.setattr(bed, "monotonic", clock.time)
        yield clock


@pytest.mark.parametrize(
    ("duration_ms", "count", "overhead"),
    (
        (100, 1, 0),
        (100, 1, 0.00001),
        (200, 2, 0),
        (200, 2, 0.00001),
        (350, 4, 0),
        (350, 4, 0.00001),
    ),
)
async def test_registered_finite_hold_survives_advancing_setup_and_preserves_fixed_end(
    hass,
    physical,
    clock,
    monkeypatch,
    duration_ms,
    count,
    overhead,
):
    coordinator, device = physical
    controller = coordinator.controller
    tick_s = CATALOG.bed.tick_ms / 1000
    anchor = clock.time()
    end = anchor + tick_s + duration_ms / 1000
    clock_reads, writes, cleanup, waits, contexts = [], [], [], [], []

    def advancing_time():
        observed = clock.time()
        clock_reads.append(observed)
        # Compare zero and nonzero CPU/callback overhead, including between
        # deadline creation and its first condition.
        clock.advance_to(observed + overhead)
        return observed

    original_send, original_delay = controller._send, controller._delay

    async def send(packet, **kwargs):
        if kwargs.get("cleanup"):
            cleanup.append(clock.time())
        return await original_send(packet, **kwargs)

    async def delay(milliseconds):
        waits.append(milliseconds)
        return await original_delay(milliseconds)

    async def write(_characteristic, packet, **_kwargs):
        writes.append((clock.time(), packet))
        contexts.append(current_command_context())

    monkeypatch.setattr(bed, "monotonic", advancing_time)
    monkeypatch.setattr(controller, "_send", send)
    monkeypatch.setattr(controller, "_delay", delay)
    coordinator.client.write_gatt_char.side_effect = write
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {
            "device_id": device,
            "control": "goodvibe_head_up",
            "duration": duration_ms / 1000,
        },
        blocking=True,
    )
    movement = [when for when, packet in writes if packet == MOVE]
    assert len(movement) == count
    assert clock_reads[1] - clock_reads[0] == overhead
    assert movement[0] >= anchor + tick_s
    assert all(
        later - earlier >= tick_s or later - earlier == pytest.approx(tick_s)
        for earlier, later in zip(movement, movement[1:], strict=False)
    )
    assert all(when < end for when in movement)
    assert cleanup and end <= cleanup[0] < end + tick_s
    assert any(0 < milliseconds <= CATALOG.bed.tick_ms for milliseconds in waits)
    assert writes[-1][1] == STOP
    stop_at = writes[-1][0]
    assert stop_at >= cleanup[0]
    if overhead == 0:
        assert movement == pytest.approx([anchor + tick_s * i for i in range(1, count + 1)])
        assert cleanup[0] == pytest.approx(end)
        # The finite budget ends movement admission, not FIFO release pacing:
        # 350ms enters cleanup at 450ms and submits STOP at 500ms.
        assert stop_at == pytest.approx(max(end, movement[-1] + tick_s))
    assert clock.time() >= stop_at  # Public completion includes cleanup drain.
    # The actual registered finite route creates COMMAND, not a shorter lease.
    assert all(context is not None and context.kind == CommandKind.COMMAND for context in contexts)
    assert all(context.lease is None and context.hold_deadline is None for context in contexts)


async def test_delayed_gatt_does_not_backfill_or_restart_finite_budget(
    physical, clock, monkeypatch
):
    coordinator, _device = physical
    controller = coordinator.controller
    tick_s = CATALOG.bed.tick_ms / 1000
    anchor = clock.time()
    end = anchor + tick_s + 0.350
    writes, cleanup = [], []
    original_send = controller._send

    async def send(packet, **kwargs):
        if kwargs.get("cleanup"):
            cleanup.append(clock.time())
        return await original_send(packet, **kwargs)

    async def write(_characteristic, packet, **_kwargs):
        writes.append((clock.time(), packet))
        if packet == MOVE:
            await asyncio.sleep(0.320)

    monkeypatch.setattr(controller, "_send", send)
    coordinator.client.write_gatt_char.side_effect = write
    await controller.hold_control("goodvibe_head_up", 350)
    assert [packet for _when, packet in writes] == [MOVE, STOP]
    assert end <= cleanup[0] < end + tick_s


@pytest.mark.parametrize("pacing_delay", (0.100, 0.300))
async def test_pacing_at_or_past_fixed_end_cannot_force_first_frame(
    physical, clock, monkeypatch, pacing_delay
):
    coordinator, _device = physical
    controller = coordinator.controller

    async def pace(cleanup):
        if not cleanup:
            await asyncio.sleep(pacing_delay)
        return True

    monkeypatch.setattr(controller, "_pace", pace)
    await controller.hold_control("goodvibe_head_up", 100)
    assert [call.args[1] for call in coordinator.client.write_gatt_char.await_args_list] == [STOP]


@pytest.mark.parametrize("ending", ("stop", "caller_cancel"))
async def test_early_stop_or_cancel_skips_motion_and_drains_captured_cleanup(
    physical, clock, ending
):
    coordinator, _device = physical
    start = clock.time()
    hold = asyncio.create_task(coordinator.controller.hold_control("goodvibe_head_up", 350))
    await asyncio.sleep(0.050)
    if ending == "stop":
        await coordinator.async_stop_command()
        await hold
    else:
        hold.cancel()
        with pytest.raises(asyncio.CancelledError):
            await hold
    assert [call.args[1] for call in coordinator.client.write_gatt_char.await_args_list] == [STOP]
    assert clock.time() < start + CATALOG.bed.tick_ms / 1000


async def test_expired_absolute_native_lease_never_forces_first_callback(physical, clock):
    coordinator, _device = physical
    external_end = clock.time() + 0.050
    context = CommandContext(
        scheduler_token=coordinator._command_scheduler.token,
        cancel_event=asyncio.Event(),
        admitted_stop_epoch=coordinator.stop_epoch,
        intent_id="expired-native-hold",
        kind=CommandKind.HOLD,
        group_id=None,
        resources=frozenset({"*"}),
        lease=HoldLease("card", 1, "goodvibe_head_up", 0.050),
        hold_deadline=external_end,
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        # Simulate an overdue native expiry callback: the absolute deadline,
        # independently of a not-yet-set event, must still fence GATT dispatch.
        await coordinator.controller.hold_control("goodvibe_head_up", 1000)
        assert context.hold_deadline == external_end
        assert [call.args[1] for call in coordinator.client.write_gatt_char.await_args_list] == [
            STOP
        ]
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


@pytest.mark.parametrize("replacement", ("controller", "physical_link"))
async def test_queued_short_hold_cannot_cross_owner_or_session(physical, clock, replacement):
    coordinator, _device = physical
    original = coordinator.controller
    client = coordinator.client
    await original._ble_lock.acquire()
    hold = asyncio.create_task(original.hold_control("goodvibe_head_up", 100))
    await asyncio.sleep(0.150)
    if replacement == "controller":
        coordinator._controller = GoodVibeController(
            coordinator, profile="ultra_sh", catalog=CATALOG
        )
    else:
        coordinator._client = None
        coordinator._position_connection_generation += 1
    original._ble_lock.release()
    with pytest.raises(ConnectionError):
        await hold
    client.write_gatt_char.assert_not_awaited()
    coordinator._client = client
