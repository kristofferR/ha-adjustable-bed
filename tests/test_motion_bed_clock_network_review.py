"""Startup clocks use Home Assistant local time."""
import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.motion_bed_protocol import (
    build_clock,
    build_thermal_clock,
)
from tests.test_motion_bed_lifecycle import real_coordinator


async def _cleanup(coord, controller):
    tasks = tuple(controller._tasks)
    await controller.stop_notify()
    await asyncio.gather(*tasks, return_exceptions=True)
    coord._cancel_disconnect_timer()
    await coord._command_scheduler.async_shutdown()




@pytest.mark.parametrize("name", ["QMS-IQ", "TL-B", "TL-W"])
@pytest.mark.parametrize("zone", ["Pacific/Auckland", "America/Los_Angeles"])
async def test_registered_startup_uses_configured_zone_with_utc_host(hass, monkeypatch, freezer, name, zone):
    instant = datetime(2026, 10, 2, 23, 45, 56, tzinfo=UTC)
    freezer.move_to(instant)
    await hass.config.async_set_time_zone(zone)
    local = instant.astimezone(ZoneInfo(zone))
    coord = await real_coordinator(hass, name)
    controller = coord.controller
    controller._startup = MotionBedController._startup.__get__(controller)
    # The clock assertion runs actual builders/startup; its delays and later poll
    # are covered separately and cannot race this isolated startup check.
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.asyncio.sleep", AsyncMock())
    controller._spawn = MagicMock()
    try:
        with monkeypatch.context() as host:
            host.setenv("TZ", "UTC")
            time.tzset()
            await coord.async_execute_controller_command(lambda c: c.start_notify())
        want = build_thermal_clock(local) if name == "TL-W" else build_clock(local)
        host_frame = build_thermal_clock(instant) if name == "TL-W" else build_clock(instant)
        frames = [call.args[1] for call in coord.client.write_gatt_char.await_args_list]
        assert want != host_frame and want in frames and host_frame not in frames
    finally:
        time.tzset()
        await _cleanup(coord, controller)








