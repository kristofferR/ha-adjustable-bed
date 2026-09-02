"""Artifact-vector tests for the frozen Phase 4 cluster 011 CST reports."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.okin_cst import OkinCstController
from custom_components.adjustable_bed.beds.okin_protocol import build_cst_command
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    OKIN_CST_VARIANT_AVIADA,
    OKIN_CST_VARIANT_BOB,
    OKIN_CST_VARIANT_CAREFREE,
    OKIN_CST_VARIANT_CLARITY,
    OKIN_CST_VARIANT_CONTEMPO,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_RESIDENT,
    OKIN_CST_VARIANT_SANCTUARY,
    OKIN_CST_VARIANT_SUPPORT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type


@pytest.mark.parametrize(
    ("primary", "secondary", "expected_hex"),
    [
        # Resident TV03: Flat + M program chord.
        (0x08010000, 0, "0c02080100000000000000000000"),
        # Sanctuary reachable full-body voice action.
        (0, 0x00000100, "0c02000000000000010000000000"),
        # Bob TV5: head massage decrease occupies both fields.
        (0x00800000, 0x00800000, "0c02008000000080000000000000"),
        # Support foot massage decrease is secondary-only.
        (0, 0x01000000, "0c02000000000100000000000000"),
        # Shared wave 3 vector, independently present across the cluster.
        (0, 0x00200000, "0c02000000000020000000000000"),
    ],
)
def test_frozen_cluster_vectors_build_exact_frames(
    primary: int, secondary: int, expected_hex: str
) -> None:
    """The shared builder must preserve both independently routed fields."""
    assert build_cst_command(primary, secondary).hex() == expected_hex


async def test_factory_preserves_explicit_cst_product_profile() -> None:
    """The generic factory must pass the validated profile into the controller."""
    assert is_valid_variant_for_bed_type(
        BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_SUPPORT
    )

    controller = await create_controller(
        MagicMock(),
        BED_TYPE_OKIN_CST,
        OKIN_CST_VARIANT_SUPPORT,
        None,
    )

    assert isinstance(controller, OkinCstController)
    assert controller.protocol_diagnostics["cst_profile"] == OKIN_CST_VARIANT_SUPPORT


@pytest.mark.parametrize(
    (
        "variant",
        "motors",
        "lounge",
        "incline",
        "memory_count",
        "lights",
        "massage_style",
        "massage_toggle",
        "zoned_massage",
        "timer_step",
    ),
    [
        (
            OKIN_CST_VARIANT_SANCTUARY,
            ("head", "feet"),
            True,
            False,
            2,
            True,
            "zoned",
            True,
            True,
            False,
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            ("head", "feet"),
            True,
            True,
            4,
            False,
            "zoned",
            False,
            True,
            True,
        ),
        (
            OKIN_CST_VARIANT_AVIADA,
            ("head", "feet", "lumbar"),
            True,
            True,
            3,
            True,
            "global",
            False,
            False,
            False,
        ),
        (
            OKIN_CST_VARIANT_BOB,
            ("head", "feet"),
            True,
            False,
            2,
            True,
            "zoned",
            True,
            True,
            False,
        ),
        (
            OKIN_CST_VARIANT_CONTEMPO,
            ("head", "feet", "lumbar"),
            True,
            True,
            3,
            True,
            "global",
            False,
            False,
            False,
        ),
        (
            OKIN_CST_VARIANT_CAREFREE,
            ("head", "feet"),
            False,
            False,
            1,
            True,
            "none",
            False,
            False,
            False,
        ),
        (
            OKIN_CST_VARIANT_CLARITY,
            ("head", "feet"),
            True,
            True,
            3,
            True,
            "global",
            False,
            False,
            False,
        ),
        (
            OKIN_CST_VARIANT_MF900,
            ("head", "feet", "lumbar"),
            True,
            True,
            3,
            True,
            "global",
            False,
            False,
            False,
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            ("head", "feet", "lumbar"),
            True,
            True,
            3,
            True,
            "zoned",
            False,
            True,
            False,
        ),
    ],
)
def test_fixed_product_profiles_expose_only_reachable_capabilities(
    variant: str,
    motors: tuple[str, ...],
    lounge: bool,
    incline: bool,
    memory_count: int,
    lights: bool,
    massage_style: str,
    massage_toggle: bool,
    zoned_massage: bool,
    timer_step: bool,
) -> None:
    """Each accepted app has one fixed, manually selectable capability set."""
    controller = OkinCstController(MagicMock(), variant=variant)

    assert tuple(spec.key for spec in controller.motor_control_specs) == motors
    assert controller.has_lumbar_support is ("lumbar" in motors)
    assert controller.supports_preset_lounge is lounge
    assert controller.supports_preset_incline is incline
    assert controller.memory_slot_count == memory_count
    assert controller.supports_discrete_light_control is lights
    assert controller.protocol_diagnostics["cst_massage_style"] == massage_style
    assert controller.supports_massage is (massage_style != "none")
    assert controller.supports_massage_toggle_control is massage_toggle
    assert controller.supports_head_massage_intensity_step_control is zoned_massage
    assert controller.supports_foot_massage_intensity_step_control is zoned_massage
    assert controller.massage_mode_step_is_timer is timer_step


@pytest.mark.parametrize(
    ("variant", "method_name", "expected_hex"),
    [
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_toggle",
            "0c02000000000000010000000000",
        ),
        (
            OKIN_CST_VARIANT_BOB,
            "massage_head_down",
            "0c02008000000080000000000000",
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            "massage_foot_down",
            "0c02000000000100000000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_mode_step",
            "0c02000002000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_wave_next",
            "0c02000000000008000000000000",
        ),
    ],
)
@patch(
    "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_profile_actions_route_artifact_fields_exactly(
    _mock_sleep: AsyncMock,
    variant: str,
    method_name: str,
    expected_hex: str,
) -> None:
    """Product-specific actions must not collapse their primary/secondary fields."""
    controller = OkinCstController(MagicMock(), variant=variant)
    write = AsyncMock()
    method: Callable[[], Awaitable[None]] = getattr(controller, method_name)

    with patch.object(controller, "write_command", write):
        await method()

    assert write.await_args_list[0].args[0].hex() == expected_hex


@patch(
    "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_resident_fourth_memory_slot_uses_m_vectors(
    _mock_sleep: AsyncMock,
) -> None:
    """Resident's additional M recall/program pair remains distinct."""
    controller = OkinCstController(MagicMock(), variant=OKIN_CST_VARIANT_RESIDENT)
    write = AsyncMock()

    with patch.object(controller, "write_command", write):
        await controller.preset_memory(4)
        await controller.program_memory(4)

    first_frames = [record.args[0].hex() for record in write.await_args_list]
    assert "0c02000100000000000000000000" in first_frames
    assert "0c02080100000000000000000000" in first_frames
