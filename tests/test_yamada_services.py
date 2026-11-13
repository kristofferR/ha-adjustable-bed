"""Production family service admission with independent P1/P2 targets."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.keeson.yamada_services import (
    async_register_yamada_services,
)
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH, SIDE_LEFT
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import yamada as app
from tests.hold_lease_wire import virtual_clock
from tests.test_bedtech_services import pair
from tests.test_yamada import bed


async def target(version):
    controller, _, client = await bed(version)
    child = MagicMock(spec=AdjustableBedCoordinator)
    child.name = version
    child.bed_type = "yamada"
    child.entry = SimpleNamespace(data={})
    child.controller_side = None
    child.capability_controller = controller
    child.stop_epoch = 0
    child.pairlink_peripheral = False

    async def execute(command, **kwargs):
        if kwargs.get("expected_stop_epoch", child.stop_epoch) == child.stop_epoch:
            await command(controller)

    child.async_execute_controller_command = AsyncMock(side_effect=execute)
    return child, controller, client


async def call(hass, targets):
    async_register_yamada_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "yamada_set_alarm",
            {
                "device_id": ["bed"],
                "slot": 1,
                "enabled": True,
                "time": "07:30",
                "weekday": 129,
                "preset": "memory_1",
            },
            blocking=True,
        )


async def test_all_targets_validate_before_requested_alarm_writes(hass):
    first, _, a = await target("p2")
    second, _, b = await target("p1")  # Other slot unknown.
    with pytest.raises(ServiceValidationError):
        await call(hass, [(first, SIDE_BOTH), (second, SIDE_BOTH)])
    a.write_gatt_char.assert_not_awaited()
    b.write_gatt_char.assert_not_awaited()


async def test_stop_on_later_target_invalidates_captured_batch_admission(hass):
    first, _, a = await target("p2")
    second, _, b = await target("p2")
    execute = first.async_execute_controller_command.side_effect

    async def stop_later(command, **kwargs):
        second.stop_epoch += 1
        await execute(command, **kwargs)

    first.async_execute_controller_command.side_effect = stop_later
    with virtual_clock():
        await call(hass, [(first, SIDE_BOTH), (second, SIDE_BOTH)])
    assert a.write_gatt_char.called
    b.write_gatt_char.assert_not_awaited()


async def test_paired_child_retains_its_profile_slot_and_other_alarm(hass):
    left, lc, a = await target("p1")
    right, _, b = await target("p2")
    lc._alarms[2] = app.Alarm(8, 45, 255, 28, True)
    parent = pair(left, right)
    with virtual_clock():
        await call(hass, [(parent, SIDE_LEFT)])
    assert a.write_gatt_char.call_args_list[0].args[1].hex() == "ed8003071e810e082dff1c000000008b"
    b.write_gatt_char.assert_not_awaited()
