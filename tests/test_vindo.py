"""Vindö's real GATT lifecycle and controller commands against an offline link."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds import vindo
from custom_components.adjustable_bed.beds.vindo import VindoController
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_VINDO,
    LINAK_CONTROL_CHAR_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_LEG_UUID,
    LINAK_POSITION_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from scripts.wire_snapshot import FakeClock, virtual_time


@pytest.fixture
def receiver():
    control = SimpleNamespace(uuid=LINAK_CONTROL_CHAR_UUID, handle=1, properties=["write"])
    legs = SimpleNamespace(uuid=LINAK_POSITION_LEG_UUID, handle=2, properties=["notify"])
    back = SimpleNamespace(uuid=LINAK_POSITION_BACK_UUID, handle=3, properties=["indicate"])
    control_roles = {control.uuid: control}
    position_roles = {legs.uuid: legs, back.uuid: back}
    services = {
        LINAK_CONTROL_SERVICE_UUID: SimpleNamespace(get_characteristic=control_roles.get),
        LINAK_POSITION_SERVICE_UUID: SimpleNamespace(get_characteristic=position_roles.get),
    }
    callbacks = {}

    async def subscribe(char, notify):
        callbacks[char.uuid] = notify

    client = SimpleNamespace(
        is_connected=True,
        services=SimpleNamespace(get_service=services.get),
        start_notify=AsyncMock(side_effect=subscribe),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )
    state = {}

    def update_state(*updates):
        state.update((update.key, update.value) for update in updates)

    coordinator = SimpleNamespace(
        client=client,
        motor_pulse_count=2,
        motor_pulse_delay_ms=300,
        cancel_command=asyncio.Event(),
        address="AA:BB:CC:DD:EE:FF",
        record_command_trace=MagicMock(),
        async_write_app_state=AsyncMock(),
        handle_controller_state_updates=update_state,
        handle_controller_state_update=state.__setitem__,
    )

    def notify(char, data):
        callbacks[char.uuid](char, bytearray(data))

    def samples(back_value, legs_value):
        notify(back, back_value.to_bytes(2, "little"))
        notify(legs, legs_value.to_bytes(2, "little"))

    return SimpleNamespace(
        client=client,
        coordinator=coordinator,
        controller=VindoController(coordinator),
        control=control,
        back=back,
        legs=legs,
        callbacks=callbacks,
        notify=notify,
        samples=samples,
        state=state,
        position_roles=position_roles,
        frames=lambda: [call.args[1].hex() for call in client.write_gatt_char.await_args_list],
    )


@pytest.mark.parametrize("name", ["Bed LiNaK 12", "LIN2BLE 34", "x-bLe2LiN 56"])
def test_discovery_offers_vindo_beside_the_shared_linak_route(name):
    info = SimpleNamespace(
        name=name,
        service_uuids=[LINAK_CONTROL_SERVICE_UUID.upper()],
        manufacturer_data={},
        address="AA:BB:CC:DD:EE:FF",
        service_data={},
    )
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type == BED_TYPE_LINAK
    assert BED_TYPE_VINDO in (detected.ambiguous_types or ())
    info.service_uuids = [LINAK_POSITION_SERVICE_UUID]
    assert BED_TYPE_VINDO not in (detect_bed_type_detailed(info).ambiguous_types or ())
    info.name, info.service_uuids = "Other bed", [LINAK_CONTROL_SERVICE_UUID]
    assert BED_TYPE_VINDO not in (detect_bed_type_detailed(info).ambiguous_types or ())


async def test_position_subscriptions_gate_writes_and_guard_old_callbacks(receiver):
    bed = receiver.controller
    with pytest.raises(BedNotConnectedError):
        await bed.lights_toggle()
    await bed.start_notify()
    assert [call.args[0] for call in receiver.client.start_notify.await_args_list] == [
        receiver.legs,
        receiver.back,
    ]
    assert receiver.frames() == []
    receiver.notify(receiver.legs, bytes.fromhex("341299"))
    receiver.notify(receiver.back, bytes.fromhex("ffff"))
    assert receiver.state == {"vindo_legs_raw": 4660, "vindo_back_raw": 65535}
    receiver.notify(receiver.back, b"\xff")
    assert receiver.state["vindo_back_raw"] is None
    late = receiver.callbacks[receiver.legs.uuid]
    await bed.stop_notify()
    await bed.start_notify()
    late(receiver.legs, bytearray.fromhex("1234"))
    assert receiver.state == {"vindo_legs_raw": None, "vindo_back_raw": None}
    await bed.lights_toggle()
    receiver.client.write_gatt_char.assert_awaited_once_with(
        receiver.control,
        bytes.fromhex("9400"),
        response=True,
    )


async def test_partial_subscription_unwinds_and_blocks_control(receiver):
    bed = receiver.controller

    async def subscribe(char, callback):
        if char is receiver.back:
            raise BleakError("subscription failed")
        receiver.callbacks[char.uuid] = callback

    receiver.client.start_notify.side_effect = subscribe
    with pytest.raises(BleakError, match="subscription failed"):
        await bed.start_notify()
    assert [call.args[0] for call in receiver.client.stop_notify.await_args_list] == [
        receiver.legs,
        receiver.back,
    ]
    with pytest.raises(BedNotConnectedError):
        await bed.move_back_up()
    assert receiver.frames() == []


async def test_startup_rejects_a_missing_role_before_subscribing(receiver):
    receiver.position_roles.clear()
    with pytest.raises(BleakError, match=LINAK_POSITION_SERVICE_UUID):
        await receiver.controller.start_notify()
    receiver.client.start_notify.assert_not_awaited()


async def test_cancellation_settles_the_write_before_stop(receiver):
    bed = receiver.controller
    await bed.start_notify()
    pending_write, finish_write = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **_):
        if data == bytes.fromhex("0b00"):
            pending_write.set()
            await finish_write.wait()

    receiver.client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(bed.move_back_up())
    await pending_write.wait()
    movement.cancel()
    assert receiver.frames() == ["0b00"]
    finish_write.set()
    with pytest.raises(asyncio.CancelledError):
        await movement
    assert receiver.frames() == ["0b00", "ff00"]


async def test_old_movement_does_not_stop_on_a_replacement_link(receiver, monkeypatch):
    bed = receiver.controller
    await bed.start_notify()

    async def replace_link(*_):
        bed.on_disconnect()
        await bed.start_notify()

    monkeypatch.setattr(vindo, "_pause", replace_link)
    with pytest.raises(BedNotConnectedError):
        await bed.move_back_up()
    assert receiver.frames() == ["0b00"]
    await bed.stop_all()
    assert receiver.frames() == ["0b00", "ff00"]


async def test_raw_memory_saves_then_recalls_from_fresh_feedback(receiver, monkeypatch):
    bed = receiver.controller
    await bed.start_notify()
    receiver.samples(200, 200)
    await bed.program_memory(1)
    receiver.coordinator.async_write_app_state.assert_awaited_once_with(bed, {"1": [200, 200]})
    assert receiver.frames() == []

    # Restore only the saved target. Incoming feedback still belongs to this link.
    saved = bed.persisted_app_state
    bed.restore_persisted_app_state(saved)
    receiver.samples(100, 100)

    async def advance(_event, seconds):
        assert seconds == 0.300
        receiver.samples(185, 215)

    monkeypatch.setattr(vindo, "_pause", advance)
    await bed.preset_memory(1)
    assert receiver.frames() == ["3700", "ff00"]


async def test_recall_requires_both_recent_axes_and_stops_when_feedback_is_lost(
    receiver, monkeypatch
):
    bed = receiver.controller
    await bed.start_notify()
    bed.restore_persisted_app_state({"1": [200, 200]})
    receiver.notify(receiver.back, bytes.fromhex("6400"))
    monkeypatch.setattr(vindo, "_POSITION_FRESH_S", 0.001)
    with pytest.raises(ValueError, match="fresh positions from both motors"):
        await bed.preset_memory(1)
    assert receiver.frames() == []

    monkeypatch.setattr(vindo, "_POSITION_FRESH_S", 2.0)
    receiver.samples(100, 100)

    async def expire(*_):
        receiver.notify(receiver.legs, bytes.fromhex("ffff"))

    monkeypatch.setattr(vindo, "_pause", expire)
    with pytest.raises(ValueError, match="stopped receiving fresh positions"):
        await bed.preset_memory(1)
    assert receiver.frames() == ["3700", "ff00"]


@pytest.mark.parametrize("feedback", ["changed", "arrived", "invalid", "expired"])
async def test_recall_selects_direction_only_when_the_write_lane_is_available(
    receiver, monkeypatch, feedback: str
):
    bed = receiver.controller
    await bed.start_notify()
    bed.restore_persisted_app_state({"1": [200, 200]})
    pending_tick = asyncio.Event()
    clock = FakeClock()

    async def occupy_lane(_event, _seconds):
        if not pending_tick.is_set():
            await bed.ble_lock.acquire()
            pending_tick.set()

    async def write(_char, data, **_kwargs):
        if data == bytes.fromhex("3400"):
            receiver.samples(200, 200)

    receiver.client.write_gatt_char.side_effect = write
    monkeypatch.setattr(vindo, "_pause", occupy_lane)
    with virtual_time(clock):
        receiver.samples(100, 100)
        recall = asyncio.create_task(bed.preset_memory(1))
        await pending_tick.wait()
        assert receiver.frames() == ["3700"]
        if feedback == "changed":
            receiver.samples(300, 300)
        elif feedback == "arrived":
            receiver.samples(200, 200)
        elif feedback == "invalid":
            receiver.notify(receiver.legs, b"\xff")
        else:
            clock.now += vindo._POSITION_FRESH_S + 0.01
        bed.ble_lock.release()
        if feedback in ("invalid", "expired"):
            with pytest.raises(ValueError, match="stopped receiving fresh positions"):
                await recall
        else:
            await recall
    expected = ["3700", "3400", "ff00"] if feedback == "changed" else ["3700", "ff00"]
    assert receiver.frames() == expected


@pytest.mark.parametrize(
    ("user_ms", "cap_ms", "last_ack", "motion_times", "stop_time"),
    [
        (1000, 20000, 0.02, [0, 0.32, 0.64, 0.96], 1.0),
        (1000, 20000, 0.08, [0, 0.32, 0.64, 0.96], 1.04),
        (1000, 760, 0.02, [0, 0.32, 0.64], 0.76),
    ],
)
async def test_combined_movement_honors_elapsed_limit_between_refreshes(
    receiver, monkeypatch, user_ms, cap_ms, last_ack, motion_times, stop_time
):
    bed = receiver.controller
    await bed.start_notify()
    clock = FakeClock()
    times = []

    async def write(_char, data, **_kwargs):
        times.append(clock.now)
        if data == bytes.fromhex("3700"):
            await asyncio.sleep(last_ack if len(times) == 4 else 0.02)

    receiver.client.write_gatt_char.side_effect = write
    monkeypatch.setattr(vindo.app, "HOLD_LIMIT_MS", cap_ms)
    with virtual_time(clock):
        await bed.move_simultaneously("back", True, "legs", True, duration_ms=user_ms)

    assert receiver.frames() == ["3700"] * len(motion_times) + ["ff00"]
    assert times == pytest.approx([*motion_times, stop_time])


@pytest.mark.parametrize("end", ["cancel", "stop_event", "deadline"])
async def test_motion_leaves_only_stop_queued_when_the_lane_stays_occupied(receiver, end):
    bed = receiver.controller
    await bed.start_notify()
    clock = FakeClock()
    with virtual_time(clock):
        async with bed.ble_lock:
            movement = asyncio.create_task(
                bed.move_simultaneously(
                    "back", True, "legs", True, duration_ms=100 if end == "deadline" else 1000
                )
            )
            await asyncio.sleep(0)
            if end == "cancel":
                movement.cancel()
            elif end == "stop_event":
                receiver.coordinator.cancel_command.set()
            await asyncio.sleep(0.15)
            assert receiver.frames() == []
        if end == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await movement
        else:
            await movement
    assert receiver.frames() == ["ff00"]


async def test_recall_uses_fresh_starting_direction_and_reports_unreached_target(
    receiver, monkeypatch
):
    bed = receiver.controller
    await bed.start_notify()
    bed.restore_persisted_app_state({"1": [200, 200]})
    receiver.samples(200, 200)
    await bed.preset_memory(1)
    assert receiver.frames() == ["ff00"]

    receiver.samples(100, 100)
    monkeypatch.setattr(vindo.app, "REFRESH_MS", vindo.app.HOLD_LIMIT_MS)
    with pytest.raises(ValueError, match="did not reach the saved position"):
        await bed.preset_memory(1)
    assert receiver.frames() == ["ff00", "3700", "ff00"]


async def test_light_and_massage_entity_actions_use_verified_one_shots(receiver, monkeypatch):
    bed = receiver.controller
    await bed.start_notify()
    pauses = []

    async def skip_wait(_event, seconds):
        pauses.append(seconds)

    monkeypatch.setattr(vindo, "_pause", skip_wait)
    buttons = {spec.key: spec for spec in bed.controller_button_specs}
    await bed.lights_on()
    await bed.lights_off()
    await buttons["vindo_light_brighter"].press_fn(bed)
    await buttons["vindo_light_dimmer"].press_fn(bed)
    await bed.massage_head_up()
    await bed.massage_head_down()
    await bed.massage_foot_up()
    await bed.massage_foot_down()
    await bed.massage_toggle()
    await buttons["vindo_massage_pattern_2"].press_fn(bed)
    assert receiver.frames() == [
        "9200",
        "9300",
        "9e00",
        "9f00",
        "8d00",
        "8e00",
        "8f00",
        "9000",
        "9100",
        "8000",
        "9100",
        "8100",
        "8100",
    ]
    assert pauses == [0.800] * 3

    pauses.clear()
    receiver.client.write_gatt_char.reset_mock()
    await buttons["vindo_identify"].press_fn(bed)
    assert receiver.frames() == ["9200", "9300", "9200", "9300"]
    assert pauses == [1.0, 0.8, 1.0]
