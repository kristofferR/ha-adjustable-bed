"""``timed_move`` joins the merged stream only for declared concurrent motors (#516)."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.command_scheduler import (
    CommandKind,
    CommandOutcome,
    StreamMember,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import ExecutionCapabilities
from tests.test_hold_lease_service import StreamController, runtime  # noqa: F401

CONCURRENT = ExecutionCapabilities(
    hold="stream", concurrent=frozenset({"motor:back", "motor:legs"})
)


class ComposingController(StreamController):
    """Writes one composed frame per tick from the live members."""

    @property
    def stream_tick_s(self) -> float:
        return 0.01

    async def write_stream_tick(self, members: tuple[StreamMember, ...]) -> None:
        self.frames.append("+".join(sorted(f"{m.motor}:{m.action}" for m in members)))

    async def end_stream_member(
        self, member: StreamMember, remaining: tuple[StreamMember, ...]
    ) -> None:
        self.frames.append(f"end {member.motor}")

    async def release_stream(self) -> None:
        self.frames.append("release")


async def _move(hass: HomeAssistant, motor: str, duration_ms: int) -> None:
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {"device_id": ["bed"], "motor": motor, "direction": "up", "duration_ms": duration_ms},
        blocking=True,
    )


async def test_two_timed_moves_share_one_composed_stream(
    runtime: tuple[HomeAssistant, AdjustableBedCoordinator],  # noqa: F811
) -> None:
    hass, coordinator = runtime
    controller = ComposingController(coordinator, CONCURRENT)
    coordinator._controller = controller
    back = asyncio.create_task(_move(hass, "back", 200))
    while not controller.frames:
        await asyncio.sleep(0.005)
    await asyncio.wait_for(_move(hass, "legs", 100), 1)
    assert "back:up+legs:up" in controller.frames
    await asyncio.wait_for(back, 1)
    assert controller.frames[-1] == "release"
    assert controller.frames.count("release") == 1
    assert "up" not in controller.frames  # the serial pulse path never ran
    scheduler = coordinator._command_scheduler
    while not scheduler.recent_records:
        await asyncio.sleep(0.001)
    record = scheduler.recent_records[-1]
    assert record.kind is CommandKind.STREAM
    assert record.outcome is CommandOutcome.COMPLETED


async def test_motor_outside_the_declaration_stays_serialized(
    runtime: tuple[HomeAssistant, AdjustableBedCoordinator],  # noqa: F811
) -> None:
    hass, coordinator = runtime
    controller = ComposingController(
        coordinator, ExecutionCapabilities(concurrent=frozenset({"motor:head", "motor:feet"}))
    )
    coordinator._controller = controller
    await asyncio.wait_for(_move(hass, "back", 100), 1)
    assert "up" in controller.frames
    assert "release" not in controller.frames
    assert coordinator._command_scheduler.recent_records[-1].kind is CommandKind.COMMAND


async def test_cover_stop_ends_only_its_streaming_motor(
    runtime: tuple[HomeAssistant, AdjustableBedCoordinator],  # noqa: F811
) -> None:
    from custom_components.adjustable_bed.cover import (
        AdjustableBedCover,
        _build_cover_description,
    )

    hass, coordinator = runtime
    controller = ComposingController(coordinator, CONCURRENT)
    coordinator._controller = controller
    spec = next(spec for spec in controller.motor_control_specs if spec.key == "back")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.hass = hass
    cover.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    back = asyncio.create_task(_move(hass, "back", 5000))
    legs = asyncio.create_task(_move(hass, "legs", 300))
    while "back:up+legs:up" not in controller.frames:
        await asyncio.sleep(0.005)
    await cover.async_stop_cover()
    await asyncio.wait_for(back, 1)
    assert "end back" in controller.frames
    assert not legs.done()
    while controller.frames[-1] != "legs:up":
        await asyncio.sleep(0.005)
    await asyncio.wait_for(legs, 1)
    assert controller.frames[-1] == "release"


async def test_repeated_cover_stop_stays_member_scoped(
    runtime: tuple[HomeAssistant, AdjustableBedCoordinator],  # noqa: F811
) -> None:
    from custom_components.adjustable_bed.cover import (
        AdjustableBedCover,
        _build_cover_description,
    )

    hass, coordinator = runtime
    controller = ComposingController(coordinator, CONCURRENT)
    coordinator._controller = controller
    spec = next(spec for spec in controller.motor_control_specs if spec.key == "back")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.hass = hass
    cover.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    back = asyncio.create_task(_move(hass, "back", 5000))
    legs = asyncio.create_task(_move(hass, "legs", 300))
    while "back:up+legs:up" not in controller.frames:
        await asyncio.sleep(0.005)
    await cover.async_stop_cover()
    await cover.async_stop_cover()
    await asyncio.wait_for(back, 1)
    await asyncio.sleep(0.03)
    assert not legs.done()
    await asyncio.wait_for(legs, 1)
    assert controller.frames.count("release") == 1


async def test_streamed_timed_moves_feed_position_estimates(
    runtime: tuple[HomeAssistant, AdjustableBedCoordinator],  # noqa: F811
) -> None:
    from custom_components.adjustable_bed import position_estimate as pe

    hass, coordinator = runtime

    class EstimatedController(ComposingController):
        @property
        def estimated_position_motor_groups(self) -> dict[str, tuple[str, ...]]:
            return {"back": ("back",), "legs": ("legs",)}

    controller = EstimatedController(coordinator, CONCURRENT)
    coordinator._controller = controller
    manager = await pe.async_setup_position_estimates(
        hass, coordinator.entry.entry_id, ((coordinator.address, None),)
    )
    bed = manager.beds[coordinator.address]
    bed.configure({"back": (20.0, 10.0), "legs": (10.0, 8.0)})
    bed.set_reference()

    back = asyncio.create_task(_move(hass, "back", 200))
    while not controller.frames:
        await asyncio.sleep(0.005)
    await asyncio.wait_for(_move(hass, "legs", 100), 1)
    # legs settled on its own; back is still streaming and not yet counted.
    assert bed.motors["back"].percent == 0
    assert bed.motors["legs"].percent == pytest.approx(100 / 10.0 * 0.1, abs=0.3)
    await asyncio.wait_for(back, 1)
    assert bed.motors["back"].percent == pytest.approx(100 / 20.0 * 0.2, abs=0.15)
    assert bed.tracking(["back", "legs"])
