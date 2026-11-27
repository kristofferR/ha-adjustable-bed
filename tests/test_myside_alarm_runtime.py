"""Alarm refresh and mutation safety through MySide's real registered HA action."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.myside import controller as bed
from custom_components.adjustable_bed.beds.myside import services
from custom_components.adjustable_bed.beds.myside.protocol import Alarm
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_myside_ha import cleanup as cleanup
from tests.test_myside_ha import frames, invoke, receive_alarm, target

OLD = Alarm(1, 55, 6, 30, 69, 169)
NEW = Alarm(1, 0, 8, 0, 46, 1)


@pytest.fixture
async def runtime(hass):
    value = await target(hass)
    services.register_services(hass)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        yield value


async def query(hass, ctrl, device, records=(OLD,)):
    await invoke(hass, [device.id], "query")
    for alarm in records:
        receive_alarm(ctrl, alarm)


async def test_consecutive_replacements_consume_deleted_slots_and_accept_new_slot_update(
    hass, runtime
):
    _, ctrl, client, device = runtime
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    await query(hass, ctrl, device, (OLD, *(Alarm(n, 0, 7, 0, 46, 1) for n in (2, 3, 4))))
    for number in (2, 3, 4):
        await invoke(hass, [device.id], "delete", alarm_id=number)
    client.write_gatt_char.reset_mock()
    await invoke(hass, [device.id], "add", hour=6, mode="memory1")
    assert ctrl.alarms == [OLD]  # Pending write is not reported state.
    receive_alarm(ctrl, Alarm(2, 0, 6, 0, 46, 1), direction=3)
    await invoke(hass, [device.id], "add", hour=7, mode="memory2")
    await invoke(hass, [device.id], "add", hour=8, mode="memory3")
    assert [bytes.fromhex(frame)[6] for frame in frames(client)] == [2, 3, 4]


async def test_refresh_clears_stale_records_and_latest_number_wins(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device, (OLD, Alarm(2, 0, 9, 0, 47, 1)))
    await invoke(hass, [device.id], "query")
    assert ctrl.alarms == []
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "enable", alarm_id=1, enabled=False)
    receive_alarm(ctrl, OLD)
    receive_alarm(ctrl, NEW)
    receive_alarm(ctrl, NEW)
    assert ctrl.alarms == [NEW]
    client.write_gatt_char.reset_mock()
    await invoke(hass, [device.id], "enable", alarm_id=1, enabled=False)
    assert frames(client) == ["6e0d20050101010008002e00d9"]
    # An omitted slot has no fresh state and is unavailable to edit/toggle.
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "enable", alarm_id=2, enabled=False)
    assert ctrl.alarms == []  # No stale copy remains after the mutation.


async def test_query_does_not_infer_completion_or_free_unreported_slots(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device, (OLD, Alarm(2, 0, 9, 0, 47, 1)))
    await query(hass, ctrl, device, ())
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    receive_alarm(ctrl, NEW)
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    assert frames(client) == []  # Another list reply still proves no free slot.


async def test_edit_invalidates_until_fresh_reply_then_toggle_preserves_latest_u(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    client.write_gatt_char.reset_mock()
    await invoke(hass, [device.id], "edit", alarm_id=1, hour=8, minute=0, mode="memory1")
    assert bytes.fromhex(frames(client)[0])[7] == 0
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "enable", alarm_id=1, enabled=False)
    assert len(frames(client)) == 1
    fresh = Alarm(1, 23, 8, 0, 46, 1)
    receive_alarm(ctrl, fresh, direction=3)
    await invoke(hass, [device.id], "enable", alarm_id=1, enabled=False)
    assert frames(client)[-1] == fresh.enabled(False).frame().hex()


async def test_fresh_report_while_waiting_for_wire_rejects_stale_frame(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    client.write_gatt_char.reset_mock()
    # Model a delayed BLE lane after service preflight captured the old record.
    await ctrl._ble_lock.acquire()
    waiting = asyncio.Event()
    original = ctrl._send

    async def send(*args, **kwargs):
        waiting.set()
        return await original(*args, **kwargs)

    with patch.object(ctrl, "_send", send):
        task = asyncio.create_task(invoke(hass, [device.id], "enable", alarm_id=1, enabled=False))
        await waiting.wait()
        receive_alarm(ctrl, NEW)
        ctrl._ble_lock.release()
        with pytest.raises(ServiceValidationError):
            await task
    assert frames(client) == [] and ctrl.alarms == [NEW]


async def test_queued_admission_is_invalidated_by_another_query(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    admission = ctrl.alarm_admission()
    await query(hass, ctrl, device, (NEW,))
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="changed"):
        await ctrl.operation("enable", alarm_id=1, enabled=False, admission=admission)
    assert frames(client) == [] and ctrl.alarms == [NEW]


async def test_cancelled_before_wire_does_not_reserve_or_invalidate(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device, (OLD, Alarm(2, 0, 7, 0, 46, 1)))
    await invoke(hass, [device.id], "delete", alarm_id=2)
    client.write_gatt_char.reset_mock()
    generation = ctrl._alarm_generation
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.operation("add", hour=7, mode="memory1"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    ctrl._ble_lock.release()
    assert ctrl._alarm_generation == generation
    assert ctrl.alarms == [OLD] and ctrl._occupied_alarm_ids == {1}
    assert frames(client) == [] and ctrl._free_alarm_ids == {2}
    await invoke(hass, [device.id], "add", hour=7, mode="memory1")
    assert bytes.fromhex(frames(client)[0])[6] == 2


@pytest.mark.parametrize("report", [False, True])
async def test_cancelled_during_write_retains_reservation_and_fresh_reply(hass, runtime, report):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device, (OLD, Alarm(2, 0, 7, 0, 46, 1), Alarm(3, 0, 7, 0, 46, 1)))
    for number in (2, 3):
        await invoke(hass, [device.id], "delete", alarm_id=number)
    client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()
    fresh = Alarm(2, 33, 9, 10, 47, 3)

    async def writing(_char, data, **kwargs):
        started.set()
        await finish.wait()
        if report:
            receive_alarm(ctrl, fresh, direction=3)

    client.write_gatt_char.side_effect = writing
    task = asyncio.create_task(ctrl.operation("add", hour=7, mode="memory1"))
    await started.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert 2 in ctrl._occupied_alarm_ids and 2 not in ctrl._free_alarm_ids
    assert (fresh in ctrl.alarms) is report
    client.write_gatt_char.side_effect = None
    await invoke(hass, [device.id], "add", hour=8, mode="memory2")
    assert [bytes.fromhex(frame)[6] for frame in frames(client)] == [2, 3]


@pytest.mark.parametrize("direction", [2, 3])
async def test_fresh_reply_during_delete_is_not_erased(hass, runtime, direction):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)

    async def writing(*_args, **_kwargs):
        receive_alarm(ctrl, NEW, direction=direction)

    client.write_gatt_char.side_effect = writing
    await invoke(hass, [device.id], "delete", alarm_id=1)
    assert ctrl.alarms == [NEW] and 1 in ctrl._occupied_alarm_ids
    assert not ctrl._free_alarm_ids


@pytest.mark.parametrize("direction,code", [("up", 0x29), ("down", 0x2A)])
async def test_combined_entity_and_actual_renewable_hold_have_no_mid_hold_stop(
    hass, direction, code
):
    coord, ctrl, client, device = await target(hass)
    await async_register_services(hass)
    spec = next(
        s for s in ctrl.controller_button_specs if s.key == f"myside_head_and_foot_{direction}"
    )
    entity = ControllerActionButton(coord, spec)
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/myside/combined_controls.json").read_text()
    )[direction]
    assert entity.extra_state_attributes | entity.capability_attributes == fixture["attributes"]
    attributes = entity.extra_state_attributes
    events = []
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):

        async def writing(_char, data, **kwargs):
            events.append((clock.now, bytes(data)))

        client.write_gatt_char.side_effect = writing

        async def hold():
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": [device.id],
                    "control": attributes["held_control"],
                    "duration": 0.75,
                    "hold_owner": "myside-card",
                    "hold_generation": 1,
                },
                blocking=True,
            )

        task = asyncio.create_task(hold())
        for _ in range(9):
            await asyncio.sleep(0.25)
            await hold()
        assert len(events) > 10 and all(data == codec.command(code) for _, data in events)
        stopped = clock.now
        await coord.async_stop_command()
        await task
    motion = [at for at, data in events if data == codec.command(code)]
    assert motion[-1] - motion[0] > 1
    assert all(b - a == pytest.approx(0.1) for a, b in zip(motion, motion[1:], strict=False))
    assert all(at >= stopped for at, data in events if data == codec.command(codec.STOP))


async def test_unrelated_reply_during_delivered_delete_still_frees_its_slot(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device, tuple(Alarm(n, 0, 7, 0, 46, 1) for n in range(1, 8)))

    async def writing(*_args, **_kwargs):
        receive_alarm(ctrl, Alarm(7, 22, 9, 0, 47, 1))

    client.write_gatt_char.side_effect = writing
    await invoke(hass, [device.id], "delete", alarm_id=2)
    assert ctrl._free_alarm_ids == {2}
    client.write_gatt_char.side_effect = None
    client.write_gatt_char.reset_mock()
    await invoke(hass, [device.id], "add", hour=8, mode="memory2")
    assert frames(client) == [Alarm(2, 0, 8, 0, 47, 1).frame().hex()]
    assert not ctrl._free_alarm_ids


@pytest.mark.parametrize("direction", [2, 3])
async def test_same_slot_reply_after_delete_revokes_replacement_admission(hass, runtime, direction):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    await invoke(hass, [device.id], "delete", alarm_id=1)
    assert ctrl._free_alarm_ids == {1}
    receive_alarm(ctrl, NEW, direction=direction)
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    assert frames(client) == [] and not ctrl._free_alarm_ids


@pytest.mark.parametrize("cancelled", [False, True])
async def test_uncertain_delete_never_creates_reusable_capacity(hass, runtime, cancelled):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    started, finish = asyncio.Event(), asyncio.Event()

    async def writing(*_args, **_kwargs):
        started.set()
        await finish.wait()
        if not cancelled:
            raise OSError("indeterminate delete")

    client.write_gatt_char.side_effect = writing
    task = asyncio.create_task(ctrl.operation("delete", alarm_id=1))
    await started.wait()
    if cancelled:
        task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError if cancelled else OSError):
        await task
    assert not ctrl._free_alarm_ids and ctrl._occupied_alarm_ids == {1}
    client.write_gatt_char.side_effect = None
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    assert frames(client) == []


async def test_query_retains_existing_deletion_proof_but_reconnect_forgets_it(hass, runtime):
    _, ctrl, client, device = runtime
    await query(hass, ctrl, device)
    await invoke(hass, [device.id], "delete", alarm_id=1)
    await query(hass, ctrl, device, ())
    assert ctrl._free_alarm_ids == {1}  # This proof came from delete, not the empty query.
    await ctrl.stop_notify()
    await ctrl.start_notify()
    await query(hass, ctrl, device)
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [device.id], "add")
    assert frames(client) == [] and not ctrl._free_alarm_ids
