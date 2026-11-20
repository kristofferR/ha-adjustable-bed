"""Jerome's power base: literal frames, lifecycle and layout-owned behavior."""

import asyncio
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic import jerome as bed
from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, transition
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.receive import (
    MalformedFrame,
    ReceiveState,
)
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from custom_components.adjustable_bed.profiles.jerome2 import EXCLUDED_LAYOUTS, LAYOUTS
from tests.jerome_vectors import CONTROL_VECTORS, FEATURE_VECTORS
from tests.state_helpers import published


def controller(layout="6BRM", wire="FRAMED"):
    coord = MagicMock()
    coord.cancel_command = asyncio.Event()
    coord.entry.data = {
        "protocol_variant": "jerome2",
        "product_type": layout,
        "motor_pulse_count": 1,
        "ble_device_name": "6BRM-bed",
    }
    coord.client.is_connected = True
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    ctrl = bed.JeromeController(coord)
    coord.controller = ctrl
    ctrl._session = Transport(
        coord.client,
        SimpleNamespace(uuid="write", properties=["write"], handle=1),
        SimpleNamespace(uuid="notify", properties=["notify"], handle=2),
        wire,
    )
    ctrl._wire = wire
    ctrl._worker.set_interval(p.worker_interval("6BRM", wire, rise=True))
    return ctrl, coord


def packets(coord):
    return [call.args[1].hex() for call in coord.client.write_gatt_char.await_args_list]


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    original = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original(0)

    async def wait(milliseconds, cancel):
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed.JeromeController, "_wait", staticmethod(wait))
    return now


@pytest.mark.parametrize(("wire", "payload", "expected"), CONTROL_VECTORS)
def test_literal_control_codec_fit(wire, payload, expected):
    assert p.control(bytes.fromhex(payload), wire).hex() == expected


@pytest.mark.parametrize(("inputs", "expected"), FEATURE_VECTORS)
def test_literal_feature_codec_fit(inputs, expected):
    kind = inputs["builder"]
    if kind == "control":
        actual = p.control(
            bytes.fromhex(inputs["code"]),
            "RAW" if inputs.get("vendor") == "NORDIC" else "FRAMED",
            inputs.get("mode", 0),
        )
    elif kind == "frame":
        actual = p.direct(*inputs["fields"])
    elif kind == "rgb":
        actual = p.rgb(*inputs["rgb"])
    elif kind == "led_time":
        actual = p.direct(0x0B, inputs["seconds"] >> 8, inputs["seconds"])
    elif kind == "aroma":
        actual = b"".join(
            p.aroma(op, value)
            for op, value in zip((0x1B, 0x1C, 0x1D), inputs["values"], strict=True)
        )
    elif kind == "alarm":
        actual = b"".join(p.alarm(inputs["delay"], inputs["command"]))
    else:
        receiver = ReceiveState(buffer=inputs["stream"])
        actual = bytes.fromhex(receiver._pack(inputs["hex_length"]))
    assert actual.hex() == expected


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_movement_uses_own_wire_and_release(clock, wire):
    ctrl, coord = controller(wire=wire)
    await ctrl.press("head_up", duration_ms=350)
    assert packets(coord)[0] == ("34" if wire == "RAW" else "6e01002493")
    assert packets(coord)[-1] == ("6e" if wire == "RAW" else "6e01006edd")
    assert clock[0] == pytest.approx(0.4)
    assert ctrl.execution.hold_for("jerome_head_up") == "stream"
    assert not ctrl.execution.concurrent


@pytest.mark.parametrize(
    ("layout", "action", "wire", "expected", "elapsed"),
    [
        ("AORM", "lock", "RAW", ["84"], 4.93),
        ("AORM", "lock", "FRAMED", ["6e010084f3", "6e01006edd"], 5.0),
        ("E9RM", "lock", "RAW", ["84"], 4.93),
        ("DXRM", "synchronization_on", "RAW", ["bc"], 2.89),
        ("DXRM", "synchronization_off", "FRAMED", ["6e0100bd2c", "6e01006edd"], 3.05),
    ],
)
async def test_vendor_specific_long_only_cleanup(clock, layout, action, wire, expected, elapsed):
    ctrl, coord = controller(layout, wire)
    await ctrl.press(action)
    assert packets(coord) == expected
    assert clock[0] == pytest.approx(elapsed)
    assert not ctrl._worker.fired and ctrl._worker.counter == 0


async def test_cancel_before_threshold_cannot_save_or_leave_pending_intent(clock, monkeypatch):
    ctrl, coord = controller("DXRM", "RAW")

    async def cancelled(milliseconds, event):
        event.set()
        return False

    monkeypatch.setattr(ctrl, "_wait", cancelled)
    await ctrl.press("synchronization_on")
    assert packets(coord) == []
    assert ctrl._worker.mode == -1


async def test_new_gesture_never_inherits_android_counter_or_latch(clock):
    ctrl, coord = controller("DXRM", "RAW")
    await ctrl.press("synchronization_on")
    before = clock[0]
    await ctrl.press("synchronization_off")
    assert clock[0] - before == pytest.approx(2.89)
    assert packets(coord) == ["bc", "bd"]


def test_source_null_short_and_persistent_worker_semantics_stay_explicit():
    for layout in ("AORM", "E9RM", "DXRM"):
        button = next(
            c for c in load_catalog("jerome2").models[layout].controls if c.long in ("84", "BC")
        )
        raw = transition(button, layout, "RAW", Selection(), "UP", app="jerome2")
        framed = transition(button, layout, "FRAMED", Selection(), "UP", app="jerome2")
        assert raw.payload is None and framed.payload is None and framed.mode == 0
    worker = p.Worker(mode=3, count=1)
    assert worker.tick() == ()
    worker.payload = b"\xbc"
    assert worker.tick()[0].payload == b"\xbc"
    worker.mode, worker.payload = 3, b"\xbd"
    assert worker.tick()[0].payload == b"\xbd"
    worker.mode = 0
    worker.tick()
    assert worker.counter == 0 and worker.fired
    worker.mode = 4
    assert worker.tick() == (p.Emission(150, p.RELEASE),)
    assert not worker.fired


