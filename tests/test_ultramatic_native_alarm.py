"""Native Both alarm plans through HA's real parent and child device targets."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _async_ensure_paired_device_registry
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.paired_devices import side_identifier
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data
from custom_components.adjustable_bed.profiles import ultramatic as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_ultramatic_runtime import ALARM_REPORT, connected, make_client, writes

MATCHING = bytes.fromhex("ed8003017f0106300001027f0106300001")
SET = {"time": "21:09:00", "weekdays": ["monday"], "wake_action": "zero_g", "enabled": False}


@pytest.fixture
async def native_alarm(hass):
    inner, client = await connected(hass)
    standalone, other_client = await connected(hass, address="AA:BB:CC:DD:EE:77")
    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_single_address_pair_entry_data(dict(inner.entry.data), name="Ultramatic sides"),
    )
    pair_entry.add_to_hass(hass)
    pair_entry.mock_state(hass, ConfigEntryState.LOADED)
    standalone.entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = SingleAddressPairedCoordinator(hass, pair_entry, inner)
    hass.data.setdefault(DOMAIN, {}).update(
        {pair_entry.entry_id: pair, standalone.entry.entry_id: standalone}
    )
    _async_ensure_paired_device_registry(hass, pair_entry, pair)
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(
        next(iter(pair.device_info["identifiers"])), pair_entry.entry_id
    )
    assert parent is not None
    devices = {"parent": parent.id}
    for side in ("left", "right"):
        device = registry.async_get_child_device_by_identifier(
            side_identifier(pair, side), pair_entry.entry_id
        )
        assert isinstance(device, dr.ChildDeviceEntry)
        devices[side] = device.id
    devices["standalone"] = registry.async_get_or_create_from_info(
        config_entry_id=standalone.entry.entry_id, device_info=standalone.device_info
    ).id
    await async_register_services(hass)
    try:
        with ExitStack() as stack:
            for coordinator in (inner, standalone):
                coordinator._disconnect_after_command = True
                stack.enter_context(
                    patch.object(
                        coordinator, "async_ensure_connected", AsyncMock(return_value=True)
                    )
                )
                stack.enter_context(
                    patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
                )
            yield hass, pair, inner, client, standalone, other_client, devices
    finally:
        await pair.async_shutdown()
        await standalone.async_shutdown()


@contextmanager
def clocked(hass):
    with virtual_clock(), patch.object(hass, "loop", asyncio.get_running_loop()):
        yield


async def alarm(hass, device_ids, operation):
    """Set the whole alarm, or turn off the reported one (no time), through set_alarm."""
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {"device_id": device_ids, **(SET if operation == "set" else {"enabled": False})},
        blocking=True,
    )


def report(client, data=MATCHING):
    client.start_notify.await_args.args[1](None, bytearray(data))


def expected(operation, selector=0):
    frame = bytes.fromhex("0705020221090000" if operation == "set" else "07057f0106300000")
    return [frame + bytes([selector])] * 2 + [app.QUERY_ALARM] * 3


def check_restored(*coordinators):
    for coordinator in coordinators:
        assert coordinator._command_connection_holds == 0
        if coordinator.is_connected:
            assert coordinator._disconnect_timer is not None


def error_text(error):
    if isinstance(error, PairedSideError):
        return repr(error.side_errors)
    return str(error)


def changed_or_stopped(error) -> bool:
    """The action refused because the bed changed or a STOP came, by key or own reason."""
    return bool(error_keys(error) & {"bed_changed", "action_stopped"}) or "Ultramatic" in error_text(error)


def error_keys(error):
    errors = error.side_errors.values() if isinstance(error, PairedSideError) else (error,)
    return {getattr(item, "translation_key", None) for item in errors}


async def wait_at_boundary(task, event):
    """Surface a public-call exception instead of hanging on an unmet fixture wait."""
    waiting = asyncio.create_task(event.wait())
    try:
        done, _pending = await asyncio.wait(
            {task, waiting}, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            await task
            pytest.fail("Public alarm finished before the fixture boundary")
        assert waiting in done, "Public alarm never reached the fixture boundary"
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.parametrize("operation", ["set", "disable"])
async def test_registered_native_parent_both_uses_one_combined_sequence(native_alarm, operation):
    hass, pair, inner, client, standalone, other_client, devices = native_alarm
    report(client)

    async def observe(_characteristic, _frame, **kwargs):
        # One app hold plus the topology's two logical-target holds on this link.
        assert inner._command_connection_holds == 3
        assert standalone._command_connection_holds == 0
        assert kwargs == {"response": False}

    client.write_gatt_char.side_effect = observe
    generation = inner.controller.operation_generation
    assert pair._targets_for("both")[0][1] is pair._single_both
    with clocked(hass):
        await alarm(hass, [devices["parent"]], operation)
    assert writes(client) == expected(operation)
    assert inner.controller.operation_generation == generation + 1
    assert writes(other_client) == []
    check_restored(inner)


@pytest.mark.parametrize("side,selector", [("left", 1), ("right", 2)])
async def test_registered_native_child_keeps_its_single_side_plan(native_alarm, side, selector):
    hass, _pair, inner, client, _standalone, other_client, devices = native_alarm
    report(client)
    with clocked(hass):
        await alarm(hass, [devices[side]], "disable")
    assert writes(client) == expected("disable", selector)
    assert writes(other_client) == []
    check_restored(inner)


async def test_registered_both_native_children_merge_into_one_combined_set(native_alarm):
    hass, _pair, inner, client, _standalone, other_client, devices = native_alarm
    with clocked(hass):
        await alarm(hass, [devices["left"], devices["right"]], "set")
    assert writes(client) == expected("set")
    assert writes(other_client) == []
    check_restored(inner)


async def test_registered_native_both_and_standalone_use_distinct_current_plans(native_alarm):
    hass, _pair, inner, client, standalone, other_client, devices = native_alarm
    assert inner.controller is not standalone.controller
    report(client)
    report(other_client)

    async def observe_standalone(_characteristic, _frame, **_kwargs):
        assert inner._command_connection_holds == standalone._command_connection_holds == 1

    async def observe_native(_characteristic, _frame, **_kwargs):
        assert inner._command_connection_holds == 3
        assert standalone._command_connection_holds == 1

    client.write_gatt_char.side_effect = observe_native
    other_client.write_gatt_char.side_effect = observe_standalone
    with clocked(hass):
        await alarm(hass, [devices["standalone"], devices["parent"]], "disable")
    assert writes(client) == writes(other_client) == expected("disable")
    check_restored(inner, standalone)


REFRESH = "alarm_refresh_needed"


@pytest.mark.parametrize(
    "bad_report,refusal",
    [
        # Its B record is off, so turning B off is refused before AB is checked.
        (ALARM_REPORT, "alarm_already_off"),
        # Both sides on but unequal: the new report revokes AB permission.
        (bytes.fromhex("ed8003017f0106300001027f0106450001"), REFRESH),
        (bytes.fromhex("ed8003027f0106300001027f0106300001"), REFRESH),
        (bytes.fromhex("ed8003017f011a2f0001027f011a2f0001"), REFRESH),
    ],
    ids=["unequal", "unequal-both-on", "missing-A", "invalid-BCD"],
)
async def test_registered_native_both_invalid_disable_blocks_earlier_standalone(
    native_alarm, bad_report, refusal
):
    hass, _pair, inner, client, standalone, other_client, devices = native_alarm
    report(other_client)
    report(client)  # A new invalid report must revoke previously valid AB permission.
    report(client, bad_report)
    with clocked(hass), pytest.raises((HomeAssistantError, ValueError)) as caught:
        await alarm(hass, [devices["standalone"], devices["parent"]], "disable")
    assert refusal in error_keys(caught.value)
    assert writes(client) == writes(other_client) == []
    inner.async_ensure_connected.assert_not_awaited()
    standalone.async_ensure_connected.assert_not_awaited()
    assert inner._command_connection_holds == standalone._command_connection_holds == 0


@pytest.mark.parametrize(
    "change",
    ["stop", "logical-roster", "physical-owner", "effective-route", "side", "stale-client"],
)
async def test_registered_native_alarm_rejects_preflight_owner_and_route_changes(
    native_alarm, change
):
    hass, pair, inner, client, standalone, other_client, devices = native_alarm
    arrived, release = asyncio.Event(), asyncio.Event()
    right = pair.children["right"]

    async def ensure(reset_timer=True):
        if not arrived.is_set():
            arrived.set()
            await release.wait()
        return True

    with (
        patch.object(inner, "async_ensure_connected", side_effect=ensure),
        clocked(hass),
    ):
        task = asyncio.create_task(alarm(hass, [devices["parent"], devices["standalone"]], "set"))
        try:
            await wait_at_boundary(task, arrived)
            if change == "stop":
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": [devices["parent"]]}, blocking=True
                )
            elif change == "logical-roster":
                pair._children["right"] = pair._single_both
            elif change == "physical-owner":
                pair._single_both._single_inner = standalone
            elif change == "effective-route":
                pair._topology.native_both = False
            elif change == "side":
                pair._single_both._single_side = "right"
            else:
                inner._client = make_client()
            release.set()
            with pytest.raises((HomeAssistantError, ConnectionError, ValueError)) as caught:
                await task
            assert changed_or_stopped(caught.value)
            assert writes(client) == ([app.control("STOP")] if change == "stop" else [])
            assert writes(other_client) == []
            check_restored(inner, standalone)
        finally:
            pair._children["right"] = right
            pair._single_both._single_inner = inner
            pair._single_both._single_side = "both"
            pair._topology.native_both = True
            inner._client = client
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class QueuedWireLock(asyncio.Lock):
    def __init__(self):
        super().__init__()
        self.arrived = asyncio.Event()

    async def __aenter__(self):
        self.arrived.set()
        return await super().__aenter__()


@pytest.mark.parametrize("change", ["effective-route", "stale-client"])
async def test_registered_native_alarm_rechecks_queued_wire_route_and_client(native_alarm, change):
    hass, pair, inner, client, _standalone, other_client, devices = native_alarm
    controller = inner.controller
    original_lock = controller._ble_lock
    queued = QueuedWireLock()
    controller._ble_lock = queued
    await queued.acquire()
    with clocked(hass):
        task = asyncio.create_task(alarm(hass, [devices["parent"]], "set"))
        try:
            await wait_at_boundary(task, queued.arrived)
            if change == "effective-route":
                pair._topology.native_both = False
            else:
                inner._client = make_client()
            queued.release()
            with pytest.raises((HomeAssistantError, ConnectionError, ValueError)) as caught:
                await task
            assert changed_or_stopped(caught.value)
            assert all(frame == app.control("STOP") for frame in writes(client))
            assert writes(other_client) == []
            check_restored(inner)
        finally:
            if queued.locked():
                queued.release()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            pair._topology.native_both = True
            inner._client = client
            controller._ble_lock = original_lock


async def test_refresh_alarm_button_sends_the_alarm_query(native_alarm):
    # Reading the alarm is the Refresh alarm button; set_alarm only writes.
    hass, _pair, inner, client, _standalone, other_client, _devices = native_alarm
    spec = next(
        s for s in inner.controller.controller_button_specs if s.key == "ultramatic_query_alarm"
    )
    generation = inner.controller.operation_generation
    with clocked(hass):
        await inner.async_execute_controller_command(spec.press_fn, resource="*")
    assert writes(client) == [app.QUERY_ALARM] * 2
    assert inner.controller.operation_generation == generation + 1
    assert writes(other_client) == []


async def test_turning_off_an_alarm_that_is_already_off_sends_nothing(native_alarm):
    hass, _pair, inner, client, _standalone, other_client, devices = native_alarm
    report(client, bytes.fromhex("ed8003017f0106300000027f0106300000"))
    with clocked(hass), pytest.raises(HomeAssistantError) as caught:
        await alarm(hass, [devices["parent"]], "disable")
    assert "already off" in error_text(caught.value)
    assert writes(client) == writes(other_client) == []
    inner.async_ensure_connected.assert_not_awaited()
    assert inner._command_connection_holds == 0
