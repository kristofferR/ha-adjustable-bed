"""Report transfers own the actual coordinator link only until they settle."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.adjustable_bed.beds.richmat_app import sleep as bed
from custom_components.adjustable_bed.beds.richmat_app.requests import Request
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT_APP_SLEEP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, monkeypatch):
    variant, quick = getattr(request, "param", ("hj", True))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:74",
            CONF_BED_TYPE: BED_TYPE_RICHMAT_APP_SLEEP,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: quick,
            CONF_IDLE_DISCONNECT_SECONDS: 2,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    client = mock_bleak_client
    tx = SimpleNamespace(uuid=bed.TX, properties=["write", "write-without-response"], handle=73, descriptors=[])
    rx = SimpleNamespace(uuid=bed.RX, properties=["notify"], handle=74, descriptors=[])
    client.services = [SimpleNamespace(uuid=bed.SERVICES[0], characteristics=[tx, rx])]
    client.mtu_size = 185
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    real_sleep = asyncio.sleep

    async def no_protocol_wait(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(bed.asyncio, "sleep", no_protocol_wait)
    assert await target.async_connect()
    assert isinstance(target.controller, bed.SleepController)
    try:
        yield target, client
    finally:
        await target.async_shutdown()


async def report(target):
    await target.async_execute_controller_command(
        lambda c: c.execute_request(Request("sleep_report", when=dt_util.now(), part=12))
    )


async def advance(hass, seconds):
    # Execute real TimerHandles without waiting on either wire or idle timers.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


async def metadata(hass, client, size):
    notify = client.start_notify.await_args.args[1]
    notify(None, bytearray(bed.packet(1, "q_report", {"fsize": size})))
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize("runtime", [(v, q) for v in ("mm", "hj") for q in (True, False)], indirect=True)
async def test_report_retains_link_beyond_handoff_and_idle_until_final_chunk(hass, runtime):
    target, client = runtime
    live = target.controller
    await report(target)
    assert live.requires_persistent_connection and target._disconnect_timer is None
    await advance(hass, 5)
    client.disconnect.assert_not_awaited()
    packed = gzip.compress(json.dumps({"algorithmVersion": "0.0.3.0"}).encode())
    await metadata(hass, client, len(packed))
    assert live.receiver.current == "q_report_allow"
    # The notification's follow-up has returned, while the transfer is still live.
    assert not live._tasks and target._disconnect_timer is None
    notify = client.start_notify.await_args.args[1]
    prefix = bytes(14) if not live.mm else b""
    notify(None, bytearray(prefix + packed[:8]))
    await advance(hass, 5)
    assert live.receiver.buffer == packed[:8] and target.is_connected
    client.disconnect.assert_not_awaited()
    notify(None, bytearray(prefix + packed[8:]))
    assert live.state["report_transfer"]["compressed_bytes"] == len(packed)
    assert not live.requires_persistent_connection and live._report_timeout is None
    assert target._disconnect_timer is not None
    await advance(hass, 5)
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("operation", ["sleep_cancel", "stop"])
async def test_report_cancellation_releases_the_actual_link(hass, runtime, operation):
    target, client = runtime
    live = target.controller
    await report(target)
    timer = live._report_timeout
    await metadata(hass, client, 100)
    if operation == "stop":
        await target.async_stop_command()
    else:
        await target.async_execute_controller_command(lambda c: c.execute_request(Request(operation)))
    assert timer.cancelled() and live._report_context is None
    assert not live.requires_persistent_connection and live.receiver.current is None
    await advance(hass, 5)
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("stage", ["metadata", "transfer"])
async def test_report_watchdog_releases_stalled_handshake_or_transfer(hass, runtime, stage):
    target, client = runtime
    live = target.controller
    await report(target)
    if stage == "transfer":
        await metadata(hass, client, 100)
        client.start_notify.await_args.args[1](None, bytearray(bytes(14) + b"partial"))
    await advance(hass, bed.REPORT_TIMEOUT_S + 1)
    assert live.state["rejection"] == "Sleep report transfer timed out"
    assert not live.requires_persistent_connection
    assert live.receiver.current is None and not live.receiver.buffer
    await advance(hass, 5)
    client.disconnect.assert_awaited_once()


async def test_old_subscription_and_watchdog_cannot_touch_a_new_report(hass, runtime):
    target, client = runtime
    live = target.controller
    await report(target)
    old_notify = client.start_notify.await_args.args[1]
    old_timeout = live._report_timeout
    expire, expire_args = old_timeout._callback, old_timeout._args
    # Reuse the very same BleakClient: identity alone does not fence old callbacks.
    await target.async_execute_controller_command(lambda c: c.start_notify())
    assert old_timeout.cancelled()
    await report(target)
    current, timer = live._report_context, live._report_timeout
    old_notify(None, bytearray(bed.packet(1, "q_report", {"fsize": 100})))
    expire(*expire_args)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert live._report_context is current and live._report_timeout is timer
    assert live.receiver.current == "q_report" and live.receiver.report_size == 0
    assert live.requires_persistent_connection and "rejection" not in live.state
    assert target._disconnect_timer is None
    # A superseded operation's watchdog is also harmless within the same session.
    expire, expire_args = timer._callback, timer._args
    await report(target)
    current, timer = live._report_context, live._report_timeout
    expire(*expire_args)
    assert live._report_context is current and live._report_timeout is timer
    await metadata(hass, client, 100)
    assert live.receiver.current == "q_report_allow"


async def test_failed_report_write_does_not_retain_connection(hass, runtime):
    target, client = runtime
    live = target.controller
    client.write_gatt_char.side_effect = OSError("failed report query")
    with pytest.raises(OSError, match="failed report query"):
        await report(target)
    assert not live.requires_persistent_connection
    assert live._report_context is None and live._report_timeout is None
