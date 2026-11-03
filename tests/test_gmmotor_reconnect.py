"""GM app intent through production controller replacement and recovery."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.gmmotor import GmmotorController
from custom_components.adjustable_bed.beds.gmmotor_sleep import GmmotorSleepController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import DOMAIN, disconnect_after_command_default_enabled
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.gmmotor_notifications import Event
from custom_components.adjustable_bed.gmmotor_requests import Request
from custom_components.adjustable_bed.gmmotor_services import async_register_gmmotor_services
from custom_components.adjustable_bed.gmmotor_sessions import sleep_intent
from custom_components.adjustable_bed.gmmotor_sleep_protocol import frame
from custom_components.adjustable_bed.gmmotor_transport import E0FF, SLEEP_NOTIFY, SLEEP_WRITE


@pytest.fixture
def gm_link(mock_coordinator_connected, mock_bleak_client, monkeypatch):
    """Mock the BLE boundary, leaving coordinator/factory/startup/teardown real."""
    write = SimpleNamespace(
        uuid=SLEEP_WRITE,
        handle=7,
        properties=["write", "write-without-response"],
        descriptors=[],
        description="write",
        service_uuid=E0FF,
    )
    notify = SimpleNamespace(
        uuid=SLEEP_NOTIFY,
        handle=8,
        properties=["notify"],
        descriptors=[],
        description="notify",
        service_uuid=E0FF,
    )
    services = MagicMock()
    services.__iter__.side_effect = lambda: iter(
        [SimpleNamespace(uuid=E0FF, characteristics=[write, notify])]
    )
    services.get_characteristic.return_value = None
    mock_bleak_client.services = services
    mock_bleak_client.mtu_size = 247
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    monkeypatch.setattr(GmmotorController, "_pause", AsyncMock(return_value=True))
    monkeypatch.setattr("custom_components.adjustable_bed.beds.gmmotor_sleep._QUEUE_TICK", 0)
    return mock_bleak_client


def coordinator(
    hass, *, sxb=None, product="E3RM", side="left", quick=False, address="AA:BB:CC:DD:EE:FF"
):
    bed_type = "gmmotor" if sxb is None else "gmmotor_sleep_sxb" if sxb else "gmmotor_sleep_mm"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": address,
            "bed_type": bed_type,
            "product_type": product,
            "gmmotor_side": side,
            "disable_angle_sensing": True,
            "disconnect_after_command": quick,
        },
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


def button(c, material):
    ctrl = c.controller
    index = next(i for i, a in enumerate(ctrl.profile.controls) if a.material.name == material)
    spec = next(s for s in ctrl.controller_button_specs if s.key == f"gm_{index}")
    return ControllerActionButton(c, spec)


@pytest.mark.parametrize("bed_type", ["gmmotor", "gmmotor_sleep_mm", "gmmotor_sleep_sxb"])
def test_new_entries_do_not_offer_quick_handoff_by_default(bed_type):
    assert disconnect_after_command_default_enabled(bed_type) is False


@pytest.mark.parametrize("quick", [False, True])
async def test_memory_program_mode_survives_actual_idle_disconnect_and_new_controller(
    hass, gm_link, quick
):
    c = coordinator(hass, quick=quick)
    assert await c.async_connect()
    first = c.controller
    await button(c, "deviceFunctionItemMemory").async_press()
    assert first._ui_state == 4
    assert c._idle_disconnect_delay() == (1 if quick else 40)
    # Fire the idle path directly rather than waiting on its protocol-independent timer.
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert c.controller is None and not gm_link.is_connected
    gm_link.write_gatt_char.reset_mock()
    slot = next(
        f"gm_{i}"
        for i, action in enumerate(first.profile.controls)
        if action.material.name == "deviceFunctionItemMemoryPosition1"
    )
    # One source sustain tick selects the slot through the bounded hold path.
    await c.async_execute_controller_command(lambda ctrl: ctrl.hold_control(slot, 100))
    assert c.controller is not first
    packets = [call.args[1] for call in gm_link.write_gatt_char.await_args_list]
    assert bytes.fromhex("6e01002b9a") in packets
    assert bytes.fromhex("6e01002e9d") not in packets


@pytest.mark.parametrize(
    ("product", "fields", "reply"),
    [
        ("FTRN", {"operation": "light_off"}, "6e0e00037f"),
        ("FTRN", {"operation": "light_color", "rgb_color": [255, 0, 0]}, "6e0e00037f"),
        ("FTRN", {"operation": "light_timeout", "value": 135}, "6e0e00037f"),
        ("A0RN", {"operation": "alarm_cancel"}, "6e09010078"),
        ("A0RN", {"operation": "alarm", "value": 30}, "6e09010078"),
        ("A0RN", {"operation": "alarm_at", "hour": 7}, "6e09010078"),
        ("FTRN", {"operation": "repeat_alarm", "hour": 7}, "6e09010078"),
        ("FTRN", {"operation": "repeat_delete"}, "6e09010078"),
        ("FTRN", {"operation": "repeat_query"}, "6e09010078"),
    ],
)
async def test_gated_service_waits_for_replacement_connection_reply(
    hass, gm_link, monkeypatch, product, fields, reply
):
    c = coordinator(hass, product=product)
    assert await c.async_connect()
    first = c.controller
    first._accept(Event("light_capability"))
    first._accept(Event("clock_capability"))
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert c.controller is None
    assert not {"light_capability", "clock_capability"}.intersection(first._events)
    async_register_gmmotor_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_args: ([(c, "both")], []),
    )
    queried = asyncio.Event()

    async def write(_characteristic, payload, **_kwargs):
        if payload == bytes.fromhex("6e0a000179"):
            queried.set()

    gm_link.write_gatt_char.reset_mock()
    gm_link.write_gatt_char.side_effect = write
    if fields["operation"] in ("alarm", "alarm_at", "repeat_alarm"):
        fields = {**fields, "mode": first.profile.alarm_choices[0][0]}
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN, "gmmotor", {"device_id": "bed", **fields}, blocking=True
        )
    )
    await asyncio.wait_for(queried.wait(), 1)
    assert c.controller is not first
    receive = gm_link.start_notify.await_args.args[1]
    wrong_reply = "6e09010078" if reply == "6e0e00037f" else "6e0e00037f"
    receive(SimpleNamespace(uuid="notify"), bytearray.fromhex(wrong_reply))
    await asyncio.sleep(0)
    assert not task.done()
    startup_writes = gm_link.write_gatt_char.await_count
    receive(SimpleNamespace(uuid="notify"), bytearray.fromhex(reply))
    await task
    assert gm_link.write_gatt_char.await_count > startup_writes
    c._cancel_disconnect_timer()


async def test_product_state_isolated_from_other_address_profile_and_admitted_right_side(
    hass, gm_link
):
    c = coordinator(hass)
    assert await c.async_connect()
    await button(c, "deviceFunctionItemMemory").async_press()
    assert c.controller._ui_state == 4
    # A second receiver with the same catalog does not inherit its armed memory mode.
    other = coordinator(hass, address="AA:BB:CC:DD:EE:02")
    other_ctrl = GmmotorController(other, profile="E3RM")
    assert other_ctrl._ui_state == 0
    # The right side is admitted by V9RM:1; its distinct catalog never gets E3RM flags.
    right = GmmotorController(c, profile="V9RM:1", side="right")
    assert right._ui_state == right.profile.initial_state == 0
    assert right.bind_side("left").controller_button_specs
    fresh = GmmotorController(c, profile="E3RM")
    assert fresh._ui_state == 0  # Changing product starts a new app view.


async def start_live(c):
    assert await c.async_connect()
    await c.async_execute_controller_command(
        lambda ctrl: ctrl.async_execute_gmmotor_request(Request("sensor_live")),
        cancel_running=False,
        resource="configuration",
    )
    return c.controller


def drop(c, client):
    client.is_connected = False
    c._on_disconnect(client)
    assert c.controller is None and c._reconnect_timer is not None


@pytest.mark.parametrize("sxb", [False, True])
async def test_live_monitoring_recovers_once_and_old_callbacks_cannot_leak(
    hass, gm_link, mock_establish_connection, sxb
):
    c = coordinator(hass, sxb=sxb)
    old = await start_live(c)
    old._queue("q_time", delayed=True)
    drop(c, gm_link)
    assert old._live_enabled and old._poll_timer is None and old._stale_timer is None
    c._cancel_auto_reconnect()
    c._schedule_auto_reconnect()
    recovery = c._reconnect_task
    assert recovery is not None
    c._schedule_auto_reconnect()
    assert c._reconnect_task is recovery
    await recovery
    current = c.controller
    assert isinstance(current, GmmotorSleepController) and current is not old
    assert current._live_enabled and current._poll_timer is not None
    assert mock_establish_connection.await_count == 2
    poll = current._poll_timer
    await c.async_start_notify()
    assert current._poll_timer is poll
    gm_link.write_gatt_char.reset_mock()
    before = dict(c.controller_state)
    old._poll()
    old._receive(SimpleNamespace(uuid="late"), bytearray(frame(b'{"cmd":"q_time","val":null}', 7)))
    old._queue("q_time", delayed=True)
    await old.stop_notify()
    await hass.async_block_till_done()
    assert current._live_enabled and c.controller_state == before
    gm_link.write_gatt_char.assert_not_awaited()
    poll.cancel()
    current._poll()
    await hass.async_block_till_done()
    packets = [call.args[1] for call in gm_link.write_gatt_char.await_args_list]
    assert len(packets) == 1 and json.loads(packets[0][14:])["cmd"] == "q_realtime"


@pytest.mark.parametrize("sxb", [False, True])
@pytest.mark.parametrize("failure", ["subscribe", "write"])
async def test_recovery_startup_failure_preserves_live_intent_for_successful_retry(
    hass, gm_link, mock_establish_connection, sxb, failure
):
    c = coordinator(hass, sxb=sxb)
    old = await start_live(c)
    drop(c, gm_link)
    if failure == "subscribe":
        gm_link.start_notify.side_effect = [BleakError("transient subscribe failure"), None]
    else:
        gm_link.write_gatt_char.side_effect = [BleakError("transient write failure"), None, None]
    c._cancel_auto_reconnect()
    c._schedule_auto_reconnect()
    recovery = c._reconnect_task
    assert recovery is not None
    await recovery
    current = c.controller
    assert isinstance(current, GmmotorSleepController) and current is not old
    assert mock_establish_connection.await_count == 3
    assert current._live_enabled and current._poll_timer is not None
    assert old._poll_timer is None and old._stale_timer is None
    gm_link.write_gatt_char.side_effect = None
    gm_link.write_gatt_char.reset_mock()
    current._poll_timer.cancel()
    current._poll()
    await hass.async_block_till_done()
    packets = [call.args[1] for call in gm_link.write_gatt_char.await_args_list]
    assert len(packets) == 1 and json.loads(packets[0][14:])["cmd"] == "q_realtime"


@pytest.mark.parametrize("sxb", [False, True])
@pytest.mark.parametrize(
    "end", ["stop", "manual", "offline_manual", "offline_unload", "cancel_startup"]
)
async def test_explicit_end_or_cancelled_recovery_does_not_restart_monitoring(
    hass, gm_link, sxb, end
):
    c = coordinator(hass, sxb=sxb)
    old = await start_live(c)
    if end.startswith("offline") or end == "cancel_startup":
        drop(c, gm_link)
    if end == "stop":
        await c.async_execute_controller_command(
            lambda ctrl: ctrl.async_execute_gmmotor_request(Request("sensor_stop")),
            cancel_running=False,
            resource="configuration",
        )
        await c.async_disconnect()
    elif end == "offline_unload":
        await c.async_shutdown()
    elif end == "cancel_startup":
        entered = asyncio.Event()

        async def stalled(*_args, **_kwargs):
            entered.set()
            await asyncio.Event().wait()

        gm_link.write_gatt_char.side_effect = stalled
        c._cancel_auto_reconnect()
        c._schedule_auto_reconnect()
        recovery = c._reconnect_task
        assert recovery is not None
        await entered.wait()
        recovery.cancel()
        with pytest.raises(asyncio.CancelledError):
            await recovery
        gm_link.write_gatt_char.side_effect = None
    else:
        await c.async_disconnect()
    assert not sleep_intent(hass, c.address, sxb=sxb).live_enabled
    assert old._poll_timer is None and old._stale_timer is None
    assert c._reconnect_timer is None
    # A later explicit connect/reload may establish a link, but cannot restart live data.
    fresh = coordinator(hass, sxb=sxb)
    assert await fresh.async_connect()
    assert fresh.controller._poll_timer is None and fresh.controller._stale_timer is None
