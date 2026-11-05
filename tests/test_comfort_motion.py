"""Comfort Motion 2.2.1 artifact vectors and its actual HA routes (row115)."""

from __future__ import annotations

import asyncio
from dataclasses import astuple
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds import comfort_motion as cm
from custom_components.adjustable_bed.codec.jiecang import TRANSPORTS
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.profiles.jiecang import COMFORT_MOTION

# Frozen Comfort Motion 2.2.1 literals.
RELEASE = bytes.fromhex("f1f14e004e7e")
LIGHT = bytes.fromhex("f1f10f000f7e")
WIRE_LEVELS = (0, 2, 3, 4)
MASSAGE = {
    "head": tuple(
        bytes.fromhex(value)
        for value in (
            "f1f1120208001c7e",
            "f1f1120208021e7e",
            "f1f1120208031f7e",
            "f1f112020804207e",
        )
    ),
    "foot": tuple(
        bytes.fromhex(value)
        for value in (
            "f1f1140208001e7e",
            "f1f114020802207e",
            "f1f114020803217e",
            "f1f114020804227e",
        )
    ),
}

ADDRESS = "AA:BB:CC:DD:EE:FF"


def services(transports=("g1",), properties=("write", "notify")):
    result = []
    for key in transports:
        service, write, notify, name = astuple(TRANSPORTS[key])
        chars = {
            uuid: SimpleNamespace(
                uuid=uuid,
                properties=properties,
                descriptors=[],
                handle=1,
                description="Comfort Motion role",
            )
            for uuid in (write, notify, name)
            if uuid
        }
        result.append(
            SimpleNamespace(
                uuid=service, get_characteristic=chars.get, characteristics=list(chars.values())
            )
        )
    return result


@pytest.fixture
def make_controller(monkeypatch):
    async def pause(_milliseconds, cancel):
        return cancel.is_set()

    monkeypatch.setattr(cm.ComfortMotionController, "_pause", staticmethod(pause))

    def make(layout="standard_2", transports=("g1",), **options):
        client = SimpleNamespace(
            services=services(transports),
            is_connected=True,
            write_gatt_char=AsyncMock(),
            start_notify=AsyncMock(),
            stop_notify=AsyncMock(),
        )
        coordinator = SimpleNamespace(
            client=client,
            address=ADDRESS,
            cancel_command=asyncio.Event(),
            motor_pulse_count=2,
            controller_state={},
            has_massage=True,
            record_command_trace=MagicMock(),
        )
        coordinator.handle_controller_state_updates = coordinator.controller_state.update
        return (
            cm.ComfortMotionController(coordinator, layout=layout, **options),
            coordinator,
            client,
        )

    return make


def packets(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    "zone,frames",
    [
        ("head", ["f1f1120208001c7e", "f1f1120208021e7e", "f1f1120208031f7e", "f1f112020804207e"]),
        ("foot", ["f1f1140208001e7e", "f1f114020802207e", "f1f114020803217e", "f1f114020804227e"]),
    ],
)


async def test_massage_vectors_are_not_optimistic(make_controller, zone, frames):
    controller, _, client = make_controller()
    for level in range(4):
        await controller.set_massage_intensity(zone, level)
    assert packets(client) == frames
    assert controller.get_massage_state()[f"{zone}_intensity"] == 0
    with pytest.raises(ValueError):
        await controller.set_massage_intensity(zone, 4)


async def test_setup_queries_without_layout_or_massage(make_controller):
    controller, coordinator, client = make_controller(transports=("g2",))
    coordinator.has_massage = False
    await controller.start_notify()
    await controller.start_notify()
    assert [offset for offset, _ in COMFORT_MOTION.bootstrap] == [200, 300, 400, 500, 600, 700]
    assert packets(client) == [
        "f1f1000101027e",
        "f1f1000101027e",
        "f1f1000140417e",
        "f1f1000140417e",
        "f1f1000108097e",
        "f1f1000108097e",
    ]
    assert client.start_notify.await_count == 1
    assert not controller.supports_device_rename
    await controller.stop_notify()
    client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("transport", ["g1", "g2"])
