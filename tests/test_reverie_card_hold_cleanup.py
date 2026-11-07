"""Native cover callers retain the controller-declared finite release policy."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie.pairlink_protocol import decrypt_user_frame
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from tests.test_reverie_pairlink import _controller, _join_central


@pytest.mark.parametrize(
    ("axis", "direction", "start", "release"),
    [
        ("back", "open", "0101ff00", "01030000"),
        ("back", "close", "0102ff00", "01030000"),
        ("legs", "open", "0104ff00", "01060000"),
        ("legs", "close", "0105ff00", "01060000"),
        ("lumbar", "open", "0107ff00", "01090000"),
        ("lumbar", "close", "0108ff00", "01090000"),
    ],
)
async def test_native_declared_cover_action_finishes_with_fresh_axis_release(
    hass, monkeypatch, axis, direction, start, release
):
    controller, client, runtime, tasks = _controller()
    client.mtu_size = 64
    await _join_central(controller, client, runtime, tasks)
    client.writes.clear()
    entry = MockConfigEntry(
        domain="adjustable_bed",
        data={
            "address": "AA:BB:CC:DD:EE:01",
            "bed_type": "reverie_pairlink",
            "protocol_variant": "R510L",
            "disable_angle_sensing": True,
        },
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller
    coordinator._client = client
    coordinator._pairlink_runtime = runtime
    controller._coordinator = coordinator
    coordinator.async_ensure_connected = AsyncMock(return_value=True)
    coordinator._async_refresh_controller_auth = AsyncMock()
    controller.prepare_for_movement = AsyncMock()
    requested_delays = []
    original_sleep = asyncio.sleep

    async def advance_protocol_clock(delay, *args, **kwargs):
        requested_delays.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", advance_protocol_clock)
    spec = next(spec for spec in controller.motor_control_specs if spec.key == axis)
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.async_write_ha_state = lambda: None
    try:
        if direction == "open":
            await cover.async_open_cover()
        else:
            await cover.async_close_cover()
        assert [
            decrypt_user_frame(
                wire, event_key=runtime.current_event_key, device_key=bytes.fromhex("10203040")
            )[10:]
            for _, wire, _ in client.writes
        ] == [bytes.fromhex(start), bytes.fromhex(release)]
        assert 1 in requested_delays
        assert cover.extra_state_attributes["held_control_up"] == f"{axis}_up"
        assert cover.extra_state_attributes["held_control_down"] == f"{axis}_down"
    finally:
        await controller.stop_notify()
        await coordinator._command_scheduler.async_shutdown()