async def test_captured_session_never_writes_cleanup_on_replacement(clock):
    ctrl, coord = controller()
    old = ctrl._session

    async def replace_link(_char, packet, **_kwargs):
        ctrl._session = replace(old)

    coord.client.write_gatt_char.side_effect = replace_link
    with pytest.raises(ConnectionError):
        await ctrl.press("head_up")
    assert packets(coord) == ["6e01002493"]


async def test_task_cancel_drains_write_before_release(clock):
    ctrl, coord = controller()
    entered, finish = asyncio.Event(), asyncio.Event()
    order = []

    async def write(_char, packet, **_kwargs):
        if packet[3] == 0x24:
            entered.set()
            await finish.wait()
        order.append(packet.hex())

    coord.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.press("head_up"))
    await entered.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert order == ["6e01002493", "6e01006edd"]


async def test_stop_suppresses_frame_queued_behind_wire_lock(clock):
    ctrl, coord = controller()
    await ctrl.ble_lock.acquire()
    task = asyncio.create_task(ctrl.press("head_up"))
    await asyncio.sleep(0)
    coord.cancel_command.set()
    ctrl.ble_lock.release()
    await task
    assert packets(coord) == ["6e01006edd"]


async def test_mode_and_side_stay_bound_until_release(clock):
    ctrl, coord = controller("BTRM")
    await ctrl.press("head_up", mode=2, duration_ms=1)
    assert packets(coord) == ["6e01022495", "6e01026edf"]
    ctrl, coord = controller("DHRM")
    with ctrl.side_scope("right"):
        await ctrl.press("head_up", duration_ms=1)
    assert packets(coord) == ["6e01012494", "6e01016ede"]
    ctrl, coord = controller("DHRM", "RAW")
    with ctrl.side_scope("right"), pytest.raises(ServiceValidationError):
        await ctrl.press("head_up")
    assert not packets(coord)


async def test_layout_overlays_have_separate_confirmed_saves(clock):
    ctrl, coord = controller("E3RM")
    await ctrl.press("save_m1")
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert clock[0] == pytest.approx(0.05)
    for layout in ("YFRM", "YGRM", "BRRM"):
        ctrl, coord = controller(layout)
        await ctrl.press("m1", keep=True, duration_ms=1)
        assert packets(coord) == ["6e01002e9d", "6e01006edd"]
        with pytest.raises(ServiceValidationError):
            ctrl.validate_action("save_m1", keep=True, confirm=True)
        assert all(
            s.hold is None
            for s in ctrl.controller_button_specs
            if s.requires_confirmation or s.card.role == "save"
        )


async def test_axis_choice_is_an_explicit_position_action(clock):
    ctrl, coord = controller("U3RM")
    for action, frame in (
        ("zero_gravity_2_up", "6e01003fae"),
        ("tv_down", "6e010042b1"),
        ("lounge_up", "6e010071e0"),
    ):
        await ctrl.press(action, duration_ms=1)
        assert packets(coord)[-2] == frame
    assert ctrl.controller_select_specs == ()


def test_all_layout_names_are_unique_with_no_placeholders_or_screen_state():
    from custom_components.adjustable_bed.labels import display_label
    from tests.test_entity_names import problems

    for layout in LAYOUTS:
        if layout in EXCLUDED_LAYOUTS:
            continue
        ctrl, _ = controller(layout)
        specs = ctrl.controller_button_specs
        names = [
            display_label((s.translation_placeholders or {}).get("action", s.name)) for s in specs
        ]
        assert not {name: problems(name) for name in names if problems(name)}, layout
        assert len(names) == len(set(names)), layout
        assert not any("button" in name.lower().split() for name in names), layout
        assert not any(word in name.lower() for name in names for word in ("music", "volume")), (
            layout
        )
        assert all(not s.local_select_fn for s in ctrl.controller_select_specs)
        assert all(
            s.hold is None for s in specs if s.requires_confirmation or s.card.role == "save"
        )
        assert len({s.key for s in specs}) == len(specs)


async def test_capability_parser_epoch_and_live_feature_fence(clock):
    ctrl, coord = controller()
    old = ctrl._session
    assert ctrl.controller_number_specs == ()
    for packet in ("6e09010078", "6e0e00037f", "6e1a000189"):
        ctrl._notification(old, old.notify, bytearray.fromhex(packet))
    assert (
        ctrl._receive.alarm_capable and ctrl._receive.light_capable and ctrl._receive.aroma_capable
    )
    assert len(ctrl.controller_number_specs) == 4
    await ctrl.set_light_color((255, 68, 68))
    assert packets(coord) == ["6e0cffff786e0d444403"]
    ctrl.on_disconnect()
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable
    with pytest.raises(ServiceValidationError):
        await ctrl.set_light_color((1, 2, 3))
    assert (
        published(
            *(
                update
                for call in coord.handle_controller_state_updates.call_args_list
                for update in call.args
            )
        )[bed.LIGHT_SECONDS]
        is None
    )


