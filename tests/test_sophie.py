"""Sophie 1.0.6 vectors, safe sessions and production HA routes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.solace.controller import preset_selected
from custom_components.adjustable_bed.beds.solace.sophie import SophieController
from custom_components.adjustable_bed.beds.solace.sophie_state import (
    ALARM_ENABLED,
    ALARM_MASSAGE,
    ALARM_MODE,
    ALARM_RING,
    ALARM_SUPPORTED,
    ALARM_TIME,
    FOOT_LEVEL,
    HEAD_LEVEL,
    SYNC_SUPPORTED,
    WAVE,
)
from custom_components.adjustable_bed.codec import ff_frame as codec
from custom_components.adjustable_bed.const import (
    SOLACE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import sophie as app
from custom_components.adjustable_bed.profiles.ff_frame import SolaceCommands as C
from custom_components.adjustable_bed.state_keys import (
    LIGHT_LEVEL,
    LIGHT_TIMER_OPTION,
    MASSAGE_TIMER_MINUTES,
    SYNCHRO_MODE,
)
from tests.state_helpers import state_writer

FIXTURES = Path(__file__).parent / "fixtures/sophie"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())


@pytest.fixture
def controller():
    coordinator = MagicMock()
    coordinator.controller_state = ControllerState()
    coordinator.cancel_command = asyncio.Event()
    coordinator.ble_device_name = "QMS-MQ-1520"
    coordinator.handle_controller_state_updates.side_effect = state_writer(
        coordinator.controller_state
    )
    char = SimpleNamespace(uuid=SOLACE_CHAR_UUID, handle=9, properties=["write", "notify"])
    client = MagicMock()
    client.is_connected = True
    client.services = [SimpleNamespace(characteristics=[char])]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    coordinator.client = client
    ctrl = SophieController(coordinator)
    coordinator.controller = ctrl
    yield ctrl
    ctrl.on_disconnect()


def written(ctrl):
    return [c.args[1].hex().upper() for c in ctrl.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_literals_and_dynamic_builders(row):
    expected = bytes.fromhex(row["expected_bytes"])
    if row["id"].startswith("V-clock"):
        now = datetime.fromisoformat(row["inputs"]["iso"])
        actual = codec.clock(now, now.isoweekday())
    elif row["id"].startswith("V-alarm"):
        a = row["inputs"]
        actual = codec.alarm(
            switch=1 if a["enabled"] else 0xA1,
            hour=a["hour"],
            minute=a["minute"],
            weekday_mask=sum(1 << day for day in a["days"]),
            repeat=bool(a["days"]),
            mode=int(a["mode"], 16),
            massage=a["massage"],
            sound=int(a["ring"]),
        )
    elif row["id"] == "V-C006":
        # The header action has no proven effect. Preserve its bytes, never expose it.
        assert expected.hex() == "ffffffff0500000000d814"
        assert expected[:-2] == codec.STOP[:-2]
        return
    elif row["id"] == "V-C049":
        # The hidden switch is excluded. Preserve its distinct bytes, never expose it.
        assert expected.hex() == "ffffffff050000001cd9dd"
        assert expected != C.MASSAGE_STOP
        return
    elif expected[4] == 5:
        actual = codec.control(expected[8], arg=expected[7], group=expected[6])
    elif expected[4] == 3:
        actual = codec.query(expected[6], expected[8])
    else:
        actual = codec.summed(expected[4], expected[6], expected[8:-2])
    assert actual == expected


@pytest.mark.parametrize(
    "name,named,modes,massage",
    [
        ("QMS-MQ", True, ("zero_g", "memory_1", "no_action"), True),
        ("QMS2-1520", True, ("zero_g", "memory_1", "no_action"), False),
        ("xQMS3-1320", True, ("zero_g", "memory_1", "no_action"), True),
        ("S3-2-1520", True, ("zero_g", "memory_1", "no_action"), True),
        *[
            (
                f"qms-{suffix}-1520",
                False,
                ("no_action", "zero_g_left", "zero_g_right", "zero_g_both"),
                True,
            )
            for suffix in ("dfq", "430", "444")
        ],
        ("1520", False, ("zero_g", "memory_1", "no_action"), True),
    ],
)
def test_independent_name_gates(name, named, modes, massage):
    assert app.named_queries(name) == named
    assert app.alarm_modes(name) == modes
    assert app.alarm_massage_allowed(name) == massage


@pytest.mark.parametrize(
    "name,accepted",
    [
        ("xMQx", True),
        ("x1520x", True),
        ("x1320x", True),
        ("mq", False),
        ("QMS2", False),
        ("", False),
    ],
)
def test_raw_scan_predicate(name, accepted):
    assert app.accepts_name(name) == accepted
    assert app.normalize_name("<:;=>?") == "CABDEF"


@pytest.mark.parametrize(
    "row,method",
    [(0, "move_back_up"), (1, "move_back_down"), (2, "move_legs_up"), (3, "move_legs_down")],
)
async def test_motor_press_release_and_cancel(controller, row, method):
    async def cancel(_char, _frame, **_):
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel
    await getattr(controller, method)()
    assert written(controller) == [VECTORS[row]["expected_bytes"], VECTORS[4]["expected_bytes"]]


async def test_short_hold_counts_write_latency_and_never_backfills(controller):
    async def slow(_char, frame, **_):
        if frame != codec.STOP:
            await asyncio.sleep(0.03)

    controller.client.write_gatt_char.side_effect = slow
    with patch("custom_components.adjustable_bed.beds.solace.sophie.asyncio.wait_for") as wait:
        await controller.hold_control("back_up", 1)
    wait.assert_not_called()
    assert written(controller) == [VECTORS[0]["expected_bytes"], VECTORS[4]["expected_bytes"]]


async def test_cleanup_cannot_jump_to_replacement_client(controller):
    old = controller.client
    replacement = MagicMock()
    replacement.is_connected = True
    replacement.write_gatt_char = AsyncMock()

    async def replace(_char, _frame, **_):
        controller.on_disconnect()
        controller._coordinator.client = replacement
        raise asyncio.CancelledError

    old.write_gatt_char.side_effect = replace
    with pytest.raises(asyncio.CancelledError):
        await controller.hold_control("back_up", 50)
    assert old.write_gatt_char.await_count == 1
    replacement.write_gatt_char.assert_not_called()


async def test_cancelled_task_still_sends_captured_release(controller):
    async def cancel(_char, frame, **_):
        if frame != codec.STOP:
            raise asyncio.CancelledError

    controller.client.write_gatt_char.side_effect = cancel
    with pytest.raises(asyncio.CancelledError):
        await controller.hold_control("legs_down", 1)
    assert written(controller) == [VECTORS[3]["expected_bytes"], VECTORS[4]["expected_bytes"]]


async def test_presets_save_clear_recall_and_no_optimistic_cache(controller):
    await controller.preset_flat()
    for index, key in enumerate(app.PRESET_KEYS):
        code = app.PRESET_CODES[index]
        if key.startswith("memory"):
            with pytest.raises(ValueError, match="Save this memory position"):
                await controller.preset_memory(index + 1)
        else:
            await getattr(controller, f"preset_{key}")()
            assert written(controller)[-1] == codec.control(code).hex().upper()
        await controller.save_preset(key)
        assert written(controller)[-1] == codec.control(code, arg=(code << 4) & 255).hex().upper()
        assert not controller._preset_is_selected(key)
        controller._parse_notification(codec.HEADER + bytes((3, 6, 0, code)))
        await controller.save_preset(key)
        assert (
            written(controller)[-1]
            == codec.control(code, arg=((code << 4) | 15) & 255).hex().upper()
        )
        if key.startswith("memory"):
            await controller.preset_memory(index + 1)
        else:
            await getattr(controller, f"preset_{key}")()
        assert (
            written(controller)[-1]
            == codec.control(code, arg=((code << 4) | 1) & 255).hex().upper()
        )
        controller._parse_notification(codec.control(code, arg=((code << 4) | 15) & 255))
        assert not controller._preset_is_selected(key)


@pytest.mark.parametrize(
    "method,row",
    [
        ("massage_wave_frequency_down", 38),
        ("massage_wave_frequency_up", 39),
        ("massage_head_down", 40),
        ("massage_head_up", 41),
        ("massage_foot_down", 42),
        ("massage_foot_up", 43),
    ],
)
async def test_source_visible_minus_plus_actions(controller, method, row):
    await getattr(controller, method)()
    assert written(controller) == [VECTORS[row]["expected_bytes"]]


async def test_timer_toggle_and_all_brightness_levels(controller):
    for duration in (10, 20, 30):
        await controller.set_massage_timer(duration)
        assert written(controller)[-1] == VECTORS[44 + (duration // 10 - 1)]["expected_bytes"]
        await controller.set_massage_timer(duration)
        assert written(controller)[-1] == VECTORS[47]["expected_bytes"]
    controller._parse_notification(bytes.fromhex("FFFFFFFF05000100"))
    for level in range(11):
        await controller.set_light_level(level)
        assert written(controller)[-1] == VECTORS[49 + level]["expected_bytes"]
    for index, option in enumerate(controller.light_timer_options):
        await controller.set_light_timer(option)
        assert written(controller)[-1] == VECTORS[60 + index]["expected_bytes"]
    await controller.lights_off()
    assert controller._coordinator.controller_state[LIGHT_TIMER_OPTION] == "Off"


async def test_cancelling_the_timer_clears_the_massage_indicators(controller):
    """The app's cancel stops the massage and resets head, foot and wave."""
    state = controller._coordinator.controller_state
    controller._parse_notification(app.MASSAGE_REPLIES["head"][2])
    controller._parse_notification(app.MASSAGE_REPLIES["foot"][3])
    controller._parse_notification(app.MASSAGE_REPLIES["wave"][1])
    await controller.set_massage_timer(20)
    assert (state[HEAD_LEVEL], state[FOOT_LEVEL], state[WAVE]) == (2, 3, 2)
    await controller.set_massage_timer(20)
    assert written(controller)[-1] == VECTORS[47]["expected_bytes"]
    assert (state[HEAD_LEVEL], state[FOOT_LEVEL], state[WAVE]) == (0, 0, 0)
    assert state[MASSAGE_TIMER_MINUTES] == 0


