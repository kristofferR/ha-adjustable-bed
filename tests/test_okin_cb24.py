"""SmartBed's runtime uses captured links and the app's profile-specific commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.smartbed import state_keys as keys
from custom_components.adjustable_bed.beds.smartbed.controller import OkinCB24Controller
from custom_components.adjustable_bed.beds.smartbed.discovery import discover, select_profile
from custom_components.adjustable_bed.command_scheduler import CommandContext, CommandKind
from custom_components.adjustable_bed.const import BED_TYPE_OKIN_CB24
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.smartbed import PROFILES, Function
from tests.error_helpers import raises_key
from tests.test_controller_contract import _FactoryCoordinator


def _hold_context(event: asyncio.Event, deadline: float | None = None) -> CommandContext:
    return CommandContext(
        scheduler_token=object(), cancel_event=event, admitted_stop_epoch=0,
        intent_id="held-massage", kind=CommandKind.HOLD, group_id=None,
        resources=frozenset({"*"}), hold_deadline=deadline,
    )


@pytest.fixture
async def make(monkeypatch):
    clock = [0.0]
    original_sleep = asyncio.sleep
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "time", lambda: clock[0])

    async def sleep(seconds):
        clock[0] += seconds
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)

    def create(profile="cb24", *, motors=2, properties=("write", "write-without-response"), side=0):
        coordinator = _FactoryCoordinator()
        coordinator.motor_count = motors
        coordinator.controller_state = ControllerState()
        coordinator.record_command_trace = MagicMock()
        coordinator.handle_controller_state_update = lambda key, value: (
            coordinator.controller_state.update({key: value})
        )
        coordinator.handle_controller_state_updates = lambda *updates: (
            coordinator.controller_state.update({u.key: u.value for u in updates})
        )
        transport = PROFILES[profile].transport
        write = cast(
            BleakGATTCharacteristic,
            SimpleNamespace(uuid=transport[1], properties=properties, handle=1),
        )
        notify = cast(
            BleakGATTCharacteristic,
            SimpleNamespace(uuid=transport[3], properties=("notify",), handle=2),
        )
        services = [SimpleNamespace(uuid=transport[0], characteristics=[write])]
        if transport[2] == transport[0]:
            services[0].characteristics.append(notify)
        else:
            services.append(SimpleNamespace(uuid=transport[2], characteristics=[notify]))
        events = []
        client = MagicMock(spec=BleakClient)
        client.services, client.is_connected = services, True

        async def write_gatt(char, frame, *, response):
            events.append((clock[0], char, bytes(frame), response))

        client.write_gatt_char = AsyncMock(side_effect=write_gatt)
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()
        coordinator.client = client
        controller = OkinCB24Controller(
            cast(AdjustableBedCoordinator, coordinator),
            protocol_variant=profile,
            motors=motors,
            bed_selection=side,
        )
        return controller, coordinator, client, events, clock

    return create


@pytest.mark.parametrize(
    "vector", json.loads((Path(__file__).parent / "fixtures/smartbed/arrows.json").read_text())
)
async def test_p5_arrows_use_live_absolute_setters_and_query_after_200ms(make, vector):
    controller, _, _, events, _ = make("cb27new")
    tag = vector["ui_tag"]
    field = (
        "head_intensity"
        if tag.startswith("head")
        else "foot_intensity"
        if tag.startswith("foot")
        else "massage_wave"
    )
    setattr(controller._parser().state, field, vector["cached_state"])
    function = {
        "head_intensity": Function.HEAD_MASSAGE,
        "foot_intensity": Function.FOOT_MASSAGE,
        "massage_wave": Function.WAVE,
    }[field]
    await controller._arrow(function, tag.endswith("increase"))
    assert [(round(t * 1000), frame.hex()) for t, _, frame, _ in events] == [
        (0, vector["expected_first_write"]),
        (200, vector["expected_followup_query"]),
    ]
    assert getattr(controller._parser().state, field) == vector["cached_state"]


@pytest.mark.parametrize(
    "profile,first,stop",
    [
        ("standard", "a55ade00002001", "a55adf00002000"),
        ("cb", "e6fe16010000000004", "e6fe16000000000005"),
        ("cb24", "05020000000100", "05020000000000"),
        ("cb27new", "2a000001010401000000", "aa0000010200"),
    ],
)
async def test_movement_repeats_300ms_and_releases_after_100ms(make, profile, first, stop):
    c, _, _, events, _ = make(profile)
    await c.hold_control("head_up", 650)
    assert [(round(t * 1000), data.hex()) for t, _, data, _ in events] == [
        (0, first),
        (300, first),
        (600, first),
        (750, stop),
    ]


async def test_cancellation_cannot_suppress_release_or_send_to_reconnected_client(make):
    c, coordinator, client, events, _ = make()
    original = client.write_gatt_char.side_effect

    async def cancel(char, frame, *, response):
        await original(char, frame, response=response)
        coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = cancel
    await c.hold_control("head_up", 1000)
    assert [e[2].hex() for e in events] == ["05020000000100", "05020000000000"]
    coordinator.cancel_command.clear()
    old_link = c._capture_link()
    coordinator.client = MagicMock(spec=BleakClient)
    coordinator.client.is_connected = True
    await c._release(old_link, bytes.fromhex("05020000000000"))
    assert len(events) == 2
    with raises_key("smartbed_session_changed"):
        await c._write(old_link, bytes.fromhex("05020000000100"))


async def test_old_preset_tap_does_not_save_but_explicit_save_holds_5200ms(make):
    c, _, _, events, _ = make()
    await c.preset_memory(1)
    assert [e[2].hex() for e in events] == ["05020001000000", "05020000000000"]
    events.clear()
    await c.save("zero_g")
    assert len(events) == 19  # immediate + 17 refreshes, then STOP
    assert round((events[-1][0] - events[0][0]) * 1000) == 5300
    assert all(e[2].hex() == "05020000100000" for e in events[:-1])
    assert all(
        spec.hold is None and (spec.requires_confirmation or "memory" in spec.key)
        for spec in c.controller_button_specs
        if "save" in spec.key
    )


async def test_p5_recall_and_save_are_distinct_and_memory_slots_are_real(make):
    c, _, _, events, _ = make("cb27new")
    await c.preset_memory(1)
    await c.program_memory(2)
    await c.save("tv")
    assert [e[2].hex() for e in events] == ["2a000001030105", "aa000001050126", "aa000001050123"]
    assert c.memory_slot_count == 2
    with raises_key("option_unavailable"):
        await c.program_memory(3)


@pytest.mark.parametrize(
    "properties,response",
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), True),
    ],
)
async def test_live_gatt_properties_determine_write_type(make, properties, response):
    c, _, _, events, _ = make(properties=properties)
    await c.preset_flat()
    assert all(e[3] is response for e in events)
    assert all(e[1] is c._link.write for e in events)


async def test_p4_alarm_and_clock_use_bcd_while_cb24_stays_binary(make):
    from datetime import datetime

    now = datetime(2026, 11, 19, 17, 42, 58)
    c, _, _, events, _ = make(motors=5)
    await c.configure_alarm(
        AlarmRequest(enabled=True, hour=23, minute=45, wake_action="zero_g", reference_time=now)
    )
    assert [e[2].hex() for e in events] == ["070426111904174258", "070580022345000100", "00c0"]
    assert round((events[1][0] - events[0][0]) * 1000) == 300


async def test_p5_notifications_keep_fallback_and_ignore_old_callback(make):
    c, coordinator, client, _, _ = make("cb27new")
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("2a000002810000365802030000000000"))
    assert coordinator.controller_state["massage_foot_intensity"] == 0
    assert coordinator.controller_state[keys.WAVE] is None
    c.on_disconnect()
    assert coordinator.controller_state[keys.WAVE] is None
    callback(None, bytearray.fromhex("2a000002810000365802030000000000"))
    assert coordinator.controller_state[keys.WAVE] is None


async def test_configuration_pages_query_highest_first_and_snapshot_sonic_reset(make):
    c, _, client, events, _ = make("cb27new")
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("2a00000581000b011f000002020000000000000000"))
    await asyncio.sleep(0)
    assert events[-1][2].hex() == "2a000005810908ffff00002225124b"
    assert c._motors == 2 and not c._rgb
    callback(None, bytearray.fromhex("2a00000581000000010700000000000000000000"))
    await asyncio.sleep(0)
    assert events[-1][2].hex() == "2a000005810902ffff00002225124b"
    assert not c._sonic
    callback(None, bytearray.fromhex("2a00000581000000010700000000000000000000"))
    assert c._sonic
    assert c.capability_snapshot()["sonic"]
    await c.stop_notify()


async def test_ab_is_the_only_native_side_route_and_stop_retains_side(make):
    c, _, _, events, _ = make("cb24_ab")
    with c.side_scope("right"):
        await c.hold_control("head_up", 1)
    assert [e[2].hex() for e in events] == ["050200000001bb", "050200000000bb"]
    other, _, _, _, _ = make("cb24")
    with other.side_scope("left"), raises_key("single_address_pair_unsupported"):
        await other.preset_flat()


def test_ordered_raw_scan_factory_and_safe_truncation():
    raw = bytearray(27)
    raw[7:12] = b"DOT\x02\x05"
    assert discover("SmartBed1234567890", bytes(raw)).profile == "cb24"
    assert discover("X", bytes(raw)).motors == 5
    raw[10] = 1
    assert discover("X", bytes(raw)).profile == "dacheng"
    assert discover("Headboard126", b"").profile == "headboard126"
    assert select_profile("auto", "X").profile == "cb24"
    assert select_profile("standard", "X", motors=4).profile == "standard"
    assert discover(None) is None
    for size in range(27):
        discover("X", bytes(raw[:size]))


@pytest.mark.parametrize("profile", PROFILES)
async def test_every_profile_is_factory_reachable_and_exposure_has_no_empty_slots(profile):
    coordinator = _FactoryCoordinator()
    c = await create_controller(
        cast(AdjustableBedCoordinator, coordinator), BED_TYPE_OKIN_CB24, profile, None
    )
    assert c.profile.key == profile
    assert c.memory_slot_count in (0, 1, 2)
    assert len({spec.key for spec in c.controller_button_specs}) == len(c.controller_button_specs)
    assert all(not spec.hold for spec in c.controller_button_specs if spec.requires_confirmation)


async def test_sonic_massage_controls_use_real_ranges(make):
    c, _, _, events, _ = make("cb27new")
    c._sonic = True
    c._parser().state.foot_intensity = 1
    await c.set_sonic_level("head", 2)
    await c.set_sonic_mode("acoustic")
    await c.set_sonic_wave(6)
    await c.set_sonic_timer("20")
    assert [e[2].hex() for e in events[::2]] == [
        "aa000006020400030604",
        "aa00000605020001",
        "aa00000603020006",
        "aa0000060b0200ffb004b004",
    ]
    assert all(e[2].hex() == "2a0000068100" for e in events[1::2])
    before = len(events)
    with raises_key("value_out_of_range"):
        await c.set_sonic_level("head", 4)
    assert len(events) == before
    assert c.standard_button_hold_spec("massage_head_up") is None
    assert all(
        spec.hold is None for spec in c.controller_button_specs if spec.requires_confirmation
    )
    assert {s.key for s in c.controller_switch_specs} == {
        "smartbed_massage",
        "smartbed_sonic",
    }


async def test_delivery_finalizes_the_command_step_before_cancelled_query(make):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
    )

    c, coordinator, client, _, _ = make("cb27new")
    c._sonic = True
    scheduler = DeviceCommandScheduler("sonic-delivery")
    original = client.write_gatt_char.side_effect

    async def send_then_cancel(char, frame, *, response):
        await original(char, frame, response=response)
        coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = send_then_cancel

    async def operation(context):
        coordinator.cancel_command = context.cancel_event
        await c.set_sonic(True)

    await scheduler.execute(CommandIntent(operation, cancel_running=False))
    assert coordinator.controller_state[keys.SONIC] is True
    client.write_gatt_char.assert_awaited_once()


def test_setup_keeps_the_profile_specific_motor_limits():
    from custom_components.adjustable_bed.config_flow import _motor_count_options

    assert _motor_count_options(BED_TYPE_OKIN_CB24, "cb24") == [2, 3, 4, 5]
    assert _motor_count_options(BED_TYPE_OKIN_CB24, "dacheng") == [2, 3, 4]
    assert _motor_count_options(BED_TYPE_OKIN_CB24, "headboard126") == [2]


async def test_gatt_latency_does_not_lengthen_ui_refresh_or_query_timers(make):
    c, _, client, events, _ = make("cb27new")
    original = client.write_gatt_char.side_effect

    async def slow_write(char, frame, *, response):
        await original(char, frame, response=response)
        await asyncio.sleep(0.007)

    client.write_gatt_char.side_effect = slow_write
    await c.hold_control("head_up", 650)
    assert [round(e[0] * 1000) for e in events] == [0, 300, 600, 750]
    events.clear()
    await c.massage_head_up()
    assert round((events[1][0] - events[0][0]) * 1000) == 200


async def test_first_dispatched_write_cancelled_before_ack_still_releases_captured_side(make):
    c, _, client, events, _ = make("cb24_ab")
    dispatched = asyncio.Event()
    original = client.write_gatt_char.side_effect

    async def pending_ack(char, frame, *, response):
        await original(char, frame, response=response)
        if frame.hex() == "050200000001bb":
            dispatched.set()
            await asyncio.Event().wait()

    client.write_gatt_char.side_effect = pending_ack

    async def held():
        with c.side_scope("right"):
            await c.hold_control("head_up", 1000)

    task = asyncio.create_task(held())
    await dispatched.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [e[2].hex() for e in events] == ["050200000001bb", "050200000000bb"]


async def test_short_tap_release_and_alarm_deadlines_exclude_ack_latency(make):
    from datetime import datetime

    c, _, client, events, _ = make()
    original = client.write_gatt_char.side_effect

    async def slow(char, frame, *, response):
        await original(char, frame, response=response)
        await asyncio.sleep(0.007)

    client.write_gatt_char.side_effect = slow
    await c.preset_memory(1)
    assert [round(e[0] * 1000) for e in events] == [0, 101]
    events.clear()
    await c.configure_alarm(
        AlarmRequest(
            enabled=True,
            hour=8,
            minute=30,
            wake_action="zero_g",
            reference_time=datetime(2026, 11, 19, 7, 0),
        )
    )
    assert round((events[1][0] - events[0][0]) * 1000) == 300
    assert events[-1][2].hex() == "00c0"


async def test_p5_timer_arrows_are_single_commands_without_stop_or_hold(make):
    c, _, _, events, _ = make("cb27new")
    await c.change_timer(True)
    assert [(round(e[0] * 1000), e[2].hex()) for e in events] == [
        (0, "05020000020000"),
        (200, "2a0000028101ff"),
    ]
    assert "smartbed_timer_up" not in c.held_control_options
    assert all(s.hold is None for s in c.controller_button_specs if "timer" in s.key)


async def test_legacy_configuration_wins_over_stored_snapshot(make):
    _, coordinator, _, _, _ = make()
    c = OkinCB24Controller(
        cast(AdjustableBedCoordinator, coordinator),
        motors=5,
        snapshot={"profile": "cb24", "motors": 2, "massage": False},
    )
    assert c.protocol == 4
    assert len(c.motor_control_specs) == 6
    assert c.supports_massage


async def test_ab_feedback_and_specs_follow_each_side_and_standalone_selection(make):
    from custom_components.adjustable_bed.state_keys import massage_state_side

    c, coordinator, client, _, _ = make("cb24_ab", side=2)
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    raw = bytearray(20)
    raw[0:4] = bytes.fromhex("a50b00aa")
    for index, value in {4: 1, 6: 1, 7: 1, 8: 3, 11: 3, 13: 2, 14: 6, 15: 1}.items():
        raw[index] = value
    callback(None, raw)
    state = coordinator.controller_state
    assert state["massage_head_intensity_left"] == 1
    assert state["massage_head_intensity_right"] == state["massage_head_intensity"] == 3
    assert state["massage_timer_left"] == 10
    assert state["massage_timer_right"] == state["massage_timer"] == 20
    assert state["smartbed_wave_left"] == 1
    assert state["smartbed_wave_right"] == state[keys.WAVE] == 2
    with c.side_scope("right"):
        assert c.controller_number_specs[0].state_key == "smartbed_wave_right"
        assert c.controller_state_sensor_specs[0].state_key == "smartbed_alarm_time_right"
        assert c.controller_state_binary_sensor_specs[0].state_key == "smartbed_alarm_on_right"
    assert massage_state_side(BED_TYPE_OKIN_CB24, "left", controller_side="left") == "left"
    assert massage_state_side(BED_TYPE_OKIN_CB24, "both") is None


async def test_auto_saved_sides_require_a_verified_ab_route_or_targeted_reconfigure():
    co = _FactoryCoordinator()
    co.entry.data["cb24_bed_selection"] = 0xAA
    with raises_key("smartbed_choose_receiver"):
        await create_controller(
            cast(AdjustableBedCoordinator, co), BED_TYPE_OKIN_CB24, "auto", None
        )
    co.entry.data["capabilities"] = {"okin_cb24": {"profile": "cb24_ab"}}
    c = await create_controller(
        cast(AdjustableBedCoordinator, co), BED_TYPE_OKIN_CB24, "auto", None
    )
    assert c.profile.key == "cb24_ab"
    assert c.supports_single_address_pairing


@pytest.mark.parametrize("profile", ("headboard126", "headboard265"))
async def test_headboards_keep_flat_and_two_memories_without_light(make, profile):
    c, _, _, events, _ = make(profile)
    assert c.supports_preset_flat and c.memory_slot_count == 2
    assert not c.supports_lights
    await c.preset_memory(2)
    assert events[0][2].hex() == "05020004000000"
    if profile == "headboard265":
        assert not c.supports_massage_timer
        assert c.controller_number_specs[0].native_max_value == 2


async def test_p5_unknown_toggle_queries_live_light_before_choosing_inverse(make):
    c, co, client, events, _ = make("cb27new")
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    original = client.write_gatt_char.side_effect

    async def reply(char, frame, *, response):
        await original(char, frame, response=response)
        if frame.hex() == "2a0000048100":
            callback(None, bytearray.fromhex("2a000004810000010000"))

    client.write_gatt_char.side_effect = reply
    await c.lights_toggle()
    assert [e[2].hex() for e in events] == [
        "2a0000048100",
        "aa0000040105000000000000",
        "2a0000048100",
    ]
    p1, _, _, _, _ = make("standard")
    assert p1.supports_light_toggle_control and not p1.supports_light_state_feedback


async def test_capability_snapshot_persists_only_after_final_page_and_sonic_state_is_scoped(make):
    c, co, client, _, _ = make("cb27new")
    c._session = SimpleNamespace(is_current=lambda: True, persist_capability_snapshot=MagicMock())
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("2a000005810003011f000002020000000000000000"))
    await asyncio.sleep(0)
    c._session.persist_capability_snapshot.assert_not_called()
    callback(None, bytearray.fromhex("2a00000581000000010700000000000000000000"))
    c._session.persist_capability_snapshot.assert_called_once()
    assert c._sonic
    callback(None, bytearray.fromhex("2a000004810000010000"))
    assert keys.SONIC_HEAD not in co.controller_state


def test_reconfigure_receiver_change_clears_unsupported_saved_native_side():
    from custom_components.adjustable_bed.setup_questions import setup_profile

    profile = setup_profile(BED_TYPE_OKIN_CB24, "cb27new")
    assert profile is not None and profile.normalize is not None
    assert profile.normalize(
        {"protocol_variant": "cb24_ab", "cb24_bed_selection": 170}, {"protocol_variant": "cb27new"}
    ) == {"protocol_variant": "cb27new", "cb24_bed_selection": 0}
    assert (
        profile.normalize({"protocol_variant": "auto", "cb24_bed_selection": 170}, {})[
            "cb24_bed_selection"
        ]
        == 170
    )


@pytest.mark.parametrize("operation", ("tap", "query", "alarm"))
async def test_queued_writes_start_ui_deadlines_at_dispatch(make, operation):
    from datetime import datetime

    c, _, _, events, clock = make("cb27new" if operation == "query" else "cb24")
    await c._ble_lock.acquire()
    if operation == "tap":
        pending = asyncio.create_task(c.preset_memory(1))
    elif operation == "query":
        pending = asyncio.create_task(c.massage_head_up())
    else:
        pending = asyncio.create_task(c.configure_alarm(AlarmRequest(
            enabled=True, hour=8, minute=30, wake_action="zero_g",
            reference_time=datetime(2026, 11, 19, 7, 0),
        )))
    await asyncio.sleep(0)
    clock[0] = 1.0
    c._ble_lock.release()
    await pending
    assert round(events[0][0] * 1000) == 1000
    assert round((events[1][0] - events[0][0]) * 1000) == {
        "tap": 101, "query": 200, "alarm": 300,
    }[operation]


@pytest.mark.parametrize("reason, readback", (("expired", True), ("stopped", False)))
async def test_renewable_massage_releases_and_reads_from_actual_lease_end(make, monkeypatch, reason, readback):
    from custom_components.adjustable_bed.command_scheduler import CommandOutcome

    c, co, _, events, clock = make()
    context = _hold_context(co.cancel_command, 0.2)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.smartbed.controller.current_command_context",
        lambda: context,
    )
    sleep = asyncio.sleep

    async def expire(seconds):
        await sleep(seconds)
        if clock[0] >= 0.2 and context.cancel_reason is None:
            context.request_cancel(CommandOutcome(reason))

    monkeypatch.setattr(asyncio, "sleep", expire)
    await c.hold_control("massage_head_up", 30000)
    assert events[1][2].hex() == "05020000000000"
    assert round(events[1][0] * 1000) == 300
    assert (events[-1][2].hex() == "00b0") is readback
    assert clock[0] == pytest.approx(0.7 if readback else 0.3)


@pytest.mark.parametrize("controller_side", (None, "left"))
def test_generic_massage_entities_read_the_physical_or_native_side(controller_side):
    from custom_components.adjustable_bed.number import (
        MASSAGE_NUMBER_DESCRIPTIONS,
        AdjustableBedMassageNumber,
    )
    from custom_components.adjustable_bed.select import AdjustableBedMassageTimerSelect

    view = SimpleNamespace(
        bed_type=BED_TYPE_OKIN_CB24, entity_side="left", controller_side=controller_side,
        controller_state={"massage_head_intensity": 1, "massage_head_intensity_left": 3,
                          "massage_timer": 10, "massage_timer_left": 20},
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedSideProxy

    view = PairedSideProxy(MagicMock(), view, "left")
    number = object.__new__(AdjustableBedMassageNumber)
    number._coordinator = view
    number.entity_description = next(d for d in MASSAGE_NUMBER_DESCRIPTIONS if d.massage_zone == "head")
    timer = object.__new__(AdjustableBedMassageTimerSelect)
    timer._coordinator = view
    timer._attr_options = ["Off", "10 min", "20 min"]
    timer._has_off = True
    assert number.native_value == (3 if controller_side else 1)
    assert timer.current_option == ("20 min" if controller_side else "10 min")


async def test_invalid_saved_route_is_reported_before_coordinator_or_ble_setup(hass, monkeypatch):
    from pytest_homeassistant.common import MockConfigEntry

    monkeypatch.setattr(AdjustableBedCoordinator, "async_import_tables", AsyncMock())
    entry = MockConfigEntry(domain="adjustable_bed", data={
        "bed_type": BED_TYPE_OKIN_CB24, "protocol_variant": "auto",
        "pair_mode": "single_address", "cb24_bed_selection": 170,
    })
    with raises_key("smartbed_choose_receiver"):
        await AdjustableBedCoordinator.async_create(hass, entry)


def test_verified_auto_ab_is_admitted_for_single_address_conversion():
    from custom_components.adjustable_bed.pairing import (
        build_single_address_pair_entry_data,
        supports_single_address_pairing,
    )
    capabilities = {"okin_cb24": {"profile": "cb24_ab"}}
    assert supports_single_address_pairing(BED_TYPE_OKIN_CB24, "auto", capabilities=capabilities)
    assert not supports_single_address_pairing(BED_TYPE_OKIN_CB24, "cb24", capabilities=capabilities)
    data = build_single_address_pair_entry_data({
        "address": "AA:BB:CC:DD:EE:01", "bed_type": BED_TYPE_OKIN_CB24,
        "protocol_variant": "auto", "capabilities": capabilities,
    }, name="Bed")
    assert data["pair_mode"] == "single_address"


async def test_sonic_specs_keep_settled_capabilities_through_startup_query(make):
    c, _, client, _, _ = make("cb27new")
    c._sonic = True
    await c.start_notify()
    before = [s.key for s in c.controller_number_specs]
    await c._query_page(c._capture_link(), 0)
    assert c._sonic and [s.key for s in c.controller_number_specs] == before
    assert not c._parser().state.has_sonic_massage
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray.fromhex("2a000005810003011f000002020000000000000000"))
    await asyncio.sleep(0)
    assert c._sonic
    callback(None, bytearray.fromhex("2a00000581000000010700000000000000000000"))
    assert c._sonic
    await c.stop_notify()


async def test_ha_light_toggle_reaches_session_readback_and_no_light_hides_capabilities(make):
    from custom_components.adjustable_bed.light import AdjustableBedOnOffLight

    c, co, _, _, _ = make("cb27new")
    c.lights_toggle = AsyncMock()
    entity = object.__new__(AdjustableBedOnOffLight)
    entity._coordinator = co
    entity._feedback_only = True

    async def execute(operation, **kwargs):
        await operation(c)

    co.async_execute_controller_command = execute
    await entity.async_toggle()
    c.lights_toggle.assert_awaited_once()
    c._light = False
    assert not c.supports_light_state_feedback
    assert not c.supports_light_toggle_control
    assert not c.supports_discrete_light_control


@pytest.mark.parametrize("length", (10, 11, 12))
@pytest.mark.parametrize("second_byte", (0, 12))
async def test_short_p5_alarm_replies_are_consumed_without_confirming_defaults(make, length, second_byte):
    c, co, client, _, _ = make("cb27new")
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    raw = bytearray.fromhex("2a0000038100000000000000")[:length]
    raw[1] = second_byte
    assert c._parser().profile_only(raw)
    callback(None, bytearray(raw))
    assert keys.ALARM_TIME not in co.controller_state
    assert keys.ALARM_ON not in co.controller_state


async def test_stop_fences_expired_hold_readback_queued_on_gatt(make, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import CommandOutcome

    c, co, _, events, _ = make()
    context = _hold_context(co.cancel_command)
    context.request_cancel(CommandOutcome.EXPIRED)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.smartbed.controller.current_command_context",
        lambda: context,
    )
    co.cancel_command.set()
    await c._ble_lock.acquire()
    pending = asyncio.create_task(c._massage_readback(c._capture_link(), -0.5))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    context.request_cancel(CommandOutcome.STOPPED)
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert c._ble_lock.locked()
    c._ble_lock.release()
    assert events == []


@pytest.mark.parametrize("lease", (False, True))
async def test_refresh_queued_past_its_deadline_cannot_dispatch(make, monkeypatch, lease):
    c, co, client, events, clock = make()
    if lease:
        context = _hold_context(co.cancel_command, 0.5)
        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.smartbed.controller.current_command_context",
            lambda: context,
        )
    acquired, release = asyncio.Event(), asyncio.Event()

    async def block_gatt():
        async with c._ble_lock:
            acquired.set()
            await release.wait()

    original = client.write_gatt_char.side_effect
    blockers: list[asyncio.Task[None]] = []

    async def write(char, frame, *, response):
        await original(char, frame, response=response)
        if len(events) == 1:
            blockers.append(asyncio.create_task(block_gatt()))

    client.write_gatt_char.side_effect = write
    held = asyncio.create_task(c.hold_control("head_up", 500))
    await acquired.wait()
    await asyncio.sleep(0)
    clock[0] = 0.7
    release.set()
    await held
    assert len(blockers) == 1
    await blockers[0]
    assert [e[2].hex() for e in events] == ["05020000000100", "05020000000000"]
    assert events[-1][0] == pytest.approx(0.7)


async def test_later_replacement_interrupts_expired_readback_delay(make, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import CommandOutcome

    c, co, _, events, _ = make()
    context = _hold_context(co.cancel_command)
    context.request_cancel(CommandOutcome.EXPIRED)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.smartbed.controller.current_command_context",
        lambda: context,
    )
    entered, never = asyncio.Event(), asyncio.Event()
    sleep = asyncio.sleep

    async def delayed(seconds):
        if seconds > 0:
            entered.set()
            await never.wait()
        else:
            await sleep(0)

    monkeypatch.setattr(asyncio, "sleep", delayed)
    pending = asyncio.create_task(c._massage_readback(c._capture_link(), 0))
    await entered.wait()
    context.request_cancel(CommandOutcome.REPLACED)
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not never.is_set()
    assert events == []


async def test_separate_address_routes_are_all_validated_before_child_construction(hass, monkeypatch):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import _build_paired_children
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left = {"address": "AA:BB:CC:DD:EE:01", "bed_type": BED_TYPE_OKIN_CB24, "protocol_variant": "cb24"}
    right = {"address": "AA:BB:CC:DD:EE:02", "bed_type": BED_TYPE_OKIN_CB24,
             "protocol_variant": "auto", "cb24_bed_selection": 170}
    data = build_pair_entry_data(left, right, name="Bed")
    entry = MockConfigEntry(domain="adjustable_bed", data=data)
    constructor = MagicMock()
    monkeypatch.setattr("custom_components.adjustable_bed.AdjustableBedCoordinator", constructor)
    with raises_key("smartbed_choose_receiver"):
        _build_paired_children(hass, entry)
    constructor.assert_not_called()


@pytest.mark.parametrize("controller_side", (None, "left", "right"))
async def test_unknown_smartbed_timer_remains_unknown_after_disconnect(make, controller_side):
    from custom_components.adjustable_bed.select import AdjustableBedMassageTimerSelect

    c, co, _, _, _ = make("cb24_ab")
    co.controller_state.update({"massage_timer": 10, "massage_timer_left": 20, "massage_timer_right": 30})
    view = SimpleNamespace(
        bed_type=BED_TYPE_OKIN_CB24, entity_side=controller_side, controller_side=controller_side,
        controller_state=co.controller_state,
    )
    timer = object.__new__(AdjustableBedMassageTimerSelect)
    timer._coordinator = view
    timer._attr_options = ["10 min", "20 min", "30 min"]
    timer._has_off = c.massage_timer_can_turn_off
    assert not timer._has_off
    assert timer.current_option == {None: "10 min", "left": "20 min", "right": "30 min"}[controller_side]
    c.on_disconnect()
    assert timer.current_option is None
