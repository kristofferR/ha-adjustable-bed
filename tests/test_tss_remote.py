"""TSS Remote's frozen route membership and usable HA command surfaces."""

import asyncio
import gzip
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.richmat_classic import dreamlab as shared
from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.discovery import matching_apps
from custom_components.adjustable_bed.beds.richmat_classic.receive import MalformedFrame
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.beds.richmat_classic.transport import ROUTES, Transport
from custom_components.adjustable_bed.beds.richmat_classic.tss_remote import (
    TssReceiveState,
    TssRemoteController,
)
from custom_components.adjustable_bed.profiles import tss_remote as app
from custom_components.adjustable_bed.setup_questions import setup_profile

FIXTURES = Path(__file__).parent / "fixtures/tss_remote"


def fixture(name):
    path = FIXTURES / (name + ".json")
    return json.loads(
        path.read_text()
        if path.exists()
        else gzip.decompress(path.with_suffix(".json.gz").read_bytes())
    )


def controller(layout="6BRM", wire="FRAMED"):
    coord = MagicMock()
    coord.cancel_command = asyncio.Event()
    coord.entry.data = {
        "protocol_variant": app.APP,
        "product_type": layout,
        "motor_pulse_count": 2,
        "ble_device_name": layout + "-bed",
    }
    coord.client.is_connected = True
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    ctrl = TssRemoteController(coord)
    coord.controller = ctrl
    ctrl._session = Transport(
        coord.client,
        SimpleNamespace(uuid="write", properties=["write"], handle=1),
        SimpleNamespace(uuid="notify", properties=["notify"], handle=2),
        wire,
    )
    ctrl._wire = wire
    return ctrl, coord


def packets(coord):
    return [call.args[1].hex() for call in coord.client.write_gatt_char.await_args_list]


@pytest.fixture(autouse=True)
def clock(monkeypatch, request):
    if "real_wire_clock" in request.fixturenames:
        return None
    now = [0.0]
    original = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original(0)

    async def wait(milliseconds, cancel):
        if cancel.is_set():
            return False
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(shared, "monotonic", lambda: now[0])
    monkeypatch.setattr(shared.asyncio, "sleep", sleep)
    monkeypatch.setattr(TssRemoteController, "_wait", staticmethod(wait))
    return now


@pytest.mark.parametrize("vector", fixture("literal-vectors"), ids=lambda v: v["id"])
def test_all_frozen_literals_select_the_existing_codec(vector):
    inputs = vector["inputs"]
    if "vendor" in inputs:
        actual = p.control(
            bytes.fromhex(inputs["payload"]),
            "RAW" if inputs["vendor"] == "NORDIC" else "FRAMED",
            inputs.get("mode", 0),
        )
    elif "direct_prefix" in inputs:
        prefix = bytes.fromhex(inputs["direct_prefix"])
        actual = p.direct(*prefix[1:])
    elif "rgb" in inputs:
        actual = p.rgb(*inputs["rgb"])
    elif "minutes" in inputs:
        actual = b"".join(p.alarm(inputs["minutes"], inputs["action"]))
    else:
        parser = TssReceiveState()
        parser.feed(bytes.fromhex(inputs["notification"]), app=app.APP, layout="A0RM")
        actual = bytes.fromhex(parser.value_event)
    assert actual.hex() == vector["expected_bytes"]


def test_every_route_action_matches_the_frozen_membership_in_both_directions():
    expected = set()
    for row in fixture("command-table"):
        wire = "RAW" if row["vendor"] == "NORDIC" else "FRAMED"
        for appearance in row["appearances"]:
            expected.add(
                (
                    appearance["variant"].upper(),
                    appearance["element"],
                    row["context"],
                    row["state"],
                    wire,
                    row["event"] == "LONG_THRESHOLD",
                    row["selected_payload_hex"].lower(),
                    row["mode_zero_literal"].lower(),
                )
            )
    actual = set()
    for layout in app.LAYOUTS:
        ctrl, _ = controller(layout)
        for button in ctrl._controls:
            contexts = [("initial", Selection())]
            if button.mem_special:
                contexts = [
                    ("memory_disarmed", Selection()),
                    ("memory_armed", Selection(armed=True)),
                ]
            elif button.hold_affected:
                contexts += (
                    [("visible_after_hold", Selection(hold=True))]
                    if button.view_id.endswith("Long")
                    else [("release", Selection(hold=False)), ("hold", Selection(hold=True))]
                )
            states = [("normal", Selection())]
            if button.tag in ("51", "52"):
                states = [
                    ("pressFlag=" + flag, Selection(press_flag=flag))
                    for flag in ("53", "54", "55", "other")
                ]
            elif button.tag == "63":
                states = [("head_selected", Selection()), ("foot_selected", Selection(head=False))]
            for context, selection in contexts:
                for state, values in states:
                    selection = replace(selection, press_flag=values.press_flag, head=values.head)
                    for wire in ("RAW", "FRAMED"):
                        for long in (False, True):
                            if button.mem_special and long != selection.armed:
                                continue
                            plan = ctrl._gesture(button, wire, selection, long=long)
                            if plan is not None:
                                actual.add(
                                    (
                                        layout,
                                        button.node,
                                        context,
                                        state,
                                        wire,
                                        long,
                                        plan.payload.hex(),
                                        p.control(plan.payload, wire).hex(),
                                    )
                                )
    missing, extra = expected - actual, actual - expected
    assert not missing, sorted(missing)[:30]
    assert not extra, sorted(extra)[:30]


@pytest.mark.parametrize("index", range(4))
async def test_real_named_gatt_route_startup_and_movement(index, clock):
    ctrl, coord = controller()
    ctrl._session = ctrl._wire = None
    uuid, tx, rx, wire = ROUTES[index]
    send = SimpleNamespace(uuid=tx, properties=["write-without-response"], handle=1)
    notify = SimpleNamespace(uuid=rx, properties=["notify"], handle=2)
    service = SimpleNamespace(get_characteristic={tx: send, rx: notify}.get)
    coord.client.services.get_service.side_effect = {uuid: service}.get
    await ctrl.start_notify()
    assert isinstance(ctrl._receive, TssReceiveState)
    assert packets(coord) == (["6e02010071"] if wire == "FRAMED" else []) + ["6e0a000179"]
    coord.client.write_gatt_char.reset_mock()
    await ctrl.execute_action(1, hold_ms=1)
    assert packets(coord) == (["34", "6e"] if wire == "RAW" else ["6e01002493", "6e01006edd"])
    assert all(
        call.kwargs["response"] is False for call in coord.client.write_gatt_char.await_args_list
    )


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize(("layout", "node"), [("FGRM", 1), ("FMRM", 2), ("FNRM", 5)])
async def test_mixed_lock_is_usable_without_ever_sending_short_audio(layout, node, wire, clock):
    ctrl, coord = controller(layout, wire)
    specs = [s for s in ctrl.controller_button_specs if s.key == f"tss_{node}_long"]
    assert len(specs) == 1 and specs[0].hold is None and specs[0].requires_confirmation
    assert not any(s.key == f"tss_{node}" for s in ctrl.controller_button_specs)
    await specs[0].press_fn(ctrl)
    assert packets(coord) == (["84", "6e"] if wire == "RAW" else ["6e010084f3", "6e01006edd"])
    assert clock[0] == pytest.approx(4.95 + 0.15)
    with pytest.raises(ServiceValidationError):
        await ctrl.execute_action(node)


