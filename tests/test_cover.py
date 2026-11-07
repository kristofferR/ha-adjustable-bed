"""Tests for adjustable bed cover entities."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import (
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from custom_components.adjustable_bed.beds.octo import OctoController
from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkCredentials,
    PairlinkHomeIdOrigin,
    PairlinkRole,
    PairlinkRuntime,
)
from custom_components.adjustable_bed.const import BED_TYPE_OCTO
from custom_components.adjustable_bed.cover import (
    AdjustableBedCover,
    AdjustableBedCoverEntityDescription,
    _build_cover_description,
)


async def _noop(_controller) -> None:
    return None


@pytest.mark.parametrize("pulse_count", [1, 50, 99])
@pytest.mark.parametrize(("motor_count", "motor"), [(1, "tv_lift"), (2, "back"), (2, "legs")])
@pytest.mark.parametrize("direction", ["open", "close"])
async def test_octo_cover_respects_configured_pulses(
    pulse_count: int, motor_count: int, motor: str, direction: str
) -> None:
    """Native OCTO actions keep configured travel even when the card supports holds."""
    coordinator = MagicMock()
    coordinator.bed_type = BED_TYPE_OCTO
    coordinator.motor_count = motor_count
    coordinator.motor_pulse_count = pulse_count
    coordinator.motor_pulse_delay_ms = 350
    coordinator.cancel_command = asyncio.Event()
    coordinator.entry.data = {}
    controller = OctoController(coordinator)
    controller._legacy_motor_layout_available = True
    controller._write_octo_command = AsyncMock()
    spec = next(spec for spec in controller.motor_control_specs if spec.key == motor)

    async def execute(command, **_kwargs) -> None:
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.async_write_ha_state = MagicMock()

    if direction == "open":
        await cover.async_open_cover()
    else:
        await cover.async_close_cover()

    movement, stop = controller._write_octo_command.await_args_list
    assert movement.kwargs["repeat_count"] == pulse_count
    assert movement.kwargs["repeat_delay_ms"] == 350
    assert movement.kwargs["data"] == [4 if motor == "legs" else 2]
    assert movement.kwargs["command"] == [2, 0x70 if direction == "open" else 0x71]
    assert stop.kwargs["command"] == [2, 0x73]
    assert not stop.kwargs["cancel_event"].is_set()


async def test_cover_commands_use_physical_position_axis_resource() -> None:
    """Logical Keeson motor names must share their seek scheduler resource."""
    coordinator = SimpleNamespace(
        capability_controller=None,
        entity_side=None,
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
        name="Test bed",
        async_execute_controller_command=AsyncMock(),
        async_stop_motor=AsyncMock(),
    )
    cover = AdjustableBedCover(
        coordinator,
        AdjustableBedCoverEntityDescription(
            key="head",
            translation_key="head",
            open_fn=_noop,
            close_fn=_noop,
            stop_fn=_noop,
            position_key="back",
        ),
    )
    cover.async_write_ha_state = MagicMock()

    await cover.async_open_cover()
    await cover.async_close_cover()
    await cover.async_stop_cover()

    assert [
        call.kwargs["resource"]
        for call in coordinator.async_execute_controller_command.await_args_list
    ] == ["motor:back", "motor:back"]
    # The Stop is a motor-scoped STOP on the same physical axis.
    assert coordinator.async_stop_motor.await_args.args[1] == "motor:back"


async def test_pairlink_controller_hold_metadata_reaches_sided_cover_attributes() -> None:
    runtime = PairlinkRuntime(
        PairlinkCredentials(
            b"\x01\x00\x00\x00",
            b"1122",
            PairlinkHomeIdOrigin.EXPLICIT_CONFIG,
        ),
        role=PairlinkRole.CENTRAL,
        target_mac="11:22:33:44:55:66",
        local_join_bt_mac=bytes.fromhex("102030405060"),
    )
    coordinator = SimpleNamespace(
        capability_controller=None,
        entry=SimpleNamespace(data={}, options={}),
        entity_side="left",
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
        name="Pairlink left",
        async_execute_controller_command=AsyncMock(),
        handle_controller_state_updates=MagicMock(),
    )
    controller = ReveriePairlinkController(coordinator, model="R510L", runtime=runtime)
    spec = next(item for item in controller.motor_control_specs if item.key == "back")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))

    assert cover.extra_state_attributes == {
        "bed_side": "left",
        "held_control_up": "back_up",
        "held_control_down": "back_down",
        "hold_start_delay_ms": 0,
        "hold_release_delay_ms": 0,
        "held_stop_scope": "motor",
    }


def test_controller_hold_metadata_is_exposed_without_changing_other_cover_attributes() -> None:
    hold = ControllerMotorHoldSpec(
        up_control="part_1_up",
        down_control="part_1_down",
        start_delay_ms=100,
        release_delay_ms=100,
        stop_scope="side",
    )
    description = _build_cover_description(
        MotorControlSpec(
            key="m1x12_part_1",
            translation_key="starcode_m1x12_part_1",
            open_fn=_noop,
            close_fn=_noop,
            stop_fn=_noop,
            hold=hold,
        )
    )
    coordinator = SimpleNamespace(
        capability_controller=None,
        entity_side="left",
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
    )
    cover = AdjustableBedCover(coordinator, description)

    assert cover.extra_state_attributes == {
        "bed_side": "left",
        "held_control_up": "part_1_up",
        "held_control_down": "part_1_down",
        "hold_start_delay_ms": 100,
        "hold_release_delay_ms": 100,
        "held_stop_scope": "side",
    }


def test_cover_without_controller_hold_does_not_publish_hold_metadata() -> None:
    coordinator = SimpleNamespace(
        capability_controller=None,
        entity_side=None,
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
    )
    cover = AdjustableBedCover(
        coordinator,
        AdjustableBedCoverEntityDescription(
            key="back",
            translation_key="back",
            open_fn=_noop,
            close_fn=_noop,
            stop_fn=_noop,
        ),
    )

    assert not cover.extra_state_attributes