@pytest.mark.parametrize("layout", range(1, 7))
@pytest.mark.parametrize("light", [False, True])
async def test_all_24_variants_and_temporal_retention(make_controller, transport, layout, light):
    physical_layout = ("standard_2", "standard_3_neck", "standard_4_legacy")[(layout - 1) // 2]
    controller, coordinator, client = make_controller(
        physical_layout, (transport,), has_light=light
    )
    sender = SimpleNamespace(uuid=astuple(TRANSPORTS[transport])[2])
    controller._handle_notification(sender, bytearray([0, 0, 6, 0, 3, 0, 4, 0, 64]))
    specs = controller.motor_control_specs
    for reply in (layout, layout, 1, 0, 255):
        controller._handle_notification(sender, bytearray([0, 0, 15, 0, reply, 0, 0]))
        assert [s.key for s in controller.motor_control_specs] == [s.key for s in specs]
        assert controller.get_massage_state() == {"head_intensity": 2, "foot_intensity": 3}
        assert controller.get_light_state() == {"is_on": True}
    assert controller.protocol_diagnostics["reported_layout"] == 0
    assert controller.supports_lights is light
    client.is_connected = False
    with pytest.raises(ConnectionError):
        await controller.massage_head_down()
    client.is_connected = True
    await controller.massage_head_down()
    assert packets(client) == ["f1f1120208021e7e"]
    reconnected = cm.ComfortMotionController(coordinator, layout=physical_layout)
    assert reconnected.get_massage_state() == controller.get_massage_state()


@pytest.mark.parametrize("wire", range(256))
async def test_unsigned_massage_parser_and_steps(make_controller, wire):
    controller, _, client = make_controller()
    sender = SimpleNamespace(uuid=astuple(TRANSPORTS["g1"])[2])
    controller._handle_notification(sender, bytearray([0, 0, 6, 0, wire, 0, wire, 0, 0]))
    await controller.massage_head_up()
    await controller.massage_foot_down()
    expected = []
    if wire in (0, 2, 3):
        expected.append(MASSAGE["head"][WIRE_LEVELS.index(wire) + 1].hex())
    if wire in (2, 3, 4):
        expected.append(MASSAGE["foot"][WIRE_LEVELS.index(wire) - 1].hex())
    assert packets(client) == expected
    if wire not in WIRE_LEVELS:
        assert controller.get_massage_state() == {"head_intensity": None, "foot_intensity": None}


async def test_short_unknown_and_light_only_preserve_massage(make_controller):
    controller, _, _ = make_controller()
    sender = SimpleNamespace(uuid="test")
    for value in (b"", b"\x00\x00\x06", bytes(12), bytes.fromhex("00000f0001")):
        controller._handle_notification(sender, bytearray(value))
    controller._handle_notification(sender, bytearray.fromhex("000005000000000040"))
    assert controller.get_massage_state() == {"head_intensity": 0, "foot_intensity": 0}
    assert controller.get_light_state() == {"is_on": True}


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_motion_cancellation_releases_with_fresh_event(make_controller, task_cancel):
    controller, coordinator, client = make_controller()

    async def write(*args, **kwargs):
        if args[1] != RELEASE:
            coordinator.cancel_command.set()
            if task_cancel:
                raise asyncio.CancelledError

    client.write_gatt_char.side_effect = write
    if task_cancel:
        with pytest.raises(asyncio.CancelledError):
            await controller.move_back_up()
    else:
        await controller.move_back_up()
    assert packets(client)[-1] == "f1f14e004e7e"


async def test_setup_failure_cleans_subscriptions_and_reconnects(make_controller):
    controller, _, client = make_controller(transports=("g1", "g2"))
    client.write_gatt_char.side_effect = ConnectionError("link lost")
    with pytest.raises(ConnectionError):
        await controller.start_notify()
    assert client.stop_notify.await_count == 2
    client.services = services(("g2",))
    client.write_gatt_char.side_effect = None
    await controller.start_notify()
    assert not controller.supports_device_rename
    assert controller.control_characteristic_uuid == astuple(TRANSPORTS["g2"])[1]


async def test_runtime_properties_and_rename(make_controller):
    controller, _, client = make_controller(transports=("g1", "g2"))
    client.services = services(("g1", "g2"), ("write-without-response", "notify"))
    await controller.write_command(LIGHT)
    assert client.write_gatt_char.await_args.kwargs == {"response": False}
    assert controller.control_characteristic_uuid == astuple(TRANSPORTS["g2"])[1]
    await controller.rename_device("Bed_1.2")
    assert client.write_gatt_char.await_args.args == (astuple(TRANSPORTS["g1"])[3], b"Bed_1.2")
    assert client.write_gatt_char.await_args.kwargs == {"response": False}
    for invalid in ("", "A" * 19, "Bed 1", "sengø", "name\n"):
        with pytest.raises(ValueError):
            controller.validate_device_rename(invalid)


async def test_wake_routine_and_stop_are_distinct_from_release(make_controller):
    controller, _, client = make_controller()
    await controller.execute_wake_routine(preset="zero_g", head_level=1, foot_level=3)
    assert packets(client) == [
        "f1f1120208021e7e",
        "f1f14e004e7e",
        "f1f114020804227e",
        "f1f14e004e7e",
        "f1f1070101097e",
    ]
    await controller.stop_wake_routine()
    assert packets(client)[-1] == "f1f11101081a7e"
    with pytest.raises(ValueError):
        await controller.execute_wake_routine(preset="yoga", head_level=0, foot_level=0)


def entry_data(layout="standard_2", transport="g1"):
    return {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Comfort Motion",
        CONF_BED_TYPE: BED_TYPE_JIECANG_APP,
        CONF_JIECANG_APP_PROFILE: "comfort_motion",
        CONF_JIECANG_APP_LAYOUT: layout,
        CONF_JIECANG_APP_TRANSPORT: transport,
        CONF_HAS_LIGHT: True,
        CONF_HAS_MASSAGE: True,
        CONF_MOTOR_COUNT: 2,
        CONF_MOTOR_PULSE_COUNT: 1,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.mark.parametrize("options", [False, True])
async def test_profile_setup_and_options_reject_other_layouts(hass, options):
    if options:
        entry = MockConfigEntry(domain=DOMAIN, data=entry_data())
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.handler = entry.entry_id
        step = flow.async_step_settings
    else:
        flow = AdjustableBedConfigFlow()
        flow._manual_data = entry_data()
        step = flow.async_step_profile_questions
    flow.hass = hass
    flow.context = {}
    result = await step(
        {
            **entry_data(),
            CONF_JIECANG_APP_LAYOUT: "standard_4_bilateral",
            CONF_JIECANG_APP_TRANSPORT: "g3",
        }
    )
    # Configure sends a layout change to the guided change before validating it.
    assert result["errors"] == (
        {"base": "migration_reconfigure_required"}
        if options
        else {
            CONF_JIECANG_APP_LAYOUT: "comfort_motion_selection",
            CONF_JIECANG_APP_TRANSPORT: "comfort_motion_selection",
        }
    )


@pytest.mark.parametrize("layout", COMFORT_MOTION.layouts)
async def test_real_entities_services_and_serialization(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    make_controller,
    layout,
):
    mock_bleak_client.services.__iter__ = lambda self: iter(services())
    mock_bleak_client.write_gatt_char.side_effect = None
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(layout), unique_id=ADDRESS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    keys = {(e.domain, e.unique_id.removeprefix(f"{ADDRESS}_")): e.entity_id for e in entities}
    assert {key for domain, key in keys if domain == "cover"} == set(COMFORT_MOTION.layouts[layout])
    assert ("button", "preset_memory_2") in keys and ("button", "preset_memory_3") not in keys
    assert not any(
        "angle" in key or "position" in key
        for domain, key in keys
        if domain in ("sensor", "number")
    )
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(coordinator.controller, cm.ComfortMotionController)
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    with patch.object(
        coordinator,
        "async_execute_controller_command",
        wraps=coordinator.async_execute_controller_command,
    ) as execute:
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": keys["cover", "back"]}, blocking=True
        )
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": keys["number", "massage_head_intensity"], "value": 3},
            blocking=True,
        )
        device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": [device.id], "name": "Bed_1.2"}, blocking=True
        )
        await hass.services.async_call(
            DOMAIN,
            "jiecang_wake",
            {"device_id": [device.id], "preset": "flat", "head_level": 0, "foot_level": 0},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN, "jiecang_stop_wake", {"device_id": [device.id]}, blocking=True
        )
        coordinator.controller._handle_notification(
            SimpleNamespace(uuid="test"), bytearray.fromhex("000005000000000040")
        )
        await hass.services.async_call(
            "light", "turn_off", {"entity_id": keys["light", "under_bed_lights"]}, blocking=True
        )
        assert execute.await_count >= 6
    assert packets(client) == [
        "f1f1010101037e",
        "f1f14e004e7e",
        "f1f112020804207e",
        "4265645f312e32",
        "f1f10801010a7e",
        "f1f11101081a7e",
        "f1f10f000f7e",
    ]
    coordinator.controller._handle_notification(
        SimpleNamespace(uuid="test"), bytearray.fromhex("00000600ff00020040")
    )
    await hass.async_block_till_done()
    state = hass.states.get(keys["number", "massage_head_intensity"])
    assert state is not None and state.state == "unknown"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("layout", COMFORT_MOTION.layouts)
