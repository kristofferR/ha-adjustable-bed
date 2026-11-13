"""Physical-session routing, cancellation and product-local operation gates."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import controller as bed
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    APP_NAMES as ALL_APP_NAMES,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import RISE_APPS
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from custom_components.adjustable_bed.profiles.richmat_resource_apps import APPS as RESOURCE_APPS
from tests.state_helpers import published

APP_NAMES = {app: name for app, name in ALL_APP_NAMES.items() if app not in RISE_APPS and app not in RESOURCE_APPS}


def controller(app="avocadoecobase", layout="GXRM", wire="FRAMED"):
    coord = MagicMock()
    coord.address = "AA:BB:CC:DD:EE:66"
    coord.cancel_command = asyncio.Event()
    coord.entry.data = {"protocol_variant": app, "product_type": layout, "motor_pulse_count": 1}
    coord.client.is_connected = True
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    ctrl = bed.RichmatClassicController(coord)
    write = SimpleNamespace(uuid="write", properties=["write"], handle=66)
    notify = SimpleNamespace(uuid="notify", properties=["notify"], handle=67)
    ctrl._session = Transport(coord.client, write, notify, wire)
    return ctrl, coord


@pytest.fixture
def instant(monkeypatch):
    async def wait(_ms, cancel):
        return not cancel.is_set()
    monkeypatch.setattr(bed.RichmatClassicController, "_wait", staticmethod(wait))
    sleep = AsyncMock()
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    return sleep


def packets(coord):
    return [c.args[1].hex() for c in coord.client.write_gatt_char.await_args_list]


async def test_null_worker_boundaries_preserve_raw_drop_and_framed_failure(instant):
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.beds.richmat_classic.protocol import Worker

    cases = json.loads((Path(__file__).parent / "fixtures/richmat_classic/null_worker_cases.json").read_text())
    assert len(cases) == 90
    for case in cases:
        ctrl, coord = controller(case["member"].split(".")[-1], wire=case["wire"])
        state = case["input"]
        ctrl._worker = Worker(mode=state["mode"], payload=None, count=2,
                              counter=2 if state["worker_phase"] == "threshold_reached" else 0,
                              fired=state["z"])
        if case["payload_action"] == "THROW_BEFORE_ENQUEUE_OR_POST;UNCAUGHT_WORKER_CAN_TERMINATE":
            with pytest.raises(ValueError, match="no framed payload"):
                await ctrl._iteration(coord.cancel_command, 0)
            assert packets(coord) == []
        else:
            await ctrl._iteration(coord.cancel_command, 0)
            expected = ["6e" if case["wire"] == "RAW" else "6e01006edd"] if case["release_reached"] else []
            assert packets(coord) == expected, case


def test_hold_selectors_preserve_source_callback_mutations():
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.beds.richmat_classic.caller import effective_status

    cases = json.loads((Path(__file__).parent / "fixtures/richmat_classic/hold_callbacks.json").read_text())
    for case in cases:
        ctrl, _ = controller(case["app"], case["layout"])
        expected = case["expected"]
        if not expected["affected_recall_ids"]:
            # The accepted callback exists, but mutates no widget in this layout.
            assert all(s.key != "richmat_classic_hold" for s in ctrl.controller_select_specs)
            continue
        hold = not expected["setReleaseHold"]
        ctrl._select("hold", "hold" if hold else "release")
        for c in ctrl._controls:
            if c.view_id in expected["affected_recall_ids"]:
                assert effective_status(c, ctrl.layout, ctrl._selection) == (1 if hold else 3), case
            if c.view_id in expected["affected_save_ids"]:
                assert ctrl.controller_button_available(f"richmat_classic_{c.node}") == hold, case
            if c.view_id == "btnFlat":
                assert effective_status(c, ctrl.layout, ctrl._selection) == expected["flat_status"], case


@pytest.mark.parametrize("app", ("fortywinks", "superior"))
def test_zrs6_navigation_is_not_exposed_as_a_bed_command(app):
    from custom_components.adjustable_bed.beds.richmat_classic.caller import Retain, transition

    ctrl, _ = controller(app, "ZRS6")
    assert [s.key for s in ctrl.controller_button_specs] == ["richmat_classic_release"]
    for c in ctrl._controls:
        result = transition(c, "ZRS6", "FRAMED", ctrl._selection, "DOWN", app=app)
        assert result.local == "navigate:" + c.tag
        assert isinstance(result.payload, Retain)
        assert isinstance(result.count_ms, Retain)
        assert result.owner == "retain"


@pytest.mark.parametrize("app", APP_NAMES)
async def test_short_preset_has_one_recall_and_one_release(app, instant):
    ctrl, coord = controller(app, "A0RN")
    node = next(c.node for c in ctrl._controls if c.short == "58" and c.status == 3)
    await ctrl.execute_action(node)
    assert packets(coord) == ["6e010058c7", "6e01006edd"]


@pytest.mark.parametrize("app", APP_NAMES)
async def test_long_preset_suppresses_short_recall_after_saving(app, instant):
    ctrl, coord = controller(app, "A0RN")
    node = next(c.node for c in ctrl._controls if c.short == "58" and c.status == 3)
    await ctrl.execute_action(node, long=True)
    assert packets(coord) == ["6e010064d3", "6e01006edd"]


async def test_armed_selectview_is_consumed_and_raw_does_not_emit_program(instant):
    ctrl, coord = controller()
    ctrl._selection = replace(ctrl._selection, armed=True)
    await ctrl.execute_action(4)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert not ctrl._selection.armed
    raw, raw_coord = controller(wire="RAW")
    raw._selection = replace(raw._selection, armed=True)
    await raw.execute_action(4)
    assert packets(raw_coord) == []  # Idle original1 UP guard does not invent a release.


async def test_cancelled_task_still_sends_fresh_release(instant):
    ctrl, coord = controller(layout="6BRM")
    count = 0
    async def write(_char, _packet, **_kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise asyncio.CancelledError
    coord.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await ctrl.execute_action(1)
    assert packets(coord) == ["6e01002493", "6e01006edd"]


async def test_a_stop_during_the_final_release_delay_still_releases():
    """A stop racing a held press's own release must not lose the release (virtual time)."""
    from tests.hold_lease_wire import virtual_clock

    ctrl, coord = controller(layout="6BRM")
    with virtual_clock():

        async def stop_during_release() -> None:
            # The press refreshes at 0 and 150 ms; its own release is due at 200 ms.
            await asyncio.sleep(0.175)
            coord.cancel_command.set()

        stopper = asyncio.create_task(stop_during_release())
        await ctrl.execute_action(1, hold_ms=150)
        await stopper
    assert packets(coord) == ["6e01002493", "6e01002493", "6e01006edd"]


