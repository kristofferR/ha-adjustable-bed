"""Public resolved-profile timed movement and delivered JMC feet tracking."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.adjustable_bed.beds.jensen_linon import JensenLinonController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    DOMAIN,
    SIDE_BOTH,
    SVANE_VARIANT_JENSEN_LINON,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from tests.test_svane import written
from tests.test_svane_light_timed_host import runtime as svane_runtime

runtime = svane_runtime


@pytest.mark.parametrize("runtime", ["multi"], indirect=True)
@pytest.mark.parametrize("motor", ["back", "legs"])
async def test_registered_timed_move_accepts_factory_resolved_jensen_linon(
    hass, runtime, monkeypatch, motor
):
    coordinator, previous = runtime
    controller = await create_controller(
        coordinator, BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON, previous.client
    )
    assert isinstance(controller, JensenLinonController)
    assert coordinator.bed_type == BED_TYPE_SVANE
    coordinator._controller = controller
    waits = []

    async def yield_hold(seconds):
        waits.append(seconds)
        await asyncio.sleep(0)

    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.sleep = yield_hold
    monkeypatch.setattr("custom_components.adjustable_bed.beds.jensen_linon.asyncio", local_asyncio)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": "bed", "motor": motor, "direction": "up", "duration_ms": 200,
        }, blocking=True)
    packets = written(controller)
    assert packets and packets[0][2] == "01"
    assert packets[-2:] == [
        (previous.client.services[0].uuid, previous.client.services[0].characteristics[0].uuid, "ff"),
        (previous.client.services[1].uuid, previous.client.services[1].characteristics[0].uuid, "ff"),
    ]
    assert waits and all(seconds == .8 for seconds in waits)
    assert not coordinator._command_lock.locked()


@pytest.mark.parametrize("runtime", ["jmc"], indirect=True)
@pytest.mark.parametrize("control,first_frame", [
    ("head_up_feet_up", "101100000000"),
    ("head_up_feet_down", "102100000000"),
])
async def test_public_head_release_near_deadline_keeps_delivered_jmc_feet_success(
    hass, runtime, monkeypatch, control, first_frame
):
    coordinator, controller = runtime
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)
    released = False

    async def wait(seconds):
        nonlocal released
        if not released:
            assert written(controller)[0][2] == first_frame
            clock[0] = .12
            await hass.services.async_call(DOMAIN, "svane_release_axis", {
                "device_id": "bed", "motor": "head",
            }, blocking=True)
            released = True
        else:
            clock[0] += seconds
        await asyncio.sleep(0)

    controller._motor_wait = wait
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "svane_hold_control", {
            "device_id": "bed", "control": control, "duration": .2,
        }, blocking=True)
    assert released and clock[0] == pytest.approx(.2)
    assert [p for _, _, p in written(controller)] == [first_frame, "100000000000"]
    assert not controller._started and not coordinator._command_lock.locked()