@pytest.mark.parametrize("zone,state", [("head", HEAD_LEVEL), ("foot", FOOT_LEVEL), ("wave", WAVE)])
def test_notification_literals(controller, zone, state):
    frozen = json.loads((FIXTURES / "notification_literals.json").read_text())
    for level, frame in enumerate(app.MASSAGE_REPLIES[zone]):
        assert frame.hex().upper() in frozen
        controller._parse_notification(frame)
        assert controller._coordinator.controller_state[state] == level + int(zone == "wave")


def test_reply_precedence_and_safe_offsets(controller):
    controller._coordinator.ble_device_name = "1520"
    state = controller._coordinator.controller_state
    controller._parse_notification(bytes.fromhex("FFFFFFFF031200AB"))
    assert state[preset_selected("memory_2")] is True
    assert state[preset_selected("tv")] is True
    controller._parse_notification(app.MASSAGE_REPLIES["head"][2] + app.MASSAGE_REPLIES["foot"][1])
    assert state[HEAD_LEVEL] == 2 and FOOT_LEVEL not in state
    present = bytes.fromhex("FFFFFFFF010004130F0730008A01020101")
    for frame in (present[:12], b"x" + present, b"\xff"):
        controller._parse_notification(frame)
    assert ALARM_ENABLED not in state
    controller._parse_notification(present + app.SYNC_ON)
    assert state[ALARM_ENABLED] and state[ALARM_TIME] == "07:30"
    assert SYNC_SUPPORTED not in state
    controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    assert not state[ALARM_ENABLED] and state[ALARM_TIME] is None
    assert state[ALARM_MODE] == "no_action" and not state[ALARM_MASSAGE] and not state[ALARM_RING]
    controller._parse_notification(bytes.fromhex("FFFFFFFF050001FF"))
    assert state[LIGHT_LEVEL] == 255
    controller._parse_notification(C.LIGHT_TIMER_10_MIN + bytes.fromhex("FFFFFF0500050000C701"))
    assert state[LIGHT_TIMER_OPTION] == "Off"


