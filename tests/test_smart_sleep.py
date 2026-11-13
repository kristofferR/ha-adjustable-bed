"""Smart Sleep's real controller, setup, entity, service and session boundaries."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.smart_sleep import state_keys as state
from custom_components.adjustable_bed.beds.smart_sleep.controller import SmartSleepController
from custom_components.adjustable_bed.codec import smart_sleep as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import smart_sleep as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.test_controller_contract import _FactoryCoordinator

ALARM = bytes.fromhex("2a0000038107017f0901061e00")
LIGHT = bytes.fromhex("2a0000048106020100000064")
MASSAGE = bytes.fromhex("2a00000281070313580226")
SETTINGS = bytes.fromhex("a50b000058020203040000000000010103000100")


def controller(fmt="p1", model=0):
    coord = _FactoryCoordinator()
    coord.entry.data[CONF_PRODUCT_TYPE] = str(model)
    coord.controller_state = ControllerState()
    coord.handle_controller_state_updates = lambda *updates: coord.controller_state.update(
        (u.key, u.value) for u in updates
    )
    coord.record_command_trace = MagicMock()
    coord.client = MagicMock(is_connected=True)
    write = MagicMock(uuid=codec.WRITE, handle=2, properties=["write"])
    notify = MagicMock(uuid=codec.NOTIFY, handle=3, properties=["notify"])
    service = MagicMock(uuid=codec.SERVICE)
    service.get_characteristic.side_effect = lambda uuid: {
        codec.WRITE: write,
        codec.NOTIFY: notify,
    }.get(uuid)
    coord.client.services.__iter__.side_effect = lambda: iter([service])
    coord.client.services.get_characteristic.return_value = None
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    coord.client.write_gatt_char = AsyncMock()
    ctrl = SmartSleepController(coord, app.PROFILES[fmt], model)
    return ctrl


@pytest.fixture
def no_delays():
    real_sleep = asyncio.sleep

    async def sleep(_delay):
        await real_sleep(0)

    with patch("custom_components.adjustable_bed.beds.smart_sleep.controller.asyncio.sleep", sleep):
        yield


@pytest.mark.parametrize("fmt,model", [("p1", model) for model in app.MODELS] + [("p2", 80)])
def test_model_capabilities_are_ui_gates_not_guessed_anatomy(fmt, model):
    ctrl = controller(fmt, model)
    assert ctrl.model == (80 if fmt == "p2" else model)
    assert [s.key for s in ctrl.motor_control_specs] == ["back", "legs", "head", "lumbar", "hips"]
    assert [app.AXES[s.key][0] for s in ctrl.motor_control_specs] == [1, 2, 3, 4, 5]
    assert ctrl.position_number_specs == ()
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.execution.concurrent
    assert ctrl.supports_memory_programming == (fmt == "p2")
    assert ctrl.supports_preset_tv == (fmt == "p2" or model != 8)
    assert ("ai_zero" in ctrl.presets) == (fmt == "p1" and model == 8)
    assert ctrl.supports_lights and ctrl.supports_massage


@pytest.mark.parametrize("model", app.MODELS)
def test_advertisement_original_byte_format_and_whole_reverse(model):
    payload = b"\x01\x02\x03\x04\x05\x06" + bytes((model - 1 if model else 90,))
    found = app.advertisement("XXSleep Bed", {89: payload}, "AA:BB")
    assert found == app.Advertisement(bytes(reversed(payload))[1:7].hex(), "p1", model)
    long = payload + b"\x10\x20\x30"
    assert (
        app.advertisement("SLEEP", {89: long}, "AA").identifier == bytes(reversed(long))[1:7].hex()
    )
    forced = app.advertisement("SLEEP", {89: b"\0" * 6 + b"\x81"}, "AA")
    assert forced.format == "p2" and forced.model == 80


def test_scan_case_company_short_fallback_and_receiver_precedence():
    from custom_components.adjustable_bed.detection import detect_bed_type

    assert app.advertisement("sleep", {89: bytes(7)}, "AA:BB") is None
    assert app.advertisement("SLEEP", {90: bytes(7)}, "AA:BB") is None
    assert app.advertisement("Sleep", {89: b"1"}, "AA:BB") == app.Advertisement("aabb", "p1", 0)

    def info(name, service_uuids=()):
        return SimpleNamespace(
            name=name,
            address="AA:BB",
            manufacturer_data={89: bytes(7)},
            service_uuids=service_uuids,
            service_data={},
        )

    assert detect_bed_type(info("Sleep bed")) == "smart_sleep"
    assert detect_bed_type(info("Sleep bed", (codec.SERVICE,))) == "smart_sleep"
    assert detect_bed_type(info("SLEEPBT")) is None
    assert detect_bed_type(info("unknown", (codec.SERVICE,))) != "smart_sleep"
    from custom_components.adjustable_bed.const import REVERIE_SERVICE_UUID

    assert detect_bed_type(info("Sleep bed", (REVERIE_SERVICE_UUID,))) == "reverie"


@pytest.mark.parametrize("enabled", [0, 1])
@pytest.mark.parametrize("length", [10, 11, 12, 13])
def test_a1_requires_all_six_alarm_fields_even_when_disabled(enabled, length):
    frame = bytearray(ALARM)
    frame[9] = enabled
    parsed = codec.parse(bytes(frame[:length]), "p2")
    if length < 13:
        assert parsed is None
    elif enabled:
        assert parsed == codec.AlarmState(True, 127, 9, (6, 30, 0))
    else:
        assert parsed == codec.AlarmState(False)


@pytest.mark.parametrize(
    "timer,expected", [("0000", (False, 0, 0, 0, 0)), ("0807", (True, 1, 2, 3, 2))]
)
def test_a3_legacy_page_projection(timer, expected):
    frame = bytes.fromhex("a50b0000" + timer + "020304") + bytes(11)
    parsed = codec.parse(frame, "p1")
    assert isinstance(parsed, codec.SettingsState)
    m = parsed.massage
    assert (m.on, m.wave, m.head, m.foot, m.timer_index) == expected
    assert not hasattr(m, "combined")


@pytest.mark.parametrize(
    "protocol,firmware,new",
    [
        ("SENSOR_VOICE", "1.1", True),
        ("SLEEPVOICE", "2.0", True),
        ("SENSOR_VOICE", "1.0", False),
        ("OTHER", "2.0", False),
        ("SLEEPVOICE", "bad", False),
    ],
)
def test_privacy_firmware_compatibility_is_not_the_format_bit(protocol, firmware, new):
    assert codec.privacy_compat(protocol, firmware) == new
    frame = bytes(18) + b"\x01\x00"
    parsed = codec.parse(b"\xa5\x0b" + frame[2:], "p2", new_privacy=new)
    assert parsed.privacy is (not new)


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_startup_reconnect_missing_replies_and_exact_roles(fmt):
    ctrl = controller(fmt)
    ctrl._wait_cancel = AsyncMock(return_value=False)
    await ctrl.async_on_connect(MagicMock())
    client = ctrl.client
    subscribed = client.start_notify.call_args.args
    assert subscribed[0].uuid == codec.NOTIFY
    frames = [c.args[1] for c in client.write_gatt_char.call_args_list]
    assert frames == ([codec.INITIALIZE] if fmt == "p2" else []) + [
        codec.query(fmt, "settings"),
        codec.query(fmt, "settings"),
        *([codec.query(fmt, "massage")] if fmt == "p2" else []),
        codec.query(fmt, "alarm"),
    ]
    assert all(
        c.kwargs["response"] is True and c.args[0].uuid == codec.WRITE
        for c in client.write_gatt_char.call_args_list
    )
    assert ctrl._coordinator.controller_state.get(state.ALARM_ON) is None
    old_callback = subscribed[1]
    await ctrl.stop_notify()
    client.stop_notify.assert_awaited_once()
    await ctrl.async_on_connect(MagicMock())
    assert client.start_notify.await_count == 2
    old_callback(subscribed[0], bytearray(ALARM))
    assert ctrl._coordinator.controller_state.get(state.ALARM_ON) is None
    new_callback = client.start_notify.call_args.args[1]
    new_callback(subscribed[0], bytearray(ALARM))
    assert ctrl._coordinator.controller_state.get(state.ALARM_ON) is (True if fmt == "p2" else None)


async def test_real_notification_fragment_coalesce_truncation_stale_disconnect_and_context():
    ctrl = controller("p2")
    await ctrl.start_notify()
    char, receive = ctrl.client.start_notify.call_args.args
    values = ctrl._coordinator.controller_state
    receive(char, bytearray(ALARM[:10]))
    assert state.ALARM_ON not in values
    receive(char, bytearray(LIGHT))  # New frame discards the missing alarm tail.
    assert state.ALARM_ON not in values
    assert values[UNDER_BED_LIGHTS_ON] is True
    receive(char, bytearray(ALARM[:7]))
    receive(char, bytearray(ALARM[7:]))
    assert values[state.ALARM_ACTION] == 9
    receive(char, bytearray(MASSAGE + LIGHT))
    assert values[state.HEAD] == "2" and values[state.FOOT] == "3"
    assert values[state.TIMER] == "2"
    bad = bytearray(ALARM)
    bad[10] = 255
    receive(char, bad)
    assert values[state.ALARM_TIME] == "06:30:00"
    disabled = bytearray(ALARM)
    disabled[9] = 0
    receive(char, disabled)
    assert values[state.ALARM_ON] is False
    assert values[state.ALARM_ACTION] == 9  # Complete disable retains schedule.
    ctrl.on_disconnect()
    receive(char, bytearray(ALARM))
    assert values[state.ALARM_ON] is None
    await ctrl.start_notify()
    receive(char, bytearray(ALARM))
    assert values[state.ALARM_ON] is None
    fresh = ctrl.client.start_notify.call_args.args[1]
    with patch(
        "custom_components.adjustable_bed.beds.smart_sleep.controller.monotonic", side_effect=[0, 2]
    ):
        fresh(char, bytearray(ALARM[:8]))
        fresh(char, bytearray(ALARM[8:]))
    assert values[state.ALARM_ON] is None
    assert ctrl._replies.pending == b""


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_motor_pulses_use_configured_count_and_source_cadence_with_fresh_release(
    fmt, no_delays
):
    ctrl = controller(fmt)
    ctrl._coordinator.motor_pulse_count = 3
    ctrl._coordinator.motor_pulse_delay_ms = 999
    await ctrl.move_axis("hips", True)
    frames = [c.args[1] for c in ctrl.client.write_gatt_char.call_args_list]
    assert frames == [codec.motion(fmt, 5, True)] * 3 + [codec.stop(fmt, motor=True)]
    assert not ctrl._coordinator.cancel_command.is_set()
    ctrl._coordinator.cancel_command.set()
    ctrl.select_child("on")
    await ctrl.stop_all()
    assert ctrl.client.write_gatt_char.call_args.args[1] == codec.stop(fmt)
    with pytest.raises(ValueError, match="child"):
        await ctrl.move_back_up()


async def test_coordinator_cancellation_drains_immutable_cleanup(no_delays):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl = controller("p1")
    released, finish = asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.sleep

    async def delay(_seconds):
        released.set()
        await finish.wait()

    ctrl._coordinator.motor_pulse_count = 1
    with patch("custom_components.adjustable_bed.beds.smart_sleep.controller.asyncio.sleep", delay):
        operation = asyncio.create_task(ctrl.move_back_up())
        waiter = asyncio.create_task(
            AdjustableBedCoordinator._async_wait_for_controller_operation(
                ctrl._coordinator,
                operation,
                cancel_event=ctrl._coordinator.cancel_command,
                operation_name="smart_sleep",
                raise_on_cancel=False,
            )
        )
        await released.wait()
        ctrl.select_child("on")
        ctrl._coordinator.cancel_command.set()
        for _ in range(3):
            await real_sleep(0)
        operation.cancel()
        await real_sleep(0)
        assert not waiter.done()
        finish.set()
        await waiter
    assert [c.args[1] for c in ctrl.client.write_gatt_char.call_args_list] == [
        codec.motion("p1", 1, True),
        codec.stop("p1", motor=True),
    ]


async def test_release_never_moves_to_replacement_connection(no_delays):
    ctrl = controller("p1")
    old = ctrl.client

    async def replace_connection(_seconds):
        ctrl._coordinator.client = MagicMock(is_connected=True)
        ctrl.on_disconnect()

    ctrl._coordinator.motor_pulse_count = 1
    with patch(
        "custom_components.adjustable_bed.beds.smart_sleep.controller.asyncio.sleep",
        replace_connection,
    ):
        await ctrl.move_back_up()
    assert old.write_gatt_char.await_count == 1
    assert not ctrl.client.write_gatt_char.called


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_all_real_entity_specs_build_and_actions_reach_wire(fmt, no_delays):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.cover import _build_cover_description

    ctrl = controller(fmt)
    ctrl._wait_cancel = AsyncMock(return_value=False)
    ctrl._massage = codec.MassageState(True, 1, 1, 1, 1, 0)
    for spec in ctrl.motor_control_specs:
        description = _build_cover_description(spec)
        await description.open_fn(ctrl)
        await description.close_fn(ctrl)
    for spec in ctrl.controller_button_specs:
        runtime = MagicMock()
        runtime.capability_controller = ctrl
        runtime.controller = ctrl

        async def execute(command, **kwargs):
            await command(ctrl)

        runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
        entity = ControllerActionButton(runtime, spec)
        entity.hass = ctrl._coordinator.hass
        with patch(
            "custom_components.adjustable_bed.button.invalidate_on_command",
            side_effect=lambda _hass, command: command,
        ):
            await entity.async_press()
        runtime.async_execute_controller_command.assert_awaited_once()
    for spec in ctrl.controller_select_specs:
        if spec.key == "smart_sleep_child_mode":
            continue
        await spec.select_fn(ctrl, spec.options[-1])
    frames = {c.args[1] for c in ctrl.client.write_gatt_char.call_args_list}
    assert all(
        codec.motion(fmt, axis, up) in frames for axis in range(1, 6) for up in (True, False)
    )
    assert codec.privacy(True) in frames
    assert codec.antisnore(True, 6, demo=True) in frames
    assert all(bytes.fromhex(h) not in frames for h in ("01b101", "01b102", "01b301", "01b401"))


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_light_gesture_and_exact_save_exposure(fmt, no_delays):
    ctrl = controller(fmt)
    if fmt == "p1":
        await ctrl.lights_toggle()
        with pytest.raises(ValueError):
            await ctrl.program_memory(1)
    else:
        await ctrl.lights_on()
        for name in codec.PRESETS:
            if name != "flat":
                await ctrl.save(name)
        ctrl._light = codec.LightState(1, 0)  # Display off, but toggle follows raw state.
        await ctrl.lights_toggle()
        assert ctrl.client.write_gatt_char.call_args.args[1] == codec.light("p2", False)
    frames = [c.args[1] for c in ctrl.client.write_gatt_char.call_args_list]
    assert frames[:2] == [codec.stop(fmt), codec.light(fmt, True)]


async def test_alarm_real_service_preflights_all_targets_before_any_write(hass):
    from custom_components.adjustable_bed.beds.smart_sleep.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    register_services(hass)
    first, second = controller("p1", 67), controller("p2")
    targets = []
    for ctrl in (first, second):
        target = MagicMock(spec=AdjustableBedCoordinator)
        target.name = "Smart Sleep"
        target.controller_side = None
        target.bed_type = "smart_sleep"
        target.capability_controller = ctrl

        async def execute(command, ctrl=ctrl, **kwargs):
            await command(ctrl)

        target.async_execute_controller_command = AsyncMock(side_effect=execute)
        targets.append((target, SIDE_BOTH))
    first.configure_clock_alarm = AsyncMock()
    second.configure_clock_alarm = AsyncMock()
    data = {
        "device_id": ["one", "two"],
        "enabled": True,
        "time": "06:30:00",
        "action": "memory_1",
        "flexible_wake": True,
    }
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        with pytest.raises(Exception, match="Flexible wake"):
            await hass.services.async_call(DOMAIN, "smart_sleep_set_alarm", data, blocking=True)
        first.configure_clock_alarm.assert_not_awaited()
        second.configure_clock_alarm.assert_not_awaited()
        data["flexible_wake"] = False
        await hass.services.async_call(DOMAIN, "smart_sleep_set_alarm", data, blocking=True)
        assert (
            first.configure_clock_alarm.await_count == second.configure_clock_alarm.await_count == 1
        )
        second.select_child("on")
        with pytest.raises(Exception, match="child"):
            await hass.services.async_call(DOMAIN, "smart_sleep_set_alarm", data, blocking=True)
        assert first.configure_clock_alarm.await_count == 1


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_explicit_app_picker_setup_and_side_owned_fields(hass, fmt):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await flow.async_step_select_app()
    picker = next(v for k, v in form["data_schema"].schema.items() if k == CONF_BED_TYPE)
    label = next(label for label, value in picker.rows().items() if value == "smart_sleep")
    assert "OKIN Smart Sleep" in label
    await flow.async_step_select_app({CONF_BED_TYPE: label})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:94"})
    await finish_new_bed(
        flow, result, {CONF_PROTOCOL_VARIANT: fmt, CONF_PRODUCT_TYPE: "67" if fmt == "p1" else "80"}
    )
    saved = flow._finish_with_verify.await_args.args[0]
    coord = _FactoryCoordinator()
    coord.entry.data = saved
    ctrl = await create_controller(coord, "smart_sleep", fmt, None)
    assert ctrl.profile.key == fmt
    assert ctrl.model == (67 if fmt == "p1" else 80)
    assert {CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT} <= per_side_profile("smart_sleep", fmt).keys


def test_alarm_wire_actions_ui_mismatch_raw_week_and_model_gate():
    ctrl = controller("p2")
    for name, value in {**app.ALARM_ACTIONS, **app.APP_ALARM_LABELS}.items():
        frame = ctrl.alarm_frame(
            enabled=True,
            weekdays=(),
            hour=6,
            minute=30,
            preset=name,
            week_mask=255,
            now=datetime(2026, 11, 12, 12),
        )
        assert frame[7] == 255 and frame[8] == codec.wrap(value, 1, 9)
    assert (
        ctrl.alarm_frame(
            enabled=True,
            weekdays=(0, 6),
            hour=6,
            minute=30,
            preset="memory_1",
            now=datetime(2026, 11, 12, 12),
        )[7]
        == 6
    )
    first = controller("p1", 3)
    with pytest.raises(ValueError, match="67"):
        first.alarm_frame(
            enabled=True, weekdays=(), hour=6, minute=30, preset="flat", flexible=True
        )
    second = controller("p1", 67)
    assert (
        second.alarm_frame(
            enabled=True, weekdays=(), hour=6, minute=30, preset="flat", flexible=True
        )[-1]
        == 1
    )


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_coordinator_owns_startup_reconnect_and_retained_entities(
    hass, mock_coordinator_connected, mock_establish_connection, fmt
):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    template = controller(fmt)
    client = template.client
    mock_establish_connection.side_effect = None
    mock_establish_connection.return_value = client
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: client.address,
            CONF_BED_TYPE: "smart_sleep",
            CONF_PROTOCOL_VARIANT: fmt,
            CONF_PRODUCT_TYPE: "67" if fmt == "p1" else "80",
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
            "idle_disconnect_seconds": 0,
        },
    )
    # Give the mocked transport the real stable test address.
    client.address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(domain=DOMAIN, data={**entry.data, CONF_ADDRESS: client.address})
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    assert coord._connection_timeout == 5

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    with patch.object(SmartSleepController, "_wait_cancel", new=AsyncMock(return_value=False)):
        assert await coord.async_connect()
        live = coord.controller
        assert isinstance(live, SmartSleepController)
        keys = [s.key for s in live.motor_control_specs]
        callback = client.start_notify.call_args.args[1]
        char = client.start_notify.call_args.args[0]
        if fmt == "p2":
            callback(char, bytearray(ALARM))
            assert coord.controller_state[state.ALARM_ON] is True
        live.select_child("on")
        await coord.async_write_app_state(live, live.persisted_app_state)
        await coord.async_disconnect()
        assert client.stop_notify.await_count == 1
        assert coord.controller_state.get(state.ALARM_ON) is None
        client.is_connected = True
        assert await coord.async_connect()
        assert coord.controller is not live
        assert [s.key for s in coord.controller.motor_control_specs] == keys
        assert coord.controller.app.child
        callback(char, bytearray(ALARM))
        assert coord.controller_state.get(state.ALARM_ON) is None
        await coord.async_disconnect()
        await coord.async_shutdown()


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_actual_controller_lease_expiry_releases_after_more_than_finite_pulses(fmt):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        CommandKind,
        DeviceCommandScheduler,
        HoldLease,
        command_resources,
    )
    from tests.hold_lease_wire import virtual_clock

    ctrl = controller(fmt)
    ctrl._coordinator.motor_pulse_count = 1
    scheduler = DeviceCommandScheduler("smart-sleep-lease")

    async def run(context):
        ctrl._coordinator.cancel_command = context.cancel_event
        await ctrl.move_back_up()

    with virtual_clock():
        await scheduler.execute(
            CommandIntent(
                run,
                resources=command_resources("motor:back"),
                kind=CommandKind.HOLD,
                lease=HoldLease(owner="test", generation=1, action="back_up", duration_s=0.35),
            )
        )
    frames = [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list]
    assert frames[:-1] == [codec.motion(fmt, 1, True)] * 4
    assert frames[-1] == codec.stop(fmt, motor=True)


async def test_p2_bounded_preset_save_and_single_release_recall_without_real_timers():
    ctrl = controller("p2")
    ctrl._wait_cancel = AsyncMock(return_value=False)
    await ctrl.hold_control("preset_read", 5500)
    assert [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list] == [
        codec.preset("p2", "read", save=True),
        codec.stop("p2"),
        codec.preset("p2", "read"),
    ]
    assert ctrl.execution.hold_for("preset_read") is None
    assert ctrl.execution.hold_for("back_up") == "stream"


@pytest.mark.parametrize(
    "mask,scheduled,now,expected",
    [
        (0, datetime(2026, 11, 12, 6), datetime(2026, 11, 12, 12), 32),
        (128, datetime(2026, 11, 12, 13), datetime(2026, 11, 12, 12), 128),
        (21, datetime(2026, 11, 12, 6), datetime(2026, 11, 12, 12), 21),
        (0, datetime(2026, 11, 12, 12, 0, 0, 1), datetime(2026, 11, 12, 12), 32),
        (0, datetime(2026, 11, 14, 6), datetime(2026, 11, 14, 12), 1),
    ],
)
def test_source_week_formula_and_floored_equality(mask, scheduled, now, expected):
    assert codec.gain_week(mask, scheduled, now) == expected


def test_alarm_does_not_invent_tomorrow_before_app_week_conversion():
    ctrl = controller("p2")
    assert (
        ctrl.alarm_frame(
            enabled=True,
            weekdays=(),
            hour=6,
            minute=30,
            preset="memory_1",
            now=datetime(2026, 11, 12, 12),
        )[7]
        == 32
    )
    legacy = controller("p1")
    with pytest.raises(ValueError, match="week_mask"):
        legacy.alarm_frame(enabled=True, weekdays=(0,), hour=6, minute=30, preset="flat")
    assert (
        legacy.alarm_frame(
            enabled=True, weekdays=(0,), hour=6, minute=30, preset="flat", week_mask=129
        )[2]
        == 129
    )


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_child_mode_change_stops_refresh_but_not_release_or_shared_settings(fmt, no_delays):
    ctrl = controller(fmt)
    ctrl._coordinator.motor_pulse_count = 3

    async def write(_char, frame, **kwargs):
        if frame == codec.motion(fmt, 1, True):
            ctrl.select_child("on")

    ctrl.client.write_gatt_char.side_effect = write
    with pytest.raises(ValueError, match="child"):
        await ctrl.move_back_up()
    assert [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list] == [
        codec.motion(fmt, 1, True),
        codec.stop(fmt, motor=True),
    ]
    ctrl._wait_cancel = AsyncMock(return_value=False)
    await ctrl.select_option("privacy", "on")
    assert [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list[-2:]] == [
        codec.privacy(True),
        codec.query(fmt, "settings"),
    ]


@pytest.mark.parametrize(
    "day,expected", [(0, 4), (1, 8), (2, 16), (3, 32), (4, 64), (5, 1), (6, 2)]
)
def test_all_seven_frozen_week_bits(day, expected):
    instant = datetime(2026, 11, 9 + day, 6)
    assert codec.gain_week(128, instant, instant) == expected


@pytest.mark.parametrize("fmt", ["p1", "p2"])
def test_real_motor_covers_publish_usable_directional_hold_leases(hass, fmt):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    ctrl = controller(fmt)
    runtime = MagicMock()
    runtime.capability_controller = ctrl
    runtime.entity_side = None
    runtime.device_info = {}
    runtime.entity_unique_id.side_effect = lambda key: "smart_sleep_" + key

    covers = _cover_entities_for(hass, runtime)
    assert {cover.entity_description.key for cover in covers} == set(app.AXES)
    for cover in covers:
        attributes = cover.extra_state_attributes
        assert attributes["hold_lease_mode"] == "stream"
        for direction in ("up", "down"):
            control = attributes[f"held_control_{direction}"]
            assert ctrl.execution.hold_for(control) == "stream"
            ctrl.validate_hold_control(control, 750)
    if fmt == "p2":
        assert ctrl.execution.hold_for("preset_read") is None


@pytest.mark.parametrize("fmt", ["p1", "p2"])
async def test_real_memory_and_preset_entities_publish_card_routes(hass, fmt, no_delays):
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.button import (
        AdjustableBedButton,
        ControllerActionButton,
        _button_entities_for,
    )

    ctrl = controller(fmt)
    runtime = MagicMock()
    runtime.bed_type = "smart_sleep"
    runtime.controller_side = runtime.entity_side = None
    runtime.capability_controller = runtime.controller = ctrl
    runtime.has_massage = True
    runtime.device_info = {}
    runtime.entity_unique_id.side_effect = lambda key: "smart_sleep_" + key
    entities = _button_entities_for(hass, runtime)
    by_key = {
        entity.entity_description.key
        if isinstance(entity, AdjustableBedButton)
        else entity._spec.key: entity
        for entity in entities
        if isinstance(entity, (AdjustableBedButton, ControllerActionButton))
    }
    frozen = json.loads(
        (Path(__file__).parent / "fixtures/smart_sleep_button_holds.json").read_text()
    )[fmt]
    for key, expected in frozen.items():
        entity = by_key[key]
        actual = {
            key: value
            for key, value in entity.extra_state_attributes.items()
            if key.startswith(("held_", "hold_"))
        }
        assert actual == expected
        if fmt == "p1":
            ctrl.validate_hold_control(actual["held_control"], 750)
    if fmt == "p2":

        async def execute(command, **kwargs):
            await command(ctrl)

        runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
        entity = by_key["smart_sleep_read"]
        entity.hass = hass
        with patch(
            "custom_components.adjustable_bed.button.invalidate_on_command",
            side_effect=lambda _hass, command: command,
        ):
            await entity.async_press()
        assert [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list] == [
            codec.stop("p2"),
            codec.preset("p2", "read"),
        ]
        assert {"smart_sleep_save_read", "program_memory_1", "program_memory_2"} <= by_key.keys()
