"""The unified alarm API retains the app's frames and physical admission."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_betterliving2_holds_and_sides import ready
from tests.test_betterliving2_runtime import NOW, bed, writes

VECTORS = json.loads((Path(__file__).parent / "fixtures/betterliving2/vectors.json").read_text())
ALARM_VECTORS = [row for row in VECTORS if row["id"] in {"P1-cancel", "P2-alarm", "P3-alarm"}]


@pytest.mark.parametrize("vector", ALARM_VECTORS, ids=lambda row: row["id"])
async def test_unified_alarm_matches_independent_literal(hass, vector):
    child, controller, client, device = await bed(hass, vector["protocol"].lower())
    await async_register_services(hass)
    try:
        assert controller.alarm_capability.weekdays
        assert not hass.services.has_service(DOMAIN, "betterliving2_set_alarm")
        with ready(child), virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": [device.id],
                    "enabled": vector["inputs"].get("enabled", True),
                    "time": "07:30",
                    "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "wake_action": "memory_1",
                },
                blocking=True,
            )
        assert writes(client)[:2] == [bytes.fromhex(vector["expected_bytes"])] * 2
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("wire", ("p1", "p2", "p3"))
@pytest.mark.parametrize("action", ("memory_1", "memory_2", "massage"))
async def test_unified_alarm_preserves_previous_plan_and_sunday_mapping(hass, wire, action):
    child, controller, client, device = await bed(hass, wire)
    await async_register_services(hass)
    try:
        with ready(child), virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            previous = controller.prepare_alarm(
                enabled=True, hour=7, minute=30, weekdays=frozenset({0, 1, 6}), action=action
            )
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": [device.id],
                    "enabled": True,
                    "time": "07:30",
                    "weekdays": ["sunday", "monday", "saturday"],
                    "wake_action": action,
                },
                blocking=True,
            )
        assert writes(client)[:2] == [previous.frame] * 2
    finally:
        await child.async_shutdown()