async def test_parser_never_fabricates_aroma_or_motor_positions():
    receiver = ReceiveState()
    for fragment in (b"\x6e\x0e", bytes.fromhex("00037f")):
        receiver.feed(fragment, app="jerome2", layout="6BRM", desk_bound=False)
    assert receiver.light_capable
    assert receiver.height_cm is None and receiver.height_inches is None
    with pytest.raises(MalformedFrame):
        receiver.feed(bytes.fromhex("6e1a00028b"), app="jerome2", layout="6BRM", desk_bound=False)


async def test_alarm_uses_selected_layout_and_shared_native_request(clock, monkeypatch):
    layout = next(
        k
        for k, m in load_catalog("jerome2").models.items()
        if {"30", "4C", "4E"} <= {c.alarm_clock for c in m.controls}
    )
    ctrl, coord = controller(layout)
    request = AlarmRequest(
        enabled=True,
        hour=12,
        minute=0,
        wake_action="memory_3",
        massage=True,
        massage_zone="both",
        reference_time=datetime(2026, 11, 19, 12, 0),
        confirm_custom_position=True,
    )
    monkeypatch.setattr(bed.dt_util, "now", lambda: request.reference_time)
    ctrl.validate_alarm(request)
    await ctrl.configure_alarm(request)
    assert packets(coord) == ["6e05a00013", "6e0605a922"]
    coord.client.write_gatt_char.reset_mock()
    await ctrl.configure_alarm(replace(request, enabled=False))
    assert packets(coord) == ["6e05000073", "6e06000074"]
    assert clock[0] == pytest.approx(1.2)
    assert ctrl.persisted_app_state == {}


async def test_startup_order_and_direct_queries_on_both_wires(clock, monkeypatch):
    for wire in ("RAW", "FRAMED"):
        ctrl, coord = controller(wire=wire)
        session = ctrl._session
        monkeypatch.setattr(bed, "select", lambda *args, session=session, **kwargs: session)
        await ctrl.start_notify()
        assert packets(coord) == (["6e02010071"] if wire == "FRAMED" else []) + [
            "6e0a000179",
            "6e1a000088",
        ]
        assert coord.client.start_notify.await_count == 1


async def test_real_timer_choices_and_inverse_switches(clock):
    ctrl, coord = controller("DXRM")
    switch = next(s for s in ctrl.controller_switch_specs if s.key == "jerome_synchronization")
    await switch.set_fn(ctrl, True)
    assert packets(coord)[0] == "6e0100bc2b"
    assert not any("synchronization" in s.key for s in ctrl.controller_button_specs)
    for layout, minutes, expected in (
        ("D1RM", 0, "6e01005ecd"),
        ("D9RM", 0, "6e01008bfa"),
        ("Y6RM", 45, "6e010061d0"),
    ):
        ctrl, coord = controller(layout)
        await ctrl.set_massage_timer(minutes)
        assert packets(coord) == [expected]
        assert ctrl.controller_select_specs == ()
        # The popup's on/off row is a toggle, so Y6RM offers no off.
        assert ctrl.massage_timer_can_turn_off is (layout != "Y6RM")


@pytest.mark.parametrize("layout", ["D1RM", "D9RM", "Y6RM"])
async def test_massage_timer_is_the_shared_select_sending_the_old_selects_frames(clock, layout):
    """Each choice of the former Jerome timer select is the shared select's same frame."""
    from custom_components.adjustable_bed.profiles.jerome2 import TIMER_PROGRESS

    old = (
        {15: p.massage_popup("15"), 30: p.massage_popup("30"), 45: p.massage_popup("45")}
        if layout == "Y6RM"
        else {
            0: p.massage_timer(layout, TIMER_PROGRESS["off"]),
            10: p.massage_timer(layout, TIMER_PROGRESS["10_minutes"]),
            20: p.massage_timer(layout, TIMER_PROGRESS["20_minutes"]),
            30: p.massage_timer(layout, TIMER_PROGRESS["30_minutes"]),
        }
    )
    ctrl, _ = controller(layout)
    assert ctrl.supports_massage_timer and ctrl.auto_enable_massage
    assert ctrl.massage_timer_options == sorted(m for m in old if m)
    for minutes, frame in old.items():
        ctrl, coord = controller(layout)
        await ctrl.set_massage_timer(minutes)
        assert packets(coord) == [frame.hex()]
        assert published(*coord.handle_controller_state_updates.call_args.args)[
            "massage_timer"
        ] == minutes
    with pytest.raises(ServiceValidationError):
        await ctrl.set_massage_timer(25)
    assert not controller("6BRM")[0].supports_massage_timer
    # The bed never reports the timer: a disconnect keeps the last one sent.
    ctrl.on_disconnect()
    assert "massage_timer" not in published(*coord.handle_controller_state_updates.call_args.args)
    # The frame has no side field, so a one-address combined side offers no timer.
    with ctrl.side_scope("left"):
        assert not ctrl.supports_massage_timer


def test_setup_discovery_are_explicit_and_searchable():
    from custom_components.adjustable_bed.beds.richmat_classic.discovery import matching_apps
    from custom_components.adjustable_bed.detection import APP_VARIANT_CHOICES
    from custom_components.adjustable_bed.setup_questions import (
        _classic_errors,
        _classic_layouts,
        _classic_normalize,
    )

    assert "Jerome" in APP_VARIANT_CHOICES["richmat_classic_apps", "jerome2"]
    for name in ("COOL TOUCH abc", "MPE_HJ012-bed", "200U&I abc", "6BRM-bed", "F5RM-bed"):
        assert "jerome2" in matching_apps(name)
    data = {"protocol_variant": "jerome2", "product_type": "6BRM"}
    assert _classic_errors(data) == {}
    assert set(_classic_layouts(data)).isdisjoint(EXCLUDED_LAYOUTS)
    assert _classic_normalize(data, {"product_type": "B6RU"})["product_type"] == "B6RM"
    for layout in EXCLUDED_LAYOUTS:
        with pytest.raises((ServiceValidationError, ValueError)):
            controller(layout)


