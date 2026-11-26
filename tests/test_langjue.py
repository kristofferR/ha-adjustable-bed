"""Frozen P1 frames and Langjue Home Assistant admission and STOP behavior."""

from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack, ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds import langjue as runtime
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import langjue as codec
from custom_components.adjustable_bed.codec.langjue import Op
from custom_components.adjustable_bed.command_scheduler import HoldLease
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_LANGJUE,
    BED_TYPE_LIMOSS_REMOTE,
    CONF_BED_TYPE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_ID,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
    PairedSideProxy,
)
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from custom_components.adjustable_bed.profiles import langjue as app
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.state_keys import (
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    massage_intensity,
)
from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
from tests.form_helpers import NEW_BED_ROUTES, form_fields, options_of, start_new_bed, suggested
from tests.hold_lease_wire import virtual_clock
from tests.test_config_flow import _patch_gate
from tests.test_detection import _make_service_info

VECTORS = json.loads((Path(__file__).parent / "fixtures/langjue_vectors.json").read_text())
WIRE = {row["id"]: bytes.fromhex(row["bytes"]) for row in VECTORS["writes"]}
ADDRESS = "AA:BB:CC:DD:EE:76"
ALARM = bytes.fromhex("5500000032080001010300080000")


def test_frozen_writes():
    actual = (
        codec.handshake(),
        codec.frame(Op.VERSION),
        codec.frame(Op.READ_LIGHT, 8),
        codec.motion(2, 0, up=True),
        codec.motion(2, 0),
        codec.motion(2, 1, up=True),
        codec.motion(2, 1),
        codec.motion(2),
        codec.preset(app.PRESETS["flat"]),
        codec.preset(app.PRESETS["zero_g"]),
        codec.preset(app.MEMORY_MODES[0]),
        codec.preset(app.MEMORY_MODES[2], save=True),
        codec.light(True),
        codec.light(False),
        codec.massage_level(1, 1),
        codec.frame(Op.READ_ALARM, 1, b"\x00"),
        codec.clock(datetime(2026, 1, 2, 7, 8, 9)),
        codec.alarm(app.ALARM_ACTIONS["flat"], (), 8, 0),
        codec.alarm(app.ALARM_ACTIONS["zero_g"], (0, 6), 6, 30),
        codec.frame(Op.MASSAGE_TIMER, 2, bytes((0, app.MASSAGE_TIMERS[20]))),
        codec.frame(Op.MASSAGE_PATTERN, 2, b"\x00\x04"),
    )
    assert actual == tuple(WIRE.values())
    assert codec.preset(app.PRESETS["anti_snore"]) == bytes.fromhex("55040000020104")


def make_client(count=2, *, alarm=ALARM, writer_props=("write", "write-without-response")):
    # Synthetic IDs deliberately differ from the service and from each other.
    writer = SimpleNamespace(
        uuid="00000001-0000-0000-0000-000000000000",
        handle=1,
        properties=writer_props,
        max_write_without_response_size=20,
    )
    notify = SimpleNamespace(
        uuid="00000002-0000-0000-0000-000000000000",
        handle=2,
        properties=["notify"],
    )
    service = SimpleNamespace(uuid=app.SERVICE.upper(), characteristics=[writer, notify])
    client = MagicMock(is_connected=True, services=[service])
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    replies = {
        WIRE["P1-W01"]: bytes.fromhex("550000008101") + bytes((count,)),
        WIRE["P1-W02"]: bytes.fromhex("550000008200"),
        bytes.fromhex("550000008300"): bytes.fromhex("550000008300"),
        WIRE["P1-W03"]: bytes.fromhex(VECTORS["notifications"][2]["bytes"]),
        WIRE["P1-W16"]: alarm,
    }

    async def write(char, frame, *, response):
        assert char is writer
        if frame in replies and (reply := replies[frame]) is not None:
            client.start_notify.await_args.args[1](notify, bytearray(reply))

    client.write_gatt_char = AsyncMock(side_effect=write)

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


def writes(client):
    return [
        (call.args[1], call.kwargs["response"]) for call in client.write_gatt_char.await_args_list
    ]


