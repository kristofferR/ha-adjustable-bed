"""Both accepted literal corpora, decisive phases and safe HA runtime callers."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.richmat_legacy import controller as bed
from custom_components.adjustable_bed.beds.richmat_legacy.protocol import LocalState, begin, packet
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.richmat_legacy import (
    APP_NAMES,
    choices,
    matching_profile,
    profiles,
)
from tests.richmat_legacy_vectors import ACCEPTED
from tests.test_casper_base import char, frames
from tests.test_controller_contract import _FactoryCoordinator


def make(app="sleep_evolution", code="A1"):
    c = _FactoryCoordinator()
    c.entry.data.update({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: code})
    c.controller_side = None
    c.record_command_trace = MagicMock()
    c.handle_controller_state_updates = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.write_gatt_char = AsyncMock()
    route = bed.TRANSPORTS["n1"]
    c.client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[char(route.write_uuid, "write")])
    ]
    ctrl = bed.RichmatLegacyController(c)
    c.controller = ctrl
    return ctrl, c


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real = asyncio.sleep

    async def pause(seconds, cancel):
        now[0] += max(0, seconds)
        await real(0)
        return cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "_pause", pause)
    return now


def test_complete_frozen_literal_corpora_against_production_encoder():
    n = [v for v in ACCEPTED["nu503"]["literal"] if v["inputs"]["mode"] == "literal"]
    s = ACCEPTED["silver"]["literal"]
    assert len(s) == 1600
    assert n
    for row in n + s:
        literal = row["inputs"].get("text", row["inputs"].get("literal"))
        assert packet(literal).hex() == row["expected_bytes"], row["id"]
    assert packet("$") == b"\x24"
    assert packet("1") == b"\x31"
    assert packet("A") != packet("a")


def phase_frames(profile, control, ticks, *, axis=0, mode=0, led=0):
    phase = begin(profile.action(control), LocalState(axis, mode, led))
    actual, count = list(phase.down), 0
    for _ in range(ticks):
        writes, count = phase.tick(count)
        actual.extend(writes)
    return [packet(v).hex() for v in (*actual, *phase.release(count))]


@pytest.mark.parametrize("row", ACCEPTED["silver"]["temporal"], ids=lambda r: r["id"])
def test_silver_all_frozen_temporal_cases(row):
    p = row["inputs"]
    v = next(v for v in ACCEPTED["silver"]["variants"] if v["id"] == p["variant"])
    code = "BE" if p["variant"] == "YtMassageActivity" else v["selector"][0]
    profile = profiles()["wsilver_legacy:" + code]
    key = ("massage_" if p["variant"] == "YtMassageActivity" else "") + p["field"]
    action = profile.action(key)
    axis = action.states.index(str(p["state"])) if "state" in p else 0
    assert phase_frames(profile, key, p["ticks"], axis=axis) == row["expected_attempts"]


N_CONTROLS = {
    "movement-6B": ("6B", "iv_post1"),
    "movement-A6": ("A6", "iv_post1"),
    "single-D2-timer": ("D2", "h26_moff"),
    "single-TH-set": ("TH", "set"),
    "single-ON-post2": ("ON", "post2"),
    "A1-memory": ("A1", "h26_lounge"),
    "A1-memory2": ("A1", "h26_tv"),
    "A2-memory2": ("A2", "h26_tv"),
    "A2-memory3": ("A2", "h26_zg"),
    "BZ-memory3": ("BZ", "h26_memb"),
    "A6-zg": ("A6", "iv_post6"),
    "M4-lounge": ("M4", "h26_lounge"),
    "R5-lounge": ("R5", "h26_lounge"),
    "T3-lounge": ("T3", "h26_lounge"),
    "M9-zg": ("M9", "h26_zg"),
    "GV-head-up": ("GV", "btn_posup"),
    "GV-foot-up": ("GV", "btn_posup"),
    "U3-select-mode2": ("U3", "h26_lounge"),
    "Ml-factory": ("Ml", "h26_tiltup"),
    "BE-massage-30": ("BE", "massage_h26_min30"),
    "TL-light": ("TL", "iv_post8"),
    "phone-bed-side-effect": ("B1", "h26_mhdec"),
}


@pytest.mark.parametrize(
    "row",
    [
        v
        for v in ACCEPTED["nu503"]["literal"]
        if v["inputs"]["mode"] in ("held", "dual", "u3", "u5-led")
    ],
    ids=lambda r: r["id"],
)
def test_sleepevolution_all_frozen_temporal_cases(row):
    p, id = row["inputs"], row["id"]
    axis, mode, led = int("foot" in id), p.get("flag", 0), p.get("flag", 0)
    if p["mode"] == "u3":
        code, key = "U3", "h26_tiltup" if p["direction"] == "up" else "h26_tiltdn"
    elif p["mode"] == "u5-led":
        code, key = "U5", "h26_mhinc"
    else:
        code, key = next(
            value
            for name, value in sorted(N_CONTROLS.items(), key=lambda item: -len(item[0]))
            if id.startswith(name)
        )
    assert (
        phase_frames(
            profiles()["sleep_evolution:" + code],
            key,
            p.get("ticks", 0),
            axis=axis,
            mode=mode,
            led=led,
        )
        == row["expected_frames"]
    )


@pytest.mark.parametrize("app,member", [("sleep_evolution", "nu503"), ("wsilver_legacy", "silver")])
def test_every_accepted_reachable_registration_and_phase_is_shipped(app, member):
    rows = ACCEPTED[member]["commands"]
    assert len(rows) == (622 if member == "nu503" else 566)
    for row in rows:
        code = "BE" if row["profile"] == "BE_massage" else row["profile"]
        key = ("massage_" if row["profile"] == "BE_massage" else "") + row["key"]
        action = profiles()[f"{app}:{code}"].action(key)
        for state, expected in row["branches"].items():
            branch = dict(action.branches)[state]
            assert list(branch.writes) == expected.get("strings", expected.get("sends"))
            threshold = expected.get("counter_threshold")
            if "counter_limits" in expected:
                threshold = (
                    int(expected["counter_limits"][0]) if expected["counter_limits"] else None
                )
            assert branch.threshold == threshold
            assert all(len(packet(v)) == 1 for v in branch.writes)
        assert list(action.down) == re.findall(r'sendMessage\("(.)"\)', row["down"])
        assert list(action.short + action.release) == re.findall(
            r'sendMessage\("(.)"\)', row["release"]
        )
        guard = re.search(r"TimerSend < (\d+)", row["release"])
        assert action.short_guard == (int(guard[1]) if guard else None)
        assert action.reset_counter == bool(re.search(r"TimerSend\s*=\s*0", row["release"]))
        assert action.label


@pytest.mark.parametrize("key", list(profiles()))
async def test_all_profile_controls_run_on_captured_gatt_and_expose_specs(clock, key):
    app, code = key.split(":")
    ctrl, c = make(app, code)
    await ctrl.start_notify()
    assert frames(c) == []
    specs = {s.key: s for s in ctrl.controller_button_specs}
    covered = {c for s in ctrl.motor_control_specs for c in (s.hold.up_control, s.hold.down_control)}
    for action in ctrl.profile.actions:
        buttons = [
            spec for key, spec in specs.items()
            if key == "richmat_legacy_" + action.key or key.startswith(f"richmat_legacy_{action.key}_")
        ]
        # Covers own their directions; pickers and wake/release-only gestures are not buttons.
        sent = {*action.down, *action.short, *(w for _, b in action.branches for w in b.writes)}
        assert bool(buttons) != (
            action.key in covered
            or action.key in ctrl._massage_timer_controls.values()
            or action.label == "Tilt ZG selector (mode 2)"
            or sent <= {"m", "n"}
        ), action
        assert all(bool(b.hold) == action.motion for b in buttons if not b.key.endswith("_save"))
        assert ctrl.execution.hold_for(action.key) == ("stream" if action.motion else None)
        c.client.write_gatt_char.reset_mock()
        await ctrl.action(action.key, duration_ms=1)
        assert all(len(call.args[1]) == 1 for call in c.client.write_gatt_char.call_args_list)
        if action.programmable:
            c.client.write_gatt_char.reset_mock()
            await ctrl.action(action.key, program=True)
            values = frames(c)
            assert any(
                v in {packet(x).hex() for _, branch in action.branches for x in branch.writes}
                for v in values
            )
            assert not {packet(x).hex() for x in action.short if x != "n"} & set(values)
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.supports_position_feedback
    assert not ctrl.position_number_specs


async def test_initialization_epoch_phase_not_restarted_and_short_motion_usable(clock):
    ctrl, c = make(code="B6")
    await ctrl.start_notify()
    clock[0] = 0.59
    await ctrl.hold_control("iv_post1", 15)
    assert frames(c) == ["24", "24", "6e"]  # Tick at .6, not DOWN+.5.
    ctrl, c = make(code="6B")
    await ctrl.start_notify()
    clock[0] += 0.01
    await ctrl.hold_control("iv_post1", 1)
    assert frames(c) == ["6d", "24", "6e"]


async def test_dedicated_program_ordinary_latency_and_cancel_no_short_recall(clock):
    ctrl, c = make()
    await ctrl.start_notify()

    async def slow(*args, **kwargs):
        clock[0] += 0.04

    c.client.write_gatt_char.side_effect = slow
    await ctrl.action("h26_lounge", program=True)
    assert frames(c) == ["2b", "6e"]
    c.client.write_gatt_char.reset_mock()
    c.cancel_command.set()
    await ctrl.action("h26_lounge", program=True)
    assert frames(c) == []
    c.cancel_command.clear()
    real_pause = bed._pause

    async def cancel_wait(seconds, event):
        c.cancel_command.set()
        return await real_pause(seconds, event)

    with patch.object(bed, "_pause", cancel_wait):
        await ctrl.action("h26_lounge", program=True)
    assert frames(c) == ["6e"]


async def test_slow_write_no_motion_backfill_and_replacement_cleanup_fenced(clock):
    ctrl, c = make(code="A6")
    await ctrl.start_notify()

    async def slow(*args, **kwargs):
        clock[0] += 1

    c.client.write_gatt_char.side_effect = slow
    await ctrl.hold_control("iv_post1", 10)
    assert frames(c) == ["24", "6e"]
    old = c.client

    async def replace(*args, **kwargs):
        c.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
        ctrl.on_disconnect()

    old.write_gatt_char.side_effect = replace
    with pytest.raises(ConnectionError):
        await ctrl.hold_control("iv_post1", 1000)
    c.client.write_gatt_char.assert_not_awaited()


async def test_submitted_write_drains_before_cancellation_release():
    ctrl, c = make(code="B6")
    await ctrl.start_notify()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def blocked(_char, value, **_kwargs):
        if value == b"$":
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = blocked
    task = asyncio.create_task(ctrl.hold_control("iv_post1", 100))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert frames(c) == ["24"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["24", "6e"]


@pytest.mark.parametrize("app", APP_NAMES)
def test_app_qualified_routes_setup_identity_and_side_ownership(app):
    assert matching_profile(app, "Ml123") == "Ml"
    assert matching_profile(app, "ML123") == ""
    assert matching_profile(app, "0B123") == "M4"
    for rejected in ("01", "02", "Vi", "YT", "MM", "T2"):
        assert not matching_profile(app, rejected + "123")
        assert rejected not in choices(app)
    assert ("A6" in choices(app)) == (app == "sleep_evolution")
    assert (
        resolve_profile_id({const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "GV"})
        == app + ":GV"
    )
    side = per_side_profile(app, "GV")
    assert side is not None
    assert {const.CONF_BLE_DEVICE_NAME, const.CONF_PROTOCOL_VARIANT} <= side.keys


@pytest.mark.parametrize(
    "route,control,command",
    [
        ("sleep_evolution:GV", "btn_posup", "33"),
        ("wsilver_legacy:GV", "btn_posup", "24"),
        ("sleep_evolution:B6", "iv_post1", "24"),
    ],
)
@pytest.mark.parametrize("end", ("expire", "stop"))
async def test_real_scheduler_renewable_motion(route, control, command, end):
    from tests.hold_lease_wire import leased_hold

    async def move(controller):
        await controller.hold_control(control, 30000)

    wire = await leased_hold(route, move, end_after_s=2, end=end)
    assert len(wire.held) > 2
    assert {w.data.hex() for w in wire.held} <= {"6d", command}
    assert [w.data.hex() for w in wire.after] == (["6e", "6e"] if end == "stop" else ["6e"])


async def test_cancellation_during_short_recall_still_completes_release(clock):
    ctrl, c = make(code="A6")
    await ctrl.start_notify()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def block(_char, value, **_kwargs):
        if value == b"E" and not entered.is_set():
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = block
    task = asyncio.create_task(ctrl.action("iv_post6", duration_ms=1))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["45", "45", "45", "6e", "6e"]


@pytest.mark.parametrize("key", list(profiles()))
def test_button_names_are_readable_and_unique(key):
    ctrl, _ = make(*key.split(":"))
    names = [spec.name for spec in ctrl.controller_button_specs]
    assert len(names) == len(set(names)), names
    for name in names:
        assert "pictogram" not in name and "arrow" not in name and "(" not in name, name
        assert not re.search(r"\b(?!TV\b)[A-Z]{2,}\b", name), name


@pytest.mark.parametrize("app", APP_NAMES)
@pytest.mark.parametrize(
    ("code", "names"),
    (
        ("A1", {"Flat"}),
        ("GV", {"Flat", "TV", "Lounge", "Zero Gravity"}),
        ("TH", {"Position 1", "Position 2", "Position 3"}),
        ("LP", {"Memory 1", "Memory 2", "Memory 3"}),
        ("T3", {"Zero Gravity"}),
    ),
)
def test_preset_buttons_have_preset_placement(app, code, names):
    from custom_components.adjustable_bed.card import (
        CARD_LIGHTING,
        CARD_MASSAGE,
        CARD_PRESET_SAVE,
        CARD_PRESETS,
        CardSection,
    )

    ctrl, _ = make(app, code)
    specs = {spec.name: spec for spec in ctrl.controller_button_specs}
    for name in names:
        # Memory slots sit with the memory tiles; other recalls are presets.
        section = CardSection.MEMORY if name.startswith("Memory") else CardSection.PRESETS
        assert specs[name].card.section == section
    for name, spec in specs.items():
        if name.startswith("Save") and spec.card.section == CardSection.PRESETS:
            assert spec.card == CARD_PRESET_SAVE and spec.requires_confirmation
            assert spec.translation_key == "catalog_save"
    for name, spec in specs.items():
        if name == "Toggle Light":
            assert spec.card == CARD_LIGHTING
        elif name.startswith("Massage"):
            assert spec.card == CARD_MASSAGE
    assert CARD_PRESETS in {spec.card for spec in specs.values()} or code == "LP"


async def test_axis_and_mode_buttons_choose_then_press(clock):
    ctrl, c = make(code="GV")
    await ctrl.start_notify()
    names = {spec.name: spec for spec in ctrl.controller_button_specs}
    assert {"Head Up", "Foot Up", "Head On/Off", "Foot On/Off"} <= set(names)
    # Leased holds accept the per-axis ids; a malformed or unoffered suffix is refused.
    assert ctrl.execution.hold_for("btn_posup@1") == "stream"
    for bad in ("btn_posup@-1", "btn_posup@2", "btn_posup@01", "btn_tv@0"):
        with pytest.raises(ValueError):
            ctrl.validate_request(bad, 1)
    assert not any("axis" in name for name in names)
    await names["Head Up"].press_fn(ctrl)
    assert ctrl._link.state.axis == 0
    await names["Foot Up"].press_fn(ctrl)
    assert ctrl._link.state.axis == 1
    ctrl, c = make(code="U3")
    await ctrl.start_notify()
    names = {spec.name: spec for spec in ctrl.controller_button_specs}
    assert {"Lumbar Up", "Tilt Up", "Lounge Up"} <= set(names)
    assert ctrl.execution.hold_for("h26_tiltup@2") == "stream"
    c.client.write_gatt_char.reset_mock()
    await ctrl.hold_control("h26_tiltup@2", 1)
    assert ctrl._link.state.mode == 2 and "41" in frames(c)


def test_gesture_only_controls_and_zero_gravity_set():
    ctrl, _ = make("wsilver_legacy", "GV")
    assert "All Off" not in {s.name for s in ctrl.controller_button_specs}  # sends only m/n
    ctrl, _ = make("sleep_evolution", "GV")
    assert "All Off" in {s.name for s in ctrl.controller_button_specs}  # sends G
    ctrl, _ = make("sleep_evolution", "T3")
    assert {"Zero Gravity", "Save Zero Gravity"} <= {s.name for s in ctrl.controller_button_specs}


@pytest.mark.parametrize("key", list(profiles()))
async def test_massage_timer_keys_are_one_select_sending_the_same_frames(clock, key):
    """Each replaced timer key's press sends exactly what the timer select sends."""
    app, code = key.split(":")
    ctrl, c = make(app, code)
    keys = {
        int(m["minutes"]): action.key
        for action in ctrl.profile.actions
        if (m := re.fullmatch(r"(?P<minutes>\d+)MIN", action.label))
    }
    if len(keys) < 2:
        # A single duration keeps its button.
        assert not ctrl.supports_massage_timer
        return
    assert ctrl._massage_timer_controls == keys
    assert ctrl.massage_timer_options == sorted(keys)
    assert not ctrl.massage_timer_can_turn_off and ctrl.auto_enable_massage
    assert not {"richmat_legacy_" + k for k in keys.values()} & {
        s.key for s in ctrl.controller_button_specs
    }
    for minutes, control in keys.items():
        sent = []
        for run in (
            lambda b, k=control: bed._press(b, control=k),
            lambda b, m=minutes: b.set_massage_timer(m),
        ):
            fresh, fc = make(app, code)
            await fresh.start_notify()
            fc.client.write_gatt_char.reset_mock()
            await run(fresh)
            sent.append(frames(fc))
        assert sent[0] == sent[1] != []
    with pytest.raises(ValueError):
        await ctrl.set_massage_timer(45)


