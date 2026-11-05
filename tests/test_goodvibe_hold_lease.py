"""Renewable holds (#483) on Good Vibe Sleep's sustained-press controls (row116).

The accepted report: a sustained press first sends after 100 ms, repeats every
100 ms with no fixed count and, once a tick fired, releases with the generic
STOP (`6e 01 side 6e sum8`, or `6e` on the single-byte link). Short, long and
short-and-long presses run their own gestures, and local memory mode turns an
eligible sustained press into one long operand. A lease is therefore scoped to
the held controls whose effective gesture is a sustained press. Every timer
here runs on virtual time.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import goodvibe_protocol as p
from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.beds.goodvibe import GoodVibeController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import (
    HOLD_CEILING_MS,
    NO_EXECUTION_CAPABILITIES,
)
from custom_components.adjustable_bed.goodvibe_catalog import ACTION_EXPANSIONS, ACTIONS, PRODUCTS
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_goodvibe_ha import runtime as goodvibe_runtime

# 6ERM mixes sustained, short and short-and-long presses on side 0. E3RM's
# memory positions are sustained presses that its Memory control's local mode
# turns into one long operand.
MIXED = "selector-0004"
MEMORY = "selector-0190"
HEAD_UP = "goodvibe_5d183b029875397d"  # 6ERM Head Up, sustained, operand 0x24
BED_LIGHT = "goodvibe_32c00c1e3a2def10"  # 6ERM Bed Light, short press
ZERO_GRAVITY = "goodvibe_78c00c9eb0644f8e"  # 6ERM Zero Gravity, short and long
MEMORY_1 = "goodvibe_06cccfe59bb8a66f"  # E3RM Memory Position 1, sustained
E3RM_HEAD_UP = "goodvibe_1c2ecffb1a47c5aa"  # E3RM Head Up, sustained
E3RM_MEMORY = "goodvibe_7e962a1c72a95e4b"  # E3RM Memory, toggles local mode
RELEASE = bytes.fromhex("6e01006edd")


def _held(profile: str, gesture: str) -> frozenset[str]:
    """The product's held controls whose catalog gesture is ``gesture``."""
    return frozenset(
        "goodvibe_" + child
        for detail in PRODUCTS[profile].actions
        for child in ACTION_EXPANSIONS.get(detail, (detail,))
        if not ACTIONS[child].local and ACTIONS[child].gesture == gesture
    )


def _controller(profile: str) -> GoodVibeController:
    coordinator = _FactoryCoordinator()
    coordinator.address = "AA:BB:CC:DD:EE:16"
    return GoodVibeController(coordinator, profile=profile)  # type: ignore[arg-type]


def _packet(control: str, side: int = 0, legacy: bool = False) -> bytes:
    return ACTIONS[control.removeprefix("goodvibe_")].packet(side, legacy)


def test_every_product_scopes_its_hold_to_its_sustained_controls() -> None:
    for profile in PRODUCTS:
        controller = _controller(profile)
        sustained = _held(profile, "sustainPress")
        execution = controller.execution
        if not sustained:
            assert execution == NO_EXECUTION_CAPABILITIES, profile
            continue
        assert execution.hold == "stream", profile
        assert execution.hold_controls == sustained, profile
        for control in controller.held_control_options:
            assert (execution.hold_for(control) == "stream") == (control in sustained)
        # Good Vibe has no motor route a lease could renew.
        assert execution.hold_for() is None
    for sensor in ("sleep_rm", "sleep_hj"):
        assert _controller(sensor).execution == NO_EXECUTION_CAPABILITIES


def test_memory_mode_takes_its_sustained_controls_out_of_the_scope() -> None:
    controller = _controller(MEMORY)
    sustained = _held(MEMORY, "sustainPress")
    eligible = {
        control
        for control in sustained
        if p.memory_eligible("E3RM", ACTIONS[control.removeprefix("goodvibe_")].label)
    }
    assert MEMORY_1 in eligible and E3RM_HEAD_UP not in eligible
    assert controller.execution.hold_controls == sustained
    controller.choices.memory = True
    assert controller.execution.hold_controls == sustained - eligible
    controller.choices.memory = False
    assert controller.execution.hold_controls == sustained