async def make_controller(hass, client, *, address=ADDRESS, **config):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BED_TYPE: BED_TYPE_LANGJUE, CONF_ADDRESS: address, **config},
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client
    controller = await create_controller(coordinator, BED_TYPE_LANGJUE, "auto", client)
    assert isinstance(controller, runtime.LangjueController)
    coordinator._controller = controller
    return coordinator, controller


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_manual_setup_confirms_direction_and_features(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="Other Smart device")
    flow._async_transport_note = AsyncMock(return_value="")
    form = await start_new_bed(flow, route, BED_TYPE_LANGJUE)
    assert form["step_id"] == "profile_questions"
    assert set(options_of(form_fields(form["data_schema"])[CONF_PRODUCT_TYPE])) == {
        app.PRESETS_ONLY,
        app.HEAD_FOOT,
    }
    form = await flow.async_step_profile_questions(
        {
            CONF_PRODUCT_TYPE: app.HEAD_FOOT,
            CONF_HAS_LIGHT: True,
            CONF_HAS_MASSAGE: True,
        }
    )
    assert form["step_id"] == "finish_settings"
    assert (
        not {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_HAS_LIGHT}
        & form_fields(form["data_schema"]).keys()
    )
    assert flow._manual_data[CONF_PRODUCT_TYPE] == app.HEAD_FOOT
    assert flow._manual_data[CONF_HAS_LIGHT] is True and flow._manual_data[CONF_HAS_MASSAGE] is True
    assert (
        detect_bed_type_detailed(_make_service_info(name="Other Smart device")).bed_type
        != BED_TYPE_LANGJUE
    )


async def test_session_sequence_and_corrected_notifications(hass):
    client = make_client()
    coord, ctrl = await make_controller(hass, client, has_light=True, has_massage=True)
    with virtual_clock():
        await ctrl.start_notify()
    assert writes(client) == [
        (WIRE["P1-W01"], True),
        (WIRE["P1-W02"], True),
        (bytes.fromhex("550000008300"), True),
        (WIRE["P1-W03"], True),
    ]
    assert coord.controller_state[UNDER_BED_LIGHTS_ON] is False

    sender, emit = client.start_notify.await_args.args
    fixtures = VECTORS["notifications"]
    emit(sender, bytearray.fromhex(fixtures[3]["bytes"]))
    assert coord.controller_state[massage_intensity("head")] == 3
    assert massage_intensity("foot") not in coord.controller_state
    emit(sender, bytearray.fromhex(fixtures[4]["bytes"]))
    assert coord.controller_state[massage_intensity("head")] == 3
    assert coord.controller_state[massage_intensity("foot")] == 3
    emit(sender, bytearray.fromhex("55000000280101"))  # Missing zone level.
    emit(sender, bytearray.fromhex(fixtures[5]["bytes"]))
    emit(sender, bytearray.fromhex(fixtures[6]["bytes"]))
    assert coord.controller_state[massage_intensity("foot")] == 3
    assert coord.controller_state[MASSAGE_TIMER_MINUTES] == 10
    assert ctrl.protocol_diagnostics["massage_status_code"] == 3
    assert not ctrl.controller_state_sensor_specs
    refresh = next(
        spec for spec in ctrl.controller_button_specs if spec.key == "langjue_massage_refresh"
    )
    assert refresh.diagnostic
    assert not ControllerActionButton(coord, refresh).entity_registry_enabled_default
    await ctrl.stop_notify()
    emit(sender, bytearray.fromhex(fixtures[3]["bytes"]))
    emit(sender, bytearray.fromhex(fixtures[6]["bytes"]))
    assert "massage_status_code" not in ctrl.protocol_diagnostics
    assert coord.controller_state.get(massage_intensity("head")) is None
    assert coord.controller_state.get(UNDER_BED_LIGHTS_ON) is None


@pytest.mark.parametrize("case", ["no-quick", "two-writers", "wrong-service"])
async def test_ambiguous_gatt_roles_fail_before_any_io(hass, case):
    client = make_client(
        writer_props=("write",) if case == "no-quick" else ("write", "write-without-response")
    )
    service = client.services[0]
    if case == "two-writers":
        service.characteristics.append(SimpleNamespace(properties=["write"]))
    elif case == "wrong-service":
        service.uuid = "c8cc3a71-2e52-4ce7-839e-774ed9703535"
    _, ctrl = await make_controller(hass, client)
    with pytest.raises(ConnectionError):
        await ctrl.start_notify()
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(("count", "confirmed"), [(2, False), (3, True), (0x0A, True)])
async def test_direction_and_stop_require_the_right_live_count(hass, count, confirmed):
    client = make_client(count)
    _, ctrl = await make_controller(
        hass, client, product_type=app.HEAD_FOOT if confirmed else app.PRESETS_ONLY
    )
    with virtual_clock():
        await ctrl.start_notify()
    client.write_gatt_char.reset_mock()
    assert bool(ctrl.motor_control_specs) is confirmed
    with pytest.raises((ValueError, ConnectionError)):
        await ctrl.move_back_up()
    assert writes(client) == []
    if count == 0x0A:
        with pytest.raises(ConnectionError, match="motor count"):
            await ctrl.preset_anti_snore()
        with pytest.raises(ConnectionError, match="motor count"):
            await ctrl.stop_all()
        assert writes(client) == []
    else:
        await ctrl.preset_anti_snore()
        await ctrl.stop_all()
        expected_stop = WIRE["P1-W08"] if count == 2 else bytes.fromhex("558903000101838383")
        assert writes(client) == [(bytes.fromhex("55040000020104"), False), (expected_stop, False)]


