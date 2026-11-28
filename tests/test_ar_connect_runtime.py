"""Full AR Connect vectors, live route gates and session-owned cancellation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ar_connect.controller import build_controller
from custom_components.adjustable_bed.beds.builder import BuildContext
from custom_components.adjustable_bed.codec import ar_connect as codec
from custom_components.adjustable_bed.codec.linak import control_frame, parse_ar_diagnostic
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import ar_connect as app
from custom_components.adjustable_bed.profiles import ar_headboard as hb
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import virtual_clock

ROOT = Path(__file__).parent / "fixtures/ar_connect"
TX = json.loads((ROOT / "app-vectors.json").read_text())
RX = json.loads((ROOT / "parser-vectors.json").read_text())
ERROR = json.loads((ROOT / "native-parser-vectors.json").read_text())


@pytest.mark.parametrize("row", TX, ids=lambda row: row["id"])
def test_full_literal_packets(row):
    key, args = row["id"], row["input"]
    name = key.split(".")[-1].replace("zeroGravity", "zero_g")
    if key.startswith(("recall.", "recall_slow.")):
        actual = control_frame(app.AR_CONNECT.recall_opcodes[app.PRESETS[name]], slow="slow" in key)
    elif key.startswith(("save.", "adapter_only.save.")):
        actual = control_frame(app.AR_CONNECT.save_opcodes[app.PRESETS[name]])
    elif key.startswith("startup_speed."):
        actual = dict(app.AR_CONNECT.custom_speed(1, 0))[name]
    elif key.startswith("gesture."):
        actual = control_frame(app.AR_CONNECT.stop_bed_opcode)
    elif key == "light.toggle":
        actual = control_frame(app.AR_CONNECT.light_toggle_opcode)
    elif key.endswith((".True", ".False")):
        actual = codec.state(args["state"])
    elif key.startswith("headboard.live."):
        actual = codec.live(codec.rgbw(tuple(args["color"]), args["tint"], args["brightness"]))
    elif key == "headboard.clock.local":
        actual = codec.clock(datetime.fromisoformat(args["local_datetime"]))
    elif key == "headboard.mood.five_steps":
        actual = codec.mood(True, 2, ((255, 0, 0, 0),) * 5)
    elif key == "headboard.routine.wake":
        actual = codec.routine(codec.Routine(True, "wake", 7, 30, 10, weekdays=("monday",)))
    else:
        actual = codec.remove(12)
    assert actual == bytes.fromhex(row["expected_hex"])


def test_all_incoming_literals_including_fragment_order():
    framer = codec.RoutineFramer()
    for row in RX:
        raw = bytes.fromhex(row["input_hex"])
        if row["id"].startswith("FF02"):
            value = codec.parse_live(raw)
            actual = codec.color(value) if value is not None else None
        else:
            actual = framer.feed(raw)
            if actual is not None:
                kind, value = actual
                actual = [
                    kind,
                    {key: routine.payload() for key, routine in value.items()}
                    if kind == "list"
                    else value,
                ]
        assert actual == row["expected"], row["id"]


@pytest.mark.parametrize("row", ERROR, ids=lambda row: row["id"])
def test_native_diagnostic_boundaries(row):
    if isinstance(row["expected"], str) and row["expected"].startswith("throws:"):
        with pytest.raises(ValueError):
            parse_ar_diagnostic(bytes.fromhex(row["input_hex"]))
    else:
        assert parse_ar_diagnostic(bytes.fromhex(row["input_hex"])) == (
            True if row["expected"] else None
        )


class Gatt:
    def __init__(self):
        self.services = {}
        self.reads = {}
        self.chars = {}

    def add(self, service, uuid, properties, value=b""):
        char = SimpleNamespace(
            uuid=uuid, properties=list(properties), handle=len(self.chars) + 1, descriptors=[]
        )
        svc = self.services.setdefault(service, SimpleNamespace(uuid=service, characteristics=[]))
        svc.characteristics.append(char)
        svc.get_characteristic = lambda key, svc=svc: next(
            (c for c in svc.characteristics if c.uuid == key), None
        )
        self.chars[uuid] = char
        self.reads[uuid] = value
        return char

    def get_service(self, uuid):
        return self.services.get(uuid)

    def get_characteristic(self, uuid):
        return self.chars.get(uuid)

    def __iter__(self):
        return iter(self.services.values())


def native_gatt(mask=0xC0, timer=False, config=True):
    g = Gatt()
    g.add(
        app.AR_CONNECT.control_service,
        app.AR_CONNECT.command_characteristic,
        ("write", "write-without-response"),
    )
    g.add("00001800-0000-1000-8000-00805f9b34fb", app.NAME_CHARACTERISTIC, ("read",), b"AR bed")
    if mask is not None:
        g.add(
            app.AR_CONNECT.reference_service,
            app.AR_CONNECT.reference_mask,
            ("read",),
            bytes([mask]),
        )
        for _axis, uuid in app.NATIVE_REFERENCES:
            g.add(app.AR_CONNECT.reference_service, uuid, ("read", "notify"), b"\0" * 4)
        g.add(
            app.AR_CONNECT.control_service,
            app.AR_CONNECT.error_characteristic,
            ("read", "notify"),
            b"",
        )
        if timer:
            g.add(app.TIMER_SERVICE, app.TIMER_EVENT, ("notify",))
    if config:
        g.add(
            app.AR_CONNECT.configuration_service,
            app.AR_CONNECT.configuration_characteristic,
            ("write",),
        )
    return g


def headboard_gatt(config=1):
    g = Gatt()
    routine = codec.Routine(True, "wake", 7, 30, 10, weekdays=("monday",))
    values = {
        "version": b'{"version":"1.0"}',
        "config": codec.compact_json({"config": config}),
        "advertising": b'{"timeout":30}',
        "pairing": b'{"timeout":60}',
        "live_state": b'{"livestat":false}',
        "mood_state": b'{"scenstat":false}',
        "live_values": b"1,2,3,4",
        "status": b'{"sysstat":"idle"}',
        "mood_values": codec.mood(True, 2, ((255, 0, 0, 0),) * 5),
        "routine": codec.compact_json(
            {"length": len(codec.compact_json({"12": routine.payload()}))}
        ),
    }
    for key, (service, uuid) in hb.TRANSPORTS.items():
        g.add(service, uuid, ("read", "write", "notify"), values.get(key, b""))
    return g


async def runtime(
    hass,
    route="native",
    *,
    mask=0xC0,
    config=1,
    timer=False,
    address="AA:BB:CC:DD:EE:12",
    layout="back_legs_head_feet",
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": address,
            "name": "AR Connect",
            "bed_type": "ar_connect",
            "protocol_variant": route,
            "product_type": layout,
            "motor_count": len(app.LAYOUTS[layout]),
            "has_massage": False,
            "disable_angle_sensing": True,
            "motor_pulse_count": 2,
        },
    )
    c = AdjustableBedCoordinator(hass, entry)
    g = native_gatt(mask, timer) if route == "native" else headboard_gatt(config)
    callbacks = {}
    client = MagicMock(is_connected=True, services=g)

    async def read(char):
        return bytearray(g.reads[char.uuid])

    async def subscribe(char, callback):
        callbacks[char.uuid] = callback

    client.read_gatt_char = AsyncMock(side_effect=read)
    client.start_notify = AsyncMock(side_effect=subscribe)
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    c._client = client
    ctrl = await build_controller(
        BuildContext(coordinator=c, bed_type="ar_connect", variant=route, client=client)
    )
    c._controller = ctrl
    await ctrl.async_discover_capabilities()
    session = SimpleNamespace(
        async_require_native_bond=AsyncMock(),
        async_start_notify=ctrl.start_notify,
        persist_capability_snapshot=MagicMock(),
    )
    with virtual_clock():
        await ctrl.async_on_connect(session)
    c.async_ensure_connected = AsyncMock(return_value=True)
    c._async_refresh_controller_auth = AsyncMock()
    return ctrl, c, client, callbacks, session


def writes(client):
    return [
        (call.args[0].uuid, bytes(call.args[1]), call.kwargs["response"])
        for call in client.write_gatt_char.call_args_list
    ]


@pytest.mark.parametrize(
    "mask,timer,model",
    [
        (None, False, "standard"),
        (0, False, "td3"),
        (0xC0, False, "advanced"),
        (0xC0, True, "advanced_with_alarm"),
    ],
)
async def test_native_live_admission_startup_and_subscription_order(hass, mask, timer, model):
    ctrl, c, client, callbacks, session = await runtime(hass, mask=mask, timer=timer)
    assert ctrl.model == model
    session.async_require_native_bond.assert_awaited_once()
    expected = ([app.TIMER_EVENT] if timer else []) + (
        [dict(app.NATIVE_REFERENCES)[a] for a in app.NATIVE_SUBSCRIBE_ORDER]
        + [app.AR_CONNECT.error_characteristic]
        if mask
        else []
    )
    assert [call.args[0].uuid for call in client.start_notify.call_args_list] == expected
    assert [row[1] for row in writes(client)] == [
        frame for _, frame in app.AR_CONNECT.custom_speed(1, 0)
    ]
    assert all(row[2] for row in writes(client))
    assert ctrl.link.ready


async def test_conditional_stop_quick_release_and_first_tick(hass):
    ctrl, c, client, _, _ = await runtime(hass, mask=None)
    client.write_gatt_char.reset_mock()
    with virtual_clock() as clock:
        await ctrl.stop_all()
        assert not writes(client)
        started = clock.now
        motion = asyncio.create_task(ctrl.hold_control("back_up", 1000))
        await asyncio.sleep(0.1)
        ctrl.on_gesture_release()
        await motion
        assert [row[1] for row in writes(client)] == [b"\xfe\0"]
        assert clock.now - started < 0.4
        await asyncio.sleep(0.2)
        client.write_gatt_char.reset_mock()
        await ctrl.hold_control("back_up", 1000)
        assert [row[1] for row in writes(client)] == [b"\x0b\0", b"\x0b\0", b"\xfe\0"]


async def test_native_memory_ui_gate_and_raw_peaceful_boundaries(hass):
    ctrl, c, client, _, _ = await runtime(hass)
    assert ctrl.is_memory_slot_programmable(1)
    assert not ctrl.is_memory_slot_programmable(2)
    assert ctrl.memory_slot_count == 4
    with pytest.raises(ServiceValidationError):
        await ctrl.program_memory(2)
    assert app.peaceful_directions({"head": 1, "back": 296, "legs": 104, "feet": 0}) == {
        "head": False,
        "back": True,
        "legs": False,
    }
    assert app.peaceful_directions({"head": 0, "back": 300, "legs": 100, "feet": 0}) == {}
    assert app.peaceful_directions({"back": 297, "legs": 103}) == {}
    assert app.peaceful_directions({"feet": -1}) == {"feet": True}


@pytest.mark.parametrize("route", ["native", "headboard"])
async def test_replaced_client_never_receives_old_writes_or_callback_state(hass, route):
    ctrl, c, client, callbacks, _ = await runtime(hass, route)
    old = ctrl.link
    c._client = MagicMock(is_connected=True)
    for uuid, callback in callbacks.items():
        callback(
            client.services.chars[uuid],
            bytearray(b'{"livestat":true}' if route == "headboard" else b"\xff\0\0\0"),
        )
    with pytest.raises(BedNotConnectedError):
        await ctrl.frame(old, "live_state" if route == "headboard" else "command", b"xx")
    c._client.write_gatt_char.assert_not_called()
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is not True


@pytest.mark.parametrize("config,lights", [(0, True), (1, True), (2, False), (3, True), (77, True)])
async def test_headboard_live_config_gates_and_explicit_response(hass, config, lights):
    ctrl, c, client, _, _ = await runtime(hass, "headboard", config=config)
    assert ctrl.supports_light_color_control is lights
    assert ctrl.alarm_capability is not None
    client.write_gatt_char.reset_mock()
    if lights:
        await ctrl.lights_on()
        await ctrl.set_light_color_rgbw((255, 0, 0, 0), 255)
        assert writes(client) == [
            (hb.TRANSPORTS["live_state"][1], b'{"state":true}', True),
            (hb.TRANSPORTS["live_values"][1], b'{"red":255,"green":0,"blue":0,"white":0}', True),
        ]
    else:
        with pytest.raises(ServiceValidationError):
            await ctrl.lights_on()
        assert not writes(client)


async def test_headboard_fragmented_list_and_non_atomic_update_failure(hass):
    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    routine = codec.Routine(True, "wake", 7, 30, 10, weekdays=("monday",))
    body = codec.compact_json({"12": routine.payload()})
    ctrl.receive("routine", body[:20])
    assert not ctrl.routines
    ctrl.receive("routine", body[20:])
    assert ctrl.routines == {"12": routine}
    client.write_gatt_char.reset_mock()

    async def fail_create(char, data, **kwargs):
        if char.uuid == hb.TRANSPORTS["routine"][1]:
            raise BleakError("write refused")

    client.write_gatt_char.side_effect = fail_create
    with virtual_clock(), pytest.raises(BleakError):
        await ctrl.put_routine(codec.Routine(True, "sleep", 22, 0, 5), "12")
    assert "12" not in ctrl.routines
    assert writes(client)[0][1] == b'{"id":12}'


async def test_failed_native_readiness_never_admits_motion(hass):
    ctrl, c, client, _, _ = await runtime(hass)
    ctrl.on_disconnect()
    await ctrl.async_discover_capabilities()
    session = SimpleNamespace(
        async_require_native_bond=AsyncMock(side_effect=ServiceValidationError("bond missing"))
    )
    with pytest.raises(ServiceValidationError):
        await ctrl.async_on_connect(session)
    with pytest.raises(BedNotConnectedError):
        await ctrl.move_back_up()


async def publish_runtime(hass, c):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import services

    c.entry.add_to_hass(hass)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=c.entry.entry_id, device_info=c.device_info
    )
    await services.async_register_services(hass)
    return device.id


async def test_public_native_cover_card_hold_and_save_gate(hass):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description

    ctrl, c, client, _, _ = await runtime(hass, mask=None)
    device_id = await publish_runtime(hass, c)
    client.write_gatt_char.reset_mock()
    cover = AdjustableBedCover(c, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    assert writes(client)[0][1] == b"\x0b\0"
    assert writes(client)[-1][1] == b"\xfe\0"
    assert cover.extra_state_attributes["held_control_up"] == "back_up"
    save = next(row for row in ctrl.controller_button_specs if row.key == "ar_connect_save_3")
    assert save.requires_confirmation and save.hold is None
    entity = ControllerActionButton(c, save)
    entity.async_write_ha_state = MagicMock()
    await entity.async_press()
    assert writes(client)[-1][1] == b"\x3a\0"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN, "save_preset", {"device_id": device_id, "preset": 2}, blocking=True
        )
    client.is_connected = False
    await c.async_shutdown()


async def test_public_headboard_light_clock_alarm_and_routine_actions(hass):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    device_id = await publish_runtime(hass, c)
    client.write_gatt_char.reset_mock()
    light = AdjustableBedLight(c, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(rgbw_color=(255, 0, 0, 0), brightness=128)
    assert writes(client)[0] == (hb.TRANSPORTS["live_state"][1], b'{"state":true}', True)
    assert json.loads(writes(client)[1][1]) == {"red": 128, "green": 0, "blue": 0, "white": 0}
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is True
    await hass.services.async_call(
        const.DOMAIN, "sync_clock", {"device_id": device_id}, blocking=True
    )
    assert writes(client)[-1][0] == hb.TRANSPORTS["clock"][1]
    await hass.services.async_call(
        const.DOMAIN,
        "set_alarm",
        {
            "device_id": device_id,
            "enabled": True,
            "time": "07:30:00",
            "duration": 10,
            "weekdays": ["monday"],
        },
        blocking=True,
    )
    value = json.loads(writes(client)[-1][1])
    assert value["mode"] == "wake" and value["hour"] == 7 and value["duration"] == 10
    await hass.services.async_call(
        const.DOMAIN,
        "ar_connect_routine",
        {
            "device_id": device_id,
            "action": "create",
            "mode": "sleep",
            "hour": 22,
            "minute": 45,
            "duration": 5,
        },
        blocking=True,
    )
    assert json.loads(writes(client)[-1][1])["mode"] == "sleep"
    await hass.services.async_call(
        const.DOMAIN,
        "ar_connect_mood",
        {
            "device_id": device_id,
            "repeat": True,
            "delay": 2,
            "colors": [{"hue": 0.5, "tint": 0.5, "brightness": 1}] * 5,
        },
        blocking=True,
    )
    value = json.loads(writes(client)[-1][1])
    assert value["colors"]["1"] == {"red": 255, "green": 0, "blue": 0, "white": 0}
    client.is_connected = False
    await c.async_shutdown()


async def test_stop_before_public_action_admission_suppresses_frame(hass):
    from custom_components.adjustable_bed import services

    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    device_id = await publish_runtime(hass, c)
    client.write_gatt_char.reset_mock()
    real = services._preflight_capability

    async def stopped(*args, **kwargs):
        result = await real(*args, **kwargs)
        await c.async_stop_command()
        return result

    with patch.object(services, "_preflight_capability", side_effect=stopped):
        await hass.services.async_call(
            const.DOMAIN,
            "ar_connect_routine",
            {"device_id": device_id, "action": "create", "mode": "wake", "hour": 7, "duration": 5},
            blocking=True,
        )
    assert not writes(client)
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("kind", ["write", "read", "subscribe"])
async def test_partial_initialization_failure_keeps_commands_unready(hass, kind):
    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    await ctrl.stop_notify()
    await ctrl.async_discover_capabilities()
    if kind == "write":
        client.write_gatt_char.side_effect = BleakError("write refused")
    elif kind == "read":
        client.read_gatt_char.side_effect = BleakError("read refused")
    else:
        client.start_notify.side_effect = BleakError("notify refused")
    session = SimpleNamespace(
        async_start_notify=ctrl.start_notify, persist_capability_snapshot=MagicMock()
    )
    with virtual_clock(), pytest.raises(BleakError):
        await ctrl.async_on_connect(session)
    assert not ctrl.link.ready
    with pytest.raises(BedNotConnectedError):
        await ctrl.lights_on()


async def test_native_hold_cancellation_and_ble_lane_deadline(hass):
    ctrl, c, client, _, _ = await runtime(hass, mask=None)
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        task = asyncio.create_task(ctrl.hold_control("back_up", 5000))
        await asyncio.sleep(0.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert writes(client)[-1][1] == b"\xfe\0"
        await asyncio.sleep(0.2)
        client.write_gatt_char.reset_mock()
        await ctrl.ble_lock.acquire()
        task = asyncio.create_task(ctrl.hold_control("back_up", 600))
        await asyncio.sleep(0.9)
        ctrl.ble_lock.release()
        await task
        assert [row[1] for row in writes(client)] == [b"\xfe\0"]


def test_app_hue_palette_is_not_an_invented_hsv_wheel():
    assert codec.hue_rgb(0) == (0, 0, 1)
    assert codec.hue_rgb(0.5) == (1, 0, 0)
    assert codec.hue_rgb(1) == pytest.approx((0, 1, 0))
    assert codec.rgbw(codec.hue_rgb(0.5), 0.5, 1) == (255, 0, 0, 0)


@pytest.mark.parametrize(
    "transport,proof,paired,accepted",
    [
        ("local", True, None, True),
        ("local", False, None, False),
        ("proxy", False, True, True),
        ("proxy", False, False, False),
        ("unknown", False, None, False),
        (None, False, None, False),
    ],
)
async def test_live_native_bond_admission_is_route_owned(hass, transport, proof, paired, accepted):
    from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
    from custom_components.adjustable_bed.coordinator_connection import _ConnectSession

    _, c, client, _, _ = await runtime(hass)
    c._connection_path = ConnectionPath("route", TransportClass(transport)) if transport else None
    c._async_observe_native_bond = AsyncMock(return_value=proof)
    c._record_native_bond_attempt = MagicMock()
    client.pair = AsyncMock(return_value=paired)
    session = _ConnectSession(c, client, {}, c.connection_generation)
    if accepted:
        await session.async_require_native_bond()
    else:
        with pytest.raises(ServiceValidationError):
            await session.async_require_native_bond()
    assert client.pair.await_count == (1 if transport == "proxy" or transport == "local" and not proof else 0)
    assert c._record_native_bond_attempt.call_count == (
        1 if transport == "proxy" and accepted else 0
    )
    client.read_gatt_char.reset_mock()
    c._async_observe_native_bond = AsyncMock(return_value=False)
    assert not await c._async_verify_bonded()
    client.read_gatt_char.assert_not_awaited()


async def test_stale_headboard_disconnect_cannot_erase_replacement_state(hass):
    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    c._controller = MagicMock()
    c.controller_state[UNDER_BED_LIGHTS_ON] = True
    ctrl.on_disconnect()
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is True


@pytest.mark.parametrize("response", [True, False])
async def test_native_write_mode_uses_current_selected_characteristic(hass, response):
    ctrl, _, client, _, _ = await runtime(hass, mask=None)
    client.write_gatt_char.reset_mock()
    char = ctrl.link.roles["command"]
    char.properties = ["write"] if response else ["write-without-response"]
    await ctrl.lights_toggle()
    assert writes(client) == [(app.AR_CONNECT.command_characteristic, b"\x94\0", response)]


@pytest.mark.parametrize("route", ["native", "headboard"])
async def test_profile_setup_discovery_and_explicit_recommendation_are_owned(hass, route):
    from custom_components.adjustable_bed.detection import (
        detect_bed_type_detailed,
        get_bed_type_options,
    )
    from custom_components.adjustable_bed.profile_id import profile_route, resolve_profile_id
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    data = {"bed_type": "ar_connect", "protocol_variant": route, "product_type": "back_legs_feet"}
    profile = setup_profile_for(data)
    assert profile is not None
    assert profile.settled(data)["motor_count"] == 3
    assert profile.settled(data)["has_massage"] is False
    assert profile_route(resolve_profile_id(data)).variant == route
    assert any("AR Connect" in row["label"] for row in get_bed_type_options())
    info = MagicMock(
        service_uuids=[app.AR_CONNECT.control_service] if route == "native" else [],
        manufacturer_data={},
        service_data={},
        address="AA:BB:CC:DD:EE:12",
    )
    info.name = "Bed 1234" if route == "native" else "My DOSseret light"
    found = detect_bed_type_detailed(info)
    assert found.bed_type == "ar_connect" or "ar_connect" in found.ambiguous_types
    assert recommend_profile(data, info, {}) is None
    if route == "headboard":
        assert profile.seed is not None
        assert profile.seed(hass, {}, info)["protocol_variant"] == "headboard"
        assert (
            profile.seed(hass, {"protocol_variant": "native"}, info)["protocol_variant"] == "native"
        )


async def test_shared_alarm_cannot_fake_turning_off_a_returned_record(hass):
    ctrl, c, client, _, _ = await runtime(hass, "headboard")
    device_id = await publish_runtime(hass, c)
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {"device_id": device_id, "enabled": False, "time": "07:30:00", "duration": 10},
            blocking=True,
        )
    assert not writes(client)
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("route", ["native", "headboard"])
async def test_real_entry_setup_exposes_only_route_entities_and_unloads(
    hass, route, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from dataclasses import replace

    from homeassistant.helpers import entity_registry as er

    g = native_gatt() if route == "native" else headboard_gatt()
    client = mock_bleak_client
    client.services = g
    client.read_gatt_char = AsyncMock(side_effect=lambda char: bytearray(g.reads[char.uuid]))
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        unique_id="AA:BB:CC:DD:EE:99",
        title="AR Connect",
        version=5,
        data={
            "address": "AA:BB:CC:DD:EE:99",
            "name": "AR Connect",
            "bed_type": "ar_connect",
            "protocol_variant": route,
            "motor_count": 2,
            "product_type": "back_legs",
            "has_massage": False,
            "disable_angle_sensing": True,
            "connection_mode": "always",
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_connection._ConnectSession.async_require_native_bond",
            new_callable=AsyncMock,
        ),
        patch.object(app, "STARTUP_DELAY_S", 0),
        patch.object(app, "AR_CONNECT", replace(app.AR_CONNECT, custom_speed_post_write_ms=0)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    c = hass.data[const.DOMAIN][entry.entry_id]
    assert c.controller is not None and c.controller.link.ready
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    keys = {entity.unique_id for entity in entities}
    if route == "native":
        assert any(key.endswith("_back") for key in keys)
        assert any(key.endswith("_preset_zero_g") for key in keys)
        assert not any(key.endswith("_ar_connect_save_2") for key in keys)
        assert not any(key.endswith("_ar_headboard_mood_on") for key in keys)
    else:
        assert any(entity.domain == "light" for entity in entities)
        assert any(key.endswith("_ar_headboard_mood") for key in keys)
        assert not any(entity.domain == "cover" for entity in entities)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert client.stop_notify.await_count > 0


async def test_optional_probe_preserves_address_wide_count_and_declares_sections(hass):
    ctrl, c, client, callbacks, _ = await runtime(hass)
    ctrl.axes = ("back", "legs")
    c._motor_count = 2
    client.write_gatt_char.reset_mock()
    back = callbacks[dict(app.NATIVE_REFERENCES)["back"]]
    with virtual_clock():
        task = asyncio.create_task(ctrl.probe_options())
        # The app counts matching-address traffic, even from another section.
        await asyncio.sleep(0.1)
        for _ in range(10):
            back(None, bytearray(4))
        await task
    assert ctrl.axes == ("back", "legs", "head")
    assert {spec.key for spec in ctrl.motor_control_specs} == {"back", "legs", "head"}
    assert [row[1] for row in writes(client)] == [
        bytes.fromhex(value)
        for value in ("0300", "fe00", "0200", "fe00", "0500", "fe00", "0400", "fe00")
    ]


async def test_identification_timing_and_cancelled_probe_release(hass):
    ctrl, c, client, _, _ = await runtime(hass)
    client.write_gatt_char.reset_mock()
    moments = []
    with virtual_clock() as clock:
        client.write_gatt_char.side_effect = lambda *a, **kw: moments.append(round(clock.now, 3))
        start = clock.now
        await ctrl.identify_side()
        assert [round(value - start, 3) for value in moments] == [0, 5, 5.5, 10.5]
        client.write_gatt_char.reset_mock()
        task = asyncio.create_task(ctrl.probe_options())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert [row[1] for row in writes(client)] == [b"\x03\0", b"\xfe\0"]


@pytest.mark.parametrize('silent', [False, True])
async def test_silent_selection_survives_controller_rebuild_and_sets_motion_flag(hass, silent):
    from custom_components.adjustable_bed.beds.ar_connect.native import NativeController

    ctrl, c, client, _, _ = await runtime(hass, mask=None)
    assert isinstance(ctrl, NativeController)
    await publish_runtime(hass, c)
    client.write_gatt_char.reset_mock()
    spec = ctrl.controller_switch_specs[0]
    await c.async_execute_controller_command(lambda current: spec.set_fn(current, silent))
    assert not writes(client) and ctrl.silent is silent
    ctrl.on_disconnect()
    c._position_connection_generation += 1
    ctrl = type(ctrl)(c, ctrl.layout)
    c._controller = ctrl
    await ctrl.async_discover_capabilities()
    session = SimpleNamespace(
        async_require_native_bond=AsyncMock(), async_start_notify=ctrl.start_notify,
        persist_capability_snapshot=MagicMock(),
    )
    with virtual_clock():
        await ctrl.async_on_connect(session)
    assert ctrl.silent is silent
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.async_execute_controller_command(
            lambda current: current.hold_control("back_up", 600)
        )
    assert [row[1] for row in writes(client)] == [bytes((0x0B, 0x40 if silent else 0)), b"\xfe\0"]
    client.is_connected = False
    await c.async_shutdown()


async def test_created_identity_does_not_invent_a_stored_routine_or_count(hass):
    from custom_components.adjustable_bed.beds.ar_connect.headboard import (
        ROUTINE_COUNT,
        ROUTINE_LIST,
    )

    ctrl, c, _, _, _ = await runtime(hass, "headboard")
    for row in RX:
        if row["id"].startswith("FD01.") and row["id"] not in ("FD01.created", "FD01.deleted"):
            ctrl.receive("routine", bytes.fromhex(row["input_hex"]))
    assert c.controller_state.get(ROUTINE_COUNT) == 1
    ctrl.receive("routine", b'{"createid":13}')
    assert c.controller_state.get(ROUTINE_COUNT) is None
    assert c.controller_state.get(ROUTINE_LIST) is None
    assert "13" not in ctrl.routines and not ctrl._routine_list_received.is_set()
