"""Calibrated travel-time estimates and saved positions (#601)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.base import ControllerMotorHoldSpec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.position_estimate import (
    EstimateReason,
    EstimateState,
    MotorEstimate,
)

LEFT = "AA:BB:CC:DD:EE:01"
RIGHT = "AA:BB:CC:DD:EE:02"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(pe, "_clock", clock)
    return clock


def controller(hass: HomeAssistant, address: str, entry_id: str = "entry") -> Any:
    """A controller whose physical coordinator resolves to an estimate."""
    held = ControllerMotorHoldSpec(up_control="back_up", down_control="back_down")
    return SimpleNamespace(
        _coordinator=SimpleNamespace(
            hass=hass, entry=SimpleNamespace(entry_id=entry_id), address=address
        ),
        estimated_position_motor_groups={
            "back": ("back",),
            "legs": ("legs",),
            "back_legs": ("back", "legs"),
            "pillow": (),
        },
        motor_control_specs=(SimpleNamespace(key="back", hold=held),),
    )


async def calibrated(
    hass: HomeAssistant,
    beds: tuple[tuple[str, str | None], ...] = ((LEFT, None),),
) -> pe.PositionEstimates:
    manager = await pe.async_setup_position_estimates(hass, "entry", beds)
    for bed in manager.beds.values():
        bed.configure({"back": (20.0, 10.0), "legs": (10.0, 8.0)})
        bed.set_reference()
    return manager


def moving(clock: Clock, seconds: float, error: BaseException | None = None) -> Callable:
    async def command(_controller: object) -> None:
        clock.now += seconds
        if error is not None:
            raise error

    return command


def test_travel_uses_separate_raise_and_lower_times() -> None:
    estimate = MotorEstimate(up_s=20.0, down_s=10.0, percent=0.0, confirmed=True)
    estimate.travel("up", 5.0)
    assert estimate.percent == 25.0
    estimate.travel("down", 1.0)
    assert estimate.percent == 15.0
    estimate.travel("up", 60.0)
    assert estimate.percent == 100.0
    estimate.travel("down", 60.0)
    assert estimate.percent == 0.0
    assert estimate.moves_since_reference == 4


def test_plan_converts_the_distance_with_its_direction_time() -> None:
    estimate = MotorEstimate(up_s=20.0, down_s=10.0, percent=40.0, confirmed=True)
    assert estimate.plan(60.0) == ("up", 4.0)
    assert estimate.plan(10.0) == ("down", 3.0)
    assert estimate.plan(40.0) is None
    assert MotorEstimate(up_s=20.0, down_s=10.0).plan(50.0) is None


def test_states() -> None:
    assert MotorEstimate().state is EstimateState.NOT_CALIBRATED
    assert MotorEstimate(up_s=1.0, down_s=1.0).state is EstimateState.UNKNOWN
    assert MotorEstimate(up_s=1.0, down_s=1.0, percent=5.0).state is EstimateState.UNCONFIRMED
    tracking = MotorEstimate(up_s=1.0, down_s=1.0, percent=5.0, confirmed=True)
    assert tracking.state is EstimateState.TRACKING


async def test_tracked_moves_follow_direction_and_combined_motors(
    hass: HomeAssistant, clock: Clock
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    ctrl = controller(hass, LEFT)

    await pe.track_motor_command(hass, "back", "up", moving(clock, 5.0))(ctrl)
    await pe.track_motor_command(hass, "back_legs", "up", moving(clock, 2.0))(ctrl)
    await pe.track_motor_command(hass, "back", "down", moving(clock, 1.0))(ctrl)

    assert bed.motors["back"].percent == pytest.approx(25.0 + 10.0 - 10.0)
    assert bed.motors["legs"].percent == pytest.approx(20.0)
    assert bed.tracking(["back", "legs"])


async def test_swallowed_release_failure_is_not_travel(hass: HomeAssistant, clock: Clock) -> None:
    """A Richmat quiet release logs a failed STOP; the estimate must not trust it."""
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.beds.richmat.controller import RichmatController

    manager = await calibrated(hass)
    ctrl = controller(hass, LEFT)
    richmat = MagicMock(spec=RichmatController)
    richmat._coordinator = ctrl._coordinator
    richmat.profile = SimpleNamespace(quiet_release=True)
    richmat._send_stop = AsyncMock(side_effect=BleakError("stop lost"))

    async def pulse_then_release(_controller: object) -> None:
        clock.now += 2.0
        await RichmatController._release(richmat)

    await pe.track_motor_command(hass, "back", "up", pulse_then_release)(ctrl)
    back = manager.beds[LEFT].motors["back"]
    assert back.state is EstimateState.UNKNOWN
    assert back.reason is EstimateReason.FAILED_MOVE


async def test_stop_mid_move_keeps_tracking_at_the_stop_time(
    hass: HomeAssistant, clock: Clock
) -> None:
    manager = await calibrated(hass)
    command = pe.track_motor_command(
        hass, "back", "up", moving(clock, 4.0, asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        await command(controller(hass, LEFT))
    back = manager.beds[LEFT].motors["back"]
    assert back.state is EstimateState.TRACKING
    assert back.percent == pytest.approx(20.0)


async def test_failed_write_is_never_reported_as_travel(hass: HomeAssistant, clock: Clock) -> None:
    manager = await calibrated(hass)
    command = pe.track_motor_command(hass, "back", "up", moving(clock, 4.0, BleakError("lost")))
    with pytest.raises(BleakError):
        await command(controller(hass, LEFT))
    back = manager.beds[LEFT].motors["back"]
    assert back.state is EstimateState.UNKNOWN
    assert back.reason is EstimateReason.FAILED_MOVE
    # The legs did not move and stay tracking.
    assert manager.beds[LEFT].motors["legs"].state is EstimateState.TRACKING


async def test_connection_loss_mid_move_makes_it_unknown(hass: HomeAssistant, clock: Clock) -> None:
    manager = await calibrated(hass)
    ctrl = controller(hass, LEFT)

    async def dropped(_controller: object) -> None:
        clock.now += 3.0
        pe.notify_connection_lost(ctrl._coordinator)

    await pe.track_motor_command(hass, "back", "up", dropped)(ctrl)
    back = manager.beds[LEFT].motors["back"]
    assert back.state is EstimateState.UNKNOWN
    assert back.reason is EstimateReason.CONNECTION_LOST
    # A disconnect while idle changes nothing.
    pe.notify_connection_lost(ctrl._coordinator)
    assert manager.beds[LEFT].motors["legs"].state is EstimateState.TRACKING


async def test_reference_set_during_a_move_is_not_shifted(
    hass: HomeAssistant, clock: Clock
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]

    async def referenced(_controller: object) -> None:
        clock.now += 4.0
        bed.set_reference(["back"])

    await pe.track_motor_command(hass, "back", "up", referenced)(controller(hass, LEFT))
    assert bed.motors["back"].percent == 0.0


async def test_hardware_presets_and_untracked_controls_invalidate(
    hass: HomeAssistant, clock: Clock
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    ctrl = controller(hass, LEFT)
    preset = AsyncMock()

    await pe.invalidate_on_command(hass, preset)(ctrl)
    preset.assert_awaited_once_with(ctrl)
    assert bed.motors["back"].reason is EstimateReason.HARDWARE_PRESET
    assert bed.motors["legs"].state is EstimateState.UNKNOWN

    bed.set_reference()
    await pe.track_held_control(hass, "memory_1", AsyncMock())(ctrl)
    assert bed.motors["back"].reason is EstimateReason.HARDWARE_PRESET

    bed.set_reference()
    await pe.track_motor_command(hass, "tilt", "up", AsyncMock())(ctrl)
    assert bed.motors["back"].reason is EstimateReason.UNTRACKED_MOVE

    # An independent actuator leaves the estimates alone.
    bed.set_reference()
    await pe.track_motor_command(hass, "pillow", "up", AsyncMock())(ctrl)
    assert bed.tracking(["back", "legs"])


async def test_held_motor_control_is_tracked(hass: HomeAssistant, clock: Clock) -> None:
    manager = await calibrated(hass)
    await pe.track_held_control(hass, "back_down", moving(clock, 1.0))(controller(hass, LEFT))
    # From flat, lowering clamps at 0% and keeps tracking.
    assert manager.beds[LEFT].motors["back"].state is EstimateState.TRACKING
    await pe.track_held_control(hass, "back_up", moving(clock, 2.0))(controller(hass, LEFT))
    assert manager.beds[LEFT].motors["back"].percent == pytest.approx(10.0)


async def test_unknown_or_unconfirmed_moves_never_become_tracking(
    hass: HomeAssistant, clock: Clock
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    bed.invalidate(EstimateReason.REMOTE, ["back"])
    await pe.track_motor_command(hass, "back", "down", moving(clock, 60.0))(controller(hass, LEFT))
    # Elapsed time alone never proves arrival at flat.
    assert bed.motors["back"].state is EstimateState.UNKNOWN


async def test_paired_sides_are_estimated_independently(hass: HomeAssistant, clock: Clock) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    shared = pe.track_motor_command(hass, "back", "up", moving(clock, 2.0))
    await shared(controller(hass, LEFT))
    manager.beds[RIGHT].configure({"back": (10.0, 10.0), "legs": (10.0, 8.0)})
    await shared(controller(hass, RIGHT))
    assert manager.beds[LEFT].motors["back"].percent == pytest.approx(10.0)
    assert manager.beds[RIGHT].motors["back"].percent == pytest.approx(20.0)
    manager.beds[RIGHT].invalidate(EstimateReason.REMOTE)
    assert manager.beds[LEFT].tracking(["back", "legs"])


async def test_wrappers_are_untouched_without_estimates(hass: HomeAssistant) -> None:
    command = AsyncMock()
    assert pe.track_motor_command(hass, "back", "up", command) is command
    assert pe.track_held_control(hass, "back_up", command) is command
    assert pe.invalidate_on_command(hass, command) is command
    assert pe.track_motor_command(None, "back", "up", command) is command


async def test_restart_restores_an_unconfirmed_estimate(
    hass: HomeAssistant, hass_storage: dict[str, Any], clock: Clock
) -> None:
    manager = await calibrated(hass)
    await pe.track_motor_command(hass, "back", "up", moving(clock, 8.4))(controller(hass, LEFT))
    await manager._store.async_save(manager._data_to_save())
    pe._registry(hass).clear()

    restored = await pe.async_setup_position_estimates(hass, "entry", ((LEFT, None),))
    back = restored.beds[LEFT].motors["back"]
    assert back.state is EstimateState.UNCONFIRMED
    assert back.reason is EstimateReason.RESTART
    assert back.percent == pytest.approx(42.0)
    assert (back.up_s, back.down_s) == (20.0, 10.0)
    with pytest.raises(ServiceValidationError):
        restored.save_position("Reading", restored.beds.values(), button=False)

    restored.beds[LEFT].confirm_unchanged()
    assert restored.beds[LEFT].tracking(["back", "legs"])


async def test_entry_reload_keeps_confirmation(hass: HomeAssistant) -> None:
    await calibrated(hass)
    await pe.async_unload_position_estimates(hass, "entry")
    reloaded = await pe.async_setup_position_estimates(hass, "entry", ((LEFT, None),))
    assert reloaded.beds[LEFT].tracking(["back", "legs"])

    # A Home Assistant restart has no session, so it is unconfirmed again.
    await pe.async_unload_position_estimates(hass, "entry")
    hass.data[DOMAIN].pop(pe._SESSION_KEY)
    restarted = await pe.async_setup_position_estimates(hass, "entry", ((LEFT, None),))
    assert restarted.beds[LEFT].state("back") is EstimateState.UNCONFIRMED


async def test_saved_positions_lifecycle(hass: HomeAssistant, clock: Clock) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    bed.motors["back"].percent = 42.0
    position = manager.save_position("  Reading ", [bed], button=True)
    assert (position.name, position.targets) == ("Reading", {"bed": {"back": 42.0, "legs": 0.0}})
    with pytest.raises(ServiceValidationError):
        manager.save_position("reading", [bed], button=False)
    assert manager.position("READING") is position
    assert manager.position(position.id) is position

    manager.rename_position(position, "Read", button=False)
    bed.motors["legs"].percent = 20.0
    manager.update_position(position)
    assert (position.name, position.button) == ("Read", False)
    assert position.targets == {"bed": {"back": 42.0, "legs": 20.0}}

    manager.delete_position(position)
    with pytest.raises(ServiceValidationError):
        manager.position("Read")


async def test_recall_moves_each_motor_for_its_calculated_time(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    bed.motors["legs"].percent = 50.0
    position = pe.SavedPosition("p1", "Reading", True, {"bed": {"back": 30.0, "legs": 25.0}})
    hass.data[DOMAIN]["entry"] = parent = object()
    moves: list[tuple[str, str, int]] = []

    async def timed_move(targets, motor, direction, duration_ms) -> None:
        assert targets == [(parent, "both")]
        moves.append((motor, direction, duration_ms))
        bed.motors[motor].travel(direction, duration_ms / 1000)

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    await pe.async_recall_position(hass, manager, position)
    assert moves == [("back", "up", 6000), ("legs", "down", 2000)]
    assert bed.motors["back"].percent == pytest.approx(30.0)


async def test_recall_reports_a_stopped_move_and_skips_the_rest(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    position = pe.SavedPosition("p1", "TV", True, {"bed": {"back": 60.0, "legs": 50.0}})
    hass.data[DOMAIN]["entry"] = object()
    moves: list[str] = []

    async def stopped(_targets, motor, direction, duration_ms) -> None:
        moves.append(motor)
        bed.motors[motor].travel(direction, duration_ms / 2000)

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", stopped)
    with pytest.raises(HomeAssistantError) as err:
        await pe.async_recall_position(hass, manager, position)
    assert err.value.translation_key == "saved_position_not_reached"
    assert moves == ["back"]
    assert bed.motors["back"].state is EstimateState.TRACKING


async def test_both_sides_recall_is_blocked_while_one_side_is_unknown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    both = manager.save_position("Reading", manager.beds.values(), button=True)
    left_only = manager.save_position("Snore", [manager.beds[LEFT]], button=False)
    assert set(both.targets) == {"left", "right"}
    assert set(left_only.targets) == {"left"}
    manager.beds[RIGHT].invalidate(EstimateReason.REMOTE)
    timed_move = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    hass.data[DOMAIN]["entry"] = object()

    with pytest.raises(ServiceValidationError) as err:
        await pe.async_recall_position(hass, manager, both)
    assert err.value.translation_key == "position_estimate_not_tracking"
    timed_move.assert_not_awaited()
    # A left-only position still works; it is already there, so nothing moves.
    await pe.async_recall_position(hass, manager, left_only)
    timed_move.assert_not_awaited()


async def test_lower_to_flat_runs_past_full_travel_and_keeps_unknown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    bed.invalidate(EstimateReason.REMOTE)
    hass.data[DOMAIN]["entry"] = object()
    timed_move = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    await pe.async_lower_to_flat(hass, manager, [bed], ["legs"])
    assert [call.args[1:] for call in timed_move.await_args_list] == [("legs", "down", 10600)]
    assert bed.state("legs") is EstimateState.UNKNOWN


def test_octo_and_richmat_declare_their_estimated_motors() -> None:
    from custom_components.adjustable_bed.beds.base import BedController
    from custom_components.adjustable_bed.beds.octo.controller import OctoController
    from custom_components.adjustable_bed.beds.richmat.controller import RichmatController
    from custom_components.adjustable_bed.beds.rmcontrol.controller import RmcontrolController

    def groups(cls: type[BedController], keys: tuple[str, ...]) -> object:
        stub = SimpleNamespace(motor_control_specs=tuple(SimpleNamespace(key=k) for k in keys))
        prop = cls.estimated_position_motor_groups
        assert isinstance(prop, property) and prop.fget is not None
        return prop.fget(stub)

    assert groups(OctoController, ("tv_lift",)) == {"tv_lift": ("tv_lift",)}
    assert groups(OctoController, ("back", "legs", "back_legs")) == {
        "back": ("back",),
        "legs": ("legs",),
        "back_legs": ("back", "legs"),
    }
    assert groups(RichmatController, ("head", "feet", "head_feet", "pillow")) == {
        "head": ("head",),
        "feet": ("feet",),
        "head_feet": ("head", "feet"),
        "pillow": (),
    }
    assert groups(RmcontrolController, ("head", "feet")) == {}
    assert groups(BedController, ("back", "legs")) == {}


async def test_recall_refuses_while_a_tracked_move_runs(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan from an unsettled estimate would be wrong; nothing moves."""
    manager = await calibrated(hass)
    bed = manager.beds[LEFT]
    hass.data[DOMAIN]["entry"] = object()
    bed.begin_move(("back",))
    timed_move = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    with pytest.raises(ServiceValidationError) as err:
        await pe.async_move_bed(hass, manager, bed, {"back": 50.0})
    assert err.value.translation_key == "position_estimate_moving"
    timed_move.assert_not_awaited()