async def test_cancelled_save_cannot_shorten_the_next_save_threshold(instant, monkeypatch):
    ctrl, coord = controller(layout="A0RN")
    node = next(c.node for c in ctrl._controls if c.short == "58" and c.status == 3)

    async def cancel_after_count(_ms, event):
        assert ctrl._worker.counter > 0
        event.set()
        return False

    monkeypatch.setattr(ctrl, "_wait", cancel_after_count)
    await ctrl.execute_action(node, long=True)
    assert ctrl._worker.counter == 0
    assert not ctrl._worker.fired
    assert ctrl._worker.payload is None
    assert packets(coord) == ["6e01006edd"]


async def test_failed_write_still_releases_and_does_not_retry(instant):
    ctrl, coord = controller(layout="6BRM")
    coord.client.write_gatt_char.side_effect = [RuntimeError("failed"), None]
    with pytest.raises(RuntimeError, match="failed"):
        await ctrl.execute_action(1)
    assert packets(coord) == ["6e01002493", "6e01006edd"]


async def test_old_session_callback_cannot_mutate_new_state():
    ctrl, coord = controller()
    old = ctrl._session
    ctrl._session = Transport(coord.client, old.write, old.notify, "RAW")
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable


async def test_raw_read_only_transport_still_controls_without_invented_reads(instant, monkeypatch):
    ctrl, coord = controller(layout="6BRM", wire="RAW")
    ctrl._device_name = "6BRM"
    selected = replace(ctrl._session, notify=SimpleNamespace(uuid="read", properties=["read"]))
    monkeypatch.setattr(bed, "select", lambda *_args, **_kwargs: selected)
    ctrl._session = None
    await ctrl.start_notify()
    coord.client.start_notify.assert_not_awaited()
    await ctrl.execute_action(1)
    assert packets(coord) == ["34", "34", "6e"]
    await ctrl.stop_notify()
    coord.client.stop_notify.assert_not_awaited()


