"""BedTech review findings exercised through physical admission and entity builders."""

from __future__ import annotations

import asyncio
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.bedtech.controller import BedTechController
from custom_components.adjustable_bed.button import (
    AdjustableBedButton,
    ControllerActionButton,
    _button_entities_for,
)
from custom_components.adjustable_bed.command_scheduler import (
    CommandKind,
    DeviceCommandScheduler,
    current_command_context,
)
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.profiles.richmat import BEDTECH_APP_PROFILES
from custom_components.adjustable_bed.select import (
    AdjustableBedMassageTimerSelect,
    _select_entities_for,
)
from tests.test_bedtech_app import controller


def physical(model):
    bed = controller(model)
    runtime = SimpleNamespace(
        capability_controller=bed,
        _bed_type="bedtech",
        _command_scheduler=DeviceCommandScheduler("physical-bed"),
        _cancel_command=asyncio.Event(),
        _cancel_counter=0,
    )
    runtime._protocol_command_resources = MethodType(
        AdjustableBedCoordinator._protocol_command_resources, runtime
    )
    runtime._build_command_intent = MethodType(
        AdjustableBedCoordinator._build_command_intent, runtime
    )
    return runtime


@pytest.mark.parametrize("model", BEDTECH_APP_PROFILES)
@pytest.mark.parametrize("replacement", ["motor:legs", "light"])
async def test_standalone_app_command_replaces_another_axis_even_without_caller_cancel(
    model, replacement
):
    runtime = physical(model)
    started = asyncio.Event()
    ended = asyncio.Event()
    calls = []

    async def old():
        context = current_command_context()
        assert context is not None
        started.set()
        await context.cancel_event.wait()
        ended.set()

    async def new():
        calls.append(replacement)

    scheduler = runtime._command_scheduler
    task = asyncio.create_task(
        scheduler.execute(
            runtime._build_command_intent(
                old,
                resource="motor:back",
                kind=CommandKind.COMMAND,
                cancel_running=True,
            )
        )
    )
    await started.wait()
    await asyncio.wait_for(
        scheduler.execute(
            runtime._build_command_intent(
                new,
                resource=replacement,
                kind=CommandKind.COMMAND,
                cancel_running=False,
            )
        ),
        1,
    )
    await asyncio.wait_for(task, 1)
    assert ended.is_set()
    assert calls == [replacement]


@pytest.mark.parametrize("model", ["auto", "bt3000"])
async def test_single_stream_policy_keeps_physical_receivers_independent(model):
    first, second = physical(model), physical(model)
    started = asyncio.Event()
    release = asyncio.Event()
    observed = []

    async def old():
        context = current_command_context()
        assert context is not None
        observed.append(context)
        started.set()
        await release.wait()

    task = asyncio.create_task(
        second._command_scheduler.execute(
            second._build_command_intent(
                old,
                resource="motor:back",
                kind=CommandKind.COMMAND,
                cancel_running=True,
            )
        )
    )
    await started.wait()
    await first._command_scheduler.execute(
        first._build_command_intent(
            AsyncMock(),
            resource="light",
            kind=CommandKind.COMMAND,
            cancel_running=False,
        )
    )
    assert not observed[0].cancel_event.is_set()
    release.set()
    await task


def test_legacy_keeps_caller_replacement_and_resource_policy():
    runtime = physical("auto")
    intent = runtime._build_command_intent(
        AsyncMock(), resource="motor:legs", kind=CommandKind.COMMAND, cancel_running=False
    )
    assert not intent.cancel_running
    assert intent.resources == frozenset({"motor:legs"})


@pytest.mark.parametrize("model", [*BEDTECH_APP_PROFILES, "auto"])
@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT])
async def test_real_entity_builders_gate_lights_and_expose_only_the_supported_timer_button(
    hass, model, side
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
            CONF_BED_TYPE: "bedtech",
            CONF_PROTOCOL_VARIANT: model,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
        },
    )
    entry.add_to_hass(hass)
    runtime = AdjustableBedCoordinator(hass, entry)
    bed = BedTechController(runtime, model)
    runtime._controller = bed
    bed.write_command = AsyncMock()

    async def execute(command, **_kwargs):
        await command(bed)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    with bed.side_scope(side):
        buttons = _button_entities_for(hass, runtime)
        lights = _light_entities_for(hass, runtime)
        selects = _select_entities_for(hass, runtime)
        toggle_buttons = [
            entity
            for entity in buttons
            if isinstance(entity, AdjustableBedButton)
            and entity.entity_description.key == "toggle_light"
        ]
        supported_light = model in {
            "bt3000",
            "bt3000fh",
            "bt6500",
            "btx5",
            "btx5fh",
            "auto",
        } and not (model == "btx5fh" and side == SIDE_RIGHT)
        assert bool(toggle_buttons) == supported_light
        assert bool(lights) == supported_light
        assert not any(isinstance(entity, AdjustableBedMassageTimerSelect) for entity in selects)
        timers = [
            entity
            for entity in buttons
            if isinstance(entity, ControllerActionButton)
            and entity._spec.key == "bedtech_massage_timer_20"
        ]
        assert bool(timers) == (model in {"bt3000", "btx5", "btx5fh"})
        if timers:
            await timers[0].async_press()
            assert bed.write_command.await_args.args[0].hex() == "6e010063d2"
