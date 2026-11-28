"""Softide frozen contracts through codec, session, native HA and command lanes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.sleep_assistant import softide as bed
from custom_components.adjustable_bed.beds.sleep_assistant.softide_state import (
    Rates,
    SoftideState,
    no_data,
)
from custom_components.adjustable_bed.codec import sleep_assistant as codec
from custom_components.adjustable_bed.profiles import softide as app
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.hold_lease_wire import _tool, virtual_clock

FIXTURES = Path(__file__).parent / "fixtures/softide"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:82"
NAME = "KSWF16S182"


def data(model="3", route="primary", sensors="single", prepare=False):
    return {
        "address": ADDRESS,
        "name": NAME,
        const.CONF_BLE_DEVICE_NAME: NAME,
        const.CONF_BED_TYPE: "softide",
        const.CONF_PROTOCOL_VARIANT: model,
        const.CONF_PRODUCT_TYPE: route,
        app.CONF_SENSORS: sensors,
        app.CONF_PREPARE: prepare,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_HAS_MASSAGE: False,
        const.CONF_MOTOR_COUNT: 3 if model in ("4", "9") else 2,
        const.CONF_MOTOR_PULSE_COUNT: 1,
        const.CONF_MOTOR_PULSE_DELAY_MS: 300,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }


def entry(hass, model="3", route="primary", sensors="single", prepare=False):
    e = MockConfigEntry(
        domain=const.DOMAIN,
        title="Softide",
        unique_id=ADDRESS,
        version=5,
        minor_version=3,
        data=data(model, route, sensors, prepare),
    )
    e.add_to_hass(hass)
    return e


def gatt(properties=("write",)):
    return _tool().FakeServices(
        {
            "services": {app.SERVICE: [app.WRITE, app.NOTIFY]},
            "properties": {app.WRITE: list(properties), app.NOTIFY: ["notify"]},
        }
    )


async def connected(hass, client, model="3", route="primary", sensors="single", prepare=False):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    e = entry(hass, model, route, sensors, prepare)
    c = AdjustableBedCoordinator(hass, e)
    client.services = gatt()
    c._client = client
    c._controller = controller = bed.SoftideController(c, app.selected(e.data))
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return c, controller


def written(client):
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    "row",
    [v for v in VECTORS if not v["fixture_disposition"].startswith(("DEAD", "DEFERRED"))],
    ids=lambda r: r["id"],
)
def test_all_frozen_reachable_literals_use_production_codec(row):
    inputs = row["inputs"]
    expected = bytes.fromhex(row["expected_bytes"])
    if "key" in inputs:
        assert app.instruction(inputs["key"]) == expected
    else:
        candidates = [
            *codec.SOFTIDE_LITERALS.values(),
            *(codec.aa_key(v[1]) for v in app.PROGRAMS.values()),
            *(app.frame(k) for k in app.WORDS),
        ]
        assert expected in candidates


def test_all_49_command_rows_have_identical_production_wire():
    for row in COMMANDS:
        if "key" in row:
            assert app.instruction(row["key"]) == bytes.fromhex(row["bytes"]), row["id"]
        elif row["kind"] == "program":
            action = next(
                key
                for key, (name, _) in app.PROGRAMS.items()
                if name.casefold() == row["action"].split(" / ")[0].casefold()
            )
            records = app.program(action)
            assert [at for at, _ in records] == [0, 200, 200, 800, 800, 1400, 1400]
            assert records[-2][1] == bytes.fromhex(row["target_frame"])
        elif row["event_id"] == 1061:
            assert row["bytes"].startswith("NO FRAME")
        else:
            assert bytes.fromhex(row["bytes"]) in [
                app.frame("stop"),
                *codec.SOFTIDE_LITERALS.values(),
            ]
    for row in json.loads((FIXTURES / "literals.json").read_text()):
        if row["scope"] == "DIRECT_BLE" and row["disposition"] not in ("DEAD/UNUSED",):
            candidates = {
                *codec.SOFTIDE_LITERALS.values(),
                *(codec.aa_key(v[1]) for v in app.PROGRAMS.values()),
                *(app.frame(k) for k in app.WORDS),
            }
            assert bytes.fromhex(row["hex"]) in candidates
    assert app.instruction(3) == app.frame("stop")
    assert app.instruction(5) == bytes.fromhex("AA03000A00040105000000F5F355")
    assert app.instruction(10) == bytes.fromhex("AA03000A0004010A000000F0F355")


@pytest.mark.parametrize(
    "model,layout",
    [
        ("1", "IQ1"),
        ("2", "IQ1"),
        ("3", "IQ3"),
        ("4", "IQ3Y"),
        ("5", "IQ1"),
        ("6", "IQ1"),
        ("7", "IQ1"),
        ("8", "IQ3"),
        ("9", "IQ3Y"),
        ("other", "IQ1"),
        ("-1", None),
    ],
)
def test_local_selector_gates(model, layout):
    p = app.selected(data(model))
    assert p.layout == layout
    assert replace(p, route="care").layout == (layout or "IQ1")
    assert bool(p.axes) == (layout is not None)
    assert ("relaxation" in p.controls) == (layout in ("IQ3", "IQ3Y"))
    assert ("after_drinking" in p.programs) == (model not in ("1", "2", "5", "6", "7"))
    assert not replace(p, route="care").programs


@pytest.mark.parametrize("model", app.MODELS)
@pytest.mark.parametrize("route", app.ROUTES)
async def test_real_setup_factory_and_profile_id(hass, model, route):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["softide"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions(
        {
            const.CONF_PROTOCOL_VARIANT: model,
            const.CONF_PRODUCT_TYPE: route,
            app.CONF_SENSORS: "combined",
            const.CONF_BLE_DEVICE_NAME: NAME,
            app.CONF_PREPARE: False,
        }
    )
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert app.selected(saved) == app.SoftideProfile(model, route, "combined", NAME)
    from custom_components.adjustable_bed.bed_traits import reads_positions

    assert not reads_positions(saved)
    assert saved[const.CONF_MOTOR_PULSE_DELAY_MS] == 300
    assert not saved[const.CONF_HAS_MASSAGE]  # App-declared shapes, no generic duplicates.
    assert resolve_profile_id(saved) == f"softide:{model}"


@pytest.mark.parametrize(
    "name,services", [(NAME, []), ("prefix" + NAME, []), ("Unknown", [app.SERVICE])]
)
def test_shared_discovery_is_only_a_low_confidence_candidate(name, services):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=services))
    assert "softide" in {result.bed_type, *(result.ambiguous_types or ())}
    if result.bed_type == "softide":
        assert result.confidence < 0.7


def test_discovery_respects_receiver_and_exclusion_precedence():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    for name in ("keyboard", "mouse", "Thermometer"):
        result = detect_bed_type_detailed(
            _make_service_info(name=name, service_uuids=[app.SERVICE])
        )
        assert result.bed_type != "softide"
    result = detect_bed_type_detailed(
        _make_service_info(name=NAME, service_uuids=[const.LINAK_CONTROL_SERVICE_UUID])
    )
    assert result.bed_type == "linak"


@pytest.mark.parametrize(
    "model,route",
    [("1", "primary"), ("3", "primary"), ("4", "primary"), ("9", "care"), ("-1", "primary")],
)
async def test_actual_entities_services_and_card_holds(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, model, route
):
    mock_bleak_client.services = gatt()
    e = entry(hass, model, route)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    c = hass.data[const.DOMAIN][e.entry_id]
    controller = c.controller
    assert isinstance(controller, bed.SoftideController)
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    mock_bleak_client.read_gatt_char.assert_not_awaited()
    entities = [v for v in er.async_get(hass).entities.values() if v.config_entry_id == e.entry_id]
    assert len([e for e in entities if e.domain == "cover"]) == len(controller.profile.axes)
    assert controller.memory_slot_count == 0 and not controller.supports_memory_programming
    assert not any("memory" in v.unique_id or "light" in v.unique_id for v in entities)
    assert controller.execution.declared == {"hold"}
    device = next(v.device_id for v in entities if v.device_id)
    with virtual_clock():
        for action in controller.held_control_options:
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": device, "control": action, "duration": 0.65},
                blocking=True,
            )
            frames = written(mock_bleak_client)
            expected = [app.frame(action)] * (3 if action.endswith(("_up", "_down")) else 1)
            if route == "primary":
                expected.append(app.frame("stop"))
            assert frames == expected, action
        for action in (*controller.profile.controls, *controller.profile.programs):
            if action in ("flat", "zero_g", "tv", "reading"):
                entity = next(e for e in entities if e.translation_key == f"preset_{action}")
            else:
                entity = next(e for e in entities if e.unique_id.endswith(f"_softide_{action}"))
            assert hass.states.get(entity.entity_id).attributes["card_section"] in (
                "massage",
                "massage_timer",
                "presets",
            )
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                "button", "press", {"entity_id": entity.entity_id}, blocking=True
            )
            if action in controller.profile.programs:
                expected = [frame for _, frame in app.program(action)]
                if action == "one_button_sleep":
                    expected.insert(0, app.frame("disable_uploads"))
            else:
                expected = [app.frame(action)]
                if route == "primary":
                    expected.append(app.frame("stop"))
                if (
                    action in ("massage_head", "massage_foot", "massage_timer")
                    or route == "primary"
                    and action in app.MODES
                ):
                    expected.append(app.frame("query"))
            assert written(mock_bleak_client) == expected, action
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("route", app.ROUTES)
async def test_refresh_timing_preparation_query_and_release(hass, mock_bleak_client, route):
    c, controller = await connected(hass, mock_bleak_client, route=route, prepare=True)
    times = []

    async def record(char, frame, **kwargs):
        times.append((round(asyncio.get_running_loop().time() * 1000), frame))

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        await controller.hold_control("back_up", 650)
        start = times[0][0]
        assert [t - start for t, _ in times[:3]] == [0, 300, 600]
        if route == "primary":
            assert times[-1][0] - start == 650 and times[-1][1] == app.frame("stop")
        times.clear()
        await controller.perform("massage_head")
        start = times[0][0]
        assert times[0][1] == app.frame("prepare_frequency")
        assert next(t - start for t, f in times if f == app.frame("massage_head")) == 300
        assert times[-1][0] - start == 1000 and times[-1][1] == app.frame("query")
        times.clear()
        await controller.perform("massage_foot")
        assert app.frame("prepare_frequency") not in [f for _, f in times]


@pytest.mark.parametrize(
    "properties,response",
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), False),
    ],
)
async def test_exact_gatt_roles_and_write_mode(hass, mock_bleak_client, properties, response):
    c, controller = await connected(hass, mock_bleak_client)
    mock_bleak_client.services = gatt(properties)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    with virtual_clock():
        await controller.perform("reading")
    assert all(
        call.kwargs["response"] is response
        for call in mock_bleak_client.write_gatt_char.await_args_list
    )
    mock_bleak_client.services = gatt(())
    with pytest.raises(ConnectionError):
        await controller.async_discover_capabilities()
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ConnectionError):
        await controller.perform("reading")
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_inflight_cancellation_settles_original_write_before_cleanup(hass, mock_bleak_client):
    c, controller = await connected(hass, mock_bleak_client)
    entered, proceed = asyncio.Event(), asyncio.Event()

    async def write(char, frame, **kwargs):
        if frame == app.frame("back_up"):
            entered.set()
            await proceed.wait()

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(controller.hold_control("back_up", 500))
        await entered.wait()
        task.cancel()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert written(mock_bleak_client) == [app.frame("back_up"), app.frame("stop")]


@pytest.mark.parametrize("route", app.ROUTES)
async def test_cancelled_program_has_no_late_stage(hass, mock_bleak_client, route):
    c, controller = await connected(hass, mock_bleak_client, route=route)
    if route == "care":
        with pytest.raises(ServiceValidationError):
            await controller.perform("one_button_sleep")
        return

    async def write(char, frame, **kwargs):
        if frame == app.frame("prepare_program"):
            c.cancel_command.set()

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await controller.perform("one_button_sleep")
    assert written(mock_bleak_client) == [
        app.frame("disable_uploads"),
        app.frame("prepare_program"),
        app.frame("stop"),
    ]


async def test_queued_write_cancellation_and_session_replacement(hass, mock_bleak_client):
    c, controller = await connected(hass, mock_bleak_client)
    await controller._ble_lock.acquire()
    task = asyncio.create_task(controller.perform("reading"))
    await asyncio.sleep(0)
    c._position_connection_generation += 1
    controller._ble_lock.release()
    with pytest.raises(HomeAssistantError):
        await task
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    await controller.async_discover_capabilities()
    await controller.start_notify()
    await controller._ble_lock.acquire()
    task = asyncio.create_task(controller.perform("reading"))
    await asyncio.sleep(0)
    c.cancel_command.set()
    controller._ble_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_write_and_notification_failures_do_not_publish_success(hass, mock_bleak_client):
    c, controller = await connected(hass, mock_bleak_client)
    mock_bleak_client.write_gatt_char.side_effect = BleakError("failed")
    with virtual_clock(), pytest.raises((BleakError, HomeAssistantError)):
        await controller.perform("one_button_sleep")
    assert c.controller_state.get(bed.PROGRAM) is None
    controller.on_disconnect()
    mock_bleak_client.start_notify.side_effect = BleakError("subscribe failed")
    await controller.async_discover_capabilities()
    with pytest.raises(BleakError):
        await controller.start_notify()
    assert controller._subscription is None
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ConnectionError):
        await controller.perform("reading")
    mock_bleak_client.write_gatt_char.assert_not_awaited()


def packet(code=1, device=NAME, **values):
    return json.dumps({"code": code, "data": values, "dvid": device, "ts": "1"}).encode()


def test_whole_callback_parser_exact_case_defaults_signed_chars_and_timer():
    d = codec.softide_notification(packet(hr=62, br=14, bm=1, lb=0, si=0, sn=7))
    assert d.data == codec.SoftideData(1, 14, 62, 0, 0, 7)
    assert codec.softide_notification(packet(HR=62)).data.hr == 0
    assert (
        codec.softide_notification(b'{"code":1,"data":{},"dvid":"\x80\xff"}').device
        == "\uff80\uffff"
    )
    for payload in (
        b"",
        b'{"code":1,"data":',
        b"null",
        b'{"code":1,"data":null}',
        packet(hr=True),
        packet(hr=2**31),
    ):
        assert codec.softide_notification(payload) is None
    for tim, expected in ((0, 1), (5999, 1), (6000, 2), (-6000, 0), (-5999, 1)):
        assert codec.SoftideFunction(Tim=tim, FuncF=1).timer_minutes == expected
    assert codec.SoftideFunction(Ftype=1, FuncF=1, Tim=6000).timer_minutes is None
    assert codec.SoftideFunction(FuncF=0, Tim=6000).timer_minutes == 0


def test_independent_sensor_consumers_and_no_data_boundary():
    d = codec.SoftideData(bm=1, hr=62, br=14)
    r = Rates()
    assert r.realtime(d, "single") == (62, 14) and r.twitch == 1
    for _ in range(99):
        r.realtime(d, "single")
    assert r.twitch == 1
    assert r.realtime(replace(d, lb=1), "single") == (0, 0) and r.twitch == 0
    m = Rates()
    assert m.moon(d, "combined", 2) == (62, 14)
    assert m.moon(replace(d, si=1, hr=70, br=12), "combined", 4) is None
    assert m.moon(d, "combined", 6) == (70, 14)
    assert m.moon(replace(d, lb=1), "combined", 8) == (70, 12)
    assert m.moon(d, "right", 9.5) is None
    assert m.moon(d, "right", 11) is None
    assert m.moon(d, "right", 12.501) == (62, 14)
    assert Rates().moon(replace(d, si=2), "left", 2) == (62, 14)
    a = Rates()
    assert a.relax(d, "combined", playing=True) is None
    assert a.relax(replace(d, si=1, hr=70, br=12), "combined", playing=True) == (70, 14)
    assert a.relax(replace(d, si=2), "left", playing=True) is None
    assert a.relax(d, "single", playing=False) is None
    assert a.relax(replace(d, lb=1), "single", playing=True) is None
    assert not no_data(18, 18) and no_data(20, 8) and not no_data(20, 7)
    state = SoftideState()
    state.start("one_button_sleep", 0)
    for i in range(20):
        assert not state.feed(replace(d, hr=0, br=0), "single", i * 2 + 2)
    assert state.moon.shown == 0
    result = False
    for i in range(19):
        result = state.feed(replace(d, hr=0, br=0), "single", 482 + i * 2)
    assert result and state.moon.shown == 19


async def test_readback_is_fenced_and_unknown_fields_stay_diagnostics(hass, mock_bleak_client):
    c, controller = await connected(hass, mock_bleak_client)
    sender, receive = mock_bleak_client.start_notify.await_args.args
    receive(sender, bytearray(packet(hr=62, br=14, bm=1, lb=0, sn=55)))
    assert c.controller_state[bed.HEART] == 62 and c.controller_state[bed.TWITCH] == 1
    receive(sender, bytearray(packet(3, FuncF=1, Tim=6000, Tmasg=99, fmasg=8, hmasg=7)))
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 2
    raw = controller.protocol_diagnostics["last_record"]
    assert isinstance(raw, dict) and raw["data"]["hmasg"] == 7
    receive(sender, bytearray(packet(3, device="another", FuncF=1, Tim=18000)))
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 4
    controller.on_disconnect()
    receive(sender, bytearray(packet(hr=88)))
    assert c.controller_state[bed.HEART] is None
    assert not controller.supports_position_feedback


def test_recommendations_keep_explicit_app_and_strong_receivers():
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_detection import _make_service_info

    assert (
        recommend_profile(data(), _make_service_info(name=NAME, service_uuids=[app.SERVICE]), {})
        is None
    )
    assert (
        recommend_profile(
            {const.CONF_BED_TYPE: "linak"},
            _make_service_info(name=NAME, service_uuids=[const.LINAK_CONTROL_SERVICE_UUID]),
            {},
        )
        is None
    )


@pytest.mark.parametrize("route", app.ROUTES)
async def test_native_scheduler_stop_cancels_pending_refresh_without_reconnecting(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, route
):
    mock_bleak_client.services = gatt()
    e = entry(hass, route=route)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    first = asyncio.Event()

    async def record(char, frame, **kwargs):
        if frame == app.frame("back_up"):
            first.set()

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        task = asyncio.create_task(
            c.async_execute_controller_command(lambda ctrl: ctrl.hold_control("back_up", 10000))
        )
        await first.wait()
        await c.async_stop_command()
        await task
        await asyncio.sleep(2)
    frames = written(mock_bleak_client)
    assert frames[0] == app.frame("back_up")
    assert (
        all(f == app.frame("stop") for f in frames[1:]) if route == "primary" else len(frames) == 1
    )
    await hass.config_entries.async_unload(e.entry_id)


async def test_no_data_parser_edge_uses_native_lane_and_superseded_program_is_fenced(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda controller: controller.perform("one_button_sleep")
        )
        ctrl._state.program_started = -1000
        mock_bleak_client.write_gatt_char.reset_mock()
        for _ in range(19):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        pending = ctrl._followup
        assert pending is not None
        await pending
        assert written(mock_bleak_client) == [frame for _, frame in app.program("rest")] + [
            app.frame("disable_uploads")
        ]
        assert ctrl._state.active_program == "rest"
        # An already queued no-data response cannot end a newly started program.
        mock_bleak_client.write_gatt_char.reset_mock()
        ctrl._state.start("one_button_sleep", 0)
        ctrl._queue_rest(ctrl._link, ctrl._subscription)
        pending = ctrl._followup
        ctrl._state.start("one_button_sleep", 1)
        assert pending is not None
        await pending
        assert written(mock_bleak_client) == []
    await hass.config_entries.async_unload(e.entry_id)


async def test_profile_change_stops_original_session_before_next_refresh(hass, mock_bleak_client):
    c, ctrl = await connected(hass, mock_bleak_client)

    async def write(char, frame, **kwargs):
        if frame == app.frame("back_up"):
            hass.config_entries.async_update_entry(
                c.entry, data={**c.entry.data, const.CONF_PROTOCOL_VARIANT: "4"}
            )

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.hold_control("back_up", 650)
    assert written(mock_bleak_client)[-1] == app.frame("stop")


async def test_frequency_initialization_persists_across_controller_recreation(
    hass, mock_bleak_client
):
    c, ctrl = await connected(hass, mock_bleak_client, prepare=True)
    await c._async_restore_app_state(ctrl)
    with virtual_clock():
        await ctrl.perform("massage_head")
    saved = ctrl.persisted_app_state
    assert saved == {"frequency_prepared": True}
    await c.async_write_app_state(ctrl, saved)
    replacement = bed.SoftideController(c, ctrl.profile)
    await c._async_restore_app_state(replacement)
    c._controller = replacement
    await replacement.async_discover_capabilities()
    await replacement.start_notify()
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await replacement.perform("massage_head")
    assert app.frame("prepare_frequency") not in written(mock_bleak_client)


def test_moon_stops_admitting_new_samples_at_its_program_budget():
    state = SoftideState()
    state.start("one_button_sleep", 0)
    for i in range(96):
        assert not state.feed(codec.SoftideData(hr=62, br=14), "single", 482 + i * 2)
    for i in range(40):
        assert not state.feed(codec.SoftideData(), "single", 1000 + i * 2)
    assert state.moon.shown == 96 and state.moon.zero == 0


@pytest.mark.parametrize("action", ("one_button_sleep", "smart_relaxation"))
async def test_sensor_program_keeps_link_past_idle_window_then_rest_releases_it(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    action,
    mock_async_ble_device_from_address,
):
    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    with virtual_clock(), patch.object(hass, "loop", asyncio.get_running_loop()):
        await c.async_execute_controller_command(lambda ctrl: ctrl.perform(action))
        assert c.controller.requires_persistent_connection
        await asyncio.sleep(600)
        mock_bleak_client.disconnect.assert_not_awaited()
        sender, receive = mock_bleak_client.start_notify.await_args.args
        receive(sender, bytearray(packet(3, Ftype=1, FuncF=0)))
        if action == "smart_relaxation":
            assert c.controller.requires_persistent_connection
            await c.async_execute_controller_command(lambda ctrl: ctrl.perform("rest"))
        assert not c.controller.requires_persistent_connection
        assert c._disconnect_timer is not None
        assert c._disconnect_timer.when() - hass.loop.time() == pytest.approx(40)
        # HA's eager task constructor requires its real loop. Check the virtual
        # deadline here, then drive the real expiry callback without a real wait.
        c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    mock_bleak_client.disconnect.assert_awaited_once()
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("unavailable", ("_softide_disable_uploads", "_softide_program"))
async def test_care_entities_and_dispatch_exclude_unreachable_sensor_stop(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, unavailable
):
    mock_bleak_client.services = gatt()
    e = entry(hass, route="care")
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    entities = [v for v in er.async_get(hass).entities.values() if v.config_entry_id == e.entry_id]
    assert not any(v.unique_id.endswith(unavailable) for v in entities)
    with pytest.raises(ServiceValidationError):
        await c.async_execute_controller_command(lambda ctrl: ctrl.perform("disable_uploads"))
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    await hass.config_entries.async_unload(e.entry_id)


async def test_direct_reports_use_ble_name_and_do_not_require_receiver_time_dvid(
    hass, mock_bleak_client
):
    c, ctrl = await connected(hass, mock_bleak_client)
    sender, receive = mock_bleak_client.start_notify.await_args.args
    receive(sender, bytearray(b'{"code":3,"data":{"FuncF":1,"Tim":6000}}'))
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 2
    c._record_observed_ble_device_name("unrelated bed")
    receive(sender, bytearray(packet(3, FuncF=1, Tim=18000)))
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 2
    c._record_observed_ble_device_name(NAME)
    receive(sender, bytearray(packet(3, device="receiverTime identity", FuncF=1, Tim=18000)))
    assert c.controller_state[MASSAGE_TIMER_MINUTES] == 4
    assert ctrl._state.active_program is None


async def test_replacement_first_write_retires_old_moon_consumer(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    entities = [v for v in er.async_get(hass).entities.values() if v.config_entry_id == e.entry_id]
    entity = next(v for v in entities if v.unique_id.endswith("_softide_smart_relaxation"))
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda controller: controller.perform("one_button_sleep")
        )
        ctrl._state.program_started = -1000
        for _ in range(18):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        assert ctrl._state.moon.shown == 18
        mock_bleak_client.write_gatt_char.reset_mock()
        first_frame = app.program("smart_relaxation")[0][1]
        injected = False
        consumers_at_replacement = []
        await asyncio.sleep(2)

        async def write(char, frame, **kwargs):
            nonlocal injected
            if frame == first_frame and not injected:
                injected = True
                consumers_at_replacement.append(ctrl._state.active_program)
                receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
                for _ in range(10):
                    await asyncio.sleep(0)

        mock_bleak_client.write_gatt_char.side_effect = write
        await hass.services.async_call(
            "button", "press", {"entity_id": entity.entity_id}, blocking=True
        )
        if ctrl._followup is not None:
            await ctrl._followup
        assert injected
        assert consumers_at_replacement == [None]
        assert written(mock_bleak_client) == [frame for _, frame in app.program("smart_relaxation")]
        assert ctrl._state.active_program == "smart_relaxation"
    await hass.config_entries.async_unload(e.entry_id)


async def test_stop_during_program_target_write_never_commits_host_program(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    target_entered, settle = asyncio.Event(), asyncio.Event()
    original_cancel = asyncio.Event()

    async def write(char, frame, **kwargs):
        nonlocal original_cancel
        if frame == app.program("one_button_sleep")[5][1]:
            original_cancel = c.cancel_command
            target_entered.set()
            await settle.wait()

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(
            c.async_execute_controller_command(
                lambda controller: controller.perform("one_button_sleep")
            )
        )
        await target_entered.wait()
        stop = asyncio.create_task(c.async_stop_command())
        await original_cancel.wait()
        settle.set()
        await task
        await stop
        assert ctrl._state.active_program is None
        assert c.controller_state.get(bed.PROGRAM) is None
        assert not ctrl.requires_persistent_connection
        frames = written(mock_bleak_client)
        assert frames[-1] == app.frame("stop")
        for _ in range(19):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        assert ctrl._followup is None
        assert written(mock_bleak_client) == frames
    await hass.config_entries.async_unload(e.entry_id)


async def test_automatic_rest_waits_for_user_lane_and_rechecks_program_ownership(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    entered, finish = asyncio.Event(), asyncio.Event()
    running_cancel = asyncio.Event()

    async def write(char, frame, **kwargs):
        nonlocal running_cancel
        if frame == app.frame("query"):
            running_cancel = c.cancel_command
            entered.set()
            await finish.wait()

    async def user(controller):
        await controller.perform("query")
        await controller.perform("smart_relaxation")

    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        ctrl._state.start("one_button_sleep", 0)
        task = asyncio.create_task(c.async_execute_controller_command(user))
        await entered.wait()
        ctrl._queue_rest(ctrl._link, ctrl._subscription)
        pending = ctrl._followup
        for _ in range(10):
            await asyncio.sleep(0)
        assert c.command_scheduler.has_pending
        assert not running_cancel.is_set()
        finish.set()
        await task
        assert pending is not None
        await pending
        assert written(mock_bleak_client) == [app.frame("query")] + [
            frame for _, frame in app.program("smart_relaxation")
        ]
        assert ctrl._state.active_program == "smart_relaxation"
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("gap", ("ble_lock", "await"))
@pytest.mark.parametrize("change", ("moon_ended", "ble_name"))
async def test_automatic_rest_rechecks_before_first_ble_write(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
    gap,
    change,
):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    reached, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda controller: controller.perform("one_button_sleep")
        )
        ctrl._state.program_started = -1000
        for _ in range(18):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        await asyncio.sleep(2)
        mock_bleak_client.write_gatt_char.reset_mock()
        sleep = asyncio.sleep
        paused = False

        async def pause(delay, *args, **kwargs):
            nonlocal paused
            if (
                gap == "await"
                and delay == 0
                and current_command_context() is not None
                and not paused
            ):
                paused = True
                reached.set()
                await resume.wait()
            await sleep(delay, *args, **kwargs)

        if gap == "ble_lock":
            await ctrl._ble_lock.acquire()
        with patch.object(asyncio, "sleep", pause):
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
            pending = ctrl._followup
            assert pending is not None
            if gap == "await":
                await reached.wait()
            else:
                for _ in range(50):
                    if ctrl._ble_lock._waiters:
                        break
                    await sleep(0)
                assert ctrl._ble_lock._waiters
            assert c.command_scheduler.active is not None
            if change == "moon_ended":
                receive(sender, bytearray(packet(3, Ftype=1, FuncF=0)))
            else:
                c._record_observed_ble_device_name("other receiver")
            if gap == "ble_lock":
                ctrl._ble_lock.release()
            resume.set()
            await pending
        assert written(mock_bleak_client) == []
        assert ctrl._state.active_program != "rest"
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("after", range(1, 8))
async def test_automatic_rest_guards_every_remaining_frame_after_claim(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
    after,
):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    reached, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda controller: controller.perform("one_button_sleep")
        )
        ctrl._state.program_started = -1000
        for _ in range(18):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        await asyncio.sleep(2)
        mock_bleak_client.write_gatt_char.reset_mock()
        sleep = asyncio.sleep
        paused = False

        async def pause(delay, *args, **kwargs):
            nonlocal paused
            if (
                current_command_context() is not None
                and len(written(mock_bleak_client)) == after
                and delay == app.REQUEST_DELAY_MS / 1000
                and not paused
            ):
                paused = True
                reached.set()
                await resume.wait()
            await sleep(delay, *args, **kwargs)

        with patch.object(asyncio, "sleep", pause):
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
            pending = ctrl._followup
            assert pending is not None
            await reached.wait()
            c._record_observed_ble_device_name("other receiver")
            resume.set()
            await pending
        # Submitted writes settle; only original-session STOP cleanup may follow.
        assert written(mock_bleak_client) == [frame for _, frame in app.program("rest")][:after] + [
            app.frame("stop")
        ]
        assert ctrl._state.active_program is None
        assert c.controller_state.get(bed.PROGRAM) is None
    await hass.config_entries.async_unload(e.entry_id)


async def test_automatic_disable_rechecks_claim_after_waiting_for_ble_lock(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
):
    from custom_components.adjustable_bed.command_scheduler import current_command_context

    mock_async_ble_device_from_address.return_value.name = NAME
    mock_bleak_client.services = gatt()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    c = hass.data[const.DOMAIN][e.entry_id]
    ctrl = c.controller
    sender, receive = mock_bleak_client.start_notify.await_args.args
    reached, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda controller: controller.perform("one_button_sleep")
        )
        ctrl._state.program_started = -1000
        for _ in range(18):
            await asyncio.sleep(2)
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
        await asyncio.sleep(2)
        mock_bleak_client.write_gatt_char.reset_mock()
        sleep = asyncio.sleep
        paused = False

        async def pause(delay, *args, **kwargs):
            nonlocal paused
            if (
                current_command_context() is not None
                and len(written(mock_bleak_client)) == 7
                and delay == app.REQUEST_DELAY_MS / 1000
                and not paused
            ):
                paused = True
                reached.set()
                await resume.wait()
            await sleep(delay, *args, **kwargs)

        with patch.object(asyncio, "sleep", pause):
            receive(sender, bytearray(packet(hr=0, br=0, lb=1)))
            pending = ctrl._followup
            assert pending is not None
            await reached.wait()
            await ctrl._ble_lock.acquire()
            resume.set()
            try:
                await sleep(0.02)
                for _ in range(50):
                    if ctrl._ble_lock._waiters:
                        break
                    await sleep(0)
                assert ctrl._ble_lock._waiters
                assert ctrl._state.active_program == "rest"
                c._record_observed_ble_device_name("other receiver")
            finally:
                ctrl._ble_lock.release()
            await pending
        assert written(mock_bleak_client) == [frame for _, frame in app.program("rest")]
    await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("suffix,response", (("", True), (":no_response", False)))
async def test_actual_wire_scenario_overrides_b002_without_changing_notify(
    monkeypatch, suffix, response
):
    tool = _tool()
    original = tool.capture_scenario
    scenario_id = "softide" if response else "softide:3:primary" + suffix
    observed = []

    async def capture(scenario, layout, frozen):
        client = tool.FakeClient(tool.Recorder(tool.FakeClock()), layout, scenario.replies)
        link = bed.select_link(client, 0)
        observed.append((link.write.properties, link.notify.properties, link.response))
        return await original(scenario, layout, frozen)

    monkeypatch.setattr(tool, "capture_scenario", capture)
    snapshot = await tool.capture_all([scenario_id])
    assert len(observed) == 1
    write_properties, notify_properties, selected_response = observed[0]
    assert write_properties == (["write"] if response else ["write-without-response"])
    assert notify_properties == ["notify"]
    assert selected_response is response
    row = snapshot["scenarios"][scenario_id]
    assert not row.get("gaps") and not row.get("connect_error")
    frames = [
        write
        for command in row["commands"].values()
        for write in command.get("writes", ())
        if type(write[2]) is bool
    ]
    assert frames and all(write[1] == app.WRITE and write[2] is response for write in frames)
