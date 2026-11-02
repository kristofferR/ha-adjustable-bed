"""Tests for adjustable bed cover entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkCredentials,
    PairlinkHomeIdOrigin,
    PairlinkRole,
    PairlinkRuntime,
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
        entry=SimpleNamespace(data={}, options={}),
        entity_side="left",
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
        name="Pairlink left",
        async_execute_controller_command=AsyncMock(),
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
    }