@pytest.mark.parametrize(
    ("chunks", "events", "buffer"),
    [
        (["6e0e", "00017d"], ["6e0e00017d"], ""),
        (["6e090100786e"], ["6e09010078"], "6e"),
        (["6e090100786e0e00017d"], ["6e09010078"], ""),
        (["6e090100786e5e"], [], ""),
    ],
)
def test_parser_preserves_fragment_and_length_first_boundaries(chunks, events, buffer):
    parser = TssReceiveState()
    seen = []
    for chunk in chunks:
        parser.feed(bytes.fromhex(chunk), app=app.APP, layout="A0RM")
        if parser.value_event:
            seen.append(parser.value_event)
    assert seen == events and parser.buffer == buffer


def test_parser_rejects_bad_checksum_and_excluded_companion():
    parser = TssReceiveState()
    with pytest.raises(MalformedFrame):
        parser.feed(bytes.fromhex("6e09010079"), app=app.APP, layout="A0RM")
    parser = TssReceiveState()
    parser.feed(bytes.fromhex("6e1a000189"), app=app.APP, layout="A0RM")
    assert not parser.aroma_capable and "aroma" not in parser.menu


def test_findable_app_setup_layouts_and_conservative_discovery():
    profile = setup_profile("richmat_classic_apps")
    choose_layout = profile.questions[0].choices
    assert callable(choose_layout)
    choices = choose_layout({"protocol_variant": app.APP})
    assert "FGRM" in choices and "WFRM" not in choices and "BSRM" not in choices
    assert "ZRS0:B8TT" in choices and "ZRS0" not in choices
    assert app.layout_from_name("200IV2-bed") == "A8RM"
    assert app.layout_from_name("209A05") is None
    assert app.layout_from_name("COOL TOUCH") is None
    assert app.APP not in matching_apps("6BRM")
    assert app.APP in matching_apps("6BRM", (ROUTES[0][0],))
    assert app.APP not in matching_apps("unrelated", (ROUTES[0][0],))


async def test_invalid_settings_and_side_selection_cannot_send():
    ctrl, coord = controller("FNRM")
    assert not ctrl.supports_single_address_pairing
    with ctrl.side_scope("right"), pytest.raises(ServiceValidationError):
        await ctrl.execute_action(6)
    for req in (Request("aroma", aroma_values=(1, 1, 1)), Request("rgb", color=(-1, 0, 0))):
        with pytest.raises(ServiceValidationError):
            ctrl.validate_richmat_classic_request(req)
    assert not packets(coord)


async def test_old_session_cleanup_and_callbacks_cannot_touch_replacement():
    ctrl, coord = controller("FGRM")
    old = ctrl._session
    with ctrl._transaction():
        ctrl.on_disconnect()
        ctrl._session = replace(old)
        await ctrl._release()
        with pytest.raises(ConnectionError, match="captured"):
            await ctrl._send(bytes.fromhex("6e010084f3"))
    ctrl._notification(old, old.notify, bytearray.fromhex("6e09010078"))
    assert not ctrl._receive.alarm_capable
    assert packets(coord) == []


async def test_cancelled_long_gesture_never_saves_or_locks(monkeypatch):
    ctrl, coord = controller("FGRM")

    async def stop_before_threshold(milliseconds, cancel):
        cancel.set()
        return False

    monkeypatch.setattr(ctrl, "_wait", stop_before_threshold)
    await ctrl.execute_action(1, long=True)
    assert packets(coord) == ["6e01006edd"]


@pytest.mark.parametrize(
    ("layout", "options", "off"),
    [
        ("D1RM", [120, 180, 300], "6e01005ecd"),
        ("D9RM", [120, 180, 300], "6e01008bfa"),
        ("Y6RM", [15, 30, 45], None),
    ],
)
async def test_layout_timers_have_the_actual_labels_not_sibling_durations(layout, options, off):
    ctrl, coord = controller(layout, "RAW")
    assert ctrl.massage_timer_options == options
    for minutes in ([0] if off else []) + options:
        await ctrl.set_massage_timer(minutes)
    assert packets(coord) == ([off] if off else []) + ["6e01005fce", "6e010063d2", "6e010061d0"]
    with pytest.raises(ServiceValidationError):
        await ctrl.set_massage_timer(10)


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_release_hold_mode_gates_confirmed_save_entities(wire):
    from custom_components.adjustable_bed.button import ControllerActionButton

    ctrl, coord = controller("YFRM", wire)
    coord.capability_controller = ctrl
    coord.controller_side = coord.entity_side = None
    specs = {s.key: s for s in ctrl.controller_button_specs}
    memory = ControllerActionButton(coord, specs["tss_8"])
    save = ControllerActionButton(coord, specs["tss_10"])
    assert memory.available and not save.available
    assert "held_control" not in memory.extra_state_attributes
    choose = next(s for s in ctrl.controller_select_specs if s.key == "dreamlab_press_mode")
    await choose.select_fn(ctrl, "hold")
    assert memory.available and save.available
    assert memory.extra_state_attributes["hold_lease_mode"] == "stream"
    assert save.extra_state_attributes["requires_confirmation"]
    assert "held_control" not in save.extra_state_attributes
    await specs["tss_10"].press_fn(ctrl)
    expected = (
        ["22", "6e", "2b", "6e"]
        if wire == "RAW"
        else ["6e01002291", "6e01006edd", "6e01002b9a", "6e01006edd"]
    )
    assert packets(coord) == expected


