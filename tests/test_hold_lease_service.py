"""Renewable ``timed_move`` and ``hold_control`` (#483) through the real coordinator."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from custom_components.adjustable_bed.services import async_register_services
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


async def test_renewals_keep_one_stream_alive_then_it_releases(runtime) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    start = asyncio.create_task(_timed(hass, 1))
    loop = asyncio.get_running_loop()
    began = loop.time()
    for _ in range(5):
        await asyncio.sleep(0.05)
        frames = len(controller.frames)
        await asyncio.wait_for(_timed(hass, 1), 0.05)
        assert "stop" not in controller.frames[frames:]
        assert not start.done()
    await asyncio.wait_for(start, 2)

    # Five 50 ms renewals of a 100 ms lease outlived three 20 ms pulses.
    assert loop.time() - began >= 0.3
    assert controller.frames.count("up") > 3
    assert controller.frames[-1] == "stop"
    assert "up" not in controller.frames[controller.frames.index("stop") :]
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


async def test_late_renewal_after_stop_is_refused_without_motion(runtime) -> None:
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


async def test_controller_without_hold_rejects_a_lease(runtime) -> None:
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


async def test_finite_timed_move_is_unchanged_without_an_owner(runtime) -> None:
    hass, coordinator = runtime
    controller = _install(coordinator, STREAM)
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {"device_id": ["bed"], "motor": "back", "direction": "up", "duration_ms": 200},
        blocking=True,
    )
    # The elapsed duration bounds the planned pulses; there is no lease and no HOLD.
    assert 3 < controller.frames.count("up") <= 11
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.COMMAND
    assert record.outcome is CommandOutcome.COMPLETED


async def test_hold_control_lease_renews_and_rejects_long_leases(runtime) -> None:
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
    start = asyncio.create_task(hold(0.1))
    while "up" not in controller.frames:
        await asyncio.sleep(0.005)
    await asyncio.wait_for(hold(0.1), 0.05)
    await asyncio.wait_for(start, 2)
    assert controller.frames[-1] == "stop"
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED


async def test_disconnect_ends_the_hold_and_refuses_renewal(runtime) -> None:
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


async def test_lease_inside_a_prepared_reservation_runs_and_expires(runtime) -> None:
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
    assert 1 < controller.frames.count("up") < 20
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