@pytest.mark.parametrize("app", APP_NAMES)
@pytest.mark.parametrize("wire,layout,expected", [("RAW", "6BRM", []), ("RAW", "FWRM", ["6e94000002"]), ("FRAMED", "6BRM", ["6e02010071"]), ("FRAMED", "FWRM", ["6e94000002", "6e94000002"])])
async def test_startup_uses_exact_transport_initialization(app, wire, layout, expected, instant, monkeypatch):
    ctrl, coord = controller(app, layout=layout, wire=wire)
    ctrl._device_name = "6BRM"
    selected = ctrl._session
    monkeypatch.setattr(bed, "select", lambda *_args, **_kwargs: selected)
    ctrl._session = None
    await ctrl.start_notify()
    coord.client.start_notify.assert_awaited_once()
    assert packets(coord) == expected
    if wire == "FRAMED":
        instant.assert_awaited_once_with(0.3)


async def test_settings_queries_and_menu_gates(instant):
    ctrl, coord = controller(layout="A0RN")
    await ctrl.async_execute_richmat_classic_request(Request("query"))
    assert packets(coord) == ["6e08010178", "6e0a000179", "6e1a000088"]
    with pytest.raises(ValueError, match="capability"):
        ctrl.validate_richmat_classic_request(Request("aroma", aroma_values=(1, 1, 2)))
    ctrl._receive.feed(bytes.fromhex("6e1a000189"), app=ctrl.app, layout=ctrl.layout)
    ctrl.validate_richmat_classic_request(Request("aroma", aroma_values=(1, 1, 2)))


async def test_proven_settings_rows_survive_a_reconnect_and_a_new_controller(instant, monkeypatch):
    """With a disconnect between calls, a query's proven rows still gate the next call."""
    from custom_components.adjustable_bed.beds.richmat_classic.protocol import rgb

    ctrl, _ = controller(layout="A0RN")
    for reply in ("6e0e00037f", "6e1a000189"):
        ctrl._receive.feed(bytes.fromhex(reply), app=ctrl.app, layout=ctrl.layout)
    assert ctrl.persisted_app_state["menu"] == ["aroma", "light"]
    replacement, coord = controller(layout="A0RN")
    with pytest.raises(ValueError, match="menu"):
        replacement.restore_persisted_app_state({**ctrl.persisted_app_state, "menu": ["wifi"]})
    replacement.restore_persisted_app_state(ctrl.persisted_app_state)
    selected = replacement._session
    monkeypatch.setattr(bed, "select", lambda *_args, **_kwargs: selected)
    replacement._session = None
    await replacement.start_notify()
    replacement.validate_richmat_classic_request(Request("aroma", aroma_values=(1, 1, 2)))
    await replacement.async_execute_richmat_classic_request(Request("rgb", color=(255, 0, 0)))
    assert packets(coord)[-1] == rgb(255, 0, 0).hex()
    with pytest.raises(ValueError, match="capability"):
        replacement.validate_richmat_classic_request(Request("cancel_alarm"))


def test_capability_and_layout_alarm_gate():
    ctrl, _ = controller(layout="A0RN")
    with pytest.raises(ValueError, match="capability"):
        ctrl.validate_richmat_classic_request(Request("rgb", color=(255, 0, 0)))
    ctrl._receive.feed(bytes.fromhex("6e0e00037f"), app=ctrl.app, layout=ctrl.layout)
    ctrl.validate_richmat_classic_request(Request("rgb", color=(255, 0, 0)))
    ctrl._receive.feed(bytes.fromhex("6e09010078"), app=ctrl.app, layout=ctrl.layout)
    with pytest.raises(ValueError, match="alarm action"):
        ctrl.validate_richmat_classic_request(Request("alarm", action="arbitrary", when=time(7, 0)))


