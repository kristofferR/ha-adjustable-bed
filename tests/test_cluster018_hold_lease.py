"""Renewable holds (#483) on the classic Richmat apps' keep buttons (row066).

All five accepted reports: a keep button (worker mode 1) repeats its payload
every worker tick with no fixed count until UP; UP sets mode 0, which sends the
release 50 ms later. Short, long and armed presses run their own gestures, and
the Hold/Release selector moves presets and Flat between them, so a lease is
scoped to the held controls that run the keep mode under the current selection.
Every timer here runs on virtual time.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.beds.cluster018 import Cluster018Controller
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.cluster018_caller import Selection
from custom_components.adjustable_bed.cluster018_profiles import Control
from custom_components.adjustable_bed.cluster018_transport import Transport
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import HOLD_CEILING_MS, NO_EXECUTION_CAPABILITIES
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_cluster018 import controller

FIXTURES = Path(__file__).parent / "fixtures" / "cluster018"
# The default wire-snapshot route: Avocado Eco Base GORM, framed over W4.
SCENARIO = "richmat_classic_apps"
NORDIC = "richmat_classic_apps:avocadoecobase:GORM:nordic"
HEAD_UP = "cluster018_6"  # GORM keep button, operand 0x43
FRAME = bytes.fromhex("6e010043b2")
RELEASE = bytes.fromhex("6e01006edd")


def _hold(control: str, errors: list[str] | None = None) -> Callable[[Any], Awaitable[None]]:
    async def move(ctrl: Any) -> None:
        try:
            # A leased hold_control runs to the stream ceiling, as the service runs it.
            await ctrl.hold_control(control, HOLD_CEILING_MS)
        except ValueError as err:
            if errors is None:
                raise
            errors.append(str(err))

    return move


def test_the_scope_follows_the_accepted_caller_vectors() -> None:
    """Every accepted DOWN/UP pair: keep mode with a payload, then mode 0, is in scope."""
    with gzip.open(FIXTURES / "callers.json.gz", "rt") as source:
        cases = json.load(source)
    pairs: dict[str, dict[str, Any]] = {}
    for case in cases:
        key = json.dumps([case["layout"], case["wire"], case["button"], case["selection"]], sort_keys=True)
        pairs.setdefault(key, {})[case["event"]] = case
    checked = kept = 0
    for pair in pairs.values():
        if set(pair) != {"DOWN", "UP"}:
            continue
        down, up = pair["DOWN"], pair["UP"]
        expected = (
            down["expected"]["mode"] == 1
            and down["expected"]["payload"] not in (None, "RETAIN")
            and up["expected"]["mode"] == 0
        )
        button = down["button"]
        control = Control(
            **{
                **button,
                "modes": tuple(button["modes"]),
                "ancestor_visibility": tuple(button["ancestor_visibility"]),
            }
        )
        selection = Selection(**down["selection"])
        stub = SimpleNamespace(
            _session=SimpleNamespace(wire=down["wire"]), layout=down["layout"], app=None
        )
        assert Cluster018Controller._keeps(cast(Any, stub), control, selection) is expected, down
        checked += 1
        kept += expected
    assert checked > 10_000 and 0 < kept < checked


def test_every_motor_of_a_plain_layout_keeps_and_no_motor_route_leases() -> None:
    ctrl, _ = controller(layout="6BRM")
    execution = ctrl.execution
    assert execution.hold == "stream"
    assert execution.hold_controls == frozenset(ctrl.held_control_options)
    assert execution.hold_for() is None


def test_the_hold_selector_moves_presets_into_the_scope() -> None:
    ctrl, _ = controller("superior", "YGRM")
    motors = frozenset(ctrl.held_control_options)
    assert ctrl.execution.hold_controls == motors
    ctrl._select("hold", "hold")
    held = frozenset(ctrl.held_control_options)
    presets = {control for control in held if control.endswith("_hold")}
    assert presets and ctrl.execution.hold_controls == held
    ctrl._select("hold", "release")
    assert ctrl.execution.hold_controls == motors
    assert presets.isdisjoint(ctrl.held_control_options)


def test_arming_a_save_takes_its_selectview_actions_out_of_the_scope() -> None:
    ctrl, _ = controller(layout="GXRM")
    special = {
        f"cluster018_{button.node}" for button in ctrl._controls if button.select_special
    } & set(ctrl.held_control_options)
    assert special and special <= (ctrl.execution.hold_controls or frozenset())
    ctrl._select("program", "armed")
    assert special.isdisjoint(ctrl.execution.hold_controls or frozenset())


def test_the_foot_selection_takes_its_null_getter_controls_out() -> None:
    ctrl, _ = controller(layout="GVRM", wire="RAW")
    tagged = {
        f"cluster018_{button.node}" for button in ctrl._controls if button.tag == "63"
    } & set(ctrl.held_control_options)
    assert tagged and tagged <= (ctrl.execution.hold_controls or frozenset())
    ctrl._selection = replace(ctrl._selection, head=False)
    assert tagged.isdisjoint(ctrl.execution.hold_controls or frozenset())


def test_a_layout_without_keep_buttons_declares_nothing() -> None:
    ctrl, _ = controller(layout="FWRM")
    ctrl._controls = tuple(button for button in ctrl._controls if button.status != 1)
    assert ctrl.execution == NO_EXECUTION_CAPABILITIES


@pytest.mark.parametrize(("scenario", "frame", "release"), [
    (SCENARIO, FRAME, RELEASE),
    (NORDIC, bytes.fromhex("43"), bytes.fromhex("6e")),
])
async def test_a_lease_keeps_refreshing_and_expiry_releases_50_ms_later(
    scenario: str, frame: bytes, release: bytes
) -> None:
    wire = await leased_hold(scenario, _hold(HEAD_UP), end_after_s=2.0, end="expire")

    assert {write.data for write in wire.held} == {frame}
    # Every 150 ms tick (plus the stubbed 7 ms write), right up to the lease end.
    assert wire.held[0].at_ms == 0
    assert all(150 <= gap <= 160 for gap in intervals(wire.held))
    assert wire.held[-1].at_ms >= wire.ended_ms - 160
    assert [write.data for write in wire.after] == [release]
    assert wire.after[0].at_ms == wire.ended_ms + 50


async def test_a_lease_stops_refreshing_at_the_30_second_ceiling() -> None:
    wire = await leased_hold(SCENARIO, _hold(HEAD_UP), end_after_s=40, end="expire")
    frames = [write for write in wire.held if write.data == FRAME]

    assert frames[-1].at_ms <= HOLD_CEILING_MS
    assert wire.held[-1].data == RELEASE
    assert wire.held[-1].at_ms <= HOLD_CEILING_MS + 210
    assert wire.after == ()


async def test_stop_preempts_a_lease_with_the_release() -> None:
    wire = await leased_hold(SCENARIO, _hold(HEAD_UP), end_after_s=1, end="stop")

    assert wire.held and {write.data for write in wire.held} == {FRAME}
    # The held task's own release, then the explicit STOP: the same frame.
    assert wire.after and {write.data for write in wire.after} == {RELEASE}


async def test_a_selector_change_after_admission_refuses_the_lease_without_writing() -> None:
    errors: list[str] = []

    async def move(ctrl: Any) -> None:
        ctrl._select("program", "armed")
        await _hold("cluster018_4", errors)(ctrl)

    wire = await leased_hold(
        SCENARIO, move, end_after_s=1, end="expire", entry_data={"product_type": "GXRM"}
    )

    assert errors == ["This control does not support renewable holds"]
    assert wire.held == wire.after == ()


def _runtime(hass: HomeAssistant, layout: str) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={
        "address": "AA:BB:CC:DD:EE:18", "bed_type": "richmat_classic_apps",
        "protocol_variant": "avocadoecobase", "product_type": layout,
        "disconnect_after_command": False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = MagicMock(is_connected=True, disconnect=AsyncMock(), stop_notify=AsyncMock())
    ctrl = Cluster018Controller(coordinator)
    coordinator._controller = coordinator._offline_controller = ctrl
    ctrl._session = Transport(
        coordinator._client,
        SimpleNamespace(uuid="write", properties=["write"]),
        SimpleNamespace(uuid="notify", properties=["notify"]),
        "FRAMED",
    )
    return coordinator


@pytest.fixture
async def bed(
    hass: HomeAssistant, request: pytest.FixtureRequest
) -> AsyncIterator[tuple[HomeAssistant, AdjustableBedCoordinator, list[tuple[float, bytes]]]]:
    """A classic-app runtime whose writes are stamped on the test's clock."""
    coordinator = _runtime(hass, getattr(request, "param", "6BRM"))
    writes: list[tuple[float, bytes]] = []

    async def write(_char: object, data: bytes, response: bool = False) -> None:
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