async def test_delivery_counts_own_frames_and_required_skips_only(clock):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        Delivery,
        DeviceCommandScheduler,
        delivered,
    )

    ctrl, coord = controller()
    results = []

    async def operation(context):
        coord.cancel_command = context.cancel_event
        with delivered(results.append):
            await ctrl._send(p.INITIALIZE)  # Startup is not this command's frame.
            context.cancel_event.set()
            await ctrl._send(p.direct(0x1B, 0, 1), context.cancel_event)
            context.cancel_event.clear()
        with delivered(results.append):
            await ctrl._send(p.direct(0x1B, 0, 1), context.cancel_event)
            context.cancel_event.set()
            await ctrl._send(p.direct(0x1C, 0, 1), context.cancel_event)
            context.cancel_event.clear()

    scheduler = DeviceCommandScheduler("jerome-delivery")
    await scheduler.execute(CommandIntent(operation))
    assert results == [Delivery.NONE, Delivery.PARTIAL]
    assert packets(coord) == ["6e02010071", "6e1b00018a"]


async def test_alarm_final_sleep_does_not_claim_an_unsent_required_frame(clock, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        Delivery,
        DeviceCommandScheduler,
        delivered,
    )

    ctrl, coord = controller()
    results = []
    waits = 0

    async def wait(milliseconds, event):
        nonlocal waits
        waits += 1
        if waits == 2:
            event.set()
            return False
        return True

    monkeypatch.setattr(ctrl, "_wait", wait)

    async def operation(context):
        coord.cancel_command = context.cancel_event
        with delivered(results.append):
            await ctrl.configure_alarm(
                AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19))
            )
            context.cancel_event.clear()

    await DeviceCommandScheduler("jerome-alarm-delivery").execute(CommandIntent(operation))
    assert results == [Delivery.SENT]
    assert packets(coord) == ["6e05000073", "6e06000074"]


async def test_long_press_remains_available_beside_dedicated_save(clock):
    ctrl, coord = controller("YFRM")
    await ctrl.press("save_m1", long_press=True)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert clock[0] == pytest.approx(3.15)
    assert ctrl.execution.hold_for("jerome_m1") == "stream"


async def test_all_aroma_parameters_keep_each_step_and_spacing(clock):
    ctrl, coord = controller()
    ctrl._receive.aroma_capable = True
    await ctrl.configure_aroma((1, 1, 2))
    assert packets(coord) == ["6e1b00018a", "6e1c00018b", "6e1d00028d"]
    assert clock[0] == pytest.approx(0.30)


async def test_service_preflights_all_targets_and_preserves_native_admission(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.errors import invalid
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key
    from tests.test_generic_services import target

    await async_register_services(hass)
    first, one = target(family=bed.JeromeController, validate_action=MagicMock(), press=AsyncMock())
    second, two = target(
        family=bed.JeromeController,
        validate_action=MagicMock(side_effect=invalid("jerome_action")),
        press=AsyncMock(),
    )

    async def query_first(query, **kwargs):
        return await query(one)

    async def query_second(query, **kwargs):
        return await query(two)

    first.async_execute_controller_query.side_effect = query_first
    second.async_execute_controller_query.side_effect = query_second
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, "both"), (second, "both")], []),
        ),
        raises_key("jerome_action"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "jerome_bed",
            {"device_id": ["one", "two"], "action": "head_up"},
            blocking=True,
        )
    one.press.assert_not_awaited()
    two.press.assert_not_awaited()
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(first, "both")], []),
    ):
        await hass.services.async_call(
            DOMAIN, "jerome_bed", {"device_id": "one", "action": "head_up"}, blocking=True
        )
    assert first.async_execute_controller_command.await_args.kwargs["resource"] == "movement"
    assert first.async_execute_controller_command.await_args.kwargs["cancel_running"]
    one.press.assert_awaited_once()


async def test_one_address_side_cannot_write_whole_bed_settings(clock):
    from tests.error_helpers import raises_key

    ctrl, coord = controller("DHRM")
    ctrl._receive.light_capable = ctrl._receive.aroma_capable = True
    with ctrl.side_scope("left"):
        assert ctrl.controller_number_specs == ()
        assert ctrl.alarm_capability is None
        assert not ctrl.supports_light_color_control
        with raises_key("jerome_feature_scope"):
            await ctrl.configure_aroma((1, 1, 2))
        with raises_key("jerome_feature_scope"):
            await ctrl.configure_alarm(
                AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19))
            )
    assert packets(coord) == []


@pytest.mark.parametrize(
    ("name", "wire", "expected"),
    [("TWRM", "RAW", 110), ("MLRM", "FRAMED", 110), ("6BRM", "RAW", 170), ("6BRM", "FRAMED", 150)],
)
async def test_interval_uses_original_name_not_selected_layout(
    clock, monkeypatch, name, wire, expected
):
    ctrl, coord = controller("AORM", wire)
    coord.entry.data["ble_device_name"] = name
    session = ctrl._session
    monkeypatch.setattr(bed, "select", lambda *args, **kwargs: session)
    await ctrl.start_notify()
    assert ctrl._worker.tick_ms == expected


