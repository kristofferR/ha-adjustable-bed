"""Renewable ``timed_move`` and ``hold_control`` (#483) through the real coordinator."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.entity_specs import (
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from custom_components.adjustable_bed.position_estimate import EstimateState
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _ContractController

ADDRESS = "AA:BB:CC:DD:EE:42"
STREAM = ExecutionCapabilities(hold="stream")


class StreamController(_ContractController):
    """Streams the back motor's frame per pulse and releases in ``finally``."""

    def __init__(self, coordinator: AdjustableBedCoordinator, execution: ExecutionCapabilities):
        super().__init__(coordinator)  # type: ignore[arg-type]
        self._execution = execution
        self.frames: list[str] = []

    @property
    def execution(self) -> ExecutionCapabilities:
        return self._execution

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return ("back_up",)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        await self.write_command(b"up", repeat_count=duration_ms // 20 + 1, repeat_delay_ms=20)
        # Release always follows, as a family's held control does.

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        cancel = cancel_event or self._coordinator.cancel_command
        try:
            for index in range(repeat_count):
                if cancel.is_set():
                    return
                self.frames.append(command.decode())
                if index < repeat_count - 1:
                    await asyncio.sleep(repeat_delay_ms / 1000)
        finally:
            if command == b"up" and cancel_event is None:
                self.frames.append("stop")

    async def move_back_up(self) -> None:
        pulse_count, pulse_delay = self.motor_pulse_settings()
        await self.write_command(b"up", repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    async def move_back_stop(self) -> None:
        return None


@pytest.fixture
async def runtime(
    hass: HomeAssistant,
) -> AsyncIterator[tuple[HomeAssistant, AdjustableBedCoordinator]]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lease bed",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Lease bed",
            CONF_BED_TYPE: BED_TYPE_DEWERTOKIN,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_MOTOR_PULSE_COUNT: 3,
            CONF_MOTOR_PULSE_DELAY_MS: 20,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = AsyncMock()
    client.is_connected = True
    coordinator._client = client
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield hass, coordinator
    await coordinator.async_shutdown()


@pytest.fixture
async def clock(runtime) -> AsyncIterator[Any]:
    """Virtual time for the test body: lease, pulse and release timers are exact.

    Entered after ``runtime`` is set up, so Home Assistant itself starts on the
    real loop. Estimates read the same clock.
    """
    with virtual_clock() as fake, patch.object(pe, "_clock", fake.time):
        yield fake


def _install(coordinator: AdjustableBedCoordinator, execution: ExecutionCapabilities):
    controller = StreamController(coordinator, execution)
    coordinator._controller = controller
    return controller


async def _timed(hass: HomeAssistant, generation: int, duration_ms: int = 100) -> None:
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": ["bed"],
            "motor": "back",
            "direction": "up",
            "duration_ms": duration_ms,
            "hold_owner": "card",
            "hold_generation": generation,
        },
        blocking=True,
    )