@pytest.mark.parametrize("replace_link", [False, True])
@pytest.mark.parametrize("operation", ["hold", "flat"])
async def test_cancelled_write_settles_before_stop(hass, replace_link, operation):
    client = make_client()
    coord, ctrl = await make_controller(hass, client, product_type=app.HEAD_FOOT)
    replacement = make_client()
    with virtual_clock():
        await ctrl.start_notify()
    client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    settled = asyncio.Event()
    first_frame = WIRE["P1-W04"] if operation == "hold" else WIRE["P1-W09"]

    async def write(char, frame, *, response):
        if frame == first_frame:
            entered.set()
            await settled.wait()
        else:
            assert settled.is_set()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        ctrl.hold_control("back_up", 5000) if operation == "hold" else ctrl.preset_flat()
    )
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert writes(client) == [(first_frame, False)]
    if replace_link:
        coord._client = replacement
    settled.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    expected = [(first_frame, False)]
    if not replace_link:
        expected.append((WIRE["P1-W08"], False))
    assert writes(client) == expected
    replacement.write_gatt_char.assert_not_awaited()


async def test_home_assistant_stop_preempts_move_and_reuses_cleanup(hass):
    client = make_client()
    coord, ctrl = await make_controller(hass, client, product_type=app.HEAD_FOOT)
    with virtual_clock():
        await ctrl.start_notify()
    client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    allow_write_to_finish = asyncio.Event()

    async def write(char, frame, *, response):
        if frame == WIRE["P1-W04"]:
            entered.set()
            await allow_write_to_finish.wait()

    client.write_gatt_char.side_effect = write
    try:
        with patch.object(coord, "async_ensure_connected", AsyncMock(return_value=True)):
            move = asyncio.create_task(
                coord.async_execute_controller_command(lambda controller: controller.move_back_up())
            )
            await asyncio.wait_for(entered.wait(), 2)
            stop = asyncio.create_task(coord.async_stop_command())
            await asyncio.wait_for(coord.cancel_command.wait(), 2)
            assert writes(client) == [(WIRE["P1-W04"], False)]
            allow_write_to_finish.set()
            await move
            await stop
            assert writes(client) == [(WIRE["P1-W04"], False), (WIRE["P1-W08"], False)]
    finally:
        allow_write_to_finish.set()
        await coord.async_shutdown()


async def test_alarm_action_disables_using_live_alarm_record(hass):
    client = make_client()
    coord, ctrl = await make_controller(hass, client)
    with virtual_clock():
        await ctrl.start_notify()
    client.write_gatt_char.reset_mock()
    hass.data.setdefault(DOMAIN, {})[coord.entry.entry_id] = coord
    await async_register_services(hass)
    try:
        with (
            patch.object(coord, "async_ensure_connected", AsyncMock(return_value=True)),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coord, "both")], []),
            ),
        ):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": ["bed"], "enabled": False},
                blocking=True,
            )
            assert writes(client) == [
                (WIRE["P1-W16"], True),
                (bytes.fromhex("550c000031080000010300080000"), True),
                (WIRE["P1-W16"], True),
            ]
            client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": ["bed"],
                    "enabled": True,
                    "weekdays": ["monday", "sunday"],
                    "wake_action": "zero_g",
                    "time": "06:30:00",
                },
                blocking=True,
            )
            assert writes(client) == [(WIRE["P1-W19"], True), (WIRE["P1-W16"], True)]
    finally:
        await coord.async_shutdown()


async def test_hold_deadline_elapses_while_waiting_for_the_gatt_lane(hass):
    client = make_client()
    _, ctrl = await make_controller(hass, client, product_type=app.HEAD_FOOT)
    with virtual_clock():
        await ctrl.start_notify()
        client.write_gatt_char.reset_mock()
        async with ctrl.ble_lock:
            await ctrl.hold_control("back_up", 10)
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("operation", ["hold", "preset"])
@pytest.mark.parametrize("cancel_source", ["event", "task"])
async def test_cancelled_queued_frame_releases_wait_without_submitting(
    hass, operation, cancel_source
):
    client = make_client()
    coord, ctrl = await make_controller(hass, client, product_type=app.HEAD_FOOT)
    with virtual_clock():
        await ctrl.start_notify()
    client.write_gatt_char.reset_mock()
    command = ctrl.hold_control("back_up", 5000) if operation == "hold" else ctrl.preset_flat()
    async with ctrl.ble_lock:
        task = asyncio.create_task(command)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if cancel_source == "event":
            coord.cancel_command.set()
        else:
            task.cancel()
        # A cancellation must finish before the queue becomes available.
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    client.write_gatt_char.assert_not_awaited()


