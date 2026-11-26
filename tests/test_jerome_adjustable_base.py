"""Literal vectors and controller behavior for the four Jerome's Adjustable Base models."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat import jerome_adjustable_base as bed
from custom_components.adjustable_bed.beds.richmat.jerome_alarm import RepeatAlarm
from custom_components.adjustable_bed.beds.richmat_app import protocol
from custom_components.adjustable_bed.beds.richmat_app.receive import EXACT, FrameBuffer
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import jerome_adjustable_base as p
from tests.error_helpers import raises_key
from tests.state_helpers import state_writer

VECTORS = json.loads((Path(__file__).parent / "fixtures/jerome_adjustable_base.json").read_text())
NOW = datetime(2026, 11, 26, 23, 59, 5, tzinfo=UTC)

ACTIONS = {
    **{
        f"{name} {direction}": code
        for motor, name in zip(p.MOTORS, ("Head", "Foot", "Head and foot"), strict=True)
        for direction, code in zip(("up", "down"), p.MOTORS[motor], strict=True)
    },
    **{
        f"{name} {gesture}": code
        for key, name in bed.PRESET_NAMES.items()
        for gesture, code in zip(("recall", "program"), p.PRESETS[key], strict=True)
    },
    "Flat": p.FLAT,
    "Head massage intensity step up": p.WAVE_MASSAGE["Head massage intensity up"],
    "Foot massage intensity step up": p.WAVE_MASSAGE["Foot massage intensity up"],
    "Massage pattern step": p.WAVE_MASSAGE["Next massage pattern"],
    "Massage off": p.WAVE_MASSAGE["Massage off"],
    **{f"Massage {time} minutes": code for time, code in p.MASSAGE_TIMERS.items()},
    "Under-bed light board toggle": p.LIGHT_TOGGLE,
    "Motor STOP on release or cancellation": codec.STOP,
    "Onboarding head up test": p.MOTORS["head"][0],
    "Onboarding head down test": p.MOTORS["head"][1],
    "Onboarding STOP": codec.STOP,
    # The codec reproduces the long Flat operand. The runtime does not offer it.
    "Flat 3-second hold": 0,
}
STARTUP = dict(
    zip(
        ("Exit one-minute mode", "Check clock", "Check light", "Check music"),
        (p.EXIT_MODE, *p.PROBES),
        strict=True,
    )
)


@pytest.mark.parametrize("vector", VECTORS["outbound"], ids=lambda vector: vector[0])
def test_outbound_vector(vector):
    _, action, row, expected = vector
    match row["form"]:
        case "single" | "side" | "fixed-prefix":
            selector, code = STARTUP[action] if action in STARTUP else ("", ACTIONS[action])
            actual = codec.function(
                code, row.get("side", 0), action=selector, single=row["form"] == "single"
            )
        case "alarm-low":
            actual = codec.countdown(row["minutes"], 0)[0]
        case "alarm-high":
            actual = codec.countdown(row["minutes"], row["action_code"])[1]
        case "white-light":
            actual = codec.rgb(255, 255, 255)
        case "light-timeout":
            assert row["seconds"] in p.LIGHT_TIMERS.values()
            actual = protocol.light_timer(row["seconds"])
        case "repeat-list":
            actual = protocol.QUERY["alarms"]
        case "repeat-delete":
            actual = protocol.delete_alarm(row["id"])
        case "repeat-upsert":
            record = RepeatAlarm.edited(
                row["id"], row["hour"], row["minute"], row["action_code"], tuple(row["weekdays"])
            )
            assert record.raw_7 == row["raw_7"]
            actual = record.with_enabled(row["enabled"]).encode()
        case "clock-sync":
            actual = codec.calendar(NOW, build=codec.record_20_len)
        case _:
            pytest.fail(f"Unrecognized outbound fixture {row}")
    assert actual == bytes.fromhex(expected)


def test_frozen_gatt_and_exact_replies():
    assert [
        (route.service_uuid, route.write_uuid, route.notify_uuid)
        for key in p.TRANSPORTS
        if (route := codec.TRANSPORTS[key])
    ] == [tuple(row) for row in VECTORS["gatt"]]
    assert [EXACT[bytes.fromhex(frame).hex()] for frame, _ in VECTORS["replies"]] == [
        "clock_available",
        "light_available",
        "aroma_available",
        "alarm_saved",
        "alarm_cancelled",
        "music_available",
        "detection_available",
        "snore_available",
        "locked",
        "unlocked",
        "stop_music",
    ]


@pytest.mark.parametrize("vector", VECTORS["incoming"], ids=lambda vector: vector[0])
def test_frozen_receive_envelope(vector):
    _, chunks, expected = vector
    buffer = FrameBuffer()
    events = []
    last = 0
    for timestamp, data in chunks:
        if timestamp - last >= round(p.RECEIVE_EXPIRY_S * 1000):
            buffer.pending.clear()
        last = timestamp
        for frame in buffer.frames(bytes.fromhex(data)):
            parsed = RepeatAlarm.decode(frame)
            if parsed is not None:
                direction, record = parsed
                assert record.raw_7 == 0
                events.append((direction, record.attributes()))
    assert events == [
        (
            2 if row["kind"] == "list" else 3,
            {
                "slot": row["id"],
                "hour": row["hour"],
                "minute": row["minute"],
                "action_code": row["action_code"],
                "enabled": row["enabled"],
                "weekdays": ["monday" if day == "Mon" else "wednesday" for day in row["weekdays"]],
            },
        )
        for row in expected
    ]


def make_client(route):
    return SimpleNamespace(
        is_connected=True,
        services=[
            SimpleNamespace(
                uuid=route.service_uuid,
                characteristics=[
                    SimpleNamespace(
                        uuid=route.notify_uuid,
                        properties=["notify"],
                        handle=11,
                        descriptors=[],
                    ),
                    SimpleNamespace(
                        uuid=route.write_uuid,
                        handle=12,
                        properties=["write", "write-without-response"],
                        descriptors=[],
                    ),
                    SimpleNamespace(
                        uuid=route.notify_uuid,
                        properties=["notify"],
                        handle=13,
                        descriptors=[],
                    ),
                ],
            ),
        ],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )


@pytest.fixture
def create(monkeypatch):
    monkeypatch.setattr(bed, "TICK_S", 0.001)
    monkeypatch.setattr(p, "PROBE_DELAY_S", 0)
    monkeypatch.setattr(p, "PRESET_SAVE_S", 0.001)
    monkeypatch.setattr(bed.dt_util, "now", lambda: NOW)

    async def build(product, transport):
        coordinator = MagicMock(controller_state={}, cancel_command=asyncio.Event())
        coordinator.handle_controller_state_updates.side_effect = state_writer(
            coordinator.controller_state
        )
        coordinator.client = make_client(codec.TRANSPORTS[transport])
        controller = bed.JeromeAdjustableBaseController(coordinator, product=product)
        coordinator.controller = controller
        await controller.start_notify()
        return coordinator, controller

    return build


def writes(coordinator):
    return written_frames(coordinator.client)


def written_frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


def notify(coordinator, raw):
    rx, callback = coordinator.client.start_notify.await_args.args
    callback(rx, bytearray.fromhex(raw))


@pytest.mark.parametrize("model", p.PRODUCTS)
@pytest.mark.parametrize("transport", p.TRANSPORTS)
async def test_live_picker_models_and_transport_startup(create, model, transport):
    coordinator, controller = await create(model, transport)
    expected = (
        ["00", "01", "01", "01"]
        if transport == "n1"
        else [
            "6e02010071",
            "6e08010178",
            "6e0a000179",
            "6e15010185",
        ]
    )
    assert writes(coordinator) == [*expected, "6e200d080301380b1a173b055b"]
    assert coordinator.client.start_notify.await_args.args[0].handle == 11
    assert controller.memory_slot_count == (2 if model in ("HDRN", "JERN") else 1)
    assert controller.supports_light_timer == (model in ("HDRN", "JERN"))
    assert bool(controller.controller_select_specs) == (model in ("HERN", "JERN"))
    assert not controller.supports_single_address_pairing
    assert controller.alarm_capability.weekdays == (model in ("HERN", "JERN"))
    coordinator.client.write_gatt_char.reset_mock()
    await controller.preset_flat()
    await controller.program_memory(1)
    assert writes(coordinator) == (
        ["31", "2b"] if transport == "n1" else ["6e010031a0", "6e01002b9a"]
    )


async def test_side_change_and_early_release_keep_admitted_end(create, monkeypatch):
    coordinator, controller = await create("HERN", "w1")
    coordinator.client.write_gatt_char.reset_mock()
    controller._select_side("right")

    async def release_before_movement(_seconds, cancel):
        controller._select_side("left")
        cancel.set()
        return False

    monkeypatch.setattr(controller, "_wait", release_before_movement)
    await controller.hold_control("jerome_adjustable_base_head_up", 1000)
    assert writes(coordinator) == ["6e01016ede"]

    coordinator.cancel_command.clear()
    coordinator.client.write_gatt_char.reset_mock()
    monkeypatch.setattr(controller, "_wait", AsyncMock(return_value=True))

    async def flip_side(*_args, **_kwargs):
        controller._select_side("right")
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = flip_side
    await controller.hold_control("jerome_adjustable_base_head_up", 100)
    assert writes(coordinator) == ["6e01002493", "6e01006edd"]


async def test_reconnect_cannot_receive_end_or_old_notifications(create):
    coordinator, controller = await create("HERN", "w1")
    old_client = coordinator.client
    old_client.write_gatt_char.reset_mock()
    controller._select_side("right")

    async def change_session(*_args, **_kwargs):
        old_client.is_connected = False
        controller.on_disconnect()
        coordinator.client = make_client(codec.TRANSPORTS["n1"])

    old_client.write_gatt_char.side_effect = change_session
    await controller.hold_control("jerome_adjustable_base_head_up", 100)
    assert old_client.write_gatt_char.await_count == 1
    await controller.start_notify()
    assert writes(coordinator) == ["00", "01", "01", "01", "6e200d080301380b1a173b055b"]
    receiver, old_notify = old_client.start_notify.await_args.args
    old_notify(receiver, bytearray.fromhex("6e09010078"))
    assert not controller._clock_ready.is_set()
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="Choose Left"):
        await controller.preset_flat()
    assert writes(coordinator) == []
    controller._select_side("left")
    await controller.preset_flat()
    assert writes(coordinator) == ["31"]


async def test_alarm_reply_stream_and_record_toggle_preserve_opaque_byte(create):
    coordinator, controller = await create("JERN", "n1")
    coordinator.client.write_gatt_char.reset_mock()
    notify(coordinator, "6e09010078")
    await controller.execute_repeat_alarm(await controller.prepare_repeat_alarm("list", None))
    with_raw = codec.record_20_len(5, 1, 2, (1, 0x8A, 6, 45, 0x58, 0xA1))
    notify(coordinator, with_raw[:4].hex())
    notify(coordinator, (with_raw[4:] + with_raw).hex())
    assert len(controller._records) == 1
    different_same_slot = codec.record_20_len(5, 1, 2, (1, 0x8B, 6, 45, 0x58, 0xA1))
    notify(coordinator, different_same_slot.hex())
    assert len(controller._records) == 2
    updated = codec.record_20_len(5, 1, 3, (1, 0x8A, 6, 45, 0x58, 0xA0))
    notify(coordinator, updated.hex())
    assert [record.repeat for record in controller._records] == [0xA0, 0xA1]
    await controller.execute_repeat_alarm(await controller.prepare_repeat_alarm("enable", 1))
    await controller.configure_alarm(AlarmRequest(enabled=False, slot=1, reference_time=NOW))
    await controller.execute_repeat_alarm(await controller.prepare_repeat_alarm("delete", 1))
    assert writes(coordinator) == [
        "6e2008050100009c",
        "6e200d050101018a062d58a159",
        "6e200d050101018a062d58a058",
        "6e2008050201019f",
    ]


async def test_wave_light_gate_and_single_alarm_ack(create):
    coordinator, controller = await create("HDRN", "w5")
    coordinator.client.write_gatt_char.reset_mock()
    with raises_key("jerome_light_not_reported", ServiceValidationError):
        await controller.toggle_light()
    notify(coordinator, "6e0e00037f")
    notify(coordinator, "6e09010078")
    await controller.toggle_light()
    await controller.white_light()
    await controller.set_light_timer("Always On")
    await controller.configure_alarm(
        AlarmRequest(enabled=True, hour=4, minute=59, wake_action="tv", reference_time=NOW)
    )
    notify(coordinator, "6e07010177")
    assert controller._clock_status == "saved"
    await controller.configure_alarm(AlarmRequest(enabled=False, reference_time=NOW))
    notify(coordinator, "6e07010278")
    assert controller._clock_status == "cancelled"
    assert writes(coordinator) == [
        "6e010050bf",
        "6e0cffff786e0dffff79",
        "6e0bffff77",
        "6e052c009f",
        "6e060158cd",
        "6e05000073",
        "6e06000074",
    ]


def test_ambiguous_matched_services_cannot_mix_a_writer_and_encoding():
    client = make_client(codec.TRANSPORTS["n1"])
    client.services.extend(make_client(codec.TRANSPORTS["w1"]).services)
    with pytest.raises(ValueError, match="More than one"):
        bed.select_app_link(client, p.TRANSPORTS, unique_service=True)


@pytest.fixture
async def ha_beds(hass, mock_coordinator_connected, mock_establish_connection, monkeypatch):
    """Real HA scheduler and public service handlers backed by isolated mock clients."""
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    targets = []
    monkeypatch.setattr(p, "PROBE_DELAY_S", 0)
    monkeypatch.setattr(p, "PRESET_SAVE_S", 0)
    monkeypatch.setattr(bed, "TICK_S", 0.005)
    monkeypatch.setattr(bed, "ALARM_REPLY_WAIT_S", 0.05)
    await async_register_services(hass)

    def resolve(_hass, device_id):
        target, side = targets[int(device_id)]
        return target, None if side == "both" else side

    monkeypatch.setattr("custom_components.adjustable_bed.services._resolve_sided_target", resolve)

    async def add(model="JERN"):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            title="Jerome bed",
            data={
                CONF_ADDRESS: f"AA:BB:CC:DD:EE:{len(targets) + 0x70:02X}",
                const.CONF_BED_TYPE: const.BED_TYPE_JEROME_ADJUSTABLE_BASE,
                const.CONF_PROTOCOL_VARIANT: model,
                const.CONF_DISABLE_ANGLE_SENSING: True,
            },
        )
        entry.add_to_hass(hass)
        target = AdjustableBedCoordinator(hass, entry)
        client = make_client(codec.TRANSPORTS["w1"])
        client.mtu_size = 23

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        client.read_gatt_char = AsyncMock()
        mock_establish_connection.side_effect = AsyncMock(return_value=client)
        assert await target.async_connect()
        notify(target, "6e09010078")
        notify(target, "6e0e00037f")
        client.write_gatt_char.reset_mock()
        targets.append((target, "both"))
        return target

    async def call(service, **data):
        await hass.services.async_call(
            const.DOMAIN,
            service,
            {"device_id": [str(index) for index in range(len(targets))], **data},
            blocking=True,
        )

    return targets, add, call


async def test_public_memory_services_use_the_model_slots(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await call("goto_preset", preset=2)
    await call("save_preset", preset=2)
    assert writes(target) == ["6e01002f9e", "6e01002c9b"]
    with pytest.raises(ServiceValidationError, match="preset"):
        await call("goto_preset", preset=3)
    assert len(writes(target)) == 2


async def _select_ha_side(target, side):
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    selector = AdjustableBedControllerSelect(target, target.controller.controller_select_specs[0])
    await selector.async_select_option(side)


async def _ha_pair(hass, targets, left, right, *, mode="concurrent", side="both"):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "jerome-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, {"left": left, "right": right}, connection_mode=mode)
    targets[:] = [(pair, side)]
    return pair


@pytest.mark.parametrize("paired", [False, True])
async def test_queued_public_hold_keeps_the_side_selected_at_admission(hass, ha_beds, paired):
    from custom_components.adjustable_bed.beds.cancellation import settled
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    targets, add, call = ha_beds
    target = await add()
    right = await add() if paired else None
    pair = None
    if right is not None:
        await _select_ha_side(right, "right")
        pair = await _ha_pair(hass, targets, target, right)
    started = asyncio.Event()
    release = asyncio.Event()
    contexts = []

    async def occupy(_controller):
        contexts.append(current_command_context())
        started.set()
        await settled(release.wait())

    occupying = asyncio.create_task(target.async_execute_controller_command(occupy))
    await started.wait()
    running = asyncio.create_task(
        call("hold_control", control="jerome_adjustable_base_head_up", duration=0.3)
    )
    try:
        await asyncio.wait_for(contexts[0].cancel_event.wait(), 1)
        await _select_ha_side(target, "right")
        if right is not None:
            await _select_ha_side(right, "left")
    finally:
        release.set()
        await asyncio.gather(occupying, running)
    assert "6e01002493" in writes(target)
    assert set(writes(target)) == {"6e01002493", "6e01006edd"}
    if right is not None and pair is not None:
        assert set(writes(right)) == {"6e01012494", "6e01016ede"}
        await pair.async_shutdown()


async def test_public_stop_during_shielded_release_sends_only_the_admitted_end(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await _select_ha_side(target, "right")
    release_started = asyncio.Event()
    let_release_finish = asyncio.Event()

    async def write(_characteristic, frame, **_kwargs):
        if frame == bytes.fromhex("6e01016ede"):
            release_started.set()
            await let_release_finish.wait()

    target.client.write_gatt_char.side_effect = write
    moving = asyncio.create_task(
        call("hold_control", control="jerome_adjustable_base_head_up", duration=0.1)
    )
    await asyncio.wait_for(release_started.wait(), 1)
    await _select_ha_side(target, "left")
    stop_epoch = target.stop_epoch
    stopping = asyncio.create_task(call("stop_all"))
    try:
        async with asyncio.timeout(1):
            while target.stop_epoch == stop_epoch:
                await asyncio.sleep(0)
    finally:
        let_release_finish.set()
        await asyncio.gather(moving, stopping)
    assert [frame for frame in writes(target) if frame in ("6e01016ede", "6e01006edd")] == [
        "6e01016ede"
    ]


async def test_public_repeat_edit_refreshes_before_disabling_the_slot(ha_beds):
    _, add, call = ha_beds
    target = await add()
    notify(target, "6e200d050102018a062d58a15a")
    assert target.controller._records[0].raw_7 == 0x8A
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
    assert target.controller._records == []
    assert writes(target) == ["6e200d0501010100070f4501ff", "6e2008050100009c"]

    async def reply(_char, frame, **_kwargs):
        if frame == protocol.QUERY["alarms"]:
            notify(target, codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1)).hex())

    target.client.write_gatt_char.side_effect = reply
    await call("set_alarm", enabled=False, slot=1)
    assert writes(target)[2:] == ["6e2008050100009c", "6e200d050101018b070f450089"]


@pytest.mark.parametrize("confirm_edit", [True, False])
async def test_public_repeat_disable_uses_only_a_confirmed_schedule(
    ha_beds, monkeypatch, confirm_edit
):
    _, add, call = ha_beds
    target = await add()
    await call("jerome_repeat_alarm", operation="list")
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")

    # The earlier list's response arrives after the edit and its refresh request.
    notify(target, "6e200d050102018a062d58a15a")
    if confirm_edit:
        notify(target, codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1)).hex())

    before_disable = len(writes(target))
    if confirm_edit:
        await call("set_alarm", enabled=False, slot=1)
        assert writes(target)[before_disable:] == ["6e200d050101018b070f450089"]
    else:
        monkeypatch.setattr(bed, "ALARM_REPLY_WAIT_S", 0.05)
        with raises_key("jerome_alarm_slot_not_reported"):
            await call("set_alarm", enabled=False, slot=1)
        assert writes(target)[before_disable:] == [protocol.QUERY["alarms"].hex()]


async def test_public_repeat_disable_ignores_update_from_before_confirmed_edit(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await call("jerome_repeat_alarm", operation="list")
    notify(target, "6e200d050102018a062d58a15a")
    await call("set_alarm", enabled=False, slot=1)
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
    notify(target, codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1)).hex())
    notify(target, codec.record_20_len(5, 1, 3, (1, 0x8A, 6, 45, 0x58, 0xA0)).hex())

    before_disable = len(writes(target))
    await call("set_alarm", enabled=False, slot=1)
    assert writes(target)[before_disable:] == ["6e200d050101018b070f450089"]


@pytest.mark.parametrize("local_edit", ["replace", "delete"])
async def test_public_explicit_list_accepts_external_edit_on_a_fresh_link(
    ha_beds, mock_establish_connection, local_edit
):
    _, add, call = ha_beds
    target = await add()
    old_client = target.client
    receiver, retired = old_client.start_notify.await_args.args
    old_generation = target.connection_generation
    edited = codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1))
    external = codec.record_20_len(5, 1, 2, (1, 0x99, 8, 30, 0x58, 0xA1))
    if local_edit == "replace":
        await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
        notify(target, edited.hex())
    else:
        notify(target, edited.hex())
        await call("jerome_repeat_alarm", operation="delete", slot=1)
    notify(target, external.hex())
    assert [record.raw_7 for record in target.controller._records] == (
        [0x8B] if local_edit == "replace" else []
    )

    client = make_client(codec.TRANSPORTS["w1"])
    client.mtu_size = 23
    client.disconnect = AsyncMock()
    client.read_gatt_char = AsyncMock()
    mock_establish_connection.side_effect = AsyncMock(return_value=client)

    async def reply(_char, frame, **_kwargs):
        if frame == bytes.fromhex("6e08010178"):
            notify(target, "6e09010078")
        elif frame == protocol.QUERY["alarms"]:
            notify(target, external.hex())

    client.write_gatt_char.side_effect = reply
    await call("jerome_repeat_alarm", operation="list")
    assert target.client is client and target.connection_generation != old_generation
    assert not old_client.is_connected
    assert target.controller._records == [RepeatAlarm(1, 0x99, 8, 30, 0x58, 0xA1)]

    retired(receiver, bytearray(edited))
    retired(receiver, bytearray(codec.record_20_len(5, 1, 3, (1, 0x8B, 7, 15, 0x45, 1))))
    await call("set_alarm", enabled=False, slot=1)
    assert writes(target)[-2:] == [
        protocol.QUERY["alarms"].hex(),
        RepeatAlarm(1, 0x99, 8, 30, 0x58, 0xA0).encode().hex(),
    ]


async def test_public_explicit_list_keeps_the_guard_when_the_ble_link_cannot_close(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
    target.client.disconnect.side_effect = None
    with raises_key("jerome_alarm_refresh_needs_link"):
        await call("jerome_repeat_alarm", operation="list")

    assert target.client.is_connected
    notify(target, "6e09010078")
    notify(target, "6e200d050102018a062d58a15a")
    before_disable = len(writes(target))
    with raises_key("jerome_alarm_slot_not_reported"):
        await call("set_alarm", enabled=False, slot=1)
    assert writes(target)[before_disable:] == [protocol.QUERY["alarms"].hex()]


async def test_public_repeat_disable_reads_recovered_notification_session(ha_beds):
    _, add, call = ha_beds
    target = await add()
    controller = target.controller
    client = target.client
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
    receiver, retired = client.start_notify.await_args.args
    disconnect = client.disconnect.side_effect
    client.disconnect.side_effect = None
    try:
        assert not await target.async_disconnect()
    finally:
        client.disconnect.side_effect = disconnect
    assert target.client is client and target.controller is controller
    assert client.start_notify.await_args.args[1] is not retired
    notify(target, "6e09010078")

    edited = codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1))
    retired(receiver, bytearray(edited))
    assert controller._records == []

    async def reply(_char, frame, **_kwargs):
        if frame == protocol.QUERY["alarms"]:
            recorded = codec.record_20_len(5, 1, 2, (1, 0x99, 8, 30, 0x58, 0xA1))
            notify(target, recorded.hex())

    client.write_gatt_char.side_effect = reply
    before_disable = len(writes(target))
    await call("set_alarm", enabled=False, slot=1)
    assert writes(target)[before_disable:] == [
        protocol.QUERY["alarms"].hex(),
        RepeatAlarm(1, 0x99, 8, 30, 0x58, 0xA0).encode().hex(),
    ]


async def test_public_repeat_enable_ignores_delayed_update_for_a_deleted_slot(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await call("set_alarm", enabled=True, time="07:15", slot=1, wake_action="zero_g")
    notify(target, codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1)).hex())
    await call("set_alarm", enabled=False, slot=1)
    await call("jerome_repeat_alarm", operation="delete", slot=1)
    notify(target, codec.record_20_len(5, 1, 3, (1, 0x8C, 7, 15, 0x45, 0)).hex())
    notify(target, codec.record_20_len(5, 1, 2, (1, 0x8B, 7, 15, 0x45, 1)).hex())

    before_enable = len(writes(target))
    with raises_key("jerome_alarm_slot_not_reported"):
        await call("jerome_repeat_alarm", operation="enable", slot=1)
    assert writes(target)[before_enable:] == [protocol.QUERY["alarms"].hex()]


@pytest.mark.parametrize("setting", ["massage", "light"])
async def test_public_timer_write_does_not_publish_after_its_session_end(ha_beds, setting):
    from custom_components.adjustable_bed.select import (
        LIGHT_TIMER_DESCRIPTION,
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedControllerStateSelect,
        AdjustableBedMassageTimerSelect,
    )
    from custom_components.adjustable_bed.state_keys import (
        LIGHT_TIMER_OPTION,
        MASSAGE_TIMER_MINUTES,
    )

    _, add, _ = ha_beds
    target = await add()
    if setting == "massage":
        selector = AdjustableBedMassageTimerSelect(
            target, MASSAGE_TIMER_DESCRIPTION, [10, 20, 30], has_off=False
        )
        option, key = "10 min", MASSAGE_TIMER_MINUTES
    else:
        selector = AdjustableBedControllerStateSelect(
            target, LIGHT_TIMER_DESCRIPTION, ["Always On", "5 min"]
        )
        option, key = "5 min", LIGHT_TIMER_OPTION
    writing = asyncio.Event()
    finish = asyncio.Event()

    async def block(*_args, **_kwargs):
        writing.set()
        await finish.wait()

    target.client.write_gatt_char.side_effect = block
    pending = asyncio.create_task(selector.async_select_option(option))
    await asyncio.wait_for(writing.wait(), 1)
    try:
        target.controller.on_disconnect()
        assert target.controller_state[key] is None
    finally:
        finish.set()
        await pending
    assert target.controller_state[key] is None


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("operation", ["enable", "delete"])
async def test_repeat_mutation_first_checks_all_receivers(hass, ha_beds, paired, operation):
    targets, add, call = ha_beds
    left, right = await add(), await add()
    pair = await _ha_pair(hass, targets, left, right) if paired else None
    notify(left, "6e200d0501020100062d58a1d0")
    with pytest.raises(ServiceValidationError, match="did not report that alarm slot"):
        await call("jerome_repeat_alarm", operation=operation, slot=1)
    assert writes(left) == []
    assert writes(right) == ["6e2008050100009c"]

    notify(right, "6e200d0501020100062d58a1d0")
    await call("jerome_repeat_alarm", operation=operation, slot=1)
    expected = "6e2008050201019f" if operation == "delete" else "6e200d0501010100062d58a1cf"
    assert writes(left) == [expected]
    assert writes(right) == ["6e2008050100009c", expected]
    if pair is not None:
        await pair.async_shutdown()


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("enable", "6e200d0501010100062d58a1cf"), ("delete", "6e2008050201019f")],
)
async def test_public_repeat_mutation_keeps_selected_sequential_link(
    hass, ha_beds, operation, expected
):
    targets, add, call = ha_beds
    left, right = await add(), await add()
    left_client, right_client = left.client, right.client
    pair = await _ha_pair(hass, targets, left, right, mode="sequential")

    async def write(_char, frame, **_kwargs):
        assert left_client.is_connected and not right_client.is_connected
        if frame == protocol.QUERY["alarms"]:
            notify(left, "6e200d0501020100062d58a1d0")

    left_client.write_gatt_char.side_effect = write
    try:
        with raises_key("jerome_alarm_needs_two_links", ServiceValidationError):
            await call("jerome_repeat_alarm", operation=operation, slot=1)
        assert not written_frames(left_client) and not written_frames(right_client)

        await call("jerome_repeat_alarm", operation=operation, slot=1, side="left")
        assert written_frames(left_client) == [protocol.QUERY["alarms"].hex(), expected]
        assert not written_frames(right_client)
        assert not left_client.is_connected
    finally:
        await pair.async_shutdown()


async def test_public_repeat_mutation_validates_mixed_receivers_before_writing(hass, ha_beds):
    targets, add, call = ha_beds
    left, right, standalone = await add(), await add(), await add()
    left_client = left.client
    pair = await _ha_pair(hass, targets, left, right, mode="sequential", side="left")
    targets.append((standalone, "both"))
    record = "6e200d0501020100062d58a1d0"
    notify(left, record)

    try:
        with raises_key("jerome_alarm_slot_not_reported", ServiceValidationError):
            await call("jerome_repeat_alarm", operation="enable", slot=1)
        assert not written_frames(left_client)
        assert not written_frames(right.client)
        assert writes(standalone) == [protocol.QUERY["alarms"].hex()]

        notify(standalone, record)
        await call("jerome_repeat_alarm", operation="enable", slot=1)
        assert written_frames(left_client) == ["6e200d0501010100062d58a1cf"]
        assert writes(standalone) == [protocol.QUERY["alarms"].hex(), "6e200d0501010100062d58a1cf"]
    finally:
        await pair.async_shutdown()


async def test_public_repeat_mutation_reports_stop_after_partial_write(ha_beds):
    _, add, call = ha_beds
    first, second = await add(), await add()
    for target in (first, second):
        notify(target, "6e200d0501020100062d58a1d0")
    change = "6e2008050201019f"

    async def write(_char, frame, **_kwargs):
        if frame.hex() == change:
            await second.async_stop_command()

    first.client.write_gatt_char.side_effect = write
    with raises_key("action_stopped"):
        await call("jerome_repeat_alarm", operation="delete", slot=1)
    assert writes(first) == [change]
    assert change not in writes(second)


async def test_repeat_alarm_service_lists_from_connected_controller(ha_beds):
    _, add, call = ha_beds
    target = await add()
    await call("jerome_repeat_alarm", operation="list")
    assert writes(target) == ["6e2008050100009c"]


async def test_public_delete_cannot_clear_a_replacement_sessions_records(ha_beds):
    _, add, call = ha_beds
    target = await add()
    record = "6e200d0501020100062d58a1d0"
    notify(target, record)
    original = target.controller
    writing = asyncio.Event()
    finish = asyncio.Event()

    async def block_delete(_characteristic, frame, **_kwargs):
        if frame == bytes.fromhex("6e2008050201019f"):
            writing.set()
            await finish.wait()

    target.client.write_gatt_char.side_effect = block_delete
    pending = asyncio.create_task(call("jerome_repeat_alarm", operation="delete", slot=1))
    await asyncio.wait_for(writing.wait(), 1)
    try:
        original.on_disconnect()
        replacement = bed.JeromeAdjustableBaseController(target, product="JERN")
        target._controller = replacement
        await replacement.start_notify()
        notify(target, "6e09010078")
        notify(target, record)
        assert target.controller_state[bed.RECORDS][0]["slot"] == 1
    finally:
        finish.set()
        await pending
    assert target.controller_state[bed.RECORDS][0]["slot"] == 1
