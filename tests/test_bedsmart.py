"""BedSmart gesture selection, cancellation and physical ownership."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic import bedsmart, lp2
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.beds.richmat_classic.protocol import Worker
from custom_components.adjustable_bed.beds.richmat_classic.receive import ReceiveState
from custom_components.adjustable_bed.beds.richmat_classic.removed_layouts import REMOVED_LAYOUTS
from custom_components.adjustable_bed.profiles.bedsmart import (
    EXCLUDED_LAYOUTS,
    MODE_LABELS,
    scan_matches,
)
from tests.test_richmat_classic_transport import Services, route


def controller(layout="6BRM", wire="FRAMED"):
    co = MagicMock()
    co.cancel_command = asyncio.Event()
    co.connection_generation = co.cancel_counter = 0
    co.entry.options = {}
    co.address = "AA:BB:CC:DD:EE:71"
    co.entry.data = {
        "product_type": layout,
        "protocol_variant": "bedsmart",
        "motor_pulse_count": 1,
        "ble_device_name": "6BRM-bed",
    }
    co.client.is_connected = True
    co.client.write_gatt_char = AsyncMock()
    co.client.start_notify = AsyncMock()
    co.client.stop_notify = AsyncMock()
    ctrl = bedsmart.BedSmartController(co)
    co.controller = ctrl
    co.client.services = Services([route(2 if wire == "RAW" else 0)])
    from custom_components.adjustable_bed.beds.richmat_classic.transport import select

    ctrl._session = select(co.client)
    ctrl._scope = bedsmart.Scope(
        ctrl,
        ctrl._session,
        co.connection_generation,
        co.address,
        dict(co.entry.data),
        dict(co.entry.options),
        None,
        co.cancel_counter,
    )
    ctrl._wire = wire
    ctrl._worker = Worker(tick_ms=150)
    return ctrl, co


def packets(co):
    return [call.args[1].hex() for call in co.client.write_gatt_char.call_args_list]


@pytest.fixture
def clock(monkeypatch):
    delays, now = [], [0.0]
    real_sleep = asyncio.sleep
    monkeypatch.setattr(bedsmart, "monotonic", lambda: now[0])
    monkeypatch.setattr(lp2, "monotonic", lambda: now[0])
    monkeypatch.setattr(lp2.dt_util, "now", lambda: datetime(2026, 11, 20, 12, tzinfo=UTC))

    async def sleep(seconds):
        delays.append(round(seconds * 1000))
        now[0] += seconds
        await real_sleep(0)

    async def wait(milliseconds, cancel):
        if cancel.is_set():
            return False
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(bedsmart.asyncio, "sleep", sleep)
    monkeypatch.setattr(bedsmart.BedSmartController, "_wait", staticmethod(wait))
    return delays


@pytest.mark.parametrize(
    "wire,first,stop", [("RAW", "34", "6e"), ("FRAMED", "6e01002493", "6e01006edd")]
)
async def test_finite_motion_and_fresh_release(clock, wire, first, stop):
    c, co = controller(wire=wire)
    await c.execute_action(1, hold_ms=150)
    assert packets(co)[0] == first
    assert packets(co)[-1] == stop
    assert clock[-1] == 50
    assert c._worker.payload is None


@pytest.mark.parametrize("layout", MODE_LABELS)
async def test_mode_select_only_where_framed_commands_carry_it(clock, layout):
    c, co = controller(layout, "FRAMED")
    (selector,) = c.controller_select_specs
    side = MODE_LABELS[layout] == ("Left", "Right")
    assert selector.key == "bedsmart_mode"
    assert selector.translation_key == ("bedsmart_side" if side else "bedsmart_mode")
    assert selector.options == (
        ("left", "right") if side else tuple(f"mode_{i}" for i in (1, 2, 3))
    )
    assert selector.local_select_fn is not None
    selector.local_select_fn(selector.options[1])
    assert not packets(co)
    assert c.persisted_app_state["mode"] == 1
    gesture = next(g for g in c._gestures("FRAMED") if g.status == 1 and not g.saves)
    await c.execute_action(gesture.node, hold_ms=150)
    assert all(bytes.fromhex(p)[2] == 1 for p in packets(co))

    restored, _ = controller(layout, "FRAMED")
    restored.restore_persisted_app_state(c.persisted_app_state)
    restored._publish()
    assert restored._coordinator.handle_controller_state_updates.call_args_list[-1].args[
        -1
    ] == bedsmart.MODE(selector.options[1])

    raw, raw_co = controller(layout, "RAW")
    assert raw.controller_select_specs == ()
    raw._ui_mode = 1
    await raw.execute_action(gesture.node, hold_ms=150)
    assert all(len(bytes.fromhex(p)) == 1 for p in packets(raw_co))
    unknown, _ = controller(layout)
    unknown._session = unknown._scope = unknown._wire = None
    assert unknown.controller_select_specs == ()


async def test_cancelled_refresh_sends_original_release(clock):
    c, co = controller()

    async def cancel(*args, **kwargs):
        co.cancel_command.set()
        co.cancel_counter += 1

    co.client.write_gatt_char.side_effect = cancel
    await c.execute_action(1)
    assert packets(co) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize(
    "change", ["client", "generation", "controller", "address", "config", "options"]
)
async def test_no_frames_or_cleanup_cross_a_physical_fence(clock, change):
    c, co = controller()
    original = co.client
    replacement = MagicMock()
    replacement.is_connected = True
    replacement.write_gatt_char = AsyncMock()

    async def changed(*args, **kwargs):
        if change == "client":
            co.client = replacement
            c._session = replace(c._session, client=replacement)
        elif change == "generation":
            co.connection_generation += 1
        elif change == "controller":
            co.controller = object()
        elif change == "address":
            co.address = "different"
        elif change == "options":
            co.entry.options = {"motor_pulse_count": 10}
        else:
            co.entry.data = {**co.entry.data, "product_type": "DHRM"}

    original.write_gatt_char.side_effect = changed
    with pytest.raises(HomeAssistantError):
        await c.execute_action(1, hold_ms=450)
    assert original.write_gatt_char.await_count == (2 if change == "options" else 1)
    if change == "options":
        assert packets(co)[-1] == "6e01006edd"
    replacement.write_gatt_char.assert_not_awaited()


async def test_inflight_write_is_drained_before_cancellation_cleanup(clock):
    c, co = controller()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def delayed(char, frame, **kwargs):
        if frame == bytes.fromhex("6e01002493"):
            entered.set()
            await finish.wait()

    co.client.write_gatt_char.side_effect = delayed
    task = asyncio.create_task(c.execute_action(1))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert packets(co) == ["6e01002493"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert packets(co) == ["6e01002493", "6e01006edd"]


async def test_e3_recall_and_immediate_confirmed_save_are_distinct(clock):
    c, co = controller("E3RM")
    await c.execute_action(1, hold_ms=300)
    assert packets(co)[:2] == ["6e01002e9d"] * 2
    co.client.write_gatt_char.reset_mock()
    clock.clear()
    await c.execute_action(1, long=True)
    assert packets(co) == ["6e01002b9a", "6e01006edd"]
    assert clock == [50]
    assert all(not (s.requires_confirmation and s.hold) for s in c.controller_button_specs)


@pytest.mark.parametrize("long", [False, True])
async def test_app_local_preset_recall_and_save_use_their_own_layout(clock, long):
    c, co = controller("A0RM")
    node = next(b.node for b in c._controls if b.short == "58" and b.status == 3)
    await c.execute_action(node, long=long)
    assert packets(co) == ["6e010064d3" if long else "6e010058c7", "6e01006edd"]


# Captured from the head or foot select's default (Head) on v5 c623aa8d9.
_GVRM_HEAD = {
    "RAW": {
        2: (["37", "6e"], [150, 50]),
        4: (["31", "6e"], [150, 50]),
        5: (["35", "6e"], [50]),
        8: (["32", "6e"], [150, 50]),
        9: (["38", "6e"], [150, 50]),
    },
    "FRAMED": {
        2: (["6e010037a6", "6e01006edd"], [150, 50]),
        4: (["6e010031a0", "6e01006edd"], [150, 50]),
        5: (["6e010035a4", "6e01006edd"], [50]),
        8: (["6e010032a1", "6e01006edd"], [150, 50]),
        9: (["6e010038a7", "6e01006edd"], [150, 50]),
    },
}


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_gvrm_head_or_foot_buttons_send_their_head_command(clock, wire):
    c, co = controller("GVRM", wire)
    assert c.controller_select_specs == ()
    sent = {}
    for b in c._controls:
        if b.tag == "63":
            co.client.write_gatt_char.reset_mock()
            clock.clear()
            spec = next(
                s for s in c.controller_button_specs if s.key == f"richmat_classic_{b.node}"
            )
            await spec.press_fn(c)
            sent[b.node] = (packets(co), list(clock))
    assert sent == _GVRM_HEAD[wire]
    # The app's foot choice has no command for these buttons.
    node = next(b.node for b in c._controls if b.tag == "63")
    with pytest.raises(ValueError, match="no command"):
        c._gesture(node, wire, head=False)


# Captured from the selected-motor select plus button on v5 c623aa8d9.
_U3RM_MOTORS = {
    ("RAW", 3): (["3f", "6e"], ["40", "6e"]),
    ("RAW", 4): (["41", "6e"], ["42", "6e"]),
    ("RAW", 5): (["71", "6e"], ["72", "6e"]),
    ("FRAMED", 3): (
        ["6e01003fae", "6e01006edd"],
        ["6e010040af", "6e01006edd"],
    ),
    ("FRAMED", 4): (
        ["6e010041b0", "6e01006edd"],
        ["6e010042b1", "6e01006edd"],
    ),
    ("FRAMED", 5): (
        ["6e010071e0", "6e01006edd"],
        ["6e010072e1", "6e01006edd"],
    ),
}


@pytest.mark.parametrize(("wire", "motor"), list(_U3RM_MOTORS))
async def test_u3_motor_buttons_send_what_the_motor_selector_sent(clock, wire, motor):
    c, co = controller("U3RM", wire)
    assert c.controller_select_specs == ()
    specs = {s.key: s for s in c.controller_button_specs}
    sent = []
    for tag, direction in (("51", "up"), ("52", "down")):
        node = next(b.node for b in c._controls if b.tag == tag)
        key = f"richmat_classic_{node}" + ("" if motor == 3 else f"_motor{motor}")
        assert specs[key].name == f"Motor {motor} {direction}"
        assert specs[key].hold is not None
        co.client.write_gatt_char.reset_mock()
        clock.clear()
        await specs[key].press_fn(c)
        assert clock == [150, 50]
        sent.append(packets(co))
    assert tuple(sent) == _U3RM_MOTORS[(wire, motor)]
    assert not any(s.name.startswith("Selected motor") for s in specs.values())


async def test_session_start_query_and_capabilities_are_separate(clock):
    c, co = controller("D1RM")
    co.client.services = Services([route(0)])
    await c.start_notify()
    assert packets(co) == ["6e02010071"]
    assert clock == [300]
    co.client.write_gatt_char.reset_mock()
    await c.query_settings()
    assert packets(co) == ["6e0a000179", "6e1a000088"]
    assert not c._receive.light_capable
    session = c._session
    c._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    assert c._receive.light_capable
    assert any(s.key == "bedsmart_lamp_seconds" for s in c.controller_number_specs)
    await c.settings(seconds=300)
    assert packets(co)[-1] == "6e0b012ca6"
    c.on_disconnect()
    c._notification(session, session.notify, bytearray.fromhex("6e1a000189"))
    assert not c._receive.aroma_capable


@pytest.mark.parametrize(
    "chunks,alarm,light",
    [
        (["6e0901", "0078"], True, False),
        (["6e090100786e0e00037f"], True, False),
        (["6e090100786e", "0e00037f"], True, True),
    ],
)
def test_parser_fragmentation_and_app_buffer_rules(chunks, alarm, light):
    state = ReceiveState()
    for chunk in chunks:
        state.feed(
            bytes.fromhex(chunk),
            app="bedsmart",
            layout="6BRM",
            desk_bound=False,
            table_controls_bound=False,
        )
    assert state.alarm_capable is alarm
    assert state.light_capable is light
    assert state.height_cm is None


def test_all_layouts_expose_only_supported_source_gestures():
    catalog = load_catalog("bedsmart")
    assert len(catalog.models) == 558
    for layout in catalog.models.keys() - EXCLUDED_LAYOUTS - REMOVED_LAYOUTS:
        c, _ = controller(layout)
        assert c.alarm_capability is not None or not c._alarm_actions()
        assert all(not (s.requires_confirmation and s.hold) for s in c.controller_button_specs)
        assert not c.supports_single_address_pairing
        assert not any(
            "reset" in s.name.lower() or "music" in s.name.lower()
            for s in c.controller_button_specs
        )
    for layout in EXCLUDED_LAYOUTS - REMOVED_LAYOUTS:
        with pytest.raises(HomeAssistantError):
            controller(layout)
    for layout in REMOVED_LAYOUTS:
        with pytest.raises(ValueError, match="factory test"):
            controller(layout)


def test_discovery_alias_precedence_and_manual_reachability():
    assert scan_matches("MPE_HJ006-1-bed")
    assert resolve_layout("bedsmart", "MPE_HJ006-1-bed", from_name=True) == "BNRM"
    assert resolve_layout("bedsmart", "B6RU") == "B6RM"
    assert not scan_matches("B6RU")
    assert not scan_matches("L&P ADJBED")
    assert resolve_layout("bedsmart", "OTRM", russian=True) == "O0RM"


async def test_shared_alarm_combination_uses_only_layout_owned_options(clock):
    c, co = controller("A9RM")
    cap = c.alarm_capability
    request = AlarmRequest(
        enabled=True,
        wake_action=cap.wake_actions[0],
        reference_time=datetime(2026, 11, 20, 12, tzinfo=UTC),
        hour=12,
    )
    await c.configure_alarm(request)
    assert len(packets(co)) == 2
    assert packets(co)[0].startswith("6e05")
    assert clock[-2:] == [300, 300]


async def test_earlier_selector_state_restores_without_changing_any_command(clock):
    c, co = controller("U3RM", "RAW")
    # Stored by earlier betas; each motor now has its own button.
    c.restore_persisted_app_state({"mode": 0, "axis": "55", "head": False, "wire": "RAW"})
    assert c.persisted_app_state == {
        "mode": 0,
        "known_light": False,
        "known_aroma": False,
        "wire": "RAW",
    }
    node = next(b.node for b in c._controls if b.tag == "51")
    await next(s for s in c.controller_button_specs if s.key == f"richmat_classic_{node}").press_fn(
        c
    )
    assert packets(co) == ["3f", "6e"]


@pytest.mark.parametrize("zone,code", [("both", 0xA9), ("head", 0xAA), ("feet", 0xAB)])
async def test_memory_three_alarm_combines_with_layout_massage(clock, zone, code):
    c, co = controller("YPRM")
    request = AlarmRequest(
        enabled=True,
        hour=12,
        wake_action="memory_3",
        massage=True,
        massage_zone=zone,
        reference_time=datetime(2026, 11, 20, 12, tzinfo=UTC),
    )
    await c.configure_alarm(request)
    assert bytes.fromhex(packets(co)[1])[3] == code


async def test_y6_native_timer_off_uses_popup_frame(clock):
    c, co = controller("Y6RM", "RAW")
    assert c.massage_timer_can_turn_off
    await c.set_massage_timer(0)
    assert packets(co) == ["6e01005ecd"]


async def test_configuration_changed_before_operation_rejects_cached_catalog(clock):
    c, co = controller()
    co.entry.data = {**co.entry.data, "product_type": "DHRM"}
    with pytest.raises(HomeAssistantError):
        await c.execute_action(1)
    assert not packets(co)


async def test_discovered_specs_survive_reconnect_but_require_new_capability_proof(clock):
    c, co = controller()
    co.client.services = Services([route(0)])
    await c.start_notify()
    session = c._session
    c._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    c._notification(session, session.notify, bytearray.fromhex("6e1a000189"))
    old_state = c.persisted_app_state
    c.on_disconnect()
    restored, restored_co = controller()
    restored.restore_persisted_app_state(old_state)
    assert {s.key for s in restored.controller_number_specs} >= {
        "bedsmart_lamp_seconds",
        "bedsmart_aroma_0",
    }
    assert not restored._receive.light_capable
    restored_co.client.services = Services([route(0)])
    await restored.start_notify()

    async def response(_char, frame, **kwargs):
        replies = {"6e0a000179": "6e0e00037f", "6e1a000088": "6e1a000189"}
        if frame.hex() in replies:
            link = restored._session
            restored._notification(link, link.notify, bytearray.fromhex(replies[frame.hex()]))

    restored_co.client.write_gatt_char.reset_mock()
    restored_co.client.write_gatt_char.side_effect = response
    await restored.settings(seconds=60)
    assert packets(restored_co) == ["6e0a000179", "6e1a000088", "6e0b003cb5"]


async def test_remembered_feature_is_not_fresh_write_permission(clock):
    c, co = controller()
    c.restore_persisted_app_state({"known_light": True})
    c._feature_event.wait = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(HomeAssistantError):
        await c.settings(seconds=60)
    assert packets(co) == ["6e0a000179", "6e1a000088"]


async def test_stop_and_cleanup_survive_timing_change_but_new_actions_do_not(clock):
    c, co = controller()

    async def configure_during_movement(_char, frame, **kwargs):
        if frame == bytes.fromhex("6e01002493"):
            co.entry.data = {**co.entry.data, "idle_disconnect_seconds": 20}
            co.cancel_command.set()

    co.client.write_gatt_char.side_effect = configure_during_movement
    await c.execute_action(1, hold_ms=600)
    assert packets(co) == ["6e01002493", "6e01006edd"]
    co.cancel_command.clear()
    await c.stop_all()
    assert packets(co)[-1] == "6e01006edd"
    with pytest.raises(HomeAssistantError):
        await c.execute_action(1)
    assert len(packets(co)) == 3


@pytest.mark.parametrize(
    "change", ["catalog", "address", "client", "generation", "owner", "gatt_route", "side"]
)
async def test_explicit_stop_never_crosses_a_retired_physical_route(clock, change):
    c, co = controller()
    if change == "catalog":
        co.entry.data = {**co.entry.data, "product_type": "DHRM"}
    elif change == "address":
        co.entry.data = {**co.entry.data, "address": "new-address"}
    elif change == "client":
        co.client = MagicMock()
    elif change == "generation":
        co.connection_generation += 1
    elif change == "owner":
        co.controller = object()
    elif change == "gatt_route":
        co.client.services = Services([route(2)])
    else:
        # An operation's native side remains pinned while the STOP waits.
        with c._transaction():
            token = c._command_side.set("right")
            try:
                await c.stop_all()
            finally:
                c._command_side.reset(token)
        assert not packets(co)
        return
    with pytest.raises(HomeAssistantError):
        await c.stop_all()
    assert not packets(co)