def setup_probe(client):
    """Patch only BLE transport and metadata I/O for real setup progress."""
    stack = ExitStack()
    stack.enter_context(_patch_gate("hci0", -55))
    stack.enter_context(
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client))
    )
    stack.enter_context(
        patch("custom_components.adjustable_bed.config_flow.discover_services", AsyncMock())
    )
    stack.enter_context(
        patch(
            "custom_components.adjustable_bed.config_flow.read_ble_device_info",
            AsyncMock(return_value=(None, None)),
        )
    )
    return stack


async def finish_probe(flow, progress):
    assert progress["type"] is FlowResultType.SHOW_PROGRESS
    await progress["progress_task"]
    transition = await flow.async_step_setup_progress()
    assert transition["step_id"] == "verify_connection"
    return await flow.async_step_verify_connection()


@pytest.mark.parametrize("receiver", ["correct", "sleep", "write_only", "offline"])
async def test_new_entry_checks_exact_langjue_receiver_and_preserves_offline_setup(hass, receiver):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._async_transport_note = AsyncMock(return_value="")
    client = make_client(
        writer_props=("write",) if receiver == "write_only" else ("write", "write-without-response")
    )
    if receiver == "sleep":
        client.services[0].uuid = "c8cc3a71-2e52-4ce7-839e-774ed9703535"

    form = await start_new_bed(flow, "typed", BED_TYPE_LANGJUE, address=ADDRESS)
    assert form["step_id"] == "profile_questions"
    form = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: app.PRESETS_ONLY})
    assert form["step_id"] == "finish_settings"
    with (
        patch.object(flow, "_verification_possible", return_value=receiver != "offline"),
        setup_probe(client),
    ):
        progress = await flow.async_step_finish_settings({})
        if receiver == "offline":
            assert progress["type"] is FlowResultType.CREATE_ENTRY
        else:
            result = await finish_probe(flow, progress)
            if receiver == "correct":
                assert result["step_id"] == "verify_connection"
                result = await flow.async_step_verify_connection({})
                assert result["type"] is FlowResultType.CREATE_ENTRY
            else:
                assert result["step_id"] in {"manual", "manual_entry"}
                assert result["errors"] == {"base": "langjue_receiver_mismatch"}
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("correct", [True, False])
async def test_reconfigure_checks_live_roles_with_no_inherited_langjue_opt_ins(hass, correct):
    old = {
        CONF_ADDRESS: ADDRESS,
        CONF_BED_TYPE: BED_TYPE_LIMOSS_REMOTE,
        CONF_PRODUCT_TYPE: app.HEAD_FOOT,
        CONF_HAS_LIGHT: True,
        CONF_HAS_MASSAGE: True,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=old)
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    flow._async_transport_note = AsyncMock(return_value="")
    client = make_client(
        writer_props=("write",) if not correct else ("write", "write-without-response")
    )

    await flow.async_step_reconfigure()
    form = await flow.async_step_reconfigure_bed_type({CONF_BED_TYPE: BED_TYPE_LANGJUE})
    assert form["step_id"] == "profile_questions"
    assert suggested(form, CONF_PRODUCT_TYPE) == app.PRESETS_ONLY
    assert suggested(form, CONF_HAS_LIGHT) is False
    assert suggested(form, CONF_HAS_MASSAGE) is False
    with setup_probe(client):
        progress = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: app.PRESETS_ONLY})
        result = await finish_probe(flow, progress)
    assert result["step_id"] == ("migration_confirm" if correct else "migration_check_failed")
    assert flow._pending_entry is not None
    assert flow._pending_entry.get(CONF_HAS_LIGHT) is not True
    assert flow._pending_entry.get(CONF_HAS_MASSAGE) is not True
    assert dict(entry.data) == old
    client.write_gatt_char.assert_not_awaited()


def register_bed_device(hass, coordinator, identifier):
    coordinator.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    return (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=coordinator.entry.entry_id,
            identifiers={(DOMAIN, identifier)},
        )
        .id
    )


async def test_reconfigure_same_langjue_profile_keeps_confirmed_controls(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_BED_TYPE: BED_TYPE_LANGJUE,
            CONF_PRODUCT_TYPE: app.HEAD_FOOT,
            CONF_HAS_LIGHT: True,
            CONF_HAS_MASSAGE: True,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    await flow.async_step_reconfigure()
    form = await flow.async_step_reconfigure_bed_type({CONF_BED_TYPE: BED_TYPE_LANGJUE})
    assert suggested(form, CONF_PRODUCT_TYPE) == app.HEAD_FOOT
    assert suggested(form, CONF_HAS_LIGHT) is True
    assert suggested(form, CONF_HAS_MASSAGE) is True


def make_pair(hass, left, right, *, mode=PAIR_CONNECTION_MODE_CONCURRENT):
    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(left.entry.data, right.entry.data, name="Langjue"),
    )
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass,
        pair_entry,
        {"left": left, "right": right},
        connection_mode=mode,
    )
    return pair, register_bed_device(hass, pair, pair_entry.data[CONF_PAIR_ID])