async def test_massage_timer_cut_off_after_the_wake_gesture_shows_nothing(monkeypatch):
    """BE wakes the bed with m before its timer key: a STOP between them sends no timer."""
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    ctrl, c = make("wsilver_legacy", "BE")
    await ctrl.start_notify()
    assert ctrl.supports_massage_timer
    cancel = c.cancel_command

    async def stopped(_seconds, event):
        cancel.set()  # STOP arrives before the first timer frame.
        return True

    monkeypatch.setattr(bed, "_pause", stopped)
    c.client.write_gatt_char.reset_mock()
    c.handle_controller_state_updates.reset_mock()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="timer",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        await ctrl.set_massage_timer(30)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert frames(c)[0] == packet("m").hex()  # Only the wake gesture and release went out.
    assert packet("A").hex() not in frames(c)
    shown = [u for call in c.handle_controller_state_updates.call_args_list for u in call.args]
    assert not any(u.key == "massage_timer" for u in shown)


async def test_massage_timer_whose_window_ends_before_its_key_shows_nothing(clock, monkeypatch):
    """A window that ends before BE's first timer refresh sent only the wake gesture."""
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    ctrl, c = make("wsilver_legacy", "BE")
    await ctrl.start_notify()

    async def late(seconds, _event):
        clock[0] += 5  # The first refresh comes after the press window.
        return False

    monkeypatch.setattr(bed, "_pause", late)
    c.client.write_gatt_char.reset_mock()
    c.handle_controller_state_updates.reset_mock()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=c.cancel_command,
        admitted_stop_epoch=0,
        intent_id="timer",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        await ctrl.set_massage_timer(30)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert packet("A").hex() not in frames(c)
    shown = [u for call in c.handle_controller_state_updates.call_args_list for u in call.args]
    assert not any(u.key == "massage_timer" for u in shown)