async def test_alarm_and_sync_gates_and_exact_wire(controller):
    args = {
        "enabled": True,
        "hour": 7,
        "minute": 30,
        "weekdays": (1, 3, 7),
        "mode": "memory_1",
        "massage": True,
        "ring": False,
    }
    with pytest.raises(ValueError, match="support"):
        await controller.set_alarm(**args)
    controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    await controller.set_alarm(**args)
    assert written(controller) == [VECTORS[-2]["expected_bytes"]]
    controller._coordinator.ble_device_name = "QMS2-1520"
    with pytest.raises(ValueError, match="QMS2"):
        await controller.set_alarm(**args)
    controller._coordinator.ble_device_name = "QMS-430-1520"
    with pytest.raises(ValueError, match="mode"):
        await controller.set_alarm(**args)
    for mode in ("zero_g_left", "zero_g_right", "zero_g_both", "no_action"):
        await controller.set_alarm(**{**args, "mode": mode})
    with pytest.raises(ValueError, match="support"):
        await controller.set_synchro(True)
    controller._parse_notification(app.SYNC_ON)
    await controller.set_synchro(False)
    assert written(controller)[-1] == VECTORS[35]["expected_bytes"]
    controller.on_disconnect()
    assert controller._coordinator.controller_state[SYNC_SUPPORTED]
    assert controller._coordinator.controller_state[SYNCHRO_MODE] is None


