"""Registered startup queries require fresh capabilities; version metadata is optional."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds import limoss_remote
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.limoss_remote_state import get_limoss_remote_session
from tests.test_coordinator_limoss_remote import actual_coordinator

CAPS = {"key_count": 8, "system": 18, "vibration": 255, "configuration": 0, "memory_count": 8}
REPLIES = {2: "0204220004", 0: "0001020304", 1: "0105060708"}


async def startup_controller(hass, monkeypatch, *, cached=True):
    # Accelerate only the host budget; native packet and repeat intervals remain intact.
    monkeypatch.setattr(limoss_remote, "_INFORMATION_TIMEOUT_SECONDS", 0.3)
    coordinator = actual_coordinator(
        hass, **{const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS} if cached else {}}
    )
    controller = await create_controller(
        coordinator, const.BED_TYPE_LIMOSS_REMOTE, None, coordinator.client
    )
    assert isinstance(controller, LimossRemoteController)
    coordinator._controller = controller
    return coordinator, controller


def respond(client, role, opcode):
    callback = client.start_notify.call_args.args[1]
    callback(role, bytearray(format_command(bytes.fromhex(REPLIES[opcode]), 0)))


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("missing", [0, 1])
async def test_registered_startup_admits_fresh02_with_missing_optional_version(
    hass, monkeypatch, cached, missing
):
    coordinator, controller = await startup_controller(hass, monkeypatch, cached=cached)
    client = coordinator.client
    emitted, times = [], []

    def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(opcode)
        times.append(asyncio.get_running_loop().time())
        if opcode != missing:
            respond(client, role, opcode)

    client.write_gatt_char.side_effect = write
    await coordinator.async_start_notify()
    assert emitted == ([2, 0] if missing == 0 else [2, 0, 1])
    assert all(b - a >= 0.075 for a, b in zip(times, times[1:], strict=False))
    assert controller.capabilities is not None
    assert controller.capabilities.system == 0x22 and controller.memory_slot_count == 4
    assert controller.layout == "cKey4"
    assert controller._notify_client is client and controller._request_reply is None
    client.stop_notify.assert_not_awaited()
    metadata = get_limoss_remote_session(coordinator.hass, coordinator.address).metadata
    assert metadata == ({} if missing == 0 else {"hardware_version": "12.34"})
    await controller.stop_notify()


@pytest.mark.parametrize("cached", [False, True])
async def test_registered_startup_never_uses_cache_without_fresh02(hass, monkeypatch, cached):
    coordinator, controller = await startup_controller(hass, monkeypatch, cached=cached)
    emitted = []
    coordinator.client.write_gatt_char.side_effect = lambda role, packet, **kwargs: emitted.append(
        LimossController._tea_decrypt(packet[1:9])[1]
    )
    with pytest.raises(TimeoutError, match="No matching app reply"):
        await coordinator.async_start_notify()
    assert emitted == [2]
    assert controller._notify_client is None and controller._request_reply is None
    coordinator.client.stop_notify.assert_awaited_once()
    assert controller.capabilities is not None if cached else controller.capabilities is None


@pytest.mark.parametrize("opcode", [0, 1])
@pytest.mark.parametrize("failure", ["error", "hang", "cancel", "disconnect"])
async def test_optional_version_write_and_owner_failures_still_fail_startup(
    hass, monkeypatch, opcode, failure
):
    coordinator, controller = await startup_controller(hass, monkeypatch)
    client = coordinator.client
    emitted = []
    transport_error = TimeoutError("ATT failure, not reply expiry")

    async def write(role, packet, **kwargs):
        command = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(command)
        if command != opcode:
            respond(client, role, command)
        elif failure == "error":
            raise transport_error
        elif failure == "hang":
            await asyncio.Event().wait()
        elif failure == "cancel":
            coordinator.cancel_command.set()
        else:
            controller.on_disconnect()
            client.is_connected = False
            respond(client, role, command)  # Delayed old-owner reply cannot rescue startup.

    client.write_gatt_char = AsyncMock(side_effect=write)
    error_type = {
        "error": TimeoutError, "hang": TimeoutError,
        "cancel": asyncio.CancelledError, "disconnect": ConnectionError,
    }[failure]
    with pytest.raises(error_type) as error:
        await coordinator.async_start_notify()
    if failure == "error":
        assert error.value is transport_error
    assert emitted == ([2, 0] if opcode == 0 else [2, 0, 1])
    assert controller._notify_client is None and controller._request_reply is None
    assert controller._request_active is None and controller._progress is None


async def test_explicit_refresh_keeps_strict_optional_reply_failure(hass, monkeypatch):
    coordinator, controller = await startup_controller(hass, monkeypatch)
    client = coordinator.client
    client.write_gatt_char.side_effect = lambda role, packet, **kwargs: respond(
        client, role, LimossController._tea_decrypt(packet[1:9])[1]
    )
    await coordinator.async_start_notify()
    client.write_gatt_char.reset_mock()

    def write(role, packet, **kwargs):
        if LimossController._tea_decrypt(packet[1:9])[1] == 2:
            respond(client, role, 2)

    client.write_gatt_char.side_effect = write
    with pytest.raises(TimeoutError, match="No matching app reply"):
        await controller.refresh_device_info()
    assert [LimossController._tea_decrypt(c.args[1][1:9])[1] for c in client.write_gatt_char.call_args_list] == [2, 0]
    assert controller._notify_client is client
    await controller.stop_notify()


@pytest.mark.parametrize("opcode", [0, 1])
async def test_caller_task_cancel_during_optional_wait_preserves_cleanup(hass, monkeypatch, opcode):
    coordinator, controller = await startup_controller(hass, monkeypatch)
    client = coordinator.client
    entered = asyncio.Event()

    def write(role, packet, **kwargs):
        command = LimossController._tea_decrypt(packet[1:9])[1]
        if command == opcode:
            entered.set()
        else:
            respond(client, role, command)

    client.write_gatt_char.side_effect = write
    startup = asyncio.create_task(coordinator.async_start_notify())
    await entered.wait()
    startup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await startup
    client.stop_notify.assert_awaited_once()
    assert controller._request_active is None and controller._notify_client is None
    assert not coordinator.cancel_command.is_set()
    metadata = get_limoss_remote_session(coordinator.hass, coordinator.address).metadata
    assert metadata == ({} if opcode == 0 else {"hardware_version": "12.34"})


async def test_pre_query_version_reply_cannot_launch_software_query(hass, monkeypatch):
    coordinator, controller = await startup_controller(hass, monkeypatch)
    client = coordinator.client
    emitted = []

    def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(opcode)
        if opcode == 2:
            respond(client, role, 0)  # Native diagnostics may retain this; it isn't query00's reply.
            respond(client, role, 2)

    client.write_gatt_char.side_effect = write
    await coordinator.async_start_notify()
    assert emitted == [2, 0]
    assert controller._notify_client is client and controller._request_active is None
    await controller.stop_notify()


@pytest.mark.parametrize("late_reply_opcode", [2, 0])
@pytest.mark.parametrize("strict", [False, True])
async def test_optional_phase_admission_respects_remaining_native_pacing(
    hass, monkeypatch, late_reply_opcode, strict
):
    coordinator, controller = await startup_controller(hass, monkeypatch, cached=False)
    budget = 0.06 if late_reply_opcode == 2 else 0.13
    monkeypatch.setattr(limoss_remote, "_INFORMATION_TIMEOUT_SECONDS", budget)
    client = coordinator.client
    emitted, starts = [], []

    async def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(opcode)
        starts.append(asyncio.get_running_loop().time())
        if opcode == late_reply_opcode:
            await asyncio.sleep(0.02)  # Host-only reply delay; native80ms remains unchanged.
        respond(client, role, opcode)

    client.write_gatt_char.side_effect = write
    if strict:
        # Public refresh retains the old strict admission/write deadline contract.
        client.start_notify.side_effect = None
        await client.start_notify(controller.client.services[0].characteristics[0], controller._notification)
        with pytest.raises(TimeoutError) as error:
            await controller.refresh_device_info()
        assert not isinstance(error.value, limoss_remote._ReplyWaitTimeout)
    else:
        await coordinator.async_start_notify()
        assert controller._notify_client is client and controller._request_active is None
        client.stop_notify.assert_not_awaited()
    assert emitted == ([2] if late_reply_opcode == 2 else [2, 0])
    assert starts[-1] + 0.08 >= starts[0] + budget
    assert controller.capabilities is not None and controller.capabilities.system == 0x22
    metadata = get_limoss_remote_session(coordinator.hass, coordinator.address).metadata
    assert metadata == ({} if late_reply_opcode == 2 else {"hardware_version": "12.34"})
    await controller.stop_notify()


@pytest.mark.parametrize("late_reply_opcode", [2, 0])
@pytest.mark.parametrize("failure", ["cancel", "disconnect", "replace", "generation"])
async def test_optional_phase_skip_never_admits_cancelled_or_stale_subscription(
    hass, monkeypatch, late_reply_opcode, failure
):
    coordinator, controller = await startup_controller(hass, monkeypatch, cached=False)
    monkeypatch.setattr(
        limoss_remote, "_INFORMATION_TIMEOUT_SECONDS", 0.06 if late_reply_opcode == 2 else 0.13
    )
    client = coordinator.client
    emitted = []

    async def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(opcode)
        if opcode == late_reply_opcode:
            await asyncio.sleep(0.02)
        respond(client, role, opcode)
        if opcode == late_reply_opcode:
            if failure == "cancel":
                coordinator.cancel_command.set()
            elif failure == "disconnect":
                client.is_connected = False
                controller.on_disconnect()
            elif failure == "replace":
                from tests.test_limoss_remote import make_controller
                coordinator._client = make_controller().client
            else:
                controller._notify_generation += 1

    client.write_gatt_char.side_effect = write
    expected = asyncio.CancelledError if failure == "cancel" else ConnectionError
    with pytest.raises(expected):
        await coordinator.async_start_notify()
    assert emitted == ([2] if late_reply_opcode == 2 else [2, 0])
    assert controller._notify_client is None and controller._request_active is None
    assert controller._request_reply is None and controller._progress is None


@pytest.mark.parametrize("blocked", ["lane", "pacing"])
async def test_admitted_optional_phase_still_fails_when_write_budget_expires(
    hass, monkeypatch, blocked
):
    coordinator, controller = await startup_controller(hass, monkeypatch, cached=False)
    client = coordinator.client
    release = asyncio.Event()
    holders: list[asyncio.Task[None]] = []
    emitted = []

    async def hold_lane():
        async with controller._ble_lock:
            await release.wait()

    async def pacing(seconds, event=None):
        await release.wait()

    def write(role, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        emitted.append(opcode)
        respond(client, role, opcode)
        if opcode == 2:
            if blocked == "lane":
                holders.append(asyncio.create_task(hold_lane()))
            else:
                controller._sleep = pacing

    client.write_gatt_char.side_effect = write
    try:
        with pytest.raises(TimeoutError) as caught:
            await coordinator.async_start_notify()
        assert not isinstance(caught.value, limoss_remote._ReplyWaitTimeout)
        assert emitted == [2]
        assert controller._notify_client is None and controller._request_active is None
        client.stop_notify.assert_awaited_once()
    finally:
        release.set()
        for holder in holders:
            await holder
