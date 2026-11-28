"""Full Flexx contract through real HA admission, product setup and runtime surfaces."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.dreamsense.flexx_motion import (
    COLOR,
    FlexxMotionController,
)
from custom_components.adjustable_bed.beds.dreamsense.flexx_receive import FlexxReceive, decode
from custom_components.adjustable_bed.beds.dreamsense.muuegm import ACTIVE
from custom_components.adjustable_bed.beds.dreamsense.transport import select as choose
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.flexx_motion import CHOICES, PALETTE, PROFILES
from custom_components.adjustable_bed.state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES
from tests.error_helpers import raises_key
from tests.flexx_motion_vectors import FULL, encode
from tests.test_dreamsense import make_client, written

NOW = datetime(2026, 11, 28, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize("row", FULL["vectors"], ids=lambda r: r["id"])
def test_all_211_frozen_vectors_use_the_existing_codec(row):
    assert encode(row) == bytes.fromhex(row["expected_bytes"].replace(" / ", ""))


@pytest.mark.parametrize("row", FULL["bindings"], ids=lambda r: r["id"])
def test_every_719_generic_binding_and_model_gate(row):
    profile = PROFILES[row["label"]]
    action = FULL["controls"][row["template"]]["action"].removeprefix("deviceFunctionItem")
    if action in ("TileUp", "TileDown"):
        assert action in profile.omitted
        assert action not in [a.action for a in profile.controls]
    elif row["role"] not in ("release", "light_utility"):
        item = next(a for a in profile.controls if a.action == action)
        assert (item.save if row["press"] == "long" else item.code) == row["opcode"]
        control = FULL["controls"][row["template"]]
        if row["role"] == "preset":
            assert item.release is False
            assert item.save_delay_ms == (3000 if profile.label == "BJRN" else 0)
            assert item.save is None or control["save_visible"]
        elif action not in ("SyncOn", "SyncOff"):
            assert item.release
    assert row["sides"] == ([0, 1] if profile.side and row["role"] != "light_utility" else [0])
    assert codec.function(row["opcode"], single=True).hex() == row["bytes_by_route"]["P1"]
    for side in row["sides"]:
        assert codec.function(row["opcode"], side).hex() == row["bytes_by_route"][f"P2.side{side}"]


@pytest.mark.parametrize("row", FULL["advanced"], ids=lambda r: r["id"])
def test_every_89_advanced_binding_uses_exact_product_flags(row):
    p = PROFILES[row["label"]]
    name = row["action"].lower()
    if "repeat alarm" in name:
        assert p.clock and p.repeat and p.alarm
    if "one-shot alarm" in name:
        assert p.clock and not p.repeat and p.alarm
    if "light" in name:
        assert p.light
    if "clock/timezone" in name:
        assert p.clock
    if "standard/split" in name:
        assert p.split and p.box_query and p.label in ("blue", "green", "orange")


def test_exact_34_models_current_picker_and_exclusions():
    assert set(PROFILES) == {p["label"] for p in FULL["products"] if p["scope"] == "DIRECT_BLE_BED"}
    assert {p.label for p in PROFILES.values() if p.normal} == {
        "AFEG300",
        "AFEG300-SH",
        "PB250",
        "PB300",
        "PB325",
        "PB450",
        "PB450-SH",
    }
    for row in FULL["products"]:
        if row["label"] not in PROFILES:
            assert row["label"] not in CHOICES
            continue
        p = PROFILES[row["label"]]
        flags = row["flags"]
        assert (p.clock, p.repeat, p.light, p.side) == tuple(
            flags[k]
            for k in (
                "alarm_gate",
                "repeat_alarm_layout",
                "rgb_light_page_gate",
                "side_selector_gate",
            )
        )
        assert not p.vibration
        if not p.normal:
            assert CHOICES[p.product].startswith("Restored product:")


async def runtime(hass, model="PB450", route=1, *, response=False):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Flexx Motion",
        data={
            CONF_ADDRESS: "11:22:33:44:55:81",
            CONF_NAME: "Flexx Motion",
            const.CONF_BED_TYPE: "flexx_motion",
            const.CONF_PROTOCOL_VARIANT: model,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: True,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = make_client(route, without_response=not response)
    ctrl = await create_controller(coord, "flexx_motion", model, coord.client)
    assert isinstance(ctrl, FlexxMotionController)
    coord._controller = ctrl
    ctrl._wait = AsyncMock()
    with patch(
        "custom_components.adjustable_bed.beds.dreamsense.flexx_motion.dt_util.now",
        return_value=NOW,
    ):
        await ctrl.start_notify()
    return coord, ctrl


def notify(coord, value):
    char, callback = coord.client.start_notify.await_args.args
    callback(char, bytearray.fromhex(value))


@pytest.mark.parametrize("route", range(6))
@pytest.mark.parametrize("model", PROFILES)
async def test_every_model_admits_all_six_exact_gatt_routes_and_startup(hass, model, route):
    coord, ctrl = await runtime(hass, model, route)
    frames = written(coord)
    assert frames[0] == ("00" if route == 0 else "6e02010071")
    end = 1
    if ctrl.profile.clock:
        assert frames[1:3] == [
            x.hex() for x in codec.time_sync(NOW, NOW, build=codec.record_20_len)
        ]
        end = 3
    assert frames[end : end + 2] == (["01", "01"] if route == 0 else ["6e08010178", "6e0a000179"])
    assert len(frames) == end + 2 + int(ctrl.profile.split)
    if ctrl.profile.split:
        assert frames[-1] == "6e20080b020000a3"
    assert all(
        call.kwargs["response"] is False for call in coord.client.write_gatt_char.await_args_list
    )
    assert not ctrl.position_number_specs and not ctrl.supports_single_address_pairing
    await ctrl.start_notify()
    assert coord.client.start_notify.await_count == 1
    ctrl.on_disconnect()


@pytest.mark.parametrize("model", PROFILES)
async def test_all_native_model_controls_saves_memory_and_timer_paths(hass, model):
    coord, ctrl = await runtime(hass, model)
    buttons = _button_entities_for(hass, coord)
    assert buttons
    for action in ctrl.profile.controls:
        coord.client.write_gatt_char.reset_mock()
        await coord.async_execute_controller_command(
            lambda c, a=action: c.press(a.action, duration_ms=100)
        )
        expected = codec.function(action.code).hex()
        assert written(coord) == [expected] + (["6e01006edd"] if action.release else [])
        if action.save is not None:
            coord.client.write_gatt_char.reset_mock()
            await coord.async_execute_controller_command(
                lambda c, a=action: c.press(a.action, save=True)
            )
            assert written(coord) == [codec.function(action.save).hex()]
    if ctrl.supports_massage_timer:
        for minutes in ctrl.massage_timer_options:
            await coord.async_execute_controller_command(
                lambda c, n=minutes: c.set_massage_timer(n)
            )
            assert coord.controller_state[MASSAGE_TIMER_MINUTES] == minutes
    assert all("Tile" not in str(s) for s in ctrl.controller_button_specs)
    ctrl.on_disconnect()


@pytest.mark.parametrize("model", PROFILES)
async def test_real_setup_restores_exact_profile_and_owns_generic_fields(hass, model):
    from custom_components.adjustable_bed import _async_sync_profile_ids
    from tests.form_helpers import finish_new_bed
    from tests.test_richmat_family_flow import setup_flow

    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "flexx_motion"})
    flow._discovery_info = None
    flow._final_settings_pending = True
    with patch.object(flow, "_verification_possible", return_value=False):
        form = await flow.async_step_profile_questions()
        assert form["type"] == "form"
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: model})
        result = await finish_new_bed(flow, result)
    saved = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    saved.add_to_hass(hass)
    _async_sync_profile_ids(hass, saved)
    assert saved.data[const.CONF_PROFILE_ID] == f"flexx_motion:{model}"
    coord = AdjustableBedCoordinator(hass, saved)
    assert coord.disable_angle_sensing
    await coord.async_prime_offline_controller()
    assert coord.capability_controller.profile == PROFILES[model]


def test_exact_property_roles_and_last_route_without_nominal_notify_constraint():
    client = make_client(1, without_response=False)
    client.services[0].characteristics.pop()
    client.services += make_client(0).services
    selected = choose(client, 1, "PB450", routes=FlexxMotionController._routes)
    assert selected.write is client.services[0].characteristics[0]
    assert selected.notify is client.services[1].characteristics[1]
    assert selected.single and selected.response
    client.services.reverse()
    assert not choose(client, 1, "PB450", routes=FlexxMotionController._routes).single
    for svc in client.services:
        svc.characteristics[0].properties = ["write-without-response"]
    with raises_key("dreamsense_transport"):
        choose(client, 1, "PB450", routes=FlexxMotionController._routes)


@pytest.mark.parametrize("model", ["PB450", "PB250", "PB450-SH", "blue", "AFEG300", "ABM10"])
async def test_fresh_capability_gates_palette_shared_timers_and_sides(hass, model):
    coord, ctrl = await runtime(hass, model)
    assert not ctrl.supports_light_timer
    notify(coord, "6e09010078 6e0e00037f")
    assert ctrl.supports_light_timer is ctrl.profile.light
    assert bool(ctrl.alarm_capability) is (ctrl.profile.clock and bool(ctrl.profile.alarm))
    if ctrl.profile.side:
        ctrl.select_side("right")
    elif ctrl.controller_select_specs:
        assert all(s.key != "dreamsense_selected_side" for s in ctrl.controller_select_specs)
    if ctrl.profile.light:
        for name, color in PALETTE.items():
            coord.client.write_gatt_char.reset_mock()
            await coord.async_execute_controller_command(
                lambda c, rgb=color: c.light_settings(color=rgb), cancel_running=False
            )
            assert written(coord) == [codec.rgb(*color).hex()]
            assert coord.controller_state[COLOR] == name
        for option, seconds in zip(
            ctrl.light_timer_options, ctrl.flexx_profile.light_seconds, strict=True
        ):
            coord.client.write_gatt_char.reset_mock()
            await coord.async_execute_controller_command(
                lambda c, op=option: c.set_light_timer(op), cancel_running=False
            )
            assert written(coord) == [
                (
                    codec.light_timer(255, 255)
                    if not seconds
                    else codec.light_timer(seconds >> 8, seconds)
                ).hex()
            ]
            assert coord.controller_state[LIGHT_TIMER_OPTION] == option
        coord.client.write_gatt_char.reset_mock()
        await coord.async_execute_controller_command(lambda c: c.close_light())
        assert written(coord) == [
            "6e010075e4"
        ]  # Dedicated close defaults left even with side selected right.
        with raises_key("dreamsense_action"):
            ctrl.validate_light((1, 2, 3), None)
    else:
        coord.client.write_gatt_char.reset_mock()
        with raises_key("dreamsense_action"):
            await ctrl.light_settings(color=PALETTE["white"])
        coord.client.write_gatt_char.assert_not_awaited()
    ctrl.on_disconnect()


def test_bounded_framing_known_fields_and_no_invented_feedback():
    rx = FlexxReceive()
    common = bytes.fromhex("6e90366e" + f"{(0x6E + 0x90 + 0x36 + 0x6E) & 255:02x}")
    assert decode(common)[1] == {"number": 1, "status": 2, "angle": 110}
    rx.feed(common[:3])
    assert not rx.events
    rx.feed(common[3:])
    motor = rx.events["motor_channel"]
    assert isinstance(motor, dict)
    assert motor["angle"] == 110
    for raw in ("6e200000", "6e2100008f", "6e4000"):
        rx.feed(bytes.fromhex(raw))
        rx.expire()
        assert not rx.pending
    probe = bytes.fromhex("6e200a040202000102a3")
    rx.feed(probe[:4])
    assert rx.pending
    rx.feed(probe[4:])
    assert rx.events["light_seconds"] == 62
    before = dict(rx.events)
    rx.feed(probe[:-1] + b"\x00")
    assert rx.events == before
    rx.feed(codec.record_20_len(2, 1, 2, (1,)))  # An unpaired level never consumes its checksum.
    assert "massage_strength" not in rx.events
    rx.feed(codec.record_20_len(17, 2, 2, (1, 0, 0)))
    assert rx.frames[-1]["dispatch"] == "excluded"


async def test_actual_stream_cancel_releases_original_side_and_failed_att_is_not_replayed(hass):
    coord, ctrl = await runtime(hass, "PB450-SH")
    ctrl.select_side("right")
    coord.client.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kw):
        if data == codec.function(0x24, 1):
            began.set()
            await finish.wait()

    coord.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.press("HeadUp", duration_ms=100))
    )
    await asyncio.wait_for(began.wait(), 2)
    ctrl.select_side("left")
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(coord)[-1] == "6e01016ede"
    coord.client.write_gatt_char.reset_mock()

    async def failed(_char, data, **kw):
        if data == codec.function(0x24):
            raise BleakError("transport failed")

    coord.client.write_gatt_char.side_effect = failed
    with pytest.raises(BleakError):
        await coord.async_execute_controller_command(lambda c: c.press("HeadUp", duration_ms=100))
    assert written(coord) == ["6e01002493", "6e01006edd"]
    ctrl.on_disconnect()


async def test_stale_callback_and_startup_failure_never_create_ready_session(hass):
    coord, ctrl = await runtime(hass)
    char, callback = coord.client.start_notify.await_args.args
    await ctrl.stop_notify()
    callback(char, bytearray.fromhex("6e09010078"))
    assert "clock" not in ctrl.receive.capabilities
    coord.client.start_notify.side_effect = BleakError("subscription failed")
    with pytest.raises(BleakError):
        await ctrl.start_notify()
    assert ctrl._ready is None
    assert not ctrl.receive.capabilities
    callback(char, bytearray.fromhex("6e0e00037f"))
    assert not ctrl.receive.capabilities


async def test_shared_alarm_service_create_ack_state_and_record_mutation_actions(hass):
    coord, ctrl = await runtime(hass, "AFEG300")
    notify(coord, "6e09010078")
    await services.async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coord, "both")], []),
    ):
        coord.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": ["flexx"],
                "enabled": True,
                "time": "06:30:00",
                "wake_action": "zero_g",
                "slot": 1,
                "weekdays": ["monday", "wednesday"],
            },
            blocking=True,
        )
        assert written(coord) == [codec.record_20_len(5, 1, 1, (1, 0, 6, 30, 0x45, 0xA1)).hex()]
        notify(coord, codec.record_20_len(5, 1, 2, (1, 0, 6, 30, 0x45, 0xA1)).hex())
        coord.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "flexx_motion_enable_alarm",
            {"device_id": ["flexx"], "alarm_number": 1, "enabled": False},
            blocking=True,
        )
        assert written(coord) == [codec.record_20_len(5, 1, 1, (1, 0, 6, 30, 0x45, 0xA0)).hex()]
        notify(coord, codec.record_20_len(5, 1, 2, (1, 0, 6, 30, 0x45, 0xA0)).hex())
        coord.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "flexx_motion_delete_alarm",
            {"device_id": ["flexx"], "alarm_number": 1},
            blocking=True,
        )
        assert written(coord) == ["6e2008050201019f"]
    ctrl.on_disconnect()


async def test_one_shot_uses_ack_only_for_current_command_and_box_mode_is_separate(hass):
    coord, ctrl = await runtime(hass, "blue")
    notify(coord, "6e09010078")
    coord.client.write_gatt_char.reset_mock()
    alarm = AlarmRequest(enabled=True, hour=6, minute=30, wake_action="zero_g", reference_time=NOW)
    with patch(
        "custom_components.adjustable_bed.beds.dreamsense.muuegm.dt_util.now", return_value=NOW
    ):
        await coord.async_execute_controller_command(
            lambda c: c.configure_alarm(alarm), cancel_running=False
        )
    assert written(coord) == [f.hex() for f in codec.countdown(1440, 0x45)]
    assert coord.controller_state.get(ACTIVE) is None
    notify(coord, "6e07010177")
    assert coord.controller_state[ACTIVE] is True
    coord.client.write_gatt_char.reset_mock()
    box = next(s for s in ctrl.controller_switch_specs if s.key == "dreamsense_split")
    await coord.async_execute_controller_command(
        lambda c: box.set_fn(c, True), cancel_running=False
    )
    assert written(coord) == ["6e20090b02010000a5"]
    notify(coord, "6e20090b02020000a6")
    assert ctrl.receive.split is True
    ctrl.on_disconnect()


@pytest.mark.parametrize("row", FULL["advanced"], ids=lambda r: r["id"])
async def test_each_advanced_binding_executes_on_its_ha_model(hass, row):
    from custom_components.adjustable_bed.profiles.dreamsense import ALARM_NAMES

    coord, ctrl = await runtime(hass, row["label"])
    startup = written(coord)
    notify(coord, "6e09010078 6e0e00037f")
    coord.client.write_gatt_char.reset_mock()
    action = row["action"]
    mode = next(iter(ctrl.profile.alarm.values()), 0)
    name = next((ALARM_NAMES[k] for k in ctrl.profile.alarm), "none")
    request = AlarmRequest(
        enabled=True, hour=6, minute=30, wake_action=name, slot=1, reference_time=NOW
    )
    expected = []
    with patch(
        "custom_components.adjustable_bed.beds.dreamsense.muuegm.dt_util.now", return_value=NOW
    ):
        if action == "Synchronize clock/timezone":
            with patch(
                "custom_components.adjustable_bed.beds.dreamsense.flexx_motion.dt_util.now",
                return_value=NOW,
            ):
                await coord.async_execute_controller_command(
                    lambda c: c.sync_clock(), cancel_running=False
                )
            expected = [f.hex() for f in codec.time_sync(NOW, NOW, build=codec.record_20_len)]
        elif action == "Set one-shot alarm countdown":
            await coord.async_execute_controller_command(
                lambda c: c.configure_alarm(request), cancel_running=False
            )
            expected = [f.hex() for f in codec.countdown(1440, mode)]
        elif action == "Cancel one-shot alarm":
            await coord.async_execute_controller_command(
                lambda c: c.configure_alarm(replace(request, enabled=False)), cancel_running=False
            )
            expected = [f.hex() for f in codec.countdown(0, 0)]
        elif action == "Query repeat alarm list":
            await coord.async_execute_controller_command(
                lambda c: c.query_alarms(), cancel_running=False
            )
            expected = ["6e2008050100009c"]
        elif action == "Set or replace repeat alarm":
            await coord.async_execute_controller_command(
                lambda c: c.configure_alarm(replace(request, weekdays=(0, 2))), cancel_running=False
            )
            expected = [codec.record_20_len(5, 1, 1, (1, 0, 6, 30, mode, 0xA1)).hex()]
        elif action == "Delete repeat alarm":
            notify(coord, codec.record_20_len(5, 1, 2, (1, 0, 6, 30, mode, 0xA1)).hex())
            identity = ctrl.validate_record(1)
            await coord.async_execute_controller_command(
                lambda c: c.delete_alarm(1, identity), cancel_running=False
            )
            expected = ["6e2008050201019f"]
        elif action == "Query standard/split mode":
            assert startup[-1] == "6e20080b020000a3"
        elif action == "Set standard/split mode":
            setting = next(s for s in ctrl.controller_switch_specs if s.key == "dreamsense_split")
            await coord.async_execute_controller_command(
                lambda c: setting.set_fn(c, True), cancel_running=False
            )
            expected = ["6e20090b02010000a5"]
        elif action == "Set light timer":
            seconds = ctrl.flexx_profile.light_seconds[0]
            option = ctrl.light_timer_options[0]
            await coord.async_execute_controller_command(
                lambda c: c.set_light_timer(option), cancel_running=False
            )
            expected = [
                (
                    codec.light_timer(seconds >> 8, seconds)
                    if seconds
                    else codec.light_timer(255, 255)
                ).hex()
            ]
        elif action == "Set palette light color":
            await coord.async_execute_controller_command(
                lambda c: c.light_settings(color=PALETTE["white"]), cancel_running=False
            )
            expected = [codec.rgb(255, 255, 255).hex()]
        else:
            pytest.fail(action)
    assert written(coord) == expected
    ctrl.on_disconnect()


def test_discovery_uses_only_case_sensitive_packet_local_names():
    from custom_components.adjustable_bed.discovery_hints._hints import Advertisement
    from custom_components.adjustable_bed.discovery_hints.flexx_motion import HINTS

    hint = HINTS[0]
    assert hint.matches(Advertisement("Custom", frozenset(), {}, "prefix-QRRM-123"))
    assert not hint.matches(Advertisement("QRRM-123", frozenset(), {}, "custom"))
    assert not hint.matches(Advertisement("qrrm-123", frozenset(), {}, "qrrm-123"))


async def test_no_delayed_motion_crosses_a_replacement_link(hass):
    coord, ctrl = await runtime(hass)
    old = coord.client
    old.write_gatt_char.reset_mock()
    entered, proceed = asyncio.Event(), asyncio.Event()

    async def delayed(ms, event=None):
        entered.set()
        await proceed.wait()

    ctrl._wait = delayed
    task = asyncio.create_task(
        coord.async_execute_controller_command(lambda c: c.press("HeadUp", duration_ms=100))
    )
    await asyncio.wait_for(entered.wait(), 2)
    ctrl.on_disconnect()
    replacement = make_client(0)
    coord._client = replacement
    proceed.set()
    await task
    old.write_gatt_char.assert_not_awaited()
    replacement.write_gatt_char.assert_not_awaited()


async def test_first_tick_short_tap_and_setting_writes_have_distinct_timing(hass):
    from custom_components.adjustable_bed.beds.dreamsense import controller as family

    coord, ctrl = await runtime(hass)
    now = [0.0]
    sent_at = []

    async def advance(ms, event=None):
        now[0] += ms / 1000

    ctrl._wait = advance
    coord.client.write_gatt_char.reset_mock()
    coord.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: sent_at.append(now[0])
    with patch.object(family, "monotonic", side_effect=lambda: now[0]):
        await coord.async_execute_controller_command(lambda c: c.hold_control("HeadUp", 50))
        assert not written(coord)
        await coord.async_execute_controller_command(lambda c: c.hold_control("HeadUp", 100))
        assert sent_at == pytest.approx([0.15, 0.15])
        coord.client.write_gatt_char.reset_mock()
        sent_at.clear()
        await coord.async_execute_controller_command(lambda c: c.press("ZeroGravity"))
        await coord.async_execute_controller_command(lambda c: c.press("AntiSnoring"))
        assert sent_at == pytest.approx([0.15, 0.15])
    ctrl.on_disconnect()


@pytest.mark.parametrize("probe", FULL["parser_probes"]["probes"], ids=lambda p: p["id"])
def test_all_frozen_state_probes_keep_physical_limits(probe):
    frame = bytes.fromhex(probe["frame"])
    receiver = FlexxReceive()
    receiver.feed(frame)
    if probe["id"].startswith("heating-"):
        assert receiver.frames[-1]["dispatch"] == "excluded"
        assert not receiver.events
        return
    event = decode(frame)
    assert event is not None
    name, value = event
    frozen = probe["expected_events"][0][1]
    if probe["id"] == "motor-angle":
        assert (name, value) == ("position_record", frozen)
    elif probe["id"] == "motor-height":
        assert (name, value) == (
            "height_record",
            {
                **{k: v for k, v in frozen.items() if k != "monitorHeight"},
                "monitor_height": frozen["monitorHeight"],
            },
        )
    elif probe["id"] == "massage-zones":
        assert (name, value) == ("massage_strength", {"1": 5, "2": 3})
    elif probe["id"] == "rgb":
        assert (name, value) == ("rgb", tuple(frozen))
    elif probe["id"] == "rgb-timer":
        assert (name, value) == ("light_seconds", frozen)
    elif probe["id"] == "box-split":
        # Keep the sealed parser probe intact; the app consumer/enum names 2 standard.
        assert frozen is True and frame[7] == 2
        assert (name, value) == ("box_mode_raw", 2)
        assert receiver.split is False
    elif probe["id"] == "common-angle":
        assert (name, value) == (
            "motor_channel",
            {"number": frozen["no"], "status": frozen["status"], "angle": frozen["angle"]},
        )
    elif probe["id"] == "common-massage":
        assert (name, value) == ("massage_channels", frozen)
    else:
        pytest.fail(probe["id"])


@pytest.mark.parametrize("row", FULL["parser_probes"]["crc_probes"])
def test_frozen_crc_probes_remain_encoder_checks_without_ota_actions(row):
    record = bytes.fromhex(row["input"] + row["crc"])
    assert codec.is_valid_crc(record)
    receiver = FlexxReceive()
    receiver.feed(record)
    assert not receiver.events


async def test_subscription_and_att_completion_are_bounded(hass):
    from tests.hold_lease_wire import virtual_clock

    coord, ctrl = await runtime(hass)
    coord.client.write_gatt_char.reset_mock()

    async def stall_move(_char, data, **kw):
        if data == codec.function(0x24):
            await asyncio.Event().wait()

    coord.client.write_gatt_char.side_effect = stall_move
    with virtual_clock(), pytest.raises(TimeoutError):
        await coord.async_execute_controller_command(lambda c: c.press("HeadUp", duration_ms=100))
    assert written(coord) == ["6e01002493", "6e01006edd"]
    await ctrl.stop_notify()

    async def stall_subscribe(*args):
        await asyncio.Event().wait()

    coord.client.start_notify.side_effect = stall_subscribe
    with virtual_clock(), pytest.raises(TimeoutError):
        await ctrl.start_notify()
    assert ctrl._ready is None
    assert not ctrl.receive.capabilities


async def test_memory_entities_keep_gestures_and_side_choice_survives_reconnection(hass):
    coord, ctrl = await runtime(hass, "VIP 3.0-SH")
    controls = [s for s in ctrl.controller_button_specs if s.key.startswith("MemoryPosition")]
    assert len(controls) == ctrl.memory_slot_count
    assert all(s.hold is not None for s in controls if ctrl._action(s.key).held)
    assert all(s.hold is None for s in ctrl.controller_button_specs if s.requires_confirmation)
    ctrl.select_side("right")
    ctrl.on_disconnect()
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    await coord.async_execute_controller_command(lambda c: c.press("HeadUp", duration_ms=100))
    assert written(coord) == ["6e01012494", "6e01016ede"]
    ctrl.on_disconnect()


async def test_unknown_alarm_modes_do_not_become_mutating_controls_or_raw_sensor_fields(hass):
    from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS

    coord, ctrl = await runtime(hass, "AFEG300")
    notify(coord, "6e09010078")
    notify(coord, codec.record_20_len(5, 1, 2, (1, 0, 6, 30, 0xFF, 1)).hex())
    records = coord.controller_state[ALARMS]
    assert isinstance(records, dict)
    fields = records["0"]
    assert isinstance(fields, dict)
    assert fields["wake_action"] is None and fields["slot"] == 1
    assert not {"reserved", "mode", "repeat_mask"}.intersection(fields)
    identity = ctrl.validate_record(1)
    coord.client.write_gatt_char.reset_mock()
    with raises_key("dreamsense_action"):
        await coord.async_execute_controller_command(
            lambda c: c.enable_alarm(1, False, identity), cancel_running=False
        )
    coord.client.write_gatt_char.assert_not_awaited()
    await coord.async_execute_controller_command(
        lambda c: c.delete_alarm(1, identity), cancel_running=False
    )
    assert written(coord) == ["6e2008050201019f"]
    ctrl.on_disconnect()


@pytest.mark.parametrize("roles_ok", (True, False))
async def test_live_setup_checks_exact_roles_without_sending_controls(
    hass, enable_custom_integrations, roles_ok
):
    from homeassistant.config_entries import SOURCE_BLUETOOTH

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import form_answers, options_of
    from tests.test_atlas_lift import packet_info
    from tests.test_config_flow import _advance_only_progress, _patch_gate

    manager = hass.config_entries.flow
    choice = await manager.async_init(
        const.DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=packet_info("Receiver", "xQRRM123"),
    )
    confirm = await manager.async_configure(
        choice["flow_id"], {"bed_type_choice": "flexx_motion"}
    )
    profile = await manager.async_configure(
        confirm["flow_id"], {const.CONF_BED_TYPE: "flexx_motion"}
    )
    assert profile["step_id"] == "profile_questions"
    settings = await manager.async_configure(
        profile["flow_id"], {const.CONF_PROTOCOL_VARIANT: "PB450"}
    )
    assert settings["step_id"] == "finish_settings"
    client = make_client(1)
    if not roles_ok:
        # A writable endpoint alone cannot satisfy the app's notification role.
        client.services[0].characteristics.pop()
    client.disconnect = AsyncMock()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -53),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
    ):
        progress = await manager.async_configure(settings["flow_id"], form_answers(settings))
        report = await _advance_only_progress(hass, progress)
    assert report["step_id"] == "verify_connection", (progress, report)
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_awaited_once()
    message = report["description_placeholders"]["capabilities"]
    assert ("The app's connection type is available" in message) is roles_ok
    if not roles_ok:
        assert "change_app" in options_of(report["data_schema"].schema["action"])
    else:
        assert not report.get("errors")


async def test_unknown_alarm_mode_rejects_all_service_targets_before_any_write(hass):
    first, valid = await runtime(hass, "AFEG300")
    second, unknown = await runtime(hass, "AFEG300")
    for coord, mode in ((first, 0x45), (second, 0xFF)):
        notify(coord, "6e09010078")
        notify(coord, codec.record_20_len(5, 1, 2, (1, 0, 6, 30, mode, 1)).hex())
        coord.client.write_gatt_char.reset_mock()
    await services.async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(first, "both"), (second, "both")], []),
    ), raises_key("dreamsense_action"):
        await hass.services.async_call(
            const.DOMAIN,
            "flexx_motion_enable_alarm",
            {"device_id": ["first", "second"], "alarm_number": 1, "enabled": False},
            blocking=True,
        )
    first.client.write_gatt_char.assert_not_awaited()
    second.client.write_gatt_char.assert_not_awaited()
    valid.on_disconnect()
    unknown.on_disconnect()
