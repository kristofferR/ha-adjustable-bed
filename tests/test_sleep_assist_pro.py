"""Frozen A16 carrier vectors and offline Home Assistant session checks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson.sleep_assist_pro import SleepAssistProController
from custom_components.adjustable_bed.codec import keeson, sleep_assist_pro, sleep_assistant
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles import sleep_assist_pro as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.form_helpers import finish_new_bed
from tests.hold_lease_wire import _tool, virtual_clock

if TYPE_CHECKING:
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

FIXTURE = json.loads((Path(__file__).parent / "fixtures/sleep_assist_pro.json").read_text())
DEVICES: dict[sleep_assist_pro.Route, str] = {
    "p1": "BASE-I4.test",
    "p2": "KSBT012345678901",
    "p3": "KSBT012345678",
    "p4": "KSWF012345678901",
    "p5": "kSslBed_test",
}


def encode_key(route: str, values: list) -> bytes:
    word, *params = values
    device = params[0] if params else ""
    seconds = params[1] if len(params) > 1 else 0
    return sleep_assist_pro.key(
        cast("sleep_assist_pro.Route", route.lower()), word, device, epoch_seconds=seconds
    )


@pytest.mark.parametrize("vector", FIXTURE["vectors"], ids=lambda v: v["id"])
def test_frozen_vectors(vector):
    name = vector["action"]
    inputs = vector["inputs"]
    match name:
        case "simple_rgb":
            actual = keeson.rgb(tuple(inputs))
        case "smart_brightness":
            actual = sleep_assistant.light(inputs[0], query=len(inputs) > 1)
        case "smart_rgb":
            actual = sleep_assistant.rgb(1, 1, *inputs)
        case "bed_clock":
            actual = sleep_assistant.clock(inputs)
        case _:
            actual = encode_key(vector["protocol"], inputs)
    assert actual.hex() == vector["expected_bytes"]


@pytest.mark.parametrize(
    ("protocol", "action", "inputs", "expected"),
    FIXTURE["keys"],
    ids=[f"{protocol}-{action}" for protocol, action, *_ in FIXTURE["keys"]],
)
def test_frozen_command_words(protocol, action, inputs, expected):
    names = {
        "foot_up": "feet_up",
        "foot_down": "feet_down",
        "tilt_up_or_side_b_head_up": "tilt_up",
        "tilt_down_or_side_b_head_down": "tilt_down",
        "bed_up_dawnhouse_layout": "bed_up",
        "bed_down_dawnhouse_layout": "bed_down",
        "zero_gravity": "zero_g",
        "massage_foot_zone_or_up": "massage_feet_up",
        "massage_head_zone_or_up": "massage_head_up",
        "massage_foot_down": "massage_feet_down",
        "anti_snore_preset": "anti_snore",
        "music_preset": "music",
        "relax_or_read_preset": "relax",
        "tv_preset": "tv",
        "one_button_sleep_or_bed_in": "bed_in",
        "demonstration_or_bed_out": "bed_out",
        "under_bed_light_toggle": "light_toggle",
    }
    assert app.WORDS[names.get(action, action)] == inputs[0]
    assert encode_key(protocol, inputs).hex() == expected


@pytest.mark.parametrize(("action", "data_hex", "expected"), FIXTURE["parsers"])
def test_frozen_feedback(action, data_hex, expected):
    data = bytes.fromhex(data_hex)
    match action:
        case "base_feedback":
            feedback = sleep_assist_pro.base_feedback(data)
            assert feedback is not None
            assert feedback.lamp == expected["lamp"]
            assert feedback.timer_minutes == {1: 20, 2: 30}[expected["led"]]
        case "parse_base_long":
            feedback = sleep_assist_pro.base_feedback(data)
            assert feedback == sleep_assist_pro.Feedback(
                lamp=bool(expected["lamp_level"]), timer_minutes=20
            )
            assert sleep_assist_pro.base_feedback(data[:-1]) is None
        case "split_dd_ee":
            assert [chunk.hex() for chunk in sleep_assistant.split_notifications(data)] == expected
        case "smart_massage22":
            assert (
                sleep_assist_pro.smart_massage_timer(data, hardware_218=True)
                == expected["ui_seconds"]
            )
            assert sleep_assist_pro.smart_massage_timer(data, hardware_218=False) is None
        case "legacy_versions":
            assert {
                key: sleep_assistant.version_fields(data_hex, kind)
                for kind, key in enumerate(("bt", "mcu", "dsp"), 1)
            } == expected


def selected(route, controls, *, light=False, name=""):
    return app.selected(
        {
            const.CONF_BLE_DEVICE_NAME: DEVICES[route],
            const.CONF_PRODUCT_TYPE: name,
            const.CONF_HAS_LIGHT: light,
            app.CONF_CONTROLS: controls,
        }
    )


@pytest.mark.parametrize("route", DEVICES)
def test_discovery_is_a_candidate_without_replacing_other_apps(route):
    info = SimpleNamespace(
        name=DEVICES[route],
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )
    result = detect_bed_type_detailed(info)
    assert const.BED_TYPE_SLEEP_ASSIST_PRO in {result.bed_type, *(result.ambiguous_types or ())}
    assert result.bed_type != const.BED_TYPE_SLEEP_ASSIST_PRO or result.confidence == 0.3
    assert app.route_for_id(info.name) == route


def test_catalog_gates_are_explicit():
    assert app.route_for_id("ksbt1234567😀") == "p3"
    assert app.route_for_id("KSBTshort") is None
    for route, controls, name in [
        ("p1", ["dawnhouse"], "Dawn House"),
        ("p4", ["dawnhouse"], ""),
        ("p4", ["rgb"], ""),
        ("p3", ["dimmer"], ""),
        ("p2", ["dimmer"], "ErgoSportive"),
        ("p3", ["tilt", "side_b"], ""),
    ]:
        with pytest.raises(ValueError, match=app.CONF_CONTROLS):
            selected(route, controls, light=True, name=name)
    assert selected("p3", ["dimmer"], light=True, name="ErgoSportive").controls == {"dimmer"}


async def test_manual_app_flow_requires_identity_and_remote_controls(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: "Sleep Assist Pro"})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:FF"})
    result = await finish_new_bed(
        flow,
        result,
        {
            const.CONF_BLE_DEVICE_NAME: DEVICES["p5"],
            app.CONF_CONTROLS: ["head"],
        },
    )
    assert result["type"] == "create_entry"
    saved = flow._finish_with_verify.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEP_ASSIST_PRO
    assert app.selected(saved).controls == {"head"}


def connected(profile, transports):
    mocked = _tool().FakeServices(
        {
            "services": {t.service_uuid: [t.write_uuid, t.notify_uuid] for t in transports},
            "properties": {
                **{t.write_uuid: ["write-without-response"] for t in transports},
                **{
                    t.notify_uuid: ["indicate" if profile.indication else "notify"]
                    for t in transports
                },
            },
        }
    )
    client = SimpleNamespace(
        services=mocked,
        is_connected=True,
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )
    updates = {}
    coordinator = SimpleNamespace(
        client=client,
        cancel_command=asyncio.Event(),
        motor_pulse_count=2,
        address="AA:BB:CC:DD:EE:FF",
        record_command_trace=lambda **_: None,
        handle_controller_state_updates=lambda *rows: updates.update(
            (update.key, update.value) for update in rows
        ),
    )
    controller = SleepAssistProController(cast("AdjustableBedCoordinator", coordinator), profile)
    return controller, coordinator, client, updates


@pytest.mark.parametrize("route", DEVICES)
async def test_hold_cancellation_and_route_cleanup(route, monkeypatch):
    profile = selected(route, ["head"])
    transport = app.TRANSPORTS[route][-1]
    c, coordinator, client, _ = connected(profile, (transport,))
    await c.async_discover_capabilities()
    await c.start_notify()
    assert client.start_notify.call_args.args[0].uuid == transport.notify_uuid
    assert client.start_notify.call_args.kwargs.get("force_indicate", False) == profile.indication
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.keeson.sleep_assist_pro.time.time",
        lambda: 1700000000,
    )

    with virtual_clock() as clock:
        # Stop during the first packet. A split JSON command must settle its
        # existing tail before release, with no second movement packet.
        times = []

        def written(*_args, **_kwargs):
            times.append(clock.time())
            coordinator.cancel_command.set()

        client.write_gatt_char.side_effect = written
        with pytest.raises(asyncio.CancelledError):
            await c.hold_control("head_up", 2000)
    payloads = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert all(
        call.args[0].uuid == transport.write_uuid and not call.kwargs["response"]
        for call in client.write_gatt_char.call_args_list
    )
    frame = sleep_assist_pro.key(route, 1, profile.device_id, epoch_seconds=1700000000)
    release = sleep_assist_pro.release(route, profile.device_id)
    assert b"".join(payloads) == frame + (release or b"")
    assert max(map(len, payloads)) <= 20
    assert round((times[-1] - times[0]) * 1000) == (800 if release else 0)


async def test_service_order_and_retired_callback():
    c, coordinator, client, updates = connected(
        selected("p1", ["head"], light=True), (app.NORDIC_0020, app.NORDIC_0001)
    )
    await c.async_discover_capabilities()
    await c.start_notify()
    char, receive = client.start_notify.call_args.args
    assert char.uuid == app.NORDIC_0020.notify_uuid
    receive(char, bytearray.fromhex("a50b0f025800000000000000010000000000"))
    assert updates[UNDER_BED_LIGHTS_ON] is True
    c.on_disconnect()
    assert updates[UNDER_BED_LIGHTS_ON] is None
    receive(char, bytearray.fromhex("a50b0f025800000000000000010000000000"))
    assert updates[UNDER_BED_LIGHTS_ON] is None

    _, _, other_client, _ = connected(c.profile, (app.A00A,))
    coordinator.client = other_client
    with pytest.raises(BleakError, match="GATT roles"):
        await c.async_discover_capabilities()


async def test_dawn_house_p5_exposes_in_out_only():
    c, _, client, _ = connected(selected("p5", ["dawnhouse"], name="DawnHouse"), (app.EE00,))
    assert c.held_control_options == ()
    assert {b.key for b in c.controller_button_specs} == {
        "sleep_assist_pro_bed_in",
        "sleep_assist_pro_bed_out",
    }
    with pytest.raises(ServiceValidationError):
        await c.hold_control("bed_up", 500)
    assert not client.write_gatt_char.called


def test_smart_marker_free_timer_and_signed_lamp():
    frame = bytearray(19)
    frame[15] = 2
    assert sleep_assist_pro.smart_feedback(bytes(frame), hardware_218=False).timer_minutes == 20
    frame[:4] = b"\xdd\xee\x0f\x01"
    frame[14] = 0x80
    assert sleep_assist_pro.smart_feedback(bytes(frame), hardware_218=True).lamp is False
    frame[14] = 0x40
    assert sleep_assist_pro.smart_feedback(bytes(frame), hardware_218=True).lamp is True


async def test_native_entities_use_only_selected_remote_controls(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.runtime_data import entry_runtime

    entry = await _setup_native_pro(
        hass, mock_bleak_client, "p3", ["head", "tv", "rgb", "massage_timer"], light=True
    )
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime.controller, SleepAssistProController)
    entities = [
        row for row in er.async_get(hass).entities.values() if row.config_entry_id == entry.entry_id
    ]
    assert [row.translation_key for row in entities if row.domain == "cover"] == ["back"]
    assert any(row.translation_key == "sleep_assist_pro_rgb_intensity" for row in entities)
    assert not any("program_memory" in row.unique_id for row in entities)
    button = next(row for row in entities if row.unique_id.endswith("sleep_assist_pro_tv"))
    with virtual_clock():
        await hass.services.async_call(
            "button", "press", {"entity_id": button.entity_id}, blocking=True
        )
    frames = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert frames[-2:] == [
        bytes.fromhex("aa03000a00040100400000baf355"),
        bytes.fromhex("aa03000a00040100000000faf355"),
    ]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rgb_requires_live_lamp_report_before_any_color_write():
    profile = selected("p3", ["rgb"], light=True)
    c, _, client, _ = connected(profile, (app.NORDIC_0001,))
    await c.async_discover_capabilities()
    await c.start_notify()
    char, receive = client.start_notify.call_args.args
    frame = bytearray(19)
    frame[0] = 0xDD
    receive(char, frame)
    with pytest.raises(ServiceValidationError, match="light is on"):
        await c.set_light_color((254, 253, 252))
    assert not client.write_gatt_char.called
    frame[14] = 0x40
    receive(char, frame)
    await c.set_light_color((254, 253, 252))
    assert (
        client.write_gatt_char.call_args.args[1].hex() == "aa010010000a01000000000101bb01020331ef55"
    )
    await c.set_rgb_intensity("60")
    assert client.write_gatt_char.call_args.args[1] == sleep_assistant.rgb(1, 1, 0, 1, 1)


async def _setup_native_pro(hass, client, route, controls, *, light=False, name=""):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant.common import MockConfigEntry

    profile = selected(route, controls, light=light, name=name)
    transport = app.TRANSPORTS[route][0]
    client.services = _tool().FakeServices(
        {
            "services": {transport.service_uuid: [transport.write_uuid, transport.notify_uuid]},
            "properties": {
                transport.write_uuid: ["write"],
                transport.notify_uuid: ["indicate" if profile.indication else "notify"],
            },
        }
    )
    if profile.indication:
        client.start_notify.side_effect = None  # The default mock only takes notify arguments.
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Bedroom",
        const.CONF_BED_TYPE: const.BED_TYPE_SLEEP_ASSIST_PRO,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_BLE_DEVICE_NAME: profile.device_id,
        app.CONF_CONTROLS: controls,
        const.CONF_HAS_LIGHT: light,
        const.CONF_PRODUCT_TYPE: name,
    }
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Bedroom", unique_id=data[CONF_ADDRESS], data=data
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("stall_cleanup", [False, True])
async def test_public_stop_regains_lane_after_stalled_gatt(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, stall_cleanup
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.errors import BedCommandTimedOutError

    entry = await _setup_native_pro(hass, mock_bleak_client, "p4", ["head"])
    registry = er.async_get(hass)
    cover = registry.async_get_entity_id("cover", const.DOMAIN, "AA:BB:CC:DD:EE:FF_back")
    stop = registry.async_get_entity_id("button", const.DOMAIN, "AA:BB:CC:DD:EE:FF_stop")
    assert cover is not None and stop is not None

    writes = []
    cancelled_at = []
    movement_admitted = asyncio.Event()
    with virtual_clock() as clock:

        async def write(char, data, *, response):
            index = len(writes)
            writes.append((char, data))
            movement_admitted.set()
            if index == 0 or (index == 1 and stall_cleanup):
                try:
                    # A cancellable backend retry that outlasts the command's budget.
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled_at.append(clock.time() - started)
                    raise

        mock_bleak_client.write_gatt_char.side_effect = write
        started = clock.time()
        move = asyncio.create_task(
            hass.services.async_call("cover", "open_cover", {"entity_id": cover}, blocking=True)
        )
        await movement_admitted.wait()
        await hass.services.async_call("button", "press", {"entity_id": stop}, blocking=True)
        assert clock.time() - started == pytest.approx(10.8 if stall_cleanup else 5.8)
        with pytest.raises(BedCommandTimedOutError):
            await move

    release = sleep_assist_pro.release("p4", DEVICES["p4"])
    assert release is not None
    char = mock_bleak_client.services.get_characteristic(app.A00A.write_uuid)
    expected_movement = sleep_assist_pro.key("p4", 1, DEVICES["p4"])[:20]
    assert all(wrote_char is char for wrote_char, _ in writes)
    assert writes[0][1] == expected_movement
    assert b"".join(payload for _, payload in writes[1:]) == (
        (release[:20] if stall_cleanup else b"") + release
    )
    assert cancelled_at == pytest.approx([5.0, 10.8] if stall_cleanup else [5.0])
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_rgb_and_brightness_only_clamp_to_ergo_sportive_minimum(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.runtime_data import entry_runtime

    entry = await _setup_native_pro(
        hass, mock_bleak_client, "p3", ["rgb", "dimmer"], light=True, name="ErgoSportive"
    )
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    light = next(row.entity_id for row in entities if row.domain == "light")
    char, receive = mock_bleak_client.start_notify.call_args.args
    frame = bytearray(19)
    frame[0], frame[14] = 0xDD, 0x40
    receive(char, frame)
    assert hass.states.get(light).state == "on"

    controller = entry_runtime(hass, entry.entry_id).controller
    assert isinstance(controller, SleepAssistProController)
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await controller.set_light_color_with_level((254, 253, 252), 12)
    mock_bleak_client.write_gatt_char.assert_not_awaited()

    with virtual_clock():
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": light,
                "rgb_color": (254, 253, 252),
                "brightness": 10,
            },
            blocking=True,
        )
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": light,
                "brightness": 1,
            },
            blocking=True,
        )
    assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
        bytes.fromhex("aa010010000a01000000000101bb01020331ef55"),
        sleep_assistant.light(13, query=False),
        sleep_assist_pro.release("p3"),
        sleep_assistant.light(13, query=False),
        sleep_assist_pro.release("p3"),
    ]
    assert hass.states.get(light).attributes["brightness"] == 13
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_pairing_menus_and_combine_repair_exclude_standalone_only_pro(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.repairs import CombineBedsRepairFlow

    entries = []
    for address in ("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            unique_id=address,
            state=ConfigEntryState.LOADED,
            data={CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_SLEEP_ASSIST_PRO},
        )
        entry.add_to_hass(hass)
        entries.append(entry)
    menu = await hass.config_entries.options.async_init(entries[0].entry_id)
    assert "pair_sides" not in menu["menu_options"]

    config_flow = AdjustableBedConfigFlow()
    config_flow.hass = hass
    assert (await config_flow.async_step_pair_beds())["reason"] == "not_enough_beds"

    repair_flow = CombineBedsRepairFlow()
    repair_flow.hass = hass
    result = await repair_flow.async_step_init()
    assert result["reason"] == "not_enough_beds"


@pytest.mark.parametrize("mode", [const.PAIR_MODE_SINGLE_ADDRESS, const.PAIR_MODE_SEPARATE_ADDRESS])
async def test_persisted_pro_pair_fails_before_ble_or_registry_setup(
    hass,
    enable_custom_integrations,
    mock_coordinator_connected,
    mock_establish_connection,
    mode,
    caplog,
):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.pairing import (
        build_pair_entry_data,
        build_single_address_pair_entry_data,
    )

    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
        const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_BASE,
    }
    if mode == const.PAIR_MODE_SINGLE_ADDRESS:
        pair = build_single_address_pair_entry_data(data, name="Paired")
        pair[const.CONF_BED_TYPE] = const.BED_TYPE_SLEEP_ASSIST_PRO
    else:
        pair = build_pair_entry_data(
            data, {**data, CONF_ADDRESS: "AA:BB:CC:DD:EE:02"}, name="Paired"
        )
        pair[const.CONF_PAIR_CHILDREN][1][const.CONF_BED_TYPE] = const.BED_TYPE_SLEEP_ASSIST_PRO
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Paired",
        unique_id=pair[const.CONF_PAIR_ID],
        data=pair,
        version=5,
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "Sleep Assist Pro beds must be set up as standalone entries." in caplog.text
    mock_establish_connection.assert_not_awaited()
    assert not dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