async def test_replaced_controller_cannot_write_or_hydrate_the_new_owner(clock):
    ctrl, coord = controller()
    session = ctrl._session
    coord.controller = MagicMock()
    with pytest.raises(ConnectionError):
        await ctrl.press("head_up")
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable
    assert packets(coord) == []


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_gvrm_keeps_head_only_old_getters_without_a_fake_save(clock, wire):
    from tests.error_helpers import raises_key

    ctrl, coord = controller("GVRM", wire)
    await ctrl.press("head_off", duration_ms=1)
    assert packets(coord) == (["35", "6e"] if wire == "RAW" else ["6e010035a4", "6e01006edd"])
    assert "save_button" not in ctrl._actions
    with raises_key("jerome_action"):
        await ctrl.press("foot_up")


async def test_alarm_accounts_for_time_spent_connecting(clock, monkeypatch):
    from datetime import timedelta

    layout = next(
        k
        for k, m in load_catalog("jerome2").models.items()
        if any(c.alarm_clock == "58" for c in m.controls)
    )
    ctrl, coord = controller(layout)
    start = datetime(2026, 11, 19, 12, 0)
    monkeypatch.setattr(bed.dt_util, "now", lambda: start + timedelta(minutes=2))
    await ctrl.configure_alarm(
        AlarmRequest(enabled=True, hour=12, minute=3, wake_action="tv", reference_time=start)
    )
    assert packets(coord) == ["6e05010074", "6e060058cc"]


def test_alarm_catalog_does_not_promote_ignored_helper_metadata():
    from tests.error_helpers import raises_key

    layout = next(
        k
        for k, m in load_catalog("jerome2").models.items()
        if any(c.alarm_clock == "6B" for c in m.controls)
    )
    ctrl, _ = controller(layout)
    assert "zero_g_2" not in ctrl.alarm_capability.wake_actions
    assert ctrl.alarm_capability.sounds == ()
    with raises_key("jerome_alarm"):
        ctrl.validate_alarm(
            AlarmRequest(
                enabled=True, wake_action="zero_g_2", reference_time=datetime(2026, 11, 19)
            )
        )
    ctrl, _ = controller()
    assert ctrl.alarm_capability is None
    ctrl._receive.alarm_capable = True
    assert ctrl.alarm_capability is not None
    ctrl.validate_alarm(AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19)))


async def test_cancel_during_final_hold_tail_does_not_invent_a_missing_refresh(clock, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        Delivery,
        DeviceCommandScheduler,
        delivered,
    )

    ctrl, coord = controller()
    results = []

    async def wait(milliseconds, event):
        event.set()
        return False

    monkeypatch.setattr(ctrl, "_wait", wait)

    async def operation(context):
        coord.cancel_command = context.cancel_event
        with delivered(results.append):
            await ctrl.press("head_up", duration_ms=1)
            context.cancel_event.clear()

    await DeviceCommandScheduler("jerome-hold-tail").execute(CommandIntent(operation))
    assert packets(coord) == ["6e01002493", "6e01006edd"]
    assert results == [Delivery.SENT]


@pytest.mark.parametrize(("interrupt_after", "expected"), [(1, "partial"), (None, "sent")])
async def test_aroma_marks_only_a_required_remaining_frame(
    clock, monkeypatch, interrupt_after, expected
):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
        delivered,
    )

    ctrl, coord = controller()
    ctrl._receive.aroma_capable = True
    results = []
    waits = 0

    async def wait(milliseconds, event):
        nonlocal waits
        waits += 1
        if waits == interrupt_after:
            event.set()
            return False
        return True

    monkeypatch.setattr(ctrl, "_wait", wait)

    async def operation(context):
        coord.cancel_command = context.cancel_event
        with delivered(results.append):
            await ctrl.configure_aroma((1, 1, 2))
            context.cancel_event.clear()

    await DeviceCommandScheduler("jerome-aroma-delivery").execute(CommandIntent(operation))
    assert len(packets(coord)) == (interrupt_after or 3)
    assert results[0].value == expected


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_missing_name_never_borrows_another_apps_timing(clock, monkeypatch, wire):
    from tests.error_helpers import raises_key

    ctrl, coord = controller(wire=wire)
    session = ctrl._session
    ctrl._session = None
    coord.entry.data.pop("ble_device_name")
    monkeypatch.setattr(bed, "select", lambda *args, **kwargs: session)
    with raises_key("jerome_device_name"):
        await ctrl.start_notify()
    assert ctrl._session is None
    assert packets(coord) == []
    coord.client.start_notify.assert_not_awaited()


@pytest.mark.parametrize("change", ["stop", "owner"])
async def test_admission_is_rechecked_in_settled_writer(change):
    ctrl, coord = controller()
    loop = asyncio.get_running_loop()
    if change == "stop":
        loop.call_soon(coord.cancel_command.set)
        await ctrl._send(p.control(b"\x24", "FRAMED"), coord.cancel_command)
    else:
        loop.call_soon(setattr, coord, "controller", object())
        with pytest.raises(ConnectionError):
            await ctrl._send(p.INITIALIZE)
    assert packets(coord) == []
    coord.record_command_trace.assert_not_called()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_gvrm_visible_roles_and_wire_admission_agree(clock, wire):
    from tests.error_helpers import raises_key

    ctrl, coord = controller("GVRM", wire)
    assert {"tv", "lounge", "zero_gravity", "flat", "toggle_underbed_light"} <= ctrl._actions.keys()
    assert not {"save_m1", "save_m2", "m1", "m2"} & ctrl._actions.keys()
    keys = {s.key for s in ctrl.controller_button_specs}
    if wire == "RAW":
        assert "jerome_lounge" in keys
        ctrl.validate_action("lounge", keep=True)
        await ctrl.press("lounge", duration_ms=370)
        assert packets(coord) == ["43", "43", "43", "6e"]
    else:
        ctrl._receive.light_capable = True
        assert not ctrl.supports_light_state_feedback
        assert "jerome_lounge" not in keys
        assert "jerome_lounge" not in ctrl.held_control_options
        with raises_key("jerome_action"):
            ctrl.validate_action("lounge")
        with raises_key("jerome_action"):
            await ctrl.press("lounge")
        assert packets(coord) == []
    ctrl._wire = None
    assert "jerome_lounge" not in {s.key for s in ctrl.controller_button_specs}