def test_avocado_urrm_observer_starvation_remains_member_specific():
    avocado, _ = controller(layout="URRM")
    coaster, _ = controller("coastersleep", "URRM")
    for ctrl in (avocado, coaster):
        for packet in ("6e09010078", "6e0e00037f", "6e1a000189"):
            ctrl._receive.feed(bytes.fromhex(packet), app=ctrl.app, layout=ctrl.layout)
    assert avocado._receive.menu == set()
    assert coaster._receive.menu == {"alarm", "light", "aroma"}


async def test_hold_state_reveals_separate_save_and_gates_long_press(instant):
    ctrl, coord = controller(layout="YGRM")
    save = next(c for c in ctrl._controls if c.view_id == "btnM1Long")
    recall = next(c for c in ctrl._controls if c.view_id == "btnM1")
    assert not ctrl.controller_button_available(f"richmat_classic_{save.node}")
    with pytest.raises(ValueError, match="hidden"):
        await ctrl.execute_action(save.node)
    ctrl._select("hold", "hold")
    assert ctrl.controller_button_available(f"richmat_classic_{save.node}")
    assert f"richmat_classic_{recall.node}_hold" in ctrl.held_control_options
    assert not ctrl.controller_button_available(f"richmat_classic_{recall.node}_long")
    await ctrl.execute_action(save.node)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]


@pytest.mark.parametrize("slot,packet", [(1,"6e96000408"),(2,"6e9600080c"),(3,"6e96001014"),(4,"6e95000003")])
async def test_desk_buttons_repeat_only_for_the_bounded_hold(slot, packet, instant):
    ctrl, coord = controller(layout="FWRM")
    await ctrl.async_execute_richmat_classic_request(Request("desk_recall", slot=slot, duration_ms=400))
    assert packets(coord) == [packet, packet]


async def test_desk_source_lifecycle_vectors_end_on_cancel_or_link_loss(instant, monkeypatch):
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "fixtures/richmat_classic/desk_lifecycles.json").read_text())
    for case in cases:
        ctrl, coord = controller("milemont", "FWRM")

        async def terminate(_milliseconds, cancel, *, kind=case["kind"], current=ctrl):
            if kind == "disconnect_resume":
                current.on_disconnect()
            else:
                cancel.set()
            return not cancel.is_set()

        monkeypatch.setattr(ctrl, "_wait", terminate)
        request = Request("desk_recall", slot=case["slot"], duration_ms=800)
        if case["kind"] == "disconnect_resume":
            with pytest.raises(ConnectionError, match="session"):
                await ctrl.async_execute_richmat_classic_request(request)
        else:
            await ctrl.async_execute_richmat_classic_request(request)
        assert packets(coord) == [case["expected_first"]], case


@pytest.mark.parametrize("operation", [Request("desk_recall", slot=1), Request("desk_unit", unit="cm"), Request("desk_target", height=80)])
def test_old_desk_response_hides_all_modern_controls(operation):
    ctrl, _ = controller(layout="FWRM")
    ctrl._receive.feed(bytes.fromhex("6e080064da"), app=ctrl.app, layout=ctrl.layout)
    with pytest.raises(ValueError, match="old-desk"):
        ctrl.validate_richmat_classic_request(operation)


@pytest.mark.parametrize("app", APP_NAMES)
async def test_error_confirmation_requires_a_new_desk_callback(app, instant):
    ctrl, coord = controller(app, "FWRM")
    request = Request("desk_reset")
    with pytest.raises(ValueError, match="awaiting confirmation"):
        ctrl.validate_richmat_classic_request(request)
    # Valid sixteen-byte 6e97 callback. The source error is buffer[6:8].
    ctrl._receive.feed(bytes.fromhex("6e970001000000000000000000000006"), app=app, layout="FWRM")
    assert ctrl._receive.error == "01"
    await ctrl.async_execute_richmat_classic_request(request)
    assert packets(coord) == ["6e95000003"]
    assert ctrl._receive.error == "01"  # Confirmation does not prove hardware recovery.
    with pytest.raises(ValueError, match="awaiting confirmation"):
        ctrl.validate_richmat_classic_request(request)


