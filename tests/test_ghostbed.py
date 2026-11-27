"""GhostBed frozen bytes, native HA controls, state and connection ownership."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.flexispot import ghostbed as ctrl
from custom_components.adjustable_bed.codec import flexispot as codec
from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.profiles import ghostbed as app
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
from tests.hold_lease_wire import virtual_clock
from tests.test_flexispot import _Service, frames
from tests.test_flexispot_delivery import _service_target
from tests.test_linx import _Services

VECTORS = json.loads((Path(__file__).parent / "fixtures/ghostbed_vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_carrier_equality(row):
    i = row["inputs"]
    assert (
        codec.frame(
            i["op"], i["key"], {int(k): v & 255 for k, v in i["fields"].items()}, i["bank"]
        ).hex()
        == row["expected_bytes"]
    )


def test_formula_domains():
    # An independent bitwise recurrence across every byte and alarm mask.
    for value in range(256):
        packet = codec.frame(0x0F, value)
        crc = 0xFFFF
        for byte in packet[2:17]:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
        assert packet[17:19] == crc.to_bytes(2, "little")
        assert (
            codec.flags(bool(value & 128), tuple(day for day in range(7) if value & 1 << day))
            == value
        )
    for left in range(3):
        for right in range(3):
            assert codec.pair(left, right) == 3 * left + right + 1
            assert codec.unpair(codec.pair(left, right)) == (left, right)


async def target(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="GhostBed",
        unique_id="AA:BB:CC:50:00:01",
        data={
            CONF_ADDRESS: "AA:BB:CC:50:00:01",
            CONF_NAME: "GhostBed",
            CONF_BED_TYPE: "ghostbed",
            "motor_count": 2,
            "has_massage": True,
            "disable_angle_sensing": True,
            "connection_mode": "always",
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    client = SimpleNamespace(
        is_connected=True,
        services=_Services([_Service()]),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    coord._client = client
    bed = await create_controller(coord, "ghostbed", "auto", client)
    coord._controller = coord._offline_controller = bed
    await bed.async_discover_capabilities()
    await bed.start_notify()
    coord._ready = True
    client.write_gatt_char.reset_mock()
    hass.data.setdefault("ghostbed_targets", []).append(coord)
    return coord, bed, client


@pytest.fixture(autouse=True)
async def cleanup(hass, monkeypatch):
    monkeypatch.setattr(app, "RELEASE_MS", 0)
    monkeypatch.setattr(app, "MASSAGE_STEP_MS", 0)
    monkeypatch.setattr(app, "ALARM_DELETE_GAP_MS", 0)
    yield
    for coord in hass.data.get("ghostbed_targets", []):
        await coord.async_shutdown()


def notify(bed, *, bank=0, snore=3, pair=0x95, massage=0x65, slots=None):
    slots = slots or (
        (codec.Alarm(6, 0, 1, 1), codec.Alarm(8, 0, 129, 2))
        if bank == 0
        else (codec.Alarm(10, 0, 129, 1), codec.Alarm(12, 0, 129, 2))
    )
    raw = bytearray(
        codec.frame(
            0x27,
            bank | 1,
            {
                4: massage,
                5: 30,
                6: 2,
                15: 0x20 | snore,
                16: pair,
                **dict(enumerate((*slots[0].fields(), *slots[1].fields()), 7)),
            },
        )
    )
    # App parser intentionally does not validate response CRC.
    raw[17:19] = b"\x00\x00"
    bed._notification(bed._link, raw)
    return raw


async def test_setup_route_and_discovery(hass, enable_custom_integrations):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.form_helpers import complete
    from tests.test_detection import _make_service_info
    from tests.test_setup_routes import _typed

    with patch(
        "custom_components.adjustable_bed.config_flow.AdjustableBedConfigFlow._verification_possible",
        return_value=False,
    ):
        result = await complete(hass, await _typed(hass, "ghostbed"), {})
    assert result["data"]["has_massage"] is True
    assert "has_light" not in result["data"]  # Fixed controller capability, not a setup field.
    assert result["data"]["motor_count"] == 2
    from custom_components.adjustable_bed.bed_traits import reads_positions

    assert not reads_positions(result["data"])
    for name in ("prefixGhostBed123", "prefixW_LeGe123"):
        found = detect_bed_type_detailed(_make_service_info(name=name))
        assert "ghostbed" in (found.bed_type, *(found.ambiguous_types or ()))
    for name in ("ghostbed", "w_lege", "random"):
        found = detect_bed_type_detailed(_make_service_info(name=name))
        assert "ghostbed" not in (found.bed_type, *(found.ambiguous_types or ()))


async def test_native_controls_and_no_inferred_capabilities(hass):
    coord, bed, client = await target(hass)
    assert len(bed.motor_control_specs) == 2
    assert bed.position_number_specs == ()
    assert not bed.supports_single_address_pairing
    assert bed.execution.declared == {"hold"}
    assert bed.memory_slot_count == 3
    for slot, wire_key in ((1, 1), (2, 3), (3, 2)):
        await coord.async_execute_controller_command(lambda c, slot=slot: c.preset_memory(slot))
        assert frames(client)[-1] == codec.frame(7, wire_key)
        await coord.async_execute_controller_command(lambda c, slot=slot: c.program_memory(slot))
        assert frames(client)[-1] == codec.frame(6, wire_key)
    for spec in bed.controller_button_specs:
        if spec.key.startswith("delete_alarm"):
            assert spec.requires_confirmation
            continue
        await coord.async_execute_controller_command(lambda c, spec=spec: spec.press_fn(c))
        assert len(frames(client)[-1]) == 20
    switches = {s.key: AdjustableBedControllerSwitch(coord, s) for s in bed.controller_switch_specs}
    await switches["massage"].async_turn_on()
    assert frames(client)[-1] == codec.frame(14, 1)
    await coord.async_execute_controller_command(lambda c: c.lights_on())
    assert frames(client)[-1] == codec.frame(4, 1)
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is True
    for spec in bed.controller_select_specs:
        if spec.key == "massage_mode":
            entity = AdjustableBedControllerSelect(coord, spec)
            await entity.async_select_option("wave")
            assert frames(client)[-1] == codec.frame(16, 3)
    await coord.async_execute_controller_command(lambda c: c.set_massage_timer(60))
    assert frames(client)[-1] == codec.frame(15, 60)
    assert coord.controller_state[MASSAGE_TIMER_MINUTES] == 60
    notify(bed)
    number = AdjustableBedControllerNumber(coord, bed.controller_number_specs[0])
    await number.async_set_native_value(4)
    assert frames(client)[-2:] == [codec.frame(18)] * 2
    with pytest.raises(ServiceValidationError):
        await number.async_set_native_value(3)


async def test_state_raw_codes_and_left_peer_defaults_without_receive_grace(hass):
    coord, bed, client = await target(hass)
    raw_callback = Mock()
    bed.set_raw_notify_callback(raw_callback)
    raw = notify(bed)
    raw_callback.assert_called_with(codec.NOTIFY, bytes(raw))
    assert coord.controller_state[ctrl.SENSITIVITY] == "medium"
    assert coord.controller_state[ctrl.ANGLE] == "15"
    assert coord.controller_state[ctrl.LEFT] is True
    assert coord.controller_state[MASSAGE_TIMER_MINUTES] == 30
    await bed.snore_setting("angle", "12")
    assert frames(client)[-1] == codec.snore(1, 4, 5)  # Peer default0, not reported peer1.
    notify(bed, snore=2, pair=0x39)
    assert coord.controller_state[ctrl.LEFT] is False
    assert coord.controller_state[ctrl.HOME] is True
    assert coord.controller_state[ctrl.SENSITIVITY] == "high"
    await bed.snore_setting("sensitivity", "medium")
    assert frames(client)[-1] == codec.snore(0, 3, 4)
    notify(bed, pair=0xFF)
    assert coord.controller_state[ctrl.SENSITIVITY] == "high"  # Invalid codes retain cache.
    await bed.snore_home(False)
    assert frames(client)[-1] == codec.snore(0, 15, 15)
    notify(bed, massage=0xFF)
    assert coord.controller_state[ctrl.LEVELS["upper"]] == 0
    assert coord.controller_state[ctrl.LEVELS["feet"]] is None
    before = coord.controller_state[UNDER_BED_LIGHTS_ON]
    bed._notification(bed._link, bytearray(codec.frame(4, 2)))
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is before


async def test_shared_alarm_service_all_four_slots_and_overlap(hass):
    coord, bed, client = await target(hass)
    device = await _service_target(hass, coord)
    notify(bed)
    with pytest.raises(ServiceValidationError):
        await bed.delete_alarm(1)
    assert frames(client) == []  # Missing bank8 must not invent empty peer slots.
    notify(bed, bank=0x80)
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {
            "device_id": [device.id],
            "enabled": True,
            "slot": 4,
            "time": "14:10",
            "weekdays": ["monday", "sunday"],
            "wake_action": "wake_mode_2",
        },
        blocking=True,
    )
    assert frames(client) == [
        codec.alarm((codec.Alarm(10, 0, 129, 1), codec.Alarm(14, 10, 193, 2)), 4, 0x34)
    ]
    notify(bed)
    notify(bed, bank=0x80)
    request = AlarmRequest(
        enabled=True,
        slot=4,
        hour=6,
        minute=30,
        weekdays=(0,),
        wake_action="wake_mode_1",
        reference_time=datetime.now(),
    )
    with pytest.raises(ServiceValidationError, match="30 minutes"):
        await bed.configure_alarm(request)  # Disabled other alarm still conflicts at exactly30.
    assert len(frames(client)) == 1
    await bed.check_alarm(replace(request, minute=31))
    await bed.configure_alarm(replace(request, enabled=False, slot=2, time_provided=False))
    assert frames(client)[-1] == codec.alarm(
        (codec.Alarm(6, 0, 1, 1), codec.Alarm(8, 0, 1, 2)), 2, 1
    )


async def test_alarm_delete_compacts_and_partial_cancel_does_not_write_replacement(hass):
    coord, bed, client = await target(hass)
    notify(bed)
    notify(bed, bank=0x80)
    await coord.async_execute_controller_command(lambda c: c.delete_alarm(2))
    assert frames(client) == [
        codec.alarm((codec.Alarm(6, 0, 1, 1), codec.Alarm(10, 0, 129, 1)), 1, 1),
        codec.alarm((codec.Alarm(12, 0, 129, 2), ctrl.EMPTY), 4, 0x34),
    ]
    notify(bed)
    notify(bed, bank=0x80)
    client.write_gatt_char.reset_mock()

    async def stop_after_first(*args, **kwargs):
        coord.cancel_command.set()

    client.write_gatt_char.side_effect = stop_after_first
    await coord.async_execute_controller_command(lambda c: c.delete_alarm(1))
    assert len(frames(client)) == 1
    assert bed._alarms == [None] * 4


@pytest.mark.parametrize("failure", ["cancel", "error", "replacement"])
async def test_motion_settles_origin_write_before_release(hass, failure):
    coord, bed, client = await target(hass)
    entered, finish = asyncio.Event(), asyncio.Event()
    original = bed._link

    async def write(_char, packet, **kwargs):
        if packet[2] == 1:
            entered.set()
            await finish.wait()
            if failure == "error":
                raise RuntimeError("backend failed after submission")

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.hold_control("back_up", 2000))
    )
    await entered.wait()
    if failure == "replacement":
        await bed.async_discover_capabilities()
    if failure != "error":
        task.cancel()
        await asyncio.sleep(0)
    finish.set()
    if failure == "error":
        with pytest.raises(RuntimeError, match="backend failed after submission"):
            await task
        from custom_components.adjustable_bed.command_scheduler import CommandOutcome

        assert not task.cancelled()
        assert coord.command_scheduler.recent_records[-1].outcome is CommandOutcome.FAILED
    else:
        with pytest.raises((asyncio.CancelledError, ConnectionError)):
            await task
    assert frames(client) == [codec.frame(1, 1)] + (
        [] if failure == "replacement" else [codec.frame(3, 1)]
    )
    if failure == "replacement":
        bed._notification(original, bytearray(codec.frame(4, 1)))
        assert coord.controller_state.get(UNDER_BED_LIGHTS_ON) is None


async def test_cancelled_subscribe_settles_and_unsubscribes(hass):
    coord, bed, client = await target(hass)
    await bed.stop_notify()
    await bed.async_discover_capabilities()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def subscribe(*args):
        entered.set()
        await finish.wait()

    client.start_notify.side_effect = subscribe
    task = asyncio.create_task(bed.start_notify())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bed._link is None
    assert client.stop_notify.await_count == 2


async def test_startup_clock_and_superseded_controller_cannot_unsubscribe(hass):
    coord, old, client = await target(hass)
    old_link = old._link
    bed = ctrl.GhostBedController(coord)
    coord._controller = bed
    await bed.async_discover_capabilities()
    with patch(
        "custom_components.adjustable_bed.beds.flexispot.ghostbed.dt_util.now",
        return_value=datetime(2026, 11, 23, 14, 5, 6),
    ):
        await bed.start_notify()
    assert frames(client) == [codec.frame(0x34, 3, {4: 14, 5: 5, 6: 6, 7: 1})]
    notify(bed)
    await old.stop_notify()
    client.stop_notify.assert_not_awaited()
    old._notification(old_link, bytearray(codec.frame(4, 2)))
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is True
    await bed.stop_notify()


@pytest.mark.parametrize("operation", ["snore", "alarm", "level"])
async def test_changed_snapshot_while_waiting_for_ble_lane_is_rejected(hass, operation):
    coord, bed, client = await target(hass)
    notify(bed)
    notify(bed, bank=0x80)
    if operation == "snore":
        command = bed.snore_home(False)
    elif operation == "level":
        command = bed.set_level("upper", 4)
    else:
        command = bed.configure_alarm(
            AlarmRequest(enabled=False, slot=1, reference_time=datetime.now(), time_provided=False)
        )
    async with bed._ble_lock:
        task = asyncio.create_task(command)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        notify(bed, slots=(codec.Alarm(7, 0, 1, 1), codec.Alarm(8, 0, 129, 2)))
    with pytest.raises(ServiceValidationError):
        await task
    assert frames(client) == []


async def test_renewable_movement_uses_proven_cadence_and_axis_cleanup(hass):
    coord, bed, client = await target(hass)
    with virtual_clock():
        await coord.async_execute_controller_command(lambda c: c.hold_control("feet_down", 450))
    assert frames(client) == [codec.frame(2, 2)] * 3 + [codec.frame(3, 2)]


async def test_subscribe_never_resolves_a_successor_after_waiting(hass):
    coord, old, client = await target(hass)
    await old.stop_notify()
    await old.async_discover_capabilities()
    original = old._link
    async with old._owner.subscription_lock:
        task = asyncio.create_task(old.start_notify())
        await asyncio.sleep(0)
        new = ctrl.GhostBedController(coord)
        coord._controller = new
        await new.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await task
    assert client.start_notify.await_count == 1  # Only the initial target setup.
    old._notification(original, bytearray(codec.frame(4, 1)))
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is None
    await new.start_notify()
    assert client.start_notify.await_count == 2
    await new.stop_notify()


async def test_successor_subscribe_waits_for_submitted_origin_unsubscribe(hass):
    coord, old, client = await target(hass)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def stop(*args):
        entered.set()
        await finish.wait()

    client.stop_notify.side_effect = stop
    cleanup = asyncio.create_task(old.stop_notify())
    await entered.wait()
    new = ctrl.GhostBedController(coord)
    coord._controller = new
    await new.async_discover_capabilities()
    subscribe = asyncio.create_task(new.start_notify())
    await asyncio.sleep(0)
    assert client.start_notify.await_count == 1
    finish.set()
    await cleanup
    await subscribe
    assert client.start_notify.await_count == 2
    await new.stop_notify()


async def test_public_alarm_can_edit_disabled_record_without_arming_it(hass):
    coord, bed, client = await target(hass)
    device = await _service_target(hass, coord)
    notify(bed)
    notify(bed, bank=0x80)
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {
            "device_id": [device.id],
            "enabled": False,
            "slot": 3,
            "time": "15:30",
            "weekdays": ["tuesday"],
            "wake_action": "wake_mode_2",
        },
        blocking=True,
    )
    assert frames(client) == [
        codec.alarm((codec.Alarm(15, 30, 2, 2), codec.Alarm(12, 0, 129, 2)), 4, 0x34)
    ]


@pytest.mark.parametrize(
    "teardown", ["failed_disconnect", "cancelled_pairing_release", "task_cancelled_pairing_release"]
)
async def test_coordinator_restores_only_the_retained_physical_session(hass, teardown):
    from bleak.exc import BleakError

    coord, bed, client = await target(hass)
    coord._link_ready = True
    original = bed._link
    original_disconnect = client.disconnect.side_effect
    try:
        if teardown == "failed_disconnect":
            client.disconnect.side_effect = BleakError("still connected")
            assert await coord.async_disconnect("idle_timeout") is False
        elif teardown == "cancelled_pairing_release":
            client.disconnect.side_effect = asyncio.CancelledError
            with pytest.raises(asyncio.CancelledError):
                await coord.async_release_for_pairing_transfer()
            assert not coord._pairing_transfer_active
        else:
            entered = asyncio.Event()

            async def blocked_disconnect():
                entered.set()
                await asyncio.Event().wait()

            client.disconnect.side_effect = blocked_disconnect
            release = asyncio.create_task(coord.async_release_for_pairing_transfer())
            await entered.wait()
            release.cancel()
            with pytest.raises(asyncio.CancelledError):
                await release
            assert not coord._pairing_transfer_active
        assert client.is_connected and coord._link_ready
        assert await coord.async_connect()
        assert bed._link is original and bed._suspended_link is None
        assert client.start_notify.await_count == 2
        assert client.start_notify.call_args.args[0] is original.notify
        assert frames(client)[-1][2:4] == bytes((0x34, 3))
        # Restoration must leave unknown records unknown, then admit fresh native state.
        assert bed._alarms == [None] * 4
        await coord.async_execute_controller_command(lambda c: c.lights_on())
        assert frames(client)[-1] == codec.frame(4, 1)
        assert client.write_gatt_char.call_args.args[0] is original.write
    finally:
        client.disconnect.side_effect = original_disconnect


@pytest.mark.parametrize("replacement", ["client", "gatt", "successor", "successor_released"])
async def test_suspended_session_cannot_reclaim_replacement_ownership(hass, replacement):
    coord, bed, client = await target(hass)
    await bed.stop_notify()
    assert bed._link is None and bed._suspended_link is not None
    if replacement == "client":
        coord._client = SimpleNamespace(**vars(client))
    elif replacement == "gatt":
        client.services = _Services([_Service()])
    else:
        successor = ctrl.GhostBedController(coord)
        coord._controller = successor
        await successor.async_discover_capabilities()
        if replacement == "successor_released":
            successor.on_disconnect()
    publisher = bed._owner.publisher
    client.start_notify.reset_mock()
    client.stop_notify.reset_mock()
    with pytest.raises(ConnectionError):
        await bed.async_resume_session()
    assert bed._owner.publisher is publisher
    assert bed._link is None
    client.start_notify.assert_not_awaited()
    client.stop_notify.assert_not_awaited()
    # Restore the test coordinator's physical handle for orderly shutdown.
    coord._client = client


@pytest.mark.parametrize("notification_at", ["first_write", "between_writes"])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_native_alarm_rejects_snapshot_superseded_by_delete_second_submission(
    hass, monkeypatch, notification_at, outcome
):
    from bleak.exc import BleakError

    coord, bed, client = await target(hass)
    device = await _service_target(hass, coord)
    a, b, c, d = (codec.Alarm(hour, 0, 129, 1) for hour in (6, 8, 10, 12))
    notify(bed, slots=(a, b))
    notify(bed, bank=0x80, slots=(c, d))
    entered, finish = asyncio.Event(), asyncio.Event()

    def interleaved_reports():
        notify(bed, slots=(a, c))
        notify(bed, bank=0x80, slots=(c, d))

    async def gap(_event, _seconds):
        if notification_at == "between_writes":
            interleaved_reports()

    monkeypatch.setattr(bed, "_wait", gap)
    calls = 0

    async def write(_char, _packet, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1 and notification_at == "first_write":
            interleaved_reports()
        if calls == 2:
            assert bed._alarms == [None] * 4  # Invalidate before the backend await.
            if outcome == "failure":
                raise BleakError("second write uncertain")
            if outcome == "cancel":
                entered.set()
                await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(coord.async_execute_controller_command(lambda c: c.delete_alarm(2)))
    if outcome == "cancel":
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        finish.set()
    if outcome == "success":
        await task
    else:
        with pytest.raises(BleakError if outcome == "failure" else asyncio.CancelledError):
            await task
    assert frames(client) == [codec.alarm((a, c), 1, 1), codec.alarm((d, ctrl.EMPTY), 4, 0x34)]
    assert bed._alarms == [None] * 4
    edit = {
        "device_id": [device.id],
        "enabled": True,
        "slot": 4,
        "time": "14:00",
        "weekdays": ["monday"],
        "wake_action": "wake_mode_1",
    }
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_alarm", edit, blocking=True)
    assert len(frames(client)) == 2
    # Fresh post-second-submission banks admit the real native action safely.
    notify(bed, slots=(a, c))
    notify(bed, bank=0x80, slots=(d, ctrl.EMPTY))
    client.write_gatt_char.side_effect = None
    await hass.services.async_call(DOMAIN, "set_alarm", edit, blocking=True)
    assert frames(client)[-1] == codec.alarm((d, codec.Alarm(14, 0, 129, 1)), 4, 0x34)


async def test_post_second_submission_notifications_survive_backend_completion(hass):
    coord, bed, client = await target(hass)
    device = await _service_target(hass, coord)
    a, b, c, d = (codec.Alarm(hour, 0, 129, 1) for hour in (6, 8, 10, 12))
    notify(bed, slots=(a, b))
    notify(bed, bank=0x80, slots=(c, d))
    calls = 0

    async def write(_char, _packet, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            assert bed._alarms == [None] * 4
            notify(bed, slots=(a, c))
            notify(bed, bank=0x80, slots=(d, ctrl.EMPTY))

    client.write_gatt_char.side_effect = write
    await coord.async_execute_controller_command(lambda c: c.delete_alarm(2))
    assert bed._all_alarms() == (a, c, d, ctrl.EMPTY)
    client.write_gatt_char.side_effect = None
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {
            "device_id": [device.id],
            "enabled": True,
            "slot": 4,
            "time": "14:00",
            "weekdays": ["monday"],
            "wake_action": "wake_mode_1",
        },
        blocking=True,
    )
    assert frames(client)[-1] == codec.alarm((d, codec.Alarm(14, 0, 129, 1)), 4, 0x34)


async def test_packet_bytes_stay_in_protocol_diagnostics_and_raw_capture(hass):
    coord, bed, client = await target(hass)
    captured = Mock()
    bed.set_raw_notify_callback(captured)
    raw = notify(bed)
    assert bed.protocol_diagnostics["raw_status"] == bytes(raw).hex()
    captured.assert_called_once_with(codec.NOTIFY, bytes(raw))
    assert "ghostbed_raw_status" not in coord.controller_state
    assert [spec.key for spec in bed.controller_state_sensor_specs] == ["ghostbed_alarms"]
    await bed.stop_notify()
    assert bed.protocol_diagnostics["raw_status"] is None


async def test_alarm_sensor_decodes_only_proven_record_labels(hass):
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    coord, bed, client = await target(hass)
    notify(bed, slots=(codec.Alarm(6, 30, 193, 1), codec.Alarm(8, 45, 2, 2)))
    notify(bed, bank=0x80, slots=(ctrl.EMPTY, codec.Alarm(9, 15, 132, 17)))
    entity = AdjustableBedControllerStateSensor(coord, bed.controller_state_sensor_specs[0])
    assert entity.native_value == (
        "1: 06:30 · On · Mon, Sun · Basic; 2: 08:45 · Off · Tue · Pro; "
        "3: Not set; 4: 09:15 · On · Wed · Unknown"
    )
    # Values with unknown meaning retain their original bytes only in diagnostics.
    assert bed.protocol_diagnostics["alarms"][3]["pattern"] == 17
    longest = codec.Alarm(23, 59, 255, 1)
    notify(bed, slots=(longest, longest))
    notify(bed, bank=0x80, slots=(longest, longest))
    assert len(entity.native_value) <= 255
    bed.on_disconnect()
    assert entity.native_value is None