async def test_switch_pairs_use_one_shared_entity_and_keep_exact_frames():
    ctrl, coord = controller("E3RM")
    sync = next(spec for spec in ctrl.controller_switch_specs if spec.key == "tss_synchronization")
    for enabled in (True, False):
        await sync.set_fn(ctrl, enabled)
    assert packets(coord) == ["6e0100bc2b", "6e01006edd", "6e0100bd2c", "6e01006edd"]
    assert sync.assumed_state
    assert all(
        spec.name not in ("Synchronization on", "Synchronization off")
        for spec in ctrl.controller_button_specs
    )


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_real_factory_entity_command_lane_and_generic_alarm_action(
    hass, mock_bleak_client, monkeypatch
):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services
    from tests.conftest import TEST_ADDRESS

    entry = MockConfigEntry(
        domain="adjustable_bed",
        data={
            "address": TEST_ADDRESS,
            "name": "Bedroom",
            "bed_type": "richmat_classic_apps",
            "profile_id": "richmat_classic_apps:tss_remote",
            "protocol_variant": app.APP,
            "product_type": "FDRM",
            "ble_device_name": "FDRM-bed",
            "motor_pulse_count": 2,
        },
    )
    entry.add_to_hass(hass)
    uuid, tx, rx, _ = ROUTES[0]
    send = SimpleNamespace(uuid=tx, properties=["write"], handle=1)
    notify = SimpleNamespace(uuid=rx, properties=["notify"], handle=2)
    service = SimpleNamespace(get_characteristic={tx: send, rx: notify}.get)
    mock_bleak_client.services.get_service.side_effect = {uuid: service}.get
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    coord = AdjustableBedCoordinator(hass, entry)
    try:
        assert await coord.async_connect()
        ctrl = coord.controller
        assert isinstance(ctrl, TssRemoteController) and ctrl.app == app.APP
        mock_bleak_client.write_gatt_char.reset_mock()
        spec = next(s for s in ctrl.controller_button_specs if s.name == "TV")
        await ControllerActionButton(coord, spec).async_press()
        assert [c.args[1].hex() for c in mock_bleak_client.write_gatt_char.await_args_list] == [
            "6e010058c7",
            "6e01006edd",
        ]
        await async_register_services(hass)
        monkeypatch.setattr(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            lambda *_a, **_k: ([(coord, "both")], []),
        )
        alarm = {
            "device_id": "bed",
            "enabled": True,
            "time": f"{(dt_util.now().hour + 1) % 24:02d}:{dt_util.now().minute:02d}:00",
            "wake_action": "tv",
        }
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call("adjustable_bed", "set_alarm", alarm, blocking=True)
        ctrl._notification(ctrl._session, notify, bytearray.fromhex("6e09010078"))
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call("adjustable_bed", "set_alarm", alarm, blocking=True)
        assert [c.args[1].hex() for c in mock_bleak_client.write_gatt_char.await_args_list] == [
            "6e053c00af",
            "6e060058cc",
        ]
    finally:
        await coord.async_shutdown()


@pytest.fixture
def real_wire_clock():
    """Leased-wire tests use the full virtual scheduler clock."""


@pytest.mark.parametrize("route", ["w1", "n1"])
async def test_card_lease_refresh_and_stop_cleanup(route, real_wire_clock):
    from tests.hold_lease_wire import intervals, leased_hold

    async def move(ctrl):
        spec = next(s for s in ctrl.controller_button_specs if s.name == "Pillow up")
        assert spec.hold is not None
        await ctrl.hold_control(spec.hold.control, 30000)

    wire = await leased_hold(
        "richmat_classic_apps:tss_remote:ZIRM:" + route, move, end_after_s=0.8, end="stop"
    )
    assert {w.data.hex() for w in wire.held} == {"3f" if route == "n1" else "6e01003fae"}
    assert len(wire.held) > 2
    assert all(delta >= (170 if route == "n1" else 110) for delta in intervals(wire.held))
    assert wire.after and all(
        w.data.hex() == ("6e" if route == "n1" else "6e01006edd") for w in wire.after
    )


def test_fixed_helpers_reproduce_every_frozen_literal():
    for row in fixture("fixed-command-table"):
        identity = row["id"]
        if identity.startswith("F-TIMER-"):
            _, _, layout, progress = identity.split("-")
            assert p.massage_timer(layout.upper(), int(progress)).hex() == row["bytes"]
        elif identity.startswith("F-POPUP-"):
            assert (
                p.control(bytes.fromhex(identity.removeprefix("F-POPUP-")), "FRAMED").hex()
                == row["bytes"]
            )
        elif identity in ("F-INIT", "F-QUERY-ALARM", "F-QUERY-LIGHT"):
            actual = {
                "F-INIT": p.INITIALIZE,
                "F-QUERY-ALARM": p.ALARM_QUERY,
                "F-QUERY-LIGHT": p.LAMP_QUERY,
            }[identity]
            assert actual.hex() == row["bytes"]
        elif identity == "F-END-NORDIC":
            assert p.release("RAW").hex() == row["bytes"]
        elif identity == "F-ALARM-CANCEL":
            assert " then ".join(frame.hex() for frame in p.alarm(0, 0)) == row["bytes"]
    # Callback values without a duration label are kept in the encoder, never
    # promoted into guessed timer options.
    assert p.massage_timer("D1RM", 1).hex() == "6e01000170"
    assert p.massage_timer("D9RM", 4).hex() == "6e01000473"


async def test_read_only_third_service_is_explicit_fresh_and_raw():
    from custom_components.adjustable_bed.const import CONF_RICHMAT_CLASSIC_THIRD_SERVICE

    ctrl, coord = controller("FGRM")
    coord.client.services.get_service.return_value = None
    tx = SimpleNamespace(uuid="fallback-write", properties=["write-without-response"], handle=3)
    rx = SimpleNamespace(uuid="fallback-read", properties=["read"], handle=4)
    coord.client.services.__iter__.return_value = [
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(characteristics=[tx, rx]),
    ]
    with pytest.raises(ConnectionError):
        await ctrl.start_notify()
    coord.entry.data[CONF_RICHMAT_CLASSIC_THIRD_SERVICE] = True
    await ctrl.start_notify()
    assert ctrl._session.write is tx and ctrl._session.wire == "RAW"
    await ctrl.execute_action(1, long=True)
    assert packets(coord) == ["84", "6e"]