async def test_profile_setup_accepts_comfort_motion(hass, layout):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._manual_data = entry_data()
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({**entry_data(layout), CONF_JIECANG_APP_TRANSPORT: "g2"})
    saved = finish.call_args.args[0]
    assert saved[CONF_JIECANG_APP_PROFILE] == "comfort_motion"
    assert saved[CONF_JIECANG_APP_LAYOUT] == layout
    assert saved[CONF_JIECANG_APP_TRANSPORT] == "g2"
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True


async def test_light_feedback_and_unknown_state(make_controller):
    controller, _, client = make_controller()
    with pytest.raises(ValueError, match="Read light state"):
        await controller.lights_on()
    await controller.lights_toggle()
    assert controller.get_light_state() == {}
    sender = SimpleNamespace(uuid="test")
    controller._handle_notification(sender, bytearray.fromhex("000005000000000040"))
    await controller.lights_on()
    assert len(packets(client)) == 1
    await controller.lights_off()
    assert packets(client) == ["f1f10f000f7e"] * 2
    assert controller.get_light_state() == {"is_on": True}


async def test_setup_cancellation_cleans_without_cross_link_timers(make_controller):
    controller, coordinator, client = make_controller()

    async def write(*args, **kwargs):
        coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError, match="cancelled"):
        await controller.start_notify()
    assert packets(client) == ["f1f1000101027e"]
    client.stop_notify.assert_awaited_once()
    assert not controller._started


