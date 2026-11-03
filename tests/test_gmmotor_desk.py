"""The dedicated GM Control desk widget's actual sender and release callbacks."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.gmmotor_desk import GmmotorDeskController
from custom_components.adjustable_bed.gmmotor_requests import Request


def controller(profile: str = "FWRM") -> GmmotorDeskController:
    coordinator = MagicMock()
    coordinator.hass.data = {}
    coordinator.cancel_command = asyncio.Event()
    ctrl = GmmotorDeskController(coordinator, profile=profile)
    ctrl.write_command = AsyncMock()
    ctrl._pause = AsyncMock(return_value=True)
    return ctrl


async def test_desk_movement_and_reset_use_their_own_builder_and_cleanup() -> None:
    ctrl = controller()
    await ctrl.hold_control("desk_up", 100)
    assert [c.args[0] for c in ctrl.write_command.call_args_list] == [
        bytes.fromhex("6e01000170"),
        bytes.fromhex("6e01006edd"),
    ]
    ctrl.write_command.reset_mock()
    await ctrl.bind_side("right").hold_control("desk_reset", 100)
    assert [c.args[0] for c in ctrl.write_command.call_args_list] == [
        bytes.fromhex("6e95000003"),
        bytes.fromhex("6e01006edd"),
    ]
    assert not ctrl.write_command.call_args.kwargs["cancel_event"].is_set()


async def test_desk_long_memory_callback_is_noop_and_short_recall_does_not_release() -> None:
    ctrl = controller("WFRM")
    await ctrl.hold_control("desk_memory_3", 3000)
    ctrl.write_command.assert_not_awaited()
    await ctrl.hold_control("desk_memory_3", 100)
    ctrl.write_command.assert_awaited_once_with(bytes.fromhex("6e0100107f"))


async def test_height_sender_converts_selected_unit_before_decimal_builder() -> None:
    ctrl = controller()
    await ctrl.async_execute_gmmotor_request(Request("desk_height", height=125, unit="cm"))
    ctrl.write_command.assert_awaited_once_with(bytes.fromhex("6e880c3234"))
    ctrl.write_command.reset_mock()
    await ctrl.async_execute_gmmotor_request(Request("desk_height", height=49.21, unit="inch"))
    ctrl.write_command.assert_awaited_once_with(bytes.fromhex("6e880c3133"))
    with pytest.raises(ValueError, match="between"):
        ctrl.validate_gmmotor_request(Request("desk_height", height=50, unit="cm"))


def test_reported_desk_limits_validate_before_any_write() -> None:
    ctrl = controller()
    ctrl._events["desk_data"] = {
        "min_cm": 65.0,
        "max_cm": 120.0,
        "min_inches": 25.6,
        "max_inches": 47.2,
    }
    with pytest.raises(ValueError, match="between 65.0 and 120.0"):
        ctrl.validate_gmmotor_request(Request("desk_height", height=125))
    with pytest.raises(ValueError):
        ctrl.validate_gmmotor_request(Request("alarm"))
    assert not ctrl.supports_single_address_pairing


async def test_units_and_setup_query_are_direct_single_shots() -> None:
    ctrl = controller()
    await ctrl.async_execute_gmmotor_request(Request("desk_unit", unit="inch"))
    await ctrl._setup_menu()
    assert [c.args[0] for c in ctrl.write_command.call_args_list] == [
        bytes.fromhex("6e91000100"),
        bytes.fromhex("6e94000002"),
    ]
