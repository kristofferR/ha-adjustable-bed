"""Base Remote's admitted sessions, scheduling, setup and useful entities."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.baseremote.controller import BaseRemoteController
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from tests.hold_lease_wire import virtual_clock


def controller(layout="6BRM", wire="FRAMED", **settings):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:66"
    coordinator.cancel_command = asyncio.Event()
    coordinator.entry.data = {
        "protocol_variant": "baseremote",
        "product_type": layout,
        "ble_device_name": "6BRM",
        "motor_pulse_count": 1,
        **settings,
    }
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()

    @asynccontextmanager
    async def connection_guard():
        yield lambda _reason: coordinator.async_disconnect()

    coordinator.async_connection_operation_guard.side_effect = connection_guard
    from tests.state_helpers import state_writer

    coordinator.published_state = {}
    coordinator.handle_controller_state_updates.side_effect = state_writer(
        coordinator.published_state
    )
    ctrl = BaseRemoteController(coordinator, device_name="6BRM")
    coordinator.controller = ctrl
    write = SimpleNamespace(uuid="write", properties=["write"], handle=66)
    notify = SimpleNamespace(uuid="notify", properties=["notify"], handle=67)
    ctrl._session = Transport(coordinator.client, write, notify, wire)
    ctrl._worker.set_interval(170 if wire == "RAW" else 150)
    return ctrl, coordinator


def packets(coordinator):
    return [call.args[1].hex() for call in coordinator.client.write_gatt_char.await_args_list]


async def test_held_control_ends_at_deadline_and_releases_once():
    ctrl, coordinator = controller()
    with virtual_clock():
        await ctrl.execute_action(1, hold_ms=300)
    assert packets(coordinator) == ["6e01002493", "6e01002493", "6e01006edd"]


@pytest.mark.parametrize("wire,expected", [("RAW", []), ("FRAMED", ["6e01006edd"])])
async def test_null_short_release_never_turns_into_a_save(wire, expected):
    ctrl, coordinator = controller("AORM", wire)
    with virtual_clock():
        # Public entities expose the real long action only; the caller/worker
        # transition itself must keep the transport-specific null semantics.
        from custom_components.adjustable_bed.beds.richmat_classic.caller import (
            Selection,
            transition,
        )
        from custom_components.adjustable_bed.beds.richmat_classic.protocol import Worker

        button = ctrl._button(8)
        up = transition(button, ctrl.layout, wire, Selection(), "UP")
        worker = Worker(mode=3, counter=2)
        from custom_components.adjustable_bed.beds.richmat_classic.caller import RETAIN

        if up.mode is not RETAIN:
            worker.mode = up.mode
        if wire == "RAW":
            assert worker.mode == 3 and worker.counter == 2
        else:
            assert worker.mode == 0
            assert worker.tick()[0].delay_ms == 50
        if wire == "FRAMED":
            await ctrl._release(50)
    assert packets(coordinator) == expected


async def test_save_waits_threshold_and_confirmation_never_holds():
    ctrl, coordinator = controller("A0RM")
    save = next(g for g in ctrl._contexts() if g.long)
    with virtual_clock():
        await ctrl.async_gesture(save)
    assert len(packets(coordinator)) == 2
    spec = next(s for s in ctrl.controller_button_specs if s.key == save.key)
    assert spec.requires_confirmation and spec.hold is None


async def test_cancellation_drains_att_before_its_captured_cleanup():
    ctrl, coordinator = controller()
    started, finish = asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.sleep

    async def write(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            started.set()
            await finish.wait()

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(ctrl.execute_action(1, hold_ms=1000))
        await started.wait()
        task.cancel()
        await real_sleep(0)
        assert len(packets(coordinator)) == 1
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert packets(coordinator) == ["6e01002493", "6e01006edd"]


async def test_old_session_cannot_receive_cleanup_or_notification():
    ctrl, coordinator = controller()
    old = ctrl._session
    with ctrl._transaction():
        ctrl.on_disconnect()
        ctrl._session = replace(old)
        await ctrl._release()
        with pytest.raises(ConnectionError, match="captured"):
            await ctrl._send(b"\x24")
    ctrl._notification(old, old.notify, bytearray.fromhex("6e09010078"))
    assert not ctrl._receive.alarm_capable
    assert packets(coordinator) == []


@pytest.mark.parametrize("layout,node", [("DTRM", 10), ("F6RM", 7), ("F4RM", 4), ("FRRM", 11)])
def test_inert_nodes_are_never_entities(layout, node):
    ctrl, _ = controller(layout)
    assert all(g.node != node for g in ctrl._contexts())


def test_no_ui_draft_selectors_or_raw_state_sensors():
    ctrl, _ = controller("E3RM")
    assert ctrl.controller_select_specs == ()
    assert ctrl.controller_state_sensor_specs == ()
    assert any(g.long for g in ctrl._contexts())


@pytest.mark.parametrize("raw", [False, True])
async def test_real_scheduler_lease_uses_source_refresh_and_drains_cleanup(raw):
    from tests.hold_lease_wire import intervals, leased_hold

    scenario = "richmat_classic_apps:baseremote:6BRM" + (":nordic" if raw else "")

    async def move(ctrl):
        await ctrl.hold_control("baseremote_m0_n1_53", 30000)

    wire = await leased_hold(scenario, move, end_after_s=0.8, end="expire")
    assert {w.data for w in wire.held} == {bytes.fromhex("34" if raw else "6e01002493")}
    refresh = 170 if raw else 150
    # The stored GATT double adds 7 ms to an acknowledged write.
    assert set(intervals(wire.held)) == {refresh + 7}
    assert [w.data for w in wire.after] == [bytes.fromhex("6e" if raw else "6e01006edd")]
    assert wire.after[0].at_ms == wire.ended_ms + 50


async def test_startup_and_queries_are_preparation_with_their_actual_delays(monkeypatch):
    from custom_components.adjustable_bed.beds.baseremote import controller as bed

    ctrl, coordinator = controller("O0RM")
    session = ctrl._session
    monkeypatch.setattr(bed, "select", lambda *_args, **_kwargs: session)
    timestamps = []

    async def write(_char, packet, **kwargs):
        timestamps.append((round(asyncio.get_running_loop().time() * 1000), packet.hex()))

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await ctrl.start_notify()
    assert [p for _, p in timestamps] == ["6e02010071", "6e08010178", "6e0a000179", "6e1a000088"]
    assert [b[0] - a[0] for a, b in zip(timestamps, timestamps[1:], strict=False)] == [0, 500, 500]
    assert coordinator.client.start_notify.await_count == 1


async def test_captured_mode_applies_to_command_and_cleanup_when_other_choices_change():
    ctrl, coordinator = controller("DHRM")
    gesture = next(g for g in ctrl._contexts() if g.mode == 1 and ctrl._held(g))

    async def write(_char, packet, **kwargs):
        ctrl._mode = 0

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await ctrl.async_gesture(gesture, duration_ms=150)
    assert all(bytes.fromhex(p)[2] == 1 for p in packets(coordinator))
    assert packets(coordinator)[-1] == "6e01016ede"


async def test_a_frame_waiting_for_another_gatt_operation_obeys_a_later_stop():
    ctrl, coordinator = controller("D1RM")
    cancel = asyncio.Event()
    async with ctrl.ble_lock:
        send = asyncio.create_task(ctrl._send(b"\x01", cancel))
        await asyncio.sleep(0)
        cancel.set()
    await send
    assert packets(coordinator) == []


def test_every_layout_has_only_real_bed_controls_and_saves_never_hold():
    from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
    from custom_components.adjustable_bed.profiles.baseremote import EXCLUDED_LAYOUTS

    for layout in load_catalog("baseremote").models.keys() - EXCLUDED_LAYOUTS:
        ctrl, _ = controller(layout)
        for spec in ctrl.controller_button_specs:
            assert not spec.name.startswith(("Button ", "Save button")), (layout, spec.name)
            assert not any(
                word in spec.name.lower()
                for word in ("music", "volume", "previous", "next", "start pause")
            )
            if spec.requires_confirmation:
                assert spec.hold is None and spec.key not in ctrl.held_control_options


def test_old_only_controls_are_unavailable_on_framed_and_never_get_fallback_bytes():
    ctrl, _ = controller("GVRM")
    key = next(g.key for g in ctrl._contexts() if g.node == 3)
    assert not ctrl.controller_button_available(key)
    ctrl._session = replace(ctrl._session, wire="RAW")
    assert ctrl.controller_button_available(key)
    assert next(g.label for g in ctrl._contexts() if g.node == 3) == "M1"


def test_translated_rejections_for_excluded_layouts_and_bad_controls():
    from tests.error_helpers import raises_key

    for layout in ("TEST", "RMCS", "WFRM", "FWRM"):
        with raises_key("baseremote_layout"):
            controller(layout)
    ctrl, _ = controller()
    with raises_key("baseremote_control"):
        ctrl.validate_hold_control("missing", 100)


async def test_partial_settings_publish_only_the_delivered_step():
    from custom_components.adjustable_bed.beds.baseremote.controller import (
        AROMA_INTERVAL,
        AROMA_ON_TIME,
        AROMA_PAUSE,
    )
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    ctrl, coordinator = controller()
    ctrl._receive.aroma_capable = True
    spec = next(s for s in ctrl.controller_number_specs if s.state_key == AROMA_ON_TIME)
    context = CommandContext(
        object(),
        coordinator.cancel_command,
        0,
        "settings",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        coordinator.cancel_command.set()
        await spec.set_fn(ctrl, 12)
        assert AROMA_ON_TIME not in coordinator.published_state
        coordinator.cancel_command.clear()
        with virtual_clock():
            await spec.set_fn(ctrl, 12)
        assert coordinator.published_state[AROMA_ON_TIME] == 12
        # The app's Save writes all three times, the unchanged ones at its starting values.
        assert coordinator.published_state[AROMA_INTERVAL] == 1
        assert coordinator.published_state[AROMA_PAUSE] == 2
        assert context.frames_written == 3
        pause = next(s for s in ctrl.controller_number_specs if s.state_key == AROMA_PAUSE)
        with virtual_clock():
            started = asyncio.get_running_loop().time()
            await pause.set_fn(ctrl, 5)
            # 150 ms after each write.
            assert asyncio.get_running_loop().time() - started == pytest.approx(0.45)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert packets(coordinator) == [
        "6e1b000c95",
        "6e1c00018b",
        "6e1d00028d",
        "6e1b000c95",
        "6e1c00018b",
        "6e1d000590",
    ]
    assert ctrl.persisted_app_state["aroma_times"] == [12, 1, 5]


async def test_group_cleanup_cannot_disconnect_a_replacement_session():
    ctrl, coordinator = controller()
    coordinator.async_disconnect = AsyncMock()
    group_write = SimpleNamespace(uuid="group-write", properties=["write"], handle=70)
    group_notify = SimpleNamespace(uuid="group-notify", properties=["notify"], handle=71)
    service = MagicMock()
    service.get_characteristic.side_effect = lambda uuid: (
        group_write if uuid.startswith("0000ffe2") else group_notify
    )
    coordinator.client.services.get_service.return_value = service

    async def write(_char, _packet, **kwargs):
        ctrl._session = replace(ctrl._session)

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(ConnectionError, match="changed before group cleanup"):
        await ctrl.async_group("AB12")
    assert packets(coordinator) == [b"AT+GROUPAB12\r\n".hex()]
    coordinator.async_disconnect.assert_not_awaited()


def test_capability_parser_accepts_fragments_but_no_desk_motor_state():
    ctrl, _ = controller()
    session = ctrl._session
    ctrl._notification(session, session.notify, bytearray.fromhex("6e09"))
    ctrl._notification(session, session.notify, bytearray.fromhex("010078"))
    assert ctrl._receive.alarm_capable
    ctrl._notification(session, session.notify, bytearray.fromhex("6e900000064044"))
    assert ctrl._receive.height_cm is None
    ctrl._notification(session, session.notify, bytearray.fromhex("6e1a000189"))
    assert ctrl._receive.aroma_capable


@pytest.mark.parametrize("raw,expected", [(False, ["6e01006edd", "6e01016ede"]), (True, ["6e"])])
async def test_explicit_stop_fans_out_only_to_modes_the_layout_owns(raw, expected):
    ctrl, coordinator = controller("DHRM", "RAW" if raw else "FRAMED")
    with virtual_clock():
        await ctrl.stop_all()
    assert packets(coordinator) == expected


async def test_capability_events_reveal_numbers_and_old_specs_recheck_the_new_session():
    from custom_components.adjustable_bed.beds.baseremote.controller import LAMP_TIMEOUT
    from tests.error_helpers import raises_key

    ctrl, coordinator = controller()
    assert ctrl.controller_number_specs == ()
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
    timeout = next(s for s in ctrl.controller_number_specs if s.state_key == LAMP_TIMEOUT)
    assert coordinator.handle_controller_state_updates.call_count >= 1
    ctrl.on_disconnect()
    ctrl._session = Transport(
        coordinator.client,
        SimpleNamespace(uuid="new", properties=["write"]),
        SimpleNamespace(uuid="notify", properties=["notify"]),
        "FRAMED",
    )
    with raises_key("baseremote_control"):
        await timeout.set_fn(ctrl, 30)
    assert packets(coordinator) == []


async def test_alarm_actions_are_layout_owned_and_cancel_does_not_invent_a_wake_action():
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from tests.error_helpers import raises_key

    ctrl, coordinator = controller("6BRM")
    assert ctrl.alarm_capability is None
    ctrl._receive.alarm_capable = True
    assert ctrl.alarm_capability is not None
    request = AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19, 12, tzinfo=UTC))
    with virtual_clock():
        await ctrl.configure_alarm(request)
    assert packets(coordinator) == ["6e05000073", "6e06000074"]
    with raises_key("baseremote_alarm"):
        ctrl.validate_alarm(replace(request, enabled=True, wake_action="tv"))


def test_mode_scoped_motion_and_memory_are_enabled_without_collapsing_card_targets():
    from custom_components.adjustable_bed.card import CardSection

    ctrl, _ = controller("DHRM")
    assert {s.key for s in ctrl.motor_control_specs} == {
        "left_head",
        "left_feet",
        "right_head",
        "right_feet",
    }
    memories = [s for s in ctrl.controller_button_specs if s.name in ("Left M1", "Right M1")]
    assert len(memories) == 2
    assert all(
        s.entity_registry_enabled_default and s.card.section is CardSection.PRESETS
        for s in memories
    )


async def test_head_and_feet_are_covers_that_hold_each_sides_own_control():
    """#1161: the operands the Richmat remotes move the head and feet with."""
    ctrl, coordinator = controller("ECRM")
    covers = {s.key: s for s in ctrl.motor_control_specs}
    assert not [s for s in ctrl.controller_button_specs if "Motor" in s.name]
    assert {s.hold.up_control for s in covers.values()} <= set(ctrl.held_control_options)
    # The card looks the release button up by its translation key.
    release = next(s for s in ctrl.controller_button_specs if s.release_only)
    assert {s.hold.release_button_key for s in covers.values()} == {release.translation_key}
    with virtual_clock():
        await covers["left_head"].open_fn(ctrl)
        await covers["right_feet"].close_fn(ctrl)
    assert packets(coordinator) == ["6e01002493", "6e01006edd", "6e01012797", "6e01016ede"]


