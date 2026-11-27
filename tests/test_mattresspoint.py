"""Bounded MattressPoint vectors, HA admission and physical session lifetime."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import config_flow
from custom_components.adjustable_bed.beds.mattresspoint.controller import (
    ALARM_ENABLED,
    MASSAGE_ACTIVE,
    MattressPointController,
)
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import (
    CommandIntent,
    Delivery,
    DeviceCommandScheduler,
    delivered,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles import mattresspoint as app
from tests.form_helpers import NEW_BED_ROUTES, form_fields, marker_default, start_new_bed
from tests.hold_lease_wire import Write, leased_hold, virtual_clock
from tests.test_config_flow import _patch_gate
from tests.test_controller_contract import _create_controller_for_bed_type, _FactoryCoordinator
from tests.test_detection import _make_service_info
from tests.test_sleeptime import _client, _writes

VECTORS = json.loads((Path(__file__).parent / "fixtures/mattresspoint_vectors.json").read_text())
DATA = {
    CONF_ADDRESS: "11:22:33:44:55:66",
    CONF_NAME: "MattressPoint",
    CONF_BED_TYPE: "mattresspoint",
    CONF_PROTOCOL_VARIANT: "BOX2422",
}
NAMES = {
    "headUp": "back_up",
    "headDown": "back_down",
    "footUp": "legs_up",
    "footDown": "legs_down",
    "HFUp": "both_up",
    "HFDown": "both_down",
    "headTiltUp": "head_tilt_up",
    "headTiltDown": "head_tilt_down",
    "lumbarUp": "lumbar_up",
    "lumbarDown": "lumbar_down",
    "memory_tvpc": "tv",
    "memory_zero": "zero_g",
    "memory_lounge": "lounge",
    "memory_antiSnore": "anti_snore",
    "flatPosition": "flat",
}
MASSAGE = {
    "massageStopAll": "off",
    "massageAll": "on",
    "timerSwitch": "timer",
    "waveAdd": "wave_up",
    "waveReduce": "wave_down",
    "headStrengthAdd": "head_up",
    "headStrengthReduce": "head_down",
    "footStrengthAdd": "foot_up",
    "footStrengthReduce": "foot_down",
}


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_all_frozen_vectors_use_existing_codec(v):
    p = v["inputs"]["parameters"]
    kind = v["inputs"]["kind"]
    name = v["action"]
    expected = bytes.fromhex(v["expected_bytes"])
    if name in NAMES:
        got = codec.frame40(app.PROFILES["BOX2442"].keys[NAMES[name]])
    elif name in MASSAGE:
        got = codec.frame40(app.MASSAGE[MASSAGE[name]])
    elif name in {
        "massageCheck",
        "underbedLighting",
        "reset",
        "stopCommand",
        "closeAlarm",
        "checkAlarm",
    }:
        got = {
            "massageCheck": app.MASSAGE_QUERY,
            "underbedLighting": app.LIGHT,
            "reset": app.RESET,
            "stopCommand": app.STOP,
            "closeAlarm": app.ALARM_DISABLE,
            "checkAlarm": app.ALARM_QUERY,
        }[name]
    elif kind == "clock":
        now = datetime(p["year"], p["month"], p["day"], p["hour"], p["minute"], p["second"])
        assert now.isoweekday() == p["weekday"]
        got = app.clock(now)
    elif kind == "alarm":
        got = app.alarm(**p)
    else:
        report = codec.SingleRecordParser().feed(expected)
        assert isinstance(report, codec.MassageReport)
        assert {
            "remaining_raw": report.seconds,
            "timer_bucket": (report.seconds - 1) // 600 + 1 if 1 <= report.seconds <= 1800 else 0,
            "head": report.head,
            "foot": report.foot,
            "mode": report.mode,
        } == v["expected_state"]
        return
    assert got == expected


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_native_setup_always_requires_explicit_box(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    choice = (
        (await flow.async_step_select_app())["data_schema"]
        .schema[CONF_BED_TYPE]
        .rows()["MattressPoint app (BOX2422 / BOX2442)"]
    )
    flow._discovery_info = _make_service_info(name="advertisement")
    flow._discovery_info.device.name = "SmartBed404-123"
    flow._async_transport_note = AsyncMock(return_value="")
    form = await start_new_bed(flow, route, choice)
    assert form["step_id"] == "profile_questions"
    field = next(
        mark for mark in form_fields(form["data_schema"]) if mark.schema == CONF_PROTOCOL_VARIANT
    )
    assert marker_default(field) is vol.UNDEFINED
    result = await flow.async_step_profile_questions({CONF_PROTOCOL_VARIANT: "BOX2442"})
    assert result["step_id"] == "finish_settings"
    assert flow._manual_data[CONF_PROTOCOL_VARIANT] == "BOX2442"
    info = _make_service_info(name="advertisement")
    info.device.name = "sMaRtBeD123"
    detected = detect_bed_type_detailed(info)
    assert "mattresspoint" in {detected.bed_type, *(detected.ambiguous_types or ())}
    assert detected.confidence < 0.8


@pytest.mark.parametrize(
    "box,axes",
    [
        ("BOX2422", ("back", "legs", "both")),
        ("BOX2442", ("back", "legs", "both", "tilt", "lumbar")),
    ],
)
async def test_factory_admits_only_selected_box_controls(box, axes):
    ctrl = await _create_controller_for_bed_type("mattresspoint", box)
    assert tuple(s.key for s in ctrl.motor_control_specs) == axes
    assert not ctrl.supports_memory_programming and not ctrl.supports_preset_flat
    assert ctrl.alarm_capability is None
    assert ctrl.requires_linked_live_readiness
    assert ctrl.execution.declared == {"hold", "hold_controls"}
    assert ctrl.execution.hold_for("back_up") == "stream"
    assert ctrl.execution.hold_for("flat") is None
    assert not ctrl.execution.concurrent
    assert not ctrl.supports_single_address_pairing
    with pytest.raises(HomeAssistantError):
        ctrl.validate_hold_control("flat", 300)


async def connected(box="BOX2442"):
    coordinator = _FactoryCoordinator()
    coordinator.record_command_trace = MagicMock()
    coordinator.handle_controller_state_updates = lambda *updates: (
        coordinator.controller_state.update((u.key, u.value) for u in updates)
    )
    client = _client()
    coordinator.client = client
    ctrl = MattressPointController(coordinator, box)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    return ctrl, coordinator, client


@pytest.mark.parametrize("endpoint", ["response_only", "wrong_service", "indicate", "offline"])
async def test_real_setup_probe_checks_properties_and_cleans_up(hass, monkeypatch, endpoint):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    monkeypatch.setattr(flow, "_verification_possible", lambda: True)
    client = _client(
        indicate=True,
        write_property="write" if endpoint == "response_only" else "write-without-response",
        service_uuid="180a" if endpoint == "wrong_service" else app_uuid(),
    )
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        AsyncMock(
            return_value=client,
            side_effect=BleakError("offline") if endpoint == "offline" else None,
        ),
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock(return_value=True))
    read = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", read)
    with _patch_gate("hci0", -55):
        progress = await flow._finish_with_verify(dict(DATA), "MattressPoint")
        await progress["progress_task"]
        await flow.async_step_setup_progress()
    await flow.async_step_verify_connection()
    result = await flow.async_step_verify_connection({})
    if endpoint in {"response_only", "wrong_service"}:
        assert result["step_id"] == "profile_questions"
        assert result["errors"] == {CONF_PROTOCOL_VARIANT: "mattresspoint_gatt"}
    read.assert_not_called()
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()
    client.read_gatt_char.assert_not_awaited()
    if endpoint != "offline":
        client.disconnect.assert_awaited_once()


def app_uuid():
    from custom_components.adjustable_bed.const import NORDIC_UART_SERVICE_UUID

    return NORDIC_UART_SERVICE_UUID


async def test_reconnect_and_diagnostic_retirement_ignore_old_notification_and_stop():
    ctrl, coord, old = await connected()
    char, receive = old.start_notify.await_args.args
    old_link = ctrl._live()
    old.stop_notify.side_effect = BleakError("retained physical link")
    with pytest.raises(BleakError):
        await ctrl.stop_notify()
    receive(char, bytearray.fromhex("a50b0e000000000000"))
    assert all(value is None for value in coord.controller_state.values())
    # A failed disconnect leaves the client connected: a renewed subscription is distinct.
    await ctrl.start_notify()
    char, new_receive = old.start_notify.await_args.args
    new_receive(char, bytearray.fromhex("a50b0e000258030508"))
    assert coord.controller_state[MASSAGE_ACTIVE] is True
    replacement = _client()
    coord.client = replacement
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    with virtual_clock():
        await ctrl._release(old_link)
    replacement.write_gatt_char.assert_not_awaited()
    receive(char, bytearray.fromhex("a50c0e00000000000001"))
    assert coord.controller_state.get(ALARM_ENABLED) is None
    # Same UUID is insufficient when the live property was lost.
    replacement.services.get_service(app_uuid()).get_characteristic(
        ctrl.control_characteristic_uuid
    ).properties = ["write"]
    with pytest.raises(HomeAssistantError):
        await ctrl.async_validate_linked_readiness()


async def test_actual_task_cancel_waits_for_submitted_movement_then_releases():
    ctrl, _, client = await connected()
    submitted = asyncio.Event()
    finish = asyncio.Event()

    async def write(_char, frame, **kwargs):
        assert kwargs["response"] is False
        if frame != app.STOP:
            submitted.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(ctrl.hold_control("back_up", 5000))
        await submitted.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert _writes(client) == [codec.frame40(1), app.STOP]


@pytest.mark.parametrize(
    "point", ["before", "partial", "final", "failure", "report", "replacement"]
)
async def test_sent_alarm_state_obeys_delivery_and_report_priority(point):
    ctrl, coord, client = await connected()
    scheduler = DeviceCommandScheduler("MattressPoint")
    deliveries = []
    attempts = 0
    char, receive = client.start_notify.await_args.args

    async def write(_char, frame, **kwargs):
        nonlocal attempts
        attempts += 1
        if point == "failure" and attempts == 2:
            raise BleakError("write failed")
        if point == "report":
            receive(char, bytearray.fromhex("a50c0e00ff05071e0001"))
        if point == "replacement":
            ctrl.on_disconnect()
        if point == "partial" and attempts == 1 or point == "final" and attempts == 3:
            coord.cancel_command.set()

    client.write_gatt_char.side_effect = write

    async def run(ctx):
        coord.cancel_command = ctx.cancel_event
        if point == "before":
            ctx.cancel_event.set()
        with delivered(deliveries.append):
            await ctrl.disable_alarm()

    with virtual_clock():
        if point in {"failure", "replacement"}:
            with pytest.raises((BleakError, HomeAssistantError)):
                await scheduler.execute(CommandIntent(run))
        else:
            await scheduler.execute(CommandIntent(run))
    assert deliveries == [
        {
            "before": Delivery.NONE,
            "partial": Delivery.PARTIAL,
            "final": Delivery.SENT,
            "failure": Delivery.PARTIAL,
            "report": Delivery.SENT,
            "replacement": Delivery.PARTIAL,
        }[point]
    ]
    if point == "final":
        assert coord.controller_state[ALARM_ENABLED] is False
    elif point == "report":
        assert coord.controller_state[ALARM_ENABLED] is True
    elif point in {"partial", "failure"}:
        assert coord.controller_state[ALARM_ENABLED] is None
    else:
        assert coord.controller_state.get(ALARM_ENABLED) is None


@pytest.mark.parametrize("stop_route", ["cover", "global"])
async def test_native_cover_stop_and_next_move_serialize(hass, monkeypatch, stop_route):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    client = _client()
    coord._client = client
    ctrl = MattressPointController(coord, "BOX2422")
    coord._controller = ctrl
    await ctrl.async_discover_capabilities()
    monkeypatch.setattr(coord, "async_ensure_connected", AsyncMock(return_value=True))
    monkeypatch.setattr(coord, "_async_refresh_controller_auth", AsyncMock())
    cover = AdjustableBedCover(coord, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.hass, cover.async_write_ha_state = hass, MagicMock()
    with virtual_clock():
        task = asyncio.create_task(cover.async_open_cover())
        await asyncio.sleep(0.35)
        await (cover.async_stop_cover() if stop_route == "cover" else coord.async_stop_command())
        await task
        await coord.async_execute_controller_command(lambda c: c.hold_control("back_down", 1))
        await coord.async_shutdown()
    assert _writes(client)[:5] == [
        codec.frame40(1),
        codec.frame40(1),
        app.STOP,
        codec.frame40(2),
        app.STOP,
    ]


async def test_renewable_lease_expires_with_delayed_stop():
    result = await leased_hold(
        "mattresspoint:BOX2422",
        lambda c: c.hold_control("back_up", 500),
        end_after_s=1.05,
        end="expire",
    )
    assert result.held == tuple(Write(at, codec.frame40(1)) for at in (0, 300, 600, 900))
    assert result.after == (Write(1150, app.STOP),)


@pytest.mark.parametrize("failed_disconnect", [False, True])
async def test_real_idle_disconnect_restores_or_rebuilds_session(
    hass,
    monkeypatch,
    mock_coordinator_connected,
    mock_establish_connection,
    failed_disconnect,
):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA)
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    first, second = _client(), _client()
    for client in (first, second):
        client.address = DATA[CONF_ADDRESS]
        for char in client.services.get_service(app_uuid()).characteristics:
            char.descriptors = []
    first.disconnect.side_effect = (
        (lambda: None) if failed_disconnect else lambda: setattr(first, "is_connected", False)
    )
    mock_establish_connection.side_effect = [first, second]
    with virtual_clock():
        assert await coord.async_connect()
        original = coord.controller
        char, old_receive = first.start_notify.await_args.args
        assert isinstance(original, MattressPointController)
        assert await coord.async_disconnect(reason="idle_timeout") is (not failed_disconnect)
        if failed_disconnect:
            assert coord.controller is original and coord.is_connected
            assert first.start_notify.await_count == 2
            assert original._subscribed
        else:
            assert not coord.is_connected
        await coord.async_execute_controller_command(lambda c: c.hold_control("back_up", 1))
        active = first if failed_disconnect else second
        assert _writes(active)[-2:] == [codec.frame40(1), app.STOP]
        old_receive(char, bytearray.fromhex("a50c0e00ff05071e0001"))
        assert coord.controller_state.get(ALARM_ENABLED) is None
        # Close the retained test client so shutdown can release it normally.
        active.disconnect.side_effect = lambda: setattr(active, "is_connected", False)
        await coord.async_shutdown()


@pytest.mark.parametrize("failure", ["capability", "live_gatt", None])
async def test_registered_paired_hold_preflights_every_physical_target(hass, monkeypatch, failure):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    members = []
    for index in range(2):
        entry = MockConfigEntry(
            domain=DOMAIN, data={**DATA, CONF_ADDRESS: f"11:22:33:44:55:{66 + index:02X}"}
        )
        entry.add_to_hass(hass)
        coord = AdjustableBedCoordinator(hass, entry)
        client = _client()
        coord._client = client
        ctrl = MattressPointController(
            coord, "BOX2422" if failure == "capability" and index else "BOX2442"
        )
        coord._controller = ctrl
        await ctrl.async_discover_capabilities()
        await ctrl.start_notify()
        coord._link_ready = True
        monkeypatch.setattr(coord, "async_ensure_connected", AsyncMock(return_value=True))
        monkeypatch.setattr(coord, "_async_refresh_controller_auth", AsyncMock())
        client.disconnect.side_effect = lambda client=client: setattr(client, "is_connected", False)
        members.append((coord, client))
    left, right = (m[0] for m in members)
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "mattresspoint-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, "both")], []))
    await services.async_register_services(hass)
    if failure == "live_gatt":
        right.controller._live().write.properties = ["write"]
    with virtual_clock():

        async def hold():
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": "bed", "control": "head_tilt_up", "duration": 0.1},
                blocking=True,
            )

        if failure:
            from custom_components.adjustable_bed.paired_topology import PairedSideError

            with pytest.raises((ServiceValidationError, PairedSideError)):
                await hold()
            assert all(not _writes(client) for _, client in members)
        else:
            await hold()
            assert all(_writes(client) == [codec.frame40(0x10), app.STOP] for _, client in members)
        await pair.async_shutdown()


@pytest.mark.parametrize(
    "header", [bytes.fromhex("a50b0e"), bytes.fromhex("a50c0e"), bytes.fromhex("ed8003")]
)
def test_shared_parser_rejects_short_matching_records_and_retires_fragment(header):
    needed = 9 if header == bytes.fromhex("a50b0e") else 10
    for size in range(len(header), needed):
        assert codec.SingleRecordParser().feed(header + bytes(size - len(header))) is None
    parser = codec.SingleRecordParser()
    fragment = bytes.fromhex("00fe16") + bytes(17)
    assert parser.feed(fragment) is None
    assert parser.feed(header + bytes(needed - len(header))) is None
    assert parser.feed(header + bytes(needed - len(header))) is not None


@pytest.mark.parametrize("point", ["locked", "between", "last_submitted"])
async def test_task_cancelled_alarm_settles_none_partial_and_final(point):
    ctrl, coord, client = await connected()
    scheduler = DeviceCommandScheduler("MattressPoint")
    ready = asyncio.Event()
    finish = asyncio.Event()
    writes = 0

    async def send(_char, frame, **_kwargs):
        nonlocal writes
        writes += 1
        if point == "between" and writes == 1:
            ready.set()
        if point == "last_submitted" and writes == 3:
            ready.set()
            await finish.wait()

    client.write_gatt_char.side_effect = send

    async def operation(ctx):
        coord.cancel_command = ctx.cancel_event
        await ctrl.disable_alarm()

    with virtual_clock():
        if point == "locked":
            await ctrl._ble_lock.acquire()
        task = asyncio.create_task(scheduler.execute(CommandIntent(operation)))
        if point == "locked":
            await asyncio.sleep(0)
        else:
            await ready.wait()
        task.cancel()
        await asyncio.sleep(0)
        if point == "locked":
            ctrl._ble_lock.release()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert coord.controller_state[ALARM_ENABLED] is (False if point == "last_submitted" else None)
    assert len(_writes(client)) == {"locked": 0, "between": 1, "last_submitted": 3}[point]