@pytest.mark.parametrize(
    ("service", "fields", "right_count"),
    [
        ("hold_control", {"control": "back_up", "duration": 0.5}, 3),
        ("timed_move", {"motor": "back", "direction": "up", "duration_ms": 500}, 3),
        ("goto_preset", {"preset": 1}, 0x0A),
    ],
)
async def test_linked_motion_checks_both_receivers_before_sending(
    hass, service, fields, right_count
):
    clients = (make_client(), make_client(right_count))
    left, right = [
        await make_controller(
            hass, client, address=f"AA:BB:CC:DD:EE:{suffix}", product_type=app.HEAD_FOOT
        )
        for client, suffix in zip(clients, ("76", "77"), strict=True)
    ]
    with virtual_clock():
        await left[1].start_notify()
        await right[1].start_notify()
    for client in clients:
        client.write_gatt_char.reset_mock()
    pair, device_id = make_pair(hass, left[0], right[0])
    await async_register_services(hass)
    try:
        with (
            patch.object(left[0], "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right[0], "async_ensure_connected", AsyncMock(return_value=True)),
            pytest.raises(PairedSideError) as failure,
        ):
            await hass.services.async_call(
                DOMAIN,
                service,
                {"device_id": [device_id], **fields},
                blocking=True,
            )
        assert failure.value.action == "linked readiness"
        assert set(failure.value.side_errors) == {"right"}
        for client in clients:
            client.write_gatt_char.assert_not_awaited()
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("enabled", [False, True])
async def test_shared_alarm_checks_all_device_targets_before_first_mutation(hass, enabled):
    clients = (make_client(), make_client(0x0A, alarm=None))
    beds = [
        await make_controller(hass, client, address=f"AA:BB:CC:DD:EE:{suffix}")
        for client, suffix in zip(clients, ("76", "77"), strict=True)
    ]
    with virtual_clock():
        for _, ctrl in beds:
            await ctrl.start_notify()
    for client in clients:
        client.write_gatt_char.reset_mock()
    device_ids = [register_bed_device(hass, coord, coord.address) for coord, _ in beds]
    await async_register_services(hass)
    fields = {"wake_action": "flat", "time": "06:30:00"} if enabled else {}
    try:
        with (
            patch.object(beds[0][0], "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(beds[1][0], "async_ensure_connected", AsyncMock(return_value=True)),
            virtual_clock(),
            pytest.raises((HomeAssistantError, ConnectionError)) as failure,
        ):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": device_ids, "enabled": enabled, **fields},
                blocking=True,
            )
        expected = [] if enabled else [(WIRE["P1-W16"], True)]
        assert writes(clients[0]) == writes(clients[1]) == expected, str(failure.value)
    finally:
        for coord, _ in beds:
            await coord.async_shutdown()


@pytest.mark.parametrize("right_count", [2, 3])
async def test_linked_alarm_readiness_precedes_mutation_on_any_device(hass, right_count):
    clients = (make_client(), make_client(), make_client(right_count))
    beds = [
        await make_controller(
            hass,
            client,
            address=f"AA:BB:CC:DD:EE:{suffix}",
            product_type=app.HEAD_FOOT,
        )
        for client, suffix in zip(clients, ("75", "76", "77"), strict=True)
    ]
    with virtual_clock():
        for (_, ctrl), client in zip(beds, clients, strict=True):
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()
    pair, pair_id = make_pair(hass, beds[1][0], beds[2][0])
    single_id = register_bed_device(hass, beds[0][0], beds[0][0].address)
    await async_register_services(hass)
    try:
        with ExitStack() as connections:
            for coord, _ in beds:
                connections.enter_context(
                    patch.object(coord, "async_ensure_connected", AsyncMock(return_value=True))
                )
            data = {"device_id": [single_id, pair_id], "enabled": False}
            if right_count == 2:
                await hass.services.async_call(DOMAIN, "set_alarm", data, blocking=True)
                for client in clients:
                    assert writes(client) == [
                        (WIRE["P1-W16"], True),
                        (bytes.fromhex("550c000031080000010300080000"), True),
                        (WIRE["P1-W16"], True),
                    ]
                for client in clients[1:]:
                    client.write_gatt_char.reset_mock()
                await hass.services.async_call(
                    DOMAIN,
                    "goto_preset",
                    {"device_id": [pair_id], "preset": 1},
                    blocking=True,
                )
                for client in clients[1:]:
                    assert writes(client) == [(WIRE["P1-W11"], False)]
            else:
                with pytest.raises(PairedSideError) as failure:
                    await hass.services.async_call(DOMAIN, "set_alarm", data, blocking=True)
                assert failure.value.action == "linked readiness"
                for client in clients:
                    client.write_gatt_char.assert_not_awaited()
    finally:
        await pair.async_shutdown()
        await beds[0][0].async_shutdown()


async def test_scheduler_lease_expires_while_waiting_for_gatt(hass):
    client = make_client()
    coord, ctrl = await make_controller(hass, client, product_type=app.HEAD_FOOT)
    try:
        with virtual_clock():
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()
            with patch.object(coord, "async_ensure_connected", AsyncMock(return_value=True)):
                async with ctrl.ble_lock:
                    await coord.async_execute_controller_command(
                        lambda bed: bed.hold_control("back_up", 5000),
                        lease=HoldLease("card", 1, "back_up", 0.01),
                    )
        client.write_gatt_char.assert_not_awaited()
    finally:
        await coord.async_shutdown()


async def test_alarm_disable_uses_latest_record_at_gatt_admission(hass):
    client = make_client()
    _, ctrl = await make_controller(hass, client)
    with virtual_clock():
        await ctrl.start_notify()
    alarm = AlarmRequest(enabled=False, reference_time=datetime(2026, 1, 2))
    await ctrl.check_alarm(alarm)
    client.write_gatt_char.reset_mock()
    sender, emit = client.start_notify.await_args.args
    latest = bytes.fromhex("5500000032080001020441061eab")
    async with ctrl.ble_lock:
        task = asyncio.create_task(ctrl.configure_alarm(alarm))
        await asyncio.sleep(0)
        emit(sender, bytearray(latest))
    await task
    assert writes(client) == [
        (codec.alarm_enabled(latest[6:], False), True),
        (WIRE["P1-W16"], True),
    ]


async def test_sequential_alarm_checks_and_writes_one_side_on_the_same_connection(hass):
    clients = (make_client(), make_client())
    beds = [
        await make_controller(hass, client, address=f"AA:BB:CC:DD:EE:{suffix}")
        for client, suffix in zip(clients, ("76", "77"), strict=True)
    ]
    with virtual_clock():
        for (_, ctrl), client in zip(beds, clients, strict=True):
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()
    left, right = (coord for coord, _ in beds)
    pair, device_id = make_pair(hass, left, right, mode=PAIR_CONNECTION_MODE_SEQUENTIAL)
    await async_register_services(hass)
    try:
        with pytest.raises(HomeAssistantError, match="one receiver at a time"):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": [device_id], "enabled": False},
                blocking=True,
            )
        for client in clients:
            client.write_gatt_char.assert_not_awaited()
        # The retained left session can complete its read and write within one cycle.
        with (
            patch.object(left, "async_connect", AsyncMock(return_value=True)) as connect,
            patch.object(left, "async_ensure_connected", AsyncMock(return_value=True)),
        ):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": [device_id], "side": "left", "enabled": False},
                blocking=True,
            )
        connect.assert_awaited_once()
        assert writes(clients[0]) == [
            (WIRE["P1-W16"], True),
            (bytes.fromhex("550c000031080000010300080000"), True),
            (WIRE["P1-W16"], True),
        ]
        clients[1].write_gatt_char.assert_not_awaited()
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("operation", ["hold", "flat"])
@pytest.mark.parametrize("linked", [False, True])
async def test_cancel_public_scheduler_caller_as_gatt_lane_opens(hass, operation, linked):
    clients = [make_client() for _ in range(2 if linked else 1)]
    beds = [
        await make_controller(
            hass,
            client,
            address=f"AA:BB:CC:DD:EE:{76 + index}",
            product_type=app.HEAD_FOOT,
        )
        for index, client in enumerate(clients)
    ]
    with virtual_clock():
        for (_, ctrl), client in zip(beds, clients, strict=True):
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()

    target = make_pair(hass, beds[0][0], beds[1][0])[0] if linked else beds[0][0]
    command = (
        (lambda bed: bed.hold_control("back_up", 5000))
        if operation == "hold"
        else (lambda bed: bed.preset_flat())
    )
    queued = [asyncio.Event() for _ in beds]

    def watch_gatt(ctrl, ready):
        send = ctrl._send_motion_frame

        async def waiting(*args, **kwargs):
            ready.set()
            return await send(*args, **kwargs)

        return patch.object(ctrl, "_send_motion_frame", waiting)

    try:
        with ExitStack() as patches:
            for (coord, ctrl), ready in zip(beds, queued, strict=True):
                patches.enter_context(watch_gatt(ctrl, ready))
                patches.enter_context(
                    patch.object(coord, "async_ensure_connected", AsyncMock(return_value=True))
                )
            async with AsyncExitStack() as lanes:
                for _, ctrl in beds:
                    await lanes.enter_async_context(ctrl.ble_lock)
                task = asyncio.create_task(target.async_execute_controller_command(command))
                for ready in queued:
                    await asyncio.wait_for(ready.wait(), 2)
            # Releasing the locks schedules both waiters. Cancel their public
            # caller before yielding to either the writer or cancellation handler.
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        for client in clients:
            if linked:
                # The group performs its own best-effort STOP on abort.
                assert all(frame == (WIRE["P1-W08"], False) for frame in writes(client))
            else:
                client.write_gatt_char.assert_not_awaited()
    finally:
        await target.async_shutdown()


