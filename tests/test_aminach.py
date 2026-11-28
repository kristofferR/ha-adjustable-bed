"""Platinum's frozen literals, native controls and connection-owned responses."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.aminach import AminachController
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.codec import aminach as codec
from custom_components.adjustable_bed.profiles import aminach as app
from tests.hold_lease_wire import virtual_clock

ROWS = json.loads((Path(__file__).parent / "fixtures/aminach/vectors.json").read_text())
ACTIONS = (
    "sleep",
    "light",
    "memo",
    "back_up",
    "back_down",
    "legs_up",
    "legs_down",
    "head_up",
    "head_down",
    "release",
)
LOCAL_ADDRESS = "01:23:45:67:89:AB"


@dataclass(eq=False)
class Char:
    uuid: str
    properties: list[str]
    handle: int
    descriptors: tuple = ()


def gatt(properties=("write", "write-without-response")):
    write = Char(app.WRITE, list(properties), 2)
    notify = Char(app.NOTIFY, ["notify"], 3)
    chars = {app.WRITE: write, app.NOTIFY: notify}
    return [
        SimpleNamespace(
            uuid=app.SERVICE, characteristics=list(chars.values()), get_characteristic=chars.get
        )
    ]


def client(properties=("write", "write-without-response")):
    return SimpleNamespace(
        services=gatt(properties),
        is_connected=True,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


async def connected(hass, count=3, properties=("write", "write-without-response")):
    c = MagicMock(
        client=client(properties),
        hass=hass,
        motor_count=count,
        motor_pulse_count=2,
        cancel_command=asyncio.Event(),
        name="Platinum",
    )
    ctrl = AminachController(c)
    c.controller = ctrl
    with patch.object(ctrl, "_adapter_address", return_value=LOCAL_ADDRESS):
        await ctrl.start_notify()
    return ctrl, c


def written(c):
    return [bytes(call.args[1]) for call in c.write_gatt_char.call_args_list]


def receive(c, data):
    c.client.start_notify.call_args.args[1](None, bytearray(data))


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["id"])
def test_all_accepted_literal_builders(row):
    if "button_index" in row["inputs"]:
        index = row["inputs"]["button_index"]
        action = ACTIONS[index - 1] if index <= 9 else "release"
        assert app.PLATINUM.frame(action) == bytes.fromhex(row["expected_bytes"])
    else:
        assert codec.adapter_response(row["inputs"]["local_adapter_address"]) == bytes.fromhex(
            row["expected_bytes"]
        )


def test_complete_frame_census_and_no_inferred_semantics():
    assert {app.PLATINUM.frame(action) for action in app.KEYS} == {
        bytes.fromhex(row["expected_bytes"]) for row in ROWS[:10]
    }
    ctrl = AminachController(MagicMock(motor_count=3))
    assert not ctrl.supports_preset_flat and not ctrl.supports_memory_presets
    assert not ctrl.supports_memory_programming and ctrl.memory_slot_count == 0
    assert not ctrl.supports_massage and not ctrl.supports_light_toggle_control
    assert not ctrl.supports_single_address_pairing
    assert ctrl.execution.concurrent == frozenset()
    assert [
        (s.key, s.name, s.entity_registry_enabled_default)
        for s in ctrl.controller_button_specs
        if not s.release_only
    ] == [("sleep", "Sleep", True), ("light", "Light", True), ("memo", "Memo", True)]


@pytest.mark.parametrize(
    ("count", "axes"), [(1, ("back",)), (2, ("back", "legs")), (3, ("back", "legs", "head"))]
)
async def test_layout_gates_every_motor_and_native_key(hass, count, axes):
    ctrl, c = await connected(hass, count)
    assert tuple(s.key for s in ctrl.motor_control_specs) == axes
    with virtual_clock():
        for spec in ctrl.motor_control_specs:
            for direction, fn in (("up", spec.open_fn), ("down", spec.close_fn)):
                c.client.write_gatt_char.reset_mock()
                await fn(ctrl)
                assert written(c.client) == [app.PLATINUM.frame(f"{spec.key}_{direction}")] * 2 + [
                    app.PLATINUM.frame("release")
                ]
                assert spec.hold.stop_scope == "side"
        for spec in ctrl.controller_button_specs:
            if spec.release_only:
                continue
            c.client.write_gatt_char.reset_mock()
            await spec.press_fn(ctrl)
            assert written(c.client)[0] == app.PLATINUM.frame(spec.key)
            assert written(c.client)[-1] == app.PLATINUM.frame("release")
    if count == 1:
        with pytest.raises(Exception, match="cannot hold"):
            await ctrl.hold_control("legs_up", 100)


@pytest.mark.parametrize(
    ("props", "response"),
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), False),
    ],
)
async def test_runtime_write_mode_and_exact_characteristic(hass, props, response):
    ctrl, c = await connected(hass, properties=props)
    await ctrl.stop_all()
    call = c.client.write_gatt_char.call_args
    assert call.args[0] is c.client.services[0].characteristics[0]
    assert call.kwargs["response"] is response


async def test_notification_requires_fixed_roles(hass):
    ctrl, c = await connected(hass)
    await ctrl.stop_notify()
    c.client.services = gatt(("read",))
    with pytest.raises(ConnectionError):
        await ctrl.start_notify()
    with pytest.raises(ConnectionError):
        await ctrl.stop_all()


async def test_exact_request_recognition_and_opaque_indicator(hass):
    ctrl, c = await connected(hass)
    receive(c, b"\xb2\x02\x01\x00")
    for data in (
        b"",
        codec.ADDRESS_REQUEST[:-1],
        codec.ADDRESS_REQUEST + b"\0",
        bytes.fromhex("b0 02 01 00 b4"),
    ):
        receive(c, data)
    await hass.async_block_till_done()
    assert not written(c.client)
    assert ctrl.protocol_diagnostics["title_indicator"] is None
    receive(c, codec.ADDRESS_REQUEST)
    receive(c, codec.ADDRESS_REQUEST)
    await hass.async_block_till_done()
    assert written(c.client) == [bytes.fromhex(ROWS[10]["expected_bytes"])]
    assert ctrl.protocol_diagnostics["recognized"]
    for data in (b"\xb2", b"\xb2\x02\x01", b"\xb2\x02\x09\x00"):
        receive(c, data)
    assert ctrl.protocol_diagnostics["title_indicator"] is None
    receive(c, b"\xb2\x02\x01\xff\x99")
    assert ctrl.protocol_diagnostics["title_indicator"] == 1
    assert not c.handle_controller_state_updates.called
    receive(c, codec.ADDRESS_REQUEST)
    await hass.async_block_till_done()
    assert len(written(c.client)) == 1


async def test_response_and_old_notifications_never_cross_sessions(hass):
    ctrl, c = await connected(hass)
    old_callback = c.client.start_notify.call_args.args[1]
    await ctrl.ble_lock.acquire()
    receive(c, codec.ADDRESS_REQUEST)
    await asyncio.sleep(0)
    ctrl.on_disconnect()
    old = c.client
    c.client = client()
    with patch.object(ctrl, "_adapter_address", return_value=LOCAL_ADDRESS):
        await ctrl.start_notify()
    ctrl.ble_lock.release()
    old_callback(None, bytearray(codec.ADDRESS_REQUEST))
    await hass.async_block_till_done()
    assert not written(old) and not written(c.client)
    assert not ctrl.protocol_diagnostics["recognized"]


async def test_unknown_initiator_does_not_substitute_the_bed_address(hass):
    ctrl, c = await connected(hass)
    ctrl._link.adapter_address = None
    receive(c, codec.ADDRESS_REQUEST)
    await hass.async_block_till_done()
    assert not written(c.client)
    with virtual_clock():
        await ctrl.press("sleep")
    assert written(c.client) == [app.PLATINUM.frame("sleep"), app.PLATINUM.frame("release")]


@pytest.mark.parametrize(
    ("transport", "domain", "reported", "expected"),
    [
        (TransportClass.LOCAL, None, None, LOCAL_ADDRESS),
        (TransportClass.PROXY, "esphome", "22:33:44:55:66:77", "22:33:44:55:66:77"),
        (TransportClass.PROXY, "esphome", "", None),
        (TransportClass.UNKNOWN, None, None, None),
    ],
)
def test_actual_initiator_address_has_proven_transport_identity(
    transport, domain, reported, expected
):
    ctrl = AminachController(MagicMock(motor_count=3))
    c = SimpleNamespace(
        _backend=SimpleNamespace(_device_info=SimpleNamespace(bluetooth_mac_address=reported))
    )
    path = ConnectionPath(source=LOCAL_ADDRESS, transport=transport, source_domain=domain)
    with (
        patch(
            "custom_components.adjustable_bed.beds.aminach.client_source",
            return_value=LOCAL_ADDRESS,
        ),
        patch(
            "custom_components.adjustable_bed.beds.aminach.async_path_for_source", return_value=path
        ),
    ):
        assert ctrl._adapter_address(c) == expected


@pytest.mark.parametrize("action", ["back_up", "memo"])
@pytest.mark.parametrize("task_cancel", [False, True])
async def test_hold_cleanup_survives_event_and_task_cancellation(hass, action, task_cancel):
    ctrl, c = await connected(hass)
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()
        times = []

        async def write(*args, **kwargs):
            times.append(round((loop.time() - start) * 1000))

        c.client.write_gatt_char.side_effect = write
        task = asyncio.create_task(ctrl.hold_control(action, 1000))
        await asyncio.sleep(0.02)
        if task_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            c.cancel_command.set()
            await task
    assert written(c.client) == [app.PLATINUM.frame(action), app.PLATINUM.frame("release")]
    assert times[-1] == 20


async def test_write_failure_still_releases_and_replaced_link_is_not_released(hass):
    ctrl, c = await connected(hass)
    c.client.write_gatt_char.side_effect = [RuntimeError("failed"), None]
    with virtual_clock(), pytest.raises(RuntimeError, match="failed"):
        await ctrl.hold_control("back_up", 100)
    assert written(c.client)[-1] == app.PLATINUM.frame("release")
    c.client.write_gatt_char.reset_mock(side_effect=True)

    async def replace_link(*args, **kwargs):
        ctrl.on_disconnect()
        c.client = client()

    old = c.client
    old.write_gatt_char.side_effect = replace_link
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.hold_control("back_up", 100)
    assert written(old) == [app.PLATINUM.frame("back_up")]
    assert not written(c.client)


@pytest.mark.parametrize("count", [1, 2, 3])
async def test_manual_app_setup_and_side_ownership(hass, count):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _motor_count_options,
    )
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from tests.form_helpers import finish_new_bed, suggested

    assert _motor_count_options("aminach") == [1, 2, 3]
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._finish_with_verify = AsyncMock()
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["aminach"]})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:FF"})
    assert result["step_id"] == "profile_questions"
    assert suggested(result, const.CONF_MOTOR_COUNT) == 3
    result = await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: count})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == count
    assert saved[const.CONF_HAS_MASSAGE] is False
    assert saved[const.CONF_MOTOR_PULSE_DELAY_MS] == 170
    assert per_side_profile("aminach", "auto").keys == frozenset({const.CONF_MOTOR_COUNT})


@pytest.mark.parametrize(
    ("name", "matches"),
    [("AMB2", True), ("AMB2-123", True), ("amb2-123", False), ("AMB", False), ("Other", False)],
)
def test_exact_name_prefix_is_only_an_app_hint(name, matches):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
    assert (result.bed_type == "aminach") is matches
    if matches:
        assert result.confidence < 0.7


@pytest.mark.parametrize(
    ("action", "expected"), [("back_up", [0, 170, 340, 400]), ("memo", [0, 90, 180, 270, 360, 400])]
)
async def test_immediate_first_refresh_and_release_cadence(hass, action, expected):
    ctrl, c = await connected(hass)
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()
        times = []

        async def write(*args, **kwargs):
            times.append(round((loop.time() - start) * 1000))

        c.client.write_gatt_char.side_effect = write
        await ctrl.hold_control(action, 400)
    assert times == expected
    assert written(c.client) == [app.PLATINUM.frame(action)] * (len(expected) - 1) + [
        app.PLATINUM.frame("release")
    ]


async def test_native_entities_send_all_reachable_control_literals(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    mock_bleak_client.services = gatt()
    address = "AA:BB:CC:DD:01:53"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Platinum",
        unique_id=address,
        data={
            "address": address,
            "name": "Platinum",
            const.CONF_BED_TYPE: "aminach",
            const.CONF_MOTOR_COUNT: 3,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_PROTOCOL_VARIANT: "auto",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not mock_bleak_client.read_gatt_char.called
    entities = [
        e for e in er.async_get(hass).entities.values() if e.config_entry_id == entry.entry_id
    ]
    assert not any(e.domain == "light" for e in entities)
    assert not any("preset_memory" in e.unique_id or "preset_flat" in e.unique_id for e in entities)
    with virtual_clock():
        for action in ("sleep", "light", "memo"):
            entity = next(e for e in entities if e.unique_id.endswith("_" + action))
            assert not entity.disabled_by
            await hass.services.async_call(
                "button", "press", {"entity_id": entity.entity_id}, blocking=True
            )
        for axis in app.LAYOUTS[3]:
            cover = next(
                e for e in entities if e.domain == "cover" and e.unique_id.endswith("_" + axis)
            )
            for service in ("open_cover", "close_cover"):
                await hass.services.async_call(
                    "cover", service, {"entity_id": cover.entity_id}, blocking=True
                )
    assert {bytes.fromhex(row["expected_bytes"]) for row in ROWS[:10]} <= set(
        written(mock_bleak_client)
    )


async def test_adapter_response_redacts_trace_and_debug_log_without_changing_wire(hass, caplog):
    import logging

    ctrl, c = await connected(hass)
    caplog.set_level(logging.DEBUG, logger="custom_components.adjustable_bed.beds.gatt_write")
    receive(c, codec.ADDRESS_REQUEST)
    await hass.async_block_till_done()
    frame = codec.adapter_response(LOCAL_ADDRESS)
    assert written(c.client) == [frame]
    payload = c.record_command_trace.call_args.kwargs["payload"]
    assert payload == {"redacted": True, "length": 10, "action": "Initiator adapter address"}
    assert frame.hex() not in caplog.text
    assert LOCAL_ADDRESS.replace(":", "").lower() not in caplog.text.lower()
    assert "REDACTED" in caplog.text
    await ctrl.stop_all()
    assert (
        c.record_command_trace.call_args.kwargs["payload"]["hex"]
        == app.PLATINUM.frame("release").hex()
    )


@pytest.mark.parametrize("entrypoint", ["detect_new_bed", "detect_bed_type_detailed"])
@pytest.mark.parametrize(
    ("name", "services", "expected"),
    [
        ("AMB2", ["32112022-0177-49cf-a554-254de334cae2"], "paramount"),
        ("AMB2 keyboard", [], None),
        ("AMB2 speaker", [app.SERVICE], None),
    ],
)
def test_app_hint_preserves_strong_services_and_exclusions(entrypoint, name, services, expected):
    from custom_components.adjustable_bed import detection
    from tests.test_detection import _make_service_info

    result = getattr(detection, entrypoint)(_make_service_info(name=name, service_uuids=services))
    assert result.bed_type == expected
    if expected is not None:
        assert result.confidence == 1.0
        assert "aminach" in result.ambiguous_types
    else:
        assert any(s.startswith("excluded:") for s in result.signals)
        assert "aminach" not in (result.ambiguous_types or ())


@pytest.fixture
async def scheduled_bed(hass):
    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Platinum",
        unique_id="AA:BB:CC:DD:15:30",
        data={
            "address": "AA:BB:CC:DD:15:30",
            "name": "Platinum",
            "bed_type": "aminach",
            "motor_count": 3,
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    co = AdjustableBedCoordinator(hass, entry)
    c = client()
    c.disconnect = AsyncMock(side_effect=lambda: setattr(c, "is_connected", False))
    co._client = c
    ctrl = AminachController(co)
    co._controller = co._offline_controller = ctrl
    co._ready = True
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = co
    with patch.object(ctrl, "_adapter_address", return_value=LOCAL_ADDRESS):
        await ctrl.start_notify()
    try:
        yield co, ctrl, c
    finally:
        await co.async_shutdown()


@pytest.mark.parametrize("later_stop", [False, True])
async def test_quick_dashboard_memo_release_keeps_refresh_until_minimum_unless_stopped(
    scheduled_bed, later_stop
):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.command_scheduler import HoldLease

    co, ctrl, c = scheduled_bed
    release_spec = next(s for s in ctrl.controller_button_specs if s.release_only)
    memo_spec = next(s for s in ctrl.controller_button_specs if s.key == "memo")
    assert memo_spec.hold.release_button_key == release_spec.key
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()
        times = []

        async def write(*args, **kwargs):
            times.append(round((loop.time() - start) * 1000))

        c.write_gatt_char.side_effect = write
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 750),
                lease=HoldLease("test-card", 1, "memo", 0.75),
            )
        )
        await asyncio.sleep(0.02)
        released = asyncio.create_task(ControllerActionButton(co, release_spec).async_press())
        if later_stop:
            await asyncio.sleep(0.03)
            await co.async_stop_command()
        await released
        await hold
    assert written(c)[0] == app.PLATINUM.frame("memo")
    assert all(
        frame == app.PLATINUM.frame("release") for frame in written(c)[2 if not later_stop else 1 :]
    )
    if later_stop:
        assert times[1] == 50
        assert written(c).count(app.PLATINUM.frame("memo")) == 1
    else:
        assert written(c) == [app.PLATINUM.frame("memo")] * 2 + [app.PLATINUM.frame("release")]
        assert times == [0, 90, 160]


@pytest.mark.parametrize("release_fails", [False, True])
async def test_failed_memo_minimum_refresh_still_releases(scheduled_bed, release_fails, caplog):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.command_scheduler import HoldLease

    co, ctrl, c = scheduled_bed
    release_spec = next(s for s in ctrl.controller_button_specs if s.release_only)
    original_frame = ctrl._frame
    memo_writes = 0
    releases = 0
    caplog.set_level("DEBUG", logger="custom_components.adjustable_bed.beds.aminach")

    async def frame(link, payload, cancel, **kwargs):
        nonlocal memo_writes, releases
        if payload == app.PLATINUM.frame("memo"):
            memo_writes += 1
            if memo_writes == 2:
                raise BleakError("Memo refresh failed")
        if payload == app.PLATINUM.frame("release"):
            releases += 1
            if release_fails:
                raise BleakError("Memo release failed")
        await original_frame(link, payload, cancel, **kwargs)

    with virtual_clock(), patch.object(ctrl, "_frame", side_effect=frame):
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 750),
                lease=HoldLease("test-card", 1, "memo", 0.75),
            )
        )
        await asyncio.sleep(0.02)
        await ControllerActionButton(co, release_spec).async_press()
        with pytest.raises(BleakError, match="Memo refresh failed"):
            await hold
    assert memo_writes == 2
    assert releases == 1
    assert written(c) == [app.PLATINUM.frame("memo")] + (
        [] if release_fails else [app.PLATINUM.frame("release")]
    )
    if release_fails:
        assert "Memo release failed after an earlier operation failure" in caplog.text


async def test_explicit_stop_interrupts_memo_without_minimum_refresh(scheduled_bed):
    co, ctrl, c = scheduled_bed
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()
        times = []

        async def write(*args, **kwargs):
            times.append(round((loop.time() - start) * 1000))

        c.write_gatt_char.side_effect = write
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 5000)
            )
        )
        await asyncio.sleep(0.02)
        await co.async_stop_command()
        await hold
    assert times[1] == 20
    assert written(c).count(app.PLATINUM.frame("memo")) == 1
    assert all(frame == app.PLATINUM.frame("release") for frame in written(c)[1:])


async def test_short_finite_memo_keeps_refresh_for_the_minimum(hass):
    ctrl, c = await connected(hass)
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()
        times = []

        async def write(*args, **kwargs):
            times.append(round((loop.time() - start) * 1000))

        c.client.write_gatt_char.side_effect = write
        await ctrl.hold_control("memo", 100)
    assert times == [0, 90, 160]
    assert written(c.client) == [app.PLATINUM.frame("memo")] * 2 + [app.PLATINUM.frame("release")]


async def test_memo_normal_release_before_first_write_never_starts_followup(scheduled_bed):
    from custom_components.adjustable_bed.button import ControllerActionButton

    co, ctrl, c = scheduled_bed
    release_spec = next(s for s in ctrl.controller_button_specs if s.release_only)
    with virtual_clock():
        await ctrl.ble_lock.acquire()
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 5000)
            )
        )
        await asyncio.sleep(0.02)
        released = asyncio.create_task(ControllerActionButton(co, release_spec).async_press())
        await asyncio.sleep(0.03)
        ctrl.ble_lock.release()
        await released
        await hold
    assert written(c) == [app.PLATINUM.frame("release")]


async def test_later_stop_fences_memo_refresh_already_waiting_for_ble_lock(scheduled_bed):
    from custom_components.adjustable_bed.button import ControllerActionButton

    co, ctrl, c = scheduled_bed
    release_spec = next(s for s in ctrl.controller_button_specs if s.release_only)
    with virtual_clock():
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 5000)
            )
        )
        await asyncio.sleep(0.02)
        await ctrl.ble_lock.acquire()
        released = asyncio.create_task(ControllerActionButton(co, release_spec).async_press())
        await asyncio.sleep(0.08)
        stopped = asyncio.create_task(co.async_stop_command())
        await asyncio.sleep(0.02)
        ctrl.ble_lock.release()
        await stopped
        await released
        await hold
    assert written(c)[0] == app.PLATINUM.frame("memo")
    assert written(c).count(app.PLATINUM.frame("memo")) == 1
    assert all(frame == app.PLATINUM.frame("release") for frame in written(c)[1:])


async def test_replacement_preempts_memo_minimum_refresh(scheduled_bed):
    from custom_components.adjustable_bed.button import ControllerActionButton

    co, ctrl, c = scheduled_bed
    release_spec = next(s for s in ctrl.controller_button_specs if s.release_only)
    with virtual_clock():
        hold = asyncio.create_task(
            co.async_execute_controller_command(
                lambda controller: controller.hold_control("memo", 5000)
            )
        )
        await asyncio.sleep(0.02)
        released = asyncio.create_task(ControllerActionButton(co, release_spec).async_press())
        await asyncio.sleep(0.03)
        await co.async_execute_controller_command(lambda controller: controller.press("sleep"))
        await released
        await hold
    assert written(c) == [
        app.PLATINUM.frame("memo"),
        app.PLATINUM.frame("release"),
        app.PLATINUM.frame("sleep"),
        app.PLATINUM.frame("release"),
    ]