def _hold(control: str, errors: list[str] | None = None) -> Callable[[Any], Awaitable[None]]:
    async def move(controller: Any) -> None:
        try:
            # A leased hold_control runs to the stream ceiling, as the service runs it.
            await controller.hold_control(control, HOLD_CEILING_MS)
        except ValueError as err:
            if errors is None:
                raise
            errors.append(str(err))

    return move


@pytest.mark.parametrize(
    ("scenario", "legacy"),
    [("goodvibe:selector-0004", False), ("goodvibe:selector-0004:goodvibe_nordic", True)],
)
async def test_a_lease_streams_every_100_ms_and_expiry_sends_one_release(
    scenario: str, legacy: bool
) -> None:
    wire = await leased_hold(scenario, _hold(HEAD_UP), end_after_s=2.05, end="expire")

    assert {write.data for write in wire.held} == {_packet(HEAD_UP, legacy=legacy)}
    # First tick after 100 ms, then every 100 ms (plus the stubbed 7 ms write)
    # with no fixed count, right up to the end of the lease.
    assert wire.held[0].at_ms == 100
    assert all(100 <= gap <= 110 for gap in intervals(wire.held))
    assert wire.held[-1].at_ms >= wire.ended_ms - 110
    # Expiry ends the refresh; the app's release follows at once, exactly once.
    assert [write.data for write in wire.after] == [b"\x6e" if legacy else RELEASE]
    assert wire.after[0].at_ms == wire.ended_ms


async def test_a_lease_stops_streaming_at_the_30_second_ceiling() -> None:
    # Each stubbed write takes 7 ms, so counting 100 ms ticks alone would overrun.
    wire = await leased_hold("goodvibe:selector-0004", _hold(HEAD_UP), end_after_s=40, end="expire")
    frames = [write for write in wire.held if write.data == _packet(HEAD_UP)]

    assert frames[-1].at_ms <= HOLD_CEILING_MS
    assert wire.held[-1].data == RELEASE
    assert wire.held[-1].at_ms <= HOLD_CEILING_MS + 110
    assert wire.after == ()


async def test_stop_preempts_a_lease_with_the_release() -> None:
    wire = await leased_hold("goodvibe:selector-0004", _hold(HEAD_UP), end_after_s=1, end="stop")

    assert wire.held and {write.data for write in wire.held} == {_packet(HEAD_UP)}
    # The held task's own release, then the explicit STOP: the same frame.
    assert {write.data for write in wire.after} == {RELEASE}


@pytest.mark.parametrize("control", [BED_LIGHT, ZERO_GRAVITY])
async def test_a_lease_never_drives_a_gesture_control(control: str) -> None:
    errors: list[str] = []
    wire = await leased_hold(
        "goodvibe:selector-0004", _hold(control, errors), end_after_s=4, end="expire"
    )

    assert errors == ["This control does not support renewable holds"]
    assert wire.held == wire.after == ()


async def test_memory_mode_after_admission_refuses_the_lease_without_writing() -> None:
    errors: list[str] = []
    hold = _hold(MEMORY_1, errors)

    async def move(controller: Any) -> None:
        controller.choices.memory = True
        await hold(controller)

    wire = await leased_hold(
        "goodvibe:selector-0004", move, end_after_s=1, end="expire", variant=MEMORY
    )

    assert errors == ["This control does not support renewable holds"]
    assert wire.held == wire.after == ()


@pytest.fixture
async def bed(
    hass: HomeAssistant, request: pytest.FixtureRequest
) -> AsyncIterator[tuple[HomeAssistant, AdjustableBedCoordinator, list[tuple[float, bytes]]]]:
    """A Good Vibe runtime whose writes are stamped on the test's clock."""
    coordinator = goodvibe_runtime(hass, getattr(request, "param", MIXED), handoff=False)
    writes: list[tuple[float, bytes]] = []

    async def write(_char: object, data: bytes, response: bool = False) -> None:
        # Resolved per write, so the stamp reads the virtual clock once it runs.
        writes.append((asyncio.get_running_loop().time(), bytes(data)))

    coordinator._client.write_gatt_char = AsyncMock(side_effect=write)
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
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
        yield hass, coordinator, writes
    coordinator._client.is_connected = False
    await coordinator.async_shutdown()


