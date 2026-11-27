"""Alarm cache authority follows actual HA command delivery and newer readback."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.meisemobell import state_keys as s
from custom_components.adjustable_bed.command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
)
from custom_components.adjustable_bed.errors import BedCommandFailedError
from custom_components.adjustable_bed.profiles import meisemobell as app
from custom_components.adjustable_bed.runtime_data import entry_runtime
from tests.hold_lease_wire import virtual_clock
from tests.test_meisemobell import frames, gatt, ready

ORIGINAL = (app.Alarm(6, 30, 130, 17, True), app.Alarm(7, 45, 132, 19, True))


def request(slot=1):
    return AlarmRequest(
        enabled=True,
        hour=8,
        minute=15,
        weekdays=(0,),
        slot=slot,
        wake_action="memory_1",
        reference_time=datetime(2026, 11, 27),
    )


def report(controller, client, values=ORIGINAL):
    callback = client.start_notify.await_args.args[1]
    if controller.route == "15_22_15a":
        callback(None, bytearray((0xED, 0x80, 3, *values[0].fields(), *values[1].fields(), 0)))
    else:
        for slot, value in enumerate(values, 1):
            if value is not None:
                callback(
                    None,
                    bytearray(
                        (
                            0xA5,
                            0x0B + slot,
                            0,
                            0,
                            value.week,
                            value.kind,
                            value.hour,
                            value.minute,
                            0,
                            int(value.enabled),
                        )
                    ),
                )


@pytest.fixture
async def bed(
    hass, request, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    route = request.param
    mock_bleak_client.services = gatt(route)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Meisemobell delivery",
        unique_id="AA:BB:CC:DD:AA:41",
        data={
            "address": "AA:BB:CC:DD:AA:41",
            "name": "Meisemobell delivery",
            "bed_type": "meisemobell",
            "protocol_variant": route,
            "motor_count": 2,
            "has_massage": False,
            "disable_angle_sensing": True,
            "connection_mode": const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    controller = coordinator.controller
    report(controller, mock_bleak_client)
    mock_bleak_client.write_gatt_char.reset_mock()
    try:
        yield coordinator, controller, mock_bleak_client
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("bed", app.PROFILES, indirect=True)
@pytest.mark.parametrize("ending", ("returned", "event", "task", "failure"))
async def test_set_finalizes_delivered_target_even_when_cancelled(bed, ending):
    coordinator, controller, client = bed
    before = dict(controller._alarms)
    observed = []
    operation_task = None

    async def write(_char, packet, **_kwargs):
        if bytes(packet)[:2] not in (b"\xed\x80", b"\x07\x05"):
            return
        context = current_command_context()
        assert context is not None
        if ending == "failure":
            raise BleakError("backend did not complete")
        if ending == "event":
            context.cancel_event.set()
        elif ending == "task":
            assert operation_task is not None
            operation_task.cancel()
            await asyncio.sleep(0)  # The settled backend write still completes.

    async def run(ctrl):
        nonlocal operation_task
        operation_task = asyncio.current_task()
        with delivered(observed.append):
            await ctrl.configure_alarm(request())

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        if ending == "failure":
            with pytest.raises(BedCommandFailedError):
                await coordinator.async_execute_controller_command(run)
        else:
            await coordinator.async_execute_controller_command(run)
    if ending == "failure":
        assert observed == [Delivery.NONE]
        assert controller._alarms == before
        assert coordinator.controller_state[s.SOURCE_1] == "reported"
    else:
        assert observed == [Delivery.SENT]
        assert 1 not in controller._alarms
        assert controller._alarms[2] is before[2]
        assert coordinator.controller_state[s.ALARM_1] == "08:15"
        assert coordinator.controller_state[s.SOURCE_1] == "sent"
        assert controller._current().last == b""
        client.write_gatt_char.side_effect = None
        client.write_gatt_char.reset_mock()
        # A later edit of slot 2 must not reuse the old target in a P1 pair frame.
        if controller.route == "15_22_15a":
            with virtual_clock(), pytest.raises(ServiceValidationError):
                await coordinator.async_execute_controller_command(
                    lambda ctrl: ctrl.configure_alarm(request(2))
                )
            assert not any(frame[:2] == b"\xed\x80" for frame in frames(client))


@pytest.mark.parametrize("bed", app.PROFILES, indirect=True)
async def test_cancellation_while_queued_for_ble_sends_and_invalidates_nothing(bed, monkeypatch):
    coordinator, controller, client = bed
    before = dict(controller._alarms)
    admitted = asyncio.Event()
    observed = []
    original_write = controller._write
    context = None

    async def gated(*args, **kwargs):
        nonlocal context
        context = current_command_context()
        admitted.set()
        await original_write(*args, **kwargs)

    monkeypatch.setattr(controller, "_write", gated)

    async def run(ctrl):
        with delivered(observed.append):
            await ctrl.configure_alarm(request())

    async with controller.ble_lock:
        task = asyncio.create_task(coordinator.async_execute_controller_command(run))
        await admitted.wait()
        assert context is not None
        context.cancel_event.set()
    await task
    assert observed == [Delivery.NONE]
    assert not frames(client)
    assert controller._alarms == before
    assert coordinator.controller_state[s.SOURCE_1] == "reported"


@pytest.mark.parametrize("bed", ("24_xx_xx",), indirect=True)
@pytest.mark.parametrize("ending", ("event_first", "task_first", "task_final", "failure_final"))
async def test_close_composite_settles_each_slot_and_overall_delivery(bed, ending):
    coordinator, controller, client = bed
    before = dict(controller._alarms)
    observed = []
    operation_task = None

    async def write(_char, packet, **_kwargs):
        slot = packet[1] - 4
        context = current_command_context()
        assert context is not None
        if ending == "failure_final" and slot == 2:
            raise BleakError("second slot failed")
        if ending == "event_first" and slot == 1:
            context.cancel_event.set()
        elif ending == ("task_first" if slot == 1 else "task_final"):
            assert operation_task is not None
            operation_task.cancel()
            await asyncio.sleep(0)

    async def run(ctrl):
        nonlocal operation_task
        operation_task = asyncio.current_task()
        with delivered(observed.append):
            await ctrl.close_alarms()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        if ending == "failure_final":
            with pytest.raises(BedCommandFailedError):
                await coordinator.async_execute_controller_command(run)
        else:
            await coordinator.async_execute_controller_command(run)
    assert 1 not in controller._alarms
    assert coordinator.controller_state[s.SOURCE_1] == "sent"
    assert coordinator.controller_state[s.ALARM_1] == "00:00"
    if ending == "task_final":
        assert observed == [Delivery.SENT]
        assert 2 not in controller._alarms
        assert coordinator.controller_state[s.SOURCE_2] == "sent"
    else:
        assert observed == [Delivery.PARTIAL]
        assert controller._alarms[2] is before[2]
        assert coordinator.controller_state[s.ALARM_2] == "07:45"
        assert coordinator.controller_state[s.SOURCE_2] == "reported"


@pytest.mark.parametrize("bed", app.PROFILES, indirect=True)
@pytest.mark.parametrize("operation", ("set", "close"))
async def test_stale_write_completion_cannot_change_replacement_link_state(bed, operation):
    coordinator, controller, client = bed
    replacement = {}
    replaced = False

    async def write(_char, packet, **_kwargs):
        nonlocal replaced
        if replaced or bytes(packet)[:2] not in (b"\xed\x80", b"\x07\x05"):
            return
        replaced = True
        await ready(controller)  # Same Bleak client, different exact _Link/listener.
        values = (app.Alarm(9, 10, 130, 17, True), ORIGINAL[1])
        report(controller, client, values)
        replacement.update(controller._alarms)

    client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(ConnectionError):
        await coordinator.async_execute_controller_command(
            lambda ctrl: (
                ctrl.configure_alarm(request()) if operation == "set" else ctrl.close_alarms()
            )
        )
    assert replaced
    assert controller._alarms == replacement
    assert coordinator.controller_state[s.ALARM_1] == "09:10"
    assert coordinator.controller_state[s.SOURCE_1] == "reported"
    assert coordinator.controller_state[s.SOURCE_2] == "reported"


@pytest.mark.parametrize("bed", ("24_xx_xx",), indirect=True)
@pytest.mark.parametrize("during_slot,reported_slot", ((1, 1), (1, 2), (2, 1), (2, 2)))
async def test_close_keeps_newer_independent_slot_reports(bed, during_slot, reported_slot):
    coordinator, controller, client = bed
    changed = app.Alarm(10, 25, 134, 6, True)

    async def write(_char, packet, **_kwargs):
        if packet[1] - 4 == during_slot:
            report(controller, client, (changed, None) if reported_slot == 1 else (None, changed))

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda ctrl: ctrl.close_alarms())
    assert controller._alarms == {reported_slot: changed}
    key = s.ALARM_1 if reported_slot == 1 else s.ALARM_2
    origin = s.SOURCE_1 if reported_slot == 1 else s.SOURCE_2
    assert coordinator.controller_state[key] == "10:25"
    assert coordinator.controller_state[origin] == "reported"


@pytest.mark.parametrize("bed", app.PROFILES, indirect=True)
@pytest.mark.parametrize("ending", ("returned", "event", "task"))
async def test_set_never_downgrades_newer_target_readback_to_sent(bed, ending):
    coordinator, controller, client = bed
    changed = app.Alarm(9, 10, 134, 19, True)
    operation_task = None

    async def write(_char, packet, **_kwargs):
        if bytes(packet)[:2] not in (b"\xed\x80", b"\x07\x05"):
            return
        report(controller, client, (changed, ORIGINAL[1]))
        if ending == "event":
            current_command_context().cancel_event.set()
        elif ending == "task":
            assert operation_task is not None
            operation_task.cancel()
            await asyncio.sleep(0)

    async def run(ctrl):
        nonlocal operation_task
        operation_task = asyncio.current_task()
        await ctrl.configure_alarm(request())

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await coordinator.async_execute_controller_command(run)
    assert controller._alarms[1] == changed
    assert coordinator.controller_state[s.ALARM_1] == "09:10"
    assert coordinator.controller_state[s.SOURCE_1] == "reported"


@pytest.mark.parametrize("bed", app.PROFILES, indirect=True)
@pytest.mark.parametrize("phase", ("queued", "in_flight"))
async def test_public_caller_task_cancel_uses_the_delivered_alarm_frame(bed, phase, monkeypatch):
    coordinator, controller, client = bed
    before = dict(controller._alarms)
    entered = asyncio.Event()
    context = None
    original_write = controller._write
    public_task = None

    async def observed_write(*args, **kwargs):
        nonlocal context
        context = current_command_context()
        entered.set()
        await original_write(*args, **kwargs)

    async def backend(_char, _packet, **_kwargs):
        if phase == "in_flight":
            assert public_task is not None
            public_task.cancel()
            await asyncio.sleep(0)

    monkeypatch.setattr(controller, "_write", observed_write)
    client.write_gatt_char.side_effect = backend
    if phase == "queued":
        async with controller.ble_lock:
            public_task = asyncio.create_task(
                coordinator.async_execute_controller_command(
                    lambda ctrl: ctrl.configure_alarm(request())
                )
            )
            await entered.wait()
            public_task.cancel()
            assert context is not None
            await asyncio.wait_for(context.cancel_event.wait(), 1)
    else:
        public_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda ctrl: ctrl.configure_alarm(request())
            )
        )
    with pytest.raises(asyncio.CancelledError):
        await public_task
    if phase == "queued":
        assert not frames(client)
        assert controller._alarms == before
        assert coordinator.controller_state[s.SOURCE_1] == "reported"
    else:
        assert len(frames(client)) == 1
        assert 1 not in controller._alarms
        assert controller._alarms[2] is before[2]
        assert coordinator.controller_state[s.ALARM_1] == "08:15"
        assert coordinator.controller_state[s.SOURCE_1] == "sent"