async def test_live_lighting_entities_gate_after_reconnect_and_keep_exact_frames():
    ctrl, coord = controller("D1RM")
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00017d"))
    assert ctrl.supports_light_state_feedback and ctrl.supports_light_color_control
    await ctrl.lights_on()
    assert packets(coord) == ["6e01003cab", "6e01006edd", "6e0a000179"]
    with pytest.raises(ServiceValidationError):
        await ctrl.lights_off()
    await ctrl.set_light_color((0, 255, 0))
    timeout = ctrl.controller_number_specs[0]
    await timeout.set_fn(ctrl, 300)
    assert packets(coord)[-2:] == ["6e0cff00796e0dff007a", "6e0b012ca6"]
    old = ctrl._session
    snapshot = ctrl.capability_snapshot()
    ctrl.on_disconnect()
    ctrl._session = replace(old)
    with pytest.raises(ServiceValidationError):
        await ctrl.set_light_color((0, 255, 0))
    assert snapshot == {"app": app.APP, "layout": "D1RM", "light": True}


async def test_mode_is_source_numbered_and_captured_through_end():
    ctrl, coord = controller("BTRM")
    mode = next(s for s in ctrl.controller_select_specs if s.key == "dreamlab_mode")
    assert mode.options == ("0", "1", "2")
    assert mode.local_select_fn is not None
    select_mode = mode.local_select_fn
    select_mode("1")
    button = next(b for b in ctrl._controls if b.short == "24")

    async def change_mode(_characteristic, _data, **_kwargs):
        select_mode("2")

    coord.client.write_gatt_char.side_effect = change_mode
    await ctrl.execute_action(button.node, hold_ms=1)
    assert packets(coord) == ["6e01012494", "6e01016ede"]
    assert not ctrl.supports_single_address_pairing


async def test_alarm_presence_without_named_presets_is_cancel_only():
    from homeassistant.util import dt as dt_util

    from custom_components.adjustable_bed.alarm import AlarmRequest

    ctrl, coord = controller("6BRM")
    assert ctrl.alarm_capability is None
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e09010078"))
    assert ctrl.alarm_capability is not None and ctrl.alarm_capability.wake_actions == ()
    await ctrl.configure_alarm(AlarmRequest(enabled=False, reference_time=dt_util.now()))
    assert packets(coord) == ["6e05000073", "6e06000074"]
    with pytest.raises(ServiceValidationError):
        await ctrl.configure_alarm(AlarmRequest(enabled=True, hour=8, reference_time=dt_util.now()))
    assert len(packets(coord)) == 2


def test_app_connection_traits_are_owned_and_do_not_change_siblings():
    from custom_components.adjustable_bed.bed_traits import bed_traits

    traits = bed_traits("richmat_classic_apps", app.APP)
    assert traits.connection_timeout == app.CONNECTION_TIMEOUT_S == 10
    assert traits.connection_scoped_state and traits.owns_device_info_reads
    assert not traits.single_address_native_both and traits.no_angle_feedback
    assert bed_traits("richmat_classic_apps", "dreamlab2").connection_timeout is None
    assert bed_traits("richmat_classic_apps", "avocadoecobase").connection_timeout is None


def connected_tss(hass, layout, address="AA:BB:CC:DD:EE:60"):
    from tests.test_maxprime import connected_profile

    return connected_profile(hass, layout, address, app.APP, TssRemoteController, release=False)


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize(
    ("layout", "node", "label", "operand", "held"), fixture("public-appearances")["controls"]
)
async def test_proven_appearance_reaches_public_entity(
    hass, layout, node, label, operand, held, wire
):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = connected_tss(hass, layout)
    coord.client.services = Services([route(2 if wire == "RAW" else 0)])
    try:
        await ctrl.start_notify()
        hass.config_entries.async_update_entry(
            coord.entry, data={**coord.entry.data, "motor_pulse_count": 2}
        )
        coord.client.write_gatt_char.reset_mock()
        spec = next(s for s in ctrl.controller_button_specs if s.key == f"tss_{node}")
        assert spec.name == label
        assert (spec.hold is not None) is held
        entity = ControllerActionButton(coord, spec)
        assert entity.available
        await entity.async_press()
        expected = (
            operand
            if wire == "RAW"
            else "6e0100" + operand + f"{(0x6F + int(operand, 16)) & 255:02x}"
        )
        assert packets(coord) == [expected] * (2 if held else 1) + [
            "6e" if wire == "RAW" else "6e01006edd"
        ]
        assert not ctrl.supports_single_address_pairing
    finally:
        await coord.async_shutdown()