@pytest.mark.parametrize(
    ("operation", "abort"),
    [
        ("hold", "cancel"),
        ("hold", "failure"),
        ("flat", "cancel"),
        ("flat", "failure"),
        ("flat", "peer_completed"),
    ],
)
async def test_linked_abort_stops_only_original_submitted_sessions(hass, operation, abort):
    clients = [make_client(), make_client()]
    beds = [
        await make_controller(
            hass, client, address=f"AA:BB:CC:DD:EE:{76 + index}", product_type=app.HEAD_FOOT
        )
        for index, client in enumerate(clients)
    ]
    (left, _), (right, _) = beds
    pair, _ = make_pair(hass, left, right)
    entered = [asyncio.Event(), asyncio.Event()]
    finish = [asyncio.Event(), asyncio.Event()]
    right_completed = asyncio.Event()
    frame = WIRE["P1-W04" if operation == "hold" else "P1-W09"]

    def hold_write(client, index):
        original = client.write_gatt_char.side_effect

        async def write(char, data, *, response):
            if data == frame:
                entered[index].set()
                await finish[index].wait()
                if index == 0 and abort != "cancel":
                    raise ConnectionError("Original left link lost after submission")
            await original(char, data, response=response)

        client.write_gatt_char.side_effect = write

    try:
        with virtual_clock():
            for index, ((_, ctrl), client) in enumerate(zip(beds, clients, strict=True)):
                await ctrl.start_notify()
                client.write_gatt_char.reset_mock()
                hold_write(client, index)

        async def command(bed):
            if operation == "hold":
                await bed.hold_control("back_up", 5000)
            else:
                await bed.preset_flat()
            if bed is beds[1][1]:
                right_completed.set()

        with (
            patch.object(left, "async_ensure_connected", AsyncMock(return_value=True)) as ensure,
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
        ):
            move = asyncio.create_task(pair.async_execute_controller_command(command))
            try:
                for event in entered:
                    await asyncio.wait_for(event.wait(), 2)
                if abort == "peer_completed":
                    finish[1].set()
                    await asyncio.wait_for(right_completed.wait(), 2)
                    assert writes(clients[1]) == [(frame, False)]

                # Replace both the GATT client and the negotiated session while
                # the original ATT submission is still outstanding.
                clients[0].is_connected = False
                replacement = make_client()
                left._client = replacement
                replacement_ctrl = await create_controller(
                    left, BED_TYPE_LANGJUE, "auto", replacement
                )
                left._controller = replacement_ctrl
                with virtual_clock():
                    await replacement_ctrl.start_notify()
                replacement.write_gatt_char.reset_mock()
                ensure_calls = ensure.await_count

                if abort == "cancel":
                    move.cancel()
                finish[0].set()
                if abort != "peer_completed":
                    await asyncio.wait_for(right.cancel_command.wait(), 2)
                    finish[1].set()
                expected_error = asyncio.CancelledError if abort == "cancel" else PairedSideError
                with pytest.raises(expected_error):
                    await move

                assert writes(clients[0]) == [(frame, False)]
                assert writes(clients[1]) == [(frame, False), (WIRE["P1-W08"], False)]
                replacement.write_gatt_char.assert_not_awaited()
                assert ensure.await_count == ensure_calls

                await pair.async_stop_command(side="left")
                assert writes(replacement) == [(WIRE["P1-W08"], False)]
            finally:
                for event in finish:
                    event.set()
                move.cancel()
                await asyncio.gather(move, return_exceptions=True)
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("sequential", [False, True])
async def test_alarm_switch_cannot_preempt_a_claimed_write(hass, sequential):
    clients = (make_client(), make_client())
    beds = [
        await make_controller(hass, client, address=f"AA:BB:CC:DD:EE:{suffix}")
        for client, suffix in zip(clients, ("76", "77"), strict=True)
    ]
    with virtual_clock():
        for (_, ctrl), client in zip(beds, clients, strict=True):
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()

    (left, _), (right, right_ctrl) = beds
    pair = None
    if sequential:
        pair, device_id = make_pair(hass, left, right, mode=PAIR_CONNECTION_MODE_SEQUENTIAL)
        target = PairedSideProxy(pair, right, "right")
        fields = {"device_id": [device_id], "side": "right"}
    else:
        target = right
        fields = {"device_id": [register_bed_device(hass, coord, coord.address) for coord, _ in beds]}
    switch = AdjustableBedControllerSwitch(target, right_ctrl.controller_switch_specs[0])
    switch.hass = hass
    await async_register_services(hass)
    before_write, resume = asyncio.Event(), asyncio.Event()
    configure_alarm = right_ctrl.configure_alarm

    async def paused_write(alarm):
        before_write.set()
        await resume.wait()
        await configure_alarm(alarm)

    disabled = (codec.alarm_enabled(ALARM[6:], False), True)
    read = (WIRE["P1-W16"], True)
    try:
        with (
            patch.object(left, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "async_connect", AsyncMock(return_value=True)),
            patch.object(right_ctrl, "configure_alarm", paused_write),
        ):
            disable = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN, "set_alarm", {**fields, "enabled": False}, blocking=True
                )
            )
            try:
                await asyncio.wait_for(before_write.wait(), 2)
                assert writes(clients[0]) == ([] if sequential else [read, disabled, read])
                assert writes(clients[1]) == [read]

                with pytest.raises(ServiceValidationError) as busy:
                    await asyncio.wait_for(switch.async_turn_on(), 2)
                assert busy.value.translation_key == "langjue_alarm_busy"
                assert writes(clients[1]) == [read]
            finally:
                resume.set()
                await disable

            assert writes(clients[1]) == [read, disabled, read]
            if not sequential:
                await switch.async_turn_on()
                assert writes(clients[1])[-3:] == [
                    read,
                    (codec.alarm_enabled(ALARM[6:], True), True),
                    read,
                ]
    finally:
        if pair is not None:
            await pair.async_shutdown()
        else:
            for coord, _ in beds:
                await coord.async_shutdown()


