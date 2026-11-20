"""Movement cleanup, native callers and connection-owned Sleep Assist state."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.sleep_assistant import state_keys as keys
from custom_components.adjustable_bed.beds.sleep_assistant.controller import (
    SleepAssistantController,
)
from custom_components.adjustable_bed.codec import sleep_assistant as codec
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
)
from custom_components.adjustable_bed.profiles import sleep_assistant as app
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import _tool, virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

LAYOUT = {
    "services": {codec.SERVICE: [codec.WRITE, codec.NOTIFY]},
    "properties": {codec.WRITE: ["write"], codec.NOTIFY: ["notify"]},
}


def make(clock, *, profile=None, replies=None):
    tool = _tool()
    coordinator = _FactoryCoordinator()
    coordinator.controller_state = {}

    def state(*updates):
        coordinator.controller_state.update((u.key, u.value) for u in updates)

    coordinator.handle_controller_state_updates = state
    coordinator.record_command_trace = Mock()
    recorder = tool.Recorder(clock)
    client = tool.FakeClient(recorder, LAYOUT, replies or {})
    coordinator.client = client
    coordinator.motor_pulse_count = 3
    controller = SleepAssistantController(coordinator, profile)
    coordinator.controller = controller
    return coordinator, controller, client, recorder


def frames(recorder):
    return [event[3] for event in recorder.events if isinstance(event[2], bool)]


@pytest.mark.parametrize("action", ["head_up", "feet_down", "anti_snore_preset", "tv"])
async def test_cancelled_stream_stops_and_finishes_source_neutral(action):
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(presets=("o1", "o2", "o3", "o4"))
        )
        await controller.async_discover_capabilities()
        await controller.start_notify()
        task = asyncio.create_task(controller.run_action(action, held=True, duration_ms=5000))
        await asyncio.sleep(0.25)
        co.cancel_command.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        written = frames(recorder)
        count = 2 if "preset" in action or action == "tv" else 1
        assert written[-count:] == [codec.instruction(0)] * count
        assert all(frame == codec.instruction(app.WORDS[action]) for frame in written[:-count])
        before = list(written)
        await asyncio.sleep(5)
        assert frames(recorder) == before


async def test_cancel_before_classifier_never_emits_delayed_preset():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(presets=("o1",))
        )
        await controller.async_discover_capabilities()
        task = asyncio.create_task(controller.run_action("anti_snore_preset"))
        await asyncio.sleep(0.1)
        co.cancel_command.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert frames(recorder) == [codec.instruction(0)] * 3
        await asyncio.sleep(5)
        assert frames(recorder) == [codec.instruction(0)] * 3


async def test_retired_link_cannot_deliver_callback_or_cleanup_to_replacement():
    with virtual_clock() as clock:
        co, controller, old, recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.start_notify()
        notify = old._subscribers[0][1]
        task = asyncio.create_task(controller.move_head_up())
        await asyncio.sleep(0.05)
        controller.on_disconnect()
        co.client = _tool().FakeClient(recorder, LAYOUT, {})
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        written = frames(recorder)
        assert written == [codec.instruction(1)]
        notify(None, bytearray.fromhex("dd000000000000000000000000004002000000"))
        assert co.controller_state[UNDER_BED_LIGHTS_ON] is None
        await controller.async_discover_capabilities()
        with controller.side_scope("left"), pytest.raises(ServiceValidationError):
            await controller.preset_flat()
        assert frames(recorder) == written


async def test_profile_reconfiguration_and_owner_change_rejected_before_write():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        co.entry.data[app.CONF_SLEEP_ASSISTANT_LIGHTING] = "4193"
        with pytest.raises(ServiceValidationError):
            await controller.set_storage(True)
        assert not frames(recorder)
        co.entry.data.pop(app.CONF_SLEEP_ASSISTANT_LIGHTING)
        co.controller = SleepAssistantController(co)
        with pytest.raises(ServiceValidationError):
            await controller.stop_all()
        assert not frames(recorder)


async def test_native_settings_state_requires_delivery_and_failed_write_stays_unknown():
    with virtual_clock() as clock:
        co, controller, client, recorder = make(clock)
        await controller.async_discover_capabilities()
        token = _CURRENT_COMMAND_CONTEXT.set(
            CommandContext(
                scheduler_token=object(),
                cancel_event=co.cancel_command,
                admitted_stop_epoch=0,
                intent_id="storage",
                kind=CommandKind.COMMAND,
                group_id=None,
                resources=frozenset({"configuration"}),
            )
        )
        co.cancel_command.set()
        await controller.set_storage(True)
        assert co.controller_state[keys.STORAGE] is None
        co.cancel_command.clear()
        await controller.set_storage(True)
        assert co.controller_state[keys.STORAGE] is True
        assert frames(recorder) == [codec.storage(1)]
        _CURRENT_COMMAND_CONTEXT.reset(token)
        client.is_connected = False
        with pytest.raises(ServiceValidationError):
            await controller.set_storage(False)
        assert co.controller_state[keys.STORAGE] is True


async def test_startup_clock_responses_versions_and_parser_qualification():
    with virtual_clock() as clock:
        profile = app.SleepAssistantProfile(
            identity="12345678",
            anti_snore=(2, 5, 6, 7, 8),
            calibration=(1, 2, 3, 4),
            gain=5,
            out_of_bed=("0" * 16, "1" * 16),
        )
        co, controller, _client, recorder = make(clock, profile=profile)
        await controller.async_discover_capabilities()
        await controller.async_on_connect(
            SimpleNamespace(async_start_notify=controller.start_notify)
        )
        assert frames(recorder)[:4] == [
            codec.serial_identity("12345678"),
            codec.bed_calibration(1, 2, 3, 4),
            codec.gain("0", "05"),
            codec.out_of_bed("0" * 16, "1" * 16),
        ]
        controller._receive(bytes.fromhex("8e00000000000000"))
        before = len(frames(recorder))
        await controller.async_refresh_diagnostics()
        assert len(frames(recorder)) == before + 2
        assert all(frame.startswith(b"7308") for frame in frames(recorder)[-2:])
        controller._receive(bytes.fromhex("8b0000021800000200020900"))
        assert controller._hw218
        await asyncio.sleep(3)
        await controller.async_refresh_diagnostics()
        assert profile.anti_snore is not None
        assert frames(recorder)[-2:] == [codec.anti_snore(*profile.anti_snore), codec.anti_hours()]
        controller._receive(bytes.fromhex("ddee0001000000000000000000004002000000"))
        assert co.controller_state[UNDER_BED_LIGHTS_ON] is True
        assert co.controller_state[MASSAGE_TIMER_MINUTES] == 20
        controller._receive(bytes.fromhex("dd000000000000000000000000008001000000"))
        assert co.controller_state[UNDER_BED_LIGHTS_ON] is False
        controller._receive(bytes.fromhex("8a0000000000000000480d0f01000001"))
        assert co.controller_state[keys.HEART["left"]] == 72
        controller.on_disconnect()
        assert co.controller_state[keys.HEART["left"]] is None


async def test_alarm_slots_countdown_and_rgb_native_controls():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(lighting="4193")
        )
        await controller.async_discover_capabilities()
        now = dt_util.now()
        alarm = AlarmRequest(
            enabled=True,
            slot=1,
            hour=7,
            minute=30,
            weekdays=(0, 6),
            wake_action="zero_g",
            reference_time=now,
        )
        await controller.configure_alarm(alarm)
        assert frames(recorder)[0] == codec.alarm(1, 7, 30, "0", 3, True)
        with pytest.raises(ServiceValidationError):
            controller.validate_alarm(replace(alarm, wake_action="flat"))
        recorder.events.clear()
        await controller.set_flat_minutes(20)
        assert frames(recorder)[0].startswith(b"7B0706")
        assert co.controller_state[keys.FLAT_MINUTES] == 20
        with pytest.raises(ServiceValidationError):
            await controller.set_flat_minutes(10)
        controller._receive(bytes.fromhex("dd000000000000000000000000004001000000"))
        await controller.set_light_color((1, 2, 3))
        await controller.set_light_level(2)
        assert frames(recorder)[-1] == codec.rgb_channels(1, 2, 3, 0.6)
        assert controller.memory_slot_count == 0 and not controller.supports_memory_programming


@pytest.mark.parametrize(
    ("action", "first", "neutral"),
    [("flat", 0, 1300), ("zero_gravity", 400, 1300), ("anti_snore_preset", 600, 1500)],
)
async def test_tap_timing_from_classifier_and_invocation(action, first, neutral):
    with virtual_clock() as clock:
        _co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(presets=("o1",))
        )
        await controller.async_discover_capabilities()
        await controller.run_action(action)
        writes = [event for event in recorder.events if isinstance(event[2], bool)]
        assert round(writes[0][0] * 1000) == first
        assert [round(event[0] * 1000) for event in writes[1:]] == [
            neutral,
            neutral + 200,
            neutral + 400,
        ]


async def test_motor_refresh_keeps_200ms_cadence_and_release_from_end_of_hold():
    with virtual_clock() as clock:
        _co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.hold_control("head_up", 600)
        writes = [event for event in recorder.events if isinstance(event[2], bool)]
        assert [round(event[0] * 1000) for event in writes] == [0, 200, 400, 1400]


async def test_post_write_retirement_cannot_republish_into_new_owner():
    with virtual_clock() as clock:
        co, controller, client, _recorder = make(clock)
        await controller.async_discover_capabilities()
        started, finish = asyncio.Event(), asyncio.Event()

        async def blocked_write(*_args, **_kwargs):
            started.set()
            await finish.wait()

        client.write_gatt_char = blocked_write
        token = _CURRENT_COMMAND_CONTEXT.set(
            CommandContext(
                scheduler_token=object(),
                cancel_event=co.cancel_command,
                admitted_stop_epoch=0,
                intent_id="retirement",
                kind=CommandKind.COMMAND,
                group_id=None,
                resources=frozenset({"configuration"}),
            )
        )
        try:
            task = asyncio.create_task(controller.set_storage(True))
            await started.wait()
            controller.on_disconnect()
            co.controller = SleepAssistantController(co)
            co.controller_state[keys.STORAGE] = False
            finish.set()
            with pytest.raises(ServiceValidationError):
                await task
            assert co.controller_state[keys.STORAGE] is False
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)


@pytest.mark.parametrize("change", ["owner_missing", "saved_route"])
async def test_absent_owner_and_changed_saved_route_reject_even_cleanup(change):
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        if change == "owner_missing":
            co.controller = None
        else:
            co.entry.data["bed_type"] = "keeson"
        with pytest.raises(ServiceValidationError):
            await controller.stop_all()
        assert not frames(recorder)


async def test_retained_physical_link_resumes_notifications_after_failed_disconnect():
    with virtual_clock() as clock:
        co, controller, client, _recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.start_notify()
        old = client._subscribers[-1][1]
        await controller.stop_notify()
        assert client.is_connected
        await controller.async_resume_session()
        old(None, bytearray.fromhex("90000000000100"))
        assert co.controller_state[keys.STORAGE] is None
        client._subscribers[-1][1](None, bytearray.fromhex("90000000000100"))
        assert co.controller_state[keys.STORAGE] is True
        await controller.set_storage(False)
        assert co.controller_state[keys.STORAGE] is False


async def test_clock_gap_preemption_retains_unsent_reply():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        controller._receive(bytes.fromhex("8e00000000000000"))
        task = asyncio.create_task(controller.async_refresh_diagnostics())
        await asyncio.sleep(0.05)
        co.cancel_command.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert controller._clock_pending == 1
        assert len(frames(recorder)) == 1
        co.cancel_command.clear()
        await controller.async_refresh_diagnostics()
        assert controller._clock_pending == 0
        assert len(frames(recorder)) == 2


async def test_only_supplied_anti_snore_level_and_latest_successful_intent_reconnect():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(anti_snore=(2, 5, 6, 7, 8))
        )
        await controller.async_discover_capabilities()
        assert controller.controller_select_specs[0].options == ("off", "mid")
        with pytest.raises(ServiceValidationError):
            await controller.set_anti_snore("high")
        assert not frames(recorder)
        await controller.set_anti_snore("off")
        controller._receive(bytes.fromhex("8b0000021800000200020900"))
        await asyncio.sleep(3)
        await controller.async_refresh_diagnostics()
        assert codec.anti_snore(2, 5, 6, 7, 8) not in frames(recorder)
        controller.on_disconnect()
        replacement = SleepAssistantController(co, controller.profile)
        co.controller = replacement
        await replacement.async_discover_capabilities()
        replacement._receive(bytes.fromhex("8b0000021800000200020900"))
        await asyncio.sleep(3)
        await replacement.async_refresh_diagnostics()
        assert codec.anti_snore(2, 5, 6, 7, 8) not in frames(recorder)
        assert frames(recorder)[-2] == codec.anti_snore(0, 5, 6, 7, 8)


async def test_alarm_six_is_one_shot_and_both_paths_invalidate_and_refresh():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.set_flat_minutes(20)
        assert frames(recorder)[-1] == codec.ALARM_QUERY
        assert co.controller_state[keys.FLAT_MINUTES] == 20
        alarm = AlarmRequest(
            enabled=True,
            slot=6,
            hour=7,
            minute=30,
            wake_action="flat",
            reference_time=dt_util.now(),
        )
        with pytest.raises(ServiceValidationError):
            controller.validate_alarm(replace(alarm, weekdays=(0,)))
        await controller.configure_alarm(alarm)
        assert co.controller_state[keys.FLAT_MINUTES] is None
        for _index in range(6):
            controller._receive(bytes.fromhex("830000071e0080000100"))
        assert "Flat" in co.controller_state[keys.ALARMS[5]]


async def test_brightness_after_reconnect_does_not_guess_black_rgb():
    with virtual_clock() as clock:
        _co, controller, _client, recorder = make(
            clock, profile=app.SleepAssistantProfile(lighting="4193")
        )
        await controller.async_discover_capabilities()
        controller._receive(bytes.fromhex("dd000000000000000000000000004002000000"))
        with pytest.raises(ServiceValidationError):
            await controller.set_light_level(2)
        assert not frames(recorder)
        await controller.set_light_color((12, 34, 56))
        await controller.set_light_level(2)
        assert frames(recorder)[-1] == codec.rgb_channels(12, 34, 56, 0.6)


async def test_multiple_supplied_levels_keep_their_own_parameters():
    with virtual_clock() as clock:
        profile = app.selected(
            {
                app.CONF_SLEEP_ASSISTANT_PARAMETERS: '{"anti_snore":[2,5,6,7,8],"anti_snore_levels":[[1,9,10,11,12],[3,13,14,15,16]]}'
            }
        )
        _co, controller, _client, recorder = make(clock, profile=profile)
        await controller.async_discover_capabilities()
        assert controller.controller_select_specs[0].options == ("off", "high", "mid", "low")
        for label, parameters in (
            ("high", (1, 9, 10, 11, 12)),
            ("mid", (2, 5, 6, 7, 8)),
            ("low", (3, 13, 14, 15, 16)),
        ):
            await controller.set_anti_snore(label)
            assert frames(recorder)[-1] == codec.anti_snore(*parameters)


async def test_startup_neutral_refresh_uses_four_proven_deadlines():
    with virtual_clock() as clock:
        _co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.async_on_connect(
            SimpleNamespace(async_start_notify=controller.start_notify)
        )
        writes = [event for event in recorder.events if isinstance(event[2], bool)]
        neutral = [event for event in writes if event[3] == codec.instruction(0)]
        assert len(neutral) == 4
        times = [round(event[0] * 1000) for event in neutral]
        assert [times[i + 1] - times[i] for i in range(3)] == [300, 200, 300]
        assert times[0] - round(writes[2][0] * 1000) == 507


async def test_matching_flat_readback_keeps_duration_and_changed_slot_invalidates():
    with virtual_clock() as clock:
        co, controller, _client, recorder = make(clock)
        await controller.async_discover_capabilities()
        await controller.set_flat_minutes(20)
        body = bytes.fromhex(frames(recorder)[0].decode("ascii"))
        reply = bytes((0x83, 0, 0, body[3], body[4], 0, 0x80, 0, 1, 0))
        for _ in range(6):
            controller._receive(reply)
        assert co.controller_state[keys.FLAT_MINUTES] == 20
        changed = bytearray(reply)
        changed[4] = (changed[4] + 1) % 60
        for _ in range(6):
            controller._receive(bytes(changed))
        assert co.controller_state[keys.FLAT_MINUTES] is None
        await controller.set_flat_minutes(0)
        for _ in range(6):
            controller._receive(bytes.fromhex("83000000000000000000"))
        assert co.controller_state[keys.FLAT_MINUTES] == 0