def test_a_motor_that_another_connection_sends_differently_keeps_its_number():
    ctrl, _ = controller("6BRM")
    assert not ctrl.supports_motor_control
    assert "Motor 1 up" in {s.name for s in ctrl.controller_button_specs}


async def test_one_base_has_each_control_once_and_never_addresses_the_right_side():
    ctrl, coordinator = controller("ECRM", baseremote_single_base=True)
    assert [s.key for s in ctrl.motor_control_specs] == ["head", "feet"]
    names = {s.name for s in ctrl.controller_button_specs}
    assert {"Flat", "Zero Gravity", "Save M1"} <= names
    assert not [name for name in names if "eft" in name or "ight" in name]
    with virtual_clock():
        await ctrl.motor_control_specs[1].open_fn(ctrl)
        await ctrl.stop_all()
    assert packets(coordinator) == ["6e01002695", "6e01006edd", "6e01006edd"]
    # A layout without sides has nothing to merge.
    ctrl, _ = controller("BTRM", baseremote_single_base=True)
    assert "Mode 3 Flat" in {s.name for s in ctrl.controller_button_specs}


async def test_stop_during_group_subscription_prevents_the_configuration_write():
    ctrl, coordinator = controller()

    async def disconnect():
        coordinator.client.is_connected = False
        return True

    coordinator.async_disconnect = AsyncMock(side_effect=disconnect)
    write = SimpleNamespace(uuid="group-write", properties=["write"])
    notify = SimpleNamespace(uuid="group-notify", properties=["notify"])
    service = MagicMock()
    service.get_characteristic.side_effect = lambda uuid: (
        write if uuid.startswith("0000ffe2") else notify
    )
    coordinator.client.services.get_service.return_value = service

    async def stopped(*_args):
        coordinator.cancel_command.set()

    coordinator.client.start_notify.side_effect = stopped
    with virtual_clock():
        await ctrl.async_group("1234")
    assert packets(coordinator) == []
    coordinator.async_disconnect.assert_awaited_once()