async def test_stale_notify_callbacks_and_runtime_gatt_selection(controller):
    await controller.start_notify()
    callback = controller.client.start_notify.await_args.args[1]
    controller.on_disconnect()
    callback(None, bytearray(app.SYNC_ON))
    assert controller._coordinator.controller_state[SYNCHRO_MODE] is None
    second = SimpleNamespace(
        uuid=SOLACE_CHAR_UUID, handle=99, properties=["write-without-response"]
    )
    controller.client.services.append(SimpleNamespace(characteristics=[second]))
    await controller.write_command(codec.STOP, cancel_event=asyncio.Event())
    assert controller.client.write_gatt_char.await_args.args[0] is second
    assert controller.client.write_gatt_char.await_args.kwargs["response"] is False


async def test_startup_offsets_are_serialized_and_session_owned(controller):
    session = MagicMock()
    session.is_current.return_value = True

    async def query(fn, **kwargs):
        if kwargs["run_if"]():
            await fn(controller)

    controller._coordinator.async_execute_controller_query.side_effect = query

    class Loop:
        time_value = 0.0

        def time(self):
            return self.time_value

    clock = Loop()
    offsets = []

    async def sleep(delay):
        clock.time_value += delay
        offsets.append(round(clock.time_value * 1000))

    with (
        patch(
            "custom_components.adjustable_bed.beds.solace.sophie.asyncio.get_running_loop",
            return_value=clock,
        ),
        patch(
            "custom_components.adjustable_bed.beds.solace.sophie.asyncio.sleep", side_effect=sleep
        ),
    ):
        await controller._startup(session, controller._generation)
    assert offsets == [300, 500, 800, 1000, 1000, 1300, 1800, 2300]
    assert len(written(controller)) == 8
    assert written(controller)[0] == VECTORS[25]["expected_bytes"]
    assert written(controller)[2] == VECTORS[26]["expected_bytes"]
    session.is_current.return_value = False
    await controller._startup(session, controller._generation)
    assert len(written(controller)) == 8