async def test_idle_disconnect_retains_entity_shapes_without_authorizing_settings(clock):
    ctrl, coord = controller("A1RM")
    session = ctrl._session
    for packet in ("6e0e00017d", "6e1a000189"):
        ctrl._notification(session, session.notify, bytearray.fromhex(packet))
    before = {s.key for s in ctrl.controller_number_specs}
    assert len(before) == 4
    assert ctrl.supports_light_color_control
    ctrl.on_disconnect()
    assert before == {s.key for s in ctrl.controller_number_specs}
    assert ctrl.supports_light_color_control
    assert not ctrl._receive.light_capable and not ctrl._receive.aroma_capable
    with pytest.raises(ServiceValidationError):
        await ctrl.configure_aroma((1, 2, 3))
    restored = bed.JeromeController(coord, capability_snapshot=ctrl.capability_snapshot())
    assert before == {s.key for s in restored.controller_number_specs}
    assert restored.supports_light_color_control
    assert not restored._receive.light_capable
    assert packets(coord) == []


async def test_rgb_first_turn_on_uses_fresh_off_state_without_inventing_color(clock):
    from custom_components.adjustable_bed.controller_state import ControllerState
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

    ctrl, coord = controller("A1RM")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00017d"))
    runtime = MagicMock(
        capability_controller=ctrl, controller=ctrl, controller_state=ControllerState()
    )
    runtime.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    light = AdjustableBedLight(runtime, LIGHT_DESCRIPTION)
    show = await light._send_rgb(ctrl, {})
    show()
    assert light.is_on
    assert light.rgb_color is None
    assert packets(coord) == ["6e01003cab", "6e01006edd"]


async def test_service_reconnects_before_dynamic_capability_validation(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import target

    await async_register_services(hass)
    ctrl, coord = controller("A1RM")
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00017d"))
    ctrl.on_disconnect()
    parent, _ = target(family=bed.JeromeController)
    parent.capability_controller = ctrl
    connections = []

    async def reconnect_and_run(command, **kwargs):
        if ctrl._session is None:
            connections.append(True)
            ctrl._session = session
            ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00017d"))
        await command(ctrl)

    async def query_live(query, **kwargs):
        result = []

        async def capture(ctrl):
            result.append(await query(ctrl))

        await reconnect_and_run(capture)
        return result[0]

    parent.async_execute_controller_query.side_effect = query_live
    parent.async_execute_controller_command.side_effect = reconnect_and_run
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(parent, "both")], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "jerome_bed",
            {"device_id": "one", "action": "light_color", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
    assert connections == [True]
    assert packets(coord) == [p.rgb(1, 2, 3).hex()]


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize("connected", [True, False])
async def test_side_layout_enters_options_and_requires_live_transport(
    hass, enable_custom_integrations, wire, connected
):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.pairing import (
        build_single_address_pair_entry_data,
        supports_single_address_pairing,
    )

    ctrl, mocked = controller("DHRM", wire)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bed",
        unique_id="AA:BB:CC:DD:EE:FF",
        version=5,
        data={
            **mocked.entry.data,
            "address": "AA:BB:CC:DD:EE:FF",
            "bed_type": "richmat_classic_apps",
            "name": "Bed",
        },
    )
    entry.add_to_hass(hass)
    inner = AdjustableBedCoordinator(hass, entry)
    inner._client = mocked.client
    inner._controller = ctrl
    ctrl._coordinator = inner
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = inner
    assert supports_single_address_pairing("richmat_classic_apps", "jerome2", product_type="DHRM")
    with pytest.raises(ValueError, match="transport proof"):
        build_single_address_pair_entry_data(entry.data, name="Bed")
    client = inner._client
    if not connected:
        inner._client = None
        ctrl._wire = None

    async def connect(reset_timer=True):
        inner._client = client
        ctrl._wire = wire
        return True

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert "pair_sides" in menu["menu_options"]
    with patch.object(inner, "async_ensure_connected", side_effect=connect):
        result = await hass.config_entries.options.async_configure(
            menu["flow_id"], {"next_step_id": "pair_sides"}
        )
        if not connected:
            assert result["type"] == "progress"
            await hass.async_block_till_done()
            result = await hass.config_entries.options.async_configure(result["flow_id"])
    if wire == "RAW":
        assert result["errors"] == {"base": "single_address_pairing_unsupported"}
    else:
        assert not result.get("errors")
        with (
            patch.object(hass.config_entries, "async_unload", AsyncMock(return_value=True)),
            patch.object(hass.config_entries, "async_setup", AsyncMock(return_value=True)),
        ):
            await hass.config_entries.options.async_configure(result["flow_id"], {"confirm": True})
            await hass.async_block_till_done()
        assert entry.data["pair_mode"] == "single_address"
    inner._cancel_disconnect_timer()


async def test_batch_rejects_framed_missing_operand_before_any_target_writes(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key
    from tests.test_generic_services import target

    await async_register_services(hass)
    first, one = controller("A1RM")
    second, two = controller("GVRM")

    def bind(ctrl):
        parent, _ = target(family=bed.JeromeController)
        parent.capability_controller = ctrl

        async def run(command, **kwargs):
            await command(ctrl)

        async def query(command, **kwargs):
            return await command(ctrl)

        parent.async_execute_controller_query.side_effect = query
        parent.async_execute_controller_command.side_effect = run
        return parent

    targets = [(bind(first), "both"), (bind(second), "both")]
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=(targets, []),
        ),
        raises_key("jerome_action"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "jerome_bed",
            {"device_id": ["one", "two"], "action": "zero_gravity"},
            blocking=True,
        )
    assert packets(one) == packets(two) == []


