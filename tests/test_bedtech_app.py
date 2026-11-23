"""The accepted BedTech app's complete vectors, model gates and sleeper routes."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.bedtech.controller import BedTechController
from custom_components.adjustable_bed.beds.bedtech.routing import app_side
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profiles.richmat import BEDTECH_APP_PROFILES
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.bedtech_vectors import ROUTES, VECTORS


def controller(model: str) -> BedTechController:
    coordinator = MagicMock()
    coordinator.entry.data = {CONF_PROTOCOL_VARIANT: model.lower()}
    coordinator.motor_pulse_count = 2
    coordinator.motor_pulse_delay_ms = 777
    return BedTechController(coordinator)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda row: row["id"])
def test_all_frozen_literals_use_the_richmat_codec(vector):
    literal = vector["command"]
    if not literal:
        assert vector["hex"] == "NO_WRITE"
        return
    bank = int(len(literal) == 2 and literal.startswith("_"))
    assert codec.command(ord(literal[bank]), bank).hex() == vector["hex"]


@pytest.mark.parametrize(
    "row", ROUTES, ids=lambda row: f"{row['model']}-{row['side']}-{row['ui_action']}"
)
async def test_every_frozen_model_action_and_side(row):
    bed = controller(row["model"])
    side = app_side(bed.model, int(row["side"]), row["ui_action"])
    if bed.supports_single_address_pairing:
        assert row["targets"] == ["sleeper1Device"]
    else:
        expected = {
            SIDE_LEFT: ["sleeper1Device"],
            SIDE_RIGHT: ["sleeper2Device"],
            SIDE_BOTH: ["sleeper1Device", "sleeper2Device"],
        }
        assert expected[side] == row["targets"]
    bed.write_command = AsyncMock()
    with bed.side_scope(side):
        if row["disposition"] == "DEAD/UNUSED":
            with pytest.raises(NotImplementedError):
                await bed.app_action(row["ui_action"])
            bed.write_command.assert_not_called()
            return
        await bed.app_action(row["ui_action"])
    literal = row["commands"][0] if row["commands"] else ""
    if not literal:
        bed.write_command.assert_not_called()
    else:
        expected_hex = next(v["hex"] for v in VECTORS if v["command"] == literal)
        assert bed.write_command.await_count == 1
        assert bed.write_command.await_args.args[0].hex() == expected_hex
        if row["ui_action"].endswith(("Up", "Down")) and "Massage" not in row["ui_action"]:
            assert bed.write_command.await_args.kwargs["repeat_delay_ms"] == 100
        if row["ui_action"].endswith("Save"):
            # The declared 3000 ms duration is never consumed by the app sender.
            assert bed.write_command.await_args.kwargs == {}


@pytest.mark.parametrize("model", BEDTECH_APP_PROFILES)
def test_model_setup_owns_its_axes_massage_and_timing(model):
    bed = controller(model)
    setup = setup_profile_for({CONF_BED_TYPE: "bedtech", CONF_PROTOCOL_VARIANT: model})
    assert setup is not None
    assert setup.owns[CONF_MOTOR_COUNT] == (4 if model == "bt6500" else 2)
    assert setup.owns[CONF_MOTOR_PULSE_DELAY_MS] == 100
    assert setup.owns[CONF_HAS_MASSAGE] == bed.supports_massage
    assert supports_single_address_pairing("bedtech", model) == model.endswith("fh")
    assert [spec.key for spec in bed.motor_control_specs] == (
        ["back", "legs", "head", "lumbar"] if model == "bt6500" else ["back", "legs"]
    )
    assert bed.execution.hold == "stream"
    assert not bed.execution.concurrent


async def test_cancel_and_stop_never_emit_a_release_packet():
    bed = controller("bt3000fh")
    bed.write_command = AsyncMock(side_effect=asyncio.CancelledError)
    with bed.side_scope(SIDE_RIGHT), pytest.raises(asyncio.CancelledError):
        await bed.move_back_up()
    assert bed.write_command.await_count == 1
    bed.write_command.reset_mock(side_effect=True)
    await bed.stop_all()
    await bed.move_back_stop()
    await bed.move_legs_stop()
    bed.write_command.assert_not_called()


@pytest.mark.parametrize("model", BEDTECH_APP_PROFILES)
@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_real_wire_hold_ends_refresh_without_release(model, end):
    from tests.hold_lease_wire import intervals, leased_hold

    async def move(bed):
        await bed.move_back_up()

    wire = await leased_hold("bedtech", move, variant=model, end_after_s=2, end=end)
    assert len(wire.held) >= 20
    assert intervals(wire.held) == {100}
    assert not wire.after
    expected = "6e01002998" if model.endswith("fh") else "6e01002493"
    assert {write.data.hex() for write in wire.held} == {expected}


@pytest.mark.parametrize("model", ["bt2000", "bt3000fh"])
async def test_explicit_connection_test_uses_first_head_for_two_seconds(model):
    from tests.hold_lease_wire import _tool

    tool = _tool()
    scenario = next(s for s in tool.build_scenarios() if s.id == f"bedtech:{model}")
    layout = json.loads(tool.LAYOUTS_PATH.read_text())["bedtech"]
    clock = tool.FakeClock()
    recorder = tool.Recorder(clock)
    with tool.virtual_time(clock):
        bed = await tool._build(scenario, tool.FakeClient(recorder, layout, scenario.replies))
        await tool._connect(bed, recorder, clock)
        recorder.events.clear()
        clock.begin_phase()
        await bed.app_action("connectionTest")
        writes = [event for event in recorder.events if isinstance(event[2], bool)]
    assert 1.99 <= clock.now <= 2.01
    assert len(writes) == 20
    assert {event[3].hex() for event in writes} == {"6e01002493"}


def single_address_pair():
    from tests.test_paired_coordinator import TestSingleAddressCoordinator

    def make(inner):
        inner.entry = MagicMock()
        inner.entry.data = {CONF_PROTOCOL_VARIANT: "bt3000fh"}
        return BedTechController(inner, "bt3000fh")

    return TestSingleAddressCoordinator()._scheduled_coordinator("bedtech", make)


@pytest.mark.parametrize("replacement", ["command", "stop", "motor_stop"])
@pytest.mark.parametrize("old_side", [SIDE_LEFT, SIDE_BOTH])
async def test_fh_other_bank_replaces_the_single_physical_timer(replacement, old_side):
    pair, inner = single_address_pair()
    started = asyncio.Event()
    stopped = asyncio.Event()
    calls = []

    async def old(bed):
        from custom_components.adjustable_bed.command_scheduler import current_command_context
        context = current_command_context()
        assert context is not None
        calls.append(("old", bed.command_side))
        started.set()
        await context.cancel_event.wait()
        stopped.set()

    async def new(bed):
        calls.append(("new", bed.command_side))

    task = asyncio.create_task(pair.async_execute_controller_command(old, side=old_side, resource="motor:back"))
    await started.wait()
    if replacement == "stop":
        await asyncio.wait_for(pair.async_stop_command(side=SIDE_RIGHT), 1)
    elif replacement == "motor_stop":
        await asyncio.wait_for(pair.async_stop_motor(new, "motor:legs", side=SIDE_RIGHT), 1)
    else:
        await asyncio.wait_for(pair.async_execute_controller_command(new, side=SIDE_RIGHT, resource="light", cancel_running=False), 1)
    await asyncio.wait_for(task, 1)
    assert stopped.is_set()
    assert inner.prepared_scopes == [] or all(scope == frozenset({"*"}) for scope in inner.prepared_scopes)
    assert pair.children[SIDE_LEFT]._scoped_command_resources("motor:back") == frozenset({"*"})
    assert pair.children[SIDE_RIGHT]._scoped_command_resources("motor:legs") == frozenset({"*"})
