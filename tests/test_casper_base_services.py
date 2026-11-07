"""Casper Base all-target validation, paired routing, and scheduler contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.casper_base import CasperBaseController
from custom_components.adjustable_bed.casper_base_protocol import Event, Request
from custom_components.adjustable_bed.casper_base_services import (
    async_register_casper_base_services,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def target():
    ctrl = MagicMock(
        spec=CasperBaseController,
        supports_casper_base_controls=True,
        validate_casper_base_request=MagicMock(),
        async_execute_casper_base_request=AsyncMock(),
    )
    c = MagicMock(spec=AdjustableBedCoordinator)
    c.controller = c.capability_controller = ctrl
    c.controller_side = None

    async def execute(command, **kw):
        await command(ctrl)

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    return c, ctrl


@pytest.fixture
async def targets(hass):
    async_register_casper_base_services(hass)
    a, b = target(), target()
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(a[0], "both"), (b[0], "both")], []),
    ):
        yield a, b


async def test_preflight_all_targets_before_any_write(hass, targets):
    (a, ac), (b, bc) = targets
    bc.validate_casper_base_request.side_effect = ValueError("unsupported product")
    with pytest.raises(ServiceValidationError, match="unsupported product"):
        await hass.services.async_call(
            DOMAIN,
            "casper_base",
            {"device_id": ["a", "b"], "operation": "rgb_power"},
            blocking=True,
        )
    a.async_execute_controller_command.assert_not_awaited()
    b.async_execute_controller_command.assert_not_awaited()
    ac.async_execute_casper_base_request.assert_not_awaited()


async def test_named_mode_and_nonpreemptive_configuration(hass, targets):
    (a, ac), _ = targets
    await hass.services.async_call(
        DOMAIN,
        "casper_base",
        {"device_id": "a", "operation": "alarm", "mode": "zero_g", "hour": 7, "minute": 30},
        blocking=True,
    )
    r = ac.async_execute_casper_base_request.await_args.args[0]
    assert r.mode == "ZeroGravity" and r.hour == 7 and r.minute == 30
    assert a.async_execute_controller_command.await_args.kwargs["resource"] == "configuration"
    assert a.async_execute_controller_command.await_args.kwargs["cancel_running"] is False


async def test_local_stop_preempts_pending_sensor_request(hass, targets):
    (a, _), _ = targets
    await hass.services.async_call(
        DOMAIN, "casper_base", {"device_id": "a", "operation": "sensor_stop"}, blocking=True
    )
    assert a.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


@pytest.mark.parametrize(
    "fields",
    [
        {"operation": "sensor_report", "month": 2, "day": 30},
        {"operation": "rgb_timer", "value": 1.5},
        {"operation": "sensor_part", "part": True},
    ],
)
async def test_invalid_actions_do_not_write(hass, targets, fields):
    (a, ac), _ = targets
    with pytest.raises((ServiceValidationError, ValueError, vol.Invalid)):
        await hass.services.async_call(
            DOMAIN, "casper_base", {"device_id": "a", **fields}, blocking=True
        )
    ac.async_execute_casper_base_request.assert_not_awaited()


async def test_real_coordinator_serializes_alarm_pair(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "bed_type": "casper_base",
            "protocol_variant": "nisconup355b",
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
        },
    )
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True, services=[])
    c._client.write_gatt_char = AsyncMock()
    ctrl = CasperBaseController(c, product="nisconup355b")
    c._controller = ctrl
    ctrl._consume(Event("clock_available", {}))
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def write(*args, **kwargs):
        assert c._command_lock.locked()
        calls.append(bytes(args[1]))
        if len(calls) == 1:
            entered.set()
            await release.wait()

    c._client.write_gatt_char.side_effect = write
    request = Request("alarm", hour=7, minute=30, mode="ZeroGravity")
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        first = asyncio.create_task(
            c.async_execute_controller_command(
                lambda _: ctrl.async_execute_casper_base_request(request),
                cancel_running=False,
                resource="configuration",
            )
        )
        await entered.wait()
        second = asyncio.create_task(
            c.async_execute_controller_command(
                lambda _: ctrl.async_perform_casper_base_action("MotorReset"), cancel_running=False
            )
        )
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        await asyncio.gather(first, second)
    assert len(calls) == 3
    assert calls[0][1] == 6 and calls[1][1] == 5 and calls[2][3] == 0x31
    c._cancel_disconnect_timer()


@pytest.fixture(autouse=True)
def no_protocol_waits(monkeypatch):
    real_sleep = asyncio.sleep

    async def immediate(_delay):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", immediate)
