"""Tests for adjustable bed cover entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.adjustable_bed.beds.base import (
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from custom_components.adjustable_bed.cover import (
    AdjustableBedCover,
    AdjustableBedCoverEntityDescription,
    _build_cover_description,
)


async def _noop(_controller) -> None:
    return None


async def test_cover_commands_use_physical_position_axis_resource() -> None:
    """Logical Keeson motor names must share their seek scheduler resource."""
    coordinator = SimpleNamespace(
        entity_side=None,
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
        name="Test bed",
        async_execute_controller_command=AsyncMock(),
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
    ] == ["motor:back", "motor:back", "motor:back"]


def test_controller_hold_metadata_is_exposed_without_changing_other_cover_attributes() -> None:
    hold = ControllerMotorHoldSpec(
        up_control="part_1_up",
        down_control="part_1_down",
        start_delay_ms=100,
        release_delay_ms=100,
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
    }


def test_cover_without_controller_hold_does_not_publish_hold_metadata() -> None:
    coordinator = SimpleNamespace(
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

    assert cover.extra_state_attributes is None