@pytest.mark.parametrize("stop_after_frame,expected", [(0, "none"), (1, "partial"), (2, "sent")])
async def test_alarm_delivery_counts_only_its_required_frames(stop_after_frame, expected):
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        delivered,
    )

    ctrl, coordinator = controller()
    ctrl._receive.alarm_capable = True
    context = CommandContext(
        object(),
        coordinator.cancel_command,
        0,
        "alarm",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    if stop_after_frame == 0:
        coordinator.cancel_command.set()

    async def stop(_characteristic, _packet, **_kwargs):
        if len(packets(coordinator)) == stop_after_frame:
            coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = stop
    observed = []
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        with virtual_clock(), delivered(observed.append):
            await ctrl.configure_alarm(
                AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19, 12, tzinfo=UTC))
            )
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert observed == [expected]
    assert context.frames_written == stop_after_frame
    assert context.frames_skipped == (0 if stop_after_frame == 2 else 1)


async def test_configuration_only_receiver_rejects_a_previously_created_timer():
    from tests.error_helpers import raises_key

    ctrl, coordinator = controller("D1RM")
    assert ctrl.supports_massage_timer
    ctrl._group_only = True
    assert not ctrl.supports_massage_timer
    assert not ctrl.supports_lights
    with raises_key("baseremote_control"):
        await ctrl.set_massage_timer(10)
    assert packets(coordinator) == []