@pytest.fixture
async def clock(bed: Any) -> AsyncIterator[Any]:
    with virtual_clock() as fake:
        yield fake


async def _hold_control(
    hass: HomeAssistant, control: str, generation: int | None, duration: float = 0.75
) -> None:
    data: dict[str, Any] = {"device_id": ["bed"], "control": control, "duration": duration}
    if generation is not None:
        data |= {"hold_owner": "card", "hold_generation": generation}
    await hass.services.async_call(DOMAIN, "hold_control", data, blocking=True)


async def test_renewals_keep_a_sustained_control_streaming_until_the_lease_lapses(
    bed: Any, clock: Any
) -> None:
    hass, coordinator, writes = bed
    began = clock.time()
    start = asyncio.create_task(_hold_control(hass, HEAD_UP, 1))
    # The card renews a 750 ms lease every 250 ms.
    for _ in range(4):
        await asyncio.sleep(0.25)
        before = len(writes)
        await asyncio.wait_for(_hold_control(hass, HEAD_UP, 1), 0.05)
        # A renewal writes no frame of its own.
        assert len(writes) == before
        assert not start.done()
    await asyncio.wait_for(start, 5)

    # Renewed last at 1000 ms, the lease lapses at 1750 ms.
    assert clock.time() - began == pytest.approx(1.75)
    held = [at for at, data in writes if data == _packet(HEAD_UP)]
    assert [round((at - began) * 1000) for at in held] == list(range(100, 1800, 100))
    assert writes[-1] == (pytest.approx(began + 1.75), RELEASE)
    assert len(writes) == len(held) + 1
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


@pytest.mark.parametrize("control", [BED_LIGHT, ZERO_GRAVITY])
async def test_a_gesture_control_refuses_a_lease_as_an_undeclared_bed_does(
    bed: Any, clock: Any, control: str
) -> None:
    hass, _coordinator, writes = bed
    with pytest.raises(ServiceValidationError, match="does not support renewable holds"):
        await _hold_control(hass, control, 1)
    assert writes == []
    # Its finite gesture is unchanged: one short operand when released early.
    await _hold_control(hass, control, None, duration=1)
    frames = [data for _at, data in writes]
    assert frames[0] == _packet(control)
    assert frames == ([_packet(control), RELEASE] if control == BED_LIGHT else [_packet(control)])


@pytest.mark.parametrize("bed", [MEMORY], indirect=True)
async def test_the_memory_control_moves_its_positions_out_of_the_lease(
    bed: Any, clock: Any
) -> None:
    hass, coordinator, writes = bed
    controller = coordinator._controller
    buttons = {
        spec.key: ControllerActionButton(coordinator, spec)
        for spec in controller.controller_button_specs
        if spec.hold is not None
    }
    assert buttons[MEMORY_1].extra_state_attributes["hold_lease_mode"] == "stream"

    # The app's Memory control sends its operand, then turns local mode on.
    await _hold_control(hass, E3RM_MEMORY, None, duration=0.1)
    assert controller.choices.memory
    assert "hold_lease_mode" not in buttons[MEMORY_1].extra_state_attributes
    assert buttons[E3RM_HEAD_UP].extra_state_attributes["hold_lease_mode"] == "stream"
    writes.clear()
    with pytest.raises(ServiceValidationError, match="does not support renewable holds"):
        await _hold_control(hass, MEMORY_1, 1)
    assert writes == []
    assert controller.choices.memory

    # Outside memory mode the position is a sustained press again.
    controller.choices.memory = False
    start = asyncio.create_task(_hold_control(hass, MEMORY_1, 2))
    await asyncio.wait_for(start, 2)
    assert [data for _at, data in writes] == [_packet(MEMORY_1)] * 7 + [RELEASE]


def test_buttons_offer_a_lease_only_on_sustained_controls(hass: HomeAssistant) -> None:
    coordinator = goodvibe_runtime(hass, MIXED)
    offered = {
        spec.key
        for spec in coordinator._controller.controller_button_specs
        if spec.hold is not None
        and ControllerActionButton(coordinator, spec).extra_state_attributes.get(
            "hold_lease_mode"
        )
        == "stream"
    }
    assert offered == _held(MIXED, "sustainPress")
    assert {BED_LIGHT, ZERO_GRAVITY}.isdisjoint(offered)