async def test_wake_task_cancellation_releases(make_controller):
    controller, _, client = make_controller()

    async def write(*args, **kwargs):
        if args[1] != RELEASE:
            raise asyncio.CancelledError

    client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await controller.execute_wake_routine(preset="flat", head_level=1)
    assert packets(client) == ["f1f1120208021e7e", "f1f14e004e7e"]


async def test_stop_notify_attempts_all_channels_after_error(make_controller):
    controller, _, client = make_controller(transports=("g1", "g2"))
    await controller.start_notify()
    client.stop_notify.side_effect = [ConnectionError("G1 unsubscribe failed"), None]
    with pytest.raises(ConnectionError):
        await controller.stop_notify()
    assert client.stop_notify.await_count == 2
    assert controller._subscriptions == []


async def test_disabled_light_has_no_controls(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, make_controller
):
    """Local light presence gates every platform, including toggle-only fallback."""
    mock_bleak_client.services.__iter__ = lambda self: iter(services())
    mock_bleak_client.write_gatt_char.side_effect = None
    entry = MockConfigEntry(
        domain=DOMAIN, data={**entry_data(), CONF_HAS_LIGHT: False}, unique_id=ADDRESS
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(entity.domain == "light" for entity in entities)
    assert not any(
        entity.unique_id.endswith(("_toggle_light", "_under_bed_lights")) for entity in entities
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
