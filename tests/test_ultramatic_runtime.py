"""Row176 through real setup/factory/entity/service and coordinator admission."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from datetime import datetime
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.ultramatic import controller as module
from custom_components.adjustable_bed.beds.ultramatic import services as app_services
from custom_components.adjustable_bed.beds.ultramatic.controller import UltramaticController
from custom_components.adjustable_bed.beds.ultramatic.state import SIDES
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _configure_questions,
    _motor_count_options,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ULTRAMATIC_SMART_BED as BED,
)
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROFILE_ID,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import (
    detect_bed_type_detailed,
    get_bed_type_options,
)
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
)
from custom_components.adjustable_bed.pairing import (
    build_single_address_pair_entry_data,
    iter_children,
)
from custom_components.adjustable_bed.profile_id import entry_profile_id
from custom_components.adjustable_bed.profiles import ultramatic as app
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from custom_components.adjustable_bed.services import async_register_services
from tests.form_helpers import NEW_BED_ROUTES, form_fields, start_new_bed
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_detection import _make_service_info

ADDRESS = "AA:BB:CC:DD:EE:76"
ALARM_REPORT = bytes.fromhex("ed8003017f010630000102020322450000")
MASSAGE_REPORT = bytes.fromhex("a50b0e010258030201000204b001030200")


def make_client(*, indicate=False):
    write = MagicMock(
        uuid=app.WRITE_UUID, properties=["write-without-response"], handle=1, descriptors=[]
    )
    notify = MagicMock(
        uuid=app.NOTIFY_UUID,
        properties=["indicate" if indicate else "notify"],
        handle=2,
        descriptors=[],
    )
    client = MagicMock()
    client.is_connected = True
    client.services = [SimpleNamespace(uuid=app.SERVICE_UUID, characteristics=[write, notify])]
    client.start_notify, client.stop_notify, client.write_gatt_char = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


def writes(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


def entry(hass, address=ADDRESS, selector=0):
    item = MockConfigEntry(
        domain=DOMAIN,
        title="Ultramatic",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Ultramatic",
            CONF_BED_TYPE: BED,
            CONF_CB24_BED_SELECTION: selector,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_MOTOR_PULSE_COUNT: 3,
            CONF_MOTOR_PULSE_DELAY_MS: 300,
        },
    )
    item.add_to_hass(hass)
    return item


async def connected(hass, *, address=ADDRESS, selector=0):
    coordinator = AdjustableBedCoordinator(hass, entry(hass, address, selector))
    client = make_client()
    coordinator._client = client
    coordinator._controller = await create_controller(coordinator, BED, "auto", client)
    await coordinator.controller.async_discover_capabilities()
    await coordinator.controller.start_notify()
    return coordinator, client


@pytest.fixture
async def runtime(hass):
    coordinator, client = await connected(hass)
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield hass, coordinator, client
    await coordinator.async_shutdown()


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_new_install_routes_ask_and_persist_exact_selector(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="smartbed-176", service_uuids=[])
    flow._async_transport_note = AsyncMock(return_value="")
    form = await start_new_bed(flow, route, BED)
    assert form["step_id"] == "profile_questions"
    assert CONF_CB24_BED_SELECTION in {m.schema for m in form_fields(form["data_schema"])}
    result = await flow.async_step_profile_questions({CONF_CB24_BED_SELECTION: 2})
    assert result["step_id"] == "finish_settings"
    fields = {m.schema for m in form_fields(result["data_schema"])}
    assert not {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_MOTOR_PULSE_DELAY_MS} & fields
    assert _motor_count_options(BED) == [2]
    assert flow._manual_data[CONF_CB24_BED_SELECTION] == 2


async def test_restore_factory_and_configure_keep_profile_and_app_owned_side_fields(hass):
    item = entry(hass, selector=1)
    await async_migrate_entry(hass, item)
    assert item.data[CONF_PROFILE_ID] == BED
    coord = _FactoryCoordinator()
    coord.entry = item
    controller = await create_controller(coord, entry_profile_id(item.data), "auto", None)
    assert isinstance(controller, UltramaticController)
    assert controller._side() == "A"
    assert controller.profile is app.PROFILE
    assert len(controller.motor_control_specs) == 5
    assert not controller.position_number_specs
    assert len(controller.controller_state_sensor_specs) == 6
    questions = _configure_questions(item.data)
    assert questions is not None
    assert [q.key for q in questions.questions] == [CONF_CB24_BED_SELECTION]
    assert questions.staged(item.data, {CONF_CB24_BED_SELECTION: 2})[CONF_CB24_BED_SELECTION] == 2
    assert CONF_CB24_BED_SELECTION in per_side_profile(BED, None).keys
    options = [row for row in get_bed_type_options() if row["value"] == BED]
    assert len(options) == 1 and "com.okin.ultramaticSmartBed" in options[0]["label"]


def test_scan_requires_platform_name_and_first_manufacturer_value():
    for name, data, accepted in (
        ("SmArTbEd176", {123: bytes.fromhex("444f540105ff")}, True),
        ("smartbed176", {123: b"bad", 456: bytes.fromhex("444f540105")}, False),
        ("other176", {123: bytes.fromhex("444f540105")}, False),
        ("smartbed176", {}, False),
    ):
        info = _make_service_info(name=name, service_uuids=[], manufacturer_data=data)
        result = detect_bed_type_detailed(info)
        assert (BED in {result.bed_type, *(result.ambiguous_types or ())}) is accepted


def test_single_address_pair_uses_one_and_two_without_importing_cb24_wire_values():
    data = build_single_address_pair_entry_data(
        {CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: BED, CONF_CB24_BED_SELECTION: 0},
        name="Ultramatic sides",
    )
    assert [child[CONF_CB24_BED_SELECTION] for child in iter_children(data)] == [1, 2]


async def test_actual_cover_and_button_publish_native_hold_and_card_metadata(runtime):
    hass, coord, client = runtime
    c = coord.controller
    spec = next(s for s in c.motor_control_specs if s.key == "lumbar")
    cover = AdjustableBedCover(coord, _build_cover_description(spec))
    cover.hass, cover.async_write_ha_state = hass, MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    assert writes(client) == [app.control("LUMBARUP")] * 3 + [app.control("STOP")]
    attrs = cover.extra_state_attributes
    assert attrs["held_control_up"] == "LUMBARUP"
    assert attrs["held_stop_scope"] == "side" and attrs["hold_lease_mode"] == "stream"
    button = ControllerActionButton(
        coord, next(s for s in c.controller_button_specs if s.key == "ultramatic_light")
    )
    button.hass = hass
    with virtual_clock():
        await button.async_press()
    assert writes(client)[-2:] == [app.control("LIGHT"), app.control("STOP")]


async def test_slow_write_finite_hold_has_deadline_and_no_backfill(runtime):
    hass, _, client = runtime
    at = []
    with virtual_clock() as clock:

        async def slow(_char, frame, **_kwargs):
            at.append((clock.elapsed, frame))
            await asyncio.sleep(0.4)

        client.write_gatt_char.side_effect = slow
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": ["bed"], "control": "HEADUP", "duration": 0.65},
            blocking=True,
        )
    assert [round(t, 3) for t, frame in at if frame != app.control("STOP")] == [0]
    assert writes(client)[-1] == app.control("STOP")


async def test_card_lease_renews_stream_and_stop_ends_generation(runtime):
    hass, coord, client = runtime
    call = {
        "device_id": ["bed"],
        "control": "HEADUP",
        "duration": 0.5,
        "hold_owner": "ultramatic-card",
        "hold_generation": 7,
    }
    with virtual_clock():
        task = asyncio.create_task(
            hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
        )
        await asyncio.sleep(0.2)
        before = len(writes(client))
        await hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
        assert len(writes(client)) == before
        await asyncio.sleep(0.2)
        await coord.async_stop_command()
        await task
        count = len(writes(client))
        with pytest.raises(ServiceValidationError, match="has ended"):
            await hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
        assert len(writes(client)) == count
    first_stop = writes(client).index(app.control("STOP"))
    assert all(frame == app.control("STOP") for frame in writes(client)[first_stop:])


@pytest.mark.parametrize("action", module.MASSAGE)
async def test_every_massage_button_writes_once_then_three_queries(runtime, action):
    _, coord, client = runtime
    with virtual_clock() as clock:
        at = []

        async def record(_char, data, **_kwargs):
            at.append(round(clock.elapsed * 1000))

        client.write_gatt_char.side_effect = record
        spec = next(
            s for s in coord.controller.controller_button_specs if s.key == f"ultramatic_{action}"
        )
        await coord.async_execute_controller_command(spec.press_fn, resource="*")
    assert writes(client) == [app.control(action)] + [app.QUERY_MASSAGE] * 3
    assert at == [0, 300, 600, 900]


@pytest.mark.parametrize("preset", module.SAVE_PRESETS)
async def test_save_buttons_use_same_recall_frame_and_six_second_deadline(runtime, preset):
    _, coord, client = runtime
    with virtual_clock():
        if preset in ("M1", "M2"):  # Saved by the generic "Save to Memory" buttons.
            press_fn = partial(type(coord.controller).program_memory, memory_num=int(preset[1]))
        else:
            spec = next(
                s
                for s in coord.controller.controller_button_specs
                if s.key == f"ultramatic_save_{preset.lower()}"
            )
            assert spec.requires_confirmation
            press_fn = spec.press_fn
        await coord.async_execute_controller_command(press_fn, resource="*")
    assert writes(client) == [app.control(preset)] * 20 + [app.control("STOP")]


async def test_reset_is_fixed_combination_and_global_stop_on_a_side(runtime):
    _, coord, client = runtime
    c = coord.controller
    with c.side_scope("right"), virtual_clock():
        await c.reset_memory()
    assert writes(client) == [bytes.fromhex("05020800100002")] * 20 + [app.control("STOP")]


async def test_alarm_service_correct_byte_order_and_mutable_buffer_schedule(runtime):
    hass, coord, client = runtime
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "ultramatic_alarm",
            {
                "device_id": ["bed"],
                "operation": "set",
                "time": "21:09:00",
                "days": 2,
                "wake": "zero_g",
                "enabled": False,
            },
            blocking=True,
        )
    assert writes(client) == [bytes.fromhex("070502022109000000")] * 2 + [app.QUERY_ALARM] * 3
    assert coord.controller_state[SIDES["AB"].alarm] is None
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.await_args_list)


@pytest.mark.parametrize(
    "fields",
    [
        {"operation": "set", "time": "06:30:00"},
        {"operation": "set", "time": "06:30:01", "days": 127, "wake": "vibrate", "enabled": True},
        {"operation": "query", "days": 127},
        {"operation": "toggle"},
    ],
)
async def test_alarm_invalid_fields_or_missing_current_report_write_nothing(runtime, fields):
    hass, _, client = runtime
    with pytest.raises((ServiceValidationError, ValueError, ConnectionError)):
        await hass.services.async_call(
            DOMAIN, "ultramatic_alarm", {"device_id": ["bed"], **fields}, blocking=True
        )
    assert writes(client) == []


async def test_all_target_capability_and_alarm_state_before_any_writes(runtime):
    hass, coord, client = runtime
    invalid = MagicMock(spec=AdjustableBedCoordinator)
    invalid.capability_controller = MagicMock()
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coord, "both"), (invalid, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="Every target"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "ultramatic_alarm",
            {
                "device_id": ["bed", "other"],
                "operation": "set",
                "time": "06:30:00",
                "days": 127,
                "wake": "memory_1",
                "enabled": True,
            },
            blocking=True,
        )
    assert not writes(client)


async def test_reported_sensor_and_toggle_are_fenced_on_disconnect(runtime):
    hass, coord, client = runtime
    c = coord.controller
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray(ALARM_REPORT))
    callback(None, bytearray(MASSAGE_REPORT))
    spec = next(s for s in c.controller_state_sensor_specs if s.state_key == SIDES["A"].timer)
    sensor = AdjustableBedControllerStateSensor(coord, spec)
    assert sensor.native_value == 10
    assert sensor.extra_state_attributes[SIDES["A"].head] == 2
    with c.side_scope("left"), virtual_clock():
        plan = c.prepare_alarm(None, toggle=True)
        assert plan.frame == bytes.fromhex("07057f010630000001")
        await c.set_alarm(plan)
    client.write_gatt_char.reset_mock()
    c.on_disconnect()
    callback(None, bytearray(ALARM_REPORT))
    assert coord.controller_state[SIDES["A"].alarm] is None
    assert sensor.native_value is None
    with pytest.raises(ConnectionError):
        c.prepare_alarm(None, toggle=True)
    assert writes(client) == []


async def test_queued_write_and_release_cannot_cross_replacement_session(runtime):
    _, coord, client = runtime
    c = coord.controller
    old = c.session_token
    async with c.ble_lock:
        task = asyncio.create_task(c._write(old, app.control("HEADUP"), asyncio.Event()))
        await asyncio.sleep(0)
        c.on_disconnect()
    with pytest.raises(ConnectionError):
        await task
    await c.async_discover_capabilities()
    with virtual_clock():
        await c._release(old)
    assert writes(client) == []


async def test_caller_cancellation_drains_captured_delayed_stop(runtime):
    _, coord, client = runtime
    c = coord.controller
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("HEADUP", 6000))
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert writes(client) == [app.control("HEADUP"), app.control("STOP")]


async def test_startup_captures_clock_then_replaced_query_and_restarts_parser(runtime):
    _, coord, client = runtime
    c = coord.controller
    session = SimpleNamespace(async_start_notify=AsyncMock(side_effect=c.start_notify))
    with (
        patch.object(module.dt_util, "now", return_value=datetime(2026, 11, 17, 6, 5, 9)),
        virtual_clock(),
    ):
        await c.async_on_connect(session)
    assert writes(client) == [
        bytes.fromhex("070426111702060509"),
        app.QUERY_MASSAGE,
        app.QUERY_MASSAGE,
    ]
    c._parser.feed(bytes.fromhex("00fe16") + bytes(17))
    callback = client.start_notify.await_args.args[1]
    c.on_disconnect()
    await c.async_discover_capabilities()
    await c.start_notify()
    callback(None, bytearray(MASSAGE_REPORT))
    assert coord.controller_state[SIDES["A"].timer] is None
    client.start_notify.await_args.args[1](None, bytearray(MASSAGE_REPORT))
    assert coord.controller_state[SIDES["A"].timer] == 10


@pytest.mark.parametrize("indicate", [False, True])
async def test_exact_gatt_properties_notify_retry_and_no_device_info_read(hass, indicate):
    coord = AdjustableBedCoordinator(hass, entry(hass))
    client = make_client(indicate=indicate)
    coord._client = client
    c = UltramaticController(coord)
    coord._controller = c
    await c.async_discover_capabilities()
    client.start_notify.side_effect = [TimeoutError(), None]
    with virtual_clock():
        await c.start_notify()
    assert client.start_notify.await_count == 2
    assert await c.async_read_device_info(MagicMock()) is True
    client.read_gatt_char.assert_not_called()
    c.on_disconnect()
    client.services[0].characteristics[0].properties = ["write"]
    with pytest.raises(ValueError, match="without-response"):
        await c.async_discover_capabilities()
    await coord.async_shutdown()


async def test_actual_configure_persists_selector_and_rebuilds_factory(hass):
    item = entry(hass, selector=1)
    flow = AdjustableBedOptionsFlow(item)
    flow.hass, flow.handler = hass, item.entry_id
    with patch(
        "custom_components.adjustable_bed.config_flow.get_available_adapters", return_value={}
    ):
        form = await flow.async_step_settings()
        assert CONF_CB24_BED_SELECTION in {m.schema for m in form_fields(form["data_schema"])}
        result = await flow.async_step_settings({CONF_CB24_BED_SELECTION: 2})
    assert result["type"] == "create_entry"
    assert item.data[CONF_CB24_BED_SELECTION] == 2
    coord = _FactoryCoordinator()
    coord.entry = item
    controller = await create_controller(coord, entry_profile_id(item.data), "auto", None)
    assert controller._side() == "B"


async def test_single_address_children_route_exact_side_with_global_release(runtime):
    hass, inner, client = runtime
    pair_data = build_single_address_pair_entry_data(
        dict(inner.entry.data), name="Ultramatic sides"
    )
    pair_entry = MockConfigEntry(domain=DOMAIN, data=pair_data)
    pair_entry.add_to_hass(hass)
    pair = SingleAddressPairedCoordinator(hass, pair_entry, inner)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ),
        virtual_clock(),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": ["right"], "control": "HEADTILTUP", "duration": 0.45},
            blocking=True,
        )
    assert writes(client) == [app.control("HEADTILTUP", "B")] * 2 + [app.control("STOP")]


async def test_two_address_pair_preserves_physical_selectors_and_rejects_sequential_both_lease(
    runtime,
):
    hass, left, left_client = runtime
    right, right_client = await connected(hass, address="AA:BB:CC:DD:EE:77", selector=2)
    pair_entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "ultramatic-two"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, pair_entry, {"left": left, "right": right}, connection_mode="sequential"
    )
    try:
        with (
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "_async_refresh_controller_auth", AsyncMock()),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "both")], []),
            ),
            virtual_clock(),
        ):
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(
                    DOMAIN,
                    "hold_control",
                    {
                        "device_id": ["pair"],
                        "control": "HEADUP",
                        "duration": 0.5,
                        "hold_owner": "card",
                        "hold_generation": 1,
                    },
                    blocking=True,
                )
            assert not writes(left_client) and not writes(right_client)
        with (
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "_async_refresh_controller_auth", AsyncMock()),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "right")], []),
            ),
            virtual_clock(),
        ):
            await hass.services.async_call(
                DOMAIN,
                "ultramatic_alarm",
                {
                    "device_id": ["right"],
                    "operation": "set",
                    "time": "23:59:00",
                    "days": 255,
                    "wake": "memory_1",
                    "enabled": True,
                },
                blocking=True,
            )
        assert not writes(left_client)
        assert (
            writes(right_client)
            == [bytes.fromhex("0705ff032359000102")] * 2 + [app.QUERY_ALARM] * 3
        )
    finally:
        await right.async_shutdown()


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_real_connection_reconnect_runs_owned_startup_and_no_generic_reads(
    hass, mock_bleak_client
):
    roles = make_client().services
    mock_bleak_client.services.__iter__ = lambda _self: iter(roles)
    mock_bleak_client.services.__len__ = lambda _self: len(roles)
    coord = AdjustableBedCoordinator(hass, entry(hass))
    coord._max_retries = 1
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
            new_callable=AsyncMock,
        ) as reads,
        virtual_clock(),
    ):
        assert await coord.async_connect()
        assert isinstance(coord.controller, UltramaticController)
        first = writes(mock_bleak_client)
        assert len(first) == 3 and first[1:] == [app.QUERY_MASSAGE] * 2
        reads.assert_not_awaited()
        old = coord.controller.session_token
        await coord.async_disconnect()
        assert await coord.async_connect()
        assert coord.controller.session_token is not old
        assert writes(mock_bleak_client)[len(first) :][1:] == [app.QUERY_MASSAGE] * 2
        await coord.async_shutdown()


@pytest.mark.parametrize("change", ["stop", "command", "replacement", "reconnect"])
async def test_alarm_admission_rejects_changes_during_live_preflight(runtime, change):
    hass, coord, client = runtime
    original = app_services._preflight_capability

    async def interleave(*args, **kwargs):
        result = await original(*args, **kwargs)
        c = coord.controller
        if change == "stop":
            coord._command_scheduler.finish_stop(coord._command_scheduler.request_stop())
        elif change == "command":
            c._operation_generation += 1
        elif change == "replacement":
            coord._controller = UltramaticController(coord)
        else:
            c.on_disconnect()
            await c.async_discover_capabilities()
        return result

    with (
        patch.object(app_services, "_preflight_capability", side_effect=interleave),
        virtual_clock(),
    ):
        try:
            await hass.services.async_call(
                DOMAIN,
                "ultramatic_alarm",
                {
                    "device_id": ["bed"],
                    "operation": "set",
                    "time": "06:30:00",
                    "days": 127,
                    "wake": "vibrate",
                    "enabled": True,
                },
                blocking=True,
            )
        except ServiceValidationError, ConnectionError:
            pass
    assert writes(client) == []


async def test_invalid_report_is_visible_but_not_writable(runtime):
    _, coord, client = runtime
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("a50c0e0001021a2f00010000000000000000"))
    assert coord.controller_state[SIDES["AB"].alarm] == "20:35"
    with pytest.raises(ValueError, match="Refresh alarms"):
        coord.controller.prepare_alarm(None, toggle=True)
    assert writes(client) == []


async def test_second_cancellation_during_stop_still_drains_cleanup(runtime):
    _, coord, client = runtime
    with virtual_clock():

        async def slow_stop(_char, data, **_kwargs):
            if data == app.control("STOP"):
                await asyncio.sleep(0.2)

        client.write_gatt_char.side_effect = slow_stop
        task = asyncio.create_task(coord.controller.hold_control("FOOTDOWN", 6000))
        await asyncio.sleep(0.15)
        task.cancel()
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert writes(client) == [app.control("FOOTDOWN"), app.control("STOP")]