async def test_renewals_keep_one_stream_alive_then_it_releases(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    began = clock.time()
    start = asyncio.create_task(_timed(hass, 1))
    for _ in range(5):
        await asyncio.sleep(0.05)
        frames = len(controller.frames)
        await asyncio.wait_for(_timed(hass, 1), 0.05)
        assert "stop" not in controller.frames[frames:]
        assert not start.done()
    await asyncio.wait_for(start, 2)

    # Five 50 ms renewals of a 100 ms lease outlived three 20 ms pulses: the
    # lease ends 100 ms after the last renewal (250 ms), and the next 20 ms
    # pulse sees it at 360 ms.
    assert clock.time() - began == pytest.approx(0.36)
    assert controller.frames == ["up"] * 18 + ["stop"]
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


async def test_late_renewal_after_stop_is_refused_without_motion(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    start = asyncio.create_task(_timed(hass, 7, duration_ms=5000))
    while "up" not in controller.frames:
        await asyncio.sleep(0.005)
    await coordinator.async_stop_command()
    await asyncio.wait_for(start, 1)
    frames = len(controller.frames)
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _timed(hass, 7)
    await asyncio.sleep(0.05)
    assert controller.frames[frames:] == []


async def test_controller_without_hold_rejects_a_lease(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, NO_EXECUTION_CAPABILITIES)
    with pytest.raises(ServiceValidationError, match="renewable holds"):
        await _timed(hass, 1)
    assert controller.frames == []
    # The refused start ended its generation; the next press uses a new one.
    controller._execution = STREAM
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _timed(hass, 1)
    await asyncio.wait_for(_timed(hass, 2, duration_ms=100), 2)
    assert controller.frames[0] == "up"


async def test_finite_timed_move_is_unchanged_without_an_owner(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {"device_id": ["bed"], "motor": "back", "direction": "up", "duration_ms": 200},
        blocking=True,
    )
    # The elapsed duration bounds the planned pulses; there is no lease and no HOLD.
    assert controller.frames == ["up"] * 11 + ["stop"]
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.COMMAND
    assert record.outcome is CommandOutcome.COMPLETED


async def test_hold_control_lease_renews_and_rejects_long_leases(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)

    async def hold(duration: float) -> None:
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": ["bed"],
                "control": "back_up",
                "duration": duration,
                "hold_owner": "card",
                "hold_generation": 3,
            },
            blocking=True,
        )

    with pytest.raises(ServiceValidationError, match="30000 ms"):
        await hold(45)
    began = clock.time()
    start = asyncio.create_task(hold(0.1))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(hold(0.1), 0.05)
    await asyncio.wait_for(start, 2)
    # Renewed at 50 ms, the lease ends at 150 ms; the 20 ms refresh sees it at 160 ms.
    assert clock.time() - began == pytest.approx(0.16)
    assert controller.frames == ["up"] * 8 + ["stop"]
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED


async def test_disconnect_ends_the_hold_and_refuses_renewal(runtime, clock) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    start = asyncio.create_task(_timed(hass, 2, duration_ms=5000))
    while "up" not in controller.frames:
        await asyncio.sleep(0.005)
    coordinator._on_disconnect(coordinator._client)
    await asyncio.wait_for(start, 1)
    assert controller.frames[-1] == "stop"
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _timed(hass, 2)


async def test_lease_inside_a_prepared_reservation_runs_and_expires(runtime, clock) -> None:
    """A paired group's side runs its held start inside the reservation."""
    from custom_components.adjustable_bed.command_scheduler import HoldLease

    _hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    held = HoldLease(owner="card", generation=1, action="up", duration_s=0.06)

    async def side() -> None:
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.move_back_up(),
            resource="motor:back",
            pulse_count=1000,
            pulse_delay_ms=20,
            lease=held,
        )

    handle = await coordinator.async_prepare_command_operation(
        side, resource="motor:back", group_id="pair"
    )
    await coordinator.async_wait_prepared_command(handle)
    coordinator.commit_prepared_command(handle)
    await asyncio.wait_for(coordinator.async_wait_prepared_command_result(handle), 2)
    assert handle.outcome is CommandOutcome.EXPIRED
    # Pulses at 0, 20 and 40 ms; the 60 ms lease ends before the fourth.
    assert controller.frames == ["up"] * 3 + ["stop"]
    assert clock.time() == pytest.approx(0.06)
    assert controller.frames[-1] == "stop"


async def test_native_both_claims_once_on_the_executing_side_view() -> None:
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.command_scheduler import HoldClaim, HoldLease
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import _async_with_hold_lease

    both = MagicMock()
    both.claim_hold_lease.return_value = HoldClaim.START
    paired = MagicMock(spec=PairedBedCoordinator)
    paired._targets_for.return_value = [("left", both), ("right", both)]
    started = []

    async def start() -> None:
        started.append(True)

    held = HoldLease(owner="card", generation=1, action="up", duration_s=1)
    await _async_with_hold_lease([(paired, "both")], held, lambda _t: "motor:back", start)
    assert started == [True]
    # One peek and one reservation, both on the view the command executes on.
    assert both.claim_hold_lease.call_count == 2
    both.release_hold_claim.assert_called_once()


class EstimatedStreamController(StreamController):
    """Streams the back motor and lets a travel-time estimate follow it (#601)."""

    held_back = False

    @property
    def estimated_position_motor_groups(self) -> dict[str, tuple[str, ...]]:
        return {"back": ("back",)}

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = super().motor_control_specs
        if not self.held_back:
            return specs
        hold = ControllerMotorHoldSpec(up_control="back_up", down_control="back_down")
        return tuple(replace(spec, hold=hold) if spec.key == "back" else spec for spec in specs)