async def test_cancelled_settings_do_not_consume_confirmation_or_save_unsent_values(instant):
    ctrl, coord = controller(layout="FWRM")
    ctrl._receive.feed(bytes.fromhex("6e970001000000000000000000000006"), app=ctrl.app, layout=ctrl.layout)
    ctrl._receive.menu.add("light")
    coord.cancel_command.set()
    await ctrl.async_execute_richmat_classic_request(Request("desk_reset"))
    await ctrl.async_execute_richmat_classic_request(Request("lamp_save", minutes=7))
    assert packets(coord) == []
    assert ctrl._receive.error_confirmation_pending
    assert ctrl.persisted_app_state["lamp_minutes"] == 0


def test_saved_local_state_is_scoped_and_rejects_foreign_alarm_selection():
    ctrl, _ = controller(layout="A0RN")
    ctrl.restore_persisted_app_state({"lamp_minutes":5,"lamp_rgb":"00ff00"})
    assert ctrl.persisted_app_state["lamp_minutes"] == 5
    assert ctrl.persisted_app_state_key == "avocadoecobase:A0RN"
    with pytest.raises(ValueError, match="alarm action"):
        ctrl.restore_persisted_app_state({"alarm_selection":"foreign"})


async def test_desk_unit_callback_uses_serialized_current_session_only():
    ctrl, coord = controller(layout='FWRM')
    session = ctrl._session
    async def execute(command, **kwargs):
        await command(ctrl)
    coord.async_execute_controller_command = AsyncMock(side_effect=execute)
    await ctrl._reply_unit(session, 1)
    assert packets(coord) == ['6e91000100']
    assert coord.async_execute_controller_command.await_args.kwargs['resource'] == 'configuration'
    ctrl._session = None
    await ctrl._reply_unit(session, 0)
    assert packets(coord) == ['6e91000100']


async def test_alarm_preferences_require_a_new_ack_event(instant):
    ctrl, coord = controller(layout='A0RN')
    ctrl._pending_alarm = next(iter(ctrl._alarm_actions()))
    ctrl._notification(ctrl._session,ctrl._session.notify,bytearray.fromhex('6e07010177'))
    selected = ctrl._preferences['alarm_selection']
    ctrl._pending_alarm = 'another action'
    ctrl._notification(ctrl._session,ctrl._session.notify,bytearray.fromhex('6e900000060408'))
    assert ctrl._preferences['alarm_selection'] == selected


async def test_member_slider_resources_and_saved_progress(instant):
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "fixtures/richmat_classic/slider_vectors.json").read_text())
    for case in cases:
        ctrl, coord = controller(case["app"], case["layout"])
        await ctrl.async_execute_richmat_classic_request(Request("massage_timer", progress=case["progress"]))
        assert packets(coord) == [case["expected"]], case
        restored, _ = controller(case["app"], case["layout"])
        restored.restore_persisted_app_state(ctrl.persisted_app_state)
        assert restored.persisted_app_state["massage_progress"] == case["progress"]


async def test_mode_change_during_movement_applies_only_to_next_gesture(instant, monkeypatch):
    ctrl, coord = controller(layout="ACRN")
    changed = False

    async def change_mode(_ms, cancel):
        nonlocal changed
        if not changed:
            ctrl._select("mode", "1")
            changed = True
        return not cancel.is_set()

    monkeypatch.setattr(ctrl, "_wait", change_mode)
    await ctrl.execute_action(5)
    assert packets(coord) == ["6e01002493", "6e01002493", "6e01006edd"]
    coord.client.write_gatt_char.reset_mock()
    await ctrl.execute_action(5)
    assert packets(coord) == ["6e01012494", "6e01012494", "6e01016ede"]


async def test_hold_choice_during_save_cannot_suppress_gesture_release(instant, monkeypatch):
    ctrl, coord = controller(layout="YGRM")
    ctrl._select("hold", "release")
    node = next(c.node for c in ctrl._controls if c.view_id == "btnM1")

    async def change_hold(_ms, cancel):
        ctrl._select("hold", "hold")
        return not cancel.is_set()

    monkeypatch.setattr(ctrl, "_wait", change_hold)
    await ctrl.execute_action(node, long=True)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert ctrl._selection.hold is True


