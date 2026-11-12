"""Captured release ownership through the real timed-move lease and STOP callers."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.command_scheduler import (
    CommandOutcome,
    current_command_context,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.services import async_register_services
from tests.test_comfy import no_real_timers  # noqa: F401
from tests.test_coordinator_sleepys_elite import _FakeGattClient, _ready_command_lane


@pytest.mark.parametrize("app", ("komfyd", "comfyds"))
@pytest.mark.parametrize("release_owner", ("expire", "bed", "cover"))
async def test_timed_move_lease_releases_captured_routing_once(hass, app, release_owner):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=app,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            const.CONF_BED_TYPE: app,
            const.CONF_PRODUCT_TYPE: 130,
            const.CONF_KAIDI_ROOM_ID: 10001,
            const.CONF_KAIDI_SOFA_ACU_NO: 0xF322,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _FakeGattClient()
    coordinator._client = client
    controller = await create_controller(coordinator, app, None, client)
    controller._ready, controller._own, controller._target = True, 0x11223344, 0x12345678
    coordinator._controller = controller
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_services(hass)
    started = asyncio.Event()
    frames: list[bytes] = []

    def change_routing():
        controller._selected_side = 2
        controller._own, controller._target = 0x88776655, 0x55667788

    async def write(_uuid, frame, **_kwargs):
        frames.append(bytes(frame))
        if frame[11] == 1:
            started.set()
            if release_owner == "expire":
                change_routing()
                context = current_command_context()
                assert context is not None and context.lease is not None
                context.request_cancel(CommandOutcome.EXPIRED)

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(
        coordinator, _build_cover_description(controller.motor_control_specs[0])
    )
    try:
        with (
            _ready_command_lane(coordinator),
            patch.object(cover, "async_write_ha_state"),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, const.SIDE_BOTH)], []),
            ),
        ):
            operation = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {
                        "device_id": ["bed"],
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 1000,
                        "hold_owner": "card",
                        "hold_generation": 1,
                    },
                    blocking=True,
                )
            )
            await started.wait()
            if release_owner == "expire":
                await operation
            else:
                change_routing()
                release = (
                    coordinator.async_stop_command()
                    if release_owner == "bed"
                    else cover.async_stop_cover()
                )
                await asyncio.gather(operation, release)
        assert [frame[11] for frame in frames] == [1, 3]
        assert frames[0][1:10] == frames[1][1:10]
        with _ready_command_lane(coordinator):
            await coordinator.async_stop_command()
        # The acknowledgement belongs to the preempted operation only. A new
        # independent STOP still sends the current side's real axis releases.
        assert [frame[11] for frame in frames[2:]] == [12, 15, 18]
    finally:
        await coordinator.async_shutdown()