@pytest.mark.parametrize("change", ["stop", "replace"])
async def test_deferred_att_rechecks_before_it_starts(change):
    ctrl, coordinator = controller()

    def invalidate():
        if change == "stop":
            coordinator.cancel_command.set()
        else:
            ctrl._session = replace(ctrl._session)

    asyncio.get_running_loop().call_soon(invalidate)
    if change == "stop":
        await ctrl.write_command(b"\x24")
    else:
        with pytest.raises(ConnectionError, match="captured"):
            await ctrl.write_command(b"\x24")
    assert packets(coordinator) == []


async def test_group_third_service_never_becomes_a_bed_command_route():
    from tests.test_richmat_classic_transport import Service, Services, channel

    ctrl, coordinator = controller()
    coordinator.entry.data["richmat_classic_third_service"] = True
    group = Service(
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        [
            channel("0000ffe2-0000-1000-8000-00805f9b34fb", "write"),
            channel("0000ffe1-0000-1000-8000-00805f9b34fb", "notify"),
        ],
    )
    coordinator.client.services = Services([Service("one", []), Service("two", []), group])
    with virtual_clock():
        await ctrl.start_notify()
    assert ctrl._group_only
    assert ctrl._session.write.uuid.startswith("0000ffe2")
    assert packets(coordinator) == []