@pytest.mark.parametrize(
    ("layout", "node", "label", "operand"), fixture("public-appearances")["timers"]
    + [("BGRM", 22, "Massage timer 10 minutes", "a1"),
       ("BGRM", 23, "Massage timer 20 minutes", "a2"),
       ("BGRM", 24, "Massage timer 30 minutes", "a3")]
)
@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_visible_duration_names_the_public_timer_action(hass, layout, node, label, operand, wire):
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = connected_tss(hass, layout)
    coord.client.services = Services([route(2 if wire == "RAW" else 0)])
    try:
        await ctrl.start_notify()
        coord.client.write_gatt_char.reset_mock()
        assert ctrl._action_name(ctrl._button(node), long=False, raw=wire == "RAW") == label
        assert not any(s.key == f"tss_{node}" for s in ctrl.controller_button_specs)
        assert ctrl.supports_massage_timer and not ctrl.massage_timer_can_turn_off
        entity = AdjustableBedMassageTimerSelect(coord, MASSAGE_TIMER_DESCRIPTION, ctrl.massage_timer_options, has_off=False)
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
        assert entity.assumed_state is True
        minutes = app.FIXED_MASSAGE_DURATIONS[label]
        option = f"{minutes} min"
        assert option in entity.options and "Off" not in entity.options
        await entity.async_select_option(option)
        assert entity.current_option == option
        expected = operand if wire == "RAW" else "6e0100" + operand + f"{(0x6F + int(operand, 16)) & 255:02x}"
        assert packets(coord) == [expected, "6e" if wire == "RAW" else "6e01006edd"]
        if layout == "APRM":
            assert any(s.key == "tss_23" for s in ctrl.controller_button_specs)
    finally:
        await coord.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize(
    ("layout", "node", "threshold"), fixture("public-appearances")["long_lights"]
)
async def test_shared_light_preserves_short_toggle_and_distinct_long_off(
    hass, layout, node, threshold, wire, clock
):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = connected_tss(hass, layout)
    coord.client.services = Services([route(2 if wire == "RAW" else 0)])
    try:
        await ctrl.start_notify()
        ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00017d"))
        assert ctrl.supports_light_state_feedback and ctrl.supports_light_color_control
        assert not any(s.key == f"tss_{node}" for s in ctrl.controller_button_specs)
        long = next(s for s in ctrl.controller_button_specs if s.key == f"tss_{node}_long")
        assert long.hold is None and ctrl.controller_button_available(long.key)
        coord.client.write_gatt_char.reset_mock()
        await ctrl.lights_on()
        assert packets(coord) == (
            ["3c", "6e"] if wire == "RAW" else ["6e01003cab", "6e01006edd"]
        ) + ["6e0a000179"]
        ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
        coord.client.write_gatt_char.reset_mock()
        light = AdjustableBedLight(coord, LIGHT_DESCRIPTION)
        light.hass = hass
        light.async_write_ha_state = MagicMock()
        started = clock[0]
        await light.async_turn_off()
        assert packets(coord) == (
            ["75", "6e"] if wire == "RAW" else ["6e010075e4", "6e01006edd"]
        ) + ["6e0a000179"]
        interval = ctrl._worker.tick_ms
        assert clock[0] - started == pytest.approx(threshold // interval * interval / 1000 + 0.15)
    finally:
        await coord.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_long_sync_pair_keeps_its_threshold_and_route_cleanup(hass, wire, clock):
    from custom_components.adjustable_bed.card import CARD_UTILITY
    from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = connected_tss(hass, "DXRM")
    coord.client.services = Services([route(2 if wire == "RAW" else 0)])
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    started = clock[0]
    pair = ctrl._inverse_actions()["synchronization"]
    assert [(a.node, a.long, a.gesture.threshold_ms, a.gesture.release_ms) for a in pair] == [
        (7, True, 3000, None if wire == "RAW" else 50),
        (9, True, 3000, None if wire == "RAW" else 50),
    ]
    switch = next(s for s in ctrl.controller_switch_specs if s.key == "tss_synchronization")
    assert switch.card == CARD_UTILITY
    entity = AdjustableBedControllerSwitch(coord, switch)
    entity.async_write_ha_state = MagicMock()
    try:
        await entity.async_turn_on()
        assert entity.is_on is True
        await entity.async_turn_off()
        assert entity.is_on is False
    finally:
        await coord.async_shutdown()
    assert packets(coord) == (
        ["bc", "bd"] if wire == "RAW" else ["6e0100bc2b", "6e01006edd", "6e0100bd2c", "6e01006edd"]
    )
    assert clock[0] - started == pytest.approx(6 if wire == "RAW" else 6.1)


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_long_massage_off_pair_keeps_the_widget_short_mode_action(hass, wire, clock):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.card import CARD_MASSAGE
    from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = connected_tss(hass, "APRM")
    coord.client.services = Services([route(2 if wire == "RAW" else 0)])
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    started = clock[0]
    on, off = ctrl._inverse_actions()["massage"]
    assert (
        on.node,
        on.long,
        off.node,
        off.long,
        off.gesture.threshold_ms,
        off.gesture.release_ms,
    ) == (22, False, 23, True, 3000, 150)
    specs = {s.key: s for s in ctrl.controller_button_specs}
    assert "tss_22" not in specs and "tss_23_long" not in specs
    assert specs["tss_23"].name == "Massage mode"
    switch = next(s for s in ctrl.controller_switch_specs if s.key == "tss_massage")
    assert switch.card == CARD_MASSAGE
    entity = AdjustableBedControllerSwitch(coord, switch)
    entity.async_write_ha_state = MagicMock()
    try:
        await ControllerActionButton(coord, specs["tss_23"]).async_press()
        await entity.async_turn_on()
        assert entity.is_on is True
        await entity.async_turn_off()
        assert entity.is_on is False
    finally:
        await coord.async_shutdown()
    assert packets(coord) == (
        ["48", "6e", "5d", "6e", "47", "6e"]
        if wire == "RAW"
        else ["6e010048b7", "6e01006edd", "6e01005dcc", "6e01006edd", "6e010047b6", "6e01006edd"]
    )
    assert clock[0] - started == pytest.approx(3.45)


async def test_oversized_callback_cannot_replay_the_previous_light_value():
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
    from tests.state_helpers import state_writer

    ctrl, coord = controller("FGRM")
    state = {}
    coord.handle_controller_state_updates.side_effect = state_writer(state)
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
    await ctrl.lights_off()
    assert ctrl._light_on is None
    coord.handle_controller_state_updates.reset_mock()
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray(513))
    assert ctrl._receive.value_event is None and ctrl._receive.events == []
    assert ctrl._light_on is None
    assert not any(
        update.key == UNDER_BED_LIGHTS_ON
        for call in coord.handle_controller_state_updates.call_args_list
        for update in call.args
    )
    with pytest.raises(ServiceValidationError):
        await ctrl.lights_on()
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00017d"))
    assert ctrl._light_on is False and state[UNDER_BED_LIGHTS_ON] is False


@pytest.mark.parametrize("count", [1, 2])
async def test_public_rgb_reconnects_idle_receivers_before_live_validation(
    hass, count, real_wire_clock
):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from tests.hold_lease_wire import virtual_clock

    receivers = [connected_tss(hass, "FGRM", f"AA:BB:CC:DD:EE:{70 + i}") for i in range(count)]
    events = []
    await services.async_register_services(hass)
    for index, (ctrl, co) in enumerate(receivers):
        ctrl._known_light = True
        ctrl.on_disconnect()
        co._is_connected = False
        co.client.is_connected = False

        async def reconnect(*, current=ctrl, coordinator=co, identifier=index, **_kwargs):
            if not coordinator.client.is_connected:
                coordinator.client.is_connected = coordinator._is_connected = True
                await current.start_notify()
                current._notification(
                    current._session, current._session.notify, bytearray.fromhex("6e0e00037f")
                )
                events.append(("connected", identifier))
            return True

        async def write(_char, data, *, identifier=index, **_kwargs):
            if bytes(data).startswith(bytes.fromhex("6e0c")):
                events.append(("rgb", identifier))

        co.async_ensure_connected = AsyncMock(side_effect=reconnect)
        co.client.write_gatt_char.side_effect = write
    targets = [(co, "both") for _, co in receivers]
    try:
        with (
            virtual_clock(),
            patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
        ):
            await hass.services.async_call(
                "adjustable_bed",
                "richmat_classic",
                {
                    "device_id": [f"bed-{i}" for i in range(count)],
                    "operation": "rgb",
                    "rgb_color": [18, 52, 86],
                },
                blocking=True,
            )
        assert events == [("connected", i) for i in range(count)] + [
            ("rgb", i) for i in range(count)
        ]
        for _, co in receivers:
            assert packets(co)[-1] == "6e0cff128b6e0d345605"
    finally:
        for _, co in receivers:
            await co.async_shutdown()