@pytest.mark.parametrize("ending", ["expiry", "stop"])
@pytest.mark.parametrize("action", ["timed_move", "hold_control"])
async def test_a_renewed_hold_is_one_estimated_movement(runtime, clock, action, ending) -> None:
    """Renewals write nothing, so the estimate sees one move until release or expiry."""
    hass, coordinator = runtime
    controller = EstimatedStreamController(coordinator, STREAM)
    controller.held_back = action == "hold_control"
    coordinator._controller = controller
    manager = await pe.async_setup_position_estimates(
        hass, coordinator.entry.entry_id, ((ADDRESS, None),)
    )
    try:
        bed = manager.beds[ADDRESS]
        bed.configure({"back": (20.0, 10.0)})
        bed.set_reference()
        begun: list[tuple[str, ...]] = []
        ended: list[float | None] = []
        begin_move, end_move = bed.begin_move, bed.end_move

        def record_begin(motors: tuple[str, ...]) -> int:
            begun.append(motors)
            return begin_move(motors)

        def record_end(token: int, direction: str, seconds: float | None) -> None:
            ended.append(seconds)
            end_move(token, direction, seconds)

        bed.begin_move = record_begin  # type: ignore[method-assign]
        bed.end_move = record_end  # type: ignore[method-assign]

        async def call() -> None:
            data = (
                {"motor": "back", "direction": "up", "duration_ms": 100}
                if action == "timed_move"
                else {"control": "back_up", "duration": 0.1}
            )
            await hass.services.async_call(
                DOMAIN,
                action,
                {"device_id": ["bed"], **data, "hold_owner": "card", "hold_generation": 1},
                blocking=True,
            )

        began = clock.time()
        start = asyncio.create_task(call())
        for _ in range(5):
            await asyncio.sleep(0.05)
            await asyncio.wait_for(call(), 0.05)
        assert clock.time() - began == pytest.approx(0.25)
        if ending == "stop":
            # The card's release: STOP ends the hold before its lease does.
            await coordinator.async_stop_command()
        await asyncio.wait_for(start, 2)

        # One movement: renewals write nothing. A STOP ends it at the release
        # (250 ms); expiry 100 ms after the last renewal, seen by the next 20 ms
        # pulse at 360 ms.
        assert begun == [("back",)]
        assert ended == [pytest.approx(0.25 if ending == "stop" else 0.36)]
        assert ended[0] is not None
        back = bed.motors["back"]
        assert back.state is EstimateState.TRACKING
        assert back.percent == pytest.approx(ended[0] / 20.0 * 100.0)
    finally:
        await pe.async_unload_position_estimates(hass, coordinator.entry.entry_id)


async def test_expiry_lets_a_delayed_release_finish(runtime, clock) -> None:
    """A lease ending is a normal end: the controller's delayed release still runs.

    The coordinator used to cancel the operation task on expiry, which cut off
    a release the controller sends after a wait. Expiry is driven through the
    scheduler's own expiry path, and the release wait by an event, so no real
    timer decides the outcome.
    """
    from custom_components.adjustable_bed.command_scheduler import HoldLease

    _hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    started = asyncio.Event()
    release_due = asyncio.Event()

    async def hold_then_release_later(ctrl) -> None:
        try:
            ctrl.frames.append("up")
            started.set()
            await coordinator.cancel_command.wait()
        finally:
            # The app's release follows the last frame after a delay.
            await release_due.wait()
            ctrl.frames.append("release")

    held = HoldLease(owner="card", generation=1, action="up", duration_s=30)
    hold = asyncio.create_task(
        coordinator.async_execute_controller_command(
            hold_then_release_later, resource="motor:back", lease=held
        )
    )
    await asyncio.wait_for(started.wait(), 2)
    # The lease timer's own path: expire the record, which sets the cancel event.
    coordinator._command_scheduler.end_holds(CommandOutcome.EXPIRED)
    for _ in range(10):
        await asyncio.sleep(0)
    release_due.set()
    await asyncio.wait_for(hold, 2)
    assert controller.frames == ["up", "release"]
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED
