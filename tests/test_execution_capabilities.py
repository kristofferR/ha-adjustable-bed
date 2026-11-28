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


async def test_ifit_screen_hold_is_scoped_to_refresh_controls():
    # iFit 1.1 (3) LongOnce/LongPress/LongMemory/LongSwitch stop their timer
    # on UP/CANCEL. Direct voice MAX/STOP bursts are not renewable holds.
    controller = await _create_controller_for_bed_type('ifit')
    assert controller.execution.declared == {'hold', 'hold_controls'}
    assert controller.execution.hold_for('head_up') == 'stream'
    assert controller.execution.hold_for('light_massage') == 'stream'
    assert controller.execution.hold_for('head_up_max') is None
    assert controller.execution.concurrent == frozenset()


async def test_ghostbed_hold_uses_current_two_axis_route() -> None:
    """GhostBed 1.3 (4): immediate movement, 200 ms refresh, axis release after 100 ms."""
    controller = await _create_controller_for_bed_type("ghostbed")
    assert controller.execution.declared == {"hold"}
    assert controller.held_control_options == ("back_up", "back_down", "feet_up", "feet_down")
    assert (controller.refresh_ms, controller.release_ms) == (200, 100)


@pytest.mark.parametrize("route", ("15_22_15a", "24_xx_xx"))
async def test_meisemobell_held_execution(route):
    # com.okin.meisemobell 1.2.8 E4/E5: immediate plus 300ms refresh,
    # release/cancel sends STOP immediately and at 100ms. One global timer.
    controller = await _create_controller_for_bed_type("meisemobell", route)
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("head_up") == "stream"
    assert controller.profile.hold.release_ms == 100
    assert controller.commands_share_timer


async def test_hestia_one_held_key_stream_has_no_composed_motor_admission():
    # Hestia Motion 1.2 (3), accepted E07: one Handler key, post0/repost100ms,
    # ACTION_UP sends zero after100ms. Combined05/0A is an explicit control,
    # not proof of independent concurrent holds or a hardware sustain interval.
    controller = await _create_controller_for_bed_type("hestia_motion")
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("both_up") == "stream"
    assert controller.profile.refresh_ms == 100
    assert controller.profile.release.steps == ((100, 0),)


@pytest.mark.parametrize("layout", ("2", "3", "4"))
async def test_konfurt_one_300ms_held_key_with_delayed_release(layout):
    # KONFURT1.0 E-TIMING: one runnable at0/300ms; UP/CANCEL schedules
    # zero-word STOP at300/600ms. No sustain or composed-key evidence.
    controller = await _create_controller_for_bed_type("konfurt", layout)
    assert controller.execution.declared == {"hold"}
    assert controller.profile.refresh_ms == 300
    assert tuple(delay for delay, _ in controller.profile.release.steps) == (300, 300)


def test_innova_control_hold_scope_has_artifact_refresh_and_release():
    # Innova Control 1.1.0 Utils sender mode1 + RemoteFragment UP: repeat,
    # then mode0's 50ms existing STOP. Modes never establish physical sides.
    from tests.test_innova_control import controller

    ctrl, _ = controller()
    assert ctrl.execution.hold_for("richmat_classic_1") == "stream"
    assert ctrl.execution.concurrent == frozenset()
    assert ctrl.app_profile.held_release_ms == 50
    assert not ctrl.supports_single_address_pairing


@pytest.mark.parametrize("product", ("JLRN", "VJRM"))
async def test_purely_sleep_normal_axes_declare_only_the_verified_stream_hold(product):
    # Purely Sleep 2.0.1 E49/E53/E55/E56: actual normal motorList ->
    # sustainPress widgets -> Timer100000us -> FIFO release OP6e on UP/CANCEL.
    # This proves no merged simultaneous commands, motor speed, or V1 menu.
    controller = await _create_controller_for_bed_type("purely_sleep", product)
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for() == "stream"
    assert controller.profile.motor_repeat_ms == 100


async def test_thrivesleep_current_motor_refresh_and_release_are_serialized():
    # Thrive Sleep 1.1.2: held widget Timer.periodic100ms; UP/CANCEL invokes
    # STOP through the FIFO. No concurrent/composed command or sustain proof.
    controller = await _create_controller_for_bed_type("thrivesleep", "level5")
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("head_up") == "stream"
    assert controller.profile.execution.concurrent == frozenset()
    assert controller.motor_pulse_settings()[1] == 100


async def test_powersbedding_single_timer_movement_stream():
    # PowersBedding 1.1.0 (2), E5: one movement timer, 100 ms refresh,
    # two zero releases 100 ms apart; no independent concurrent axis holds.
    controller = await _create_controller_for_bed_type("powersbedding")
    assert controller.execution.declared == {"hold"}
    assert controller.execution.hold_for("both_up") == "stream"
    assert controller.profile.release.steps == ((0, 0), (100, 0))