@pytest.fixture
async def connected_sophie(
    hass,
    mock_coordinator_connected,
    mock_async_ble_device_from_address,
    mock_bleak_client,
    enable_custom_integrations,
):
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_BLE_DEVICE_NAME,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
        CONF_MOTOR_COUNT,
        CONF_PROTOCOL_VARIANT,
        DOMAIN,
    )

    char = MagicMock()
    char.uuid, char.handle, char.properties = SOLACE_CHAR_UUID, 15, ["write", "notify"]
    service = SimpleNamespace(uuid="12340000-0000-1000-8000-00805f9b34fb", characteristics=[char])
    mock_bleak_client.services.__iter__ = lambda _: iter([service])
    mock_bleak_client.services.__len__ = lambda _: 1
    mock_bleak_client.services.get_characteristic.return_value = char
    mock_bleak_client.write_gatt_char.side_effect = None
    mock_async_ble_device_from_address.return_value.name = "QMS-MQ-1520"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=5,
        minor_version=3,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Sophie",
            CONF_BED_TYPE: "solace",
            CONF_PROTOCOL_VARIANT: "sophie",
            CONF_BLE_DEVICE_NAME: "QMS-MQ-1520",
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_ensure_connected()
    assert isinstance(coordinator.controller, SophieController)
    coordinator.controller._cancel_startup()
    await hass.async_block_till_done()
    mock_bleak_client.write_gatt_char.reset_mock()

    def entity(domain, key):
        found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"AA:BB:CC:DD:EE:FF_{key}")
        assert found is not None, (domain, key)
        return found

    yield entry, coordinator, entity
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_real_setup_entities_and_alarm_service(hass, connected_sophie):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import DOMAIN

    entry, coordinator, entity = connected_sophie
    ctrl = coordinator.controller
    assert ctrl.profile.key == "sophie"
    assert (
        er.async_get(hass).async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:FF_back_position")
        is None
    )
    ctrl._parse_notification(bytes.fromhex("FFFFFFFF05000100"))
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity("number", "light_level"), "value": 4},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity("select", "light_timer"), "option": "8 hours"},
        blocking=True,
    )
    assert written(ctrl)[-2:] == [VECTORS[53]["expected_bytes"], VECTORS[61]["expected_bytes"]]
    tv = hass.states.get(entity("button", "sophie_program_tv")).attributes
    assert tv["card_section"] == "presets" and tv["card_role"] == "save"
    ctrl._parse_notification(bytes.fromhex("FFFFFFFF010004130F0730008A01020101"))
    await hass.async_block_till_done()
    # Controller-state sensors are disabled by default; the published state is what they show.
    assert coordinator.controller_state[ALARM_ENABLED]
    assert coordinator.controller_state[ALARM_TIME] == "07:30"
    device_id = (
        er.async_get(hass).async_get(entity("binary_sensor", "sophie_alarm_enabled")).device_id
    )
    await hass.services.async_call(
        DOMAIN,
        "set_alarm",
        {
            "device_id": device_id,
            "enabled": True,
            "time": "07:30:00",
            "weekdays": ["monday", "wednesday", "sunday"],
            "wake_action": "memory_1",
            "massage": True,
        },
        blocking=True,
    )
    assert written(ctrl)[-1] == VECTORS[-2]["expected_bytes"]
    ctrl._parse_notification(app.SYNC_ON)
    # The shared Controller Sync switch is disabled by default; drive its command.
    sync = er.async_get(hass).async_get(entity("switch", "synchro_mode"))
    assert sync is not None and sync.disabled_by is not None
    await coordinator.async_execute_controller_command(lambda c: c.set_synchro(False))
    assert written(ctrl)[-1] == VECTORS[35]["expected_bytes"]


