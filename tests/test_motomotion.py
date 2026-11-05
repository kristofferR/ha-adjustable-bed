"""Accepted row113 vectors through live controller and receive/action boundaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds import motomotion as bed
from custom_components.adjustable_bed.codec.motomotion import (
    Position,
    ascii_command,
    binary_command,
    music_command,
)
from custom_components.adjustable_bed.motomotion_protocol import (
    decimal,
    light_cycle,
    posture,
    rgb_total,
)
from custom_components.adjustable_bed.motomotion_requests import Request
from custom_components.adjustable_bed.motomotion_state import State
from custom_components.adjustable_bed.profiles.motomotion import Profile, eligible


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.address = "AA:BB:CC:DD:EE:13"
    c.entry.data = {"ble_device_name": "SOFA000001MC00H"}
    c.cancel_command = asyncio.Event()
    c.client.is_connected = True
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.controller_state = {}
    c.handle_controller_state_updates.side_effect = c.controller_state.update
    return c


def controller(c, name="SOFA000001MC00H"):
    c.entry.data = {"ble_device_name": name}
    ctrl = bed.MotoMotionController(c)
    char = SimpleNamespace(uuid="0000ffe1-0000-1000-8000-00805f9b34fb", handle=13)
    ctrl._session = (c.client, char, char)
    ctrl._unpair_write = char
    c.capability_controller = ctrl
    return ctrl


@pytest.fixture
def instant(monkeypatch):
    times = []

    async def wait(self, seconds, cancel):
        times.append(seconds)
        return not cancel.is_set()

    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    return times


def frame(length, changes=None):
    tokens = ["0"] * length
    for index, value in (changes or {}).items():
        tokens[index] = str(value)
    return b"$" + " ".join(tokens).encode() + b"\r"


def written(c):
    return [call.args[1] for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    ("command", "parameter", "hex_value"),
    [
        (1, 0, "2423303030303130303030303030303031520d"),
        (263, 10000, "2423303032363331303030303030303036520d"),
        (500, 12345, "2423303035303031323334353030303034520d"),
        (315, 10120, "2423303033313531303132303030303035520d"),
    ],
)
def test_ascii_vectors(command, parameter, hex_value):
    assert ascii_command(command, parameter).hex() == hex_value


@pytest.mark.parametrize(
    ("command", "parameter", "hex_value"),
    [
        (33050, 0, "2423811a00009b410d"),
        (9, 63, "24230009003f36410d"),
        (1, 31, "24230001001f1e410d"),
    ],
)
def test_binary_vectors(command, parameter, hex_value):
    assert binary_command(command, parameter).hex() == hex_value


def test_posture_and_music_vectors():
    assert Position(1, 2, 3, 4, 5).to_bytes().hex() == "41494f4b00010004000300020005520d"
    assert Position(-1, 65536, 0, 65535, 0).to_bytes().hex() == "41494f4b0000ffff0000ffff0000520d"
    assert (
        posture("tv", 170, float("nan"), 55).to_bytes().hex() == "41494f4b00a70364055801a0026f520d"
    )
    with pytest.raises(ValueError):
        posture("upright", 170, float("nan"), 55)
    assert (
        b"".join(music_command(k, v) for k, v in zip("MTBV", [8, 10, 5, 5], strict=True)).hex()
        == "24234d30380d24235431300d24234230350d24235630350d"
    )


@pytest.mark.parametrize("zeroes", [0, 19, 4300, 10000])
@pytest.mark.parametrize("value", [0, 7, 9223372036854775807])
def test_decimal_admits_padded_native_values(zeroes, value):
    assert decimal("0" * zeroes + str(value)) == value


@pytest.mark.parametrize(
    "value", ["", "1 2", "-7", "１２", "9223372036854775808", "0" * 5000 + "9223372036854775808"]
)
def test_decimal_rejects_actual_errors(value):
    with pytest.raises(ValueError):
        decimal(value)


def test_native_intermediate_wrap_and_light_order():
    assert rgb_total(("4611686018427387904", "4611686018427387905", "9223372036854775807")) == 0
    assert light_cycle("9223372036854775807", True) == 32788
    assert light_cycle("", False) == 32788
    with pytest.raises(ValueError):
        light_cycle("", True)


@pytest.mark.parametrize(
    ("selector", "panel"),
    [
        ("1", "One"),
        ("2", "One"),
        ("3", "Three"),
        ("5", "Five"),
        ("6", "Six"),
        ("7", "Seven"),
        ("8", "One"),
        ("9", "One"),
        ("A", "A"),
        ("D", "D"),
        ("E", "E"),
        ("G", "G"),
        ("H", "H"),
        ("J", "J"),
        ("M", "Music"),
        ("Z", "One"),
    ],
)
def test_all_primary_routes(selector, panel):
    assert Profile("SOFA00000" + selector + "MC00H").panel == panel


def test_independent_name_domains_and_safe_short_name():
    assert Profile("BT2010000").panel == "Binary music"
    assert Profile("SOFA00000MA000H").panel == "One"
    p = Profile("SOFA000006AD00H")
    assert p.users and not p.rgb and p.heat
    assert Profile("SOFA000005S00FM").sides
    assert Profile("SOFA000005S00FM").massage
    assert eligible("xMOTO")
    with pytest.raises(ValueError):
        Profile("xMOTO")
    assert not eligible("sofa0000010000H")
    with pytest.raises(ValueError):
        Profile("MOTO0000050")
    for name in ("BT201SOFA", "MOTOSOFA000001"):
        assert eligible(name)
        with pytest.raises(ValueError):
            Profile(name)


def test_parser_partial_stores_and_buffer_reset():
    state = State()
    events = []
    state.feed(frame(11, {0: 7, 3: 30, 4: 2}), "SOFA000001MC00H", events.append)
    assert state.cm is not None and state.cm.heat == 1
    with pytest.raises(ValueError):
        state.feed(frame(11, {0: 9, 3: ""}), "SOFA000001MC00H", events.append)
    assert state.rgb == ("9", "0", "0") and state.cm.heat == 1
    assert events == ["OK"] and not state.buffer
    state.feed(frame(24) + frame(11, {0: 999}), "SOFA000001MC00H", events.append)
    assert state.token_count == 24 and state.rgb == ("0", "0", "0")
    state.feed(frame(43), "SOFA000001MC00H", events.append)
    assert events == ["OK", "OK", "OK", "OK"]


async def test_partial_receive_changes_real_lumbar_without_ok(coordinator, instant):
    c = controller(coordinator, "SOFA00000ESC00M")
    char = c._session[2]
    c._notification(0, char, bytearray(frame(37, {26: 30, 35: 0})))
    await asyncio.sleep(0)  # Deliver named event against current singleton.
    assert c._local_d
    c._notification(0, char, bytearray(frame(37, {26: "", 35: 2})))
    assert c._rejection and c._state.cm.heat == 1
    await c.action("motomotion_lumbar_toggle")
    assert written(coordinator) == [ascii_command(353)] * 3
    assert instant == [0.1, 0.1]


async def test_queued_event_reads_latest_partial_singleton(coordinator, instant):
    c = controller(coordinator, "SOFA00000DMC00H")
    char = c._session[2]
    c._notification(0, char, bytearray(frame(38, {0: 0, 1: 8})))
    c._notification(0, char, bytearray(frame(37, {26: "", 35: 2})))
    assert not c._local_d
    await asyncio.sleep(0)
    assert c._local_d
    await c.action("motomotion_lumbar_toggle")
    assert written(coordinator) == [ascii_command(33050), ascii_command(16)]
    assert instant == [0.3]


async def test_long_padded_rgb_failure_then_live_toggle(coordinator, instant):
    c = controller(coordinator)
    char = c._session[2]
    c._notification(0, char, bytearray(frame(11, {0: "0" * 6000, 3: ""})))
    assert c._rejection
    await c.action("motomotion_light_toggle")
    assert written(coordinator) == [ascii_command(k, 120) for k in (315, 316, 317)]
    c._state.rgb = ("0", "", "0")
    with pytest.raises(ValueError):
        await c.action("motomotion_light_toggle")
    assert len(written(coordinator)) == 3


async def test_d_light_overflow_through_live_action_and_unknown_guard(coordinator, instant):
    c = controller(coordinator, "SOFA00000DMC00H")
    c._state.d = ("0" * 6000 + "9223372036854775807", "0")
    c._local_d = True
    await c.action("motomotion_light_cycle")
    assert written(coordinator) == [bytes.fromhex("2423333237383830303030303030303036520d")]
    c._state.d = ("", "0")
    with pytest.raises(ValueError):
        await c.action("motomotion_light_cycle")
    c._local_d = False
    await c.action("motomotion_light_cycle")
    assert len(written(coordinator)) == 2


async def test_old_notify_session_rejected(coordinator):
    c = controller(coordinator)
    char = c._session[2]
    await c.stop_notify()
    c._notification(0, char, bytearray(frame(24)))
    assert c._state.token_count == 0


async def test_binding_cache_request_before_ble_without_durability(coordinator, monkeypatch):
    c = controller(coordinator)
    c._manufacturer = b"\x01"
    char = c._session[1]
    bind = SimpleNamespace(uuid="ffe2")
    monkeypatch.setattr(bed, "select_transport", lambda client: (char, char, bind, 0))
    draws = iter([0, 1, 2, 3, 127, 128, 253, 254])
    monkeypatch.setattr(bed.secrets, "randbelow", lambda n: next(draws))
    events = []
    coordinator.save_app_state.side_effect = lambda ctrl: events.append(
        ("request", ctrl._bind_code)
    )

    async def write(characteristic, value, **kwargs):
        events.append(("BLE", value.hex()))

    coordinator.client.write_gatt_char.side_effect = write
    await c.start_notify()
    assert events == [("request", "000102037f80fdfe"), ("BLE", "000102037f80fdfe")]
    assert c._bind_code == "000102037f80fdfe"


async def test_side_scoped_callable_and_invalid_other_child(coordinator, instant):
    c = controller(coordinator, "SOFA000001SC00H")
    c._state.rgb = ("0", "0", "0")
    spec = next(s for s in c.controller_button_specs if s.key == "motomotion_light_toggle")
    await spec.press_fn(c.bind_side("right"))
    assert written(coordinator) == [ascii_command(k, 10120) for k in (315, 316, 317)]
    with pytest.raises(ValueError):
        await c.bind_side("left").select("side", "right")


def test_restore_side_defaults_for_existing_state(coordinator):
    c = controller(coordinator, "SOFA000001SB00H")
    c.restore_persisted_app_state({"side": "right"})
    c.restore_persisted_app_state({})
    assert c.persisted_app_state["side"] == "left"


@pytest.mark.parametrize("side", ["both", "", None, 1, ["right"]])
def test_restore_rejects_invalid_side(coordinator, side):
    c = controller(coordinator, "SOFA000001SB00H")
    with pytest.raises(ValueError, match="saved side"):
        c.restore_persisted_app_state({"side": side})


def test_restore_posture_defaults_for_existing_state(coordinator):
    c = controller(coordinator, "SOFA000001A000H")
    c.restore_persisted_app_state({"posture": "tv"})
    c.restore_persisted_app_state({})
    assert c.persisted_app_state["posture"] == "upright"


@pytest.mark.parametrize("value", ["unknown", "", None, 1, ["tv"]])
async def test_restore_rejects_invalid_posture(coordinator, value):
    c = controller(coordinator, "SOFA000001A000H")
    c.restore_persisted_app_state(
        {"posture": value, "dimensions": {"height": 170, "buttocks": 100, "knee": 55}}
    )
    assert c._posture is None
    with pytest.raises(ValueError, match="Select a MotoMotion posture"):
        await c.action("motomotion_posture_recall")
    assert written(coordinator) == []
    await c.select("posture", "tv")
    await c.action("motomotion_posture_recall")
    assert written(coordinator) == [posture("tv", 170, 100, 55).to_bytes()]


@pytest.mark.parametrize("mismatch", ["user", "posture", "dimensions", "range", "bool", "shape"])
async def test_working_target_owner_or_shape_mismatch_cannot_save_old_targets(
    coordinator, instant, mismatch
):
    from copy import deepcopy

    c = controller(coordinator, "SOFA000001A000H")
    await c.async_execute_motomotion_request(
        Request("save_user", user="A", dimensions=(170, 100, 55))
    )
    await c.async_execute_motomotion_request(
        Request("save_user", user="B", dimensions=(160, 90, 50))
    )
    await c.async_execute_motomotion_request(Request("select_user", user="A", posture="tv"))
    await c.async_execute_motomotion_request(
        Request("fine_tune", posture="tv", targets=Position(300, 400, 500, 600, 200))
    )
    saved = deepcopy(c.persisted_app_state)
    working = saved["working_targets"]
    assert isinstance(working, dict)
    dimensions = working["dimensions"]
    positions = working["positions"]
    assert isinstance(dimensions, dict) and isinstance(positions, dict)
    if mismatch == "user":
        working["user"] = "B"
    elif mismatch == "posture":
        working["posture"] = "lay"
    elif mismatch == "dimensions":
        dimensions["height"] = 160
    elif mismatch == "range":
        positions["head"] = 65536
    elif mismatch == "bool":
        positions["head"] = True
    else:
        del positions["tilt"]
    restored = controller(coordinator, "SOFA000001A000H")
    coordinator.client.write_gatt_char.reset_mock()
    restored.restore_persisted_app_state(saved)
    assert restored._user == "A" and restored._posture == "tv" and restored._targets is None
    with pytest.raises(ValueError, match="Recall or fine tune"):
        await restored.action("motomotion_posture_save")
    assert written(coordinator) == []


async def test_measurement_and_user_change_invalidate_working_targets(coordinator, instant):
    c = controller(coordinator, "SOFA000001A000H")
    for user, dims in [("A", (170, 100, 55)), ("B", (160, 90, 50))]:
        await c.async_execute_motomotion_request(Request("save_user", user=user, dimensions=dims))
    await c.async_execute_motomotion_request(Request("select_user", user="A", posture="tv"))
    await c.set_number("target_head", 300)
    await c.action("motomotion_posture_save")
    await c.set_number("height", 175)
    assert c._targets is None
    assert c._custom["tv"].head == 300
    await c.async_execute_motomotion_request(Request("select_user", user="B", posture="tv"))
    assert c._targets is None and c._custom == {}
    await c.async_execute_motomotion_request(Request("select_user", user="A", posture="tv"))
    assert c._custom["tv"].head == 300


async def test_legacy_music_preferences_restore_without_new_optional_fields(coordinator, instant):
    c = controller(coordinator, "BT2010000")
    c.restore_persisted_app_state({"custom_eq": [17, 13, 14, 15]})
    assert c._music_mode == "custom" and c._eq == [17, 13, 14, 15]
    await c.select("music_mode", "wide")
    assert written(coordinator)[-1] == binary_command(9, 17)


async def test_number_and_select_callbacks_are_callable(coordinator, instant):
    c = controller(coordinator, "BT2010000")
    spec = next(s for s in c.controller_number_specs if s.key == "motomotion_treble")
    await spec.set_fn(c, 9)
    assert written(coordinator) == [binary_command(1, 9), binary_command(2, 9)]
    mode = c.controller_select_specs[0]
    await mode.select_fn(c, "wide")
    assert written(coordinator)[2:] == [
        binary_command(k, v)
        for k, v in zip((1, 2, 3, 4, 5, 6, 9), (10, 10, 5, 5, 5, 7, 8), strict=True)
    ]


async def test_user_service_admission_and_helper_domain_separation(coordinator, instant):
    c = controller(coordinator, "SOFA000001A000H")
    with pytest.raises(ValueError):
        c.validate_motomotion_request(
            Request("save_user", user="K", dimensions=(170, float("nan"), 55))
        )
    await c.async_execute_motomotion_request(
        Request("save_user", user="K", dimensions=(170, 100, 55))
    )
    await c.async_execute_motomotion_request(Request("recall", user="K", posture="tv"))
    assert written(coordinator) == [posture("tv", 170, 100, 55).to_bytes()]
    with pytest.raises(ValueError):
        c.validate_motomotion_request(Request("fine_tune", targets=Position(864, 0, 0, 0, 0)))


@pytest.mark.parametrize("length", [11, 16, 24, 31, 37, 38, 39, 42, 43, 50, 62, 71])
def test_every_receive_length_and_exact_event_multiplicity(length):
    s = State()
    events = []
    s.feed(frame(length), "SOFA000001MC00H", events.append)
    assert s.token_count == length
    assert events == (["OK", "OK"] if length == 43 else ["OK"])
    if length == 62:
        assert s.cm is not None and s.cm.calibrated and s.cm.flag
    if length == 50:
        assert s.hsw == (False, 0)


@pytest.mark.parametrize("index", [19, 20, 21, 22, 23, 24, 48, 30])
def test_calibration_parses_all_fields_before_store(index):
    s = State()
    events = []
    s.feed(frame(62), "SOFA000001MC00H", events.append)
    previous = s.cm
    with pytest.raises(ValueError):
        s.feed(frame(62, {19: 1, index: ""}), "SOFA000001MC00H", events.append)
    assert s.cm is previous and events == ["OK"]


async def test_memory_cancel_cleanup_cannot_be_suppressed(coordinator, monkeypatch):
    c = controller(coordinator, "SOFA000001MCE0H")
    frames = []

    async def write(frame, repeat_count=1, repeat_delay_ms=100, cancel_event=None):
        if frame == ascii_command(256):
            coordinator.cancel_command.set()
            raise asyncio.CancelledError
        assert cancel_event is not None and not cancel_event.is_set()
        frames.append(frame)

    async def sleep(seconds):
        assert seconds == 0.05

    async def wait(self, seconds, cancel):
        return True

    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    monkeypatch.setattr(c, "write_command", write)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await c.preset_memory(1)
    assert frames == [ascii_command(0)] * 3


async def test_pending_color_and_light_read_current_state(coordinator, monkeypatch):
    c = controller(coordinator)

    async def mutate(self, seconds, cancel):
        c._rgb[:] = [255, 0, 128]
        return True

    monkeypatch.setattr(bed.MotoMotionController, "_wait", mutate)
    await c._color()
    assert written(coordinator) == [
        ascii_command(315, 120),
        ascii_command(316, 0),
        ascii_command(317, 60),
    ]
    c = controller(coordinator, "SOFA00000DMC00H")
    c._local_d = True
    c._state.d = ("1", "0")

    async def receive(self, seconds, cancel):
        c._state.d = ("7", "0")
        c._deliver(c._generation, "OK")
        return True

    monkeypatch.setattr(bed.MotoMotionController, "_wait", receive)
    await c.action("motomotion_light_cycle")
    assert written(coordinator)[-1] == ascii_command(32795)


async def test_program_does_not_trigger_apps_accidental_release_recall(coordinator, instant):
    c = controller(coordinator, "SOFA00000ESC00M")
    await c.program_memory(1)
    assert written(coordinator) == [ascii_command(33050), ascii_command(263)]
    assert ascii_command(256) not in written(coordinator)


async def test_custom_postures_stay_with_selected_user(coordinator, instant):
    c = controller(coordinator, "SOFA000001A000H")
    for user in ("K", "L"):
        await c.async_execute_motomotion_request(
            Request("save_user", user=user, dimensions=(170, 100, 55))
        )
    await c.async_execute_motomotion_request(Request("select_user", user="K"))
    await c.async_execute_motomotion_request(Request("fine_tune", targets=Position(1, 2, 3, 4, 5)))
    await c.async_execute_motomotion_request(Request("save_posture"))
    await c.async_execute_motomotion_request(Request("select_user", user="L"))
    assert c._custom == {}
    await c.async_execute_motomotion_request(Request("select_user", user="K"))
    assert c._position() == Position(1, 2, 3, 4, 5)
    restored = controller(coordinator, "SOFA000001A000H")
    restored.restore_persisted_app_state(c.persisted_app_state)
    assert restored._position() == Position(1, 2, 3, 4, 5)


async def test_held_movement_cadence_and_fresh_cleanup(coordinator, monkeypatch):
    c = controller(coordinator)
    now = [0.0]
    times = []

    async def delay(self, seconds, cancel):
        if cancel.is_set():
            return False
        now[0] += seconds
        return True

    async def sleep(seconds):
        now[0] += seconds

    async def write(characteristic, value, **kwargs):
        times.append((round(now[0], 3), value))
        if value == ascii_command(2) and now[0] >= 0.2:
            coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = write
    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", delay)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.hold_control("motomotion_headrest_up", 1000)
    assert times == [
        (0.1, ascii_command(2)),
        (0.2, ascii_command(2)),
        (0.25, ascii_command(0)),
        (0.25, ascii_command(0)),
        (0.25, ascii_command(0)),
    ]


async def test_right_child_level_consumes_right_delivered_state(coordinator, instant):
    from custom_components.adjustable_bed.motomotion_state import Comfort

    c = controller(coordinator, "SOFA000001S000M")
    c._local_lr = (Comfort(heat=0), Comfort(heat=2))
    await c.bind_side("right").async_execute_motomotion_action("motomotion_heat_up")
    assert written(coordinator) == [ascii_command(334, 10000)]
    c._publish()
    assert coordinator.controller_state["motomotion_heat_left"] == 0
    assert coordinator.controller_state["motomotion_heat_right"] == 2
    assert {s.key for s in c.bind_side("right").controller_state_sensor_specs} == {
        "motomotion_status",
        "motomotion_heat_right",
        "motomotion_massage_right",
    }


async def test_h_heat_switches_between_hsw_and_cm_by_delivered_current_count(coordinator, instant):
    c = controller(coordinator, "SOFA00000HMC00H")
    char = c._session[2]
    c._notification(0, char, bytearray(frame(50, {12: 4, 13: 4, 14: 4})))
    await asyncio.sleep(0)
    assert c._panel_heat == 3  # HSW is not remapped.
    await c.action("motomotion_heat_cycle")
    assert written(coordinator)[-1] == ascii_command(332)
    c._notification(0, char, bytearray(frame(11, {3: 90})))
    await asyncio.sleep(0)
    assert c._panel_heat == 2  # Same singleton HSW survives, but this event consumes CM.
    await c.action("motomotion_heat_cycle")
    assert written(coordinator)[-1] == ascii_command(335)


def test_transport_role_overwrite_preserves_exact_full_characteristics():
    a = SimpleNamespace(uuid="0000ffe1-0000-1000-8000-00805f9b34fb")
    binding = SimpleNamespace(uuid="0000ffe2-0000-1000-8000-00805f9b34fb")
    b = SimpleNamespace(uuid="custom-fff1-write")
    n = SimpleNamespace(uuid="custom-fff2-notify")
    client = SimpleNamespace(
        services=[
            SimpleNamespace(uuid="custom-ffe0", characteristics=[a, binding]),
            SimpleNamespace(uuid="custom-fff0", characteristics=[b, n]),
        ]
    )
    assert bed.select_transport(client) == (b, n, binding, 0)
    client.services.reverse()
    assert bed.select_transport(client) == (a, a, binding, 0.1)
    client.services.clear()
    with pytest.raises(ValueError):
        bed.select_transport(client)


async def test_start_failure_invalidates_pending_callbacks(coordinator, monkeypatch):
    c = controller(coordinator)
    char = c._session[2]
    monkeypatch.setattr(bed, "select_transport", lambda client: (char, char, None, 0))
    coordinator.client.start_notify.side_effect = ConnectionError("CCCD rejected")
    with pytest.raises(ConnectionError):
        await c.start_notify()
    assert c._session is None
    c._notification(1, char, bytearray(frame(24)))
    assert c._state.token_count == 0


def test_durable_ledger_covers_every_accepted_identifier_and_command():
    import json
    from pathlib import Path

    d = json.loads(
        (
            Path(__file__).parents[1] / "docs/apk-analysis/dispositions/row113-motomotion.json"
        ).read_text()
    )
    assert len(d["items"]) == len({item["id"] for item in d["items"]}) == 316
    assert len(d["command_coverage"]) == 144
    assert (
        d["coverage"]["primary_routes"]
        == d["coverage"]["unique_panel_classes"] + d["coverage"]["aliases"]
        == 17
    )
    for item in d["items"]:
        assert item["disposition"] in ("IMPLEMENTED", "ALREADY_IMPLEMENTED", "EXCLUDED")
        assert item["reason"]
        if item["disposition"] == "IMPLEMENTED":
            assert item["groups"] and all(g in d["behavior_groups"] for g in item["groups"])
    for group in d["behavior_groups"].values():
        assert group["code"] and group["tests"]
        for reference in group["code"] + group["tests"]:
            path, symbol = reference.split("::")
            text = (Path(__file__).parents[1] / path).read_text()
            assert ("def " + symbol.split(".")[-1] + "(") in text or (
                "class " + symbol + ":"
            ) in text


async def test_release_before_first_period_never_starts_motor(coordinator, monkeypatch):
    c = controller(coordinator)
    now = [0.0]

    async def delay(self, seconds, cancel):
        now[0] += seconds
        return not cancel.is_set()

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", delay)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.hold_control("motomotion_headrest_up", 20)
    assert written(coordinator) == [ascii_command(0)] * 3
    assert now[0] == pytest.approx(0.07)


async def test_unbind_disconnects_if_cancelled_after_write(coordinator, monkeypatch):
    c = controller(coordinator)
    coordinator.async_disconnect = AsyncMock()

    async def sleep(seconds):
        assert seconds == 1
        raise asyncio.CancelledError

    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await c.action("motomotion_unbind")
    assert written(coordinator) == [b"$#005001234500004R\r"]
    assert coordinator.client.write_gatt_char.await_args.kwargs == {"response": False}
    coordinator.async_disconnect.assert_awaited_once()


async def test_old_physical_target_cannot_receive_notifications_or_commands(coordinator):
    c = controller(coordinator)
    char = c._session[2]
    coordinator.address = "AA:BB:CC:DD:EE:99"
    c._notification(0, char, bytearray(frame(24)))
    assert c._state.token_count == 0
    with pytest.raises(ConnectionError):
        await c.write_command(ascii_command(1))
    assert written(coordinator) == []


@pytest.mark.parametrize(
    ("selector", "slots"),
    [
        ("1", 2),
        ("2", 2),
        ("3", 2),
        ("5", 2),
        ("6", 1),
        ("7", 0),
        ("8", 2),
        ("9", 2),
        ("A", 0),
        ("D", 1),
        ("E", 1),
        ("G", 4),
        ("H", 0),
        ("J", 2),
        ("M", 0),
        ("Z", 2),
    ],
)
def test_panel_memory_admission_matches_full_source_layout(coordinator, selector, slots):
    c = controller(coordinator, "SOFA00000" + selector + "MC00M")
    assert c.memory_slot_count == slots
    assert c.supports_memory_presets == c.supports_memory_programming == bool(slots)
    assert sum(key.startswith("motomotion_memory_") for key in c.held_control_options) == slots


async def test_panel_a_rejects_every_memory_entry_before_write(coordinator):
    c = controller(coordinator, "SOFA00000AMC00H")
    for operation in (
        c.preset_memory(1),
        c.program_memory(1),
        c.hold_control("motomotion_memory_1", 100),
    ):
        with pytest.raises(ValueError):
            await operation
    assert written(coordinator) == []


@pytest.mark.parametrize(
    ("selector", "direction", "expected"),
    [
        ("2", "up", ascii_command(32)),
        ("2", "down", ascii_command(16)),
        ("1", "up", binary_command(2)),
        ("1", "down", binary_command(1)),
    ],
)
async def test_selector2_ascii_branch_precedes_moto_binary(
    coordinator, monkeypatch, selector, direction, expected
):
    c = controller(coordinator, "MOTO00000" + selector + "00000")
    now = [0.0]

    async def wait(self, seconds, cancel):
        now[0] += seconds
        return True

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.hold_control("motomotion_headrest_" + direction, 150)
    assert written(coordinator) == [expected, *([ascii_command(0)] * 3)]
    if selector == "2":
        spec = next(
            s for s in c.controller_button_specs if s.key == "motomotion_headrest_" + direction
        )
        assert spec.name == "Back " + direction
        assert spec.translation_placeholders == {"action": "Back " + direction}


@pytest.mark.parametrize("duration", [20, 250])
async def test_home_held_refresh_has_no_source_release_frame(coordinator, monkeypatch, duration):
    c = controller(coordinator)
    now = [0.0]
    ticks = []

    async def wait(self, seconds, cancel):
        now[0] += seconds
        return not cancel.is_set()

    async def write(char, value, **kwargs):
        ticks.append(round(now[0], 3))

    coordinator.client.write_gatt_char.side_effect = write
    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    await c.hold_control("motomotion_home", duration)
    assert written(coordinator) == [ascii_command(262)] * (duration // 100)
    assert ticks == ([] if duration == 20 else [0.1, 0.2])
    spec = next(s for s in c.controller_button_specs if s.key == "motomotion_home")
    assert spec.hold.start_delay_ms == 0 and spec.hold.release_delay_ms == 0
    assert spec.hold.release_button_key == "motomotion_release"


async def test_switch_posture_invalidates_save_and_rebuilds_five_target_axes(coordinator, instant):
    c = controller(coordinator, "SOFA000001A000H")
    await c.async_execute_motomotion_request(
        Request("save_user", user="K", dimensions=(170, 100, 55))
    )
    await c.async_execute_motomotion_request(Request("select_user", user="K"))
    await c.async_execute_motomotion_request(
        Request("fine_tune", posture="tv", targets=Position(1, 2, 3, 4, 5))
    )
    with pytest.raises(ValueError, match="different user or posture"):
        await c.async_execute_motomotion_request(Request("save_posture", posture="lay"))
    assert c._posture == "tv" and c._custom == {}
    await c.select("posture", "lay")
    assert c._targets is None
    with pytest.raises(ValueError):
        await c.action("motomotion_posture_save")
    await c.set_number("target_lumbar", 20)
    lay = posture("lay", 170, 100, 55)
    assert c._targets == Position(lay.head, lay.base, lay.back, 20, lay.tilt)
    await c.action("motomotion_posture_save")
    restored = controller(coordinator, "SOFA000001A000H")
    restored.restore_persisted_app_state(c.persisted_app_state)
    await restored.select("posture", "lay")
    assert restored._position() == c._targets


@pytest.mark.parametrize(
    ("advert", "saved", "admit"),
    [
        (b"", "", True),
        (b"\x01", "", True),
        (b"\x02" + b"\x12" * 8, "12" * 8, True),
        (b"\x02" + b"\x12" * 8, "34" * 8, False),
        (b"\x02" + b"\x12" * 8, "", False),
        (b"\x02\x12", "12" * 8, False),
    ],
)
async def test_binding_suffix_admission_before_subscription_or_commands(
    coordinator, monkeypatch, advert, saved, admit
):
    c = controller(coordinator)
    c._manufacturer = advert
    c.restore_persisted_app_state({"bind_code": saved})
    char = c._session[1]
    monkeypatch.setattr(bed, "select_transport", lambda client: (char, char, None, 0))
    if admit:
        await c.start_notify()
        await c.write_command(ascii_command(1))
        assert written(coordinator) == [ascii_command(1)]
    else:
        with pytest.raises(ValueError, match="ownership"):
            await c.start_notify()
        assert c._session is None and "ownership" in c._rejection
        coordinator.client.start_notify.assert_not_awaited()
        with pytest.raises(ConnectionError):
            await c.write_command(ascii_command(1))
        assert written(coordinator) == []


async def test_unbind_uses_ffe1_after_normal_fff_roles_win(coordinator, monkeypatch):
    c = controller(coordinator)
    old = c._session[1]
    normal = SimpleNamespace(uuid="0000fff1-0000-1000-8000-00805f9b34fb", handle=20)
    notify = SimpleNamespace(uuid="0000fff2-0000-1000-8000-00805f9b34fb", handle=21)
    coordinator.client.services = [
        SimpleNamespace(uuid="ffe0", characteristics=[old]),
        SimpleNamespace(uuid="fff0", characteristics=[normal, notify]),
    ]
    coordinator.async_disconnect = AsyncMock()

    async def sleep(seconds):
        return None

    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.start_notify()
    assert c._session[1] is normal and c._unpair_write is old
    await c.action("motomotion_unbind")
    assert coordinator.client.write_gatt_char.await_args.args[:2] == (old, b"$#005001234500004R\r")
    assert coordinator.client.write_gatt_char.await_args.kwargs == {"response": False}
    coordinator.async_disconnect.assert_awaited_once()
    coordinator.client.services = [SimpleNamespace(uuid="fff0", characteristics=[normal, notify])]
    await c.start_notify()
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="FFE0/FFE1"):
        await c.action("motomotion_unbind")
    assert written(coordinator) == []


async def test_binding_rejection_clears_when_exact_saved_ownership_recovers(
    coordinator, monkeypatch
):
    c = controller(coordinator)
    c._manufacturer = b"\x02" + b"\x12" * 8
    char = c._session[1]
    monkeypatch.setattr(bed, "select_transport", lambda client: (char, char, None, 0))
    with pytest.raises(ValueError):
        await c.start_notify()
    assert "ownership" in coordinator.controller_state["motomotion_status"]
    c.restore_persisted_app_state({"bind_code": "12" * 8})
    await c.start_notify()
    assert coordinator.controller_state["motomotion_status"] == "ready"


def test_name_predicates_and_receive_use_native_string_code_unit_indices():
    name = "SOFA😴0001MC00M"
    assert len(name) == 14 and eligible(name)
    p = Profile(name)
    assert p.panel == "One" and p.music and p.light_kind == 2 and p.massage
    s = State()
    events = []
    s.feed(frame(11, {0: 7, 3: 30, 4: 2}), name, events.append)
    assert s.rgb == ("7", "0", "0") and s.cm.heat == 1 and s.cm.massage == 2
    assert s.left is None and s.right is None and events == ["OK"]


async def test_native_selector2_index_with_surrogate_pair_keeps_ascii_branch(
    coordinator, monkeypatch
):
    c = controller(coordinator, "MOTO😴000200000")
    assert c.profile.panel == "One" and c.profile.char(9) == "2"
    now = [0.0]

    async def wait(self, seconds, cancel):
        now[0] += seconds
        return not cancel.is_set()

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    await c.hold_control("motomotion_headrest_up", 150)
    assert written(coordinator) == [ascii_command(32), *([ascii_command(0)] * 3)]


async def test_restore_working_targets_defaults_for_existing_state(coordinator):
    c = controller(coordinator, "SOFA000001A000H")
    raw = {"head": 300, "base": 100, "back": 200, "lumbar": 0, "tilt": 0}
    dimensions = {"height": 170, "buttocks": 100, "knee": 55}
    selected = {"users": {"K": [170, 100, 55]}, "user": "K", "posture": "tv", "dimensions": dimensions}
    c.restore_persisted_app_state({**selected, "targets": raw})
    assert c._targets is None
    assert c.persisted_app_state["working_targets"] is None
    assert "targets" not in c.persisted_app_state
    c.restore_persisted_app_state({
        **selected,
        "working_targets": {"user": "K", "posture": "tv", "dimensions": dimensions, "positions": raw},
        "targets": {**raw, "head": 1},
    })
    assert c._targets == Position(**raw)
    await c.set_number("target_back", 400)
    assert written(coordinator) == [Position(300, 100, 400, 0, 0).to_bytes()]
    c.restore_persisted_app_state({})
    assert c.persisted_app_state["working_targets"] is None


@pytest.mark.parametrize(
    "targets",
    [
        [],
        {"head": 300},
        *[
            {"head": value, "base": 100, "back": 200, "lumbar": 0, "tilt": 0}
            for value in (-1, 65536, True, 1.5)
        ],
    ],
)
async def test_restore_rejects_invalid_working_targets(coordinator, targets):
    c = controller(coordinator, "SOFA000001A000H")
    dimensions = {"height": 170, "buttocks": 100, "knee": 55}
    c.restore_persisted_app_state({
        "posture": "tv", "dimensions": dimensions,
        "working_targets": {"user": None, "posture": "tv", "dimensions": dimensions, "positions": targets},
    })
    assert c._posture == "tv" and c._targets is None
    with pytest.raises(ValueError, match="Recall or fine tune"):
        await c.action("motomotion_posture_save")
    assert written(coordinator) == []
