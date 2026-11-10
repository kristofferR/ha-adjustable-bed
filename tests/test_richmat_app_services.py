"""Richmat services use restored preferences and the live scheduler/connection lane."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat_app import controller as bed
from custom_components.adjustable_bed.beds.richmat_app.services import (
    async_register_richmat_app_services,
)
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_RICHMAT_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Richmat app",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:73",
            CONF_NAME: "Richmat app",
            CONF_BED_TYPE: BED_TYPE_RICHMAT_APP,
            CONF_PROTOCOL_VARIANT: getattr(request, "param", "7IRM"),
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = target
    route = codec.TRANSPORTS["w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, properties=["write"], handle=73, descriptors=[])
    rx = SimpleNamespace(uuid=route.notify_uuid, properties=["notify"], handle=74, descriptors=[])
    mock_bleak_client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])
    ]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    # Advance only the protocol's waits, yielding so real scheduler tasks run.
    now = [0.0]
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await real_sleep(0)

    async def wait(self, seconds, cancel):
        await sleep(seconds)
        return not cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed.RichmatAppController, "_wait", wait)
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, bed.RichmatAppController)
    async_register_richmat_app_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, "both")], []),
    ):
        yield target, mock_bleak_client
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


async def invoke(hass, operation, **fields):
    await hass.services.async_call(
        DOMAIN, "richmat_app", {"device_id": "bed", "operation": operation, **fields}, blocking=True
    )


@pytest.mark.parametrize("side", ["right", "both"])
async def test_real_connect_and_idle_reconnect_preserve_selected_side_and_stop(hass, runtime, side):
    target, client = runtime
    offline = target.capability_controller
    selector = AdjustableBedControllerSelect(target, offline.controller_select_specs[0])
    await selector.async_select_option(side)
    await target.async_write_app_state(offline, offline.persisted_app_state)
    expected = 1 if side == "right" else 2
    for _ in range(2):
        assert await target.async_connect()
        live = target.controller
        assert live._side() == expected
        assert target.controller_state[bed.SIDE] == side
        assert live.local["side"] == expected
        client.write_gatt_char.reset_mock()
        selector = AdjustableBedControllerSelect(target, live.controller_select_specs[0])

        async def change_selection(*args, select=selector, **kwargs):
            await select.async_select_option("left")

        client.write_gatt_char.side_effect = change_selection
        await target.async_execute_controller_command(
            lambda c: c.hold_control("richmat_app_cb18d1", 200), resource="motor:*"
        )
        frames = written(client)
        assert len(frames) == 3
        assert all(bytes.fromhex(frame)[2] == expected for frame in frames)
        assert bytes.fromhex(frames[-1])[3] == 110
        client.write_gatt_char.side_effect = None
        await selector.async_select_option(side)
        await target.async_disconnect("idle_timeout")
        assert not target.is_connected


async def test_registered_cycling_demo_is_cancelled_by_real_cover_stop_before_wire_lock(
    hass, runtime
):
    target, client = runtime
    assert await target.async_connect()
    live = target.controller
    cover = AdjustableBedCover(target, _build_cover_description(live.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    movement = asyncio.Event()
    cleanup = asyncio.Event()
    finish_cleanup = asyncio.Event()
    cancellation = None

    async def write(_char, data, **kwargs):
        nonlocal cancellation
        if data[3] == 36:
            cancellation = target.cancel_command
            movement.set()
        elif data[3] == 110:
            if not cleanup.is_set():
                assert cancellation.is_set()
                assert target._command_lock.locked()
                cleanup.set()
                await finish_cleanup.wait()

    client.write_gatt_char.side_effect = write
    demo = asyncio.create_task(
        invoke(
            hass,
            "demo",
            steps=[{"action": "deviceFunctionItemHeadUp", "sustain": True, "seconds": 60}],
            cycle=True,
        )
    )
    stop = None
    try:
        async with asyncio.timeout(2):
            await movement.wait()
            stop = asyncio.create_task(cover.async_stop_cover())
            await cleanup.wait()
            assert cancellation.is_set() and not stop.done()
            finish_cleanup.set()
            await asyncio.gather(demo, stop)
        assert written(client)[0] == "6e01002493"
        assert written(client)[-2:] == ["6e01006edd", "6e01006edd"]
        assert live.local["demo_running"] is False
        assert not target._command_lock.locked()
    finally:
        finish_cleanup.set()
        for task in (demo, stop):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (demo, stop) if t is not None), return_exceptions=True)


@pytest.mark.parametrize(
    "runtime,operation,ack,packet",
    [
        ("LURN", "light_timer", "6e0e00037f", "6e0bffff77"),
        ("A5RN", "cancel_alarm", "6e09010078", "6e05000073"),
        ("7IRM", "detection", "6e90c101c0", "6e88c210c8"),
    ],
    indirect=["runtime"],
)
@pytest.mark.parametrize("state", ["initially_offline", "idle_disconnected", "negative_reply"])
async def test_registered_service_refreshes_live_capabilities_before_rejection(
    hass, runtime, operation, ack, packet, state
):
    target, client = runtime
    assert not target.is_connected
    assert target.capability_controller.features == set()
    if state in ("idle_disconnected", "negative_reply"):

        async def previous_reply(_char, callback):
            asyncio.get_running_loop().call_soon(callback, None, bytearray.fromhex(ack))

        client.start_notify.side_effect = previous_reply
        assert await target.async_connect()
        assert target.controller.features
        await target.async_disconnect("idle_timeout")
    client.write_gatt_char.reset_mock()

    async def notify(_char, callback):
        if state != "negative_reply":
            asyncio.get_running_loop().call_soon(callback, None, bytearray.fromhex(ack))

    client.start_notify.side_effect = notify
    if state == "negative_reply":
        with pytest.raises(ServiceValidationError, match="capability acknowledgement"):
            await invoke(hass, operation)
    else:
        await invoke(hass, operation)
    assert target.is_connected and client.start_notify.await_count >= 1
    assert (packet in written(client)) is (state != "negative_reply")
    assert not target._command_lock.locked()


@pytest.mark.parametrize("runtime", ["LURN"], indirect=True)
async def test_live_preflight_validates_every_target_before_any_requested_write(hass, runtime):
    first, client = runtime

    async def notify(_char, callback):
        asyncio.get_running_loop().call_soon(callback, None, bytearray.fromhex("6e0e00037f"))

    client.start_notify.side_effect = notify
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:74",
            CONF_BED_TYPE: BED_TYPE_RICHMAT_APP,
            CONF_PROTOCOL_VARIANT: "7IRM",
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    other_entry.add_to_hass(hass)
    second = AdjustableBedCoordinator(hass, other_entry)
    other_client = MagicMock()
    other_client.is_connected = True
    other_client.services = client.services
    other_client.start_notify = AsyncMock()
    other_client.stop_notify = AsyncMock()
    other_client.write_gatt_char = AsyncMock()
    other_client.disconnect = AsyncMock(
        side_effect=lambda: setattr(other_client, "is_connected", False)
    )
    second._client = other_client
    second._controller = bed.RichmatAppController(second, product="7IRM")
    await second._controller.start_notify()
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (second, "both")], []),
            ),
            pytest.raises(ServiceValidationError, match="capability acknowledgement"),
        ):
            await invoke(hass, "light_timer")
        assert first.is_connected and first.controller.features
        assert "6e0bffff77" not in written(client) + written(other_client)
    finally:
        await second.async_shutdown()


@pytest.mark.parametrize("runtime", ["HMRN"], indirect=True)
@pytest.mark.parametrize(
    "mode,zone,temperature,expected", [(2, 1, 40, (40, 35)), (1, 2, 20, (22, 20))]
)
async def test_blanket_temperature_hydrates_current_settings_after_connect_and_reconnect(
    hass, runtime, mode, zone, temperature, expected
):
    from custom_components.adjustable_bed.beds.richmat_app import protocol as p

    target, client = runtime
    notification = None

    async def subscribe(_char, callback):
        nonlocal notification
        notification = callback
        asyncio.get_running_loop().call_soon(
            callback, None, bytearray(codec.record_20_len(13, 1, 2, (0, 1)))
        )

    async def write(_char, data, **kwargs):
        if data == p.QUERY["blanket"]:
            current = codec.record_20_len(
                13, 5, 2, (0, mode, 22 if mode == 1 else 30, 35 if mode == 2 else 24)
            )
            asyncio.get_running_loop().call_soon(notification, None, bytearray(current))

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.side_effect = write
    for _ in range(2):
        await invoke(hass, "blanket_temperature", zone=zone, temperature=temperature)
        frames = written(client)
        query = p.QUERY["blanket"].hex()
        setting = p.extended(13, 5, mode, *expected).hex()
        assert frames.count(query) == 1
        assert frames[-1] == setting and frames.index(query) < frames.index(setting)
        live = target.controller
        assert live._blanket_mode_received.is_set()
        await target.async_disconnect("idle_timeout")
        assert not live._blanket_mode_received.is_set()
        client.write_gatt_char.reset_mock()