async def test_real_timed_move_short_native_hold(hass, connected_sophie):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import DOMAIN

    _, coordinator, entity = connected_sophie
    device_id = er.async_get(hass).async_get(entity("cover", "back")).device_id
    await hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": device_id,
            "motor": "back",
            "direction": "up",
            "duration_ms": 100,
        },
        blocking=True,
    )
    assert written(coordinator.controller) == [
        VECTORS[0]["expected_bytes"],
        VECTORS[4]["expected_bytes"],
    ]


@pytest.mark.parametrize(
    ("name", "actions", "massage"),
    [
        ("QMS-MQ-1520", ("none", "zero_g", "memory_1"), True),
        ("QMS2-1520", ("none", "zero_g", "memory_1"), False),
        ("QMS-430-1520", ("none", "zero_g_left", "zero_g_right", "zero_g"), True),
    ],
)
async def test_alarm_capability_follows_the_model_name(controller, name, actions, massage):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    controller._coordinator.ble_device_name = name
    assert controller.alarm_capability is None
    controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    capability = controller.alarm_capability
    assert capability is not None
    assert capability.wake_actions == actions and capability.massage == massage
    request = AlarmRequest(
        enabled=True, hour=7, minute=30, wake_action="zero_g", reference_time=datetime.now()
    )
    await controller.configure_alarm(request)
    mode = "zero_g_both" if "zero_g_left" in actions else "zero_g"
    assert (
        written(controller)[-1]
        == codec.alarm(
            switch=1,
            hour=7,
            minute=30,
            weekday_mask=0,
            repeat=False,
            mode=app.ALARM_MODES[mode],
            massage=False,
            sound=0,
        )
        .hex()
        .upper()
    )


async def test_app_picker_and_import_executor_load_actual_profile(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_BLE_DEVICE_NAME,
        CONF_HAS_MASSAGE,
        CONF_MOTOR_COUNT,
        CONF_PROTOCOL_VARIANT,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.form_helpers import finish_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await flow.async_step_select_app()
    picker = next(v for k, v in form["data_schema"].schema.items() if k == CONF_BED_TYPE)
    labels = {v: k for k, v in picker.rows().items()}
    assert "Sophie" in labels["solace:sophie"]
    result = await flow.async_step_select_app({CONF_BED_TYPE: labels["solace:sophie"]})
    assert result["step_id"] == "manual_entry"
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:55"})
    if result.get("step_id") == "profile_questions":
        answers = {CONF_BLE_DEVICE_NAME: "QMS2-1520"}
        schema = result["data_schema"]
        assert schema is not None
        schema(answers)
        result = await flow.async_step_profile_questions(answers)
    await finish_new_bed(flow, result, {})
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_PROTOCOL_VARIANT] == "sophie" and saved[CONF_MOTOR_COUNT] == 2
    assert saved[CONF_HAS_MASSAGE] is True
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = saved
    ctrl = await create_controller(coordinator, "solace", "sophie", None)
    assert isinstance(ctrl, SophieController) and ctrl.profile.key == "sophie"


