"""Focused tests for the accepted Reverie Composer conversion behavior."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.adjustable_bed.beds.reverie.comfort import (
    ReverieComfortRequest,
    build_p1_composer_payload,
    build_stk_composer_payload,
    validate_comfort_request,
)
from custom_components.adjustable_bed.beds.reverie.controller import ReverieController


class _Clock:
    now = 0.0

    def time(self) -> float:
        return self.now

    def call_later(self, *_args: object) -> None:
        raise AssertionError("stable-notification progression must not self-schedule")


def _p2_controller() -> tuple[ReverieController, _Clock]:
    clock = _Clock()

    def create_task(coro, _name: str):
        return asyncio.create_task(coro)

    coordinator = SimpleNamespace(
        hold_command_connection=nullcontext,
        hass=SimpleNamespace(loop=clock, async_create_task=create_task),
        handle_controller_state_update=lambda *_args: None,
        handle_controller_state_updates=lambda *_args: None,
        async_execute_controller_command=None,
    )
    controller = ReverieController(coordinator, model="8Q")

    async def execute(operation, **_kwargs):
        await operation(controller)

    coordinator.async_execute_controller_command = execute
    controller.write_command = AsyncMock()
    return controller, clock


def _position_frame(head: int, foot: int) -> bytearray:
    return bytearray((0, 0, head, foot, 0, 0, 0, 0, 0))


def test_p1_composer_keeps_raw_byte_fields_without_general_clamping() -> None:
    request = ReverieComfortRequest(
        head_position=0,
        foot_position=17,
        lumbar_position=255,
        head_massage=2,
        foot_massage=3,
    )

    validate_comfort_request(
        request,
        supported_fields=frozenset(
            {
                "head_position",
                "foot_position",
                "lumbar_position",
                "head_massage",
                "foot_massage",
            }
        ),
    )

    assert build_p1_composer_payload(request, body_tilt=False) == bytes.fromhex(
        "000011ff080c00000000"
    )


def test_body_tilt_uses_the_accepted_signed_axis_mapping() -> None:
    negative = ReverieComfortRequest(0, 0, -100, 0, 0)
    positive = ReverieComfortRequest(0, 0, 100, 0, 0)

    assert build_p1_composer_payload(negative, body_tilt=True) == bytes.fromhex(
        "00000000000000000000"
    )
    assert build_p1_composer_payload(positive, body_tilt=True) == bytes.fromhex(
        "00000064000000000000"
    )


def test_non_tilt_profile_returns_without_a_write_for_negative_lumbar() -> None:
    request = ReverieComfortRequest(0, 0, -1, 0, 0)

    assert build_p1_composer_payload(request, body_tilt=False) is None


def test_stk_routine_payload_preserves_the_exact_side_specific_axis() -> None:
    request = ReverieComfortRequest(11, 22, 33, 2, 3)

    assert build_stk_composer_payload(
        request, side=1, current_head=None, current_head2=77
    ) == bytes.fromhex("000b164d0c080800000000")
    assert build_stk_composer_payload(
        request, side=2, current_head=66, current_head2=None
    ) == bytes.fromhex("004216210c080800000000")
    assert build_stk_composer_payload(
        request, side=3, current_head=None, current_head2=None
    ) == bytes.fromhex("000b16210c080800000000")


def test_stk_routine_requires_live_preserved_axis_feedback() -> None:
    request = ReverieComfortRequest(11, 22, 33, 2, 3)

    with pytest.raises(ValueError, match="current head2 feedback"):
        build_stk_composer_payload(request, side=1, current_head=None, current_head2=None)
    with pytest.raises(ValueError, match="current head feedback"):
        build_stk_composer_payload(request, side=2, current_head=None, current_head2=None)


async def test_p2_uses_current_notifications_instead_of_pre_request_equality() -> None:
    controller, clock = _p2_controller()
    controller._parse_position_data(_position_frame(25, 40))
    await controller.async_set_comfort(
        ReverieComfortRequest(head_position=25, foot_position=40)
    )

    current = _position_frame(10, 20)
    controller._parse_position_data(current)
    await asyncio.sleep(0)
    clock.now = 0.001
    controller._parse_position_data(current)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert controller.write_command.await_count == 2
    assert controller.write_command.await_args_list[0].args[0] == controller._build_command(
        [0x35]
    )
    assert controller.write_command.await_args_list[1].args[0] == controller._build_command(
        [0x51, 25]
    )
    assert [command for command, _value in controller._comfort_writes] == [[0x52]]


async def test_p2_later_progress_requires_a_stable_notification_after_two_seconds() -> None:
    controller, clock = _p2_controller()
    request = ReverieComfortRequest(head_position=25, foot_position=40)
    await controller.async_set_comfort(request)
    sample = _position_frame(10, 20)
    controller._parse_position_data(sample)
    clock.now = 0.001
    controller._parse_position_data(sample)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert controller.write_command.await_count == 2
    clock.now = 1.999
    controller._parse_position_data(sample)
    await asyncio.sleep(0)
    assert controller.write_command.await_count == 2

    clock.now = 2.001
    await asyncio.sleep(0)
    assert controller.write_command.await_count == 2
    controller._parse_position_data(sample)
    await asyncio.sleep(0)
    assert controller.write_command.await_count == 2
    clock.now = 2.002
    controller._parse_position_data(sample)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert controller.write_command.await_count == 3
    assert controller.write_command.await_args_list[-1].args[0] == controller._build_command(
        [0x52, 40]
    )