async def test_selected_save_and_hold_survive_controller_handoff(instant):
    ctrl, _ = controller(layout="GXRM")
    ctrl._select("program", "armed")
    restored, coord = controller(layout="GXRM")
    restored.restore_persisted_app_state(ctrl.persisted_app_state)
    await restored.execute_action(4)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert not restored._selection.armed
    hold, _ = controller(layout="YGRM")
    hold._select("hold", "hold")
    next_hold, _ = controller(layout="YGRM")
    next_hold.restore_persisted_app_state(hold.persisted_app_state)
    assert next_hold.held_control_options == hold.held_control_options
    assert next_hold._worker.mode == -1


def test_unexpected_disconnect_invalidates_session_and_publishes_status():
    ctrl, coord = controller()
    old = ctrl._session
    ctrl._worker.mode = 1
    ctrl.on_disconnect()
    assert ctrl._session is None
    assert ctrl._worker.mode == -1
    assert published(*coord.handle_controller_state_updates.call_args.args)["richmat_classic_status"] == "disconnected"
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable


async def test_real_coordinator_disconnect_keeps_latest_local_selector_owner(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    entry = MockConfigEntry(domain=DOMAIN, data={
        "address": "AA:BB:CC:DD:EE:66", "bed_type": "richmat_classic_apps",
        "protocol_variant": "avocadoecobase", "product_type": "YGRM",
    })
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    await coord.async_prime_offline_controller()
    old = coord.capability_controller
    assert isinstance(old, bed.RichmatClassicController)
    client = MagicMock(is_connected=True)
    coord._client = client
    live = bed.RichmatClassicController(coord)
    coord._controller = live
    await coord._async_restore_app_state(live)
    live._select("hold", "hold")
    expected = live.held_control_options
    assert expected
    coord._intentional_disconnect = True
    coord._on_disconnect(client)
    assert coord.capability_controller is live
    assert coord.capability_controller is not old
    assert coord.capability_controller.held_control_options == expected
    spec = next(s for s in live.controller_select_specs if s.key == "richmat_classic_hold")
    entity = AdjustableBedControllerSelect(coord, spec)
    await entity.async_select_option("release")
    assert live._selection.hold is False
    next_live = bed.RichmatClassicController(coord)
    coord._controller = next_live
    await coord._async_restore_app_state(next_live)
    assert next_live._selection.hold is False
    recall = next(c for c in next_live._controls if c.view_id == "btnM1")
    assert f"richmat_classic_{recall.node}_hold" not in next_live.held_control_options


async def test_native_release_entity_keeps_the_admitted_mode_through_cleanup(hass, monkeypatch):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.base import CONTROLLER_GESTURE_RELEASE
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={
        "address": "AA:BB:CC:DD:EE:66", "bed_type": "richmat_classic_apps",
        "protocol_variant": "avocadoecobase", "product_type": "ACRN",
    })
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = MagicMock(is_connected=True, disconnect=AsyncMock(), stop_notify=AsyncMock())
    ctrl = bed.RichmatClassicController(coord)
    coord._controller = ctrl
    coord._offline_controller = ctrl
    ctrl._session = Transport(coord.client, SimpleNamespace(uuid="write", properties=["write"]), SimpleNamespace(uuid="notify", properties=["notify"]), "FRAMED")
    first_write = asyncio.Event()

    async def write(_char, _packet, **_kwargs):
        first_write.set()

    coord._client.write_gatt_char = AsyncMock(side_effect=write)
    monkeypatch.setattr(coord, "async_ensure_connected", AsyncMock(return_value=True))
    monkeypatch.setattr(coord, "_async_refresh_controller_auth", AsyncMock())
    movement = ControllerActionButton(coord, next(s for s in ctrl.controller_button_specs if s.key == "richmat_classic_5"))
    release_button = ControllerActionButton(coord, next(s for s in ctrl.controller_button_specs if s.release_only))
    task = asyncio.create_task(movement.async_press())
    await first_write.wait()
    ctrl._select("mode", "1")
    await release_button.async_press()
    await task
    assert packets(coord) == ["6e01002493", "6e01006edd"]
    assert not CONTROLLER_GESTURE_RELEASE.get()
    coord._client.is_connected = False
    await coord.async_shutdown()
