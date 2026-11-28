"""Session, preflight and release races through the AI Bed runtime."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.ai_bed import controller as bed
from custom_components.adjustable_bed.beds.ai_bed.requests import Request
from custom_components.adjustable_bed.codec import ai_bed as codec
from custom_components.adjustable_bed.profiles.ai_bed import PROFILES
from tests.test_controller_contract import _FactoryCoordinator


@pytest.fixture(autouse=True)
async def clock(monkeypatch):
    now = [0.0]

    async def fast_pause(seconds, *events):
        if any(event.is_set() for event in events):
            return True
        if seconds >= 10 and len(events) == 1:
            await events[0].wait()
            return True
        if len(events) == 3 and seconds == 2:  # a query waits for a test-supplied fresh reply
            await events[-1].wait()
            return True
        now[0] += seconds
        await asyncio.sleep(0)
        return any(event.is_set() for event in events)

    monkeypatch.setattr(bed, "pause", fast_pause)
    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    yield now
    for controller in CREATED:
        await controller.stop_keepalive()
    CREATED.clear()


async def until(predicate):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Expected operation did not become ready")


CREATED = []


def make(route="305", properties=("write", "write-without-response")):
    c = _FactoryCoordinator()
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.cancel_command = asyncio.Event()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    c.client.disconnect = AsyncMock()
    c.hass.async_create_background_task = lambda coro, name: asyncio.create_task(coro)
    profile = PROFILES[route]
    tx = SimpleNamespace(uuid=profile.write, properties=properties, handle=1)
    rx = SimpleNamespace(uuid=profile.notify, properties=("notify",), handle=2)
    svc = SimpleNamespace(get_characteristic=lambda uuid: tx if uuid == profile.write else rx)
    c.client.services.get_service.return_value = svc
    controller = bed.AiBedController(c, route, "MpeV3B-5-M2")
    CREATED.append(controller)
    return c, controller, tx


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


async def test_privacy_pin_releases_idle_connection_without_recovery(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:29",
            "name": "AI Bed",
            "bed_type": "ai_bed",
            "protocol_variant": "305",
            "ble_device_name": "MpeV3B-5-M2",
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    fake, ctrl, _ = make()
    client = fake.client
    ctrl._coordinator = target
    target._client, target._controller = client, ctrl
    target._disconnect_after_command = False
    target._link_ready = True
    target._idle_deadline = hass.loop.time() + 30

    async def disconnect():
        client.is_connected = False
        target._on_disconnect(client)

    client.disconnect.side_effect = disconnect
    try:
        await ctrl.start_notify()
        assert target._auto_reconnect_enabled()
        request = Request(action="privacy_pin", pin="123")
        stamp = await ctrl.prepare_request(request)
        async with target._command_lock:
            await ctrl.execute_request(request, stamp)
        client.disconnect.assert_awaited_once()
        assert target._reconnect_timer is None
        assert target._last_disconnect_reason == "intentional"
        assert target.client is None
    finally:
        await target.async_shutdown()


@pytest.mark.parametrize("route", ("305", "limos", "hj001", "qrrm"))
def test_held_card_actions_have_a_standard_stop_target(route):
    from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
    from custom_components.adjustable_bed.card import CARD_STOP

    _, ctrl, _ = make(route)
    stop = next(description for description in BUTTON_DESCRIPTIONS if description.key == "stop")
    assert any(spec.hold is not None for spec in ctrl.controller_button_specs)
    assert _should_add_button(stop, ctrl, False)
    assert stop.card == CARD_STOP


@pytest.mark.parametrize("route", ("305", "limos", "hj001", "qrrm"))
async def test_public_stop_while_disconnected_does_not_open_a_connection(hass, route):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:28",
            "name": "AI Bed",
            "bed_type": "ai_bed",
            "protocol_variant": route,
            "ble_device_name": "MpeV3B-5-M2",
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    await target.async_prime_offline_controller()
    target.async_ensure_connected = AsyncMock(return_value=False)
    try:
        await target.async_stop_command()
        target.async_ensure_connected.assert_not_awaited()
        assert target.client is None
    finally:
        await target.async_shutdown()


@pytest.mark.parametrize("route", ("limos", "qrrm", "hj001", "305"))
async def test_route_holds_first_tick_and_exact_release(route):
    c, ctrl, _ = make(route)
    await ctrl.start_notify()
    key = next(k for k, a in ctrl.profile.actions.items() if a.motion)
    task = asyncio.create_task(ctrl.hold_control(key, ctrl.profile.refresh_ms + 20))
    await asyncio.sleep(0)
    assert not written(c)  # first scheduled tick, no eager starter
    await task
    expected = ctrl.profile.encode(ctrl.profile.actions[key]).hex()
    assert written(c) == [expected] + (["aa080800000000aa"] * 2 if route == "305" else [])
    await ctrl.stop_keepalive()


@pytest.mark.parametrize("route", ("limos", "qrrm", "hj001"))
async def test_tap_sends_once_no_invented_stop(route):
    c, ctrl, _ = make(route)
    await ctrl.start_notify()
    key = next(k for k, a in ctrl.profile.actions.items() if a.motion)
    await ctrl.action(key)
    assert written(c) == [ctrl.profile.encode(ctrl.profile.actions[key]).hex()]
    await ctrl.stop_keepalive()


async def test_cancelled_hold_never_releases_on_replacement_client():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    original = c.client
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    await asyncio.sleep(0)
    ctrl.on_disconnect()
    c.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not original.write_gatt_char.called
    assert not c.client.write_gatt_char.called
    await ctrl.stop_keepalive()


async def test_alarm_stamp_checked_under_actual_writer_lock_and_invalidated_on_failed_attempt():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    alarm = AlarmRequest(
        reference_time=datetime(2026, 11, 27, tzinfo=UTC),
        enabled=True,
        hour=6,
        minute=30,
        weekdays=(0, 6),
    )
    await ctrl.check_alarm(alarm)
    await ctrl.ble_lock.acquire()
    task = asyncio.create_task(ctrl.configure_alarm(alarm))
    await asyncio.sleep(0)
    ctrl._live().revision += 1
    ctrl.ble_lock.release()
    with pytest.raises(ValueError, match="after preflight"):
        await task
    assert not written(c)
    await ctrl.check_alarm(alarm)
    c.client.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(BleakError):
        await ctrl.configure_alarm(alarm)
    assert ctrl._alarm_check is None
    with pytest.raises(ValueError, match="after preflight"):
        await ctrl.configure_alarm(alarm)
    await ctrl.stop_keepalive()


async def test_alarm_shared_writer_uses_checked_request():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    alarm = AlarmRequest(
        reference_time=datetime(2026, 11, 27, tzinfo=UTC),
        enabled=True,
        hour=6,
        minute=30,
        weekdays=(0,),
    )
    await ctrl.check_alarm(alarm)
    await ctrl.configure_alarm(alarm)
    assert written(c) == ["aa0820061e01148f"]
    await ctrl.stop_keepalive()


async def test_disable_inflation_requires_fresh_reply_and_preserves_time():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    link = ctrl._live()
    link.schedules = {"inflation_hour": 1, "inflation_minute": 2}
    req = Request("inflation", enabled=False)
    task = asyncio.create_task(ctrl.prepare_request(req))
    await until(lambda: bool(written(c)))
    assert link.schedules is None and not task.done()
    data = bytearray.fromhex("bb0b2302061e7f000000")
    data.append(__import__("functools").reduce(__import__("operator").xor, data, 0))
    ctrl._receive(link, bytes(data))
    stamp = await task
    await ctrl.execute_request(req, stamp)
    assert written(c)[-1] == codec.schedule(0x1E, 6, 30, 0).hex()
    assert link.schedules is None
    await ctrl.stop_keepalive()


async def test_property_selected_ordinary_and_reliable_writes():
    for properties, ordinary, reliable in (
        (["write"], True, True),
        (["write-without-response"], False, False),
        (["write", "write-without-response"], False, True),
    ):
        c, ctrl, _ = make(properties=properties)
        await ctrl.start_notify()
        link = ctrl._live()
        await ctrl._send(link, codec.frame(0x22))
        assert c.client.write_gatt_char.call_args.kwargs["response"] is ordinary
        await ctrl._send(link, codec.frame(0x22), reliable=True)
        assert c.client.write_gatt_char.call_args.kwargs["response"] is reliable
        await ctrl.stop_keepalive()


async def test_preview_cancel_sends_off_and_rollback_only_to_original_link():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    link = ctrl._live()
    link.strengths[1] = (3, 4)
    request = Request("vibration_preview", mode=1, head=5, foot=6, seconds=5)
    stamp = await ctrl.prepare_request(request)
    task = asyncio.create_task(ctrl.execute_request(request, stamp))
    await until(lambda: "aa06160101ba" in written(c))
    c.cancel_command.set()
    await task
    assert written(c)[-2:] == ["aa06160202ba", codec.vibration_both(1, 3, 4, True).hex()]
    assert 1 not in link.strengths
    await ctrl.stop_keepalive()


@pytest.mark.parametrize("replace_link", (False, True))
async def test_failed_preview_off_does_not_suppress_current_link_rollback(replace_link):
    c, ctrl, _ = make()
    await ctrl.start_notify()
    link = ctrl._live()
    original_client = c.client
    link.strengths[1] = (3, 4)
    request = Request("vibration_preview", mode=1, head=5, foot=6, seconds=3)
    stamp = await ctrl.prepare_request(request)
    off = codec.frame(0x16, (2, 2))
    restore = codec.vibration_both(1, 3, 4, True)

    async def write(_characteristic, packet, **_kwargs):
        if packet == off:
            c.cancel_command.set()
            if replace_link:
                ctrl.on_disconnect()
                c.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
            raise BleakError("preview off failed")

    original_client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError, match="preview off failed"):
        await ctrl.execute_request(request, stamp)
    packets = [call.args[1] for call in original_client.write_gatt_char.await_args_list]
    if replace_link:
        assert packets[-1] == off
        assert restore not in packets
        c.client.write_gatt_char.assert_not_awaited()
    else:
        assert packets[-2:] == [off, restore]


async def test_raw_qrrm_never_enters_generic_mpe_parser():
    c, ctrl, _ = make("qrrm")
    await ctrl.start_notify()
    c.handle_controller_state_updates.reset_mock()
    ctrl._receive(ctrl._live(), bytes.fromhex("bb06a403010219"))
    assert not c.handle_controller_state_updates.called
    assert set(ctrl.profile.actions) == {
        "recall_sleep",
        "both_rise",
        "both_down",
        "foot_rise",
        "foot_down",
        "head_rise",
        "head_down",
    }
    await ctrl.stop_keepalive()


def test_findable_explicit_routes_preserve_confident_receivers_and_saved_profiles():
    from custom_components.adjustable_bed.detection import (
        detect_bed_type_detailed,
        resolve_bed_type_choice,
    )
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
    from tests.test_detection import _make_service_info

    for route in ("305", "limos", "hj001", "qrrm"):
        assert resolve_bed_type_choice(f"ai_bed:{route}") == ("ai_bed", route)
        assert is_valid_variant_for_bed_type("ai_bed", route)
    info = _make_service_info(name="QRRM", service_uuids=[PROFILES["hj001"].service])
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type != "ai_bed"  # existing receiver keeps its identification
    assert "ai_bed" in (detected.ambiguous_types or ())
    assert recommend_profile({"bed_type": "ai_bed", "protocol_variant": "qrrm"}, info, {}) is None
    accessory = _make_service_info(name="SUTA-DRAWQRRM", service_uuids=[])
    detected = detect_bed_type_detailed(accessory)
    assert detected.bed_type != "ai_bed" and "ai_bed" not in (detected.ambiguous_types or ())


async def test_native_number_callbacks_emit_frames():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    for spec in ctrl.controller_number_specs:
        await spec.set_fn(ctrl, spec.native_max_value)
    assert written(c) == [
        "aa051204b9",
        codec.frame(0x10, (100, 0)).hex(),
        codec.frame(0x10, (0, 100)).hex(),
    ]
    assert not ctrl.supports_preset_flat
    assert not any(action.code in (0x2B, 0x2C, 0x90) for action in ctrl.profile.actions.values())
    await ctrl.stop_keepalive()


async def test_shared_alarm_service_passes_preflight_to_actual_writer(
    hass, mock_coordinator_connected, mock_bleak_client
):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const, services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="AI Bed",
        data={
            "address": "AA:BB:CC:DD:EE:28",
            "name": "AI Bed",
            "bed_type": "ai_bed",
            "protocol_variant": "305",
            "ble_device_name": "MpeV3B-5-M2",
            "disable_angle_sensing": True,
            "connection_mode": const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    profile = PROFILES["305"]
    char = SimpleNamespace(
        uuid=profile.write, properties=["write", "notify"], handle=28, descriptors=[]
    )
    svc = SimpleNamespace(
        uuid=profile.service, characteristics=[char], get_characteristic=lambda _: char
    )
    mock_bleak_client.services.get_service.side_effect = lambda uuid: (
        svc if uuid == profile.service else None
    )
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    await services.async_register_services(hass)
    with patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])):
        try:
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {"device_id": "bed", "enabled": True, "time": "06:30:00", "weekdays": ["monday"]},
                blocking=True,
            )
            packets = [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list]
            assert codec.schedule(0x20, 6, 30, 1) in packets
            await hass.services.async_call(
                const.DOMAIN,
                "ai_bed",
                {
                    "device_id": "bed",
                    "action": "inflation",
                    "enabled": True,
                    "hour": 7,
                    "minute": 45,
                    "weekdays": [1],
                },
                blocking=True,
            )
            packets = [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list]
            assert codec.schedule(0x1E, 7, 45, 2) in packets
        finally:
            await target.async_shutdown()


async def test_cancel_before_preview_write_does_not_emit_cleanup():
    c, ctrl, _ = make()
    await ctrl.start_notify()
    link = ctrl._live()
    link.strengths[0] = (3, 4)
    request = Request("vibration_preview")
    stamp = await ctrl.prepare_request(request)
    c.cancel_command.set()
    await ctrl.execute_request(request, stamp)
    assert not written(c)
    await ctrl.stop_keepalive()


@pytest.mark.parametrize(("route", "action"), [("limos", "deep_program"), ("305", "qc_stm32")])
async def test_multistep_action_keeps_original_session(route, action):
    c, ctrl, _ = make(route)
    ctrl.name = "MpeV3B-5E"
    await ctrl.start_notify()
    first_link = ctrl._live()
    replacement = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    async def replace_link(*args, **kwargs):
        ctrl.on_disconnect()
        c.client = replacement
        ctrl._link = bed.Link(replacement, first_link.write, first_link.notify)

    first_link.client.write_gatt_char.side_effect = replace_link
    await ctrl.action(action)
    assert first_link.client.write_gatt_char.await_count == 1
    assert not replacement.write_gatt_char.called
    await ctrl.stop_keepalive()


async def test_periodic_hold_absorbs_gatt_write_latency(clock):
    c, ctrl, _ = make("qrrm")
    await ctrl.start_notify()
    stamps = []

    async def latency(*args, **kwargs):
        stamps.append(clock[0])
        clock[0] += 0.007

    c.client.write_gatt_char.side_effect = latency
    await ctrl.hold_control("head_rise", 100)
    assert stamps == pytest.approx([0.03, 0.06, 0.09])
    await ctrl.stop_keepalive()


@pytest.mark.parametrize("route", ("305", "limos", "hj001", "qrrm"))
def test_primary_native_control_shapes_and_diagnostics(route):
    from custom_components.adjustable_bed.light import AdjustableBedOnOffLight, _light_entities_for

    c, ctrl, _ = make(route)
    c.capability_controller = ctrl
    c.entity_unique_id = lambda key: key
    c.device_info = {}
    c.entity_side = None
    c.bed_type = "ai_bed"
    assert ctrl.controller_state_sensor_specs == ()
    c.controller_state[bed.RAW] = "diagnostic payload"
    assert ctrl.protocol_diagnostics[str(bed.RAW)] == "diagnostic payload"
    if route != "305":
        assert ctrl.controller_switch_specs == ctrl.controller_select_specs == ()
        assert not ctrl.supports_massage_timer
        assert _light_entities_for(c.hass, c) == []
        return
    assert len(_light_entities_for(c.hass, c)) == 1
    assert isinstance(_light_entities_for(c.hass, c)[0], AdjustableBedOnOffLight)
    assert len(ctrl.controller_switch_specs) == 3
    assert len(ctrl.controller_select_specs) == 1
    assert ctrl.massage_timer_options == [10, 20, 30]
    assert not ctrl.massage_timer_can_turn_off
    assert all(
        not spec.key.startswith(("ai_bed_lamp_", "ai_bed_massage_"))
        for spec in ctrl.controller_button_specs
    )


async def test_native_massage_controls_publish_consistent_assumed_state():
    c, ctrl, _ = make()
    c.handle_controller_state_updates = lambda *updates: c.controller_state.update(
        (update.key, update.value) for update in updates
    )
    await ctrl.start_notify()
    switches = {spec.key: spec for spec in ctrl.controller_switch_specs}
    await switches["ai_bed_massage_both"].set_fn(ctrl, True)
    assert all(
        c.controller_state[key] is True
        for key in (bed.MASSAGE_HEAD, bed.MASSAGE_FOOT, bed.MASSAGE_BOTH)
    )
    await switches["ai_bed_massage_head"].set_fn(ctrl, False)
    assert c.controller_state[bed.MASSAGE_HEAD] is False
    assert c.controller_state[bed.MASSAGE_FOOT] is True
    assert c.controller_state[bed.MASSAGE_BOTH] is False
    mode = ctrl.controller_select_specs[0]
    await mode.select_fn(ctrl, "3")
    assert c.controller_state[bed.MASSAGE_MODE] == "3"
    await ctrl.set_massage_timer(20)
    assert c.controller_state[bed.MASSAGE_TIMER_MINUTES] == 20
    await ctrl.lights_on()
    await ctrl.lights_off()
    assert written(c) == [
        codec.frame(*bed.FIXED[key]).hex()
        for key in (
            "massage_both_on",
            "massage_head_off",
            "massage_mode_3",
            "massage_timer_20",
            "lamp_on",
            "lamp_off",
        )
    ]
    ctrl.on_disconnect()
    assert all(
        c.controller_state[key] is None
        for key in (
            bed.MASSAGE_HEAD,
            bed.MASSAGE_FOOT,
            bed.MASSAGE_BOTH,
            bed.MASSAGE_MODE,
            bed.MASSAGE_TIMER_MINUTES,
        )
    )


@pytest.mark.parametrize(
    "case", ("retired", "cancelled", "partial", "heartbeat", "cleanup", "retry")
)
async def test_held_back_command_frames_have_honest_delivery(case):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
    )

    c, ctrl, _ = make()
    await ctrl.start_notify()
    link = ctrl._live()
    observed = []
    scheduler = DeviceCommandScheduler("ai-bed-delivery")

    async def operation(context):
        c.cancel_command = context.cancel_event
        if case == "partial":
            await ctrl._send(link, codec.frame(0x22), c.cancel_command)
        if case in ("retired", "partial"):
            ctrl.on_disconnect()
        if case == "cancelled":
            c.cancel_command.set()
        if case == "retry":
            c.client.write_gatt_char.side_effect = BleakError("not delivered")
        event = (
            None
            if case == "heartbeat"
            else asyncio.Event()
            if case == "cleanup"
            else c.cancel_command
        )
        await ctrl._send(
            link, codec.frame(0x22), event, heartbeat=case == "heartbeat", reliable=case == "retry"
        )
        observed.append((context.frames_written, context.frames_skipped))

    await scheduler.execute(CommandIntent(operation))
    assert observed == [
        (1, 1) if case == "partial" else (0, 0) if case in ("heartbeat", "cleanup") else (0, 1)
    ]


@pytest.mark.parametrize(
    "action",
    (
        "inflation",
        "inflation_off",
        "vibration_apply",
        "vibration_preview",
        "settings_query",
        "privacy_pin",
    ),
)
async def test_registered_service_keeps_prepare_and_write_in_each_sequential_session(
    hass, monkeypatch, action
):
    from functools import reduce
    from operator import xor

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const, services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    children = {}
    packets = {"left": [], "right": []}
    controllers = []
    for index, side in enumerate(("left", "right")):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": f"AA:BB:CC:DD:EE:{index + 40:02X}",
                "name": side,
                "bed_type": "ai_bed",
                "protocol_variant": "305",
                "ble_device_name": "MpeV3B-5-M2",
                "disable_angle_sensing": True,
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        _, ctrl, _ = make()
        ctrl._coordinator = child
        client = MagicMock(
            is_connected=False,
            start_notify=AsyncMock(),
            stop_notify=AsyncMock(),
            disconnect=AsyncMock(),
        )
        profile = ctrl.profile
        char = SimpleNamespace(uuid=profile.write, properties=["write", "notify"], handle=index + 1)
        client.services.get_service.return_value = SimpleNamespace(
            get_characteristic=lambda _, _char=char: _char
        )
        child._client, child._controller = client, ctrl
        child._async_refresh_controller_auth = AsyncMock()

        async def connect(*_args, _ctrl=ctrl, _client=client, **_kwargs):
            _client.is_connected = True
            await _ctrl.start_notify()
            return True

        async def disconnect(*_args, _ctrl=ctrl, _client=client, **_kwargs):
            await _ctrl.stop_notify()
            _client.is_connected = False
            return True

        async def write(_char, packet, *, response, _ctrl=ctrl, _side=side):
            packets[_side].append(packet)
            if packet[2] == 0x22:
                body = bytes.fromhex("bb0b2302061e7f000000")
                _ctrl._receive(_ctrl._live(), body + bytes([reduce(xor, body, 0)]))
            elif packet[2] == 0x41:
                body = bytes.fromhex("bb0ea200000000030405060708")
                _ctrl._receive(_ctrl._live(), body + bytes([reduce(xor, body, 0)]))

        client.write_gatt_char = AsyncMock(side_effect=write)
        child.async_connect = child.async_ensure_connected = connect
        child.async_disconnect = disconnect
        children[side] = child
        controllers.append(ctrl)
    pair_entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "ai-bed-sequential"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, pair_entry, children, connection_mode="sequential")
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, "both")], []))
    await services.async_register_services(hass)
    request = {
        "device_id": "bed",
        "action": "inflation" if action == "inflation_off" else action,
        "enabled": action != "inflation_off",
        "weekdays": [0],
        "pin": "123",
    }
    try:
        await hass.services.async_call(const.DOMAIN, "ai_bed", request, blocking=True)
        expected = {
            "inflation": 0x1E,
            "inflation_off": 0x1E,
            "vibration_apply": 0xA1,
            "vibration_preview": 0xA1,
            "settings_query": 0x41,
            "privacy_pin": 0x9D,
        }[action]
        assert all(any(frame[2] == expected for frame in frames) for frames in packets.values())
        assert all(ctrl._link is None for ctrl in controllers)
    finally:
        for child in children.values():
            await child.async_shutdown()


@pytest.mark.parametrize(
    "case", ("complete", "cancel", "cleanup_failure", "replacement", "cancel_before")
)
async def test_preview_does_not_leave_native_massage_state_stale(case):
    c, ctrl, _ = make()
    c.handle_controller_state_updates = lambda *updates: c.controller_state.update(
        (update.key, update.value) for update in updates
    )
    await ctrl.start_notify()
    await ctrl.set_massage("both", True)
    await ctrl.controller_select_specs[0].select_fn(ctrl, "3")
    keys = (bed.MASSAGE_HEAD, bed.MASSAGE_FOOT, bed.MASSAGE_BOTH, bed.MASSAGE_MODE)
    previous = tuple(c.controller_state[key] for key in keys)
    assert previous == (True, True, True, "3")
    ctrl._live().strengths[1] = (3, 4)
    request = Request("vibration_preview", mode=1, head=5, foot=6, seconds=3)
    stamp = await ctrl.prepare_request(request)

    async def write(_char, packet, **_kwargs):
        if packet == codec.frame(0x16, (1, 1)):
            if case == "cancel":
                c.cancel_command.set()
            elif case == "replacement":
                ctrl.on_disconnect()
                c.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
                # State belonging to a replacement session must survive old cleanup.
                c.controller_state.update(zip(keys, previous, strict=True))
        if packet == codec.frame(0x16, (2, 2)) and case == "cleanup_failure":
            raise BleakError("cleanup outcome is unknown")

    c.client.write_gatt_char.side_effect = write
    if case == "cancel_before":
        c.cancel_command.set()
    if case == "cleanup_failure":
        with pytest.raises(BleakError, match="unknown"):
            await ctrl.execute_request(request, stamp)
    else:
        await ctrl.execute_request(request, stamp)
    assert tuple(c.controller_state[key] for key in keys) == (
        previous if case in ("replacement", "cancel_before") else (None, None, None, None)
    )
