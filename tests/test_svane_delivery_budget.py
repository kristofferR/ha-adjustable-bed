"""Public delivery outcomes at the exact delayed-feet hold boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.svane import FEET, HEAD, UP
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.services import async_register_services
from tests.test_svane import written
from tests.test_svane_services import target


@pytest.mark.parametrize("scenario", [
    "head_write_exhausts_budget", "feet_wait_exhausts_budget", "jmc_feet_wait_exhausts_budget",
    "nearby_complete", "cancelled", "released", "previous_feet_delivery",
])
async def test_registered_hold_reports_incomplete_delivery_and_preserves_normal_exits(
    hass, monkeypatch, scenario
):
    await async_register_services(hass)
    profile = "jmc" if scenario.startswith("jmc") else "multi"
    coordinator, controller = target(profile)
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)
    head = controller._role(HEAD, UP)
    feet = controller._role(FEET, UP)
    observed = []

    async def write(role, payload, **kwargs):
        observed.append((clock[0], role, bytes(payload)))
        if role is head and bytes(payload) == b"\x01\x00" and scenario in (
            "head_write_exhausts_budget", "nearby_complete"
        ):
            clock[0] += .002

    waits = 0

    async def advance(seconds):
        nonlocal waits
        waits += 1
        clock[0] += seconds
        if waits == 1:
            if scenario in ("feet_wait_exhausts_budget", "jmc_feet_wait_exhausts_budget"):
                clock[0] += .002
            elif scenario == "cancelled":
                controller._coordinator.cancel_command.set()
            elif scenario == "released":
                controller.request_svane_axis_release("feet")
        await asyncio.sleep(0)

    controller._motor_wait = advance
    controller.client.write_gatt_char.side_effect = write
    duration = .103 if scenario == "nearby_complete" else .201 if scenario == "previous_feet_delivery" else .101
    control = "feet_up" if "feet_wait" in scenario else "head_up_feet_up"
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        if scenario.endswith("exhausts_budget"):
            with pytest.raises(ServiceValidationError, match="selected feet axis could start"):
                await hass.services.async_call(DOMAIN, "svane_hold_control",
                    {"device_id": "bed", "control": control, "duration": duration}, blocking=True)
        else:
            await hass.services.async_call(DOMAIN, "svane_hold_control",
                {"device_id": "bed", "control": control, "duration": duration}, blocking=True)
    assert not controller._started
    assert not controller.ble_lock.locked()
    if scenario in ("nearby_complete", "previous_feet_delivery"):
        first_feet = next(time for time, role, payload in observed
                          if role is feet and payload == b"\x01\x00")
        assert first_feet == pytest.approx(.102 if scenario == "nearby_complete" else .1)
        assert written(controller)[-1][2] == "0000"
    else:
        assert not any(role is feet and payload == b"\x01\x00" for _, role, payload in observed)
        if control.startswith("head"):
            head_moves = 2 if scenario == "released" else 1
            assert [(role, payload) for _, role, payload in observed] == (
                [(head, b"\x01\x00")] * head_moves + [(head, b"\x00\x00")]
            )
        else:
            assert not observed
