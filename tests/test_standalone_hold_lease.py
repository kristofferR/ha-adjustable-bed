"""Renewable holds (#483) on standalone controllers with stream evidence.

Under a lease each controller streams its own held frame at its app's refresh
until the lease ends or STOP preempts it; either sets the command's cancel
event. Then the controller's own release follows. Lease renewal, expiry,
staleness and STOP ordering are the scheduler's and are covered by
``test_hold_lease.py`` and ``test_hold_lease_service.py``; here each controller
proves its side: an open-ended stream at its cadence and its release.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds import vmatbasic_protocol
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.eshine_protocol import control_frame
from custom_components.adjustable_bed.beds.jensen import JensenCommands, JensenController
from custom_components.adjustable_bed.beds.leggett_gen2 import (
    LeggettGen2Commands,
    LeggettGen2Controller,
)
from custom_components.adjustable_bed.beds.linak import LinakCommands, LinakController
from custom_components.adjustable_bed.beds.linak_protocol import LinakProfile
from custom_components.adjustable_bed.beds.octo import (
    OCTO_MOTOR_HEAD,
    OCTO_PROTOCOL_HOLD_INTERVAL_MS,
    OctoController,
)
from custom_components.adjustable_bed.beds.starcode_m1x12 import StarcodeM1X12Controller
from custom_components.adjustable_bed.beds.timotion_ahf import build_timotion_ahf_command
from custom_components.adjustable_bed.beds.vibradorm_app import MOTORS as VIBRADORM_APP_MOTORS
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
    HoldLease,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ESHINE,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
)
from custom_components.adjustable_bed.execution import MAX_HOLD_MS
from tests.test_controller_contract import _create_controller_for_bed_type
from tests.test_eshine import make as make_eshine
from tests.test_furnimove import make_controller as make_furnimove
from tests.test_sleepys_elite_app import _controller as sleepys_controller
from tests.test_starcode_m5x5 import controller_stop as m5x5_stop
from tests.test_starcode_m5x5 import make_controller as make_m5x5
from tests.test_timotion_ahf import controller_for as timotion_controller
from tests.test_vibradorm_app import make_controller as make_vibradorm_app
from tests.test_vmatbasic import make_controller as make_vmatbasic

DECLARED = (
    BED_TYPE_ESHINE,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
)


@pytest.mark.parametrize("bed_type", DECLARED)
async def test_standalone_controllers_declare_a_stream_hold(bed_type: str) -> None:
    controller = await _create_controller_for_bed_type(bed_type)
    assert controller.execution.hold == "stream"


async def test_the_generic_vibradorm_route_keeps_finite_pulses() -> None:
    controller = await _create_controller_for_bed_type(BED_TYPE_VIBRADORM)
    assert controller.execution.hold is None


@contextlib.contextmanager
def _leased(cancel: asyncio.Event) -> Iterator[None]:
    """Run as the scheduler runs a renewable hold."""
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="hold",
        kind=CommandKind.HOLD,
        group_id=None,
        resources=frozenset({"*"}),
        lease=HoldLease(owner="card", generation=1, action="up", duration_s=0.75),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


@dataclass(frozen=True)
class Case:
    """One controller: how to build it, hold it, and recognize its frames."""

    build: Callable[[HomeAssistant], BedController]
    hold: Callable[[BedController], Awaitable[None]]
    held: Callable[[BedController], bytes]
    release: Callable[[BedController], bytes]
    refresh_ms: int
    prepare: Callable[[BedController], Awaitable[None]] | None = None


def _recorded(controller: BedController) -> list[bytes]:
    if (frames := getattr(controller, "_lease_frames", None)) is not None:
        return list(frames)
    client = controller._coordinator.client  # type: ignore[attr-defined]
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


def _plain_coordinator(hass: HomeAssistant, *, pulses: tuple[int, int] = (3, 50)) -> MagicMock:
    """A runtime whose finite pulses end well before one second."""
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.address = "AA:BB:CC:DD:EE:83"
    coordinator.motor_count = 2
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count, coordinator.motor_pulse_delay_ms = pulses
    coordinator.client = MagicMock(is_connected=True)
    coordinator.client.write_gatt_char = AsyncMock()
    return coordinator


def _linak(profile: LinakProfile) -> Callable[[HomeAssistant], BedController]:
    def build(hass: HomeAssistant) -> BedController:
        controller = LinakController(_plain_coordinator(hass), profile=profile)
        controller._await_control_ready = AsyncMock()  # type: ignore[method-assign]
        return controller

    return build


def _jensen(hass: HomeAssistant) -> BedController:
    coordinator = _plain_coordinator(hass)
    coordinator.disable_angle_sensing = True
    return JensenController(coordinator)


def _gen2(hass: HomeAssistant) -> BedController:
    return LeggettGen2Controller(_plain_coordinator(hass))


def _record_commands(controller: BedController) -> BedController:
    """Record write_command frames, honoring its repeat cadence and cancel event."""
    frames: list[bytes] = []

    async def write_command(
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        cancel = cancel_event or controller._coordinator.cancel_command  # type: ignore[attr-defined]
        for index in range(repeat_count):
            if index:
                await asyncio.sleep(repeat_delay_ms / 1000)
            if cancel.is_set():
                return
            frames.append(bytes(command))

    controller._lease_frames = frames  # type: ignore[attr-defined]
    controller.write_command = write_command  # type: ignore[method-assign]
    return controller


def _octo(hass: HomeAssistant) -> BedController:
    coordinator = _plain_coordinator(hass)
    coordinator.entry.data = {}
    controller = OctoController(coordinator)
    controller._session_ready = True
    return _record_commands(controller)


def _timotion(hass: HomeAssistant) -> BedController:
    controller, _runtime = timotion_controller()
    controller._status_ready = True
    controller._feature_mask = 0
    return _record_commands(controller)


async def _furnimove_ready(controller: BedController) -> None:
    await controller.async_discover_capabilities()  # type: ignore[attr-defined]
    _record_commands(controller)


def _m1x12(hass: HomeAssistant) -> BedController:
    coordinator = _plain_coordinator(hass)
    coordinator.name = "M1X12"
    controller = StarcodeM1X12Controller(coordinator, profile="cb25")
    controller._ready = True
    controller._interrupt_group = AsyncMock()  # type: ignore[method-assign]
    return controller


def _sleepys(hass: HomeAssistant) -> BedController:
    controller = sleepys_controller("BOX15", connected=True)
    builders: list[bytes] = []

    async def write_route(route, **_kwargs) -> None:
        await asyncio.sleep(0)
        builders.append(route.builder.encode())

    controller._lease_frames = builders  # type: ignore[attr-defined]
    controller._write_route = write_route  # type: ignore[method-assign]
    return controller


def _m5x5(hass: HomeAssistant) -> BedController:
    controller = make_m5x5(hass)
    controller._coordinator.client.write_gatt_char = AsyncMock()  # type: ignore[attr-defined]
    return controller


async def _eshine_ready(controller: BedController) -> None:
    await controller.async_discover_capabilities()
    await controller.start_notify()


def _plan(controller: BedController) -> None:
    """Hand the controller the pulses a leased timed move plans, as services do."""
    coordinator = controller._coordinator  # type: ignore[attr-defined]
    if not isinstance(getattr(coordinator, "motor_pulse_count", None), int):
        coordinator.motor_pulse_count, coordinator.motor_pulse_delay_ms = 3, 50
    _, delay = controller.motor_pulse_settings()
    coordinator.motor_pulse_count = controller.timed_move_repeat_count(MAX_HOLD_MS, delay)
    coordinator.motor_pulse_delay_ms = delay


CASES: dict[str, Case] = {
    "octo": Case(
        _octo,
        lambda c: c.hold_control("back_up", MAX_HOLD_MS),  # type: ignore[attr-defined]
        lambda c: c._build_packet([0x02, 0x70], [OCTO_MOTOR_HEAD]),  # type: ignore[attr-defined]
        lambda c: c._build_packet([0x02, 0x73], None),  # type: ignore[attr-defined]
        OCTO_PROTOCOL_HOLD_INTERVAL_MS,
    ),
    "timotion_ahf": Case(
        _timotion,
        lambda c: c.move_back_up(),
        lambda c: build_timotion_ahf_command(0x01),
        lambda c: build_timotion_ahf_command(),
        100,
    ),
    "furnimove": Case(
        lambda hass: make_furnimove(),
        lambda c: c.move_back_up(),
        lambda c: c._lease_frames[0],  # type: ignore[attr-defined]
        # The handset's zero key, from its release schedule.
        lambda c: bytes.fromhex("040200000000"),
        100,
        _furnimove_ready,
    ),
    "starcode_m1x12": Case(
        _m1x12,
        lambda c: c.hold_control("part_1_up", MAX_HOLD_MS),  # type: ignore[attr-defined]
        lambda c: c._normal("part_1_up"),  # type: ignore[attr-defined]
        lambda c: c._normal("stop"),  # type: ignore[attr-defined]
        100,
    ),
    "sleepys_elite_app": Case(
        _sleepys,
        lambda c: c.hold_control(c.held_control_options[0], MAX_HOLD_MS),  # type: ignore[attr-defined]
        lambda c: c._route(c.held_control_options[0]).builder.encode(),  # type: ignore[attr-defined]
        lambda c: b"stop",
        100,
    ),
    "linak_bed_control": Case(
        _linak(LinakProfile.BED_CONTROL),
        lambda c: c.move_back_up(),
        lambda c: LinakCommands.MOVE_BACK_UP,
        lambda c: LinakCommands.MOVE_STOP,
        100,
    ),
    "linak_performance": Case(
        _linak(LinakProfile.PERFORMANCE),
        lambda c: c.move_back_up(),
        lambda c: LinakCommands.MOVE_BACK_UP,
        lambda c: LinakCommands.PERFORMANCE_RELEASE,
        300,
    ),
    "jensen": Case(
        _jensen,
        lambda c: c.move_head_up(),
        lambda c: JensenCommands.MOTOR_HEAD_UP,
        lambda c: JensenCommands.MOTOR_STOP,
        300,
    ),
    "leggett_gen2": Case(
        _gen2,
        lambda c: c.move_head_up(),
        lambda c: LeggettGen2Commands.MOTOR_HEAD_UP,
        lambda c: LeggettGen2Commands.MOTOR_HEAD_STOP,
        200,
    ),
    "eshine": Case(
        lambda hass: make_eshine(),
        lambda c: c.hold_control("head_up", MAX_HOLD_MS),  # type: ignore[attr-defined]
        lambda c: control_frame("head_up", c._compact),  # type: ignore[attr-defined]
        lambda c: control_frame("stop", c._compact),  # type: ignore[attr-defined]
        100,
        _eshine_ready,
    ),
    "starcode_m5x5": Case(
        _m5x5,
        lambda c: c.move_head_up(),
        lambda c: c.packet("head_up"),  # type: ignore[attr-defined]
        m5x5_stop,  # type: ignore[arg-type]
        100,
    ),
    "vibradorm_app": Case(
        lambda hass: make_vibradorm_app(),
        lambda c: c.move_back_up(),
        lambda c: bytes((VIBRADORM_APP_MOTORS["back_up"],)),
        lambda c: b"\xff",
        100,
    ),
    "vmatbasic": Case(
        lambda hass: make_vmatbasic(),
        lambda c: c.move_back_up(),
        lambda c: bytes((vmatbasic_protocol.MOTOR_ACTIONS["back_up"],)),
        lambda c: b"\xff",
        30,
    ),
}


@pytest.fixture(params=sorted(CASES))
def case(request: pytest.FixtureRequest) -> Case:
    return CASES[request.param]


async def test_a_lease_streams_past_a_finite_press_then_releases(
    hass: HomeAssistant, case: Case
) -> None:
    controller = case.build(hass)
    if case.prepare is not None:
        await case.prepare(controller)
        controller._coordinator.client.write_gatt_char.reset_mock()  # type: ignore[attr-defined]
    _plan(controller)
    cancel = controller._coordinator.cancel_command  # type: ignore[attr-defined]
    with _leased(cancel):
        task = asyncio.create_task(case.hold(controller))
    await asyncio.sleep(1.3)
    assert not task.done(), "a leased hold ended on its own"
    held = case.held(controller)
    streamed = _recorded(controller)
    assert set(streamed) == {held}
    # The app's own refresh paces the stream.
    assert len(streamed) >= 1.0 / (case.refresh_ms / 1000) * 0.7

    cancel.set()  # The lease ran out, or STOP preempted it.
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    tail = _recorded(controller)[len(streamed) :]
    assert tail and set(tail) == {case.release(controller)}


@pytest.mark.parametrize(
    "name",
    ["jensen", "linak_bed_control", "linak_performance", "timotion_ahf", "vibradorm_app", "vmatbasic"],
)
async def test_a_finite_press_still_ends_on_its_own(hass: HomeAssistant, name: str) -> None:
    """Without a lease the entry's pulses, or the one-second press, still apply."""
    case = CASES[name]
    controller = case.build(hass)
    await asyncio.wait_for(case.hold(controller), 2)
    frames = _recorded(controller)
    assert frames[0] == case.held(controller)
    assert frames[-1] == case.release(controller)