async def test_rgb_batch_rejects_an_unproven_second_receiver_before_any_rgb(hass, real_wire_clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from tests.hold_lease_wire import virtual_clock

    receivers = [connected_tss(hass, "FGRM", f"AA:BB:CC:DD:EE:{80 + i}") for i in range(2)]
    await services.async_register_services(hass)
    try:
        with virtual_clock():
            for i, (ctrl, co) in enumerate(receivers):
                await ctrl.start_notify()
                if i == 0:
                    ctrl._notification(
                        ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f")
                    )
                co.client.write_gatt_char.reset_mock()
            with (
                patch.object(
                    services,
                    "_resolve_sided_targets",
                    return_value=([(co, "both") for _, co in receivers], []),
                ),
                pytest.raises(ServiceValidationError),
            ):
                await hass.services.async_call(
                    "adjustable_bed",
                    "richmat_classic",
                    {
                        "device_id": ["one", "two"],
                        "operation": "rgb",
                        "rgb_color": [18, 52, 86],
                    },
                    blocking=True,
                )
        assert all(not packets(co) for _, co in receivers)
    finally:
        for _, co in receivers:
            await co.async_shutdown()


@pytest.mark.parametrize("invalidate", ["session", "capability", "disconnect"])
@pytest.mark.parametrize(("count", "peer_app"), [(1, app.APP), (2, app.APP), (2, "dreamlab2")])
async def test_rgb_batch_final_guard_checks_every_receiver_under_the_gatt_lock(
    hass, invalidate, count, peer_app, real_wire_clock
):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from tests.hold_lease_wire import virtual_clock

    first, left = connected_tss(hass, "FGRM", "AA:BB:CC:DD:EE:90")
    second, right = connected_tss(hass, "FGRM", "AA:BB:CC:DD:EE:91")
    if peer_app == "dreamlab2":
        hass.config_entries.async_update_entry(
            right.entry,
            data={
                **right.entry.data,
                "product_type": "6BRM",
                "protocol_variant": peer_app,
                "profile_id": "richmat_classic_apps:dreamlab2",
            },
        )
        second = shared.DreamlabController(right, app=peer_app, device_name="6BRM")
        right._controller = second
    targets = [(left, "both"), (right, "both")][:count]
    affected, affected_co = (first, left) if count == 1 else (second, right)
    await services.async_register_services(hass)
    try:
        with (
            virtual_clock(),
            patch.object(
                services,
                "_resolve_sided_targets",
                return_value=(targets, []),
            ),
        ):
            for ctrl, co in ((first, left), (second, right)):
                await ctrl.start_notify()
                ctrl._notification(
                    ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f")
                )
                co.client.write_gatt_char.reset_mock()
            waiting = asyncio.Event()
            original = first._send

            async def send(packet, cancel=None):
                waiting.set()
                await original(packet, cancel)

            with patch.object(first, "_send", side_effect=send):
                async with first._ble_lock:
                    call = asyncio.create_task(
                        hass.services.async_call(
                            "adjustable_bed",
                            "richmat_classic",
                            {
                                "device_id": ["one", "two"],
                                "operation": "rgb",
                                "rgb_color": [18, 52, 86],
                            },
                            blocking=True,
                        )
                    )
                    await waiting.wait()
                    if invalidate == "session":
                        affected._session = replace(affected._session)
                    elif invalidate == "capability":
                        affected._receive.light_capable = False
                    else:
                        affected_co.client.is_connected = False
                error = (
                    ConnectionError
                    if count == 1 and invalidate != "capability"
                    else ServiceValidationError
                )
                with pytest.raises(error):
                    await call
            assert not packets(left) and not packets(right)
    finally:
        await left.async_shutdown()
        await right.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
@pytest.mark.parametrize("entrypoint", ["service", "light"])
async def test_real_idle_reconnect_waits_for_delayed_lamp_reply(
    hass, mock_bleak_client, mock_coordinator_connected, monkeypatch, wire, real_wire_clock,
    entrypoint,
):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.conftest import TEST_ADDRESS
    from tests.hold_lease_wire import virtual_clock

    entry = MockConfigEntry(
        domain="adjustable_bed",
        data={
            "address": TEST_ADDRESS,
            "name": "Bedroom",
            "bed_type": "richmat_classic_apps",
            "profile_id": "richmat_classic_apps:tss_remote",
            "protocol_variant": app.APP,
            "product_type": "FGRM",
            "ble_device_name": "FGRM",
            "connection_mode": "idle",
            "capabilities": {
                "richmat_classic_apps": {"app": app.APP, "layout": "FGRM", "light": True}
            },
        },
    )
    entry.add_to_hass(hass)
    uuid, tx, rx, _ = ROUTES[2 if wire == "RAW" else 0]
    send = SimpleNamespace(uuid=tx, properties=["write"], handle=1)
    notify = SimpleNamespace(uuid=rx, properties=["notify"], handle=2)
    service = SimpleNamespace(get_characteristic={tx: send, rx: notify}.get)
    mock_bleak_client.services.get_service.side_effect = {uuid: service}.get
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    co = AdjustableBedCoordinator(hass, entry)
    await services.async_register_services(hass)
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_a, **_k: ([(co, "both")], []))
    events = []
    with virtual_clock():
        try:
            assert await co.async_connect()
            old = co.controller
            assert isinstance(old, TssRemoteController)
            old_callback = mock_bleak_client.start_notify.await_args.args[1]
            old_callback(old._session.notify, bytearray.fromhex("6e0e00037f"))
            assert old._known_light
            from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

            light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
            light.hass = hass
            light.async_write_ha_state = MagicMock()
            co._cancel_disconnect_timer()
            await co._async_idle_disconnect()
            assert co._last_disconnect_reason == "idle_timeout"
            assert not co.is_connected

            async def write(_char, data, **_kwargs):
                loop = asyncio.get_running_loop()
                if bytes(data) == p.LAMP_QUERY:
                    events.append(("query", loop.time()))
                    callback = mock_bleak_client.start_notify.await_args.args[1]
                    # Invalid input and an old connection's valid reply cannot admit RGB.
                    loop.call_later(0.02, callback, _char, bytearray.fromhex("6e0e00037e"))
                    loop.call_later(0.04, old_callback, _char, bytearray.fromhex("6e0e00037f"))
                    loop.call_later(0.08, callback, _char, bytearray.fromhex("6e0e00037f"))
                elif bytes(data).startswith(bytes.fromhex("6e0c")):
                    events.append(("rgb", loop.time()))

            mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)
            if entrypoint == "light":
                await light.async_turn_on(rgb_color=(18, 52, 86))
            else:
                await hass.services.async_call(
                    "adjustable_bed", "richmat_classic",
                    {"device_id": "bed", "operation": "rgb", "rgb_color": [18, 52, 86]},
                    blocking=True,
                )
            assert [event for event, _ in events] == ["query", "rgb"]
            assert events[1][1] - events[0][1] >= 0.08 - 0.00001
            assert packets(co)[-1] == "6e0cff128b6e0d345605"
        finally:
            await co.async_shutdown()


