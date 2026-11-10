"""Accepted row161 literal vectors and actual HA controller/service behavior."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.keeson.comfortbase import (
    NOTIFY_SERVICE,
    WRITE_SERVICE,
    ComfortBaseController,
)
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_COMFORTBASE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.profiles import comfortbase as app
from custom_components.adjustable_bed.profiles.keeson import COMFORTBASE, encode
from custom_components.adjustable_bed.setup_questions import _comfortbase_settings
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/comfortbase/vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:61"
STOP = "e6fe16000000000005"


@pytest.mark.parametrize("row", VECTORS["builders"], ids=lambda v: v["id"])
def test_frozen_builders(row):
    fields = row["inputs"]
    if row["builder"] == "control":
        actual = codec.frame(fields["command"], header=0xE6, side=fields["selector"])
    elif row["builder"] == "current_time":
        actual = codec.clock_fields(tuple(
            (fields["year"] - 1900) & 255 if k == "year" else fields[k] & 255
            for k in ("year", "month_zero", "day", "hour", "minute", "second")
        ))
    else:
        actual = codec.alarm_table(3, bytes(fields[k] & 255 for k in ("hour", "minute", "parameter3", "memory")))
    assert actual.hex() == row["expected_bytes"]


@pytest.mark.parametrize("row", VECTORS["notifications"], ids=lambda v: v["id"])
def test_frozen_notifications_and_documented_safe_assembly(row):
    assembler = codec.ComfortBaseAssembler()
    emitted = []
    for chunk in row["chunks"]:
        frame = assembler.feed(bytes.fromhex(chunk)) if chunk is not None else None
        if frame is not None:
            minutes = codec.comfortbase_timer(frame)
            emitted.append({"bytes": frame.hex(), "minutes": minutes, "selected": minutes})
    # Android replays an old prefix on the second tail (N16), and emits a
    # fabricated zero category on an empty tail (N20). HA consumes once.
    expected = row["expected"][:1] if row["id"] == "N16" else [] if row["id"] == "N20" else row["expected"]
    assert emitted == expected


def test_notification_prefix_is_bounded_and_direct_reply_invalidates_it():
    parser = codec.ComfortBaseAssembler()
    prefix = bytes.fromhex("f4fe16") + bytes(17)
    assert parser.feed(prefix) is None
    assert parser.feed(bytes(4)) is None
    assert parser.feed(bytes(3)) is None
    assert parser.feed(prefix) is None
    assert parser.feed(bytes(16)) == bytes(16)
    assert parser.feed(bytes(3)) is None


class Char:
    def __init__(self, uuid, properties):
        self.uuid, self.properties = uuid, properties
        self.handle = id(self) & 65535
        self.descriptors = []


def gatt(properties=("write",)):
    def service(uuid, char):
        return SimpleNamespace(uuid=uuid, characteristics=[char], get_characteristic=lambda key: char if key == char.uuid else None)

    return [
        service(WRITE_SERVICE, Char(KEESON_BASE_WRITE_CHAR_UUID, list(properties))),
        service(NOTIFY_SERVICE, Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])),
    ]


def entry(hass, product):
    data = {CONF_ADDRESS: ADDRESS, CONF_NAME: "ComfortBase", CONF_BED_TYPE: BED_TYPE_COMFORTBASE,
            CONF_PROTOCOL_VARIANT: product, CONF_DISABLE_ANGLE_SENSING: True,
            **_comfortbase_settings({CONF_PROTOCOL_VARIANT: product})}
    e = MockConfigEntry(domain=DOMAIN, title="ComfortBase", unique_id=ADDRESS, data=data)
    e.add_to_hass(hass)
    return e


async def controller(hass, client, product="odessa"):
    client.services = gatt()
    coordinator = AdjustableBedCoordinator(hass, entry(hass, product))
    await coordinator.async_connect()
    assert isinstance(coordinator.controller, ComfortBaseController)
    client.write_gatt_char.reset_mock()
    return coordinator.controller


def written(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("product", app.PRODUCTS)
async def test_product_setup_factory_gates(hass, product):
    data = _comfortbase_settings({CONF_PROTOCOL_VARIANT: product})
    c = await create_controller(MagicMock(hass=hass), BED_TYPE_COMFORTBASE, product, None)
    assert isinstance(c, ComfortBaseController)
    expected = app.PRODUCTS[product]
    assert tuple(s.key for s in c.motor_control_specs) == expected.axes
    assert data[CONF_MOTOR_COUNT] == len(expected.axes) - ("both" in expected.axes)
    assert data[CONF_HAS_MASSAGE] == c.supports_massage == expected.massage_light
    assert c.supports_lights == expected.massage_light
    assert c.supports_massage_mode_step_control == expected.massage_light
    assert c.supports_massage_intensity_step_control == expected.massage_light
    assert c.supports_massage_wave_direction_control == expected.massage_light
    assert not c.supports_single_address_pairing
    assert not c.supports_massage_toggle_control
    assert not c.supports_head_massage_intensity_step_control
    assert not c.supports_massage_off_control
    assert not c.supports_massage_intensity_preset_control
    assert c.memory_slot_count == 2 and c.supports_clock_sync
    assert len(c.controller_state_sensor_specs) == int(expected.massage_light)
    assert all(s.scheduler_resource == "*" for s in c.motor_control_specs)
    assert is_valid_variant_for_bed_type(BED_TYPE_COMFORTBASE, product)
    assert "ComfortBaseForBluetooth" in BED_TYPE_DISPLAY_NAMES[BED_TYPE_COMFORTBASE]
    assert CONF_MOTOR_COUNT in hidden_generic_fields(BED_TYPE_COMFORTBASE, product)
    assert per_side_profile(BED_TYPE_COMFORTBASE, product).variant_owned


@pytest.mark.parametrize("axis", app.AXES)
async def test_actual_motor_frames_and_stop(hass, mock_coordinator_connected, mock_bleak_client, axis):
    c = await controller(hass, mock_bleak_client)
    c._coordinator._motor_pulse_count = 1
    for direction in (True, False):
        mock_bleak_client.write_gatt_char.reset_mock()
        await c._move_motor(axis, direction)
        assert written(mock_bleak_client)[0] == encode(COMFORTBASE, app.AXES[axis][1 if direction else 2]).hex()
        assert written(mock_bleak_client)[-1] == STOP
    c._coordinator.cancel_command.set()
    await c.stop_all()
    assert written(mock_bleak_client)[-1] == STOP


async def test_task_cancellation_releases_with_fresh_event(hass, mock_coordinator_connected, mock_bleak_client):
    c = await controller(hass, mock_bleak_client)
    entered = asyncio.Event()

    async def block(_char, data, **kwargs):
        if data.hex() != STOP:
            entered.set()
            await asyncio.Event().wait()

    mock_bleak_client.write_gatt_char.side_effect = block
    task = asyncio.create_task(c.program_memory(1))
    await entered.wait()
    c._coordinator.cancel_command.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(mock_bleak_client)[-1] == STOP


async def test_preset_light_massage_single_shots(hass, mock_coordinator_connected, mock_bleak_client):
    c = await controller(hass, mock_bleak_client)
    for name in ("zero_g", "flat", "anti_snore"):
        await c._preset(name)
    for memory in (1, 2):
        await c.preset_memory(memory)
    await c.lights_toggle()
    await c.massage_mode_step()
    await c.massage_wave_next()
    await c.massage_wave_previous()
    await c.massage_intensity_up()
    await c.massage_intensity_down()
    words = [*app.PRESETS.values(), *app.MEMORY.values(), app.LIGHT_TOGGLE, *app.MASSAGE.values()]
    assert written(mock_bleak_client) == [encode(COMFORTBASE, word).hex() for word in words]


async def test_gatt_notify_and_reconnect_reset(hass, mock_coordinator_connected, mock_bleak_client):
    c = await controller(hass, mock_bleak_client)
    notify = mock_bleak_client.services[1].characteristics[0]
    c._notification(notify, bytearray.fromhex("0000000000000000b200"))
    assert c._coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 20
    c._notification(notify, bytearray.fromhex("f4fe160000000000000000000000000000000002"))
    c.on_disconnect()
    c._notification(notify, bytearray(3))
    assert c._coordinator.controller_state[MASSAGE_TIMER_MINUTES] is None
    mock_bleak_client.services = gatt(("write-without-response",))
    await c.lights_toggle()
    assert mock_bleak_client.write_gatt_char.call_args.kwargs["response"] is False
    mock_bleak_client.services[0].uuid = "wrong-parent"
    with pytest.raises(ConnectionError):
        await c.lights_toggle()


@pytest.mark.parametrize("product", ["odessa", "freestyle"])
async def test_ha_entities_and_alarm_service(hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch, product):
    mock_bleak_client.services = gatt()
    e = entry(hass, product)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def exists(platform, key):
        return registry.async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}") is not None

    assert exists("button", "comfortbase_save_flat")
    assert exists("button", "comfortbase_save_zero_g")
    assert exists("button", "comfortbase_save_anti_snore")
    assert exists("button", "program_memory_1") and exists("button", "program_memory_2")
    assert exists("button", "massage_wave_next") == (product != "freestyle")
    assert exists("sensor", "massage_timer") == (product != "freestyle")
    assert not exists("select", "massage_timer")
    assert not exists("switch", "under_bed_lights")
    if product == "odessa":
        for motor in ("elevate", "both"):
            entity_id = registry.async_get_entity_id("cover", DOMAIN, f"{ADDRESS}_{motor}")
            attributes = hass.states.get(entity_id).attributes
            assert attributes["hold_lease_mode"] == "stream"
            assert attributes["hold_lease_motor"] == motor
    dev = next(x.device_id for x in registry.entities.values() if x.config_entry_id == e.entry_id)
    now = datetime(2026, 11, 10, 2, 59, 3)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.keeson.comfortbase.dt_util.now", lambda: now)
    monkeypatch.setattr(app, "ALARM_DELAY_SECONDS", 0)
    for memory, frame in [(1, "ed8003071eff0e00000000000000005d"), (2, "ed8003071eff0f00000000000000005c")]:
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(DOMAIN, "comfortbase_set_alarm", {"device_id": dev, "enabled": True, "time": "07:30:00", "memory": memory}, blocking=True)
        assert written(mock_bleak_client) == ["e780017e0a0a023b03c5"] * 2 + [frame]
    mock_bleak_client.write_gatt_char.reset_mock()
    await hass.services.async_call(DOMAIN, "comfortbase_set_alarm", {"device_id": dev, "enabled": False}, blocking=True)
    assert written(mock_bleak_client) == ["ed80030000000000000000000000008f"]
    for bad in [{"enabled": True}, {"enabled": True, "time": "06:00:01"}]:
        mock_bleak_client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "comfortbase_set_alarm", {"device_id": dev, **bad}, blocking=True)
        assert not written(mock_bleak_client)
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("motor", ["elevate", "both"])
async def test_card_motor_service_renews_one_continuous_stream(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, motor
):
    """The actual card route outlives a finite batch without an intermediate STOP."""
    mock_bleak_client.services = gatt()
    e = entry(hass, "odessa")
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][e.entry_id]
    coordinator._motor_pulse_count = 1
    registry = er.async_get(hass)
    dev = next(x.device_id for x in registry.entities.values() if x.config_entry_id == e.entry_id)
    mock_bleak_client.write_gatt_char.reset_mock()

    async def renew():
        await hass.services.async_call(
            DOMAIN, "timed_move", {
                "device_id": dev, "motor": motor, "direction": "up", "duration_ms": 200,
                "hold_owner": "card", "hold_generation": 1,
            }, blocking=True,
        )

    with virtual_clock():
        start = asyncio.create_task(renew())
        for _ in range(5):
            await asyncio.sleep(0.1)
            await renew()
            assert not start.done()
            assert STOP not in written(mock_bleak_client)
        await start
    frames = written(mock_bleak_client)
    assert len(frames) > 5
    first_stop = frames.index(STOP)
    assert frames[:first_stop] == [encode(COMFORTBASE, app.AXES[motor][1]).hex()] * first_stop
    assert set(frames[first_stop:]) == {STOP}
    assert await hass.config_entries.async_unload(e.entry_id)
