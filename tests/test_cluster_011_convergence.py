"""Artifact-vector tests for the frozen Phase 4 cluster 011 CST reports."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.okin_cst import OkinCstController
from custom_components.adjustable_bed.beds.okin_protocol import build_cst_command
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
from custom_components.adjustable_bed.config_flow import _motor_count_options
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
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

_ZERO_G_MEMORY = (
    "0c02000010000000000000000000",
    "0c02080010000000000000000000",
)
_INCLINE_MEMORY = (
    "0c02000040000000000000000000",
    "0c02080040000000000000000000",
)
_LOUNGE_MEMORY = (
    "0c02000020000000000000000000",
    "0c02080020000000000000000000",
)
_M_MEMORY = (
    "0c02000100000000000000000000",
    "0c02080100000000000000000000",
)


def _assert_command_and_stop_sequence(
    write: AsyncMock, expected_hex: str
) -> asyncio.Event:
    """Assert one command followed by two uncancellable STOP writes."""
    assert len(write.await_args_list) == 3
    command, first_stop, second_stop = write.await_args_list
    assert command.args[0].hex() == expected_hex

    stop_event = first_stop.kwargs["cancel_event"]
    assert isinstance(stop_event, asyncio.Event)
    assert not stop_event.is_set()
    for stop in (first_stop, second_stop):
        assert stop.args == (build_cst_command(),)
        assert stop.kwargs == {"cancel_event": stop_event}
    return stop_event


@dataclass(frozen=True)
class CstProfileExpectation:
    """Complete user-visible surface for one fixed CST product profile."""

    variant: str
    motors: tuple[str, ...]
    lounge: bool
    incline: bool
    memory_names: tuple[str, ...]
    memory_vectors: tuple[tuple[str, str], ...]
    lights: bool
    massage_style: str
    massage_toggle: bool = False
    timer_step: bool = False


_PROFILE_EXPECTATIONS = (
    CstProfileExpectation(
        OKIN_CST_VARIANT_SANCTUARY,
        ("head", "feet"),
        True,
        False,
        ("Zero Gravity", "Lounge"),
        (_ZERO_G_MEMORY, _LOUNGE_MEMORY),
        True,
        "zoned",
        massage_toggle=True,
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_RESIDENT,
        ("head", "feet"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge", "M"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY, _M_MEMORY),
        False,
        "zoned",
        timer_step=True,
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_AVIADA,
        ("head", "feet", "lumbar"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY),
        True,
        "global",
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_BOB,
        ("head", "feet"),
        True,
        False,
        ("Zero Gravity", "Lounge"),
        (_ZERO_G_MEMORY, _LOUNGE_MEMORY),
        True,
        "zoned",
        massage_toggle=True,
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_CONTEMPO,
        ("head", "feet", "lumbar"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY),
        True,
        "global",
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_CAREFREE,
        ("head", "feet"),
        False,
        False,
        ("Zero Gravity",),
        (_ZERO_G_MEMORY,),
        True,
        "none",
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_CLARITY,
        ("head", "feet"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY),
        True,
        "global",
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_MF900,
        ("head", "feet", "lumbar"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY),
        True,
        "global",
    ),
    CstProfileExpectation(
        OKIN_CST_VARIANT_SUPPORT,
        ("head", "feet", "lumbar"),
        True,
        True,
        ("Zero Gravity", "Incline", "Lounge"),
        (_ZERO_G_MEMORY, _INCLINE_MEMORY, _LOUNGE_MEMORY),
        True,
        "zoned",
    ),
)

_COMMON_BUTTONS = {
    "connect",
    "disconnect",
    "preset_anti_snore",
    "preset_flat",
    "preset_zero_g",
    "stop",
}


def _expected_button_keys(expected: CstProfileExpectation) -> set[str]:
    """Return the exact button surface described by a profile expectation."""
    keys = set(_COMMON_BUTTONS)
    for slot in range(1, len(expected.memory_names) + 1):
        keys.update({f"preset_memory_{slot}", f"program_memory_{slot}"})
    if expected.lounge:
        keys.add("preset_lounge")
    if expected.incline:
        keys.add("preset_incline")
    if expected.massage_style == "global":
        keys.update({"massage_all_down", "massage_all_off", "massage_all_up", "massage_mode_step"})
    elif expected.massage_style == "zoned":
        keys.update(
            {
                "massage_all_off",
                "massage_foot_down",
                "massage_foot_up",
                "massage_head_down",
                "massage_head_up",
                "massage_mode_step",
            }
        )
        if expected.massage_toggle:
            keys.add("massage_all_toggle")
        if expected.timer_step:
            keys.update({"massage_wave_next", "massage_wave_previous"})
    return keys


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


@pytest.mark.parametrize("expected", _PROFILE_EXPECTATIONS, ids=lambda expected: expected.variant)
async def test_factory_and_config_preserve_every_cst_product_profile(
    expected: CstProfileExpectation,
) -> None:
    """Factory and motor-count validation must preserve every fixed profile."""
    motor_count = len(expected.motors)
    assert is_valid_variant_for_bed_type(BED_TYPE_OKIN_CST, expected.variant)
    assert _motor_count_options(BED_TYPE_OKIN_CST, expected.variant) == [motor_count]

    controller = await create_controller(
        MagicMock(),
        BED_TYPE_OKIN_CST,
        expected.variant,
        None,
    )

    assert isinstance(controller, OkinCstController)
    assert controller.protocol_diagnostics["cst_profile"] == expected.variant
    assert tuple(spec.key for spec in controller.motor_control_specs) == expected.motors


@pytest.mark.parametrize("expected", _PROFILE_EXPECTATIONS, ids=lambda expected: expected.variant)
def test_fixed_product_profiles_expose_exact_reachable_entity_surface(
    expected: CstProfileExpectation,
) -> None:
    """Each accepted app must expose exactly its reachable controls."""
    controller = OkinCstController(MagicMock(), variant=expected.variant)
    has_massage = expected.massage_style != "none"
    zoned_massage = expected.massage_style == "zoned"

    assert tuple(spec.key for spec in controller.motor_control_specs) == expected.motors
    assert controller.stale_motor_entity_keys == (
        frozenset({"back", "legs", "tilt"})
        if "lumbar" in expected.motors
        else frozenset({"back", "legs", "lumbar", "tilt"})
    )
    assert controller.has_lumbar_support is ("lumbar" in expected.motors)
    assert controller.supports_preset_zero_g is True
    assert controller.supports_preset_anti_snore is True
    assert controller.supports_preset_lounge is expected.lounge
    assert controller.supports_preset_incline is expected.incline
    assert controller.supports_memory_presets is True
    assert controller.supports_memory_programming is True
    assert controller.memory_slot_count == len(expected.memory_names)
    assert controller.memory_slot_names == expected.memory_names
    assert len(expected.memory_vectors) == len(expected.memory_names)
    assert controller.supports_lights is expected.lights
    assert controller.supports_light_toggle_control is expected.lights
    assert controller.supports_discrete_light_control is expected.lights
    assert controller.protocol_diagnostics["cst_massage_style"] == expected.massage_style
    assert controller.supports_massage is has_massage
    assert controller.auto_enable_massage is has_massage
    assert controller.supports_massage_off_control is has_massage
    assert controller.supports_massage_toggle_control is expected.massage_toggle
    assert controller.supports_massage_intensity_step_control is (
        expected.massage_style == "global"
    )
    assert controller.supports_head_massage_intensity_step_control is zoned_massage
    assert controller.supports_foot_massage_intensity_step_control is zoned_massage
    assert controller.supports_massage_mode_step_control is has_massage
    assert controller.massage_mode_step_is_timer is expected.timer_step
    assert controller.supports_massage_wave_direction_control is expected.timer_step
    assert controller.supports_stop_all is True

    button_keys = {
        description.key
        for description in BUTTON_DESCRIPTIONS
        if _should_add_button(description, controller, has_massage)
    }
    assert button_keys == _expected_button_keys(expected)

    switch_keys = {
        description.key
        for description in SWITCH_DESCRIPTIONS
        if description.required_capability is None
        or getattr(controller, description.required_capability, False)
    }
    assert switch_keys == ({"under_bed_lights"} if expected.lights else set())


def test_auto_profile_preserves_legacy_massage_opt_in() -> None:
    """An unresolved CST entry must not gain massage entities on upgrade."""
    controller = OkinCstController(MagicMock(), variant=VARIANT_AUTO)

    assert controller.supports_massage is True
    assert controller.auto_enable_massage is False


@pytest.mark.parametrize(
    ("variant", "method_name", "expected_hex"),
    [
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_head_up",
            "0c02000008000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_head_down",
            "0c02008000000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_foot_up",
            "0c02000004000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_foot_down",
            "0c02010000000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SANCTUARY,
            "massage_toggle",
            "0c02000000000000010000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_head_up",
            "0c02000008000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_head_down",
            "0c02008000000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_foot_up",
            "0c02000004000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_RESIDENT,
            "massage_foot_down",
            "0c02010000000000000000000000",
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
        (
            OKIN_CST_VARIANT_BOB,
            "massage_head_up",
            "0c02000008000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_BOB,
            "massage_head_down",
            "0c02008000000080000000000000",
        ),
        (
            OKIN_CST_VARIANT_BOB,
            "massage_foot_up",
            "0c02000004000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_BOB,
            "massage_foot_down",
            "0c02010000000100000000000000",
        ),
        (
            OKIN_CST_VARIANT_BOB,
            "massage_toggle",
            "0c02000000000000010000000000",
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            "massage_head_up",
            "0c02000008000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            "massage_head_down",
            "0c02008000000080000000000000",
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            "massage_foot_up",
            "0c02000004000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_SUPPORT,
            "massage_foot_down",
            "0c02000000000100000000000000",
        ),
        (
            OKIN_CST_VARIANT_AVIADA,
            "massage_intensity_up",
            "0c0200000c000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_AVIADA,
            "massage_intensity_down",
            "0c02018000000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_AVIADA,
            "massage_mode_step",
            "0c02000000000008000000000000",
        ),
        (
            OKIN_CST_VARIANT_AVIADA,
            "massage_off",
            "0c02020000000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_CAREFREE,
            "lights_toggle",
            "0c02000200000000000000000000",
        ),
        (
            OKIN_CST_VARIANT_CAREFREE,
            "lights_on",
            "0c02000000000000004000000000",
        ),
        (
            OKIN_CST_VARIANT_CAREFREE,
            "lights_off",
            "0c02000000000000008000000000",
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

    _assert_command_and_stop_sequence(write, expected_hex)


@pytest.mark.parametrize(
    ("variant", "method_name"),
    [
        (OKIN_CST_VARIANT_AVIADA, "massage_head_up"),
        (OKIN_CST_VARIANT_RESIDENT, "massage_toggle"),
        (OKIN_CST_VARIANT_SANCTUARY, "massage_wave_next"),
        (OKIN_CST_VARIANT_SANCTUARY, "massage_wave_previous"),
        (OKIN_CST_VARIANT_CAREFREE, "massage_head_up"),
        (OKIN_CST_VARIANT_CAREFREE, "massage_toggle"),
        (OKIN_CST_VARIANT_CAREFREE, "massage_mode_step"),
        (OKIN_CST_VARIANT_CAREFREE, "massage_wave_next"),
        (OKIN_CST_VARIANT_CAREFREE, "massage_wave_previous"),
    ],
)
async def test_profile_actions_reject_unproven_commands_without_writing(
    variant: str,
    method_name: str,
) -> None:
    """Profiles must fail closed when an action has no frozen command mapping."""
    controller = OkinCstController(MagicMock(), variant=variant)
    write = AsyncMock()
    method: Callable[[], Awaitable[None]] = getattr(controller, method_name)

    with (
        patch.object(controller, "write_command", write),
        pytest.raises(NotImplementedError, match="not supported"),
    ):
        await method()

    write.assert_not_awaited()


@patch(
    "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
    new_callable=AsyncMock,
)
@pytest.mark.parametrize("expected", _PROFILE_EXPECTATIONS, ids=lambda expected: expected.variant)
async def test_every_profile_memory_slot_uses_its_exact_vectors(
    _mock_sleep: AsyncMock,
    expected: CstProfileExpectation,
) -> None:
    """Every profile must retain its exact ordered recall/program mapping."""
    controller = OkinCstController(MagicMock(), variant=expected.variant)
    write = AsyncMock()

    with patch.object(controller, "write_command", write):
        for slot, (recall_hex, program_hex) in enumerate(expected.memory_vectors, start=1):
            await controller.preset_memory(slot)
            recall_stop_event = _assert_command_and_stop_sequence(write, recall_hex)
            write.reset_mock()

            await controller.program_memory(slot)
            program_stop_event = _assert_command_and_stop_sequence(write, program_hex)
            assert program_stop_event is not recall_stop_event
            write.reset_mock()