@pytest.mark.parametrize("proven", [False, True])
async def test_mixed_dreamlab_peer_is_live_admitted_before_any_tss_rgb(
    hass, proven, real_wire_clock
):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from tests.hold_lease_wire import virtual_clock

    first, left = connected_tss(hass, "FGRM", "AA:BB:CC:DD:EE:A0")
    _, right = connected_tss(hass, "6BRM", "AA:BB:CC:DD:EE:A1")
    hass.config_entries.async_update_entry(
        right.entry,
        data={
            **right.entry.data,
            "protocol_variant": "dreamlab2",
            "profile_id": "richmat_classic_apps:dreamlab2",
        },
    )
    second = shared.DreamlabController(right, app="dreamlab2", device_name="6BRM")
    right._controller = second
    await services.async_register_services(hass)
    with virtual_clock():
        try:
            for ctrl, co in ((first, left), (second, right)):
                await ctrl.start_notify()
                if ctrl is first or proven:
                    ctrl._notification(
                        ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f")
                    )
                co.client.write_gatt_char.reset_mock()
            with patch.object(
                services,
                "_resolve_sided_targets",
                return_value=([(left, "both"), (right, "both")], []),
            ):
                call = hass.services.async_call(
                    "adjustable_bed",
                    "richmat_classic",
                    {"device_id": ["one", "two"], "operation": "rgb", "rgb_color": [18, 52, 86]},
                    blocking=True,
                )
                if proven:
                    await call
                    assert packets(left) == packets(right) == ["6e0cff128b6e0d345605"]
                else:
                    with pytest.raises(ServiceValidationError):
                        await call
                    assert not packets(left) and not packets(right)
        finally:
            await left.async_shutdown()
            await right.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_independent_light_off_refreshes_power_before_native_on(hass, wire, real_wire_clock):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight
    from tests.hold_lease_wire import virtual_clock
    from tests.test_richmat_classic_transport import Services, route

    ctrl, co = connected_tss(hass, "FGRM")
    co.client.services = Services([route(2 if wire == "RAW" else 0)])
    unregister = None
    with virtual_clock():
        try:
            await ctrl.start_notify()
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
            light = AdjustableBedLight(co, LIGHT_DESCRIPTION)
            light.hass = hass
            light.async_write_ha_state = MagicMock()
            light._handle_light_state(co.controller_state)
            unregister = co.register_controller_state_callback(light._handle_light_state)
            assert light.is_on is True
            co.client.write_gatt_char.reset_mock()
            spec = next(s for s in ctrl.controller_button_specs if s.key == "tss_2_long")
            before = asyncio.get_running_loop().time()
            await ControllerActionButton(co, spec).async_press()
            assert asyncio.get_running_loop().time() - before == pytest.approx(3.15)
            assert packets(co) == (
                ["75", "6e"] if wire == "RAW" else ["6e010075e4", "6e01006edd"]
            ) + ["6e0a000179"]
            assert ctrl._light_on is None
            assert light.is_on is None
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00017d"))
            assert light.is_on is False
            co.client.write_gatt_char.reset_mock()
            await light.async_turn_on()
            assert packets(co) == (
                ["3c", "6e"] if wire == "RAW" else ["6e01003cab", "6e01006edd"]
            ) + ["6e0a000179"]
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))

            async def still_on(_char, payload, **_kwargs):
                if bytes(payload) == p.LAMP_QUERY:
                    ctrl._notification(
                        ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f")
                    )

            co.client.write_gatt_char.side_effect = still_on
            await light.async_turn_off()
            assert light.is_on is True
        finally:
            if unregister is not None:
                unregister()
            await co.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_cancelled_independent_light_off_keeps_unsent_power(hass, wire, real_wire_clock):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from tests.hold_lease_wire import virtual_clock
    from tests.test_richmat_classic_transport import Services, route

    ctrl, co = connected_tss(hass, "FGRM")
    co.client.services = Services([route(2 if wire == "RAW" else 0)])
    with virtual_clock():
        try:
            await ctrl.start_notify()
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
            co.client.write_gatt_char.reset_mock()
            spec = next(s for s in ctrl.controller_button_specs if s.key == "tss_2_long")

            async def stop():
                await asyncio.sleep(0.08)
                await co.async_stop_command()

            await asyncio.gather(
                ControllerActionButton(co, spec).async_press(), stop(), return_exceptions=True
            )
            assert ctrl._light_on is True
            end = "6e" if wire == "RAW" else "6e01006edd"
            assert packets(co) and set(packets(co)) == {end}
        finally:
            await co.async_shutdown()


@pytest.mark.parametrize("outcome", ["timeout", "stop", "replacement"])
async def test_lamp_admission_wait_is_bounded_cancelled_and_session_owned(
    hass, outcome, real_wire_clock
):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.beds.richmat_classic.tss_remote import (
        LAMP_ADMISSION_TIMEOUT_S,
    )
    from tests.hold_lease_wire import virtual_clock

    ctrl, co = connected_tss(hass, "FGRM")
    await services.async_register_services(hass)
    with virtual_clock():
        try:
            await ctrl.start_notify()
            co.client.write_gatt_char.reset_mock()
            old_session = ctrl._session

            async def interrupt():
                await asyncio.sleep(0.08)
                if outcome == "stop":
                    await co.async_stop_command()
                elif outcome == "replacement":
                    ctrl._session = replace(old_session)
                    ctrl._receive = ctrl._new_receive()
                    ctrl._notification(
                        old_session, old_session.notify, bytearray.fromhex("6e0e00037f")
                    )

            with patch.object(
                services, "_resolve_sided_targets", return_value=([(co, "both")], [])
            ):
                before = asyncio.get_running_loop().time()
                call = hass.services.async_call(
                    "adjustable_bed",
                    "richmat_classic",
                    {"device_id": "bed", "operation": "rgb", "rgb_color": [18, 52, 86]},
                    blocking=True,
                )
                if outcome == "stop":
                    await asyncio.gather(call, interrupt(), return_exceptions=True)
                else:
                    task = asyncio.create_task(interrupt())
                    with pytest.raises(ServiceValidationError):
                        await call
                    await task
                elapsed = asyncio.get_running_loop().time() - before
                if outcome == "timeout":
                    assert elapsed == pytest.approx(LAMP_ADMISSION_TIMEOUT_S)
                else:
                    assert elapsed < LAMP_ADMISSION_TIMEOUT_S
            assert not any(packet.startswith("6e0c") for packet in packets(co))
            if outcome != "stop":
                assert not packets(co)
        finally:
            await co.async_shutdown()