async def test_renewals_keep_a_keep_button_refreshing_until_the_lease_lapses(
    bed: Any, clock: Any
) -> None:
    hass, coordinator, writes = bed
    began = clock.time()
    start = asyncio.create_task(_hold_control(hass, "cluster018_1", 1))
    # The card renews a 750 ms lease every 250 ms.
    for _ in range(4):
        await asyncio.sleep(0.25)
        before = len(writes)
        await asyncio.wait_for(_hold_control(hass, "cluster018_1", 1), 0.05)
        # A renewal writes no frame of its own.
        assert len(writes) == before
        assert not start.done()
    await asyncio.wait_for(start, 5)

    # Renewed last at 1000 ms, the lease lapses at 1750 ms; the release follows 50 ms later.
    held = [at for at, data in writes if data == bytes.fromhex("6e01002493")]
    assert [round((at - began) * 1000) for at in held] == list(range(0, 1751, 150))
    assert writes[-1] == (pytest.approx(began + 1.8), RELEASE)
    assert len(writes) == len(held) + 1
    record = coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


@pytest.mark.parametrize("bed", ["GXRM"], indirect=True)
async def test_an_armed_action_refuses_a_lease_as_an_undeclared_bed_does(
    bed: Any, clock: Any
) -> None:
    hass, coordinator, writes = bed
    ctrl = coordinator._controller
    ctrl._select("program", "armed")
    with pytest.raises(ServiceValidationError, match="does not support renewable holds"):
        await _hold_control(hass, "cluster018_4", 1)
    assert writes == []
    assert ctrl._selection.armed


@pytest.mark.parametrize("bed", ["YGRM"], indirect=True)
async def test_buttons_offer_a_lease_only_on_keep_buttons(bed: Any) -> None:
    _hass, coordinator, _writes = bed
    ctrl = coordinator._controller
    ctrl._select("hold", "hold")
    buttons = {
        spec.key: ControllerActionButton(coordinator, spec)
        for spec in ctrl.controller_button_specs
        if spec.hold is not None
    }
    offered = {
        key
        for key, button in buttons.items()
        if button.extra_state_attributes.get("hold_lease_mode") == "stream"
    }
    assert offered == set(ctrl.held_control_options)
    ctrl._select("hold", "release")
    offered = {
        key
        for key, button in buttons.items()
        if button.extra_state_attributes.get("hold_lease_mode") == "stream"
    }
    assert offered == set(ctrl.held_control_options)
    assert not any(key.endswith("_hold") for key in offered)
