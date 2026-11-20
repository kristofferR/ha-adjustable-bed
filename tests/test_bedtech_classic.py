"""Bed Tech's native controls, independent wire literals and session boundaries."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.bedtech.classic import (
    SNORE_ENABLED,
    BedTechClassicController,
    Classifier,
)
from custom_components.adjustable_bed.beds.richmat_mh import protocol as p
from custom_components.adjustable_bed.beds.richmat_mh.app_catalog import catalog
from custom_components.adjustable_bed.beds.richmat_mh.controller import (
    SMART_LIGHT_LOCK_KEY,
    SNORE_KEY,
    resolve_model,
)
from custom_components.adjustable_bed.profiles.bedtech_classic import SURFACE_IDS
from custom_components.adjustable_bed.profiles.richmat_mh_apps import variants
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.state_helpers import state_writer
from tests.test_richmat_mh import sleeps as sleeps


def make(model="5i", *, variant=None, snapshot=None):
    c = MagicMock()
    c.cancel_command = asyncio.Event()
    c.stop_epoch = 0
    c.motor_count = 2
    c.get_max_angle.return_value = 68.0
    c.motor_pulse_count = 2
    c.motor_pulse_delay_ms = 100
    data = {"capabilities": {"richmat_mh": snapshot}} if snapshot else {}
    c.entry = SimpleNamespace(data=data)
    c.controller_state = {}
    c.client = MagicMock(is_connected=True)
    c.client.write_gatt_char = AsyncMock()
    c.handle_controller_state_update.side_effect = c.controller_state.__setitem__
    c.handle_controller_state_updates.side_effect = state_writer(c.controller_state)
    ctrl = BedTechClassicController(c, variant=variant or f"model_{model}")
    c.controller = ctrl
    ctrl._owner_client = c.client
    ctrl._write_char = MagicMock(uuid=p.GATT_MAPS[0][1], properties=["write"])
    return ctrl


def frames(ctrl):
    return [bytes(call.args[1]).hex() for call in ctrl.client.write_gatt_char.call_args_list]


def test_app_is_separate_and_fully_selectable():
    assert len(catalog("bedtech_classic")) == len(SURFACE_IDS) == 514
    assert variants("bedtech_classic")["model_a7rm"] == "BT2000"
    assert resolve_model("bedtech_classic", "auto", "Cool Touch xyz")[1] == "choose_model"
    assert resolve_model("bedtech_classic", "model_3i", None) == ("3i", None)
    assert resolve_model("bedtech_classic", "auto", "5i")[1] == "no_name"
    assert "model_qrrm" not in variants("bedtech_classic")


@pytest.mark.parametrize("model", SURFACE_IDS)
def test_catalog_mints_only_usable_unique_entities(model):
    ctrl = make(model)
    for version in ("0000", "0001"):
        ctrl._version, ctrl._call_page = version, version == "0001"
        buttons = ctrl.controller_button_specs
        assert len({b.key for b in buttons}) == len(buttons)
        assert all(b.name.strip() for b in buttons)
        assert all(b.hold is None for b in buttons if b.requires_confirmation)
        assert all(
            spec.native_min_value <= spec.native_max_value for spec in ctrl.controller_number_specs
        )
        assert all(
            spec.key
            for spec in (
                *ctrl.motor_control_specs,
                *ctrl.controller_select_specs,
                *ctrl.controller_state_sensor_specs,
            )
        )


def test_generic_and_typed_routes_stay_independent():
    ctrl = make("5i")
    assert any(c.code == 0x2A and c.keep_ms == 100 for c in ctrl._controls())
    assert not any(c.code == 0x2A for c in make("grrm")._controls())
    assert not any(c.code == 0x2A for c in make("bprn")._controls())
    ctrl = make("3i")
    ctrl._version, ctrl._call_page = "0001", True
    assert ctrl._memory_slots()[3][1].code == 0xB3
    assert ctrl._memory_slots()[3][1].keep_ms == 0
    ctrl = make("7i")
    ctrl._version, ctrl._call_page = "0001", True
    assert next(x for x in ctrl._angles() if x[1] == "Pillow") == (3, "Pillow", 0, 25, 0)


async def test_mode_captured_before_wait_and_release_drained():
    with virtual_clock():
        ctrl = make()
        ctrl._transmit_mode = 2
        ctrl._coordinator.motor_pulse_count = 1
        await ctrl._ble_lock.acquire()
        task = asyncio.create_task(ctrl.move_axis("head_feet", "down"))
        await asyncio.sleep(0)
        ctrl._transmit_mode = 1
        ctrl._ble_lock.release()
        await task
        assert frames(ctrl) == ["6e01022a9b", "6e01026edf"]


async def test_stop_before_ble_lane_sends_only_cleanup():
    with virtual_clock():
        ctrl = make()
        await ctrl._ble_lock.acquire()
        task = asyncio.create_task(ctrl.move_axis("head", "up"))
        await asyncio.sleep(0)
        ctrl._coordinator.stop_epoch += 1
        ctrl._coordinator.cancel_command.set()
        ctrl._ble_lock.release()
        await task
        assert frames(ctrl) == ["6e01006edd"]


async def test_reconnect_during_hold_cannot_release_new_link():
    with virtual_clock():
        ctrl = make()
        original = ctrl.client

        async def sent(*_args, **_kwargs):
            ctrl._session_generation += 1
            ctrl._coordinator.client = MagicMock(is_connected=True)

        original.write_gatt_char.side_effect = sent
        with raises_key("bed_changed"):
            await ctrl.move_axis("head", "up")
        assert original.write_gatt_char.await_count == 1
        ctrl.client.write_gatt_char.assert_not_called()


def test_led_feedback_without_phantom_sender_and_snore_init_bug():
    ctrl = make("cfrm")
    ctrl._dev = {"led": True, "snore": True}
    assert not any("smart_light_lock" in s.key for s in ctrl.controller_button_specs)
    ctrl._classifier.rx_type = "INIT"
    ctrl._handle_notification(None, bytearray.fromhex("6e23000a9b"))
    assert ctrl._coordinator.controller_state[SMART_LIGHT_LOCK_KEY] is True
    ctrl._handle_notification(None, bytearray.fromhex("6e214500d4"))
    assert SNORE_KEY not in ctrl._coordinator.controller_state
    ctrl._classifier.rx_type = "SNORE"
    ctrl._handle_notification(None, bytearray.fromhex("6e234621f8"))
    assert ctrl._coordinator.controller_state[SNORE_KEY] == "anti_snore"
    ctrl._classifier.rx_type = "SNORE"
    ctrl._handle_notification(None, bytearray.fromhex("6e07010177"))
    assert ctrl._coordinator.controller_state[SNORE_ENABLED] is True


def test_parser_keeps_response_specific_checks_and_fences_truncation():
    parser = Classifier()
    parser.rx_type = "INIT"
    assert parser.feed(bytes.fromhex("6e23000a00")) == []
    assert parser.feed(bytes.fromhex("6e90348000"))[0].extra == ("-128",)
    parser = Classifier()
    assert parser.feed(bytes.fromhex("6e20")) == []
    # Calendar packets have neither a declared-length nor sum admission in this app.
    assert parser.feed(bytes.fromhex("6e20000501020102030405ff"))[0].kind == "calendar"


@pytest.mark.parametrize("cancel_after_frame, expected", [(False, "none"), (True, "partial")])
async def test_required_repetition_delivery_is_settled(cancel_after_frame, expected):
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from tests.test_shown_state import _running_command

    ctrl = make()
    command = _running_command(ctrl._coordinator.cancel_command)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    shown = []
    local_stop = asyncio.Event()
    if cancel_after_frame:
        ctrl.client.write_gatt_char.side_effect = lambda *_a, **_kw: local_stop.set()
    else:
        local_stop.set()
    try:
        with scheduler.delivered(shown.append):
            await ctrl.write_command(
                bytes.fromhex("6e01002493"),
                repeat_count=2,
                repeat_delay_ms=0,
                cancel_event=local_stop,
            )
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    assert shown == [expected]
    assert not ctrl._coordinator.cancel_command.is_set()


@pytest.mark.parametrize("version, interval", [(False, 0.3), (True, 0.4)])
async def test_startup_uses_own_schedule_and_never_delivers_a_user_frame(version, interval, sleeps):
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from tests.test_shown_state import _running_command

    ctrl = make()
    command = _running_command(ctrl._coordinator.cancel_command)

    async def reply(_char, data, **_kw):
        if data.hex() == "6e9a000008" and version:
            ctrl._apply(p.Event("version", "0001"))

    ctrl.client.write_gatt_char.side_effect = reply
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    try:
        await ctrl._run_session_setup()
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    assert sleeps == [0.3, 0.3] + [interval] * (16 if version else 10)
    assert frames(ctrl)[:2] == ["6e9a000008", "6e02010071"]
    assert command.frames_written == 0


@pytest.mark.parametrize("powered_reply", [False, True])
async def test_cached_mattress_needs_fresh_session_initialization(powered_reply, sleeps):
    ctrl = make(
        variant="model_5i_mattress",
        snapshot={
            "app": "bedtech_classic",
            "model": "5i_mattress",
            "version": "0000",
            "normal_ready": True,
        },
    )
    assert ctrl._normal_ready
    assert any("mattress" in spec.key for spec in ctrl.motor_control_specs)
    ctrl._normal_values[1, 1] = 3
    before_probe = []

    async def reply(_char, data, **_kwargs):
        if not before_probe:
            before_probe.append((ctrl._normal_ready, dict(ctrl._normal_values)))
            if powered_reply:
                raw = bytearray([0x5E, 0x1A, 0, 1] + [0] * 24)
                raw[19] = 1
                ctrl._apply(p.Event("mattress_init", p.finalize(raw).hex()))

    ctrl.client.write_gatt_char.side_effect = reply
    await ctrl._run_session_setup()
    assert before_probe == [(False, {})]
    assert ctrl._normal_ready is powered_reply
    ctrl.client.write_gatt_char.reset_mock(side_effect=True)

    if powered_reply:
        await ctrl.normal_setting("left", "pressure", "low")
        ctrl.client.write_gatt_char.side_effect = lambda *_a, **_kw: (
            ctrl._coordinator.cancel_command.set()
        )
        await ctrl.normal_pillow("left", 1)
        assert frames(ctrl) == ["5e01010161", "5e01060166", "5e01060065"]
    else:
        with pytest.raises(ValueError):
            await ctrl.normal_setting("left", "pressure", "low")
        with pytest.raises(ValueError):
            await ctrl.normal_pillow("left", 1)
        with raises_key("option_unavailable"):
            await ctrl.normal_pillow_stop("left")
        ctrl.client.write_gatt_char.assert_not_called()


async def test_native_clock_sends_old_typed_clock_literals():

    ctrl = make("5i")
    ctrl._dev = {"alarm": True}
    ctrl._version, ctrl._call_page = "0001", True
    with patch(
        "custom_components.adjustable_bed.beds.bedtech.classic.dt_util.now",
        return_value=datetime(2026, 11, 19, 18, 2, 3, tzinfo=UTC),
    ):
        assert ctrl.supports_clock_sync
        await ctrl.sync_clock()
    assert frames(ctrl) == ["6e13120295", "6e1403ff84"]


async def test_button_light_off_and_minutes_use_the_selected_page():
    with virtual_clock():
        ctrl = make("garm")
        ctrl._dev = {"led": True}
        await ctrl.tap(0x75)
        await ctrl.write_light_timer(900, 15)
        assert frames(ctrl) == ["6e010075e4", "6e01006edd", "6e0b038400"]
        from custom_components.adjustable_bed.beds.richmat_mh.controller import (
            LIGHT_TIMER_MINUTES_KEY,
        )

        assert ctrl._coordinator.controller_state[LIGHT_TIMER_MINUTES_KEY] == 15


def calendar_model():
    from custom_components.adjustable_bed.profiles.bedtech_classic import CALENDAR_MODELS

    return make(next(iter(sorted(CALENDAR_MODELS))))


def test_calendar_capacity_and_accessory_fields_are_reported_not_guessed():
    from custom_components.adjustable_bed.beds.bedtech.classic import ACCESSORY, CALENDAR_ROWS

    ctrl = calendar_model()
    assert ctrl.alarm_capability.live_check and ctrl.alarm_capability.live_slots
    ctrl._apply(p.Event("calendar", "6e2000050102100203042eff"))
    assert ctrl._calendar_alarms[10]["bed"] == 2
    # Invalid signed times remain observations and cannot authorize an overwrite.
    ctrl._apply(p.Event("calendar", "6e2000050102100280042eff"))
    assert 10 not in ctrl._calendar_alarms
    assert ctrl._coordinator.controller_state[CALENDAR_ROWS][-1]["hour"] == -128
    ctrl._apply(p.Event("accessory", "6e90b060006e90d28000"))
    assert ctrl._coordinator.controller_state[ACCESSORY] == {
        "mode": 1,
        "power": 1,
        "intensity": -128,
    }


async def test_calendar_save_preserves_reported_bed_and_only_sends_actual_alarm(sleeps):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    with patch(
        "custom_components.adjustable_bed.beds.bedtech.classic.dt_util.now",
        return_value=datetime(2026, 11, 19, 18, 2, 3, tzinfo=UTC),
    ):
        await ctrl.configure_alarm(
            AlarmRequest(
                enabled=True,
                slot=2,
                hour=7,
                minute=30,
                wake_action="memory_1",
                weekdays=(0, 6),
                reference_time=datetime(2026, 11, 19, 18, 2, 3, tzinfo=UTC),
            )
        )
    assert frames(ctrl)[-2] == "6e200d0501010201071e2e837b"
    assert frames(ctrl)[-1] == "6e2008050100009c"


def test_stale_callback_cannot_publish_after_profile_change():
    ctrl = make("cfrm")
    ctrl._dev = {"led": True}
    ctrl._classifier.rx_type = "INIT"
    ctrl._coordinator.entry.data = {"protocol_variant": "model_5i"}
    ctrl._handle_notification(None, bytearray.fromhex("6e23000a9b"))
    assert SMART_LIGHT_LOCK_KEY not in ctrl._coordinator.controller_state


async def test_calendar_delete_uses_only_a_reported_slot(sleeps):
    ctrl = calendar_model()
    with raises_key("alarm_refresh_needed"):
        await ctrl.delete_alarm(2)
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    spec = next(s for s in ctrl.controller_button_specs if s.key == "bedtech_delete_alarm_2")
    assert (
        spec.requires_confirmation
        and spec.hold is None
        and not spec.entity_registry_enabled_default
    )
    await ctrl.delete_alarm(2)
    assert frames(ctrl) == ["6e200805020102a0", "6e2008050100009c"]
    assert sleeps == [0.3]
    assert 2 not in ctrl._calendar_alarms


async def test_calendar_roster_change_while_waiting_rejects_the_write():
    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.delete_alarm(2))
    await asyncio.sleep(0)
    ctrl._calendar_alarms[2] = {**ctrl._calendar_alarms[2], "bed": 2}
    ctrl._ble_lock.release()
    with raises_key("bed_changed"):
        await task
    ctrl.client.write_gatt_char.assert_not_called()


async def test_settings_edit_cannot_suppress_captured_session_release():
    with virtual_clock():
        ctrl = make()
        ctrl._transmit_mode = 2
        ctrl._coordinator.motor_pulse_count = 1

        def edited(*_args, **_kwargs):
            ctrl._coordinator.entry.data = {"protocol_variant": "model_cfrm"}
            ctrl._transmit_mode = 1

        ctrl.client.write_gatt_char.side_effect = edited
        await ctrl.move_axis("head", "up")
        assert frames(ctrl) == ["6e01022495", "6e01026edf"]


async def test_cold_typed_readback_uses_pending_session_route(sleeps):
    from custom_components.adjustable_bed.beds.richmat_mh.controller import (
        ANGLE_KEYS,
        INTENSITY_KEYS,
        MOTOR_MODE_KEY,
    )

    ctrl = make("5i")
    ctrl.set_group_type("GROUP_SYNC")

    def reply(_char, data, **_kwargs):
        if data == p.TX_VERSION:
            ctrl._apply(p.Event("version", "0001"))
        elif data == p.TX_ALARM:
            ctrl._apply(p.Event("init", p.RX_ALARM))
        elif data == p.TX_MOTOR_MODE:
            ctrl._apply(p.Event("motor_mode", "01"))
        elif data == p.TX_MOTOR_ANGLES[0]:
            ctrl._apply(p.Event("motor_angle", "00", ("32",)))
        elif data == p.TX_QUERY_MASSAGE:
            ctrl._apply(p.Event("massage", "000000010011"))

    ctrl.client.write_gatt_char.side_effect = reply
    await ctrl._run_session_setup()
    assert ctrl.route == "C"
    state = ctrl._coordinator.controller_state
    assert state[MOTOR_MODE_KEY] == "mode1"
    assert state[ANGLE_KEYS["back"]] == 32
    assert state[INTENSITY_KEYS["head"]] == 3
    assert state[INTENSITY_KEYS["foot"]] == 2


def test_generic_countdown_does_not_grant_typed_clock():
    ctrl = make("ufrm")
    ctrl._dev = {"alarm": True}
    assert ctrl.alarm_capability is not None
    assert not ctrl.supports_clock_sync


async def test_native_calendar_preflight_reads_slot_after_idle_disconnect(hass, sleeps):
    from contextlib import nullcontext

    from tests.alarm_helpers import call_set_alarm

    ctrl = calendar_model()
    ctrl.on_disconnect()
    ctrl._owner_client = ctrl.client

    def reply(_char, data, **_kwargs):
        if data.hex() == "6e2008050100009c":
            ctrl._apply(p.Event("calendar", "6e2000050102100203042eff"))

    ctrl.client.write_gatt_char.side_effect = reply
    # This receiver has no single-address side routing. The shared test helper
    # otherwise binds "both" for controllers that support that topology.
    with patch.object(ctrl, "side_scope", return_value=nullcontext()):
        await call_set_alarm(hass, ctrl, {"enabled": False, "slot": 10})
    assert any(frame.startswith("6e200d0501010a02") for frame in frames(ctrl))


def test_late_calendar_records_offer_dynamic_delete_buttons():
    ctrl = calendar_model()
    assert ctrl.has_dynamic_buttons and ctrl.has_dynamic_controller_entities
    assert next(
        s for s in ctrl.controller_button_specs if s.key == "bedtech_refresh_alarms"
    ).diagnostic
    assert not any("delete_alarm" in spec.key for spec in ctrl.controller_button_specs)
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    assert any(spec.key == "bedtech_delete_alarm_2" for spec in ctrl.controller_button_specs)


async def test_calendar_disable_reads_latest_fields_at_dispatch(sleeps):
    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.codec.richmat import record_20_len

    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    entered = asyncio.Event()
    proceed = asyncio.Event()
    original = ctrl._dispatch

    async def waiting(frame, **kwargs):
        if kwargs.get("factory") is not None:
            entered.set()
            await proceed.wait()
        await original(frame, **kwargs)

    with patch.object(ctrl, "_dispatch", side_effect=waiting):
        task = asyncio.create_task(
            ctrl.configure_alarm(
                AlarmRequest(
                    enabled=False, slot=2, reference_time=datetime(2026, 11, 19, tzinfo=UTC)
                )
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        ctrl._apply(p.Event("calendar", "6e2000050102020108102f45"))
        proceed.set()
        await task
    assert record_20_len(5, 1, 1, (2, 1, 8, 16, 0x2F, 0x44)).hex() in frames(ctrl)


async def test_calendar_compound_identity_rejects_ambiguous_native_slot():
    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    ctrl._apply(p.Event("calendar", "6e2000050102020208102f45"))
    assert set(ctrl._calendar_records) == {(2, 1), (2, 2)}
    assert 2 not in ctrl._calendar_alarms
    with raises_key("alarm_refresh_needed"):
        await ctrl.delete_alarm(2)
    ctrl.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("operation", ["clock", "countdown"])
async def test_stop_between_required_user_frames_is_partial(operation):
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from custom_components.adjustable_bed.alarm import AlarmRequest
    from tests.test_shown_state import _running_command

    with virtual_clock():
        ctrl = make("5i" if operation == "clock" else "ufrm")
        ctrl._dev = {"alarm": True}
        if operation == "clock":
            ctrl._version, ctrl._call_page = "0001", True
        command = _running_command(ctrl._coordinator.cancel_command)
        token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
        shown = []

        def stop(*_args, **_kwargs):
            ctrl._coordinator.stop_epoch += 1
            ctrl._coordinator.cancel_command.set()

        ctrl.client.write_gatt_char.side_effect = stop
        try:
            with scheduler.delivered(shown.append), pytest.raises(asyncio.CancelledError):
                if operation == "clock":
                    await ctrl.sync_clock()
                else:
                    await ctrl.configure_alarm(
                        AlarmRequest(
                            enabled=True,
                            hour=7,
                            wake_action="memory_1",
                            reference_time=datetime(2026, 11, 19, tzinfo=UTC),
                        )
                    )
        finally:
            scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
        assert shown == ["partial"]
        assert len(frames(ctrl)) == 1


def test_calendar_keeps_reported_waist_alarm_capability():
    ctrl = calendar_model()
    ctrl._waist = True
    capability = ctrl.alarm_capability
    assert capability is not None and capability.mattress_sides == ("left", "right", "both")
    assert capability.massage_intensities == 3


async def test_cancel_during_last_clock_write_does_not_invent_a_missing_frame():
    from custom_components.adjustable_bed import command_scheduler as scheduler
    from tests.test_shown_state import _running_command

    ctrl = make("5i")
    ctrl._dev = {"alarm": True}
    ctrl._version, ctrl._call_page = "0001", True
    command = _running_command(ctrl._coordinator.cancel_command)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    entered, release = asyncio.Event(), asyncio.Event()

    async def writing(*_args, **_kwargs):
        if ctrl.client.write_gatt_char.await_count == 2:
            entered.set()
            await release.wait()

    ctrl.client.write_gatt_char.side_effect = writing
    task = asyncio.create_task(ctrl.sync_clock())
    shown = []
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        release.set()
        with scheduler.delivered(shown.append), pytest.raises(asyncio.CancelledError):
            await task
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    assert len(frames(ctrl)) == 2
    assert shown == ["sent"]


def test_live_calendar_slots_cannot_disable_native_live_check():
    from custom_components.adjustable_bed.alarm import AlarmCapability

    with pytest.raises(ValueError, match="require a live check"):
        AlarmCapability(live_slots=True)


def test_known_delete_button_survives_disconnect_and_snapshot_restore():
    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    key = "bedtech_delete_alarm_2"
    assert ctrl.controller_button_available(key)
    snapshot = ctrl.capability_snapshot()
    ctrl.on_disconnect()
    assert key in {spec.key for spec in ctrl.controller_button_specs}
    assert not ctrl.controller_button_available(key)
    ctrl._coordinator.entry.data = {"capabilities": {"richmat_mh": snapshot}}
    restored = BedTechClassicController(ctrl._coordinator, variant=f"model_{ctrl.model.model_id}")
    assert key in {spec.key for spec in restored.controller_button_specs}
    assert not restored.controller_button_available(key)
    restored._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    assert restored.controller_button_available(key)


async def test_stop_before_delete_write_keeps_the_reported_slot():
    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.delete_alarm(2))
    await asyncio.sleep(0)
    ctrl._coordinator.stop_epoch += 1
    ctrl._coordinator.cancel_command.set()
    ctrl._ble_lock.release()
    await task
    assert 2 in ctrl._calendar_alarms
    ctrl.client.write_gatt_char.assert_not_called()


async def test_native_calendar_keeps_the_identity_checked_before_write(hass):
    from contextlib import nullcontext

    from tests.alarm_helpers import call_set_alarm

    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    configure = ctrl.configure_alarm
    checked = []

    async def replace_record(request):
        checked.append(request.record_identity)
        ctrl._calendar_records.clear()
        ctrl._apply(p.Event("calendar", "6e20000501020202071e2e83"))
        await configure(request)

    with (
        patch.object(ctrl, "side_scope", return_value=nullcontext()),
        patch.object(ctrl, "configure_alarm", side_effect=replace_record),
        raises_key("bed_changed"),
    ):
        await call_set_alarm(hass, ctrl, {"enabled": False, "slot": 2})
    assert checked == [(2, 1)]
    ctrl.client.write_gatt_char.assert_not_called()


def test_bed_calendar_rejects_mattress_intensity_without_mattress_side():
    from dataclasses import replace

    from custom_components.adjustable_bed.alarm import AlarmRequest

    ctrl = calendar_model()
    ctrl._waist = True
    request = AlarmRequest(
        enabled=False, massage_intensity=3, reference_time=datetime(2026, 11, 19, tzinfo=UTC)
    )
    with raises_key("alarm_option_not_supported"):
        ctrl.validate_alarm(request)
    ctrl.validate_alarm(replace(request, mattress_side="left"))


def test_disconnect_publishes_roster_invalidation_for_button_availability():
    from custom_components.adjustable_bed.beds.ruf_richmat.controller import (
        CALENDAR_ALARM_COUNT,
        CALENDAR_ALARMS,
    )

    ctrl = calendar_model()
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    ctrl._coordinator.handle_controller_state_updates.reset_mock()
    ctrl.on_disconnect()
    updates = ctrl._coordinator.handle_controller_state_updates.call_args.args
    assert CALENDAR_ALARMS({}) in updates and CALENDAR_ALARM_COUNT(0) in updates
    assert not ctrl.controller_button_available("bedtech_delete_alarm_2")
    assert "bedtech_delete_alarm_2" in {spec.key for spec in ctrl.controller_button_specs}


@pytest.mark.parametrize("boundary", ["live_check", "dispatch"])
async def test_native_calendar_page_cannot_change_to_three_slot_alarm(hass, boundary):
    from contextlib import nullcontext

    from tests.alarm_helpers import call_set_alarm

    ctrl = calendar_model()
    ctrl._version = "0001"
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    original = ctrl.check_alarm if boundary == "live_check" else ctrl.configure_alarm

    async def changed_page(request):
        ctrl._apply(p.Event("init", p.RX_ALARM))
        assert not ctrl._calendar_page()
        await original(request)

    with (
        patch.object(ctrl, "side_scope", return_value=nullcontext()),
        patch.object(
            ctrl,
            "check_alarm" if boundary == "live_check" else "configure_alarm",
            side_effect=changed_page,
        ),
        raises_key("bed_changed"),
    ):
        await call_set_alarm(hass, ctrl, {"enabled": False, "slot": 2})
    ctrl.client.write_gatt_char.assert_not_called()


async def test_calendar_page_rechecked_after_ble_wait(sleeps):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    ctrl = calendar_model()
    ctrl._version = "0001"
    ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(
        ctrl.configure_alarm(
            AlarmRequest(
                enabled=False,
                slot=2,
                record_identity=(2, 1),
                reference_time=datetime(2026, 11, 19, tzinfo=UTC),
            )
        )
    )
    await asyncio.sleep(0)
    ctrl._apply(p.Event("init", p.RX_ALARM))
    assert not ctrl._calendar_page()
    ctrl._ble_lock.release()
    with raises_key("bed_changed"):
        await task
    ctrl.client.write_gatt_char.assert_not_called()


async def test_native_cached_three_slot_plan_cannot_write_new_calendar_page(hass):
    from contextlib import nullcontext

    from custom_components.adjustable_bed import services
    from tests.alarm_helpers import call_set_alarm

    ctrl = calendar_model()
    ctrl._version, ctrl._call_page, ctrl._dev = "0001", True, {"alarm": True}
    assert ctrl.alarm_capability.slots == 3 and not ctrl.alarm_capability.live_slots
    execute = services._execute_alarm_step

    async def reconnect(*args, **kwargs):
        ctrl._version, ctrl._call_page = "0000", False
        ctrl._apply(p.Event("calendar", "6e20000501020201071e2e83"))
        assert ctrl.alarm_capability.live_slots
        await execute(*args, **kwargs)

    with (
        patch.object(ctrl, "side_scope", return_value=nullcontext()),
        patch.object(services, "_execute_alarm_step", side_effect=reconnect),
        patch.object(ctrl, "configure_alarm", new=AsyncMock()) as configure,
        raises_key("bed_changed"),
    ):
        await call_set_alarm(hass, ctrl, {"enabled": False, "slot": 2})
    configure.assert_not_awaited()
    ctrl.client.write_gatt_char.assert_not_called()
