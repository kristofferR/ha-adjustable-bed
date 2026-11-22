"""Relax Motion literal vectors, actual native callers, gates and STOP ownership."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.relax_motion import controller as bed
from custom_components.adjustable_bed.beds.relax_motion import state_keys as state
from custom_components.adjustable_bed.codec import relax_motion as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import relax_motion as app
from tests.error_helpers import raises_key
from tests.relax_motion_vectors import EXTRA, P1, P2
from tests.test_controller_contract import _FactoryCoordinator


@pytest.mark.parametrize("q,pid,cid,param,expected", P1)
def test_p1_literals(q, pid, cid, param, expected):
    assert codec.p1(q, pid, cid, param).hex() == expected


@pytest.mark.parametrize("mask,expected", P2)
def test_p2_literals(mask, expected):
    assert codec.normal(mask).hex() == expected


@pytest.mark.parametrize("cmd,tag,value,expected", EXTRA)
def test_extra_literals(cmd, tag, value, expected):
    assert codec.extra(cmd, tag, value).hex() == expected


def test_release_and_no_side_rewriting():
    assert codec.P2_RELEASE.hex() == "0000000000"
    assert codec.normal(1, 2).hex() == "ee01050000000102c0"
    assert codec.extra(262, 0x1050000, 257).hex() == "ee02050605000001c0"


@pytest.mark.parametrize(
    "data,expected",
    [
        ("de82011203000000", True),
        ("0182011201000000ffaa", True),
        ("0182011200000000", False),
        ("0182011204000000", False),
        ("0181011201000000", False),
        ("01820112", False),
        ("018201", None),
        ("0182021201000000", None),
    ],
)
def test_reply(data, expected):
    assert codec.sleep_state(bytes.fromhex(data)) is expected


def make(number=32, route="relax", coord=None):
    c = coord or _FactoryCoordinator()
    c.entry.data.update({CONF_BED_TYPE: "relax_motion", CONF_PROTOCOL_VARIANT: route})
    if number is not None:
        c.entry.data[CONF_PRODUCT_TYPE] = str(number)
    else:
        c.entry.data.pop(CONF_PRODUCT_TYPE, None)
    c.controller_state = ControllerState()
    c.handle_controller_state_updates = lambda *updates: c.controller_state.update(
        (u.key, u.value) for u in updates
    )
    c.record_command_trace = MagicMock()
    write = SimpleNamespace(
        uuid="00001001-0000-1000-8000-00805f9b34fb", handle=2, properties=["write"]
    )
    notify = SimpleNamespace(
        uuid="00001002-0000-1000-8000-00805f9b34fb", handle=3, properties=["notify"]
    )
    c.client = MagicMock(is_connected=True)
    c.client.services = [
        SimpleNamespace(uuid=codec.SERVICE, characteristics=[write, notify], is_primary=True)
    ]
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.disconnect = AsyncMock(return_value=True)
    c.client.write_gatt_char = AsyncMock()
    ctrl = bed.RelaxMotionController(c)
    c.controller = ctrl
    return ctrl, c


def frames(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.call_args_list]


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await real_sleep(0)

    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    return now


@pytest.mark.parametrize(
    "number,route,protocol,axes,memory,light",
    [
        (1, "relax", "p1", ("back", "legs"), 0, False),
        (1, "cheers_zh", "p1", ("back", "legs"), 5, False),
        (1, "cheers_en", "p1", ("back", "legs"), 0, False),
        (31, "relax", "p1", ("back", "lumbar", "legs"), 5, True),
        (14, "relax", "p1", ("all_motors",), 0, False),
        (500, "relax", "p2", ("back", "legs"), 1, False),
        (725, "relax", "p2", ("back", "lumbar", "legs"), 0, False),
        (500, "legacy", "p1", ("back", "legs"), 5, False),
        (451, "relax", "p2", ("back", "legs"), 0, False),
        (450, "relax", "p1", ("back", "legs"), 0, False),
        (451, "cheers_zh", "p1", ("back", "legs"), 5, False),
    ],
)
def test_model_and_route_gates(number, route, protocol, axes, memory, light):
    ctrl, _ = make(number, route)
    assert ctrl.profile.key == protocol
    assert tuple(spec.key for spec in ctrl.motor_control_specs) == axes
    assert ctrl.memory_slot_count == memory
    assert ctrl.supports_lights is light
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.supports_clock_sync and not ctrl.supports_clock_alarm
    assert not ctrl.position_number_specs
    assert not any(spec.hold for spec in ctrl.controller_button_specs if spec.requires_confirmation)


async def test_unresolved_model_and_replaced_selection_reject_before_write(clock):
    ctrl, c = make(None)
    assert not ctrl.motor_control_specs and not ctrl.memory_slot_count
    with raises_key("relax_motion_model"):
        await ctrl.async_discover_capabilities()
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    c.entry.data[CONF_PRODUCT_TYPE] = "500"
    with raises_key("relax_motion_session"):
        await ctrl.preset_flat()
    assert frames(c) == []


def test_manufacturer_identity_is_company_prefixed_and_sorted():
    assert app.advertisement({89: bytes((200, 100, 111))}) == 500
    assert app.advertisement({89: bytes((200, 100, 111))}, legacy=True) == 89
    assert app.advertisement({3: b"\x01", 2: b"\x10"}) == 2
    assert app.advertisement({}) is None
    assert app.advertisement({89: b"\x01"}) == 89


async def test_gatt_order_and_notify_fanout(clock):
    ctrl, c = make(500)
    original = c.client.services[0]
    later = SimpleNamespace(
        uuid="0000ffff-0000-1000-8000-00805f9b34fb", handle=8, properties=["write-without-response"]
    )
    indicated = SimpleNamespace(
        uuid="0000fffe-0000-1000-8000-00805f9b34fb", handle=9, properties=["indicate"]
    )
    original.characteristics.extend([later, indicated])
    c.client.services.append(SimpleNamespace(uuid="other", characteristics=[], is_primary=True))
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await ctrl.program_memory(1)
    assert all(
        call.args[0] is later and call.kwargs["response"] is False
        for call in c.client.write_gatt_char.call_args_list
    )
    assert c.client.start_notify.call_count == 2
    await ctrl.stop_notify()
    assert c.client.stop_notify.call_count == 2


async def test_p1_main_and_editor_stop_and_serial_wrap(clock):
    ctrl, c = make(31)
    await ctrl.async_discover_capabilities()
    ctrl._serial = 254
    await ctrl.hold_control("lumbar_up", 1000)
    assert frames(c) == ["ff01010000000000", "00010b0110270000", "0101010000000000"]
    await ctrl.editor_stop("lumbar")
    assert frames(c)[-1] == "0201080100000000"


async def test_p2_burst_and_actual_release(clock):
    ctrl, c = make(500)
    await ctrl.async_discover_capabilities()
    await ctrl.preset_memory(1)
    assert frames(c) == ["0000000000"] * 2 + ["ee01050001000000c0"] * 3 + ["0000000000"] * 2
    assert clock[0] == pytest.approx(0.8)
    c.client.write_gatt_char.reset_mock()
    await ctrl.program_memory(1)
    assert frames(c) == ["ee02050605000000c0"] * 3 + ["0000000000"] * 2
    with raises_key("relax_motion_memory"):
        await ctrl.program_memory(2)


@pytest.mark.parametrize("number", [32, 500])
async def test_early_release_drains_delayed_work(clock, number):
    ctrl, c = make(number)
    await ctrl.async_discover_capabilities()
    entered = asyncio.Event()

    async def pause(seconds, epoch):
        entered.set()
        await c.cancel_command.wait()
        raise asyncio.CancelledError

    ctrl._pause = pause
    task = asyncio.create_task(ctrl.hold_control("back_up", 1000))
    await entered.wait()
    c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    before = frames(c)
    await asyncio.sleep(0)
    assert frames(c) == before
    assert all(
        frame == "0000000000" if number > 450 else frame[4:8] == "0100" for frame in frames(c)
    )


async def test_controller_local_stop_does_not_cancel_pair_event(clock):
    ctrl, c = make(500)
    await ctrl.async_discover_capabilities()
    await ctrl.stop_all()
    assert not c.cancel_command.is_set()
    assert frames(c) == ["0000000000"] * 2


async def test_sleep_gate_and_stale_callback(clock):
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    with raises_key("relax_motion_control"):
        await ctrl.setting("interval", 2)
    callback(None, bytes.fromhex("de82011203000000"))
    await ctrl.setting("interval", 2)
    assert frames(c)[-1][2:] == "03051178000000"
    assert c.controller_state.get(state.INTERVAL) == 2
    callback(None, bytes.fromhex("de82011200000000"))
    assert ctrl._snore_ready and c.controller_state.get(state.SLEEP) is False
    ctrl.on_disconnect()
    callback(None, bytes.fromhex("de82011203000000"))
    assert not ctrl._snore_ready and c.controller_state.get(state.SLEEP) is None


async def test_cheers_locale_rhythm_and_cosy_gates(clock):
    ctrl, c = make(32, "cheers_zh")
    await ctrl.async_discover_capabilities()
    await ctrl.rhythm(2)
    await ctrl.massage("head", 3)
    assert frames(c)[-1][4:8] == "2202"
    await ctrl.massage_off()
    await ctrl.massage("foot", 1)
    assert frames(c)[-1][4:8] == "0402"
    await ctrl.cosy(True)
    assert frames(c)[-1][4:8] == "0106"
    for route in ("relax", "cheers_en"):
        ctrl, c = make(32, route)
        await ctrl.async_discover_capabilities()
        with raises_key("relax_motion_control"):
            await ctrl.rhythm(1)
        if route == "cheers_en":
            with raises_key("relax_motion_control"):
                await ctrl.massage("head", 1)


async def test_actual_factory_uses_saved_model_and_route(clock):
    from custom_components.adjustable_bed.controller_factory import create_controller

    ctrl, c = make(725)
    built = await create_controller(c, "relax_motion", "relax", c.client)
    assert isinstance(built, bed.RelaxMotionController)
    assert built.number == 725 and built.profile.key == "p2"
    assert tuple(s.key for s in built.motor_control_specs) == ("back", "lumbar", "legs")


async def test_real_setup_uses_advertised_identity_without_default(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock(name="Relax Motion")
    info.name, info.address = "Motion", "AA:BB:CC:DD:EE:98"
    info.service_uuids = [codec.SERVICE]
    info.manufacturer_data = {89: bytes((200, 100, 111))}
    info.source = "auto"
    info.advertisement = SimpleNamespace(local_name=info.name)
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "picked", "relax_motion")
    assert result["step_id"] in ("profile_questions", "finish_settings")
    if result["step_id"] == "profile_questions":
        result = await flow.async_step_profile_questions(
            {CONF_PRODUCT_TYPE: "500", CONF_PROTOCOL_VARIANT: "relax"}
        )
    assert result["step_id"] == "finish_settings"
    assert flow._manual_data[CONF_PRODUCT_TYPE] == "500"
    assert flow._manual_data[CONF_PROTOCOL_VARIANT] == "relax"


@pytest.mark.parametrize(
    "name,services,expected",
    [
        ("Motion", [codec.SERVICE], True),
        ("ZKYL-bed", [codec.SERVICE], False),
        ("", [codec.SERVICE], False),
        ("Motion", ["0000180a-0000-1000-8000-00805f9b34fb", codec.SERVICE], False),
    ],
)
def test_actual_discovery_admission(name, services, expected):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = MagicMock()
    info.name, info.service_uuids, info.manufacturer_data = name, services, {89: b"\x01"}
    info.advertisement = SimpleNamespace(local_name=name)
    result = detect_bed_type_detailed(info)
    assert ("relax_motion" in (result.ambiguous_types or ())) is expected


async def native(hass, number=32, route="relax"):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Relax Motion",
        version=5,
        data={
            "address": "AA:BB:CC:DD:12:00",
            "name": "Relax Motion",
            "bed_type": "relax_motion",
            "product_type": str(number),
            "protocol_variant": route,
            "motor_count": 2,
            "has_massage": False,
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    child = AdjustableBedCoordinator(hass, entry)
    _, template = make(number)
    child._client = template.client
    ctrl = bed.RelaxMotionController(child)
    child._controller = ctrl
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = child
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=child.device_info
    )
    child.async_ensure_connected = AsyncMock(return_value=True)
    child._async_refresh_controller_auth = AsyncMock()
    return child, ctrl, template, device


async def test_real_native_number_and_light_delivery(hass, clock):
    from custom_components.adjustable_bed.command_scheduler import current_command_context
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL

    child, ctrl, transport, _ = await native(hass)
    number = AdjustableBedControllerNumber(child, ctrl.controller_number_specs[0])
    number.hass = hass
    try:
        await number.async_set_native_value(6000)
        assert number.native_value == 6000
        assert frames(transport) == ["0103011170170000"]
        available = ctrl.controller_switch_specs[0].available_fn
        assert available is not None
        assert not available(ctrl)
        with raises_key("relax_motion_control"):
            await ctrl.setting("interval", 5)
        transport.client.write_gatt_char.reset_mock()

        async def cancel_after_prep(*_args, **_kwargs):
            current_command_context().cancel_event.set()

        transport.client.write_gatt_char.side_effect = cancel_after_prep
        await child.async_execute_controller_command(lambda c: c.set_light_level(100))
        assert child.controller_state.get(LIGHT_LEVEL) is None
        assert len(frames(transport)) == 1  # STOP preparation only.
    finally:
        await child.async_shutdown()


async def test_real_native_inflight_write_is_settled_before_stop(hass, clock):
    from custom_components.adjustable_bed.command_scheduler import (
        Delivery,
        current_command_context,
        delivered,
    )

    child, ctrl, transport, _ = await native(hass)
    seen = []

    async def stop_after_frame(_char, frame, **_kwargs):
        if frame[2:4] == b"\x01\x05":
            current_command_context().cancel_event.set()

    transport.client.write_gatt_char.side_effect = stop_after_frame

    async def operation(c):
        with delivered(seen.append):
            await c.set_light_level(100)

    try:
        await child.async_execute_controller_command(operation)
        assert seen == [Delivery.SENT]
        assert ctrl.light_intensity == 100
    finally:
        await child.async_shutdown()


async def test_registered_hold_service_and_native_stop(hass, clock):
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    child, ctrl, transport, device = await native(hass, 500)
    try:
        await async_register_services(hass)
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "back_up", "duration": 0.6},
            blocking=True,
        )
        assert any(frame == "ee01050000000100c0" for frame in frames(transport))
        assert frames(transport)[-2:] == ["0000000000"] * 2
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [device.id]}, blocking=True
        )
        assert frames(transport)[-2:] == ["0000000000"] * 2
    finally:
        await child.async_shutdown()


async def test_all_memory_editor_and_tool_writes_use_reachable_catalog(clock):
    ctrl, c = make(32)
    await ctrl.async_discover_capabilities()
    for slot, recall, save in (
        (1, "1103", "1003"),
        (2, "1303", "1203"),
        (3, "1503", "1403"),
        (4, "1703", "1603"),
        (5, "1903", "1803"),
    ):
        await ctrl.preset_memory(slot)
        assert frames(c)[-1][4:8] == recall
        c.client.write_gatt_char.reset_mock()
        await ctrl.program_memory(slot)
        assert len(frames(c)) == 1 and frames(c)[0][4:8] == save
    for zone, codes in (
        ("head", ("2301", "0102", "0202", "0302")),
        ("foot", ("2401", "0402", "0502", "0602")),
    ):
        for level, command in enumerate(codes):
            await ctrl.massage(zone, level)
            assert frames(c)[-1][4:8] == command
    await ctrl.lights_off()
    assert frames(c)[-1][4:] == "000500000000"
    await ctrl.lights_on()
    assert frames(c)[-1][4:] == "0105ffffffff"
    ctrl._notification(ctrl._link, bytes.fromhex("de82011203000000"), "test")
    await ctrl.setting("snore", False)
    assert frames(c)[-1][2:] == "03031100000000"
    await ctrl.setting("snore", True)
    assert frames(c)[-1][2:] == "03031101000000"


@pytest.mark.parametrize("ending", ["disconnect", "replace", "model", "local_stop"])
async def test_pending_native_movement_cannot_escape_lifecycle(clock, ending):
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    paused, resume = asyncio.Event(), asyncio.Event()
    original = ctrl._pause

    async def pause(seconds, epoch):
        paused.set()
        await resume.wait()
        await original(0, epoch)

    ctrl._pause = pause
    task = asyncio.create_task(ctrl.hold_control("back_up", 1000))
    await paused.wait()
    if ending == "disconnect":
        ctrl.on_disconnect()
    elif ending == "replace":
        c.controller = bed.RelaxMotionController(c)
    elif ending == "model":
        c.entry.data[CONF_PRODUCT_TYPE] = "500"
    else:
        await ctrl.stop_all()
    resume.set()
    try:
        await task
    except asyncio.CancelledError, Exception:
        pass
    assert all(frame[4:8] == "0100" for frame in frames(c))
    assert not c.cancel_command.is_set()


async def test_task_cancellation_during_final_write_keeps_delivered_state(hass, clock):
    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    child, ctrl, transport, _ = await native(hass)
    seen, owner = [], []

    async def write(_char, frame, **_kwargs):
        if frame[2:4] == b"\x01\x05":
            owner[0].cancel()
            await asyncio.sleep(0)

    transport.client.write_gatt_char.side_effect = write

    async def operation(c):
        owner.append(asyncio.current_task())
        with delivered(seen.append):
            await c.set_light_level(100)

    try:
        await child.async_execute_controller_command(operation)
        assert seen == [Delivery.SENT]
        assert ctrl.light_intensity == 100
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("cancel_task", [False, True])
async def test_stop_in_settled_scheduling_gap_prevents_write(clock, monkeypatch, cancel_task):
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    original = bed.settled

    async def before_schedule(operation):
        if cancel_task:
            asyncio.current_task().cancel()
        else:
            c.cancel_command.set()
        return await original(operation)

    monkeypatch.setattr(bed, "settled", before_schedule)
    task = asyncio.create_task(
        ctrl._send(ctrl._link, bytes.fromhex("0101030110270000"), ctrl._epoch)
    )
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == []


@pytest.mark.parametrize(
    "field,value", [(CONF_PRODUCT_TYPE, "500"), (CONF_PROTOCOL_VARIANT, "cheers_zh")]
)
async def test_running_movement_releases_original_link_during_reconfigure(clock, field, value):
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    original = ctrl._pause

    async def pause(seconds, epoch):
        if any(frame[4:8] == "0301" for frame in frames(c)):
            c.entry.data[field] = value
            c.cancel_command.set()
            raise asyncio.CancelledError
        await original(seconds, epoch)

    ctrl._pause = pause
    with pytest.raises(asyncio.CancelledError):
        await ctrl.hold_control("back_up", 1000)
    assert [frame[4:8] for frame in frames(c)] == ["0100", "0301", "0100"]
    with raises_key("relax_motion_session"):
        await ctrl.hold_control("back_up", 1000)


async def test_p2_stop_attempts_second_release_after_first_failure(clock):
    ctrl, c = make(500)
    await ctrl.async_discover_capabilities()
    c.client.write_gatt_char.side_effect = [RuntimeError("first release failed"), None]
    with pytest.raises(RuntimeError, match="first release failed"):
        await ctrl.stop_all()
    assert frames(c) == ["0000000000", "0000000000"]
    assert clock[0] == pytest.approx(0.2)


async def test_disconnect_during_settled_setting_never_republishes_old_state(hass, clock):
    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    child, ctrl, transport, _ = await native(hass)
    owners, seen = [], []

    async def write(_char, frame, **_kwargs):
        if frame[2:4] == b"\x01\x05":
            ctrl.on_disconnect()
            owners[0].cancel()
            await asyncio.sleep(0)

    transport.client.write_gatt_char.side_effect = write

    async def operation(c):
        owners.append(asyncio.current_task())
        with delivered(seen.append):
            await c.set_light_level(100)

    try:
        await child.async_execute_controller_command(operation)
        assert seen == [Delivery.SENT]
        assert ctrl.light_intensity is None
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("submitted,expected", [("500", "89"), ("700", "700"), ("89", "89")])
async def test_actual_setup_applies_page_before_model_seed(hass, submitted, expected):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock()
    info.name, info.address, info.source = "Motion", "AA:BB:CC:DD:EE:98", "auto"
    info.service_uuids = [codec.SERVICE]
    info.manufacturer_data = {89: bytes((200, 100, 111))}
    info.advertisement = SimpleNamespace(local_name=info.name)
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    result = await start_new_bed(flow, "picked", "relax_motion")
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data[CONF_PRODUCT_TYPE] == "500"
    result = await flow.async_step_profile_questions(
        {CONF_PRODUCT_TYPE: submitted, CONF_PROTOCOL_VARIANT: "legacy"}
    )
    assert result["step_id"] == "finish_settings"
    assert flow._manual_data[CONF_PRODUCT_TYPE] == expected
    assert flow._manual_data[CONF_PROTOCOL_VARIANT] == "legacy"


@pytest.mark.parametrize("number,minimum", [(32, 200), (500, 300)])
async def test_native_short_hold_rejected_in_preflight_without_frames(hass, clock, number, minimum):
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    child, ctrl, transport, device = await native(hass, number)
    try:
        with raises_key("relax_motion_hold"):
            ctrl.validate_hold_control("back_up", minimum)
        with raises_key("relax_motion_hold"):
            ctrl.validate_timed_movement("back", "up", 100)
        await async_register_services(hass)
        with raises_key({"relax_motion_hold", "action_rejected"}):
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": [device.id], "control": "back_up", "duration": 0.1},
                blocking=True,
            )
        assert frames(transport) == []
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize("number,route", [(1, "relax"), (32, "cheers_en")])
async def test_memory_editor_stop_is_gated(clock, number, route):
    ctrl, c = make(number, route)
    await ctrl.async_discover_capabilities()
    assert not any("editor_stop" in spec.key for spec in ctrl.controller_button_specs)
    with raises_key("relax_motion_control"):
        await ctrl.editor_stop("back")
    assert frames(c) == []


@pytest.mark.parametrize(
    "value,expected",
    [("0500", 500), ("0", 0), ("²", None), ("５００", None), (True, None), ("", None)],
)
def test_one_numeric_identity_parser(value, expected):
    from custom_components.adjustable_bed.setup_questions import setup_profile

    assert app.model_number(value) == expected
    profile = setup_profile("relax_motion")
    assert profile.validate is not None
    previous = {CONF_BED_TYPE: "relax_motion", CONF_PROTOCOL_VARIANT: "relax"}
    staged = profile.staged(previous, {CONF_PRODUCT_TYPE: value})
    if expected is not None:
        assert staged[CONF_PRODUCT_TYPE] == str(expected)
    else:
        assert profile.validate(staged) == {CONF_PRODUCT_TYPE: "relax_motion_model"}


async def test_rhythm_uses_strength_cycle_and_global_off(clock):
    ctrl, c = make(32, "cheers_zh")
    await ctrl.async_discover_capabilities()
    await ctrl.rhythm(1)
    assert not ctrl.controller_button_available("relax_motion_head_massage_0")
    assert not any(
        spec.key == "relax_motion_head_massage_0" for spec in ctrl.controller_button_specs
    )
    with raises_key("relax_motion_control"):
        await ctrl.massage("head", 0)
    await ctrl.massage("head", 1)
    assert frames(c)[-1][4:8] == "2002"
    await ctrl.massage_off()
    assert ctrl.controller_button_available("relax_motion_head_massage_0")
    await ctrl.massage("head", 0)
    assert frames(c)[-1][4:8] == "2301"


async def test_auto_route_cannot_keep_a_live_legacy_protocol(clock):
    ctrl, c = make(500, "legacy")
    await ctrl.async_discover_capabilities()
    c.entry.data[CONF_PROTOCOL_VARIANT] = "auto"
    with raises_key("relax_motion_session"):
        await ctrl.hold_control("back_up", 1000)
    assert frames(c) == []
    await ctrl.stop_all()
    assert frames(c)[-1][4:8] == "0100"
    fresh = bed.RelaxMotionController(c)
    assert fresh.profile.key == "p2"


async def test_dispatch_deadline_is_rechecked_inside_shielded_task(clock, monkeypatch):
    ctrl, c = make()
    await ctrl.async_discover_capabilities()
    original = bed.settled

    async def before_schedule(operation):
        if len(frames(c)) == 1:
            clock[0] = 0.202
        return await original(operation)

    monkeypatch.setattr(bed, "settled", before_schedule)
    with raises_key("relax_motion_hold"):
        await ctrl.hold_control("back_up", 201)
    assert [frame[4:8] for frame in frames(c)] == ["0100", "0100"]


async def test_real_button_listener_refreshes_rhythm_availability(hass, clock):
    from custom_components.adjustable_bed.button import ControllerActionButton

    child, _, transport, _ = await native(hass)
    hass.config_entries.async_update_entry(
        child.entry, data={**child.entry.data, CONF_PROTOCOL_VARIANT: "cheers_zh"}
    )
    ctrl = bed.RelaxMotionController(child)
    child._controller = ctrl
    await ctrl.async_discover_capabilities()
    spec = next(s for s in ctrl.controller_button_specs if s.key == "relax_motion_head_massage_0")
    button = ControllerActionButton(child, spec)
    button.hass = hass
    button.entity_id = "button.relax_motion_head_off"
    shown = []
    button.async_write_ha_state = MagicMock(side_effect=lambda: shown.append(button.available))
    try:
        await button.async_added_to_hass()
        await ctrl.rhythm(1)
        assert shown and shown[-1] is False
        assert child.controller_state.get(state.RHYTHM) is True
        await ctrl.rhythm(0)
        assert shown[-1] is True
        assert child.controller_state.get(state.RHYTHM) is False
    finally:
        await button.async_will_remove_from_hass()
        await child.async_shutdown()


@pytest.mark.parametrize("route", ["relax", "cheers_zh"])
async def test_massage_numbers_follow_delivered_levels_and_rhythm(hass, clock, route):
    from custom_components.adjustable_bed.command_scheduler import current_command_context
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber

    child, ctrl, transport, _ = await native(hass, route=route)
    specs = {s.key: s for s in ctrl.controller_number_specs}
    spec = specs["relax_motion_head_intensity"]
    assert spec.translation_key == "massage_head_intensity"
    assert (spec.native_min_value, spec.native_max_value, spec.native_step) == (1, 3, 1)
    assert not any(
        s.key.endswith(("massage_1", "massage_2", "massage_3"))
        for s in ctrl.controller_button_specs
    )
    number = AdjustableBedControllerNumber(child, spec)
    number.hass = hass
    try:
        assert number.native_value is None
        await number.async_set_native_value(2)
        assert frames(transport)[-1][4:8] == "0202"
        assert number.native_value == 2
        if route == "cheers_zh":
            await child.async_execute_controller_command(lambda _: ctrl.rhythm(1))
            assert number.native_value is None
        await number.async_set_native_value(3)
        assert frames(transport)[-1][4:8] == ("2202" if route == "cheers_zh" else "0302")
        assert number.native_value == 3
        await child.async_execute_controller_command(lambda c: c.massage_off())
        assert number.native_value is None
        await number.async_set_native_value(1)
        assert frames(transport)[-1][4:8] == "0102"

        async def cancel_after_prep(*_args, **_kwargs):
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()

        transport.client.write_gatt_char.side_effect = cancel_after_prep
        await number.async_set_native_value(3)
        assert number.native_value == 1
        ctrl.on_disconnect()
        assert number.native_value is None
    finally:
        await child.async_shutdown()


@pytest.mark.parametrize(
    "name,services",
    [
        ("ZKYL-bed", [codec.SERVICE]),
        ("Motion", ["0000180a-0000-1000-8000-00805f9b34fb", codec.SERVICE]),
        ("", [codec.SERVICE]),
    ],
)
def test_setup_seed_uses_discovery_gates_and_preserves_manual_identity(name, services):
    from custom_components.adjustable_bed.setup_questions import setup_profile

    info = SimpleNamespace(
        name=name,
        service_uuids=services,
        manufacturer_data={89: bytes((200, 100, 111))},
        advertisement=SimpleNamespace(local_name=name),
    )
    profile = setup_profile("relax_motion")
    assert profile.seed is not None
    data = {CONF_BED_TYPE: "relax_motion", CONF_PROTOCOL_VARIANT: "relax"}
    seeded = profile.seed(None, data, info)
    assert CONF_PRODUCT_TYPE not in seeded
    manual = profile.seed(None, {**data, CONF_PRODUCT_TYPE: "700"}, info)
    assert manual[CONF_PRODUCT_TYPE] == "700"
    older = profile.seed(None, {**data, CONF_PROTOCOL_VARIANT: "legacy"}, info)
    assert older.get(CONF_PRODUCT_TYPE) == ("89" if name else None)


def real_advertisement(name="Motion", services=None):
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

    return BluetoothServiceInfoBleak.from_scan(
        "test",
        BLEDevice("AA:BB:CC:DD:EE:98", name, {}),
        AdvertisementData(
            local_name=name,
            manufacturer_data={89: bytes((200, 100, 111))},
            service_data={},
            service_uuids=services if services is not None else [codec.SERVICE],
            tx_power=None,
            rssi=-50,
            platform_data=(),
        ),
        0,
        True,
    )


@pytest.mark.parametrize("route", ["relax", "cheers_zh", "cheers_en", "legacy"])
@pytest.mark.parametrize("number,motors", [(14, 1), (32, 2), (725, 3)])
async def test_complete_setup_reaches_verification_with_exact_profile(hass, route, number, motors):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = real_advertisement()
    flow._async_transport_note = AsyncMock(return_value="")
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "picked", "relax_motion")
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions(
        {CONF_PRODUCT_TYPE: str(number), CONF_PROTOCOL_VARIANT: route}
    )
    assert result["step_id"] == "finish_settings"
    result = await flow.async_step_finish_settings({})
    assert result["type"] == "create_entry", result
    stored = flow._finish_with_verify.await_args.args[0]
    assert stored[CONF_PRODUCT_TYPE] == str(number)
    assert stored[CONF_PROTOCOL_VARIANT] == route
    assert stored["motor_count"] == motors


async def test_configure_retains_legacy_route_after_idle_setting(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed.controller_factory import create_controller

    child, _, _, _ = await native(hass, 500, "legacy")
    try:
        initial = await hass.config_entries.options.async_init(child.entry.entry_id)
        form = await hass.config_entries.options.async_configure(
            initial["flow_id"], {"next_step_id": "settings"}
        )
        with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)):
            result = await hass.config_entries.options.async_configure(
                form["flow_id"], {"connection_mode": "idle", "idle_disconnect_seconds": 60}
            )
            await hass.async_block_till_done()
        assert result["type"] == "create_entry", result
        assert child.entry.data[CONF_PROTOCOL_VARIANT] == "legacy"
        assert child.entry.data["idle_disconnect_seconds"] == 60
        fresh = await create_controller(child, "relax_motion", "legacy", None)
        assert fresh.profile.key == "p1"
    finally:
        await child.async_shutdown()


async def test_cross_app_change_rejects_old_controller_and_keeps_cleanup(clock):
    ctrl, c = make(45)
    await ctrl.async_discover_capabilities()
    c.entry.data[CONF_BED_TYPE] = "cheerssleep"
    c.entry.data[CONF_PROTOCOL_VARIANT] = "auto"
    with raises_key("relax_motion_session"):
        await ctrl.hold_control("back_up", 1000)
    assert frames(c) == []
    await ctrl.stop_all()
    assert frames(c)[-1][4:8] == "0100"


def test_real_ble_name_fallback_does_not_admit_or_seed_a_model():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.setup_questions import setup_profile

    info = real_advertisement(None)
    assert info.name and info.advertisement.local_name is None
    result = detect_bed_type_detailed(info)
    assert "relax_motion" not in (result.ambiguous_types or ())
    profile = setup_profile("relax_motion")
    assert profile.seed is not None
    data = {CONF_BED_TYPE: "relax_motion", CONF_PROTOCOL_VARIANT: "relax"}
    assert CONF_PRODUCT_TYPE not in profile.seed(None, data, info)


async def test_blank_rendered_model_can_seed_after_switching_to_older_page(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import form_answers, start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = real_advertisement(
        services=["0000180a-0000-1000-8000-00805f9b34fb", codec.SERVICE]
    )
    flow._async_transport_note = AsyncMock(return_value="")
    result = await start_new_bed(flow, "picked", "relax_motion")
    answers = form_answers(result)
    assert answers[CONF_PRODUCT_TYPE] == ""
    answers[CONF_PROTOCOL_VARIANT] = "legacy"
    result = await flow.async_step_profile_questions(answers)
    assert result["step_id"] == "finish_settings", result
    assert flow._manual_data[CONF_PRODUCT_TYPE] == "89"


@pytest.mark.parametrize("discovered,expected", [(False, None), (True, "500")])
async def test_cross_app_selection_drops_previous_apps_model(hass, discovered, expected):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_BED_TYPE: "cheerssleep",
        CONF_PRODUCT_TYPE: "45",
        CONF_PROTOCOL_VARIANT: "auto",
        "address": "AA:BB:CC:DD:EE:98",
        "name": "Motion",
    }
    flow._discovery_info = real_advertisement() if discovered else None
    flow._select_family_route("relax_motion", None)
    assert CONF_PRODUCT_TYPE not in flow._manual_data
    result = await flow.async_step_profile_questions()
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data.get(CONF_PRODUCT_TYPE) == expected


def test_a_configured_remacro_bed_is_not_asked_about_relax_motion(hass):
    """The shared service makes new setups ask; it raises nothing on a bed already set up."""
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from custom_components.adjustable_bed.profile_review import suggested_apps

    info = real_advertisement("Motion")
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type == "remacro" and "relax_motion" in detected.ambiguous_types
    data = {"bed_type": "remacro", "address": info.address}
    assert recommend_profile(data, info, {}) is None
    with patch(
        "custom_components.adjustable_bed.profile_review._last_service_info", return_value=info
    ):
        assert "relax_motion" not in suggested_apps(hass, data)


@pytest.mark.parametrize("advertised_name", ["Motion", "SmartBed"])
async def test_rendered_bluetooth_discovery_offers_relax_motion_explicitly(hass, advertised_name):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import select_options, suggested

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._async_transport_note = AsyncMock(return_value="")
    result = await flow.async_step_bluetooth(real_advertisement(advertised_name))
    assert result["step_id"] == "bluetooth_disambiguate", result
    options = select_options(result, "bed_type_choice")
    assert options["relax_motion"] == "Relax Motion app"
    assert "remacro" in options and "show_all" in options
    assert next(iter(options)) == "remacro"
    assert not {"rize_home", "n32_motion_bed", "symphony", "yamada", "nerum"}.intersection(options)
    assert suggested(result, "bed_type_choice") is None
    result = await flow.async_step_bluetooth_disambiguate({"bed_type_choice": "relax_motion"})
    assert result["step_id"] == "bluetooth_confirm"
    options = select_options(result, CONF_BED_TYPE)
    assert "relax_motion" in options
    result = await flow.async_step_bluetooth_confirm({CONF_BED_TYPE: "relax_motion"})
    assert result["step_id"] == "profile_questions", result
    assert flow._manual_data[CONF_PRODUCT_TYPE] == "500"
