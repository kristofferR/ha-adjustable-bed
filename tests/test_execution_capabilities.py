"""Execution capabilities (#483, #516): what a declaration admits, and what it needs."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import BED_TYPE_SLEEP_ASSIST_PRO, SUPPORTED_BED_TYPES
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from tests.test_controller_contract import _create_controller_for_bed_type

STREAM_HOOKS = ("stream_tick_s", "write_stream_tick", "end_stream_member", "release_stream")


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_concurrent_declaration_implements_the_stream_hooks(bed_type: str) -> None:
    """A controller that merges motors must compose its own frames (#516).

    The base hooks raise, so a merged stream would fail before its release.
    """
    controller = await _create_controller_for_bed_type(bed_type)
    if not controller.execution.concurrent:
        return
    for hook in STREAM_HOOKS:
        assert getattr(type(controller), hook) is not getattr(BedController, hook), (
            bed_type,
            hook,
        )


async def test_sleep_assist_pro_renewable_hold_is_serialized() -> None:
    """A16 Remote starts one 200 ms refresh timer for the selected control."""
    controller = await _create_controller_for_bed_type(BED_TYPE_SLEEP_ASSIST_PRO)
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("head_up") == "stream"


def test_default_declares_nothing() -> None:
    assert NO_EXECUTION_CAPABILITIES.declared == frozenset()
    assert ExecutionCapabilities(
        hold="stream", sustain_ms=217, concurrent=frozenset({"motor:back", "motor:legs"})
    ).declared == {"hold", "sustain_ms", "concurrent"}
    assert ExecutionCapabilities(hold="stream", hold_controls=frozenset({"x"})).declared == {
        "hold",
        "hold_controls",
    }


def test_a_scoped_hold_admits_only_its_controls() -> None:
    scoped = ExecutionCapabilities(hold="stream", hold_controls=frozenset({"held"}))
    assert scoped.hold_for("held") == "stream"
    assert scoped.hold_for("gesture") is None
    # A motor route is outside every control scope.
    assert scoped.hold_for() is None
    whole = ExecutionCapabilities(hold="latched")
    assert whole.hold_for("any") == whole.hold_for() == "latched"
    assert NO_EXECUTION_CAPABILITIES.hold_for("any") is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hold": "pulsed"},
        {"sustain_ms": 200},
        {"hold": "stream", "sustain_ms": 0},
        {"concurrent": frozenset({"motor:back"})},
        {"concurrent": frozenset({"motor:back", ""})},
        {"hold_controls": frozenset({"held"})},
        {"hold": "stream", "hold_controls": frozenset()},
        {"hold": "stream", "hold_controls": frozenset({""})},
    ],
)
def test_invalid_declarations_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ExecutionCapabilities(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("selector", ("KSBT03CK", "KSBT03CL"))
async def test_kingkoil_stream_is_one_control_without_invented_release(selector: str) -> None:
    # King Koil Bed1.0 E-TIME: immediate Timer300ms; both UP/CANCEL paths
    # cancel refresh only. No merged keys, speed or sustain interval is proven.
    controller = await _create_controller_for_bed_type("kingkoil", selector)
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("head_up") == "stream"
    assert controller.profile.release.steps == ()
    assert controller.profile.refresh_ms == 300


async def test_scott_living_refresh_has_no_release_or_composed_keys():
    # Scott Living 1.0.2 ControlManager: fixed-delay100ms, UP/CANCEL ends
    # the shared scheduler without a BLE release. No sustain/merged key proof.
    from custom_components.adjustable_bed.profiles.scott_living import LAYOUTS, profile

    for layout in LAYOUTS:
        controller = await _create_controller_for_bed_type("scott_living")
        controller.profile = profile(layout)
        assert controller.execution.declared == {"hold"}
        assert controller.execution.hold_for("head_up") == "stream"
