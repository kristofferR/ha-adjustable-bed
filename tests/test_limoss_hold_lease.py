"""Renewable holds (#483) on the Limoss DD app profiles: Limoss Remote and FSM Relax.

Each profile streams its held channel at its own tick until the lease ends,
then sends its five-frame STOP burst. The legacy route declares nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.fsm_relax import FsmRelaxController, FsmRelaxSetup
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import (
    LimossRemoteCapabilities,
    LimossRemoteSequence,
)
from custom_components.adjustable_bed.codec import limoss as codec
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import (
    BED_TYPE_FSM_RELAX,
    BED_TYPE_LIMOSS_REMOTE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    DOMAIN,
    LIMOSS_CHAR_UUID,
    LIMOSS_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import NO_EXECUTION_CAPABILITIES
from custom_components.adjustable_bed.fsm_relax_state import FsmRelaxSession
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemoryStore,
    LimossRemoteSession,
)
from custom_components.adjustable_bed.profiles.limoss import (
    FSM_RELAX,
    LEGACY,
    LIMOSS_REMOTE,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.limoss_vectors import FROZEN_BODIES

STOP = codec.body(codec.STOP).hex()
# Back up (Limoss Remote ``motor_1_up``, FSM Relax ``command_12``), no reversal.
HELD = codec.flagged(0x12, (False,) * 4).hex()


def test_only_the_app_profiles_declare_a_stream_hold() -> None:
    assert LIMOSS_REMOTE.execution.hold == "stream"
    assert FSM_RELAX.execution.hold == "stream"
    assert LEGACY.execution.hold is None


@pytest.mark.parametrize("profile", [LIMOSS_REMOTE, FSM_RELAX], ids=lambda p: p.key)
def test_held_and_release_frames_are_frozen(profile) -> None:
    frozen = FROZEN_BODIES[profile.key]
    held = {op for layout in profile.layouts.values() for op in layout if op is not None}
    assert {codec.body(op).hex() for op in held} <= frozen
    assert codec.body(profile.stop.opcode).hex() == STOP
    assert STOP in frozen
    assert profile.stop.frames == 5
    assert profile.tick_ms is not None


@dataclass
class Bed:
    hass: HomeAssistant
    coordinator: AdjustableBedCoordinator
    controller: BedController
    writes: list[tuple[float, str]]

    def bodies(self) -> list[str]:
        return [body for _, body in self.writes]


def _client(writes: list[tuple[float, str]]) -> MagicMock:
    char = SimpleNamespace(uuid=LIMOSS_CHAR_UUID, handle=7, properties=["write", "notify"])
    client = MagicMock(
        is_connected=True,
        services=[SimpleNamespace(uuid=LIMOSS_SERVICE_UUID, characteristics=[char])],
    )

    async def write(_char, packet, response=False) -> None:
        body = codec.decode(bytes(packet))
        assert body is not None
        writes.append((asyncio.get_running_loop().time(), body.hex()))

    client.write_gatt_char = AsyncMock(side_effect=write)
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    return client


def _controller(bed_type: str, coordinator: AdjustableBedCoordinator) -> BedController:
    if bed_type == BED_TYPE_FSM_RELAX:
        fsm = FsmRelaxController(coordinator, setup=FsmRelaxSetup(), session=FsmRelaxSession())
        fsm._accept_body(b"\x02\x08\x04\x00\x08")
        fsm._live_capabilities = True
        return fsm
    remote = LimossRemoteController(
        coordinator,
        product="bed",
        cached_capabilities=LimossRemoteCapabilities(8, 0x12, 255, 0, 8),
        session=LimossRemoteSession(memories=LimossRemoteMemoryStore()),
        sequence=LimossRemoteSequence(),
    )
    # The live receiver session is ready; preflight only re-queries it.
    remote.start_notify = AsyncMock()  # type: ignore[method-assign]
    return remote


@pytest.fixture(params=[BED_TYPE_LIMOSS_REMOTE, BED_TYPE_FSM_RELAX])
async def bed(hass: HomeAssistant, request: pytest.FixtureRequest) -> AsyncIterator[Bed]:
    bed_type: str = request.param
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Limoss",
        unique_id="AA:BB:CC:DD:EE:51",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
            CONF_NAME: "Limoss",
            CONF_BED_TYPE: bed_type,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    writes: list[tuple[float, str]] = []
    coordinator._client = _client(writes)
    controller = _controller(bed_type, coordinator)
    coordinator._controller = controller
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
            patch.object(coordinator, "save_app_state", MagicMock(), create=True)
        )
        resolve = stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.limoss_remote_services._resolve_sided_targets",
                new=resolve,
            )
        )
        yield Bed(hass, coordinator, controller, writes)
    await coordinator.async_shutdown()


@pytest.fixture
async def clock(bed: Bed) -> AsyncIterator[Any]:
    """Virtual time for the test body: ticks, leases and renewals are exact.

    Entered after ``bed`` is set up, so Home Assistant itself starts on the real
    loop.
    """
    with virtual_clock() as fake:
        yield fake


async def _hold(bed: Bed, generation: int, duration: float = 0.3) -> None:
    control = "motor_1_up" if isinstance(bed.controller, LimossRemoteController) else "command_12"
    await bed.hass.services.async_call(
        DOMAIN,
        "hold_control",
        {
            "device_id": ["bed"],
            "control": control,
            "duration": duration,
            "hold_owner": "card",
            "hold_generation": generation,
        },
        blocking=True,
    )


async def _started(bed: Bed) -> None:
    async with asyncio.timeout(2):
        while HELD not in bed.bodies():
            await asyncio.sleep(0.005)


def _tick_s(bed: Bed) -> float:
    profile = bed.controller.profile  # type: ignore[attr-defined]
    return profile.tick_ms / 1000


async def test_renewals_keep_streaming_then_expiry_sends_the_stop_burst(bed: Bed, clock: Any) -> None:
    start = asyncio.create_task(_hold(bed, 1))
    await _started(bed)
    began = asyncio.get_running_loop().time()
    for _ in range(4):
        await asyncio.sleep(0.2)
        await asyncio.wait_for(_hold(bed, 1), 1)
        assert STOP not in bed.bodies()
        assert not start.done()
    await asyncio.wait_for(start, 3)

    # Four 200 ms renewals of a 300 ms lease outlived the first lease.
    bodies = bed.bodies()
    first_stop = bodies.index(STOP)
    assert bodies[first_stop:] == [STOP] * 5
    assert set(bodies[:first_stop]) == {HELD}
    times = [at for at, body in bed.writes if body == HELD]
    assert times[-1] - began >= 0.8
    # The profile's own tick paces the stream; no renewal writes a frame.
    mean_gap = (times[-1] - times[0]) / (len(times) - 1)
    assert _tick_s(bed) * 0.9 <= mean_gap <= _tick_s(bed) * 1.5
    record = bed.coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


async def test_lease_expiry_without_renewal_releases(bed: Bed, clock: Any) -> None:
    await asyncio.wait_for(_hold(bed, 2, duration=0.15), 2)
    bodies = bed.bodies()
    assert bodies[-5:] == [STOP] * 5
    assert bodies.count(STOP) == 5
    assert bed.coordinator._command_scheduler.recent_records[-1].outcome is (
        CommandOutcome.EXPIRED
    )


async def test_stop_preempts_renewal(bed: Bed, clock: Any) -> None:
    start = asyncio.create_task(_hold(bed, 3, duration=5))
    await _started(bed)
    await bed.coordinator.async_stop_command()
    await asyncio.wait_for(start, 2)
    bodies = bed.bodies()
    stop_at = bodies.index(STOP)
    assert HELD not in bodies[stop_at:]
    frames = len(bodies)
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _hold(bed, 3)
    await asyncio.sleep(3 * _tick_s(bed))
    assert len(bed.bodies()) == frames



async def test_an_undeclared_profile_refuses_a_lease_before_writing(bed: Bed) -> None:
    with (
        patch.object(
            type(bed.controller),
            "execution",
            new_callable=PropertyMock,
            return_value=NO_EXECUTION_CAPABILITIES,
        ),
        pytest.raises(ServiceValidationError, match="renewable holds"),
    ):
        await _hold(bed, 9)
    assert bed.writes == []


async def test_a_renewed_hold_is_one_tracked_movement(bed: Bed, clock: Any) -> None:
    """Renewals extend the running command, so position estimates see one move."""
    from custom_components.adjustable_bed import limoss_remote_services, services

    runs: list[str] = []
    track = services.track_held_control

    def spy(hass, control, command):
        tracked = track(hass, control, command)

        async def run(controller) -> None:
            runs.append(control)
            await tracked(controller)

        return run

    with (
        patch.object(services, "track_held_control", spy),
        patch.object(limoss_remote_services, "track_held_control", spy),
    ):
        start = asyncio.create_task(_hold(bed, 6))
        await _started(bed)
        for _ in range(3):
            await asyncio.sleep(0.2)
            await asyncio.wait_for(_hold(bed, 6), 1)
        await asyncio.wait_for(start, 3)
    assert len(runs) == 1
    assert bed.bodies()[-5:] == [STOP] * 5
