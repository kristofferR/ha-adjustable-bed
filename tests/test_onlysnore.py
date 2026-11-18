"""Snore Monitor's actual setup, controller, entities and BED action paths."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.onlysnore import state_keys as state
from custom_components.adjustable_bed.beds.onlysnore.controller import OnlySnoreController
from custom_components.adjustable_bed.codec import onlysnore as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import onlysnore as app
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

STATUS = bytes.fromhex("a50b000059020304060000000000000107000006")
CONFIG_THREE = bytes.fromhex("a50a08000000000003")
ALARM = bytes.fromhex("a50e08007f05071e000101")
PARAMETERS = json.loads(
    (Path(__file__).parent / "fixtures" / "onlysnore" / "parameters.json").read_text()
)


@pytest.mark.parametrize("row", PARAMETERS)
def test_reachable_intervention_parameter_literals(row):
    assert codec.intervention(row["mode"], row["level"]) == bytes.fromhex(row["expected_bytes"])


def controller(model="unKnow", alarm_count=1, *, coordinator: _FactoryCoordinator | None = None):
    coord = coordinator if coordinator is not None else _FactoryCoordinator()
    coord.entry.data.update({CONF_BED_TYPE: "onlysnore", CONF_PRODUCT_TYPE: model})
    coord.controller_state = ControllerState()
    coord.handle_controller_state_updates = lambda *updates: coord.controller_state.update(
        (update.key, update.value) for update in updates
    )
    coord.record_command_trace = MagicMock()
    coord.motor_pulse_count = 1
    coord.client = MagicMock(is_connected=True, address="AA:BB:CC:DD:EE:FF")
    write = MagicMock(uuid=codec.WRITE, handle=2, properties=["write-without-response"])
    notify = MagicMock(uuid=codec.NOTIFY, handle=3, properties=["notify"])
    service = MagicMock(uuid=codec.SERVICE)
    service.get_characteristic.side_effect = lambda uuid: {
        codec.WRITE: write,
        codec.NOTIFY: notify,
    }.get(uuid)
    coord.client.services.__iter__.side_effect = lambda: iter([service])
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    coord.client.write_gatt_char = AsyncMock()
    ctrl = OnlySnoreController(coord, model, alarm_count)
    coord.controller = ctrl
    return ctrl


def frames(ctrl):
    return [call.args[1] for call in ctrl.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("model", app.MODELS)
def test_models_keep_proven_ui_without_guessed_sensing_or_side(model):
    ctrl = controller(model)
    assert ctrl.model == model
    assert list(app.AXES) == [spec.key for spec in ctrl.motor_control_specs]
    assert [app.AXES[spec.key] for spec in ctrl.motor_control_specs] == [
        "head",
        "foot",
        "lumbar",
        "headrest",
        "hips",
    ]
    assert ctrl.position_number_specs == ()
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.execution.concurrent
    assert ctrl.memory_slot_count == 2 and ctrl.supports_memory_programming
    assert ctrl.supports_lights and not ctrl.supports_discrete_light_control
    assert {s.key for s in ctrl.controller_select_specs} == {"onlysnore_intervention"}
    assert {s.key for s in ctrl.controller_switch_specs} == {
        "onlysnore_massage",
        "onlysnore_privacy",
        "onlysnore_detection",
    }


def test_discovery_reverses_before_slice_and_preserves_existing_service_precedence():
    from custom_components.adjustable_bed.const import REVERIE_SERVICE_UUID
    from custom_components.adjustable_bed.detection import detect_bed_type

    payload = bytes.fromhex("0123456789ab02")
    assert app.advertisement("sLeEp_v123", {89: payload}, "AB:89:67:45:23:01") == "double"
    assert codec.manufacturer(payload + bytes.fromhex("1020")) == ("1002ab896745", "double")
    assert codec.manufacturer(b"\x12\x34") == ("3412", "unKnow")
    for name, vendor, address in (
        ("SLEEP", {89: payload}, "AB:89:67:45:23:01"),
        ("SLEEP_V", {90: payload}, "AB:89:67:45:23:01"),
        ("SLEEP_V", {89: payload}, "00:00:00:00:00:00"),
        ("FP", {89: payload}, "AB:89:67:45:23:01"),
        ("SLEEP_V", {89: payload[:6] + b"\x0a"}, "AB:89:67:45:23:01"),
    ):
        assert app.advertisement(name, vendor, address) is None
    info = SimpleNamespace(
        name="SLEEP_V123",
        manufacturer_data={89: payload},
        address="AB:89:67:45:23:01",
        service_uuids=[],
        service_data={},
    )
    assert detect_bed_type(info) == "onlysnore"
    info.service_uuids = [REVERIE_SERVICE_UUID]
    assert detect_bed_type(info) == "reverie"


async def test_manual_setup_persisted_profile_factory_and_side_owned_model(hass):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profile_id import entry_profile_id, with_profile_ids
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await flow.async_step_select_app()
    picker = next(
        value for key, value in form["data_schema"].schema.items() if key == CONF_BED_TYPE
    )
    label = next(label for label, value in picker.rows().items() if value == "onlysnore")
    assert "Snore Monitor" in label
    await flow.async_step_select_app({CONF_BED_TYPE: label})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:FF"})
    await finish_new_bed(flow, result, {CONF_PRODUCT_TYPE: "double"})
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_PRODUCT_TYPE] == "double"
    saved = with_profile_ids(saved)
    assert entry_profile_id(saved) == "onlysnore"
    coord = _FactoryCoordinator()
    coord.entry.data = saved
    built = await create_controller(coord, "onlysnore", None, None)
    assert isinstance(built, OnlySnoreController) and built.model == "double"
    assert CONF_PRODUCT_TYPE in per_side_profile("onlysnore", None).keys


async def test_configure_and_restore_keep_model_independent_from_alarm_snapshot(hass):
    from custom_components.adjustable_bed.beds.builder import BuildContext
    from custom_components.adjustable_bed.beds.onlysnore.controller import build_controller
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES, _onlysnore_seed

    coordinator = _FactoryCoordinator()
    ctrl = controller("meise", coordinator=coordinator)
    data = coordinator.entry.data
    data["capabilities"] = {"onlysnore": {"alarm_count": 3}}
    ctx = BuildContext(
        coordinator=ctrl._coordinator, bed_type="onlysnore", variant=None, client=None
    )
    built = await build_controller(ctx)
    assert built.model == "meise" and built.capability_snapshot() == {"alarm_count": 3}
    assert len(built.controller_state_binary_sensor_specs) == 3
    assert len(SETUP_PROFILES["onlysnore"].questions) == 1
    discovered = SimpleNamespace(
        name="SLEEP_V",
        manufacturer_data={89: bytes.fromhex("0123456789ab02")},
        address="AB:89:67:45:23:01",
    )
    assert _onlysnore_seed(hass, data, discovered)[CONF_PRODUCT_TYPE] == "meise"
    assert _onlysnore_seed(hass, {}, discovered)[CONF_PRODUCT_TYPE] == "double"
    data[CONF_PRODUCT_TYPE] = "wifi"
    with pytest.raises(ValueError, match="model"):
        await build_controller(ctx)


async def test_actual_configure_preserves_restored_profile_and_owned_fields(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.profile_id import with_profile_ids
    from tests.test_setup_questions import entry_for

    entry = entry_for(
        hass,
        with_profile_ids(
            {
                CONF_BED_TYPE: "onlysnore",
                CONF_PRODUCT_TYPE: "dormimundo",
                "address": "AA:BB:CC:DD:EE:FF",
                "motor_count": 2,
                "has_massage": True,
                "disable_angle_sensing": True,
            }
        ),
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    assert "motor_count" not in {marker.schema for marker in form["data_schema"].schema}
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await flow._async_options_form({}, step_id="settings")
    assert entry.data[CONF_PRODUCT_TYPE] == "dormimundo"
    assert entry.data["profile_id"] == "onlysnore"
    assert entry.data["has_massage"] is True


async def test_optional_information_reads_publish_only_current_session():
    ctrl = controller()
    firmware = MagicMock(uuid=codec.FIRMWARE, properties=["read"])
    hardware = MagicMock(uuid=codec.HARDWARE, properties=["read"])
    bed_service = next(iter(ctrl.client.services))
    info = MagicMock(uuid="0000180a-0000-1000-8000-00805f9b34fb")
    info.get_characteristic.side_effect = lambda uuid: {
        codec.FIRMWARE: firmware,
        codec.HARDWARE: hardware,
    }.get(uuid)
    ctrl.client.services.__iter__.side_effect = lambda: iter([bed_service, info])
    ctrl.client.read_gatt_char = AsyncMock(side_effect=[b"1.2\0", b"BOX\0"])
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.async_on_connect(SimpleNamespace(is_current=lambda: True))
    assert ctrl._coordinator.controller_state[state.FIRMWARE] == "1.2"
    assert ctrl._coordinator.controller_state[state.HARDWARE] == "BOX"
    assert ctrl.client.read_gatt_char.call_args_list[0].args == (firmware,)


async def test_session_exact_startup_properties_and_no_sensing():
    ctrl = controller()
    await ctrl.read_positions(motor_count=5)
    delays = []

    async def wait(ms):
        delays.append(ms)
        return False

    ctrl._wait = wait
    with patch(
        "custom_components.adjustable_bed.beds.onlysnore.controller.dt_util.now",
        return_value=datetime(2026, 11, 17, 12, 34, 56),
    ):
        await ctrl.async_on_connect(SimpleNamespace(is_current=lambda: True))
    assert delays == [100, 300, 100]
    assert frames(ctrl) == [bytes.fromhex("07047e0a11010c2238"), b"\0\xb0", b"\0\xa0"]
    assert all(
        call.kwargs["response"] is False for call in ctrl.client.write_gatt_char.call_args_list
    )
    write = ctrl._role(codec.WRITE)
    write.properties = ["write"]
    with pytest.raises(ConnectionError, match="without response"):
        await ctrl.sync_clock()


async def test_notifications_state_writers_alarm_capability_and_stale_cache():
    ctrl = controller()
    await ctrl.start_notify()
    char, callback = ctrl.client.start_notify.call_args.args
    callback(char, bytearray(STATUS))
    assert ctrl._coordinator.controller_state[state.PRIVACY] == "on"
    assert ctrl._coordinator.controller_state[state.INTERVENTION] == "7"
    assert ctrl._coordinator.controller_state[state.MASSAGE] is True
    callback(char, bytearray(CONFIG_THREE))
    callback(char, bytearray(ALARM))
    assert ctrl._coordinator.controller_state[state.ALARM_COUNT] == 3
    assert ctrl._coordinator.controller_state[state.ALARM_TIME[2]] == "07:30"
    assert ctrl._coordinator.controller_state[state.ALARM_OPEN[2]] is True
    for length in range(20):
        assert codec.parse(STATUS[:length]) is None
    ctrl.on_disconnect()
    assert ctrl._status is None and ctrl._alarms == {}
    assert ctrl._coordinator.controller_state.get(state.PRIVACY) is None
    callback(char, bytearray(STATUS))
    assert ctrl._status is None
    await ctrl.start_notify()
    callback(char, bytearray(STATUS))
    assert ctrl._status is None
    new_char, new_callback = ctrl.client.start_notify.call_args.args
    new_callback(new_char, bytearray(STATUS))
    assert ctrl._status is not None
    ctrl._coordinator.controller = controller()
    new_callback(new_char, bytearray(CONFIG_THREE))
    assert ctrl._coordinator.controller_state.get(state.ALARM_COUNT) is None


async def test_real_specs_reach_wire_through_entities(hass):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.cover import _cover_entities_for

    ctrl = controller()
    runtime = MagicMock()
    runtime.capability_controller = runtime.controller = ctrl
    runtime.entity_side = runtime.controller_side = None
    runtime.device_info = {}
    runtime.entity_unique_id.side_effect = lambda key: "onlysnore_" + key

    async def execute(command, **kwargs):
        await command(ctrl)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    covers = _cover_entities_for(hass, runtime)
    assert len(covers) == 5
    for cover in covers:
        assert cover.extra_state_attributes["hold_lease_mode"] == "stream"
    with virtual_clock():
        for spec in ctrl.motor_control_specs:
            await spec.open_fn(ctrl)
            await spec.close_fn(ctrl)
        for spec in ctrl.controller_button_specs:
            entity = ControllerActionButton(runtime, spec)
            entity.hass = hass
            with patch(
                "custom_components.adjustable_bed.button.invalidate_on_command",
                side_effect=lambda _hass, command: command,
            ):
                await entity.async_press()
        for spec in ctrl.controller_select_specs:
            await spec.select_fn(ctrl, spec.options[-1])
        for spec in ctrl.controller_switch_specs:
            await spec.set_fn(ctrl, True)
        await ctrl.preset_reading()
        await ctrl.lights_toggle()
        await ctrl.program_memory(1)
        await ctrl.preset_memory(2)
    sent = set(frames(ctrl))
    assert {
        codec.control(app.KEYS[f"{axis}_{direction}"])
        for axis in app.AXES.values()
        for direction in ("up", "down")
    } <= sent
    assert codec.intervention(2, 1) in sent and codec.INTERVENTION_STOP in sent
    assert codec.setting(178, 1) in sent and codec.setting(181, 1) in sent
    assert codec.control(app.KEYS["memory_1"], save=True) in sent
    assert not {codec.setting(177, 1), codec.setting(177, 2), codec.setting(179, 1)} & sent


async def test_finite_deadline_inflight_latency_no_catchup_and_captured_release():
    ctrl = controller()
    original = ctrl.client.write_gatt_char
    times = []

    async def slow_write(*args, **kwargs):
        times.append(asyncio.get_running_loop().time())
        await original(*args, **kwargs)
        if args[1] != codec.control(0):
            await asyncio.sleep(0.4)

    ctrl.client.write_gatt_char = AsyncMock(side_effect=slow_write)
    with virtual_clock():
        await ctrl.hold_control("back_up", 300)
    assert frames(ctrl) == [codec.control(1), codec.control(0)]
    assert times[-1] - times[0] == pytest.approx(0.4)


async def test_renewable_hold_uses_scheduler_lease_beyond_single_pulse():
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        CommandKind,
        DeviceCommandScheduler,
        HoldLease,
        command_resources,
    )

    ctrl = controller()
    scheduler = DeviceCommandScheduler("onlysnore-test")

    async def run(context):
        ctrl._coordinator.cancel_command = context.cancel_event
        await ctrl.move_back_up()

    with virtual_clock():
        await scheduler.execute(
            CommandIntent(
                run,
                resources=command_resources("motor:back"),
                kind=CommandKind.HOLD,
                lease=HoldLease(owner="test", generation=1, action="back_up", duration_s=0.5),
            )
        )
    assert frames(ctrl) == [codec.control(1)] * 4 + [codec.control(0)]


async def test_preset_program_transition_and_plain_recall_never_saves():
    ctrl = controller()
    with virtual_clock():
        await ctrl.hold_control("preset_reading", 5700)
    sent = frames(ctrl)
    assert codec.control(app.KEYS["reading"]) in sent
    assert codec.control(app.KEYS["reading"], save=True) in sent
    assert sent[-1] == codec.control(0, save=True)
    ctrl.client.write_gatt_char.reset_mock()
    ctrl._coordinator.motor_pulse_count = 40
    with virtual_clock():
        await ctrl.preset_lounge()
    assert not any(frame[-1] == 15 for frame in frames(ctrl))
    assert not any(spec.key == "onlysnore_save_flat" for spec in ctrl.controller_button_specs)


async def test_cancel_during_release_drains_before_operation_finishes():
    ctrl = controller()
    started, finish = asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.sleep

    async def delay(_seconds):
        started.set()
        await finish.wait()

    ctrl._wait = AsyncMock(return_value=True)
    with patch("custom_components.adjustable_bed.beds.onlysnore.controller.asyncio.sleep", delay):
        task = asyncio.create_task(ctrl.move_back_up())
        await started.wait()
        task.cancel()
        await real_sleep(0)
        task.cancel()
        await real_sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(ctrl) == [codec.control(1), codec.control(0)]


async def test_queued_write_and_cleanup_cannot_retarget_replacement():
    ctrl = controller()
    old_client = ctrl.client
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.write_command(codec.control(1)))
    await asyncio.sleep(0)
    ctrl.on_disconnect()
    ctrl._coordinator.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    ctrl._ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    assert not old_client.write_gatt_char.called
    assert not ctrl.client.write_gatt_char.called


def test_alarm_restrictions_and_distinct_source_week_paths():
    now = datetime(2026, 11, 22, 12)
    single, triple = controller(), controller(alarm_count=3)
    assert single.alarm_frame(1, True, 7, 30, 0, 0, False, now=now)[2] == 2
    assert triple.alarm_frame(1, True, 7, 30, 0, 0, False, now=now, weekday_now=now)[2] == 0
    assert triple.alarm_frame(
        3, False, 7, 30, 0, 0, False, now=now, weekday_now=now
    ) == bytes.fromhex("07070001071e00000000")
    with pytest.raises(ValueError, match="slot"):
        single.alarm_frame(2, True, 7, 30, 0, 0, False)
    with pytest.raises(ValueError, match="Soft wake"):
        single.alarm_frame(1, True, 7, 30, 0, 0, True)


async def test_registered_alarm_service_validates_every_target_before_writes(hass):
    from custom_components.adjustable_bed.beds.onlysnore.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    register_services(hass)
    first, second = controller(alarm_count=3), controller()
    targets = []
    for ctrl in (first, second):
        ctrl._coordinator._position_connection_generation = 1
        target = MagicMock(spec=AdjustableBedCoordinator)
        target.name = "Snore Monitor"
        target.address = ctrl._coordinator.address
        target.bed_type = "onlysnore"
        target.entry = ctrl._coordinator.entry
        target.controller_side = None
        target.capability_controller = target.controller = ctrl
        target.client = ctrl.client
        target._position_connection_generation = 1
        target._command_scheduler = MagicMock(token=object())
        target.stop_epoch = 0
        ctrl._coordinator = target

        async def execute(command, ctrl=ctrl, **kwargs):
            await command(ctrl)

        target.async_execute_controller_command = AsyncMock(side_effect=execute)
        targets.append((target, SIDE_BOTH))
    first.set_alarm = AsyncMock()
    second.set_alarm = AsyncMock()
    data = {"device_id": ["one", "two"], "time": "07:30", "slot": 2}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        with pytest.raises(Exception, match="slot"):
            await hass.services.async_call(DOMAIN, "onlysnore_set_alarm", data, blocking=True)
        first.set_alarm.assert_not_awaited()
        second.set_alarm.assert_not_awaited()
        data["slot"] = 1
        await hass.services.async_call(DOMAIN, "onlysnore_set_alarm", data, blocking=True)
        first.set_alarm.assert_awaited_once()
        second.set_alarm.assert_awaited_once()


async def test_real_registry_parent_and_child_alarm_targets_keep_side_and_conflict(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.onlysnore.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import child_device_info

    register_services(hass)
    physical = {}
    for index, side in enumerate(("left", "right"), 1):
        address = f"AA:BB:CC:DD:EE:{index:02X}"
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=5,
            data={
                "address": address,
                CONF_BED_TYPE: "onlysnore",
                CONF_PRODUCT_TYPE: "single",
                "profile_id": "onlysnore",
                "disable_angle_sensing": True,
                "idle_disconnect_seconds": 0,
            },
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._client = controller().client
        coordinator._client.address = address

        async def disconnect(client=coordinator._client):
            client.is_connected = False

        coordinator._client.disconnect = AsyncMock(side_effect=disconnect)
        ctrl = OnlySnoreController(coordinator, "single")
        coordinator._controller = ctrl
        coordinator._position_connection_generation = 1
        coordinator.async_ensure_connected = AsyncMock(return_value=True)
        ctrl.set_alarm = AsyncMock()
        physical[side] = (coordinator, ctrl)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    pair_entry = MockConfigEntry(domain=DOMAIN, version=5, data={"pair_id": "onlysnore-registry"})
    pair_entry.add_to_hass(hass)
    pair_entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, pair_entry, {side: item[0] for side, item in physical.items()}
    )
    hass.data.setdefault(DOMAIN, {})[pair_entry.entry_id] = pair
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(config_entry_id=pair_entry.entry_id, **pair.device_info)
    children = {
        side: registry.async_get_or_create_child(
            config_entry_id=pair_entry.entry_id, **child_device_info(pair, side)
        )
        for side in physical
    }
    try:
        await hass.services.async_call(
            DOMAIN,
            "onlysnore_set_alarm",
            {"device_id": children["left"].id, "time": "07:30"},
            blocking=True,
        )
        physical["left"][1].set_alarm.assert_awaited_once()
        physical["right"][1].set_alarm.assert_not_awaited()
        with pytest.raises(Exception, match="conflicts"):
            await hass.services.async_call(
                DOMAIN,
                "onlysnore_set_alarm",
                {"device_id": children["left"].id, "side": "right", "time": "07:30"},
                blocking=True,
            )
        physical["left"][1].set_alarm.reset_mock()
        await hass.services.async_call(
            DOMAIN, "onlysnore_set_alarm", {"device_id": parent.id, "time": "07:30"}, blocking=True
        )
        physical["left"][1].set_alarm.assert_awaited_once()
        physical["right"][1].set_alarm.assert_awaited_once()
    finally:
        for coordinator, _ctrl in physical.values():
            await coordinator.async_shutdown()


async def test_stop_during_lazy_import_rejects_all_targets_before_execution(hass):
    from custom_components.adjustable_bed.beds.onlysnore.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    register_services(hass)
    ctrl = controller()
    target = MagicMock(spec=AdjustableBedCoordinator)
    target.address = ctrl._coordinator.address
    target.bed_type = "onlysnore"
    target.entry = ctrl._coordinator.entry
    target.client, target.controller = ctrl.client, ctrl
    target.capability_controller = ctrl
    target._position_connection_generation = 1
    target._command_scheduler = MagicMock(token=object())
    target.stop_epoch = 0
    target.async_execute_controller_command = AsyncMock()

    async def import_then_stop(*_args):
        target.stop_epoch += 1

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, SIDE_BOTH)], []),
        ),
        patch(
            "custom_components.adjustable_bed.beds.onlysnore.services.async_import_modules",
            side_effect=import_then_stop,
        ),
        pytest.raises(Exception, match="STOP"),
    ):
        await hass.services.async_call(
            DOMAIN, "onlysnore_set_alarm", {"device_id": "one", "time": "07:30"}, blocking=True
        )
    target.async_execute_controller_command.assert_not_awaited()
    assert frames(ctrl) == []


async def test_sequential_both_lease_rejects_before_claim_and_finite_buttons_remain():
    from custom_components.adjustable_bed.button import _combined_motor_buttons_for
    from custom_components.adjustable_bed.command_scheduler import HoldLease
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import _async_with_hold_lease

    ctrl = controller()
    parent = MagicMock(spec=PairedBedCoordinator)
    parent.connection_mode = "sequential"
    parent.pair_id = "onlysnore-pair"
    sides = [
        SimpleNamespace(controller_side=None, capability_controller=ctrl, bed_type="onlysnore")
        for _ in range(2)
    ]
    parent.children = dict(zip(("left", "right"), sides, strict=True))
    parent._targets_for.return_value = [("left", sides[0]), ("right", sides[1])]
    start = AsyncMock()
    with pytest.raises(Exception, match="concurrent|sequential|Both"):
        await _async_with_hold_lease(
            [(parent, "both")],
            HoldLease(owner="test", generation=1, action="back_up", duration_s=1),
            lambda _target: "motor:back",
            start,
        )
    start.assert_not_awaited()
    buttons = _combined_motor_buttons_for(parent, sides)
    assert len(buttons) == 10
    assert all("held_control" not in button.extra_state_attributes for button in buttons)
    with patch(
        "custom_components.adjustable_bed.services._async_timed_move", new=AsyncMock()
    ) as finite:
        await buttons[0].async_press()
    finite.assert_awaited_once()


async def test_coordinator_startup_reconnect_and_stale_notification(
    hass, mock_coordinator_connected, mock_establish_connection
):
    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    client = controller().client
    mock_establish_connection.side_effect = None
    mock_establish_connection.return_value = client
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": client.address,
            CONF_BED_TYPE: "onlysnore",
            CONF_PRODUCT_TYPE: "single",
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coord = AdjustableBedCoordinator(hass, entry)

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    with patch.object(OnlySnoreController, "_wait", new=AsyncMock(return_value=False)):
        assert await coord.async_connect()
        live = coord.controller
        assert isinstance(live, OnlySnoreController)
        char, callback = client.start_notify.call_args.args
        callback(char, bytearray(STATUS))
        assert coord.controller_state.get(state.PRIVACY) == "on"
        await coord.async_disconnect()
        assert coord.controller_state.get(state.PRIVACY) is None
        client.is_connected = True
        assert await coord.async_connect()
        assert coord.controller is not live
        callback(char, bytearray(STATUS))
        assert coord.controller_state.get(state.PRIVACY) is None
        await coord.async_disconnect()
        await coord.async_shutdown()
