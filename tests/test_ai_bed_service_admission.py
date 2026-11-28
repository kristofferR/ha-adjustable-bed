"""Reject an incompatible paired target before any live AI Bed preparation."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.ai_bed.controller import AiBedController
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator


async def test_later_incompatible_side_rejects_before_either_child_connects(hass, monkeypatch):
    children = {}
    for index, (side, route) in enumerate((("left", "305"), ("right", "limos"))):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": f"AA:BB:CC:DD:EE:{index + 50:02X}",
                "name": side,
                "bed_type": "ai_bed",
                "protocol_variant": route,
                "ble_device_name": "MpeV3B-5-M2",
                "disable_angle_sensing": True,
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        child._controller = AiBedController(child, route, "MpeV3B-5-M2")
        child.async_ensure_connected = AsyncMock(return_value=False)
        child.async_execute_controller_command = AsyncMock()
        children[side] = child
    pair_entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "ai-bed-admission"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, pair_entry, children, connection_mode="sequential")
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, "both")], []))
    await services.async_register_services(hass)
    try:
        with pytest.raises(ServiceValidationError) as rejected:
            await hass.services.async_call(
                const.DOMAIN,
                "ai_bed",
                {"device_id": "bed", "action": "settings_query"},
                blocking=True,
            )
        assert isinstance(rejected.value.__cause__, ValueError)
        assert "primary AI Bed route" in str(rejected.value.__cause__)
        for child in children.values():
            child.async_ensure_connected.assert_not_awaited()
            child.async_execute_controller_command.assert_not_awaited()
            assert child.client is None
    finally:
        for child in children.values():
            await child.async_shutdown()
