"""Sleeptime frozen wire vectors and its setup and notification boundaries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_setup_entry, config_flow
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.sleeptime.controller import SleeptimeController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import (
    CommandIntent,
    Delivery,
    DeviceCommandScheduler,
    delivered,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPTIME,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_MODE_SINGLE_ADDRESS,
    SIDE_LEFT,
    SIDE_RIGHT,
    TIMED_MOVE_MOTOR_OPTIONS,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.profiles import sleeptime as app
from custom_components.adjustable_bed.setup_operation import OperationOutcome
from tests.form_helpers import NEW_BED_ROUTES, form_fields, marker_default, start_new_bed
from tests.hold_lease_wire import Write, leased_hold, virtual_clock
from tests.test_config_flow import _patch_gate
from tests.test_controller_contract import _create_controller_for_bed_type, _FactoryCoordinator
from tests.test_detection import _make_service_info

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "sleeptime_vectors.json").read_text())
FROZEN_BYTES = {vector["id"]: bytes.fromhex(vector["expected_bytes"]) for vector in VECTORS}
MASSAGE = FROZEN_BYTES["massage-state"]
ALARM = FROZEN_BYTES["alarm-state"]
ED = FROZEN_BYTES["alarm-ack"]
FRAGMENT = FROZEN_BYTES["fragment-unmatched"]

ADDRESS = "11:22:33:44:55:66"
ENTRY_DATA = {
    CONF_ADDRESS: ADDRESS,
    CONF_NAME: "Sleeptime",
    CONF_BED_TYPE: BED_TYPE_SLEEPTIME,
    CONF_PROTOCOL_VARIANT: "404",
    CONF_DISABLE_ANGLE_SENSING: True,
}

# The labels below map the frozen app rows to the integration's public control names.
POSITIONS = (
    "back_up",
    "back_down",
    "legs_up",
    "legs_down",
    "neck_up",
    "neck_down",
    "lumbar_up",
    "lumbar_down",
    "head_tilt_up",
    "head_tilt_down",
    "foot_tilt_up",
    "foot_tilt_down",
    "bed_height_up",
    "bed_height_down",
    "tv",
    "zero_g",
    "reading",
    "anti_snore",
    "flat",
    "memory_1",
    "memory_2",
)
FRAMES = {
    **{
        vector["id"]: codec.frame40(app.PROFILE.keys[key], 1)
        for vector, key in zip(VECTORS[:21], POSITIONS, strict=True)
    },
    "light": app.LIGHT,
    "release-stop": app.STOP,
    "memory-reset": app.RESET,
    **{
        vector["id"]: codec.frame40(app.MASSAGE[key][0])
        for vector, key in zip(VECTORS[24:32], app.MASSAGE, strict=True)
    },
    "massage-query": app.MASSAGE_QUERY,
    "alarm-query": app.ALARM_QUERY,
}


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_frozen_sleeptime_vectors(vector):
    key, inputs = vector["id"], vector["inputs"]
    expected = bytes.fromhex(vector["expected_bytes"])
    if key in FRAMES:
        assert FRAMES[key] == expected
        return
    builder = inputs["builder"]
    if builder == "clock":
        assert app.clock(datetime.fromisoformat(inputs["local_date"])) == expected
    elif builder in {"alarm", "next_alarm"}:
        days = (
            app.once_mask(
                datetime.fromisoformat(inputs["current"]), inputs["hour"], inputs["minute"]
            )
            if builder == "next_alarm"
            else inputs["day_mask"]
        )
        assert (
            app.alarm(
                inputs["mode"], days, inputs["hour"], inputs["minute"], bool(inputs["enabled"])
            )
            == expected
        )
    else:
        parser = codec.SingleRecordParser()
        result = parser.feed(expected)
        if builder == "massage_state":
            assert isinstance(result, codec.MassageReport)
            decoded = inputs["expected_decoded"]
            assert (result.mode, result.head, result.foot) == (
                decoded["mode"],
                decoded["head"],
                decoded["foot"],
            )
        elif builder == "alarm_state":
            assert isinstance(result, codec.ShortAlarmReport)
            decoded = inputs["expected_decoded"]
            assert (result.week, result.mode, result.hour, result.minute, result.enabled) == tuple(
                decoded[name] for name in ("day", "mode", "hour", "minute", "open")
            )
        else:
            assert builder == "fragment"
            assert result is None and parser.pending
            assert parser.feed(bytes.fromhex(inputs["next"])) is None
            assert not parser.pending


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_new_install_asks_and_saves_layout(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="advertisement")
    flow._discovery_info.device.name = "sMaRtBeD404-123"
    flow._async_transport_note = AsyncMock(return_value="")
    form = await start_new_bed(flow, route, BED_TYPE_SLEEPTIME)
    assert form["step_id"] == "profile_questions"
    field = next(
        mark for mark in form_fields(form["data_schema"]) if mark.schema == CONF_PROTOCOL_VARIANT
    )
    assert marker_default(field) == (vol.UNDEFINED if route == "typed" else "404")
    result = await flow.async_step_profile_questions({CONF_PROTOCOL_VARIANT: "404"})
    assert result["step_id"] == "finish_settings"
    assert flow._manual_data[CONF_PROTOCOL_VARIANT] == "404"


@pytest.mark.parametrize(
    ("selector", "extra"),
    [
        ("205", ()),
        ("402", ("neck", "lumbar")),
        ("404", ("tilt", "foot_tilt", "bed_height")),
        ("405", ("neck", "lumbar")),
    ],
)
async def test_layouts_and_detection(selector, extra):
    info = _make_service_info(name="advertisement")
    info.device.name = f"sMaRtBeD{selector}-123"
    result = detect_bed_type_detailed(info)
    assert BED_TYPE_SLEEPTIME in {result.bed_type, *(result.ambiguous_types or ())}
    assert app.select(f"X{info.device.name}") is None
    controller = await _create_controller_for_bed_type(BED_TYPE_SLEEPTIME, selector)
    assert isinstance(controller, SleeptimeController)
    assert tuple(spec.key for spec in controller.motor_control_specs) == ("back", "legs", *extra)
    assert all(spec.key in TIMED_MOVE_MOTOR_OPTIONS for spec in controller.motor_control_specs)
    assert controller.execution.hold_for("back_up") == "stream"
    assert controller.execution.hold_for("memory_1") is None
    assert not controller.execution.concurrent
    assert not controller.supports_single_address_pairing
    assert controller.supports_preset_flat is (selector != "404")
    assert "flat" in controller.alarm_capability.wake_actions
    assert ("zero_g" in controller.alarm_capability.wake_actions) is (selector != "404")


def _client(
    *,
    indicate=False,
    write_property="write-without-response",
    service_uuid=NORDIC_UART_SERVICE_UUID,
):
    write = SimpleNamespace(uuid=NORDIC_UART_WRITE_CHAR_UUID, handle=1, properties=[write_property])
    notify = SimpleNamespace(
        uuid=NORDIC_UART_READ_CHAR_UUID, handle=2, properties=["indicate" if indicate else "notify"]
    )
    service = SimpleNamespace(
        uuid=service_uuid,
        get_characteristic={write.uuid: write, notify.uuid: notify}.get,
        characteristics=[write, notify],
    )
    services = MagicMock()
    services.__iter__.return_value = [service]
    services.get_service.side_effect = {service_uuid: service}.get
    return SimpleNamespace(
        is_connected=True,
        services=services,
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        read_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )


async def _connected(*, indicate=False):
    coordinator = _FactoryCoordinator()
    coordinator.record_command_trace = MagicMock()
    coordinator.handle_controller_state_updates = MagicMock()
    client = _client(indicate=indicate)
    coordinator.client = client
    controller = SleeptimeController(coordinator, "404")
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return controller, coordinator, client


@pytest.mark.parametrize("endpoint", ["unrelated", "response_only", "indicate", "empty", "offline"])
async def test_setup_verifies_exact_uart_without_blocking_offline_setup(
    hass, monkeypatch, endpoint
):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    monkeypatch.setattr(flow, "_verification_possible", lambda: True)
    client = _client(
        indicate=True,
        write_property="write" if endpoint == "response_only" else "write-without-response",
        service_uuid="180a" if endpoint == "unrelated" else NORDIC_UART_SERVICE_UUID,
    )
    if endpoint == "empty":
        client.services = None
    connect = AsyncMock(
        return_value=client, side_effect=BleakError("offline") if endpoint == "offline" else None
    )
    monkeypatch.setattr("bleak_retry_connector.establish_connection", connect)
    monkeypatch.setattr(
        config_flow, "discover_services", AsyncMock(return_value=endpoint != "empty")
    )
    read_info = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", read_info)

    with _patch_gate("hci0", -55):
        progress = await flow._finish_with_verify(dict(ENTRY_DATA), "Sleeptime")
        assert progress["step_id"] == "setup_progress"
        task = progress["progress_task"]
        assert task is not None
        await task
        assert (await flow.async_step_setup_progress())["step_id"] == "verify_connection"

    verify = await flow.async_step_verify_connection()
    assert verify["step_id"] == "verify_connection"
    result = await flow.async_step_verify_connection({})
    incompatible = endpoint in {"unrelated", "response_only"}
    assert flow.operation.result.outcome is (
        OperationOutcome.CONNECTION_FAILED
        if incompatible or endpoint == "offline"
        else OperationOutcome.SUCCESS
    )
    if incompatible:
        assert (
            "lacks the write and status channels"
            in verify["description_placeholders"]["capabilities"]
        )
        assert result["step_id"] == "profile_questions"
        assert result["errors"] == {CONF_PROTOCOL_VARIANT: "sleeptime_gatt"}
    else:
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PROTOCOL_VARIANT] == "404"
    read_info.assert_not_called()
    client.write_gatt_char.assert_not_awaited()
    client.read_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()
    if endpoint != "offline":
        client.disconnect.assert_awaited_once()


async def test_persisted_single_address_pair_fails_live_admission(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sleeptime sides",
        unique_id="sleeptime-pair",
        data={
            **ENTRY_DATA,
            CONF_PAIR_ID: "sleeptime-pair",
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = _client()
    controller = SleeptimeController(coordinator, "404")
    coordinator._controller = controller
    await controller.async_discover_capabilities()
    monkeypatch.setattr(
        AdjustableBedCoordinator, "async_create", AsyncMock(return_value=coordinator)
    )
    monkeypatch.setattr(coordinator, "async_connect", AsyncMock(return_value=True))
    shutdown = AsyncMock()
    monkeypatch.setattr(coordinator, "async_shutdown", shutdown)
    forward = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward)

    with pytest.raises(ConfigEntryError) as error:
        await async_setup_entry(hass, entry)
    assert error.value.translation_key == "single_address_pair_unsupported"
    shutdown.assert_awaited_once()
    forward.assert_not_awaited()


def _writes(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


async def test_cancelled_hold_owns_its_delayed_stop():
    controller, _, client = await _connected()
    wrote = asyncio.Event()
    client.write_gatt_char.side_effect = lambda *_args, **_kwargs: wrote.set()
    with virtual_clock():
        hold = asyncio.create_task(controller.hold_control("bed_height_up", 5000))
        await wrote.wait()
        hold.cancel()
        with pytest.raises(asyncio.CancelledError):
            await hold
        await controller.hold_control("bed_height_down", 1)
    assert _writes(client) == [
        bytes.fromhex("05 02 00 00 00 50 01"),
        app.STOP,
        bytes.fromhex("05 02 00 00 00 a0 01"),
        app.STOP,
    ]
    assert {call.kwargs["response"] for call in client.write_gatt_char.await_args_list} == {False}


@pytest.mark.parametrize("release_fails", [False, True])
async def test_pending_move_waits_for_previous_moves_stop(release_fails):
    controller, coordinator, client = await _connected()
    scheduler = DeviceCommandScheduler("Sleeptime")
    wrote = asyncio.Event()
    sent = []
    failed = False

    def send(_char, frame, **_kwargs):
        nonlocal failed
        if frame == app.STOP and release_fails and not failed:
            failed = True
            raise BleakError("first release failed")
        sent.append(frame)
        wrote.set()

    client.write_gatt_char.side_effect = send

    async def up(context):
        coordinator.cancel_command = context.cancel_event
        await controller.hold_control("bed_height_up", 5000)

    async def down(context):
        coordinator.cancel_command = context.cancel_event
        await controller.hold_control("bed_height_down", 1)

    with virtual_clock():
        first = asyncio.create_task(scheduler.execute(CommandIntent(up)))
        await wrote.wait()
        await scheduler.execute(CommandIntent(down))
        await asyncio.gather(first, return_exceptions=release_fails)
    assert failed is release_fails
    assert sent == [
        bytes.fromhex("05 02 00 00 00 50 01"),
        app.STOP,
        bytes.fromhex("05 02 00 00 00 a0 01"),
        app.STOP,
    ]


@pytest.mark.parametrize(
    ("stop_route", "release_fails"),
    [("global", False), ("cover", False), ("gesture", False), ("global", True), ("gesture", True)],
)
async def test_stop_reuses_only_successful_release_before_next_movement(
    hass, monkeypatch, stop_route, release_fails
):
    entry = MockConfigEntry(domain=DOMAIN, title="Sleeptime", unique_id=ADDRESS, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _client()
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    coordinator._client = client
    controller = SleeptimeController(coordinator, "404")
    coordinator._controller = controller
    await controller.async_discover_capabilities()
    monkeypatch.setattr(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
    monkeypatch.setattr(coordinator, "_async_refresh_controller_auth", AsyncMock())

    delivery = []
    native_send_stop = controller._send_stop

    async def record_stop():
        with delivered(delivery.append):
            await native_send_stop()

    monkeypatch.setattr(controller, "_send_stop", record_stop)
    spec = next(spec for spec in controller.motor_control_specs if spec.key == "bed_height")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.hass, cover.async_write_ha_state = hass, MagicMock()
    release = next(spec for spec in controller.controller_button_specs if spec.release_only)
    button = ControllerActionButton(coordinator, release)
    button.hass = hass
    stop = {
        "global": coordinator.async_stop_command,
        "cover": cover.async_stop_cover,
        "gesture": button.async_press,
    }[stop_route]

    sent = []
    failed = False
    up, down = (bytes.fromhex("05 02 00 00 00 50 01"), bytes.fromhex("05 02 00 00 00 a0 01"))
    with virtual_clock() as clock:

        def send(_char, frame, **_kwargs):
            nonlocal failed
            if frame == app.STOP and release_fails and not failed:
                failed = True
                raise BleakError("first release failed")
            sent.append((round(clock.elapsed * 1000), frame))

        client.write_gatt_char.side_effect = send
        active = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda ctrl: ctrl.hold_control("bed_height_up", 5000),
            )
        )
        await asyncio.sleep(0.35)
        stopping = asyncio.create_task(stop())
        await asyncio.sleep(0.001)
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.hold_control("bed_height_down", 1),
        )
        await stopping
        await asyncio.gather(active, return_exceptions=release_fails)
        assert [frame for _, frame in sent] == [up, up, app.STOP, down, app.STOP]
        assert sent[2][0] == (550 if release_fails else 450)
        assert failed is release_fails
        assert delivery == [Delivery.SENT]

        # A past receipt cannot make an unrelated explicit STOP a no-op.
        await coordinator.async_stop_command()
        assert len(sent) == 6 and sent[-1][1] == app.STOP
        assert delivery == [Delivery.SENT, Delivery.SENT]

        await coordinator.async_shutdown()


@pytest.mark.parametrize("failed_stops", [0, 1, 2], ids=["release", "fallback", "failure"])
async def test_sequential_paired_cover_stop_settles_before_disconnect(hass, monkeypatch, failed_stops):
    def receiver(address):
        entry = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, CONF_ADDRESS: address})
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._controller = SleeptimeController(coordinator, "404")
        return coordinator

    left, right = receiver(ADDRESS), receiver("11:22:33:44:55:77")
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "sleeptime-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {SIDE_LEFT: left, SIDE_RIGHT: right},
        connection_mode=PAIR_CONNECTION_MODE_SEQUENTIAL,
    )
    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    client = _client()
    client.is_connected = False
    left._client = client
    controller = left.controller
    assert controller is not None

    async def connect_left():
        client.is_connected = True
        await controller.async_discover_capabilities()
        return True

    connect = AsyncMock(side_effect=connect_left)
    ensure = AsyncMock(side_effect=lambda **_kwargs: client.is_connected)
    connect_right = AsyncMock(return_value=False)
    monkeypatch.setattr(left, "async_connect", connect)
    monkeypatch.setattr(left, "async_ensure_connected", ensure)
    monkeypatch.setattr(left, "_async_refresh_controller_auth", AsyncMock())
    monkeypatch.setattr(right, "async_connect", connect_right)
    spec = next(spec for spec in controller.motor_control_specs if spec.key == "bed_height")
    cover = AdjustableBedCover(PairedSideProxy(pair, left, SIDE_LEFT), _build_cover_description(spec))
    cover.hass, cover.async_write_ha_state = hass, MagicMock()
    up = bytes.fromhex("05 02 00 00 00 50 01")
    events = []
    stops = 0

    with virtual_clock() as clock:
        def record(event):
            events.append((round(clock.elapsed * 1000), event))

        def send(_char, frame, **_kwargs):
            nonlocal stops
            assert client.is_connected
            record(frame)
            if frame == app.STOP:
                stops += 1
                if stops <= failed_stops:
                    raise BleakError(f"STOP write {stops} failed")

        def disconnect():
            record("disconnected")
            client.is_connected = False

        client.write_gatt_char.side_effect = send
        client.disconnect.side_effect = disconnect
        movement = asyncio.create_task(cover.async_open_cover())
        await asyncio.sleep(0.35)
        stop_error = None
        try:
            await cover.async_stop_cover()
        except PairedSideError as err:
            stop_error = err
        events_at_stop = events.copy()
        (result,) = await asyncio.gather(movement, return_exceptions=True)
        events_after_move = events.copy()
        await pair.async_shutdown()

        if failed_stops == 2:
            assert stop_error is not None
            assert "STOP write 2 failed" in str(stop_error.side_errors[SIDE_LEFT])
        else:
            assert stop_error is None
        expected = [(0, up), (300, up), (450, app.STOP)]
        if failed_stops:
            expected.append((550, app.STOP))
        assert events_at_stop[:len(expected)] == expected
        if failed_stops:
            assert isinstance(result, PairedSideError)
            assert "STOP write 1 failed" in str(result.side_errors[SIDE_LEFT])
        else:
            assert result is None
        assert events_after_move == [*expected, (expected[-1][0], "disconnected")]
        connect.assert_awaited_once()
        ensure.assert_awaited_once()
        connect_right.assert_not_awaited()


async def test_sleeptime_motor_lease_keeps_refreshing_then_releases():
    async def lift(controller):
        await controller.hold_control("bed_height_up", 500)

    result = await leased_hold("sleeptime:404", lift, end_after_s=1.05, end="expire")
    lift_frame = bytes.fromhex("05 02 00 00 00 50 01")
    assert result.held == tuple(Write(at, lift_frame) for at in (0, 300, 600, 900))
    assert result.after == (Write(1150, app.STOP),)


@pytest.mark.parametrize("reply", [ALARM, ED], ids=["a5", "ed"])
async def test_frozen_alarm_replies_update_editor_after_fragment_is_consumed(reply):
    _, coordinator, client = await _connected(indicate=True)
    characteristic, receive = client.start_notify.await_args.args
    zero = reply[:4] + bytes(1) + reply[5:]
    receive(characteristic, bytearray(FRAGMENT))
    receive(characteristic, bytearray(zero))
    coordinator.handle_controller_state_updates.assert_not_called()

    receive(characteristic, bytearray(reply))
    values = {
        update.key: update.value
        for update in coordinator.handle_controller_state_updates.call_args.args
    }
    assert values == {
        "alarm_editor_time": f"{reply[6]:02d}:{reply[7]:02d}",
        "alarm_editor_enabled": True,
        "alarm_editor_mode": reply[5],
        "alarm_editor_weekday_mask": reply[4],
        "alarm_reported_weekday_mask": reply[4],
        "alarm_reported_open": 1,
    }
    receive(characteristic, bytearray(zero))
    values = {
        update.key: update.value
        for update in coordinator.handle_controller_state_updates.call_args.args
    }
    assert values == {
        "alarm_editor_time": "06:30",
        "alarm_editor_enabled": False,
        "alarm_editor_mode": 8,
        "alarm_editor_weekday_mask": 255,
        "alarm_reported_weekday_mask": 0,
        "alarm_reported_open": 1,
    }


async def test_alarm_writes_keep_their_payload_and_use_the_disabled_editor_fields():
    controller, coordinator, client = await _connected(indicate=True)
    characteristic, receive = client.start_notify.await_args.args
    receive(characteristic, bytearray(MASSAGE))
    values = {
        update.key: update.value
        for update in coordinator.handle_controller_state_updates.call_args.args
    }
    assert values["massage_remaining_seconds"] == 601 and values["massage_timer_band"] == 2

    def answer(_characteristic, frame, **_kwargs):
        if frame == app.ALARM_QUERY:
            receive(characteristic, bytearray(ALARM))

    client.write_gatt_char.side_effect = answer
    request = AlarmRequest(
        enabled=True,
        wake_action="reading",
        hour=23,
        minute=59,
        weekdays=tuple(range(7)),
        reference_time=datetime(2026, 11, 28, 9),
    )
    with virtual_clock():
        await controller.configure_alarm(request)
        enabled = bytes.fromhex("07 05 02 ff 17 3b 00 01 00")
        assert _writes(client) == [enabled, enabled, *([app.ALARM_QUERY] * 3)]
        client.write_gatt_char.reset_mock()
        await controller.configure_alarm(replace(request, enabled=False))
        disabled = bytes.fromhex("07 05 08 04 06 1e 00 00 00")
        assert _writes(client) == [app.ALARM_QUERY, disabled, disabled, *([app.ALARM_QUERY] * 3)]


async def test_buffered_ed_cannot_supply_an_alarm_disable_reply():
    controller, coordinator, client = await _connected()
    characteristic, receive = client.start_notify.await_args.args

    def answer(_characteristic, frame, **_kwargs):
        if frame == app.ALARM_QUERY:
            receive(characteristic, bytearray(FRAGMENT))
            receive(characteristic, bytearray(ED))

    client.write_gatt_char.side_effect = answer
    with virtual_clock(), pytest.raises(TimeoutError):
        await controller.configure_alarm(
            AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 28, 9))
        )
    assert _writes(client) == [app.ALARM_QUERY]
    coordinator.handle_controller_state_updates.assert_not_called()


def test_fragment_replacement_and_short_chunks_preserve_the_pending_prefix():
    parser = codec.SingleRecordParser()
    assert parser.feed(FRAGMENT) is None
    assert parser.feed(b"\xa5\x0b") is None and parser.pending
    assert parser.feed(b"\x09" + FRAGMENT[1:]) is None and parser.pending
    assert parser.feed(ED) is None and not parser.pending
    assert parser.feed(ED) == codec.ShortAlarmReport(1, 3, 9, 7, 45, 1)
    assert parser.feed(ED[:9]) is None
    assert parser.feed(ALARM[:9]) is None
    assert parser.feed(MASSAGE[:8]) is None