def native_runtime(hass, layout="DHRM", address="AA:BB:CC:DD:EE:01"):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl, mocked = controller(layout)
    entry = MockConfigEntry(
        domain="adjustable_bed",
        title="Bed",
        unique_id=address,
        version=5,
        data={
            **mocked.entry.data,
            "address": address,
            "bed_type": "richmat_classic_apps",
            "name": "Bed",
            "connection_mode": "release",
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    inner = AdjustableBedCoordinator(hass, entry)
    inner._client, inner._controller = mocked.client, ctrl
    inner._client.disconnect = AsyncMock()
    ctrl._coordinator = inner
    return inner, ctrl


def native_pair(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    inner, ctrl = native_runtime(hass)
    data = build_single_address_pair_entry_data(inner.entry.data, name="Bed", transport_proven=True)
    return (
        SingleAddressPairedCoordinator(
            hass, MockConfigEntry(domain="adjustable_bed", data=data), inner
        ),
        inner,
        ctrl,
    )


async def test_native_both_movement_and_stop_emit_both_source_side_modes(hass, clock):
    from unittest.mock import patch

    pair, inner, ctrl = native_pair(hass)
    client = inner.client
    with patch.object(inner, "async_ensure_connected", AsyncMock(return_value=True)):
        await pair.async_execute_controller_command(
            lambda c: c.press("head_up", duration_ms=1), side="both"
        )
        assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
            "6e01002493",
            "6e01006edd",
            "6e01012494",
            "6e01016ede",
        ]
        client.write_gatt_char.reset_mock()
        await pair.async_stop_command(side="both")
        assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
            "6e01006edd",
            "6e01016ede",
        ]
    inner._cancel_disconnect_timer()
    client.is_connected = False


async def test_paired_rejected_input_is_a_query_result_without_stop(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key

    pair, inner, ctrl = native_pair(hass)
    client = inner.client
    await async_register_services(hass)
    before = inner.stop_epoch
    with (
        patch.object(inner, "async_ensure_connected", AsyncMock(return_value=True)),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ),
        raises_key("jerome_action"),
    ):
        await hass.services.async_call(
            DOMAIN, "jerome_bed", {"device_id": "one", "action": "lounge"}, blocking=True
        )
    client.write_gatt_char.assert_not_awaited()
    assert inner.stop_epoch == before
    inner._cancel_disconnect_timer()
    client.is_connected = False


async def test_batch_holds_inspected_links_past_a_later_targets_idle_timeout(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    first, one = native_runtime(hass, "A1RM")
    second, two = native_runtime(hass, "A1RM", "AA:BB:CC:DD:EE:02")
    clients = [first.client, second.client]
    for ctrl in (one, two):
        session = ctrl._session
        ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00017d"))
    query = second.async_execute_controller_query

    async def later_query(callback, **kwargs):
        first._cancel_disconnect_timer()
        await first._async_idle_disconnect()
        assert first.is_connected
        return await query(callback, **kwargs)

    await async_register_services(hass)
    with (
        patch.object(first, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(second, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(second, "async_execute_controller_query", side_effect=later_query),
        patch.object(first, "_async_disconnect_locked", AsyncMock()) as disconnect,
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, "both"), (second, "both")], []),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "jerome_bed",
            {"device_id": ["one", "two"], "action": "light_color", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
        disconnect.assert_not_awaited()
    for inner, client in zip((first, second), clients, strict=True):
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [p.rgb(1, 2, 3)]
        assert not inner._command_connection_holds
        inner._cancel_disconnect_timer()
        client.is_connected = False


async def test_sequential_batch_reacquires_capability_proof_on_each_new_link(hass, clock):
    from contextlib import ExitStack
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    first, one = native_runtime(hass, "A1RM")
    second, two = native_runtime(hass, "A1RM", "AA:BB:CC:DD:EE:02")
    inners, controllers = (first, second), (one, two)
    sessions = [ctrl._session for ctrl in controllers]
    clients = [inner.client for inner in inners]
    connected = [0, 0]
    for inner, ctrl, client in zip(inners, controllers, clients, strict=True):
        ctrl._known_light = True
        inner._offline_controller = ctrl
        inner._client = inner._controller = None
        ctrl.on_disconnect()
        client.is_connected = False
        hass.config_entries.async_update_entry(
            inner.entry,
            data={
                **inner.entry.data,
                "capabilities": {"richmat_classic_apps": ctrl.capability_snapshot()},
            },
        )

    pair = PairedBedCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN, data={"pair_id": "pair_bed", "name": "Bed"}),
        {"left": first, "right": second},
        connection_mode="sequential",
    )

    def prepare(index):
        inner, ctrl, client, session = (
            inners[index],
            controllers[index],
            clients[index],
            sessions[index],
        )

        async def connect(**kwargs):
            assert not inners[1 - index].is_connected
            connected[index] += 1
            client.is_connected = True
            inner._client, inner._controller = client, ctrl
            ctrl._session = session
            ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00017d"))
            return True

        async def ensure(**kwargs):
            return True if inner.is_connected else await connect()

        async def disconnect():
            client.is_connected = False

        return connect, ensure, disconnect

    await async_register_services(hass)
    with ExitStack() as stack:
        for index, inner in enumerate(inners):
            connect, ensure, disconnect = prepare(index)
            stack.enter_context(patch.object(inner, "async_connect", side_effect=connect))
            stack.enter_context(patch.object(inner, "async_ensure_connected", side_effect=ensure))
            clients[index].disconnect.side_effect = disconnect
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "both")], []),
            )
        )
        await hass.services.async_call(
            DOMAIN,
            "jerome_bed",
            {"device_id": "one", "action": "light_color", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
    assert connected == [2, 2]
    for inner, client in zip(inners, clients, strict=True):
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [p.rgb(1, 2, 3)]
        assert not inner.is_connected
        assert not inner._command_connection_holds
        inner._cancel_disconnect_timer()


async def test_paired_inspection_does_not_replace_an_active_shared_timer_hold(
    hass, clock, monkeypatch
):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key

    pair, inner, ctrl = native_pair(hass)
    client = inner.client
    moving, finish = asyncio.Event(), asyncio.Event()
    cancellation = []

    async def held_wait(milliseconds, cancel):
        moving.set()
        cancellation.append(cancel)
        done = asyncio.create_task(finish.wait())
        stopped = asyncio.create_task(cancel.wait())
        try:
            await asyncio.wait((done, stopped), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (done, stopped):
                task.cancel()
            await asyncio.gather(done, stopped, return_exceptions=True)
        clock[0] += milliseconds / 1000
        return not cancel.is_set()

    monkeypatch.setattr(ctrl, "_wait", held_wait)
    await async_register_services(hass)
    with (
        patch.object(inner, "async_ensure_connected", AsyncMock(return_value=True)),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ),
    ):
        movement = asyncio.create_task(
            pair.async_execute_controller_command(
                lambda c: c.press("head_up", keep=True, duration_ms=1), side="left"
            )
        )
        await moving.wait()
        rejected = asyncio.create_task(
            hass.services.async_call(
                DOMAIN, "jerome_bed", {"device_id": "one", "action": "lounge"}, blocking=True
            )
        )
        try:
            for _ in range(12):
                await asyncio.sleep(0)
            assert not cancellation[0].is_set()
            assert not movement.done()
            assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
                "6e01002493"
            ]
        finally:
            finish.set()
            await movement
        with raises_key("jerome_action"):
            await rejected
    assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
        "6e01002493",
        "6e01006edd",
    ]
    assert inner.stop_epoch == 0
    inner._cancel_disconnect_timer()
    client.is_connected = False


