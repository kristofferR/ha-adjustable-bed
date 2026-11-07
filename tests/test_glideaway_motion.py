"""Row068 revision01 artifact vectors, not hardware captures.

Accepted REPORT.SHA256 b3b4b2cc669d8050a68070aa3f9c1ad8021b0c7f9b244ab6703ae4d0caf3ec04.
The R01-F01 timer comparison is intentional and covered explicitly.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.bed_traits import bed_type_has_position_feedback
from custom_components.adjustable_bed.beds import glideaway_motion as gm
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import (
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_OKIN_ORE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    GLIDEAWAY_MOTION_MODELS,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
from tests.form_helpers import finish_new_bed, start_new_bed
from tests.state_helpers import state_writer

ZERO = bytes.fromhex("e6fe16000000000005")
# C01..C25, accepted command-table.md. Sustained saves share recall frames.
VECTORS = [
    ("C01", "back_up", "e6fe16010000000004"),
    ("C02", "back_down", "e6fe16020000000003"),
    ("C03", "feet_up", "e6fe16040000000001"),
    ("C04", "feet_down", "e6fe160800000000fd"),
    ("C05", "both_up", "e6fe16050000000000"),
    ("C06", "both_down", "e6fe160a00000000fb"),
    ("C07", "tilt_up", "e6fe161000000000f5"),
    ("C08", "tilt_down", "e6fe162000000000e5"),
    ("C09", "bed_height_up", "e6fe164000000000c5"),
    ("C10", "bed_height_down", "e6fe16800000000085"),
    ("C11", "stop", "e6fe16000000000005"),
    ("C12", "flat", "e6fe160000000800fd"),
    ("C13", "anti_snore", "e6fe16008000000085"),
    ("C14", "zero_g", "e6fe160010000000f5"),
    ("C15", "memory_1", "e6fe160020000000e5"),
    ("C16", "memory_2", "e6fe160040000000c5"),
    ("C17", "save_1", "e6fe160020000000e5"),
    ("C18", "save_2", "e6fe160040000000c5"),
    ("C19", "light", "e6fe16000002000003"),
    ("C20", "massage_intensity_up", "e6fe16000c000000f9"),
    ("C21", "massage_intensity_down", "e6fe16000080010084"),
    ("C22", "massage_wave_up", "e6fe160000001000f5"),
    ("C23", "massage_wave_down", "e6fe16000000040001"),
    ("C24", "massage_timer", "e6fe16000200000003"),
    ("C25", "massage_off", "e6fe16000100000004"),
]


@pytest.fixture
def coordinator():
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_pulse_delay_ms = 17  # Must never replace the proven 300 ms.
    coordinator.address = "AA:BB:CC:DD:EE:68"
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    write = SimpleNamespace(uuid=gm.WRITE_CHAR, properties=["write"], handle=68)
    notify = SimpleNamespace(uuid=gm.NOTIFY_CHAR, properties=["notify"], handle=69)
    write_service = MagicMock()
    write_service.get_characteristic.side_effect = lambda uuid: (
        write if uuid == gm.WRITE_CHAR else None
    )
    notify_service = MagicMock()
    notify_service.get_characteristic.side_effect = lambda uuid: (
        notify if uuid == gm.NOTIFY_CHAR else None
    )
    coordinator.client.services.get_service.side_effect = {
        gm.WRITE_SERVICE: write_service,
        gm.NOTIFY_SERVICE: notify_service,
    }.get
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = state_writer(coordinator.controller_state)
    return coordinator


@pytest.fixture
def instant(monkeypatch):
    clock = [0.0]

    async def advance_wait(_event, delay):
        clock[0] += delay

    async def advance_sleep(delay):
        clock[0] += delay

    wait = AsyncMock(side_effect=advance_wait)
    sleep = AsyncMock(side_effect=advance_sleep)
    monkeypatch.setattr(gm, "monotonic_ns", lambda: round(clock[0] * 1_000_000_000))
    monkeypatch.setattr(gm, "_wait_for_cancel", wait)
    monkeypatch.setattr(gm.asyncio, "sleep", sleep)
    return wait, sleep


def written(coordinator):
    return [call.args[1] for call in coordinator.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("model", GLIDEAWAY_MOTION_MODELS)
@pytest.mark.parametrize("row,action,expected", VECTORS, ids=[v[0] for v in VECTORS])
async def test_command_vectors(coordinator, instant, model, row, action, expected):
    controller = gm.GlideawayMotionController(coordinator, model=model)
    if action not in controller.held_control_options and action not in ("stop", "save_1", "save_2"):
        with pytest.raises(ValueError):
            await controller.hold_control(action, 300)
        assert written(coordinator) == []
        return
    if action == "stop":
        await controller.stop_all()
        assert written(coordinator) == [bytes.fromhex(expected)] * 2
    elif action.startswith("save_"):
        await controller.program_memory(int(action[-1]))
        assert written(coordinator) == [bytes.fromhex(expected)] * 18 + [ZERO, ZERO]
        assert sum(call.args[1] for call in instant[0].await_args_list) == pytest.approx(5.2)
    else:
        await controller.hold_control(action, 300)
        assert written(coordinator) == [bytes.fromhex(expected), ZERO, ZERO]
    assert [call.args[0] for call in instant[1].await_args_list] == [0.3, 0.3]
    assert all(sum(packet) & 255 == 255 for packet in written(coordinator))


@pytest.mark.parametrize(
    "model,axes,extra",
    [
        ("motion_400", ("back", "feet", "both"), False),
        ("motion_450", ("back", "feet", "bed_height"), False),
        ("motion_500", ("back", "feet", "both", "bed_height"), True),
        ("motion_600", ("back", "feet", "tilt", "bed_height"), True),
    ],
)
async def test_models_and_cover_controls(coordinator, instant, model, axes, extra):
    controller = gm.GlideawayMotionController(coordinator, model=model)
    assert tuple(spec.key for spec in controller.motor_control_specs) == axes
    assert controller.supports_lights == controller.supports_massage == extra
    assert controller.auto_enable_massage == extra
    assert controller.memory_slot_count == 2 and controller.supports_memory_programming
    assert not controller.supports_single_address_pairing
    assert not controller.supports_position_feedback
    assert not controller.supports_discrete_light_control
    assert not controller.supports_massage_toggle_control
    assert not controller.supports_head_massage_intensity_step_control
    for spec in controller.motor_control_specs:
        coordinator.client.write_gatt_char.reset_mock()
        await spec.open_fn(controller)
        assert written(coordinator) == [gm.command_frame(gm.AXES[spec.key][0])] * 3 + [ZERO, ZERO]
        assert spec.scheduler_resource == "*"
    assert all(call.args[1] == pytest.approx(0.3) for call in instant[0].await_args_list)
    for unsupported in set(gm.AXES) - set(axes):
        with pytest.raises(ValueError):
            await controller._move_axis(unsupported, True)


async def test_recall_does_not_program_and_invalid_slots_write_nothing(coordinator, instant):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    coordinator.motor_pulse_count = 100
    await controller.preset_memory(1)
    assert written(coordinator) == [bytes.fromhex("e6fe160020000000e5"), ZERO, ZERO]
    coordinator.client.write_gatt_char.reset_mock()
    for method in (controller.preset_memory, controller.program_memory):
        with pytest.raises(ValueError):
            await method(3)
    with pytest.raises(ValueError):
        await controller.hold_control("memory_1", 5000)
    assert written(coordinator) == []


async def test_event_cancel_still_releases_twice(coordinator, instant):
    controller = gm.GlideawayMotionController(coordinator, model="motion_600")
    instant[0].side_effect = lambda *_: coordinator.cancel_command.set()
    await controller.move_back_up()
    assert written(coordinator) == [bytes.fromhex("e6fe16010000000004"), ZERO, ZERO]


@pytest.mark.parametrize("latency,starts,hold_end", [(0.2, [0.0, 0.3], 0.6), (0.7, [0.0], 0.7)])
async def test_hold_deadline_includes_write_latency(
    coordinator, monkeypatch, latency, starts, hold_end
):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    clock = [0.0]
    writes = []
    release_started = []

    async def write(*_args, **_kwargs):
        writes.append(clock[0])
        clock[0] += latency

    async def wait(_event, delay):
        clock[0] += delay

    async def release():
        release_started.append(clock[0])

    monkeypatch.setattr(gm, "monotonic_ns", lambda: round(clock[0] * 1_000_000_000))
    monkeypatch.setattr(gm, "_wait_for_cancel", wait)
    monkeypatch.setattr(controller, "write_command", write)
    monkeypatch.setattr(controller, "stop_all", release)
    await controller.hold_control("back_up", 600)
    assert writes == pytest.approx(starts)
    assert release_started == pytest.approx([hold_end])


async def test_repeated_task_cancellation_cannot_abandon_release(coordinator, monkeypatch):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    held = asyncio.Event()
    first_release = asyncio.Event()
    let_release_finish = asyncio.Event()

    async def blocked_hold(*_):
        held.set()
        await asyncio.Event().wait()

    async def release_delay(_delay):
        first_release.set()
        await let_release_finish.wait()

    monkeypatch.setattr(gm, "_wait_for_cancel", blocked_hold)
    monkeypatch.setattr(gm.asyncio, "sleep", release_delay)
    task = asyncio.create_task(controller.move_back_up())
    await held.wait()
    task.cancel()
    await first_release.wait()
    task.cancel()
    let_release_finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(coordinator) == [bytes.fromhex("e6fe16010000000004"), ZERO, ZERO]


async def test_write_failure_still_attempts_release(coordinator, instant):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    coordinator.client.write_gatt_char.side_effect = [BleakError("write failed"), None, None]
    with pytest.raises(BleakError):
        await controller.move_back_up()
    assert written(coordinator)[-2:] == [ZERO, ZERO]


@pytest.mark.parametrize("second_fails", [False, True])
async def test_first_release_failure_still_attempts_second(coordinator, instant, second_fails):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    first_error = BleakError("first release failed")
    coordinator.client.write_gatt_char.side_effect = [
        first_error,
        BleakError("second release failed") if second_fails else None,
    ]
    with pytest.raises(BleakError) as raised:
        await controller.stop_all()
    assert raised.value is first_error
    assert written(coordinator) == [ZERO, ZERO]
    assert [call.args[0] for call in instant[1].await_args_list] == [0.3, 0.3]


@pytest.mark.parametrize(
    "properties,response",
    [
        (["write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], False),
    ],
)
async def test_gatt_roles_subscription_and_mode(coordinator, properties, response):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    characteristic = controller._role(gm.WRITE_SERVICE, gm.WRITE_CHAR)
    characteristic.properties = properties
    await controller.start_notify()
    assert written(coordinator) == []  # No startup query/auth/RTC.
    assert coordinator.client.start_notify.await_args.args[0].uuid == gm.NOTIFY_CHAR
    await controller.write_command(ZERO)
    assert coordinator.client.write_gatt_char.await_args.kwargs["response"] is response
    assert coordinator.client.write_gatt_char.await_args.args[0] is characteristic
    await controller.stop_notify()
    assert coordinator.client.stop_notify.await_count == 1
    coordinator.client.services.get_service.side_effect = lambda _: None
    with pytest.raises(BleakError):
        await controller.write_command(ZERO)


@pytest.mark.parametrize(
    "prefix,length,offset", [(b"\xe7\xfe", 10, 8), (b"\xed\xfe", 16, 14), (b"\xf4\xfe", 21, 19)]
)
@pytest.mark.parametrize("raw,expected", [(0, 0), (1, 10), (2, 20), (3, 30), (255, 0), (254, 2540)])
async def test_timer_notification_vectors(coordinator, prefix, length, offset, raw, expected):
    controller = gm.GlideawayMotionController(coordinator, model="motion_500")
    packet = bytearray(length)
    packet[:2] = prefix
    packet[offset] = raw
    controller._on_notification(MagicMock(), packet)
    assert coordinator.controller_state[gm.STATE_TIMER] == expected
    assert coordinator.controller_state["glideaway_motion_massage_timer_raw"] == raw


async def test_audited_timer_previous_display_comparison(coordinator):
    controller = gm.GlideawayMotionController(coordinator, model="motion_500")
    controller._timer(1)
    controller._timer(10)
    assert coordinator.controller_state[gm.STATE_TIMER] == 10  # R01-F01
    controller._timer(255)
    assert coordinator.controller_state[gm.STATE_TIMER] == 0
    controller._timer(10)
    assert coordinator.controller_state[gm.STATE_TIMER] == 100


async def test_fragmentation_and_safe_bounds(coordinator):
    controller = gm.GlideawayMotionController(coordinator, model="motion_500")
    other = gm.GlideawayMotionController(coordinator, model="motion_600")
    packet = bytearray(23)
    packet[:2] = b"\xf4\xfe"
    packet[19] = 3
    controller._on_notification(MagicMock(), packet[:18])
    other._on_notification(MagicMock(), packet[18:])
    assert not coordinator.controller_state
    controller._on_notification(MagicMock(), packet[18:])
    assert coordinator.controller_state[gm.STATE_TIMER] == 30
    for bad in (b"", b"\xe7", b"\xe7\xfe", b"\xed\x80", b"\xed\x80" + bytes(29)):
        controller._on_notification(MagicMock(), bytearray(bad))
    controller._on_notification(MagicMock(), packet[:18])
    controller._fragment_time -= 3
    controller._on_notification(MagicMock(), packet[18:])
    assert controller._fragment == b""
    controller._on_notification(MagicMock(), packet[:18])
    controller.invalidate_diagnostics()
    controller._on_notification(MagicMock(), packet[18:])
    assert coordinator.controller_state[gm.STATE_TIMER] is None


@pytest.mark.parametrize("tail", [0x00, 0xF4])
async def test_one_byte_fragment_continuation(coordinator, tail):
    controller = gm.GlideawayMotionController(coordinator, model="motion_500")
    packet = bytearray(21)
    packet[:2] = b"\xf4\xfe"
    packet[19] = 3
    packet[20] = tail
    controller._on_notification(MagicMock(), packet[:20])
    assert not coordinator.controller_state
    controller._on_notification(MagicMock(), packet[20:])
    assert coordinator.controller_state[gm.STATE_TIMER] == 30
    assert controller._fragment == b""

    controller.invalidate_diagnostics()
    controller._on_notification(MagicMock(), packet[:20])
    controller._fragment_time -= 3
    controller._on_notification(MagicMock(), packet[20:])
    assert coordinator.controller_state[gm.STATE_TIMER] is None
    assert controller._fragment == b""


@pytest.mark.parametrize(
    "wake,expected",
    [
        ("none", "ed 80 03 06 1e 04 00 00 00 00 00 00 00 00 00 67"),
        ("memory_1", "ed 80 03 06 1e 04 11 00 00 00 00 00 00 00 00 56"),
        ("memory_2", "ed 80 03 06 1e 04 13 00 00 00 00 00 00 00 00 54"),
    ],
)
async def test_alarm_vectors_rtc_sequence_and_parser(
    coordinator, instant, monkeypatch, wake, expected
):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    now = datetime(2026, 11, 3, 10, 0, 6)  # Tuesday, selected 06:30 is earlier.
    monkeypatch.setattr(gm.dt_util, "now", lambda: now)
    await controller.configure_clock_alarm(
        enabled=True, weekdays=(), hour=6, minute=30, preset=wake
    )
    assert written(coordinator) == [gm.rtc_frame(now), bytes.fromhex(expected)]
    assert instant[1].await_args.args == (0.3,)
    controller._on_notification(MagicMock(), bytearray.fromhex(expected))
    assert coordinator.controller_state[gm.STATE_ALARM] == "on"
    assert coordinator.controller_state["glideaway_motion_alarm_hour"] == 6
    assert coordinator.controller_state["glideaway_motion_alarm_minute"] == 30
    assert coordinator.controller_state["glideaway_motion_alarm_wake"] == wake
    coordinator.client.write_gatt_char.reset_mock()
    await controller.configure_clock_alarm(
        enabled=False, weekdays=(), hour=0, minute=0, preset="none"
    )
    assert written(coordinator)[1].hex() == "ed80030000000000000000000000008f"
    controller._on_notification(MagicMock(), bytearray(written(coordinator)[1]))
    assert coordinator.controller_state[gm.STATE_ALARM] == "off"


def test_calendar_and_rtc_vectors():
    now = datetime(2026, 11, 3, 0, 5, 6)
    assert gm.rtc_frame(now).hex() == "e780017e0a02ff050603"
    assert gm.alarm_frame(True, 11, 0, "memory_1", now)[5] == 8
    assert gm.alarm_frame(True, 0, 5, "memory_2", now)[5] == 4
    assert gm.alarm_frame(True, 11, 0, "none", datetime(2026, 11, 7, 10))[5] == 1
    assert gm.alarm_frame(True, 9, 0, "none", datetime(2026, 11, 8, 10))[5] == 1


async def test_query_alarm_twice_and_explicit_clock_sync(coordinator, instant, monkeypatch):
    controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    await controller.controller_button_specs[0].press_fn(controller)
    assert written(coordinator) == [bytes.fromhex("e28003009a")] * 2
    assert instant[1].await_args.args == (0.2,)
    now = datetime(2026, 11, 3, 0, 5, 6)
    monkeypatch.setattr(gm.dt_util, "now", lambda: now)
    await controller.sync_clock()
    assert written(coordinator)[-1] == gm.rtc_frame(now)


async def test_factory_manual_models_and_profile_ownership(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:68", CONF_BED_TYPE: BED_TYPE_GLIDEAWAY_MOTION},
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    for model in GLIDEAWAY_MOTION_MODELS:
        controller = await create_controller(
            coordinator, BED_TYPE_GLIDEAWAY_MOTION, protocol_variant=model, client=None
        )
        assert isinstance(controller, gm.GlideawayMotionController)
        assert controller.model == model
        assert is_valid_variant_for_bed_type(BED_TYPE_GLIDEAWAY_MOTION, model)
    with pytest.raises(ValueError):
        await create_controller(
            coordinator, BED_TYPE_GLIDEAWAY_MOTION, protocol_variant="auto", client=None
        )
    assert not is_valid_variant_for_bed_type(BED_TYPE_GLIDEAWAY_MOTION, "auto")
    assert not requires_pairing(BED_TYPE_GLIDEAWAY_MOTION)
    assert not bed_type_has_position_feedback(BED_TYPE_GLIDEAWAY_MOTION, "motion_400")
    from custom_components.adjustable_bed.detection import bed_type_label

    choices = {o["value"]: o["label"] for o in get_bed_type_options()}
    assert all(
        "Glideaway" in choices[f"glideaway_motion:{model}"] for model in GLIDEAWAY_MOTION_MODELS
    )
    # Okin ORE is a protocol route, off the list, and names no Glideaway app.
    assert BED_TYPE_OKIN_ORE not in choices
    assert "Glideaway" not in bed_type_label(BED_TYPE_OKIN_ORE)
    assert hidden_generic_fields(BED_TYPE_GLIDEAWAY_MOTION, "motion_400") == {
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
    }
    assert per_side_profile(BED_TYPE_GLIDEAWAY_MOTION, "motion_400").variant_owned


@pytest.fixture
async def alarm_target(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Glideaway",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:68",
            CONF_NAME: "Glideaway",
            CONF_BED_TYPE: BED_TYPE_GLIDEAWAY_MOTION,
            CONF_PROTOCOL_VARIANT: "motion_400",
            CONF_MOTOR_PULSE_COUNT: 1,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = gm.GlideawayMotionController(coordinator, model="motion_400")
    coordinator.async_execute_controller_command = AsyncMock()
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_ADDRESS])}
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await services.async_register_services(hass)
    return coordinator, device.id


async def test_alarm_service_validation_and_queue(hass, alarm_target):
    coordinator, device_id = alarm_target
    calls = {"device_id": [device_id], "enabled": True, "time": "06:30:00", "wake_mode": "memory_1"}
    await hass.services.async_call(DOMAIN, "glideaway_set_alarm", calls, blocking=True)
    coordinator.async_execute_controller_command.assert_awaited_once()
    command = coordinator.async_execute_controller_command.await_args.args[0]
    controller = MagicMock(spec=gm.GlideawayMotionController)
    controller.configure_clock_alarm = AsyncMock()
    await command(controller)
    controller.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(), hour=6, minute=30, preset="memory_1"
    )
    coordinator.async_execute_controller_command.reset_mock()
    for invalid in ({**calls, "time": "06:30:01"}, {"device_id": [device_id], "enabled": True}):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "glideaway_set_alarm", invalid, blocking=True)
    coordinator.async_execute_controller_command.assert_not_awaited()
    coordinator._bed_type = BED_TYPE_OKIN_ORE
    coordinator._controller = MagicMock(spec=BedController, requires_disconnected_transport=False)
    with pytest.raises(ServiceValidationError, match="does not support Glideaway alarms"):
        await hass.services.async_call(DOMAIN, "glideaway_set_alarm", calls, blocking=True)
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("model", GLIDEAWAY_MOTION_MODELS)
async def test_manual_setup_saves_explicit_app_model(hass, model):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "typed", f"glideaway_motion:{model}", "AA:BB:CC:DD:EE:68")
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_BED_TYPE] == BED_TYPE_GLIDEAWAY_MOTION
    assert saved[CONF_PROTOCOL_VARIANT] == model


@pytest.mark.parametrize(
    "model,extra",
    [("motion_400", False), ("motion_450", False), ("motion_500", True), ("motion_600", True)],
)
@pytest.mark.parametrize("retained_massage", [False, True])
async def test_entity_exposure_follows_the_model(
    hass, alarm_target, model, extra, retained_massage
):
    from custom_components.adjustable_bed import sensor
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.cover import _cover_entities_for

    coordinator, _ = alarm_target
    coordinator._has_massage = retained_massage
    controller = gm.GlideawayMotionController(coordinator, model=model)
    coordinator._controller = controller
    covers = _cover_entities_for(hass, coordinator)
    assert len(covers) == len(gm.LAYOUTS[model])
    buttons = _button_entities_for(hass, coordinator)
    keys = {b.entity_description.key for b in buttons if hasattr(b, "entity_description")}
    assert {
        "preset_flat",
        "preset_zero_g",
        "preset_anti_snore",
        "program_memory_1",
        "program_memory_2",
    } <= keys
    assert ("toggle_light" in keys) == extra
    assert ("massage_all_off" in keys) == extra
    assert ("massage_all_up" in keys) == extra
    assert ("massage_all_down" in keys) == extra
    assert ("massage_wave_frequency_up" in keys) == extra
    assert ("massage_wave_frequency_down" in keys) == extra
    assert ("massage_mode_step" in keys) == extra
    assert "massage_all_toggle" not in keys
    assert "massage_head_up" not in keys
    received = []
    await sensor.async_setup_entry(hass, coordinator.entry, received.extend)
    assert any(s.unique_id == coordinator.entity_unique_id(gm.STATE_ALARM) for s in received)
    assert (
        any(s.unique_id == coordinator.entity_unique_id(gm.STATE_TIMER) for s in received) == extra
    )


@pytest.mark.parametrize(
    "method,frame",
    [
        ("preset_flat", "e6fe160000000800fd"),
        ("preset_zero_g", "e6fe160010000000f5"),
        ("preset_anti_snore", "e6fe16008000000085"),
        ("lights_toggle", "e6fe16000002000003"),
        ("massage_off", "e6fe16000100000004"),
        ("massage_intensity_up", "e6fe16000c000000f9"),
        ("massage_intensity_down", "e6fe16000080010084"),
        ("massage_wave_frequency_up", "e6fe160000001000f5"),
        ("massage_wave_frequency_down", "e6fe16000000040001"),
        ("massage_mode_step", "e6fe16000200000003"),
    ],
)
async def test_entity_actions_use_live_vectors(coordinator, instant, method, frame):
    controller = gm.GlideawayMotionController(coordinator, model="motion_600")
    await getattr(controller, method)()
    assert written(coordinator) == [bytes.fromhex(frame), ZERO, ZERO]


async def test_complete_f4_and_signed_alarm_state(coordinator):
    controller = gm.GlideawayMotionController(coordinator, model="motion_600")
    packet = bytearray(40)
    packet[:2] = b"\xf4\xfe"
    packet[19] = 4
    controller._on_notification(MagicMock(), packet)
    assert coordinator.controller_state[gm.STATE_TIMER] == 40
    controller._on_notification(MagicMock(), bytearray.fromhex("ed8003ff800177"))
    assert coordinator.controller_state[gm.STATE_ALARM] == "on"
    assert coordinator.controller_state["glideaway_motion_alarm_hour"] == -1
    assert coordinator.controller_state["glideaway_motion_alarm_minute"] == -128
    assert coordinator.controller_state["glideaway_motion_alarm_wake"] == "none"


async def test_public_hold_and_sync_clock_dispatch(hass, alarm_target):
    coordinator, device_id = alarm_target
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {"device_id": [device_id], "control": "back_up", "duration": 0.6},
        blocking=True,
    )
    controller = MagicMock()
    controller.hold_control = AsyncMock()
    await coordinator.async_execute_controller_command.await_args.args[0](controller)
    controller.hold_control.assert_awaited_once_with("back_up", 600)
    coordinator.async_execute_controller_command.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device_id], "control": "tilt_up", "duration": 0.6},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
    await hass.services.async_call(DOMAIN, "sync_clock", {"device_id": [device_id]}, blocking=True)
    controller.sync_clock = AsyncMock()
    await coordinator.async_execute_controller_command.await_args.args[0](controller)
    controller.sync_clock.assert_awaited_once()


async def test_alarm_whole_selection_validation_before_dispatch(hass, alarm_target):
    coordinator, device_id = alarm_target
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:69", CONF_BED_TYPE: BED_TYPE_OKIN_ORE},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    other = AdjustableBedCoordinator(hass, entry)
    other.async_execute_controller_command = AsyncMock()
    hass.data[DOMAIN][entry.entry_id] = other
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_ADDRESS])}
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "glideaway_set_alarm",
            {"device_id": [device_id, device.id], "enabled": True, "time": "06:30:00"},
            blocking=True,
        )
    coordinator.async_execute_controller_command.assert_not_awaited()
    other.async_execute_controller_command.assert_not_awaited()