@pytest.mark.parametrize("overlap", ["action", "switch"])
async def test_overlapping_alarm_action_cannot_consume_a_batchs_checked_record(hass, overlap):
    clients = (make_client(), make_client())
    beds = [
        await make_controller(hass, client, address=f"AA:BB:CC:DD:EE:{suffix}")
        for client, suffix in zip(clients, ("76", "77"), strict=True)
    ]
    with virtual_clock():
        for (_, ctrl), client in zip(beds, clients, strict=True):
            await ctrl.start_notify()
            client.write_gatt_char.reset_mock()

    (left, _), (right, right_controller) = beds
    ids = [register_bed_device(hass, coord, coord.address) for coord, _ in beds]
    await async_register_services(hass)
    before_write, resume = asyncio.Event(), asyncio.Event()
    execute_alarm_step = services._execute_alarm_step

    async def pause_batch(parent, side, command, plan, **kwargs):
        if parent is left and kwargs.get("cancel_running") is None:
            before_write.set()
            await resume.wait()
        await execute_alarm_step(parent, side, command, plan, **kwargs)

    try:
        with (
            patch.object(left, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(services, "_execute_alarm_step", pause_batch),
        ):
            disable = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "set_alarm",
                    {"device_id": ids, "enabled": False},
                    blocking=True,
                )
            )
            try:
                await asyncio.wait_for(before_write.wait(), 2)
                # Both live records were read and neither receiver has mutated.
                for client in clients:
                    assert writes(client) == [(WIRE["P1-W16"], True)]

                with pytest.raises(ServiceValidationError) as busy:
                    if overlap == "action":
                        await hass.services.async_call(
                            DOMAIN,
                            "set_alarm",
                            {
                                "device_id": ids[1:],
                                "enabled": True,
                                "time": "07:15:00",
                                "wake_action": "zero_g",
                            },
                            blocking=True,
                        )
                    else:
                        switch = AdjustableBedControllerSwitch(
                            right, right_controller.controller_switch_specs[0]
                        )
                        switch.hass = hass
                        await switch.async_turn_on()
                assert busy.value.translation_key == "langjue_alarm_busy"
            finally:
                resume.set()
                await disable

            for client in clients:
                assert writes(client) == [
                    (WIRE["P1-W16"], True),
                    (bytes.fromhex("550c000031080000010300080000"), True),
                    (WIRE["P1-W16"], True),
                ]

            # The reservation was released with the completed batch.
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": ids[1:],
                    "enabled": True,
                    "time": "07:15:00",
                    "wake_action": "zero_g",
                },
                blocking=True,
            )
            assert writes(clients[1])[-2:] == [
                (codec.alarm(4, (), 7, 15), True),
                (WIRE["P1-W16"], True),
            ]
    finally:
        for coord, _ in beds:
            await coord.async_shutdown()