async def test_peer_stop_during_lamp_admission_blocks_the_whole_batch(hass, real_wire_clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed import services
    from tests.hold_lease_wire import virtual_clock

    first, left = connected_tss(hass, "FGRM", "AA:BB:CC:DD:EE:B0")
    second, right = connected_tss(hass, "FGRM", "AA:BB:CC:DD:EE:B1")
    await services.async_register_services(hass)
    with virtual_clock():
        try:
            for ctrl, co in ((first, left), (second, right)):
                await ctrl.start_notify()
                co.client.write_gatt_char.reset_mock()
            first._notification(
                first._session, first._session.notify, bytearray.fromhex("6e0e00037f")
            )

            async def stop_peer():
                await asyncio.sleep(0.02)
                await left.async_stop_command()

            async def reply():
                await asyncio.sleep(0.08)
                second._notification(
                    second._session, second._session.notify, bytearray.fromhex("6e0e00037f")
                )

            with patch.object(
                services,
                "_resolve_sided_targets",
                return_value=([(left, "both"), (right, "both")], []),
            ):
                await asyncio.gather(
                    hass.services.async_call(
                        "adjustable_bed",
                        "richmat_classic",
                        {
                            "device_id": ["one", "two"],
                            "operation": "rgb",
                            "rgb_color": [18, 52, 86],
                        },
                        blocking=True,
                    ),
                    stop_peer(),
                    reply(),
                )
            assert not any(
                packet.startswith("6e0c") for co in (left, right) for packet in packets(co)
            )
        finally:
            await left.async_shutdown()
            await right.async_shutdown()


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_delivered_light_off_invalidates_power_even_when_cancelled_after_write(
    hass, wire, real_wire_clock
):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from tests.hold_lease_wire import virtual_clock
    from tests.test_richmat_classic_transport import Services, route

    ctrl, co = connected_tss(hass, "FGRM")
    co.client.services = Services([route(2 if wire == "RAW" else 0)])
    with virtual_clock():
        try:
            await ctrl.start_notify()
            ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
            co.client.write_gatt_char.reset_mock()
            off = "75" if wire == "RAW" else "6e010075e4"

            async def write(_char, data, **_kwargs):
                if bytes(data).hex() == off:
                    co.cancel_command.set()

            co.client.write_gatt_char.side_effect = write
            spec = next(s for s in ctrl.controller_button_specs if s.key == "tss_2_long")
            await ControllerActionButton(co, spec).async_press()
            assert ctrl._light_on is None
            assert packets(co) == [off, "6e" if wire == "RAW" else "6e01006edd"]
        finally:
            await co.async_shutdown()


@pytest.mark.parametrize(("layout", "node"), [("ZWRM", 15), ("OTRM", 20), ("APRM", 26), ("AURM", 20)])
async def test_fixed_timer_retype_keeps_user_settings_and_independent_actions(hass, layout, node):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.entity_retypes import async_carry_over_retyped_entities
    from custom_components.adjustable_bed.entity_sweep import EntityLedger
    from custom_components.adjustable_bed.removed_entities import async_setup_removed_entities

    ctrl, co = connected_tss(hass, layout)
    registry = er.async_get(hass)
    await async_setup_removed_entities(hass)
    old = registry.async_get_or_create(
        "button", DOMAIN, co.entity_unique_id(f"tss_{node}"),
        config_entry=co.entry, suggested_object_id="bed_duration",
    )
    registry.async_update_entity(old.entity_id, name="My timer", disabled_by=er.RegistryEntryDisabler.USER)
    other = None
    if layout != 'AURM':
        other_node = next(a.node for a in ctrl.fixed_massage_timers.values() if a.node != node)
        other = registry.async_get_or_create(
            "button", DOMAIN, co.entity_unique_id(f"tss_{other_node}"),
            config_entry=co.entry, suggested_object_id="other_duration",
        )
    else:
        assert 'tss_20' not in {spec.key for spec in ctrl.controller_button_specs}
    independent = None
    if layout == "APRM":
        independent = registry.async_get_or_create(
            "button", DOMAIN, co.entity_unique_id("tss_23"),
            config_entry=co.entry, suggested_object_id="massage_mode",
        )
    try:
        async_carry_over_retyped_entities(hass, co.entry, co)
        new_id = registry.async_get_entity_id("select", DOMAIN, co.entity_unique_id("massage_timer"))
        assert new_id == "select.bed_duration"
        new = registry.async_get(new_id)
        assert new.name == "My timer" and new.disabled_by is er.RegistryEntryDisabler.USER
        assert registry.async_get(old.entity_id) is None
        ledger = EntityLedger(hass, co.entry, co)
        ledger.platforms_forwarded(["button", "select"])
        for domain in ("button", "select"):
            ledger.platform_finished(domain)
        ledger.record("timer", [("select", co.entity_unique_id("massage_timer"))])
        ledger.record("buttons", [("button", co.entity_unique_id(s.key)) for s in ctrl.controller_button_specs])
        ledger.async_sweep()
        if other is not None:
            assert registry.async_get(other.entity_id) is None
        if layout == "APRM":
            assert independent is not None
            assert registry.async_get(independent.entity_id) is independent
            assert any(spec.key == "tss_23" for spec in ctrl.controller_button_specs)
    finally:
        await co.async_shutdown()


async def test_fixed_timer_select_rejects_unproven_duration_without_writes(hass):
    ctrl, co = connected_tss(hass, "ZWRM")
    try:
        await ctrl.start_notify()
        co.client.write_gatt_char.reset_mock()
        for minutes in (0, 10, 20, 30, 121):
            with pytest.raises(ServiceValidationError):
                await co.async_execute_controller_command(lambda current, selected=minutes: current.set_massage_timer(selected))
        assert not packets(co)
    finally:
        await co.async_shutdown()