async def test_a_side_left_unknown_stops_the_other_side(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    position = manager.save_position("Reading", manager.beds.values(), button=False)
    for bed in manager.beds.values():
        bed.motors["back"].percent = 50.0
    hass.data[DOMAIN]["entry"] = object()
    stopped: list[str | None] = []

    async def timed_move(targets, motor, _direction, _ms) -> None:
        if targets[0][1] == "left":
            # A swallowed release failure: no exception, but the estimate is unknown.
            manager.beds[LEFT].invalidate(EstimateReason.FAILED_MOVE, [motor])
            return
        await asyncio.Event().wait()

    async def stop(_hass: object, _manager: object, bed: pe.BedEstimate) -> None:
        stopped.append(bed.side)

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    monkeypatch.setattr(pe, "async_stop_bed", stop)
    with pytest.raises(HomeAssistantError) as err:
        await pe.async_recall_position(hass, manager, position)
    assert err.value.translation_key == "position_estimate_move_failed"
    assert stopped == ["right"]


async def test_cancelling_a_recall_drains_every_side(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    position = manager.save_position("Reading", manager.beds.values(), button=False)
    for bed in manager.beds.values():
        bed.motors["back"].percent = 50.0
    hass.data[DOMAIN]["entry"] = object()
    cleaned: list[str] = []
    started = asyncio.Event()

    async def timed_move(targets, _motor, _direction, _ms) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.append(targets[0][1])

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    recall = asyncio.create_task(pe.async_recall_position(hass, manager, position))
    await started.wait()
    recall.cancel()
    with pytest.raises(asyncio.CancelledError):
        await recall
    assert sorted(cleaned) == ["left", "right"]


async def test_a_failed_side_stops_the_other_side(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    position = manager.save_position("Reading", manager.beds.values(), button=False)
    for bed in manager.beds.values():
        bed.motors["back"].percent = 50.0
    hass.data[DOMAIN]["entry"] = object()
    stopped: list[str | None] = []

    async def timed_move(targets, _motor, _direction, _ms) -> None:
        if targets[0][1] == "left":
            raise BleakError("write failed")
        await asyncio.Event().wait()

    async def stop(_hass: object, _manager: object, bed: pe.BedEstimate) -> None:
        stopped.append(bed.side)

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    monkeypatch.setattr(pe, "async_stop_bed", stop)
    with pytest.raises(BleakError):
        await pe.async_recall_position(hass, manager, position)
    assert stopped == ["right"]


async def test_stop_during_lower_both_ends_the_whole_request(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await calibrated(hass, ((LEFT, "left"), (RIGHT, "right")))
    parent = SimpleNamespace(_command_scheduler=SimpleNamespace(stop_epoch=0))
    hass.data[DOMAIN]["entry"] = parent
    moved: list[str] = []

    async def timed_move(targets, motor, _direction, _ms) -> None:
        moved.append(f"{targets[0][1]}:{motor}")
        parent._command_scheduler.stop_epoch += 1  # the user pressed STOP

    monkeypatch.setattr("custom_components.adjustable_bed.services._async_timed_move", timed_move)
    await pe.async_lower_to_flat(hass, manager, manager.beds.values())
    assert moved == ["left:back"]