@pytest.mark.parametrize("cancel_at", ["att", "spacing"])
async def test_alarm_task_cancellation_retains_partial_delivery(cancel_at):
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        Delivery,
        delivered,
    )

    ctrl, coordinator = controller()
    ctrl._receive.alarm_capable = True
    started, finish = asyncio.Event(), asyncio.Event()
    context = CommandContext(
        object(),
        coordinator.cancel_command,
        0,
        "alarm",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    observed = []

    async def write(_characteristic, _packet, **_kwargs):
        if cancel_at == "att":
            started.set()
            await finish.wait()

    async def spacing(_ms, _cancel):
        started.set()
        await asyncio.Event().wait()
        return True

    coordinator.client.write_gatt_char.side_effect = write
    if cancel_at == "spacing":
        ctrl._wait = spacing

    async def run():
        with delivered(observed.append):
            await ctrl.configure_alarm(
                AlarmRequest(enabled=False, reference_time=datetime(2026, 11, 19, 12, tzinfo=UTC))
            )

    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        task = asyncio.create_task(run())
        await started.wait()
        task.cancel()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert len(packets(coordinator)) == 1
    assert observed == [Delivery.PARTIAL]


async def test_group_does_not_report_success_when_the_link_stays_open():
    from tests.error_helpers import raises_key
    from tests.test_richmat_classic_transport import Service, Services, channel

    ctrl, coordinator = controller()
    coordinator.async_disconnect = AsyncMock(return_value=False)
    coordinator.client.services = Services(
        [
            Service(
                "0000ffe0-0000-1000-8000-00805f9b34fb",
                [
                    channel("0000ffe2-0000-1000-8000-00805f9b34fb", "write"),
                    channel("0000ffe1-0000-1000-8000-00805f9b34fb", "notify"),
                ],
            )
        ]
    )
    with virtual_clock(), raises_key("baseremote_group_disconnect"):
        await ctrl.async_group("1234")
    assert packets(coordinator) == [b"AT+GROUP1234\r\n".hex()]


@pytest.mark.parametrize("layout", ["D1RM", "D9RM"])
async def test_massage_timer_is_the_shared_select_with_a_real_off(layout):
    from custom_components.adjustable_bed.beds.richmat_classic.protocol import massage_timer
    from tests.error_helpers import raises_key

    ctrl, coordinator = controller(layout)
    assert ctrl.supports_massage_timer and ctrl.auto_enable_massage
    assert ctrl.massage_timer_options == [10, 20, 30] and ctrl.massage_timer_can_turn_off
    assert ctrl.controller_select_specs == ()
    # The slider's four stops, which the app labels 0, 2H, 3H and 5H.
    for minutes, progress in ((0, 0), (10, 2), (20, 3), (30, 5)):
        coordinator.client.write_gatt_char.reset_mock()
        await ctrl.set_massage_timer(minutes)
        assert packets(coordinator) == [massage_timer(layout, progress).hex()]
    with raises_key("baseremote_control"):
        await ctrl.set_massage_timer(10)


def test_aroma_times_are_settings_that_start_disabled():
    from homeassistant.const import EntityCategory

    ctrl, _ = controller("D1RM")
    ctrl._receive.aroma_capable = True
    aroma = [s for s in ctrl.controller_number_specs if "aroma" in s.key]
    assert len(aroma) == 3
    assert all(
        not s.entity_registry_enabled_default and s.entity_category is EntityCategory.CONFIG
        for s in aroma
    )


async def test_a_nordic_connection_names_each_control_by_what_it_sends():
    from tests.error_helpers import raises_key

    framed, _ = controller("BERM", "FRAMED")
    light = framed._light_toggle()
    assert framed.supports_lights and framed._button(light).short == "3C"
    listed_for_framed = next(g for g in framed._contexts() if g.node == light and not g.long)

    ctrl, coordinator = controller("BERM", "RAW")
    # Over Nordic UART this layout's light control sends the legacy "motor 1+2 up" operand.
    assert not ctrl.supports_lights
    gesture = next(g for g in ctrl._contexts() if g.node == light and not g.long)
    assert gesture.label == "Motor 1+2 up" and gesture.key.endswith("_raw")
    assert not any("light" in s.name.lower() for s in ctrl.controller_button_specs)
    with raises_key("baseremote_control"):
        await ctrl.async_gesture(listed_for_framed)
    with raises_key("baseremote_control"):
        await ctrl.lights_toggle()
    assert packets(coordinator) == []


def test_a_long_press_light_off_stays_a_button_beside_the_light():
    ctrl, _ = controller("CZRM")
    assert ctrl.supports_light_toggle_control
    names = [s.name for s in ctrl.controller_button_specs]
    assert sum("light off" in n.lower() for n in names) == 1
    assert not any(n.lower().endswith("light on/off") for n in names)