@pytest.mark.parametrize("stop_after", [0, 1])
async def test_batch_stop_during_inspection_rejects_before_any_action(hass, clock, stop_after):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.error_helpers import raises_key

    first, _ = native_runtime(hass, "6BRM")
    second, _ = native_runtime(hass, "6BRM", "AA:BB:CC:DD:EE:02")
    clients = [first.client, second.client]
    inspected = (first, second)[stop_after]
    query = inspected.async_execute_controller_query

    async def inspect_then_stop(callback, **kwargs):
        result = await query(callback, **kwargs)
        await second.async_stop_command()
        return result

    await async_register_services(hass)
    with (
        patch.object(first, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(second, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(inspected, "async_execute_controller_query", side_effect=inspect_then_stop),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, "both"), (second, "both")], []),
        ),
        raises_key("action_stopped"),
    ):
        await hass.services.async_call(
            DOMAIN, "jerome_bed", {"device_id": ["one", "two"], "action": "head_up"}, blocking=True
        )
    clients[0].write_gatt_char.assert_not_awaited()
    assert [call.args[1].hex() for call in clients[1].write_gatt_char.await_args_list] == [
        "6e01006edd"
    ]
    assert second.stop_epoch == 1
    for inner, client in zip((first, second), clients, strict=True):
        inner._cancel_disconnect_timer()
        client.is_connected = False


@pytest.mark.parametrize("caller_cancelled", [False, True])
async def test_stop_during_connection_inspection_is_translated_unless_caller_cancelled(
    hass, clock, caller_cancelled
):
    from unittest.mock import patch

    from homeassistant.core import ServiceCall

    from custom_components.adjustable_bed.beds.richmat_classic.jerome_services import handle_jerome
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.error_helpers import raises_key

    first, _ = native_runtime(hass, "6BRM")
    second, _ = native_runtime(hass, "6BRM", "AA:BB:CC:DD:EE:02")
    clients = [first.client, second.client]
    checking, resume = asyncio.Event(), asyncio.Event()

    async def delayed_connection(**kwargs):
        checking.set()
        await resume.wait()
        return True

    call = ServiceCall(
        hass,
        DOMAIN,
        "jerome_bed",
        {
            "device_id": ["one", "two"],
            "action": "head_up",
            "keep": False,
            "confirm": False,
            "long_press": False,
            "duration_ms": 1000,
        },
    )
    with (
        patch.object(first, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(second, "async_ensure_connected", side_effect=delayed_connection),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, "both"), (second, "both")], []),
        ),
    ):
        operation = asyncio.create_task(handle_jerome(call))
        await checking.wait()
        stop = asyncio.create_task(second.async_stop_command())
        for _ in range(8):
            await asyncio.sleep(0)
        assert second.stop_epoch == 1
        if caller_cancelled:
            operation.cancel()
        resume.set()
        if caller_cancelled:
            with pytest.raises(asyncio.CancelledError):
                await operation
        else:
            with raises_key("action_stopped"):
                await operation
        await stop
    clients[0].write_gatt_char.assert_not_awaited()
    assert [call.args[1].hex() for call in clients[1].write_gatt_char.await_args_list] == [
        "6e01006edd"
    ]
    for inner, client in zip((first, second), clients, strict=True):
        assert not inner._command_connection_holds
        inner._cancel_disconnect_timer()
        client.is_connected = False