async def test_real_paired_alarm_side_ownership_and_all_target_gate(hass):
    from datetime import time

    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import ServiceValidationError
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import handle_set_alarm

    children = {}
    for side, address, name in (
        ("left", "AA:BB:CC:DD:EE:01", "QMS-MQ-1520"),
        ("right", "AA:BB:CC:DD:EE:02", "QMS-430-1520"),
    ):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": address,
                "name": side,
                "bed_type": "solace",
                "protocol_variant": "sophie",
                const.CONF_BLE_DEVICE_NAME: name,
                const.CONF_DISABLE_ANGLE_SENSING: True,
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        char = SimpleNamespace(uuid=SOLACE_CHAR_UUID, handle=7, properties=["write", "notify"])
        child._client = MagicMock(
            is_connected=True, services=[SimpleNamespace(characteristics=[char])]
        )
        child._client.write_gatt_char = AsyncMock()
        child._controller = SophieController(child)
        child.async_ensure_connected = AsyncMock(return_value=True)
        child._async_refresh_controller_auth = AsyncMock()
        child.controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
        children[side] = child
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "sophie-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, children, connection_mode="concurrent")

    def call(wake_action):
        return ServiceCall(
            hass,
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": ["pair"],
                "enabled": True,
                "time": time(7, 30),
                "wake_action": wake_action,
            },
        )

    try:
        with patch(
            "custom_components.adjustable_bed.services._call_targets", return_value=[(pair, "both")]
        ):
            with pytest.raises(ServiceValidationError):
                await handle_set_alarm(call("memory_1"))
            for child in children.values():
                child.client.write_gatt_char.assert_not_awaited()
            await handle_set_alarm(call("none"))
        left, right = (children[side] for side in ("left", "right"))
        assert len(written(left.controller)) == len(written(right.controller)) == 1
        # A left-only target retains the left model and never touches the right.
        with patch(
            "custom_components.adjustable_bed.services._call_targets", return_value=[(pair, "left")]
        ):
            await handle_set_alarm(call("memory_1"))
        assert len(written(left.controller)) == 2 and len(written(right.controller)) == 1
    finally:
        for child in children.values():
            child.controller.on_disconnect()
            child._cancel_disconnect_timer()


async def test_light_support_gate_and_cancelled_write_never_publish_success(controller):
    with pytest.raises(ValueError, match="brightness support"):
        await controller.set_light_level(2)
    controller._coordinator.controller_state[LIGHT_LEVEL] = 0
    controller._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await controller.set_light_level(2)
    assert controller._coordinator.controller_state[LIGHT_LEVEL] == 0
    controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("name", ["QMS-MQ-1520", "QMS2-1520", "S3-2-1520", "QMS3-1320", "1520"])
def test_saved_query_replies_respect_selected_family_and_echoes_remain_shared(controller, name):
    controller._coordinator.ble_device_name = name
    state = controller._coordinator.controller_state
    for frame, family in (("FFFFFFFF0306000B", "q2"), ("FFFFFFFF031200AB", "q1")):
        state.clear()
        controller._parse_notification(bytes.fromhex(frame))
        accepted = controller._query_family == family
        assert state.get(preset_selected("memory_2"), False) is accepted
        assert state.get(preset_selected("tv"), False) is (accepted and family == "q1")
    controller._parse_notification(C.PROGRAM_MEMORY_1)
    assert state[preset_selected("memory_1")] is True
    controller._parse_notification(C.PROGRAM_MEMORY_1_SELECTED)
    assert state[preset_selected("memory_1")] is False


@pytest.mark.parametrize("action", ["alarm", "sync"])
async def test_proven_support_survives_idle_disconnect_and_reconnect_without_new_reply(
    hass, connected_sophie, action
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import DOMAIN

    _, coordinator, entity = connected_sophie
    previous = coordinator.controller
    previous._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    previous._parse_notification(app.SYNC_ON)
    device_id = (
        er.async_get(hass).async_get(entity("binary_sensor", "sophie_alarm_enabled")).device_id
    )
    assert await coordinator.async_disconnect(reason="idle_timeout")
    assert not coordinator.is_connected
    assert coordinator.controller_state[ALARM_SUPPORTED] is True
    assert coordinator.controller_state[SYNC_SUPPORTED] is True
    assert coordinator.controller_state[SYNCHRO_MODE] is None
    # The command must pass offline preflight and reconnect before any delayed
    # startup query could reply. Neither support fact is fabricated on reconnect.
    with patch.object(SophieController, "async_after_connect", new_callable=AsyncMock):
        if action == "alarm":
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": device_id,
                    "enabled": True,
                    "time": "07:30:00",
                    "weekdays": ["monday", "wednesday", "sunday"],
                    "wake_action": "memory_1",
                    "massage": True,
                },
                blocking=True,
            )
            expected = VECTORS[-2]["expected_bytes"]
        else:
            await coordinator.async_execute_controller_command(lambda c: c.set_synchro(False))
            expected = VECTORS[35]["expected_bytes"]
    assert coordinator.is_connected and coordinator.controller is not previous
    assert written(coordinator.controller) == [expected]


