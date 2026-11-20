"""SUTA accepted name gates, actual transport, gestures and notification fences."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.suta import controller as bed
from custom_components.adjustable_bed.beds.suta.receive import TextReceiver, moon, temp
from custom_components.adjustable_bed.codec import suta as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.suta import (
    PROFILES,
    ROUTES,
    profile_for_name,
    route_for_name,
    service_for_name,
)
from custom_components.adjustable_bed.setup_questions import setup_profile
from custom_components.adjustable_bed.state_keys import massage_intensity
from tests.test_controller_contract import _FactoryCoordinator

ROUTE_ROWS = json.loads((Path(__file__).parent / "fixtures/suta/routes.json").read_text())


def char(uuid, *properties):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=7)


def make(name="SUTA-B905"):
    c = _FactoryCoordinator()
    c.entry.data[const.CONF_BLE_DEVICE_NAME] = name
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    c.client._backend = None
    write = char("last-writer", "write-without-response", "notify")
    notify = char("notify-role", "indicate")
    service = SimpleNamespace(uuid=service_for_name(name), characteristics=[char("first-writer", "write"), notify, write])
    c.client.services.get_service.side_effect = lambda uuid: service if uuid == service.uuid else None
    controller = bed.SutaController(c)
    c.controller = controller
    return controller, c


def written(c):
    return [call.args[1] for call in c.client.write_gatt_char.call_args_list]


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real_sleep = asyncio.sleep

    async def pause(seconds, cancel):
        if cancel.is_set():
            return True
        now[0] += seconds
        await real_sleep(0)
        return cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "pause", pause)
    return now


@pytest.mark.parametrize("row", ROUTE_ROWS, ids=lambda row: row["id"])
def test_all_name_routes(row):
    key = row["id"]
    name = "SUTA-unknown" if key == "fallback" else "SUTA" if key == "short-name" else key.split("*")[0]
    assert route_for_name(name) == key
    assert ROUTES[key] == row["controller"]
    profile = profile_for_name(name)
    assert (profile.key if profile else None) == row["controller"]


@pytest.mark.parametrize(("name", "service"), [("SUTA-YOGA", "fff0"), ("SUTA-YOGABED", "ffe0"), ("SUTA-ROLL", "fff0"), ("SUTA-ROLLSOFA", "ffe0"), ("SUTA-STOR", "fff0"), ("SUTA-STORAGE", "ffe0"), ("SUTA-MOON1", "ffe0")])
def test_full_name_transport_differs_from_nine_character_ui(name, service):
    assert service_for_name(name)[4:8] == service


async def test_factory_uses_raw_name_and_preserves_display_title():
    _, c = make("SUTA-B202D")
    c.entry.title = "A friendly bed"
    controller = await create_controller(c, "suta", "auto", c.client, device_name="SUTA-B905")
    assert controller.profile.key == "MattressControllerM510Fragment"
    assert c.entry.title == "A friendly bed"


async def test_property_selected_last_writer_and_write_precedence(clock):
    controller, c = make()
    await controller.start_notify()
    assert c.client.start_notify.await_count == 1
    assert c.client.start_notify.call_args.args[0].uuid == "notify-role"
    await controller.preset_tv()
    call = c.client.write_gatt_char.call_args
    assert call.args[0].uuid == "last-writer"
    assert call.kwargs["response"] is True
    assert call.args[1] == codec.text("AT+MODE=BOTH TV")


async def test_missing_gatt_never_falls_back_to_fixed_uuid(clock):
    controller, c = make()
    c.client.services.get_service.return_value = None
    c.client.services.get_service.side_effect = None
    with pytest.raises(ValueError, match="service is missing"):
        await controller.start_notify()
    c.client.write_gatt_char.assert_not_awaited()


async def test_b905_recall_at_3_2_and_save_at_4_0_4_2_after_reset(clock):
    controller, c = make()
    await controller.start_notify()
    assert controller.profile.threshold_s == 4
    stamps = []

    async def record(*args, **kwargs):
        stamps.append(clock[0])

    c.client.write_gatt_char.side_effect = record
    await controller.hold_control("both_set_tv", 3200)
    assert written(c) == [codec.text("AT+MODE=BOTH TV")]
    c.client.write_gatt_char.reset_mock()
    stamps.clear()
    start = clock[0]
    await controller.hold_control("both_set_tv", 4201)
    assert written(c) == [codec.text("AT+SETMODE=BOTH TV")] * 2
    assert stamps == pytest.approx([start + 4.0, start + 4.2])


async def test_short_valid_hold_first_frame_and_proven_stop(clock):
    controller, c = make("SUTA-B402")
    await controller.start_notify()
    await controller.hold_control("ctrl_two_up", 1)
    assert written(c) == [codec.text("AT+CTRL=BOTH TWO UP"), *([codec.text("AT+CTRL=BOTH STOP")] * 4)]


async def test_slow_write_does_not_backfill_movement(clock):
    controller, c = make("SUTA-B803")
    await controller.start_notify()

    async def slow(*args, **kwargs):
        clock[0] += 2

    c.client.write_gatt_char.side_effect = slow
    await controller.hold_control("ctrl_back_up", 1000)
    assert written(c) == [codec.text("AT+CTRL=BOTH BACK UP"), *([codec.text("AT+CTRL=BOTH STOP")] * 2)]


async def test_cleanup_uses_fresh_cancel_and_captured_session(clock):
    controller, c = make("SUTA-B803")
    await controller.start_notify()
    first = True

    async def cancel(*args, **kwargs):
        nonlocal first
        if first:
            c.cancel_command.set()
            first = False

    c.client.write_gatt_char.side_effect = cancel
    await controller.hold_control("ctrl_back_up", 1000)
    assert written(c)[1:] == [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_stale_notification_and_cleanup_do_not_touch_replacement(clock):
    controller, c = make()
    await controller.start_notify()
    sender, callback = c.client.start_notify.call_args.args
    link = controller._link
    controller.on_disconnect()
    new, _ = make()
    c.controller = new
    callback(sender, bytearray(b"+OK:GD=2611161210\r\n"))
    await controller._release(link)
    assert not controller.observations
    assert not written(c)


async def test_snore_delay_is_owned_and_cancelled_not_replayed(clock, monkeypatch):
    controller, c = make()
    await controller.start_notify()
    original = bed.pause

    async def cancel_delayed(seconds, cancel):
        if seconds == 60:
            c.cancel_command.set()
        return await original(seconds, cancel)

    monkeypatch.setattr(bed, "pause", cancel_delayed)
    await controller.action("snore_cycle")
    assert written(c) == [codec.text("AT+MODE=BOTH SNORE")] * 3


async def test_n520_does_not_infer_position_state_from_shared_parser(clock):
    controller, c = make("SUTA-N520")
    await controller.start_notify()
    sender, callback = c.client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("00000a000000140000"))
    assert not controller.observations
    assert not controller.supports_position_feedback


def test_temp_version_repair_and_separate_moon_decoder():
    a081 = bytes.fromhex("5359a08100041a0b10016b5443")
    a001 = bytes.fromhex("5359a00100041a0b1001eb5443")
    assert temp(a081)["firmware_version"] == 1
    assert temp(a001) == {}
    assert moon(a001)["firmware_version"] == 1
    assert moon(a081) == {}


def test_text_fragment_behavior_and_alarm_fields():
    receiver = TextReceiver()
    assert receiver.feed(b"+OK:GD=261116") == {}
    assert receiver.feed(b"1210\r\n") == {}
    assert receiver.feed(b"+ERR:bad\r\n") == {}
    assert TextReceiver().feed(b"+OK:GA=0106300101\r\n")["alarm"] == {"weekday": 1, "key": "06300101", "time": "0630", "loop": "01", "enabled": "01"}
    receiver = TextReceiver()
    assert receiver.feed(b"+OK:Version=1.0,") == {}
    assert receiver.feed(b"Update=261116\r\n")["version"] == "1.0\n261116"


async def test_adaptive_stiffness_requires_observed_mode_but_fixed_soft_is_usable(clock):
    controller, c = make("SUTA-MOON")
    await controller.start_notify()
    with pytest.raises(ValueError, match="current MOON"):
        await controller.execute_request(bed.Request("adaptive_4_stiff", logical_side=1))
    await controller.execute_request(bed.Request("adaptive_4_soft", logical_side=1))
    sender, callback = c.client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("5359970400020103475443"))
    await controller.execute_request(bed.Request("adaptive_4_stiff", logical_side=1))
    assert written(c)[-1] == codec.binary(0x97, 4, bytes((1, 1)))


async def test_temp_startup_and_side_domains(clock):
    controller, c = make("SUTA-TEMP")
    await controller.start_notify()
    await controller.async_after_connect(MagicMock())
    assert written(c) == [codec.binary(0xA1, 5, b"\x0f"), codec.binary(0xA0, 1, b"\x0f")]
    with pytest.raises(ValueError):
        await controller.execute_request(bed.Request("temperature_setpoint", logical_side=1, value=21))
    await controller.execute_request(bed.Request("temperature_setpoint", logical_side=2, value=40))
    assert written(c)[-1] == codec.binary(0xA1, 3, bytes((2, 40)))


def test_capabilities_and_dead_rows_are_model_specific():
    b905, _ = make("SUTA-B905")
    assert b905.memory_slot_count == 0
    b702, _ = make("SUTA-B702")
    assert b702.memory_slot_count == 4
    b803, _ = make("SUTA-B803")
    assert b803.memory_slot_count == 3
    assert not b803.supports_lights
    assert not b803.supports_synchro
    assert "ctrl_two_down" not in PROFILES["MattressControllerB805Fragment"].commands
    assert "set_mode_both_m2" not in PROFILES["MattressControllerB901Fragment"].commands


def test_setup_requires_raw_name_and_owns_generic_expansion():
    profile = setup_profile("suta")
    assert profile is not None and profile.validate is not None and profile.derive is not None
    assert profile.validate({const.CONF_BLE_DEVICE_NAME: "SUTA-TEMP"}) == {}
    assert profile.validate({const.CONF_BLE_DEVICE_NAME: "SUTA"}) != {}
    assert profile.validate({const.CONF_BLE_DEVICE_NAME: "SUTA-DRAWER"}) != {}
    assert profile.derive({const.CONF_BLE_DEVICE_NAME: "SUTA-B905"})[const.CONF_MOTOR_PULSE_DELAY_MS] == 150
    assert profile.derive({const.CONF_BLE_DEVICE_NAME: "SUTA-RBHC"})[const.CONF_DISABLE_ANGLE_SENSING] is False


@pytest.mark.parametrize(("name", "control", "count", "first", "interval"), [
    ("SUTA-B803", "set_mode_both_m1", 2, 3.0, 0.2),
    ("SUTA-B905", "both_set_tv", 2, 4.0, 0.2),
    ("SUTA-N520", "both_set_snore", 3, 3.1, 0.1),
    ("SUTA-N520", "both_set_tv", 3, 3.1, 0.1),
    ("SUTA-N520", "set_mode_zerog", 3, 3.1, 0.1),
])
async def test_dedicated_save_completes_proven_burst_under_radio_latency(clock, name, control, count, first, interval):
    controller, c = make(name)
    await controller.start_notify()
    stamps = []

    async def delayed_write(*args, **kwargs):
        stamps.append(clock[0])
        clock[0] += 0.25

    c.client.write_gatt_char.side_effect = delayed_write
    await controller.action(control)
    command = controller.profile.commands[control]
    assert written(c) == [codec.text(command.text)] * count
    assert stamps == pytest.approx([first + i * (0.25 + interval) for i in range(count)])


async def test_user_finite_save_hold_keeps_elapsed_deadline_under_radio_latency(clock):
    controller, c = make("SUTA-B803")
    await controller.start_notify()

    async def delayed_write(*args, **kwargs):
        clock[0] += 0.25

    c.client.write_gatt_char.side_effect = delayed_write
    await controller.hold_control("set_mode_both_m1", 3201)
    assert written(c) == [codec.text("AT+SETMODE=BOTH M1")]


async def test_dedicated_save_cancellation_after_submission_suppresses_remaining_burst(clock):
    controller, c = make("SUTA-B905")
    await controller.start_notify()

    async def stop_after_write(*args, **kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = stop_after_write
    await controller.action("both_set_tv")
    assert written(c) == [codec.text("AT+SETMODE=BOTH TV")]


async def test_dedicated_save_cancelled_during_countdown_does_not_recall(clock, monkeypatch):
    controller, c = make("SUTA-B905")
    await controller.start_notify()
    original = bed.pause

    async def release_while_waiting(seconds, cancel):
        controller.on_gesture_release()
        cancel.set()
        return await original(seconds, cancel)

    monkeypatch.setattr(bed, "pause", release_while_waiting)
    await controller.action("both_set_tv")
    assert not written(c)


async def test_dedicated_save_never_finishes_burst_on_replacement_session(clock):
    controller, c = make("SUTA-B905")
    await controller.start_notify()

    async def replace_after_write(*args, **kwargs):
        controller.on_disconnect()

    c.client.write_gatt_char.side_effect = replace_after_write
    with pytest.raises(ConnectionError, match="session changed"):
        await controller.action("both_set_tv")
    assert written(c) == [codec.text("AT+SETMODE=BOTH TV")]


def _labels(controller):
    return {spec.key: (spec.translation_placeholders or {}).get("action", spec.name) for spec in controller.controller_button_specs}


def test_entity_labels_follow_the_app_buttons():
    b702, _ = make("SUTA-B702")
    labels = _labels(b702)
    assert labels["suta_ctrl_two_up"] == "Back and foot up"
    assert labels["suta_ctrl_bott_down"] == "Storage lift down"
    assert labels["suta_both_set_tv"] == "Save TV position"
    save = next(spec for spec in b702.controller_button_specs if spec.key == "suta_both_set_tv")
    assert save.hold is None and save.requires_confirmation
    assert labels["suta_release"] == "Release held control"
    assert {s.key for s in b702.controller_switch_specs} == {"suta_lock"}
    b402, _ = make("SUTA-B402")
    assert _labels(b402)["suta_ctrl_two_up"] == "Whole bed up"
    assert "suta_snore_cycle" not in _labels(b402)
    b905, _ = make("SUTA-B905")
    labels = _labels(b905)
    # Massage steps are the shared head, foot and overall massage levels.
    assert not any(key.startswith("suta_mass_") for key in labels)
    assert b905.massage_intensity_zones == ["head", "foot", "all"]
    assert b905.massage_intensity_max == 3 and b905.auto_enable_massage
    assert labels["suta_beep_enable"] == "Enable beep"
    beep = next(s for s in b905.controller_button_specs if s.key == "suta_beep_enable")
    assert beep.diagnostic and not beep.entity_registry_enabled_default
    # Queries and unlabeled app gestures stay reachable only through the action.
    assert not {"suta_get_sys_version", "suta_get_alarm", "suta_get_date"} & labels.keys()
    rbhc, _ = make("SUTA-RBHC1")
    assert not {"suta_angle_on", "suta_angle_off"} & _labels(rbhc).keys()
    moon_, _ = make("SUTA-MOON")
    labels = _labels(moon_)
    assert labels["suta_adaptive_14_soft_0203"] == "Right adaptive mode 5: soft"
    assert not any(key.startswith(("suta_massage_strength_", "suta_massage_timer_")) for key in labels)
    assert [s.key for s in moon_.controller_select_specs] == [
        "suta_left_massage_timer",
        "suta_right_massage_timer",
    ]
    assert [s.key for s in moon_.controller_number_specs] == [
        "suta_left_massage_strength",
        "suta_right_massage_strength",
    ]
    assert not any(key.startswith(("suta_automatic_adjustment", "suta_firmware_version")) for key in labels)
    temp_, _ = make("SUTA-TEMP")
    assert _labels(temp_)["suta_heating_timer_020a"] == "Right heating timer 10 h"
    for controller in (b702, b402, b905, rbhc, moon_, temp_):
        names = list(_labels(controller).values())
        assert len(names) == len(set(names))


async def test_switches_send_the_app_frames_and_read_reported_state(clock):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    left = next(s for s in moon_.controller_switch_specs if s.key == "suta_automatic_adjustment_1")
    await left.set_fn(moon_, True)
    assert written(c)[-1] == codec.binary(0x97, 0x0B, bytes((1, 1)))
    sender, callback = c.client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("5359970d000800020a0000020a01") + bytes((0, 0, 0)))
    states = {update.key: update.value for update in c.handle_controller_state_updates.call_args.args}
    assert states[bed.AUTOMATIC_ADJUSTMENT[1]] is True
    assert states[bed.AUTOMATIC_ADJUSTMENT[2]] is False

    temp_, c = make("SUTA-TEMP")
    await temp_.start_notify()
    heating, light = temp_.controller_switch_specs
    await heating.set_fn(temp_, False)
    await light.set_fn(temp_, True)
    assert written(c)[-2:] == [codec.binary(0xA1, 1, b"\x00"), codec.binary(0xA1, 2, b"\x01")]

    b402, c = make("SUTA-B402")
    await b402.start_notify()
    (lock,) = b402.controller_switch_specs
    assert lock.state_key is None
    await lock.set_fn(b402, True)
    assert written(c)[-1] == codec.text("AT+SETLOCK=ON")


def test_one_off_alarm_is_the_next_day_without_the_loop_flag():
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest

    controller, _ = make("SUTA-B905")
    # Wednesday 07:00, so 06:30 is next on Thursday: wire day 4 counting from Sunday 0.
    reference = datetime(2026, 11, 18, 7, 0, tzinfo=UTC)
    alarm = AlarmRequest(enabled=True, hour=6, minute=30, reference_time=reference)
    assert controller._alarm_texts(alarm) == ("AT+SA=04063000",)
    assert make("SUTA-MOON")[0].alarm_capability is None


@pytest.mark.parametrize(("zone", "key"), [("head", "mass_head_dt"), ("foot", "mass_foot_dt")])
async def test_massage_levels_send_the_step_buttons_frames(clock, zone, key):
    """Each level is the matching step button: off is level 0."""
    command = bed.SHARED.get(key) or make()[0].commands[key]
    for level, suffix in enumerate(command.suffixes):
        by_button, c_button = make()
        await by_button.start_notify()
        c_button.client.write_gatt_char.reset_mock()
        await bed._action(by_button, key=key, suffix=suffix)
        by_number, c_number = make()
        await by_number.start_notify()
        c_number.client.write_gatt_char.reset_mock()
        await by_number.set_massage_intensity(zone, level)
        assert written(c_number) == written(c_button) != []
        states = {
            u.key: u.value
            for call in c_number.handle_controller_state_updates.call_args_list
            for u in call.args
        }
        assert states[massage_intensity(zone)] == level


async def test_overall_massage_level_needs_a_running_zone(clock):
    controller, c = make()
    await controller.start_notify()
    assert not controller.massage_intensity_available("all")
    with pytest.raises(ValueError, match="Enable that massage zone"):
        await controller.set_massage_intensity("all", 2)
    await controller.set_massage_intensity("head", 1)
    assert controller.massage_intensity_available("all")
    c.client.write_gatt_char.reset_mock()
    await controller.set_massage_intensity("all", 2)
    by_number = written(c)
    other, c_other = make()
    await other.start_notify()
    await bed._action(other, key="mass_head_dt", suffix=other.commands["mass_head_dt"].suffixes[1])
    c_other.client.write_gatt_char.reset_mock()
    await bed._action(other, key="mass_head_lv", suffix=other.commands["mass_head_lv"].suffixes[2])
    assert by_number == written(c_other) != []


@pytest.mark.parametrize("side", (1, 2))
async def test_moon_massage_strength_numbers_send_the_strength_buttons_frames(clock, side):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    number = next(
        s for s in moon_.controller_number_specs if s.key.endswith("_massage_strength")
        and s.key.startswith(f"suta_{('left', 'right')[side - 1]}")
    )
    assert (number.native_min_value, number.native_max_value) == (1, 3)
    for level in (1, 2, 3):
        c.client.write_gatt_char.reset_mock()
        await number.set_fn(moon_, level)
        by_number = written(c)
        c.client.write_gatt_char.reset_mock()
        await bed._binary_action(moon_, action=f"massage_strength_{level}", payload=bytes((side, level)))
        assert by_number == written(c) != []


async def test_moon_massage_strength_shows_the_sent_level_until_the_bed_reports(clock):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    left = next(s for s in moon_.controller_number_specs if s.key == "suta_left_massage_strength")
    c.handle_controller_state_updates.reset_mock()
    await left.set_fn(moon_, 3)
    states = {u.key: u.value for u in c.handle_controller_state_updates.call_args.args}
    assert states[bed.MASSAGE_STRENGTH[1]] == 3 and states[bed.MASSAGE_STRENGTH[2]] is None
    # Other state published before the next report keeps the sent level.
    moon_._publish()
    states = {u.key: u.value for u in c.handle_controller_state_updates.call_args.args}
    assert states[bed.MASSAGE_STRENGTH[1]] == 3 and states[bed.MASSAGE_STRENGTH[2]] is None
    # The bed's full-state report replaces it: both sides at strength 2.
    sender, callback = c.client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("5359970d000800020a0000020a01") + bytes((0, 0, 0)))
    states = {u.key: u.value for u in c.handle_controller_state_updates.call_args.args}
    assert states[bed.MASSAGE_STRENGTH[1]] == 2 and states[bed.MASSAGE_STRENGTH[2]] == 2


@pytest.mark.parametrize("side", (1, 2))
async def test_moon_massage_timer_selects_send_the_timer_buttons_frames(clock, side):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    select = next(
        s for s in moon_.controller_select_specs
        if s.key == f"suta_{('left', 'right')[side - 1]}_massage_timer"
    )
    assert select.options == ("10 min", "20 min", "30 min")
    for minutes in (10, 20, 30):
        c.client.write_gatt_char.reset_mock()
        await select.select_fn(moon_, f"{minutes} min")
        by_select = written(c)
        c.client.write_gatt_char.reset_mock()
        await bed._binary_action(moon_, action=f"massage_timer_{minutes}", payload=bytes((side, minutes)))
        assert by_select == written(c) != []
    # Only MOON has per-side massage timers.
    b905, _ = make("SUTA-B905")
    assert b905.controller_select_specs == ()


async def test_moon_massage_timer_shows_the_sent_duration_until_the_bed_reports(clock):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    right = next(s for s in moon_.controller_select_specs if s.key == "suta_right_massage_timer")
    c.handle_controller_state_updates.reset_mock()
    await right.select_fn(moon_, "30 min")
    states = {u.key: u.value for u in c.handle_controller_state_updates.call_args.args}
    assert states[bed.MASSAGE_TIMER[2]] == "30 min" and states[bed.MASSAGE_TIMER[1]] is None
    # The bed's full-state report replaces it: both sides at 10 minutes.
    sender, callback = c.client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("5359970d000800020a0000020a01") + bytes((0, 0, 0)))
    states = {u.key: u.value for u in c.handle_controller_state_updates.call_args.args}
    assert states[bed.MASSAGE_TIMER[1]] == states[bed.MASSAGE_TIMER[2]] == "10 min"


async def test_overall_level_cut_off_between_zones_is_unknown(clock):
    """Stop between the head and foot writes leaves the overall level unknown."""
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    controller, c = make()
    await controller.start_notify()
    await controller.set_massage_intensity("head", 1)
    await controller.set_massage_intensity("foot", 1)
    c.handle_controller_state_updates.reset_mock()
    cancel = c.cancel_command

    async def write(*_args, **_kwargs):
        cancel.set()  # STOP arrives after the head zone's level went out.

    c.client.write_gatt_char.side_effect = write
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="overall-level",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        await controller.set_massage_intensity("all", 2)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert context.frames_written == 1
    assert len(written(c)) >= 1
    states = {
        u.key: u.value for call in c.handle_controller_state_updates.call_args_list for u in call.args
    }
    assert states[massage_intensity("all")] is None


async def test_moon_strength_from_a_replaced_link_is_not_shown(clock):
    moon_, c = make("SUTA-MOON")
    await moon_.start_notify()
    left = next(s for s in moon_.controller_number_specs if s.key == "suta_left_massage_strength")

    async def write(*_args, **_kwargs):
        moon_.on_disconnect()  # The link drops while the write settles.

    c.client.write_gatt_char.side_effect = write
    c.handle_controller_state_updates.reset_mock()
    with contextlib.suppress(ConnectionError, ValueError):
        await left.set_fn(moon_, 3)
    published = [
        u.value
        for call in c.handle_controller_state_updates.call_args_list
        for u in call.args
        if u.key == bed.MASSAGE_STRENGTH[1]
    ]
    assert 3 not in published