@pytest.mark.parametrize("phase", ["waiting", "executing"])
@pytest.mark.parametrize("transition", ["stop", "task_cancel", "disconnect"])
async def test_startup_query_preemption_preserves_only_current_session_work(
    connected_sophie, phase, transition
):
    _, coordinator, _ = connected_sophie
    controller = coordinator.controller
    coordinator._disconnect_after_command = False
    session = MagicMock()
    session.is_current.side_effect = lambda: (
        coordinator.controller is controller and coordinator.is_connected
    )
    entered, blocked = asyncio.Event(), asyncio.Event()
    execute_query = coordinator.async_execute_controller_query

    async def query(fn, **kwargs):
        if phase == "waiting":
            entered.set()
        await execute_query(fn, **kwargs)

    async def write(_char, frame, **kwargs):
        if frame == C.QUERY_Q2[0]:
            entered.set()
            await blocked.wait()

    owns_lock = phase == "waiting"
    if owns_lock:
        await coordinator._command_lock.acquire()
    else:
        controller.client.write_gatt_char.side_effect = write
    with (
        patch.multiple(
            app,
            QUERY_DELAY_MS=0,
            QUERY_SPACING_MS=0,
            CLOCK_DELAY_MS=0,
            SYNC_AFTER_CLOCK_MS=0,
            LIGHT_QUERY_DELAY_MS=0,
        ),
        patch.object(coordinator, "async_execute_controller_query", side_effect=query) as queries,
        patch.object(controller, "sync_clock", new_callable=AsyncMock) as clock,
    ):
        await controller.async_after_connect(session)
        startup = controller._startup_task
        assert startup is not None
        stop: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(2):
                await entered.wait()
                if transition == "stop":
                    stop = asyncio.create_task(coordinator.async_stop_command())
                    # Let the real public STOP fence the waiting/active query.
                    await asyncio.sleep(0)
                elif transition == "task_cancel":
                    startup.cancel()
                else:
                    controller.on_disconnect()
                if owns_lock:
                    coordinator._command_lock.release()
                    owns_lock = False
                if transition == "stop":
                    assert stop is not None
                    await stop
                    await startup
                else:
                    with pytest.raises(asyncio.CancelledError):
                        await startup
        finally:
            if owns_lock:
                coordinator._command_lock.release()

        attempted = [C.QUERY_Q2[0].hex().upper()] if phase == "executing" else []
        if transition == "stop":
            assert queries.await_count == 8
            clock.assert_awaited_once()
            expected = [codec.STOP, *C.QUERY_Q2[1:], app.SYNC_QUERY, C.LIGHT_STATUS_QUERY]
            assert written(controller) == attempted + [frame.hex().upper() for frame in expected]
        else:
            assert queries.await_count == 1
            clock.assert_not_awaited()
            assert written(controller) == attempted


async def test_sync_switch_reads_unknown_after_disconnect(hass, connected_sophie):
    from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS, AdjustableBedSwitch

    _, coordinator, _ = connected_sophie
    description = next(d for d in SWITCH_DESCRIPTIONS if d.key == "synchro_mode")
    switch = AdjustableBedSwitch(coordinator, description)
    switch.async_write_ha_state = MagicMock()
    coordinator.controller._parse_notification(app.SYNC_ON)
    switch._handle_controller_state_update(coordinator.controller_state)
    assert switch.is_on is True
    coordinator.controller.on_disconnect()
    switch._handle_controller_state_update(coordinator.controller_state)
    assert switch.is_on is None
